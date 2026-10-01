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
STAGE2_SECTION = "17. Stage 2 evaluation protocol — pre-registered"


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
    assert "10%" in section, "the loss-reduction threshold is no longer stated"
    # Stage 1 ran with AMP off and its pre-registration says so. AMP was reversed on
    # 2026-09-30 and Stage 1b runs with it on, but §15's record of the conditions Stage 1
    # actually ran under is NOT edited to match -- that is the whole point of
    # pre-registration. Both strings must be present, in their own subsections.
    assert "AMP off" in section, (
        "docs/07 §15 no longer states the AMP-off conditions Stage 1 ran under. A "
        "pre-registration records what was committed before the run; a later decision to "
        "reverse AMP is a new subsection, never an edit to this one."
    )
    assert "15.6" in section and "AMP on" in section, (
        "docs/07 §15 does not pre-register Stage 1b under the reversed AMP decision. A "
        "run whose conditions differ from §15's needs its own committed criteria before "
        "it starts, or it has none."
    )


def section_text(heading: str) -> str:
    """One section of `docs/07`, with whitespace collapsed.

    Collapsed because these guards assert *content*, and a phrase in this document
    routinely spans a line break. Matching raw text would make the guard fail on a
    rewrap that changed nothing, which trains everyone to edit the assertion instead of
    reading it — the failure mode §16.2 records for hashing a prose section.
    """
    text = read("docs", "07_vv_protocol.md").replace("\r\n", "\n")
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert match, f"docs/07 section {heading!r} not found"
    return re.sub(r"\s+", " ", match.group(0))


def test_TC_088_the_stage2_protocol_still_fixes_its_parameters():
    """§17 is pre-registration for a result that can be reported once.

    Every number in it moves the headline figure, so each is asserted individually rather
    than the section merely being asserted to exist. The bootstrap parameters are the
    sharpest: 2000 resamples and α = 0.05 are fixed *now* precisely so that neither can
    later be chosen to move an interval across a boundary.
    """
    section = section_text(STAGE2_SECTION)
    for phrase, why in [
        ("in-domain validation only", "checkpoint selection must exclude the held-out vendor"),
        ("exactly once", "the test set is evaluated once"),
        ("2000", "the bootstrap resample count is fixed"),
        ("0.05", "the interval's alpha is fixed"),
        ("patient", "the resampling unit is the patient, not the frame"),
        ("SRS-057", "native-geometry inversion is asserted against ingestion spacing"),
        ("SRS-074", "metrics are computed in native geometry"),
        ("before the test set is touched", "the evaluation code is committed first"),
    ]:
        assert phrase in section, f"docs/07 §17 no longer states {phrase!r} — {why}"


def test_TC_088_the_stage2_protocol_forbids_retraining_on_the_test_set():
    """The prohibition, and its one permitted exception, must both survive.

    An absolute ban with no stated route for a legitimate follow-up invites the ban to be
    quietly ignored; the route is "a new experiment, pre-registered as such", and it is
    only a control if it stays written down.
    """
    section = section_text(STAGE2_SECTION)
    assert "No retraining against the test set" in section
    assert "new experiment" in section and "pre-registered as such" in section, (
        "docs/07 §17 no longer states the one permitted route for acting on a "
        "cross-vendor result, so the prohibition has no legitimate alternative"
    )
    assert "A degraded cross-vendor result is a result" in section, (
        "docs/07 §17 no longer states that the degradation is the contribution. Without "
        "it, a poor held-out figure reads as a failure to be recovered from"
    )


def test_TC_088_the_stage3_secondary_analyses_keep_their_declared_rule():
    """§19 is pre-registration for analyses that have not run yet.

    The threshold-selection rule is the sharpest part: a grid, an objective, the split it is
    selected on and a tie-break, all fixed before any Stage 3 result exists. Each is asserted
    individually, because a rule missing its tie-break is not a rule on a 7-patient split
    where ties are likely.
    """
    section = section_text("19. Stage 3 secondary analyses — pre-registered")
    for phrase, why in [
        ("[1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]", "the threshold grid is declared"),
        ("Youden's J", "the selection objective is declared"),
        ("smallest", "the tie-break is declared"),
        ("`val`** split only", "selection is on validation only, never test or reference"),
        ("remain primary", "the fixed-threshold figures stay primary"),
        ("never instead", "a selected threshold never replaces the fixed one"),
        ("about 21 patients", "the pooled analysis states the n it exists for"),
        ("post-hoc for cirrus", "the same analysis has a different standing for cirrus"),
    ]:
        assert phrase in section, f"docs/07 §19 no longer states {phrase!r} — {why}"


def test_TC_088_the_stage1b_thresholds_are_the_stage1_thresholds():
    """Stage 1b changes the *conditions*, not the bar.

    Re-running under a faster configuration is only informative if the thresholds are the
    ones committed before any result was seen. A new stage that quietly relaxed them would
    be a description of the new run, which is what `docs/07` §15.5 forbids.
    """
    section = stage1_criteria_text()
    stage1b = section[section.index("15.6") :]
    for value in ("0.0451", "0.0428", "0.0384", "10%"):
        assert value in stage1b, (
            f"Stage 1b's pre-registration does not restate {value}. The thresholds carry "
            f"over unchanged; stating them here is what makes that checkable."
        )


# --- Attribution trailers: check removed 2026-10-01 ------------------------------------
#
# `test_TC_088_no_commit_carries_an_attribution_trailer` was here and asserted that no
# commit message in the last 400 carried a `Co-Authored-By` line. It is **deliberately
# deleted, not skipped or xfailed** (`docs/07` §4 A3 permits no skipped test).
#
# It was dropped because it enforced a decision that contradicts a stronger one. The rest
# of this project holds that **the record states what happened**: `docs/08` keeps Stage 1's
# `determinism.json` unedited with its 1308 fallbacks, TC-109 scopes its invariant to
# records written after SRS-085 rather than rewriting earlier ones, and `docs/13` carries
# the author's own retracted claims as findings. A test requiring tool attribution to be
# absent from history requires the history to say something other than what happened, and
# in practice it required rewriting history to enforce — which broke nine cited SHAs on
# 2026-09-23 and is why TC-108 exists.
#
# See `docs/13`, 2026-10-01. TC-108 still checks that every SHA cited in `docs/` resolves,
# which is the control that actually matters about commit history here.


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
