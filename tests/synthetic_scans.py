"""Synthetic scans and records for end-to-end tests of the chain scripts' real `main`.

**Synthetic only** (`docs/06` DMP-C12): nothing here reads RETOUCH. Each fold gets a few
volumes with a vendor's anisotropic spacing and, per volume, IRF present in both prediction and
reference, SRF predicted where the reference has none (a false positive above the presence
threshold) and PED empty in both, so every case the metrics and the section 21 rule treat
differently is present.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ocuval.eval import predictions
from ocuval.eval.pipeline import EvaluationPlan, evaluate
from ocuval.eval.report import RUN_DIRS

THRESHOLD = 10
PASSES = 20  # the configured value, which the B-scan script checks each record against
VENDOR = {"cirrus": "cirrus", "spectralis": "spectralis", "topcon": "topcon"}
SPACINGS = {  # (axial, lateral, separation), within docs/06 section 3.1.2's ranges
    "cirrus": (0.001955, 0.011742, 0.046878),
    "spectralis": (0.003872, 0.011406, 0.120774),
    "topcon": (0.002600, 0.011720, 0.046880),
}


def fold_volumes(fold: str, n: int = 3, first: int = 1) -> list[dict]:
    rng = np.random.default_rng(len(fold) * 100 + first)
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
                "vendor": VENDOR[fold],
                "prediction": prediction,
                "reference": reference,
                "image": (rng.random(shape) * 255).astype(np.uint8),
                "spacing_mm": SPACINGS[fold],
                "scores": {"IRF": float(rng.random()), "SRF": 0.6, "PED": 0.01},
            }
        )
    return out


def measured(volume: dict) -> dict:
    return predictions.measured_volume(
        sample_id=volume["sample_id"],
        patient_id=volume["patient_id"],
        vendor=volume["vendor"],
        prediction=volume["prediction"],
        reference=volume["reference"],
        spacing_mm=volume["spacing_mm"],
        scores=volume["scores"],
        threshold=THRESHOLD,
    )


def record_for(fold: str, volumes: list[dict], bucket: str = "test") -> dict:
    """A record as `05_evaluate.py` writes it, with the notes the B-scan script checks."""
    plan = EvaluationPlan(
        fold_id=f"{fold}_holdout",
        bucket="val",  # evaluated as open; the bucket field is set below
        seed=42,
        n_resamples=200,
        presence_voxel_threshold=THRESHOLD,
        mc_passes=PASSES,
        notes={"frames_per_chunk": 8, "checkpoint": "best.pt"},
    )
    record = evaluate(plan, [measured(v) for v in volumes])
    record["bucket"] = bucket
    return json.loads(json.dumps(record))


def write_held_out_records(root: Path, folder: str, by_fold: dict[str, list[dict]]) -> None:
    """`artifacts/runs/<run>/<folder>/evaluation_test.json` under `root`, for every fold."""
    for fold, volumes in by_fold.items():
        path = root / "artifacts" / "runs" / RUN_DIRS[fold] / folder / "evaluation_test.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record_for(fold, volumes)), encoding="utf-8")


def manifest_rows(by_fold: dict[str, list[dict]]) -> list[dict]:
    return [
        {"patient_id": v["patient_id"], "sample_id": v["sample_id"], "vendor": v["vendor"],
         "spacing_mm": list(v["spacing_mm"]), "source_path": v["patient_id"],
         "intensity_window": [0.0, 255.0]}
        for volumes in by_fold.values() for v in volumes
    ]  # fmt: skip


def all_folds() -> dict[str, list[dict]]:
    return {fold: fold_volumes(fold, first=1 + 10 * i) for i, fold in enumerate(VENDOR)}
