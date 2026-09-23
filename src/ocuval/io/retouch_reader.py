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
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ocuval.io.metaimage import MetaImageHeader, parse_header, read_volume_array

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


#: The archive nests one level below the vendor directory and uses the organisers' own
#: names, which are not the lowercase vendor keys in configs/data.yaml. The inner
#: directory is discovered rather than hard-coded, so a re-release that renames it does
#: not silently find nothing.
VENDOR_DIRECTORIES: dict[str, str] = {
    "cirrus": "TrainingCirrus",
    "spectralis": "TrainingSpectralis",
    "topcon": "TrainingTopcon",
}

#: Label values configs/data.yaml fixes. Anything else in a reference volume is a
#: defect in the archive or in this reader, never a new class to accommodate.
EXPECTED_LABELS = frozenset({0, 1, 2, 3})


def spacing_from_header(header: MetaImageHeader) -> tuple[float, float, float]:
    """Reorder MetaImage (x, y, z) spacing into this project's (axial, lateral, sep).

    **This reordering is the single most dangerous line in the ingestion path**, so it
    is a named function with its own test rather than an inline index permutation.

    MetaImage gives `ElementSpacing` as (x, y, z), which for RETOUCH means
    (lateral within a B-scan, axial, separation between B-scans). `OCTVolume.spacing_mm`
    and `dicom_writer._pixel_measures` both expect (axial, lateral, separation), because
    within a frame the rows run axially and the columns laterally.

    Swapping the first two produces a volume in mm³ that is wrong by the ratio of the
    two spacings — for Cirrus, a factor of six — from a segmentation that is perfectly
    correct. Nothing in the mask, the image or the review screen would show it. That is
    HAZ-012 exactly, and `docs/05` §5.4 explains why no downstream control catches it.
    """
    lateral, axial, separation = header.element_spacing
    return (axial, lateral, separation)


def _check_reference_matches(
    oct_header: MetaImageHeader, ref_header: MetaImageHeader, source: str
) -> None:
    """A reference standard that does not describe the same grid as its image is
    unusable, and the mismatch is invisible once both are arrays of plausible size."""
    if oct_header.dim_size != ref_header.dim_size:
        raise ValueError(
            f"{source}: oct and reference disagree on DimSize "
            f"({oct_header.dim_size} vs {ref_header.dim_size})"
        )
    if oct_header.element_spacing != ref_header.element_spacing:
        raise ValueError(
            f"{source}: oct and reference disagree on ElementSpacing "
            f"({oct_header.element_spacing} vs {ref_header.element_spacing})"
        )


def read_volume(path: Path, vendor: str) -> OCTVolume:
    """Read a single RETOUCH volume. Raises on unreadable or malformed input.

    `path` is a subject directory containing oct.mhd/oct.raw and, where a reference
    exists, reference.mhd/reference.raw.

    **The element type is taken from the header and carried, not cast.** Spectralis
    volumes are 16-bit and Cirrus and Topcon are 8-bit (`docs/06` §3.1.1); widening the
    8-bit ones on the way in would make every downstream object claim a precision its
    source never had, and narrowing the 16-bit one would lose data outright.

    No value here is defaulted. A missing header, a missing spacing, an unreadable
    element type or a truncated payload all raise, naming the path (SRS-004).
    """
    path = Path(path)
    source = str(path)
    if not path.is_dir():
        raise ValueError(f"{source}: not a directory")

    oct_header_path = path / "oct.mhd"
    oct_header = parse_header(oct_header_path)
    pixels = read_volume_array(oct_header_path)

    spacing = spacing_from_header(oct_header)
    validate_spacing(spacing, source=source)

    labels = None
    ref_header_path = path / "reference.mhd"
    if ref_header_path.is_file():
        ref_header = parse_header(ref_header_path)
        _check_reference_matches(oct_header, ref_header, source)
        labels = read_volume_array(ref_header_path)
        present = set(np.unique(labels).tolist())
        if not present <= EXPECTED_LABELS:
            raise ValueError(
                f"{source}: reference contains label values {sorted(present - EXPECTED_LABELS)} "
                f"outside the frozen set {sorted(EXPECTED_LABELS)} in configs/data.yaml. "
                f"A new label value is a changed contract, not a volume to be processed."
            )

    return OCTVolume(
        pixel_array=pixels,
        label_array=labels,
        patient_id=path.name,
        vendor=vendor,
        spacing_mm=spacing,
        source_path=path,
    )


def subject_directories(raw_root: Path, vendor: str) -> list[Path]:
    """Every subject directory for one vendor, in sorted order.

    Sorted so that iteration order is stable across filesystems, for the same reason
    `data.splits` sorts before shuffling: an order that varies between machines makes a
    seeded run reproducible-looking and not reproducible.
    """
    raw_root = Path(raw_root)
    if vendor not in VENDOR_DIRECTORIES:
        raise ValueError(
            f"unknown vendor {vendor!r}; configs/data.yaml fixes {sorted(VENDOR_DIRECTORIES)}"
        )
    outer = raw_root / VENDOR_DIRECTORIES[vendor]
    if not outer.is_dir():
        raise ValueError(f"{outer}: vendor directory not found under {raw_root}")

    inner = sorted(d for d in outer.iterdir() if d.is_dir())
    if len(inner) != 1:
        raise ValueError(
            f"{outer}: expected exactly one release directory inside, found {len(inner)}: "
            f"{[d.name for d in inner]}"
        )
    return sorted((d for d in inner[0].iterdir() if d.is_dir()), key=lambda d: d.name)


def iter_volumes(raw_root: Path, vendors: list[str]) -> Iterator[OCTVolume]:
    """Yield every OCTVolume under raw_root for the given vendors.

    A generator rather than a list: the 70 volumes total several gigabytes and nothing
    in this pipeline needs them resident at once.
    """
    for vendor in vendors:
        for subject in subject_directories(raw_root, vendor):
            yield read_volume(subject, vendor)
