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

Usage:
    python scripts/benchmark_device.py --micro-batches 2 4 --iters 20
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import torch
import yaml

FOLD_FRAMES = {"cirrus_holdout": 2610, "spectralis_holdout": 4032, "topcon_holdout": 3088}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("configs/train_seg.yaml"))
    parser.add_argument("--data-config", type=Path, default=Path("configs/data.yaml"))
    parser.add_argument("--fold", default="cirrus_holdout")
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--micro-batches", type=int, nargs="+", default=[2, 4])
    parser.add_argument("--epochs", type=int, default=150, help="for the projection")
    parser.add_argument("--skip-real", action="store_true")
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


def real_rate(cfg, data_cfg, fold, micro, accumulation, amp, device, iters, warmup):
    """Same step, fed by the cached loader over real frames."""
    from monai.losses import DiceCELoss

    from ocuval.data.datamodule import build_loaders
    from ocuval.data.splits import load as load_split
    from ocuval.models.seg_unet import build_model
    from ocuval.runs import load_manifest, manifest_path

    manifest = load_manifest(manifest_path(data_cfg))
    split = load_split(Path(data_cfg["paths"]["splits_root"]) / f"{fold}.json")

    local = json.loads(json.dumps(cfg))
    local["train"]["micro_batch_size"] = micro
    train_loader, _, _ = build_loaders(split, local, manifest)

    model = build_model(cfg).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(cfg["optim"]["lr"]))
    loss_fn = DiceCELoss(include_background=False, to_onehot_y=True, softmax=True)
    step = make_step(model, optimizer, loss_fn, amp, device, accumulation)

    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    iterator = iter(train_loader)
    pending, done, started, images_seen = [], 0, None, 0
    total_steps = warmup + iters
    while done < total_steps:
        try:
            batch = next(iterator)
        except StopIteration:
            iterator = iter(train_loader)
            continue
        pending.append(
            (batch["image"].to(device, non_blocking=True), batch["label"].to(device).long())
        )
        if len(pending) < accumulation:
            continue
        step(pending)
        images_seen += sum(p[0].shape[0] for p in pending) if started is not None else 0
        pending = []
        done += 1
        if done == warmup:
            if device == "cuda":
                torch.cuda.synchronize()
            started = time.perf_counter()
            images_seen = 0

    if device == "cuda":
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    peak = torch.cuda.max_memory_allocated() / 2**30 if device == "cuda" else 0.0

    del model, optimizer, train_loader
    if device == "cuda":
        torch.cuda.empty_cache()

    return {
        "seconds_per_optimizer_step": round(elapsed / iters, 4),
        "images_per_second": round(images_seen / elapsed, 1),
        "peak_gpu_gib": round(peak, 2),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    data_cfg = yaml.safe_load(Path(args.data_config).read_text(encoding="utf-8"))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    effective = int(cfg["train"]["batch_size"])

    hardware = describe_device()
    print(json.dumps(hardware, indent=2), flush=True)
    if device == "cuda" and not hardware["tensor_cores"]:
        print(
            "\nNOTE: no tensor cores on this device (capability "
            f"{hardware['capability']}). FP16 arithmetic is heavily reduced on consumer "
            "Pascal, so AMP may save memory and cost time. Both are measured.\n",
            flush=True,
        )

    rows = []
    for micro in args.micro_batches:
        if effective % micro:
            print(f"skipping micro-batch {micro}: does not divide {effective}", flush=True)
            continue
        accumulation = effective // micro
        for amp in (False, True) if device == "cuda" else (False,):
            label = f"micro={micro} accum={accumulation} amp={'on' if amp else 'off'}"
            row = {"micro_batch": micro, "accumulation": accumulation, "amp": amp}
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
                    )
                    print(f"  real       {label}: {row['real_loader']}", flush=True)
                except torch.cuda.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    row["real_loader"] = {"error": "out of memory"}
                    print(f"  real       {label}: OUT OF MEMORY", flush=True)
            rows.append(row)

    record = {
        "hardware": hardware,
        "effective_batch_size": effective,
        "roi_size": list(cfg["data"]["roi_size"]),
        "num_workers": cfg["data"].get("num_workers"),
        "cache_dir": cfg["data"].get("cache_dir"),
        "iters": args.iters,
        "warmup": args.warmup,
        "epochs_projected": args.epochs,
        "rows": rows,
    }

    print(
        f"\n{'config':28} {'peak GiB':>9} {'img/s':>8} {'h/epoch':>8}   hours per fold at "
        f"{args.epochs} epochs"
    )
    for row in rows:
        for source in ("real_loader", "synthetic"):
            value = row.get(source)
            if not value or "error" in value:
                continue
            rate = value["images_per_second"]
            label = f"{source[:4]} m={row['micro_batch']} amp={'on' if row['amp'] else 'off'}"
            per_epoch = FOLD_FRAMES[args.fold] / rate / 3600
            line = f"{label:28} {value['peak_gpu_gib']:>9.2f} {rate:>8.1f} {per_epoch:>8.3f}   "
            line += "  ".join(
                f"{fold.split('_')[0]}={frames * args.epochs / rate / 3600:5.1f}h"
                for fold, frames in FOLD_FRAMES.items()
            )
            print(line)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"\nwritten to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
