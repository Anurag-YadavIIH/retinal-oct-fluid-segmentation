"""The segmentation training loop.

Traces to: SRS-024, SRS-031, SRS-075, SRS-076, SRS-077
Implements risk control: RC-018 (run provenance), RC-028 (checkpoint integrity)
Verifies: TC-050, TC-057

**Resume is the normal path, not an exception.** Kaggle sessions are preemptible, so the
loop looks for a checkpoint in the run directory and continues from it rather than
requiring a flag. An absent checkpoint already means a fresh run, unambiguously, and a
flag would be the thing forgotten at the moment it mattered.

**Validation order is fixed, training order is shuffled.** A metric computed over a
shuffled loader is identical in expectation and different in floating-point detail, so
two evaluations of one checkpoint would disagree in the last digits for no reason.

**Non-deterministic kernels are recorded rather than suppressed.** SRS-077 asks for
`torch.use_deterministic_algorithms` with a fallback, and for the fallback list to reach
the run output. The loop captures warnings for the whole run and writes what fell back,
because an undocumented fallback is an undocumented source of run-to-run variation.
"""

from __future__ import annotations

import json
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch

from ocuval.data.datamodule import accumulation_plan
from ocuval.data.splits import Split
from ocuval.training.checkpoint import (
    BEST_NAME,
    CHECKPOINT_NAME,
    describe_determinism,
    find_resume,
    load_checkpoint,
    request_determinism,
    save_checkpoint,
)


@dataclass
class EpochResult:
    epoch: int
    train_loss: float
    val_dice: float | None = None
    per_class_dice: list[float] = field(default_factory=list)
    seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "train_loss": round(self.train_loss, 6),
            "val_dice": None if self.val_dice is None else round(self.val_dice, 6),
            "per_class_dice": [round(v, 6) for v in self.per_class_dice],
            "seconds": round(self.seconds, 1),
        }


def build_loss(cfg: dict):
    from monai.losses import DiceCELoss

    loss_cfg = cfg["loss"]
    if str(loss_cfg.get("name", "dice_ce")).lower() != "dice_ce":
        raise ValueError(f"unsupported loss {loss_cfg['name']!r}; only 'dice_ce' is provided")
    # include_background False: the classes are imbalanced and background dominates every
    # B-scan, so including it would let a model that predicts nothing score well.
    return DiceCELoss(
        include_background=bool(loss_cfg.get("include_background", False)),
        to_onehot_y=bool(loss_cfg.get("to_onehot_y", True)),
        softmax=bool(loss_cfg.get("softmax", True)),
    )


def build_optimizer(cfg: dict, model: torch.nn.Module):
    optim_cfg = cfg["optim"]
    name = str(optim_cfg.get("name", "adamw")).lower()
    if name != "adamw":
        raise ValueError(f"unsupported optimiser {name!r}; only 'adamw' is provided")
    return torch.optim.AdamW(
        model.parameters(),
        lr=float(optim_cfg["lr"]),
        weight_decay=float(optim_cfg.get("weight_decay", 0.0)),
    )


def build_scheduler(cfg: dict, optimizer, epochs: int):
    name = str(cfg["optim"].get("scheduler", "cosine")).lower()
    if name != "cosine":
        raise ValueError(f"unsupported scheduler {name!r}; only 'cosine' is provided")
    return torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, epochs))


@torch.no_grad()
def validate(model, loader, classes: int, device: str) -> tuple[float, list[float]]:
    """Mean foreground Dice and the per-class values.

    Per class as well as mean, because CLAUDE.md §5 requires per-class reporting and a
    mean can hide a class the model never predicts -- which with three fluid classes of
    very different prevalence is the likely failure, not a hypothetical one.
    """
    from monai.metrics import DiceMetric

    metric = DiceMetric(include_background=False, reduction="mean_batch", get_not_nans=False)
    model.eval()
    for batch in loader:
        images = batch["image"].to(device)
        labels = batch["label"].to(device)
        logits = model(images)
        predicted = torch.argmax(logits, dim=1, keepdim=True)
        one_hot_pred = torch.zeros_like(logits).scatter_(1, predicted, 1.0)
        one_hot_true = torch.zeros_like(logits).scatter_(1, labels.long(), 1.0)
        metric(y_pred=one_hot_pred, y=one_hot_true)
    per_class = metric.aggregate()
    metric.reset()
    values = [float(v) for v in torch.atleast_1d(per_class)]
    finite = [v for v in values if v == v]  # NaN where a class is absent everywhere
    return (sum(finite) / len(finite) if finite else float("nan")), values


def train_fold(
    split: Split,
    cfg: dict,
    manifest: list[dict[str, Any]],
    run_dir: Path,
    *,
    device: str | None = None,
    max_epochs: int | None = None,
) -> list[EpochResult]:
    """Train one fold, resuming if the run directory holds a checkpoint.

    Returns the per-epoch history. Everything else it produces -- checkpoints, the
    provenance record, the determinism report -- lands in `run_dir`.
    """
    from ocuval.data.datamodule import build_loaders
    from ocuval.models.seg_unet import build_model, record_checkpoint_hash

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")

    seed = int(cfg.get("run", {}).get("seed", 0))
    determinism = request_determinism(seed)

    train_cfg = cfg["train"]
    epochs = int(max_epochs if max_epochs is not None else train_cfg["epochs"])
    patience = int(train_cfg.get("early_stopping_patience", 25))
    grad_clip = float(train_cfg.get("grad_clip", 0.0))
    use_amp = bool(train_cfg.get("amp", True)) and device == "cuda"
    classes = int(cfg["model"]["out_channels"])

    micro_batch, accumulation_steps, effective_batch = accumulation_plan(cfg)
    train_loader, val_loader, _ = build_loaders(split, cfg, manifest)
    model = build_model(cfg).to(device)
    loss_fn = build_loss(cfg)
    optimizer = build_optimizer(cfg, model)
    scheduler = build_scheduler(cfg, optimizer, epochs)
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

    start_epoch, best_metric, best_epoch = 0, float("-inf"), -1
    resume_from = find_resume(run_dir)
    if resume_from is not None:
        meta = load_checkpoint(
            resume_from,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=scaler,
            map_location=device,
        )
        start_epoch = meta["epoch"] + 1
        if meta["best_metric"] is not None:
            best_metric = float(meta["best_metric"])
        print(f"resuming from epoch {start_epoch} (best so far {best_metric:.4f})", flush=True)

    history: list[EpochResult] = []
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")

        for epoch in range(start_epoch, epochs):
            started = time.time()
            model.train()
            total, seen = 0.0, 0
            optimizer.zero_grad(set_to_none=True)
            pending = 0

            for position, batch in enumerate(train_loader):
                images = batch["image"].to(device)
                labels = batch["label"].to(device).long()
                with torch.autocast(device_type=device, enabled=use_amp):
                    loss = loss_fn(model(images), labels)
                # Scale by 1/steps so the accumulated gradient is the MEAN over the
                # effective batch rather than the sum. Without this the gradient is
                # `steps` times too large and the run is not the run that was
                # configured -- TC-078 asserts exactly this, by checking that omitting
                # the scaling falls outside the tolerance.
                scaler.scale(loss / accumulation_steps).backward()
                total += float(loss.detach()) * images.shape[0]
                seen += images.shape[0]
                pending += 1

                is_last = position + 1 == len(train_loader)
                if pending < accumulation_steps and not is_last:
                    continue

                # Clipping applies to the ACCUMULATED gradient, once per optimiser step.
                # Clipping each micro-batch would clip a partial gradient and change the
                # direction of the step, not merely its length.
                if grad_clip > 0:
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
                pending = 0
            scheduler.step()

            result = EpochResult(epoch=epoch, train_loss=total / max(1, seen))
            if (epoch + 1) % int(train_cfg.get("val_interval", 1)) == 0:
                result.val_dice, result.per_class_dice = validate(
                    model, val_loader, classes, device
                )
            result.seconds = time.time() - started
            history.append(result)
            print(json.dumps(result.as_dict()), flush=True)

            # Written every epoch, before any early-stopping decision, so an interrupted
            # run always resumes from the most recent state rather than the best one.
            last = save_checkpoint(
                run_dir / CHECKPOINT_NAME,
                epoch=epoch,
                model=model,
                optimizer=optimizer,
                scheduler=scheduler,
                scaler=scaler,
                best_metric=best_metric if best_metric > float("-inf") else None,
                extra={"fold_id": split.fold_id, "device": device},
            )
            record_checkpoint_hash(last)

            if result.val_dice is not None and result.val_dice > best_metric:
                best_metric, best_epoch = result.val_dice, epoch
                best = save_checkpoint(
                    run_dir / BEST_NAME,
                    epoch=epoch,
                    model=model,
                    optimizer=optimizer,
                    scheduler=scheduler,
                    scaler=scaler,
                    best_metric=best_metric,
                    extra={"fold_id": split.fold_id, "device": device},
                )
                record_checkpoint_hash(best)
            elif best_epoch >= 0 and epoch - best_epoch >= patience:
                print(f"early stop: no improvement for {patience} epochs", flush=True)
                break

        messages = [str(w.message) for w in captured]

    (run_dir / "batching.json").write_text(
        json.dumps(
            {
                "effective_batch_size": effective_batch,
                "micro_batch_size": micro_batch,
                "accumulation_steps": accumulation_steps,
                "amp_enabled": use_amp,
                "device": device,
            },
            indent=2,
        )
        + chr(10),
        encoding="utf-8",
    )
    (run_dir / "determinism.json").write_text(
        json.dumps(describe_determinism(determinism, messages), indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "history.json").write_text(
        json.dumps([r.as_dict() for r in history], indent=2) + "\n", encoding="utf-8"
    )
    return history
