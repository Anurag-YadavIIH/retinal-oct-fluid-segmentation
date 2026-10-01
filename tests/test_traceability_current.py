"""TC-104: the traceability matrix is current.

Verifies: TC-104
Traces to: NFR-008

`docs/09` states coverage counts. Nothing recomputed them, so they drifted -- to "50 of 85
written, 47 executed" against an actual 86 and 83, understating the written count by 26. The
drift was found by a person reading the figures, which until now was the only thing that
could find it. TC-104 was registered for exactly this and went unwritten for long enough
that the defect it was meant to prevent happened twice on the same artefact (`docs/07` §3
rule 8, and `docs/13` 2026-09-30).

**The direction of the check matters.** This parses the numbers `docs/09` *claims*, recomputes
them from the source documents and the test files, and asserts the two agree. A test that
merely printed the recomputed figures would be a reporting tool; this one fails when the
document and the repository disagree, whichever of them is wrong. So editing `docs/09`
without changing reality fails, and adding a test without updating `docs/09` fails too.

**What "executed" means here, stated rather than assumed.** A test case counts as *never
executed* when every test function carrying its identifier is marked `requires_pacs` -- the
documented reason the three Docker-blocked cases cannot run. That is computed from the test
sources, not from a pytest collection, because running pytest inside pytest makes the answer
depend on which invocation is in progress.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
TESTS = REPO_ROOT / "tests"

MATRIX = DOCS / "09_traceability_matrix.md"
PROTOCOL = DOCS / "07_vv_protocol.md"
REQUIREMENTS = DOCS / "02_software_requirements_spec.md"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


# --- recomputing the truth -------------------------------------------------------------


def registered_test_cases() -> set[str]:
    """Identifiers with a ROW in `docs/07` §6, parsed from the first table cell.

    From the first cell and not from a mention in prose, for the reason TC-109 records: an
    identifier named inside a `docs/13` entry once satisfied its own registration check.
    """
    found = set()
    for line in text(PROTOCOL).splitlines():
        match = re.match(r"\|\s*\**(TC-\d{3})\b", line.strip())
        if match:
            found.add(match.group(1))
    return found


def _marks(node, module_marks: set[str]) -> set[str]:
    """Marker names on one test function, plus the module's own `pytestmark`."""
    names = set(module_marks)
    for decorator in node.decorator_list:
        attribute = decorator.func if isinstance(decorator, ast.Call) else decorator
        parts = []
        while isinstance(attribute, ast.Attribute):
            parts.append(attribute.attr)
            attribute = attribute.value
        if parts and parts[-1] != "mark":
            # pytest.mark.<name> -> parts == ["<name>", "mark"]
            names.add(parts[0])
        elif len(parts) >= 2:
            names.add(parts[0])
    return names


def _module_marks(tree: ast.Module) -> set[str]:
    """`pytestmark = pytest.mark.X` or a list of them, at module level."""
    found: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(t, "id", None) == "pytestmark" for t in node.targets):
            continue
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Attribute):
                parent = sub.value
                if isinstance(parent, ast.Attribute) and parent.attr == "mark":
                    found.add(sub.attr)
    return found


def written_test_cases() -> dict[str, set[str]]:
    """Identifier -> the union of markers on every test function carrying it.

    **Parsed with `ast`, not by searching for the marker's name in the file.** The first
    version of this function string-matched `"requires_pacs"` anywhere in the source and
    counted eight cases as never executed instead of three -- because one file mentions the
    marker in a comment and because *this file's own docstring* names it. That is `docs/07`
    §3 rule 8 inside the test written to enforce rule 8: resolve the mechanism, do not
    grep for its name.
    """
    out: dict[str, set[str]] = {}
    for path in sorted(TESTS.glob("test_*.py")):
        tree = ast.parse(text(path))
        module_marks = _module_marks(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            match = re.match(r"test_TC_(\d{3})", node.name)
            if not match:
                continue
            identifier = f"TC-{match.group(1)}"
            out.setdefault(identifier, set())
            out[identifier] |= _marks(node, module_marks)
    return out


def never_executed(written: dict[str, set[str]]) -> set[str]:
    """Written cases no invocation here can run: every carrier needs a PACS.

    A case counts as never executed when `requires_pacs` is on it, since CI and every local
    sweep deselect that marker and Docker is not installed (`docs/08` D3's sibling).
    """
    return {identifier for identifier, marks in written.items() if "requires_pacs" in marks}


def allocated_srs() -> tuple[int, int]:
    """(SRS rows, SRS rows naming at least one test case) from `docs/02`.

    SRS rows carry a fourth column holding their test cases. **NFR rows carry only three**
    and name no test case at all -- their allocation is expressed in the other direction, by
    `docs/07` §6's "Verifies" column. The first draft of this test asserted NFR rows had a TC
    column and failed 0 of 8, which is how the asymmetry was found; it is recorded here so
    the next reader does not take the failure for missing coverage.
    """
    rows = with_test = 0
    for line in text(REQUIREMENTS).splitlines():
        if not re.match(r"\|\s*SRS-\d{3}\s*\|", line.strip()):
            continue
        rows += 1
        if re.search(r"TC-\d{3}", line.rsplit("|", 2)[-2]):
            with_test += 1
    return rows, with_test


def nfr_identifiers() -> set[str]:
    return set(re.findall(r"\|\s*(NFR-\d{3})\s*\|", text(REQUIREMENTS)))


def nfr_covered_by_register() -> set[str]:
    """NFRs named by at least one TC row in `docs/07` §6 -- the direction that carries it."""
    covered = set()
    for line in text(PROTOCOL).splitlines():
        if re.match(r"\|\s*\**TC-\d{3}\b", line.strip()):
            covered |= set(re.findall(r"NFR-\d{3}", line))
    return covered


# --- what the document claims ----------------------------------------------------------


def claimed(pattern: str) -> int:
    """One bolded figure from `docs/09`, by the sentence that introduces it."""
    match = re.search(pattern, text(MATRIX))
    assert match, f"docs/09 no longer states a figure matching {pattern!r}"
    return int(match.group(1))


# --- the assertions --------------------------------------------------------------------


def test_TC_104_the_registered_count_is_current():
    assert claimed(r"registered\*\* in `docs/07` §6: \*\*(\d+)\*\*") == len(
        registered_test_cases()
    ), "docs/09's registered count does not match the rows in docs/07 §6"


def test_TC_104_the_written_count_is_current():
    assert claimed(r"\*\*written\*\*: \*\*(\d+)\*\*") == len(written_test_cases()), (
        "docs/09's written count does not match the `test_TC_nnn_` functions in tests/. "
        "Either a test was added without updating docs/09, or the figure is stale."
    )


def test_TC_104_the_executed_count_is_current():
    written = written_test_cases()
    blocked = never_executed(written)
    assert claimed(r"\*\*(\d+) are executed\*\*") == len(written) - len(blocked)
    assert claimed(r"\*\*(\d+) have never been run\*\*") == len(blocked)


def test_TC_104_the_never_run_cases_are_the_ones_named():
    """The identifiers, not just the count. A different three would keep the count right."""
    blocked = never_executed(written_test_cases())
    stated = re.search(r"have never been run\*\* \(([^)]+)\)", text(MATRIX))
    assert stated, "docs/09 no longer names the never-run cases"
    named = {part.strip() for part in stated.group(1).split(",")}
    assert (
        named == blocked
    ), f"docs/09 names {sorted(named)} as never run; the test sources say {sorted(blocked)}"


def test_TC_104_the_unwritten_count_is_current():
    registered = registered_test_cases()
    written = set(written_test_cases())
    assert claimed(r"\*\*(\d+)\*\* are registered and unwritten") == len(registered - written)


def test_TC_104_the_requirement_allocation_counts_are_current():
    srs_rows, srs_with_test = allocated_srs()
    assert srs_with_test == srs_rows, (
        f"{srs_rows - srs_with_test} SRS rows name no test case; every software "
        f"requirement must trace to at least one (CLAUDE.md §3)"
    )
    assert (
        claimed(r"\*\*(\d+) of \d+\*\*\s+SRS") == srs_rows
    ), f"docs/09 states a different SRS count from the {srs_rows} rows in docs/02"


def test_TC_104_every_nfr_is_verified_by_a_registered_test_case():
    """NFR coverage comes from `docs/07` §6, since NFR rows in `docs/02` have no TC column."""
    identifiers = nfr_identifiers()
    uncovered = sorted(identifiers - nfr_covered_by_register())
    assert not uncovered, f"NFRs named by no TC row in docs/07 §6: {uncovered}"
    assert claimed(r"\*\*(\d+) of \d+\*\* NFR") == len(identifiers)


def test_TC_104_every_written_case_is_registered():
    """Overlaps TC-109 deliberately: this is the check whose absence let three slip."""
    unregistered = sorted(set(written_test_cases()) - registered_test_cases())
    assert not unregistered, f"written but unregistered in docs/07 §6: {unregistered}"


def test_TC_104_can_fail():
    """docs/07 §3 rule 8: the mechanism must be able to refuse.

    If `claimed` silently returned the recomputed value, or the parsers returned the same
    thing by construction, every assertion above would pass unconditionally. This asserts
    the parsers are reading two independent places that could disagree.
    """
    assert claimed(r"\*\*written\*\*: \*\*(\d+)\*\*") == len(written_test_cases())
    with pytest.raises(AssertionError, match="no longer states"):
        claimed(r"\*\*written-nonsense\*\*: \*\*(\d+)\*\*")
    assert len(registered_test_cases()) > len(written_test_cases()), (
        "registered and written are equal, so the two parsers may be reading one source; "
        "they are independent only if they can differ"
    )
