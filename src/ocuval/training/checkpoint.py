"""Checkpointing and resume, including the random state (SRS-075, SRS-076, SRS-077).

Traces to: SRS-075, SRS-076, SRS-077
Verifies: TC-059

**Why the RNG state is part of the checkpoint and not an afterthought.** Rule 4 says a
result must be reproducible from the committed configuration alone. A run that resumes
from saved weights but a fresh random seed produces a different batch order, different
augmentation and a different dropout mask from the run it claims to continue. The
weights would be right and the trajectory would not, so two runs of "the same"
configuration would diverge for a reason nothing recorded. Saving the generators makes a
resumed run a continuation rather than a new run that happens to start from old weights.

**What equivalence can and cannot be claimed.** On CPU a resumed run is bit-identical to
an uninterrupted one, and TC-059 asserts exactly that. On GPU it is not, and this module
does not pretend otherwise: several CUDA kernels reachable from this network -- some
interpolation and upsampling backward passes among them -- have no deterministic
implementation, so results agree to a tolerance rather than exactly. `SRS-076` states the
tolerance; `describe_determinism` records which operations forced a fallback, because an
undocumented fallback is an undocumented source of run-to-run variation.

**Atomicity.** A checkpoint is written to a temporary file and renamed. `os.replace` is
atomic on both POSIX and Windows, so a process killed mid-write leaves the previous
checkpoint intact rather than a truncated file that fails to load at the moment it is
most needed.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch

CHECKPOINT_NAME = "last.pt"
BEST_NAME = "best.pt"


@dataclass
class DeterminismReport:
    """What was asked for, what was granted, and what fell back."""

    requested: bool
    deterministic_algorithms: bool
    cudnn_deterministic: bool
    cublas_workspace_config: str | None
    fallbacks: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "deterministic_algorithms": self.deterministic_algorithms,
            "cudnn_deterministic": self.cudnn_deterministic,
            "cublas_workspace_config": self.cublas_workspace_config,
            "fallbacks": sorted(self.fallbacks),
        }


def request_determinism(seed: int, *, warn_only: bool = True) -> DeterminismReport:
    """Seed every generator and ask torch for deterministic kernels.

    `warn_only=True` is deliberate and is what SRS-077 requires. With it False, torch
    raises the first time it reaches an operation with no deterministic implementation,
    which on this network means training cannot start at all. Warning instead lets the
    run proceed and lets `describe_determinism` record what was non-deterministic, which
    is more honest than either aborting or silently not asking.

    CUBLAS_WORKSPACE_CONFIG is set because cuBLAS reductions are otherwise
    non-deterministic regardless of the torch flag. It must be set before the first CUDA
    context is created; setting it here is effective when this is called before any
    tensor reaches the device, which is what the training entry point does.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

    granted = True
    try:
        torch.use_deterministic_algorithms(True, warn_only=warn_only)
    except Exception:  # noqa: BLE001 - older torch, or a build without support
        granted = False

    cudnn_deterministic = False
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False  # benchmark picks kernels by timing
        cudnn_deterministic = bool(torch.backends.cudnn.deterministic)

    return DeterminismReport(
        requested=True,
        deterministic_algorithms=granted,
        cudnn_deterministic=cudnn_deterministic,
        cublas_workspace_config=os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
    )


def describe_determinism(report: DeterminismReport, warnings_seen: list[str]) -> dict[str, Any]:
    """Fold captured warnings into the report, so fallbacks reach the run output.

    torch reports a non-deterministic fallback as a UserWarning naming the operation.
    The training loop captures warnings and passes them here rather than this module
    installing a global warning filter, which would be a side effect on the whole
    process for the benefit of one record.
    """
    for message in warnings_seen:
        if "does not have a deterministic implementation" in message:
            report.fallbacks.append(message.strip().splitlines()[0])
    return report.as_dict()


def rng_state() -> dict[str, Any]:
    """Every generator that affects training (SRS-075).

    All four matter. Python's `random` drives some MONAI transforms, NumPy drives others
    and the split shuffle, torch CPU drives dataloader shuffling, and torch CUDA drives
    dropout on the device -- which is the one that matters most here, since dropout is
    non-zero by requirement so that MC-dropout works at inference.
    """
    state = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
    }
    if torch.cuda.is_available():
        state["torch_cuda"] = torch.cuda.get_rng_state_all()
    return state


def set_rng_state(state: dict[str, Any]) -> None:
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(_as_byte_tensor(state["torch"]))
    if "torch_cuda" in state and torch.cuda.is_available():
        torch.cuda.set_rng_state_all([_as_byte_tensor(s) for s in state["torch_cuda"]])


def _as_byte_tensor(value: Any) -> torch.Tensor:
    """torch.load may return the state as a tensor already; normalise either way."""
    if isinstance(value, torch.Tensor):
        return value.cpu().to(torch.uint8)
    return torch.as_tensor(value, dtype=torch.uint8)


def save_checkpoint(
    path: Path,
    *,
    epoch: int,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer | None = None,
    scheduler: Any | None = None,
    scaler: Any | None = None,
    best_metric: float | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Write a checkpoint atomically (SRS-075).

    Written to `<name>.tmp` and renamed. `os.replace` is atomic on POSIX and Windows, so
    a kill during the write cannot leave a half-written file in place of a good one --
    which is exactly the moment a checkpoint is needed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "epoch": int(epoch),
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict() if optimizer is not None else None,
        "scheduler": scheduler.state_dict() if scheduler is not None else None,
        "scaler": scaler.state_dict() if scaler is not None else None,
        "best_metric": best_metric,
        "rng": rng_state(),
        "extra": extra or {},
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    os.replace(temporary, path)
    return path


def load_checkpoint(
    path: Path,
    *,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer | None = None,
    scheduler: Any | None = None,
    scaler: Any | None = None,
    restore_rng: bool = True,
    map_location: str = "cpu",
) -> dict[str, Any]:
    """Restore a checkpoint and return its metadata.

    `restore_rng` defaults True and should stay True for a resume. It exists as a flag
    only for loading a checkpoint for *inference*, where continuing the training
    trajectory is meaningless and restoring a training RNG state would be misleading.
    """
    payload = torch.load(Path(path), map_location=map_location, weights_only=False)
    model.load_state_dict(payload["model"])
    if optimizer is not None and payload.get("optimizer") is not None:
        optimizer.load_state_dict(payload["optimizer"])
    if scheduler is not None and payload.get("scheduler") is not None:
        scheduler.load_state_dict(payload["scheduler"])
    if scaler is not None and payload.get("scaler") is not None:
        scaler.load_state_dict(payload["scaler"])
    if restore_rng and "rng" in payload:
        set_rng_state(payload["rng"])
    return {
        "epoch": int(payload["epoch"]),
        "best_metric": payload.get("best_metric"),
        "extra": payload.get("extra", {}),
    }


def find_resume(run_dir: Path) -> Path | None:
    """The checkpoint to resume from, or None for a fresh run.

    Resuming is detected from the run directory rather than requested by a flag. On a
    preemptible machine the resume is the normal case and the flag would be the thing
    forgotten; an absent checkpoint already means a fresh run, unambiguously.
    """
    candidate = Path(run_dir) / CHECKPOINT_NAME
    return candidate if candidate.is_file() else None


def resume_tolerance(device: str) -> float:
    """Tolerance for SRS-076's equivalence check, by device.

    Zero on CPU: the operations this network uses are deterministic there, so a resumed
    run is bit-identical and anything else is a defect.

    Non-zero on CUDA because some kernels reachable from this network have no
    deterministic implementation. The value is a stated bound on accumulated
    floating-point divergence over a few epochs at float32, not a measurement of
    correctness -- exceeding it means something other than kernel non-determinism is
    wrong, and staying within it is not proof that nothing is.
    """
    return 0.0 if device == "cpu" else 1e-4
