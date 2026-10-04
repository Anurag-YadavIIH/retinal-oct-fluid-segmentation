"""Monte Carlo dropout uncertainty estimation.

Traces to: SRS-029, SRS-030 (uncertainty output), SRS-091 (seeded per volume)
Implements risk control: RC-009 (routing low-confidence cases to human review)
Verifies: TC-055, TC-056, TC-128

Dropout layers are kept active at inference and the forward pass is repeated; the
per-voxel standard deviation across passes is the uncertainty map.

**Why dropout only, and not the whole model, is put into training mode.** `model.train()`
would also switch the normalisation layers, and this network uses `InstanceNorm2d` --
whose default `track_running_stats=False` means train mode makes it recompute statistics
per sample rather than use stored ones. That would change the *prediction*, not just its
spread, so the mean over passes would no longer be an estimate of the model's output. Only
`nn.Dropout*` modules are enabled, which is what MC-dropout actually requires.

**The mean, not a single pass, is the prediction.** SRS-052 takes the detection score from
the mean class probability, so the mean has to be the thing that is also segmented and
measured, or the detection arm and the segmentation arm would describe different outputs
(SRS-050: one model, two views).
"""

from __future__ import annotations

import hashlib

import numpy as np


def volume_seed(seed: int, volume_key: str) -> int:
    """The seed a volume's MC-dropout passes draw from: a pure function of its inputs (SRS-091).

    **Why per volume, and derived.** The passes draw dropout masks from torch's global
    generator, because `nn.Dropout` takes no generator argument. Unseeded, two evaluations of
    the same checkpoint differed in 49 aggregate figures (`docs/13`, 2026-10-04). Seeding once
    per process would fix that, but would still make a volume's masks depend on how many
    volumes ran before it, so `--limit` or a different bucket order would change its result.
    Re-seeding from `(seed, volume)` makes each volume's draws a property of the volume alone.
    This is the same derive-don't-store reasoning as `epoch_seed` (SRS-076).

    **`volume_key` is the source subject identifier (`TRAIN0nn`), not the SOP Instance UID.**
    UIDs are minted per conversion (SRS-023), so a seed keyed on one would change on every
    re-conversion. RETOUCH has one volume per subject, so the subject identifies the volume.

    Hashed rather than added, so nearby seeds or similar keys do not share draws.
    """
    digest = hashlib.sha256(f"mc_dropout:{int(seed)}:{volume_key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (2**63 - 1)


def reseed_for_volume(seed: int, volume_key: str) -> int:
    """Seed torch's global generator, CPU and every CUDA device, for one volume's passes.

    Call immediately before that volume's `mc_dropout_predict` calls. Returns the derived
    seed so the caller can record it.
    """
    import torch

    derived = volume_seed(seed, volume_key)
    torch.manual_seed(derived)  # seeds the CPU generator and every CUDA device's
    return derived


def enable_dropout(model) -> int:
    """Put every dropout layer into training mode, leaving everything else in eval.

    Returns how many layers were switched, so a caller can assert the mechanism did
    something. A model with no dropout would otherwise produce an uncertainty map of exact
    zeros, which looks like perfect confidence rather than like a missing mechanism --
    `docs/07` §3 rule 8.
    """
    import torch

    switched = 0
    for module in model.modules():
        if isinstance(module, torch.nn.modules.dropout._DropoutNd):
            module.train()
            switched += 1
    return switched


def mc_dropout_predict(model, batch, passes: int):
    """Return (mean_probabilities, per_voxel_std) over the given number of passes.

    `batch` is a tensor of shape (N, C, H, W); the return is a pair of numpy arrays of
    shape (N, classes, H, W). Softmax is applied per pass **before** averaging: averaging
    logits and then normalising is a different quantity, and is not a probability.

    `passes` must be at least 2 -- a standard deviation over one sample is 0 by definition,
    which would report perfect confidence from a single forward pass.
    """
    import torch

    if passes < 2:
        raise ValueError(
            f"passes={passes}: a standard deviation over one pass is identically zero, "
            f"which would report perfect confidence. SRS-029 configures 20."
        )

    model.eval()
    if enable_dropout(model) == 0:
        raise ValueError(
            "the model has no dropout layers, so repeated passes are identical and the "
            "uncertainty map would be exactly zero. `model.dropout` must be non-zero "
            "(configs/train_seg.yaml sets 0.2 for this reason)."
        )

    stack = []
    with torch.no_grad():
        for _ in range(passes):
            stack.append(torch.softmax(model(batch), dim=1).detach().cpu().numpy())
    draws = np.stack(stack, axis=0)
    # ddof=0: this is the spread of the sample of passes actually drawn, not an estimate of
    # a population variance. With `passes` fixed by configuration the distinction is a
    # constant factor, and stating which one is reported matters more than the choice.
    return draws.mean(axis=0), draws.std(axis=0, ddof=0)


def scan_confidence(uncertainty_map) -> float:
    """Reduce a per-voxel uncertainty map to one scan-level confidence score.

    `1 - mean(std)` over the whole map, in [0, 1] and increasing with confidence.

    **The mean rather than the max**, deliberately: the maximum per-voxel standard
    deviation is almost always near its ceiling somewhere along a fluid boundary, where
    disagreement between passes is expected and uninformative. A max would therefore be
    nearly constant across scans and would rank none of them, which defeats RC-009's
    purpose of routing the least confident cases to review.

    The ceiling of a per-voxel standard deviation over softmax outputs is 0.5, so the score
    is rescaled by 2 to span [0, 1]. Without that, a maximally uncertain scan would score
    0.5 and read as middling rather than as the worst possible.
    """
    values = np.asarray(uncertainty_map, dtype=float)
    if values.size == 0:
        raise ValueError("an empty uncertainty map has no confidence to report")
    return float(1.0 - 2.0 * np.nanmean(values))


__all__ = [
    "enable_dropout",
    "mc_dropout_predict",
    "reseed_for_volume",
    "scan_confidence",
    "volume_seed",
]
