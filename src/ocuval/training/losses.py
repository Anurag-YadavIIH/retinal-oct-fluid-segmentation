"""Training losses with a deterministic implementation on CUDA.

Traces to: SRS-084
Verifies: TC-089

**Why this module exists.** The Stage 1 smoke run set
`torch.use_deterministic_algorithms(True, warn_only=True)` and recorded **1308
fallbacks**, every one of them the same operation:

    nll_loss2d_forward_out_cuda_template does not have a deterministic implementation

That is the cross-entropy term inside MONAI's `DiceCELoss`, so it fired on essentially
every training step. GPU training was therefore never deterministic, while `run.json`
reported that deterministic algorithms were active. The flag cost whatever it costs and
delivered nothing on the path that mattered.

Only **one** operation lacked a deterministic implementation, which makes the problem
fixable rather than merely reportable: cross-entropy can be written as
`log_softmax` → `gather` → `mean`, all of which have deterministic CUDA kernels, instead
of dispatching to `nll_loss2d`. The Dice term is untouched -- it never appeared in the
fallback list.

**This is a substitution, not an approximation.** The formulation below is algebraically
the same function as `nn.CrossEntropyLoss` with mean reduction, no class weights and no
ignored index. It differs only in floating-point summation order, which is why TC-089
compares it back to back against MONAI's own loss within a stated tolerance rather than
asserting exact equality -- the same arrangement TC-120 uses for the metrics against
MONAI, and for the same reason: an independent implementation is worth having only if
something checks it against the reference.
"""

from __future__ import annotations

import torch
from torch.nn import functional as functional_nn


def deterministic_cross_entropy(logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """Mean cross-entropy over all voxels, without dispatching to `nll_loss2d`.

    `logits` is (B, C, H, W); `target` is (B, 1, H, W) or (B, H, W) of class indices.

    Equivalent to `nn.CrossEntropyLoss(reduction="mean")` for the unweighted case with
    no ignored index. Each step is a deterministic CUDA kernel:

    - `log_softmax` reduces over the channel dimension, which is contiguous and small,
      and uses a deterministic tree reduction;
    - `gather` is an indexed read with no accumulation, so there is nothing to race;
    - `mean` over the whole tensor is a deterministic reduction.

    `nll_loss2d_forward` is avoided entirely, which is the point -- it is the single
    operation that fell back in the Stage 1 run.
    """
    if target.dim() == logits.dim():
        if target.shape[1] != 1:
            raise ValueError(
                f"target has {target.shape[1]} channels; expected a single channel of "
                f"class indices, or no channel dimension at all"
            )
        index = target.long()
    elif target.dim() == logits.dim() - 1:
        index = target.long().unsqueeze(1)
    else:
        raise ValueError(
            f"target shape {tuple(target.shape)} is not compatible with "
            f"logits shape {tuple(logits.shape)}"
        )

    log_probs = functional_nn.log_softmax(logits, dim=1)
    picked = torch.gather(log_probs, 1, index)
    return -picked.mean()


class DeterministicDiceCELoss(torch.nn.Module):
    """MONAI's Dice term plus a deterministic cross-entropy term (SRS-084).

    Deliberately reuses `monai.losses.DiceLoss` rather than reimplementing it. The Dice
    term never appeared in the fallback list, so replacing it would be changing code
    that is not broken -- and every line of loss this project writes itself is a line
    that has to be verified against something.

    `lambda_dice` and `lambda_ce` match MONAI's defaults of 1.0 each, so the total is
    the sum of the two terms exactly as `DiceCELoss` computes it.
    """

    def __init__(
        self,
        include_background: bool = False,
        to_onehot_y: bool = True,
        softmax: bool = True,
        lambda_dice: float = 1.0,
        lambda_ce: float = 1.0,
    ):
        super().__init__()
        from monai.losses import DiceLoss

        self.dice = DiceLoss(
            include_background=include_background, to_onehot_y=to_onehot_y, softmax=softmax
        )
        self.lambda_dice = float(lambda_dice)
        self.lambda_ce = float(lambda_ce)

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        dice_term = self.dice(logits, target)
        ce_term = deterministic_cross_entropy(logits, target)
        return self.lambda_dice * dice_term + self.lambda_ce * ce_term
