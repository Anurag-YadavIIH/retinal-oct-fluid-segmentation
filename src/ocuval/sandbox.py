"""A synthetic repository root, for a chain's mandatory dry run (SRS-107).

Traces to: SRS-107, SRS-108
Verified by: TC-156, TC-157

A dry run executes a chain's own steps, with the same scripts and arguments, from a root that
holds synthetic data only. Every path the chain scripts use resolves against the working
directory (configs, the manifest, the archive, the records, the saved maps, the outputs), so a
step run from the sandbox reads and writes nothing of the repository's. Its access log is marked
as a sandbox, the one place the SRS-088 gate opens a sealed bucket without a certificate.

**Nothing here reads RETOUCH** (`docs/06` DMP-C12). The volumes are built from integer
arithmetic and a seeded generator: in each, IRF is present in both prediction and reference,
SRF is predicted where the reference has none, above the presence threshold, and PED is absent
from both. That gives the §21.2 rule a worst, median and best scan and a false-positive case.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import yaml

from ocuval.eval import predictions, sealed
from ocuval.eval.pipeline import EvaluationPlan, evaluate
from ocuval.eval.report import FOLDS, RUN_DIRS

REPO = Path(__file__).resolve().parents[2]
SPACINGS = {  # (axial, lateral, separation), within configs/data.yaml's per-vendor ranges
    "cirrus": (0.001955, 0.011742, 0.046878),
    "spectralis": (0.003872, 0.011406, 0.120774),
    "topcon": (0.0026, 0.01172, 0.04688),
}
ARCHIVE = Path("data") / "raw" / "synthetic"
PREDICTIONS = Path("artifacts") / "predictions_final"


def synthetic_volumes(vendor: str, n: int = 3, first: int = 1) -> list[dict]:
    """`n` volumes of one vendor, identified TRAIN{first:03d} onwards."""
    rng = np.random.default_rng(1000 * len(vendor) + first)
    out = []
    for k in range(n):
        index = first + k
        shape = (4, 40 + index, 24)
        reference = np.zeros(shape, dtype=np.uint8)
        prediction = np.zeros(shape, dtype=np.uint8)
        reference[1:3, 10:20, 5:15] = 1
        prediction[1:3, 11 + index % 3 : 21, 6 + k : 15] = 1
        prediction[0, 30:34, 2 : 8 + k] = 2
        out.append(
            {
                "patient_id": f"TRAIN{index:03d}",
                "sample_id": f"S{index:03d}",
                "vendor": vendor,
                "prediction": prediction,
                "reference": reference,
                "image": (rng.random(shape) * 255).astype(np.uint8),
                "spacing_mm": SPACINGS[vendor],
                "scores": {"IRF": float(rng.random()), "SRF": 0.6, "PED": 0.01},
            }
        )
    return out


def write_metaimage(directory: Path, stem: str, array: np.ndarray, spacing: tuple) -> None:
    """A RETOUCH-style MetaImage pair. The header orders spacing (lateral, axial, separation)
    and sizes (columns, rows, B-scans); `spacing` is in the project's (axial, lateral,
    separation) order, written with `repr` so it reads back bit-identically."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{stem}.raw").write_bytes(np.ascontiguousarray(array, dtype=np.uint8).tobytes())
    axial, lateral, separation = spacing
    slices, rows, cols = array.shape
    lines = [
        "ObjectType = Image",
        "NDims = 3",
        "BinaryData = True",
        "BinaryDataByteOrderMSB = False",
        "CompressedData = False",
        f"ElementSpacing = {lateral!r} {axial!r} {separation!r}",
        f"DimSize = {cols} {rows} {slices}",
        "ElementNumberOfChannels = 1",
        "ElementType = MET_UCHAR",
        f"ElementDataFile = {stem}.raw",
    ]
    (directory / f"{stem}.mhd").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_final_bscans(root: Path, volumes_per_fold: int = 3) -> dict[str, list[dict]]:
    """The inputs of `docs/07` §21.11, synthetic: what `09_illustrative_bscans.py
    --record-set final` reads, under `root`. Returns the volumes, by fold."""
    root = Path(root)
    if root.resolve() == REPO.resolve():
        raise ValueError("a sandbox is never the repository itself")
    (root / "configs").mkdir(parents=True, exist_ok=True)
    for name in ("train_seg.yaml", "data.yaml"):
        shutil.copyfile(REPO / "configs" / name, root / "configs" / name)
    cfg = yaml.safe_load((REPO / "configs" / "train_seg.yaml").read_text(encoding="utf-8"))
    data_cfg = yaml.safe_load((REPO / "configs" / "data.yaml").read_text(encoding="utf-8"))
    threshold = int(cfg["inference"]["presence_voxel_threshold"])
    passes = int(cfg["inference"]["mc_dropout_passes"])

    by_fold, rows = {}, []
    for number, fold in enumerate(FOLDS):
        volumes = synthetic_volumes(fold, volumes_per_fold, first=1 + 20 * number)
        by_fold[fold] = volumes
        fold_id = f"{fold}_holdout"
        folder = PREDICTIONS / fold_id / "test"
        entries, measured = {}, []
        for v in volumes:
            source = ARCHIVE / v["patient_id"]
            write_metaimage(root / source, "oct", v["image"], v["spacing_mm"])
            write_metaimage(root / source, "reference", v["reference"], v["spacing_mm"])
            rows.append(
                {"patient_id": v["patient_id"], "sample_id": v["sample_id"],
                 "vendor": v["vendor"], "spacing_mm": list(v["spacing_mm"]),
                 "source_path": source.as_posix(), "intensity_window": [0.0, 255.0]}
            )  # fmt: skip
            entries[v["patient_id"]] = predictions.save_prediction(
                root / folder,
                patient_id=v["patient_id"],
                sample_id=v["sample_id"],
                vendor=v["vendor"],
                labels=v["prediction"],
                spacing_mm=v["spacing_mm"],
                scores=v["scores"],
            )
            measured.append(
                predictions.measured_volume(
                    sample_id=v["sample_id"],
                    patient_id=v["patient_id"],
                    vendor=v["vendor"],
                    prediction=v["prediction"],
                    reference=v["reference"],
                    spacing_mm=v["spacing_mm"],
                    scores=v["scores"],
                    threshold=threshold,
                )
            )
        plan = EvaluationPlan(
            fold_id=fold_id,
            bucket="val",  # measured as open; the record is labelled `test` below
            seed=int(cfg["run"]["seed"]),
            n_resamples=200,
            presence_voxel_threshold=threshold,
            mc_passes=passes,
            notes={
                "frames_per_chunk": 8,
                "checkpoint": "best.pt",
                "predictions_directory": folder.as_posix(),
                "synthetic": "sandbox for a dry run (SRS-107)",
            },
        )
        record = evaluate(plan, measured)
        record["bucket"] = "test"
        record["predictions"] = predictions.manifest(entries)
        path = root / "artifacts" / "runs" / RUN_DIRS[fold] / "audited" / "evaluation_test.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    manifest = root / data_cfg["paths"]["dicom_root"] / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    sealed.mark_sandbox(root / "artifacts")
    return by_fold


__all__ = ["build_final_bscans", "synthetic_volumes", "write_metaimage"]
