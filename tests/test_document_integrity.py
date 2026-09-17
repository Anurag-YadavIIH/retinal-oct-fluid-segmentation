"""Document and configuration integrity — docs/07 section 8.

Covers TC-105 (intended use change gate) and TC-106 (image digests match the SOUP list).

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
