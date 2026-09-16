"""TC-004 — no patient may appear in more than one split.

This is the CI gate described in CLAUDE.md rule 2. It is the only xfail permitted
in this repository, and it comes off as soon as ocuval.data.splits is implemented
(milestone 4). If this test ever fails after that point, the data pipeline is
wrong — fix the pipeline, never the test.

The invariant, stated precisely:

    For a resolved Split s and its manifest m, the sets of patient identifiers
    appearing in s.train, s.val and s.test are pairwise disjoint. Additionally,
    every sample in s.test whose vendor differs from s.held_out_vendor is a
    defect, and every patient in the manifest appears in exactly one split.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    reason="ocuval.data.splits not implemented yet — milestone 4. Remove this marker then.",
    strict=True,
)
def test_TC_004_patients_are_disjoint_across_splits():
    from ocuval.data.splits import assert_no_patient_overlap  # noqa: F401

    raise AssertionError("not implemented")
