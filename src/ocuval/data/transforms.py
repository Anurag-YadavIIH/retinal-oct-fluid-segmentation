"""MONAI transform chains for training, validation, and inference.

Traces to: SRS-070, SRS-072, SRS-073, SRS-074 (preprocessing)
Implements risk control: RC-031 (inheritance), and supports RC-021..RC-023 (spacing)
Verifies: TC-044, TC-046, TC-047, TC-048

Two design decisions carry the weight here, and both are about not letting a vendor
identify itself to the network through something other than its images.

**Intensity is normalised per volume, by a percentile window computed at ingestion.**
Dividing by the dtype maximum normalises the container rather than the signal. Measured
on RETOUCH, that leaves topcon at roughly twice the median of the other two, because
topcon carries a raised black level -- p1 = 35/255, a detector offset rather than
tissue. A constant brightness offset perfectly correlated with vendor is the most
learnable shortcut in the dataset. See `io.retouch_reader.intensity_window`.

**Only the axial axis is resampled, to a coarsest-common target (SRS-073).** Lateral
spacing is ~0.0117 mm in all three vendors, so it needs nothing. B-scan separation is
not read here at all: training is 2D and frames are independent. The axial target is a
declared constant in `configs/train_seg.yaml` (SRS-072) rather than a statistic of the
fold, because a target derived from whichever volumes happened to be in a fold would
make preprocessing incomparable between folds. It is the coarsest choice so that no
volume is ever upsampled -- upsampling fabricates detail, and fabricated detail would
substitute a smoothness signature for the brightness signature the windowing removes.

What this chain deliberately does NOT do: it does not compute any statistic from the
data it is given. Every number it applies arrives either from the configuration or from
the sample's own recorded metadata.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from monai.transforms import (
    Compose,
    EnsureChannelFirstd,
    MapTransform,
    RandAdjustContrastd,
    RandFlipd,
    RandRotated,
    RandScaleIntensityd,
    RandShiftIntensityd,
    RandZoomd,
    SpatialPadd,
    ToTensord,
)
from torch.nn import functional as functional_nn

# Index of the axial component in every spacing tuple in this project.
# (axial, lateral, separation) -- see io.retouch_reader.SPACING_COMPONENTS.
AXIAL = 0
LATERAL = 1

IMAGE = "image"
LABEL = "label"
SPACING = "spacing_mm"
WINDOW = "intensity_window"


class ApplyStoredIntensityWindowd(MapTransform):
    """Apply the volume's recorded intensity window. Never computes one (SRS-070).

    The window arrives on the sample, having been computed once at ingestion from the
    raw volume. This transform is a deterministic affine map plus a clip.

    Recomputing here would be wrong in a way that is easy to miss. For 2D training the
    array handed to a transform is a single B-scan, so a percentile taken here would be
    a per-frame statistic: adjacent B-scans would get different windows, injecting an
    intensity gradient along the volume that the acquisition does not contain, and
    breaking any later 2.5D adjacent-slice input. SRS-071 makes the inheritance a
    requirement; this transform is where it would otherwise be violated.

    Raises if the window is absent rather than falling back to computing one. A silent
    fallback would produce a plausible image and an unreproducible normalisation.
    """

    def __init__(self, keys, window_key: str = WINDOW, allow_missing_keys: bool = False):
        super().__init__(keys, allow_missing_keys)
        self.window_key = window_key

    def __call__(self, data: dict[str, Any]) -> dict[str, Any]:
        d = dict(data)
        if self.window_key not in d:
            raise KeyError(
                f"sample carries no {self.window_key!r}. The window is computed at "
                f"ingestion (SRS-070) and inherited by every frame (SRS-071); computing "
                f"one here would make normalisation depend on which frame was handed in."
            )
        low, high = (float(v) for v in d[self.window_key])
        if not high > low:
            raise ValueError(f"degenerate intensity window ({low}, {high}) on this sample")
        for key in self.key_iterator(d):
            array = d[key]
            as_tensor = isinstance(array, torch.Tensor)
            values = array.float() if as_tensor else np.asarray(array, dtype=np.float32)
            scaled = (values - low) / (high - low)
            d[key] = torch.clamp(scaled, 0.0, 1.0) if as_tensor else np.clip(scaled, 0.0, 1.0)
        return d


class ResampleAxiald(MapTransform):
    """Resample the axial axis only, to a declared target spacing (SRS-072, SRS-073).

    The zoom factor is per-sample, because it depends on that acquisition's native axial
    spacing, but the *target* is a constant from the configuration. That distinction is
    the requirement: a target derived from the data would vary with fold membership.

    The lateral axis is left untouched -- all three vendors sit at ~0.0117 mm -- and
    B-scan separation is never read. `spacing_mm` is updated in place for the axial
    component so that anything downstream sees the geometry it is actually holding, and
    the native spacing is preserved under `native_spacing_mm` so SRS-074 can invert back
    to it for metric computation.

    Interpolation differs by key and must: bilinear on the image, nearest on the label.
    Interpolating a label array linearly produces fractional class indices, which either
    crash or, worse, round into a different class along every boundary -- and boundaries
    are exactly what HD95 measures.
    """

    def __init__(
        self,
        keys,
        target_axial_mm: float,
        label_keys: tuple[str, ...] = (LABEL,),
        spacing_key: str = SPACING,
        allow_missing_keys: bool = False,
    ):
        super().__init__(keys, allow_missing_keys)
        if not target_axial_mm > 0:
            raise ValueError(f"target axial spacing must be positive, got {target_axial_mm}")
        self.target_axial_mm = float(target_axial_mm)
        self.label_keys = set(label_keys)
        self.spacing_key = spacing_key

    def __call__(self, data: dict[str, Any]) -> dict[str, Any]:
        d = dict(data)
        spacing = tuple(float(v) for v in d[self.spacing_key])
        native_axial = spacing[AXIAL]
        d.setdefault("native_spacing_mm", spacing)

        factor = native_axial / self.target_axial_mm
        if np.isclose(factor, 1.0):
            return d

        for key in self.key_iterator(d):
            tensor = d[key]
            was_numpy = not isinstance(tensor, torch.Tensor)
            if was_numpy:
                tensor = torch.as_tensor(np.asarray(tensor))
            # (C, H, W) -> (1, C, H, W) for interpolate, resizing H only.
            working = tensor.unsqueeze(0)
            height = working.shape[-2]
            new_height = max(1, int(round(height * factor)))
            if key in self.label_keys:
                resized = functional_nn.interpolate(
                    working.float(), size=(new_height, working.shape[-1]), mode="nearest"
                ).to(tensor.dtype)
            else:
                resized = functional_nn.interpolate(
                    working.float(),
                    size=(new_height, working.shape[-1]),
                    mode="bilinear",
                    align_corners=False,
                )
            resized = resized.squeeze(0)
            d[key] = resized.numpy() if was_numpy else resized

        d[self.spacing_key] = (self.target_axial_mm, spacing[LATERAL], spacing[2])
        return d


def _preprocessing(cfg: dict) -> tuple[float, tuple[int, int]]:
    """Pull the declared constants out of the resolved config (SRS-072).

    Read rather than defaulted: a default here would mean a run whose configuration was
    incomplete still produced numbers, and the run output would record a target the run
    did not use.
    """
    data = cfg.get("data", cfg)
    try:
        target = float(data["preprocessing"]["axial_spacing_mm"])
        roi = tuple(int(v) for v in data["roi_size"])
    except KeyError as error:
        raise KeyError(
            f"configs/train_seg.yaml is missing {error}; the axial target and roi_size "
            f"are declared constants (SRS-072) and have no default."
        ) from error
    if len(roi) != 2:
        raise ValueError(f"roi_size must be (axial, lateral), got {roi!r}")
    return target, roi


def _base_chain(cfg: dict, keys: tuple[str, ...]) -> list:
    """The deterministic part, shared by training and evaluation.

    Order matters and is not arbitrary: the window is applied to the raw values it was
    computed from, before any interpolation mixes neighbouring intensities; resampling
    then happens in a fixed intensity scale; padding last, so the pad value 0 means
    "background" on the same scale as the data.
    """
    target_axial, roi = _preprocessing(cfg)
    label_keys = tuple(k for k in keys if k == LABEL)
    return [
        EnsureChannelFirstd(keys=keys, channel_dim="no_channel"),
        ApplyStoredIntensityWindowd(keys=(IMAGE,)),
        ResampleAxiald(keys=keys, target_axial_mm=target_axial, label_keys=label_keys),
        # Pad only. roi_size is chosen so the tallest resampled volume still fits, so
        # this never crops -- cropping could remove fluid at the retinal margin, and a
        # segmentation metric cannot see a lesion that preprocessing discarded.
        SpatialPadd(keys=keys, spatial_size=roi, mode="constant", constant_values=0),
        ToTensord(keys=keys),
    ]


def train_transforms(cfg: dict, seed: int | None = None, keys: tuple[str, ...] = (IMAGE, LABEL)):
    """Augmenting chain used for the training split only.

    The lateral flip is the one worth justifying. Laterality is omitted from every object
    this project writes (RC-029), so a horizontal flip does not contradict a recorded
    left/right eye -- there is none to contradict. What it does is approximately
    randomise eye laterality, which is useful augmentation: fluid location correlates
    with laterality through the position of the fovea and disc, and a model that learns
    that correlation from an imbalanced training set carries it into a vendor where the
    balance differs. The flip is lateral only; a vertical flip would invert the retinal
    layer order, which is anatomy rather than nuisance variation.

    Intensity augmentation runs after the window has been applied, so it perturbs a
    normalised scale. That is deliberate: the augmentation should simulate residual
    acquisition variation, not undo the normalisation whose whole purpose is to remove
    the systematic part.
    """
    chain = _base_chain(cfg, keys)
    label_keys = tuple(k for k in keys if k == LABEL)
    mode = tuple("nearest" if k in label_keys else "bilinear" for k in keys)
    chain += [
        RandFlipd(keys=keys, spatial_axis=LATERAL, prob=0.5),
        RandZoomd(keys=keys, prob=0.25, min_zoom=0.9, max_zoom=1.1, mode=mode, keep_size=True),
        RandRotated(
            keys=keys,
            prob=0.2,
            range_x=0.087,  # +-5 degrees; OCT B-scans are near-axially aligned already
            mode=mode,
            padding_mode="zeros",
        ),
        RandScaleIntensityd(keys=(IMAGE,), factors=0.1, prob=0.3),
        RandShiftIntensityd(keys=(IMAGE,), offsets=0.05, prob=0.3),
        RandAdjustContrastd(keys=(IMAGE,), prob=0.2, gamma=(0.8, 1.25)),
    ]
    composed = Compose(chain)
    if seed is not None:
        composed.set_random_state(seed=seed)
    return composed


def eval_transforms(cfg: dict, keys: tuple[str, ...] = (IMAGE, LABEL)):
    """Deterministic chain used for validation, test, and inference.

    No random transform appears here at all, rather than appearing with prob=0. A
    transform present with zero probability still consumes random state, which makes a
    seeded evaluation depend on how many samples preceded it.
    """
    return Compose(_base_chain(cfg, keys))


def invert_axial_resample(
    prediction: np.ndarray | torch.Tensor,
    native_spacing_mm: tuple[float, float, float],
    native_shape: tuple[int, int],
) -> np.ndarray:
    """Return a prediction to the acquisition's native grid (SRS-074).

    Every metric and every volume in mm3 is computed in native geometry. Measuring on
    the resampled grid would report a number derived from a spacing the acquisition
    never had, and SRS-057 requires the spacing used for a volume to be bit-identical to
    the spacing recorded at ingestion -- which after resampling it is not.

    Nearest-neighbour throughout: this inverts a label map, and any interpolation would
    invent boundary voxels in exactly the place HD95 measures.
    """
    array = (
        prediction
        if isinstance(prediction, torch.Tensor)
        else torch.as_tensor(np.asarray(prediction))
    )
    working = array.float()
    while working.ndim < 4:
        working = working.unsqueeze(0)
    restored = functional_nn.interpolate(working, size=tuple(native_shape), mode="nearest")
    restored = restored.reshape(*array.shape[:-2], *native_shape)
    return restored.to(array.dtype).numpy()
