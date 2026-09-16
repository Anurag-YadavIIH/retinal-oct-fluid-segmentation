"""Segmentation network construction.

Traces to: SRS-TBD (model)

2D / 2.5D only. Full 3D is out of scope: the dataset is small and the
cross-vendor question does not require it. Dropout must be non-zero — MC-dropout
uncertainty at inference depends on it.
"""

from __future__ import annotations


def build_model(cfg: dict):
    """Build the MONAI network described by the model section of the config."""
    raise NotImplementedError
