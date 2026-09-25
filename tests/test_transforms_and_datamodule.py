"""Verification of ocuval.data.transforms and ocuval.data.datamodule.

Covers TC-044 (per-volume window at ingestion), TC-045 (frames inherit it),
TC-046 (declared target spacing), TC-047 (axial axis only), TC-048 (native geometry).

Everything here is synthetic. The fixtures are written in the *source* conventions --
raw integer intensities at two bit depths, spacing in (axial, lateral, separation) with
the axial component genuinely the finest -- because a fixture written in the consuming
code's convention cannot test a conversion (docs/07 section 3 rule 7).
"""

from __future__ import annotations

import numpy as np
import pytest

from ocuval.data.datamodule import (
    assert_window_inheritance,
    build_frame_split,
    check_manifest,
    frame_counts_from_manifest,
    frame_records,
)
from ocuval.data.splits import Sample, leave_one_vendor_out
from ocuval.data.transforms import (
    ApplyStoredIntensityWindowd,
    ResampleAxiald,
    eval_transforms,
    invert_axial_resample,
    train_transforms,
)
from ocuval.io.retouch_reader import apply_intensity_window, intensity_window

CFG = {
    "run": {"seed": 20260916},
    "data": {
        "roi_size": [576, 512],
        "mode": "2d",
        "preprocessing": {"axial_spacing_mm": 0.004, "intensity_percentiles": [1.0, 99.0]},
    },
}

# Real measured spacings, in this project's (axial, lateral, separation) order.
SPACING = {
    "cirrus": (0.001955, 0.011742, 0.046878),
    "spectralis": (0.003872, 0.010856, 0.116380),
    "topcon": (0.002600, 0.011720, 0.046880),
}


def frame(height=1024, width=512, seed=0, pedestal=0, bits=8):
    rng = np.random.default_rng(seed)
    signal = rng.random((height, width))
    top = 200 if pedestal else (255 if bits == 8 else 65535)
    scaled = signal * top + pedestal
    return scaled.astype(np.uint8 if bits == 8 else np.uint16)


# --- TC-044: the window is a property of the volume, computed from raw -------------


def test_TC_044_window_is_the_first_and_ninetyninth_percentile():
    volume = frame(seed=1)
    low, high = intensity_window(volume)
    assert low == pytest.approx(float(np.percentile(volume, 1)))
    assert high == pytest.approx(float(np.percentile(volume, 99)))


def test_TC_044_applying_the_window_maps_it_onto_zero_one_and_clips():
    volume = frame(seed=2)
    window = intensity_window(volume)
    out = apply_intensity_window(volume, window)
    assert out.min() == 0.0 and out.max() == 1.0
    assert out.dtype == np.float32
    # Values outside the window are clipped, not extrapolated.
    assert apply_intensity_window(np.array([window[0] - 50]), window)[0] == 0.0
    assert apply_intensity_window(np.array([window[1] + 50]), window)[0] == 1.0


def test_TC_044_eight_and_sixteen_bit_of_one_signal_normalise_alike():
    """The bit depth is a property of the container, not of the signal."""
    rng = np.random.default_rng(3)
    signal = rng.random((4, 64, 64))
    a8 = (signal * 255).astype(np.uint8)
    a16 = (signal * 65535).astype(np.uint16)
    n8 = apply_intensity_window(a8, intensity_window(a8))
    n16 = apply_intensity_window(a16, intensity_window(a16))
    # They cannot agree more closely than 8-bit quantisation permits.
    assert np.abs(n8 - n16).max() < 1.0 / 255


def test_TC_044_a_detector_pedestal_is_removed_exactly():
    """The topcon case: p1 = 35/255 is an offset, not tissue.

    Dtype-max scaling preserves it and hands the network a brightness offset perfectly
    correlated with vendor. The window removes it.
    """
    base = frame(height=64, seed=4, pedestal=0, bits=8)
    base = (base.astype(np.float64) * 200 / 255).astype(np.uint8)
    raised = (base.astype(np.int32) + 35).astype(np.uint8)

    assert int(np.median(raised)) - int(np.median(base)) == 35  # the defect is present

    n_base = apply_intensity_window(base, intensity_window(base))
    n_raised = apply_intensity_window(raised, intensity_window(raised))
    assert np.abs(n_base - n_raised).max() == pytest.approx(0.0, abs=1e-6)

    # And dtype-max scaling does NOT remove it — this is why the window exists.
    assert np.abs(base / 255.0 - raised / 255.0).max() > 0.1


def test_TC_044_degenerate_window_is_rejected_not_rescaled():
    with pytest.raises(ValueError, match="degenerate"):
        intensity_window(np.full((8, 8), 7, dtype=np.uint8))


def test_TC_044_transform_never_computes_a_window():
    """Absent window raises. A fallback would give a plausible image and an
    unreproducible normalisation."""
    transform = ApplyStoredIntensityWindowd(keys=("image",))
    with pytest.raises(KeyError, match="no 'intensity_window'"):
        transform({"image": frame(height=8, width=8)})


# --- TC-045: inheritance across expansion ------------------------------------------


def manifest_rows(n_per_vendor=3, frames=5):
    rows = []
    for vendor in ("cirrus", "spectralis", "topcon"):
        for i in range(n_per_vendor):
            rows.append(
                {
                    "sample_id": f"{vendor}-{i}",
                    "patient_id": f"{vendor}-P{i}",
                    "vendor": vendor,
                    "shape": [frames, 64, 32],
                    "spacing_mm": list(SPACING[vendor]),
                    "intensity_window": [float(10 * i), float(200 + i)],
                    "source_path": f"/raw/{vendor}/{i}",
                }
            )
    return rows


def resolved_split(rows, held_out="spectralis"):
    samples = [Sample(r["sample_id"], r["patient_id"], r["vendor"]) for r in rows]
    return leave_one_vendor_out(
        samples,
        held_out,
        val_fraction=0.34,
        seed=1,
        fold_id=f"{held_out}_holdout",
        ref_fraction=0.34,
    )


def test_TC_045_every_frame_carries_its_volumes_window():
    rows = manifest_rows()
    split = resolved_split(rows)
    frame_split = build_frame_split(split, rows)
    by_id = {r["sample_id"]: tuple(r["intensity_window"]) for r in rows}
    for bucket in ("train", "val", "test"):
        records = frame_records(rows, frame_split, bucket)
        assert records
        for record in records:
            assert record["intensity_window"] == by_id[record["sample_id"]]
        assert_window_inheritance(records, rows)


def test_TC_045_a_frame_with_the_wrong_window_is_detected():
    """The assertion must fail on the thing it exists to catch."""
    rows = manifest_rows()
    frame_split = build_frame_split(resolved_split(rows), rows)
    records = frame_records(rows, frame_split, "train")
    records[0] = {**records[0], "intensity_window": (999.0, 1000.0)}
    with pytest.raises(AssertionError, match="do not carry their volume's intensity window"):
        assert_window_inheritance(records, rows)


def test_TC_045_frame_counts_come_from_the_manifest_shape():
    rows = manifest_rows(frames=7)
    assert set(frame_counts_from_manifest(rows).values()) == {7}


def test_TC_045_manifest_missing_the_window_is_refused():
    rows = manifest_rows()
    del rows[0]["intensity_window"]
    with pytest.raises(KeyError, match="intensity_window"):
        check_manifest(rows)


def test_TC_045_a_frame_whose_volume_is_absent_raises_rather_than_being_skipped():
    """Silently skipping would shrink a split without changing its apparent size."""
    rows = manifest_rows()
    split = resolved_split(rows)
    frame_split = build_frame_split(split, rows)
    # Drop a volume that is genuinely in the bucket being read, not just any row.
    dropped = split.test[0]
    thinned = [r for r in rows if r["sample_id"] != dropped]
    assert len(thinned) == len(rows) - 1
    with pytest.raises(KeyError, match="not in the manifest"):
        frame_records(thinned, frame_split, "test")


# --- TC-046: the target spacing is declared, not derived ---------------------------


def test_TC_046_target_comes_from_the_configuration():
    sample = {
        "image": frame(height=1024, width=64),
        "spacing_mm": SPACING["cirrus"],
        "intensity_window": (0.0, 220.0),
    }
    out = eval_transforms(CFG, keys=("image",))(dict(sample))
    assert float(out["spacing_mm"][0]) == CFG["data"]["preprocessing"]["axial_spacing_mm"]


def test_TC_046_two_folds_use_the_identical_target():
    """A target derived from the data would vary with fold membership."""
    made = []
    for vendor in ("cirrus", "topcon"):
        sample = {
            "image": frame(height=512, width=64),
            "spacing_mm": SPACING[vendor],
            "intensity_window": (0.0, 220.0),
        }
        made.append(float(eval_transforms(CFG, keys=("image",))(sample)["spacing_mm"][0]))
    assert made[0] == made[1] == 0.004


def test_TC_046_missing_declared_constant_raises_rather_than_defaulting():
    broken = {"data": {"roi_size": [576, 512]}}
    with pytest.raises(KeyError, match="axial_spacing_mm|preprocessing"):
        eval_transforms(broken, keys=("image",))


def test_TC_046_target_is_at_or_above_every_measured_axial_spacing():
    """The coarsest choice: no volume is ever upsampled, because upsampling fabricates
    detail and would substitute a smoothness signature for the brightness one."""
    target = CFG["data"]["preprocessing"]["axial_spacing_mm"]
    for vendor, spacing in SPACING.items():
        assert spacing[0] <= target, vendor


# --- TC-047: only the axial axis ----------------------------------------------------


def test_TC_047_lateral_spacing_is_unchanged():
    sample = {
        "image": frame(height=512, width=64),
        "spacing_mm": SPACING["cirrus"],
        "intensity_window": (0.0, 220.0),
    }
    out = eval_transforms(CFG, keys=("image",))(dict(sample))
    assert float(out["spacing_mm"][1]) == SPACING["cirrus"][1]


def test_TC_047_separation_does_not_affect_the_result():
    """Training is 2D and frames are independent, so separation must not reach the
    chain. Two samples differing only in separation must produce identical frames."""
    image = frame(height=512, width=64, seed=9)
    axial, lateral, _ = SPACING["cirrus"]
    a = eval_transforms(CFG, keys=("image",))(
        {
            "image": image.copy(),
            "spacing_mm": (axial, lateral, 0.0469),
            "intensity_window": (0.0, 220.0),
        }
    )
    b = eval_transforms(CFG, keys=("image",))(
        {
            "image": image.copy(),
            "spacing_mm": (axial, lateral, 0.1286),
            "intensity_window": (0.0, 220.0),
        }
    )
    assert np.array_equal(a["image"].numpy(), b["image"].numpy())


def test_TC_047_axial_resampling_changes_the_height_in_the_right_direction():
    """Non-identity on the fixture: a conversion that did nothing would pass otherwise."""
    image = frame(height=1024, width=64)
    out = ResampleAxiald(keys=("image",), target_axial_mm=0.004)(
        {"image": image[None], "spacing_mm": SPACING["cirrus"]}
    )
    # cirrus is finer than the target, so it must be DOWNsampled.
    assert out["image"].shape[-2] < 1024
    assert out["image"].shape[-2] == round(1024 * SPACING["cirrus"][0] / 0.004)
    assert out["image"].shape[-1] == 64  # lateral untouched


def test_TC_047_all_vendors_converge_to_the_same_output_shape():
    shapes = set()
    for vendor, height in (("cirrus", 1024), ("spectralis", 496), ("topcon", 885)):
        out = eval_transforms(CFG, keys=("image",))(
            {
                "image": frame(height=height, width=512),
                "spacing_mm": SPACING[vendor],
                "intensity_window": (0.0, 220.0),
            }
        )
        shapes.add(tuple(out["image"].shape))
    assert shapes == {(1, 576, 512)}


def test_TC_047_labels_are_resampled_without_inventing_a_class():
    label = np.zeros((1, 1024, 64), dtype=np.uint8)
    label[0, 100:200, 10:30] = 2
    label[0, 400:450, 10:30] = 3
    out = ResampleAxiald(keys=("label",), target_axial_mm=0.004, label_keys=("label",))(
        {"label": label, "spacing_mm": SPACING["cirrus"]}
    )
    assert set(np.unique(out["label"]).tolist()) <= {0, 2, 3}


# --- TC-048: native geometry ---------------------------------------------------------


def test_TC_048_inversion_returns_the_native_shape():
    native_height, width = 1024, 64
    out = eval_transforms(CFG, keys=("image",))(
        {
            "image": frame(height=native_height, width=width),
            "spacing_mm": SPACING["cirrus"],
            "intensity_window": (0.0, 220.0),
        }
    )
    assert out["image"].shape[-2] == 576
    back = invert_axial_resample(out["image"], out["native_spacing_mm"], (native_height, width))
    assert back.shape[-2:] == (native_height, width)


def test_TC_048_native_spacing_is_preserved_bit_identically():
    """SRS-057: the spacing used for a volume in mm3 must equal ingestion's exactly."""
    native = SPACING["cirrus"]
    out = eval_transforms(CFG, keys=("image",))(
        {
            "image": frame(height=512, width=64),
            "spacing_mm": native,
            "intensity_window": (0.0, 220.0),
        }
    )
    assert out["native_spacing_mm"] == native
    assert out["native_spacing_mm"][0] != out["spacing_mm"][0]  # they genuinely differ


def test_TC_048_measuring_without_inverting_is_detectably_different():
    """Guards the guard: if resampled and native agreed, the requirement would be
    vacuous and the test could not fail."""
    label = np.zeros((1, 1024, 64), dtype=np.uint8)
    label[0, 300:500, 10:40] = 1
    out = ResampleAxiald(keys=("label",), target_axial_mm=0.004, label_keys=("label",))(
        {"label": label, "spacing_mm": SPACING["cirrus"]}
    )
    resampled_count = int((out["label"] == 1).sum())
    native_count = int((label == 1).sum())
    assert resampled_count != native_count
    back = invert_axial_resample(out["label"], SPACING["cirrus"], (1024, 64))
    # Inverting recovers the native count to within nearest-neighbour rounding.
    assert abs(int((back == 1).sum()) - native_count) / native_count < 0.02


# --- the training chain ---------------------------------------------------------------


def test_train_chain_is_deterministic_under_a_seed():
    sample = {
        "image": frame(height=512, width=64),
        "label": np.zeros((512, 64), np.uint8),
        "spacing_mm": SPACING["cirrus"],
        "intensity_window": (0.0, 220.0),
    }
    a = train_transforms(CFG, seed=7)(dict(sample))
    b = train_transforms(CFG, seed=7)(dict(sample))
    assert np.allclose(a["image"].numpy(), b["image"].numpy())


def test_eval_chain_contains_no_random_transform():
    """A random transform with prob=0 still consumes random state, which would make a
    seeded evaluation depend on how many samples preceded it."""
    from monai.transforms import Randomizable

    assert not any(isinstance(t, Randomizable) for t in eval_transforms(CFG).transforms)
