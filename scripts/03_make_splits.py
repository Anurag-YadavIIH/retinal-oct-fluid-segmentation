"""Build and persist a leave-one-vendor-out, patient-level split.

Traces to: SRS-018..SRS-023, SRS-031
Implements risk control: RC-001..RC-005

Asserts no patient overlap before writing. See CLAUDE.md rule 2: no patient, volume or
B-scan may appear in more than one split, and a failure here means the data pipeline is
wrong rather than that the assertion is inconvenient.

Takes the fold configuration; the data configuration is read from `--data-config` so the
manifest and output paths resolve the same way as in the other stages.

Usage:
    python scripts/03_make_splits.py --config configs/folds/spectralis_holdout.yaml
    python scripts/03_make_splits.py --config configs/folds        # every fold
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from ocuval.data.splits import Sample, assert_no_patient_overlap, leave_one_vendor_out, save
from ocuval.runs import load_manifest, manifest_path, resolve, write_provenance


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/folds"),
        help="a fold configuration, or a directory of them",
    )
    parser.add_argument("--data-config", type=Path, default=Path("configs/data.yaml"))
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def fold_configs(path: Path) -> list[Path]:
    return sorted(path.glob("*.yaml")) if path.is_dir() else [path]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_config = resolve(args.data_config, Path("."))
    output_root = args.output or data_config.path("splits_root")
    data_config = resolve(args.data_config, output_root)

    source = manifest_path(data_config.config)
    if not source.is_file():
        print(f"!! no manifest at {source}; run 01_convert_to_dicom.py first", file=sys.stderr)
        return 2
    rows = load_manifest(source)
    manifest = [Sample(r["sample_id"], r["patient_id"], r["vendor"]) for r in rows]

    configs = fold_configs(args.config)
    if not configs:
        print(f"!! no fold configuration found at {args.config}", file=sys.stderr)
        return 2

    write_provenance(
        "03_make_splits",
        data_config,
        {"manifest": str(source), "folds": [str(c) for c in configs], "volumes": len(manifest)},
    )

    written = []
    for config_path in configs:
        fold = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        split = leave_one_vendor_out(
            manifest,
            fold["held_out_vendor"],
            val_fraction=fold["split"]["val_fraction"],
            seed=fold["split"]["seed"],
            fold_id=fold["fold_id"],
            ref_fraction=fold["split"]["ref_fraction"],
        )
        # Rule 2, before anything is written. A split that leaks must not reach disk,
        # because a file on disk is the thing a later run will trust.
        assert_no_patient_overlap(split, manifest)

        destination = output_root / f"{split.fold_id}.json"
        save(split, destination)
        written.append(str(destination))
        print(
            f"  {split.fold_id:24} train={len(split.train):3} val={len(split.val):3} "
            f"test={len(split.test):3} ref={len(split.in_domain_ref):3}  -> {destination}",
            flush=True,
        )

    write_provenance(
        "03_make_splits",
        data_config,
        {
            "manifest": str(source),
            "folds": [str(c) for c in configs],
            "volumes": len(manifest),
            "splits_written": written,
        },
    )
    print(f"\nwrote {len(written)} split(s) from {len(manifest)} volumes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
