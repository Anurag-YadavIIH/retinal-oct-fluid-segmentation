"""Train one fold, resuming automatically if the run directory holds a checkpoint.

Traces to: SRS-024, SRS-031, SRS-075
Implements risk control: RC-018

Training runs on Kaggle, not in a development session (CLAUDE.md §6). This script is the
entry point that notebook calls.

The cache pre-pass runs first by default (SRS-078). Without it the first epoch pays
~1.9 h of per-frame volume decoding; with it, ~53 s of per-volume decoding.

Usage:
    python scripts/04_train.py --config configs/train_seg.yaml \\
        --fold configs/folds/spectralis_holdout.yaml --run-dir artifacts/runs/spectralis
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from ocuval.data.splits import load as load_split
from ocuval.runs import (
    DirtyWorkingTreeError,
    load_manifest,
    manifest_path,
    require_clean_tree,
    resolve,
    resolve_cache_dir,
    source_record,
    write_provenance,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("configs/train_seg.yaml"))
    parser.add_argument(
        "--fold", type=Path, default=None, help="defaults to data.fold in the config"
    )
    parser.add_argument("--data-config", type=Path, default=Path("configs/data.yaml"))
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=None, help="override train.epochs")
    parser.add_argument(
        "--max-epochs-this-session",
        type=int,
        default=None,
        help=(
            "train at most this many epochs now, checkpoint and exit (SRS-080). "
            "Bounds this invocation, not the fold: --epochs is the fold total."
        ),
    )
    parser.add_argument(
        "--telemetry-interval",
        type=float,
        default=30.0,
        help="seconds between accelerator telemetry samples; 0 disables (SRS-082)",
    )
    parser.add_argument("--device", default=None)
    parser.add_argument("--no-prepass", action="store_true", help="skip the cache pre-pass")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help=(
            "start even though the working tree has uncommitted changes (SRS-086). The "
            "run is then not reproducible from any commit, and run.json records that."
        ),
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help=(
            "where the frame cache lives; overrides OCUVAL_CACHE_DIR and data.cache_dir. "
            "The committed config holds a relative default because it is shared by every "
            "machine; the resolved path is recorded in run.json."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    fold_path = args.fold or Path(cfg["data"]["fold"])
    fold = yaml.safe_load(Path(fold_path).read_text(encoding="utf-8"))
    fold_id = fold["fold_id"]

    data_config = resolve(args.data_config, Path("."))
    source = manifest_path(data_config.config)
    if not source.is_file():
        print(f"!! no manifest at {source}; run 01_convert_to_dicom.py first", file=sys.stderr)
        return 2
    manifest = load_manifest(source)

    splits_root = data_config.path("splits_root")
    split_file = splits_root / f"{fold_id}.json"
    if not split_file.is_file():
        print(f"!! no split at {split_file}; run 03_make_splits.py first", file=sys.stderr)
        return 2
    # SRS-024: only from a resolved, persisted split. Never an ad-hoc sample list.
    split = load_split(split_file)

    run_dir = args.run_dir or Path("artifacts/runs") / fold_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # SRS-086: a fold run is meant to be cited, so it refuses to start against
    # uncommitted changes. The check lives here and not in `train_fold`, because tests
    # and exploratory runs must stay runnable from a tree that is being worked in.
    # Checked BEFORE the provenance is written, so a refused run leaves no record
    # suggesting it began.
    origin = source_record()
    try:
        require_clean_tree(origin, allow_dirty=args.allow_dirty)
    except DirtyWorkingTreeError as refusal:
        print(f"!! {refusal}", file=sys.stderr)
        return 3
    if args.allow_dirty and origin.get("dirty"):
        print(
            "!! --allow-dirty: this run cannot be reproduced from any commit, and "
            "run.json records that (SRS-086).",
            file=sys.stderr,
        )

    # SRS-031: provenance before training starts, so an aborted run still records what
    # it was attempting.
    resolved = resolve(args.config, run_dir)
    write_provenance(
        "04_train",
        resolved,
        {
            "fold_id": fold_id,
            "fold_config": str(fold_path),
            "split": str(split_file),
            "manifest": str(source),
            "resolved_fold": fold,
            # The config holds a relative default; this is where the cache actually was.
            "resolved_cache_dir": str(resolve_cache_dir(cfg, args.cache_dir).resolve()),
            "epochs_requested": args.epochs,
            "max_epochs_this_session": args.max_epochs_this_session,
            # Recorded even when false: an override nobody can see in the output is
            # indistinguishable from no check at all.
            "allow_dirty": bool(args.allow_dirty),
        },
    )

    if not args.no_prepass:
        from ocuval.data.datamodule import (
            LoadFrame,
            build_frame_split,
            flat_chain,
            frame_records,
            prepare_cache,
        )
        from ocuval.data.transforms import eval_transforms

        cache_root = resolve_cache_dir(cfg, args.cache_dir) / fold_id
        frame_split = build_frame_split(split, manifest)
        for bucket in ("train", "val"):
            records = frame_records(manifest, frame_split, bucket)
            chain = flat_chain(LoadFrame(), eval_transforms(cfg))
            counts = prepare_cache(records, chain, cache_root / bucket)
            print(
                f"pre-pass {bucket}: {len(records)} frames from {len(counts)} volumes", flush=True
            )

    from ocuval.training.loop import train_fold

    history = train_fold(
        split,
        cfg,
        manifest,
        run_dir,
        device=args.device,
        max_epochs=args.epochs,
        max_epochs_this_session=args.max_epochs_this_session,
        telemetry_interval=args.telemetry_interval or None,
    )
    best = max(
        (r for r in history if r.val_dice is not None), key=lambda r: r.val_dice, default=None
    )
    if best is not None:
        print(f"\nbest val dice {best.val_dice:.4f} at epoch {best.epoch}")
    print(f"run directory: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
