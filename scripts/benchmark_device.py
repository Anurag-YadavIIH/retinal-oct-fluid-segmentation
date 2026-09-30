"""Time the real training step on this machine, synthetically and through the real loader.

Traces to: SRS-031 (the result is recorded with the resolved config), SRS-079

Two measurements, because they answer different questions and the gap between them is
itself the answer to a third:

- **Synthetic**: forward, loss, backward and optimiser on tensors of the real shape.
  This is what the accelerator can do when nothing is waiting on data.
- **Real loader**: the same step driven by the cached `PersistentDataset` over real
  frames. On Windows, DataLoader workers start with `spawn` rather than `fork`, so
  worker startup is expensive and a laptop CPU can become the bottleneck instead of the
  GPU.

If the two agree, the GPU is the limit and a faster card would help. If the real-loader
figure is much lower, the CPU or the disk is the limit and a faster card would not.

AMP is measured rather than assumed. This machine is consumer Pascal (GTX 1050,
compute capability 6.1), which has **no tensor cores** and heavily reduced FP16
throughput; AMP may cut activation memory and still cost time. Both are reported.

**Two corrections, 2026-09-30, after this script's projection was mistaken for a
measurement** (`docs/13`):

- **Determinism is requested exactly as `train_fold` requests it**, via
  `request_determinism`, and can be turned off with `--no-determinism` to price it. It
  was previously not requested at all, so the benchmark timed a run the loop never
  performs: `torch.use_deterministic_algorithms(True)` selects different kernels, and a
  budget built on the faster ones understates every epoch.
- **The steady-state window is time-based, not a fixed iteration count.** `--iters` is
  now a floor and `--min-seconds` the real bound, because 20 optimiser steps is a few
  seconds against epochs that take minutes, and a few seconds is mostly cache warming.

**A projected epoch time is labelled `projected_`, never `measured_`.** Every field here
whose name does not start with `measured_` is arithmetic on a measurement, not one.

The loss comes from `build_loss(cfg)` rather than being constructed here, so what is
timed is what the run uses; `--loss` overrides it to compare two implementations under
one harness. Phase timings split the step into loading and augmentation, host-to-device
transfer, and forward plus backward, which is what identifies the bottleneck rather than
merely bounding it.

Usage:
    python scripts/benchmark_device.py --micro-batches 2 4 --min-seconds 60
    python scripts/benchmark_device.py --no-determinism --skip-synthetic   # price it
    python scripts/benchmark_device.py --loss deterministic --skip-synthetic
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import warnings
from pathlib import Path

import torch
import yaml

FOLD_FRAMES = {"cirrus_holdout": 2610, "spectralis_holdout": 4032, "topcon_holdout": 3088}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("configs/train_seg.yaml"))
    parser.add_argument("--data-config", type=Path, default=Path("configs/data.yaml"))
    parser.add_argument("--fold", default="cirrus_holdout")
    parser.add_argument(
        "--iters", type=int, default=20, help="minimum timed optimiser steps; a floor"
    )
    parser.add_argument(
        "--min-seconds",
        type=float,
        default=30.0,
        help="keep timing until this much steady state has elapsed; the real bound",
    )
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--micro-batches", type=int, nargs="+", default=[2, 4])
    parser.add_argument("--epochs", type=int, default=150, help="for the projection")
    parser.add_argument("--skip-real", action="store_true")
    parser.add_argument("--skip-synthetic", action="store_true")
    parser.add_argument(
        "--no-determinism",
        dest="determinism",
        action="store_false",
        help="measure without the determinism the loop requests, to price it",
    )
    parser.add_argument(
        "--loss",
        choices=("config", "monai", "deterministic"),
        default="config",
        help="'config' uses build_loss(cfg), which is what a run uses",
    )
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def describe_device() -> dict[str, object]:
    if not torch.cuda.is_available():
        return {"device": "cpu", "name": platform.processor() or "cpu", "tensor_cores": False}
    index = torch.cuda.current_device()
    major, minor = torch.cuda.get_device_capability(index)
    return {
        "device": "cuda",
        "name": torch.cuda.get_device_name(index),
        "capability": f"{major}.{minor}",
        # Tensor cores arrived with compute capability 7.0 (Volta). Pascal is 6.x.
        "tensor_cores": major >= 7,
        "total_memory_gib": round(torch.cuda.get_device_properties(index).total_memory / 2**30, 2),
        "torch_build": torch.__version__,
        "cuda_runtime": torch.version.cuda,
    }


def make_step(model, optimizer, loss_fn, amp: bool, device: str, accumulation: int):
    """One optimiser step over `accumulation` micro-batches, as the loop does it."""
    scaler = torch.cuda.amp.GradScaler(enabled=amp and device == "cuda")

    def step(micro_batches):
        optimizer.zero_grad(set_to_none=True)
        for images, labels in micro_batches:
            with torch.autocast(device_type=device, enabled=amp and device == "cuda"):
                loss = loss_fn(model(images), labels)
            scaler.scale(loss / accumulation).backward()
        scaler.step(optimizer)
        scaler.update()

    return step


def synthetic_rate(
    cfg, micro: int, accumulation: int, amp: bool, device: str, iters: int, warmup: int
):
    from monai.losses import DiceCELoss

    from ocuval.models.seg_unet import build_model

    roi = tuple(int(v) for v in cfg["data"]["roi_size"])
    classes = int(cfg["model"]["out_channels"])
    model = build_model(cfg).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(cfg["optim"]["lr"]))
    loss_fn = DiceCELoss(include_background=False, to_onehot_y=True, softmax=True)

    images = torch.randn(micro, 1, *roi, device=device)
    labels = torch.randint(0, classes, (micro, 1, *roi), device=device)
    micro_batches = [(images, labels)] * accumulation

    step = make_step(model, optimizer, loss_fn, amp, device, accumulation)
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    for _ in range(warmup):
        step(micro_batches)
    if device == "cuda":
        torch.cuda.synchronize()

    started = time.perf_counter()
    for _ in range(iters):
        step(micro_batches)
    if device == "cuda":
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - started

    peak = torch.cuda.max_memory_allocated() / 2**30 if device == "cuda" else 0.0
    del model, optimizer, images, labels, micro_batches
    if device == "cuda":
        torch.cuda.empty_cache()

    effective = micro * accumulation
    return {
        "seconds_per_optimizer_step": round(elapsed / iters, 4),
        "images_per_second": round(effective * iters / elapsed, 1),
        "peak_gpu_gib": round(peak, 2),
    }


def resolve_loss(cfg, choice: str):
    """The loss the run uses, or a named one to compare against it.

    `build_loss(cfg)` rather than a locally constructed `DiceCELoss`: a benchmark that
    builds its own loss measures a configuration nothing runs, which is how this script
    came to report a step the loop never performs.
    """
    from ocuval.training.loop import build_loss

    if choice == "config":
        return build_loss(cfg), "build_loss(cfg)"
    if choice == "monai":
        from monai.losses import DiceCELoss

        return DiceCELoss(include_background=False, to_onehot_y=True, softmax=True), "monai"
    from ocuval.training.losses import DeterministicDiceCELoss

    return (
        DeterministicDiceCELoss(include_background=False, to_onehot_y=True, softmax=True),
        "deterministic",
    )


def real_rate(
    cfg,
    data_cfg,
    fold,
    micro,
    accumulation,
    amp,
    device,
    iters,
    warmup,
    min_seconds: float = 0.0,
    loss_choice: str = "config",
):
    """Same step, fed by the cached loader over real frames, split by phase.

    The phase split exists because a single throughput figure bounds the problem without
    locating it. Loading is timed around `next(iterator)`, transfer around the `.to(device)`
    calls, and compute around the step -- with a `synchronize` before each boundary on
    CUDA, since without one the asynchronous launch queue attributes GPU time to whichever
    host call happens to block next.
    """
    from ocuval.data.datamodule import build_loaders, seed_epoch
    from ocuval.data.splits import load as load_split
    from ocuval.models.seg_unet import build_model
    from ocuval.runs import load_manifest, manifest_path

    manifest = load_manifest(manifest_path(data_cfg))
    split = load_split(Path(data_cfg["paths"]["splits_root"]) / f"{fold}.json")

    local = json.loads(json.dumps(cfg))
    local["train"]["micro_batch_size"] = micro
    train_loader, val_loader, _ = build_loaders(split, local, manifest)
    # Seeded as the loop seeds it, so the augmentation work timed here is an epoch's work
    # and not whatever the construction seed happened to produce.
    seed_epoch(train_loader, cfg.get("run", {}).get("seed"), 0)

    model = build_model(cfg).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(cfg["optim"]["lr"]))
    loss_fn, loss_name = resolve_loss(cfg, loss_choice)
    step = make_step(model, optimizer, loss_fn, amp, device, accumulation)

    def sync() -> None:
        if device == "cuda":
            torch.cuda.synchronize()

    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    iterator = iter(train_loader)
    pending: list[tuple[torch.Tensor, torch.Tensor]] = []
    done, started, images_seen = 0, None, 0
    phases = {"load_augment": 0.0, "transfer": 0.0, "compute": 0.0}
    while True:
        mark = time.perf_counter()
        try:
            batch = next(iterator)
        except StopIteration:
            iterator = iter(train_loader)
            continue
        loading = time.perf_counter() - mark

        mark = time.perf_counter()
        pending.append((batch["image"].to(device), batch["label"].to(device).long()))
        sync()
        transfer = time.perf_counter() - mark

        if started is not None:
            phases["load_augment"] += loading
            phases["transfer"] += transfer
        if len(pending) < accumulation:
            continue

        mark = time.perf_counter()
        step(pending)
        sync()
        if started is not None:
            phases["compute"] += time.perf_counter() - mark
            images_seen += sum(p[0].shape[0] for p in pending)
        pending = []
        done += 1

        if done == warmup:
            sync()
            started = time.perf_counter()
            images_seen = 0
            phases = dict.fromkeys(phases, 0.0)
        elif started is not None:
            timed = done - warmup
            # Both bounds: enough steps to be a sample, and enough wall time that cache
            # warming and one-off allocations are a small fraction of what is measured.
            if timed >= iters and time.perf_counter() - started >= min_seconds:
                break

    sync()
    elapsed = time.perf_counter() - started
    timed_steps = done - warmup
    peak = torch.cuda.max_memory_allocated() / 2**30 if device == "cuda" else 0.0

    # Validation is timed separately because it is a different shape of work -- no
    # backward, no optimiser, and the eval chain has no random transforms -- so folding it
    # into the training rate would understate the epoch it is part of.
    validation = None
    mark = time.perf_counter()
    model.eval()
    val_images = 0
    with torch.no_grad():
        for batch in val_loader:
            images = batch["image"].to(device)
            model(images)
            val_images += int(images.shape[0])
    sync()
    if val_images:
        validation = {
            "measured_seconds": round(time.perf_counter() - mark, 3),
            "measured_images": val_images,
            "measured_images_per_second": round(val_images / (time.perf_counter() - mark), 1),
        }

    del model, optimizer, train_loader, val_loader
    if device == "cuda":
        torch.cuda.empty_cache()

    accounted = sum(phases.values())
    return {
        "loss": loss_name,
        "measured_seconds_per_optimizer_step": round(elapsed / timed_steps, 4),
        "measured_images_per_second": round(images_seen / elapsed, 1),
        "measured_steady_state_seconds": round(elapsed, 2),
        "measured_timed_steps": timed_steps,
        "peak_gpu_gib": round(peak, 2),
        "measured_phase_seconds": {k: round(v, 3) for k, v in phases.items()},
        "measured_phase_fraction": (
            {k: round(v / accounted, 3) for k, v in phases.items()} if accounted else None
        ),
        # Anything the three phases do not account for: queueing, the collate, Python
        # overhead between the timed regions. Reported rather than silently absorbed.
        "measured_unaccounted_seconds": round(elapsed - accounted, 3),
        "validation": validation,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    data_cfg = yaml.safe_load(Path(args.data_config).read_text(encoding="utf-8"))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    effective = int(cfg["train"]["batch_size"])

    # Requested exactly as train_fold requests it (loop.py:224), and before any model or
    # loader is built. A benchmark that omits this measures kernels the run never selects.
    report = None
    if args.determinism:
        from ocuval.training.checkpoint import request_determinism

        report = request_determinism(int(cfg.get("run", {}).get("seed", 0)))

    hardware = describe_device()
    print(json.dumps(hardware, indent=2), flush=True)
    how = "requested as the loop does" if args.determinism else "OFF (--no-determinism)"
    print(f"determinism: {how}", flush=True)
    if device == "cuda" and not hardware["tensor_cores"]:
        print(
            "\nNOTE: no tensor cores on this device (capability "
            f"{hardware['capability']}). FP16 arithmetic is heavily reduced on consumer "
            "Pascal, so AMP may save memory and cost time. Both are measured.\n",
            flush=True,
        )

    # Fallbacks are warnings raised *during* compute, so a determinism record snapshotted
    # before the first step necessarily reports zero of them -- which reads as "none
    # occurred" and is exactly the self-contradicting record SRS-085 exists to forbid.
    # They are collected across the whole measurement and resolved afterwards, as
    # `train_fold` does it.
    rows = []
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        for micro in args.micro_batches:
            if effective % micro:
                print(f"skipping micro-batch {micro}: does not divide {effective}", flush=True)
                continue
            accumulation = effective // micro
            for amp in (False, True) if device == "cuda" else (False,):
                label = f"micro={micro} accum={accumulation} amp={'on' if amp else 'off'}"
                row = {"micro_batch": micro, "accumulation": accumulation, "amp": amp}
                if not args.skip_synthetic:
                    try:
                        row["synthetic"] = synthetic_rate(
                            cfg, micro, accumulation, amp, device, args.iters, args.warmup
                        )
                        print(f"  synthetic  {label}: {row['synthetic']}", flush=True)
                    except torch.cuda.OutOfMemoryError:
                        torch.cuda.empty_cache()
                        row["synthetic"] = {"error": "out of memory"}
                        print(f"  synthetic  {label}: OUT OF MEMORY", flush=True)
                        rows.append(row)
                        continue

                if not args.skip_real:
                    try:
                        row["real_loader"] = real_rate(
                            cfg,
                            data_cfg,
                            args.fold,
                            micro,
                            accumulation,
                            amp,
                            device,
                            args.iters,
                            args.warmup,
                            min_seconds=args.min_seconds,
                            loss_choice=args.loss,
                        )
                        print(f"  real       {label}: {row['real_loader']}", flush=True)
                    except torch.cuda.OutOfMemoryError:
                        torch.cuda.empty_cache()
                        row["real_loader"] = {"error": "out of memory"}
                        print(f"  real       {label}: OUT OF MEMORY", flush=True)
                rows.append(row)

    determinism = None
    if report is not None:
        from ocuval.training.checkpoint import describe_determinism

        determinism = describe_determinism(report, [str(w.message) for w in captured])
        print(
            f"determinism achieved: {determinism['deterministic_algorithms']} "
            f"({determinism['fallback_count']} operation(s) fell back)",
            flush=True,
        )

    record = {
        "hardware": hardware,
        "effective_batch_size": effective,
        "roi_size": list(cfg["data"]["roi_size"]),
        "num_workers": cfg["data"].get("num_workers"),
        "cache_dir": cfg["data"].get("cache_dir"),
        "iters": args.iters,
        "min_seconds": args.min_seconds,
        "warmup": args.warmup,
        "determinism_requested": args.determinism,
        "determinism": determinism,
        "loss_choice": args.loss,
        "epochs_projected": args.epochs,
        "rows": rows,
    }

    # Everything right of img/s is arithmetic on the measurement, and the header says so.
    # This table's projected epoch time was once quoted as an observed rate (`docs/13`).
    print(
        f"\n{'config':28} {'peak GiB':>9} {'MEASURED':>9} | {'PROJECTED h/epoch':>17}   "
        f"PROJECTED hours per fold at {args.epochs} epochs"
    )
    print(f"{'':28} {'':>9} {'img/s':>9} |")
    for row in rows:
        for source in ("real_loader", "synthetic"):
            value = row.get(source)
            if not value or "error" in value:
                continue
            rate = value.get("measured_images_per_second", value.get("images_per_second"))
            label = f"{source[:4]} m={row['micro_batch']} amp={'on' if row['amp'] else 'off'}"
            per_epoch = FOLD_FRAMES[args.fold] / rate / 3600
            line = f"{label:28} {value['peak_gpu_gib']:>9.2f} {rate:>9.1f} | {per_epoch:>17.3f}   "
            line += "  ".join(
                f"{fold.split('_')[0]}={frames * args.epochs / rate / 3600:5.1f}h"
                for fold, frames in FOLD_FRAMES.items()
            )
            print(line)
            phases = value.get("measured_phase_fraction")
            if phases:
                share = "  ".join(f"{k}={v:.0%}" for k, v in phases.items())
                print(f"{'':28} measured phase share: {share}")

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"\nwritten to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
