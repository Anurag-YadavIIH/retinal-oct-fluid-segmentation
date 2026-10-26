"""Re-evaluate the six sealed buckets for HD95 after the spacing-axis fix (`docs/07` §17.12).

Traces to: SRS-102 (and SRS-088, SRS-090, SRS-091 through the scripts it calls)

**Launched by the author** from an interactive terminal kept open (`docs/07` §17.8). Never run
by Claude Code, and never as a tool call a time limit can kill. It runs once: it refuses to
start if its own status log already records a start.

The order is §17.12's, and the chain stops at the first failure without retrying a step:

  0. Pre-flight refusals: the working tree is dirty, **the HD95 fix is absent** (checked by its
     behaviour: a one-B-scan shift through `measure_volume` must score exactly the separation),
     a checkpoint or a 24 October corrected record is missing, any output already exists, or
     the chain has run before. Nothing is unlocked and nothing is written but the refusal.
  1. **Access counts**: the six sealed buckets must have exactly the counts §17.12 states.
  2. **The reproducibility check**: two seeded evaluations of `cirrus_holdout`'s open `val`
     bucket must compare IDENTICAL (SRS-090), or no sealed bucket is unlocked.
  3. The six sealed buckets, `test` then `in_domain_ref` per fold, each with an `Unlock`
     naming §17.12, §17.7(b) and the defect, **each followed by the gate**: every value of the
     new record other than HD95 must equal the 24 October corrected record exactly, or the
     chain stops before the next unlock. Only HD95 may change.

**Outputs are new files only**, under `corrected_hd95/` of each run directory. Each step logs its
stdout and stderr under `artifacts/chain/`, and appends to `artifacts/chain/hd95_status.txt`,
which is appended to and never truncated.

Usage, from the repository root:
    .venv\\Scripts\\python.exe scripts\\12_reevaluate_hd95.py --approved-by "Anurag Yadav"
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SECTION = "docs/07 section 17.12"
CHAIN_DIR = Path("artifacts") / "chain"
STATUS = CHAIN_DIR / "hd95_status.txt"
MARKER = "HD95 CHAIN START"
OUT_DIR = "corrected_hd95"
BASE_DIR = "corrected"

RUNS = {
    "cirrus_holdout": Path("artifacts/runs/cirrus_holdout_stage2"),
    "spectralis_holdout": Path("artifacts/runs/spectralis_holdout_stage3"),
    "topcon_holdout": Path("artifacts/runs/topcon_holdout_stage3"),
}
# The "now" column of docs/07 section 17.12. TC-150 checks this against the document.
EXPECTED_COUNTS = {
    ("cirrus_holdout", "test"): 6,
    ("cirrus_holdout", "in_domain_ref"): 4,
    ("spectralis_holdout", "test"): 4,
    ("spectralis_holdout", "in_domain_ref"): 2,
    ("topcon_holdout", "test"): 4,
    ("topcon_holdout", "in_domain_ref"): 2,
}
SEALED_ORDER = ("test", "in_domain_ref")
REASON = (
    f"HD95 re-evaluation under {SECTION} and section 17.7(b); defect: measure_volume passed "
    "the spacing in (axial, lateral, separation) order to a per-axis HD95 on (B-scan, row, "
    "column) arrays (docs/13 2026-10-25); only HD95 may change, gated against the 24 October "
    "corrected records; no change to model, checkpoint, threshold or other metric definitions"
)
# Ignored by the gate: the run's own provenance, as SRS-090 ignores it.
PROVENANCE = frozenset({"utc", "notes", "bucket_access_count"})


@dataclass(frozen=True)
class Step:
    name: str
    kind: str  # "counts", "open", "seeded_check", "compare", "sealed" or "gate"
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


def evaluate_argv(python: str, run: Path, bucket: str, output: Path) -> tuple[str, ...]:
    return (python, "-u", "scripts/05_evaluate.py", "--run", str(run), "--bucket", bucket,
            "--output", str(output))  # fmt: skip


def build_plan(args: argparse.Namespace) -> list[Step]:
    """Every step, in §17.12's order. Builds commands only; runs nothing."""
    cirrus = RUNS["cirrus_holdout"]
    val_a = cirrus / OUT_DIR / "evaluation_val_seeded_a.json"
    val_b = cirrus / OUT_DIR / "evaluation_val_seeded_b.json"
    plan = [
        Step("access_counts", "counts"),
        Step("cirrus_val_a", "open", evaluate_argv(args.python, cirrus, "val", val_a), val_a),
        Step("cirrus_val_b", "open", evaluate_argv(args.python, cirrus, "val", val_b), val_b),
        Step("reproducibility_seeded", "seeded_check", inputs=(val_a, val_b)),
        Step(
            "reproducibility_compare",
            "compare",
            (args.python, "-u", "scripts/compare_evaluation_records.py", str(val_a), str(val_b)),
            inputs=(val_a, val_b),
        ),
    ]
    for fold, run in RUNS.items():
        for bucket in SEALED_ORDER:
            output = run / OUT_DIR / f"evaluation_{bucket}.json"
            base = run / BASE_DIR / f"evaluation_{bucket}.json"
            argv = evaluate_argv(args.python, run, bucket, output) + (
                "--unlock-bucket", "--unlock-reason", REASON, "--approved-by", args.approved_by,
            )  # fmt: skip
            plan.append(Step(f"{fold}_{bucket}", "sealed", argv, output))
            plan.append(Step(f"{fold}_{bucket}_gate", "gate", inputs=(base, output)))
    return plan


# --- the gate ------------------------------------------------------------------------------


def _leaves(node: Any, path: str = ""):
    """Every scalar, keyed by path, with list lengths; skips provenance and any `hd95` key."""
    if isinstance(node, dict):
        for key in sorted(node):
            if (path == "" and key in PROVENANCE) or key == "hd95":
                continue
            yield from _leaves(node[key], f"{path}/{key}")
    elif isinstance(node, list):
        yield f"{path}#len", len(node)
        for index, item in enumerate(node):
            yield from _leaves(item, f"{path}[{index}]")
    else:
        yield path, node


def _same(a: Any, b: Any) -> bool:
    """Exact equality, NaN on both sides counting as the same undefined result (SRS-090)."""
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


def non_hd95_differences(reference: dict, candidate: dict) -> list[str]:
    """Every difference between two records other than in HD95 or provenance (SRS-102)."""
    ref, cand = dict(_leaves(reference)), dict(_leaves(candidate))
    absent = "<absent>"
    return [
        f"{key}: {ref.get(key, absent)!r} -> {cand.get(key, absent)!r}"
        for key in sorted(set(ref) | set(cand))
        if not _same(ref.get(key, absent), cand.get(key, absent))
    ]


# --- refusals and running ------------------------------------------------------------------


def fix_present() -> bool:
    """The HD95 fix, checked by its behaviour through the real call path."""
    spec = importlib.util.find_spec("ocuval.eval.pipeline")
    if spec is None:
        return False
    import numpy as np

    from ocuval.eval.pipeline import measure_volume

    spacing = (0.0039, 0.0117, 0.047)  # (axial, lateral, separation), all distinct
    reference = np.zeros((6, 12, 12), dtype=np.uint8)
    reference[2, 4:8, 4:8] = 1
    prediction = np.roll(reference, 1, axis=0)  # one B-scan further on
    rows = measure_volume(prediction, reference, spacing, classes=("IRF",))
    hd = next(r["value"] for r in rows if r["metric"] == "hd95")
    return math.isclose(hd, spacing[2], rel_tol=1e-9)


def access_count_differences(root: Path | None = None) -> list[str]:
    from ocuval.eval import sealed

    return [
        f"{fold} {bucket}: access_count {found}, §17.12 states {expected}"
        for (fold, bucket), expected in EXPECTED_COUNTS.items()
        if (found := sealed.access_count(bucket, fold_id=fold, root=root)) != expected
    ]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)


def refusals(plan: list[Step]) -> list[str]:
    found = []
    status = REPO / STATUS
    if status.is_file() and MARKER in status.read_text(encoding="utf-8"):
        found.append(f"{STATUS} already records {MARKER}; this chain never runs twice")
    if git("status", "--porcelain").stdout.strip():
        found.append("the working tree is not clean")
    if not fix_present():
        found.append("the HD95 spacing fix is not in this code (measure_volume self-check)")
    for run in RUNS.values():
        if not (REPO / run / "best.pt").is_file():
            found.append(f"{run} has no best.pt")
    for step in plan:
        if step.kind == "gate" and not (REPO / step.inputs[0]).is_file():
            found.append(f"{step.inputs[0]} is missing; the gate has nothing to compare against")
        if step.output is not None and (REPO / step.output).exists():
            found.append(f"{step.output} exists; no earlier output is ever overwritten")
    if list((REPO / CHAIN_DIR).glob("hd95_*.log")):
        found.append(f"hd95_* logs already exist in {CHAIN_DIR}")
    return found


def log(message: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}"
    with (REPO / STATUS).open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


def run_step(step: Step) -> int:
    out = REPO / CHAIN_DIR / f"hd95_{step.name}.out.log"
    err = REPO / CHAIN_DIR / f"hd95_{step.name}.err.log"
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
            differences = access_count_differences(REPO / "artifacts")
            if differences:
                for difference in differences:
                    log(f"COUNT DIFFERS {difference}")
                return stop("access counts differ from docs/07 section 17.12; record first")
            log("ACCESS COUNTS as section 17.12 states")
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
            differences = non_hd95_differences(base, new)
            if differences:
                for difference in differences[:50]:
                    log(f"GATE DIFFERS {difference}")
                return stop(f"{step.name}: {len(differences)} value(s) other than HD95 changed")
            log(f"GATE PASSED {step.name}: only HD95 differs from the 24 October record")
        else:
            code = run_step(step)
            if code != 0:
                return stop(f"{step.name} exited {code}")
    log("CHAIN END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
