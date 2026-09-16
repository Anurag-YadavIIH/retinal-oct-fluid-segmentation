"""Monte Carlo dropout uncertainty estimation.

Traces to: SRS-TBD (uncertainty output)
Implements risk control: RC-TBD (routing low-confidence cases to human review)

Dropout layers are kept active at inference and the forward pass is repeated;
the per-voxel standard deviation across passes is the uncertainty map.
"""

from __future__ import annotations


def mc_dropout_predict(model, batch, passes: int):
    """Return (mean_probabilities, per_voxel_std) over the given number of passes."""
    raise NotImplementedError


def scan_confidence(uncertainty_map) -> float:
    """Reduce a per-voxel uncertainty map to one scan-level confidence score."""
    raise NotImplementedError
