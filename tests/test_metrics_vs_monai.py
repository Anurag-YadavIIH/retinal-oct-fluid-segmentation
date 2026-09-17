"""TC-120 — back-to-back verification of our metrics against MONAI's.

Every other test of `ocuval.eval.metrics` was written by whoever wrote the module, from
the same understanding of what the metric means. That leaves one risk those tests cannot
address: an implementation that is internally consistent, passes every fixture, and is
wrong. Agreement with a second, independently written implementation is the standard
answer, and it is evidence neither suite provides alone.

Marked `slow`: it imports the torch stack, which the rest of the metric suite
deliberately does not need (CLAUDE.md §4). It needs no data — the masks are generated.

A disagreement here is a **finding to be explained**, not automatically a defect in this
project. Our edge-case definitions are fixed in docs/13 under rule 6 and differ from
MONAI's in places this file documents. Either way the explanation belongs in docs/13.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch
from monai.metrics import compute_hausdorff_distance
from monai.metrics.meandice import compute_dice

from ocuval.eval import metrics

pytestmark = pytest.mark.slow

SPACING_MM = (0.0039, 0.0117, 0.047)


def as_monai(mask: np.ndarray) -> torch.Tensor:
    """MONAI expects (batch, channel, *spatial) one-hot tensors."""
    return torch.from_numpy(mask.astype(np.float32))[None, None]


def random_pair(rng: np.random.Generator, shape=(16, 18, 20)) -> tuple[np.ndarray, np.ndarray]:
    """A prediction and reference with realistic structure and partial overlap.

    Blobs rather than uniform noise: HD95 is a surface metric, and salt-and-pepper masks
    have a surface area unlike anything a segmentation produces, so agreement on them
    would be a weaker test than it looks.
    """
    reference = np.zeros(shape, dtype=bool)
    prediction = np.zeros(shape, dtype=bool)
    for _ in range(int(rng.integers(1, 4))):
        origin = [int(rng.integers(1, s - 5)) for s in shape]
        size = [int(rng.integers(2, 5)) for _ in shape]
        offset = [int(rng.integers(-1, 2)) for _ in shape]
        ref_slice = tuple(slice(o, o + d) for o, d in zip(origin, size, strict=True))
        pred_slice = tuple(
            slice(max(o + f, 0), max(o + f, 0) + d)
            for o, d, f in zip(origin, size, offset, strict=True)
        )
        reference[ref_slice] = True
        prediction[pred_slice] = True
    return prediction, reference


@pytest.mark.parametrize("seed", range(12))
def test_TC_120_dice_agrees_with_monai(seed):
    rng = np.random.default_rng(seed)
    prediction, reference = random_pair(rng)
    if not prediction.any() or not reference.any():
        pytest.skip("degenerate pair; the empty-mask convention is ours, not MONAI's")

    ours = metrics.dice(prediction, reference)
    theirs = float(compute_dice(as_monai(prediction), as_monai(reference)).item())
    assert ours == pytest.approx(theirs, abs=1e-6)


@pytest.mark.parametrize("seed", range(12))
def test_TC_120_hd95_agrees_with_monai(seed):
    rng = np.random.default_rng(seed)
    prediction, reference = random_pair(rng)
    if not prediction.any() or not reference.any():
        pytest.skip("degenerate pair; the empty-mask convention is ours, not MONAI's")

    ours = metrics.hd95(prediction, reference, SPACING_MM)
    theirs = float(
        compute_hausdorff_distance(
            as_monai(prediction),
            as_monai(reference),
            percentile=95,
            spacing=list(SPACING_MM),
        ).item()
    )
    assert ours == pytest.approx(theirs, rel=1e-3, abs=1e-6)


def test_TC_120_agreement_holds_on_identical_masks():
    mask = np.zeros((12, 12, 12), dtype=bool)
    mask[3:8, 4:9, 2:7] = True
    assert metrics.dice(mask, mask) == pytest.approx(
        float(compute_dice(as_monai(mask), as_monai(mask)).item())
    )
    assert metrics.hd95(mask, mask, SPACING_MM) == pytest.approx(
        float(
            compute_hausdorff_distance(
                as_monai(mask), as_monai(mask), percentile=95, spacing=list(SPACING_MM)
            ).item()
        ),
        abs=1e-9,
    )


def test_TC_120_hd95_agreement_is_spacing_sensitive_in_both():
    """Agreement on one spacing could be coincidence; it must track spacing together."""
    reference = np.zeros((16, 16, 16), dtype=bool)
    reference[4:10, 4:10, 4:10] = True
    prediction = np.zeros((16, 16, 16), dtype=bool)
    prediction[4:11, 4:10, 4:10] = True

    for spacing in [(0.0039, 0.0117, 0.047), (0.05, 0.05, 0.2), (0.01, 0.02, 0.03)]:
        ours = metrics.hd95(prediction, reference, spacing)
        theirs = float(
            compute_hausdorff_distance(
                as_monai(prediction),
                as_monai(reference),
                percentile=95,
                spacing=list(spacing),
            ).item()
        )
        assert ours == pytest.approx(theirs, rel=1e-3, abs=1e-6), spacing


def test_TC_120_documents_where_the_conventions_differ():
    """Our empty-mask definitions are deliberate and are not MONAI's.

    docs/13 fixes them: both-empty Dice is 1.0 and both-empty HD95 is 0.0, because the
    prediction and reference agree the class is absent. MONAI returns NaN for the same
    case. This is recorded rather than reconciled — a disagreement that is understood is
    not a defect, but an undocumented one would be.
    """
    empty = np.zeros((8, 8, 8), dtype=bool)
    assert metrics.dice(empty, empty) == 1.0
    assert metrics.hd95(empty, empty, SPACING_MM) == 0.0

    theirs = float(compute_dice(as_monai(empty), as_monai(empty)).item())
    assert np.isnan(theirs)
