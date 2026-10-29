"""TC-154 — the final re-evaluation chain follows `docs/07` §17.13; its gate holds the population.

Traces to: SRS-105

**Arguments, the step plan, the gate and the pre-flight checks only. Nothing here executes the
chain**: no evaluation, no unlock, no read of the access log. The gate is a pure function tested
on synthetic records. The chain's first execution is the author's run.
"""

from __future__ import annotations

import copy
import importlib.util
import re
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "final_reevaluation", REPO / "scripts" / "14_final_reevaluation.py"
)
CHAIN = importlib.util.module_from_spec(SPEC)
sys.modules["final_reevaluation"] = CHAIN  # dataclasses resolve their module through sys.modules
SPEC.loader.exec_module(CHAIN)

APPROVER = "Anurag Yadav"
FOLDS = ("cirrus_holdout", "spectralis_holdout", "topcon_holdout")


def plan():
    return CHAIN.build_plan(CHAIN.parse_args(["--approved-by", APPROVER]))


def test_TC_154_the_approver_is_required_and_non_empty():
    with pytest.raises(SystemExit):
        CHAIN.parse_args([])
    with pytest.raises(SystemExit):
        CHAIN.parse_args(["--approved-by", "  "])
    with pytest.raises(SystemExit):
        CHAIN.parse_args(["--approved-by", APPROVER, "--skip-gate"])


def test_TC_154_the_steps_are_in_section_17_13_order():
    expected = ["access_counts", "cirrus_val_a", "cirrus_val_b", "reproducibility_seeded",
                "reproducibility_compare", "cirrus_val_gate",
                "spectralis_holdout_val", "spectralis_holdout_val_gate",
                "topcon_holdout_val", "topcon_holdout_val_gate"]  # fmt: skip
    for fold in FOLDS:
        for bucket in ("test", "in_domain_ref"):
            expected += [f"{fold}_{bucket}", f"{fold}_{bucket}_gate"]
    expected += ["bscans", "access_counts_after"]
    assert [step.name for step in plan()] == expected


def test_TC_154_every_evaluation_output_is_new_and_under_audited():
    outputs = [s.output for s in plan() if s.kind in ("open", "sealed")]
    assert len(outputs) == 10 and len(set(outputs)) == 10
    for output in outputs:
        assert output.parent.name == "audited", output
        assert output.parent.parent in CHAIN.RUNS.values(), output


def test_TC_154_each_gate_compares_with_that_buckets_previous_record():
    steps = plan()
    by_output = {s.output: s for s in steps if s.output is not None}
    gates = [s for s in steps if s.kind == "gate"]
    assert len(gates) == 9
    for gate in gates:
        base, new = gate.inputs
        assert new in by_output, gate.name
        assert base.parent.parent == new.parent.parent, gate.name
        if (
            new.name.startswith("evaluation_val")
            and "spectralis" not in gate.name
            and "topcon" not in gate.name
        ):
            assert base == CHAIN.RUNS["cirrus_holdout"] / "corrected_hd95" / (
                "evaluation_val_seeded_a.json"
            )
        elif new.name.startswith("evaluation_val"):
            assert base.parent.name == "corrected" and base.name == "evaluation_val.json"
        else:
            assert base.parent.name == "corrected_hd95" and base.name == new.name


def test_TC_154_sealed_steps_unlock_naming_17_13_and_17_7b_and_open_steps_do_not():
    for step in plan():
        if step.argv is None or step.kind == "bscans":
            continue
        unlocking = "--unlock-bucket" in step.argv
        assert unlocking == (step.kind == "sealed"), step.name
        if unlocking:
            reason = step.argv[step.argv.index("--unlock-reason") + 1]
            assert "17.13" in reason and "17.7(b)" in reason
            assert step.argv[step.argv.index("--approved-by") + 1] == APPROVER


def test_TC_154_the_bscan_step_reads_the_audited_records_and_cites_17_13_and_21():
    step = next(s for s in plan() if s.kind == "bscans")
    argv = step.argv
    assert argv[argv.index("--record-set") + 1] == "audited"
    reason = argv[argv.index("--unlock-reason") + 1]
    assert re.search(r"17\.13", reason) and re.search(r"(?<![\d.])21(?![\d])", reason)
    assert argv[argv.index("--output-dir") + 1] == str(CHAIN.ILLUSTRATIONS)


def test_TC_154_the_expected_counts_are_the_ones_section_17_13_states():
    protocol = (REPO / "docs" / "07_vv_protocol.md").read_text(encoding="utf-8")
    section = protocol.split("### 17.13", 1)[1].split("\n---", 1)[0]
    stated = {
        (f"{fold}_holdout", bucket): (int(now), int(after))
        for fold, bucket, now, after in re.findall(
            r"^\| (cirrus|spectralis|topcon) \| `(test|in_domain_ref)` \| \*\*(\d+) → (\d+)\*\*",
            section,
            re.M,
        )
    }
    assert {k: v[0] for k, v in stated.items()} == CHAIN.EXPECTED_COUNTS
    assert {k: v[1] for k, v in stated.items()} == CHAIN.expected_after(set())


def test_TC_154_the_after_rule_adds_one_more_to_each_test_bucket_holding_a_pick():
    after = CHAIN.expected_after({"cirrus", "topcon"})
    assert after[("cirrus_holdout", "test")] == 9
    assert after[("spectralis_holdout", "test")] == 6
    assert after[("topcon_holdout", "test")] == 7
    assert after[("cirrus_holdout", "in_domain_ref")] == 6


# --- the gate ------------------------------------------------------------------------------


def estimate(value):
    return {"value": value, "ci_low": value - 0.1, "ci_high": value + 0.1, "n": 7}


def record():
    per_class = {"dice": estimate(0.5), "hd95": estimate(1.25)}
    detection = {"sensitivity": estimate(1.0), "specificity": estimate(0.0),
                 "auroc": {"value": 0.9, "positives": 3, "negatives": 4}}  # fmt: skip
    return {
        "fold_id": "cirrus_holdout", "bucket": "test", "n_patients": 2, "n_volumes": 2,
        "vendors": ["cirrus"], "unit_of_measurement": "volume",
        "bootstrap": {"n_resamples": 2000, "alpha": 0.05, "seed": 1, "resampling_unit": "patients"},
        "presence_voxel_threshold": 10, "mc_passes": 20,
        "segmentation": {"all_vendors": {"IRF": per_class}},
        "detection": {"all_vendors": {"IRF": detection}, "cirrus": {"IRF": detection}},
        "per_volume": [
            {"patient_id": "p1", "sample_id": "s1", "fluid_class": "IRF", "dice": 0.5,
             "hd95": 1.25, "predicted_voxels": 40, "reference_voxels": 30,
             "reference_present": True, "score": 0.8},
            {"patient_id": "p2", "sample_id": "s2", "fluid_class": "IRF", "dice": 1.0,
             "hd95": 0.0, "predicted_voxels": 0, "reference_voxels": 0,
             "reference_present": False, "score": 0.1},
        ],
    }  # fmt: skip


def changed(path, value):
    r = copy.deepcopy(record())
    node = r
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return r


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("segmentation", "all_vendors", "IRF", "dice", "value"), 0.7),
        (("segmentation", "all_vendors", "IRF", "hd95", "ci_high"), 3.0),
        (("detection", "all_vendors", "IRF", "auroc", "value"), 0.95),
        (("detection", "all_vendors", "IRF", "sensitivity", "value"), 0.5),
        (("per_volume", 0, "dice"), 0.6),
        (("per_volume", 0, "hd95"), 0.9),
        (("per_volume", 0, "predicted_voxels"), 41),
        (("per_volume", 0, "score"), 0.81),
        (("utc",), "2026-10-30"),
        (("bucket_access_count",), 9),
    ],
)
def test_TC_154_the_gate_passes_any_change_to_a_metric(path, value):
    assert CHAIN.population_differences(record(), changed(path, value)) == []


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("n_patients",), 3),
        (("n_volumes",), 3),
        (("vendors",), ["cirrus", "topcon"]),
        (("bootstrap", "n_resamples"), 1000),
        (("presence_voxel_threshold",), 20),
        (("mc_passes",), 10),
        (("bucket",), "in_domain_ref"),
        (("per_volume", 0, "reference_voxels"), 31),
        (("per_volume", 1, "reference_present"), True),
        (("per_volume", 1, "patient_id"), "p9"),
        (("detection", "cirrus", "IRF", "auroc", "positives"), 4),
        (("detection", "all_vendors", "IRF", "auroc", "negatives"), 5),
    ],
)
def test_TC_154_the_gate_stops_on_a_change_to_the_population_or_the_reference(path, value):
    assert CHAIN.population_differences(record(), changed(path, value))


def test_TC_154_the_gate_stops_on_a_row_added_or_removed():
    more = copy.deepcopy(record())
    more["per_volume"].append(dict(more["per_volume"][0], sample_id="s3"))
    assert CHAIN.population_differences(record(), more)
    fewer = copy.deepcopy(record())
    fewer["per_volume"] = fewer["per_volume"][:1]
    assert CHAIN.population_differences(record(), fewer)


# --- the fix checks stand in for SHAs, so each must be able to fail (rule 8) ----------------


def test_TC_154_every_fix_check_passes_on_this_code():
    assert CHAIN.missing_fixes() == []


def test_TC_154_the_d1_check_fails_on_the_legacy_inversion(monkeypatch):
    from ocuval.data import transforms

    def legacy(native_height, source_rows):  # torch's legacy nearest: floor(j * h / H)
        return (np.arange(native_height) * len(source_rows)) // native_height

    monkeypatch.setattr(transforms, "nearest_source", legacy)
    assert CHAIN.d1_fixed() is False


def test_TC_154_the_d4_d5_and_d3_checks_fail_when_their_fix_is_undone(monkeypatch):
    from ocuval.eval import pipeline

    real_load = CHAIN.load_script

    def without_box(name, filename):
        module = real_load(name, filename)
        module.predict_volume = lambda model, frames, device, passes, chunk: None
        return module

    monkeypatch.setattr(CHAIN, "load_script", without_box)
    assert CHAIN.d4_fixed() is False
    monkeypatch.undo()

    real_read = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, *a, **k: real_read(self, *a, **k).replace(
            "assert_spacing_unchanged(native.spacing_mm,",
            'assert_spacing_unchanged(row["spacing_mm"],',
        ),
    )
    assert CHAIN.d5_fixed() is False
    monkeypatch.undo()

    monkeypatch.delattr(pipeline, "secondary_hd95")
    assert CHAIN.d3_fixed() is False
