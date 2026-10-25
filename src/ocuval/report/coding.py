"""The project's declared private coding scheme for the RETOUCH fluid classes.

Traces to: SRS-065 (coded concepts)
Implements risk control: RC-029 (HAZ-015)

**Why a private scheme rather than a standard code.** The three RETOUCH fluid classes —
intraretinal fluid, subretinal fluid and pigment epithelial detachment — were searched
for in the concept dictionary pydicom ships, which carries the standard's own tables.
No verified code was found for any of the three. `SegmentDescription` will not accept
omission, so the choice was between a private scheme and borrowing a standard code that
approximately fits.

A borrowed code was rejected. It is the inverse of the `AnatomicRegionSequence` failure
this project already avoids: it *looks* interoperable while meaning something slightly
different to every reader, and nothing in the object marks the approximation. A private
scheme is honest and unambiguously non-interoperable, which is the true state.

**The scheme is declared in the object, not left as a bare local string.** PS3.3 C.12.1
makes `CodingSchemeUID` Type 1C, "Required if Coding Scheme is identified by an ISO 8824
object identifier" — so identifying the scheme by an OID under this project's root both
satisfies the condition and is what makes the declaration meaningful. `CodingSchemeRegistry`
and `CodingSchemeExternalID` do not apply: this scheme is not registered.

The root carries the caveat in `docs/06` §7.1 — it is a declared placeholder and is not
registered, so this scheme UID is structurally valid and globally unclaimed like every
other UID this project mints.

Callers with verified codes from a scheme they trust pass them instead; nothing here is
mandatory (SRS-065).
"""

from __future__ import annotations

from highdicom.sr import CodedConcept
from pydicom import Dataset

#: Private coding scheme designator. PS3.16 reserves designators beginning "99" for
#: private schemes, so this one announces itself as local by its name alone.
OCUVAL_SCHEME_DESIGNATOR = "99OCUVAL"

#: The research-use designation (SRS-042, RC-014), decided by the author 2026-10-16
#: (docs/11 section 10 item 2): A, Content Qualification on every SEG, SR and OPT object;
#: B, this text in the SEG's Series and Content Descriptions and the SR's Series Description,
#: ASCII and 60 characters, within LO's 64; C, the SR left UNVERIFIED and PRELIMINARY.
CONTENT_QUALIFICATION = "RESEARCH"
RESEARCH_USE_TEXT = "RESEARCH USE ONLY: automated, not validated, review required"

OCUVAL_SCHEME_NAME = "OcuVal RETOUCH fluid classes"

#: Identifies the scheme by OID, satisfying the C.12.1 condition above. Derived from the
#: configured UID root; the default mirrors `configs/data.yaml` (`dicom.uid_root`).
DEFAULT_SCHEME_UID = "1.2.826.0.1.3680043.10.9999.1"

#: The vocabulary itself. Code values are the RETOUCH class abbreviations, so an object
#: is readable by a human who knows the dataset and opaque to one who does not — which
#: is an accurate description of what a private scheme is.
FLUID_CODE_VALUES: dict[str, str] = {
    "IRF": "Intraretinal fluid",
    "SRF": "Subretinal fluid",
    "PED": "Pigment epithelial detachment",
}


#: Measurement and evaluation names in the SR for which no verified generic concept exists
#: (docs/11 section 10 item 5). Declared in this scheme by the author's decision of
#: 2026-10-16, on the same reasoning as the fluid classes. The volume measurement and the
#: review evaluation's value are verified standard codes and are not here.
MEASUREMENT_CODE_VALUES: dict[str, str] = {
    "VOXELCOUNT": "Predicted voxel count",
    "VOXELVOLUME": "Voxel volume",
    "MCCONF": "MC-dropout scan-level confidence",
    "REVIEW": "Review recommended",
}


def measurement_code(value: str) -> CodedConcept:
    """The declared local code for one SR measurement or evaluation name."""
    if value not in MEASUREMENT_CODE_VALUES:
        declared = sorted(MEASUREMENT_CODE_VALUES)
        raise KeyError(f"{value!r} is not a declared measurement name {declared}")
    return CodedConcept(
        value=value,
        scheme_designator=OCUVAL_SCHEME_DESIGNATOR,
        meaning=MEASUREMENT_CODE_VALUES[value],
    )


def fluid_code(label: str, *, scheme_uid: str = DEFAULT_SCHEME_UID) -> CodedConcept:
    """The declared local code for one RETOUCH fluid class.

    Raises for any label outside the three frozen classes: the scheme declares exactly
    those three, and extending it silently would make the declaration untrue.
    """
    if label not in FLUID_CODE_VALUES:
        raise KeyError(
            f"{label!r} is not one of the declared fluid classes "
            f"{sorted(FLUID_CODE_VALUES)}. This scheme declares exactly those three; "
            f"supply a coded concept explicitly for anything else."
        )
    del scheme_uid  # the UID identifies the scheme in the object, not each code
    return CodedConcept(
        value=label,
        scheme_designator=OCUVAL_SCHEME_DESIGNATOR,
        meaning=FLUID_CODE_VALUES[label],
    )


def coding_scheme_identification(*, scheme_uid: str = DEFAULT_SCHEME_UID) -> Dataset:
    """The `CodingSchemeIdentificationSequence` item declaring this scheme.

    Without this, a `99OCUVAL` designator in a segment description is a bare local
    string that says nothing about whose scheme it is. With it, the object carries the
    scheme's identity, name and responsible organisation, so a reader can tell what they
    are looking at and that they are not expected to interoperate with it.
    """
    item = Dataset()
    item.CodingSchemeDesignator = OCUVAL_SCHEME_DESIGNATOR
    item.CodingSchemeUID = scheme_uid
    item.CodingSchemeName = OCUVAL_SCHEME_NAME
    # ASCII only (SRS-095): no Specific Character Set is declared, so a character outside
    # the default repertoire is substituted on writing. Until 2026-10-16 an em dash here
    # was stored as "?" in every SEG and SR (docs/11 section 10 item 7).
    item.CodingSchemeResponsibleOrganization = (
        "OcuVal research project, not a registered coding scheme authority"
    )
    return item


def declare_scheme(dataset: Dataset, *, scheme_uid: str = DEFAULT_SCHEME_UID) -> None:
    """Attach the scheme declaration to an emitted object, if not already present.

    Idempotent, and additive: an existing sequence is extended rather than replaced, so
    declaring this scheme never removes a caller's own declarations.
    """
    existing = list(getattr(dataset, "CodingSchemeIdentificationSequence", []))
    if any(
        getattr(item, "CodingSchemeDesignator", None) == OCUVAL_SCHEME_DESIGNATOR
        for item in existing
    ):
        return
    dataset.CodingSchemeIdentificationSequence = [
        *existing,
        coding_scheme_identification(scheme_uid=scheme_uid),
    ]
