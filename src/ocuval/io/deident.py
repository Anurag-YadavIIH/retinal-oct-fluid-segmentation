"""De-identification under DICOM PS3.15 Annex E Basic Application Confidentiality Profile.

Traces to: SRS-TBD (de-identification)
Implements risk control: RC-TBD

No real PHI ever enters this project — the data is public challenge data. The
control is implemented and tested anyway, because demonstrating it is the point.

Patient pseudonyms are derived with a salted hash; the salt is read from the
environment variable named in configs/data.yaml and is never committed.
"""

from __future__ import annotations

from pathlib import Path


def pseudonymise(patient_id: str, salt: str) -> str:
    """Return a stable pseudonym for a patient identifier."""
    raise NotImplementedError


def deidentify_instance(src: Path, dst: Path, salt: str) -> None:
    """Apply the confidentiality profile to one DICOM instance."""
    raise NotImplementedError


def verify_deidentified(path: Path) -> list[str]:
    """Return the names of any tags that should have been removed but were not.

    An empty list means the instance passes. Used by TC-TBD.
    """
    raise NotImplementedError
