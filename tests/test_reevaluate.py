"""TC-137 — the re-evaluation chain follows `docs/07` §17.11 and writes only new files.

Traces to: SRS-096

**Argument handling and the step plan only. Nothing here executes the chain**: no evaluation,
no unlock, no git call and no read of the access log. That is by the author's instruction;
the chain's first execution is the author's own run, and its status log records it.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("reevaluate", REPO / "scripts" / "10_reevaluate.py")
CHAIN = importlib.util.module_from_spec(SPEC)
sys.modules["reevaluate"] = CHAIN  # dataclasses resolve their module through sys.modules
SPEC.loader.exec_module(CHAIN)

APPROVER = "Anurag Yadav"


def plan():
    return CHAIN.build_plan(CHAIN.parse_args(["--approved-by", APPROVER]))


def test_TC_137_the_approver_is_required():
    with pytest.raises(SystemExit):
        CHAIN.parse_args([])


def test_TC_137_an_empty_approver_is_refused():
    with pytest.raises(SystemExit):
        CHAIN.parse_args(["--approved-by", "   "])


def test_TC_137_unknown_arguments_are_refused():
    with pytest.raises(SystemExit):
        CHAIN.parse_args(["--approved-by", APPROVER, "--skip-check"])


def test_TC_137_the_steps_are_in_section_17_11_order():
    names = [step.name for step in plan()]
    assert names == [
        "access_counts",
        "cirrus_val_a",
        "cirrus_val_b",
        "reproducibility_seeded",
        "reproducibility_compare",
        "spectralis_holdout_val",
        "topcon_holdout_val",
        "cirrus_holdout_test",
        "cirrus_holdout_in_domain_ref",
        "spectralis_holdout_test",
        "spectralis_holdout_in_domain_ref",
        "topcon_holdout_test",
        "topcon_holdout_in_domain_ref",
    ]


def test_TC_137_every_output_is_new_and_under_corrected():
    outputs = [step.output for step in plan() if step.output is not None]
    assert len(outputs) == 10
    assert len(set(outputs)) == len(outputs), "two steps would write the same file"
    for output in outputs:
        assert output.parent.name == "corrected", output
        assert output.parent.parent in CHAIN.RUNS.values(), output


def test_TC_137_sealed_steps_unlock_with_section_17_11_and_open_steps_do_not():
    for step in plan():
        if step.argv is None:
            continue
        unlocking = "--unlock-bucket" in step.argv
        assert unlocking == (step.kind == "sealed"), step.name
        if unlocking:
            reason = step.argv[step.argv.index("--unlock-reason") + 1]
            assert "17.11" in reason and "17.7(b)" in reason and CHAIN.FIX_COMMIT in reason
            assert step.argv[step.argv.index("--approved-by") + 1] == APPROVER


def test_TC_137_the_comparison_reads_exactly_the_two_reproducibility_records():
    steps = {step.name: step for step in plan()}
    pair = (steps["cirrus_val_a"].output, steps["cirrus_val_b"].output)
    assert steps["reproducibility_compare"].inputs == pair
    assert steps["reproducibility_seeded"].inputs == pair
    assert steps["reproducibility_compare"].argv[-2:] == tuple(str(p) for p in pair)


def test_TC_137_the_expected_counts_are_the_ones_section_17_11_states():
    """The script's counts must not drift from the document that pre-registers them."""
    protocol = (REPO / "docs" / "07_vv_protocol.md").read_text(encoding="utf-8")
    section = protocol.split("### 17.11", 1)[1].split("\n---", 1)[0]
    stated = {
        (f"{fold}_holdout", bucket): int(now)
        for fold, bucket, now in re.findall(
            r"^\| (cirrus|spectralis|topcon) \| `(test|in_domain_ref)` \| \*\*(\d+) → \d+\*\*",
            section,
            re.M,
        )
    }
    assert stated == CHAIN.EXPECTED_COUNTS
