"""De-identification under DICOM PS3.15 Annex E Basic Application Confidentiality Profile.

Traces to: SRS-012, SRS-013, SRS-014, SRS-015, SRS-016, SRS-017 (de-identification)
Implements risk control: RC-011, RC-012 (HAZ-009), and RC-008 for the vendor attribute

No real PHI ever enters this project — the data is public challenge data. The control is
implemented and tested anyway, because demonstrating it is the point.

Patient pseudonyms are derived with a salted hash; the salt is read from the environment
variable named in configs/data.yaml and is never committed.

**Attributes are named by DICOM keyword, never by tag number.** pydicom resolves the
keyword to the tag, so this module cannot invent a tag: the worst available failure is
naming an attribute that does not exist, which raises at import of the table rather than
writing plausible-looking incorrect DICOM. That is CLAUDE.md's most expensive failure
mode removed by construction.

**Known limit of the control.** `PROFILE` below is a subset of the Annex E attribute
table, not the whole of it — a faithful implementation needs the standard's full table.
`verify_deidentified` checks exactly the attributes in `PROFILE`, so **it cannot detect
an identifying attribute the table omits**: application and verification share one source
of truth. docs/04 SOUP-001 records this as a limitation of the control rather than of the
library, and it is an open item against this module.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from pathlib import Path

import pydicom
from pydicom.datadict import tag_for_keyword

# Marks a value as a pseudonym rather than an original identifier. Verification keys off
# it, so the two halves cannot disagree about what a de-identified value looks like.
PSEUDONYM_PREFIX = "OCUVAL-"


class Action(Enum):
    """The subset of PS3.15 Annex E actions this module applies."""

    REMOVE = "X"  # delete the attribute entirely
    EMPTY = "Z"  # retain the attribute with a zero-length value
    PSEUDONYM = "P"  # replace with a salted hash of the original value


# Keyword -> action. Extending this table is a requirements change, not an edit:
# verification is derived from it, so an omission here is an omission in both halves.
PROFILE: dict[str, Action] = {
    "PatientName": Action.PSEUDONYM,
    "PatientID": Action.PSEUDONYM,
    "OtherPatientIDs": Action.REMOVE,
    "OtherPatientNames": Action.REMOVE,
    "PatientBirthDate": Action.REMOVE,
    "PatientBirthTime": Action.REMOVE,
    "PatientAddress": Action.REMOVE,
    "PatientTelephoneNumbers": Action.REMOVE,
    "PatientMotherBirthName": Action.REMOVE,
    "MilitaryRank": Action.REMOVE,
    "ReferringPhysicianName": Action.EMPTY,
    "ReferringPhysicianAddress": Action.REMOVE,
    "ReferringPhysicianTelephoneNumbers": Action.REMOVE,
    "PerformingPhysicianName": Action.REMOVE,
    "NameOfPhysiciansReadingStudy": Action.REMOVE,
    "OperatorsName": Action.REMOVE,
    "InstitutionName": Action.REMOVE,
    "InstitutionAddress": Action.REMOVE,
    "InstitutionalDepartmentName": Action.REMOVE,
    "StationName": Action.REMOVE,
    "AccessionNumber": Action.EMPTY,
    "StudyID": Action.EMPTY,
    "RequestingPhysician": Action.REMOVE,
    "RequestingService": Action.REMOVE,
    "AdmissionID": Action.REMOVE,
    "PatientComments": Action.REMOVE,
    "AdditionalPatientHistory": Action.REMOVE,
    "DeviceSerialNumber": Action.REMOVE,
}

# Attributes that must survive, checked explicitly because they sit next to the ones
# being removed and are the easiest thing to lose by widening the table (SRS-017,
# RC-008). Losing the manufacturer destroys per-vendor reporting, which is the project.
MUST_SURVIVE: tuple[str, ...] = ("Manufacturer", "ManufacturerModelName", "Modality")

_UNRESOLVED = sorted(k for k in (*PROFILE, *MUST_SURVIVE) if tag_for_keyword(k) is None)
if _UNRESOLVED:  # pragma: no cover - a typo in the table, caught at import
    raise RuntimeError(f"unknown DICOM keywords in the profile table: {_UNRESOLVED}")


def _violates(action: Action, value: str) -> bool:
    """True when a surviving attribute's value is not what its action required.

    Shared by verification so that "what counts as de-identified" is defined once.
    """
    if action is Action.REMOVE:
        return True  # present at all is the violation
    if action is Action.EMPTY:
        return value != ""
    return not value.startswith(PSEUDONYM_PREFIX)


def pseudonymise(patient_id: str, salt: str) -> str:
    """Return a stable pseudonym for a patient identifier.

    A pure function of the identifier and the salt (SRS-014): the same pair yields the
    same pseudonym in every run and on every machine, not merely within one process.
    Within-run stability is what keeps patient-level splitting valid after
    de-identification; cross-run stability is what makes a recorded result traceable to
    the volume it came from, which is what URS-010 is actually for. The requirement said
    only the first until 2026-09-25, when the wording was corrected -- this function
    always satisfied both, but a requirement that permits an ephemeral salt is a
    requirement that permits losing provenance. See docs/06 section 5.1.

    Different under a different salt, so the mapping cannot be reversed by anyone
    without it.

    The salt is required and has no default. A pseudonym derived from an unsalted hash
    of a small identifier space is trivially reversible by enumeration, which would be a
    control that looks like a control and is not.
    """
    if not salt:
        raise ValueError("a non-empty salt is required; refusing to derive an unsalted pseudonym")
    digest = hashlib.sha256(f"{salt}:{patient_id}".encode()).hexdigest()
    return f"{PSEUDONYM_PREFIX}{digest[:16].upper()}"


def _apply(dataset: pydicom.Dataset, salt: str) -> None:
    for keyword, action in PROFILE.items():
        if keyword not in dataset:
            continue
        if action is Action.REMOVE:
            delattr(dataset, keyword)
        elif action is Action.EMPTY:
            setattr(dataset, keyword, "")
        elif action is Action.PSEUDONYM:
            setattr(dataset, keyword, pseudonymise(str(getattr(dataset, keyword)), salt))


def deidentify_instance(src: Path, dst: Path, salt: str) -> None:
    """Apply the confidentiality profile to one DICOM instance.

    Raises if a `MUST_SURVIVE` attribute was present in the source and is absent from the
    result. Losing the vendor is not a degraded output, it is a failed run (SRS-017).
    """
    dataset = pydicom.dcmread(str(src))
    present_before = [k for k in MUST_SURVIVE if k in dataset]

    _apply(dataset, salt)

    lost = [k for k in present_before if k not in dataset]
    if lost:
        raise ValueError(f"de-identification removed attributes that must survive: {lost}")

    # PS3.15 requires the instance to declare that it has been de-identified.
    dataset.PatientIdentityRemoved = "YES"
    dataset.DeidentificationMethod = "OcuVal PS3.15 Annex E Basic (subset; see docs/04)"

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dataset.save_as(str(dst))


def verify_deidentified(path: Path) -> list[str]:
    """Return the names of any tags that should have been removed but were not.

    An empty list means the instance passes, and it is the only condition under which it
    passes (SRS-015). A non-empty return aborts the conversion run (SRS-016); failing
    instances are never silently skipped. Used by TC-033 and TC-034.

    Checks exactly the attributes in `PROFILE`. See the module docstring: this cannot
    detect an attribute the table omits.
    """
    dataset = pydicom.dcmread(str(path))
    offending = [
        keyword
        for keyword, action in PROFILE.items()
        if keyword in dataset and _violates(action, str(getattr(dataset, keyword)))
    ]

    if getattr(dataset, "PatientIdentityRemoved", "") != "YES":
        offending.append("PatientIdentityRemoved")

    return sorted(offending)
