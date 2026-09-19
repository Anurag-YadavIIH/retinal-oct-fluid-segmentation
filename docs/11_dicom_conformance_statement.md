<!--
Document: DICOM Conformance Statement
Status: NOT DRAFTED — template only
Owner: Anurag Yadav
Last reviewed: -
Change history: docs/13_change_control_log.md
-->

# DICOM Conformance Statement

> **Status: template.** This document has not been drafted. Fill it in before
> writing any code that depends on it — see CLAUDE.md rule 1.

## 1. Introduction and scope

## 2. Implementation model

## 3. Networking — DICOMweb

### 3.1 STOW-RS
### 3.2 WADO-RS
### 3.3 QIDO-RS

## 4. Media storage and SOP classes supported

| SOP Class | UID | Role |
|---|---|---|
| Ophthalmic Tomography Image Storage | 1.2.840.10008.5.1.4.1.1.77.1.5.4 | created, read |
| Segmentation Storage | 1.2.840.10008.5.1.4.1.1.66.4 | created |
| Comprehensive 3D SR Storage | 1.2.840.10008.5.1.4.1.1.88.34 | created |

## 5. Transfer syntaxes

## 6. Attribute mapping

## 7. UID policy

> The rest of this document remains a template. This section and §10 are populated
> ahead of it because they record a decision taken on 2026-09-16, not because the
> statement as a whole is drafted.

Study, series and SOP Instance UIDs are generated under the root configured in
`configs/data.yaml` (`dicom.uid_root`). **That root is not registered** — see
`docs/06` §7.1 for the full statement and its consequences.

The decision taken is to document the placeholder rather than to register a root,
and not to substitute a different-looking value. In consequence this implementation
makes **no claim of global UID uniqueness**, and objects it creates are confined to
the local Orthanc instance.

## 8. De-identification profile and options

## 9. Character sets

## 10. Known limitations

1. **Unregistered UID root.** UIDs are structurally valid but globally unclaimed
   (§7, `docs/06` §7.1). Objects must not leave the local Orthanc instance.
2. **Research-use designation mechanism unresolved.** URS-011 and SRS-042 require an
   in-object designation that a result is research-use-only, not clinically validated,
   and automated. The conformant means of expressing this in a SEG and an SR is not yet
   decided; candidates and their trade-offs are listed in `docs/01` §8 item 1. To be
   settled here before milestone 6.
3. **Objects derived from RETOUCH are non-conformant to the Ophthalmic Tomography
   Image IOD in named respects.** The IOD assumes a real acquisition on a real device
   with a fundus reference image; RETOUCH is a converted archive with that context
   stripped. Specifically, the following cannot be populated from available data:

   | Not populated | Requirement | Why it cannot be supplied |
   |---|---|---|
   | `ImageLaterality` (Ocular Region Imaged, module usage **M**) | Type 1, enumerated `R`/`L`/`B` — no empty and no unknown value exists | RETOUCH records no laterality |
   | `AnatomicRegionSequence` (same module) | Type 1, coded from CID 4209 | Recorded region is macular OCT, but the module is omitted whole rather than partly filled |
   | `AcquisitionDateTime` (Ophthalmic Tomography Image, module usage **M**) | Type 1, unconditional | RETOUCH records no acquisition date or time; the conversion time is a different fact wearing the same name |
| `ManufacturerModelName`, `DeviceSerialNumber` (Enhanced General Equipment, **M**) | Type 1 | Describe the scanner, which RETOUCH identifies only by vendor. `DeviceSerialNumber` is additionally removed by the confidentiality profile |
| Plane Position (Patient) macro | **C** — required when no Ophthalmic Photography Reference Image is available, which is our case (Table A.52.4.3-1) | No patient coordinate frame is recorded |
   | Plane Orientation (Patient) macro | **C** — same condition | The B-scan plane's orientation in patient coordinates is unrecorded |

   **The alternative considered and rejected was fabricating values.** A detectable
   non-conformance is safer than an undetectable fabrication: a missing Type 1 attribute
   is flagged by any validator, whereas an invented laterality is read downstream as a
   true anatomical fact, and DICOM provides no way to mark a value as provisional. The
   writer therefore refuses by default (SRS-062) and, under an explicit research
   exception, omits rather than fills (SRS-063).

   `AcquisitionDateTime`, `ManufacturerModelName` and `DeviceSerialNumber` were not
   anticipated when this item was first drafted. They were found by the SRS-064
   check running against highdicom's PS3.3-derived tables, which is the difference
   between a conformance claim that has been verified and one that has been
   remembered.

   `AnatomicRegionSequence` is omitted for a different reason: the value is known —
   RETOUCH is macular OCT — but the module requires a code from CID 4209 and that
   binding has not been verified against the standard. An unverified code is an
   invented code with extra steps, so the caller supplies it or it is omitted.

   Established from the normative text: Ocular Region Imaged usage from Table A.52.3-1;
   `ImageLaterality` type and values from PS3.3 C.8.17.5; macro usages from
   Table A.52.4.3-1. Ophthalmic Frame Location is usage **U** and is omitted with no
   conformance consequence.

   **This sits alongside the unregistered UID root in item 1.** Both are reasons the
   objects this project creates must not be transmitted beyond the local Orthanc
   instance.

4. **Out-of-scope input criteria unresolved.** SRS-048 requires rejection of
   out-of-scope acquisitions; which attributes establish that is not known until the
   conversion in milestone 3 exists (`docs/02` §6 item 2).
