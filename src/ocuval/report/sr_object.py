"""Build DICOM Structured Report objects carrying quantitative measurements.

Traces to: SRS-TBD (structured reporting)

Carries per-class fluid volume and the scan-level confidence score from
MC-dropout, so that the uncertainty travels with the result rather than living
only in a log file.
"""

from __future__ import annotations

from pathlib import Path


def build_measurement_report(
    seg_instance: Path,
    volumes_mm3: dict,
    confidence: float,
    uid_root: str,
):
    """Construct a highdicom measurement report referencing the SEG object."""
    raise NotImplementedError


def write_report(sr, out_path: Path) -> Path:
    """Persist a Structured Report object to disk."""
    raise NotImplementedError
