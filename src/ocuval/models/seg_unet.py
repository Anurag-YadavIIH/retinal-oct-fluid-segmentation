"""Segmentation network construction and checkpoint admission.

Traces to: SRS-027, SRS-028, SRS-061
Verifies: TC-053, TC-054, TC-058

2D / 2.5D only. Full 3D is out of scope: the dataset is small and the cross-vendor
question does not require it.

**Dropout must be non-zero and the configuration is rejected if it is not** (SRS-028).
This looks like a strange thing to enforce until you see what depends on it: MC-dropout
at inference is the project's only uncertainty estimate, and it is what produces the
confidence that routes a scan to human review (RC-009). With `dropout: 0` the model
still trains, still scores, and silently reports zero variance across every MC pass --
maximum confidence everywhere, including where it is wrong. That is worse than no
uncertainty estimate, so it is refused at construction rather than discovered later.

**Checkpoints are admitted, not merely loaded** (SRS-061). A checkpoint is executable
content: `torch.load` reconstructs pickled objects, so loading an untrusted one is
arbitrary code execution. Every checkpoint this project writes gets a SHA-256 recorded
beside it, the hash is verified before the file is opened, and a file with no recorded
hash is refused rather than trusted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import torch

HASH_NAME = "checkpoints.sha256"
SUPPORTED_MODES = ("2d", "2.5d")


def build_model(cfg: dict) -> torch.nn.Module:
    """Build the MONAI network described by the model section of the config.

    Channels and strides come from the configuration rather than being hard-coded, so
    the architecture is part of the recorded run configuration (SRS-031) and a result
    can be tied to the network that produced it.
    """
    from monai.networks.nets import SegResNet, UNet

    model_cfg = cfg.get("model", cfg)
    data_cfg = cfg.get("data", {})

    mode = str(data_cfg.get("mode", "2d")).lower()
    if mode not in SUPPORTED_MODES:
        raise ValueError(
            f"data.mode is {mode!r}; only {SUPPORTED_MODES} are provided (SRS-027). "
            f"Full 3D is out of scope: the dataset is small and the cross-vendor "
            f"question does not need it."
        )

    dropout = float(model_cfg.get("dropout", 0.0))
    if dropout <= 0.0:
        raise ValueError(
            f"model.dropout is {dropout}; it must be non-zero (SRS-028). MC-dropout is "
            f"this project's only uncertainty estimate and with zero dropout every pass "
            f"is identical, so the model reports maximum confidence everywhere -- "
            f"including where it is wrong. That is worse than reporting none."
        )

    # 2.5D feeds adjacent B-scans as channels; the network is still 2D.
    in_channels = int(model_cfg.get("in_channels", 1))
    if mode == "2.5d":
        in_channels = 2 * int(data_cfg.get("slice_context", 1)) + 1

    name = str(model_cfg.get("name", "unet")).lower()
    if name == "unet":
        return UNet(
            spatial_dims=2,
            in_channels=in_channels,
            out_channels=int(model_cfg["out_channels"]),
            channels=tuple(int(c) for c in model_cfg["channels"]),
            strides=tuple(int(s) for s in model_cfg["strides"]),
            dropout=dropout,
        )
    if name == "segresnet":
        return SegResNet(
            spatial_dims=2,
            in_channels=in_channels,
            out_channels=int(model_cfg["out_channels"]),
            dropout_prob=dropout,
        )
    raise ValueError(f"unknown model.name {name!r}; expected 'unet' or 'segresnet'")


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def record_checkpoint_hash(path: Path, registry: Path | None = None) -> str:
    """Record a checkpoint's SHA-256 (SRS-061). Called whenever one is written."""
    path = Path(path)
    registry = Path(registry) if registry else path.parent / HASH_NAME
    digest = _digest(path)
    known: dict[str, str] = {}
    if registry.is_file():
        known = json.loads(registry.read_text(encoding="utf-8"))
    known[path.name] = digest
    registry.write_text(json.dumps(known, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digest


def verify_checkpoint(
    path: Path, registry: Path | None = None, *, artifacts_root: Path | None = None
) -> str:
    """Admit a checkpoint, or refuse it (SRS-061).

    Three refusals, each for a different failure:

    - **Outside `artifacts/`**: a checkpoint from anywhere else was not produced by this
      project, and `torch.load` on it is arbitrary code execution.
    - **No recorded hash**: an unrecorded checkpoint is one nothing vouches for. Treating
      absence as permission would make the whole check optional in practice.
    - **Hash mismatch**: the file changed after it was written.
    """
    path = Path(path).resolve()
    root = Path(artifacts_root or "artifacts").resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(
            f"refusing to load {path}: checkpoints are loaded only from {root} "
            f"(SRS-061). A checkpoint is executable content, not data."
        ) from error

    registry = Path(registry) if registry else path.parent / HASH_NAME
    if not registry.is_file():
        raise ValueError(
            f"refusing to load {path}: no hash registry at {registry}. An unrecorded "
            f"checkpoint is one nothing vouches for (SRS-061)."
        )
    known = json.loads(registry.read_text(encoding="utf-8"))
    if path.name not in known:
        raise ValueError(
            f"refusing to load {path}: no recorded hash for it in {registry} (SRS-061)."
        )
    actual = _digest(path)
    if actual != known[path.name]:
        raise ValueError(
            f"refusing to load {path}: SHA-256 is {actual}, recorded {known[path.name]}. "
            f"The file changed after it was written (SRS-061)."
        )
    return actual


def load_verified(path: Path, model: torch.nn.Module, **kwargs: Any) -> dict[str, Any]:
    """Verify then load. The only way a checkpoint should reach a model."""
    from ocuval.training.checkpoint import load_checkpoint

    verify_checkpoint(
        path, kwargs.pop("registry", None), artifacts_root=kwargs.pop("artifacts_root", None)
    )
    return load_checkpoint(Path(path), model=model, **kwargs)
