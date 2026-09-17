"""Read native RETOUCH volumes into arrays plus metadata.

Traces to: SRS-001, SRS-003, SRS-004, SRS-005, SRS-054, SRS-055, SRS-056 (data ingestion)
Implements risk control: RC-021, RC-022, RC-023 (HAZ-012)

RETOUCH ships per-vendor directories of MetaImage (.mhd/.raw) volumes with a
matching reference segmentation. This module is the only place that knows about
that on-disk layout; everything downstream sees DICOM.

Voxel spacing is validated here and nowhere given a default. A correct segmentation
with wrong spacing produces a confidently wrong volume in mm³ that looks entirely right
in the mask and to a grader — see docs/05 §5.4. Spacing is therefore treated as data to
be checked, not metadata to be trusted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

# Physical plausibility bound for a retinal OCT voxel, in millimetres.
#
# Derived from anatomy rather than from any vendor's specification, so it holds without
# the dataset: a whole retina is roughly 0.3 mm thick, so a voxel edge of 0.5 mm cannot
# be a retinal OCT sample in any axis. Real axial spacings are a few micrometres and
# B-scan separations tens to low hundreds of micrometres, so this bound is loose by two
# orders of magnitude — it is a physical impossibility check, not a tolerance.
#
# The specific defect it catches: axial resolution is conventionally quoted in
# micrometres, so a spacing that should read 0.0039 mm arriving as 3.9 is a 1000x volume
# error, and 3.9 > 0.5 rejects it.
#
# Per-vendor empirical ranges remain owed (docs/07 open item 6) and need the data. They
# will tighten this, not replace it.
MAX_PLAUSIBLE_SPACING_MM = 0.5


@dataclass(frozen=True)
class OCTVolume:
    """One OCT volume with the metadata the pipeline must preserve end to end."""

    pixel_array: object  # np.ndarray, shape (n_bscans, height, width)
    label_array: object | None  # np.ndarray or None when no reference exists
    patient_id: str
    vendor: str
    spacing_mm: tuple[float, float, float]
    source_path: Path


def validate_spacing(spacing: tuple[float, ...] | None, *, source: str = "<unknown>") -> None:
    """Reject voxel spacing that cannot have come from a retinal OCT acquisition.

    Rejects rather than warns or clamps (SRS-056, RC-023): a warning on a metadata
    defect that is invisible downstream is the same as no control at all.

    No default is ever substituted for missing spacing (SRS-055, RC-022) — a volume
    without spacing cannot yield a measurement, and inventing one converts a loud failure
    into a silent wrong number.

    Raises ValueError naming the component and the permitted range. Returns None on
    acceptance.
    """
    if spacing is None:
        raise ValueError(
            f"{source}: voxel spacing is absent and no default exists. "
            f"A volume without spacing cannot produce a measurement."
        )
    if len(spacing) != 3:
        raise ValueError(f"{source}: spacing must have three components, got {spacing!r}")

    for axis, component in enumerate(spacing):
        if not isinstance(component, int | float) or isinstance(component, bool):
            raise ValueError(f"{source}: spacing component {axis} is not numeric: {component!r}")
        if not math.isfinite(component):
            raise ValueError(f"{source}: spacing component {axis} is not finite: {component!r}")
        if component <= 0:
            raise ValueError(
                f"{source}: spacing component {axis} must be positive, got {component}"
            )
        if component > MAX_PLAUSIBLE_SPACING_MM:
            raise ValueError(
                f"{source}: spacing component {axis} is {component} mm, above the physical "
                f"limit of {MAX_PLAUSIBLE_SPACING_MM} mm for retinal OCT. A value near this "
                f"magnitude usually means micrometres were read as millimetres, which is a "
                f"1000x volume error."
            )

    if len(set(spacing)) == 1:
        raise ValueError(
            f"{source}: spacing is isotropic {spacing!r}. OCT is always anisotropic — axial "
            f"sampling is far finer than B-scan separation — so three equal components "
            f"indicate collapsed or defaulted metadata rather than a real acquisition."
        )


def read_volume(path: Path, vendor: str) -> OCTVolume:
    """Read a single RETOUCH volume. Raises on unreadable or malformed input."""
    raise NotImplementedError


def iter_volumes(raw_root: Path, vendors: list[str]):
    """Yield every OCTVolume under raw_root for the given vendors."""
    raise NotImplementedError
