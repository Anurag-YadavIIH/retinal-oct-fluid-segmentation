"""TC-080, TC-081, TC-082 — the Orthanc round-trip.

**These tests have never been executed.** Docker was not available in the environment
where they were written (2026-09-19), so no Orthanc instance existed to run them
against. They are written against the DICOMweb specification and this project's
requirements, not against observed server behaviour, and they should be treated as
unverified until someone reports a run.

That is deliberate rather than merely unavoidable. A test written against a live server
tends to encode what that server happens to accept; one written against the
specification states what the software must do. The first time these run, a failure may
mean the client is wrong, or that the test asserts something the specification requires
and Orthanc does not implement. Both are findings, and the second belongs in `docs/11`.

Marked `requires_pacs`, which CI excludes (`docs/07` §2). To run them:

    make pacs-up          # or: docker compose -f docker/docker-compose.yml up -d orthanc
    pytest -m requires_pacs
"""

from __future__ import annotations

import os

import numpy as np
import pytest
from pydicom.dataset import Dataset

from ocuval.io import dicom_writer as dw
from ocuval.io import dicomweb
from ocuval.io.retouch_reader import OCTVolume
from ocuval.report import seg_object as seg

pytestmark = pytest.mark.requires_pacs

UID_ROOT = "1.2.826.0.1.3680043.10.9999"
SPACING_MM = (0.0039, 0.0117, 0.047)
DEFAULT_PACS = "http://localhost:8042/dicom-web"


@pytest.fixture(scope="module")
def client() -> dicomweb.DicomWebClient:
    """Endpoint from the environment, matching docker-compose's OCUVAL_PACS_URL.

    The client itself ignores the environment (RC-027); this reads the endpoint before
    constructing it, which is configuration rather than ambient HTTP settings.
    """
    return dicomweb.DicomWebClient(os.environ.get("OCUVAL_PACS_URL", DEFAULT_PACS))


@pytest.fixture
def written_instance(tmp_path):
    """One OPT instance on disk, with its identifying UIDs."""
    rng = np.random.default_rng(20260919)
    volume = OCTVolume(
        pixel_array=rng.integers(0, 4096, size=(6, 24, 16), dtype=np.uint16),
        label_array=None,
        patient_id="ROUNDTRIP001",
        vendor="topcon",
        spacing_mm=SPACING_MM,
        source_path=tmp_path / "topcon" / "ROUNDTRIP001",
    )
    region = Dataset()
    region.CodeValue = "TEST-MACULA"
    region.CodingSchemeDesignator = "99OCUVAL"
    region.CodeMeaning = "Macula (test fixture)"
    context = dw.AcquisitionContext(
        laterality="R",
        anatomic_region=region,
        manufacturer_model_name="3D OCT-2000",
        device_serial_number="SN-TEST-0001",
        acquisition_datetime="20260101120000",
    )
    return dw.write_volume(volume, tmp_path / "opt", UID_ROOT, context=context)


# --- TC-080: STOW-RS ---------------------------------------------------------------


def test_TC_080_instances_are_stored(client, written_instance):
    result = client.store(written_instance.paths)
    assert result.ok, f"PACS rejected instances: {result.failed_sop_instance_uids}"
    assert set(result.referenced_sop_instance_uids) == set(written_instance.sop_instance_uids)


def test_TC_080_storing_twice_does_not_report_failure(client, written_instance):
    """Re-storing the same instance is not an error; a PACS may accept or dedupe it.

    Asserted because a caller that treats a duplicate store as a failure would abort a
    resumed run that had already pushed some instances.
    """
    client.store(written_instance.paths)
    second = client.store(written_instance.paths)
    assert second.ok


# --- TC-081: WADO-RS and round-trip fidelity ---------------------------------------


def test_TC_081_stored_instance_is_retrievable(client, written_instance):
    client.store(written_instance.paths)
    retrieved = client.retrieve_instance(
        written_instance.study_instance_uid,
        written_instance.series_instance_uid,
        written_instance.sop_instance_uids[0],
    )
    assert retrieved, "WADO-RS returned an empty instance"


def test_TC_081_retrieved_instance_matches_what_was_sent(client, written_instance, tmp_path):
    """SRS-044: pixel data, spacing and identity must survive the round trip.

    Byte equality is deliberately not asserted. A PACS may legitimately re-encode an
    instance — changing transfer syntax, adding its own metadata — so the assertion is on
    the attributes the requirements name, not on the file.
    """
    import pydicom

    client.store(written_instance.paths)
    payload = client.retrieve_instance(
        written_instance.study_instance_uid,
        written_instance.series_instance_uid,
        written_instance.sop_instance_uids[0],
    )
    path = tmp_path / "retrieved.dcm"
    path.write_bytes(payload)
    got = pydicom.dcmread(str(path))
    sent = dw.read_back(written_instance.paths[0])

    assert got.SOPInstanceUID == sent.SOPInstanceUID
    assert got.Manufacturer == sent.Manufacturer  # vendor survives (SRS-009, RC-008)
    assert int(got.NumberOfFrames) == int(sent.NumberOfFrames)
    assert got.PixelData == sent.PixelData

    got_measures = got.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
    sent_measures = sent.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
    assert [float(v) for v in got_measures.PixelSpacing] == [
        float(v) for v in sent_measures.PixelSpacing
    ]
    assert float(got_measures.SliceThickness) == float(sent_measures.SliceThickness)


def test_TC_081_segmentation_round_trips_with_its_source_references(
    client, written_instance, tmp_path
):
    """The link that makes HAZ-004 detectable must survive the PACS, not just the writer."""
    import pydicom

    sources = [dw.read_back(p) for p in written_instance.paths]
    segmentation = seg.build_segmentation(
        sources,
        [
            seg.FluidSegment(label=name, mask=np.zeros((6, 24, 16), dtype=np.uint8))
            for name in ("IRF", "SRF", "PED")
        ],
        series_instance_uid=dw.generate_uid(UID_ROOT),
        sop_instance_uid=dw.generate_uid(UID_ROOT),
    )
    seg_path = tmp_path / "seg.dcm"
    segmentation.save_as(str(seg_path), write_like_original=False)

    client.store(written_instance.paths)
    client.store([seg_path])

    payload = client.retrieve_instance(
        segmentation.StudyInstanceUID,
        segmentation.SeriesInstanceUID,
        segmentation.SOPInstanceUID,
    )
    path = tmp_path / "retrieved_seg.dcm"
    path.write_bytes(payload)
    retrieved = pydicom.dcmread(str(path))

    assert seg.referenced_sop_instance_uids(retrieved) == {str(s.SOPInstanceUID) for s in sources}


def test_TC_081_unknown_instance_raises_rather_than_returning_empty(client):
    with pytest.raises(dicomweb.DicomWebError):
        client.retrieve_instance(f"{UID_ROOT}.404", f"{UID_ROOT}.404", f"{UID_ROOT}.404")


# --- TC-082: nothing beyond store and retrieve -------------------------------------


def test_TC_082_stored_instance_is_not_modified_by_this_software(client, written_instance):
    """SRS-045, RC-017: the client stores and retrieves, and does nothing else.

    Retrieving twice must yield the same object. If this software mutated or reconciled
    anything on the PACS, the second retrieval would differ.
    """
    client.store(written_instance.paths)
    args = (
        written_instance.study_instance_uid,
        written_instance.series_instance_uid,
        written_instance.sop_instance_uids[0],
    )
    assert client.retrieve_instance(*args) == client.retrieve_instance(*args)


def test_TC_082_search_does_not_alter_the_archive(client, written_instance):
    client.store(written_instance.paths)
    before = client.retrieve_instance(
        written_instance.study_instance_uid,
        written_instance.series_instance_uid,
        written_instance.sop_instance_uids[0],
    )
    client.search_series(StudyInstanceUID=written_instance.study_instance_uid)
    after = client.retrieve_instance(
        written_instance.study_instance_uid,
        written_instance.series_instance_uid,
        written_instance.sop_instance_uids[0],
    )
    assert before == after
