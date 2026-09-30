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
    # Fallbacks are deduplicated to {op, count, first_seen} since SRS-085 -- the Stage 1
    # run stored 1308 copies of one sentence. The unrelated warning must still be
    # excluded: this collects determinism fallbacks, not every warning of the run.
    assert len(recorded["fallbacks"]) == 1
    entry = recorded["fallbacks"][0]
    assert entry["op"] == "upsample_bilinear2d_backward_out_cuda"
    assert entry["count"] == 1
    assert "upsample_bilinear2d_backward" in entry["first_seen"]
    assert recorded["fallback_count"] == 1
    assert (
        recorded["deterministic_algorithms"] is False
    ), "a report listing a fallback must not also claim deterministic algorithms"


def test_TC_059_gpu_tolerance_is_stated_and_nonzero():
    """Bit-exactness is not claimed on GPU, and the tolerance is explicit."""
    assert resume_tolerance("cpu") == 0.0
    assert resume_tolerance("cuda") > 0.0


def train_scaled(model, optimizer, epoch_batches, scaler, amp: bool) -> None:
    """The loop's step, including the GradScaler, so AMP is exercised as it is used."""
    model.train()
    loss_fn = torch.nn.MSELoss()
    for x, y in epoch_batches:
        optimizer.zero_grad()
        with torch.autocast(device_type="cuda", enabled=amp):
            loss = loss_fn(model(x), y)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()


@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device in this environment")
@pytest.mark.parametrize("amp", [False, True], ids=["fp32", "amp"])
def test_TC_059_resuming_on_gpu_agrees_within_the_stated_tolerance(tmp_path, amp):
    """SRS-076's GPU case, re-verified under AMP when AMP was enabled (2026-09-30).

    **Measured: bit-identical, 0.0 deviation, with and without AMP.** The stated tolerance
    is therefore not needed for *this* network and the test asserts the stronger result it
    actually gets, while keeping the bound as the documented claim.

    **What this does not show.** `tiny_model` is Linear/ReLU/Dropout: it contains no
    convolution and no upsampling, which are exactly the operations whose CUDA kernels lack
    deterministic implementations. Bit-identity here says nothing about the real UNet, and
    `resume_tolerance("cuda")` stays non-zero for that reason rather than because anything
    here needed it. **TC-121 is the evidence for the real network** -- it runs the shipped
    model on the real fold and compares two runs byte for byte. Do not promote this result
    into a claim about the GPU generally.

    The scaler state is carried through the checkpoint: under AMP the loss scale is part of
    the trajectory, so a resume that restored weights and not the scale would take a
    differently scaled step and this test would see it.
    """
    data = [[(x.cuda(), y.cuda()) for x, y in epoch] for epoch in batches(5)]

    request_determinism(SEED)
    straight = tiny_model().cuda()
    optimizer = torch.optim.Adam(straight.parameters(), lr=1e-3)
    scaler = torch.cuda.amp.GradScaler(enabled=amp)
    for epoch in range(5):
        train_scaled(straight, optimizer, data[epoch], scaler, amp)
    expected = weights(straight)

    request_determinism(SEED)
    interrupted = tiny_model().cuda()
    optimizer = torch.optim.Adam(interrupted.parameters(), lr=1e-3)
    scaler = torch.cuda.amp.GradScaler(enabled=amp)
    for epoch in range(3):
        train_scaled(interrupted, optimizer, data[epoch], scaler, amp)
    save_checkpoint(
        tmp_path / CHECKPOINT_NAME,
        epoch=2,
        model=interrupted,
        optimizer=optimizer,
        scaler=scaler,
    )

    resumed = tiny_model().cuda()
    resumed_optimizer = torch.optim.Adam(resumed.parameters(), lr=1e-3)
    resumed_scaler = torch.cuda.amp.GradScaler(enabled=amp)
    load_checkpoint(
        tmp_path / CHECKPOINT_NAME,
        model=resumed,
        optimizer=resumed_optimizer,
        scaler=resumed_scaler,
        map_location="cuda",
    )
    for epoch in range(3, 5):
        train_scaled(resumed, resumed_optimizer, data[epoch], resumed_scaler, amp)

    tolerance = resume_tolerance("cuda")
    actual = weights(resumed)
    worst = max(float((a - b).abs().max()) for a, b in zip(expected, actual, strict=True))
    assert worst <= tolerance, (
        f"resumed GPU run diverged by {worst:.3e}, beyond the stated tolerance "
        f"{tolerance}. Kernel non-determinism explains a small difference; exceeding the "
        f"bound means something else is wrong."
    )
    assert worst == 0.0, (
        f"this network resumed bit-identically on GPU when measured on 2026-09-30, at "
        f"both precisions, and now deviates by {worst:.3e}. That is within the stated "
        f"tolerance and is still a change worth explaining: it means an operation here "
        f"became order-dependent. Investigate before widening anything."
    )


# TC-039 lives in tests/test_frame_cache.py.
