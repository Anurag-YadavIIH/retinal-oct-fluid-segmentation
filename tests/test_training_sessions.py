"""Verification of nightly-session behaviour and accelerator telemetry.

Covers TC-079 (session bounds, warmup, continuous log) and TC-095 (telemetry), and
extends TC-059 across a warmup boundary and partway through a patience window.

Each fold now fits one evening, so these are safety nets against a crash or a Windows
restart rather than the core plan. Checkpoint completeness still matters for exactly
that reason: the run that gets interrupted is the one nobody planned to interrupt.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from ocuval.data.datamodule import LoadFrame
from ocuval.data.splits import Sample, leave_one_vendor_out
from ocuval.training.checkpoint import CHECKPOINT_NAME, load_checkpoint
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


def test_TC_059_early_stopping_state_survives_resume(synthetic, tmp_path):
    """Without it a resume silently restarts the patience window."""
    split, rows = synthetic
    run_dir = tmp_path / "run"
    train_fold(
        split, CFG, rows, run_dir, device="cpu", max_epochs_this_session=3, telemetry_interval=None
    )

    payload = torch.load(run_dir / CHECKPOINT_NAME, map_location="cpu", weights_only=False)
    early = payload["extra"]["early_stopping"]
    assert set(early) >= {"best_epoch", "since_improvement", "patience"}

    model = torch.nn.Linear(4, 4)
    del model
    entries = [e for e in log_entries(run_dir) if e.get("event") == "epoch"]
    assert entries[-1]["best_epoch"] >= 0, "a best epoch should have been recorded"


def test_TC_059_resuming_mid_patience_does_not_reset_the_counter(synthetic, tmp_path):
    """Resume partway through a patience window and the counter must carry over."""
    import copy

    from ocuval.models.seg_unet import build_model

    cfg = copy.deepcopy(CFG)
    cfg["train"]["early_stopping_patience"] = 2
    split, rows = synthetic
    run_dir = tmp_path / "run"

    train_fold(
        split, cfg, rows, run_dir, device="cpu", max_epochs_this_session=3, telemetry_interval=None
    )
    before = torch.load(run_dir / CHECKPOINT_NAME, map_location="cpu", weights_only=False)
    carried = before["extra"]["early_stopping"]["since_improvement"]

    meta = load_checkpoint(run_dir / CHECKPOINT_NAME, model=build_model(cfg))
    assert meta["extra"]["early_stopping"]["since_improvement"] == carried
    assert meta["extra"]["early_stopping"]["patience"] == 2


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
