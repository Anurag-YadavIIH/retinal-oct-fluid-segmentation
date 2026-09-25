"""Write OCT volumes as DICOM Ophthalmic Tomography Image objects.

Traces to: SRS-006, SRS-007, SRS-008, SRS-009, SRS-010, SRS-011, SRS-054, SRS-062,
SRS-063, SRS-064 (DICOM conversion)
Implements risk control: RC-008, RC-015, RC-016, RC-021, RC-029 (HAZ-012, HAZ-015)

Uses pydicom. **highdicom has no constructor for this IOD** — its purpose-built classes
cover Segmentation, SR, parametric maps, annotations and secondary capture, not
Ophthalmic Tomography — so this module assembles the dataset directly. That makes it the
highest invention risk in the project, and it is why `validate_against_iod` exists:
highdicom *does* ship module and attribute tables generated from PS3.3, so the object we
build is checked against the standard's own requirements rather than against this
module's memory of them. Turning "did I remember the IOD correctly" into a check rather
than a hope is the whole point (SRS-064, TC-028).

**What RETOUCH cannot supply.** The Ophthalmic Tomography Image IOD assumes a real
acquisition on a real device with a fundus reference image. RETOUCH is a converted
archive with that context stripped, so several mandatory attributes have no source
value — image laterality above all (Type 1, enumerated R/L/B, no empty and no unknown
permitted). The rule here is **refuse, or omit — never fill** (RC-029):

1. By default the caller must supply the missing context and conversion aborts without
   it (SRS-062).
2. Under an explicitly enabled research exception, the affected attribute is omitted,
   the omission logged and recorded, and never populated with a substitute (SRS-063).

The reasoning, recorded in docs/11 §10 item 3: a detectable non-conformance is safer
than an undetectable fabrication. A missing Type 1 attribute is flagged by any
validator; an invented laterality is read downstream as a recorded anatomical fact, and
DICOM offers no way to mark a value provisional.

Established against the normative text (PS3.3): IOD module table A.52.3-1, Ocular Region
Imaged C.8.17.5, functional group macro usages A.52.4.3-1. Ophthalmic Frame Location is
usage U and is omitted with no conformance consequence.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pydicom
from highdicom import _iods, _modules
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian
from pydicom.uid import generate_uid as _pydicom_generate_uid

from ocuval.io.retouch_reader import OCTVolume, validate_spacing

logger = logging.getLogger(__name__)

# Ophthalmic Tomography Image Storage. Mirrors configs/data.yaml dicom.sop_class; the
# config is authoritative and callers pass it in, this is the cross-check.
OPT_SOP_CLASS_UID = "1.2.840.10008.5.1.4.1.1.77.1.5.4"

IOD_KEY = "ophthalmic-tomography-image"

# Mandatory attributes the source cannot supply, by module. Omitting one produces a
# declared non-conformance (docs/11 §10 item 3); filling one produces HAZ-015.
#
# Keyed per attribute rather than per module, because the problem is not module shaped:
# AcquisitionDateTime sits in a module that also carries the pixel description, so that
# module cannot be dropped whole. It was found by validate_against_iod rather than by
# reading the standard, which is the check earning its place.
UNPOPULATABLE: dict[str, tuple[str, ...]] = {
    # Type 1, enumerated R/L/B, no unknown member. RETOUCH records no laterality.
    "ocular-region-imaged": ("ImageLaterality", "AnatomicRegionSequence"),
    # Type 1. These describe the scanner, which RETOUCH identifies only by vendor.
    # DeviceSerialNumber is also removed by the confidentiality profile.
    "enhanced-general-equipment": ("ManufacturerModelName", "DeviceSerialNumber"),
    # Type 1, unconditional. RETOUCH records no acquisition date or time, and the
    # conversion time is a different fact wearing the same name.
    "ophthalmic-tomography-image": ("AcquisitionDateTime",),
}

# Enumerated Values for ImageLaterality in PS3.3 C.8.17.5. There is no unknown member:
# that absence is the whole problem, and is why the writer refuses rather than guessing.
LATERALITY_VALUES = ("R", "L", "B")


class AcquisitionContextError(ValueError):
    """Raised when context the source cannot supply was not supplied by the caller."""


@dataclass(frozen=True)
class AcquisitionContext:
    """Facts about the acquisition that RETOUCH does not record.

    Every field here exists because the IOD requires it and the dataset lacks it. None
    has a default: a default would be exactly the fabrication RC-029 forbids.
    """

    laterality: str
    anatomic_region: Dataset | None = None
    manufacturer_model_name: str | None = None
    device_serial_number: str | None = None
    acquisition_datetime: str | None = None

    def __post_init__(self) -> None:
        if self.laterality not in LATERALITY_VALUES:
            raise AcquisitionContextError(
                f"laterality must be one of {LATERALITY_VALUES} (PS3.3 C.8.17.5, Type 1); "
                f"got {self.laterality!r}. There is no unknown value — if the source does "
                f"not record laterality, enable the research exception so the module is "
                f"omitted rather than invented."
            )


@dataclass(frozen=True)
class WriteResult:
    """What a conversion produced, including what it declined to produce.

    `omissions` is recorded rather than logged only, so it reaches the run output and any
    later report (SRS-063). Each entry is "module.Attribute".
    """

    paths: list[Path]
    sop_instance_uids: list[str]
    study_instance_uid: str
    series_instance_uid: str
    frame_of_reference_uid: str = ""
    omissions: list[str] = field(default_factory=list)


def generate_uid(uid_root: str) -> str:
    """Generate a UID under the project's configured root.

    The root is a declared placeholder and is not registered (docs/06 §7.1), so UIDs
    from here are structurally valid and carry no claim of global uniqueness. Objects
    must not leave the local Orthanc instance.
    """
    if not uid_root:
        raise ValueError("a UID root is required; no default exists")
    prefix = uid_root if uid_root.endswith(".") else uid_root + "."
    return _pydicom_generate_uid(prefix=prefix)


def required_modules() -> list[str]:
    """Mandatory modules of the OPT IOD, from highdicom's PS3.3-derived table."""
    return [m["key"] for m in _iods.IOD_MODULE_MAP[IOD_KEY] if m["usage"] == "M"]


def _top_level_type1(module_key: str) -> list[str]:
    return [
        a["keyword"]
        for a in _modules.MODULE_ATTRIBUTE_MAP[module_key]
        if not a["path"] and a["type"] == "1"
    ]


def validate_against_iod(
    dataset: Dataset, *, permitted_omissions: tuple[str, ...] = ()
) -> list[str]:
    """Return the mandatory attributes missing from `dataset`, module by module.

    Checked against highdicom's module and attribute tables, which are generated from
    PS3.3 — so this verifies the object against the standard rather than against this
    module's own idea of the standard (SRS-064).

    **Limit, stated rather than implied:** only top-level Type 1 attributes of mandatory
    modules are checked. Type 1 attributes nested inside sequences, and conditional
    (Type 1C/2C) attributes whose conditions are met, are not. This is a floor on
    conformance, not a certificate of it.
    """
    missing: list[str] = []
    for module_key in required_modules():
        for keyword in _top_level_type1(module_key):
            name = f"{module_key}.{keyword}"
            if name in permitted_omissions:
                continue
            value = getattr(dataset, keyword, None)
            if value is None or (isinstance(value, str) and value == ""):
                missing.append(name)
    return sorted(missing)


def _supplied(context: AcquisitionContext | None) -> dict[str, bool]:
    """Which unpopulatable mandatory attributes the caller has actually supplied."""
    if context is None:
        return {
            f"{module}.{attr}": False for module, attrs in UNPOPULATABLE.items() for attr in attrs
        }
    return {
        # Laterality is required by AcquisitionContext itself, so a context implies it.
        "ocular-region-imaged.ImageLaterality": True,
        "ocular-region-imaged.AnatomicRegionSequence": context.anatomic_region is not None,
        "enhanced-general-equipment.ManufacturerModelName": (
            context.manufacturer_model_name is not None
        ),
        "enhanced-general-equipment.DeviceSerialNumber": (context.device_serial_number is not None),
        "ophthalmic-tomography-image.AcquisitionDateTime": (
            context.acquisition_datetime is not None
        ),
    }


def _resolve_omissions(context: AcquisitionContext | None, research_exception: bool) -> list[str]:
    """Decide which mandatory attributes are omitted, or refuse (SRS-062, SRS-063)."""
    unsatisfiable = sorted(k for k, ok in _supplied(context).items() if not ok)
    if not unsatisfiable:
        return []

    if not research_exception:
        raise AcquisitionContextError(
            f"cannot write a conformant object: {unsatisfiable} are mandatory (Type 1) "
            f"and the source does not record them. Supply them via AcquisitionContext, "
            f"or enable the research exception to omit them — the writer will not invent "
            f"values for them (docs/05 RC-029, docs/11 §10 item 3)."
        )

    for name in unsatisfiable:
        logger.warning(
            "research exception: omitting mandatory attribute %r. The object is "
            "non-conformant in this respect by design; see docs/11 §10 item 3.",
            name,
        )
    return unsatisfiable


#: Unsigned integer depths this IOD permits, mapped to Bits Allocated. PS3.3 C.8.17.7
#: enumerates 8 and 16 for Bits Allocated and fixes Pixel Representation at 0, so a
#: signed or wider array cannot be written without a conversion the caller must choose.
PERMITTED_PIXEL_DTYPES: dict[str, int] = {"uint8": 8, "uint16": 16}


def _bit_depth(pixels: np.ndarray) -> int:
    """Bits Allocated for a pixel array, from its dtype.

    Refuses anything outside the IOD's enumerated values rather than casting into them.
    A float or signed array reaching here means an earlier stage changed the data, and
    silently narrowing it would hide that.
    """
    name = str(pixels.dtype)
    if name not in PERMITTED_PIXEL_DTYPES:
        raise ValueError(
            f"pixel dtype {name} cannot be written to this IOD: PS3.3 C.8.17.7 enumerates "
            f"Bits Allocated as 8 or 16 with Pixel Representation 0, so only "
            f"{sorted(PERMITTED_PIXEL_DTYPES)} are writable. Convert deliberately upstream "
            f"if that is intended."
        )
    return PERMITTED_PIXEL_DTYPES[name]


def _pixel_measures(volume: OCTVolume) -> Dataset:
    """Pixel Measures functional group — where spacing lives for this IOD.

    Usage M in Table A.52.4.3-1. Spacing is **not** a top-level PixelSpacing element for
    a multi-frame IOD; it sits in this macro inside the Shared Functional Groups
    Sequence.

    Axis convention, stated because getting it backwards is HAZ-012 with no visible
    symptom: `volume.pixel_array` is (n_bscans, rows, columns) and `spacing_mm` is
    (axial, lateral, b-scan separation). Within a frame the rows run axially and the
    columns laterally, so PixelSpacing is [axial, lateral] — row spacing first, per
    PS3.3 — and SliceThickness is the separation between B-scans.
    """
    axial, lateral, bscan_separation = volume.spacing_mm
    measures = Dataset()
    measures.PixelSpacing = [float(axial), float(lateral)]
    measures.SliceThickness = float(bscan_separation)
    return measures


def _shared_functional_groups(volume: OCTVolume) -> Dataset:
    """Shared groups: Pixel Measures (usage M) and Plane Orientation (usage C, required).

    Plane Orientation and Plane Position are usage C in Table A.52.4.3-1, "Required if
    **no** Ophthalmic Photography Reference Image is available" — which is our case, so
    both are required rather than optional.

    **Why these are populated while laterality is not.** The values are expressed in the
    frame of reference this object declares for itself (`FrameOfReferenceUID`, minted
    above). Within that frame the row and column directions and the frame positions are
    not estimates of anything — they are the definition of the frame, and they are exact.
    Laterality is different in kind: it asserts a fact about the patient that the source
    never recorded, and no declaration by this software can make it true.

    What is *not* claimed: any registration to patient anatomy. The frame is local and
    the UID says so by being ours. A consumer that needs anatomical orientation will not
    find it here, which is the correct outcome, because it is not known.
    """
    orientation = Dataset()
    orientation.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]

    shared = Dataset()
    shared.PixelMeasuresSequence = [_pixel_measures(volume)]
    shared.PlaneOrientationSequence = [orientation]
    return shared


def _per_frame_functional_groups(n_frames: int, bscan_separation_mm: float) -> list[Dataset]:
    """Frame Content (usage M, may not be Shared) and Plane Position (usage C, required).

    Frame positions step by the real B-scan separation, so the spacing that governs the
    volume computation is expressed twice in the object and the two must agree. That
    redundancy is deliberate: a disagreement between PixelMeasures and the frame step is
    detectable, where a single unchecked value is not (HAZ-012).
    """
    groups = []
    for index in range(n_frames):
        content = Dataset()
        content.FrameAcquisitionNumber = index + 1
        content.StackID = "1"
        content.InStackPositionNumber = index + 1
        content.DimensionIndexValues = [index + 1]

        position = Dataset()
        position.ImagePositionPatient = [0.0, 0.0, float(index * bscan_separation_mm)]

        frame = Dataset()
        frame.FrameContentSequence = [content]
        frame.PlanePositionSequence = [position]
        groups.append(frame)
    return groups


def _build_dataset(
    volume: OCTVolume,
    uid_root: str,
    context: AcquisitionContext | None,
    omissions: list[str],
    study_uid: str,
    series_uid: str,
    frame_of_reference_uid: str,
    software_version: str,
) -> Dataset:
    pixels = np.asarray(volume.pixel_array)
    if pixels.ndim != 3:
        raise ValueError(f"expected a 3-D volume (frames, rows, columns), got {pixels.shape}")
    n_frames, rows, columns = pixels.shape

    ds = Dataset()
    now = datetime.datetime.now(tz=datetime.UTC)

    # SOP Common (M)
    ds.SOPClassUID = OPT_SOP_CLASS_UID
    ds.SOPInstanceUID = generate_uid(uid_root)

    # Patient (M) — all Type 2, so zero-length is conformant and is what a converted
    # archive honestly has. De-identification replaces these downstream.
    ds.PatientName = ""
    ds.PatientID = volume.patient_id
    ds.PatientBirthDate = ""
    ds.PatientSex = ""

    # General Study (M) / General Series (M) / Ophthalmic Tomography Series (M)
    ds.StudyInstanceUID = study_uid
    ds.StudyDate = ""
    ds.StudyTime = ""
    ds.AccessionNumber = ""
    ds.ReferringPhysicianName = ""
    ds.StudyID = ""
    ds.SeriesInstanceUID = series_uid
    ds.Modality = "OPT"
    ds.SeriesNumber = 1

    # General Equipment (M) — Manufacturer is the scanner vendor, which RETOUCH does
    # record, and is what SRS-009 requires to be recoverable from the object.
    ds.Manufacturer = volume.vendor

    # Enhanced General Equipment (M) — SoftwareVersions is genuinely ours: this software
    # created the SOP instance. Model and serial describe the scanner and are unknown.
    ds.SoftwareVersions = software_version
    if context is not None and context.manufacturer_model_name is not None:
        ds.ManufacturerModelName = context.manufacturer_model_name
    if context is not None and context.device_serial_number is not None:
        ds.DeviceSerialNumber = context.device_serial_number

    # Image Pixel (M)
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = int(rows)
    ds.Columns = int(columns)

    # Bit depth is carried from the source, not cast up. PS3.3 C.8.17.7 enumerates
    # BitsAllocated as 8 or 16 and BitsStored as 8, 12 or 16, with High Bit one less
    # than Bits Stored, so both source depths in this dataset are conformant as they
    # stand (docs/06 §3.1.1: Spectralis is 16-bit, Cirrus and Topcon 8-bit).
    #
    # Widening 8-bit data to 16 would be lossless and still wrong: every object would
    # declare a precision its acquisition never had, and a consumer reading BitsStored
    # has no way to tell a genuine 16-bit scan from a padded 8-bit one.
    bits = _bit_depth(pixels)
    ds.BitsAllocated = bits
    ds.BitsStored = bits
    ds.HighBit = bits - 1
    ds.PixelRepresentation = 0  # Enumerated Value 0 for this IOD
    ds.PixelData = pixels.tobytes()

    # Ophthalmic Tomography Image (M)
    ds.ImageType = ["DERIVED", "SECONDARY"]
    if context is not None and context.acquisition_datetime is not None:
        ds.AcquisitionDateTime = context.acquisition_datetime
    ds.AcquisitionNumber = 1
    ds.InConcatenationNumber = 1
    ds.InConcatenationTotalNumber = 1
    ds.ConcatenationFrameOffsetNumber = 0
    ds.BurnedInAnnotation = "NO"
    ds.LossyImageCompression = "00"
    ds.PresentationLUTShape = "IDENTITY"

    # Ophthalmic Tomography Parameters (M)
    ds.DetectorType = "CCD"
    ds.AcquisitionDeviceTypeCodeSequence = []

    # Ophthalmic Tomography Acquisition Parameters (M) — all Type 2.
    for keyword in (
        "EmmetropicMagnification",
        "IntraOcularPressure",
        "HorizontalFieldOfView",
        "PupilDilated",
        "AxialLengthOfTheEye",
    ):
        setattr(ds, keyword, None)
    ds.RefractiveStateSequence = []

    # Acquisition Context (M) — Type 2 sequence; empty is conformant.
    ds.AcquisitionContextSequence = []

    # Frame of Reference — usage C, and its condition is not met here: there is no
    # Ophthalmic Photography Reference Image and the volumetric properties flag is not
    # set. The condition ends "May be present otherwise", so including it is conformant.
    #
    # It is included because a downstream multi-frame Segmentation cannot be built
    # without one: the SEG IOD needs a shared spatial frame to relate its frames to the
    # source. The UID asserts only that the frames of this one volume share a frame of
    # reference, which is true by construction — it is an identifier minted for a real
    # relationship, in the same category as StudyInstanceUID, not an anatomical fact
    # invented to satisfy a validator.
    ds.FrameOfReferenceUID = frame_of_reference_uid
    ds.PositionReferenceIndicator = ""

    # Multi-frame Dimension (M)
    dimension_uid = generate_uid(uid_root)
    organization = Dataset()
    organization.DimensionOrganizationUID = dimension_uid
    ds.DimensionOrganizationSequence = [organization]

    # Multi-frame Functional Groups (M) — spacing lives here, not at top level.
    ds.ContentDate = now.strftime("%Y%m%d")
    ds.ContentTime = now.strftime("%H%M%S")
    ds.InstanceNumber = 1
    ds.NumberOfFrames = int(n_frames)
    ds.SharedFunctionalGroupsSequence = [_shared_functional_groups(volume)]
    ds.PerFrameFunctionalGroupsSequence = _per_frame_functional_groups(
        n_frames, volume.spacing_mm[2]
    )

    # Ocular Region Imaged (M) — written only from caller-supplied values.
    #
    # AnatomicRegionSequence must be coded from CID 4209. The obvious value is a macula
    # code, but this module does not carry one: the binding has not been verified against
    # the standard, and an unverified code is an invented code with extra steps. The
    # caller supplies it or it is omitted.
    if context is not None:
        ds.ImageLaterality = context.laterality
        if context.anatomic_region is not None:
            ds.AnatomicRegionSequence = [context.anatomic_region]

    return ds


def write_volume(
    volume: OCTVolume,
    out_dir: Path,
    uid_root: str,
    *,
    context: AcquisitionContext | None = None,
    research_exception: bool = False,
    software_version: str | None = None,
    study_instance_uid: str | None = None,
    series_instance_uid: str | None = None,
    frame_of_reference_uid: str | None = None,
) -> WriteResult:
    """Write one OCTVolume as a multi-frame DICOM instance. Returns what was produced.

    `research_exception` is off by default and must be set deliberately. When set, any
    mandatory attribute that cannot be populated from available data is omitted, a
    warning names it, and it is recorded in the result (SRS-063).
    """
    from ocuval import __version__

    validate_spacing(volume.spacing_mm, source=str(volume.source_path), vendor=volume.vendor)
    omissions = _resolve_omissions(context, research_exception)

    study_uid = study_instance_uid or generate_uid(uid_root)
    series_uid = series_instance_uid or generate_uid(uid_root)
    frame_of_reference_uid = frame_of_reference_uid or generate_uid(uid_root)

    ds = _build_dataset(
        volume,
        uid_root,
        context,
        omissions,
        study_uid,
        series_uid,
        frame_of_reference_uid or generate_uid(uid_root),
        software_version or __version__,
    )

    missing = validate_against_iod(ds, permitted_omissions=tuple(omissions))
    if missing:
        raise ValueError(
            f"object is incomplete against the Ophthalmic Tomography Image IOD: {missing}. "
            f"This is a defect in the writer, not in the data — conversion aborts rather "
            f"than emitting an object that claims conformance it does not have (SRS-064)."
        )

    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ds.SOPInstanceUID}.dcm"
    ds.save_as(str(path), write_like_original=False)

    return WriteResult(
        paths=[path],
        sop_instance_uids=[ds.SOPInstanceUID],
        study_instance_uid=study_uid,
        series_instance_uid=series_uid,
        frame_of_reference_uid=frame_of_reference_uid,
        omissions=omissions,
    )


def read_back(path: Path) -> pydicom.Dataset:
    """Read an instance this module wrote. Convenience for round-trip verification."""
    return pydicom.dcmread(str(path))
