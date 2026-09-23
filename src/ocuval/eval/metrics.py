"""Segmentation and detection metrics with bootstrap confidence intervals.

Traces to: SRS-032, SRS-033, SRS-034, SRS-035 (evaluation), SRS-040, SRS-059
(volume derivation), SRS-053 (detection)
Implements risk control: RC-006, RC-007, RC-024, RC-026

A bare point estimate is not a result anywhere in this repository. Every aggregate
function here returns an estimate together with its interval and the sample size.

Accuracy is deliberately absent. The classes are severely imbalanced — foreground is
0.60-1.48% of voxels, measured across all 70 volumes (docs/06 section 3.2) — so a null
predictor scores 98.52-99.40%. Do not add an accuracy function; TC-002 asserts there is
none.

The empty-mask conventions below are not edge cases on this dataset. 58 of 70 volumes
lack at least one fluid class and only 12 contain all three (docs/06 section 3.2.1), so
both-empty Dice and one-empty HD95 are exercised on the majority of per-class
evaluations. That is the strongest available vindication of returning NaN rather than
inf from hd95: on this data, inf would have destroyed most per-class HD95 aggregates
rather than a rare one.

These are pure functions over numpy arrays, not MONAI metrics, and that is deliberate
(CLAUDE.md section 4 records the exception). Two reasons:

1. **docs/10's credibility rests on these being independently computable.** A reported
   Dice that can only be reproduced by running this project's own training stack is a
   weaker claim than one any reader can recompute from a mask and a spacing tuple.
2. **Pure array functions are verifiable without a torch runtime**, so the metrics that
   every result depends on are tested in a fast suite with no GPU, no model and no
   framework version in the way.

MONAI supplies transforms, networks and losses elsewhere. Its metric implementations are
used as an *independent cross-check* rather than as the source: TC-120 runs ours and
MONAI's back to back over random masks and requires agreement. Two independent
implementations agreeing is stronger evidence than either alone, and it is the standard
answer to the risk that reimplementing a metric reimplements it wrongly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

# Distances to or from an empty surface are undefined. Both empty means the prediction
# and the reference agree that there is nothing there, which is perfect agreement and
# scores 0.0 mm. Exactly one empty is undefined and returns NaN rather than inf: inf
# would silently destroy any mean or bootstrap it entered, while NaN propagates
# visibly and forces the caller to decide. Recorded in docs/13 under rule 6.
EMPTY_BOTH_HD95 = 0.0


@dataclass(frozen=True)
class Estimate:
    """A point estimate with its bootstrap interval and the sample size behind it.

    SRS-033 forbids emitting a metric without both. This type is how that is enforced:
    the aggregate functions return it, so there is no path that yields a bare float.
    """

    value: float
    ci_low: float
    ci_high: float
    n: int

    def __post_init__(self) -> None:
        if self.n < 0:
            raise ValueError(f"sample size must be non-negative, got {self.n}")
        if self.ci_low > self.ci_high:
            raise ValueError(f"interval is inverted: [{self.ci_low}, {self.ci_high}]")


def _as_bool(mask: np.ndarray) -> np.ndarray:
    """Coerce a label mask to boolean without silently accepting float noise."""
    arr = np.asarray(mask)
    if arr.dtype == bool:
        return arr
    if not np.all(np.isin(arr, (0, 1))):
        raise ValueError("mask must contain only 0 and 1, or be boolean")
    return arr.astype(bool)


def _check_same_shape(pred: np.ndarray, target: np.ndarray) -> None:
    if pred.shape != target.shape:
        raise ValueError(f"shape mismatch: prediction {pred.shape}, reference {target.shape}")


def _check_spacing(spacing: tuple[float, ...], ndim: int) -> tuple[float, ...]:
    """Reject spacing that cannot produce a meaningful physical distance.

    No default is supplied here or anywhere else (SRS-055): a caller that has no
    spacing must fail, not fall back. See also ocuval.io.retouch_reader.
    """
    if len(spacing) != ndim:
        raise ValueError(f"spacing has {len(spacing)} components, array has {ndim} dimensions")
    for component in spacing:
        if not math.isfinite(component) or component <= 0:
            raise ValueError(f"spacing components must be finite and positive, got {spacing}")
    return tuple(float(c) for c in spacing)


def dice(pred: np.ndarray, target: np.ndarray) -> float:
    """Dice coefficient for one class, as a fraction of overlapping volume.

    Returns 1.0 when both masks are empty: the prediction and the reference agree that
    the class is absent, which is correct rather than undefined. This differs from HD95,
    where the same case is a distance to an empty surface.
    """
    p, t = _as_bool(pred), _as_bool(target)
    _check_same_shape(p, t)
    total = int(p.sum()) + int(t.sum())
    if total == 0:
        return 1.0
    return 2.0 * float(np.logical_and(p, t).sum()) / float(total)


def _surface(mask: np.ndarray) -> np.ndarray:
    """Boundary voxels of a binary mask: the mask minus its erosion.

    Erosion uses a connectivity-1 structuring element, so a voxel is on the surface when
    any face-adjacent neighbour is outside the mask.
    """
    if not mask.any():
        return np.zeros_like(mask, dtype=bool)
    eroded = ndimage.binary_erosion(mask, ndimage.generate_binary_structure(mask.ndim, 1))
    return np.logical_and(mask, np.logical_not(eroded))


def hd95(pred: np.ndarray, target: np.ndarray, spacing: tuple[float, ...]) -> float:
    """95th-percentile symmetric Hausdorff distance, in millimetres.

    The plain Hausdorff distance is the largest distance from any point on one surface
    to the nearest point on the other. That makes it a one-voxel metric: a single
    spurious voxel far from the lesion sets the whole score, and in speckly OCT with
    small multi-focal fluid that is the expected failure, not an exception. Taking the
    95th percentile discards the worst 5% as outliers while keeping what makes the
    measure useful — sensitivity to where the boundary is, which Dice cannot see at all.

    **Symmetry is the max of the two directed percentiles**, not a percentile of the two
    directions pooled. The distinction is not cosmetic: pooling lets a well-matched
    direction dilute a badly-matched one, so a prediction that follows the reference
    closely everywhere except one under-segmented region scores better than it should.
    max-of-directed is also the definition MONAI, medpy and the segmentation literature
    use, which is what makes a number here comparable to a published RETOUCH result.

    An earlier version of this function pooled the directions. TC-120 caught it by
    disagreeing with MONAI; the change is recorded in docs/13 under rule 6.

    Distances are physical, not in voxels: the transform is spacing-aware, because OCT
    voxels are strongly anisotropic and "two voxels away" means different distances
    along different axes.

    Returns 0.0 when both masks are empty, and NaN when exactly one is. NaN rather than
    inf is deliberate — see the module constant.
    """
    p, t = _as_bool(pred), _as_bool(target)
    _check_same_shape(p, t)
    sampling = _check_spacing(spacing, p.ndim)

    if not p.any() and not t.any():
        return EMPTY_BOTH_HD95
    if not p.any() or not t.any():
        return float("nan")

    p_surface, t_surface = _surface(p), _surface(t)

    # distance_transform_edt measures distance to the nearest zero, so the surface is
    # inverted before transforming: the result is distance from every voxel to the
    # nearest surface voxel, in millimetres.
    to_target = ndimage.distance_transform_edt(~t_surface, sampling=sampling)
    to_pred = ndimage.distance_transform_edt(~p_surface, sampling=sampling)

    forward = float(np.percentile(to_target[p_surface], 95))
    backward = float(np.percentile(to_pred[t_surface], 95))
    return max(forward, backward)


def sensitivity_specificity(pred: np.ndarray, target: np.ndarray) -> tuple[float, float]:
    """Sensitivity and specificity for one class, returned separately.

    Returned as a pair and never combined into a single figure. Accuracy would be that
    combination weighted by prevalence, which at this prevalence is meaningless — see
    the module docstring.

    A rate over an empty denominator is undefined and returns NaN: no positive cases
    means sensitivity has nothing to measure, and saying 0.0 or 1.0 would invent a
    result.
    """
    p, t = _as_bool(pred), _as_bool(target)
    _check_same_shape(p, t)

    true_positive = float(np.logical_and(p, t).sum())
    true_negative = float(np.logical_and(~p, ~t).sum())
    positives = float(t.sum())
    negatives = float((~t).sum())

    sensitivity = true_positive / positives if positives else float("nan")
    specificity = true_negative / negatives if negatives else float("nan")
    return sensitivity, specificity


def volume_mm3(mask: np.ndarray, spacing: tuple[float, ...]) -> tuple[float, int, float]:
    """Volume of one class in cubic millimetres, with the terms it was derived from.

    Returns (volume_mm3, voxel_count, voxel_volume_mm3). The two extra terms are not a
    convenience: SRS-059 requires the derivation to be recomputable from the emitted
    object alone, because a volume that is wrong only in its spacing looks entirely
    correct in the mask and to a grader (HAZ-012, docs/05 section 5.4).

    No spacing default exists. A caller without spacing gets an exception.
    """
    m = _as_bool(mask)
    sampling = _check_spacing(spacing, m.ndim)
    voxel_volume = float(np.prod(sampling))
    count = int(m.sum())
    return count * voxel_volume, count, voxel_volume


def bootstrap_ci(
    values: np.ndarray,
    *,
    seed: int,
    n_resamples: int = 2000,
    alpha: float = 0.05,
) -> Estimate:
    """Percentile bootstrap interval over per-sample values.

    Resampling is seeded from the run configuration and reproduces exactly on
    re-execution (SRS-034, NFR-002). The seed is keyword-only and has no default, so a
    caller cannot obtain an unseeded interval by omission.

    NaN values are excluded before resampling and the reported n is the count actually
    used — a sample the metric could not be computed for must not silently count as
    evidence. Where every value is NaN the estimate is NaN over n=0 rather than an
    error, so that one degenerate class does not abort a whole evaluation.
    """
    arr = np.asarray(values, dtype=float).ravel()
    finite = arr[~np.isnan(arr)]
    n = int(finite.size)
    if n == 0:
        nan = float("nan")
        return Estimate(value=nan, ci_low=nan, ci_high=nan, n=0)

    point = float(finite.mean())
    if n == 1:
        return Estimate(value=point, ci_low=point, ci_high=point, n=1)

    rng = np.random.default_rng(seed)
    means = finite[rng.integers(0, n, size=(n_resamples, n))].mean(axis=1)
    low, high = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return Estimate(value=point, ci_low=float(low), ci_high=float(high), n=n)
