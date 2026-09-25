"""Verification of ocuval.io.deident and the spacing guard in ocuval.io.retouch_reader.

Covers TC-030..TC-035 (de-identification) and TC-014, TC-015 (spacing rejection).

DICOM instances are generated with pydicom rather than read from real data: no RETOUCH
volume is needed, nothing in this file touches data/, and every case including the
failure cases can be constructed exactly.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pydicom
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from ocuval.io import deident
from ocuval.io.retouch_reader import (
    MAX_PLAUSIBLE_SPACING_MM,
    spacing_ranges,
    validate_spacing,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

SALT = "test-salt-not-a-real-one"


def make_instance(tmp_path, name="instance.dcm", **overrides):
    """A synthetic OPT instance carrying identifying attributes to be removed."""
    ds = Dataset()
    ds.PatientName = "Yadav^Anurag"
    ds.PatientID = "PID-000123"
    ds.PatientBirthDate = "19900101"
    ds.PatientAddress = "1 Example Street"
    ds.OtherPatientNames = "Anon^Other"
    ds.ReferringPhysicianName = "Referrer^Some"
    ds.InstitutionName = "Example Eye Hospital"
    ds.InstitutionAddress = "2 Example Road"
    ds.OperatorsName = "Operator^One"
    ds.AccessionNumber = "ACC-9999"
    ds.StudyID = "STUDY-1"
    ds.DeviceSerialNumber = "SN-12345"
    ds.PatientComments = "referred by colleague"

    # Must survive.
    ds.Manufacturer = "Topcon"
    ds.ManufacturerModelName = "3D OCT-2000"
    ds.Modality = "OPT"

    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.77.1.5.4"
    ds.SOPInstanceUID = generate_uid()
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()

    for key, value in overrides.items():
        setattr(ds, key, value)

    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    path = tmp_path / name
    ds.save_as(str(path), write_like_original=False)
    return path


# --- pseudonymise: TC-031, TC-032 -------------------------------------------------


def test_TC_032_pseudonym_is_stable_for_one_salt():
    assert deident.pseudonymise("PID-1", SALT) == deident.pseudonymise("PID-1", SALT)


# A pseudonym recorded once, by hand, from the definition in docs/06 section 5:
# sha256("<salt>:<patient id>"), first 16 hex digits uppercased, prefixed "P". If this
# constant and the function ever disagree, every pseudonym issued before the change
# became unreproducible -- which is the failure SRS-014 was reworded on 2026-09-25 to
# forbid. Recomputing it from the function under test would assert nothing.
KNOWN_PSEUDONYM = "OCUVAL-" + hashlib.sha256(f"{SALT}:PID-1".encode()).hexdigest()[:16].upper()


def test_TC_032_pseudonym_matches_an_independently_computed_digest():
    """Cross-run stability, stated as a value rather than as a comparison.

    The other cross-run test proves the function agrees with itself in a fresh process.
    This one proves it agrees with the *definition*, so a change to the derivation is
    caught even if it is deterministic.
    """
    assert deident.pseudonymise("PID-1", SALT) == KNOWN_PSEUDONYM


def test_TC_032_pseudonym_is_stable_across_processes():
    """SRS-014: the same identifier and salt in a separate interpreter, not one run.

    Run in a subprocess deliberately. Within one process a cache, a module-level RNG
    seed or a hash seed would all produce agreement that does not survive a restart,
    and those are exactly the mistakes that make provenance hold only until the process
    exits. PYTHONHASHSEED is set to a different value than the parent's default so that
    a derivation accidentally depending on str.__hash__ cannot pass.
    """
    program = "from ocuval.io import deident;" f"print(deident.pseudonymise('PID-1', {SALT!r}))"
    environment = dict(os.environ, PYTHONHASHSEED="12345")
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )
    assert result.stdout.strip() == deident.pseudonymise("PID-1", SALT)
    assert result.stdout.strip() == KNOWN_PSEUDONYM


def test_TC_031_pseudonym_changes_with_the_salt():
    assert deident.pseudonymise("PID-1", SALT) != deident.pseudonymise("PID-1", "other-salt")


def test_TC_031_different_patients_get_different_pseudonyms():
    assert deident.pseudonymise("PID-1", SALT) != deident.pseudonymise("PID-2", SALT)


def test_TC_031_pseudonym_does_not_contain_the_original_identifier():
    assert "PID-000123" not in deident.pseudonymise("PID-000123", SALT)


def test_TC_031_empty_salt_is_refused():
    """An unsalted hash of a small identifier space is reversible by enumeration."""
    with pytest.raises(ValueError, match="salt"):
        deident.pseudonymise("PID-1", "")


# --- deidentify_instance: TC-030, TC-033, TC-034, TC-035 ---------------------------


def test_TC_030_identifying_attributes_are_removed_or_emptied(tmp_path):
    src = make_instance(tmp_path)
    dst = tmp_path / "out" / "clean.dcm"
    deident.deidentify_instance(src, dst, SALT)

    ds = pydicom.dcmread(str(dst))
    for keyword, action in deident.PROFILE.items():
        if action is deident.Action.REMOVE:
            assert keyword not in ds, f"{keyword} survived removal"
        elif action is deident.Action.EMPTY and keyword in ds:
            assert str(getattr(ds, keyword)) == ""


def test_TC_030_patient_identifiers_are_replaced_with_pseudonyms(tmp_path):
    src = make_instance(tmp_path)
    dst = tmp_path / "clean.dcm"
    deident.deidentify_instance(src, dst, SALT)

    ds = pydicom.dcmread(str(dst))
    assert str(ds.PatientID) == deident.pseudonymise("PID-000123", SALT)
    assert "Yadav" not in str(ds.PatientName)


def test_TC_030_instance_declares_that_identity_was_removed(tmp_path):
    src = make_instance(tmp_path)
    dst = tmp_path / "clean.dcm"
    deident.deidentify_instance(src, dst, SALT)
    assert pydicom.dcmread(str(dst)).PatientIdentityRemoved == "YES"


def test_TC_032_pseudonyms_are_stable_across_instances_in_one_run(tmp_path):
    a = make_instance(tmp_path, name="a.dcm")
    b = make_instance(tmp_path, name="b.dcm")
    deident.deidentify_instance(a, tmp_path / "a-out.dcm", SALT)
    deident.deidentify_instance(b, tmp_path / "b-out.dcm", SALT)
    first = pydicom.dcmread(str(tmp_path / "a-out.dcm")).PatientID
    second = pydicom.dcmread(str(tmp_path / "b-out.dcm")).PatientID
    assert first == second


def test_TC_035_vendor_survives_de_identification(tmp_path):
    src = make_instance(tmp_path)
    dst = tmp_path / "clean.dcm"
    deident.deidentify_instance(src, dst, SALT)

    ds = pydicom.dcmread(str(dst))
    assert ds.Manufacturer == "Topcon"
    assert ds.ManufacturerModelName == "3D OCT-2000"
    assert ds.Modality == "OPT"


def test_TC_035_must_survive_list_is_disjoint_from_the_profile():
    """A keyword in both tables would remove the vendor and pass every other test."""
    assert not set(deident.MUST_SURVIVE) & set(deident.PROFILE)


def test_TC_033_verification_passes_a_clean_instance(tmp_path):
    src = make_instance(tmp_path)
    dst = tmp_path / "clean.dcm"
    deident.deidentify_instance(src, dst, SALT)
    assert deident.verify_deidentified(dst) == []


def test_TC_033_verification_reports_a_residual_identifier(tmp_path):
    src = make_instance(tmp_path)
    dst = tmp_path / "clean.dcm"
    deident.deidentify_instance(src, dst, SALT)

    doctored = pydicom.dcmread(str(dst))
    doctored.PatientAddress = "1 Example Street"  # put an identifier back
    doctored.save_as(str(dst))

    assert "PatientAddress" in deident.verify_deidentified(dst)


def test_TC_033_verification_reports_an_unemptied_attribute(tmp_path):
    src = make_instance(tmp_path)
    dst = tmp_path / "clean.dcm"
    deident.deidentify_instance(src, dst, SALT)

    doctored = pydicom.dcmread(str(dst))
    doctored.AccessionNumber = "ACC-9999"
    doctored.save_as(str(dst))

    assert "AccessionNumber" in deident.verify_deidentified(dst)


def test_TC_033_verification_reports_an_untouched_instance(tmp_path):
    """The failure case that matters: the profile was never applied at all."""
    src = make_instance(tmp_path)
    offending = deident.verify_deidentified(src)
    assert "PatientIdentityRemoved" in offending
    assert len(offending) > 5


def test_TC_034_non_empty_verification_is_the_only_failing_condition(tmp_path):
    """SRS-015: an empty list is the only condition under which an instance passes."""
    src = make_instance(tmp_path)
    dst = tmp_path / "clean.dcm"
    deident.deidentify_instance(src, dst, SALT)
    result = deident.verify_deidentified(dst)
    assert isinstance(result, list) and result == []


def test_TC_035_losing_a_must_survive_attribute_aborts(tmp_path, monkeypatch):
    """Simulates a profile table widened until it removes the vendor."""
    monkeypatch.setitem(deident.PROFILE, "Manufacturer", deident.Action.REMOVE)
    src = make_instance(tmp_path)
    with pytest.raises(ValueError, match="must survive"):
        deident.deidentify_instance(src, tmp_path / "clean.dcm", SALT)


def test_TC_030_profile_keywords_all_resolve_to_real_dicom_tags():
    """The reason the table is keyed by keyword: an invented attribute cannot survive."""
    from pydicom.datadict import tag_for_keyword

    for keyword in (*deident.PROFILE, *deident.MUST_SURVIVE):
        assert tag_for_keyword(keyword) is not None, keyword


# --- spacing rejection: TC-014, TC-015 --------------------------------------------


def test_TC_015_valid_anisotropic_spacing_is_accepted():
    validate_spacing((0.0039, 0.0117, 0.047))


def test_TC_014_absent_spacing_is_rejected_with_no_default():
    with pytest.raises(ValueError, match="absent and no default"):
        validate_spacing(None)


def test_TC_015_micrometre_valued_spacing_is_rejected():
    """The 1000x error: 3.9 is the micrometre value of 0.0039 mm."""
    with pytest.raises(ValueError, match="micrometres were read as millimetres"):
        validate_spacing((3.9, 11.7, 47.0))


def test_TC_015_single_micrometre_valued_component_is_rejected():
    """Only the axial component mis-scaled — the harder, more likely case."""
    with pytest.raises(ValueError, match="physical limit"):
        validate_spacing((3.9, 0.0117, 0.047))


@pytest.mark.parametrize(
    ("spacing", "match"),
    [
        ((0.0, 0.0117, 0.047), "must be positive"),
        ((-0.0039, 0.0117, 0.047), "must be positive"),
        ((float("nan"), 0.0117, 0.047), "not finite"),
        ((float("inf"), 0.0117, 0.047), "not finite"),
        ((0.0039, 0.0117), "three components"),
        ((0.0039, 0.0117, 0.047, 0.1), "three components"),
        ((0.005, 0.005, 0.005), "isotropic"),
        (("0.0039", 0.0117, 0.047), "not numeric"),
    ],
)
def test_TC_015_unusable_spacing_is_rejected(spacing, match):
    with pytest.raises(ValueError, match=match):
        validate_spacing(spacing)


def test_TC_015_rejection_names_the_component_and_the_source():
    with pytest.raises(ValueError) as excinfo:
        validate_spacing((3.9, 0.0117, 0.047), source="cirrus/TRAIN001")
    message = str(excinfo.value)
    assert "cirrus/TRAIN001" in message
    assert "component 0" in message


def test_TC_015_the_bound_is_far_above_any_real_oct_spacing():
    """Guards the guard: the limit must not be so tight it rejects real acquisitions."""
    assert MAX_PLAUSIBLE_SPACING_MM > 0.25  # coarsest plausible B-scan separation
    assert MAX_PLAUSIBLE_SPACING_MM < 3.9  # and still rejects the micrometre case


# --- per-vendor spacing ranges: TC-015 (docs/07 item 6, closed 2026-09-25) ---------
#
# Spacings below are real, taken from the RETOUCH training partition. They are written
# in this project's (axial, lateral, separation) order, so a test that transposes them
# is testing the thing docs/07 section 3 rule 7 warns about.

REAL_SPACING = {
    "cirrus": (0.001955, 0.011742, 0.046878),
    "spectralis": (0.003872, 0.010856, 0.116380),
    "topcon": (0.002600, 0.011720, 0.046880),
}


@pytest.mark.parametrize("vendor", sorted(REAL_SPACING))
def test_TC_015_measured_spacing_is_accepted_for_its_own_vendor(vendor):
    validate_spacing(REAL_SPACING[vendor], vendor=vendor, source=f"{vendor}/real")


@pytest.mark.parametrize("vendor", sorted(REAL_SPACING))
def test_TC_015_axis_transposition_is_rejected_by_the_per_vendor_range(vendor):
    """The defect the outer bound cannot see.

    A transposed axial/lateral pair is physically small in every component, so the
    0.5 mm bound accepts it and the resulting volume in mm3 is wrong by a factor of
    roughly six with nothing visible in the mask or on a review screen. That is HAZ-012,
    and the per-vendor range is the only control in the pipeline that catches it.
    """
    axial, lateral, separation = REAL_SPACING[vendor]
    transposed = (lateral, axial, separation)

    validate_spacing(transposed, source="outer bound alone")  # no vendor: accepted

    with pytest.raises(ValueError, match="outside the measured range"):
        validate_spacing(transposed, vendor=vendor, source=f"{vendor}/transposed")


@pytest.mark.parametrize("vendor", sorted(REAL_SPACING))
def test_TC_015_full_metaimage_axis_reversal_is_rejected(vendor):
    """The specific wrong conversion spacing_from_header exists to prevent."""
    axial, lateral, separation = REAL_SPACING[vendor]
    with pytest.raises(ValueError, match="outside the measured range"):
        validate_spacing((separation, lateral, axial), vendor=vendor, source=vendor)


def test_TC_015_an_unmeasured_vendor_falls_back_to_the_physical_bound():
    """Not an error: the physical bound still applied, and refusing every new vendor
    would fail for a reason about our measurements rather than about the acquisition."""
    validate_spacing((0.0039, 0.0117, 0.047), vendor="nidek", source="unmeasured")
    with pytest.raises(ValueError, match="physical limit"):
        validate_spacing((3.9, 0.0117, 0.047), vendor="nidek", source="unmeasured")


def test_TC_015_per_vendor_rejection_names_vendor_axis_and_range():
    with pytest.raises(ValueError) as excinfo:
        validate_spacing((0.011742, 0.001955, 0.046878), vendor="cirrus", source="cirrus/T1")
    message = str(excinfo.value)
    assert "cirrus/T1" in message
    assert "axial" in message
    assert "cirrus" in message
    assert "0.000978" in message and "0.00391" in message


def test_TC_015_ranges_are_declared_in_millimetres():
    """The units are read, not assumed: a config in micrometres must not be silently
    reinterpreted, which is the same 1000x error the physical bound exists to catch."""
    import yaml

    block = yaml.safe_load((REPO_ROOT / "configs" / "data.yaml").read_text(encoding="utf-8"))[
        "spacing_plausibility"
    ]
    assert block["units"] == "mm"
    assert block["max_any_component_mm"] == MAX_PLAUSIBLE_SPACING_MM


def test_TC_015_every_configured_vendor_has_all_three_components():
    for vendor, axes in spacing_ranges().items():
        assert set(axes) == {"axial", "lateral", "separation"}, vendor
        for axis, (low, high) in axes.items():
            assert 0 < low < high <= MAX_PLAUSIBLE_SPACING_MM, (vendor, axis)


def test_TC_015_configured_vendors_match_the_configured_vendor_list():
    """A vendor with no range silently falls back to the physical bound, so the two
    lists drifting apart would weaken the guard without any test failing."""
    import yaml

    config = yaml.safe_load((REPO_ROOT / "configs" / "data.yaml").read_text(encoding="utf-8"))
    assert set(spacing_ranges()) == set(config["vendors"])
