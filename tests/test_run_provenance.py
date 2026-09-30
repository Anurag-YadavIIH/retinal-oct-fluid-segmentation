"""TC-122: the run record identifies the code, and a dirty tree refuses to run.

Verifies: TC-122
Traces to: SRS-086, SRS-031; NFR-002

`docs/08` D4 recorded the gap this closes. Stage 1's `run.json` pinned the configuration,
the seed, the platform, the torch build and the lock's digest — and nothing identifying
the project's own source. A configuration pinned against unidentified code is not
reproducible, which is what SRS-031 exists to deliver.

The same file also carried a top-level `seed: null` beside `resolved_config.run.seed:
20260916`: two homes for one value, one of them wrong. That is the pattern CLAUDE.md
already forbids for `batch_size`, and it is asserted here rather than merely removed,
because a field nothing checks can come back.

**Real repositories, not mocks.** Each case builds a throwaway git repository with
`git init` and drives the real `source_record`. A fake that returns a dict would verify
the assertions in this file and nothing about whether the parsing works.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
import yaml

from ocuval.runs import (
    DirtyWorkingTreeError,
    require_clean_tree,
    resolve,
    source_record,
    write_provenance,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="TC-122 needs git")


def git(root, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A real repository with one commit, so `dirty` starts false."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    (root / "tracked.txt").write_text("one\n", encoding="utf-8")
    git(root, "add", "tracked.txt")
    git(root, "commit", "-q", "-m", "initial")
    return root


# --- what the record carries ----------------------------------------------------------


def test_TC_122_a_clean_repository_reports_its_commit_and_is_not_dirty(repo):
    record = source_record(repo)
    assert record["commit"] == git(repo, "rev-parse", "HEAD")
    assert len(record["commit"]) == 40
    assert record["dirty"] is False
    assert record["branch"] == git(repo, "rev-parse", "--abbrev-ref", "HEAD")


@pytest.mark.parametrize(
    ("what", "change"),
    [
        ("modified", lambda root: (root / "tracked.txt").write_text("two\n", encoding="utf-8")),
        ("untracked", lambda root: (root / "extra.py").write_text("x = 1\n", encoding="utf-8")),
    ],
)
def test_TC_122_any_uncommitted_change_makes_the_tree_dirty(repo, what, change):
    """**Untracked files count**, and that is the case that motivated this.

    `scripts/evaluate_stage1.py` was untracked when it produced the Stage 1 result, so a
    check that ignored untracked files would have passed on exactly the situation this
    requirement exists to catch.
    """
    assert source_record(repo)["dirty"] is False
    change(repo)
    assert source_record(repo)["dirty"] is True, f"an {what} file did not register as dirty"


def test_TC_122_outside_a_repository_every_field_is_unknown_not_absent(tmp_path):
    """`None` rather than a missing key: a reader must be able to tell "no git here" from
    "nobody looked"."""
    record = source_record(tmp_path)
    assert set(record) >= {"commit", "dirty", "branch"}
    assert record["commit"] is None
    assert record["dirty"] is None


def test_TC_122_commit_is_never_reported_without_dirty_beside_it(repo):
    """A commit written beside uncommitted edits names code that did not run.

    That is worse than recording nothing, because it looks precise. The two fields travel
    together or neither is trustworthy.
    """
    for record in (source_record(repo), source_record(repo.parent)):
        if record["commit"] is not None:
            assert record["dirty"] is not None


# --- the refusal ----------------------------------------------------------------------


def test_TC_122_a_dirty_tree_is_refused(repo):
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(DirtyWorkingTreeError, match="uncommitted changes"):
        require_clean_tree(source_record(repo))


def test_TC_122_a_missing_commit_is_refused(tmp_path):
    """Not being in a repository is also a failure to identify the code."""
    with pytest.raises(DirtyWorkingTreeError, match="no commit identifier"):
        require_clean_tree(source_record(tmp_path))


def test_TC_122_a_clean_tree_is_permitted(repo):
    require_clean_tree(source_record(repo))


@pytest.mark.parametrize("record", [{"dirty": True, "commit": "a" * 40}, {"dirty": None}])
def test_TC_122_allow_dirty_overrides_both_refusals(record):
    require_clean_tree(record, allow_dirty=True)


def test_TC_122_the_guard_can_fail(repo):
    """docs/07 §3 rule 8: a guard that cannot refuse is not a guard.

    Without this, `require_clean_tree` could `return` unconditionally and every case above
    that expects success would still pass.
    """
    clean = source_record(repo)
    require_clean_tree(clean)
    (repo / "new.txt").write_text("x\n", encoding="utf-8")
    with pytest.raises(DirtyWorkingTreeError):
        require_clean_tree(source_record(repo))


# --- what lands in run.json -----------------------------------------------------------


def provenance(tmp_path) -> dict:
    config = tmp_path / "cfg.yaml"
    config.write_text(yaml.safe_dump({"run": {"seed": 20260916}}), encoding="utf-8")
    destination = write_provenance("04_train", resolve(config, tmp_path / "out"))
    return json.loads(destination.read_text(encoding="utf-8"))


def test_TC_122_run_json_carries_the_source_block(tmp_path):
    record = provenance(tmp_path)
    assert "source" in record, "run.json does not identify the code that produced the run"
    assert set(record["source"]) >= {"commit", "dirty", "branch"}


def test_TC_122_run_json_has_no_duplicate_seed_field(tmp_path):
    """SRS-086's last sentence, and `docs/08` D4's second half.

    The removed field read `null` on every training run while the real seed sat in the
    resolved configuration. Asserted rather than merely deleted, because a field nothing
    checks can come back — which is how `data.batch_size` returned once already.
    """
    record = provenance(tmp_path)
    assert "seed" not in record, (
        "run.json has a top-level `seed` again. The seed has exactly one home, "
        "`resolved_config.run.seed`, which is where the run reads it from."
    )
    assert record["resolved_config"]["run"]["seed"] == 20260916


def test_TC_122_the_training_script_refuses_a_dirty_tree_before_writing_provenance():
    """The refusal is wired into the stage whose output gets cited, and precedes the
    provenance write, so a refused run leaves no record suggesting it began."""
    source = (
        (__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts" / "04_train.py")
        .read_text(encoding="utf-8")
        .replace("\r\n", "\n")
    )
    assert "require_clean_tree(" in source, "04_train.py does not check the working tree"
    assert source.index("require_clean_tree(") < source.index("write_provenance("), (
        "the working-tree check runs after the provenance is written, so a refused run "
        "would still leave a run.json claiming it started"
    )
    assert '"allow_dirty": bool(args.allow_dirty)' in source, (
        "the override is not recorded in run.json. An escape hatch nobody can see in the "
        "output is indistinguishable from no check at all."
    )
