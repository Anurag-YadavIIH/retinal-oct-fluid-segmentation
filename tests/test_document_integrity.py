"""Document and configuration integrity — docs/07 section 8.

Covers TC-105 (intended use change gate), TC-106 (image digests match the SOUP list)
and TC-108 (cited commit SHAs resolve).

Not an IEC 62304 verification level. These exist because this project's documents make
claims about each other and about the code, and nothing else checks them.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def section_text(document: Path, heading: str) -> str:
    """Return one top-level section of a Markdown document, heading included.

    Line endings are normalised to LF and trailing whitespace stripped before the text
    is returned. Without that, the same content hashes differently on a checkout where
    core.autocrlf rewrote it than it does in CI, and TC-105 would fail for a reason
    that has nothing to do with the intended use changing.
    """
    text = document.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if match is None:
        raise AssertionError(f"section '{heading}' not found in {document.name}")
    body = "\n".join(line.rstrip() for line in match.group(0).splitlines())
    return body.strip() + "\n"


# --- TC-105 -----------------------------------------------------------------------

# Hash of docs/01 section 2, "Indications for use".
#
# docs/03 section 5.2 states that widening the intended use voids the safety
# classification. This constant is the forcing function: changing section 2 fails this
# test, and the only way to make it pass is to update the hash deliberately — an edit a
# reviewer sees alongside whatever change to docs/03 accompanied it.
#
# What this is NOT: proof that re-classification happened. docs/07 section 7.3 states
# that limit. CI tests a merge result rather than a commit, so "modified in the same
# commit" is not observable here. The gate forces review; it does not replace it.
INDICATIONS_SHA256 = "a427085efa44a48f570ba1d67f786d4e8432dc372ec823f3050525c5d7a544b0"

INTENDED_USE = REPO_ROOT / "docs" / "01_intended_use.md"
SAFETY_CLASSIFICATION = REPO_ROOT / "docs" / "03_safety_classification.md"


def test_TC_105_indications_for_use_is_unchanged():
    current = hashlib.sha256(
        section_text(INTENDED_USE, "2. Indications for use").encode("utf-8")
    ).hexdigest()
    assert current == INDICATIONS_SHA256, (
        "docs/01 section 2 (indications for use) has changed.\n\n"
        "Widening the intended use voids the safety classification in docs/03 "
        "(docs/03 section 5.2). Before updating INDICATIONS_SHA256 to\n"
        f"    {current}\n"
        "confirm that docs/03 has been reviewed against the new indications, and record "
        "the change in docs/13 per NFR-007."
    )


def test_TC_105_the_gate_detects_a_modified_section(tmp_path):
    """An assertion that never fires has not been shown to work."""
    original = INTENDED_USE.read_text(encoding="utf-8")
    widened = tmp_path / "01_intended_use.md"
    widened.write_text(
        original.replace("| Population | Adult |", "| Population | Adult and paediatric |"),
        encoding="utf-8",
    )
    changed = hashlib.sha256(
        section_text(widened, "2. Indications for use").encode("utf-8")
    ).hexdigest()
    assert changed != INDICATIONS_SHA256


def test_TC_105_hash_is_stable_under_line_ending_rewrites(tmp_path):
    """core.autocrlf must not be able to fail this gate."""
    lf = INTENDED_USE.read_text(encoding="utf-8").replace("\r\n", "\n")
    crlf_copy = tmp_path / "crlf.md"
    crlf_copy.write_bytes(lf.replace("\n", "\r\n").encode("utf-8"))
    assert section_text(crlf_copy, "2. Indications for use") == section_text(
        INTENDED_USE, "2. Indications for use"
    )


def test_TC_105_safety_classification_still_claims_the_dependency():
    """The gate is pointless if docs/03 stops asserting that widening voids it."""
    text = SAFETY_CLASSIFICATION.read_text(encoding="utf-8")
    assert "classification is void" in text


# --- TC-106 -----------------------------------------------------------------------

SOUP_LIST = REPO_ROOT / "docs" / "04_soup_list.md"
DOCKERFILE = REPO_ROOT / "docker" / "Dockerfile.api"
COMPOSE = REPO_ROOT / "docker" / "docker-compose.yml"

DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def digests_in(path: Path) -> set[str]:
    return set(DIGEST.findall(path.read_text(encoding="utf-8")))


def soup_row_digest(soup_id: str) -> str:
    for line in SOUP_LIST.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"| {soup_id} |"):
            found = DIGEST.findall(line)
            if not found:
                raise AssertionError(f"{soup_id} row records no digest")
            return found[0]
    raise AssertionError(f"{soup_id} not found in docs/04")


@pytest.mark.parametrize(
    ("soup_id", "source"),
    [("SOUP-017", DOCKERFILE), ("SOUP-014", COMPOSE)],
)
def test_TC_106_image_digest_matches_the_soup_row(soup_id, source):
    recorded = soup_row_digest(soup_id)
    used = digests_in(source)
    assert recorded in used, (
        f"{source.relative_to(REPO_ROOT)} does not use the digest recorded against "
        f"{soup_id} in docs/04.\n"
        f"  recorded: {recorded}\n"
        f"  in file:  {sorted(used) or 'none — the image may have been repinned to a tag'}\n"
        "Changing an image is a SOUP change: update the row and record it in docs/13."
    )


@pytest.mark.parametrize("source", [DOCKERFILE, COMPOSE])
def test_TC_106_images_are_pinned_by_digest_not_by_tag(source):
    """Catches a repin to a mutable tag, which TC-106's equality check alone would not."""
    assert digests_in(source), (
        f"{source.relative_to(REPO_ROOT)} pins no image by digest. A tag is not a "
        "version: it resolves to different contents over time and defeats reproducible "
        "builds (NFR-002, docs/04 SOUP-017)."
    )


def test_TC_106_the_check_detects_a_drifted_digest(tmp_path):
    drifted = tmp_path / "Dockerfile.api"
    drifted.write_text(
        DOCKERFILE.read_text(encoding="utf-8").replace(
            soup_row_digest("SOUP-017"), "sha256:" + "0" * 64
        ),
        encoding="utf-8",
    )
    assert soup_row_digest("SOUP-017") not in digests_in(drifted)


# --- TC-108 -----------------------------------------------------------------------
#
# Every commit SHA cited in prose must resolve to a commit reachable from main.
#
# Why this exists. On 2026-09-23 the history was rewritten to strip co-author trailers
# from 44 commit messages. Content was untouched, but every SHA from the root commit
# onward changed, and nine citations across four files silently became references to
# commits that no longer existed. Nothing caught it; it was found by reading.
#
# The citation that mattered was 104342b, the incident that scripts/check_change_control.py
# was written in response to and cites as its own justification. A guard whose stated
# evidence does not resolve is a guard a reviewer cannot check.
#
# This is deliberately a test rather than a note in docs/07, because a check that is
# specified and not wired is not a check — the same distinction docs/05 section 5.3
# draws, and the reason TC-107 sat inert until the hook was installed.

SHA_CITATION = re.compile(r"\b[0-9a-f]{7,40}\b")

# SHAs that no longer resolve and are cited deliberately, because the document's subject
# IS the superseded identifier. Every entry needs a reason, and every entry is asserted
# genuinely unreachable below — so this cannot be used to silence a citation that ought
# to resolve. Adding a live SHA here fails the companion test.
RETIRED_SHAS = {
    # docs/13, 2026-09-23: the pre-rewrite SHAs, named so a reader holding an older
    # clone can map their copy onto the current history. Recording the remap requires
    # naming both sides of it.
    "35027a3": "pre-rewrite SHA of the initial commit, now 945705d",
    "8c2086b": "pre-rewrite SHA of the docs/06 draft, now 56a30b3",
    "104342b": "pre-rewrite SHA of the change control incident, now 3c16231",
    "1a9d75b": "pre-rewrite SHA of the DICOMweb client commit, now dde5706",
}

# .pre-commit-config.yaml is in this list because a scan scoped to docs/ and scripts/
# missed the citation it carries. The set is the files whose *prose* names commits.
CITING_FILES = (
    sorted((REPO_ROOT / "docs").glob("*.md"))
    + sorted((REPO_ROOT / "scripts").glob("*.py"))
    + [REPO_ROOT / "CLAUDE.md", REPO_ROOT / ".pre-commit-config.yaml"]
)


def git_output(*args: str) -> str:
    import subprocess

    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        pytest.skip(f"git unavailable or not a repository: {' '.join(args)}")
    return result.stdout


def cited_shas() -> dict[str, list[str]]:
    """Map each cited SHA to the files citing it.

    Two things are deliberately NOT recognised, and both are false negatives rather
    than false positives:

    - An abbreviation that happens to contain no a-f digit. Roughly 4% of seven
      character abbreviations are all-decimal, and requiring a letter is what keeps
      DICOM codes (`49755003`, `118565006`) and tags (`00081199`) out of the results.
      Citing such a SHA is not wrong, it is simply unchecked.
    - Uppercase hex, because DICOM tags are written uppercase throughout this repo.

    A 64 character sha256 digest is excluded by the 40 character ceiling: the word
    boundary cannot fall mid-token, so no prefix of it matches.
    """
    found: dict[str, list[str]] = {}
    for path in CITING_FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for token in SHA_CITATION.findall(text):
            if not any(character in "abcdef" for character in token):
                continue
            if token in RETIRED_SHAS:
                continue
            found.setdefault(token, []).append(path.relative_to(REPO_ROOT).as_posix())
    return found


def assert_history_is_available() -> None:
    """Fail loudly on a shallow clone rather than reporting every citation as dangling.

    A shallow checkout contains one commit, so `git rev-list` returns one SHA and every
    cited SHA appears unresolvable. The citations would be fine and the diagnosis would
    be wrong. This separates the two failures, because they have opposite fixes: a stale
    citation is remapped, a shallow clone is deepened.

    Deliberately an assertion and not a skip. Skipping would mean the guard silently
    stops running in exactly the environment it exists to protect -- which is the
    specified-but-not-wired failure this project has now hit three times.
    """
    if git_output("rev-parse", "--is-shallow-repository").strip() == "true":
        raise AssertionError(
            "this is a shallow clone, so commit history is not available and TC-108 "
            "cannot resolve any citation. This is NOT a stale-citation failure. In CI, "
            "set `fetch-depth: 0` on actions/checkout (it defaults to 1); locally, run "
            "`git fetch --unshallow`."
        )


def reachable_commits() -> set[str]:
    """Full SHAs reachable from main, falling back to origin/main then HEAD.

    The fallback exists for CI, where the checkout can be detached and `main` may not
    be a local branch. HEAD last rather than first so that a citation to a commit that
    exists only on an unmerged branch still fails when main is available.
    """
    for ref in ("main", "origin/main", "HEAD"):
        if git_output("rev-parse", "--verify", "--quiet", ref).strip():
            return set(git_output("rev-list", ref).split())
    pytest.skip("no main, origin/main or HEAD to resolve citations against")


def test_TC_108_every_cited_sha_resolves_to_a_commit_on_main():
    assert_history_is_available()
    reachable = reachable_commits()
    dangling = {
        sha: files
        for sha, files in cited_shas().items()
        if not any(full.startswith(sha) for full in reachable)
    }
    listing = "\n".join(
        f"  {sha} cited in {', '.join(files)}" for sha, files in sorted(dangling.items())
    )
    assert not dangling, (
        "commit SHAs cited in prose do not resolve to any commit reachable from main:\n"
        + listing
        + "\n\nA history rewrite changes every SHA from the rewritten commit onward. "
        "Remap the citations, or prefer a description plus a date where the identity of "
        "the commit is not itself the point (docs/13, 2026-09-25). If the superseded SHA "
        "is itself the subject, add it to RETIRED_SHAS with a reason."
    )


def test_TC_108_retired_shas_are_genuinely_unreachable():
    """RETIRED_SHAS must not become a way to excuse a citation that should resolve."""
    assert_history_is_available()
    reachable = reachable_commits()
    live = {
        sha: reason
        for sha, reason in RETIRED_SHAS.items()
        if any(full.startswith(sha) for full in reachable)
    }
    assert not live, (
        "these SHAs are exempted as retired but still resolve on main, so the exemption "
        f"is hiding a citation the guard should be checking: {sorted(live)}"
    )


def test_TC_108_the_check_detects_a_dangling_citation():
    """The guard must fail on a SHA that cannot resolve, or it proves nothing."""
    reachable = reachable_commits()
    impossible = "deadbee"
    assert not any(full.startswith(impossible) for full in reachable)


def test_TC_108_finds_the_citations_that_are_actually_there():
    """Guards against the regex silently matching nothing, which would pass vacuously."""
    found = cited_shas()
    assert found, "no commit SHA citations found at all — the pattern has stopped matching"
    assert any(
        "scripts/check_change_control.py" in files for files in found.values()
    ), "the change control hook's own citation is no longer being scanned"
