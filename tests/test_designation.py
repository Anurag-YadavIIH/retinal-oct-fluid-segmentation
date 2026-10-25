"""TC-077 — the research-use designation is carried in every emitted object.

Traces to: SRS-042, RC-014; `docs/11` §10 item 2 (the author's decision of 2026-10-16)

Checks all three parts of the decided mechanism on **real builder output, serialised and read
back**, because an attribute set in memory and lost on writing would satisfy a check of the
in-memory object and protect nothing:

- **A**, Content Qualification `RESEARCH` on the SEG, the SR and an Ophthalmic Tomography
  Image object from `io/dicom_writer`;
- **B**, the exact text below in the SEG's Series Description and Content Description and the
  SR's Series Description;
- **C**, the SR's Verification Flag UNVERIFIED and Preliminary Flag PRELIMINARY.

The expected text is written here as a literal, not imported from the code, so the test
cannot agree with a wrong constant. RC-014 counts as verified only once this passes.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pydicom
import pytest
from highdicom.sr import CodedConcept
from pydicom.dataset import Dataset

from ocuval.io import dicom_writer as dw
from ocuval.io.retouch_reader import OCTVolume
from ocuval.report import seg_object as seg
from ocuval.report import sr_object as sr

UID_ROOT = "1.2.826.0.1.3680043.10.9999"
SPACING_MM = (0.0039, 0.0117, 0.047)
FRAMES, ROWS, COLUMNS = 4, 16, 12
TEXT = "RESEARCH USE ONLY: automated, not validated, review required"


def local_code(value: str, meaning: str) -> CodedConcept:
    return CodedConcept(value=value, scheme_designator="99OCUVAL", meaning=meaning)


def read_back(dataset: Dataset) -> Dataset:
    buffer = io.BytesIO()
    dataset.save_as(buffer, write_like_original=False)
    return pydicom.dcmread(io.BytesIO(buffer.getvalue()))


@pytest.fixture
def opt_path(tmp_path) -> Path:
    rng = np.random.default_rng(20261016)
    volume = OCTVolume(
        pixel_array=rng.integers(0, 4096, size=(FRAMES, ROWS, COLUMNS), dtype=np.uint16),
        label_array=None,
        patient_id="SYNTH077",
        vendor="topcon",
        spacing_mm=SPACING_MM,
        source_path=tmp_path / "topcon" / "SYNTH077",
    )
    result = dw.write_volume(volume, tmp_path / "opt", UID_ROOT, research_exception=True)
    return result.paths[0]


@pytest.fixture
def sources(opt_path) -> list[Dataset]:
    return [dw.read_back(opt_path)]


@pytest.fixture
def segmentation(sources) -> Dataset:
    masks = [np.zeros((FRAMES, ROWS, COLUMNS), dtype=np.uint8) for _ in range(3)]
    masks[0].reshape(-1)[:5] = 1
    classes = ("IRF", "SRF", "PED")
    built = seg.build_segmentation(
        sources,
        [seg.FluidSegment(label=c, mask=m) for c, m in zip(classes, masks, strict=True)],
        series_instance_uid=dw.generate_uid(UID_ROOT),
        sop_instance_uid=dw.generate_uid(UID_ROOT),
    )
    return read_back(built)


@pytest.fixture
def report(sources) -> Dataset:
    voxel_volume = SPACING_MM[0] * SPACING_MM[1] * SPACING_MM[2]
    built = sr.build_measurement_report(
        sources,
        [
            sr.FluidMeasurement(
                label=c,
                coded_type=local_code(c, c),
                volume_mm3=n * voxel_volume,
                voxel_count=n,
                voxel_volume_mm3=voxel_volume,
            )
            for c, n in (("IRF", 5), ("SRF", 0), ("PED", 2))
        ],
        sr.MeasurementNames(
            voxel_count=local_code("VC", "count"),
            voxel_volume=local_code("VV", "voxel volume"),
            confidence=local_code("CONF", "confidence"),
        ),
        confidence=0.9,
        review_recommended=True,
        procedure_reported=local_code("OCTSEG", "OCT fluid segmentation"),
        device_uid=dw.generate_uid(UID_ROOT),
        series_instance_uid=dw.generate_uid(UID_ROOT),
        sop_instance_uid=dw.generate_uid(UID_ROOT),
    )
    return read_back(built)


def test_TC_077_the_text_is_ascii_and_fits_a_long_string():
    assert TEXT.isascii() and len(TEXT) <= 64  # LO, PS3.5 Table 6.2-1


def test_TC_077_a_content_qualification_research_on_every_object(opt_path, segmentation, report):
    opt = pydicom.dcmread(str(opt_path))
    for name, dataset in (("OPT", opt), ("SEG", segmentation), ("SR", report)):
        assert dataset.get("ContentQualification") == "RESEARCH", name


def test_TC_077_b_the_text_in_the_seg_series_and_content_descriptions(segmentation):
    assert segmentation.get("SeriesDescription") == TEXT
    assert segmentation.get("ContentDescription") == TEXT


def test_TC_077_b_the_text_in_the_sr_series_description(report):
    assert report.get("SeriesDescription") == TEXT


def test_TC_077_c_the_sr_is_unverified_and_preliminary(report):
    assert report.VerificationFlag == "UNVERIFIED"
    assert report.PreliminaryFlag == "PRELIMINARY"
    assert "VerifyingObserverSequence" not in report
