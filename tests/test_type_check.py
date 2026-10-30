"""TC-158 — the type check passes over `src/` and `scripts/`, and can fail.

Traces to: SRS-109

The §21.10 run failed because a name holding the sealed records was rebound to the spacing; a
type checker reports that, and no test of the script's parts exercised it. So the check runs
over everything a chain or the pipeline can execute, with unannotated bodies checked too, and
the same configuration is shown to catch that defect.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("src", "scripts")


def mypy(*targets: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mypy", *targets],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def test_TC_158_mypy_reports_no_finding_over_src_and_scripts():
    result = mypy(*SOURCE_DIRS)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
    assert "Success: no issues found" in result.stdout


def test_TC_158_the_configuration_checks_unannotated_bodies_and_nothing_is_silenced():
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["mypy"]
    assert config["check_untyped_defs"] is True
    assert config.get("ignore_errors") is not True
    for folder in SOURCE_DIRS:
        for path in (REPO / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "type: ignore" not in text, f"{path.relative_to(REPO)} silences a finding"


def test_TC_158_ci_runs_the_same_check_and_the_version_is_pinned_alike():
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert re.search(r"^\s+mypy src scripts\s*$", workflow, re.M), "CI does not run the check"
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    pinned = re.search(r'"mypy==([\d.]+)"', pyproject).group(1)
    lock = (REPO / "requirements.lock").read_text(encoding="utf-8")
    assert f"mypy=={pinned}" in lock.splitlines()
    soup = (REPO / "docs" / "04_soup_list.md").read_text(encoding="utf-8")
    assert re.search(rf"^\| SOUP-\d+ \| mypy \| {re.escape(pinned)} \|", soup, re.M)


def test_TC_158_the_check_reports_the_defect_that_stopped_section_21_10(tmp_path):
    probe = REPO / "scripts" / "_tc158_probe.py"
    probe.write_text(
        "def gate(recorded: dict) -> object:\n"
        "    return recorded.get('x')\n"
        "\n"
        "\n"
        "def main() -> None:\n"
        "    recorded = {('run', 's'): {'IRF': (0.5, 10)}}\n"
        "    recorded = (0.002, 0.01, 0.05)  # the spacing, under the records' name\n"
        "    gate(recorded)\n",
        encoding="utf-8",
    )
    try:
        result = mypy(str(probe.relative_to(REPO)))
    finally:
        probe.unlink()
    assert result.returncode != 0
    assert "Incompatible types in assignment" in result.stdout
