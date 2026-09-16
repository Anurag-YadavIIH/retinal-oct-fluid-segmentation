"""Read native RETOUCH volumes into arrays plus metadata.

Traces to: SRS-TBD (data ingestion)

RETOUCH ships per-vendor directories of MetaImage (.mhd/.raw) volumes with a
matching reference segmentation. This module is the only place that knows about
that on-disk layout; everything downstream sees DICOM.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OCTVolume:
    """One OCT volume with the metadata the pipeline must preserve end to end."""

    pixel_array: object  # np.ndarray, shape (n_bscans, height, width)
    label_array: object | None  # np.ndarray or None when no reference exists
    patient_id: str
    vendor: str
    spacing_mm: tuple[float, float, float]
    source_path: Path


def read_volume(path: Path, vendor: str) -> OCTVolume:
    """Read a single RETOUCH volume. Raises on unreadable or malformed input."""
    raise NotImplementedError


def iter_volumes(raw_root: Path, vendors: list[str]):
    """Yield every OCTVolume under raw_root for the given vendors."""
    raise NotImplementedError
