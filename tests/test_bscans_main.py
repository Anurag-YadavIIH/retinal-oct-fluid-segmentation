"""TC-146 (amended 2026-10-30) — `09_illustrative_bscans.py`'s real `main`, end to end.

Traces to: SRS-093

On 2026-10-30 the §21.10 run opened three sealed buckets, regenerated all six picks and then
failed inside its own gate: the D5 fix had bound the spacing check's result to `recorded`, the
name that held the sealed records' values, so the gate received a tuple (`docs/13`). Every
earlier test called the script's functions one at a time; none ran `main`. This one does, on
synthetic scans with the model, the reader and the transforms stood in. The loop, the selection,
the spacing check, the measurement, the gate, the rendering and the save are the script's own.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

import synthetic_scans as synth

REPO = Path(__file__).resolve().parents[1]
REASON = "illustrations under docs/07 section 17.13 and section 21 (21.10)"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stand_in(monkeypatch, tmp_path, by_fold, mismatch=False):
    """Everything but the script's own logic: GPU, model, reader, transforms, manifest."""
    import torch

    from ocuval import runs
    from ocuval.data import transforms
    from ocuval.io import retouch_reader
    from ocuval.models import seg_unet
    from ocuval.training import checkpoint

    volumes = {v["patient_id"]: v for vs in by_fold.values() for v in vs}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OCUVAL_ARTIFACTS", str(tmp_path / "artifacts"))
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(checkpoint, "request_determinism", lambda seed: {})
    monkeypatch.setattr(runs, "manifest_path", lambda cfg: None)
    monkeypatch.setattr(runs, "load_manifest", lambda path: synth.manifest_rows(by_fold))
    monkeypatch.setattr(
        retouch_reader,
        "read_volume",
        lambda path, vendor: types.SimpleNamespace(
            pixel_array=volumes[str(path)]["image"],
            label_array=volumes[str(path)]["reference"],
            spacing_mm=volumes[str(path)]["spacing_mm"],
        ),
    )
    model = types.SimpleNamespace(to=lambda device: model)
    monkeypatch.setattr(seg_unet, "build_model", lambda cfg: model)
    monkeypatch.setattr(seg_unet, "load_verified", lambda *a, **k: {"epoch": 1})
    monkeypatch.setattr(transforms, "eval_transforms", lambda cfg: lambda d: {"image": d["image"]})
    monkeypatch.setattr(transforms, "content_box", lambda *a: None)
    monkeypatch.setattr(
        transforms, "invert_axial_resample", lambda labels, spacing, shape, target_axial_mm: labels
    )

    def predict(model, frames, device, passes, chunk, box):
        v = next(v for v in volumes.values() if v["image"].shape == frames.shape
                 and np.array_equal(v["image"], frames))  # fmt: skip
        labels = v["prediction"].copy()
        if mismatch:
            labels[1, 12, 10] = 0  # one voxel: the regenerated map is not the evaluated one
        return labels, v["scores"]

    script = load("bscans_tc146", REPO / "scripts" / "09_illustrative_bscans.py")
    real_load = script.load_module

    def load_module(name, path):
        module = real_load(name, path)
        if Path(path).name == "05_evaluate.py":
            module.predict_volume = predict
        return module

    monkeypatch.setattr(script, "load_module", load_module)
    return script


def argv(tmp_path):
    return ["--unlock-reason", REASON, "--approved-by", "a", "--record-set", "audited",
            "--config", str(REPO / "configs" / "train_seg.yaml"),
            "--data-config", str(REPO / "configs" / "data.yaml"),
            "--output-dir", str(tmp_path / "out")]  # fmt: skip


def test_TC_146_main_regenerates_gates_and_saves_on_synthetic_scans(tmp_path, monkeypatch):
    by_fold = synth.all_folds()
    synth.write_held_out_records(tmp_path, "audited", by_fold)
    script = stand_in(monkeypatch, tmp_path, by_fold)
    assert script.main(argv(tmp_path)) == 0
    selection = json.loads((tmp_path / "out" / "selection.json").read_text(encoding="utf-8"))
    assert selection["gate"] == "passed" and selection["failed_roles"] == []
    roles = [p["role"] for p in selection["picks"]]
    assert {"worst", "median", "best", "fp_srf"} <= set(roles)
    assert sorted(p.name for p in (tmp_path / "out").glob("*.png")) == sorted(
        f"bscan_{r}.png" for r in roles
    )
    log = (tmp_path / "artifacts" / "sealed_access.jsonl").read_text(encoding="utf-8")
    assert len(log.splitlines()) == len({p["run"] for p in selection["picks"]})


def test_TC_146_main_saves_nothing_when_a_regenerated_map_differs(tmp_path, monkeypatch):
    by_fold = synth.all_folds()
    synth.write_held_out_records(tmp_path, "audited", by_fold)
    script = stand_in(monkeypatch, tmp_path, by_fold, mismatch=True)
    assert script.main(argv(tmp_path)) == 1
    assert not list((tmp_path / "out").glob("*.png"))
    selection = json.loads((tmp_path / "out" / "selection.json").read_text(encoding="utf-8"))
    assert selection["gate"] == "failed" and selection["failed_roles"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
