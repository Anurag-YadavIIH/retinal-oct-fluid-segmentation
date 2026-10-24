"""Commit hook: check docs/10, docs/12 and the README against the records when they change.

Serves: SRS-099. The check itself is `ocuval.eval.report` (SRS-098).

- **No watched document staged:** exit 0, nothing to check.
- **Records present:** the *staged* versions of the documents (what the commit will hold, not
  the working tree) are checked; any difference blocks the commit (exit 1).
- **Records absent:** the commit proceeds (exit 0), and a warning says the check **did not
  run** and why. The hook is declared `verbose: true`, because pre-commit hides a passing
  hook's output, and a warning nobody sees is a silent skip.

Runs at the commit-msg stage, beside the repository's other local guards: that is the hook
type this repository installs. The staged files are read from git rather than passed in,
because at that stage pre-commit passes only the message file.

**Standard library only until a watched document is staged.** A `language: system` hook runs
whichever `python` is first on PATH, which need not have this project installed. If it cannot
import the check, the hook re-runs itself with the repository's `.venv` interpreter. If there
is none, it **blocks** when records are on disk (the environment that should run the check is
broken) and warns, as for absent records, when they are not.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNS = REPO / "artifacts" / "runs"
# Must equal ocuval.eval.report.DOCS; TC-145 checks it.
WATCHED = ("docs/10_analytical_validation_report.md", "docs/12_model_card.md", "README.md")
VENVS = (REPO / ".venv" / "Scripts" / "python.exe", REPO / ".venv" / "bin" / "python")


def staged_files(repo: Path = REPO) -> set[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo, capture_output=True, text=True, check=True,
    )  # fmt: skip
    return set(out.stdout.split())


def staged_documents(repo: Path = REPO) -> dict[str, str]:
    """The documents as the commit will hold them: the index, not the working tree."""
    from ocuval.eval import report

    texts = {}
    for key, path in report.DOCS.items():
        out = subprocess.run(["git", "show", f":{path}"], cwd=repo, capture_output=True, check=True)
        texts[key] = out.stdout.decode("utf-8")
    return texts


def warning(reason: str, touched: list[str]) -> str:
    bar = "!" * 78
    return (
        f"{bar}\nWARNING: the report-tables check DID NOT RUN (SRS-099).\n"
        f"Reason: {reason}.\n"
        f"Changed in this commit and NOT checked against the records: {', '.join(touched)}.\n"
        "Run `python scripts/11_report_tables.py` where the records are, before pushing.\n"
        f"{bar}"
    )


def run(staged: set[str], runs: Path, read_documents, out=print) -> int:
    from ocuval.eval import report

    touched = sorted(staged & set(WATCHED))
    if not touched:
        return 0
    if not report.records_present(runs):
        out(warning(f"the evaluation records are absent under {runs}", touched))
        return 0
    differences = report.check(report.generate(report.load_records(runs)), read_documents())
    if differences:
        out("report tables: the staged documents disagree with the records (SRS-099):")
        for d in differences:
            out(str(d))
        return 1
    out(f"report tables: {', '.join(touched)} agree with the records")
    return 0


def main() -> int:
    touched = sorted(staged_files() & set(WATCHED))
    if not touched:
        return 0
    try:
        import ocuval.eval.report  # noqa: F401
    except ImportError:
        here = Path(sys.executable).resolve()
        venv = next((p for p in VENVS if p.is_file() and p.resolve() != here), None)
        if venv is not None:
            return subprocess.call([str(venv), str(Path(__file__).resolve())])
        reason = f"no interpreter here can import the project ({sys.executable})"
        if records_on_disk(RUNS):
            # The author's decision, 2026-10-24: records here mean this machine should run
            # the check, so a broken environment blocks rather than warns.
            print(f"report tables: BLOCKED (SRS-099): the records are present under {RUNS}, "
                  f"but {reason}. Fix the environment and commit again.")  # fmt: skip
            return 1
        print(warning(reason, touched))
        return 0
    return run(set(touched), RUNS, staged_documents)


def records_on_disk(runs: Path) -> bool:
    """Whether any corrected evaluation record is here, judged with the standard library only.

    Used only where the project cannot be imported. It is deliberately looser than
    `report.records_present`: any record at all means this machine should run the check.
    """
    return any(runs.glob("*/corrected/evaluation_*.json"))


if __name__ == "__main__":
    sys.exit(main())
