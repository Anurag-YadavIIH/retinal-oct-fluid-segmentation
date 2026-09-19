"""Verification of ocuval.io.dicom_writer.

Covers TC-020..TC-024 (conversion), TC-026 (absent laterality aborts), TC-027 (research
exception omits rather than invents) and TC-028 (object checked against the published
IOD module table).

Everything runs on a synthetic anisotropic volume. No RETOUCH data is required.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest
from highdicom import _iods
from pydicom.dataset import Dataset

from ocuval.io import dicom_writer as dw
from ocuval.io.retouch_reader import OCTVolume

UID_ROOT = "1.2.826.0.1.3680043.10.9999"
SPACING_MM = (0.0039, 0.0117, 0.047)


@pytest.fixture
def volume(tmp_path) -> OCTVolume:
    """A synthetic volume with realistic anisotropic spacing and distinct dimensions.

    Rows, columns and frame count are all different so a transposed axis cannot pass by
    coincidence.
    """
    rng = np.random.default_rng(20260916)
    pixels = rng.integers(0, 4096, size=(9, 40, 32), dtype=np.uint16)
    return OCTVolume(
        pixel_array=pixels,
        label_array=None,
        patient_id="TRAIN001",
        vendor="topcon",
        spacing_mm=SPACING_MM,
        source_path=tmp_path / "topcon" / "TRAIN001",
    )


@pytest.fixture
def context() -> dw.AcquisitionContext:
    """Context a real acquisition would carry. Synthetic volumes supply it so the
    production path is fully exercised rather than only the exception path."""
    region = Dataset()
    region.CodeValue = "TEST-MACULA"
    region.CodingSchemeDesignator = "99OCUVAL"
    region.CodeMeaning = "Macula (test fixture, not a verified CID 4209 binding)"
    return dw.AcquisitionContext(
        laterality="R",
        anatomic_region=region,
        manufacturer_model_name="3D OCT-2000",
        device_serial_number="SN-TEST-0001",
        acquisition_datetime="20260101120000",
    )


# --- TC-020, TC-021, TC-022, TC-023 -----------------------------------------------


def test_TC_020_writes_the_configured_sop_class(volume, context, tmp_path):
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    ds = dw.read_back(result.paths[0])
    assert ds.SOPClassUID == dw.OPT_SOP_CLASS_UID
    assert ds.Modality == "OPT"


def test_TC_020_is_multi_frame_with_one_frame_per_bscan(volume, context, tmp_path):
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    ds = dw.read_back(result.paths[0])
    assert int(ds.NumberOfFrames) == volume.pixel_array.shape[0]
    assert len(ds.PerFrameFunctionalGroupsSequence) == volume.pixel_array.shape[0]


def test_TC_021_uids_are_generated_under_the_configured_root(volume, context, tmp_path):
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    ds = dw.read_back(result.paths[0])
    for uid in (ds.SOPInstanceUID, ds.StudyInstanceUID, ds.SeriesInstanceUID):
        assert str(uid).startswith(UID_ROOT + ".")


def test_TC_021_uid_root_is_required(volume, context, tmp_path):
    with pytest.raises(ValueError, match="UID root is required"):
        dw.write_volume(volume, tmp_path / "out", "", context=context)


def test_TC_022_uids_are_recorded_in_the_result(volume, context, tmp_path):
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    ds = dw.read_back(result.paths[0])
    assert result.sop_instance_uids == [ds.SOPInstanceUID]
    assert result.study_instance_uid == ds.StudyInstanceUID


def test_TC_022_two_conversions_differ_only_in_uids(volume, context, tmp_path):
    first = dw.read_back(
        dw.write_volume(volume, tmp_path / "a", UID_ROOT, context=context).paths[0]
    )
    second = dw.read_back(
        dw.write_volume(volume, tmp_path / "b", UID_ROOT, context=context).paths[0]
    )
    uid_keywords = {
        "SOPInstanceUID",
        "StudyInstanceUID",
        "SeriesInstanceUID",
        "DimensionOrganizationSequence",
        "ContentTime",
        "ContentDate",
    }
    for elem in first:
        if elem.keyword in uid_keywords or elem.keyword == "PixelData":
            continue
        assert elem.value == getattr(second, elem.keyword), elem.keyword
    assert first.PixelData == second.PixelData
    assert first.SOPInstanceUID != second.SOPInstanceUID


def test_TC_023_vendor_is_recoverable_from_the_object(volume, context, tmp_path):
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    assert dw.read_back(result.paths[0]).Manufacturer == "topcon"


# --- TC-024: spacing, the HAZ-012 surface ------------------------------------------


def test_TC_024_spacing_is_in_pixel_measures_not_top_level(volume, context, tmp_path):
    """For a multi-frame IOD spacing lives in the functional group, not as a top-level
    PixelSpacing element. Writing it top-level would be silently ignored by a conformant
    reader."""
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    ds = dw.read_back(result.paths[0])
    assert "PixelSpacing" not in ds
    measures = ds.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
    assert measures.PixelSpacing is not None


def test_TC_024_spacing_round_trips_with_the_correct_axis_order(volume, context, tmp_path):
    """Axial first, lateral second, B-scan separation as SliceThickness."""
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    measures = (
        dw.read_back(result.paths[0]).SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
    )
    axial, lateral, separation = SPACING_MM
    assert float(measures.PixelSpacing[0]) == pytest.approx(axial)
    assert float(measures.PixelSpacing[1]) == pytest.approx(lateral)
    assert float(measures.SliceThickness) == pytest.approx(separation)


def test_TC_024_anisotropy_survives_conversion(volume, context, tmp_path):
    """Three distinct values must remain three distinct values."""
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    measures = (
        dw.read_back(result.paths[0]).SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
    )
    values = [
        float(measures.PixelSpacing[0]),
        float(measures.PixelSpacing[1]),
        float(measures.SliceThickness),
    ]
    assert len(set(values)) == 3


def test_TC_024_native_geometry_is_preserved(volume, context, tmp_path):
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    ds = dw.read_back(result.paths[0])
    frames, rows, columns = volume.pixel_array.shape
    assert (int(ds.NumberOfFrames), int(ds.Rows), int(ds.Columns)) == (frames, rows, columns)


def test_TC_024_pixel_data_round_trips_unchanged(volume, context, tmp_path):
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    ds = dw.read_back(result.paths[0])
    restored = np.frombuffer(ds.PixelData, dtype=np.uint16).reshape(volume.pixel_array.shape)
    assert np.array_equal(restored, volume.pixel_array)


def test_TC_024_implausible_spacing_is_rejected_before_writing(volume, context, tmp_path):
    bad = OCTVolume(
        pixel_array=volume.pixel_array,
        label_array=None,
        patient_id=volume.patient_id,
        vendor=volume.vendor,
        spacing_mm=(3.9, 0.0117, 0.047),  # micrometres read as millimetres
        source_path=volume.source_path,
    )
    with pytest.raises(ValueError, match="physical limit"):
        dw.write_volume(bad, tmp_path / "out", UID_ROOT, context=context)


# --- TC-026: refuse rather than fill -----------------------------------------------


def test_TC_026_absent_context_aborts_conversion(volume, tmp_path):
    with pytest.raises(dw.AcquisitionContextError) as excinfo:
        dw.write_volume(volume, tmp_path / "out", UID_ROOT)
    message = str(excinfo.value)
    assert "ocular-region-imaged.AnatomicRegionSequence" in message
    assert "AcquisitionDateTime" in message
    assert "will not invent" in message


def test_TC_026_nothing_is_written_when_context_is_missing(volume, tmp_path):
    out = tmp_path / "out"
    with pytest.raises(dw.AcquisitionContextError):
        dw.write_volume(volume, out, UID_ROOT)
    assert not out.exists() or not list(out.glob("*.dcm"))


@pytest.mark.parametrize("bad", ["", "U", "UNKNOWN", "r", "X", "Left"])
def test_TC_026_laterality_outside_the_enumerated_values_is_refused(bad):
    with pytest.raises(dw.AcquisitionContextError, match="laterality must be one of"):
        dw.AcquisitionContext(laterality=bad)


def test_TC_026_there_is_no_unknown_laterality_value():
    """The absence of an unknown member is why the writer must refuse."""
    assert set(dw.LATERALITY_VALUES) == {"R", "L", "B"}


def test_TC_026_acquisition_context_has_no_default_laterality():
    import inspect

    parameter = inspect.signature(dw.AcquisitionContext).parameters["laterality"]
    assert parameter.default is inspect.Parameter.empty


# --- TC-027: omit, never fill -------------------------------------------------------


def test_TC_027_research_exception_omits_the_module(volume, tmp_path):
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, research_exception=True)
    ds = dw.read_back(result.paths[0])
    assert "ImageLaterality" not in ds
    assert "AnatomicRegionSequence" not in ds


def test_TC_027_omitted_attributes_are_absent_not_invented(volume, tmp_path):
    """The distinction the whole design rests on: absent, not present-and-wrong."""
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, research_exception=True)
    ds = dw.read_back(result.paths[0])
    for attrs in dw.UNPOPULATABLE.values():
        for keyword in attrs:
            assert keyword not in ds, f"{keyword} was populated under the research exception"


def test_TC_027_omissions_are_recorded_in_the_result(volume, tmp_path):
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, research_exception=True)
    assert "ocular-region-imaged.ImageLaterality" in result.omissions
    assert "ophthalmic-tomography-image.AcquisitionDateTime" in result.omissions
    assert "enhanced-general-equipment.DeviceSerialNumber" in result.omissions


def test_TC_027_omissions_are_logged_at_warning_level(volume, tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="ocuval.io.dicom_writer"):
        dw.write_volume(volume, tmp_path / "out", UID_ROOT, research_exception=True)
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("ImageLaterality" in m for m in warnings)
    assert any("non-conformant" in m for m in warnings)


def test_TC_027_exception_is_off_by_default(volume, tmp_path):
    import inspect

    parameter = inspect.signature(dw.write_volume).parameters["research_exception"]
    assert parameter.default is False
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_TC_027_supplied_context_produces_no_omissions(volume, context, tmp_path):
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    assert result.omissions == []
    ds = dw.read_back(result.paths[0])
    assert ds.ImageLaterality == "R"


# --- TC-028: check, not hope --------------------------------------------------------


def test_TC_028_object_satisfies_every_mandatory_module(volume, context, tmp_path):
    """Validated against highdicom's PS3.3-derived tables, not against our own notion."""
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    assert dw.validate_against_iod(dw.read_back(result.paths[0])) == []


def test_TC_028_validator_reports_a_removed_mandatory_attribute(volume, context, tmp_path):
    """An assertion never shown to fire has not been shown to work."""
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
    ds = dw.read_back(result.paths[0])
    del ds.ImageLaterality
    missing = dw.validate_against_iod(ds)
    assert "ocular-region-imaged.ImageLaterality" in missing


def test_TC_028_validator_honours_recorded_omissions(volume, tmp_path):
    result = dw.write_volume(volume, tmp_path / "out", UID_ROOT, research_exception=True)
    ds = dw.read_back(result.paths[0])
    assert dw.validate_against_iod(ds, permitted_omissions=tuple(result.omissions)) == []
    # ...and without the permission, the same object is reported incomplete.
    assert dw.validate_against_iod(ds) != []


def test_TC_028_module_list_comes_from_the_standard_not_from_us():
    """Guards the guard: if highdicom's table is not the source, the check is circular."""
    from_table = {m["key"] for m in _iods.IOD_MODULE_MAP[dw.IOD_KEY] if m["usage"] == "M"}
    assert set(dw.required_modules()) == from_table
    assert "ocular-region-imaged" in from_table
    assert "ophthalmic-tomography-image-multi-frame-functional-groups" in from_table


def test_TC_028_ophthalmic_frame_location_is_not_required():
    """Usage U in Table A.52.4.3-1 — omitted with no conformance consequence."""
    ds_keywords = set()
    for module in dw.required_modules():
        from highdicom import _modules

        ds_keywords |= {a["keyword"] for a in _modules.MODULE_ATTRIBUTE_MAP[module]}
    # The macro's attributes may appear in the flattened table; what matters is that we
    # do not treat the macro as mandatory.
    assert "OphthalmicFrameLocationSequence" not in {
        a for attrs in dw.UNPOPULATABLE.values() for a in attrs
    }


def test_TC_028_non_3d_input_is_rejected(context, tmp_path):
    flat = OCTVolume(
        pixel_array=np.zeros((10, 10), dtype=np.uint16),
        label_array=None,
        patient_id="P1",
        vendor="cirrus",
        spacing_mm=SPACING_MM,
        source_path=tmp_path / "cirrus" / "P1",
    )
    with pytest.raises(ValueError, match="expected a 3-D volume"):
        dw.write_volume(flat, tmp_path / "out", UID_ROOT, context=context)


def test_TC_028_writer_aborts_if_it_leaves_a_mandatory_attribute_unset(
    volume, context, tmp_path, monkeypatch
):
    """Simulates the writer forgetting an attribute the standard requires.

    This is the failure mode SRS-064 exists for: not bad data, but a defect in this
    module. It must abort rather than emit an object claiming conformance it lacks.
    """
    real = dw._top_level_type1

    def with_an_extra_requirement(module_key):
        if module_key == "sop-common":
            return [*real(module_key), "InstitutionalDepartmentName"]
        return real(module_key)

    monkeypatch.setattr(dw, "_top_level_type1", with_an_extra_requirement)
    with pytest.raises(ValueError, match="incomplete against the Ophthalmic Tomography"):
        dw.write_volume(volume, tmp_path / "out", UID_ROOT, context=context)
