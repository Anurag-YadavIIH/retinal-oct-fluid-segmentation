"""DICOMweb client for the local Orthanc PACS (STOW-RS, WADO-RS, QIDO-RS).

Traces to: SRS-043, SRS-044, SRS-045, SRS-060 (PACS communication)
Implements risk control: RC-017, RC-018, RC-027 (HAZ-014)

**The client reads no ambient environment configuration** (SRS-060, RC-027). Sessions are
built with `trust_env=False`, so `.netrc`, `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` and
`REQUESTS_CA_BUNDLE` are all ignored and behaviour depends only on the run configuration.
That closes the `requests` advisory in `docs/04` §2.2 without moving the pin, and it
serves NFR-002: a client whose behaviour varies with machine state is not reproducible.

The over-breadth is deliberate and is a known limitation, recorded in `docs/04` §2.6 —
it would break this client behind the corporate proxy and internal CA that the reading
centre in `docs/01` §4 would actually sit behind. Correct here, wrong there, stated
rather than fixed.

**Nothing here acts on the PACS beyond storing and retrieving this project's own
objects** (SRS-045, RC-017). There is no delete, no modify, no reconcile, and nothing
that marks an object verified or signed off. A pre-read produces candidates; a candidate
is not something software finalises.

**multipart/related is assembled and parsed here rather than by a library.** `requests`
has no native support for it, and the DICOMweb wire format is where a silent
half-transmission is most likely. Keeping it explicit makes it testable without a
server, which is why the format functions below are pure.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import requests

DICOM_MEDIA_TYPE = "application/dicom"
CRLF = b"\r\n"


class DicomWebError(RuntimeError):
    """A DICOMweb request failed, or returned something unusable."""


@dataclass(frozen=True)
class StoreResult:
    """What the PACS reported after a STOW-RS request."""

    status_code: int
    referenced_sop_instance_uids: list[str]
    failed_sop_instance_uids: list[str]

    @property
    def ok(self) -> bool:
        return not self.failed_sop_instance_uids


def build_multipart(parts: list[bytes], boundary: str, media_type: str = DICOM_MEDIA_TYPE) -> bytes:
    """Assemble a multipart/related body from raw part payloads.

    RFC 2387 with the DICOMweb constraints: every part carries its own Content-Type, the
    boundary is prefixed with `--`, and the body ends with a closing boundary followed by
    `--`. Lines are CRLF-delimited, which is not optional — a receiver that parses
    strictly will reject bare LF and one that parses loosely may accept a truncated body.
    """
    if not parts:
        raise ValueError("at least one part is required; an empty STOW-RS body stores nothing")
    if not boundary or any(c in boundary for c in '"\\ '):
        raise ValueError(f"unusable multipart boundary: {boundary!r}")

    chunks: list[bytes] = []
    for payload in parts:
        chunks += [
            b"--" + boundary.encode("ascii"),
            CRLF,
            f"Content-Type: {media_type}".encode("ascii"),
            CRLF,
            f"Content-Length: {len(payload)}".encode("ascii"),
            CRLF,
            CRLF,
            payload,
            CRLF,
        ]
    chunks += [b"--" + boundary.encode("ascii") + b"--", CRLF]
    return b"".join(chunks)


def parse_multipart(body: bytes, boundary: str) -> list[bytes]:
    """Split a multipart/related body back into its part payloads.

    Returns the payloads only, with headers stripped. A body whose closing boundary is
    absent raises rather than returning what was received so far: a truncated response
    that yields usable-looking parts is how a half-retrieved study passes for a whole
    one (SRS-044).
    """
    if not boundary:
        raise ValueError("a boundary is required to parse a multipart body")
    delimiter = b"--" + boundary.encode("ascii")
    closing = delimiter + b"--"

    if closing not in body:
        raise DicomWebError(
            "multipart body has no closing boundary; the response was truncated. "
            "Refusing to return partial parts, which would be indistinguishable from a "
            "complete retrieval."
        )

    body = body.split(closing)[0]
    payloads: list[bytes] = []
    for segment in body.split(delimiter):
        if not segment.strip():
            continue
        # Headers and payload are separated by a blank line.
        separator = segment.find(CRLF + CRLF)
        if separator == -1:
            continue
        payload = segment[separator + 4 :]
        if payload.endswith(CRLF):
            payload = payload[:-2]
        if payload:
            payloads.append(payload)
    return payloads


def boundary_from_content_type(content_type: str) -> str:
    """Extract the boundary from a Content-Type header.

    Raises when absent: a multipart response without a declared boundary cannot be
    parsed, and guessing one would be a way to appear to succeed.
    """
    match = re.search(r'boundary=(?:"([^"]+)"|([^;\s]+))', content_type or "")
    if not match:
        raise DicomWebError(f"no boundary in Content-Type: {content_type!r}")
    return match.group(1) or match.group(2)


class DicomWebClient:
    """Minimal DICOMweb client. Base URL example: http://localhost:8042/dicom-web"""

    def __init__(self, base_url: str, timeout_s: float = 30.0) -> None:
        if not base_url:
            raise ValueError("a base URL is required; no default endpoint exists")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._session = requests.Session()
        # SRS-060, RC-027. See the module docstring for what this disables and why.
        self._session.trust_env = False

    # -- URL construction ----------------------------------------------------------

    def studies_url(self) -> str:
        return f"{self.base_url}/studies"

    def instance_url(self, study_uid: str, series_uid: str, sop_uid: str) -> str:
        for name, value in (("study", study_uid), ("series", series_uid), ("instance", sop_uid)):
            if not value:
                raise ValueError(f"{name} UID is required to address an instance")
        return f"{self.base_url}/studies/{study_uid}/series/{series_uid}/instances/{sop_uid}"

    def series_url(self) -> str:
        return f"{self.base_url}/series"

    # -- requests ------------------------------------------------------------------

    def store(self, instances: list[Path]) -> StoreResult:
        """STOW-RS: push instances to the PACS.

        Never executed against a live Orthanc as of 2026-09-19 — see TC-080's status in
        `docs/07`.
        """
        if not instances:
            raise ValueError("no instances to store")
        payloads = [Path(p).read_bytes() for p in instances]
        boundary = uuid.uuid4().hex
        body = build_multipart(payloads, boundary)

        response = self._session.post(
            self.studies_url(),
            data=body,
            headers={
                "Content-Type": (
                    f'multipart/related; type="{DICOM_MEDIA_TYPE}"; boundary={boundary}'
                ),
                "Accept": "application/dicom+json",
            },
            timeout=self.timeout_s,
        )
        if response.status_code >= 400:
            raise DicomWebError(
                f"STOW-RS failed: {response.status_code} {response.reason} "
                f"from {self.studies_url()}: {response.text[:400]}"
            )
        return parse_store_response(response.status_code, response.json())

    def retrieve_instance(self, study_uid: str, series_uid: str, sop_uid: str) -> bytes:
        """WADO-RS: retrieve one instance.

        Never executed against a live Orthanc as of 2026-09-19 — see TC-081 in `docs/07`.
        """
        url = self.instance_url(study_uid, series_uid, sop_uid)
        response = self._session.get(
            url,
            headers={"Accept": f'multipart/related; type="{DICOM_MEDIA_TYPE}"'},
            timeout=self.timeout_s,
        )
        if response.status_code >= 400:
            raise DicomWebError(
                f"WADO-RS failed: {response.status_code} {response.reason} from {url}"
            )
        parts = parse_multipart(
            response.content, boundary_from_content_type(response.headers.get("Content-Type", ""))
        )
        if len(parts) != 1:
            raise DicomWebError(f"expected exactly one instance from {url}, got {len(parts)} parts")
        return parts[0]

    def search_series(self, **query: str) -> list[dict]:
        """QIDO-RS: search for series."""
        response = self._session.get(
            self.series_url(),
            params=query,
            headers={"Accept": "application/dicom+json"},
            timeout=self.timeout_s,
        )
        if response.status_code == 204:
            return []
        if response.status_code >= 400:
            raise DicomWebError(
                f"QIDO-RS failed: {response.status_code} {response.reason} from {self.series_url()}"
            )
        return response.json()


# DICOM JSON attribute keywords used in a STOW-RS response.
_REFERENCED_SOP_SEQUENCE = "00081199"
_FAILED_SOP_SEQUENCE = "00081198"
_SOP_INSTANCE_UID = "00081155"


def parse_store_response(status_code: int, payload: dict) -> StoreResult:
    """Read the referenced and failed instance UIDs out of a STOW-RS response.

    A response that reports failures is not an error at the HTTP level — the PACS may
    accept some instances and reject others — so the failed list is carried through
    rather than discarded. A caller that ignores it would treat a partial store as a
    whole one.
    """

    def uids(key: str) -> list[str]:
        sequence = (payload or {}).get(key, {}).get("Value", []) or []
        found = []
        for item in sequence:
            value = item.get(_SOP_INSTANCE_UID, {}).get("Value", []) or []
            found.extend(str(v) for v in value)
        return found

    return StoreResult(
        status_code=status_code,
        referenced_sop_instance_uids=uids(_REFERENCED_SOP_SEQUENCE),
        failed_sop_instance_uids=uids(_FAILED_SOP_SEQUENCE),
    )
