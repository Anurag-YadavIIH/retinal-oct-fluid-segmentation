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


def loss_fn():
    from monai.losses import DiceCELoss

    return DiceCELoss(include_background=False, to_onehot_y=True, softmax=True)


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


def whole_batch_gradient(model, images, labels):
    model.zero_grad(set_to_none=True)
    loss_fn()(model(images), labels).backward()
    return gradients_of(model)


def accumulated_gradient(model, images, labels, steps, *, scale=True):
    model.zero_grad(set_to_none=True)
    micro = images.shape[0] // steps
    criterion = loss_fn()
    for index in range(steps):
        chunk = slice(index * micro, (index + 1) * micro)
        loss = criterion(model(images[chunk]), labels[chunk])
        (loss / steps if scale else loss).backward()
    return gradients_of(model)


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
