"""TC-156 — no sealed bucket opens without a completed dry run at this commit.

Traces to: SRS-107

The control sits in the SRS-088 gate itself, which every sealed access passes through, so no
script or chain can open a bucket by forgetting its dry run. Each way a certificate can be wrong
is refused, before anything is logged; a sandbox-marked log, where a dry run opens its synthetic
buckets, needs none, and the repository's own `artifacts/` never counts as one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ocuval.eval import sealed

COMMIT = "0123456789abcdef0123456789abcdef01234567"
UNLOCK = sealed.Unlock(bucket="test", reason="TC-156", approved_by="a")


@pytest.fixture
def at_commit(monkeypatch):
    monkeypatch.setattr(sealed, "repository_state", lambda: (COMMIT, True))
    monkeypatch.delenv(sealed.CERTIFICATE_ENV, raising=False)


def certificate(tmp_path, monkeypatch, **changes):
    body = {
        "chain": "tc156",
        "commit": COMMIT,
        "clean": True,
        "complete": True,
        "steps": [{"name": "bscans", "exit": 0}],
        "sealed": [["cirrus_holdout", "test"]],
    }
    body.update(changes)
    path = tmp_path / "certificate.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(sealed.CERTIFICATE_ENV, str(path))
    return path


def logged(root: Path) -> int:
    path = root / "sealed_access.jsonl"
    return len(path.read_text(encoding="utf-8").splitlines()) if path.is_file() else 0


def test_TC_156_without_a_certificate_sealed_buckets_are_refused_and_nothing_is_logged(
    tmp_path, at_commit
):
    root = tmp_path / "artifacts"
    for bucket in ("test", "in_domain_ref"):
        unlock = sealed.Unlock(bucket=bucket, reason="r", approved_by="a")
        with pytest.raises(sealed.SealedSplitError, match="dry run"):
            sealed.require_unsealed(bucket, unlock, fold_id="cirrus_holdout", root=root)
    sealed.require_unsealed("val", None, fold_id="cirrus_holdout", root=root)
    assert logged(root) == 0


def test_TC_156_a_complete_certificate_at_this_commit_opens_its_bucket(
    tmp_path, monkeypatch, at_commit
):
    root = tmp_path / "artifacts"
    certificate(tmp_path, monkeypatch)
    sealed.require_unsealed("test", UNLOCK, fold_id="cirrus_holdout", root=root)
    assert logged(root) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"complete": False},
        {"steps": [{"name": "bscans", "exit": 1}]},
        {"steps": []},
        {"commit": "f" * 40},
        {"clean": False},
        {"sealed": [["topcon_holdout", "test"]]},
        {"sealed": [["cirrus_holdout", "in_domain_ref"]]},
    ],
)
def test_TC_156_every_wrong_certificate_is_refused_and_nothing_is_logged(
    tmp_path, monkeypatch, at_commit, changes
):
    root = tmp_path / "artifacts"
    certificate(tmp_path, monkeypatch, **changes)
    with pytest.raises(sealed.SealedSplitError, match="dry run"):
        sealed.require_unsealed("test", UNLOCK, fold_id="cirrus_holdout", root=root)
    assert logged(root) == 0


def test_TC_156_a_dirty_tree_or_an_unreadable_certificate_is_refused(tmp_path, monkeypatch):
    root = tmp_path / "artifacts"
    certificate(tmp_path, monkeypatch)
    monkeypatch.setattr(sealed, "repository_state", lambda: (COMMIT, False))
    with pytest.raises(sealed.SealedSplitError, match="dry run"):
        sealed.require_unsealed("test", UNLOCK, fold_id="cirrus_holdout", root=root)
    monkeypatch.setattr(sealed, "repository_state", lambda: (COMMIT, True))
    (tmp_path / "certificate.json").write_text("not json", encoding="utf-8")
    with pytest.raises(sealed.SealedSplitError, match="dry run"):
        sealed.require_unsealed("test", UNLOCK, fold_id="cirrus_holdout", root=root)
    assert logged(root) == 0


def test_TC_156_a_sandbox_log_opens_without_a_certificate(tmp_path, at_commit):
    root = tmp_path / "sandbox" / "artifacts"
    sealed.mark_sandbox(root)
    sealed.require_unsealed("test", UNLOCK, fold_id="cirrus_holdout", root=root)
    assert logged(root) == 1


def test_TC_156_the_repositorys_own_artifacts_is_never_a_sandbox(monkeypatch, at_commit):
    real = sealed.REPO / "artifacts"
    monkeypatch.setattr(Path, "is_file", lambda self: self.name == sealed.SANDBOX_MARKER or
                        Path.exists(self))  # fmt: skip
    assert not sealed.is_sandbox(real)
    with pytest.raises(ValueError, match="never a sandbox"):
        sealed.mark_sandbox(real)
