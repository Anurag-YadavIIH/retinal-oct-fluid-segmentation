"""Every test identifier is registered, and a run record cannot contradict itself.

Covers TC-109 (NFR-008, SRS-085).

Two failures prompted this, on 2026-09-30, and they are the same failure twice:

**An identifier used by a test with no row in the register.** `TC-087` named four
tests in `tests/test_multipart_upload.py` for two days while `docs/07` had no row for
it. The `commit-msg` hook did not object, and could not: it requires a new identifier
appearing in `docs/` to come with a `docs/13` entry, and TC-087 appeared **inside that
very entry** -- so the guard was satisfied by the thing it was guarding.

**A record whose two halves disagreed.** `determinism.json` reported
`deterministic_algorithms: true` above 1308 lines saying the loss function had no
deterministic implementation. Each statement was true alone; together they misled,
because a reader takes the first as the answer.

Both are `docs/07` §3 rule 8: nothing inspected the artefact.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = REPO_ROOT / "docs" / "07_vv_protocol.md"


def registered_ids() -> set[str]:
    """Identifiers that have a register ROW, not merely a mention.

    A row, because a mention in prose is exactly what let TC-087 slip through: it was
    named in a `docs/13` entry and in a commit message, and neither is a register.
    """
    rows = set()
    for line in PROTOCOL.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        first_cell = stripped.split("|")[1].strip()
        match = re.fullmatch(r"\**(TC-\d{3})\**", first_cell)
        if match:
            rows.add(match.group(1))
    return rows


def test_ids_in_use() -> dict[str, list[str]]:
    used: dict[str, list[str]] = {}
    for path in sorted((REPO_ROOT / "tests").glob("*.py")):
        for name in re.findall(r"test_(TC_\d{3})", path.read_text(encoding="utf-8")):
            used.setdefault(name.replace("TC_", "TC-"), []).append(path.name)
    return used


# --- register completeness --------------------------------------------------------


def test_TC_109_the_register_is_not_empty():
    """Guards the guard: a parser that matched nothing would pass everything below."""
    rows = registered_ids()
    assert len(rows) >= 60, f"only {len(rows)} register rows parsed; the pattern is wrong"
    for known in ("TC-004", "TC-059", "TC-087", "TC-120"):
        assert known in rows, f"{known} should be registered and was not parsed"


def test_TC_109_every_test_identifier_has_a_register_row():
    used = test_ids_in_use()
    assert used, "no TC identifiers found in the test suite"
    missing = {tc: files for tc, files in sorted(used.items()) if tc not in registered_ids()}
    assert not missing, (
        f"identifiers used by tests with no row in docs/07 §6 or §8: {missing}. A test "
        f"carrying an unregistered identifier traces to nothing, which is the gap "
        f"CLAUDE.md rule 5 exists to close. Naming it in docs/13 or a commit message is "
        f"not a register."
    )


# --- the determinism record ---------------------------------------------------------


def test_TC_109_a_report_with_fallbacks_does_not_claim_determinism():
    from ocuval.training.checkpoint import DeterminismReport

    report = DeterminismReport(
        requested=True,
        deterministic_algorithms=True,
        cudnn_deterministic=True,
        cublas_workspace_config=":4096:8",
        fallbacks=["some_op does not have a deterministic implementation, but you set X"],
    )
    record = report.as_dict()
    assert (
        record["deterministic_algorithms"] is False
    ), "the record claims deterministic algorithms while listing a fallback"
    assert (
        record["deterministic_algorithms_granted"] is True
    ), "the distinction between requested-and-accepted and actually-achieved was lost"


def test_TC_109_a_clean_report_still_claims_determinism():
    """The invariant must not be satisfied by always reporting False."""
    from ocuval.training.checkpoint import DeterminismReport

    record = DeterminismReport(
        requested=True,
        deterministic_algorithms=True,
        cudnn_deterministic=True,
        cublas_workspace_config=":4096:8",
        fallbacks=[],
    ).as_dict()
    assert record["deterministic_algorithms"] is True


def test_TC_109_fallbacks_are_stored_deduplicated():
    from ocuval.training.checkpoint import DeterminismReport

    message = "nll_loss2d_forward_out_cuda_template does not have a deterministic implementation"
    record = DeterminismReport(
        requested=True,
        deterministic_algorithms=True,
        cudnn_deterministic=True,
        cublas_workspace_config=None,
        fallbacks=[message] * 1308,
    ).as_dict()

    assert record["fallback_count"] == 1308, "the total must survive deduplication"
    assert len(record["fallbacks"]) == 1, "1308 copies of one operation is one row"
    entry = record["fallbacks"][0]
    assert entry["op"] == "nll_loss2d_forward_out_cuda_template"
    assert entry["count"] == 1308
    assert "first_seen" in entry
    assert len(json.dumps(record)) < 4000, (
        f"the record serialises to {len(json.dumps(record))} bytes; the Stage 1 file was "
        f"465 KB of near-identical repetition"
    )


def test_TC_109_distinct_operations_keep_distinct_rows():
    """Deduplication must not collapse genuinely different findings into one."""
    from ocuval.training.checkpoint import summarise_fallbacks

    rows = summarise_fallbacks(
        ["alpha_op does not have a deterministic implementation"] * 3
        + ["beta_op does not have a deterministic implementation"]
    )
    assert [(r["op"], r["count"]) for r in rows] == [("alpha_op", 3), ("beta_op", 1)]


@pytest.mark.requires_data
def test_TC_109_a_real_run_record_is_self_consistent():
    """Checked against an actual run directory where one exists."""
    runs = sorted((REPO_ROOT / "artifacts" / "runs").glob("*/determinism.json"))
    if not runs:
        pytest.skip("no run directory on this machine")
    checked = 0
    for path in runs:
        record = json.loads(path.read_text(encoding="utf-8"))
        if "deterministic_algorithms_granted" not in record:
            # Written before SRS-085 existed. A run record states what happened and is
            # not edited afterwards to satisfy a rule introduced later -- the Stage 1
            # file's self-contradiction is preserved deliberately and reported as a
            # finding in docs/08 instead.
            continue
        checked += 1
        if record.get("fallbacks"):
            assert (
                record["deterministic_algorithms"] is False
            ), f"{path} claims deterministic algorithms while listing fallbacks"
    if checked == 0:
        pytest.skip("no run record written since SRS-085 was introduced")
