"""TC-136 — every text value in an emitted object is encodable without substitution.

Traces to: SRS-095; `docs/11` §10 item 7

**The defect this exists for.** The private coding scheme's declaration carried an em dash
(U+2014) in Coding Scheme Responsible Organization. Neither the SEG nor the SR declares
Specific Character Set, the dash is not in ISO 8859-1, and pydicom substituted `?` when
writing, with a warning and nothing more. Every SEG and SR emitted before the fix stored a
value different from the one built. No test saw it, because no test serialised an object:
the unit tests build objects in memory, and pydicom encodes only when writing bytes.

So this test writes bytes. It builds an OPT object, a SEG and an SR with the real builders
from synthetic input, serialises each with the warning raised as an error, checks every text
value against the declared repertoire, and reads the bytes back to confirm nothing changed.
"""

from __future__ import annotations

import io
import warnings
from collections import Counter
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
SUBSTITUTION = "Failed to encode value"


def local_code(value: str, meaning: str) -> CodedConcept:
    return CodedConcept(value=value, scheme_designator="99OCUVAL", meaning=meaning)


def text_values(dataset: Dataset, path: str = ""):
    """Every text value in the dataset, nested sequences included, as (path, value)."""
    for element in dataset:
        if element.VR == "SQ":
            for index, item in enumerate(element.value):
                yield from text_values(item, f"{path}{element.keyword}[{index}].")
            continue
        if element.VR in ("OB", "OW", "OF", "OD", "OL", "OV", "UN") or element.value is None:
            continue
        values = element.value if isinstance(element.value, list | tuple) else [element.value]
        for value in values:
            if isinstance(value, str | pydicom.valuerep.PersonName):
                yield f"{path}{element.keyword}", str(value)


def outside_repertoire(dataset: Dataset) -> list[str]:
    """Text values not representable where no character set is declared (SRS-095)."""
    if dataset.get("SpecificCharacterSet"):
        raise AssertionError(
            "a Specific Character Set is declared; this check covers the default repertoire "
            "only, so extend it before relying on it"
        )
    return [
        f"{where}: {value!r}"
        for where, value in text_values(dataset)
        if any(ord(character) > 127 for character in value)
    ]


def unchanged_on_writing(built: Dataset, stored: Dataset) -> list[str]:
    """Text values as built that the stored object does not carry unchanged.

    One direction only: a read-back object also has values the built one held as dates,
    times or empty values, which the walker skips in memory, so equality both ways would
    fail on types rather than on content.
    """
    remaining = Counter(text_values(stored))
    missing = []
    for pair in text_values(built):
        if remaining[pair]:
            remaining[pair] -= 1
        else:
            missing.append(f"{pair[0]}: {pair[1]!r}")
    return missing


def serialise(dataset: Dataset) -> bytes:
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.filterwarnings("error", message=SUBSTITUTION)
        dataset.save_as(buffer, write_like_original=False)
    return buffer.getvalue()


@pytest.fixture
def opt_path(tmp_path) -> Path:
    rng = np.random.default_rng(20260919)
    volume = OCTVolume(
        pixel_array=rng.integers(0, 4096, size=(FRAMES, ROWS, COLUMNS), dtype=np.uint16),
        label_array=None,
        patient_id="SYNTH001",
        vendor="topcon",
        spacing_mm=SPACING_MM,
        source_path=tmp_path / "topcon" / "SYNTH001",
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
    with warnings.catch_warnings():
        warnings.filterwarnings("error", message=SUBSTITUTION)
        result = dw.write_volume(volume, tmp_path / "opt", UID_ROOT, context=context)
    return result.paths[0]


@pytest.fixture
def sources(opt_path) -> list[Dataset]:
    return [dw.read_back(opt_path)]


@pytest.fixture
def segmentation(sources) -> Dataset:
    """Segments without a caller-supplied code, so the private scheme is declared."""
    masks = [np.zeros((FRAMES, ROWS, COLUMNS), dtype=np.uint8) for _ in range(3)]
    masks[0].reshape(-1)[:5] = 1
    return seg.build_segmentation(
        sources,
        [
            seg.FluidSegment(label=name, mask=mask)
            for name, mask in zip(("IRF", "SRF", "PED"), masks, strict=True)
        ],
        series_instance_uid=dw.generate_uid(UID_ROOT),
        sop_instance_uid=dw.generate_uid(UID_ROOT),
    )


@pytest.fixture
def report(sources) -> Dataset:
    voxel_volume = SPACING_MM[0] * SPACING_MM[1] * SPACING_MM[2]
    names = sr.MeasurementNames(
        voxel_count=local_code("VOXELCOUNT", "Predicted voxel count (local)"),
        voxel_volume=local_code("VOXELVOLUME", "Voxel volume (local)"),
        confidence=local_code("MCCONF", "MC-dropout scan-level confidence (local)"),
    )
    measurements = [
        sr.FluidMeasurement(
            label=label,
            coded_type=local_code(label, f"{label} (local)"),
            volume_mm3=count * voxel_volume,
            voxel_count=count,
            voxel_volume_mm3=voxel_volume,
        )
        for label, count in (("IRF", 5), ("SRF", 11), ("PED", 0))
    ]
    return sr.build_measurement_report(
        sources,
        measurements,
        names,
        confidence=0.83,
        procedure_reported=local_code("OCTSEG", "OCT fluid segmentation (local)"),
        device_uid=dw.generate_uid(UID_ROOT),
        series_instance_uid=dw.generate_uid(UID_ROOT),
        sop_instance_uid=dw.generate_uid(UID_ROOT),
    )


def test_TC_136_the_opt_object_is_ascii_and_written_without_substitution(opt_path):
    written = pydicom.dcmread(str(opt_path))
    assert outside_repertoire(written) == []


def test_TC_136_the_seg_is_ascii_and_serialises_without_substitution(segmentation):
    assert "CodingSchemeIdentificationSequence" in segmentation, "private scheme not declared"
    assert outside_repertoire(segmentation) == []
    stored = pydicom.dcmread(io.BytesIO(serialise(segmentation)))
    assert unchanged_on_writing(segmentation, stored) == []


def test_TC_136_the_sr_is_ascii_and_serialises_without_substitution(report):
    assert "CodingSchemeIdentificationSequence" in report, "private scheme not declared"
    assert outside_repertoire(report) == []
    stored = pydicom.dcmread(io.BytesIO(serialise(report)))
    assert unchanged_on_writing(report, stored) == []


def test_TC_136_a_non_ascii_value_is_reported_and_refused(segmentation):
    """Shown able to fail: a value outside the repertoire is found, and writing it raises."""
    item = segmentation.CodingSchemeIdentificationSequence[0]
    item.CodingSchemeResponsibleOrganization = "OcuVal research project — test"
    assert outside_repertoire(segmentation) == [
        "CodingSchemeIdentificationSequence[0].CodingSchemeResponsibleOrganization: "
        "'OcuVal research project — test'"
    ]
    with pytest.raises(UserWarning, match=SUBSTITUTION):
        serialise(segmentation)


def test_TC_136_a_substituted_value_is_caught_on_read_back(segmentation):
    """Shown able to fail: if substitution happened silently, the comparison sees it."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        item = segmentation.CodingSchemeIdentificationSequence[0]
        item.CodingSchemeResponsibleOrganization = "OcuVal research project — test"
        buffer = io.BytesIO()
        segmentation.save_as(buffer, write_like_original=False)
    stored = pydicom.dcmread(io.BytesIO(buffer.getvalue()))
    assert unchanged_on_writing(segmentation, stored) == [
        "CodingSchemeIdentificationSequence[0].CodingSchemeResponsibleOrganization: "
        "'OcuVal research project — test'"
    ]
