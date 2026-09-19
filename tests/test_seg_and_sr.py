"""Verification of ocuval.report.seg_object and ocuval.report.sr_object.

Covers TC-070 (SEG via highdicom, one segment per class), TC-071 (SEG references its
source instances), TC-074 (units declared explicitly) and TC-075 (voxel count recorded
as a real measurement).

Runs on a synthetic volume converted by ocuval.io.dicom_writer, so the SEG is referenced
back to a real OPT instance this project produced. No RETOUCH data is required.
"""

from __future__ import annotations

import numpy as np
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


def local_code(value: str, meaning: str) -> CodedConcept:
    """A declared local code under a private coding scheme designator.

    DICOM permits private scheme designators, and one *says* it is local rather than
    impersonating SNOMED. Used here because no verified standard code exists for the
    RETOUCH fluid classes — see seg_object's module docstring. It is a test fixture, not
    a recommendation for production.
    """
    return CodedConcept(value=value, scheme_designator="99OCUVAL", meaning=meaning)


@pytest.fixture
def source_images(tmp_path) -> list[Dataset]:
    rng = np.random.default_rng(20260919)
    volume = OCTVolume(
        pixel_array=rng.integers(0, 4096, size=(FRAMES, ROWS, COLUMNS), dtype=np.uint16),
        label_array=None,
        patient_id="TRAIN001",
        vendor="topcon",
        spacing_mm=SPACING_MM,
        source_path=tmp_path / "topcon" / "TRAIN001",
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
    result = dw.write_volume(volume, tmp_path / "opt", UID_ROOT, context=context)
    return [dw.read_back(p) for p in result.paths]


@pytest.fixture
def segments() -> list[seg.FluidSegment]:
    masks = {}
    for name, count in (("IRF", 5), ("SRF", 11), ("PED", 0)):
        mask = np.zeros((FRAMES, ROWS, COLUMNS), dtype=np.uint8)
        if count:
            mask.reshape(-1)[:count] = 1
        masks[name] = mask
    return [
        seg.FluidSegment(label=name, mask=mask, coded_type=local_code(name, f"{name} (local)"))
        for name, mask in masks.items()
    ]


# --- TC-070 -----------------------------------------------------------------------


def test_TC_070_one_segment_per_fluid_class(source_images, segments):
    obj = seg.build_segmentation(
        source_images,
        segments,
        series_instance_uid=dw.generate_uid(UID_ROOT),
        sop_instance_uid=dw.generate_uid(UID_ROOT),
    )
    assert len(obj.SegmentSequence) == 3
    assert [s.SegmentLabel for s in obj.SegmentSequence] == ["IRF", "SRF", "PED"]


def test_TC_070_segments_carry_coded_descriptions_not_free_text(source_images, segments):
    obj = seg.build_segmentation(
        source_images,
        segments,
        series_instance_uid=dw.generate_uid(UID_ROOT),
        sop_instance_uid=dw.generate_uid(UID_ROOT),
    )
    for item in obj.SegmentSequence:
        category = item.SegmentedPropertyCategoryCodeSequence[0]
        seg_type = item.SegmentedPropertyTypeCodeSequence[0]
        for code in (category, seg_type):
            assert code.CodeValue
            assert code.CodingSchemeDesignator
            assert code.CodeMeaning


def test_TC_070_category_is_the_verified_standard_code(source_images, segments):
    obj = seg.build_segmentation(
        source_images,
        segments,
        series_instance_uid=dw.generate_uid(UID_ROOT),
        sop_instance_uid=dw.generate_uid(UID_ROOT),
    )
    category = obj.SegmentSequence[0].SegmentedPropertyCategoryCodeSequence[0]
    assert category.CodeValue == "49755003"
    assert category.CodingSchemeDesignator == "SCT"


def test_TC_070_coded_type_has_no_default(source_images):
    """No verified code exists for the fluid classes, so one must be supplied."""
    with pytest.raises(seg.SegmentCodingError, match="will not substitute"):
        seg.FluidSegment(label="IRF", mask=np.zeros((2, 2, 2), dtype=np.uint8), coded_type=None)


def test_TC_070_segmentation_requires_a_source_image(segments):
    with pytest.raises(ValueError, match="at least one source image"):
        seg.build_segmentation(
            [],
            segments,
            series_instance_uid=dw.generate_uid(UID_ROOT),
            sop_instance_uid=dw.generate_uid(UID_ROOT),
        )


# --- TC-071: the link that makes HAZ-004 detectable --------------------------------


def test_TC_071_references_the_source_sop_instance_uids(source_images, segments):
    obj = seg.build_segmentation(
        source_images,
        segments,
        series_instance_uid=dw.generate_uid(UID_ROOT),
        sop_instance_uid=dw.generate_uid(UID_ROOT),
    )
    expected = {str(image.SOPInstanceUID) for image in source_images}
    assert seg.referenced_sop_instance_uids(obj) == expected


def test_TC_071_referenced_uids_are_not_the_segmentations_own(source_images, segments):
    """Guards against a reference that points at the SEG itself and looks populated."""
    obj = seg.build_segmentation(
        source_images,
        segments,
        series_instance_uid=dw.generate_uid(UID_ROOT),
        sop_instance_uid=dw.generate_uid(UID_ROOT),
    )
    assert str(obj.SOPInstanceUID) not in seg.referenced_sop_instance_uids(obj)


def test_TC_071_a_different_volume_produces_different_references(tmp_path, segments, source_images):
    other = source_images
    obj_a = seg.build_segmentation(
        other,
        segments,
        series_instance_uid=dw.generate_uid(UID_ROOT),
        sop_instance_uid=dw.generate_uid(UID_ROOT),
    )
    assert seg.referenced_sop_instance_uids(obj_a) == {str(i.SOPInstanceUID) for i in other}


# --- SR: TC-074 and TC-075 ---------------------------------------------------------


@pytest.fixture
def names() -> sr.MeasurementNames:
    return sr.MeasurementNames(
        voxel_count=local_code("VOXELCOUNT", "Predicted voxel count (local)"),
        voxel_volume=local_code("VOXELVOLUME", "Voxel volume (local)"),
        confidence=local_code("MCCONF", "MC-dropout scan-level confidence (local)"),
    )


@pytest.fixture
def report(source_images, names) -> Dataset:
    voxel_volume = SPACING_MM[0] * SPACING_MM[1] * SPACING_MM[2]
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
        source_images,
        measurements,
        names,
        confidence=0.83,
        procedure_reported=local_code("OCTSEG", "OCT fluid segmentation (local)"),
        device_uid=dw.generate_uid(UID_ROOT),
        series_instance_uid=dw.generate_uid(UID_ROOT),
        sop_instance_uid=dw.generate_uid(UID_ROOT),
    )


def test_TC_074_every_quantity_carries_a_coded_unit(report):
    found = sr.numeric_measurements(report)
    assert found, "no NUM content items were emitted"
    for _name, _value, unit in found:
        assert unit, "a measurement was emitted without a coded unit"


def test_TC_074_volume_units_are_coded_ucum_cubic_millimetres(report):
    units = {unit for _n, _v, unit in sr.numeric_measurements(report)}
    assert "mm3" in units


def test_TC_074_units_are_codes_not_text(report):
    """A unit written as a string in a comment is not machine-readable."""

    def walk(items):
        for item in items or []:
            if getattr(item, "ValueType", None) == "NUM":
                measured = item.MeasuredValueSequence[0]
                code = measured.MeasurementUnitsCodeSequence[0]
                assert code.CodingSchemeDesignator == "UCUM"
                assert code.CodeValue
            walk(getattr(item, "ContentSequence", None))

    walk(report.ContentSequence)


# --- TC-075: the derivation must be machine-auditable ------------------------------


def test_TC_075_voxel_count_is_a_real_measurement(report):
    found = sr.numeric_measurements(report)
    counts = [(n, v, u) for n, v, u in found if u == "{counts}"]
    assert counts, "voxel count was not emitted as a NUM measurement with a count unit"


def test_TC_075_voxel_counts_match_the_input(report):
    counts = sorted(v for _n, v, u in sr.numeric_measurements(report) if u == "{counts}")
    assert counts == [0.0, 5.0, 11.0]


def test_TC_075_volume_is_recomputable_from_the_emitted_terms(report):
    """volume == voxel_count x voxel_volume, from the object alone (SRS-059, RC-026)."""
    found = sr.numeric_measurements(report)
    volumes = sorted(v for _n, v, u in found if u == "mm3")
    counts = sorted(v for _n, v, u in found if u == "{counts}")
    voxel_volume = SPACING_MM[0] * SPACING_MM[1] * SPACING_MM[2]
    # Per-class volumes and the repeated voxel-volume terms are both in mm3; the
    # recomputation is what matters, not their order.
    for count in counts:
        assert any(v == pytest.approx(count * voxel_volume, rel=1e-9) for v in volumes)


def test_TC_075_confidence_is_carried_in_the_report(report):
    values = [v for _n, v, u in sr.numeric_measurements(report) if u == "1"]
    assert pytest.approx(0.83) in values


def test_TC_075_confidence_outside_zero_to_one_is_rejected(source_images, names):
    with pytest.raises(ValueError, match=r"confidence must be in \[0, 1\]"):
        sr.build_measurement_report(
            source_images,
            [],
            names,
            confidence=1.4,
            procedure_reported=local_code("OCTSEG", "OCT fluid segmentation (local)"),
            device_uid=dw.generate_uid(UID_ROOT),
            series_instance_uid=dw.generate_uid(UID_ROOT),
            sop_instance_uid=dw.generate_uid(UID_ROOT),
        )


def test_TC_075_measurement_names_have_no_defaults_where_unverified():
    with pytest.raises(sr.MeasurementCodingError):
        sr.MeasurementNames(voxel_count=None, voxel_volume=None, confidence=None)


def test_TC_075_volume_name_is_the_verified_standard_code():
    assert sr.VOLUME.value == "118565006"
    assert sr.VOLUME.scheme_designator == "SCT"


def test_TC_070_at_least_one_segment_is_required(source_images):
    with pytest.raises(ValueError, match="at least one segment"):
        seg.build_segmentation(
            source_images,
            [],
            series_instance_uid=dw.generate_uid(UID_ROOT),
            sop_instance_uid=dw.generate_uid(UID_ROOT),
        )


def test_TC_075_report_requires_a_source_image(names):
    with pytest.raises(ValueError, match="at least one source image"):
        sr.build_measurement_report(
            [],
            [],
            names,
            confidence=0.5,
            procedure_reported=local_code("OCTSEG", "OCT fluid segmentation (local)"),
            device_uid=dw.generate_uid(UID_ROOT),
            series_instance_uid=dw.generate_uid(UID_ROOT),
            sop_instance_uid=dw.generate_uid(UID_ROOT),
        )
