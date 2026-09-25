"""Verification of ocuval.io.metaimage and ocuval.io.retouch_reader.

Covers TC-010..TC-013, TC-016 (data ingestion) and TC-017 (MetaImage format handling).
TC-018, which checks the real archive against docs/06, is marked `requires_data` and
lives at the end of this file.

Everything except TC-018 runs on synthetic .mhd/.raw fixtures written by this module, so
the format handling is verified against the specification rather than against whatever
one vendor's export happens to contain.
"""

from __future__ import annotations

import numpy as np
import pytest

from ocuval.io import metaimage as mi
from ocuval.io import retouch_reader as rr

# (x, y, z) as MetaImage orders them: lateral, axial, B-scan separation.
HEADER_SPACING = (0.011742, 0.001955, 0.046878)
# What OCTVolume must carry: axial, lateral, separation.
EXPECTED_SPACING = (0.001955, 0.011742, 0.046878)


def write_volume_files(
    directory,
    *,
    dims=(8, 6, 4),  # x, y, z
    spacing=HEADER_SPACING,
    element_type="MET_UCHAR",
    stem="oct",
    labels=False,
    extra=None,
    truncate=0,
):
    """Write a synthetic MetaImage pair and return its header path."""
    directory.mkdir(parents=True, exist_ok=True)
    dtype = mi.ELEMENT_TYPES[element_type]
    n = dims[0] * dims[1] * dims[2]
    if labels:
        payload = np.tile(np.array([0, 1, 2, 3], dtype=dtype), n // 4 + 1)[:n]
    else:
        payload = np.arange(n, dtype=np.int64).astype(dtype)
    raw = directory / f"{stem}.raw"
    data = payload.tobytes()
    raw.write_bytes(data[: len(data) - truncate] if truncate else data)

    lines = [
        "ObjectType = Image",
        "NDims = 3",
        "BinaryData = True",
        "BinaryDataByteOrderMSB = False",
        "CompressedData = False",
        f"ElementSpacing = {spacing[0]} {spacing[1]} {spacing[2]}",
        f"DimSize = {dims[0]} {dims[1]} {dims[2]}",
        "ElementNumberOfChannels = 1",
        f"ElementType = {element_type}",
        f"ElementDataFile = {stem}.raw",
    ]
    if extra:
        lines += extra
    header = directory / f"{stem}.mhd"
    header.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return header


@pytest.fixture
def subject(tmp_path):
    d = tmp_path / "TRAIN001"
    write_volume_files(d, stem="oct")
    write_volume_files(d, stem="reference", labels=True)
    return d


# --- TC-017: MetaImage format handling --------------------------------------------


def test_TC_017_dim_size_is_reversed_into_slices_rows_columns(tmp_path):
    """DimSize is (x, y, z); the array must be (z, y, x).

    Getting this backwards yields an array of the right size and the wrong content,
    which no size check can catch.
    """
    header = write_volume_files(tmp_path / "v", dims=(8, 6, 4))
    assert mi.read_volume_array(header).shape == (4, 6, 8)


def test_TC_017_element_type_is_honoured_not_assumed(tmp_path):
    for element_type, expected in (("MET_UCHAR", "uint8"), ("MET_USHORT", "uint16")):
        header = write_volume_files(tmp_path / element_type, element_type=element_type)
        assert str(mi.read_volume_array(header).dtype) == expected


def test_TC_017_unknown_element_type_raises_rather_than_guessing(tmp_path):
    header = write_volume_files(tmp_path / "v")
    header.write_text(
        header.read_text(encoding="utf-8").replace("MET_UCHAR", "MET_WIDGET"), encoding="utf-8"
    )
    with pytest.raises(mi.MetaImageError, match="unsupported ElementType"):
        mi.parse_header(header)


def test_TC_017_truncated_payload_raises(tmp_path):
    """A short file is a truncated download; returning what was read hands back a
    volume that is partly another volume."""
    header = write_volume_files(tmp_path / "v", truncate=16)
    with pytest.raises(mi.MetaImageError, match="truncated or does not match"):
        mi.read_volume_array(header)


def test_TC_017_compressed_data_is_refused(tmp_path):
    header = write_volume_files(tmp_path / "v")
    header.write_text(
        header.read_text(encoding="utf-8").replace(
            "CompressedData = False", "CompressedData = True"
        ),
        encoding="utf-8",
    )
    with pytest.raises(mi.MetaImageError, match="does not decompress"):
        mi.parse_header(header)


def test_TC_017_non_3d_volume_is_refused(tmp_path):
    header = write_volume_files(tmp_path / "v")
    header.write_text(
        header.read_text(encoding="utf-8").replace("NDims = 3", "NDims = 2"), encoding="utf-8"
    )
    with pytest.raises(mi.MetaImageError, match="3-D volumes only"):
        mi.parse_header(header)


def test_TC_017_missing_header_raises(tmp_path):
    with pytest.raises(mi.MetaImageError, match="no such header file"):
        mi.parse_header(tmp_path / "absent.mhd")


def test_TC_017_missing_raw_file_raises(tmp_path):
    header = write_volume_files(tmp_path / "v")
    (tmp_path / "v" / "oct.raw").unlink()
    with pytest.raises(mi.MetaImageError, match="not found"):
        mi.read_volume_array(header)


# --- TC-011: the spacing reorder, which is the dangerous line ----------------------


def test_TC_011_spacing_is_reordered_from_header_order(tmp_path):
    """MetaImage (lateral, axial, sep) -> OCTVolume (axial, lateral, sep)."""
    header = mi.parse_header(write_volume_files(tmp_path / "v", spacing=HEADER_SPACING))
    assert rr.spacing_from_header(header) == EXPECTED_SPACING


def test_TC_011_reorder_is_not_the_identity(tmp_path):
    """Guards the guard: a fixture whose first two components matched would pass a
    broken implementation."""
    header = mi.parse_header(write_volume_files(tmp_path / "v", spacing=HEADER_SPACING))
    assert rr.spacing_from_header(header) != header.element_spacing


def test_TC_011_axial_is_the_finest_component_after_reorder(tmp_path):
    """In real OCT the axial sampling is finest; if the reorder were wrong this fails."""
    header = mi.parse_header(write_volume_files(tmp_path / "v", spacing=HEADER_SPACING))
    axial, lateral, separation = rr.spacing_from_header(header)
    assert axial < lateral < separation


def test_TC_011_anisotropy_survives_reading(subject):
    volume = rr.read_volume(subject, "cirrus")
    assert len(set(volume.spacing_mm)) == 3


# --- TC-010, TC-016: the record the reader returns --------------------------------


def test_TC_010_reader_returns_a_complete_record(subject):
    volume = rr.read_volume(subject, "cirrus")
    assert volume.pixel_array.shape == (4, 6, 8)
    assert volume.label_array.shape == (4, 6, 8)
    assert volume.patient_id == "TRAIN001"
    assert volume.vendor == "cirrus"
    assert volume.spacing_mm == EXPECTED_SPACING
    assert volume.source_path == subject


def test_TC_010_patient_id_comes_from_the_directory_name(subject):
    assert rr.read_volume(subject, "cirrus").patient_id == subject.name


def test_TC_016_spacing_is_validated_during_reading(tmp_path):
    """An implausible spacing must be refused at ingestion, not carried downstream."""
    d = tmp_path / "TRAIN002"
    write_volume_files(d, stem="oct", spacing=(0.0117, 3.9, 0.0469))  # axial in micrometres
    with pytest.raises(ValueError, match="physical limit"):
        rr.read_volume(d, "cirrus")


def test_TC_010_absent_reference_yields_none_not_an_empty_array(tmp_path):
    d = tmp_path / "TRAIN003"
    write_volume_files(d, stem="oct")
    volume = rr.read_volume(d, "topcon")
    assert volume.label_array is None


def test_TC_010_label_outside_the_frozen_set_is_refused(tmp_path):
    d = tmp_path / "TRAIN004"
    write_volume_files(d, stem="oct")
    header = write_volume_files(d, stem="reference", labels=True)
    raw = d / "reference.raw"
    data = bytearray(raw.read_bytes())
    data[0] = 7  # a label configs/data.yaml does not define
    raw.write_bytes(bytes(data))
    assert header.exists()
    with pytest.raises(ValueError, match="outside the frozen set"):
        rr.read_volume(d, "topcon")


def test_TC_012_reference_disagreeing_with_its_image_is_refused(tmp_path):
    d = tmp_path / "TRAIN005"
    write_volume_files(d, stem="oct", dims=(8, 6, 4))
    write_volume_files(d, stem="reference", dims=(8, 6, 8), labels=True)
    with pytest.raises(ValueError, match="disagree on DimSize"):
        rr.read_volume(d, "cirrus")


def test_TC_012_reference_with_different_spacing_is_refused(tmp_path):
    d = tmp_path / "TRAIN006"
    write_volume_files(d, stem="oct", spacing=HEADER_SPACING)
    write_volume_files(d, stem="reference", spacing=(0.02, 0.002, 0.05), labels=True)
    with pytest.raises(ValueError, match="disagree on ElementSpacing"):
        rr.read_volume(d, "cirrus")


def test_TC_012_missing_directory_names_the_path(tmp_path):
    missing = tmp_path / "TRAIN999"
    with pytest.raises(ValueError, match=str(missing.name)):
        rr.read_volume(missing, "cirrus")


# --- TC-013: layout knowledge stays in this module --------------------------------


def test_TC_013_unknown_vendor_is_refused(tmp_path):
    with pytest.raises(ValueError, match="unknown vendor"):
        rr.subject_directories(tmp_path, "nidek")


def test_TC_013_missing_vendor_directory_names_it(tmp_path):
    with pytest.raises(ValueError, match="vendor directory not found"):
        rr.subject_directories(tmp_path, "cirrus")


def test_TC_013_ambiguous_release_directory_is_refused(tmp_path):
    outer = tmp_path / rr.VENDOR_DIRECTORIES["cirrus"]
    (outer / "ReleaseA").mkdir(parents=True)
    (outer / "ReleaseB").mkdir(parents=True)
    with pytest.raises(ValueError, match="expected exactly one release directory"):
        rr.subject_directories(tmp_path, "cirrus")


def test_TC_013_subject_directories_are_sorted(tmp_path):
    inner = tmp_path / rr.VENDOR_DIRECTORIES["topcon"] / "RETOUCH-TrainingSet-Topcon"
    for name in ("TRAIN070", "TRAIN049", "TRAIN055"):
        (inner / name).mkdir(parents=True)
    found = [d.name for d in rr.subject_directories(tmp_path, "topcon")]
    assert found == ["TRAIN049", "TRAIN055", "TRAIN070"]


def test_TC_013_only_this_module_knows_the_archive_layout():
    """SRS-005: the RETOUCH directory names appear here and nowhere else in src/."""
    import subprocess

    out = subprocess.run(
        ["git", "grep", "-l", "TrainingCirrus", "--", "src"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    assert out == ["src/ocuval/io/retouch_reader.py"], out


# --- TC-018: the real archive, against what docs/06 claims ------------------------


@pytest.mark.requires_data
class TestArchiveMatchesDocumentation:
    """Regression guard on the figures docs/06 section 3 records.

    These were measured on 2026-09-23 and several superseded literature-derived values.
    If the archive is ever re-downloaded or re-extracted, this is what catches a change.
    """

    ROOT = "data/raw/retouch"

    def test_TC_018_subject_counts_match_docs_06(self):
        from pathlib import Path

        counts = {v: len(rr.subject_directories(Path(self.ROOT), v)) for v in rr.VENDOR_DIRECTORIES}
        assert counts == {"cirrus": 24, "spectralis": 24, "topcon": 22}

    def test_TC_018_subject_ids_are_unique_across_vendors(self):
        from pathlib import Path

        seen = []
        for vendor in rr.VENDOR_DIRECTORIES:
            seen += [d.name for d in rr.subject_directories(Path(self.ROOT), vendor)]
        assert len(seen) == len(set(seen)) == 70

    def test_TC_018_element_types_match_docs_06(self):
        from pathlib import Path

        expected = {"cirrus": "uint8", "spectralis": "uint16", "topcon": "uint8"}
        for vendor, dtype in expected.items():
            first = rr.subject_directories(Path(self.ROOT), vendor)[0]
            assert str(rr.read_volume(first, vendor).pixel_array.dtype) == dtype

    def test_TC_018_every_volume_passes_the_spacing_guard(self):
        from pathlib import Path

        from ocuval.io.metaimage import parse_header

        for vendor in rr.VENDOR_DIRECTORIES:
            for subj in rr.subject_directories(Path(self.ROOT), vendor):
                spacing = rr.spacing_from_header(parse_header(subj / "oct.mhd"))
                rr.validate_spacing(spacing, source=str(subj))


# --- TC-049: the two paths must not diverge -----------------------------------------
#
# Training reads the archive's native MetaImage; results are reported against the DICOM
# instance. Two paths now exist for one acquisition, and nothing else checks that they
# still describe the same thing. That is HAZ-004's shape: a real value attached to the
# wrong acquisition. The failure would surface as a misaligned SEG overlaid on a study,
# long after the run that produced it, and by then the run is what would be doubted.
#
# This compares the written instance against the source it was written from, rather than
# re-deriving both from one reader -- comparing a reader to itself would pass whatever
# the writer did.


@pytest.mark.requires_data
def test_TC_049_dicom_and_metaimage_agree_for_a_sample_per_vendor():
    from pathlib import Path

    import numpy as np
    import pydicom
    import yaml

    from ocuval.io.retouch_reader import read_volume, subject_directories

    config = yaml.safe_load(Path("configs/data.yaml").read_text(encoding="utf-8"))
    raw_root = Path(config["paths"]["raw_root"])
    dicom_root = Path(config["paths"]["dicom_root"])
    if not dicom_root.is_dir():
        pytest.skip(f"{dicom_root} not present; run the conversion stage first")

    checked = 0
    for vendor in config["vendors"]:
        instances = sorted((dicom_root / vendor).glob("*.dcm"))
        directories = subject_directories(raw_root, vendor)
        if not instances or not directories:
            pytest.skip(f"no converted instances for {vendor}")

        # Match by patient identifier rather than by position: a positional match would
        # pass even if conversion had reordered the subjects, which is the error most
        # likely to attach a result to the wrong acquisition.
        by_patient = {}
        for path in instances:
            header = pydicom.dcmread(str(path), stop_before_pixels=True)
            by_patient[str(header.PatientID)] = path

        directory = directories[0]
        volume = read_volume(directory, vendor)
        path = by_patient.get(volume.patient_id)
        if path is None:
            pytest.skip(
                f"{vendor}/{volume.patient_id} has no instance under its own identifier "
                f"(the converted tree may be de-identified; compare against dicom_root)"
            )

        dataset = pydicom.dcmread(str(path))
        pixels = dataset.pixel_array

        assert pixels.shape == volume.pixel_array.shape, (
            f"{vendor}/{volume.patient_id}: DICOM shape {pixels.shape} against MetaImage "
            f"{volume.pixel_array.shape}. SRS-010 forbids resampling during conversion."
        )
        assert pixels.dtype == volume.pixel_array.dtype, (
            f"{vendor}/{volume.patient_id}: DICOM dtype {pixels.dtype} against MetaImage "
            f"{volume.pixel_array.dtype}. SRS-066 requires the element type carried, not cast."
        )
        assert np.array_equal(pixels, volume.pixel_array), (
            f"{vendor}/{volume.patient_id}: pixel data differs between the written "
            f"instance and the source it was written from. Training reads one and "
            f"results are reported against the other (HAZ-004)."
        )

        measures = dataset.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
        # PixelSpacing is [row, column] = [axial, lateral]; B-scan separation is carried
        # as SliceThickness, per the writer's reading of Table A.52.4.3-1.
        axial, lateral = (float(v) for v in measures.PixelSpacing)
        separation = float(measures.SliceThickness)
        assert (axial, lateral, separation) == volume.spacing_mm, (
            f"{vendor}/{volume.patient_id}: DICOM spacing "
            f"{(axial, lateral, separation)} against MetaImage {volume.spacing_mm}. "
            f"SRS-054 requires spacing to survive conversion unchanged."
        )
        checked += 1

    assert checked == len(config["vendors"]), f"only {checked} vendors checked"
