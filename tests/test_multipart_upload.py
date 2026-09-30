"""Multipart form handling through a real FastAPI route (TC-087).

**Why this exists before the service does.** `python-multipart` was bumped 0.0.9 to
0.0.31 against `fastapi==0.111.1`, and Starlette imports it under a module name that
changed across that range -- older Starlette does `import multipart`, newer
`python_multipart`. Nothing in this repository exercised it, because `/infer` is not
built, so a broken combination would have been discovered when the service was written
and blamed on the service.

The route here is defined in the test, not imported from `ocuval.service`. That is
deliberate: this tests the **dependency combination**, not this project's API, and it
must keep working as a signal while `service/api.py` is still a stub.
"""

from __future__ import annotations

import io

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi is a declared dependency")
pytest.importorskip("multipart", reason="python-multipart is a declared dependency")

from fastapi import FastAPI, File, Form, UploadFile  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def build_app() -> FastAPI:
    app = FastAPI()

    @app.post("/upload")
    # B008 (function call in a default argument) is FastAPI's required idiom for
    # declaring form and file parameters, not an accident.
    async def upload(note: str = Form(...), payload: UploadFile = File(...)):  # noqa: B008
        content = await payload.read()
        return {
            "note": note,
            "filename": payload.filename,
            "content_type": payload.content_type,
            "size": len(content),
            "head": content[:4].hex(),
        }

    return app


def test_TC_087_python_multipart_is_importable_under_the_name_starlette_uses():
    """The specific failure the version bump risked.

    Starlette moved from `import multipart` to `import python_multipart` across this
    range. Whichever name this Starlette uses, at least one must import, or file upload
    fails at request time rather than at import time -- which is the worst moment.
    """
    import importlib

    available = []
    for name in ("multipart", "python_multipart"):
        try:
            importlib.import_module(name)
        except ImportError:
            continue
        available.append(name)
    assert available, (
        "neither 'multipart' nor 'python_multipart' imports, so Starlette cannot parse "
        "multipart forms regardless of what python-multipart's version says"
    )


def test_TC_087_a_multipart_form_round_trips_through_a_route():
    """The combination, exercised end to end rather than asserted from versions."""
    payload = b"\x00\x01DICM-not-really"
    with TestClient(build_app()) as client:
        response = client.post(
            "/upload",
            data={"note": "cirrus_holdout"},
            files={"payload": ("volume.dcm", io.BytesIO(payload), "application/dicom")},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["note"] == "cirrus_holdout"
    assert body["filename"] == "volume.dcm"
    assert body["content_type"] == "application/dicom"
    assert body["size"] == len(payload)
    assert body["head"] == payload[:4].hex(), "the bytes arrived altered"


def test_TC_087_a_missing_required_part_is_rejected_not_silently_accepted():
    """Guards the guard: a route that accepted anything would pass the test above."""
    with TestClient(build_app()) as client:
        response = client.post("/upload", data={"note": "no file attached"})
    assert response.status_code == 422, (
        f"expected 422 for a missing file part, got {response.status_code}. A route that "
        f"accepts a malformed form is not validating it."
    )


def test_TC_087_versions_are_the_ones_pinned():
    """If this drifts, the combination under test is not the combination shipped."""
    from importlib.metadata import version

    assert version("fastapi") == "0.111.1"
    assert version("python-multipart") == "0.0.31"
