"""Write fluid measurements as a DICOM Structured Report.

Traces to: SRS-040, SRS-041, SRS-042, SRS-057, SRS-058, SRS-059 (SR output)
Implements risk control: RC-009, RC-014, RC-024, RC-025, RC-026 (HAZ-007, HAZ-012)

**Units are coded, not written as text** (SRS-058, RC-025). A measurement whose unit is
a string in a comment is not machine-readable, and a consumer that has to guess whether
a number is mm³ or µm³ is a thousand-fold volume error waiting to happen — which is
HAZ-012 arriving by a second route. Every unit here is a UCUM coded concept verified
against the dictionary pydicom ships:

- `mm3` / cubic millimeter — `codes.UCUM.CubicMillimeter`
- `{counts}` / Counts — `codes.UCUM.Counts`
- `1` / no units — `codes.UCUM.NoUnits`, for the confidence ratio

**The voxel count is a measurement, not an annotation** (SRS-059, RC-026). It is emitted
as a NUM content item with its own coded name and unit, alongside the voxel volume, so
that volume = count x voxel volume can be recomputed from the object by software. A
comment saying "1000 voxels" would satisfy a reader and not a validator, and the point of
RC-026 is that the derivation is auditable by machine.

**Coded names, and which could be verified.** `SCT 118565006 Volume` is verified and used
for the volume measurement. There is no generic count or confidence concept in the
dictionary, so those names are caller-supplied on the same rule as the fluid classes in
`seg_object`: an unverified code is an invented code with extra steps.
"""

from __future__ import annotations

from dataclasses import dataclass

from highdicom.sr import (
    CodedConcept,
    Comprehensive3DSR,
    DeviceObserverIdentifyingAttributes,
    Measurement,
    MeasurementReport,
    MeasurementsAndQualitativeEvaluations,
    ObservationContext,
    ObserverContext,
    TrackingIdentifier,
)
from pydicom import Dataset
from pydicom.sr.codedict import codes

from ocuval.report.coding import OCUVAL_SCHEME_DESIGNATOR, declare_scheme

# Verified UCUM concepts. RC-025 is satisfied by these being coded, not by their values.
UNIT_CUBIC_MM = codes.UCUM.CubicMillimeter
UNIT_COUNTS = codes.UCUM.Counts
UNIT_NO_UNITS = codes.UCUM.NoUnits

# Verified measurement name.
VOLUME = codes.SCT.Volume


class MeasurementCodingError(ValueError):
    """Raised when a measurement name has no caller-supplied coded concept."""


@dataclass(frozen=True)
class MeasurementNames:
    """Coded names for the measurements this project emits.

    `volume` is verified and defaulted. The other three are not available in the
    concept dictionary and have no default: the caller supplies a verified standard code
    or an explicitly declared local one.
    """

    voxel_count: CodedConcept | Dataset
    voxel_volume: CodedConcept | Dataset
    confidence: CodedConcept | Dataset
    volume: CodedConcept | Dataset = VOLUME

    def __post_init__(self) -> None:
        for field_name in ("voxel_count", "voxel_volume", "confidence"):
            if getattr(self, field_name) is None:
                raise MeasurementCodingError(
                    f"{field_name} has no coded name. No verified standard concept was "
                    f"found for it, so one must be supplied rather than substituted "
                    f"(docs/05 RC-029)."
                )


@dataclass(frozen=True)
class FluidMeasurement:
    """One fluid class's measurements, carrying the terms of its own derivation.

    `voxel_count` and `voxel_volume_mm3` are not diagnostics: SRS-059 requires the
    volume to be recomputable from the emitted object alone, because a volume that is
    wrong only in its spacing looks entirely correct in the mask and to a grader.
    """

    label: str
    coded_type: CodedConcept | Dataset
    volume_mm3: float
    voxel_count: int
    voxel_volume_mm3: float


def build_measurement_report(
    source_images: list[Dataset],
    measurements: list[FluidMeasurement],
    names: MeasurementNames,
    *,
    confidence: float,
    procedure_reported: CodedConcept | Dataset,
    device_uid: str,
    series_instance_uid: str,
    sop_instance_uid: str,
    series_number: int = 3,
    instance_number: int = 1,
    software_version: str | None = None,
) -> Comprehensive3DSR:
    """Build a Comprehensive 3D SR carrying per-class volumes and the scan confidence.

    `confidence` is the scan-level MC-dropout value required by SRS-041 and RC-009. It is
    carried in the report rather than only in run logs, because a confidence visible only
    in a log is not available to the grader at the moment of review, which is the only
    moment it matters.
    """
    from ocuval import __version__

    if not source_images:
        raise ValueError("at least one source image is required")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be in [0, 1], got {confidence}")

    observer = ObserverContext(
        observer_type=codes.DCM.Device,
        observer_identifying_attributes=DeviceObserverIdentifyingAttributes(
            uid=device_uid,
            name="OcuVal",
            manufacturer_name="OcuVal",
            model_name="OcuVal fluid segmentation",
        ),
    )
    context = ObservationContext(observer_device_context=observer)

    groups = []
    for index, item in enumerate(measurements):
        items = [
            Measurement(name=names.volume, value=float(item.volume_mm3), unit=UNIT_CUBIC_MM),
            # RC-026: a real NUM measurement, so the derivation is machine-auditable.
            Measurement(name=names.voxel_count, value=float(item.voxel_count), unit=UNIT_COUNTS),
            Measurement(
                name=names.voxel_volume,
                value=float(item.voxel_volume_mm3),
                unit=UNIT_CUBIC_MM,
            ),
        ]
        groups.append(
            MeasurementsAndQualitativeEvaluations(
                tracking_identifier=TrackingIdentifier(
                    uid=f"{device_uid}.{index + 1}", identifier=item.label
                ),
                finding_type=item.coded_type,
                measurements=items,
            )
        )

    # Scan-level confidence, carried as its own measurement group rather than as a
    # property of any one fluid class: it describes the inference, not a finding.
    groups.append(
        MeasurementsAndQualitativeEvaluations(
            tracking_identifier=TrackingIdentifier(
                uid=f"{device_uid}.confidence", identifier="scan-level confidence"
            ),
            measurements=[
                Measurement(name=names.confidence, value=float(confidence), unit=UNIT_NO_UNITS)
            ],
        )
    )

    report = MeasurementReport(
        observation_context=context,
        procedure_reported=procedure_reported,
        imaging_measurements=groups,
    )

    document = Comprehensive3DSR(
        evidence=source_images,
        content=report[0],
        series_instance_uid=series_instance_uid,
        series_number=series_number,
        sop_instance_uid=sop_instance_uid,
        instance_number=instance_number,
        manufacturer="OcuVal",
        software_versions=software_version or __version__,
    )

    coded = [names.volume, names.voxel_count, names.voxel_volume, names.confidence]
    coded += [m.coded_type for m in measurements]
    if any(
        getattr(c, "scheme_designator", None) == OCUVAL_SCHEME_DESIGNATOR
        or getattr(c, "CodingSchemeDesignator", None) == OCUVAL_SCHEME_DESIGNATOR
        for c in coded
    ):
        declare_scheme(document)

    return document


def numeric_measurements(dataset: Dataset) -> list[tuple[str, float, str]]:
    """Every NUM content item in the report, as (concept meaning, value, unit code).

    Walks the content tree so a test can assert that a quantity is a real measurement
    rather than text — which is what RC-026 and RC-025 actually require.
    """
    found: list[tuple[str, float, str]] = []

    def walk(items) -> None:
        for item in items or []:
            if getattr(item, "ValueType", None) == "NUM":
                name = item.ConceptNameCodeSequence[0].CodeMeaning
                measured = item.MeasuredValueSequence[0]
                unit = measured.MeasurementUnitsCodeSequence[0].CodeValue
                found.append((str(name), float(measured.NumericValue), str(unit)))
            walk(getattr(item, "ContentSequence", None))

    walk(getattr(dataset, "ContentSequence", None))
    return found
