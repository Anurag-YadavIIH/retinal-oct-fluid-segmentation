"""DICOMweb client for the local Orthanc PACS (STOW-RS, WADO-RS, QIDO-RS).

Traces to: SRS-TBD (PACS communication)
"""

from __future__ import annotations

from pathlib import Path


class DicomWebClient:
    """Minimal DICOMweb client. Base URL example: http://localhost:8042/dicom-web"""

    def __init__(self, base_url: str, timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def store(self, instances: list[Path]) -> dict:
        """STOW-RS: push instances to the PACS."""
        raise NotImplementedError

    def retrieve_instance(self, study_uid: str, series_uid: str, sop_uid: str) -> bytes:
        """WADO-RS: retrieve one instance."""
        raise NotImplementedError

    def search_series(self, **query: str) -> list[dict]:
        """QIDO-RS: search for series."""
        raise NotImplementedError
