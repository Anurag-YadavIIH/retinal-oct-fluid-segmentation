"""TC-055, TC-056: MC-dropout uncertainty.

Traces to: SRS-029, SRS-030
Implements risk control: RC-009 (routing low-confidence cases to human review)

The mechanism is easy to get subtly wrong in ways that produce a plausible-looking
uncertainty map: averaging logits instead of probabilities, leaving the whole model in
training mode so normalisation statistics move too, or running a single pass and reporting a
standard deviation of zero as confidence. Each is asserted against here rather than assumed
away -- `docs/07` §3 rule 8, since all three produce output of the right shape.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from ocuval.models.uncertainty import enable_dropout, mc_dropout_predict, scan_confidence


def tiny(dropout: float = 0.5) -> torch.nn.Module:
    """Conv + InstanceNorm + Dropout, mirroring the real network's layer kinds.

    `InstanceNorm2d` is present deliberately: it is the layer whose behaviour would change
    if `model.train()` were used instead of enabling dropout alone.
    """
    torch.manual_seed(0)
    return torch.nn.Sequential(
        torch.nn.Conv2d(1, 4, 3, padding=1),
        torch.nn.InstanceNorm2d(4),
        torch.nn.Dropout2d(dropout),
        torch.nn.Conv2d(4, 4, 1),
    )


def batch(n: int = 2, size: int = 8) -> torch.Tensor:
    return torch.randn(n, 1, size, size, generator=torch.Generator().manual_seed(1))


# --- TC-055: the passes differ, and the mean is a probability ---------------------------


def test_TC_055_repeated_passes_disagree_so_the_map_is_not_identically_zero():
    """If dropout were not active the passes would be identical and std exactly 0.

    That is the failure this test exists for: an uncertainty map of zeros reads as perfect
    confidence rather than as a mechanism that never ran.
    """
    mean, std = mc_dropout_predict(tiny(), batch(), passes=8)
    assert std.shape == mean.shape
    assert float(std.max()) > 0.0, "every pass agreed exactly; dropout was not active"


def test_TC_055_the_mean_is_a_probability_distribution_over_classes():
    """Softmax is applied per pass BEFORE averaging.

    Averaging logits and normalising afterwards is a different quantity and is not a
    probability; the giveaway is that the class axis would not sum to 1.
    """
    mean, _ = mc_dropout_predict(tiny(), batch(), passes=6)
    sums = mean.sum(axis=1)
    assert np.allclose(sums, 1.0, atol=1e-5), f"class axis sums to {sums.min()}..{sums.max()}"
    assert float(mean.min()) >= 0.0


def test_TC_055_a_single_pass_is_refused():
    """A standard deviation over one sample is identically zero by definition."""
    with pytest.raises(ValueError, match="one pass"):
        mc_dropout_predict(tiny(), batch(), passes=1)


def test_TC_055_a_model_without_dropout_is_refused():
    """Silence here would mean reporting a zero uncertainty map as high confidence."""
    plain = torch.nn.Sequential(torch.nn.Conv2d(1, 4, 1))
    with pytest.raises(ValueError, match="no dropout layers"):
        mc_dropout_predict(plain, batch(), passes=4)


def test_TC_055_only_dropout_is_switched_not_the_normalisation():
    """SRS-029's mechanism, and the reason `model.train()` is not used.

    `InstanceNorm2d` defaults to `track_running_stats=False`, so training mode changes how
    it normalises -- which would change the prediction itself, not merely its spread, and
    the mean over passes would stop being an estimate of the model's output.
    """
    model = tiny()
    model.eval()
    switched = enable_dropout(model)
    assert switched == 1, f"expected one dropout layer to be switched, got {switched}"
    kinds = {type(m).__name__: m.training for m in model.modules()}
    assert kinds["Dropout2d"] is True, "dropout was not enabled"
    assert kinds["InstanceNorm2d"] is False, "normalisation was switched too; use eval + dropout"
    assert kinds["Conv2d"] is False


def test_TC_055_enable_dropout_reports_zero_when_there_is_nothing_to_enable():
    """The count is what lets a caller assert the mechanism did something."""
    assert enable_dropout(torch.nn.Sequential(torch.nn.Conv2d(1, 2, 1))) == 0


# --- TC-056: the scan-level confidence score -------------------------------------------


def test_TC_056_confidence_is_one_for_a_certain_scan_and_zero_for_the_worst():
    """Scaled by 2 because a per-voxel std over softmax outputs tops out at 0.5.

    Without that, a maximally uncertain scan would score 0.5 and read as middling rather
    than as the worst possible, which would make RC-009's routing threshold meaningless.
    """
    assert scan_confidence(np.zeros((4, 4))) == pytest.approx(1.0)
    assert scan_confidence(np.full((4, 4), 0.5)) == pytest.approx(0.0)


def test_TC_056_confidence_decreases_as_uncertainty_rises():
    low = scan_confidence(np.full((8, 8), 0.05))
    high = scan_confidence(np.full((8, 8), 0.30))
    assert low > high, "confidence must fall as the uncertainty map rises"


def test_TC_056_the_mean_not_the_max_drives_the_score():
    """RC-009 needs the score to *rank* scans, which a max cannot do.

    The maximum per-voxel standard deviation is near its ceiling somewhere along almost any
    fluid boundary, so a max-based score would be nearly constant across scans. These two
    maps share a maximum of 0.5 and differ everywhere else; their scores must differ.
    """
    a = np.zeros((10, 10))
    a[0, 0] = 0.5
    b = np.full((10, 10), 0.25)
    b[0, 0] = 0.5
    assert scan_confidence(a) != pytest.approx(scan_confidence(b)), (
        "two maps with the same maximum scored identically, so the score is driven by the "
        "max and cannot rank scans"
    )
    assert scan_confidence(a) > scan_confidence(b)


def test_TC_056_an_empty_map_is_refused():
    with pytest.raises(ValueError, match="empty uncertainty map"):
        scan_confidence(np.array([]))


def test_TC_056_nan_voxels_do_not_destroy_the_score():
    """One undefined voxel must not make a whole scan's confidence undefined."""
    values = np.full((4, 4), 0.1)
    values[0, 0] = np.nan
    assert not np.isnan(scan_confidence(values))
