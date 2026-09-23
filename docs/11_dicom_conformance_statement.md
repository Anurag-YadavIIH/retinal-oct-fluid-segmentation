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

   **The omissions are universal, not occasional.** On the first end-to-end conversion
   of the RETOUCH training partition (2026-09-23), the SRS-063 research exception fired
   on **70 of 70 volumes**, omitting all five attributes above in every single one. Not
   one volume in the dataset carries any of them.

   This is worth stating next to the list because the list alone reads as though the
   omissions were exceptional. They are not: **for RETOUCH-derived data the strict path
   of SRS-062 is unreachable**. It is implemented and tested (TC-026), and it will never
   execute on this dataset, because the caller has nothing to supply. A reader assessing
   conformance should assume every object this project produces from RETOUCH is missing
   all five, rather than treating it as a per-volume question.

   The strict path remains the default and remains correct. It is what makes the
   exception an exception — the writer refuses by default and must be told, per run, to
   omit rather than fill. But nothing about this dataset can satisfy it.

   **This sits alongside the unregistered UID root in item 1.** Both are reasons the
   objects this project creates must not be transmitted beyond the local Orthanc
   instance.

4. **Frame of Reference is present although its condition is not met.** Table A.52.3-1
   makes the module conditional — "Required if Ophthalmic Photography Reference Image
   available or if Ophthalmic Volumetric Properties Flag (0022,1622) is YES. **May be
   present otherwise.**" Neither trigger applies here, and the module is included under
   that last clause.

   **It is an identifier, not an anatomical claim.** That sentence is why this
   conditional module is populated while Ocular Region Imaged in item 3 is not. The UID
   is minted by this software and asserts only that the frames of a single volume share
   a frame of reference — true by construction, in the same category as a Study Instance
   UID. `ImageLaterality` asserts a fact about a body, which no declaration by this
   software can make true. The two are different in kind, and that difference, not
   convenience, decides which conditional attributes are written.

   It is included because a multi-frame DICOM Segmentation cannot be built without one:
   the SEG IOD needs a shared spatial frame to relate its frames to the source.

   Plane Position and Plane Orientation follow from the same decision. Both are usage C
   in Table A.52.4.3-1 and **required** in our case, since no Ophthalmic Photography
   Reference Image is available. Their values are expressed in the frame of reference
   this object declares for itself, where the row and column directions and the frame
   positions are exact by definition rather than estimates. Frame positions step by the
   recorded B-scan separation, so the spacing governing the volume computation appears
   twice in the object — once in Pixel Measures as `SliceThickness`, once as the step
   between consecutive `ImagePositionPatient` values. **That redundancy is the point.** A
   declared geometry can be cross-checked against itself; a fabricated value can be
   cross-checked against nothing. TC-024 asserts the two agree, so a defect in either is
   detectable rather than silent (HAZ-012).

5. **Coded concepts: verified, caller-supplied, or declared local — never invented.**
   Checked against the concept dictionary pydicom ships, which carries the standard's
   tables:

   | Concept | Status |
   |---|---|
   | Segmented property category | `SCT 49755003 Morphologically Abnormal Structure` — verified, used |
   | Anatomic region | `SCT 5665001 Retina` — verified, used |
   | Measurement name, volume | `SCT 118565006 Volume` — verified, used |
   | Units `mm3`, `{counts}`, `1` | UCUM, all three verified, used |
   | Segmented property type for IRF, SRF, PED | **no verified code found for any of the three** — declared private scheme, caller may override |
   | Measurement names for voxel count and confidence | **no verified generic concept found** — caller-supplied, no default |

   **What was searched.** The concept dictionary pydicom ships, which carries the
   standard's own tables across SCT, DCM, UCUM, LN, FMA and ten other schemes — 10,751
   SCT keywords among them. Searched for "retinal fluid", "subretinal", "pigment
   epithelial", "detachment" and "macular edema". **Nothing verifiable was found for any
   of the three fluid classes.** The same search did verify the segment category, the
   retinal anatomic region, the volume measurement name and all three units, so the
   absence is a finding about the vocabulary rather than a failure to look.

   **Decision: a declared private coding scheme**, `99OCUVAL`, implemented in
   `ocuval.report.coding` (SRS-065). Omission is not available — the Segmentation IOD
   requires the segment type — so the alternatives were a private scheme or a borrowed
   standard code that approximately fits.

   **The borrowed code was rejected.** It is the `AnatomicRegionSequence` decision in
   item 3 inverted: rather than declining to write a code that could not be verified, it
   writes one that *looks* interoperable while meaning something slightly different to
   every reader, with nothing in the object marking the approximation. A private scheme
   is honest and unambiguously non-interoperable, which is the true state of this
   vocabulary.

   **The scheme is declared inside the object.** PS3.3 C.12.1 makes `CodingSchemeUID`
   Type 1C, "Required if Coding Scheme is identified by an ISO 8824 object identifier",
   so the scheme is identified by an OID under this project's root and carries its name
   and responsible organisation. `CodingSchemeRegistry` and `CodingSchemeExternalID` do
   not apply: the scheme is not registered, and the object says so by their absence. A
   bare `99OCUVAL` designator with no identification sequence would be a local string
   telling a reader nothing.

   **Interoperability consequence, stated plainly.** No other system will interpret
   these codes. A consumer can determine that they are local, who issued them and what
   they mean in prose, and can map them deliberately — but no automatic interpretation
   is possible and none should be attempted. That is a real cost, accepted because the
   alternative is a silent misinterpretation rather than an obvious gap.

   Callers with verified codes from a scheme they trust pass them instead; the private
   scheme is then neither used nor declared (SRS-065, TC-076).

6. **Out-of-scope input criteria unresolved.** SRS-048 requires rejection of
   out-of-scope acquisitions; which attributes establish that is not known until the
   conversion in milestone 3 exists (`docs/02` §6 item 2).
