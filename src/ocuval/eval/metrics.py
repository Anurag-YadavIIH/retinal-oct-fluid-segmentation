"""Segmentation and classification metrics with bootstrap confidence intervals.

Traces to: SRS-TBD (evaluation)

A bare point estimate is not a result anywhere in this repository. Every function
here returns an estimate together with its interval.

Accuracy is deliberately absent. The classes are severely imbalanced and it is
misleading; do not add it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Estimate:
    """A point estimate with its bootstrap confidence interval."""

    value: float
    ci_low: float
    ci_high: float
    n: int


def dice(pred, target, label: int) -> float:
    """Dice coefficient for one label on one sample."""
    raise NotImplementedError


def hd95(pred, target, label: int, spacing_mm: tuple[float, float, float]) -> float:
    """95th-percentile Hausdorff distance, in millimetres, for one label."""
    raise NotImplementedError


def sensitivity_specificity(pred, target, label: int) -> tuple[float, float]:
    """Per-label sensitivity and specificity for the detection arm."""
    raise NotImplementedError


def bootstrap_ci(values: list[float], n_resamples: int, seed: int, alpha: float = 0.05) -> Estimate:
    """Percentile bootstrap interval. Resampling is at patient level, not sample level."""
    raise NotImplementedError
