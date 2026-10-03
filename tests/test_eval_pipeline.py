"""Verification of the §17 evaluation pipeline.

Covers TC-124 (patient-level bootstrap), TC-125 (the seal), TC-055/TC-056 (MC-dropout),
TC-065/TC-066/TC-067 (detection derived from segmentation), TC-073 (spacing assertion).

Traces to: SRS-029, SRS-030, SRS-050..SRS-053, SRS-057, SRS-087, SRS-088

These are pure-function tests over small arrays wherever possible. The pipeline's job is to
turn measurements into a reportable record, and that part must be auditable without a GPU --
the same argument that keeps `eval/metrics.py` in numpy.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ocuval.eval import sealed, subgroup
from ocuval.eval.metrics import auroc, bootstrap_ci, bootstrap_ci_grouped
from ocuval.eval.pipeline import (
    EvaluationPlan,
    aggregate_detection,
    assert_spacing_unchanged,
    detection_rows,
    evaluate,
    measure_volume,
)

SEED = 20260916


# --- TC-124: the bootstrap resamples patients ------------------------------------------


def clustered(n_patients=20, per_patient=10, spread=0.1, noise=0.002, seed=1):
    """Values that are nearly constant within a patient and vary between patients.

    This is the shape real data has -- neighbouring B-scans of one eye are close to
    repeated measurements -- and it is the shape that makes the two bootstraps disagree.
    """
    rng = np.random.default_rng(seed)
    groups = np.repeat(np.arange(n_patients), per_patient)
    values = np.repeat(rng.normal(0.7, spread, n_patients), per_patient)
    return values + rng.normal(0, noise, values.size), groups


def test_TC_124_n_is_the_number_of_patients_not_measurements():
    """SRS-087. The reported `n` is the unit the interval describes."""
    values, groups = clustered()
    est = bootstrap_ci_grouped(values, groups, seed=SEED)
    assert est.n == 20, f"n={est.n}; it must count patients, not the 200 measurements"
    assert bootstrap_ci(values, seed=SEED).n == 200, "the ungrouped version counts values"


def test_TC_124_the_patient_level_interval_is_wider_on_clustered_data():
    """The whole reason SRS-087 exists, asserted as a measurement rather than argued.

    Resampling measurements independently treats correlated frames as independent evidence
    and narrows the interval by roughly sqrt(cluster size) -- in the direction that
    overstates certainty. With a cluster size of 10 the expected ratio is about 3.2.
    """
    values, groups = clustered(per_patient=10)
    naive = bootstrap_ci(values, seed=SEED)
    patient = bootstrap_ci_grouped(values, groups, seed=SEED)
    ratio = (patient.ci_high - patient.ci_low) / (naive.ci_high - naive.ci_low)
    assert ratio > 2.0, (
        f"the patient-level interval is only {ratio:.2f}x the naive one. On data this "
        f"clustered it should be ~3x; a ratio near 1 means the grouping is being ignored."
    )


def test_TC_124_grouping_is_irrelevant_when_every_patient_has_one_measurement():
    """A negative control on the mechanism: with no clustering the two must nearly agree.

    If the grouped version were wider here too, its extra width would be an artefact of the
    implementation rather than of the correlation it exists to capture.
    """
    rng = np.random.default_rng(7)
    values = rng.normal(0.7, 0.1, 60)
    groups = np.arange(60)
    naive = bootstrap_ci(values, seed=SEED)
    patient = bootstrap_ci_grouped(values, groups, seed=SEED)
    ratio = (patient.ci_high - patient.ci_low) / (naive.ci_high - naive.ci_low)
    assert 0.8 < ratio < 1.25, f"ratio {ratio:.2f} on unclustered data; expected about 1"


def test_TC_124_is_reproducible_from_the_seed():
    values, groups = clustered()
    a = bootstrap_ci_grouped(values, groups, seed=SEED)
    b = bootstrap_ci_grouped(values, groups, seed=SEED)
    c = bootstrap_ci_grouped(values, groups, seed=SEED + 1)
    assert (a.ci_low, a.ci_high) == (b.ci_low, b.ci_high), "same seed gave a different interval"
    assert (a.ci_low, a.ci_high) != (c.ci_low, c.ci_high), "the seed changes nothing"


def test_TC_124_nan_values_are_dropped_and_do_not_count_as_evidence():
    values = np.array([0.5, np.nan, 0.6, 0.7])
    groups = np.array(["a", "a", "b", "c"])
    est = bootstrap_ci_grouped(values, groups, seed=SEED)
    assert est.n == 3, f"n={est.n}; a patient whose only value is NaN must not count"
    assert not np.isnan(est.value)


def test_TC_124_every_estimate_carries_its_unit():
    """SRS-087 and `docs/07` §17.2: `n` without its unit is a misreportable number."""
    values, groups = clustered()
    out = subgroup.estimate(values, groups, seed=SEED)
    assert out["n_unit"] == "patients"
    assert out["n"] == 20
    assert out["n_measurements"] == 200
    assert out["bootstrap"] == {
        "n_resamples": 2000,
        "alpha": 0.05,
        "seed": SEED,
        "unit": "patients",
    }


# --- TC-125: the seal ------------------------------------------------------------------


@pytest.mark.parametrize("bucket", sorted(sealed.SEALED_BUCKETS))
def test_TC_125_a_sealed_bucket_is_refused_without_an_unlock(bucket):
    with pytest.raises(sealed.SealedSplitError, match="sealed"):
        sealed.require_unsealed(bucket)


def test_TC_125_the_open_bucket_needs_nothing():
    sealed.require_unsealed("val")


def test_TC_125_an_unlock_opens_one_bucket_only():
    unlock = sealed.Unlock(bucket="test", reason="r", approved_by="a")
    with pytest.raises(sealed.SealedSplitError, match="opens one bucket"):
        sealed.require_unsealed("in_domain_ref", unlock)


def test_TC_125_an_unlock_cannot_be_built_without_a_reason():
    for bad in ("", "   "):
        with pytest.raises(ValueError, match="must say something"):
            sealed.Unlock(bucket="test", reason=bad, approved_by="a")
        with pytest.raises(ValueError, match="must say something"):
            sealed.Unlock(bucket="test", reason="r", approved_by=bad)


def test_TC_125_access_is_logged_and_counted(tmp_path):
    """SRS-088's substance. `docs/07` §17.1 permits one evaluation; this is the count."""
    unlock = sealed.Unlock(bucket="test", reason="pre-registered one-time run", approved_by="AY")
    assert sealed.access_count("test", root=tmp_path) == 0
    sealed.require_unsealed("test", unlock, fold_id="cirrus_holdout", root=tmp_path)
    assert sealed.access_count("test", root=tmp_path) == 1

    entries = sealed.read_access_log(tmp_path)
    assert len(entries) == 1
    assert entries[0]["bucket"] == "test"
    assert entries[0]["fold_id"] == "cirrus_holdout"
    assert entries[0]["reason"] == "pre-registered one-time run"
    assert entries[0]["approved_by"] == "AY"
    assert entries[0]["prior_accesses"] == 0
    assert entries[0]["run_id"], "each entry must name the run that made it (SRS-088)"


def test_TC_125_a_genuinely_second_run_is_recorded_as_one(monkeypatch, tmp_path):
    """A second *run* must count and must say it was not the first.

    The run identifier is substituted here because a test shares one process with the code it
    exercises, so two runs cannot otherwise be simulated. That substitution is the only way to
    distinguish "two gate calls" from "two runs" in a single interpreter -- which is precisely
    the distinction the D6 defect failed to make.
    """
    unlock = sealed.Unlock(bucket="test", reason="first run", approved_by="AY")
    monkeypatch.setattr(sealed, "RUN_ID", "run-one")
    sealed.require_unsealed("test", unlock, fold_id="cirrus_holdout", root=tmp_path)
    assert sealed.access_count("test", root=tmp_path) == 1

    monkeypatch.setattr(sealed, "RUN_ID", "run-two")
    sealed.require_unsealed("test", unlock, fold_id="cirrus_holdout", root=tmp_path)
    assert sealed.access_count("test", root=tmp_path) == 2
    assert sealed.read_access_log(tmp_path)[1]["prior_accesses"] == 1, (
        "a second run must record that it was not the first; that record is the only thing "
        "that makes 'exactly once' checkable afterwards"
    )


def test_TC_125_one_run_counts_once_however_many_times_it_checks_the_seal(tmp_path):
    """SRS-088 as corrected (`docs/08` D6).

    A completed run checks the seal twice -- in `05_evaluate.py` before the split is read and
    in `pipeline.py` at aggregation -- and the count previously reported 2 for one run. The
    raw log still records both calls, because it is the primary evidence; the *count* is runs.
    """
    unlock = sealed.Unlock(bucket="test", reason="one run, two gates", approved_by="AY")
    sealed.require_unsealed("test", unlock, fold_id="f", root=tmp_path)
    sealed.require_unsealed("test", unlock, fold_id="f", root=tmp_path)

    assert sealed.gate_calls("test", root=tmp_path) == 2, "the raw log must keep both calls"
    assert (
        sealed.access_count("test", root=tmp_path) == 1
    ), "two gate calls from one process counted as two runs; that is the D6 defect"


def test_TC_125_a_count_is_not_gate_calls_halved(tmp_path):
    """The killed run logged ONE entry, so dividing by two would have counted it as half.

    This is why runs are identified rather than inferred from the number of calls.
    """
    unlock = sealed.Unlock(bucket="test", reason="r", approved_by="a")
    sealed.require_unsealed("test", unlock, root=tmp_path)  # a run that stops after one gate
    assert sealed.gate_calls("test", root=tmp_path) == 1
    assert (
        sealed.access_count("test", root=tmp_path) == 1
    ), "a run that was killed between the two gates must still count as one access"


def test_TC_125_entries_without_a_run_id_are_counted_individually(tmp_path):
    """Historical entries predate `run_id` and are deliberately over-counted.

    Inferring runs from timestamps would be a guess presented as a count. The raw log is kept
    so a reader can see the entries and the reasons that distinguish them, and `docs/08` D6
    states the true figure.
    """
    path = sealed.access_log_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"bucket": "test", "utc": "2026-10-01T12:58:29+00:00"})
        + "\n"
        + json.dumps({"bucket": "test", "utc": "2026-10-01T13:29:32+00:00"})
        + "\n",
        encoding="utf-8",
    )
    assert sealed.access_count("test", root=tmp_path) == 2


def test_TC_125_the_raw_log_is_never_rewritten(tmp_path):
    """SRS-088: correcting a count must never be done by editing the evidence."""
    unlock = sealed.Unlock(bucket="test", reason="r", approved_by="a")
    sealed.require_unsealed("test", unlock, root=tmp_path)
    before = sealed.access_log_path(tmp_path).read_text(encoding="utf-8")
    sealed.access_count("test", root=tmp_path)
    sealed.gate_calls("test", root=tmp_path)
    assert (
        sealed.access_log_path(tmp_path).read_text(encoding="utf-8") == before
    ), "reading the count altered the log; the log is evidence and is append-only"


def test_TC_125_the_log_survives_the_process(tmp_path):
    """Counted from the file, not from memory, or restarting would reset the count."""
    unlock = sealed.Unlock(bucket="test", reason="r", approved_by="a")
    sealed.require_unsealed("test", unlock, root=tmp_path)
    path = sealed.access_log_path(tmp_path)
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[0])["bucket"] == "test"


def test_TC_125_assert_only_unsealed_catches_a_sealed_bucket_in_a_list():
    sealed.assert_only_unsealed(["train", "val"])
    with pytest.raises(sealed.SealedSplitError, match="test"):
        sealed.assert_only_unsealed(["val", "test"])


def test_TC_125_the_pipeline_refuses_a_sealed_bucket(tmp_path):
    """The gate is wired into `evaluate`, not merely available beside it."""
    plan = EvaluationPlan(fold_id="cirrus_holdout", bucket="test", seed=SEED)
    with pytest.raises(sealed.SealedSplitError):
        evaluate(plan, [], artifacts_root=tmp_path)


# --- TC-073: the spacing assertion -----------------------------------------------------


def test_TC_073_matching_spacing_passes_and_is_returned():
    recorded = [0.001955, 0.011742, 0.046878]
    assert assert_spacing_unchanged(recorded, recorded, "TRAIN001") == tuple(recorded)


def test_TC_073_a_difference_in_the_last_digit_aborts():
    """SRS-057 says bit-identical, so the test uses a difference a tolerance would admit.

    A volume wrong only in its spacing looks entirely correct in the mask and to a grader
    (HAZ-012), which is why this compares exactly rather than with `isclose`.
    """
    recorded = [0.001955, 0.011742, 0.046878]
    used = [0.0019550000000001, 0.011742, 0.046878]
    with pytest.raises(ValueError, match="bit-identical"):
        assert_spacing_unchanged(used, recorded, "TRAIN001")


# --- TC-065 / TC-066 / TC-067: detection derived from the segmentation -----------------


def test_TC_065_presence_comes_from_the_predicted_voxel_count():
    """SRS-050: one model, two views. No separate classifier exists to consult."""
    rows = detection_rows(
        {"IRF": 50, "SRF": 0, "PED": 3},
        {"IRF": 40, "SRF": 10, "PED": 0},
        {"IRF": 0.9, "SRF": 0.2, "PED": 0.1},
        threshold=10,
    )
    by_class = {r["fluid_class"]: r for r in rows}
    assert by_class["IRF"]["predicted_present"] is True
    assert by_class["SRF"]["predicted_present"] is False, "0 voxels is absent"
    assert by_class["PED"]["predicted_present"] is False, "3 voxels is below the threshold of 10"
    assert by_class["SRF"]["reference_present"] is True, "a missed class is a miss, not missing"
    assert by_class["PED"]["reference_present"] is False


@pytest.mark.parametrize(("threshold", "expected"), [(1, True), (10, False), (100, False)])
def test_TC_066_the_threshold_is_read_and_actually_applied(threshold, expected):
    """SRS-051: the threshold comes from configuration and changes the answer.

    Parametrised because a threshold that is read but ignored would pass a single case.
    """
    rows = detection_rows({"IRF": 5}, {"IRF": 5}, {"IRF": 0.5}, threshold=threshold)
    assert rows[0]["predicted_present"] is expected
    assert rows[0]["threshold"] == threshold


def test_TC_066_the_shipped_config_declares_the_threshold():
    """A threshold hard-coded in the evaluator is one no run record can show."""
    import yaml

    repo_root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((repo_root / "configs" / "train_seg.yaml").read_text(encoding="utf-8"))
    assert isinstance(cfg["inference"]["presence_voxel_threshold"], int)


def test_TC_067_auroc_uses_the_score_and_not_the_thresholded_decision():
    """SRS-052: the continuous score is the MC-dropout mean probability.

    Built so that the thresholded decisions are uninformative while the scores rank
    perfectly: if AUROC were computed from `predicted_present` it would be 0.5 here.
    """
    rows = []
    for index in range(8):
        present = index >= 4
        rows.append(
            {
                "vendor": "spectralis",
                "patient_id": f"P{index}",
                "fluid_class": "IRF",
                "metric": "detection",
                "predicted_present": True,  # every decision identical, so uninformative
                "reference_present": present,
                "score": 0.1 * index,
                "predicted_voxels": 100,
                "threshold": 10,
            }
        )
    out = aggregate_detection(rows, seed=SEED, n_resamples=200, alpha=0.05)
    entry = out["spectralis"]["IRF"]
    assert entry["auroc"]["value"] == 1.0, "AUROC must come from the score, not the decision"
    assert entry["sensitivity"]["value"] == 1.0
    assert entry["specificity"]["value"] == 0.0
    assert entry["auroc"]["n_unit"] == "patients"


def test_TC_067_auroc_is_nan_for_a_single_class_subgroup():
    """Expected per vendor on the rarer classes. 0.5 would read as a measured coin flip."""
    assert np.isnan(auroc([0.1, 0.9], [1, 1]))
    assert np.isnan(auroc([0.1, 0.9], [0, 0]))


def test_TC_067_auroc_handles_ties_by_midrank():
    """MC-dropout probabilities tie readily: a class absent from every pass scores 0.0."""
    assert auroc([0.5, 0.5, 0.5, 0.5], [0, 0, 1, 1]) == 0.5
    assert auroc([0.0, 0.0, 1.0, 1.0], [0, 0, 1, 1]) == 1.0
    assert auroc([0.0, 1.0, 0.0, 1.0], [0, 0, 1, 1]) == 0.5


# --- the record the protocol requires --------------------------------------------------


def _voxels(rows, metric):
    return {r["fluid_class"]: r["voxels"] for r in rows if r["metric"] == metric}


def synthetic_volumes(n_patients=6):
    rng = np.random.default_rng(3)
    volumes = []
    for index in range(n_patients):
        vendor = "spectralis" if index % 2 else "topcon"
        prediction = np.zeros((4, 8, 8), dtype=np.uint8)
        reference = np.zeros((4, 8, 8), dtype=np.uint8)
        prediction[0, 1:4, 1:4] = 1
        reference[0, 1:5, 1:4] = 1
        prediction[1, 2:4, 2:5] = 2
        reference[1, 2:4, 2:5] = 2
        seg = measure_volume(prediction, reference, (0.004, 0.0117, 0.047))
        predicted = _voxels(seg, "volume_mm3_predicted")
        truth = _voxels(seg, "volume_mm3_reference")
        volumes.append(
            {
                "sample_id": f"uid-{index}",
                "patient_id": f"TRAIN{index:03d}",
                "vendor": vendor,
                "segmentation": seg,
                "detection": detection_rows(
                    predicted, truth, {k: float(rng.random()) for k in truth}, threshold=10
                ),
            }
        )
    return volumes


# --- TC-126: per-volume rows, from which every aggregate is recomputable ---------------


def varied_volumes(n_patients=10, seed=11):
    """Volumes whose masks differ, including the case `docs/07` §19.1 exists for.

    `synthetic_volumes` gives every volume identical masks, so an aggregate recomputed from
    its rows would match trivially. Here overlap varies per volume, some classes are absent
    from the reference, and some of those absent classes are predicted anyway -- the
    false-positive case that scores Dice 0.0 (metrics.py:104-117) and that the present/absent
    decomposition exists to separate out.
    """
    rng = np.random.default_rng(seed)
    volumes = []
    for index in range(n_patients):
        vendor = ("spectralis", "topcon")[index % 2]
        shape = (3, 16, 16)
        prediction = np.zeros(shape, dtype=np.uint8)
        reference = np.zeros(shape, dtype=np.uint8)
        for label in (1, 2, 3):
            if rng.random() < 0.6:  # class present in the reference
                a, b = rng.integers(0, 10, 2)
                reference[label - 1, a : a + 5, b : b + 5] = label
                shift = rng.integers(0, 3)
                prediction[label - 1, a + shift : a + shift + 5, b : b + 4] = label
            elif rng.random() < 0.7:  # absent, but predicted: a false positive
                prediction[label - 1, 0 : rng.integers(1, 4), 0:2] = label
        seg = measure_volume(prediction, reference, (0.004, 0.0117, 0.047))
        volumes.append(
            {
                "sample_id": f"uid-{index}",
                "patient_id": f"TRAIN{index:03d}",
                "vendor": vendor,
                "segmentation": seg,
                "detection": detection_rows(
                    _voxels(seg, "volume_mm3_predicted"),
                    _voxels(seg, "volume_mm3_reference"),
                    {k: float(rng.random()) for k in ("IRF", "SRF", "PED")},
                    threshold=10,
                ),
            }
        )
    return volumes


def test_TC_126_one_row_per_volume_per_class_with_every_required_field(tmp_path):
    volumes = varied_volumes()
    plan = EvaluationPlan(fold_id="f", bucket="val", seed=SEED, n_resamples=200)
    rows = evaluate(plan, volumes, artifacts_root=tmp_path)["per_volume"]
    assert len(rows) == len(volumes) * 3
    required = {
        "sample_id",
        "patient_id",
        "vendor",
        "fluid_class",
        "dice",
        "hd95",
        "reference_present",
        "reference_voxels",
        "predicted_voxels",
    }
    for row in rows:
        assert required <= set(row), f"missing {sorted(required - set(row))}"
    keys = {(r["sample_id"], r["fluid_class"]) for r in rows}
    assert len(keys) == len(rows), "a volume-class pair appears twice"


def test_TC_126_the_fixture_exercises_the_absent_but_predicted_case(tmp_path):
    """Vacuity guard: the cases the next tests depend on must actually occur."""
    plan = EvaluationPlan(fold_id="f", bucket="val", seed=SEED, n_resamples=200)
    rows = evaluate(plan, varied_volumes(), artifacts_root=tmp_path)["per_volume"]
    absent_predicted = [r for r in rows if not r["reference_present"] and r["predicted_voxels"]]
    assert absent_predicted, "no false-positive volume in the fixture; it tests nothing"
    assert {r["dice"] for r in absent_predicted} == {0.0}, "absent-but-predicted must score 0.0"
    assert any(r["reference_present"] for r in rows)
    assert {r["vendor"] for r in rows} == {"spectralis", "topcon"}


@pytest.mark.parametrize("metric", ["dice", "hd95"])
def test_TC_126_every_aggregate_is_recomputable_from_the_rows(tmp_path, metric):
    """The property the cirrus re-run will rely on: the summary and the rows cannot disagree.

    Each per-vendor and pooled per-class value is the mean over the rows' finite values, and
    must equal the reported aggregate **exactly** -- not approximately, since both are computed
    from the same floats and any difference would mean a second, divergent route.
    """
    plan = EvaluationPlan(fold_id="f", bucket="val", seed=SEED, n_resamples=200)
    result = evaluate(plan, varied_volumes(), artifacts_root=tmp_path)
    rows = result["per_volume"]
    scopes = {"all_vendors": rows} | {
        v: [r for r in rows if r["vendor"] == v] for v in result["vendors"]
    }
    compared = 0
    for scope, subset in scopes.items():
        block = (
            result["segmentation"]["all_vendors"]
            if scope == "all_vendors"
            else result["segmentation"]["by_vendor"][scope]
        )
        for fluid in ("IRF", "SRF", "PED"):
            values = [
                r[metric] for r in subset if r["fluid_class"] == fluid and r[metric] is not None
            ]
            finite = [v for v in values if not np.isnan(v)]
            reported = block[fluid][metric]
            if not finite:
                assert np.isnan(reported["value"])
                continue
            assert float(np.mean(finite)) == reported["value"], (
                f"{scope} {fluid} {metric}: rows give {np.mean(finite)!r}, record says "
                f"{reported['value']!r}"
            )
            assert (
                len(
                    {
                        r["patient_id"]
                        for r in subset
                        if r["fluid_class"] == fluid
                        and r[metric] is not None
                        and not np.isnan(r[metric])
                    }
                )
                == reported["n"]
            )
            compared += 1
    assert compared >= 6, f"only {compared} comparisons; the fixture is too thin"


def test_TC_126_reference_present_matches_the_detection_arm(tmp_path):
    """The present/absent strata must be the strata the detection metrics used."""
    volumes = varied_volumes()
    plan = EvaluationPlan(fold_id="f", bucket="val", seed=SEED, n_resamples=200)
    rows = evaluate(plan, volumes, artifacts_root=tmp_path)["per_volume"]
    detection = {
        (v["sample_id"], d["fluid_class"]): d["reference_present"]
        for v in volumes
        for d in v["detection"]
    }
    for row in rows:
        assert row["reference_present"] == detection[(row["sample_id"], row["fluid_class"])]


def test_TC_126_adding_the_rows_changes_no_aggregate(tmp_path):
    """The rows are a new field, never a new computation of the existing ones.

    The segmentation and detection blocks are recomputed here by the original route --
    `subgroup.by_vendor` and `aggregate_detection` on the same inputs, without
    `per_volume_rows` anywhere in the path -- and must equal what `evaluate` now emits.
    """
    volumes = varied_volumes()
    plan = EvaluationPlan(fold_id="f", bucket="val", seed=SEED, n_resamples=200)
    result = evaluate(plan, volumes, artifacts_root=tmp_path)

    seg = [
        {
            **r,
            "patient_id": v["patient_id"],
            "vendor": v["vendor"],
            "sample_id": v["sample_id"],
            "seed": SEED,
        }
        for v in volumes
        for r in v["segmentation"]
        if r["metric"] in ("dice", "hd95")
    ]
    det = [
        {**r, "patient_id": v["patient_id"], "vendor": v["vendor"]}
        for v in volumes
        for r in v["detection"]
    ]
    expected_seg = subgroup.by_vendor(seg)
    expected_det = aggregate_detection(det, seed=SEED, n_resamples=200, alpha=0.05)
    assert json.dumps(result["segmentation"], sort_keys=True, default=str) == json.dumps(
        expected_seg, sort_keys=True, default=str
    )
    assert json.dumps(result["detection"], sort_keys=True, default=str) == json.dumps(
        expected_det, sort_keys=True, default=str
    )


def test_the_record_carries_everything_section_17_5_requires(tmp_path):
    """`docs/07` §17.5 is a list of fields. This asserts the list, item by item."""
    plan = EvaluationPlan(fold_id="cirrus_holdout", bucket="val", seed=SEED, n_resamples=200)
    result = evaluate(plan, synthetic_volumes(), artifacts_root=tmp_path)

    assert result["bootstrap"]["resampling_unit"] == "patients"
    assert result["bootstrap"]["n_resamples"] == 200
    assert result["bootstrap"]["alpha"] == 0.05
    assert result["bootstrap"]["seed"] == SEED
    assert result["presence_voxel_threshold"] == 10
    assert result["unit_of_measurement"] == "volume"
    assert result["bucket_access_count"] == 0, "the open bucket is not an access to count"
    assert sorted(result["vendors"]) == ["spectralis", "topcon"]

    for vendor in result["vendors"]:
        for fluid in ("IRF", "SRF", "PED"):
            for metric in ("dice", "hd95"):
                entry = result["segmentation"]["by_vendor"][vendor][fluid][metric]
                assert entry["n_unit"] == "patients"
                assert {"value", "ci_low", "ci_high", "n"} <= set(entry)


def test_pooled_figures_sit_beside_the_per_vendor_ones_never_instead(tmp_path):
    """SRS-032's reasoning extended across vendors: a pooled number hides the variation."""
    plan = EvaluationPlan(fold_id="cirrus_holdout", bucket="val", seed=SEED, n_resamples=200)
    result = evaluate(plan, synthetic_volumes(), artifacts_root=tmp_path)
    assert "all_vendors" in result["segmentation"]
    assert set(result["segmentation"]["by_vendor"]) == {"spectralis", "topcon"}


def test_the_generalisation_gap_reports_no_interval_and_says_why():
    """Subtracting two independently bootstrapped intervals is not a confidence interval."""
    in_domain = {"IRF": {"dice": {"value": 0.70, "ci_low": 0.65, "ci_high": 0.75}}}
    held_out = {"IRF": {"dice": {"value": 0.50, "ci_low": 0.44, "ci_high": 0.56}}}
    gap = subgroup.generalisation_gap(in_domain, held_out)
    entry = gap["by_class"]["IRF"]["dice"]
    assert entry["gap"] == pytest.approx(0.20)
    assert entry["intervals_overlap"] is False
    assert "not a confidence interval" in gap["note"]
    assert "ci_low" not in entry, "the gap must not carry an interval of its own"


def test_a_varying_bootstrap_seed_across_rows_is_refused():
    """SRS-034: a resampling seed that varies by row makes the intervals irreproducible."""
    rows = [
        {
            "vendor": "a",
            "patient_id": "p",
            "fluid_class": "IRF",
            "metric": "dice",
            "value": 0.5,
            "seed": 1,
        },
        {
            "vendor": "a",
            "patient_id": "q",
            "fluid_class": "IRF",
            "metric": "dice",
            "value": 0.6,
            "seed": 2,
        },
    ]
    with pytest.raises(ValueError, match="exactly one bootstrap seed"):
        subgroup.by_vendor(rows)
