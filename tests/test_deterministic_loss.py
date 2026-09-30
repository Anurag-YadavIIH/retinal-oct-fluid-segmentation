"""Back-to-back verification of the deterministic loss against MONAI (TC-089, SRS-084).

The arrangement is TC-120's, and exists for the same reason: an independent
implementation is worth having only if something checks it against the reference. Here
the reference is `monai.losses.DiceCELoss`, which is what the project used until the
Stage 1 run recorded 1308 `nll_loss2d_forward_out_cuda_template` determinism fallbacks.

**Tolerance.** `rtol = 1e-5`, `atol = 1e-7` at float32. The two implementations compute
the same function and differ only in floating-point summation order -- `log_softmax` +
`gather` + `mean` against `nll_loss2d`. A bound this tight would not survive an
algebraic difference, which is the point: it distinguishes a reordering from a different
loss.
"""

from __future__ import annotations

import pytest
import torch

from ocuval.training.losses import DeterministicDiceCELoss, deterministic_cross_entropy

RTOL, ATOL = 1e-5, 1e-7
CLASSES = 4


def fixture(batch=2, height=24, width=16, seed=0, device="cpu"):
    generator = torch.Generator(device="cpu").manual_seed(seed)
    logits = torch.randn(batch, CLASSES, height, width, generator=generator).to(device)
    target = torch.randint(0, CLASSES, (batch, 1, height, width), generator=generator).to(device)
    return logits, target


# --- the cross-entropy term on its own ------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_TC_089_cross_entropy_matches_torch_reference(seed):
    """Against `nn.CrossEntropyLoss`, which is what MONAI calls internally."""
    logits, target = fixture(seed=seed)
    reference = torch.nn.CrossEntropyLoss(reduction="mean")(logits, target.squeeze(1).long())
    measured = deterministic_cross_entropy(logits, target)
    assert measured.item() == pytest.approx(reference.item(), rel=RTOL, abs=ATOL)


def test_TC_089_cross_entropy_accepts_target_with_or_without_a_channel():
    logits, target = fixture(seed=7)
    with_channel = deterministic_cross_entropy(logits, target)
    without_channel = deterministic_cross_entropy(logits, target.squeeze(1))
    assert with_channel.item() == pytest.approx(without_channel.item(), rel=RTOL, abs=ATOL)


def test_TC_089_a_multichannel_target_is_refused_rather_than_guessed():
    logits, _ = fixture(seed=8)
    bad = torch.zeros(2, CLASSES, 24, 16)
    with pytest.raises(ValueError, match="single channel"):
        deterministic_cross_entropy(logits, bad)


# --- the whole loss, back to back -----------------------------------------------------


@pytest.mark.parametrize("seed", range(8))
def test_TC_089_total_loss_matches_monai_dice_ce(seed):
    from monai.losses import DiceCELoss

    logits, target = fixture(seed=seed)
    reference = DiceCELoss(include_background=False, to_onehot_y=True, softmax=True)
    measured = DeterministicDiceCELoss(include_background=False, to_onehot_y=True, softmax=True)
    expected = reference(logits, target).item()
    actual = measured(logits, target).item()
    assert actual == pytest.approx(expected, rel=RTOL, abs=ATOL), (
        f"seed {seed}: {actual} against MONAI's {expected}. The replacement is meant to "
        f"be the same function in a different summation order, not a different loss."
    )


def test_TC_089_gradients_match_monai_dice_ce():
    """Matching the value is not enough -- the gradient is what training uses."""
    from monai.losses import DiceCELoss

    logits, target = fixture(seed=11)

    a = logits.clone().requires_grad_(True)
    DiceCELoss(include_background=False, to_onehot_y=True, softmax=True)(a, target).backward()

    b = logits.clone().requires_grad_(True)
    DeterministicDiceCELoss(include_background=False, to_onehot_y=True, softmax=True)(
        b, target
    ).backward()

    assert torch.allclose(
        a.grad, b.grad, rtol=1e-4, atol=1e-6
    ), f"gradients differ by up to {(a.grad - b.grad).abs().max().item():.3e}"


def test_TC_089_the_comparison_can_fail():
    """Guards the guard: the tolerance must reject a genuinely different loss."""
    from monai.losses import DiceCELoss

    logits, target = fixture(seed=3)
    reference = DiceCELoss(include_background=False, to_onehot_y=True, softmax=True)(
        logits, target
    ).item()
    # lambda_ce doubled: algebraically a different loss, not a reordering.
    altered = DeterministicDiceCELoss(
        include_background=False, to_onehot_y=True, softmax=True, lambda_ce=2.0
    )(logits, target).item()
    assert altered != pytest.approx(
        reference, rel=RTOL, abs=ATOL
    ), "the tolerance cannot distinguish the reference loss from a different one"


# --- the property the replacement exists for -------------------------------------------


@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device")
def test_TC_089_no_determinism_fallback_on_cuda():
    """**The reason this module exists.** Under deterministic algorithms, the reference
    loss warns on `nll_loss2d` and the replacement must not warn at all."""
    import warnings

    from monai.losses import DiceCELoss

    logits, target = fixture(seed=5, device="cuda")
    torch.use_deterministic_algorithms(True, warn_only=True)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            DiceCELoss(include_background=False, to_onehot_y=True, softmax=True)(logits, target)
        reference_fallbacks = [
            str(w.message) for w in caught if "deterministic implementation" in str(w.message)
        ]

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            DeterministicDiceCELoss(include_background=False, to_onehot_y=True, softmax=True)(
                logits, target
            )
        replacement_fallbacks = [
            str(w.message) for w in caught if "deterministic implementation" in str(w.message)
        ]
    finally:
        torch.use_deterministic_algorithms(False)

    assert reference_fallbacks, (
        "MONAI's DiceCELoss did not warn on this device, so there is nothing for the "
        "replacement to fix and this test proves nothing"
    )
    assert (
        not replacement_fallbacks
    ), f"the replacement still falls back: {replacement_fallbacks[:2]}"
