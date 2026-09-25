"""Verification of ocuval.models.seg_unet.

Covers TC-053 (2D/2.5D only), TC-054 (zero dropout rejected) and TC-058 (checkpoint
provenance and integrity).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import torch
import yaml

from ocuval.models.seg_unet import (
    HASH_NAME,
    build_model,
    load_verified,
    record_checkpoint_hash,
    verify_checkpoint,
)
from ocuval.training.checkpoint import save_checkpoint

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return yaml.safe_load((REPO_ROOT / "configs" / "train_seg.yaml").read_text(encoding="utf-8"))


# --- TC-053 -------------------------------------------------------------------------


def test_TC_053_mode_is_honoured_from_config(config):
    assert isinstance(build_model(config), torch.nn.Module)


def test_TC_053_two_and_a_half_d_widens_the_input_channels(config):
    cfg = copy.deepcopy(config)
    cfg["data"]["mode"] = "2.5d"
    cfg["data"]["slice_context"] = 2
    model = build_model(cfg)
    first = next(m for m in model.modules() if isinstance(m, torch.nn.Conv2d))
    assert first.in_channels == 5, "2.5D feeds 2*context+1 adjacent B-scans as channels"


@pytest.mark.parametrize("mode", ["3d", "3D", "volumetric"])
def test_TC_053_no_3d_architecture_is_constructible(config, mode):
    cfg = copy.deepcopy(config)
    cfg["data"]["mode"] = mode
    with pytest.raises(ValueError, match="only|2d"):
        build_model(cfg)


def test_TC_053_network_is_always_two_dimensional(config):
    """Even in 2.5D the convolutions are 2D; the context is channels, not depth."""
    model = build_model(config)
    assert not any(isinstance(m, torch.nn.Conv3d) for m in model.modules())


# --- TC-054 -------------------------------------------------------------------------


@pytest.mark.parametrize("dropout", [0.0, 0, -0.1])
def test_TC_054_zero_dropout_is_refused_naming_mc_dropout(config, dropout):
    cfg = copy.deepcopy(config)
    cfg["model"]["dropout"] = dropout
    with pytest.raises(ValueError, match="MC-dropout"):
        build_model(cfg)


def test_TC_054_the_shipped_config_has_non_zero_dropout(config):
    """The requirement is worthless if the config it guards violates it."""
    assert float(config["model"]["dropout"]) > 0.0


def test_TC_054_dropout_actually_perturbs_the_forward_pass(config):
    """A refusal on the config value proves nothing if dropout is inert in the network.

    This is the property SRS-028 exists for: with dropout active, repeated passes must
    differ, or MC-dropout reports zero variance and maximum confidence everywhere.
    """
    model = build_model(config)
    model.train()
    x = torch.randn(1, 1, 64, 64)
    torch.manual_seed(0)
    a = model(x)
    torch.manual_seed(1)
    b = model(x)
    assert not torch.allclose(a, b), "dropout is configured but not perturbing the output"


# --- TC-058 -------------------------------------------------------------------------


@pytest.fixture
def artifact_checkpoint(tmp_path, config):
    root = tmp_path / "artifacts"
    run = root / "runs" / "f1"
    path = save_checkpoint(run / "last.pt", epoch=0, model=build_model(config))
    record_checkpoint_hash(path)
    return root, path


def test_TC_058_a_recorded_checkpoint_is_admitted(artifact_checkpoint):
    root, path = artifact_checkpoint
    assert verify_checkpoint(path, artifacts_root=root)


def test_TC_058_checkpoint_outside_artifacts_is_refused(tmp_path, config):
    outside = tmp_path / "elsewhere" / "last.pt"
    save_checkpoint(outside, epoch=0, model=build_model(config))
    record_checkpoint_hash(outside)
    with pytest.raises(ValueError, match="loaded only from"):
        verify_checkpoint(outside, artifacts_root=tmp_path / "artifacts")


def test_TC_058_altered_checkpoint_fails_the_hash_check(artifact_checkpoint):
    root, path = artifact_checkpoint
    with path.open("ab") as handle:
        handle.write(b"\x00")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_checkpoint(path, artifacts_root=root)


def test_TC_058_checkpoint_with_no_recorded_hash_is_refused(artifact_checkpoint, config):
    root, path = artifact_checkpoint
    other = save_checkpoint(path.parent / "unrecorded.pt", epoch=1, model=build_model(config))
    with pytest.raises(ValueError, match="no recorded hash"):
        verify_checkpoint(other, artifacts_root=root)


def test_TC_058_missing_registry_is_refused_rather_than_treated_as_permission(tmp_path, config):
    root = tmp_path / "artifacts"
    path = save_checkpoint(root / "runs" / "f1" / "last.pt", epoch=0, model=build_model(config))
    assert not (path.parent / HASH_NAME).exists()
    with pytest.raises(ValueError, match="no hash registry"):
        verify_checkpoint(path, artifacts_root=root)


def test_TC_058_load_verified_refuses_before_it_opens_the_file(tmp_path, config):
    """Verification must precede torch.load, which executes pickled content."""
    outside = tmp_path / "elsewhere" / "last.pt"
    save_checkpoint(outside, epoch=0, model=build_model(config))
    with pytest.raises(ValueError, match="loaded only from"):
        load_verified(outside, build_model(config), artifacts_root=tmp_path / "artifacts")


def test_TC_058_registry_records_one_entry_per_checkpoint(artifact_checkpoint, config):
    root, path = artifact_checkpoint
    second = save_checkpoint(path.parent / "best.pt", epoch=3, model=build_model(config))
    record_checkpoint_hash(second)
    known = json.loads((path.parent / HASH_NAME).read_text(encoding="utf-8"))
    assert set(known) == {"last.pt", "best.pt"}
    assert all(len(v) == 64 for v in known.values())


def test_TC_058_a_verified_checkpoint_round_trips_into_a_model(artifact_checkpoint, config):
    root, path = artifact_checkpoint
    model = build_model(config)
    meta = load_verified(path, model, artifacts_root=root)
    assert meta["epoch"] == 0
