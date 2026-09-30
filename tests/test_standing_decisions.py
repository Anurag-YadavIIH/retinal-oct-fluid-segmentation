"""Standing decisions from CLAUDE.md §7, enforced where enforcement is possible (TC-088).

**Why this file exists.** On 2026-09-28 a Stage 1 run was launched under conditions
contradicting a standing decision, because the AMP decision lived only in prose. That
prompted an audit of every standing decision in CLAUDE.md §7, asking of each: is this
enforced by anything, or does it survive only because someone remembers it?

The audit is recorded in `docs/07` §16. This file holds the tests it produced. Decisions
that cannot be enforced by a test are listed there explicitly and say why -- an
unenforceable decision that is *known* to be unenforceable is a different thing from one
assumed to be safe.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def read(*parts: str) -> str:
    return (REPO_ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def data_config() -> dict:
    return yaml.safe_load(read("configs", "data.yaml"))


def train_config() -> dict:
    return yaml.safe_load(read("configs", "train_seg.yaml"))


# --- "The UID root stays an unregistered placeholder, declared" -----------------------


def test_TC_088_uid_root_matches_the_declared_placeholder():
    """The decision is that the root is a placeholder AND that it is declared as one.

    Previously prose only. A root quietly changed to something plausible-looking would
    have contradicted `docs/11` with nothing objecting -- and a plausible but
    unregistered root is worse than an obvious one, because it invites trust.
    """
    root = str(data_config()["dicom"]["uid_root"])
    conformance = read("docs", "11_dicom_conformance_statement.md")
    assert root in conformance, (
        f"uid_root {root!r} is not mentioned in docs/11. The root must be declared "
        f"where conformance is stated, not merely configured."
    )
    assert re.search(
        r"unregistered|placeholder", conformance, re.I
    ), "docs/11 does not describe the UID root as unregistered or a placeholder"


# --- "Training reads train.batch_size and nowhere else" -------------------------------


def test_TC_088_batch_size_has_exactly_one_home():
    """A second `data.batch_size` was added and removed on 2026-09-25. Two places to
    state one value is how a run reports a batch size it did not use."""
    config = train_config()
    assert "batch_size" in config["train"]
    assert "batch_size" not in config["data"], (
        "configs/train_seg.yaml declares batch_size under data: as well as train:. "
        "The datamodule reads train.batch_size; a second copy can only drift."
    )


# --- "Pre-registered criteria are not edited after seeing results" ---------------------

# SHA-256 of docs/07 section 15, the Stage 1 acceptance criteria, as committed in
# f4d2a34 before any run. This constant is the forcing function: editing section 15
# fails this test, and the only way to make it pass is to update the hash deliberately,
# which a reviewer sees in the diff alongside whatever result prompted it.
#
# What this is NOT: proof that the criteria were not changed for a bad reason. It makes
# the change visible, which is all a hash can do. docs/07 section 15.5 states that a
# failed criterion stops the next stage rather than getting rewritten.
STAGE1_SECTION = "15. Stage 1 smoke run — acceptance criteria, pre-registered"


def stage1_criteria_text() -> str:
    text = read("docs", "07_vv_protocol.md").replace("\r\n", "\n")
    match = re.search(rf"^## {re.escape(STAGE1_SECTION)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert match, "docs/07 section 15 not found"
    return "\n".join(line.rstrip() for line in match.group(0).splitlines()).strip() + "\n"


def test_TC_088_the_stage1_criteria_still_state_their_measured_baselines():
    """The numbers are the criterion. Prose about 'beating a trivial baseline' without
    them would be unfalsifiable, which is what pre-registration exists to prevent."""
    section = stage1_criteria_text()
    for value in ("0.0451", "0.0428", "0.0384"):
        assert value in section, (
            f"baseline {value} is missing from docs/07 section 15. The spatial-prior "
            f"figures are the pre-registered bar; without them the criterion is a wish."
        )
    assert "AMP off" in section, "the run conditions no longer state AMP off"
    assert "10%" in section, "the loss-reduction threshold is no longer stated"


# --- "Commits carry no Claude Code attribution" ----------------------------------------


def test_TC_088_no_commit_carries_an_attribution_trailer():
    """History was rewritten on 2026-09-23 to remove these. Nothing stopped them coming
    back until now."""
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "log", "--format=%B", "-n", "400"],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        pytest.skip("git unavailable or not a repository")
    offenders = [
        line.strip() for line in result.stdout.splitlines() if "co-authored-by" in line.lower()
    ]
    assert not offenders, f"attribution trailers present in history: {offenders[:3]}"


# --- "Training reads the archive's native MetaImage, not the DICOM" --------------------


def test_TC_088_the_training_data_path_does_not_read_dicom():
    """DICOM is the output interface, not the input. If the loader ever reads it, the
    training pair has two sources with nothing asserting they correspond (HAZ-004)."""
    datamodule = read("src", "ocuval", "data", "datamodule.py")
    assert "pydicom" not in datamodule, (
        "data/datamodule.py references pydicom. Training reads MetaImage; the DICOM "
        "instances this project writes carry no segmentation."
    )
    assert "read_volume" in datamodule, "the loader no longer reads the native volume"


# --- "Splits are keyed on the source subject, never the SOP Instance UID" --------------


def test_TC_088_persisted_splits_name_subjects_not_uids():
    """Checked against the real files where they exist, not only the constructor."""
    splits_root = REPO_ROOT / "data" / "splits"
    files = sorted(splits_root.glob("*_holdout.json")) if splits_root.is_dir() else []
    if not files:
        pytest.skip("no resolved splits on this machine")

    import json

    for path in files:
        split = json.loads(path.read_text(encoding="utf-8"))
        for bucket in ("train", "val", "test", "in_domain_ref"):
            for entry in split[bucket]:
                assert not entry.count(".") >= 4, (
                    f"{path.name} bucket {bucket} contains {entry!r}, which looks like a "
                    f"UID. Splits are keyed on the source subject (SRS-023)."
                )


# --- "Accuracy alone is never reported" (CLAUDE.md §5) ---------------------------------


def test_TC_088_no_accuracy_function_exists():
    """Already covered by TC-002; asserted here too because the audit asked of every
    decision whether anything enforces it, and the answer must not depend on memory."""
    metrics = read("src", "ocuval", "eval", "metrics.py")
    assert not re.search(r"def\s+\w*accuracy", metrics), "an accuracy function exists"
