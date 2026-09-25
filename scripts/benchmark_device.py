"""Time the real training step on whatever accelerator is present.

Traces to: SRS-031 (the result is recorded with the resolved config)

Run this on each Kaggle accelerator before the first real run and use whichever is
faster. The planning estimate in `docs/13` is derived from measured FLOPs -- 75.6 GFLOP
per training image -- and an assumed ~30% MFU, which is an assumption and not a
measurement. The P100 in particular has **no tensor cores**, so its AMP gain is much
smaller than its 2:1 FP16 ratio suggests; the T4 does have them but is a slower card
overall. Which wins is an empirical question.

Times the whole step -- forward, loss, backward, optimiser -- on synthetic tensors of
the real shape, so the number is not contaminated by dataloading. Dataloading is
measured separately by the cache pre-pass timing.

Usage, on Kaggle:
    python scripts/benchmark_device.py --config configs/train_seg.yaml --iters 20
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("configs/train_seg.yaml"))
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5, help="discarded; CUDA is slow to settle")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def describe_device() -> dict[str, object]:
    if not torch.cuda.is_available():
        return {"device": "cpu", "name": platform.processor() or "cpu", "tensor_cores": False}
    index = torch.cuda.current_device()
    name = torch.cuda.get_device_name(index)
    major, _minor = torch.cuda.get_device_capability(index)
    return {
        "device": "cuda",
        "name": name,
        "count": torch.cuda.device_count(),
        "capability": f"{major}.{_minor}",
        # Tensor cores arrived with compute capability 7.0 (Volta). The P100 is 6.0.
        "tensor_cores": major >= 7,
        "total_memory_gb": round(torch.cuda.get_device_properties(index).total_memory / 1e9, 1),
    }


def time_steps(model, optimizer, loss_fn, batch, iters: int, warmup: int, amp: bool, device: str):
    images, labels = batch
    scaler = torch.cuda.amp.GradScaler(enabled=amp and device == "cuda")

    def one_step():
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type=device, enabled=amp and device == "cuda"):
            loss = loss_fn(model(images), labels)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

    for _ in range(warmup):
        one_step()
    if device == "cuda":
        torch.cuda.synchronize()

    started = time.perf_counter()
    for _ in range(iters):
        one_step()
    if device == "cuda":
        torch.cuda.synchronize()
    return time.perf_counter() - started


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    from monai.losses import DiceCELoss

    from ocuval.models.seg_unet import build_model

    device = "cuda" if torch.cuda.is_available() else "cpu"
    roi = tuple(int(v) for v in config["data"]["roi_size"])
    batch_size = int(config["train"]["batch_size"])
    classes = int(config["model"]["out_channels"])

    model = build_model(config).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(config["optim"]["lr"]))
    loss_fn = DiceCELoss(
        include_background=bool(config["loss"]["include_background"]),
        to_onehot_y=True,
        softmax=True,
    )
    images = torch.randn(batch_size, 1, *roi, device=device)
    labels = torch.randint(0, classes, (batch_size, 1, *roi), device=device)

    results = {}
    for amp in (False, True) if device == "cuda" else (False,):
        elapsed = time_steps(
            model, optimizer, loss_fn, (images, labels), args.iters, args.warmup, amp, device
        )
        per_step = elapsed / args.iters
        results["amp" if amp else "fp32"] = {
            "seconds_per_step": round(per_step, 4),
            "images_per_second": round(batch_size / per_step, 1),
        }

    record = {
        "hardware": describe_device(),
        "batch_size": batch_size,
        "roi_size": list(roi),
        "iters": args.iters,
        "warmup": args.warmup,
        "results": results,
        "torch": torch.__version__,
    }

    print(json.dumps(record, indent=2))
    for name, value in results.items():
        images_per_second = value["images_per_second"]
        print(f"\n{name:5} {images_per_second:7.1f} img/s", end="")
        for fold, frames in (("cirrus", 2610), ("spectralis", 4032), ("topcon", 3088)):
            hours = frames * 150 / images_per_second / 3600
            print(f"   {fold}={hours:.1f}h", end="")
    print("\n\n150 epochs per fold. Compare this figure between accelerators.")

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
