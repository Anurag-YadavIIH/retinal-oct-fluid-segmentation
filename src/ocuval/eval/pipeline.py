"""The evaluation pipeline, exactly as pre-registered in `docs/07` §17.

Traces to: SRS-032, SRS-033, SRS-034, SRS-050, SRS-051, SRS-052, SRS-053, SRS-057,
SRS-074, SRS-087, SRS-088
Verifies: TC-055, TC-056, TC-065, TC-066, TC-067, TC-073, TC-124, TC-125

The protocol was committed before any Stage 2 training started, and this module implements
it rather than interpreting it. Four properties are structural here, not conventions:

**1. The split is gated.** Every bucket passes through `sealed.require_unsealed` before a
record is read, so reaching the test split takes an explicit reasoned `Unlock` that is
logged. §17.1 permits one evaluation; §17.5 requires the count; `sealed.py` supplies it.

**2. Measurement happens in native geometry.** A prediction is produced on the resampled
grid and inverted back with `invert_axial_resample` before any metric touches it (SRS-074),
and the spacing used is asserted bit-identical to the spacing recorded at ingestion
(SRS-057). HD95 is a distance: on a resampled grid it would report millimetres the
acquisition never had. Because the three vendors' native axial spacings differ, measuring
on the common grid would also make the per-vendor comparison itself an artefact of
preprocessing -- corrupting the headline.

**3. Detection is a second view of one model, not a second model** (SRS-050). Presence
comes from the predicted voxel count against a configured threshold (SRS-051); the AUROC
score comes from the MC-dropout mean probability (SRS-052). No classifier is trained and no
forward pass happens beyond the MC-dropout passes.

**4. Intervals are patient-level** (SRS-087). Everything aggregates through
`subgroup.estimate`, which resamples patients and reports `n` in patients with the unit
named.

**Volume-level, not frame-level, is the unit of a reported metric.** Frames are how the
network sees the data; a clinician sees a volume, SRS-059's volumes are per acquisition,
and HD95 over a single B-scan measures a 2-D distance that is not the quantity `docs/10`
reports. So frames are assembled back into volumes before anything is measured.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from ocuval.eval import sealed, subgroup
from ocuval.eval.metrics import auroc, dice, hd95, sensitivity_specificity, volume_mm3

CLASS_NAMES = ("IRF", "SRF", "PED")
SEGMENTATION_METRICS = ("dice", "hd95")


@dataclass
class EvaluationPlan:
    """Everything fixed before the run, so nothing is chosen while results are visible."""

    fold_id: str
    bucket: str
    seed: int
    n_resamples: int = 2000
    alpha: float = 0.05
    presence_voxel_threshold: int = 10
    mc_passes: int = 20
    unlock: sealed.Unlock | None = None
    classes: tuple[str, ...] = CLASS_NAMES
    notes: dict[str, Any] = field(default_factory=dict)


def assert_spacing_unchanged(used: Sequence[float], recorded: Sequence[float], sample_id: str):
    """SRS-057: the spacing a measurement used is bit-identical to the ingested spacing.

    Compared with `==` on floats, intentionally. The requirement says bit-identical, and a
    tolerance here would admit exactly the failure it exists to catch: a spacing that
    survived a round trip through a resample and came back *almost* right would give volumes
    wrong by a few percent while every mask looked correct (HAZ-012).
    """
    u, r = tuple(float(x) for x in used), tuple(float(x) for x in recorded)
    if u != r:
        raise ValueError(
            f"{sample_id}: spacing used for measurement {u} is not bit-identical to the "
            f"spacing recorded at ingestion {r} (SRS-057). Aborting before a volume is "
            f"emitted."
        )
    return u


def measure_volume(
    prediction: np.ndarray,
    reference: np.ndarray,
    spacing: Sequence[float],
    *,
    classes: Sequence[str] = CLASS_NAMES,
) -> list[dict]:
    """Per-class segmentation metrics for one volume, in native geometry.

    `prediction` and `reference` are integer label volumes already on the native grid.
    Returns one row per class per metric, which is the shape `subgroup.by_vendor` consumes.
    """
    if prediction.shape != reference.shape:
        raise ValueError(f"prediction {prediction.shape} and reference {reference.shape} differ")
    rows = []
    for index, name in enumerate(classes, start=1):
        p = prediction == index
        r = reference == index
        rows.append({"fluid_class": name, "metric": "dice", "value": dice(p, r)})
        rows.append({"fluid_class": name, "metric": "hd95", "value": hd95(p, r, tuple(spacing))})
        predicted_mm3, predicted_voxels, _ = volume_mm3(p, tuple(spacing))
        reference_mm3, reference_voxels, _ = volume_mm3(r, tuple(spacing))
        rows.append(
            {
                "fluid_class": name,
                "metric": "volume_mm3_predicted",
                "value": predicted_mm3,
                "voxels": predicted_voxels,
            }
        )
        rows.append(
            {
                "fluid_class": name,
                "metric": "volume_mm3_reference",
                "value": reference_mm3,
                "voxels": reference_voxels,
            }
        )
    return rows


def detection_rows(
    predicted_voxels: dict[str, int],
    reference_voxels: dict[str, int],
    mean_probability: dict[str, float],
    *,
    threshold: int,
) -> list[dict]:
    """Volume-level presence and score for one volume, derived from the segmentation.

    SRS-050: derived from the same model's output, never a separate classifier. SRS-051:
    presence is `predicted voxel count > threshold`, the threshold read from configuration
    and never hard-coded. SRS-052: the continuous score is the MC-dropout mean probability.

    A class truly present with zero predicted voxels is a miss, not a missing value --
    which is why presence is a comparison and not a `None`.
    """
    rows = []
    for name in sorted(reference_voxels):
        rows.append(
            {
                "fluid_class": name,
                "metric": "detection",
                "predicted_present": bool(predicted_voxels.get(name, 0) > threshold),
                "reference_present": bool(reference_voxels[name] > 0),
                "score": float(mean_probability.get(name, float("nan"))),
                "predicted_voxels": int(predicted_voxels.get(name, 0)),
                "threshold": int(threshold),
            }
        )
    return rows


def aggregate_detection(rows: Sequence[dict], *, seed: int, n_resamples: int, alpha: float):
    """Sensitivity, specificity and AUROC per class and per vendor (SRS-053).

    Sensitivity and specificity are computed over the pooled confusion counts of each
    subgroup and then given a patient-level interval over the per-volume indicators, so the
    point estimate and its interval describe the same quantity.

    AUROC gets **no interval here**, and that is stated rather than silently omitted: a
    cluster bootstrap of a rank statistic resamples patients whose volumes are then ranked
    against each other, which is defensible but is a different estimator from the one the
    point value reports. Doing it properly is a pre-registered change, not an inline choice.
    """
    out: dict = {}
    vendors = sorted({r["vendor"] for r in rows})
    for vendor in [*vendors, "all_vendors"]:
        selected = rows if vendor == "all_vendors" else [r for r in rows if r["vendor"] == vendor]
        out[vendor] = {}
        for name in sorted({r["fluid_class"] for r in selected}):
            per_class = [r for r in selected if r["fluid_class"] == name]
            truth = np.array([r["reference_present"] for r in per_class], dtype=bool)
            guess = np.array([r["predicted_present"] for r in per_class], dtype=bool)
            scores = np.array([r["score"] for r in per_class], dtype=float)
            sens, spec = sensitivity_specificity(guess, truth)

            positives = [r for r in per_class if r["reference_present"]]
            negatives = [r for r in per_class if not r["reference_present"]]
            entry = {
                "sensitivity": _rate(positives, True, seed, n_resamples, alpha, sens),
                "specificity": _rate(negatives, False, seed, n_resamples, alpha, spec),
                "auroc": {
                    "value": auroc(scores, truth),
                    "n": int(len({r["patient_id"] for r in per_class})),
                    "n_unit": subgroup.UNIT,
                    "n_volumes": len(per_class),
                    "positives": int(truth.sum()),
                    "negatives": int((~truth).sum()),
                    "interval": None,
                    "interval_note": (
                        "no interval: a cluster bootstrap of a rank statistic is a "
                        "different estimator from the point value and is a pre-registered "
                        "change, not an inline choice"
                    ),
                },
            }
            out[vendor][name] = entry
    return out


def _rate(subset, want_positive: bool, seed: int, n_resamples: int, alpha: float, point: float):
    """Interval for a rate over the volumes that define its denominator."""
    if not subset:
        return {
            "value": point,
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "n": 0,
            "n_unit": subgroup.UNIT,
            "n_volumes": 0,
            "note": "empty denominator; a rate over no cases is undefined, not zero",
        }
    # Both rates are "the prediction agreed with the truth on this subset": sensitivity over
    # the truly-present volumes, specificity over the truly-absent ones. One expression, so
    # the two cannot drift apart.
    correct = [float(bool(r["predicted_present"]) == want_positive) for r in subset]
    out = subgroup.estimate(
        correct,
        [r["patient_id"] for r in subset],
        seed=seed,
        n_resamples=n_resamples,
        alpha=alpha,
    )
    out["value"] = point  # pooled point estimate; the interval is the resampled spread
    out["n_volumes"] = len(subset)
    return out


def evaluate(
    plan: EvaluationPlan,
    volumes: Sequence[dict],
    *,
    artifacts_root: Path | None = None,
) -> dict:
    """Run the pre-registered evaluation over already-measured volumes.

    `volumes` is a sequence of dicts, one per acquisition, each carrying `patient_id`,
    `vendor`, `sample_id`, `segmentation` (the rows from `measure_volume`) and `detection`
    (the rows from `detection_rows`). Inference and inversion happen upstream; this function
    is the part that must be auditable without a GPU, so it takes measurements rather than
    tensors.
    """
    sealed.require_unsealed(
        plan.bucket, plan.unlock, fold_id=plan.fold_id, root=artifacts_root
    )

    seg_rows, det_rows = [], []
    for volume in volumes:
        for row in volume["segmentation"]:
            seg_rows.append(
                {
                    **row,
                    "patient_id": volume["patient_id"],
                    "vendor": volume["vendor"],
                    "sample_id": volume["sample_id"],
                    "seed": plan.seed,
                }
            )
        for row in volume.get("detection", []):
            det_rows.append(
                {**row, "patient_id": volume["patient_id"], "vendor": volume["vendor"]}
            )

    reportable = [r for r in seg_rows if r["metric"] in SEGMENTATION_METRICS]
    segmentation = subgroup.by_vendor(reportable)
    detection = aggregate_detection(
        det_rows, seed=plan.seed, n_resamples=plan.n_resamples, alpha=plan.alpha
    )

    patients = sorted({v["patient_id"] for v in volumes})
    return {
        "protocol": "docs/07 §17",
        "utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "fold_id": plan.fold_id,
        "bucket": plan.bucket,
        "sealed": plan.bucket in sealed.SEALED_BUCKETS,
        "bucket_access_count": sealed.access_count(
            plan.bucket, fold_id=plan.fold_id, root=artifacts_root
        ),
        "unit_of_measurement": "volume",
        "n_patients": len(patients),
        "n_volumes": len(volumes),
        "vendors": sorted({v["vendor"] for v in volumes}),
        "bootstrap": {
            "n_resamples": plan.n_resamples,
            "alpha": plan.alpha,
            "seed": plan.seed,
            "resampling_unit": subgroup.UNIT,
        },
        "presence_voxel_threshold": plan.presence_voxel_threshold,
        "mc_passes": plan.mc_passes,
        "segmentation": segmentation,
        "detection": detection,
        "notes": plan.notes,
    }


def write_record(result: dict, destination: Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


__all__ = [
    "CLASS_NAMES",
    "SEGMENTATION_METRICS",
    "EvaluationPlan",
    "aggregate_detection",
    "assert_spacing_unchanged",
    "detection_rows",
    "evaluate",
    "measure_volume",
    "write_record",
]
