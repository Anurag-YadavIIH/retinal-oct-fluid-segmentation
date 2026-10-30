"""TC-155 — a saved prediction reloads identically, and re-measuring it reproduces the record.

Traces to: SRS-106

**Synthetic data only** (`docs/06` DMP-C12). The volumes are built here, with three vendors'
anisotropic spacings and, in each volume, one class present in both prediction and reference, one
predicted where the reference is empty, and one empty in both. The record evaluated from the
re-measured maps must equal the record evaluated from the originals in every leaf; and the check
must be able to fail (`docs/07` §3 rule 8): one voxel changed is seen by the checksum, by the
manifest check and by the re-measured record.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from ocuval.eval import predictions
from ocuval.eval.pipeline import EvaluationPlan, evaluate

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "compare_records", REPO / "scripts" / "compare_evaluation_records.py"
)
COMPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPARE)

THRESHOLD = 10
SPACINGS = {  # (axial, lateral, separation), docs/06 section 3.1.2
    "cirrus": (0.001955, 0.011742, 0.046878),
    "spectralis": (0.003872, 0.011406, 0.120774),
    "topcon": (0.002600, 0.011720, 0.046880),
}


def synthetic_volumes():
    """Six volumes, two per vendor. IRF in both, SRF predicted only, PED in neither."""
    rng = np.random.default_rng(155)
    volumes = []
    for index, (vendor, spacing) in enumerate(
        [v for v in SPACINGS.items() for _ in range(2)], start=1
    ):
        shape = (4, 40 + index, 24)
        reference = np.zeros(shape, dtype=np.uint8)
        prediction = np.zeros(shape, dtype=np.uint8)
        reference[1:3, 10:20, 5:15] = 1
        prediction[1:3, 11 + index % 3 : 21, 6:15] = 1
        prediction[0, 30:34, 2:8] = 2  # SRF predicted, absent from the reference
        prediction[rng.integers(0, 4), rng.integers(0, 40), rng.integers(0, 24)] = 1  # a stray
        volumes.append(
            {
                "patient_id": f"TRAIN{index:03d}",
                "sample_id": f"S{index:03d}",
                "vendor": vendor,
                "prediction": prediction,
                "reference": reference,
                "spacing_mm": spacing,
                "scores": {"IRF": float(rng.random()), "SRF": float(rng.random()), "PED": 0.1 / 3},
            }
        )
    return volumes


def measured(volume, prediction=None):
    return predictions.measured_volume(
        sample_id=volume["sample_id"],
        patient_id=volume["patient_id"],
        vendor=volume["vendor"],
        prediction=volume["prediction"] if prediction is None else prediction,
        reference=volume["reference"],
        spacing_mm=volume["spacing_mm"],
        scores=volume["scores"],
        threshold=THRESHOLD,
    )


def record_of(volumes):
    plan = EvaluationPlan(fold_id="f", bucket="val", seed=7, n_resamples=200,
                          presence_voxel_threshold=THRESHOLD)  # fmt: skip
    return evaluate(plan, volumes)


def save_all(folder, volumes):
    return {
        v["patient_id"]: predictions.save_prediction(
            folder,
            patient_id=v["patient_id"],
            sample_id=v["sample_id"],
            vendor=v["vendor"],
            labels=v["prediction"],
            spacing_mm=v["spacing_mm"],
            scores=v["scores"],
        )
        for v in volumes
    }


def remeasured_record(folder, volumes):
    references = {v["patient_id"]: v["reference"] for v in volumes}
    return record_of(
        [
            predictions.remeasure(folder / f"{pid}.npz", references[pid], THRESHOLD)
            for pid in references
        ]
    )


def differences(a, b):
    """TC-127's comparator, leaf by leaf, with `per_volume` compared too (it excludes it).

    NaN on both sides is the same undefined result there, as an HD95 with one mask empty is;
    plain list equality would call it a difference.
    """
    _, differ = COMPARE.compare(a, b)
    _, rows = COMPARE.compare({"rows": a["per_volume"]}, {"rows": b["per_volume"]})
    return [d[0] for d in differ + rows if d[0] != "/utc"]


def test_TC_155_a_saved_map_reloads_identically(tmp_path):
    volumes = synthetic_volumes()
    save_all(tmp_path, volumes)
    for v in volumes:
        saved = predictions.load_prediction(tmp_path / f"{v['patient_id']}.npz")
        assert saved["labels"].dtype == np.uint8
        assert saved["labels"].shape == v["prediction"].shape
        assert np.array_equal(saved["labels"], v["prediction"])
        assert saved["spacing_mm"] == v["spacing_mm"]  # bit-identical floats
        assert saved["scores"] == v["scores"]
        assert (saved["patient_id"], saved["sample_id"], saved["vendor"]) == (
            v["patient_id"], v["sample_id"], v["vendor"],
        )  # fmt: skip


def test_TC_155_re_measuring_reproduces_the_record_in_every_leaf(tmp_path):
    volumes = synthetic_volumes()
    original = record_of([measured(v) for v in volumes])
    save_all(tmp_path, volumes)
    again = remeasured_record(tmp_path, volumes)
    assert differences(original, again) == []
    # The synthetic set exercises every case the metrics treat differently.
    rows = original["per_volume"]
    assert {r["fluid_class"] for r in rows if r["reference_present"]} == {"IRF"}
    assert any(r["predicted_voxels"] and not r["reference_voxels"] for r in rows)
    assert any(not r["predicted_voxels"] and not r["reference_voxels"] for r in rows)


def test_TC_155_the_manifest_names_one_file_per_volume_and_every_checksum_matches(tmp_path):
    volumes = synthetic_volumes()
    manifest = predictions.manifest(save_all(tmp_path, volumes))
    record = record_of([measured(v) for v in volumes])
    assert sorted(manifest["files"]) == sorted(v["patient_id"] for v in volumes)
    assert manifest["format"] == predictions.FORMAT
    for v in volumes:
        entry = manifest["files"][v["patient_id"]]
        assert entry["sha256"] == predictions.sha256_file(tmp_path / entry["file"])
        assert entry["labels_sha256"] == predictions.labels_sha256(v["prediction"])
        assert entry["shape"] == list(v["prediction"].shape) and entry["dtype"] == "uint8"
    assert predictions.manifest_problems(manifest, tmp_path, record["per_volume"]) == []


def test_TC_155_saving_the_same_map_twice_gives_byte_identical_files(tmp_path):
    volumes = synthetic_volumes()
    first, second = save_all(tmp_path / "a", volumes), save_all(tmp_path / "b", volumes)
    assert first == second
    for v in volumes:
        name = f"{v['patient_id']}.npz"
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_TC_155_one_voxel_changed_is_seen_by_the_checksum_the_manifest_and_the_record(tmp_path):
    volumes = synthetic_volumes()
    manifest = predictions.manifest(save_all(tmp_path, volumes))
    original = record_of([measured(v) for v in volumes])

    target = volumes[2]
    altered = target["prediction"].copy()
    altered[1, 15, 10] = 0  # inside the IRF overlap
    path = tmp_path / f"{target['patient_id']}.npz"
    path.unlink()
    predictions.save_prediction(
        tmp_path, patient_id=target["patient_id"], sample_id=target["sample_id"],
        vendor=target["vendor"], labels=altered, spacing_mm=target["spacing_mm"],
        scores=target["scores"],
    )  # fmt: skip

    assert predictions.sha256_file(path) != manifest["files"][target["patient_id"]]["sha256"]
    problems = predictions.manifest_problems(manifest, tmp_path, original["per_volume"])
    assert len(problems) == 1 and target["patient_id"] in problems[0]
    assert differences(original, remeasured_record(tmp_path, volumes))


def test_TC_155_a_missing_or_extra_file_or_volume_is_named(tmp_path):
    volumes = synthetic_volumes()
    manifest = predictions.manifest(save_all(tmp_path, volumes))
    rows = record_of([measured(v) for v in volumes])["per_volume"]

    (tmp_path / "TRAIN001.npz").unlink()
    assert any("TRAIN001" in p for p in predictions.manifest_problems(manifest, tmp_path, rows))

    fewer_rows = [r for r in rows if r["patient_id"] != "TRAIN002"]
    problems = predictions.manifest_problems(manifest, tmp_path, fewer_rows)
    assert any("TRAIN002" in p for p in problems)

    (tmp_path / "TRAIN099.npz").write_bytes(b"not listed")
    assert any("TRAIN099" in p for p in predictions.manifest_problems(manifest, tmp_path, rows))


def test_TC_155_a_folder_already_holding_a_file_is_refused_before_anything_is_read(tmp_path):
    (tmp_path / "earlier.npz").write_bytes(b"")
    with pytest.raises(FileExistsError):
        predictions.require_empty(tmp_path)
    predictions.require_empty(tmp_path / "new")  # absent is fine, and nothing is created
    assert not (tmp_path / "new").exists()

    # The evaluation refuses it first: --run names nothing, so reading anything would fail
    # differently.
    evaluation = evaluate_script()
    with pytest.raises(SystemExit, match="SRS-106"):
        evaluation.main(["--run", str(tmp_path / "no_run"), "--save-predictions", str(tmp_path)])


def evaluate_script():
    path = REPO / "scripts" / "05_evaluate.py"
    spec = importlib.util.spec_from_file_location("evaluate_tc155", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_TC_155_the_evaluation_script_saves_and_its_written_record_is_reproduced(
    tmp_path, monkeypatch
):
    """`05_evaluate.main` end to end, with the model, the reader and the transforms stood in.

    What is real: the loop, the spacing check, `measured_volume`, saving, the manifest,
    `evaluate` and `write_record`. The record is read back from its JSON file, as a later
    re-measurement would read it, and must be reproduced leaf for leaf.
    """
    import types

    from ocuval.data import transforms
    from ocuval.io import retouch_reader
    from ocuval.models import seg_unet

    volumes = synthetic_volumes()
    by_subject = {v["patient_id"]: v for v in volumes}
    evaluation = evaluate_script()
    monkeypatch.setattr(evaluation, "request_determinism", lambda seed: {})
    monkeypatch.setattr(evaluation, "describe_determinism", lambda *a: {})
    monkeypatch.setattr(evaluation, "source_record", lambda: {})
    monkeypatch.setattr(evaluation, "manifest_path", lambda cfg: None)
    monkeypatch.setattr(
        evaluation,
        "load_manifest",
        lambda path: [
            {
                "patient_id": v["patient_id"],
                "sample_id": v["sample_id"],
                "vendor": v["vendor"],
                "spacing_mm": list(v["spacing_mm"]),
                "source_path": v["patient_id"],
                "intensity_window": [0, 1],
            }
            for v in volumes
        ],  # fmt: skip
    )
    monkeypatch.setattr(
        evaluation,
        "load_split",
        lambda path: types.SimpleNamespace(val=list(by_subject), held_out_vendor=None),
    )
    monkeypatch.setattr(
        retouch_reader,
        "read_volume",
        lambda path, vendor: types.SimpleNamespace(
            pixel_array=by_subject[str(path)]["reference"].astype(np.float32),
            label_array=by_subject[str(path)]["reference"],
            spacing_mm=by_subject[str(path)]["spacing_mm"],
        ),
    )
    model = types.SimpleNamespace(to=lambda device: model)
    monkeypatch.setattr(seg_unet, "build_model", lambda cfg: model)
    monkeypatch.setattr(seg_unet, "load_verified", lambda *a, **k: {"epoch": 3})
    monkeypatch.setattr(transforms, "eval_transforms", lambda cfg: lambda d: {"image": d["image"]})
    monkeypatch.setattr(transforms, "content_box", lambda *a: None)
    current = {}

    def predict(model, frames, device, passes, chunk, box):
        # The frames are the reference as float; find whose they are, and return its prediction.
        subject = next(s for s, v in by_subject.items() if v["reference"].shape == frames.shape
                       and np.array_equal(v["reference"], frames))  # fmt: skip
        current["subject"] = subject
        return by_subject[subject]["prediction"], by_subject[subject]["scores"]

    monkeypatch.setattr(evaluation, "predict_volume", predict)
    monkeypatch.setattr(
        transforms, "invert_axial_resample", lambda labels, spacing, shape, target_axial_mm: labels
    )

    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text('{"fold_id": "f"}', encoding="utf-8")
    output, folder = tmp_path / "evaluation_val.json", tmp_path / "saved" / "f" / "val"
    argv = ["--run", str(run), "--bucket", "val", "--device", "cpu", "--output", str(output),
            "--save-predictions", str(folder)]  # fmt: skip
    assert evaluation.main(argv) == 0

    import json

    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["notes"]["predictions_directory"] == folder.as_posix()
    assert predictions.manifest_problems(record["predictions"], folder, record["per_volume"]) == []
    plan = EvaluationPlan(fold_id="f", bucket="val", seed=record["bootstrap"]["seed"],
                          presence_voxel_threshold=record["presence_voxel_threshold"],
                          mc_passes=record["mc_passes"])  # fmt: skip
    again = evaluate(
        plan,
        [
            predictions.remeasure(
                folder / entry["file"],
                by_subject[pid]["reference"],
                record["presence_voxel_threshold"],
            )  # fmt: skip
            for pid, entry in record["predictions"]["files"].items()
        ],
    )
    again = json.loads(json.dumps(again))  # the same serialisation the record went through
    assert differences({k: v for k, v in record.items() if k != "predictions"}, again) == []


def test_TC_155_an_existing_file_is_never_overwritten(tmp_path):
    volume = synthetic_volumes()[0]
    save_all(tmp_path, [volume])
    with pytest.raises(FileExistsError):
        save_all(tmp_path, [volume])


def test_TC_155_a_saved_map_is_ignored_by_git():
    probe = "artifacts/predictions_final/cirrus_holdout/test/TRAIN001.npz"
    result = subprocess.run(["git", "check-ignore", "-q", probe], cwd=REPO, check=False)
    assert result.returncode == 0, f"{probe} is not ignored by git (DMP-C13)"


def test_TC_155_the_evaluation_saves_exactly_what_it_measures():
    """`05_evaluate.py` hands one map, one spacing and one score set to both functions."""
    tree = ast.parse((REPO / "scripts" / "05_evaluate.py").read_text(encoding="utf-8"))
    calls = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name in ("measured_volume", "save_prediction"):
                calls.setdefault(name, []).append({k.arg: ast.dump(k.value) for k in node.keywords})
    assert len(calls.get("measured_volume", [])) == 1, "the evaluation must measure through SRS-106"
    assert len(calls.get("save_prediction", [])) == 1, "the evaluation must save what it measures"
    measure, save = calls["measured_volume"][0], calls["save_prediction"][0]
    assert save["labels"] == measure["prediction"]
    assert save["spacing_mm"] == measure["spacing_mm"]
    assert save["scores"] == measure["scores"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
