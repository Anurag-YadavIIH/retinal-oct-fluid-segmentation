"""TC-121: two GPU runs of one configuration must agree bit-for-bit.

Verifies: TC-121
Traces to: SRS-076, SRS-077, SRS-084, SRS-085; CLAUDE.md rule 4

**Why this test exists, and why zero fallbacks was not enough.** After adopting
`dice_ce_deterministic` (SRS-084), `determinism.json` records zero non-deterministic
fallbacks. That is a weaker statement than it sounds: it says no operation *announced*
non-determinism. It does not say two runs agree. An operation with no warning can still
be order-dependent -- atomics in a reduction, a workspace-size-dependent algorithm
choice, a non-associative accumulation over a grid whose scheduling varies. The two are
different claims and the second is the one CLAUDE.md rule 4 makes.

This is `docs/07` §3 rule 8 in its most literal form: the observable output of a
deterministic run and a nearly deterministic one is identical until you compare two of
them. So the test compares two of them, byte for byte, on the model weights, the
optimiser state and the per-epoch loss log.

**Rule 4 is claimed achieved on GPU only on this test's evidence.** If it fails, the
claim is withdrawn and the finding recorded -- `docs/07` §15.6 criterion 5 says so, and
that was committed before the run.

The run is two epochs, which is the smallest number that exercises an optimiser step, a
scheduler step and a validation pass. It costs ~8 minutes per run on this hardware, so it
is marked `slow` and `requires_data` and is not part of the default sweep.

**One declared deviation from the committed configuration**, and only one:
`optim.warmup_epochs` is lowered from 5 to `WARMUP_EPOCHS` because `build_scheduler`
refuses a warmup at least as long as the run, and rightly — a 2-epoch run with a 5-epoch
warmup would have no decay phase at all. Warmup length changes the learning rate, not
which kernels execute, so it does not affect what this test measures.
`test_TC_121_only_the_warmup_deviates_from_the_committed_config` asserts that this is the
*only* difference, so the deviation cannot quietly grow into a configuration nobody runs.
The warmup boundary itself is exercised on GPU by Stage 1b's resume (`docs/07` §15.6), not
here.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import torch
import yaml

from ocuval.data.splits import load as load_split
from ocuval.runs import load_manifest, manifest_path
from ocuval.training.loop import EPOCH_LOG, train_fold

pytestmark = [
    pytest.mark.slow,
    pytest.mark.requires_data,
    pytest.mark.skipif(not torch.cuda.is_available(), reason="TC-121 is the GPU claim"),
]

REPO_ROOT = Path(__file__).resolve().parents[1]
FOLD = "cirrus_holdout"
EPOCHS = 2
# 1, so epoch 0 is warmup and epoch 1 is decay: the SequentialLR transition happens inside
# the run rather than being skipped by it.
WARMUP_EPOCHS = 1


def committed_config() -> dict:
    return yaml.safe_load((REPO_ROOT / "configs" / "train_seg.yaml").read_text(encoding="utf-8"))


def config_under_test() -> dict:
    cfg = copy.deepcopy(committed_config())
    cfg["optim"]["warmup_epochs"] = WARMUP_EPOCHS
    return cfg


def digest(payload: object) -> str:
    """A hash of a checkpoint's tensors, in a fixed key order.

    Hashing `.numpy().tobytes()` rather than comparing with `torch.allclose`: this test
    exists to distinguish bit-identity from near-identity, and a tolerance would defeat
    its entire purpose.
    """
    hasher = hashlib.sha256()
    if isinstance(payload, dict):
        for key in sorted(payload, key=str):
            hasher.update(str(key).encode())
            hasher.update(digest(payload[key]).encode())
    elif isinstance(payload, list | tuple):
        for item in payload:
            hasher.update(digest(item).encode())
    elif torch.is_tensor(payload):
        hasher.update(payload.detach().cpu().numpy().tobytes())
    else:
        hasher.update(repr(payload).encode())
    return hasher.hexdigest()


def epoch_rows(run_dir: Path) -> list[dict]:
    lines = (run_dir / EPOCH_LOG).read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    return [r for r in rows if "train_loss" in r]


def run_once(run_dir: Path, cfg: dict, split, manifest) -> None:
    train_fold(
        split,
        cfg,
        manifest,
        run_dir,
        device="cuda",
        max_epochs=EPOCHS,
        telemetry_interval=None,
    )


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory):
    """Two independent runs of one configuration, from the committed config.

    The *committed* config, not a fixture's idea of one: this test verifies the claim made
    about real runs, and a locally assembled configuration would verify a different one
    (`docs/07` §3 rule 7 -- a fixture in the consuming code's convention cannot test the
    thing it consumes).
    """
    cfg = config_under_test()
    data_cfg = yaml.safe_load((REPO_ROOT / "configs" / "data.yaml").read_text(encoding="utf-8"))

    manifest_file = manifest_path(data_cfg)
    split_file = Path(data_cfg["paths"]["splits_root"]) / f"{FOLD}.json"
    if not Path(manifest_file).is_file() or not split_file.is_file():
        pytest.skip("RETOUCH manifest or splits absent; TC-121 needs the real fold")

    manifest = load_manifest(manifest_file)
    split = load_split(split_file)

    root = tmp_path_factory.mktemp("tc121")
    first, second = root / "run_a", root / "run_b"
    run_once(first, copy.deepcopy(cfg), split, manifest)
    run_once(second, copy.deepcopy(cfg), split, manifest)
    return first, second


def test_TC_121_the_configuration_under_test_is_the_one_that_was_decided():
    """Guards against this test passing on a configuration nobody runs.

    Two runs of a non-deterministic configuration can agree by luck on a short run; two
    runs of the *wrong* configuration agreeing says nothing at all. The claim is about
    `dice_ce_deterministic` with AMP on, so the test states which configuration its
    evidence covers.
    """
    cfg = committed_config()
    assert cfg["loss"]["name"] == "dice_ce_deterministic"
    assert cfg["train"]["amp"] is True
    assert cfg["run"]["deterministic"] is True


def test_TC_121_only_the_warmup_deviates_from_the_committed_config():
    """The one declared deviation must stay the only one.

    A test that quietly diverges from the shipped configuration produces evidence about
    something nobody runs -- which is exactly how the AMP decision came to be wrong
    (`docs/13`, 2026-09-30). So the difference is enumerated rather than trusted.
    """

    def flatten(node, prefix=""):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from flatten(value, f"{prefix}.{key}" if prefix else str(key))
        else:
            yield prefix, node

    committed = dict(flatten(committed_config()))
    under_test = dict(flatten(config_under_test()))
    differing = {k for k in committed | under_test if committed.get(k) != under_test.get(k)}
    assert differing == {"optim.warmup_epochs"}, (
        f"TC-121 runs a configuration differing from the committed one in {differing}. "
        f"Only optim.warmup_epochs may differ, and only because a 2-epoch run cannot "
        f"have a 5-epoch warmup."
    )


def test_TC_121_no_operation_fell_back_to_a_nondeterministic_kernel(two_runs):
    """SRS-085. The necessary half of the claim, and on its own not the sufficient half."""
    for run_dir in two_runs:
        record = json.loads((run_dir / "determinism.json").read_text(encoding="utf-8"))
        assert record["requested"] is True
        assert record.get("fallback_count", 0) == 0, (
            f"{run_dir.name} recorded {record['fallback_count']} non-deterministic "
            f"fallback(s): {record.get('fallbacks')}. The deterministic loss was adopted "
            f"to bring this to zero (SRS-084)."
        )
        assert record["deterministic_algorithms"] is True, (
            "the record does not claim achieved determinism, which since SRS-085 means "
            "something fell back"
        )


def test_TC_121_the_two_runs_trained_and_the_comparison_can_see_a_difference(two_runs):
    """Vacuity guard, and a negative control for the comparator.

    If both runs produced identical-but-trivial output -- no steps taken, weights still at
    initialisation -- every assertion below would pass while verifying nothing. And if
    `digest` could not distinguish two genuinely different tensors of this shape, the
    bit-identity test would be unfalsifiable.

    The control uses real data of the real shape: epoch 0's weights against epoch 1's,
    from the same run. They must differ, because training changed them.
    """
    first, _ = two_runs
    rows = epoch_rows(first)
    assert len(rows) == EPOCHS, f"expected {EPOCHS} epochs, found {len(rows)}"
    assert rows[0]["train_loss"] != rows[-1]["train_loss"], (
        "the loss did not move across the run, so these two runs may agree because "
        "nothing happened rather than because it happened identically"
    )

    last = torch.load(first / "last.pt", map_location="cpu", weights_only=False)
    best = torch.load(first / "best.pt", map_location="cpu", weights_only=False)
    if last["epoch"] != best["epoch"]:
        assert digest(last["model"]) != digest(best["model"]), (
            "two checkpoints from different epochs of one run hash identically, so "
            "`digest` cannot see a real difference and proves nothing below"
        )


def test_TC_121_model_weights_are_byte_identical(two_runs):
    first, second = two_runs
    a = torch.load(first / "last.pt", map_location="cpu", weights_only=False)
    b = torch.load(second / "last.pt", map_location="cpu", weights_only=False)
    assert a["epoch"] == b["epoch"]
    assert digest(a["model"]) == digest(b["model"]), (
        "two runs of one configuration produced different weights on GPU. CLAUDE.md "
        "rule 4 is NOT achieved on this device: the seed is recorded and the run is "
        "still not reproducible. Do not weaken this to a tolerance -- a tolerance here "
        "would assert near-determinism, which is the thing being distinguished from."
    )


def test_TC_121_optimiser_state_is_byte_identical(two_runs):
    """Weights alone are not enough: Adam's moments carry the trajectory forward.

    Two runs could agree on weights at epoch 2 and diverge afterwards if `exp_avg_sq`
    differed, so a resumed or continued run would not be the same run.
    """
    first, second = two_runs
    a = torch.load(first / "last.pt", map_location="cpu", weights_only=False)
    b = torch.load(second / "last.pt", map_location="cpu", weights_only=False)
    assert digest(a["optimizer"]) == digest(b["optimizer"]), (
        "optimiser state differs between two runs of one configuration, so the two runs "
        "would diverge from here even if their weights agree"
    )


def test_TC_121_the_epoch_log_is_identical(two_runs):
    """The loss log is the human-readable half of the claim.

    Compared exactly, not to a rounded number of places: the log is what a reader takes as
    the run's trajectory, and two trajectories that differ in the sixth decimal are two
    trajectories.
    """
    first, second = two_runs
    compared = ("epoch", "train_loss", "val_dice", "per_class_dice")
    a = [{k: r.get(k) for k in compared} for r in epoch_rows(first)]
    b = [{k: r.get(k) for k in compared} for r in epoch_rows(second)]
    assert a == b, f"the epoch logs differ:\n  run_a {a}\n  run_b {b}"
