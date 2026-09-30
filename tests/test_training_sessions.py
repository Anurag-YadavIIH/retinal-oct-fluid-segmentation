"""Verification of nightly-session behaviour and accelerator telemetry.

Covers TC-079 (session bounds, warmup, continuous log) and TC-095 (telemetry), and
extends TC-059 across a warmup boundary and partway through a patience window.

Each fold now fits one evening, so these are safety nets against a crash or a Windows
restart rather than the core plan. Checkpoint completeness still matters for exactly
that reason: the run that gets interrupted is the one nobody planned to interrupt.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from ocuval.data.datamodule import LoadFrame
from ocuval.data.splits import Sample, leave_one_vendor_out
from ocuval.training.checkpoint import CHECKPOINT_NAME
from ocuval.training.loop import (
    EPOCH_LOG,
    STOP_FILE,
    append_epoch_log,
    build_optimizer,
    build_scheduler,
    clear_stop,
    stop_requested,
    train_fold,
)
from ocuval.training.telemetry import COLUMNS, GpuTelemetry, sample_once

SEED = 20260916
ROI = [64, 32]

CFG = {
    "run": {"seed": SEED},
    "data": {
        "mode": "2d",
        "roi_size": ROI,
        "cache": "none",
        "num_workers": 0,
        "preprocessing": {"axial_spacing_mm": 0.004, "intensity_percentiles": [1.0, 99.0]},
    },
    "model": {
        "name": "unet",
        "in_channels": 1,
        "out_channels": 4,
        "channels": [4, 8, 16],
        "strides": [2, 2],
        "dropout": 0.2,
    },
    "loss": {"name": "dice_ce", "include_background": False, "to_onehot_y": True, "softmax": True},
    "optim": {
        "name": "adamw",
        "lr": 0.001,
        "weight_decay": 0.0,
        "scheduler": "cosine",
        "warmup_epochs": 2,
    },
    "train": {
        "epochs": 6,
        "batch_size": 2,
        "micro_batch_size": 2,
        "amp": False,
        "grad_clip": 1.0,
        "early_stopping_patience": 25,
        "val_interval": 1,
    },
}


def manifest_rows(n_per_vendor=3, frames=2):
    rows, n = [], 0
    for vendor in ("cirrus", "spectralis", "topcon"):
        for _ in range(n_per_vendor):
            n += 1
            rows.append(
                {
                    "sample_id": f"uid-{n}",
                    "patient_id": f"TRAIN{n:03d}",
                    "vendor": vendor,
                    "shape": [frames, ROI[0], ROI[1]],
                    "dtype": "uint8",
                    "spacing_mm": [0.004, 0.0117, 0.047],
                    "intensity_window": [0.0, 200.0],
                    "source_path": f"/raw/{vendor}/{n}",
                    "path": f"/dicom/{vendor}/uid-{n}.dcm",
                }
            )
    return rows


@pytest.fixture
def synthetic(monkeypatch):
    def fake_call(self, record):
        rng = np.random.default_rng(abs(hash(record["frame_id"])) % (2**32))
        out = dict(record)
        out["image"] = rng.integers(0, 200, tuple(ROI)).astype(np.uint8)
        label = np.zeros(tuple(ROI), dtype=np.uint8)
        label[10:20, 5:15] = 1
        label[30:36, 5:15] = 2
        out["label"] = label
        return out

    monkeypatch.setattr(LoadFrame, "__call__", fake_call)
    rows = manifest_rows()
    samples = [Sample(r["sample_id"], r["patient_id"], r["vendor"]) for r in rows]
    split = leave_one_vendor_out(
        samples, "topcon", val_fraction=0.25, seed=SEED, fold_id="topcon_holdout", ref_fraction=0.25
    )
    return split, rows


def log_entries(run_dir: Path) -> list[dict]:
    path = Path(run_dir) / EPOCH_LOG
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# --- TC-079: session bounds -----------------------------------------------------------


def test_TC_079_max_epochs_this_session_stops_after_exactly_that_many(synthetic, tmp_path):
    split, rows = synthetic
    run_dir = tmp_path / "run"

    first = train_fold(
        split, CFG, rows, run_dir, device="cpu", max_epochs_this_session=2, telemetry_interval=None
    )
    assert [r.epoch for r in first] == [0, 1]
    assert (run_dir / CHECKPOINT_NAME).is_file(), "the session must checkpoint before exiting"

    second = train_fold(
        split, CFG, rows, run_dir, device="cpu", max_epochs_this_session=2, telemetry_interval=None
    )
    assert [r.epoch for r in second] == [2, 3], "the next session must continue, not restart"


def test_TC_079_session_limit_does_not_change_the_fold_total(synthetic, tmp_path):
    """--epochs is the experiment; --max-epochs-this-session is the evening."""
    split, rows = synthetic
    run_dir = tmp_path / "run"
    train_fold(
        split,
        CFG,
        rows,
        run_dir,
        device="cpu",
        max_epochs=5,
        max_epochs_this_session=2,
        telemetry_interval=None,
    )
    entries = [e for e in log_entries(run_dir) if e.get("event") == "session_start"]
    assert entries[0]["fold_total_epochs"] == 5
    assert entries[0]["to_epoch_exclusive"] == 2


def test_TC_079_stop_file_ends_the_session_after_the_current_epoch(synthetic, tmp_path):
    split, rows = synthetic
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    (run_dir / STOP_FILE).write_text("", encoding="utf-8")

    history = train_fold(split, CFG, rows, run_dir, device="cpu", telemetry_interval=None)

    assert len(history) == 1, "STOP must let the current epoch finish, and only that one"
    assert (run_dir / CHECKPOINT_NAME).is_file(), "the epoch must be checkpointed"
    assert not (run_dir / STOP_FILE).exists(), "STOP must be removed so the next session runs"

    end = [e for e in log_entries(run_dir) if e.get("event") == "session_end"][-1]
    assert end["stopped_by"] == "stop_file"
    assert end["fold_complete"] is False


def test_TC_079_a_stale_stop_file_does_not_end_the_next_session(synthetic, tmp_path):
    """The file is cleared at start as well as on use, or one STOP would stop forever."""
    split, rows = synthetic
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    (run_dir / STOP_FILE).write_text("", encoding="utf-8")
    train_fold(split, CFG, rows, run_dir, device="cpu", telemetry_interval=None)

    history = train_fold(
        split, CFG, rows, run_dir, device="cpu", max_epochs_this_session=2, telemetry_interval=None
    )
    assert len(history) == 2, "a removed STOP must not keep stopping later sessions"


def test_TC_079_stop_helpers_are_symmetric(tmp_path):
    assert not stop_requested(tmp_path)
    (tmp_path / STOP_FILE).write_text("", encoding="utf-8")
    assert stop_requested(tmp_path)
    clear_stop(tmp_path)
    assert not stop_requested(tmp_path)
    clear_stop(tmp_path)  # removing an absent file must not raise


# --- TC-079: the continuous log --------------------------------------------------------


def test_TC_079_the_epoch_log_is_appended_across_sessions_never_restarted(synthetic, tmp_path):
    split, rows = synthetic
    run_dir = tmp_path / "run"

    train_fold(
        split, CFG, rows, run_dir, device="cpu", max_epochs_this_session=2, telemetry_interval=None
    )
    after_first = log_entries(run_dir)
    train_fold(
        split, CFG, rows, run_dir, device="cpu", max_epochs_this_session=2, telemetry_interval=None
    )
    after_second = log_entries(run_dir)

    assert len(after_second) > len(after_first), "the log was truncated, not appended"
    assert after_second[: len(after_first)] == after_first, "earlier lines were rewritten"

    epochs = [e["epoch"] for e in after_second if e.get("event") == "epoch"]
    assert epochs == [0, 1, 2, 3], "the fold's curve must be one continuous record"


def test_TC_079_session_boundaries_are_recorded_in_the_log(synthetic, tmp_path):
    split, rows = synthetic
    run_dir = tmp_path / "run"
    for _ in range(2):
        train_fold(
            split,
            CFG,
            rows,
            run_dir,
            device="cpu",
            max_epochs_this_session=2,
            telemetry_interval=None,
        )

    entries = log_entries(run_dir)
    starts = [e for e in entries if e.get("event") == "session_start"]
    ends = [e for e in entries if e.get("event") == "session_end"]
    assert len(starts) == len(ends) == 2
    assert starts[0]["resumed"] is False
    assert starts[1]["resumed"] is True
    assert starts[1]["from_epoch"] == 2


def test_TC_079_the_log_records_the_learning_rate_each_epoch(synthetic, tmp_path):
    """Without it a warmup or decay bug is invisible after the fact."""
    split, rows = synthetic
    run_dir = tmp_path / "run"
    train_fold(
        split, CFG, rows, run_dir, device="cpu", max_epochs_this_session=3, telemetry_interval=None
    )
    rates = [e["lr"] for e in log_entries(run_dir) if e.get("event") == "epoch"]
    assert len(rates) == 3
    assert rates[0] < rates[1], "learning rate should rise during warmup"


def test_TC_079_append_epoch_log_creates_the_file_and_appends(tmp_path):
    append_epoch_log(tmp_path, {"event": "a"})
    append_epoch_log(tmp_path, {"event": "b"})
    assert [e["event"] for e in log_entries(tmp_path)] == ["a", "b"]


# --- TC-079: warmup ---------------------------------------------------------------------


def test_TC_079_warmup_epochs_is_honoured(synthetic):
    """It was configured and ignored until 2026-09-26; a key nothing reads describes a
    run that did not happen."""
    model = torch.nn.Linear(4, 4)
    optimizer = build_optimizer(CFG, model)
    scheduler = build_scheduler(CFG, optimizer, 10)
    base = float(CFG["optim"]["lr"])

    rates = []
    for _ in range(10):
        rates.append(optimizer.param_groups[0]["lr"])
        optimizer.step()
        scheduler.step()

    warmup = int(CFG["optim"]["warmup_epochs"])
    assert rates[0] < base, "warmup must start below the configured rate"
    assert all(rates[i] < rates[i + 1] for i in range(warmup - 1)), "rate must rise"
    assert rates[warmup] == pytest.approx(base), "rate must reach the configured value"
    assert rates[warmup + 1] < rates[warmup], "and decay after"


def test_TC_079_warmup_longer_than_the_run_is_refused():
    import copy

    cfg = copy.deepcopy(CFG)
    cfg["optim"]["warmup_epochs"] = 10
    with pytest.raises(ValueError, match="no decay phase"):
        build_scheduler(cfg, build_optimizer(cfg, torch.nn.Linear(4, 4)), 10)


def test_TC_059_resume_across_a_warmup_boundary_matches_an_uninterrupted_run(synthetic, tmp_path):
    """The boundary is where a scheduler resumed by epoch count instead of by state
    would diverge, and nowhere else."""
    split, rows = synthetic
    warmup = int(CFG["optim"]["warmup_epochs"])

    straight = tmp_path / "straight"
    train_fold(
        split,
        CFG,
        rows,
        straight,
        device="cpu",
        max_epochs_this_session=warmup + 2,
        telemetry_interval=None,
    )
    expected = [e["lr"] for e in log_entries(straight) if e.get("event") == "epoch"]

    split_run = tmp_path / "split"
    train_fold(
        split,
        CFG,
        rows,
        split_run,
        device="cpu",
        max_epochs_this_session=warmup - 1,
        telemetry_interval=None,
    )
    train_fold(
        split,
        CFG,
        rows,
        split_run,
        device="cpu",
        max_epochs_this_session=3,
        telemetry_interval=None,
    )
    actual = [e["lr"] for e in log_entries(split_run) if e.get("event") == "epoch"]

    assert len(actual) == len(expected) == warmup + 2
    for index, (a, b) in enumerate(zip(expected, actual, strict=True)):
        assert a == pytest.approx(b, rel=1e-9), f"learning rate diverged at epoch {index}"


def early_state(run_dir: Path, name: str = CHECKPOINT_NAME) -> dict:
    payload = torch.load(Path(run_dir) / name, map_location="cpu", weights_only=False)
    state = dict(payload["extra"]["early_stopping"])
    state["best_metric"] = payload.get("best_metric")
    state["epoch"] = payload["epoch"]
    return state


def test_TC_059_early_stopping_state_is_present_in_the_checkpoint(synthetic, tmp_path):
    """A structural precondition only. Presence is not correctness -- see below."""
    split, rows = synthetic
    run_dir = tmp_path / "run"
    train_fold(
        split, CFG, rows, run_dir, device="cpu", max_epochs_this_session=3, telemetry_interval=None
    )
    early = early_state(run_dir)
    assert {"best_epoch", "since_improvement", "patience"} <= set(early)


def test_TC_059_the_checkpoint_records_the_best_from_its_own_epoch(synthetic, tmp_path):
    """**The defect this exists to catch.**

    `last.pt` for epoch N must describe the state *after* epoch N is scored, not after
    epoch N-1. Written before the best-check, it lags by one epoch: a resume then
    believes the best metric is the previous epoch's, and can overwrite `best.pt` with a
    worse model while still improving on the stale figure.

    Found on 2026-09-30 during the Stage 1 smoke run, where `last.pt` at epoch 15 read
    `best 0.6726 at epoch 14` while epoch 15 had itself scored 0.6821. The three earlier
    TC-059 early-stopping cases all passed throughout, because each asserted something
    that holds identically whether the state is current or stale -- key presence, a
    round-trip equality, and a learning-rate trajectory. See docs/13, 2026-09-30.
    """
    split, rows = synthetic
    run_dir = tmp_path / "run"
    # ONE epoch, deliberately. Epoch 0 always improves, because the best starts at
    # -inf, so the lag is guaranteed to show rather than depending on whether the
    # session's final epoch happened to be an improving one. An earlier version of this
    # test ran four epochs and passed on the buggy code whenever epoch 3 did not
    # improve -- a test whose detection depends on chance is not a test.
    train_fold(
        split, CFG, rows, run_dir, device="cpu", max_epochs_this_session=1, telemetry_interval=None
    )

    epochs = [e for e in log_entries(run_dir) if e.get("event") == "epoch"]
    scored = [e for e in epochs if e.get("val_dice") is not None]
    assert scored, "no epoch produced a validation score"
    assert len(scored) == 1, "this case is deterministic only for a single epoch"
    best_seen = max(e["val_dice"] for e in scored)
    best_seen_epoch = max(scored, key=lambda e: e["val_dice"])["epoch"]

    # Compared at the log's own precision: EpochResult.as_dict rounds val_dice to six
    # decimals while the checkpoint keeps full precision, so an exact comparison fails
    # on representation rather than on staleness. The defect this guards against is a
    # whole epoch's difference, which shows in the third decimal, not the seventh.
    early = early_state(run_dir)
    assert round(early["best_metric"], 6) == pytest.approx(best_seen), (
        f"last.pt records best_metric={early['best_metric']} but the best validation "
        f"score across the session was {best_seen}. The checkpoint is stale: it was "
        f"written before the best-metric update for its own epoch."
    )
    assert (
        early["best_epoch"] == best_seen_epoch
    ), f"last.pt records best_epoch={early['best_epoch']}, expected {best_seen_epoch}"


def epoch_sequences(
    split, rows, cfg, epochs: range, *, reseed: str = "both", content: bool = False
) -> dict[int, list[str]]:
    """What the training loader serves, epoch by epoch, keyed by epoch number.

    Built through `build_loaders` and reseeded through `seed_epoch`, the two calls
    `train_fold` makes (loop.py:234 and loop.py:305), so this exercises the shipped
    mechanism rather than a re-implementation of it. One call models one session: an
    uninterrupted run is `range(0, 5)`, and a resume is a second call over `range(3, 5)`
    with a loader built fresh, as a new process would build it.

    `content=True` appends a digest of each frame's pixels, so the comparison covers the
    augmentation applied to a sample and not only which sample it was.

    `reseed` selects how much of the mechanism is present, so each half can be shown to
    be load-bearing (docs/07 §3 rule 8): "both" is the shipped behaviour, "sampler"
    reseeds the loader generator but leaves the MONAI chain seeded once at construction,
    and "none" removes both.
    """
    from ocuval.data.datamodule import build_loaders, epoch_seed, seed_epoch

    seed = cfg["run"]["seed"]
    loader, _, _ = build_loaders(split, cfg, rows)
    sequences: dict[int, list[str]] = {}
    for epoch in epochs:
        if reseed == "both":
            seed_epoch(loader, seed, epoch)
        elif reseed == "sampler":
            loader.generator.manual_seed(epoch_seed(seed, epoch, "sampler"))
        served: list[str] = []
        for batch in loader:
            for position, name in enumerate(batch["frame_id"]):
                if not content:
                    served.append(name)
                    continue
                pixels = batch["image"][position].detach().numpy()
                served.append(f"{name}:{hashlib.sha256(pixels.tobytes()).hexdigest()[:16]}")
        sequences[epoch] = served
    return sequences


def test_TC_059_a_resumed_session_serves_the_same_sample_order(synthetic, tmp_path):
    """**The mechanism, tested directly.**

    The outcome test below checks which epoch scores best, which depends on the sample
    order only sometimes -- it passed twice in three runs with the defect present. This
    asserts the order itself, so it cannot pass by luck.

    The defect: `build_loaders` seeded the DataLoader's generator from `run.seed` once,
    at construction, and `set_rng_state` restores torch's *global* generator, not that
    dedicated object. A resumed session therefore replayed the shuffle sequence from the
    beginning -- its first epoch got epoch 0's permutation regardless of which epoch it
    was actually resuming at, so a resumed run trained on a different batch order and was
    literally a different run. That contradicts SRS-076.
    """
    split, rows = synthetic
    total, resume_at = 5, 3

    uninterrupted = epoch_sequences(split, rows, CFG, range(total))
    before_stop = epoch_sequences(split, rows, CFG, range(resume_at))
    after_resume = epoch_sequences(split, rows, CFG, range(resume_at, total))

    assert uninterrupted[0], "the loader served nothing; this test would be vacuous"
    assert len({tuple(s) for s in uninterrupted.values()}) > 1, (
        "every epoch served the same order, so shuffling is not happening and this "
        "test cannot detect a shuffle defect"
    )

    for epoch, sequence in (before_stop | after_resume).items():
        assert sequence == uninterrupted[epoch], (
            f"epoch {epoch} served a different sample order in a session that did not "
            f"start at epoch 0.\n"
            f"  uninterrupted starts: {uninterrupted[epoch][:6]}\n"
            f"  resumed       starts: {sequence[:6]}\n"
            f"A resumed run must be the same run. The order must be a pure function of "
            f"(seed, epoch) so that resuming reproduces it with nothing to restore."
        )


def test_TC_059_a_resumed_session_serves_the_same_augmented_frames(synthetic):
    """Order is not enough: the *pixels* must match too.

    Every MONAI `Randomizable` keeps its own `np.random.RandomState` (monai
    transform.py:186), independent of the global NumPy state by design, so
    `np.random.get_state()` cannot see it and the checkpoint cannot save it.
    `transforms.py:253` seeds the chain once at construction, which made the augmentation
    a function of how many epochs the *process* had run -- the ordering defect again, in
    a generator no snapshot reaches. A resumed session replayed epoch 0's augmentation.

    This was invisible to the order test, and it is what kept the outcome test below
    failing 13 times in 20 after the sampler was fixed.
    """
    split, rows = synthetic
    total, resume_at = 5, 3

    uninterrupted = epoch_sequences(split, rows, CFG, range(total), content=True)
    after_resume = epoch_sequences(split, rows, CFG, range(resume_at, total), content=True)

    assert len({tuple(s) for s in uninterrupted.values()}) > 1, (
        "every epoch served identical pixels, so augmentation is not happening and this "
        "test cannot detect an augmentation defect"
    )
    for epoch, sequence in after_resume.items():
        assert sequence == uninterrupted[epoch], (
            f"epoch {epoch} served differently augmented frames after a resume.\n"
            f"  uninterrupted starts: {uninterrupted[epoch][:3]}\n"
            f"  resumed       starts: {sequence[:3]}\n"
            f"Augmentation must be a pure function of (seed, epoch) for the same reason "
            f"the sample order must be: a resumed run is the same run or it is not one."
        )


@pytest.mark.parametrize(
    ("reseed", "what"),
    [("none", "neither generator"), ("sampler", "the sampler only")],
)
def test_TC_059_without_the_per_epoch_reseed_a_resume_diverges(synthetic, reseed, what):
    """Both halves of the mechanism must be shown to be load-bearing.

    docs/07 §3 rule 8: a test for a mechanism must be able to fail. `reseed="sampler"` is
    the case that matters most -- it is the state the code was in after the ordering fix,
    when the order test passed and the run was still not reproducible.
    """
    split, rows = synthetic
    total, resume_at = 5, 3

    uninterrupted = epoch_sequences(split, rows, CFG, range(total), reseed=reseed, content=True)
    after_resume = epoch_sequences(
        split, rows, CFG, range(resume_at, total), reseed=reseed, content=True
    )

    assert any(after_resume[epoch] != uninterrupted[epoch] for epoch in after_resume), (
        f"reseeding {what} still reproduced every epoch, so the tests above prove "
        f"nothing about the part that was removed"
    )


def test_TC_059_resuming_after_an_improving_epoch_preserves_the_best(synthetic, tmp_path):
    """Resume immediately after an epoch that improved, and compare to an uninterrupted
    run: `best.pt`, `best_metric`, `best_epoch` and `since_improvement` must all match.

    This is the case the stale checkpoint corrupts. The resumed run inherits an
    understated best, so an epoch that is worse than the true best but better than the
    stale one overwrites `best.pt` -- silently degrading model selection.
    """
    split, rows = synthetic
    total = 5

    straight = tmp_path / "straight"
    train_fold(split, CFG, rows, straight, device="cpu", max_epochs=total, telemetry_interval=None)

    interrupted = tmp_path / "interrupted"
    train_fold(
        split,
        CFG,
        rows,
        interrupted,
        device="cpu",
        max_epochs=total,
        max_epochs_this_session=3,
        telemetry_interval=None,
    )
    train_fold(
        split, CFG, rows, interrupted, device="cpu", max_epochs=total, telemetry_interval=None
    )

    expected, actual = early_state(straight), early_state(interrupted)
    for field in ("best_metric", "best_epoch", "since_improvement"):
        assert actual[field] == pytest.approx(expected[field]), (
            f"{field} differs after a resume: uninterrupted {expected[field]!r}, "
            f"resumed {actual[field]!r}. A resumed run must be the same run."
        )

    straight_best = torch.load(straight / "best.pt", map_location="cpu", weights_only=False)
    resumed_best = torch.load(interrupted / "best.pt", map_location="cpu", weights_only=False)
    assert resumed_best["epoch"] == straight_best["epoch"], (
        f"best.pt came from epoch {resumed_best['epoch']} after a resume but "
        f"{straight_best['epoch']} without one -- model selection diverged."
    )
    assert resumed_best["best_metric"] == pytest.approx(straight_best["best_metric"])


def test_TC_059_the_epoch_log_reports_the_best_from_its_own_epoch(synthetic, tmp_path):
    """The log has the same lag as the checkpoint, and for the same reason.

    `append_epoch_log` also runs before the best-check, so a reader of `epochs.jsonl`
    sees the best as of the previous epoch. Observed directly in the Stage 1 log.
    """
    split, rows = synthetic
    run_dir = tmp_path / "run"
    train_fold(
        split, CFG, rows, run_dir, device="cpu", max_epochs_this_session=4, telemetry_interval=None
    )

    scored = [
        e
        for e in log_entries(run_dir)
        if e.get("event") == "epoch" and e.get("val_dice") is not None
    ]
    running_best = float("-inf")
    for entry in scored:
        running_best = max(running_best, entry["val_dice"])
        # Rounded for the same reason as the checkpoint comparison above: val_dice is
        # logged to six decimals, best_metric is not.
        assert round(entry["best_metric"], 6) == pytest.approx(running_best), (
            f"epoch {entry['epoch']} logs best_metric={entry['best_metric']} but the best "
            f"through that epoch inclusive is {running_best}. The log is written before "
            f"the best-metric update for its own epoch."
        )


def test_TC_059_resuming_mid_patience_carries_the_counter(synthetic, tmp_path):
    """Rewritten twice. The first version read `since_improvement` out of the checkpoint
    and asserted that loading the same checkpoint returned it -- `x == x`, which verifies
    `torch.load`, not the value, and it never resumed despite its name.

    The second version asserted `since_improvement >= before` at the first resumed epoch.
    That failed 3 times in 20, and correctly: when the first resumed epoch *improves*, the
    counter resets to 0 and the run is behaving exactly as specified. The assertion was a
    consequence of the trajectory, not the mechanism -- the same flaw, twice in one file.

    The mechanism is that a resumed run is the same run, so the invariant is that its
    epoch log equals an uninterrupted run's, whatever the trajectory does. Every
    interruption point is tried rather than one chosen point, because which boundary lands
    mid-patience depends on the trajectory and so cannot be fixed in advance.
    """
    import copy

    cfg = copy.deepcopy(CFG)
    cfg["train"]["early_stopping_patience"] = 2
    split, rows = synthetic
    total = 6
    compared = ("epoch", "val_dice", "best_metric", "best_epoch", "since_improvement")

    straight = tmp_path / "straight"
    train_fold(split, cfg, rows, straight, device="cpu", max_epochs=total, telemetry_interval=None)
    expected = [e for e in log_entries(straight) if e.get("event") == "epoch"]

    assert any(e["since_improvement"] >= 1 for e in expected), (
        "no epoch in the uninterrupted run was inside a patience window, so this test "
        "cannot be about carrying the counter across a resume"
    )

    for stop_after in range(1, len(expected)):
        run_dir = tmp_path / f"interrupted_{stop_after}"
        train_fold(
            split,
            cfg,
            rows,
            run_dir,
            device="cpu",
            max_epochs=total,
            max_epochs_this_session=stop_after,
            telemetry_interval=None,
        )
        carried = early_state(run_dir)["since_improvement"]
        train_fold(
            split, cfg, rows, run_dir, device="cpu", max_epochs=total, telemetry_interval=None
        )
        actual = [e for e in log_entries(run_dir) if e.get("event") == "epoch"]

        assert [{k: e[k] for k in compared} for e in actual] == [
            {k: e[k] for k in compared} for e in expected
        ], (
            f"interrupting after epoch {stop_after - 1} changed the run. The checkpoint "
            f"carried since_improvement={carried}; a resumed run must reproduce the "
            f"uninterrupted trajectory epoch for epoch, including when the counter resets."
        )
        assert early_state(run_dir)["patience"] == 2


# --- TC-095: telemetry --------------------------------------------------------------------


def test_TC_095_telemetry_file_appears_with_a_header(tmp_path):
    telemetry = GpuTelemetry(tmp_path, interval=0.2).start()
    telemetry.stop()
    path = tmp_path / "gpu_telemetry.csv"
    assert path.is_file()
    header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header == list(COLUMNS)
    for field in ("temperature.gpu", "clocks.current.sm", "utilization.gpu", "memory.used"):
        assert field in header


def test_TC_095_telemetry_appends_over_time(tmp_path):
    import time

    telemetry = GpuTelemetry(tmp_path, interval=0.2).start()
    time.sleep(0.75)
    telemetry.stop()
    rows = (tmp_path / "gpu_telemetry.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) >= 3, "expected a header and at least two samples"
    assert telemetry.samples >= 2


def test_TC_095_a_failing_nvidia_smi_is_recorded_and_not_fatal(tmp_path, monkeypatch):
    """Telemetry is evidence about a run, not part of it."""
    import ocuval.training.telemetry as telemetry_module

    monkeypatch.setattr(telemetry_module, "nvidia_smi_available", lambda: False)
    telemetry = telemetry_module.GpuTelemetry(tmp_path, interval=0.2).start()
    telemetry.stop()

    rows = (tmp_path / "gpu_telemetry.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) >= 2
    assert "nvidia-smi not on PATH" in rows[1]
    assert telemetry.errors >= 1


def test_TC_095_telemetry_stops_when_the_run_does(tmp_path):
    import time

    telemetry = GpuTelemetry(tmp_path, interval=0.2).start()
    time.sleep(0.5)
    telemetry.stop()
    after_stop = telemetry.samples
    time.sleep(0.6)
    assert telemetry.samples == after_stop, "the sampler kept running after the run ended"


def test_TC_095_a_run_writes_telemetry_into_its_run_directory(synthetic, tmp_path):
    split, rows = synthetic
    run_dir = tmp_path / "run"
    train_fold(
        split, CFG, rows, run_dir, device="cpu", max_epochs_this_session=1, telemetry_interval=0.2
    )
    assert (run_dir / "gpu_telemetry.csv").is_file()
    end = [e for e in log_entries(run_dir) if e.get("event") == "session_end"][-1]
    assert end["telemetry_samples"] is not None and end["telemetry_samples"] >= 1


def test_TC_095_sample_once_returns_either_values_or_a_reason():
    values, error = sample_once()
    assert bool(values) != bool(error), "exactly one of a reading or an explanation"
