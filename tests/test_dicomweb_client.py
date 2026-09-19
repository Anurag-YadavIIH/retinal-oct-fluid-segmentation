"""Verification of the DICOMweb client internals — TC-083 and the multipart core.

Everything in this file runs today, with no Orthanc and no Docker. The round-trip
assertions that need a live PACS are in `test_dicomweb_roundtrip.py` and are marked
`requires_pacs`.

The split is deliberate. Multipart assembly and parsing are hand-written because
`requests` has no native support for multipart/related, which makes them both the most
likely defect and the part most worth testing against the specification rather than
against whatever a particular server happens to tolerate.
"""

from __future__ import annotations

import pytest

from ocuval.io import dicomweb as dw

BASE = "http://localhost:8042/dicom-web"


@pytest.fixture
def client() -> dw.DicomWebClient:
    return dw.DicomWebClient(BASE)


# --- TC-083: the client ignores ambient environment configuration -----------------


def test_TC_083_session_does_not_trust_the_environment(client):
    assert client._session.trust_env is False


def test_TC_083_netrc_and_proxy_variables_are_ignored(client, monkeypatch, tmp_path):
    """With credentials and proxies set in the environment, none may be picked up."""
    netrc = tmp_path / ".netrc"
    netrc.write_text("machine localhost login someone password secret\n", encoding="utf-8")
    monkeypatch.setenv("NETRC", str(netrc))
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(tmp_path / "nonexistent.pem"))

    fresh = dw.DicomWebClient(BASE)
    settings = fresh._session.merge_environment_settings(BASE, {}, None, None, None)
    assert settings["proxies"] == {}
    assert settings["verify"] is not str(tmp_path / "nonexistent.pem")


def test_TC_083_base_url_is_required():
    with pytest.raises(ValueError, match="base URL is required"):
        dw.DicomWebClient("")


def test_TC_083_trailing_slash_is_normalised():
    assert dw.DicomWebClient(BASE + "/").base_url == BASE


# --- URL construction -------------------------------------------------------------


def test_TC_080_instance_url_is_built_from_the_three_uids(client):
    url = client.instance_url("1.2.3", "4.5.6", "7.8.9")
    assert url == f"{BASE}/studies/1.2.3/series/4.5.6/instances/7.8.9"


def test_TC_080_studies_and_series_urls(client):
    assert client.studies_url() == f"{BASE}/studies"
    assert client.series_url() == f"{BASE}/series"


@pytest.mark.parametrize(
    ("study", "series", "sop", "missing"),
    [("", "s", "i", "study"), ("st", "", "i", "series"), ("st", "s", "", "instance")],
)
def test_TC_080_missing_uid_is_rejected(client, study, series, sop, missing):
    """A URL with an empty path segment addresses the wrong resource, silently."""
    with pytest.raises(ValueError, match=f"{missing} UID is required"):
        client.instance_url(study, series, sop)


# --- multipart assembly -----------------------------------------------------------


def test_TC_080_multipart_body_has_opening_and_closing_boundaries():
    body = dw.build_multipart([b"PAYLOAD"], "abc123")
    assert body.startswith(b"--abc123\r\n")
    assert body.endswith(b"--abc123--\r\n")


def test_TC_080_each_part_declares_its_media_type_and_length():
    body = dw.build_multipart([b"AB", b"CDEF"], "bnd")
    assert body.count(b"Content-Type: application/dicom") == 2
    assert b"Content-Length: 2" in body
    assert b"Content-Length: 4" in body


def test_TC_080_lines_are_crlf_delimited():
    """A receiver that parses strictly rejects bare LF; one that parses loosely may
    accept a truncated body. Neither is a good outcome."""
    body = dw.build_multipart([b"X"], "bnd")
    headers = body.split(b"\r\n\r\n")[0]
    assert b"\n" not in headers.replace(b"\r\n", b"")


def test_TC_080_empty_part_list_is_rejected():
    with pytest.raises(ValueError, match="at least one part"):
        dw.build_multipart([], "bnd")


@pytest.mark.parametrize("bad", ["", 'has"quote', "has space", "has\\backslash"])
def test_TC_080_unusable_boundary_is_rejected(bad):
    with pytest.raises(ValueError, match="boundary"):
        dw.build_multipart([b"X"], bad)


# --- multipart parsing ------------------------------------------------------------


def test_TC_081_round_trips_through_assembly_and_parsing():
    parts = [b"\x00\x01binary", b"second-part", b"\xff" * 64]
    body = dw.build_multipart(parts, "rt")
    assert dw.parse_multipart(body, "rt") == parts


def test_TC_081_preserves_binary_payloads_exactly():
    payload = bytes(range(256))
    assert dw.parse_multipart(dw.build_multipart([payload], "b"), "b") == [payload]


def test_TC_081_truncated_body_raises_rather_than_returning_partial_parts():
    """The failure that makes a half-retrieved study look whole."""
    body = dw.build_multipart([b"one", b"two"], "trunc")
    truncated = body[: len(body) // 2]
    with pytest.raises(dw.DicomWebError, match="truncated"):
        dw.parse_multipart(truncated, "trunc")


def test_TC_081_parsing_requires_a_boundary():
    with pytest.raises(ValueError, match="boundary is required"):
        dw.parse_multipart(b"anything", "")


def test_TC_081_boundary_is_read_from_the_content_type():
    header = 'multipart/related; type="application/dicom"; boundary=abc-123'
    assert dw.boundary_from_content_type(header) == "abc-123"


def test_TC_081_quoted_boundary_is_read():
    header = 'multipart/related; boundary="quoted-bnd"; type="application/dicom"'
    assert dw.boundary_from_content_type(header) == "quoted-bnd"


@pytest.mark.parametrize("header", ["", "application/dicom+json", "multipart/related"])
def test_TC_081_missing_boundary_raises_rather_than_guessing(header):
    with pytest.raises(dw.DicomWebError, match="no boundary"):
        dw.boundary_from_content_type(header)


# --- STOW-RS response parsing -----------------------------------------------------


def test_TC_080_store_response_reports_referenced_instances():
    payload = {
        "00081199": {
            "Value": [{"00081155": {"Value": ["1.2.3"]}}, {"00081155": {"Value": ["4.5.6"]}}]
        }
    }
    result = dw.parse_store_response(200, payload)
    assert result.referenced_sop_instance_uids == ["1.2.3", "4.5.6"]
    assert result.ok


def test_TC_080_store_response_carries_failures_rather_than_discarding_them():
    """A PACS may accept some instances and reject others; a caller that ignores the
    failed list treats a partial store as a whole one."""
    payload = {
        "00081199": {"Value": [{"00081155": {"Value": ["ok-1"]}}]},
        "00081198": {"Value": [{"00081155": {"Value": ["bad-1"]}}]},
    }
    result = dw.parse_store_response(202, payload)
    assert result.referenced_sop_instance_uids == ["ok-1"]
    assert result.failed_sop_instance_uids == ["bad-1"]
    assert not result.ok


def test_TC_080_empty_store_response_is_handled():
    result = dw.parse_store_response(200, {})
    assert result.referenced_sop_instance_uids == []
    assert result.ok


def test_TC_080_store_requires_instances(client):
    with pytest.raises(ValueError, match="no instances to store"):
        client.store([])


# --- SRS-045 / RC-017: nothing beyond store and retrieve --------------------------


def test_TC_082_client_exposes_no_mutating_operation():
    """No delete, modify, reconcile, or sign-off. A pre-read produces candidates."""
    forbidden = ("delete", "remove", "modify", "update", "reconcile", "verify", "approve", "sign")
    public = [n for n in dir(dw.DicomWebClient) if not n.startswith("_")]
    for name in public:
        assert not any(word in name.lower() for word in forbidden), name


def test_TC_082_client_issues_only_get_and_post():
    """Read the source rather than trusting the method names above."""
    import inspect

    source = inspect.getsource(dw.DicomWebClient)
    for verb in ("_session.delete", "_session.put", "_session.patch"):
        assert verb not in source
