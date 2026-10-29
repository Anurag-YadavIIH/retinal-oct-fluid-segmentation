"""The final re-evaluation after the audit of 2026-10-28 (`docs/07` §17.13), with the B-scans.

Traces to: SRS-105, SRS-106 (and SRS-088, SRS-090, SRS-091, SRS-093 through the scripts it calls)

**Launched by the author** from an interactive terminal kept open (`docs/07` §17.8). Never run
by Claude Code, and never as a tool call a time limit can kill. It runs once: it refuses to
start if its own status log already records a start.

The order is §17.13's, and the chain stops at the first failure without retrying a step:

  0. Pre-flight refusals: a dirty tree; **any fix §17.13 names absent**, checked by behaviour
     (D1 placement against integer arithmetic, D4 content box, D5 spacing source, D3 secondary
     block); a checkpoint or previous record missing; any output present, saved predictions
     included; a previous start; less free space than the saved maps could take uncompressed.
  1. **Access counts**: the six sealed buckets must have exactly the counts §17.13 states.
  2. **The reproducibility check**: two seeded evaluations of `cirrus_holdout`'s open `val`
     bucket must compare IDENTICAL (SRS-090), and the first must pass the gate.
  3. The open `val` buckets of `spectralis_holdout` and `topcon_holdout`, each gated.
  4. The six sealed buckets, `test` then `in_domain_ref` per fold, each with an `Unlock`
     naming §17.13 and §17.7(b), **each followed by the gate**: the population and the
     reference must equal the bucket's previous record, or the chain stops before the next
     unlock. Every metric may change; who and what was measured may not.
  5. The six illustrative B-scans of §21.10, from the new held-out records.
  6. **Access counts after**: each sealed bucket one more than in step 1, and each `test`
     bucket holding a chosen scan one more again.

**Every evaluation saves its label maps (SRS-106)** under
`artifacts/predictions_final/<fold>/<bucket>/`, and every gate also checks them against the
record's manifest: one file per measured volume, each matching its SHA-256. They are local
derived data (`docs/06` DMP-C13), never uploaded.

**Outputs are new files only**, under `audited/` of each run directory, in
`artifacts/predictions_final/` and in `artifacts/illustrations_audited/`. Each step logs its
stdout and stderr under `artifacts/chain/`, and appends to `artifacts/chain/audited_status.txt`,
which is never truncated.

Usage, from the repository root:
    .venv\\Scripts\\python.exe scripts\\14_final_reevaluation.py --approved-by "Anurag Yadav"
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SECTION = "docs/07 section 17.13"
CHAIN_DIR = Path("artifacts") / "chain"
STATUS = CHAIN_DIR / "audited_status.txt"
MARKER = "AUDITED CHAIN START"
OUT_DIR = "audited"
ILLUSTRATIONS = Path("artifacts") / "illustrations_audited"
PREDICTIONS = Path("artifacts") / "predictions_final"
# The largest acquisition, cirrus: 128 B-scans of 1024 x 512 uint8 (docs/06 section 3.1). The
# space refusal assumes every map is this size and none compresses: an upper bound, not an estimate.
MAX_MAP_BYTES = 128 * 1024 * 512

RUNS = {
    "cirrus_holdout": Path("artifacts/runs/cirrus_holdout_stage2"),
    "spectralis_holdout": Path("artifacts/runs/spectralis_holdout_stage3"),
    "topcon_holdout": Path("artifacts/runs/topcon_holdout_stage3"),
}
# The "now" column of docs/07 section 17.13. TC-154 checks this against the document.
EXPECTED_COUNTS = {
    ("cirrus_holdout", "test"): 7,
    ("cirrus_holdout", "in_domain_ref"): 5,
    ("spectralis_holdout", "test"): 5,
    ("spectralis_holdout", "in_domain_ref"): 3,
    ("topcon_holdout", "test"): 5,
    ("topcon_holdout", "in_domain_ref"): 3,
}
SEALED_ORDER = ("test", "in_domain_ref")
# The previous record of each bucket, which the gate compares with.
PREVIOUS = {"sealed": "corrected_hd95", "cirrus_val": "corrected_hd95", "other_val": "corrected"}
REASON = (
    f"final re-evaluation under {SECTION} and section 17.7(b), after the audit of 2026-10-28: "
    "inversion (D1) and detection score (D4) fixed in the evaluation code; gated on the "
    "population and reference being unchanged; no change to model, checkpoint, threshold or "
    "metric definitions"
)
REASON_21 = (
    f"illustrative B-scans under {SECTION} and docs/07 section 21 (21.10), from the new "
    "held-out records; for illustration only, not an evaluation"
)
# What the gate holds fixed at the top of a record.
TOP_LEVEL = ("fold_id", "bucket", "n_patients", "n_volumes", "vendors", "unit_of_measurement",
             "bootstrap", "presence_voxel_threshold", "mc_passes")  # fmt: skip


@dataclass(frozen=True)
class Step:
    name: str
    kind: str  # counts, open, seeded_check, compare, gate, sealed, bscans or counts_after
    argv: tuple[str, ...] | None = None
    output: Path | None = None
    inputs: tuple[Path, ...] = field(default_factory=tuple)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--approved-by",
        required=True,
        help="the approver named in every Unlock (SRS-088); never defaulted",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="the interpreter for each evaluation (default: this one)",
    )
    args = parser.parse_args(argv)
    if not args.approved_by.strip():
        parser.error("--approved-by must name the approver")
    return args


def predictions_folder(fold: str, output: Path) -> Path:
    """`artifacts/predictions_final/<fold>/<bucket>`, the bucket named as the record is."""
    return PREDICTIONS / fold / output.stem.removeprefix("evaluation_")


def evaluate_argv(python: str, fold: str, bucket: str, output: Path) -> tuple[str, ...]:
    return (python, "-u", "scripts/05_evaluate.py", "--run", str(RUNS[fold]), "--bucket", bucket,
            "--output", str(output), "--save-predictions",
            str(predictions_folder(fold, output)))  # fmt: skip


def build_plan(args: argparse.Namespace) -> list[Step]:
    """Every step, in §17.13's order. Builds commands only; runs nothing."""
    cirrus = RUNS["cirrus_holdout"]
    val_a = cirrus / OUT_DIR / "evaluation_val.json"
    val_b = cirrus / OUT_DIR / "evaluation_val_seeded_b.json"
    plan = [
        Step("access_counts", "counts"),
        Step(
            "cirrus_val_a",
            "open",
            evaluate_argv(args.python, "cirrus_holdout", "val", val_a),
            val_a,
        ),
        Step(
            "cirrus_val_b",
            "open",
            evaluate_argv(args.python, "cirrus_holdout", "val", val_b),
            val_b,
        ),
        Step("reproducibility_seeded", "seeded_check", inputs=(val_a, val_b)),
        Step(
            "reproducibility_compare",
            "compare",
            (args.python, "-u", "scripts/compare_evaluation_records.py", str(val_a), str(val_b)),
            inputs=(val_a, val_b),
        ),
        Step(
            "cirrus_val_gate",
            "gate",
            inputs=(cirrus / PREVIOUS["cirrus_val"] / "evaluation_val_seeded_a.json", val_a),
        ),  # fmt: skip
    ]
    for fold in ("spectralis_holdout", "topcon_holdout"):
        run = RUNS[fold]
        output = run / OUT_DIR / "evaluation_val.json"
        base = run / PREVIOUS["other_val"] / "evaluation_val.json"
        plan.append(Step(f"{fold}_val", "open", evaluate_argv(args.python, fold, "val", output),
                         output))  # fmt: skip
        plan.append(Step(f"{fold}_val_gate", "gate", inputs=(base, output)))
    for fold, run in RUNS.items():
        for bucket in SEALED_ORDER:
            output = run / OUT_DIR / f"evaluation_{bucket}.json"
            base = run / PREVIOUS["sealed"] / f"evaluation_{bucket}.json"
            argv = evaluate_argv(args.python, fold, bucket, output) + (
                "--unlock-bucket", "--unlock-reason", REASON, "--approved-by", args.approved_by,
            )  # fmt: skip
            plan.append(Step(f"{fold}_{bucket}", "sealed", argv, output))
            plan.append(Step(f"{fold}_{bucket}_gate", "gate", inputs=(base, output)))
    bscans = (args.python, "-u", "scripts/09_illustrative_bscans.py", "--record-set", "audited",
              "--unlock-reason", REASON_21, "--approved-by", args.approved_by,
              "--output-dir", str(ILLUSTRATIONS))  # fmt: skip
    plan.append(Step("bscans", "bscans", bscans, ILLUSTRATIONS))
    plan.append(Step("access_counts_after", "counts_after"))
    return plan


# --- the gate ------------------------------------------------------------------------------


def population(record: dict) -> dict:
    """What §17.13 holds fixed: who and what was measured, never how well."""
    rows = {
        (r["patient_id"], r.get("sample_id"), r["fluid_class"]):
            (r["reference_present"], r["reference_voxels"])
        for r in record["per_volume"]
    }  # fmt: skip
    counts = {
        (vendor, cls): (entry["auroc"]["positives"], entry["auroc"]["negatives"])
        for vendor, by_class in record["detection"].items()
        for cls, entry in by_class.items()
    }
    return {
        "top": {key: record.get(key) for key in TOP_LEVEL},
        "rows": rows,
        "n_rows": len(record["per_volume"]),
        "auroc_counts": counts,
    }


def population_differences(previous: dict, new: dict) -> list[str]:
    """Every difference in the population or the reference (SRS-105). Metrics are not read."""
    a, b = population(previous), population(new)
    found = [f"{key}: {a['top'][key]!r} -> {b['top'][key]!r}"
             for key in TOP_LEVEL if a["top"][key] != b["top"][key]]  # fmt: skip
    if a["n_rows"] != b["n_rows"]:
        found.append(f"per-volume rows: {a['n_rows']} -> {b['n_rows']}")
    for key in sorted(set(a["rows"]) | set(b["rows"]), key=str):
        if a["rows"].get(key) != b["rows"].get(key):
            found.append(f"row {key[2]} of a volume: {a['rows'].get(key)} -> {b['rows'].get(key)}")
    for key in sorted(set(a["auroc_counts"]) | set(b["auroc_counts"])):
        if a["auroc_counts"].get(key) != b["auroc_counts"].get(key):
            found.append(f"AUROC +/- {key}: {a['auroc_counts'].get(key)} -> "
                         f"{b['auroc_counts'].get(key)}")  # fmt: skip
    return found


def saved_prediction_problems(record: dict, root: Path) -> list[str]:
    """SRS-106: the record's manifest names exactly its volumes, and every file matches."""
    from ocuval.eval.predictions import manifest_problems

    folder = record.get("notes", {}).get("predictions_directory")
    if "predictions" not in record or not folder:
        return ["the record carries no prediction manifest"]
    return manifest_problems(record["predictions"], root / folder, record["per_volume"])


# --- refusals and running ------------------------------------------------------------------


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def d1_fixed() -> bool:
    """A band through the real chain and inversion lands where integer arithmetic puts it."""
    import numpy as np
    import yaml

    from ocuval.data.transforms import axial_target, eval_transforms, invert_axial_resample

    cfg = yaml.safe_load((REPO / "configs" / "train_seg.yaml").read_text(encoding="utf-8"))
    rows, spacing = 1024, (0.001955, 0.011742, 0.046878)  # cirrus, docs/06 section 3.1
    label = np.zeros((rows, 16), dtype=np.uint8)
    label[401:404, :] = 1
    out = eval_transforms(cfg)({"image": label.astype(np.float32), "label": label,
                                "intensity_window": (0.0, 1.0), "spacing_mm": spacing})  # fmt: skip
    target = axial_target(cfg)
    back = invert_axial_resample(np.asarray(out["label"]), spacing, label.shape,
                                 target_axial_mm=target)[0]  # fmt: skip
    prepared = int(round(rows * spacing[0] / target))
    src = (np.arange(prepared) * rows) // prepared
    distance = np.abs(np.arange(rows)[:, None] - src[None, :])
    nearest = distance == distance.min(axis=1, keepdims=True)
    tied_even = nearest & (np.arange(prepared)[None, :] % 2 == 0)
    cell = np.where(nearest.sum(axis=1) > 1, tied_even.argmax(axis=1), nearest.argmax(axis=1))
    return bool(np.array_equal(back, label[src][cell]))


def d4_fixed() -> bool:
    evaluation = load_script("evaluate_for_chain", "05_evaluate.py")
    return "box" in inspect.signature(evaluation.predict_volume).parameters


def d5_fixed() -> bool:
    source = (REPO / "scripts" / "05_evaluate.py").read_text(encoding="utf-8")
    return 'assert_spacing_unchanged(native.spacing_mm, row["spacing_mm"]' in source


def d3_fixed() -> bool:
    from ocuval.eval import pipeline

    return hasattr(pipeline, "secondary_hd95") and "segmentation_secondary" in inspect.getsource(
        pipeline.evaluate
    )


FIX_CHECKS = {"D1": d1_fixed, "D4": d4_fixed, "D5": d5_fixed, "D3": d3_fixed}


def missing_fixes() -> list[str]:
    return [name for name, check in FIX_CHECKS.items() if not check()]


def access_counts(root: Path) -> dict[tuple[str, str], int]:
    from ocuval.eval import sealed

    return {key: sealed.access_count(key[1], fold_id=key[0], root=root) for key in EXPECTED_COUNTS}


def expected_after(picked_runs: set[str]) -> dict[tuple[str, str], int]:
    """Each sealed bucket one more; each `test` bucket holding a chosen scan one more again."""
    return {
        (fold, bucket): count + 1 + (bucket == "test" and fold.split("_")[0] in picked_runs)
        for (fold, bucket), count in EXPECTED_COUNTS.items()
    }


def bytes_needed(plan: list[Step], root: Path) -> int:
    """Every map the plan saves at the largest size, uncompressed, counted from the records the
    gates compare with. The second reproducibility run saves as many as the first."""
    bases = {s.inputs[1]: s.inputs[0] for s in plan if s.kind == "gate"}
    total = 0
    for step in plan:
        if step.kind in ("open", "sealed"):
            base = bases.get(step.output) or bases[step.output.with_name("evaluation_val.json")]
            total += json.loads((root / base).read_text(encoding="utf-8"))["n_volumes"]
    return total * MAX_MAP_BYTES


def space_problem(free: int, needed: int) -> str | None:
    if free < needed:
        return (f"{free / 1e9:.1f} GB free on the drive holding artifacts/, and the saved maps "
                f"could take {needed / 1e9:.1f} GB uncompressed (SRS-106)")  # fmt: skip
    return None


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)


def refusals(plan: list[Step]) -> list[str]:
    found = []
    status = REPO / STATUS
    if status.is_file() and MARKER in status.read_text(encoding="utf-8"):
        found.append(f"{STATUS} already records {MARKER}; this chain never runs twice")
    if git("status", "--porcelain").stdout.strip():
        found.append("the working tree is not clean")
    for name in missing_fixes():
        found.append(f"fix {name} is not in this code (checked by its behaviour)")
    for run in RUNS.values():
        if not (REPO / run / "best.pt").is_file():
            found.append(f"{run} has no best.pt")
    for step in plan:
        if step.kind == "gate" and not (REPO / step.inputs[0]).is_file():
            found.append(f"{step.inputs[0]} is missing; the gate has nothing to compare against")
        if step.kind in ("open", "sealed") and (REPO / step.output).exists():
            found.append(f"{step.output} exists; no earlier output is ever overwritten")
    folder = REPO / ILLUSTRATIONS
    if folder.exists() and any(folder.iterdir()):
        found.append(f"{ILLUSTRATIONS} holds files; section 21.10 never overwrites")
    saved = REPO / PREDICTIONS
    if saved.exists() and any(saved.iterdir()):
        found.append(f"{PREDICTIONS} holds files; saved predictions are never overwritten")
    if not any("is missing; the gate" in reason for reason in found):
        free = shutil.disk_usage(REPO / "artifacts").free
        problem = space_problem(free, bytes_needed(plan, REPO))
        if problem:
            found.append(problem)
    if list((REPO / CHAIN_DIR).glob("audited_*.log")):
        found.append(f"audited_* logs already exist in {CHAIN_DIR}")
    return found


def log(message: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}"
    with (REPO / STATUS).open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


def run_step(step: Step) -> int:
    out = REPO / CHAIN_DIR / f"audited_{step.name}.out.log"
    err = REPO / CHAIN_DIR / f"audited_{step.name}.err.log"
    log(f"START {step.name}")
    with out.open("w", encoding="utf-8") as stdout, err.open("w", encoding="utf-8") as stderr:
        code = subprocess.run(step.argv, cwd=REPO, stdout=stdout, stderr=stderr, check=False)
    log(f"END   {step.name} exit {code.returncode}")
    return code.returncode


def both_seeded(paths: tuple[Path, ...]) -> bool:
    for path in paths:
        notes = json.loads((REPO / path).read_text(encoding="utf-8")).get("notes", {})
        if not {"determinism", "mc_dropout_seeds"} <= set(notes):
            return False
    return True


def stop(why: str) -> int:
    log(f"CHAIN STOPPED: {why}")
    log("CHAIN END")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = build_plan(args)
    refused = refusals(plan)
    if refused:
        for reason in refused:
            print(f"!! refused: {reason}", file=sys.stderr)
        return 2
    (REPO / CHAIN_DIR).mkdir(parents=True, exist_ok=True)
    for run in RUNS.values():
        (REPO / run / OUT_DIR).mkdir(exist_ok=True)
    log(f"{MARKER} at {git('rev-parse', 'HEAD').stdout.strip()}")

    for step in plan:
        if step.kind == "counts":
            found = access_counts(REPO / "artifacts")
            if found != EXPECTED_COUNTS:
                for key, value in found.items():
                    log(f"COUNT {key}: {value}, section 17.13 states {EXPECTED_COUNTS[key]}")
                return stop("access counts differ from docs/07 section 17.13; record first")
            log("ACCESS COUNTS as section 17.13 states")
        elif step.kind == "seeded_check":
            if not both_seeded(step.inputs):
                return stop("a reproducibility record is not seeded; no sealed bucket unlocked")
        elif step.kind == "compare":
            code = run_step(step)
            if code != 0:
                outcome = "DIFFER" if code == 1 else f"exit {code}"
                return stop(f"reproducibility check {outcome}; no sealed bucket unlocked")
            log("REPRODUCIBILITY IDENTICAL")
        elif step.kind == "gate":
            base, new = (json.loads((REPO / p).read_text(encoding="utf-8")) for p in step.inputs)
            differences = population_differences(base, new)
            if differences:
                for difference in differences[:50]:
                    log(f"GATE DIFFERS {difference}")
                return stop(f"{step.name}: the population or the reference changed")
            problems = saved_prediction_problems(new, REPO)
            if problems:
                for problem in problems[:50]:
                    log(f"SAVED PREDICTIONS {problem}")
                return stop(f"{step.name}: the saved predictions do not match the record")
            log(f"GATE PASSED {step.name}: population and reference unchanged; "
                f"{len(new['predictions']['files'])} saved maps match the manifest")  # fmt: skip
        elif step.kind == "counts_after":
            selection = json.loads((REPO / ILLUSTRATIONS / "selection.json").read_text("utf-8"))
            picked = {p["run"] for p in selection["picks"]}
            found, want = access_counts(REPO / "artifacts"), expected_after(picked)
            for key, value in found.items():
                log(f"COUNT AFTER {key}: {value} (expected {want[key]})")
            if found != want:
                return stop("access counts after differ from section 17.13's rule; examine the log")
            log("ACCESS COUNTS AFTER as section 17.13 states")
        else:
            code = run_step(step)
            if code != 0:
                return stop(f"{step.name} exited {code}")
    log("CHAIN END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
