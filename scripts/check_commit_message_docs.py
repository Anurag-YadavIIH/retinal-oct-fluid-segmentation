#!/usr/bin/env python
"""Fail a commit whose message claims to change a document it does not touch.

Traces to: NFR-007, NFR-008 (change control and traceability)

**The failure this exists to catch.** On 2026-09-19 a commit message described content
added to `docs/11` and `docs/13`. The patch script that should have written it aborted
partway on a stale anchor, and the commit proceeded anyway, so the message documented a
decision the repository did not contain. It was caught by reading the result, not by any
check. In a project whose entire argument is that claims should be verifiable, a commit
message asserting an untrue thing about its own contents is precisely the failure class
worth automating away.

**Why claim phrases rather than any mention.** Naming a document is usually a
cross-reference — "per `docs/05` RC-029" — and failing those would fire on most honest
commits in this repository. A guard that cries wolf gets disabled, which is worse than
no guard. This hook therefore fires only when the message *asserts that the commit
changed* the document: "recorded in docs/11", "docs/13 updated", "adds to docs/07".

Run as a `commit-msg` hook, so it sees both the message and the staged tree.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DOC_PATH = r"`?(docs/[0-9A-Za-z_./-]*\.md)`?"

# Phrases that turn a mention into a claim about this commit's own contents. Kept
# short and literal: a clever matcher here would be its own source of false confidence.
CLAIM_BEFORE = (
    r"(?:recorded in|records|written into|added to|adds to|updated in|carried into|"
    r"appended to|now in|landed in|documented in)\s+"
)
CLAIM_AFTER = (
    r"\s+(?:updated|amended|extended|now records|now carries|now states|now reads|"
    r"gains|rewritten|regenerated|corrected)"
)

PATTERNS = (
    re.compile(CLAIM_BEFORE + DOC_PATH, re.I),
    re.compile(DOC_PATH + CLAIM_AFTER, re.I),
)

OVERRIDE = "no-doc-check"


def staged_files() -> set[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip().replace("\\", "/") for line in out.stdout.splitlines() if line.strip()}


def claimed_documents(message: str) -> set[str]:
    claimed: set[str] = set()
    for line in message.splitlines():
        if line.lstrip().startswith("#"):
            continue  # git's own comment lines
        for pattern in PATTERNS:
            claimed.update(m.replace("\\", "/") for m in pattern.findall(line))
    return claimed


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: check_commit_message_docs.py <commit-msg-file>", file=sys.stderr)
        return 2

    message = Path(argv[1]).read_text(encoding="utf-8")
    if OVERRIDE in message:
        return 0

    claimed = claimed_documents(message)
    if not claimed:
        return 0

    touched = staged_files()
    missing = sorted(c for c in claimed if c not in touched)
    if not missing:
        return 0

    print("commit message claims to change documents this commit does not touch:", file=sys.stderr)
    for path in missing:
        print(f"    {path}", file=sys.stderr)
    print(
        "\nEither stage the change the message describes, or reword the message so it "
        f"cross-references rather than claims. Add '{OVERRIDE}' to the message to "
        "override deliberately.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
