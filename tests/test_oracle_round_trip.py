"""TC-151: oracle round trip. A perfect model must measure perfectly, for every vendor geometry.

Verifies: SRS-074. Registered 2026-10-29 from the audit of 2026-10-28, step 1 (`docs/13`).

Each geometry of docs/06 section 3.1 (B-scan size, axial spacing from section 3.1.2) is
written as a MetaImage pair, read by the real reader, prepared frame by frame by the real
evaluation chain, "predicted" by an oracle that returns the true labels in the prepared space,
inverted by the real inversion and measured by the real `measure_volume`.

**What "the true labels in the prepared space" are.** The models were trained on labels the
chain's nearest-neighbour resampling took from native rows `floor(i * rows / prepared)`. A
model that learned its training labels perfectly emits, at prepared row i, the class of that
native row; the oracle emits exactly that. Correct inversion returns each native row to the
prepared row whose sampled native row is nearest to it, ties to the even prepared row.

Two checks, neither with a tolerance that could absorb a shift:

- **Shapes built to survive resampling** are constant on every set of native rows that one
  prepared row stands for under that rule, computed here by integer arithmetic independent of
  the code under test. They must come back exactly: Dice 1, HD95 0, exact voxels and mm3.
- **Bands swept across every sub-row phase**, 11 heights at 40 consecutive positions, through
  the real chain and inversion: the mean signed centroid shift must be under 0.1 native row.
  Nearest-neighbour resampling cannot return an arbitrary band exactly, but it must not move
  bands systematically.

Topcon's height and axial spacing are paired as 885 rows at 0.0026 mm and 650 at 0.0035 mm,
inferred (the only pairing under which roi_size fits every volume); 650 at 0.0026 is added.
Set OCUVAL_ORACLE_FULL=1 to use each geometry's full B-scan count; by default 7 B-scans,
which changes no in-frame geometry, keep CI's memory bounded.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest
import yaml

from ocuval.data.transforms import axial_target, eval_transforms, invert_axial_resample
from ocuval.eval.pipeline import CLASS_NAMES, assert_spacing_unchanged, measure_volume
from ocuval.io.retouch_reader import read_volume

REPO = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((REPO / "configs" / "train_seg.yaml").read_text(encoding="utf-8"))
FULL = os.environ.get("OCUVAL_ORACLE_FULL") == "1"

# D1 (docs/13, 2026-10-29): the inversion resizes with torch's legacy nearest mode, which moves
# every prediction about one native row deeper. Strict, so CI fails the moment D1 is fixed and
# this marker is still here. Remove it in the commit that fixes D1.
D1 = pytest.mark.xfail(
    strict=True,
    reason="D1: legacy nearest-neighbour inversion moves predictions about one native row deeper",
)

# vendor, B-scans, rows (axial), columns (lateral), (lateral, axial, separation) mm, dtype.
GEOMETRIES = {
    "cirrus_sep_min": ("cirrus", 128, 1024, 512, (0.011742, 0.001955, 0.046878), np.uint8),
    "cirrus_sep_max": ("cirrus", 128, 1024, 512, (0.011742, 0.001955, 0.047244), np.uint8),
    "spectralis_lat_min": ("spectralis", 49, 496, 512, (0.010856, 0.003872, 0.116380), np.uint16),
    "spectralis_lat_max": ("spectralis", 49, 496, 512, (0.011950, 0.003872, 0.128624), np.uint16),
    "topcon_650": ("topcon", 128, 650, 512, (0.011720, 0.003500, 0.046880), np.uint8),
    "topcon_885": ("topcon", 128, 885, 512, (0.011720, 0.002600, 0.046880), np.uint8),
    "topcon_885_64": ("topcon", 64, 885, 512, (0.011720, 0.002600, 0.046880), np.uint8),
    "topcon_650_at_0026": ("topcon", 128, 650, 512, (0.011720, 0.002600, 0.046880), np.uint8),
}
ELEMENT_TYPE = {np.uint8: "MET_UCHAR", np.uint16: "MET_USHORT"}


def write_metaimage(directory: Path, name: str, array: np.ndarray, xyz_spacing) -> None:
    """Write (z, y, x) `array` as MetaImage: x fastest, DimSize and spacing given as (x, y, z)."""
    z, y, x = array.shape
    (directory / f"{name}.raw").write_bytes(
        np.ascontiguousarray(array).astype("<" + array.dtype.str[1:]).tobytes()
    )
    (directory / f"{name}.mhd").write_text(
        "\n".join([
            "ObjectType = Image", "NDims = 3", "BinaryData = True",
            "BinaryDataByteOrderMSB = False", "CompressedData = False",
            f"DimSize = {x} {y} {z}",
            "ElementSpacing = " + " ".join(repr(float(v)) for v in xyz_spacing),
            f"ElementType = {ELEMENT_TYPE[array.dtype.type]}",
            f"ElementDataFile = {name}.raw",
        ]) + "\n",
        encoding="utf-8",
    )  # fmt: skip


def prepared_rows(native_rows: int, axial_mm: float, target_mm: float) -> int:
    """Prepared height by the resampling rule, recomputed here: round(rows * factor)."""
    factor = axial_mm / target_mm
    return native_rows if np.isclose(factor, 1.0) else max(1, int(round(native_rows * factor)))


def sampled_rows(native_rows: int, prepared: int) -> np.ndarray:
    """The native row each prepared row's label is taken from: floor(i * rows / prepared)."""
    return (np.arange(prepared) * native_rows) // prepared


def cells(native_rows: int, prepared: int) -> np.ndarray:
    """For each native row, the prepared row whose sampled row is nearest; ties to the even one.

    Integer arithmetic over every candidate, independent of the code under test.
    """
    src = sampled_rows(native_rows, prepared)
    distance = np.abs(np.arange(native_rows)[:, None] - src[None, :])
    nearest = distance == distance.min(axis=1, keepdims=True)
    tied_even = nearest & (np.arange(prepared)[None, :] % 2 == 0)
    return np.where(nearest.sum(axis=1) > 1, tied_even.argmax(axis=1), nearest.argmax(axis=1))


def surviving_fluid(shape, prepared: int) -> np.ndarray:
    """Fluid constant on each set of native rows that one prepared row stands for.

    Each class occupies whole cells, at fixed fractions of the height, so every geometry gets
    all three: a two-cell IRF band over three B-scans, a one-cell SRF band, a PED block.
    """
    b, rows, cols = shape
    cell = cells(rows, prepared)
    label = np.zeros(shape, dtype=np.uint8)
    mid = b // 2
    for value, (lo, hi), (c0, c1), bs in [
        (1, (0.30, 0.30 + 2 / prepared), (60, 190), range(max(0, mid - 1), min(b, mid + 2))),
        (2, (0.55, 0.55 + 1 / prepared), (200, 380), range(mid, min(b, mid + 1))),
        (3, (0.66, 0.71), (300, 470), range(max(0, mid - 2), min(b, mid + 3))),
    ]:
        in_rows = (cell >= int(lo * prepared)) & (cell < int(hi * prepared))
        for s in bs:
            label[s, in_rows, c0:c1] = value
    return label


def oracle_round_trip(tmp_path: Path, geometry: str):
    vendor, n_b, rows, cols, xyz, dtype = GEOMETRIES[geometry]
    n_b = n_b if FULL else min(n_b, 7)
    lateral, axial, _separation = xyz
    shape = (n_b, rows, cols)
    target = axial_target(CFG)
    truth = surviving_fluid(shape, prepared_rows(rows, axial, target))
    rng = np.random.default_rng(20261028)
    high = 255 if dtype is np.uint8 else 4000
    image = rng.integers(0, high, size=shape, dtype=np.int64).astype(dtype)
    subject = tmp_path / f"TRAIN_{geometry}"
    subject.mkdir()
    write_metaimage(subject, "oct", image, xyz)
    write_metaimage(subject, "reference", truth, xyz)

    # Ingestion, as scripts/01_convert_to_dicom.py records it, through JSON as the manifest is.
    volume = read_volume(subject, vendor)
    row = json.loads(json.dumps({
        "vendor": vendor, "spacing_mm": list(volume.spacing_mm),
        "intensity_window": list(volume.intensity_window),
    }))  # fmt: skip

    # Evaluation, mirroring scripts/05_evaluate.py lines 177-222, the model replaced by the oracle.
    native = read_volume(subject, row["vendor"])
    reference = np.asarray(native.label_array)
    recorded = assert_spacing_unchanged(row["spacing_mm"], row["spacing_mm"], subject.name)
    chain = eval_transforms(CFG)
    labels = []
    for index in range(native.pixel_array.shape[0]):
        sample = chain({
            "image": native.pixel_array[index], "label": reference[index],
            "intensity_window": row["intensity_window"], "spacing_mm": row["spacing_mm"],
            "vendor": row["vendor"],
        })  # fmt: skip
        labels.append(np.asarray(sample["label"]).squeeze().astype(np.uint8))  # the oracle
    prediction = invert_axial_resample(
        np.stack(labels), tuple(row["spacing_mm"]), (reference.shape[1], reference.shape[2]),
        target_axial_mm=axial_target(CFG),
    )  # fmt: skip
    prediction = np.asarray(prediction).astype(np.uint8).reshape(reference.shape)
    seg = measure_volume(prediction, reference, recorded)
    return truth, reference, prediction, seg, (axial, lateral, xyz[2])


def summarise(truth, prediction, seg, spacing_axl):
    """Per class: Dice, HD95, voxel counts and mm3 against an independent expectation."""
    voxel_mm3 = spacing_axl[0] * spacing_axl[1] * spacing_axl[2]
    out = {}
    for index, name in enumerate(CLASS_NAMES, start=1):
        got = {r["metric"]: r for r in seg if r["fluid_class"] == name}
        true_voxels = int((truth == index).sum())
        out[name] = {
            "dice": got["dice"]["value"],
            "hd95": got["hd95"]["value"],
            "true_voxels": true_voxels,
            "reference_voxels": got["volume_mm3_reference"]["voxels"],
            "predicted_voxels": got["volume_mm3_predicted"]["voxels"],
            "true_mm3": true_voxels * voxel_mm3,
            "predicted_mm3": got["volume_mm3_predicted"]["value"],
            "reference_mm3": got["volume_mm3_reference"]["value"],
            "misplaced_voxels": int(((prediction == index) != (truth == index)).sum()),
        }
    return out


def assert_perfect(summary):
    for name, s in summary.items():
        assert s["true_voxels"] > 0, f"{name}: the fixture placed no fluid"
        assert s["reference_voxels"] == s["true_voxels"], (name, s)
        assert s["reference_mm3"] == pytest.approx(s["true_mm3"], rel=1e-12), (name, s)
        assert s["dice"] == 1.0, (name, s)
        assert s["hd95"] == 0.0, (name, s)
        assert s["predicted_voxels"] == s["true_voxels"], (name, s)
        assert s["predicted_mm3"] == pytest.approx(s["true_mm3"], rel=1e-12), (name, s)
        assert s["misplaced_voxels"] == 0, (name, s)


@pytest.mark.parametrize("geometry", sorted(GEOMETRIES))
def test_TC_151_the_forward_sampling_is_the_one_this_test_computes(geometry):
    """The independent arithmetic above describes the real chain, or the other checks mean
    nothing: a ramp of native row numbers through the chain's label path comes out as
    floor(i * rows / prepared), row for row."""
    _vendor, _b, rows, _cols, xyz, _dtype = GEOMETRIES[geometry]
    ramp = np.repeat(np.arange(rows, dtype=np.float32)[:, None], 4, axis=1)
    out = eval_transforms(CFG)({
        "image": np.zeros_like(ramp), "label": ramp, "intensity_window": (0.0, 1.0),
        "spacing_mm": (xyz[1], xyz[0], xyz[2]),
    })  # fmt: skip
    prepared = prepared_rows(rows, xyz[1], axial_target(CFG))
    column = np.asarray(out["label"]).squeeze()[:, 254]  # a padded column holds 0; this is data
    top = (column.shape[0] - prepared) // 2
    assert np.array_equal(column[top : top + prepared], sampled_rows(rows, prepared))


@D1
@pytest.mark.parametrize("geometry", sorted(GEOMETRIES))
def test_TC_151_surviving_fluid_is_recovered_exactly(tmp_path, geometry):
    truth, reference, prediction, seg, spacing = oracle_round_trip(tmp_path, geometry)
    assert np.array_equal(reference, truth), "the reader did not return the reference written"
    assert_perfect(summarise(truth, prediction, seg, spacing))


@D1
@pytest.mark.parametrize("geometry", sorted(GEOMETRIES))
def test_TC_151_bands_at_every_phase_come_back_without_a_systematic_shift(geometry):
    """One frame, one band per column: 11 heights at 40 consecutive native positions."""
    _vendor, _b, rows, _cols, xyz, _dtype = GEOMETRIES[geometry]
    spacing = (xyz[1], xyz[0], xyz[2])
    label = np.zeros((rows, 440), dtype=np.uint8)
    for column in range(440):
        height, top = 1 + column // 40, int(0.4 * rows) + column % 40
        label[top : top + height, column] = 1
    out = eval_transforms(CFG)({
        "image": label.astype(np.float32), "label": label, "intensity_window": (0.0, 1.0),
        "spacing_mm": spacing,
    })  # fmt: skip
    back = invert_axial_resample(
        np.asarray(out["label"]), spacing, label.shape, target_axial_mm=axial_target(CFG)
    )[0]
    native_rows = np.arange(rows)[:, None]
    shifts = [
        (native_rows[:, 0][back[:, c] == 1].mean() - native_rows[:, 0][label[:, c] == 1].mean())
        for c in range(440)
        if (back[:, c] == 1).any()
    ]
    assert len(shifts) > 400, "most bands must survive resampling for the mean to mean anything"
    assert abs(float(np.mean(shifts))) < 0.1, f"mean centroid shift {np.mean(shifts):+.3f} rows"
