"""TC-128: evaluation is seeded per volume and requests determinism, so two runs agree.

Verifies: SRS-091

Two unseeded evaluations of one checkpoint differed in 49 aggregate figures (`docs/13`,
2026-10-04). These tests pin the repair on CPU: a volume's MC-dropout result is a function of
`(seed, subject)` alone. It is the same across processes, and does not depend on what ran before
it. The GPU half of the claim -- that kernel choice does not reintroduce variation -- is not
testable here. It is verified by two evaluations of the open val bucket compared with
TC-127's comparator (`docs/07` §17.10).
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch

from ocuval.models.uncertainty import mc_dropout_predict, reseed_for_volume, volume_seed

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "05_evaluate.py"


def tiny() -> torch.nn.Module:
    """Conv + InstanceNorm + Dropout, the real network's layer kinds (as in TC-055)."""
    torch.manual_seed(0)
    return torch.nn.Sequential(
        torch.nn.Conv2d(1, 4, 3, padding=1),
        torch.nn.InstanceNorm2d(4),
        torch.nn.Dropout2d(0.5),
        torch.nn.Conv2d(4, 4, 1),
    )


def batch() -> torch.Tensor:
    return torch.randn(3, 1, 8, 8, generator=torch.Generator().manual_seed(1))


def predict(model, seed: int, subject: str) -> np.ndarray:
    reseed_for_volume(seed, subject)
    mean, _ = mc_dropout_predict(model, batch(), passes=5)
    return mean


def test_TC_128_the_volume_seed_is_a_pure_function_of_seed_and_subject():
    assert volume_seed(20260916, "TRAIN001") == volume_seed(20260916, "TRAIN001")
    assert volume_seed(20260916, "TRAIN001") != volume_seed(20260916, "TRAIN002")
    assert volume_seed(20260916, "TRAIN001") != volume_seed(20260917, "TRAIN001")
    assert 0 <= volume_seed(20260916, "TRAIN001") < 2**63 - 1


def test_TC_128_reseeding_makes_a_volume_identical_whatever_was_drawn_before():
    model = tiny()
    first = predict(model, 20260916, "TRAIN001")
    torch.rand(1000)  # anything else drawing from the global generator in between
    second = predict(model, 20260916, "TRAIN001")
    assert np.array_equal(first, second)


def test_TC_128_a_volume_does_not_depend_on_processing_order():
    model = tiny()
    a_first = predict(model, 20260916, "TRAIN001")
    predict(model, 20260916, "TRAIN002")
    predict(model, 20260916, "TRAIN002")
    a_after_b = predict(model, 20260916, "TRAIN001")
    assert np.array_equal(a_first, a_after_b)


def test_TC_128_the_mechanism_can_fail_a_different_seed_or_subject_changes_the_draws():
    """Rule 8: identical outputs prove nothing unless different inputs can change them."""
    model = tiny()
    base = predict(model, 20260916, "TRAIN001")
    assert not np.array_equal(base, predict(model, 20260917, "TRAIN001"))
    assert not np.array_equal(base, predict(model, 20260916, "TRAIN002"))
    # And without reseeding, consecutive draws differ: dropout is genuinely active.
    mean_1, _ = mc_dropout_predict(model, batch(), passes=5)
    mean_2, _ = mc_dropout_predict(model, batch(), passes=5)
    assert not np.array_equal(mean_1, mean_2)


PROGRAM = """
import hashlib, torch
from ocuval.models.uncertainty import mc_dropout_predict, reseed_for_volume
torch.manual_seed(0)
model = torch.nn.Sequential(
    torch.nn.Conv2d(1, 4, 3, padding=1), torch.nn.InstanceNorm2d(4),
    torch.nn.Dropout2d(0.5), torch.nn.Conv2d(4, 4, 1),
)
x = torch.randn(3, 1, 8, 8, generator=torch.Generator().manual_seed(1))
torch.rand(int(__import__("sys").argv[1]))  # a different amount of prior RNG use per process
reseed_for_volume(20260916, "TRAIN001")
mean, _ = mc_dropout_predict(model, x, passes=5)
print(hashlib.sha256(mean.tobytes()).hexdigest())
"""


def test_TC_128_two_separate_processes_produce_byte_identical_results():
    digests = [
        subprocess.run(
            [sys.executable, "-c", PROGRAM, str(prior)],
            capture_output=True,
            text=True,
            check=True,
            env={**__import__("os").environ, "CUDA_VISIBLE_DEVICES": "-1"},
        ).stdout.strip()
        for prior in (0, 777)
    ]
    assert len(digests[0]) == 64
    assert digests[0] == digests[1]
    in_process = hashlib.sha256(predict(tiny(), 20260916, "TRAIN001").tobytes()).hexdigest()
    assert in_process == digests[0]


def _main_function() -> ast.FunctionDef:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")


def _calls(node: ast.AST) -> list[tuple[int, str]]:
    found = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            found.append((sub.lineno, name))
    return found


def test_TC_128_the_evaluation_script_requests_determinism_before_the_model_reaches_the_device():
    """The wiring, inspected rather than assumed: the request precedes `build_model`."""
    calls = _calls(_main_function())
    first = {name: line for line, name in sorted(calls, reverse=True)}
    assert "request_determinism" in first, "evaluation never requests determinism"
    assert first["request_determinism"] < first["build_model"]


def test_TC_128_the_evaluation_script_reseeds_each_volume_immediately_before_predicting_it():
    main = _main_function()
    loops = [n for n in ast.walk(main) if isinstance(n, ast.For)]
    volume_loop = next(
        loop for loop in loops if any(name == "predict_volume" for _, name in _calls(loop))
    )
    names = [name for _, name in sorted(_calls(volume_loop))]
    reseed_at = names.index("reseed_for_volume")
    predict_at = names.index("predict_volume")
    assert reseed_at < predict_at
    # Nothing that draws from torch's generator sits between the two.
    assert names[reseed_at + 1 : predict_at] in ([], ["stack", "int"], ["int", "stack"])
    assert "describe_determinism" in [name for _, name in _calls(main)]
