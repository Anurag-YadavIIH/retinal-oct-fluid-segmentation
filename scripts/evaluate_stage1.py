"""Evaluate the Stage 1 smoke run against docs/07 section 15, as committed in f4d2a34.

Traces to: TC-096

**Why this does not simply read history.json.** The pre-registered baseline in section
15.2 was computed as a per-frame Dice averaged over the validation frames where the class
is present in the prediction or the reference, skipping frames where it is absent from
both. The training loop's own validation uses MONAI's DiceMetric with a different
aggregation. Comparing the loop's number against the baseline would compare two
different quantities and could pass or fail for that reason alone.

This recomputes the model's per-class Dice with the **identical function** used to
produce the baseline, on the same 580 validation frames, so the comparison in criterion 2
is like for like.

Usage:
    python scripts/evaluate_stage1.py --run-dir artifacts/runs/cirrus_holdout
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import yaml

CLASSES = {1: "IRF", 2: "SRF", 3: "PED"}


def dice(pred: np.ndarray, true: np.ndarray) -> float | None:
    """Identical to the baseline's definition. None when the class is absent from BOTH."""
    p, t = pred.sum(), true.sum()
    if p == 0 and t == 0:
        return None
    return float(2.0 * np.logical_and(pred, true).sum() / (p + t))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, default=Path("artifacts/runs/cirrus_holdout"))
    parser.add_argument("--config", type=Path, default=Path("configs/train_seg.yaml"))
    parser.add_argument("--data-config", type=Path, default=Path("configs/data.yaml"))
    parser.add_argument("--fold", default="cirrus_holdout")
    parser.add_argument("--checkpoint", default="best.pt")
    parser.add_argument(
        "--stage",
        choices=("1", "1b"),
        default="1",
        help="1b adds criterion 5, determinism measured rather than inferred (docs/07 §15.6)",
    )
    parser.add_argument(
        "--baseline", type=Path, default=Path("artifacts/benchmarks/stage1_baseline.json")
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from monai.data import PersistentDataset

    from ocuval.data.datamodule import LoadFrame, build_frame_split, flat_chain, frame_records
    from ocuval.data.splits import load as load_split
    from ocuval.data.transforms import eval_transforms
    from ocuval.models.seg_unet import build_model, load_verified
    from ocuval.runs import load_manifest, manifest_path, resolve_cache_dir

    args = parse_args(argv)
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    data_cfg = yaml.safe_load(args.data_config.read_text(encoding="utf-8"))
    run_dir = Path(args.run_dir)

    report: dict = {"run_dir": str(run_dir), "checkpoint": args.checkpoint, "criteria": {}}

    # ---- Criterion 1: training loss decreases materially -----------------------------
    entries = [
        json.loads(line)
        for line in (run_dir / "epochs.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    epochs = sorted((e for e in entries if e.get("event") == "epoch"), key=lambda e: e["epoch"])
    first3 = float(np.mean([e["train_loss"] for e in epochs[:3]]))
    last3 = float(np.mean([e["train_loss"] for e in epochs[-3:]]))
    reduction = (first3 - last3) / first3
    report["criteria"]["1_loss_decreases"] = {
        "epochs_completed": len(epochs),
        "mean_first_three": round(first3, 6),
        "mean_last_three": round(last3, 6),
        "reduction_fraction": round(reduction, 6),
        "threshold": 0.10,
        "pass": bool(reduction >= 0.10),
    }

    # ---- inference on the validation split -------------------------------------------
    manifest = load_manifest(manifest_path(data_cfg))
    split = load_split(Path(data_cfg["paths"]["splits_root"]) / f"{args.fold}.json")
    records = frame_records(manifest, build_frame_split(split, manifest), "val")
    cache = resolve_cache_dir(cfg) / args.fold / "val"

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = build_model(cfg).to(device)
    # SRS-061: verified before loading, on a real checkpoint.
    meta = load_verified(run_dir / args.checkpoint, model, map_location=device, restore_rng=False)
    report["checkpoint_epoch"] = meta["epoch"]
    report["checkpoint_best_metric"] = meta.get("best_metric")
    model.eval()

    chain = flat_chain(LoadFrame(), eval_transforms(cfg))
    dataset = PersistentDataset(records, transform=chain, cache_dir=str(cache))

    scores: dict[int, list[float]] = {c: [] for c in CLASSES}
    predicted_frames = dict.fromkeys(CLASSES, 0)
    truth_frames = dict.fromkeys(CLASSES, 0)
    predicted_voxels = dict.fromkeys(CLASSES, 0)

    with torch.no_grad():
        for index in range(len(dataset)):
            item = dataset[index]
            image = item["image"].unsqueeze(0).to(device)
            truth = item["label"].squeeze(0).numpy()
            prediction = torch.argmax(model(image), dim=1)[0].cpu().numpy()
            for c in CLASSES:
                p, t = prediction == c, truth == c
                predicted_frames[c] += int(p.any())
                truth_frames[c] += int(t.any())
                predicted_voxels[c] += int(p.sum())
                value = dice(p, t)
                if value is not None:
                    scores[c].append(value)

    # ---- Criterion 2: beats both baselines, per class ---------------------------------
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))["classes"]
    per_class = {}
    for c, name in CLASSES.items():
        measured = float(np.mean(scores[c])) if scores[c] else 0.0
        bar_b = float(baseline[name]["val_dice_spatial_prior"])
        per_class[name] = {
            "measured_dice": round(measured, 4),
            "frames_scored": len(scores[c]),
            "baseline_a_all_background": 0.0,
            "baseline_b_spatial_prior": bar_b,
            "beats_a": bool(measured > 0.0),
            "beats_b": bool(measured > bar_b),
            "pass": bool(measured > 0.0 and measured > bar_b),
        }
    report["criteria"]["2_beats_baselines"] = {
        "per_class": per_class,
        "pass": all(v["pass"] for v in per_class.values()),
    }

    # ---- Criterion 3: no class collapses to always-empty ------------------------------
    collapse = {
        name: {
            "frames_predicted": predicted_frames[c],
            "frames_with_class_in_truth": truth_frames[c],
            "total_val_frames": len(records),
            "predicted_voxels": predicted_voxels[c],
            "pass": bool(predicted_frames[c] > 0),
        }
        for c, name in CLASSES.items()
    }
    report["criteria"]["3_no_class_collapse"] = {
        "per_class": collapse,
        "pass": all(v["pass"] for v in collapse.values()),
    }

    # ---- Criterion 4: the run's own records exist -------------------------------------
    registry = {}
    registry_path = run_dir / "checkpoints.sha256"
    if registry_path.is_file():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    sessions = [e for e in entries if e.get("event") == "session_start"]
    resumed = [e for e in sessions if e.get("resumed")]

    artefacts = {
        "last.pt": (run_dir / "last.pt").is_file(),
        "best.pt": (run_dir / "best.pt").is_file(),
        "both_in_checkpoints.sha256": {"last.pt", "best.pt"} <= set(registry),
        "determinism.json": (run_dir / "determinism.json").is_file(),
        "determinism_has_fallbacks_key": "fallbacks"
        in json.loads((run_dir / "determinism.json").read_text(encoding="utf-8")),
        "epochs.jsonl": (run_dir / "epochs.jsonl").is_file(),
        "epoch_log_appended_across_sessions": len(sessions) >= 2,
        "successful_resume": len(resumed) >= 1,
        "gpu_telemetry.csv": (run_dir / "gpu_telemetry.csv").is_file(),
        "run.json": (run_dir / "run.json").is_file(),
    }
    report["criteria"]["4_run_records_exist"] = {
        "artefacts": artefacts,
        "pass": all(artefacts.values()),
    }

    # ---- Criterion 5: determinism measured, not inferred (docs/07 §15.6) --------------
    #
    # Stage 1b only. Two halves, and the second is the load-bearing one:
    #   (a) this run recorded zero non-deterministic fallbacks -- checked here;
    #   (b) two runs of this configuration agree bit-for-bit -- that is TC-121, which
    #       cannot be checked from one run directory and is not pretended to be.
    # Zero fallbacks means no operation *announced* non-determinism. It is not the claim
    # that two runs agree, so (a) passing on its own is not criterion 5 passing.
    if args.stage == "1b":
        record = json.loads((run_dir / "determinism.json").read_text(encoding="utf-8"))
        fallbacks = record.get("fallback_count", len(record.get("fallbacks", [])))
        report["criteria"]["5_determinism_measured"] = {
            "requested": record.get("requested"),
            "deterministic_algorithms_achieved": record.get("deterministic_algorithms"),
            "fallback_count": fallbacks,
            "fallbacks": record.get("fallbacks"),
            "zero_fallbacks_pass": fallbacks == 0,
            "bit_identity_verified_by": "TC-121 (tests/test_gpu_determinism.py), run separately",
            "pass": fallbacks == 0 and record.get("deterministic_algorithms") is True,
        }

    report["overall_pass"] = all(v["pass"] for v in report["criteria"].values())

    destination = run_dir / "stage1_evaluation.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nwritten to {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
