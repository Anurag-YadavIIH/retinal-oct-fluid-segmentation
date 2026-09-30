"""Verification of gradient accumulation (TC-078, SRS-079).

The equivalence rests on a property of the network, not on a numerical coincidence:
nothing in it couples samples within a batch. `docs/07` §14 records that the built model
uses eight `InstanceNorm2d` layers and zero batch-normalisation layers, checked by
inspecting the constructed module tree. Under batch normalisation the accumulated
gradient would be the gradient of a *different function* and no tolerance would make it
equivalent, so the first test here is the structural one.
"""

from __future__ import annotations

import copy

import pytest
import torch

from ocuval.data.datamodule import accumulation_plan
from ocuval.models.seg_unet import build_model

# docs/07 §14. For float32 summation reordering over four additions.
RTOL = 1e-4
ATOL = 1e-6
# AMP was enabled on 2026-09-30 (docs/13) and fp16 rounding is coarser by orders of
# magnitude. Measured over 72 cases -- 12 seeds x {2,4,8} steps x both losses -- the worst
# deviation needs atol = 1.96e-05, so 5e-5 leaves 2.55x headroom.
#
# This bound was FIRST SET AT 1e-5 from a single seed and a second seed exceeded it at
# 1.53e-05 (docs/07 §14, docs/13). A tolerance derived from one sample is a guess; the
# seeds are parametrised below so the bound is exercised more than once.
#
# This is NOT the widening CLAUDE.md forbids -- that rule is about batch normalisation
# making the accumulated gradient the gradient of a different function, where no tolerance
# is correct. Here the function is identical and only the precision changed.
AMP_ATOL = 5e-5
AMP_SEEDS = [0, 4, 7, 11]

CFG = {
    "data": {"mode": "2d"},
    "model": {
        "name": "unet",
        "in_channels": 1,
        "out_channels": 4,
        "channels": [4, 8, 16],
        "strides": [2, 2],
        "dropout": 0.2,
    },
    "train": {"batch_size": 8, "micro_batch_size": 2},
}


def fixture_batch(n=8, size=32, seed=0):
    generator = torch.Generator().manual_seed(seed)
    images = torch.randn(n, 1, size, size, generator=generator)
    labels = torch.randint(0, 4, (n, 1, size, size), generator=generator)
    return images, labels


def gradients_of(model):
    return [p.grad.detach().clone() for p in model.parameters() if p.grad is not None]


def loss_fn(name: str = "dice_ce_deterministic"):
    """Built through `build_loss`, so the equivalence is verified for the loss that runs.

    Was a locally constructed `DiceCELoss`, which meant this test verified accumulation for
    a loss the configuration no longer names (SRS-084, adopted 2026-09-30). Both are
    parametrised below, because §14's claim that the substitution does not move the
    tolerance is only established by measuring both.
    """
    from ocuval.training.loop import build_loss

    return build_loss(
        {"loss": {"name": name, "include_background": False, "to_onehot_y": True, "softmax": True}}
    )


# --- the structural precondition ------------------------------------------------------


def test_TC_078_network_uses_instance_norm_not_batch_norm():
    """The precondition for equivalence, asserted rather than assumed.

    If this ever fails, gradient accumulation stops being equivalent and the fix is to
    stop accumulating -- not to widen the tolerance.
    """
    model = build_model(CFG)
    batch_norms = [
        m
        for m in model.modules()
        if isinstance(m, torch.nn.modules.batchnorm._BatchNorm)  # noqa: SLF001
    ]
    instance_norms = [
        m
        for m in model.modules()
        if isinstance(m, torch.nn.modules.instancenorm._InstanceNorm)  # noqa: SLF001
    ]
    assert not batch_norms, (
        f"{len(batch_norms)} batch-normalisation layer(s) found. Batch-norm statistics "
        f"over a micro-batch differ from statistics over the effective batch, so the "
        f"accumulated gradient would be the gradient of a different function. "
        f"Accumulation must be disabled, not re-toleranced (docs/07 §14)."
    )
    assert instance_norms, "expected instance normalisation in the built network"


# --- TC-078: the equivalence -----------------------------------------------------------


def whole_batch_gradient(model, images, labels, *, loss="dice_ce_deterministic"):
    model.zero_grad(set_to_none=True)
    loss_fn(loss)(model(images), labels).backward()
    return gradients_of(model)


def accumulated_gradient(model, images, labels, steps, *, scale=True, loss="dice_ce_deterministic"):
    model.zero_grad(set_to_none=True)
    micro = images.shape[0] // steps
    criterion = loss_fn(loss)
    for index in range(steps):
        chunk = slice(index * micro, (index + 1) * micro)
        value = criterion(model(images[chunk]), labels[chunk])
        (value / steps if scale else value).backward()
    return gradients_of(model)


LOSSES = ["dice_ce", "dice_ce_deterministic"]


def test_TC_078_one_step_of_eight_equals_four_micro_batches_of_two():
    """The claim SRS-079 makes, at the sizes this workstation will actually use."""
    torch.manual_seed(0)
    model = build_model(CFG)
    model.eval()  # dropout off: this is about batching, not about stochastic layers
    images, labels = fixture_batch(8)

    whole = whole_batch_gradient(model, images, labels)
    accumulated = accumulated_gradient(model, images, labels, steps=4)

    assert len(whole) == len(accumulated) > 0
    for a, b in zip(whole, accumulated, strict=True):
        assert torch.allclose(a, b, rtol=RTOL, atol=ATOL), (
            f"accumulated gradient differs from the whole-batch gradient by "
            f"{(a - b).abs().max():.3e}, outside rtol={RTOL} atol={ATOL} (docs/07 §14)"
        )


@pytest.mark.parametrize("steps", [2, 4, 8])
def test_TC_078_equivalence_holds_at_every_dividing_micro_batch(steps):
    torch.manual_seed(0)
    model = build_model(CFG)
    model.eval()
    images, labels = fixture_batch(8, seed=steps)
    whole = whole_batch_gradient(model, images, labels)
    accumulated = accumulated_gradient(model, images, labels, steps=steps)
    for a, b in zip(whole, accumulated, strict=True):
        assert torch.allclose(a, b, rtol=RTOL, atol=ATOL)


@pytest.mark.parametrize("loss", LOSSES)
def test_TC_078_the_loss_substitution_does_not_move_the_tolerance(loss):
    """§14's claim that the deterministic loss is a substitution, not an approximation.

    If the replacement changed the function rather than the summation order, the
    accumulation deviation would differ between the two losses. Measured 2026-09-30 it does
    not: both need `atol = 1.88e-10` on CPU, identically. That is independent evidence for
    TC-089's claim, arrived at by a different route.
    """
    torch.manual_seed(0)
    model = build_model(CFG)
    model.eval()
    images, labels = fixture_batch(8)
    whole = whole_batch_gradient(model, images, labels, loss=loss)
    accumulated = accumulated_gradient(model, images, labels, steps=4, loss=loss)
    for a, b in zip(whole, accumulated, strict=True):
        assert torch.allclose(a, b, rtol=RTOL, atol=ATOL), (
            f"accumulation under {loss} deviates by {(a - b).abs().max():.3e}, outside "
            f"rtol={RTOL} atol={ATOL}. docs/07 §14 records both losses at 1.88e-10."
        )


# --- TC-078 under AMP, enabled 2026-09-30 ---------------------------------------------
#
# AMP changes the arithmetic, so the tolerance was re-measured rather than assumed to
# carry over -- which is the mistake that made the original AMP decision wrong.


def amp_gradients(model, images, labels, steps, *, scale=True):
    """Whole-batch and accumulated gradients under autocast, sharing one GradScaler.

    One scaler, as `train_fold` uses one: the scale factor must be identical across the
    micro-batches of a step, or their sum is not the accumulated gradient of anything. Both
    results are unscaled by the same factor before comparison, so the comparison is between
    gradients and not between scaled gradients.
    """
    scaler = torch.cuda.amp.GradScaler(enabled=True)

    def run(chunks):
        model.zero_grad(set_to_none=True)
        criterion = loss_fn()
        for chunk, divisor in chunks:
            with torch.autocast(device_type="cuda", enabled=True):
                value = criterion(model(images[chunk]), labels[chunk])
            scaler.scale(value / divisor if scale else value).backward()
        return [g / scaler.get_scale() for g in gradients_of(model)]

    micro = images.shape[0] // steps
    whole = run([(slice(None), 1)])
    parts = [(slice(i * micro, (i + 1) * micro), steps) for i in range(steps)]
    return whole, run(parts)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="AMP equivalence is a CUDA claim")
@pytest.mark.parametrize("steps", [2, 4, 8])
@pytest.mark.parametrize("seed", AMP_SEEDS)
def test_TC_078_equivalence_holds_under_amp_at_the_wider_tolerance(steps, seed):
    """docs/07 §14: `atol = 5e-5` under AMP, measured as needing up to 1.96e-05.

    The bound is 50x the fp32 one and that widening is recorded with its measurement. It
    binds no planned run -- `micro_batch_size` equals `batch_size`, so accumulation_steps
    is 1 and there is nothing to reorder -- and is measured now rather than when a smaller
    card forces accumulation and nobody wants to stop.

    **Parametrised over seeds deliberately.** The first version of this test used one seed,
    the bound was set from it, and another seed exceeded it immediately. The seeds include
    the two that produced the worst deviations of the 72 measured.
    """
    torch.manual_seed(0)
    model = build_model(CFG).cuda()
    model.eval()
    images, labels = fixture_batch(8, seed=seed)
    whole, accumulated = amp_gradients(model, images.cuda(), labels.cuda(), steps)
    for a, b in zip(whole, accumulated, strict=True):
        assert torch.allclose(a, b, rtol=RTOL, atol=AMP_ATOL), (
            f"accumulation under AMP deviates by {(a - b).abs().max():.3e} at {steps} "
            f"steps, outside rtol={RTOL} atol={AMP_ATOL} (docs/07 §14)"
        )


@pytest.mark.skipif(not torch.cuda.is_available(), reason="AMP equivalence is a CUDA claim")
def test_TC_078_the_wider_amp_tolerance_still_rejects_unscaled_accumulation():
    """A bound loosened 50x is only a bound if it still catches what it was written for.

    Without this, `atol = 5e-5` would be an unverified relaxation: the fp32 negative case
    would still pass and say nothing about whether the AMP one discriminates.
    """
    torch.manual_seed(0)
    model = build_model(CFG).cuda()
    model.eval()
    images, labels = fixture_batch(8)
    whole, unscaled = amp_gradients(model, images.cuda(), labels.cuda(), steps=4, scale=False)
    assert any(
        not torch.allclose(a, b, rtol=RTOL, atol=AMP_ATOL)
        for a, b in zip(whole, unscaled, strict=True)
    ), "the widened AMP tolerance cannot distinguish correct accumulation from no scaling"


@pytest.mark.skipif(not torch.cuda.is_available(), reason="AMP equivalence is a CUDA claim")
def test_TC_078_the_amp_tolerance_is_needed_and_not_merely_generous():
    """The fp32 bound must actually fail under AMP, or the widening was unnecessary.

    §14 records `atol = 1e-6` as insufficient under AMP. If that were wrong the honest
    change would be to keep the tighter bound, so the claim is asserted rather than trusted.
    """
    torch.manual_seed(0)
    model = build_model(CFG).cuda()
    model.eval()
    images, labels = fixture_batch(8)
    whole, accumulated = amp_gradients(model, images.cuda(), labels.cuda(), steps=4)
    assert any(
        not torch.allclose(a, b, rtol=RTOL, atol=ATOL)
        for a, b in zip(whole, accumulated, strict=True)
    ), (
        "AMP accumulation stayed inside the fp32 tolerance, so docs/07 §14's widening to "
        "5e-5 is not justified by this hardware and should be reverted rather than kept"
    )


def test_TC_078_omitting_the_loss_scaling_is_detected():
    """Guards the guard.

    Without the 1/steps scaling the gradient is `steps` times too large. If the
    tolerance could not tell that apart from correct accumulation, the test above would
    pass on an implementation that does not accumulate at all.
    """
    torch.manual_seed(0)
    model = build_model(CFG)
    model.eval()
    images, labels = fixture_batch(8)

    whole = whole_batch_gradient(model, images, labels)
    unscaled = accumulated_gradient(model, images, labels, steps=4, scale=False)

    assert any(
        not torch.allclose(a, b, rtol=RTOL, atol=ATOL) for a, b in zip(whole, unscaled, strict=True)
    ), "the tolerance cannot distinguish correct accumulation from no scaling at all"


def test_TC_078_accumulation_is_not_vacuous():
    """A model whose gradients were all zero would satisfy any comparison."""
    torch.manual_seed(0)
    model = build_model(CFG)
    model.eval()
    images, labels = fixture_batch(8)
    whole = whole_batch_gradient(model, images, labels)
    assert any(g.abs().max() > 0 for g in whole), "all gradients are zero"


# --- the plan ---------------------------------------------------------------------------


def test_TC_078_plan_reports_micro_steps_and_effective_batch():
    assert accumulation_plan(CFG) == (2, 4, 8)


def test_TC_078_micro_batch_defaults_to_the_effective_batch():
    cfg = copy.deepcopy(CFG)
    del cfg["train"]["micro_batch_size"]
    assert accumulation_plan(cfg) == (8, 1, 8)


@pytest.mark.parametrize("micro", [3, 5, 6, 7])
def test_TC_078_a_micro_batch_that_does_not_divide_is_refused(micro):
    """An uneven final micro-batch would weight its samples differently."""
    cfg = copy.deepcopy(CFG)
    cfg["train"]["micro_batch_size"] = micro
    with pytest.raises(ValueError, match="does not divide"):
        accumulation_plan(cfg)


def test_TC_078_micro_batch_larger_than_the_effective_batch_is_refused():
    cfg = copy.deepcopy(CFG)
    cfg["train"]["micro_batch_size"] = 16
    with pytest.raises(ValueError, match="exceeds"):
        accumulation_plan(cfg)


def test_TC_078_the_shipped_config_is_self_consistent():
    from pathlib import Path

    import yaml

    cfg = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "configs" / "train_seg.yaml").read_text(
            encoding="utf-8"
        )
    )
    micro, steps, effective = accumulation_plan(cfg)
    assert effective == int(cfg["train"]["batch_size"])
    assert micro * steps == effective
