"""TC-150 — the HD95 re-evaluation chain follows `docs/07` §17.12; its gate admits HD95 only.

Traces to: SRS-102

**Arguments, the step plan and the gate's comparison only. Nothing here executes the chain**:
no evaluation, no unlock, no read of the access log. The gate is a pure function and is tested
on synthetic records. The chain's first execution is the author's run.
"""

from __future__ import annotations

import copy
import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "reevaluate_hd95", REPO / "scripts" / "12_reevaluate_hd95.py"
)
CHAIN = importlib.util.module_from_spec(SPEC)
sys.modules["reevaluate_hd95"] = CHAIN  # dataclasses resolve their module through sys.modules
SPEC.loader.exec_module(CHAIN)

APPROVER = "Anurag Yadav"


def plan():
    return CHAIN.build_plan(CHAIN.parse_args(["--approved-by", APPROVER]))


def test_TC_150_the_approver_is_required_and_non_empty():
    with pytest.raises(SystemExit):
        CHAIN.parse_args([])
    with pytest.raises(SystemExit):
        CHAIN.parse_args(["--approved-by", "  "])
    with pytest.raises(SystemExit):
        CHAIN.parse_args(["--approved-by", APPROVER, "--skip-gate"])


def test_TC_150_the_steps_are_in_section_17_12_order_each_sealed_step_then_its_gate():
    names = [step.name for step in plan()]
    sealed = [f"{f}_holdout_{b}" for f in ("cirrus", "spectralis", "topcon")
              for b in ("test", "in_domain_ref")]  # fmt: skip
    expected = ["access_counts", "cirrus_val_a", "cirrus_val_b", "reproducibility_seeded",
                "reproducibility_compare"]  # fmt: skip
    for name in sealed:
        expected += [name, f"{name}_gate"]
    assert names == expected


def test_TC_150_every_output_is_new_and_under_corrected_hd95():
    outputs = [step.output for step in plan() if step.output is not None]
    assert len(outputs) == 8 and len(set(outputs)) == 8
    for output in outputs:
        assert output.parent.name == "corrected_hd95", output
        assert output.parent.parent in CHAIN.RUNS.values(), output


def test_TC_150_each_gate_compares_its_bucket_with_the_24_october_record():
    steps = plan()
    for index, step in enumerate(steps):
        if step.kind == "gate":
            sealed = steps[index - 1]
            base, new = step.inputs
            assert new == sealed.output
            assert base.parent.name == "corrected" and base.name == sealed.output.name


def test_TC_150_sealed_steps_unlock_naming_17_12_and_17_7b_and_open_steps_do_not():
    for step in plan():
        if step.argv is None:
            continue
        unlocking = "--unlock-bucket" in step.argv
        assert unlocking == (step.kind == "sealed"), step.name
        if unlocking:
            reason = step.argv[step.argv.index("--unlock-reason") + 1]
            assert "17.12" in reason and "17.7(b)" in reason
            assert step.argv[step.argv.index("--approved-by") + 1] == APPROVER


def test_TC_150_the_expected_counts_are_the_ones_section_17_12_states():
    protocol = (REPO / "docs" / "07_vv_protocol.md").read_text(encoding="utf-8")
    section = protocol.split("### 17.12", 1)[1].split("\n---", 1)[0]
    stated = {
        (f"{fold}_holdout", bucket): int(now)
        for fold, bucket, now in re.findall(
            r"^\| (cirrus|spectralis|topcon) \| `(test|in_domain_ref)` \| \*\*(\d+) → \d+\*\*",
            section,
            re.M,
        )
    }
    assert stated == CHAIN.EXPECTED_COUNTS


# --- the gate ------------------------------------------------------------------------------


def estimate(value):
    return {"value": value, "ci_low": value - 0.1, "ci_high": value + 0.1, "n": 7}


def record():
    per_class = {"dice": estimate(0.5), "hd95": estimate(1.25)}
    detection = {"sensitivity": estimate(1.0), "specificity": estimate(0.0),
                 "auroc": {"value": 0.9, "positives": 3, "negatives": 4}}  # fmt: skip
    return {
        "utc": "2026-10-24T00:00:00", "notes": {"evaluation_source": "a"}, "bucket_access_count": 5,
        "segmentation": {"all_vendors": {"IRF": per_class}},
        "detection": {"all_vendors": {"IRF": detection}},
        "per_volume": [{"patient_id": "p1", "fluid_class": "IRF", "dice": 0.5, "hd95": 1.25,
                        "predicted_voxels": 40, "reference_voxels": 30,
                        "reference_present": True, "score": 0.8}],
    }  # fmt: skip


def changed(path, value):
    r = copy.deepcopy(record())
    node = r
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return r


@pytest.mark.parametrize(
    "path",
    [
        ("segmentation", "all_vendors", "IRF", "hd95"),
        ("per_volume", 0, "hd95"),
        ("utc",),
        ("notes",),
        ("bucket_access_count",),
    ],
    ids=["aggregate-hd95", "per-volume-hd95", "utc", "notes", "access-count"],
)
def test_TC_150_the_gate_passes_a_change_to_hd95_or_provenance(path):
    aggregate = path == ("segmentation", "all_vendors", "IRF", "hd95")
    value = {"value": 9.9, "ci_low": 1.0, "ci_high": 20.0, "n": 5} if aggregate else 7.5
    assert CHAIN.non_hd95_differences(record(), changed(path, value)) == []


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("segmentation", "all_vendors", "IRF", "dice", "value"), 0.5000001),
        (("segmentation", "all_vendors", "IRF", "dice", "ci_low"), 0.3),
        (("segmentation", "all_vendors", "IRF", "dice", "n"), 6),
        (("detection", "all_vendors", "IRF", "sensitivity", "value"), 0.9),
        (("detection", "all_vendors", "IRF", "specificity", "ci_high"), 0.2),
        (("detection", "all_vendors", "IRF", "auroc", "value"), 0.91),
        (("detection", "all_vendors", "IRF", "auroc", "negatives"), 5),
        (("per_volume", 0, "dice"), 0.49),
        (("per_volume", 0, "predicted_voxels"), 41),
        (("per_volume", 0, "reference_voxels"), 31),
        (("per_volume", 0, "reference_present"), False),
        (("per_volume", 0, "score"), 0.81),
    ],
)
def test_TC_150_the_gate_stops_on_any_other_change(path, value):
    differences = CHAIN.non_hd95_differences(record(), changed(path, value))
    assert len(differences) == 1, differences


def test_TC_150_the_gate_stops_on_a_row_added_or_removed():
    more = copy.deepcopy(record())
    more["per_volume"].append(dict(more["per_volume"][0], patient_id="p2"))
    assert CHAIN.non_hd95_differences(record(), more)
    fewer = copy.deepcopy(record())
    fewer["per_volume"] = []
    assert CHAIN.non_hd95_differences(record(), fewer)


def test_TC_150_the_fix_check_passes_on_this_code_and_fails_on_the_old_order(monkeypatch):
    """The pre-flight self-check stands in for a SHA, so it must be able to fail (rule 8)."""
    from ocuval.eval import pipeline

    assert CHAIN.fix_present() is True
    monkeypatch.setattr(pipeline, "array_axis_spacing", lambda s: tuple(float(v) for v in s))
    assert CHAIN.fix_present() is False
