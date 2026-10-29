"""Audit of 2026-10-28, step 2: recompute every metric on the open `val` buckets independently.

Traces to: SRS-103. Its independent half is verified by TC-152. Run by the author on
2026-10-29 on the tree that merges `hd95-results` into `images`: 21 volumes, no difference
from the pipeline or from the stored records (`docs/13`). It mirrors the evaluation glue as it
stood then; it writes nothing under `docs/`.

For each fold's open `val` bucket (never a sealed one: `sealed.require_unsealed` is called
with no unlock, so a sealed bucket is refused), it:

1. **Predicts exactly as the evaluation does**: the glue of `scripts/05_evaluate.py`
   (lines 177-222) mirrored, its own `predict_volume` reused, each volume reseeded from
   `(seed, subject)` (SRS-091), so the prediction is the one the pipeline measures.
2. **Measures with the pipeline**: `measure_volume`, the current code.
3. **Measures independently**, sharing no code with the project's reader or metrics: its own
   MetaImage parse of `reference.mhd` and of the spacing, Dice from counts, mm3 from the
   header's three spacings, and **HD95 by a different algorithm**, surface points in
   millimetres and a KD-tree rather than a distance transform.
4. **Compares** the two per volume and class, and both with the stored `val` record.
5. **Runs the oracle on the real references**: each reference put through the chain and back
   with no model, measured independently, giving the round trip's Dice and HD95 ceiling and
   the signed axial shift of its edges on real anatomy (audit step 1).

Writes numbers only, to `artifacts/audit/crosscheck_val.json`; no mask, image or pixel value
is saved or printed. GPU, roughly the duration of the three `val` evaluations: **launched by
the author from an interactive terminal** (CLAUDE.md, `docs/07` §17.8).

Usage:
    python scripts/13_crosscheck_val.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

REPO = Path(__file__).resolve().parents[1]
RUNS = REPO / "artifacts" / "runs"
OUTPUT = REPO / "artifacts" / "audit" / "crosscheck_val.json"
FOLDS = {
    "cirrus": "cirrus_holdout_stage2",
    "spectralis": "spectralis_holdout_stage3",
    "topcon": "topcon_holdout_stage3",
}
# The stored val records. Cirrus's is from the docs/07 section 17.12 chain (HD95 corrected);
# spectralis and topcon val were not re-run there, so their HD95 is on the wrong axes and only
# their Dice and voxel counts are compared.
STORED = {
    "cirrus": ("corrected_hd95/evaluation_val_seeded_a.json", True),
    "spectralis": ("corrected/evaluation_val.json", False),
    "topcon": ("corrected/evaluation_val.json", False),
}
CLASSES = ("IRF", "SRF", "PED")
ELEMENT = {"MET_UCHAR": "u1", "MET_CHAR": "i1", "MET_USHORT": "u2", "MET_SHORT": "i2"}


# --- independent implementation: reading -------------------------------------------------


def independent_header(path: Path) -> dict:
    fields = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip()
    return fields


def independent_reference(subject_dir: Path):
    """The reference labels as (B-scans, rows, columns) and the per-axis spacing for that order.

    MetaImage stores x fastest and gives DimSize and ElementSpacing as (x, y, z); for RETOUCH
    x is lateral, y axial, z the B-scan index. So the array is (z, y, x) and its per-axis
    spacing is (z, y, x) of ElementSpacing.
    """
    header = independent_header(subject_dir / "reference.mhd")
    x, y, z = (int(v) for v in header["DimSize"].split())
    sx, sy, sz = (float(v) for v in header["ElementSpacing"].split())
    order = ">" if header.get("BinaryDataByteOrderMSB", "False").lower() == "true" else "<"
    raw = np.fromfile(
        subject_dir / header["ElementDataFile"], dtype=order + ELEMENT[header["ElementType"]]
    )
    assert raw.size == x * y * z, f"{subject_dir}: payload does not match DimSize"
    return raw.reshape(z, y, x), (sz, sy, sx)


# --- independent implementation: metrics ---------------------------------------------------


def independent_dice(p: np.ndarray, r: np.ndarray) -> float:
    total = int(p.sum()) + int(r.sum())
    return 1.0 if total == 0 else 2.0 * int((p & r).sum()) / total


def boundary(mask: np.ndarray) -> np.ndarray:
    """Mask voxels with a face neighbour outside the mask; outside the array counts as outside."""
    padded = np.pad(mask, 1, constant_values=False)
    interior = np.ones_like(mask)
    for axis in range(3):
        for step in (-1, 1):
            interior &= np.roll(padded, step, axis=axis)[1:-1, 1:-1, 1:-1]
    return mask & ~interior


def independent_hd95(p: np.ndarray, r: np.ndarray, per_axis_mm) -> float:
    """Max of the two directed 95th percentiles of surface-to-surface distance, in mm.

    0 when both are empty and NaN when exactly one is, the definitions SRS-032 and the
    pipeline state. The percentile is numpy's default (linear), the convention the
    pipeline uses; a different convention would be a different estimator, not a cross-check.
    """
    if not p.any() and not r.any():
        return 0.0
    if not p.any() or not r.any():
        return float("nan")
    scale = np.asarray(per_axis_mm, dtype=float)
    pts_p = np.argwhere(boundary(p)) * scale
    pts_r = np.argwhere(boundary(r)) * scale
    forward = np.percentile(cKDTree(pts_r).query(pts_p)[0], 95)
    backward = np.percentile(cKDTree(pts_p).query(pts_r)[0], 95)
    return float(max(forward, backward))


def independent_measure(prediction, reference, per_axis_mm) -> dict:
    voxel = per_axis_mm[0] * per_axis_mm[1] * per_axis_mm[2]
    out = {}
    for index, name in enumerate(CLASSES, start=1):
        p, r = prediction == index, reference == index
        out[name] = {
            "dice": independent_dice(p, r),
            "hd95": independent_hd95(p, r, per_axis_mm),
            "predicted_voxels": int(p.sum()),
            "reference_voxels": int(r.sum()),
            "predicted_mm3": int(p.sum()) * voxel,
            "reference_mm3": int(r.sum()) * voxel,
        }
    return out


def edge_shift(prediction, reference, index) -> tuple[float | None, float | None]:
    """Mean signed axial offset, in native rows, of predicted against reference top and bottom
    edges, over A-scans where both contain the class; positive means deeper."""
    p, r = prediction == index, reference == index
    rows = np.arange(p.shape[1])[None, :, None]
    both = p.any(1) & r.any(1)
    if not both.any():
        return None, None
    top = np.where(p, rows, 10**9).min(1) - np.where(r, rows, 10**9).min(1)
    bottom = np.where(p, rows, -1).max(1) - np.where(r, rows, -1).max(1)
    return float(top[both].mean()), float(bottom[both].mean())


# --- comparison ----------------------------------------------------------------------------


def same(a, b, rel=0.0, abs_tol=0.0) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, float) and math.isnan(a):
        return isinstance(b, float) and math.isnan(b)
    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_tol) if (rel or abs_tol) else a == b


def compare(pipeline: dict, independent: dict) -> list[str]:
    """Per class: Dice and voxel counts exactly, mm3 to 1e-12 relative, HD95 to 1e-9 mm."""
    found = []
    for name in CLASSES:
        p, i = pipeline[name], independent[name]
        for key in ("dice", "predicted_voxels", "reference_voxels"):
            if not same(p[key], i[key]):
                found.append(f"{name} {key}: pipeline {p[key]!r}, independent {i[key]!r}")
        for key in ("predicted_mm3", "reference_mm3"):
            if not same(p[key], i[key], rel=1e-12):
                found.append(f"{name} {key}: pipeline {p[key]!r}, independent {i[key]!r}")
        if not same(p["hd95"], i["hd95"], abs_tol=1e-9):
            found.append(f"{name} hd95: pipeline {p['hd95']!r}, independent {i['hd95']!r}")
    return found


def pipeline_values(seg: list[dict]) -> dict:
    out = {}
    for name in CLASSES:
        rows = {r["metric"]: r for r in seg if r["fluid_class"] == name}
        out[name] = {
            "dice": rows["dice"]["value"],
            "hd95": rows["hd95"]["value"],
            "predicted_voxels": rows["volume_mm3_predicted"]["voxels"],
            "reference_voxels": rows["volume_mm3_reference"]["voxels"],
            "predicted_mm3": rows["volume_mm3_predicted"]["value"],
            "reference_mm3": rows["volume_mm3_reference"]["value"],
        }
    return out


def predict_both_scores(mc_dropout_predict, model, frames, passes, chunk, top, rows):
    """`05_evaluate.predict_volume`, mirrored call for call, also scoring the native region.

    The recorded score is each class's highest mean probability over the padded frame
    (05_evaluate.py lines 124-127); presence is counted on the cropped native grid. The second
    score takes the maximum over the prepared rows that invert to native ones, `top` to
    `top + rows`, so the two views can be compared (independent review, R3).
    """
    import torch

    labels, padded, native = [], np.zeros(len(CLASSES)), np.zeros(len(CLASSES))
    for start in range(0, frames.shape[0], chunk):
        block = torch.as_tensor(frames[start : start + chunk], dtype=torch.float32)
        mean, _std = mc_dropout_predict(model, block.unsqueeze(1).to("cuda"), passes)
        labels.append(mean.argmax(axis=1).astype(np.uint8))
        for i in range(len(CLASSES)):
            padded[i] = max(padded[i], float(mean[:, i + 1].max()))
            native[i] = max(native[i], float(mean[:, i + 1, top : top + rows].max()))
        del block
        torch.cuda.empty_cache()
    scores = {n: (float(padded[i]), float(native[i])) for i, n in enumerate(CLASSES)}
    return np.concatenate(labels, axis=0), scores


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# --- run -----------------------------------------------------------------------------------


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folds", nargs="+", default=list(FOLDS), choices=list(FOLDS))
    parser.add_argument("--frames-per-chunk", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None, help="first N volumes, smoke run only")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; this audit never overwrites a result")
    import torch
    import yaml

    from ocuval.data.splits import load as load_split
    from ocuval.data.transforms import (
        axial_target,
        eval_transforms,
        invert_axial_resample,
        resampled_height,
    )
    from ocuval.eval import sealed
    from ocuval.eval.pipeline import assert_spacing_unchanged, measure_volume
    from ocuval.io.retouch_reader import read_volume
    from ocuval.models.seg_unet import build_model, load_verified
    from ocuval.models.uncertainty import mc_dropout_predict, reseed_for_volume
    from ocuval.runs import load_manifest, manifest_path, source_record
    from ocuval.training.checkpoint import request_determinism

    if not torch.cuda.is_available():
        raise SystemExit("needs the GPU: the stored val records were measured on it")
    cfg = yaml.safe_load((REPO / "configs/train_seg.yaml").read_text(encoding="utf-8"))
    data_cfg = yaml.safe_load((REPO / "configs/data.yaml").read_text(encoding="utf-8"))
    seed = int(cfg["run"]["seed"])
    request_determinism(seed)  # before the first CUDA context, as 05_evaluate does
    manifest = {row["patient_id"]: row for row in load_manifest(manifest_path(data_cfg))}
    chain = eval_transforms(cfg)
    target = axial_target(cfg)
    passes = int(cfg["inference"]["mc_dropout_passes"])

    result = {"source": source_record(), "folds": {}}
    for fold in args.folds:
        run_dir = RUNS / FOLDS[fold]
        fold_id = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["fold_id"]
        split = load_split(Path(data_cfg["paths"]["splits_root"]) / f"{fold_id}.json")
        sealed.require_unsealed("val", None, fold_id=fold_id)  # open bucket; sealed is refused
        stored_path, stored_hd95 = STORED[fold]
        stored = json.loads((run_dir / stored_path).read_text(encoding="utf-8"))
        stored_rows = {(r["patient_id"], r["fluid_class"]): r for r in stored["per_volume"]}
        model = build_model(cfg).to("cuda")
        load_verified(run_dir / "best.pt", model, map_location="cuda", restore_rng=False)
        subjects = list(split.val)[: args.limit] if args.limit else list(split.val)
        volumes = []
        for subject in subjects:
            row = manifest[subject]
            native = read_volume(Path(row["source_path"]), row["vendor"])
            reference = np.asarray(native.label_array)
            recorded = assert_spacing_unchanged(native.spacing_mm, row["spacing_mm"], subject)
            prepared, oracle_labels = [], []
            for index in range(native.pixel_array.shape[0]):
                sample = chain({
                    "image": native.pixel_array[index], "label": reference[index],
                    "intensity_window": row["intensity_window"],
                    "spacing_mm": row["spacing_mm"], "vendor": row["vendor"],
                })  # fmt: skip
                prepared.append(np.asarray(sample["image"]).squeeze())
                oracle_labels.append(np.asarray(sample["label"]).squeeze().astype(np.uint8))
            reseed_for_volume(seed, subject)
            shape2d = (reference.shape[1], reference.shape[2])
            content = resampled_height(shape2d[0], float(row["spacing_mm"][0]), target)
            frames = np.stack(prepared)
            top = (frames.shape[1] - content) // 2
            labels, scores = predict_both_scores(
                mc_dropout_predict, model, frames, passes, args.frames_per_chunk, top, content
            )
            prediction = invert_axial_resample(
                labels, tuple(row["spacing_mm"]), shape2d, target_axial_mm=target
            )
            prediction = np.asarray(prediction).astype(np.uint8).reshape(reference.shape)
            oracle = invert_axial_resample(
                np.stack(oracle_labels), tuple(row["spacing_mm"]), shape2d, target_axial_mm=target
            )
            oracle = np.asarray(oracle).astype(np.uint8).reshape(reference.shape)

            pipe = pipeline_values(measure_volume(prediction, reference, recorded))
            ind_reference, per_axis = independent_reference(Path(row["source_path"]))
            indep = independent_measure(prediction, ind_reference, per_axis)
            differences = compare(pipe, indep)
            if not np.array_equal(ind_reference, reference):
                differences.append("the independently read reference differs from the pipeline's")
            versus_stored = []
            for name in CLASSES:
                s = stored_rows[(subject, name)]
                for key in ("dice", "predicted_voxels", "reference_voxels"):
                    if not same(s[key], pipe[name][key]):
                        versus_stored.append(
                            f"{name} {key}: stored {s[key]!r}, now {pipe[name][key]!r}"
                        )
                if stored_hd95 and not same(s["hd95"], pipe[name]["hd95"], abs_tol=1e-9):
                    versus_stored.append(
                        f"{name} hd95: stored {s['hd95']!r}, now {pipe[name]['hd95']!r}"
                    )
                if not same(s["score"], scores[name][0]):  # verifies the mirrored prediction loop
                    versus_stored.append(
                        f"{name} score: stored {s['score']!r}, now {scores[name][0]!r}"
                    )
            oracle_measures = independent_measure(oracle, ind_reference, per_axis)
            for index, name in enumerate(CLASSES, start=1):
                oracle_measures[name]["edge_shift_rows"] = edge_shift(oracle, ind_reference, index)
            volumes.append({
                "subject": subject, "vendor": row["vendor"], "pipeline": pipe,
                "independent": indep, "pipeline_vs_independent": differences,
                "pipeline_vs_stored": versus_stored, "oracle": oracle_measures,
                "score_padded_vs_native": scores, "reference_present": {
                    n: bool(indep[n]["reference_voxels"] > 0) for n in CLASSES},
            })  # fmt: skip
            print(f"  {fold}: volume {len(volumes)}/{len(subjects)}: "
                  f"{len(differences)} pipeline/independent, {len(versus_stored)} stored "
                  f"difference(s)", flush=True)  # fmt: skip
        result["folds"][fold] = {"stored_record": stored_path, "volumes": volumes}
        del model
        torch.cuda.empty_cache()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    n = sum(len(f["volumes"]) for f in result["folds"].values())
    d1 = sum(
        len(v["pipeline_vs_independent"]) for f in result["folds"].values() for v in f["volumes"]
    )
    d2 = sum(len(v["pipeline_vs_stored"]) for f in result["folds"].values() for v in f["volumes"])
    print(f"CROSSCHECK END: {n} volumes; {d1} pipeline/independent and {d2} stored difference(s); "
          f"written to {args.output}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
