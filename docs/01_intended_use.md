<!--
Document: Intended Use and User Requirements
Status: DRAFT v0.1
Owner: Anurag Yadav
Last reviewed: 2026-09-16
Change history: docs/13_change_control_log.md

Scope of this document: it defines what the software is for and who uses it, and
allocates URS-001..URS-011. It deliberately claims nothing about performance
beyond the requirement that performance be characterised and reported (URS-007).
The dataset characteristics that constrain what may be claimed are in docs/06
sections 1.3, 3.1 and 3.2 and are restated as limitations in section 6 here.
-->

# Intended Use and User Requirements

## 1. Intended use statement

OcuVal is research software that produces a **candidate** voxel-wise segmentation of
three retinal fluid compartments — intraretinal fluid (IRF), subretinal fluid (SRF) and
pigment epithelial detachment (PED) — from a single macular spectral-domain OCT volume
acquired on one of three scanner platforms (Zeiss Cirrus, Heidelberg Spectralis,
Topcon), together with a per-class fluid volume in mm³ for the imaged eye and a
scan-level confidence estimate. It is intended for use by a trained reading-centre
grader or image analyst, working under the supervision of a retinal specialist, as a
**pre-read** within a retrospective research or clinical-trial reading workflow: the
software proposes, the grader reviews, corrects and records. No output of this software
constitutes an assessment until a grader has acted on it.

## 2. Indications for use

| Dimension | In scope |
|---|---|
| Modality | Spectral-domain OCT, macular cube acquisitions |
| Scanner platforms | Zeiss Cirrus, Heidelberg Spectralis, Topcon — macular cube protocols as represented in the RETOUCH dataset |
| Anatomy | Macula |
| Disease | Macular edema secondary to neovascular AMD and to retinal vein occlusion (RVO) |
| Findings | IRF, SRF, PED — as defined by the RETOUCH reference standard (`docs/06` §1.1) |
| Unit of analysis | One acquisition, one eye |
| Population | Adult |

The finding definitions are inherited from the RETOUCH reference standard, not
independently specified. Where that standard's conventions are ambiguous, the ambiguity
propagates into this software and is not resolved by it.

## 3. Intended user and required competence

The intended user is a **trained reading-centre grader or image analyst** operating in a
research or clinical-trial reading workflow, supervised by a retinal specialist. This
mirrors the provenance of the reference standard itself (`docs/06` §1.2): the software
is intended to assist the same class of user who produced the annotations it learned
from.

Assumed competence, stated explicitly because the risk analysis in `docs/05` depends on
it:

- trained in the identification and grading of retinal fluid on OCT B-scans;
- able to recognise an incorrect segmentation — including one that is plausible but
  wrong — and to correct or reject it;
- familiar with the reading workflow's own recording and sign-off conventions;
- working under retinal specialist supervision, with escalation available.

The software is **not** intended for use by a clinician at the point of care, by an
imaging technician, by an untrained annotator, or by a patient.

## 4. Intended use environment

An offline research or reading-centre workstation, or a reading-centre server, operating
on retrospectively acquired and de-identified OCT volumes. Results are written as DICOM
Segmentation and Structured Report objects to a local PACS. There is no point-of-care
deployment, no real-time or intra-operative use, no use on live acquisition, and no
connection to any system that acts on the output automatically.

## 5. What this software is not

> This is a research and portfolio artefact built on public challenge data. It has
> not been clinically validated, carries no regulatory clearance, and must not be
> used in patient care.

To be unambiguous, the statement above is the governing one and is restated here rather
than delegated to the README. Specifically, OcuVal is **not**:

- a diagnostic device, and it diagnoses nothing;
- a treatment-monitoring tool — it does not support longitudinal comparison of fluid
  between visits, and no requirement in §7 concerns change over time (see §6, L4);
- a triage or prioritisation system;
- an autonomous system — it takes no action and releases no result on its own
  authority (URS-003);
- a replacement for grader judgment, and it is not validated to reduce grading time,
  grader workload, or inter-grader variability. No such claim is made or tested.

## 6. Limitations and contraindications

### 6.1 Stated limitations

These follow from the dataset and are not defects to be fixed; they bound what may ever
be claimed. Each is carried into `docs/10` and `docs/12`.

| ID | Limitation |
|---|---|
| L1 | **Small evaluation sets.** Only the RETOUCH training partition carries public annotations, so each held-out-vendor fold evaluates on roughly 22–24 subjects (`docs/06` §1.3). Confidence intervals will be wide; they are reported with the sample size visible, and a narrow interval from this data indicates a defect rather than a good model. |
| L2 | **Severe class imbalance.** Fluid occupies 0.55–1.26% of voxels (`docs/06` §3.2). Accuracy is meaningless here — a null predictor exceeds 98.7% — and is never reported (URS-007). |
| L3 | **Appearance shift and prevalence shift are not separable.** Prevalence varies by roughly five-fold across vendors for the same class (`docs/06` §3.2), so a cross-vendor performance gap cannot be attributed to appearance alone. |
| L4 | **Repeatability is entirely uncharacterised.** RETOUCH provides one volume per subject with no repeat acquisitions, so test–retest variability of the reported volumes has never been measured. No claim about measurement stability is made, and none may be inferred from the reported Dice or volume figures. |
| L5 | **Reference-standard variability is unquantified.** The released annotations were not double-graded and no per-case inter-rater agreement is published (`docs/06` §1.2). Every reported metric contains an unmeasured component of grader disagreement. |
| L6 | **Image quality is a confounder.** Cirrus volumes are reported as lower quality than the other two platforms (`docs/06` §3.3); a poor held-out-Cirrus result has at least two candidate explanations. |
| L7 | **One acquisition, one eye.** The software has no notion of a patient across studies, of fellow-eye comparison, or of prior imaging. |

### 6.2 Contraindications — out of scope, must not be processed

Inputs outside the following are out of scope. The software identifies and rejects them
rather than producing an unreliable result (URS-009).

- Any use on live patients or in patient care, in any setting.
- Diabetic macular edema, and any macular or retinal disease other than neovascular AMD
  and RVO.
- OCT angiography, en-face imaging, and any derived or projected view.
- Any imaging modality other than SD-OCT B-scan volumes — fundus photography, FA, ICG,
  ultrasound.
- Acquisitions that do not conform to the macular cube protocols of the three named
  platforms, including non-macular OCT (optic nerve head, anterior segment, widefield)
  and non-standard scan patterns.
- Scanner platforms other than Cirrus, Spectralis and Topcon, including later hardware
  or software revisions of those three not represented in RETOUCH.
- Paediatric acquisitions.

## 7. User requirements

Each requirement is written to be decomposable into at least one SRS requirement in
`docs/02` and verifiable by at least one test case in `docs/07`. SRS, hazard and test
allocations are TBD until those documents exist; `docs/09` tracks the gap.

| ID | Requirement | Rationale |
|---|---|---|
| URS-001 | The software shall accept a single macular SD-OCT volume from a Cirrus, Spectralis or Topcon scanner and produce a voxel-wise segmentation labelling exactly the three fluid classes IRF, SRF and PED, plus background, using the fixed label indices in `configs/data.yaml`. | This is the scope of the software. Fixing the classes and their indices in a requirement prevents scope drift and makes reordering — which would silently invalidate every checkpoint and every reported metric — a requirements change rather than an edit. |
| URS-002 | For each acquisition the software shall report a fluid volume in mm³ for each of the three classes, for the imaged eye, derived from the segmentation and the acquisition's voxel spacing. | Volume is the quantity a grader records; a mask alone does not serve the workflow in §1. Deriving it from per-acquisition spacing rather than an assumed value is what makes it comparable across platforms with different geometry (`docs/06` §3.1). |
| URS-003 | Every output shall be a candidate for grader review. The software shall take no automated action, shall not record or release a result on its own authority, and shall require an explicit grader action before any result enters a record. | The workflow in §1 is a pre-read. Human review reduces, but does not eliminate, the probability of an undetected error: automation bias is well documented, and a plausible but wrong segmentation is more readily accepted than an obviously wrong one. The residual is evaluated in `docs/03`. |
| URS-004 | The software shall present its output in a form the intended user can inspect against the source images and correct or reject, using standard DICOM tooling and without access to this software's source code. | The competence assumption in §3 is that the grader can recognise and correct a wrong segmentation. That is only true if the output is reviewable in their own tooling; an output that can only be inspected through bespoke tooling defeats URS-003 in practice. |
| URS-005 | Each output shall carry a scan-level confidence estimate and an explicit indication of whether review is recommended, recorded in the DICOM Structured Report and not only in run logs. | A confidence figure visible only in a log is not available to the grader at the moment of review, which is the only moment it matters. Placing it in the SR makes it travel with the result. `service/schemas.py` already models both fields (`confidence`, `review_recommended`). |
| URS-006 | The scanner platform shall be recorded as a first-class attribute of every sample and shall be preserved through conversion, de-identification, inference and into every evaluation output. | Per-vendor reporting (URS-007) is the project's headline result and is impossible if vendor identity is lost anywhere in the pipeline. De-identification is the most likely place to lose it, since manufacturer attributes sit near the identifiers being removed. |
| URS-007 | Performance shall be characterised and reported per fluid class and per scanner platform, each figure accompanied by a bootstrap 95% confidence interval and the sample size it was computed from. Accuracy shall not be reported. | Verifiable without asserting a performance floor this dataset cannot support (L1). The per-class and per-vendor breakdown is what makes a result interpretable given L2 and L3; a single aggregate figure would let total failure on the rarest class hide behind the most common one. |
| URS-008 | The software shall process each volume in its native acquisition geometry. It shall not resample volumes from different platforms into a common geometry as a precondition of inference or evaluation. | Slice count and axial resolution differ substantially across the three platforms (`docs/06` §3.1). That heterogeneity is part of the domain shift under study; harmonising it away would remove part of the effect the project exists to measure. |
| URS-009 | The software shall determine whether an input falls within the indications in §2 and shall reject out-of-scope input with a stated reason rather than returning a segmentation. | Without this, every contraindication in §6.2 is prose with nothing enforcing it. An out-of-scope volume that silently returns a confident-looking mask is the most direct route from "research artefact" to "misused result". The criteria by which conformance is judged are unresolved: they depend on what the converted DICOM objects actually carry, which is not known until milestone 3. The SRS derivation may therefore need to narrow this requirement once that lands. It is deliberately not narrowed here on speculation (§8, item 2). |
| URS-010 | Every output shall be attributable to the model version, resolved configuration and random seed that produced it, and shall be reproducible from the committed configuration alone. | Nothing in §6 can be honestly stated about a result that cannot be reproduced. This is also what makes a change to an evaluation definition detectable rather than silent (CLAUDE.md rule 6). This requirement spans two concerns that fail differently and verify differently: provenance — UID lineage, the de-identification record, source instance references — which is checked by inspecting an artefact, and determinism — seeds, persisted splits, pinned configuration — which is checked by running twice and diffing. They are kept as one requirement; if `docs/07` finds that unwieldy to verify, the cut runs along that seam. |
| URS-011 | Every output object shall carry, within the DICOM object itself, a designation — readable both by software and by a person — that the result is research-use-only, has not been clinically validated, and was produced by an automated method requiring human review. | §5 and the README both state this, but neither travels with the file, and a SEG or SR object is precisely the kind of artefact that is copied out of its context. This is the only such designation that survives the object leaving this repository. The requirement states the property rather than the mechanism: the conformant means of expressing it in a SEG and an SR is unresolved and is settled in `docs/11` (§8, item 1). |

### Allocation status

| URS | SRS | HAZ | TC |
|---|---|---|---|
| URS-001 | TBD | TBD | TBD |
| URS-002 | TBD | TBD | TBD |
| URS-003 | TBD | TBD | TBD |
| URS-004 | TBD | TBD | TBD |
| URS-005 | TBD | TBD | TBD |
| URS-006 | TBD | TBD | TBD |
| URS-007 | TBD | TBD | TBD |
| URS-008 | TBD | TBD | TBD |
| URS-009 | TBD | TBD | TBD |
| URS-010 | TBD | TBD | TBD |
| URS-011 | TBD | TBD | TBD |

## 8. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | The conformant expression of the URS-011 designation inside a DICOM SEG and SR is unresolved, and no tag is named in this document deliberately. There is no single canonical mechanism. Candidates to evaluate: series or image comments; the derivation description; a private tag under a registered root; and whatever `highdicom` exposes for algorithm identification on SEG and SR. The trade-off runs between visibility to other tooling and resistance to being stripped — a private tag is safe but invisible to third-party viewers, a standard free-text field is visible but easily removed. To be settled in `docs/11_dicom_conformance_statement.md` with the options written out, not decided in passing at implementation time. | `docs/11`, milestone 6 |
| 2 | The criteria by which URS-009 judges an input in or out of scope depend on what the converted DICOM objects carry, which is not known until milestone 3. The SRS derivation may need to narrow URS-009 at that point. | `docs/02`, milestone 3 |
