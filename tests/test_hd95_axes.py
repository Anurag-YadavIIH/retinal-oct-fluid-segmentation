"""TC-149 — HD95 puts each spacing component on its own array axis, through the real call path.

Traces to: SRS-032 (as amended 2026-10-26); `docs/13`, finding of 2026-10-25

Volumes are (B-scans, rows, columns); the project's spacing is (axial, lateral, separation).
Until 2026-10-26 `measure_volume` passed the spacing unchanged to `hd95`, which applies it
axis by axis, so every HD95 was measured on the wrong axes. These tests go through
`measure_volume`, the function the evaluation calls, not `hd95` alone, because `hd95` was
never wrong: the order handed to it was.

**The fixture is anisotropic in all three components**, each distinct, so a displacement
along any axis has exactly one correct answer. **TC-072 could not have caught this:** a volume
is the product of the three components, which no axis order changes.
"""

from __future__ import annotations

import numpy as np
import pytest

from ocuval.eval.pipeline import measure_volume

AXIAL, LATERAL, SEPARATION = 0.0039, 0.0117, 0.047
SPACING = (AXIAL, LATERAL, SEPARATION)  # the project's order, as recorded at ingestion
CLASSES = ("IRF",)


def mask(bscan: int, row: int, column: int) -> np.ndarray:
    volume = np.zeros((10, 20, 20), dtype=np.uint8)  # (B-scans, rows, columns)
    volume[bscan, row : row + 6, column : column + 6] = 1
    return volume


def hd95_of(prediction: np.ndarray, reference: np.ndarray) -> float:
    rows = measure_volume(prediction, reference, SPACING, classes=CLASSES)
    return next(r["value"] for r in rows if r["metric"] == "hd95")


@pytest.mark.parametrize(
    ("displacement", "expected"),
    [((1, 0, 0), SEPARATION), ((0, 1, 0), AXIAL), ((0, 0, 1), LATERAL)],
    ids=["one-bscan", "one-row-axial", "one-column-lateral"],
)
def test_TC_149_a_one_voxel_shift_scores_that_axis_physical_spacing(displacement, expected):
    reference = mask(4, 5, 5)
    prediction = mask(4 + displacement[0], 5 + displacement[1], 5 + displacement[2])
    assert hd95_of(prediction, reference) == pytest.approx(expected, rel=1e-9)


def test_TC_149_volumes_are_unchanged_by_the_fix():
    """The volume uses the product of the spacing, so it was right before and must not move."""
    reference = mask(4, 5, 5)
    rows = measure_volume(reference, reference, SPACING, classes=CLASSES)
    predicted = next(r for r in rows if r["metric"] == "volume_mm3_predicted")
    assert predicted["voxels"] == 36
    assert predicted["value"] == 36 * float(np.prod(SPACING))  # exactly, project order


def test_TC_149_identical_masks_still_score_zero_and_dice_one():
    reference = mask(4, 5, 5)
    rows = measure_volume(reference, reference, SPACING, classes=CLASSES)
    values = {r["metric"]: r["value"] for r in rows}
    assert values["hd95"] == 0.0 and values["dice"] == 1.0
