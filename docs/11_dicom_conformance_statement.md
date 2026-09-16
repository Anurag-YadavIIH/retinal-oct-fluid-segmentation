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
3. **Out-of-scope input criteria unresolved.** SRS-048 requires rejection of
   out-of-scope acquisitions; which attributes establish that is not known until the
   conversion in milestone 3 exists (`docs/02` §6 item 2).
