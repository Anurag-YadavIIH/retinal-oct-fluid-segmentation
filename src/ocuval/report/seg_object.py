"""Build DICOM Segmentation (SEG) objects from model output using highdicom.

Traces to: SRS-TBD (segmentation output)

Segment descriptions must carry coded concepts, not free text, so the object is
interpretable by any conformant viewer. Source image references must point at the
instances the segmentation was actually derived from.
"""

from __future__ import annotations

from pathlib import Path


def build_segmentation(source_instances: list[Path], mask, label_names: list[str], uid_root: str):
    """Construct a highdicom Segmentation from a multi-class mask."""
    raise NotImplementedError


def write_segmentation(seg, out_path: Path) -> Path:
    """Persist a Segmentation object to disk."""
    raise NotImplementedError
