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
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# One identifier per process. The seal is checked more than once in a run -- before the split
# is read and again at aggregation -- and `access_count` counts distinct run identifiers so
# that those checks are one access rather than two (`docs/08` D6).
RUN_ID = uuid.uuid4().hex

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
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def gate_calls(bucket: str, *, fold_id: str | None = None, root: Path | None = None) -> int:
    """Raw entries in the log for this bucket -- one per gate call, not per run."""
    return sum(
        1
        for entry in read_access_log(root)
        if entry.get("bucket") == bucket and (fold_id is None or entry.get("fold_id") == fold_id)
    )


def access_count(bucket: str, *, fold_id: str | None = None, root: Path | None = None) -> int:
    """How many **evaluation runs** have read this bucket, from the durable log.

    This is the number `docs/07` §17.5 requires. It is derived from the log rather than
    tracked in memory, so it survives the process and cannot be reset by restarting --
    which is the only way a count of "exactly once" means anything.

    **Corrected 2026-10-01 (`docs/08` D6).** It previously returned the number of *gate
    calls*, and the seal is checked twice in a completed run -- once in
    `scripts/05_evaluate.py` before the split is read, once in `eval/pipeline.py` at
    aggregation. So one finished run logged two entries and the count read 3 for two runs of
    `test` (one killed early, one complete) and 2 for one run of `in_domain_ref`. No reported
    figure depended on it, but the number did not answer the question §17.5 asks.

    **Runs are counted by `run_id`, not by dividing by two.** Dividing would assume every run
    reaches both gates, which the killed run did not -- it logged one entry and would have
    counted as half. Each process stamps its entries with one identifier and runs are the
    number of distinct identifiers.

    **Entries written before `run_id` existed are counted individually**, which deliberately
    over-counts the two historical `test` runs as three. The alternative -- inferring runs
    from timestamps -- would be a guess presented as a count, and the raw log is retained
    precisely so that a reader can see the three entries and the reasons that distinguish
    them. `docs/08` D6 states the true figure.
    """
    runs: set[str] = set()
    legacy = 0
    for entry in read_access_log(root):
        if entry.get("bucket") != bucket:
            continue
        if fold_id is not None and entry.get("fold_id") != fold_id:
            continue
        identifier = entry.get("run_id")
        if identifier is None:
            legacy += 1
        else:
            runs.add(identifier)
    return len(runs) + legacy


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
        # One identifier per process, so the two gate calls a completed run makes are one
        # run in the count (`docs/08` D6). Stamped here rather than passed in, because a
        # caller that had to supply it could supply a fresh one per call and silently
        # restore the defect.
        "run_id": RUN_ID,
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
    "gate_calls",
    "access_log_path",
    "assert_only_unsealed",
    "read_access_log",
    "require_unsealed",
]
