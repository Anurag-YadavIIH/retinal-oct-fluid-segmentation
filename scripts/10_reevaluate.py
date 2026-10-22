"""Re-evaluate all three folds after the inversion fix, exactly as `docs/07` §17.11 says.

Traces to: SRS-096 (and SRS-088, SRS-090, SRS-091 through the scripts it calls)

**Launched by the author** from an interactive terminal kept open (`docs/07` §17.8). Never run
by Claude Code, and never as a tool call a time limit can kill. It runs once: it refuses to
start if its own status log already records a start.

The order is §17.11's, and the chain stops at the first failure without retrying a step:

  0. Pre-flight refusals: the working tree is dirty, the inversion fix (`3c085a1`) is not an
     ancestor of `HEAD`, a checkpoint is missing, any output already exists, or the chain has
     run before. Nothing is unlocked and nothing is written but the refusal.
  1. **Access counts.** `sealed.access_count` for all six sealed buckets must equal the counts
     §17.11 states. Any difference stops the chain before any evaluation; the difference is
     for the author to record first.
  2. **The reproducibility check.** Two seeded evaluations of `cirrus_holdout`'s open `val`
     bucket. Both must carry the SRS-091 determinism report and compare IDENTICAL under
     SRS-090, or **no sealed bucket is unlocked.**
  3. The open `val` buckets of `spectralis_holdout` and `topcon_holdout`, for §19.2.
  4. The six sealed buckets, `test` then `in_domain_ref` for each fold, each opened with an
     `Unlock` whose reason names §17.11, §17.7(b) and the defect.

**Outputs are new files only**, under a `corrected/` folder of each run directory. The records
of 2026-10-01 and 2026-10-04/05 are never touched. Each step logs its stdout and stderr to its
own files under `artifacts/chain/`, and appends start, end and exit code to
`artifacts/chain/reeval_status.txt`, which is appended to and never truncated.

Usage, from the repository root:
    .venv\\Scripts\\python.exe scripts\\10_reevaluate.py --approved-by "Anurag Yadav"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIX_COMMIT = "3c085a1"
SECTION = "docs/07 section 17.11"
CHAIN_DIR = Path("artifacts") / "chain"
STATUS = CHAIN_DIR / "reeval_status.txt"
MARKER = "REEVAL CHAIN START"

# fold -> run directory, as evaluated on 2026-10-04/05 (docs/08 section 5g.1).
RUNS = {
    "cirrus_holdout": Path("artifacts/runs/cirrus_holdout_stage2"),
    "spectralis_holdout": Path("artifacts/runs/spectralis_holdout_stage3"),
    "topcon_holdout": Path("artifacts/runs/topcon_holdout_stage3"),
}
# The "now" column of docs/07 section 17.11. TC-137 checks this against the document.
EXPECTED_COUNTS = {
    ("cirrus_holdout", "test"): 4,
    ("cirrus_holdout", "in_domain_ref"): 3,
    ("spectralis_holdout", "test"): 2,
    ("spectralis_holdout", "in_domain_ref"): 1,
    ("topcon_holdout", "test"): 2,
    ("topcon_holdout", "in_domain_ref"): 1,
}
SEALED_ORDER = ("test", "in_domain_ref")
REASON = (
    f"re-evaluation under {SECTION} and section 17.7(b); defect: invert_axial_resample "
    f"resized padded frames without removing the padding (docs/13 2026-10-16), fixed by "
    f"{FIX_COMMIT}; no change to model, checkpoint, threshold or metric definitions"
)


@dataclass(frozen=True)
class Step:
    """One step of the chain. `argv` is None for a check the chain performs itself."""

    name: str
    kind: str  # "counts", "open", "seeded_check", "compare" or "sealed"
    argv: tuple[str, ...] | None = None
    output: Path | None = None
    inputs: tuple[Path, ...] = field(default_factory=tuple)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--approved-by",
        required=True,
        help="the approver named in every Unlock (SRS-088); required, never defaulted",
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


def corrected(run: Path, name: str) -> Path:
    return run / "corrected" / name


def evaluate_argv(python: str, run: Path, bucket: str, output: Path) -> tuple[str, ...]:
    return (python, "-u", "scripts/05_evaluate.py", "--run", str(run), "--bucket", bucket,
            "--output", str(output))  # fmt: skip


def build_plan(args: argparse.Namespace) -> list[Step]:
    """Every step, in §17.11's order. Builds commands only; runs nothing."""
    cirrus = RUNS["cirrus_holdout"]
    val_a = corrected(cirrus, "evaluation_val_seeded_a.json")
    val_b = corrected(cirrus, "evaluation_val_seeded_b.json")
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
    for fold in ("spectralis_holdout", "topcon_holdout"):
        output = corrected(RUNS[fold], "evaluation_val.json")
        plan.append(
            Step(
                f"{fold}_val", "open", evaluate_argv(args.python, RUNS[fold], "val", output), output
            )
        )
    for fold, run in RUNS.items():
        for bucket in SEALED_ORDER:
            output = corrected(run, f"evaluation_{bucket}.json")
            argv = evaluate_argv(args.python, run, bucket, output) + (
                "--unlock-bucket", "--unlock-reason", REASON, "--approved-by", args.approved_by,
            )  # fmt: skip
            plan.append(Step(f"{fold}_{bucket}", "sealed", argv, output))
    return plan


def access_count_differences(root: Path | None = None) -> list[str]:
    """Every sealed bucket whose recorded count is not the one §17.11 states."""
    from ocuval.eval import sealed

    differences = []
    for (fold, bucket), expected in EXPECTED_COUNTS.items():
        found = sealed.access_count(bucket, fold_id=fold, root=root)
        if found != expected:
            differences.append(f"{fold} {bucket}: access_count {found}, §17.11 states {expected}")
    return differences


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)


def refusals(plan: list[Step]) -> list[str]:
    found = []
    status = REPO / STATUS
    if status.is_file() and MARKER in status.read_text(encoding="utf-8"):
        found.append(f"{STATUS} already records {MARKER}; this chain never runs twice")
    if git("status", "--porcelain").stdout.strip():
        found.append("the working tree is not clean")
    if git("merge-base", "--is-ancestor", FIX_COMMIT, "HEAD").returncode != 0:
        found.append(f"the inversion fix {FIX_COMMIT} is not an ancestor of HEAD")
    for run in RUNS.values():
        if not (REPO / run / "best.pt").is_file():
            found.append(f"{run} has no best.pt")
    for step in plan:
        if step.output is not None and (REPO / step.output).exists():
            found.append(f"{step.output} exists; no earlier output is ever overwritten")
    if list((REPO / CHAIN_DIR).glob("reeval_*.log")):
        found.append(f"reeval_* logs already exist in {CHAIN_DIR}")
    return found


def log(message: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}"
    with (REPO / STATUS).open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


def run_step(step: Step) -> int:
    out = REPO / CHAIN_DIR / f"reeval_{step.name}.out.log"
    err = REPO / CHAIN_DIR / f"reeval_{step.name}.err.log"
    log(f"START {step.name}")
    with out.open("w", encoding="utf-8") as stdout, err.open("w", encoding="utf-8") as stderr:
        code = subprocess.run(step.argv, cwd=REPO, stdout=stdout, stderr=stderr, check=False)
    log(f"END   {step.name} exit {code.returncode}")
    return code.returncode


def both_seeded(paths: tuple[Path, ...]) -> bool:
    """Both records carry the SRS-091 determinism report and per-volume seeds."""
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
    log(f"{MARKER} at {git('rev-parse', 'HEAD').stdout.strip()}")

    for step in plan:
        if step.kind == "counts":
            differences = access_count_differences(REPO / "artifacts")
            if differences:
                for difference in differences:
                    log(f"COUNT DIFFERS {difference}")
                return stop("access counts differ from docs/07 section 17.11; record first")
            log("ACCESS COUNTS as section 17.11 states")
        elif step.kind == "seeded_check":
            if not both_seeded(step.inputs):
                return stop("a reproducibility record is not seeded; no sealed bucket unlocked")
        elif step.kind == "compare":
            code = run_step(step)
            if code != 0:
                outcome = "DIFFER" if code == 1 else f"exit {code}"
                return stop(f"reproducibility check {outcome}; no sealed bucket unlocked")
            log("REPRODUCIBILITY IDENTICAL")
        else:
            code = run_step(step)
            if code != 0:
                return stop(f"{step.name} exited {code}")
    log("CHAIN END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
