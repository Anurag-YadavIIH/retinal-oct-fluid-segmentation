"""The illustrative B-scans of `docs/07` §21.11, from the saved maps, behind a mandatory dry run.

Traces to: SRS-107, SRS-108 (and SRS-088, SRS-093, SRS-106 through the script it calls)

**Launched by the author** from an interactive terminal kept open (`docs/07` §17.8). Never run
by Claude Code. It runs once: it refuses to start if its own status log already records a start.
It needs no GPU: the maps are the ones the final run saved, checked by checksum (SRS-106).

The order, stopping at the first failure without retrying a step:

  0. Refusals: a dirty tree; a previous start; output already present; a held-out record or
     its saved-map folder missing.
  1. **Access counts**: the six sealed buckets must have exactly the counts §21.11 states.
  2. **The dry run (SRS-107)**: a sandbox of synthetic records, saved maps and archives is
     built in a temporary folder, and every step of this chain runs there, through the same
     script and arguments. Only if every step completes is the certificate written, and only
     with it will the SRS-088 gate open a real bucket.
  3. **The B-scans**: `09_illustrative_bscans.py --record-set final`, with the certificate.
  4. **Access counts after**: each `test` bucket holding a pick one more than in step 1.

Each step logs under `artifacts/chain/final_bscans_*`; the status log
`artifacts/chain/final_bscans_status.txt` is appended to and never truncated.

Usage, from the repository root:
    .venv\\Scripts\\python.exe scripts\\15_final_bscans.py --approved-by "Anurag Yadav"
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHAIN = "final_bscans"
CHAIN_DIR = Path("artifacts") / "chain"
STATUS = CHAIN_DIR / f"{CHAIN}_status.txt"
MARKER = "FINAL BSCANS CHAIN START"
CERTIFICATE = CHAIN_DIR / f"dryrun_{CHAIN}.json"
OUTPUT = Path("artifacts") / "illustrations_final"
FOLDS = ("cirrus", "spectralis", "topcon")
# The counts docs/07 section 21.11 states, read from the log after section 17.13. TC-157
# checks this against the document.
EXPECTED_COUNTS = {
    ("cirrus_holdout", "test"): 9,
    ("cirrus_holdout", "in_domain_ref"): 6,
    ("spectralis_holdout", "test"): 7,
    ("spectralis_holdout", "in_domain_ref"): 4,
    ("topcon_holdout", "test"): 7,
    ("topcon_holdout", "in_domain_ref"): 4,
}
# The buckets this chain may open, and so the buckets its certificate lists.
MAY_OPEN = [[f"{fold}_holdout", "test"] for fold in FOLDS]
REASON = (
    "illustrative B-scans under docs/07 section 21 (21.11), drawn from the label maps the final "
    "run of section 17.13 saved, checked by SHA-256; no model, no GPU; for illustration only, "
    "not an evaluation"
)


@dataclass(frozen=True)
class Step:
    name: str
    kind: str  # counts, dry_run, bscans or counts_after
    argv: tuple[str, ...] | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--approved-by", required=True, help="named in every Unlock; never defaulted"
    )
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)
    if not args.approved_by.strip():
        parser.error("--approved-by must name the approver")
    return args


def bscans_argv(python: str, approved_by: str) -> tuple[str, ...]:
    return (python, "-u", str(REPO / "scripts" / "09_illustrative_bscans.py"),
            "--record-set", "final", "--unlock-reason", REASON, "--approved-by", approved_by,
            "--output-dir", str(OUTPUT))  # fmt: skip


def build_plan(args: argparse.Namespace) -> list[Step]:
    return [
        Step("access_counts", "counts"),
        Step("dry_run", "dry_run"),
        Step("bscans", "bscans", bscans_argv(args.python, args.approved_by)),
        Step("access_counts_after", "counts_after"),
    ]


# --- counts --------------------------------------------------------------------------------


def access_counts(artifacts: Path) -> dict[tuple[str, str], int]:
    from ocuval.eval import sealed

    return {k: sealed.access_count(k[1], fold_id=k[0], root=artifacts) for k in EXPECTED_COUNTS}


def picked_runs(root: Path) -> set[str]:
    selection = json.loads((root / OUTPUT / "selection.json").read_text(encoding="utf-8"))
    return {p["run"] for p in selection["picks"]}


def expected_after(before: dict, picked: set[str]) -> dict[tuple[str, str], int]:
    """Each `test` bucket holding a pick one more; every other count unchanged."""
    return {
        (fold, bucket): count + (bucket == "test" and fold.split("_")[0] in picked)
        for (fold, bucket), count in before.items()
    }


def outputs_complete(root: Path) -> bool:
    """The B-scan step's gate passed and saved one image per pick."""
    folder = root / OUTPUT
    if not (folder / "selection.json").is_file():
        return False
    selection = json.loads((folder / "selection.json").read_text(encoding="utf-8"))
    images = sorted(p.name for p in folder.glob("bscan_*.png"))
    return selection["gate"] == "passed" and images == sorted(
        f"bscan_{p['role']}.png" for p in selection["picks"]
    )


# --- the dry run (SRS-107) -----------------------------------------------------------------


def run_in(step: Step, root: Path, env: dict, logs: Path) -> int:
    logs.mkdir(parents=True, exist_ok=True)
    with (
        (logs / f"{step.name}.out.log").open("w", encoding="utf-8") as out,
        (logs / f"{step.name}.err.log").open("w", encoding="utf-8") as err,
    ):
        assert step.argv is not None
        return subprocess.run(step.argv, cwd=root, env=env, stdout=out, stderr=err,
                              check=False).returncode  # fmt: skip


def dry_run(plan: list[Step], sandbox: Path, logs: Path) -> list[dict]:
    """Every step of `plan` in a synthetic sandbox; the record of each, with its exit status.

    The sandbox's counts start at zero, so the count steps check the same rule against them.
    """
    from ocuval import sandbox as synthetic
    from ocuval.eval import sealed

    synthetic.build_final_bscans(sandbox)
    env = {k: v for k, v in os.environ.items() if k != sealed.CERTIFICATE_ENV}
    env["OCUVAL_ARTIFACTS"] = str(sandbox / "artifacts")
    before = access_counts(sandbox / "artifacts")
    record = []
    for step in plan:
        if step.kind == "counts":
            ok = all(v == 0 for v in before.values())
        elif step.kind == "dry_run":
            continue  # this step itself
        elif step.kind == "bscans":
            ok = run_in(step, sandbox, env, logs) == 0 and outputs_complete(sandbox)
        else:
            ok = outputs_complete(sandbox) and access_counts(sandbox / "artifacts") == (
                expected_after(before, picked_runs(sandbox))
            )
        record.append({"name": step.name, "exit": 0 if ok else 1})
        if not ok:
            break
    return record


def certificate(steps: list[dict], plan: list[Step]) -> dict:
    from ocuval.eval import sealed

    commit, clean = sealed.repository_state()
    names = [s.name for s in plan if s.kind != "dry_run"]
    return {
        "chain": CHAIN,
        "commit": commit,
        "clean": clean,
        "complete": [s["name"] for s in steps] == names and all(s["exit"] == 0 for s in steps),
        "steps": steps,
        "sealed": MAY_OPEN,
        "utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


# --- refusals and running ------------------------------------------------------------------


def refusals() -> list[str]:
    from ocuval.eval import report, sealed

    found = []
    status = REPO / STATUS
    if status.is_file() and MARKER in status.read_text(encoding="utf-8"):
        found.append(f"{STATUS} already records {MARKER}; this chain never runs twice")
    if not sealed.repository_state()[1]:
        found.append("the working tree is not clean")
    folder = REPO / OUTPUT
    if folder.exists() and any(folder.iterdir()):
        found.append(f"{OUTPUT} holds files; section 21.11 never overwrites")
    for fold, arms in report.record_paths(REPO / "artifacts" / "runs")["audited"].items():
        path = arms["test"]
        if not path.is_file():
            found.append(f"{fold}: {path} is missing")
            continue
        saved = json.loads(path.read_text(encoding="utf-8"))["notes"].get("predictions_directory")
        if not saved or not (REPO / saved).is_dir():
            found.append(f"{fold}: the saved maps of {path} are missing (SRS-106)")
    return found


def log(message: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}"
    (REPO / CHAIN_DIR).mkdir(parents=True, exist_ok=True)
    with (REPO / STATUS).open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


def stop(why: str) -> int:
    log(f"CHAIN STOPPED: {why}")
    log("CHAIN END")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = build_plan(args)
    refused = refusals()
    if refused:
        for reason in refused:
            print(f"!! refused: {reason}", file=sys.stderr)
        return 2
    from ocuval.eval import sealed

    log(f"{MARKER} at {sealed.repository_state()[0]}")
    before: dict = {}
    for step in plan:
        if step.kind == "counts":
            before = access_counts(REPO / "artifacts")
            if before != EXPECTED_COUNTS:
                for key, value in before.items():
                    log(f"COUNT {key}: {value}, section 21.11 states {EXPECTED_COUNTS[key]}")
                return stop("access counts differ from docs/07 section 21.11; record first")
            log("ACCESS COUNTS as section 21.11 states")
        elif step.kind == "dry_run":
            log("START dry_run")
            with tempfile.TemporaryDirectory(prefix="ocuval_dryrun_") as folder:
                steps = dry_run(plan, Path(folder), REPO / CHAIN_DIR / f"{CHAIN}_dryrun")
            cert = certificate(steps, plan)
            for s in steps:
                log(f"DRY RUN {s['name']} exit {s['exit']}")
            if not cert["complete"]:
                return stop("the dry run did not complete every step; no sealed bucket opened")
            (REPO / CERTIFICATE).write_text(json.dumps(cert, indent=1) + "\n", encoding="utf-8")
            log(f"DRY RUN COMPLETE: certificate {CERTIFICATE} at {cert['commit']}")
        elif step.kind == "bscans":
            env = dict(os.environ)
            env[sealed.CERTIFICATE_ENV] = str(REPO / CERTIFICATE)
            log("START bscans")
            code = run_in(step, REPO, env, REPO / CHAIN_DIR / f"{CHAIN}_real")
            log(f"END   bscans exit {code}")
            if code != 0:
                return stop(f"bscans exited {code}")
        else:
            found = access_counts(REPO / "artifacts")
            want = expected_after(before, picked_runs(REPO))
            for key, value in found.items():
                log(f"COUNT AFTER {key}: {value} (expected {want[key]})")
            if found != want:
                return stop("access counts after differ from section 21.11's rule; examine the log")
            log("ACCESS COUNTS AFTER as section 21.11 states")
    log("CHAIN END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
