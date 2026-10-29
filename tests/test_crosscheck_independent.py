"""TC-152: the audit's independent metrics agree with the pipeline's on synthetic masks, and can
disagree.

Verifies: SRS-103. Audit of 2026-10-28, step 2, registered 2026-10-29. Runs before
`scripts/13_crosscheck_val.py` is used on real data, so a difference found there is about the
pipeline and not about an untested second implementation.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from ocuval.eval.metrics import dice, hd95
from ocuval.eval.pipeline import array_axis_spacing

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "crosscheck", REPO / "scripts" / "13_crosscheck_val.py"
)
CROSS = importlib.util.module_from_spec(spec)
sys.modules["crosscheck"] = CROSS
spec.loader.exec_module(CROSS)

SPACING = (0.001955, 0.011742, 0.047)  # project order: axial, lateral, separation


def blob(shape, centre, radii):
    z, y, x = np.ogrid[: shape[0], : shape[1], : shape[2]]
    return ((z - centre[0]) / radii[0]) ** 2 + ((y - centre[1]) / radii[1]) ** 2 + (
        (x - centre[2]) / radii[2]
    ) ** 2 <= 1


@pytest.mark.parametrize("seed", range(6))
def test_TC_152_independent_dice_and_hd95_equal_the_pipeline(seed):
    rng = np.random.default_rng(seed)
    shape = (9, 60, 50)
    r = blob(shape, (4, 30, 25), (2.5, 9, 12))
    p = blob(shape, (4 + rng.integers(-1, 2), 30 + rng.integers(-4, 5), 25 + rng.integers(-4, 5)),
             (2 + rng.random(), 7 + 4 * rng.random(), 10 + 4 * rng.random()))  # fmt: skip
    p[rng.integers(0, 9), rng.integers(0, 60), rng.integers(0, 50)] = True  # a stray voxel
    per_axis = array_axis_spacing(SPACING)
    assert CROSS.independent_dice(p, r) == dice(p, r)
    assert math.isclose(CROSS.independent_hd95(p, r, per_axis), hd95(p, r, per_axis), abs_tol=1e-9)


def test_TC_152_independent_hd95_sees_a_one_bscan_shift_at_the_bscan_spacing():
    r = np.zeros((5, 20, 20), dtype=bool)
    r[2, 5:15, 5:15] = True
    p = np.roll(r, 1, axis=0)
    assert CROSS.independent_hd95(p, r, array_axis_spacing(SPACING)) == pytest.approx(0.047)
    # and the project order, given to it unreordered, gives a different (wrong) answer
    assert CROSS.independent_hd95(p, r, SPACING) != pytest.approx(0.047)


def test_TC_152_empty_cases_follow_the_stated_definitions():
    empty, full = np.zeros((3, 4, 4), dtype=bool), np.ones((3, 4, 4), dtype=bool)
    assert CROSS.independent_hd95(empty, empty, (1, 1, 1)) == 0.0
    assert math.isnan(CROSS.independent_hd95(full, empty, (1, 1, 1)))
    assert CROSS.independent_dice(empty, empty) == 1.0


def test_TC_152_the_comparison_reports_a_difference_and_passes_agreement():
    row = {"dice": 0.5, "hd95": 0.1, "predicted_voxels": 3, "reference_voxels": 4,
           "predicted_mm3": 1.0, "reference_mm3": 2.0}  # fmt: skip
    a = {c: dict(row) for c in CROSS.CLASSES}
    b = {c: dict(row) for c in CROSS.CLASSES}
    assert CROSS.compare(a, b) == []
    b["SRF"]["hd95"] = 0.1 + 1e-6
    assert CROSS.compare(a, b) == ["SRF hd95: pipeline 0.1, independent 0.100001"]
