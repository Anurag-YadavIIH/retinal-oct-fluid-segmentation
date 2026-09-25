"""Verification of ocuval.training.loop.

Covers TC-050 (dataloaders only from a resolved split) and TC-057 (run provenance).

No real data and no real training: the loop is exercised on synthetic frames for two
epochs on CPU, which verifies that it runs, checkpoints, resumes and records, not that
it learns anything. Training happens on Kaggle (CLAUDE.md §6).
"""

from __future__ import annotations

import json

import numpy as np
import pytest
import torch

from ocuval.data.datamodule import LoadFrame
from ocuval.data.splits import Sample, leave_one_vendor_out, save
from ocuval.training.checkpoint import BEST_NAME, CHECKPOINT_NAME
from ocuval.training.loop import build_loss, build_optimizer, build_scheduler, train_fold

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
    "optim": {"name": "adamw", "lr": 0.001, "weight_decay": 0.0, "scheduler": "cosine"},
    "train": {
        "epochs": 2,
        "batch_size": 2,
        "amp": False,
        "grad_clip": 1.0,
        "early_stopping_patience": 25,
        "val_interval": 1,
    },
}


def manifest_rows(n_per_vendor=2, frames=2):
    rows = []
    n = 0
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
    """Frames that never touch the filesystem, with fluid present so Dice is defined."""

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
    rows = manifest_rows(n_per_vendor=3)
    samples = [Sample(r["sample_id"], r["patient_id"], r["vendor"]) for r in rows]
    split = leave_one_vendor_out(
        samples,
        "topcon",
        val_fraction=0.25,
        seed=SEED,
        fold_id="topcon_holdout",
        ref_fraction=0.25,
    )
    return split, rows


# --- construction --------------------------------------------------------------------


def test_build_loss_optimizer_and_scheduler_come_from_config():
    model = torch.nn.Linear(4, 4)
    assert build_loss(CFG) is not None
    optimizer = build_optimizer(CFG, model)
    assert isinstance(optimizer, torch.optim.AdamW)
    assert optimizer.param_groups[0]["lr"] == pytest.approx(0.001)
    assert build_scheduler(CFG, optimizer, 10) is not None


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [("loss", "name", "focal"), ("optim", "name", "sgd"), ("optim", "scheduler", "step")],
)
def test_unsupported_component_is_refused_rather_than_substituted(section, key, value):
    """Silently substituting a component would change the experiment without recording it."""
    import copy

    cfg = copy.deepcopy(CFG)
    cfg[section][key] = value
    model = torch.nn.Linear(4, 4)
    with pytest.raises(ValueError, match="unsupported"):
        if section == "loss":
            build_loss(cfg)
        elif key == "name":
            build_optimizer(cfg, model)
        else:
            build_scheduler(cfg, build_optimizer(cfg, model), 10)


# --- TC-050 ---------------------------------------------------------------------------


def test_TC_050_training_requires_a_resolved_split(synthetic, tmp_path):
    """SRS-024: a Split object, not an ad-hoc list of samples."""
    _split, rows = synthetic
    with pytest.raises((AttributeError, TypeError)):
        train_fold(["uid-1", "uid-2"], CFG, rows, tmp_path / "run", device="cpu")


def test_TC_050_a_split_loaded_from_disk_drives_the_run(synthetic, tmp_path):
    split, rows = synthetic
    path = tmp_path / "topcon_holdout.json"
    save(split, path)
    assert json.loads(path.read_text(encoding="utf-8"))["test"]  # subjects, from disk
    history = train_fold(split, CFG, rows, tmp_path / "run", device="cpu", max_epochs=1)
    assert len(history) == 1


# --- TC-057 ---------------------------------------------------------------------------


def test_TC_057_determinism_and_history_are_written(synthetic, tmp_path):
    split, rows = synthetic
    run_dir = tmp_path / "run"
    train_fold(split, CFG, rows, run_dir, device="cpu", max_epochs=2)

    determinism = json.loads((run_dir / "determinism.json").read_text(encoding="utf-8"))
    assert determinism["requested"] is True
    assert "fallbacks" in determinism  # SRS-077: recorded, even when empty

    history = json.loads((run_dir / "history.json").read_text(encoding="utf-8"))
    assert len(history) == 2
    assert all("train_loss" in row for row in history)


# --- checkpointing through the loop ----------------------------------------------------


def test_loop_checkpoints_every_epoch_and_records_a_hash(synthetic, tmp_path):
    split, rows = synthetic
    run_dir = tmp_path / "run"
    train_fold(split, CFG, rows, run_dir, device="cpu", max_epochs=2)

    assert (run_dir / CHECKPOINT_NAME).is_file()
    assert (run_dir / BEST_NAME).is_file()
    registry = json.loads((run_dir / "checkpoints.sha256").read_text(encoding="utf-8"))
    assert set(registry) >= {CHECKPOINT_NAME}
    assert all(len(v) == 64 for v in registry.values())


def test_loop_resumes_from_the_run_directory_without_a_flag(synthetic, tmp_path):
    """Resume is detected, not requested: on a preemptible machine it is the normal path."""
    split, rows = synthetic
    run_dir = tmp_path / "run"

    first = train_fold(split, CFG, rows, run_dir, device="cpu", max_epochs=1)
    assert [r.epoch for r in first] == [0]

    second = train_fold(split, CFG, rows, run_dir, device="cpu", max_epochs=3)
    assert [r.epoch for r in second] == [1, 2], "resumed run restarted from zero"

    history = json.loads((run_dir / "history.json").read_text(encoding="utf-8"))
    assert [row["epoch"] for row in history] == [1, 2]


def test_loop_reports_per_class_dice_not_only_a_mean(synthetic, tmp_path):
    """CLAUDE.md §5: per class, because a mean hides a class never predicted."""
    split, rows = synthetic
    history = train_fold(split, CFG, rows, tmp_path / "run", device="cpu", max_epochs=1)
    assert history[0].per_class_dice
    assert len(history[0].per_class_dice) == CFG["model"]["out_channels"] - 1
