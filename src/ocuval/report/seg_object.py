"""Write segmentation results as DICOM Segmentation objects.

Traces to: SRS-038, SRS-039, SRS-042 (segmentation output)
Implements risk control: RC-013, RC-014, RC-029 (HAZ-010, HAZ-011, HAZ-015)

Built with `highdicom.seg.Segmentation`, which does have a purpose-built constructor for
this IOD — unlike the Ophthalmic Tomography Image objects in `ocuval.io.dicom_writer`,
which are assembled by hand. Handing highdicom the source images is also what produces
the reference back to them (SRS-039, RC-013): that link is what makes HAZ-004, a result
attached to the wrong acquisition, detectable rather than silent.

**Coded concepts, and which of them could be verified.** A segment description requires
a coded category and a coded type, both Type 1. Checked against the concept dictionary
pydicom ships:

- Category: `SCT 49755003 Morphologically Abnormal Structure` — **verified**, used here.
- Anatomic region: `SCT 5665001 Retina` — **verified**, used here.
- Type, for IRF / SRF / PED: **no code found for any of the three.** They are therefore
  caller-supplied with no default, on the same rule that governs laterality in
  `dicom_writer` and `AnatomicRegionSequence` there: a code that has not been verified
  against its scheme is an invented code with extra steps.

Unlike laterality, omission is not available — `SegmentDescription` requires the code —
so the only honest options are a verified standard code or an explicitly declared local
one. Callers who have neither should use a private coding scheme designator, which DICOM
permits and which *says* it is local rather than impersonating SNOMED.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from highdicom import AlgorithmIdentificationSequence
from highdicom.seg import SegmentAlgorithmTypeValues, Segmentation, SegmentDescription
from highdicom.sr import CodedConcept
from pydicom import Dataset
from pydicom.sr.codedict import codes

# Verified against pydicom's shipped concept dictionary, which carries the standard's
# own tables. Changing either is a coded-concept change and belongs in docs/13.
SEGMENTED_PROPERTY_CATEGORY = codes.SCT.MorphologicallyAbnormalStructure
RETINA = codes.SCT.Retina


class SegmentCodingError(ValueError):
    """Raised when a fluid class has no caller-supplied coded type."""


@dataclass(frozen=True)
class FluidSegment:
    """One fluid class to be written as a segment.

    `coded_type` has no default. There is no verified standard code for intraretinal
    fluid, subretinal fluid or pigment epithelial detachment in the concept dictionary
    this project can check against, and supplying an unverified one would be the
    fabrication RC-029 forbids.
    """

    label: str
    mask: np.ndarray
    coded_type: CodedConcept | Dataset

    def __post_init__(self) -> None:
        if self.coded_type is None:
            raise SegmentCodingError(
                f"fluid class {self.label!r} has no coded segmented property type. No "
                f"verified standard code exists for the RETOUCH fluid classes, so one "
                f"must be supplied — a verified code from a standard scheme, or an "
                f"explicitly declared local code under a private coding scheme "
                f"designator. The writer will not substitute one (docs/05 RC-029)."
            )


def build_segmentation(
    source_images: list[Dataset],
    segments: list[FluidSegment],
    *,
    series_instance_uid: str,
    sop_instance_uid: str,
    series_number: int = 2,
    instance_number: int = 1,
    software_version: str | None = None,
    manufacturer: str = "OcuVal",
    manufacturer_model_name: str = "OcuVal fluid segmentation",
    device_serial_number: str = "N/A",
) -> Segmentation:
    """Build a DICOM Segmentation from per-class masks.

    `source_images` is what ties the result to the acquisition it came from. highdicom
    writes the referenced series and instance UIDs from it, and TC-071 asserts they
    match the input.

    Segments are written in the order given; the caller is responsible for that order
    matching the frozen label indices in `configs/data.yaml`.
    """
    from ocuval import __version__

    if not source_images:
        raise ValueError(
            "at least one source image is required; a segmentation with no "
            "referenced source cannot be reviewed against anything (SRS-039)"
        )
    if not segments:
        raise ValueError("at least one segment is required")

    algorithm = AlgorithmIdentificationSequence(
        name="OcuVal fluid segmentation",
        version=software_version or __version__,
        family=codes.DCM.ArtificialIntelligence,
    )

    descriptions = [
        SegmentDescription(
            segment_number=index + 1,
            segment_label=segment.label,
            segmented_property_category=SEGMENTED_PROPERTY_CATEGORY,
            segmented_property_type=segment.coded_type,
            algorithm_type=SegmentAlgorithmTypeValues.AUTOMATIC,
            algorithm_identification=algorithm,
            anatomic_regions=[RETINA],
        )
        for index, segment in enumerate(segments)
    ]

    # (frames, rows, columns, segments), which is what highdicom expects for a
    # multi-segment label array.
    stacked = np.stack([np.asarray(s.mask).astype(np.uint8) for s in segments], axis=-1)

    return Segmentation(
        source_images=source_images,
        pixel_array=stacked,
        segmentation_type="BINARY",
        segment_descriptions=descriptions,
        series_instance_uid=series_instance_uid,
        series_number=series_number,
        sop_instance_uid=sop_instance_uid,
        instance_number=instance_number,
        manufacturer=manufacturer,
        manufacturer_model_name=manufacturer_model_name,
        software_versions=software_version or __version__,
        device_serial_number=device_serial_number,
    )


def referenced_sop_instance_uids(segmentation: Dataset) -> set[str]:
    """Every source SOP Instance UID the segmentation references (SRS-039, RC-013).

    Used by TC-071 to assert the link back to the acquisition is real, which is what
    makes a result attached to the wrong study detectable.
    """
    found: set[str] = set()
    for series in getattr(segmentation, "ReferencedSeriesSequence", []):
        for instance in getattr(series, "ReferencedInstanceSequence", []):
            found.add(str(instance.ReferencedSOPInstanceUID))
    return found
