"""TC-123: two independently configured GPU runs agree exactly while their schedules coincide.

Verifies: TC-123
Traces to: SRS-076, SRS-077, SRS-083, SRS-084, SRS-085; CLAUDE.md rule 4

**Why this is stronger than TC-121.** TC-121 runs two copies of one configuration back to
back in one process and compares them. This compares two runs that were never intended to
be comparable:

| | `cirrus_holdout_stage1b` | `cirrus_holdout_stage2` |
|---|---|---|
| `--epochs` | 20 | 150 |
| sessions | **2**, resumed at epoch 3 | 1 |
| scheduler | cosine `T_max` 15 | cosine `T_max` 145 |
| launched | 2026-10-01 16:58 UTC | 2026-10-01 07:46 UTC |

Different fold lengths, different session structures, hours apart, and one of them **crossed
a resume boundary inside the warmup window**. They agree to every recorded digit for as long
as their learning rates coincide. Nothing was arranged to make that happen; it falls out of
seeding every epoch from `(seed, epoch)` rather than saving and restoring generator state.

**The boundary is asserted, not merely tolerated.** A test that only checked the matching
epochs would pass if the two runs were identical throughout -- which would mean the cosine
horizon was being ignored and SRS-083 was broken. So this also asserts that divergence
begins at exactly the first epoch trained under a differing rate.

**The learning rate logged at epoch N is the rate epoch N+1 will use.** `scheduler.step()`
runs at `loop.py:353` and the log is written at `loop.py:399`, after it. So epoch N trains
under the rate logged at epoch N-1, and the first epoch that can differ is one later than
the first epoch whose logged `lr` differs. Getting this backwards would put the expected
boundary in the wrong place, so it is derived here rather than assumed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_data

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS = REPO_ROOT / "artifacts" / "runs"
EARLIER = "cirrus_holdout_stage1b"
LATER = "cirrus_holdout_stage2"
METRICS = ("train_loss", "val_dice", "per_class_dice")


def load(name: str) -> tuple[dict[int, dict], list[dict]]:
    path = RUNS / name / "epochs.jsonl"
    if not path.is_file():
        pytest.skip(f"{name}/epochs.jsonl absent; the run directories are gitignored")
    epochs, events = {}, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if "train_loss" in entry:
            epochs[entry["epoch"]] = entry
        elif entry.get("event"):
            events.append(entry)
    return epochs, events


@pytest.fixture(scope="module")
def runs():
    a, events_a = load(EARLIER)
    b, events_b = load(LATER)
    shared = sorted(set(a) & set(b))
    if len(shared) < 6:
        pytest.skip("fewer than six shared epochs; nothing to compare")
    return a, b, shared, events_a, events_b


def first_differing_rate(a, b, shared) -> int | None:
    """The first shared epoch whose *logged* rate differs between the runs."""
    for epoch in shared:
        if a[epoch].get("lr") != b[epoch].get("lr"):
            return epoch
    return None


def test_TC_123_the_two_runs_really_were_configured_differently(runs):
    """Vacuity guard. Two runs of the *same* configuration agreeing proves far less.

    If someone re-created either run directory with matching settings, every assertion below
    would pass while the claim this test exists to make -- that agreement survives different
    configurations -- would be untested.
    """
    a, b, shared, events_a, events_b = runs
    starts_a = [e for e in events_a if e.get("event") == "session_start"]
    starts_b = [e for e in events_b if e.get("event") == "session_start"]
    assert len(starts_a) >= 2, f"{EARLIER} no longer shows two sessions; it is the resumed run"
    assert any(e.get("resumed") for e in starts_a), f"{EARLIER} shows no resumed session"
    assert len(starts_b) == 1, f"{LATER} should be a single uninterrupted session"
    assert max(a) < max(b), "the later run should be the longer one"
    assert first_differing_rate(a, b, shared) is not None, (
        "the two runs never diverge in learning rate, so they are not the differently "
        "configured pair this test claims to compare"
    )


def test_TC_123_metrics_agree_exactly_while_the_rates_coincide(runs):
    """The claim. Exact equality, no tolerance: this distinguishes determinism from
    near-determinism, and a tolerance would defeat the purpose."""
    a, b, shared, _, _ = runs
    boundary = first_differing_rate(a, b, shared)
    # Epoch N trains under the rate logged at N-1 (loop.py:353 then :399), so the last epoch
    # that must agree is the one whose own rate came from the last shared logged value.
    last_agreeing = boundary  # inclusive: this epoch trained under the previous, shared rate
    compared = 0
    for epoch in [e for e in shared if e <= last_agreeing]:
        for field in METRICS:
            assert a[epoch][field] == b[epoch][field], (
                f"epoch {epoch} {field} differs between two runs whose learning rate for "
                f"that epoch was identical: {EARLIER}={a[epoch][field]!r} "
                f"{LATER}={b[epoch][field]!r}. CLAUDE.md rule 4 does not hold."
            )
            compared += 1
    assert compared >= 15, f"only {compared} field comparisons; too few to mean anything"


def test_TC_123_the_mean_training_loss_over_the_first_three_epochs_is_identical(runs):
    """The figure `docs/08` quotes for both runs, asserted rather than left in prose.

    1.648121 appears in §5b.3 as Stage 1b's criterion-1 numerator and again in §5c.3 as
    Stage 2's. Two documents quoting one number is exactly where a transcription error
    hides, so the equality is computed here.
    """
    a, b, _, _, _ = runs
    mean_a = sum(a[e]["train_loss"] for e in (0, 1, 2)) / 3
    mean_b = sum(b[e]["train_loss"] for e in (0, 1, 2)) / 3
    assert mean_a == mean_b, f"epochs 0-2 mean loss differs: {mean_a!r} vs {mean_b!r}"
    assert round(mean_a, 6) == 1.648121, (
        f"epochs 0-2 mean loss is {mean_a:.6f}, not the 1.648121 recorded in docs/08 "
        f"§5b.3 and §5c.3"
    )


def test_TC_123_agreement_spans_the_earlier_run_s_resume_boundary(runs):
    """The part that makes this evidence for SRS-076 specifically.

    Stage 1b resumed at epoch 3. Its epochs 3 onward were produced by a process that had
    reconstructed sample order and augmentation from `(seed, epoch)` with nothing restored;
    Stage 2's were produced by a process that never stopped. If the reseeding were wrong,
    these are the epochs that would differ.
    """
    a, b, shared, events_a, _ = runs
    resumed_at = min(
        e["from_epoch"] for e in events_a if e.get("event") == "session_start" and e.get("resumed")
    )
    boundary = first_differing_rate(a, b, shared)
    after_resume = [e for e in shared if resumed_at <= e <= boundary]
    assert after_resume, (
        f"the earlier run resumed at epoch {resumed_at}, which is beyond the last epoch "
        f"whose rates coincide ({boundary}); this test would compare nothing"
    )
    for epoch in after_resume:
        for field in METRICS:
            assert a[epoch][field] == b[epoch][field], (
                f"epoch {epoch} {field} differs, and it is after {EARLIER} resumed at "
                f"epoch {resumed_at}. A resumed run must be the same run (SRS-076)."
            )


def test_TC_123_divergence_begins_where_the_schedules_part_and_not_before(runs):
    """The boundary, asserted in both directions.

    Without this the test would pass if the two runs were identical for all 20 shared
    epochs -- which would mean the cosine horizon had no effect and SRS-083 was broken. The
    expected first divergence is one epoch after the first differing logged rate, because
    the rate logged at epoch N is the rate epoch N+1 uses (loop.py:353, :399).
    """
    a, b, shared, _, _ = runs
    boundary = first_differing_rate(a, b, shared)
    expected = boundary + 1
    if expected not in shared:
        pytest.skip("the runs do not share the epoch where divergence is expected")
    assert any(a[expected][f] != b[expected][f] for f in METRICS), (
        f"epoch {expected} is identical in both runs, but it is the first epoch trained "
        f"under differing learning rates ({a[boundary]['lr']!r} against "
        f"{b[boundary]['lr']!r} logged at epoch {boundary}). Either the cosine horizon is "
        f"being ignored -- SRS-083 -- or `--epochs` is not reaching the scheduler."
    )
