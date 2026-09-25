#!/usr/bin/env python
"""Fail a commit that introduces a new identifier without a change control entry.

Traces to: NFR-007 (change control), NFR-008 (traceability)
Verifies: TC-107

**The failure this exists to catch.** Commit `3c16231` added SRS-065 to `docs/02` and
did not touch `docs/13`. Its message described a change control entry that was not
there, because the patch script writing it aborted partway and the commit proceeded
anyway. It was found by reading the result rather than by any check.

**Why this rule and not a commit-message check.** The obvious guard — fail when a message
names a `docs/` file the commit does not touch — would not have caught it. That commit
*did* touch `docs/11`; the first edit applied before the script died. Measured against
all 37 commits in the repository's history, the message rule fires zero times and this
rule fires exactly once: on `3c16231`. A guard is worth having when it catches the thing
that actually happened.

CLAUDE.md rule 6 and NFR-007 both say a new requirement, hazard or control is recorded
with a date and rationale. This makes that mechanical instead of remembered.

What it cannot check: whether the entry is *true*. `docs/07` §8 says so of TC-107 and
that limit is unchanged — an entry can exist and be wrong. This closes the gap where no
entry exists at all.

Note on the SHA: the incident commit was `104342b` until the history was rewritten on
2026-09-23 to strip co-author trailers, which changed every SHA from the root onward
without changing any content. It is `3c16231` now. TC-108 checks that citations like
this one keep resolving.
"""

from __future__ import annotations

import re
import subprocess
import sys

IDENTIFIER = re.compile(r"\b(?:URS|SRS|NFR|HAZ|RC|TC|SOUP)-\d{3}\b")
CHANGE_LOG = "docs/13_change_control_log.md"
OVERRIDE = "no-change-control"


def _run(args: list[str]) -> str:
    result = subprocess.run(
        args, capture_output=True, check=False, encoding="utf-8", errors="replace"
    )
    return result.stdout or ""


def staged_files() -> set[str]:
    return {p.replace("\\", "/") for p in _run(["git", "diff", "--cached", "--name-only"]).split()}


def newly_introduced_identifiers() -> set[str]:
    """Identifiers appearing in the staged docs/ diff that do not yet exist in docs/.

    Comparing against the whole of `docs/` at HEAD, rather than against the same file,
    means moving an identifier between documents is not treated as introducing it.
    """
    diff = _run(["git", "diff", "--cached", "--unified=0", "--", "docs"])
    added = {
        match.group(0)
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
        for match in IDENTIFIER.finditer(line)
    }
    if not added:
        return set()
    existing = set(
        _run(
            [
                "git",
                "grep",
                "-hoE",
                r"\b(URS|SRS|NFR|HAZ|RC|TC|SOUP)-[0-9]{3}\b",
                "HEAD",
                "--",
                "docs",
            ]
        ).split()
    )
    return added - existing


def main(argv: list[str]) -> int:
    message = ""
    if len(argv) > 1:
        try:
            with open(argv[1], encoding="utf-8") as handle:
                message = handle.read()
        except OSError:
            message = ""
    if OVERRIDE in message:
        return 0

    introduced = newly_introduced_identifiers()
    if not introduced:
        return 0
    if CHANGE_LOG in staged_files():
        return 0

    print(
        f"this commit introduces {len(introduced)} new identifier(s) but does not touch "
        f"{CHANGE_LOG}:",
        file=sys.stderr,
    )
    for identifier in sorted(introduced):
        print(f"    {identifier}", file=sys.stderr)
    print(
        "\nNFR-007 and CLAUDE.md rule 6 require a new requirement, hazard, control or "
        f"test case to be recorded with a date and rationale. Add the entry, or put "
        f"'{OVERRIDE}' in the message to override deliberately.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
