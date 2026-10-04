"""TC-127: the exact record comparison treats NaN-in-both as equal and nothing else as close.

Verifies: SRS-090

`scripts/compare_evaluation_records.py` decides whether a sealed bucket may be unlocked
(`scripts/run_remaining.ps1`, step 0), so both of its failure directions matter. A spurious
difference blocks a legitimate run; a missed one admits a non-reproducible record. Its first real
use reported `nan -> nan` as a difference (`docs/13`, 2026-10-04), which is the first direction.
These tests pin both.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_evaluation_records.py"


@pytest.fixture(scope="module")
def cmp():
    spec = importlib.util.spec_from_file_location("compare_evaluation_records", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record() -> dict:
    """The shape of an evaluation record, including the undefined-metric case."""
    return {
        "utc": "2026-10-04T07:19:42+00:00",
        "notes": {"evaluation_source": {"commit": "aaaaaaa"}},
        "bucket_access_count": 1,
        "per_volume": [{"sample_id": "s1", "dice": 0.5}],
        "bucket": "val",
        "segmentation": {
            "all_vendors": {"IRF": {"dice": {"value": 0.42925279591375975, "n": 7}}},
        },
        "detection": {
            "topcon": {"IRF": {"auroc": {"value": math.nan}, "specificity": {"value": math.nan}}},
        },
    }


def test_TC_127_nan_in_both_records_is_the_same_result(cmp):
    _, differ = cmp.compare(record(), record())
    assert differ == []


def test_TC_127_nan_in_only_one_record_is_a_difference(cmp):
    defined = record()
    defined["detection"]["topcon"]["IRF"]["auroc"]["value"] = 0.75
    for reference, candidate in ((record(), defined), (defined, record())):
        _, differ = cmp.compare(reference, candidate)
        assert [key for key, _, _ in differ] == ["/detection/topcon/IRF/auroc/value"]


def test_TC_127_a_last_digit_change_is_a_difference(cmp):
    original = record()["segmentation"]["all_vendors"]["IRF"]["dice"]["value"]
    # The next representable double: the smallest change a float can carry. (Two decimal
    # literals that look different can parse to the same double, which is how the first draft
    # of this test asserted nothing.)
    adjacent = math.nextafter(original, 1.0)
    assert adjacent != original
    changed = record()
    changed["segmentation"]["all_vendors"]["IRF"]["dice"]["value"] = adjacent
    _, differ = cmp.compare(record(), changed)
    assert [key for key, _, _ in differ] == ["/segmentation/all_vendors/IRF/dice/value"]


def test_TC_127_a_missing_leaf_is_a_difference(cmp):
    shorter = record()
    del shorter["segmentation"]["all_vendors"]["IRF"]["dice"]["n"]
    _, differ = cmp.compare(record(), shorter)
    assert differ == [("/segmentation/all_vendors/IRF/dice/n", 7, cmp.ABSENT)]


def test_TC_127_only_the_four_named_top_level_keys_are_excluded(cmp):
    varied = record()
    varied["utc"] = "later"
    varied["notes"] = {"evaluation_source": {"commit": "bbbbbbb"}}
    varied["bucket_access_count"] = 2
    varied["per_volume"][0]["dice"] = 0.9
    assert cmp.compare(record(), varied)[1] == []

    # The same key names deeper in the record are compared like any other leaf.
    nested = copy.deepcopy(record())
    nested["segmentation"]["all_vendors"]["IRF"]["utc"] = "x"
    assert [k for k, _, _ in cmp.compare(record(), nested)[1]] == [
        "/segmentation/all_vendors/IRF/utc"
    ]


def test_TC_127_exit_status_is_0_identical_1_different_2_unreadable(cmp, tmp_path, capsys):
    same_a, same_b, other = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "c.json"
    # json.dumps writes NaN as the bare token NaN, which is what the evaluation records hold.
    same_a.write_text(json.dumps(record()), encoding="utf-8")
    same_b.write_text(json.dumps(record()), encoding="utf-8")
    changed = record()
    changed["bucket"] = "test"
    other.write_text(json.dumps(changed), encoding="utf-8")

    assert cmp.main([str(same_a), str(same_b)]) == 0
    assert "IDENTICAL" in capsys.readouterr().out
    assert cmp.main([str(same_a), str(other)]) == 1
    assert "DIFFER: 1 leaves" in capsys.readouterr().out
    assert cmp.main([str(same_a), str(tmp_path / "missing.json")]) == 2
