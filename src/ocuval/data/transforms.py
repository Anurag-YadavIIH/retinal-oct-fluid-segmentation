"""MONAI transform chains for training, validation, and inference.

Traces to: SRS-TBD (preprocessing)

Intensity normalisation is per-volume, not per-dataset: the whole point of the
experiment is that vendors differ, so a global statistic would leak the very
distribution shift the project is trying to measure.
"""

from __future__ import annotations


def train_transforms(roi_size: tuple[int, int], seed: int):
    """Augmenting chain used for the training split only."""
    raise NotImplementedError


def eval_transforms(roi_size: tuple[int, int]):
    """Deterministic chain used for validation, test, and inference."""
    raise NotImplementedError
