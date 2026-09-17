"""Verification of ocuval.eval.metrics.

Covers TC-002 (no accuracy metric), TC-060 (Dice and HD95 per class), TC-061 (every
metric carries a CI and n), TC-062 (bootstrap seeded and reproducible), TC-068
(detection rates reported separately) and TC-072 (volume arithmetic from known
anisotropic spacing).

Expected values are computed independently of the implementation, per docs/07 section 3
rule 4 — a test that recomputes the implementation's own logic verifies nothing.
"""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

from ocuval.eval import metrics

# --- TC-072 fixture, exactly as specified in docs/07 section 7.1 -------------------
# Deliberately anisotropic: with equal spacings a transposed or collapsed axis order
# still yields the right answer, so an isotropic fixture would hide the whole defect
# class that HAZ-012 describes.
SPACING_MM = (0.0039, 0.0117, 0.047)
VOXEL_VOLUME_MM3 = 0.0039 * 0.0117 * 0.047  # 2.14461e-06
IRF_VOXELS = 1_000
SRF_VOXELS = 10_000


@pytest.fixture
def anisotropic_masks() -> dict[str, np.ndarray]:
    """Label masks with exactly known voxel counts per class."""
    shape = (40, 40, 40)
    irf = np.zeros(shape, dtype=bool)
    srf = np.zeros(shape, dtype=bool)
    ped = np.zeros(shape, dtype=bool)
    irf.reshape(-1)[:IRF_VOXELS] = True
    srf.reshape(-1)[IRF_VOXELS : IRF_VOXELS + SRF_VOXELS] = True
    return {"IRF": irf, "SRF": srf, "PED": ped}


# --- TC-002 -----------------------------------------------------------------------


def test_TC_002_no_accuracy_function_is_exposed():
    names = [n.lower() for n in dir(metrics)]
    assert not any("accuracy" in n for n in names)


def test_TC_002_no_accuracy_is_computed_in_source():
    source = inspect.getsource(metrics)
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))
    # The word appears in the module docstring explaining its absence; what must not
    # exist is a definition of one.
    assert "def accuracy" not in code


# --- TC-072 -----------------------------------------------------------------------


def test_TC_072_volume_from_known_anisotropic_spacing(anisotropic_masks):
    expected = {
        "IRF": IRF_VOXELS * VOXEL_VOLUME_MM3,
        "SRF": SRF_VOXELS * VOXEL_VOLUME_MM3,
        "PED": 0.0,
    }
    for name, mask in anisotropic_masks.items():
        volume, count, voxel_volume = metrics.volume_mm3(mask, SPACING_MM)
        assert volume == pytest.approx(expected[name], rel=1e-12)
        assert voxel_volume == pytest.approx(VOXEL_VOLUME_MM3, rel=1e-12)
        assert count == int(mask.sum())


def test_TC_072_reported_voxel_count_matches_the_fixture(anisotropic_masks):
    _, count, _ = metrics.volume_mm3(anisotropic_masks["SRF"], SPACING_MM)
    assert count == SRF_VOXELS


def test_TC_072_derivation_is_recomputable_from_reported_terms(anisotropic_masks):
    """SRS-059: volume must be reconstructible from the two terms reported with it."""
    volume, count, voxel_volume = metrics.volume_mm3(anisotropic_masks["IRF"], SPACING_MM)
    assert count * voxel_volume == pytest.approx(volume, rel=1e-12)


def test_TC_072_axis_order_changes_the_volume(anisotropic_masks):
    """Anisotropy is what makes a transposed spacing detectable — guard the guard."""
    straight, _, _ = metrics.volume_mm3(anisotropic_masks["IRF"], SPACING_MM)
    collapsed, _, _ = metrics.volume_mm3(anisotropic_masks["IRF"], (0.0039, 0.0039, 0.0039))
    assert straight != pytest.approx(collapsed, rel=1e-6)


@pytest.mark.parametrize(
    "bad_spacing",
    [
        (0.0039, 0.0117),
        (0.0, 0.0117, 0.047),
        (-0.0039, 0.0117, 0.047),
        (float("nan"), 0.0117, 0.047),
        (float("inf"), 0.0117, 0.047),
    ],
)
def test_TC_072_unusable_spacing_is_rejected(anisotropic_masks, bad_spacing):
    with pytest.raises(ValueError):
        metrics.volume_mm3(anisotropic_masks["IRF"], bad_spacing)


# --- TC-060 -----------------------------------------------------------------------


def test_TC_060_dice_on_known_overlap():
    pred = np.zeros((10, 10), dtype=bool)
    target = np.zeros((10, 10), dtype=bool)
    pred[0:4, 0] = True  # 4 voxels
    target[2:8, 0] = True  # 6 voxels, 2 shared
    assert metrics.dice(pred, target) == pytest.approx(2 * 2 / (4 + 6))


def test_TC_060_dice_is_one_when_both_masks_are_empty():
    empty = np.zeros((5, 5), dtype=bool)
    assert metrics.dice(empty, empty) == 1.0


def test_TC_060_dice_is_zero_when_disjoint():
    pred = np.zeros((6, 6), dtype=bool)
    target = np.zeros((6, 6), dtype=bool)
    pred[0, 0] = True
    target[5, 5] = True
    assert metrics.dice(pred, target) == 0.0


def test_TC_060_hd95_is_zero_for_identical_masks():
    mask = np.zeros((12, 12), dtype=bool)
    mask[3:9, 3:9] = True
    assert metrics.hd95(mask, mask, (1.0, 1.0)) == pytest.approx(0.0)


def test_TC_060_hd95_uses_spacing_not_voxel_counts():
    """A one-voxel boundary error must scale with the spacing of the axis it lies on."""
    target = np.zeros((20, 20), dtype=bool)
    target[5:15, 5:15] = True
    pred = np.zeros((20, 20), dtype=bool)
    pred[5:16, 5:15] = True  # extended by one voxel along axis 0

    coarse = metrics.hd95(pred, target, (1.0, 0.1))
    fine = metrics.hd95(pred, target, (0.1, 0.1))
    assert coarse > fine


def test_TC_060_hd95_resists_a_single_distant_outlier():
    """The property the 95th percentile exists for: one stray voxel must not set it."""
    target = np.zeros((60, 60), dtype=bool)
    target[25:35, 25:35] = True
    clean = target.copy()
    speckled = target.copy()
    speckled[0, 0] = True  # one spurious voxel, far away

    spacing = (0.05, 0.05)
    assert metrics.hd95(speckled, target, spacing) < 5 * metrics.hd95(clean, target, spacing) + 1.0


def test_TC_060_hd95_is_zero_when_both_masks_are_empty():
    empty = np.zeros((8, 8), dtype=bool)
    assert metrics.hd95(empty, empty, (1.0, 1.0)) == metrics.EMPTY_BOTH_HD95


def test_TC_060_hd95_is_nan_when_exactly_one_mask_is_empty():
    """NaN, never inf: inf would silently destroy any mean or bootstrap it entered."""
    empty = np.zeros((8, 8), dtype=bool)
    occupied = np.zeros((8, 8), dtype=bool)
    occupied[2:5, 2:5] = True
    value = metrics.hd95(occupied, empty, (1.0, 1.0))
    assert math.isnan(value)
    assert not math.isinf(value)


def test_TC_060_shape_mismatch_is_rejected():
    with pytest.raises(ValueError):
        metrics.dice(np.zeros((4, 4), dtype=bool), np.zeros((4, 5), dtype=bool))


# --- TC-068 -----------------------------------------------------------------------


def test_TC_068_sensitivity_and_specificity_on_a_known_table():
    target = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], dtype=bool)
    pred = np.array([1, 1, 0, 0, 1, 0, 0, 0, 0, 0], dtype=bool)
    # TP=2, FN=2, TN=5, FP=1
    sensitivity, specificity = metrics.sensitivity_specificity(pred, target)
    assert sensitivity == pytest.approx(2 / 4)
    assert specificity == pytest.approx(5 / 6)


def test_TC_068_rates_are_returned_separately_not_combined():
    result = metrics.sensitivity_specificity(
        np.ones((3, 3), dtype=bool), np.ones((3, 3), dtype=bool)
    )
    assert isinstance(result, tuple) and len(result) == 2


def test_TC_068_sensitivity_is_nan_with_no_positive_cases():
    target = np.zeros((4, 4), dtype=bool)
    pred = np.zeros((4, 4), dtype=bool)
    sensitivity, specificity = metrics.sensitivity_specificity(pred, target)
    assert math.isnan(sensitivity)
    assert specificity == pytest.approx(1.0)


# --- TC-061 and TC-062 ------------------------------------------------------------


def test_TC_061_estimate_carries_interval_and_sample_size():
    est = metrics.bootstrap_ci(np.array([0.6, 0.7, 0.8, 0.9]), seed=20260916)
    assert est.n == 4
    assert est.ci_low <= est.value <= est.ci_high


def test_TC_061_seed_is_keyword_only_and_has_no_default():
    signature = inspect.signature(metrics.bootstrap_ci)
    seed = signature.parameters["seed"]
    assert seed.kind is inspect.Parameter.KEYWORD_ONLY
    assert seed.default is inspect.Parameter.empty


def test_TC_061_nan_values_are_excluded_and_n_reflects_that():
    est = metrics.bootstrap_ci(np.array([0.5, float("nan"), 0.7]), seed=1)
    assert est.n == 2


def test_TC_061_all_nan_yields_nan_over_zero_samples():
    est = metrics.bootstrap_ci(np.array([float("nan"), float("nan")]), seed=1)
    assert est.n == 0
    assert math.isnan(est.value)


def test_TC_061_inverted_interval_is_rejected_by_construction():
    with pytest.raises(ValueError):
        metrics.Estimate(value=0.5, ci_low=0.9, ci_high=0.1, n=3)


def test_TC_062_bootstrap_is_reproducible_at_one_seed():
    values = np.array([0.42, 0.55, 0.61, 0.73, 0.68, 0.51])
    first = metrics.bootstrap_ci(values, seed=20260916)
    second = metrics.bootstrap_ci(values, seed=20260916)
    assert (first.value, first.ci_low, first.ci_high, first.n) == (
        second.value,
        second.ci_low,
        second.ci_high,
        second.n,
    )


def test_TC_062_the_seed_is_actually_used():
    """Guards against the seed being accepted and ignored.

    Deliberately not asserted on a single bound: with a small sample the bootstrap
    distribution is discrete and one percentile can coincide across seeds without
    anything being wrong. The check is that the two intervals are not identical in
    every bound, over a sample large enough for the percentiles to resolve.
    """
    values = np.linspace(0.2, 0.9, 40)
    first = metrics.bootstrap_ci(values, seed=1)
    second = metrics.bootstrap_ci(values, seed=2)
    assert first.value == pytest.approx(second.value)  # the point estimate is not resampled
    assert (first.ci_low, first.ci_high) != (second.ci_low, second.ci_high)


# --- coverage of the error and edge paths -----------------------------------------
# Added 2026-09-17 after a coverage review. All four were reachable, none dead. The
# int-array path below is the important one: it is not an obscure branch but the
# production path, since label arrays arrive from MetaImage as integers while every
# fixture above uses dtype=bool.


def test_TC_060_integer_label_arrays_are_accepted():
    """The production path: MetaImage reference arrays are ints, not bools."""
    pred = np.array([[0, 1, 1], [0, 0, 1]], dtype=np.uint8)
    target = np.array([[0, 1, 0], [0, 0, 1]], dtype=np.int32)
    assert metrics.dice(pred, target) == pytest.approx(2 * 2 / (3 + 2))


def test_TC_060_integer_and_boolean_masks_agree():
    rng = np.random.default_rng(7)
    as_int = rng.integers(0, 2, size=(8, 8)).astype(np.uint8)
    other = rng.integers(0, 2, size=(8, 8)).astype(np.uint8)
    assert metrics.dice(as_int, other) == metrics.dice(as_int.astype(bool), other.astype(bool))


@pytest.mark.parametrize("bad", [np.array([0, 2, 1]), np.array([0.0, 0.5, 1.0])])
def test_TC_060_masks_with_values_other_than_zero_and_one_are_rejected(bad):
    """A soft-max probability map passed as a mask must fail, not be truncated."""
    with pytest.raises(ValueError, match="only 0 and 1"):
        metrics.dice(bad, np.zeros(3, dtype=bool))


def test_TC_060_surface_of_an_empty_mask_is_empty():
    """Defensive guard in a private helper: hd95 early-returns before reaching it."""
    empty = np.zeros((4, 4), dtype=bool)
    assert not metrics._surface(empty).any()


def test_TC_061_negative_sample_size_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        metrics.Estimate(value=0.5, ci_low=0.4, ci_high=0.6, n=-1)


def test_TC_061_single_usable_value_yields_a_degenerate_interval():
    """A fold with one evaluable sample: the interval is the point, and n says so."""
    est = metrics.bootstrap_ci(np.array([0.73, float("nan")]), seed=1)
    assert est.n == 1
    assert est.value == est.ci_low == est.ci_high == pytest.approx(0.73)
