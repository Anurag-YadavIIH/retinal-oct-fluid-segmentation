"""Compare two evaluation records leaf by leaf, by exact equality, with no tolerance.

Serves: `docs/07` §17.7b and `docs/08` D7 -- a re-run of a sealed bucket is admissible only if
every aggregate it reports reproduces the original record exactly.

Excluded keys, and only these, because they legitimately differ between two runs:

- `utc`: when the run happened.
- `notes`: the run's own provenance, including the evaluation commit.
- `bucket_access_count`: rises by one per sealed access, by design (SRS-088).
- `per_volume`: absent from records written before `6295bd0` (SRS-089).

Every other leaf -- each value, interval, `n` and bootstrap setting -- must match. Floats are
compared with `==`, because "close" is the claim this comparison exists to rule out.

Exit status: 0 identical, 1 different, 2 unreadable input.

Usage:
    python scripts/compare_evaluation_records.py REFERENCE.json CANDIDATE.json
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

EXCLUDED = frozenset({"utc", "notes", "bucket_access_count", "per_volume"})
ABSENT = "<absent>"


def leaves(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Every scalar in the record, keyed by its path. List lengths are leaves too."""
    if isinstance(node, dict):
        for key in sorted(node):
            if path == "" and key in EXCLUDED:
                continue
            yield from leaves(node[key], f"{path}/{key}")
    elif isinstance(node, list):
        yield f"{path}#len", len(node)
        for index, item in enumerate(node):
            yield from leaves(item, f"{path}[{index}]")
    else:
        yield path, node


def compare(reference: dict, candidate: dict) -> tuple[int, list[tuple[str, Any, Any]]]:
    ref, cand = dict(leaves(reference)), dict(leaves(candidate))
    differ = [
        (key, ref.get(key, ABSENT), cand.get(key, ABSENT))
        for key in sorted(set(ref) | set(cand))
        if ref.get(key, ABSENT) != cand.get(key, ABSENT)
    ]
    return len(ref), differ


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        reference, candidate = (json.loads(Path(p).read_text(encoding="utf-8")) for p in args)
    except (OSError, ValueError) as error:
        print(f"!! cannot read records: {error}", file=sys.stderr)
        return 2
    count, differ = compare(reference, candidate)
    print(f"reference {args[0]}\ncandidate {args[1]}")
    print(f"compared {count} leaves, excluded {sorted(EXCLUDED)}")
    if not differ:
        print("IDENTICAL: every compared leaf matches exactly")
        return 0
    print(f"DIFFER: {len(differ)} leaves")
    for key, before, after in differ:
        print(f"  {key}: {before!r} -> {after!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
