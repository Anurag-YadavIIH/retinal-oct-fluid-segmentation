"""The seal over the test and in-domain reference splits.

Traces to: SRS-088
Verifies: TC-125

`docs/07` §17.1 permits the held-out vendor's test set to be evaluated **exactly once**,
after training has ended and after the evaluation code is committed. §17.5 requires the
count of evaluations to be recorded, and §17.6 lists a second undeclared evaluation among
the things that would make Stage 2 invalid.

**A limit nobody counts is not a limit.** That is the whole argument for this module. The
protocol can say "once" as often as it likes; what makes it true is that reading the split
is a thing code cannot do by accident, and that each time it happens leaves a record
nobody had to remember to write.

So the two sealed buckets are unreadable without an `Unlock` carrying a reason, and every
successful access appends a line to a durable log under `artifacts/`. The in-domain
reference is sealed alongside the test split because it is the other half of the headline
comparison: tuning anything against it would bias the *gap* that `docs/10` reports, which
is the number this project exists to produce.

**What this is not.** It is not a security boundary. Anyone editing this file, or reading
the JSON directly, walks straight past it — and that is fine, because the risk being
controlled is *absent-minded* access during development, not an adversary. The control
that matters is the access log: if the test split is ever read twice, the log says so, and
`docs/08` has to explain it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# The buckets a `Split` carries that must never be read casually. `train` and `val` are
# deliberately absent: the pipeline is developed and validated against `val`, which is
# in-domain and already seen by model selection, so reading it costs nothing.
SEALED_BUCKETS = frozenset({"test", "in_domain_ref"})

ACCESS_LOG = Path("artifacts") / "sealed_access.jsonl"


class SealedSplitError(RuntimeError):
    """A sealed bucket was requested without an unlock (SRS-088)."""


@dataclass(frozen=True)
class Unlock:
    """Explicit, reasoned permission to read one sealed bucket.

    A dataclass rather than a boolean flag, and `reason` has no default. A boolean can be
    passed by a caller who has not thought about it -- `unlock=True` reads as a detail --
    whereas a value that cannot be constructed without writing down why makes the decision
    visible at the call site and in the log.
    """

    bucket: str
    reason: str
    approved_by: str

    def __post_init__(self) -> None:
        if self.bucket not in SEALED_BUCKETS:
            raise ValueError(
                f"{self.bucket!r} is not a sealed bucket; sealed are {sorted(SEALED_BUCKETS)}"
            )
        for field in ("reason", "approved_by"):
            if not str(getattr(self, field)).strip():
                raise ValueError(f"Unlock.{field} must say something; it goes in the access log")


def access_log_path(root: Path | None = None) -> Path:
    return (Path(root) if root else Path(os.environ.get("OCUVAL_ARTIFACTS", "artifacts"))) / (
        ACCESS_LOG.name
    )


def read_access_log(root: Path | None = None) -> list[dict]:
    path = access_log_path(root)
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def access_count(bucket: str, *, fold_id: str | None = None, root: Path | None = None) -> int:
    """How many times this bucket has been read, from the durable log.

    This is the number `docs/07` §17.5 requires in the evaluation output. It is read from
    the log rather than tracked in memory, so it survives the process and cannot be reset
    by restarting -- which is the only way a count of "exactly once" means anything.
    """
    return sum(
        1
        for entry in read_access_log(root)
        if entry.get("bucket") == bucket and (fold_id is None or entry.get("fold_id") == fold_id)
    )


def require_unsealed(
    bucket: str,
    unlock: Unlock | None = None,
    *,
    fold_id: str | None = None,
    root: Path | None = None,
) -> None:
    """Gate one bucket. Raises unless the bucket is open or a matching `Unlock` is given.

    Called by anything that resolves a bucket name to records. On success for a sealed
    bucket it appends to the access log **before** the caller does any work, so a crash
    mid-evaluation still leaves evidence that the split was opened -- the same reasoning
    that writes run provenance at the start of a stage rather than the end (SRS-031).
    """
    if bucket not in SEALED_BUCKETS:
        return
    if unlock is None:
        raise SealedSplitError(
            f"{bucket!r} is sealed (SRS-088). `docs/07` §17.1 permits the test split to be "
            f"evaluated exactly once, after the evaluation code is committed. Pass an "
            f"Unlock(bucket={bucket!r}, reason=..., approved_by=...) if that moment has "
            f"come; it will be recorded in {access_log_path(root)}."
        )
    if unlock.bucket != bucket:
        raise SealedSplitError(
            f"the unlock names {unlock.bucket!r} but {bucket!r} was requested; an unlock "
            f"opens one bucket, not any bucket"
        )

    previous = access_count(bucket, fold_id=fold_id, root=root)
    path = access_log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "bucket": bucket,
        "fold_id": fold_id,
        "reason": unlock.reason,
        "approved_by": unlock.approved_by,
        # Recorded, not enforced. A second access is a fact for `docs/08` to explain, and
        # refusing it here would tempt someone to delete the log to get past the refusal --
        # which would destroy the only evidence. The count is the control.
        "prior_accesses": previous,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def assert_only_unsealed(buckets: list[str]) -> None:
    """Assert a whole evaluation touches no sealed bucket.

    Used by the validation path, which must be provable to have stayed inside `val`. An
    assertion over the list of buckets is stronger than inspecting each call, because it
    fails on a bucket nobody remembered to gate.
    """
    offenders = sorted(set(buckets) & SEALED_BUCKETS)
    if offenders:
        raise SealedSplitError(
            f"this evaluation was declared unsealed but requests {offenders}; "
            f"use an Unlock, or correct the bucket list"
        )


__all__ = [
    "ACCESS_LOG",
    "SEALED_BUCKETS",
    "SealedSplitError",
    "Unlock",
    "access_count",
    "access_log_path",
    "assert_only_unsealed",
    "read_access_log",
    "require_unsealed",
]
