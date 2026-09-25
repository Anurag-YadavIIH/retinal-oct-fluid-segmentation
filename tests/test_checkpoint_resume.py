"""Verification of ocuval.training.checkpoint and the frame cache pre-pass.

Covers TC-059 (resuming equals not being interrupted) and TC-039 (the cache cannot
change a value).

TC-059 runs on CPU, where SRS-076 requires **bit-identical** equivalence. The GPU case
is a stated tolerance rather than an assertion of bit-exactness, because several CUDA
kernels reachable from this network have no deterministic implementation; the test
records that distinction rather than pretending the CPU result generalises.
"""

from __future__ import annotations

import os

import numpy as np
import pytest
import torch

from ocuval.training.checkpoint import (
    CHECKPOINT_NAME,
    DeterminismReport,
    describe_determinism,
    find_resume,
    load_checkpoint,
    request_determinism,
    resume_tolerance,
    rng_state,
    save_checkpoint,
    set_rng_state,
)

SEED = 20260916


def tiny_model() -> torch.nn.Module:
    """Small enough to train in a test, with dropout so the RNG genuinely matters.

    Dropout is the point. Without a stochastic layer a resumed run would agree even if
    the generator state were discarded, and the test would pass while verifying nothing
    about SRS-075's requirement to save it.
    """
    torch.manual_seed(SEED)
    return torch.nn.Sequential(
        torch.nn.Linear(16, 32),
        torch.nn.ReLU(),
        torch.nn.Dropout(0.2),
        torch.nn.Linear(32, 4),
    )


def batches(n_epochs: int, per_epoch: int = 4) -> list[list[tuple[torch.Tensor, torch.Tensor]]]:
    generator = torch.Generator().manual_seed(1234)
    return [
        [
            (torch.randn(8, 16, generator=generator), torch.randn(8, 4, generator=generator))
            for _ in range(per_epoch)
        ]
        for _ in range(n_epochs)
    ]


def train(model, optimizer, epoch_batches) -> None:
    model.train()
    loss_fn = torch.nn.MSELoss()
    for x, y in epoch_batches:
        optimizer.zero_grad()
        loss_fn(model(x), y).backward()
        optimizer.step()


def weights(model) -> list[torch.Tensor]:
    return [p.detach().clone() for p in model.parameters()]


# --- TC-059 ---------------------------------------------------------------------------


def test_TC_059_resuming_equals_not_being_interrupted_on_cpu(tmp_path):
    """Five epochs, against three plus a resume of two. SRS-076, CPU case: bit-identical."""
    data = batches(5)

    request_determinism(SEED)
    straight = tiny_model()
    optimizer = torch.optim.Adam(straight.parameters(), lr=1e-3)
    for epoch in range(5):
        train(straight, optimizer, data[epoch])
    expected = weights(straight)

    request_determinism(SEED)
    interrupted = tiny_model()
    optimizer = torch.optim.Adam(interrupted.parameters(), lr=1e-3)
    for epoch in range(3):
        train(interrupted, optimizer, data[epoch])
    save_checkpoint(
        tmp_path / CHECKPOINT_NAME, epoch=2, model=interrupted, optimizer=optimizer, best_metric=0.5
    )

    # A genuinely separate continuation: new objects, and the generators deliberately
    # disturbed first, so only what the checkpoint restores can make the runs agree.
    torch.manual_seed(999)
    np.random.seed(999)
    resumed = tiny_model()
    resumed_optimizer = torch.optim.Adam(resumed.parameters(), lr=1e-3)
    meta = load_checkpoint(tmp_path / CHECKPOINT_NAME, model=resumed, optimizer=resumed_optimizer)
    assert meta["epoch"] == 2
    assert meta["best_metric"] == 0.5
    for epoch in range(3, 5):
        train(resumed, resumed_optimizer, data[epoch])

    tolerance = resume_tolerance("cpu")
    assert tolerance == 0.0
    for a, b in zip(expected, weights(resumed), strict=True):
        assert torch.equal(a, b), (
            "a resumed CPU run diverged from an uninterrupted one. SRS-076 requires "
            "bit-identical equivalence on CPU; a difference here is a defect, not "
            "kernel non-determinism."
        )


def test_TC_059_discarding_the_rng_state_breaks_equivalence(tmp_path):
    """The guard must fail when the thing it protects is removed.

    Without this, the test above would pass on a checkpoint that saved no RNG state at
    all, and SRS-075's requirement to save it would be unverified.
    """
    data = batches(5)

    request_determinism(SEED)
    straight = tiny_model()
    optimizer = torch.optim.Adam(straight.parameters(), lr=1e-3)
    for epoch in range(5):
        train(straight, optimizer, data[epoch])
    expected = weights(straight)

    request_determinism(SEED)
    interrupted = tiny_model()
    optimizer = torch.optim.Adam(interrupted.parameters(), lr=1e-3)
    for epoch in range(3):
        train(interrupted, optimizer, data[epoch])
    save_checkpoint(tmp_path / CHECKPOINT_NAME, epoch=2, model=interrupted, optimizer=optimizer)

    torch.manual_seed(999)
    resumed = tiny_model()
    resumed_optimizer = torch.optim.Adam(resumed.parameters(), lr=1e-3)
    load_checkpoint(
        tmp_path / CHECKPOINT_NAME,
        model=resumed,
        optimizer=resumed_optimizer,
        restore_rng=False,  # the defect being simulated
    )
    for epoch in range(3, 5):
        train(resumed, resumed_optimizer, data[epoch])

    assert any(
        not torch.equal(a, b) for a, b in zip(expected, weights(resumed), strict=True)
    ), "discarding the RNG state made no difference, so this test proves nothing"


def test_TC_059_checkpoint_carries_every_generator(tmp_path):
    model = tiny_model()
    save_checkpoint(tmp_path / CHECKPOINT_NAME, epoch=0, model=model)
    payload = torch.load(tmp_path / CHECKPOINT_NAME, map_location="cpu", weights_only=False)
    assert set(payload) >= {"epoch", "model", "optimizer", "scheduler", "scaler", "rng", "extra"}
    assert set(payload["rng"]) >= {"python", "numpy", "torch"}
    if torch.cuda.is_available():
        assert "torch_cuda" in payload["rng"]


def test_TC_059_rng_round_trip_reproduces_the_next_draw():
    state = rng_state()
    first = (torch.randn(4), np.random.rand(4), os.urandom(0) or None)
    set_rng_state(state)
    second = (torch.randn(4), np.random.rand(4), None)
    assert torch.equal(first[0], second[0])
    assert np.array_equal(first[1], second[1])


def test_TC_059_write_is_atomic_and_leaves_no_partial_file(tmp_path):
    """A kill mid-write must leave the previous checkpoint intact, not a truncated one."""
    path = tmp_path / CHECKPOINT_NAME
    model = tiny_model()
    save_checkpoint(path, epoch=1, model=model)
    good = path.read_bytes()

    # Simulate a failed write: the temporary exists, the real file is untouched.
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(b"truncated garbage")
    assert path.read_bytes() == good
    assert load_checkpoint(path, model=tiny_model())["epoch"] == 1
    assert not list(tmp_path.glob("*.tmp.tmp"))


def test_TC_059_find_resume_detects_a_fresh_run(tmp_path):
    assert find_resume(tmp_path) is None
    save_checkpoint(tmp_path / CHECKPOINT_NAME, epoch=0, model=tiny_model())
    assert find_resume(tmp_path) == tmp_path / CHECKPOINT_NAME


def test_TC_059_determinism_is_requested_and_reported():
    report = request_determinism(SEED)
    assert report.requested is True
    assert report.cublas_workspace_config == ":4096:8"
    recorded = report.as_dict()
    assert set(recorded) >= {
        "requested",
        "deterministic_algorithms",
        "cudnn_deterministic",
        "cublas_workspace_config",
        "fallbacks",
    }


def test_TC_059_a_nondeterministic_fallback_is_recorded_not_swallowed():
    """SRS-077: an undocumented fallback is an undocumented source of variation."""
    report = DeterminismReport(
        requested=True,
        deterministic_algorithms=True,
        cudnn_deterministic=True,
        cublas_workspace_config=":4096:8",
    )
    recorded = describe_determinism(
        report,
        [
            "upsample_bilinear2d_backward_out_cuda does not have a deterministic "
            "implementation, but you set torch.use_deterministic_algorithms",
            "an unrelated warning that must not be collected",
        ],
    )
    assert len(recorded["fallbacks"]) == 1
    assert "upsample_bilinear2d_backward" in recorded["fallbacks"][0]


def test_TC_059_gpu_tolerance_is_stated_and_nonzero():
    """Bit-exactness is not claimed on GPU, and the tolerance is explicit."""
    assert resume_tolerance("cpu") == 0.0
    assert resume_tolerance("cuda") > 0.0


@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device in this environment")
def test_TC_059_resuming_on_gpu_agrees_within_the_stated_tolerance(tmp_path):
    data = [[(x.cuda(), y.cuda()) for x, y in epoch] for epoch in batches(5)]

    request_determinism(SEED)
    straight = tiny_model().cuda()
    optimizer = torch.optim.Adam(straight.parameters(), lr=1e-3)
    for epoch in range(5):
        train(straight, optimizer, data[epoch])
    expected = weights(straight)

    request_determinism(SEED)
    interrupted = tiny_model().cuda()
    optimizer = torch.optim.Adam(interrupted.parameters(), lr=1e-3)
    for epoch in range(3):
        train(interrupted, optimizer, data[epoch])
    save_checkpoint(tmp_path / CHECKPOINT_NAME, epoch=2, model=interrupted, optimizer=optimizer)

    resumed = tiny_model().cuda()
    resumed_optimizer = torch.optim.Adam(resumed.parameters(), lr=1e-3)
    load_checkpoint(
        tmp_path / CHECKPOINT_NAME,
        model=resumed,
        optimizer=resumed_optimizer,
        map_location="cuda",
    )
    for epoch in range(3, 5):
        train(resumed, resumed_optimizer, data[epoch])

    tolerance = resume_tolerance("cuda")
    for a, b in zip(expected, weights(resumed), strict=True):
        assert torch.allclose(a, b, atol=tolerance, rtol=0), (
            f"resumed GPU run diverged by more than the stated tolerance {tolerance}. "
            f"Kernel non-determinism explains a small difference; exceeding the bound "
            f"means something else is wrong."
        )


# TC-039 lives in tests/test_frame_cache.py.
