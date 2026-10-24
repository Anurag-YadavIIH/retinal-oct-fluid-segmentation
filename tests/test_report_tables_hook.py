"""TC-145 — the report-tables hook blocks on a difference, and never skips silently.

Traces to: SRS-099

Runs on synthetic documents and a stand-in generator, so CI runs it without the records.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ocuval.eval import report

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "report_hook", REPO / "scripts" / "check_report_tables_hook.py"
)
HOOK = importlib.util.module_from_spec(SPEC)
sys.modules["report_hook"] = HOOK
SPEC.loader.exec_module(HOOK)

DOC10 = "docs/10_analytical_validation_report.md"
TEXT = "Intro: 3 of 9 comparisons overlap.\n"


def generated():
    g = report.Generated()
    g.say("docs/10", "3 of 9 comparisons overlap")
    return g


@pytest.fixture
def records_present(monkeypatch):
    monkeypatch.setattr(report, "records_present", lambda runs: True)
    monkeypatch.setattr(report, "load_records", lambda runs: None)
    monkeypatch.setattr(report, "generate", lambda sets: generated())


def documents(text):
    return lambda: {"docs/10": text, "docs/12": "", "README": ""}


def test_TC_145_nothing_watched_staged_means_nothing_to_check(tmp_path):
    lines = []
    assert HOOK.run({"src/ocuval/eval/report.py"}, tmp_path, documents(TEXT), lines.append) == 0
    assert lines == []


def test_TC_145_absent_records_warn_loudly_and_never_silently(tmp_path):
    lines = []
    assert HOOK.run({DOC10, "README.md"}, tmp_path / "none", documents(TEXT), lines.append) == 0
    assert len(lines) == 1
    message = lines[0]
    assert "DID NOT RUN" in message and "SRS-099" in message
    assert "evaluation records are absent" in message and str(tmp_path / "none") in message
    assert DOC10 in message and "README.md" in message


def test_TC_145_a_difference_blocks_the_commit(tmp_path, records_present):
    lines = []
    changed = documents(TEXT.replace("3 of 9", "4 of 9"))
    assert HOOK.run({DOC10}, tmp_path, changed, lines.append) == 1
    assert any("not found: 3 of 9" in line for line in lines)


def test_TC_145_agreement_lets_the_commit_through(tmp_path, records_present):
    lines = []
    assert HOOK.run({DOC10}, tmp_path, documents(TEXT), lines.append) == 0
    assert lines and "agree with the records" in lines[0]


def test_TC_145_the_watched_files_are_the_generators_documents():
    assert set(HOOK.WATCHED) == set(report.DOCS.values())


def test_TC_145_the_hook_reads_the_staged_text_not_the_working_tree(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    for path in report.DOCS.values():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("staged\n", encoding="utf-8")
    git("add", ".")
    (tmp_path / DOC10).write_text("working tree\n", encoding="utf-8")
    assert HOOK.staged_documents(tmp_path)["docs/10"] == "staged\n"
    assert HOOK.staged_files(tmp_path) == set(report.DOCS.values())


@pytest.fixture
def no_project(monkeypatch):
    monkeypatch.setattr(HOOK, "staged_files", lambda: {DOC10})
    monkeypatch.setattr(HOOK, "VENVS", ())
    monkeypatch.setitem(sys.modules, "ocuval.eval.report", None)  # import now raises


def test_TC_145_no_interpreter_and_no_records_warns_rather_than_skipping(
    no_project, monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(HOOK, "RUNS", tmp_path)
    assert HOOK.main() == 0
    out = capsys.readouterr().out
    assert "DID NOT RUN" in out and "no interpreter here can import the project" in out


def test_TC_145_no_interpreter_with_records_present_blocks(
    no_project, monkeypatch, tmp_path, capsys
):
    record = tmp_path / "some_run" / "corrected" / "evaluation_test.json"
    record.parent.mkdir(parents=True)
    record.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(HOOK, "RUNS", tmp_path)
    assert HOOK.main() == 1
    out = capsys.readouterr().out
    assert "BLOCKED" in out and "records are present" in out


def test_TC_145_the_records_probe_sees_only_corrected_evaluation_records(tmp_path):
    assert not HOOK.records_on_disk(tmp_path)
    (tmp_path / "run" / "corrected").mkdir(parents=True)
    (tmp_path / "run" / "evaluation_test.json").write_text("{}", encoding="utf-8")
    assert not HOOK.records_on_disk(tmp_path)
    (tmp_path / "run" / "corrected" / "evaluation_val.json").write_text("{}", encoding="utf-8")
    assert HOOK.records_on_disk(tmp_path)


def test_TC_145_the_hook_is_declared_so_that_its_output_is_always_shown():
    config = yaml.safe_load((REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [h for repo in config["repos"] for h in repo["hooks"] if h["id"] == "report-tables"]
    assert len(hooks) == 1
    hook = hooks[0]
    assert hook["entry"] == "python scripts/check_report_tables_hook.py"
    assert hook["stages"] == ["commit-msg"] and hook["always_run"] is True
    assert hook["pass_filenames"] is False and hook["verbose"] is True
