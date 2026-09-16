"""Write OCT volumes as conformant DICOM Ophthalmic Tomography Image objects.

Traces to: SRS-TBD (DICOM conversion)

Uses pydicom/highdicom only — do not hand-roll DICOM encoding. Where a tag or
UID requirement is uncertain, stop and flag it rather than inventing a value:
plausible-looking but incorrect DICOM is the most expensive failure mode here.
The behaviour implemented here must match docs/11_dicom_conformance_statement.md.
"""

from __future__ import annotations

from pathlib import Path

from ocuval.io.retouch_reader import OCTVolume


def generate_uid(uid_root: str) -> str:
    """Generate a UID under the project's registered root."""
    raise NotImplementedError


def write_volume(volume: OCTVolume, out_dir: Path, uid_root: str) -> list[Path]:
    """Write one OCTVolume as DICOM instances. Returns the paths written."""
    raise NotImplementedError
