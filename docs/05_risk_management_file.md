<!--
Document: Risk Management File (ISO 14971)
Status: DRAFT v0.1
Owner: Anurag Yadav
Last reviewed: 2026-09-17
Change history: docs/13_change_control_log.md

Allocates HAZ-001..HAZ-011 and RC-001..RC-020. Supersedes the interim identifiers
used before this document existed: HS-1..HS-7 in docs/03 §3 and DMP-C1..DMP-C10 in
docs/06. §3.1 and §4.1 carry the mappings. Like docs/03, this file assesses the
intended use in docs/01 as if it were real.
-->

# Risk Management File (ISO 14971)

## 1. Scope and risk policy

### 1.1 What this file covers

Risk arising from the OcuVal software system in the intended use stated in `docs/01`: a
pre-read for a supervised reading-centre grader in a retrospective research or
clinical-trial reading workflow. The software safety class assigned in `docs/03` is
**B**, and the harm pathway is endpoint corruption rather than point-of-care error.

As in `docs/03` §1.1, the analysis treats that intended use as real. The repository as
it exists is not deployed and its actual residual risk is nil.

Clause references to ISO 14971 and IEC 62304 carry the caveat in `docs/03` §1.2: they
are corroborated across secondary sources but unverified against normative text.

### 1.2 Probability policy — the part that governs everything below

IEC 62304 requires the probability of a software failure to be taken as **100%** for
classification. Carrying that into risk estimation naively would make every probability
identical and the analysis useless, so this file decomposes probability the way ISO
14971 permits:

- **P1** — probability that the hazardous situation occurs, given the software fails.
  **Taken as 1 throughout.** No row below reduces risk by arguing the code is reliable.
- **P2** — probability that the hazardous situation leads to harm. Estimated per hazard,
  and this is where the workflow, the controls, and the structural bounds in `docs/01`
  actually do their work.

Every probability in §3 is a **P2**. This is the only honest way to run a software risk
analysis that is not permitted to claim reliability.

### 1.3 Two kinds of harm

The hazards below produce harm of two kinds, and collapsing them would hide the more
likely one:

- **Harm to a person** — the ISO 14971 sense. Reachable only through a corrupted study
  or trial endpoint influencing a later clinical decision, across several independent
  organisations. Bounded at non-serious injury by `docs/03` §5.2.
- **Harm to data integrity and to the research record** — a wrong measurement recorded,
  a biased endpoint, a misleading published result. Not personal injury, far more
  likely, and the thing this software can actually cause on its own.

Severity below scores harm to a person, because that is what ISO 14971 asks for. Where
the data-integrity harm is materially worse than the personal-harm score suggests, the
row says so. **A low severity score in §3 is not a statement that the failure does not
matter.**

## 2. Risk acceptability criteria

### 2.1 Severity of harm to a person

| Level | Meaning |
|---|---|
| S1 | Negligible — no injury; inconvenience or data loss only |
| S2 | Minor — non-serious, reversible injury, or a delay in care not causing lasting effect |
| S3 | Serious — injury requiring intervention, or lasting impairment |
| S4 | Death |

`docs/03` §5.2 concluded that the intended use structurally excludes S3 and S4: no
individual's care depends on an output. **S3 appears nowhere in §3 by construction, not
by optimism** — if a row ever needs S3, the intended use has changed and the
classification is void.

### 2.2 Probability (P2) that the hazardous situation leads to harm

| Level | Meaning |
|---|---|
| P-A | Improbable — requires several independent failures outside this software |
| P-B | Remote — plausible but requires an unlikely combination |
| P-C | Occasional — expected to occur over the life of a study |
| P-D | Frequent — expected in routine use |

### 2.3 Acceptability matrix

| | P-A | P-B | P-C | P-D |
|---|---|---|---|---|
| **S1** | Acceptable | Acceptable | Acceptable | ALARP |
| **S2** | Acceptable | ALARP | ALARP | **Unacceptable** |
| **S3** | ALARP | **Unacceptable** | **Unacceptable** | **Unacceptable** |

**ALARP** means the risk is tolerable only with controls in place and the residual
recorded. An **Unacceptable** residual blocks release.

### 2.4 A criterion this project adds

A risk whose realisation would be **invisible in normal use** is escalated one
probability band when its residual is evaluated, regardless of estimate. A wrong result
that announces itself is recoverable; one that does not is not. This is the criterion
that drives HAZ-005, and it exists because `docs/03` §4.1 established that the dominant
failure mode is the one review is least able to catch.

## 3. Hazard analysis

### 3.1 Identifier mapping

| This file | Supersedes |
|---|---|
| HAZ-001..HAZ-007 | HS-1..HS-7 in `docs/03` §3, in order |
| HAZ-008..HAZ-011 | New here — not identified in `docs/03`, which scoped itself to the output path |
| HAZ-015 | New here. **Distinct from HAZ-004 and HAZ-012.** HAZ-004 is a real value attached to the wrong subject; HAZ-012 is a real value corrupted in transit; HAZ-015 is a value that never existed being created to satisfy a format requirement. The first two corrupt data, the third manufactures it |
| HAZ-012 | New here. **Not a segmentation failure.** `docs/03` HS-1..HS-3 all concern the mask being wrong; HAZ-012 is the mask being right and the measurement being wrong anyway, which no HS covers and which none of the mask-directed controls reach |
| HAZ-013, HAZ-014 | New here, from the SOUP anomaly findings in `docs/04` §2.2 |

`docs/03` keeps its HS-n labels as written; they are not reissued retrospectively. This
table is the join.

### 3.2 Analysis

P1 is 1 in every row (§1.2). The Prob column is P2.

| ID | Hazard | Foreseeable sequence of events | Hazardous situation | Harm | Sev | Prob | Risk | Controls |
|---|---|---|---|---|---|---|---|---|
| HAZ-001 | Under-segmentation — fluid present, reported absent or smaller | Model misses small or boundary lesions → candidate looks plausible → grader accepts under automation bias → understated volume recorded → enters study endpoint | Recorded measurement understates disease | Data integrity; via a biased endpoint, eventual non-serious injury | S2 | P-A | ALARP | RC-006, RC-009, RC-017 |
| HAZ-002 | Over-segmentation — spurious or inflated fluid | Noise or artefact segmented as fluid → accepted at review → overstated volume recorded | Recorded measurement overstates disease | As HAZ-001 | S2 | P-A | ALARP | RC-006, RC-009, RC-017 |
| HAZ-003 | Fluid assigned to the wrong compartment | IRF/SRF/PED confusion, or label indices reordered → an endpoint defined on one compartment is computed on another | A compartment-specific endpoint is silently wrong | Data integrity; misattributed clinical meaning | S2 | P-A | ALARP | RC-020, RC-006, RC-017 |
| HAZ-004 | Result attributed to the wrong patient, eye or acquisition | Pseudonym collision, UID collision, or manifest index error → SEG/SR attached to the wrong study → recorded against a subject it did not come from | A measurement is recorded against the wrong person | Data integrity; a person's record carries another's measurement | S2 | P-B | ALARP | RC-012, RC-013, RC-015, RC-008 |
| HAZ-005 | **Undetected vendor-correlated systematic bias** | Model performs materially worse on one platform → evaluation does not break results out per vendor, or does so wrongly → bias is invisible case by case → platform correlates with site or study arm → bias confounded with the effect under study | Every measurement from one platform is biased in the same direction | Data integrity at study scale; a wrong efficacy conclusion | S2 | P-B → **escalated to P-C under §2.4** | **ALARP, highest residual in this file** | RC-005, RC-006, RC-007, RC-008, RC-016 |
| HAZ-006 | Out-of-scope acquisition processed | DME, OCTA, en-face, non-macular or unlisted platform submitted → no rejection → confident-looking result returned outside any validated domain | A measurement is produced where no performance claim exists | Data integrity; unwarranted confidence | S2 | P-B | ALARP | RC-010, RC-014 |
| HAZ-007 | Low-confidence result not flagged | MC-dropout confidence wrong, absent, or not carried into the SR → the one signal designed to counteract over-acceptance is missing | Grader reviews a low-confidence result as if routine | Compounds HAZ-001, HAZ-002 | S2 | P-B | ALARP | RC-009 |
| HAZ-008 | Patient overlap between splits inflates the reported performance | B-scans from one patient land in train and test → Dice reflects memorisation → published figure is optimistic → graders and readers trust the output more than the evidence supports | Every downstream use rests on an overstated claim | Data integrity; **weakens RC-017, so it degrades the control on every other hazard** | S2 | P-B | ALARP | RC-001, RC-002, RC-003, RC-004 |
| HAZ-009 | De-identification failure leaves an identifier in an output object | Profile not applied, or applied and not verified → object carrying an identifier is stored or shared | An identifier persists where it must not | Privacy. No PHI exists in this project's data, so realised harm is nil here — the control is demonstrated, not relied on | S1 | P-A | Acceptable | RC-011, RC-012, RC-030 |
| HAZ-010 | SEG or SR fails to reference its source instances correctly | Referencing wrong or absent → grader cannot open the result against the images it came from, or it attaches to the wrong study | The result is unreviewable, or reviewable against the wrong images | Defeats the precondition of RC-017 | S2 | P-B | ALARP | RC-013, RC-015 |
| HAZ-011 | Output object leaves its context without its research-use designation | SEG or SR copied out of the repository or the local PACS → nothing in the object says it is research-use-only and automated → treated as a validated clinical result | An unvalidated measurement is read as a clinical one | The one hazard whose harm is *increased* by the artefact being well-formed | S2 | P-B | ALARP | RC-014, RC-019 |
| HAZ-012 | **Acquisition metadata corruption — voxel spacing wrong, absent, or altered in transit** | Axial resolution conventionally quoted in micrometres arrives unconverted (0.0039 mm read as 3.9 → a 1000× volume error) → or spacing is absent and silently defaulted → or anisotropic spacing is collapsed to isotropic → or a transform alters spacing between ingestion and volume computation → mm³ computed from a **correct** mask is wrong by a constant factor | A confidently wrong volume is recorded from a segmentation that is right | Data integrity; the recorded measurement is wrong by orders of magnitude while every visible artefact looks correct | S2 | P-B → **escalated to P-C under §2.4** | **ALARP — second-highest residual in this file** | RC-021, RC-022, RC-023, RC-024, RC-025, RC-026 |
| HAZ-013 | Checkpoint of unknown provenance or altered content is loaded | A checkpoint not produced by this project, or altered since it was written, is loaded → either the wrong model computes every result, or a crafted checkpoint executes code during deserialisation (`docs/04` §2.2, PyTorch and MONAI) | The system runs weights it did not produce | Data integrity; every output from that run is unattributable. In the deserialisation case, arbitrary code execution | S2 | P-A | ALARP | RC-028, RC-018 |
| HAZ-014 | DICOMweb client picks up ambient environment configuration | `.netrc`, proxy or certificate settings present in the environment are used by the HTTP client → credentials leaked to a third party on a crafted URL (`docs/04` §2.2, requests), or traffic silently redirected | Client behaviour depends on state outside the run configuration | Confidentiality of local PACS credentials; loss of reproducibility. No PHI is involved | S1 | P-B | Acceptable | RC-027, RC-018 |
| HAZ-015 | **Acquisition metadata that the source does not supply is fabricated to satisfy a mandatory DICOM attribute** | A required Type 1 attribute has no value in the source — laterality being the concrete case → a plausible value is written to make the object conformant → downstream the value is indistinguishable from a recorded fact, because DICOM has no way to mark a value provisional → a result is read as pertaining to an eye, position or orientation that was never recorded | An invented anatomical fact travels with the object, carrying the authority of the format | Data integrity; in the laterality case it is a measurement attributed to the wrong eye, which is HAZ-004's harm arriving by a different route | S2 | P-B | ALARP | RC-029, RC-014 |

## 4. Risk control measures

### 4.1 Identifier mapping

| This file | Supersedes |
|---|---|
| RC-019 | DMP-C1, DMP-C2, DMP-C3, DMP-C4, DMP-C5 |
| RC-001 | DMP-C6 |
| RC-002 | DMP-C7, DMP-C9 |
| RC-003 | DMP-C8 |
| RC-004 | DMP-C10 |

`docs/06` keeps its DMP-C labels; `docs/09` now carries RC identifiers in the RC column
and the interim entries are retired. `docs/06` §10 item 5 is closed by this.

### 4.2 Controls

Type follows the ISO 14971 hierarchy: **Design** (inherent safety), **Protective**
(detection or barrier), **Information** (labelling, user procedure). The hierarchy is an
order of preference — information for safety is the weakest.

| ID | Control | Type | Implements | Implemented in | Verified by (TC) |
|---|---|---|---|---|---|
| RC-001 | Splitting confined to one module; nothing else may partition data | Design | SRS-018 | `data/splits.py` | TC-003 |
| RC-002 | Patient-level disjointness asserted at split construction and again at start of training; exception never caught | Protective | SRS-019, SRS-020 | `data/splits.py` | TC-004 |
| RC-003 | The disjointness test gates CI and is never skipped or weakened | Protective | NFR-005 | `.github/workflows/ci.yml` | TC-004 |
| RC-004 | Splits seeded, persisted and reproducible from committed configuration | Design | SRS-023, NFR-002 | `data/splits.py` | TC-041 |
| RC-005 | Test split contains only the held-out vendor | Design | SRS-021 | `data/splits.py` | TC-004 |
| RC-006 | Per-class and per-vendor reporting with bootstrap CI and sample size | Protective | SRS-032, SRS-033, SRS-036, SRS-037, SRS-053 | `eval/metrics.py`, `eval/subgroup.py` | TC-060, TC-061, TC-063, TC-064, TC-068 |
| RC-007 | Accuracy is not provided and not reported | Design | SRS-035 | `eval/metrics.py` | TC-002 |
| RC-008 | Vendor preserved through conversion, de-identification and into evaluation output | Design | SRS-009, SRS-017 | `io/dicom_writer.py`, `io/deident.py` | TC-023, TC-035, TC-110 |
| RC-009 | MC-dropout scan-level confidence and review-recommended indication, carried in the SR | Protective | SRS-029, SRS-030, SRS-041 | `models/uncertainty.py`, `report/sr_object.py` | TC-055, TC-056, TC-076 |
| RC-010 | Out-of-scope input rejected with a stated reason, no segmentation returned | Protective | SRS-004, SRS-048 | `io/retouch_reader.py`, `service/api.py` | TC-092 |
| RC-011 | Confidentiality profile applied and verified; non-empty verification aborts the run | Protective | SRS-012, SRS-015, SRS-016 | `io/deident.py` | TC-030, TC-033, TC-034 |
| RC-012 | Salted-hash pseudonyms, salt from environment, stable within a run | Design | SRS-013, SRS-014 | `io/deident.py` | TC-031, TC-032 |
| RC-013 | SEG references the source image instances it was derived from | Design | SRS-039 | `report/seg_object.py` | TC-071 |
| RC-014 | Research-use-only designation carried inside every output object | Information | SRS-042 | `report/seg_object.py`, `report/sr_object.py` | TC-077, TC-081 |
| RC-015 | UIDs generated under the configured root and recorded in the run output | Design | SRS-007, SRS-008 | `io/dicom_writer.py` | TC-021, TC-022 |
| RC-016 | Native acquisition geometry preserved; no cross-vendor resampling | Design | SRS-010, SRS-026 | `io/dicom_writer.py`, `data/transforms.py` | TC-024, TC-052 |
| RC-017 | Human review required before any result is recorded; no automated action and no sign-off endpoint | Information | SRS-045, SRS-047 | `io/dicomweb.py`, `service/api.py` | TC-082, TC-091 |
| RC-018 | Outputs attributable to model version, resolved config and seed | Protective | SRS-031, SRS-049 | `ocuval/__init__.py`, `service/api.py` | TC-057, TC-093 |
| RC-019 | Data governance — no redistribution, no commercial use, scope limited to fluid segmentation and detection, single registered user | Information | NFR-004 | `.gitignore`, `.pre-commit-config.yaml` | TC-100 |
| RC-020 | Label indices and vendor keys frozen in configuration; reordering is a requirements change | Design | SRS-002 | `configs/data.yaml` | TC-001 |
| RC-021 | Voxel spacing carried as a first-class field, on the same terms as vendor, through every stage | Design | SRS-054 | `io/retouch_reader.py`, `io/dicom_writer.py`, `io/deident.py` | TC-016, TC-110 |
| RC-022 | Spacing asserted present at ingestion; no default or fallback value exists anywhere; absence aborts | Protective | SRS-055 | `io/retouch_reader.py` | TC-005, TC-014 |
| RC-023 | Per-vendor spacing plausibility range in configuration; out-of-range **rejects** the volume rather than warning | Protective | SRS-056 | `io/retouch_reader.py`, `configs/data.yaml` | TC-015 |
| RC-024 | Spacing used for volume computation asserted bit-identical to spacing recorded at ingestion | Protective | SRS-057 | `report/sr_object.py` | TC-072, TC-073 |
| RC-025 | Units declared explicitly in the SR, never implied by convention | Design | SRS-058 | `report/sr_object.py` | TC-074 |
| RC-026 | Voxel count and voxel volume recorded alongside mm³ so the derivation is auditable from the object alone | Protective | SRS-059 | `report/sr_object.py` | TC-072, TC-075 |
| RC-027 | DICOMweb client takes configuration only from the run configuration; `trust_env=False`, no ambient `.netrc`, proxy or certificate settings | Design | SRS-060 | `io/dicomweb.py` | TC-083 |
| RC-028 | Checkpoints loaded only from the project's own `artifacts/` directory, hash recorded at write time and verified before load; mismatch or missing hash aborts | Protective | SRS-061 | `models/seg_unet.py`, `service/api.py` | TC-058 |
| RC-030 | **No reidentification, and no attempt at it.** No linkage of this data to any external dataset, no demographic inference, no attempt to recover subject identity from image content or metadata. Technically supported by the one-way salted-hash pseudonyms of SRS-013 whose salt is never committed, so the project's own outputs cannot be relinked by a reader of the repository | Information + Design | SRS-013, SRS-014 | `io/deident.py` | TC-031 (technical half only — see §4.4) |
| RC-029 | **Refuse, or omit — never fill.** Acquisition context absent from the source must be supplied explicitly by the caller or the conversion aborts; under an explicitly enabled research exception the affected module is omitted entire and the omission logged and recorded, never populated with a substituted value | Design | SRS-062, SRS-063, SRS-064 | `io/dicom_writer.py` | TC-026, TC-027, TC-028 |

### 4.3 RC-017 is deliberately typed as Information

RC-017 — mandatory human review — is the control most often mistaken for a Design or
Protective measure. It is neither. It is a procedure the user performs, which places it
at the weakest level of the ISO 14971 hierarchy, and `docs/03` §4.1 established why that
matters here: automation bias makes review weakest against exactly the subtle,
systematic errors that are most likely and most damaging.

Typing it honestly has a consequence visible in §5: **no hazard in this file reaches an
acceptable residual on the strength of RC-017 alone.**

### 4.4 RC-030 is half technical and half undertaking

RC-030 comes from the signed Agreement of Data Confidentiality, which obliges the
recipient not to reidentify the data or attempt to (`docs/06` §2.1). It has two halves
and only one of them is testable.

The **technical half** is real and verified: pseudonyms are one-way salted hashes and the
salt is never written to a committed file or run output (SRS-013), so nothing this
project publishes can be relinked to a source identifier by a reader. TC-031 exercises
it.

The **procedural half** — not attempting reidentification by other means, such as
linkage to an external dataset or inference from image content — is an undertaking by
the recipient. No test can verify that someone did not try something. Recording it as a
control with a test would overstate what is assured, so it is recorded as an undertaking
and the test allocation covers the technical half only.

This is the same distinction `docs/03` §4.1 draws about human review: a control that
depends on a person behaving as intended is real, weaker than a mechanism, and must not
be written up as though it were one.

## 5. Residual risk evaluation

### 5.1 Per hazard

| ID | Residual after controls | Rationale |
|---|---|---|
| HAZ-001, HAZ-002 | ALARP | RC-006 makes a systematic version of this visible in evaluation; RC-009 flags the low-confidence cases; RC-017 catches gross cases only. The residual is the subtle, individually plausible error that passes review — irreducible with the controls available |
| HAZ-003 | ALARP | RC-020 and TC-001 make index reordering a hard failure rather than a silent one. Residual is genuine model confusion between compartments, which RC-006 surfaces per class |
| HAZ-004 | ALARP | RC-012, RC-013 and RC-015 address the mechanisms. Residual is dominated by the unregistered UID root (`docs/06` §7.1): UIDs carry no claim of global uniqueness, which is accepted only because objects never leave the local Orthanc instance |
| HAZ-005 | **ALARP — the highest residual in this file** | RC-006 is the only control that can surface it, and RC-006 is *inside the software whose failure is assumed*. There is no external control for this hazard: §2.4 escalates it for invisibility, ERC-5 aggregation is ineffective against systematic bias, and RC-017 cannot see it case by case. See §5.2 |
| HAZ-006 | ALARP | RC-010 is the control; its criteria are unresolved until milestone 3 (`docs/02` §6 item 2), so the residual is currently larger than the table implies |
| HAZ-007 | ALARP | RC-009 is single-point: if the confidence path fails, nothing else detects it. No independent check exists |
| HAZ-008 | ALARP, **lowest residual in this file** | The strongest control set here — RC-001 through RC-005, four of five now verified by passing tests including the CI gate. `splits.py` is implemented and assigns patients rather than slices, so slice-level leakage is prevented by construction rather than detected. Residual is that RC-001, the prohibition on other modules partitioning data, is still unverified: TC-003 is a static check and is not written |
| HAZ-009 | Acceptable | Harm is nil in this project: the data contains no PHI. The control is implemented and verified to demonstrate the capability, not because this dataset needs it |
| HAZ-010 | ALARP | RC-013 addresses it; nothing verifies reviewability end to end, which would need a round-trip through a real viewer rather than a round-trip through Orthanc |
| HAZ-011 | ALARP | RC-014 is Information-type and its mechanism is unresolved (`docs/11` §10 item 2). Until that is settled the control is specified but not realised |
| HAZ-012 | **ALARP — second-highest residual** | RC-022 and RC-023 remove the two silent paths: nothing defaults, and an implausible value is rejected rather than logged. RC-024 closes the in-transit case. RC-026 makes the derivation auditable after the fact. But **every one of these controls is inside the software whose failure is assumed**, and RC-017 reaches none of them — a grader reviewing a correct mask has no way to see that the millimetres are wrong. See §5.4 |
| HAZ-013 | ALARP | RC-028 is the control on which `docs/04` accepts the PyTorch and MONAI deserialisation findings (§5.5). Residual is the case where the recorded hash itself is wrong, which nothing independently checks |
| HAZ-014 | Acceptable | RC-027 removes the mechanism entirely rather than mitigating it. No PHI is involved and the only credentials are to a local Orthanc instance. **The control is over-broad** — it also disables proxy and CA-bundle environment settings, which would break the client in the reading-centre environment `docs/01` §4 describes (`docs/04` §2.6). Correct here, wrong there, and stated rather than fixed |
| HAZ-015 | ALARP | RC-029 removes the fabrication path by construction: there is no code path that supplies a value the source did not. The residual is that omission produces a **non-conformant** object (`docs/11` §10 item 3), which is a real cost accepted deliberately — a missing Type 1 attribute is flagged by any validator, an invented one is not, and DICOM offers no way to mark a value provisional |

### 5.2 HAZ-005 — stated plainly

The project's headline contribution is measuring cross-vendor degradation. HAZ-005 is
the hazard that the measurement is itself wrong or absent, and it has a structural
problem no amount of control design fixes: **the only thing that can detect it is the
evaluation code, which is part of the software system whose failure is assumed.**

This restates, from the risk side, the conclusion `docs/03` §5.1 reached from the
classification side: the per-vendor reporting that would surface a systematic bias is
inside the software and so cannot be credited as an external control. The two documents
are making the same argument about the same hazard, and neither is independent evidence
for the other.

No external risk control reaches it. Grader review cannot see a systematic bias in a
single case. Statistical aggregation does not dilute it. Supervision does not address
it. It is reduced by RC-006, RC-008, RC-007 and RC-005, and what remains is accepted for
one reason only: the structural bound in `docs/01` that no individual's care depends on
an output. Remove that bound and this hazard alone would force the classification to be
reopened.

### 5.4 HAZ-012 — why the mask-directed controls do not reach it

Everything in §4.2 that addresses a wrong measurement addresses a wrong **mask**.
HAZ-012 is the case where the mask is right.

A volume in cubic millimetres is voxel count × voxel volume, and voxel volume comes
entirely from spacing metadata. SRS-010 and SRS-026 forbid resampling the *image* across
vendors; neither says anything about the metadata, and that asymmetry is the hole. The
OCT-specific version is concrete: axial resolution is conventionally quoted in
micrometres, so a spacing that should read 0.0039 mm arriving as 3.9 is a thousand-fold
volume error in which every pixel, every contour and every review screen looks exactly
as it should.

This is why RC-017 is worth nothing here, and why §2.4's invisibility escalation applies.
A grader is asked to check a segmentation. They are not asked, and have no means, to
check that the millimetres attached to it were derived from the right number.

### 5.5 HAZ-013 — the basis on which the SOUP findings are accepted

`docs/04` §2.2 records that PyTorch 2.3.1 and MONAI 1.3.2 are affected by deserialisation
defects on the model-loading path. Both are **accepted rather than remediated**, and
RC-028 is the basis.

The threat in both advisories is a maliciously crafted model file. This system loads
exactly one class of file: checkpoints it produced itself, from its own `artifacts/`
directory, hash-verified against the value recorded when they were written. The intended
use excludes loading a third-party checkpoint, and SRS-061 makes that a requirement
rather than a habit.

Bumping PyTorch to 2.6 to close a threat the intended use already excludes would move
MONAI with it, invalidate the SOUP assessment of both, and change the numerical
behaviour of every trained model — a large, coupled change to chase a risk that RC-028
addresses directly. That is the wrong trade, and the rationale is recorded here so the
acceptance is a decision rather than an omission.

The acceptance is conditional on RC-028 actually existing. Until `src/` is implemented it
does not, and §5.3 applies.

### 5.3 Controls not yet real

Every one of the 28 controls in §4.2 carries a test case from `docs/07`. **Nine are
verified by a passing test as of 2026-09-17** — RC-002, RC-003, RC-004 and RC-005
(splitting), RC-006 and RC-007 (metrics), RC-020 (frozen contract), RC-024 and RC-026
(volume derivation). The other 19 name a test case specified and not yet written.

HAZ-008's control set is now real rather than planned: `data/splits.py` is implemented
and TC-004 passes for the first time, having been a strict xfail until 2026-09-17. The rest carry `TBD` and are specified
but unverified, because `src/` is stubs and `docs/07` is not drafted.

This file therefore describes a control set that is, as of 2026-09-17, mostly a plan.
That is accurate for milestone 2 and is not a defect in the analysis, but no statement
in §5.1 should be read as describing controls in operation.

## 6. Risk/benefit and overall residual risk statement

### 6.1 Overall residual risk

Every hazard is ALARP or Acceptable. None is Unacceptable, so nothing here blocks
release on its own terms. That conclusion rests on three things, and it is worth being
explicit that two of them are properties of the workflow rather than achievements of the
software:

1. **The structural bound.** No individual's care depends on any output (`docs/01` §5).
   This is what holds severity at S2 across the entire file.
2. **The bounded deployment.** Objects never leave the local Orthanc instance
   (`docs/06` §7.1), which is what makes the unregistered UID root tolerable.
3. **The control set in §4.2** — which is largely specified rather than implemented
   (§5.3).

### 6.2 Risk/benefit

ISO 14971 asks whether the benefit outweighs the residual risk. For a deployed device
this is a clinical judgment. For this project the honest answer is narrower: **there is
no clinical benefit to weigh, because there is no clinical use.** The benefit is
methodological — a quantified, per-vendor characterisation of how a fluid segmentation
model degrades across scanner platforms, reported with intervals and sample sizes, which
is information the field has too little of.

Against that, the residual risks above are tolerable because the workflow interposes a
competent human and an aggregated endpoint between the software and any patient, and
because the software makes no claim its evaluation does not support.

**This is not a statement that the software is safe to use clinically. It is not, it is
not validated for it, and `docs/01` §5 forbids it.**

### 6.3 Conditions on this conclusion

This evaluation is void if any of the following changes, and each requires the file to
be reopened rather than amended:

- `docs/01` §2 indications widen, or any output comes to inform an individual's care
  (`docs/03` §5.2 and §8 item 6).
- Objects are transmitted beyond the local Orthanc instance.
- The per-vendor reporting in RC-006 is weakened, aggregated or dropped — it is the only
  control reaching HAZ-005.
- TC-004 is skipped, weakened or removed, which would return HAZ-008 to an uncontrolled
  state.

## 7. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | ~~24 of 28 controls have no verifying test.~~ **Partly resolved 2026-09-17:** `docs/07` allocates a test case to all 28. 24 of those test cases are unimplemented (§5.3). Every RC needs a TC in `docs/07`; CLAUDE.md §3 requires each risk control to trace to a requirement and each requirement to a test. | `docs/07` |
| 2 | RC-010's criteria are unresolved until the converted DICOM exists, so HAZ-006's residual is larger than §5.1 states. | Milestone 3 |
| 3 | RC-014's mechanism is unresolved (`docs/11` §10 item 2), so HAZ-011 is specified but uncontrolled in practice. | `docs/11` |
| 4 | RC-009 is a single-point control for HAZ-007 with no independent check. Whether that is acceptable, or whether a second signal is needed, is undecided. | `docs/07` |
| 5 | **No risk control reaches URS-002.** Surfaced by deriving `docs/09`: SRS-003, SRS-040 and SRS-046 — the path that computes and reports the fluid volume in mm³ — carry no RC, although a wrong volume is precisely the harm in HAZ-001 and HAZ-002. The controls there act on the segmentation, not on the derivation from segmentation to millimetres. Either that derivation gets its own control or the analysis must say why it needs none. | `docs/07` |
| 6 | ~~The SOUP findings in `docs/04` §2.2 are not represented as hazards here.~~ **Resolved 2026-09-17:** HAZ-013 and HAZ-014 carry the PyTorch/MONAI and requests findings, controlled by RC-028 and RC-027. python-multipart was remediated by version bump instead (`docs/04` §2.5), so it needs no hazard here. | — closed |
| 7 | RC-028 depends on a recorded checkpoint hash, and nothing independently verifies that the recorded hash is itself correct. The control degrades to trust-on-first-write. | `docs/07` |
| 8 | No post-release risk monitoring or production feedback process exists, which ISO 14971 expects. Nothing consumes field experience because there is no field. | — |
