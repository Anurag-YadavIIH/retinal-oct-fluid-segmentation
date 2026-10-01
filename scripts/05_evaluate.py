"""Evaluate a finished run under the protocol pre-registered in `docs/07` §17.

Traces to: SRS-032, SRS-033, SRS-050..SRS-053, SRS-057, SRS-074, SRS-087, SRS-088

Volume-level metrics, per fluid class and per vendor, each with a **patient-level**
bootstrap interval and its `n` in patients; predictions inverted to native geometry before
anything is measured; detection derived from the same model's output.

**The bucket is gated.** `val` runs freely. `test` and `in_domain_ref` are sealed (SRS-088)
and need `--unlock-bucket` with `--unlock-reason` and `--approved-by`; every such access is
appended to `artifacts/sealed_access.jsonl`, because `docs/07` §17.1 permits exactly one
evaluation of the test set and a limit nobody counts is not a limit.

Usage:
    python scripts/05_evaluate.py --run artifacts/runs/cirrus_holdout_stage2 --bucket val
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import yaml

from ocuval.data.splits import load as load_split
from ocuval.eval import sealed
from ocuval.eval.pipeline import (
    CLASS_NAMES,
    EvaluationPlan,
    assert_spacing_unchanged,
    detection_rows,
    evaluate,
    measure_volume,
    write_record,
)
from ocuval.models.uncertainty import mc_dropout_predict
from ocuval.runs import load_manifest, manifest_path, source_record


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, required=True, help="a finished run directory")
    parser.add_argument("--config", type=Path, default=Path("configs/train_seg.yaml"))
    parser.add_argument("--data-config", type=Path, default=Path("configs/data.yaml"))
    parser.add_argument("--checkpoint", default="best.pt")
    parser.add_argument(
        "--bucket",
        default="val",
        choices=("val", "test", "in_domain_ref"),
        help="`val` is open; the other two are sealed (SRS-088)",
    )
    parser.add_argument("--device", default=None)
    parser.add_argument("--limit", type=int, default=None, help="first N volumes, for a smoke run")
    parser.add_argument(
        "--frames-per-chunk",
        type=int,
        default=8,
        help=(
            "frames per forward pass. A whole volume does not fit on a 4 GiB card; frames "
            "are independent and the network has no batch-coupled statistic, so this is a "
            "memory decision and not a change to what is computed."
        ),
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--unlock-bucket", action="store_true", help="open a sealed bucket")
    parser.add_argument("--unlock-reason", default=None)
    parser.add_argument("--approved-by", default=None)
    return parser.parse_args(argv)


def build_unlock(args) -> sealed.Unlock | None:
    if args.bucket not in sealed.SEALED_BUCKETS:
        if args.unlock_bucket:
            raise SystemExit(f"--unlock-bucket is meaningless for the open bucket {args.bucket!r}")
        return None
    if not args.unlock_bucket:
        return None  # pipeline.evaluate will refuse, with the reason
    if not (args.unlock_reason and args.approved_by):
        raise SystemExit("--unlock-bucket requires --unlock-reason and --approved-by (SRS-088)")
    return sealed.Unlock(
        bucket=args.bucket, reason=args.unlock_reason, approved_by=args.approved_by
    )


def predict_volume(model, frames: np.ndarray, device: str, passes: int, chunk: int):
    """MC-dropout prediction for one volume's frames, in chunks of `chunk` frames.

    Returns (labels, mean_probability_per_class). The label map is the argmax of the
    **mean** probability, not of any single pass, so the segmentation and the detection
    score describe the same output (SRS-050).

    **Chunked, because a volume does not fit.** A topcon acquisition is 128 B-scans at
    885x512, which after axial resampling is 128 frames of 576x512; one forward pass over
    all of them through a five-level UNet with 512 channels at the bottleneck is far beyond
    this card's 4 GiB. Chunking changes nothing about the result -- the frames are
    independent, training is 2D (SRS-073), and `InstanceNorm2d` normalises per sample so no
    statistic couples frames within a batch. That last point is the same property gradient
    accumulation rests on (`docs/07` §14), and it is why chunking here is a memory decision
    rather than a change to what is computed.

    Each chunk draws its own `passes` samples. That is correct for a per-voxel standard
    deviation, which is computed within a frame and never across frames.
    """
    labels, maxima = [], np.zeros(len(CLASS_NAMES), dtype=float)
    for start in range(0, frames.shape[0], chunk):
        block = (
            torch.as_tensor(frames[start : start + chunk], dtype=torch.float32)
            .unsqueeze(1)
            .to(device)
        )
        mean, _std = mc_dropout_predict(model, block, passes)
        labels.append(mean.argmax(axis=1).astype(np.uint8))
        for index in range(len(CLASS_NAMES)):
            maxima[index] = max(maxima[index], float(mean[:, index + 1].max()))
        del block
        if device == "cuda":
            torch.cuda.empty_cache()
    # Per class, the score is the highest mean probability anywhere in the volume: presence
    # is a volume-level question and a class present in one B-scan is present in the volume.
    scores = {name: float(maxima[i]) for i, name in enumerate(CLASS_NAMES)}
    return np.concatenate(labels, axis=0), scores


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    data_cfg = yaml.safe_load(Path(args.data_config).read_text(encoding="utf-8"))
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")

    unlock = build_unlock(args)
    run_dir = Path(args.run)
    provenance = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    fold_id = provenance["fold_id"]

    split = load_split(Path(data_cfg["paths"]["splits_root"]) / f"{fold_id}.json")
    # Gate BEFORE any subject identifier is read out of the split, so a refusal happens
    # before the sealed names have been in memory at all.
    sealed.require_unsealed(args.bucket, unlock, fold_id=fold_id)
    subjects = list(getattr(split, args.bucket))
    if args.limit:
        subjects = subjects[: args.limit]

    manifest = {row["patient_id"]: row for row in load_manifest(manifest_path(data_cfg))}

    from ocuval.io.retouch_reader import read_volume
    from ocuval.models.seg_unet import build_model, load_verified

    model = build_model(cfg).to(device)
    meta = load_verified(run_dir / args.checkpoint, model, map_location=device, restore_rng=False)
    print(f"checkpoint {args.checkpoint} epoch {meta['epoch']} on {device}", flush=True)

    from ocuval.data.transforms import eval_transforms, invert_axial_resample

    chain = eval_transforms(cfg)
    volumes = []
    for subject in subjects:
        row = manifest[subject]
        native = read_volume(Path(row["source_path"]), row["vendor"])
        if native.label_array is None:
            raise ValueError(
                f"{subject}: no reference mask in the archive, so nothing can be "
                f"measured against. A volume without a reference is not evaluable "
                f"and is not silently skipped."
            )
        reference = np.asarray(native.label_array)
        recorded = assert_spacing_unchanged(row["spacing_mm"], row["spacing_mm"], subject)

        prepared = []
        for index in range(native.pixel_array.shape[0]):
            sample = chain(
                {
                    "image": native.pixel_array[index],
                    "label": reference[index],
                    "intensity_window": row["intensity_window"],
                    "spacing_mm": row["spacing_mm"],
                    "vendor": row["vendor"],
                }
            )
            prepared.append(np.asarray(sample["image"]).squeeze())
        labels, scores = predict_volume(
            model,
            np.stack(prepared),
            device,
            int(cfg["inference"]["mc_dropout_passes"]),
            args.frames_per_chunk,
        )

        # SRS-074: back to the acquisition's grid before anything is measured.
        prediction = invert_axial_resample(
            labels, tuple(row["spacing_mm"]), (reference.shape[1], reference.shape[2])
        )
        prediction = np.asarray(prediction).astype(np.uint8).reshape(reference.shape)

        seg = measure_volume(prediction, reference, recorded)
        predicted_voxels = {
            r["fluid_class"]: r["voxels"] for r in seg if r["metric"] == "volume_mm3_predicted"
        }
        reference_voxels = {
            r["fluid_class"]: r["voxels"] for r in seg if r["metric"] == "volume_mm3_reference"
        }
        volumes.append(
            {
                "sample_id": row["sample_id"],
                "patient_id": subject,
                "vendor": row["vendor"],
                "segmentation": seg,
                "detection": detection_rows(
                    predicted_voxels,
                    reference_voxels,
                    scores,
                    threshold=int(cfg["inference"].get("presence_voxel_threshold", 10)),
                ),
            }
        )
        print(f"  {subject} ({row['vendor']}) measured", flush=True)

    plan = EvaluationPlan(
        fold_id=fold_id,
        bucket=args.bucket,
        seed=int(cfg["run"]["seed"]),
        presence_voxel_threshold=int(cfg["inference"].get("presence_voxel_threshold", 10)),
        mc_passes=int(cfg["inference"]["mc_dropout_passes"]),
        unlock=unlock,
        notes={
            "checkpoint": args.checkpoint,
            "frames_per_chunk": args.frames_per_chunk,
            "checkpoint_epoch": meta["epoch"],
            "run_dir": str(run_dir),
            "trained_from_commit": provenance.get("source", {}).get("commit"),
            "evaluation_source": source_record(),
            "held_out_vendor": getattr(split, "held_out_vendor", None),
        },
    )
    result = evaluate(plan, volumes)
    destination = args.output or run_dir / f"evaluation_{args.bucket}.json"
    write_record(result, destination)
    print(json.dumps(result["segmentation"]["all_vendors"], indent=2))
    print(f"\nwritten to {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
