"""TC-157 — the §21.11 B-scans come from the saved maps, checked by checksum, with no model.

Traces to: SRS-108, SRS-107

`09_illustrative_bscans.py --record-set final` runs here as the chain runs it: a separate
process, from a sandbox root, with no stand-in. **torch is made unimportable in that process**,
so the run proving the mode needs no model is the run itself. Also here: the chain's plan, its
dry run and certificate, and the rule that every script a chain calls has an end-to-end test of
its real `main` (step 3 of the author's instruction of 2026-10-30).
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from ocuval import sandbox
from ocuval.eval import predictions, sealed

REPO = Path(__file__).resolve().parents[1]
BSCANS = REPO / "scripts" / "09_illustrative_bscans.py"
REASON = "illustrative B-scans under docs/07 section 21 (21.11), for illustration only"
NO_TORCH = (
    "import runpy, sys; sys.modules['torch'] = None; sys.argv = sys.argv[1:]; "
    "runpy.run_path(sys.argv[0], run_name='__main__')"
)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CHAIN = load("final_bscans_chain", REPO / "scripts" / "15_final_bscans.py")


def clean_environment() -> dict:
    """The parent's environment without a certificate, and without pytest-cov's subprocess
    variables: a child started from the sandbox would otherwise write coverage data the parent
    cannot combine with its own."""
    return {k: v for k, v in os.environ.items()
            if k != sealed.CERTIFICATE_ENV and not k.startswith("COV_CORE")}  # fmt: skip


def run_final(root: Path) -> subprocess.CompletedProcess:
    env = clean_environment()
    env["OCUVAL_ARTIFACTS"] = str(root / "artifacts")
    argv = [sys.executable, "-c", NO_TORCH, str(BSCANS), "--record-set", "final",
            "--unlock-reason", REASON, "--approved-by", "a"]  # fmt: skip
    return subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, check=False)


def opened(root: Path) -> int:
    log = root / "artifacts" / "sealed_access.jsonl"
    return len(log.read_text(encoding="utf-8").splitlines()) if log.is_file() else 0


def picks_of(root: Path) -> list[dict]:
    out = root / "artifacts" / "illustrations_final" / "selection.json"
    return json.loads(out.read_text(encoding="utf-8"))["picks"]


@pytest.fixture
def root(tmp_path):
    sandbox.build_final_bscans(tmp_path / "root")
    return tmp_path / "root"


def test_TC_157_main_draws_gates_and_saves_from_the_saved_maps_with_no_torch(root):
    result = run_final(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert CHAIN.outputs_complete(root)
    assert opened(root) == len({p["run"] for p in picks_of(root)})
    assert "drawn from its saved map" in result.stdout


def test_TC_157_a_saved_file_off_its_checksum_is_refused_before_any_bucket_opens(root):
    folder = root / "artifacts" / "predictions_final"
    for path in folder.rglob("*.npz"):
        path.write_bytes(path.read_bytes() + b"\0")  # every file altered: whichever is picked
    result = run_final(root)
    assert result.returncode != 0 and "SHA-256" in result.stderr
    assert opened(root) == 0
    assert not (root / "artifacts" / "illustrations_final").exists()


def test_TC_157_a_map_whose_bytes_differ_from_the_manifest_saves_no_image(root):
    for path in (root / "artifacts" / "runs").rglob("evaluation_test.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        for entry in record["predictions"]["files"].values():
            entry["labels_sha256"] = "0" * 64  # the files still match: only the maps' bytes do not
        path.write_text(json.dumps(record), encoding="utf-8")
    result = run_final(root)
    assert result.returncode == 1
    assert not list((root / "artifacts" / "illustrations_final").glob("*.png"))


def test_TC_157_a_saved_spacing_off_the_checked_one_saves_no_image(root):
    for fold in sandbox.FOLDS:
        path = (
            root
            / "artifacts"
            / "runs"
            / sandbox.RUN_DIRS[fold]
            / "audited"
            / "evaluation_test.json"
        )
        record = json.loads(path.read_text(encoding="utf-8"))
        folder = root / record["notes"]["predictions_directory"]
        for subject, entry in record["predictions"]["files"].items():
            saved = predictions.load_prediction(folder / entry["file"])
            (folder / entry["file"]).unlink()
            axial, lateral, separation = saved["spacing_mm"]
            record["predictions"]["files"][subject] = predictions.save_prediction(
                folder, patient_id=subject, sample_id=saved["sample_id"], vendor=saved["vendor"],
                labels=saved["labels"], spacing_mm=(axial * 2, lateral, separation),
                scores=saved["scores"],
            )  # fmt: skip
        path.write_text(json.dumps(record), encoding="utf-8")
    result = run_final(root)
    assert result.returncode == 1 and "spacing or shape differs" in result.stdout
    assert not list((root / "artifacts" / "illustrations_final").glob("*.png"))


# --- the chain ----------------------------------------------------------------------------


def args():
    return CHAIN.parse_args(["--approved-by", "Anurag Yadav"])


def test_TC_157_the_chain_steps_are_in_order_and_the_bscan_step_cites_21_11():
    plan = CHAIN.build_plan(args())
    assert [s.name for s in plan] == ["access_counts", "dry_run", "bscans", "access_counts_after"]
    argv = next(s.argv for s in plan if s.kind == "bscans")
    assert argv[argv.index("--record-set") + 1] == "final"
    assert re.search(r"21\.11", argv[argv.index("--unlock-reason") + 1])
    assert [[f"{f}_holdout", "test"] for f in sandbox.FOLDS] == CHAIN.MAY_OPEN


def test_TC_157_the_expected_counts_are_the_ones_section_21_11_states():
    protocol = (REPO / "docs" / "07_vv_protocol.md").read_text(encoding="utf-8")
    section = protocol.split("### 21.11", 1)[1]
    stated = {
        (f"{fold}_holdout", bucket): int(now)
        for fold, bucket, now in re.findall(
            r"^\| (cirrus|spectralis|topcon) \| `(test|in_domain_ref)` \| \*\*(\d+) → ",
            section,
            re.M,
        )
    }
    assert stated == CHAIN.EXPECTED_COUNTS


def test_TC_157_the_dry_run_completes_in_a_sandbox_and_its_certificate_lists_the_buckets(
    tmp_path, monkeypatch
):
    for key in [k for k in os.environ if k.startswith("COV_CORE")]:
        monkeypatch.delenv(key)  # as clean_environment(): the dry run starts a child process
    plan = CHAIN.build_plan(args())
    steps = CHAIN.dry_run(plan, tmp_path / "sandbox", tmp_path / "logs")
    assert steps == [
        {"name": n, "exit": 0} for n in ("access_counts", "bscans", "access_counts_after")
    ]
    monkeypatch.setattr(sealed, "repository_state", lambda: ("c" * 40, True))
    cert = CHAIN.certificate(steps, plan)
    assert cert["complete"] and cert["commit"] == "c" * 40 and cert["sealed"] == CHAIN.MAY_OPEN
    assert not CHAIN.certificate(steps[:1], plan)["complete"]  # a step missing is not complete


def test_TC_157_a_failed_dry_run_writes_no_certificate_and_runs_no_real_step(tmp_path, monkeypatch):
    monkeypatch.setattr(CHAIN, "REPO", tmp_path)
    monkeypatch.setattr(CHAIN, "refusals", lambda: [])
    monkeypatch.setattr(CHAIN, "access_counts", lambda artifacts: dict(CHAIN.EXPECTED_COUNTS))
    monkeypatch.setattr(sealed, "repository_state", lambda: ("c" * 40, True))
    monkeypatch.setattr(CHAIN, "dry_run", lambda plan, box, logs: [
        {"name": "access_counts", "exit": 0}, {"name": "bscans", "exit": 1}])  # fmt: skip
    real = []
    monkeypatch.setattr(CHAIN, "run_in", lambda *a: real.append(a) or 0)
    assert CHAIN.main(["--approved-by", "Anurag Yadav"]) == 1
    assert real == [] and not (tmp_path / CHAIN.CERTIFICATE).exists()
    status = (tmp_path / CHAIN.STATUS).read_text(encoding="utf-8")
    assert "the dry run did not complete every step" in status


# --- step 3: every script a chain calls has an end-to-end test of its real main --------------

CHAINS = ("10_reevaluate.py", "12_reevaluate_hd95.py", "14_final_reevaluation.py",
          "15_final_bscans.py")  # fmt: skip
END_TO_END = {
    "05_evaluate.py": ("test_saved_predictions.py",
                       "test_TC_155_the_evaluation_script_saves_and_its_written_record_is_reproduced"),
    "compare_evaluation_records.py": ("test_compare_records.py",
                                      "test_TC_127_exit_status_is_0_identical_1_different_2_unreadable"),
    "09_illustrative_bscans.py": ("test_bscans_main.py",
                                  "test_TC_146_main_regenerates_gates_and_saves_on_synthetic_scans"),
}  # fmt: skip


def scripts_called(chain_file: str) -> set[str]:
    module = load(f"chain_{chain_file[:2]}", REPO / "scripts" / chain_file)
    plan = module.build_plan(module.parse_args(["--approved-by", "a"]))
    return {
        Path(arg).name
        for step in plan
        if step.argv
        for arg in step.argv
        if str(arg).endswith(".py")
    }


def test_TC_157_every_script_a_chain_calls_has_an_end_to_end_test_of_its_main():
    called = set().union(*(scripts_called(c) for c in CHAINS))
    assert called == set(END_TO_END), f"called {sorted(called)}; map every one to its test"
    for script, (file, name) in END_TO_END.items():
        tree = ast.parse((REPO / "tests" / file).read_text(encoding="utf-8"))
        test = next(
            (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name), None
        )
        assert test is not None, f"{file}::{name} is gone"
        calls = [n for n in ast.walk(test) if isinstance(n, ast.Call)
                 and getattr(n.func, "attr", None) == "main"]  # fmt: skip
        assert calls, f"{file}::{name} never calls {script}'s main"
