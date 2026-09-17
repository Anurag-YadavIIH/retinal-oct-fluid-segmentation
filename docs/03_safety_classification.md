<!--
Document: IEC 62304 Software Safety Classification
Status: DRAFT v0.1
Owner: Anurag Yadav
Last reviewed: 2026-09-17
Change history: docs/13_change_control_log.md

Classifies the software system against the intended use in docs/01, treating that
intended use as real. Hazardous situations are identified here as HS-1..HS-7, which
are local to this document; docs/05 allocates the HAZ-nnn identifiers and may merge
or split these when it does.
-->

# IEC 62304 Software Safety Classification

## 1. Purpose

To assign a software safety class to the OcuVal software system under IEC 62304 §4.3,
and to show the reasoning that produces it.

### 1.1 What is being classified

This project is never used on real patients (`docs/01` §5). A classification conducted
against that fact would be trivial and worthless: nothing is deployed, so nothing can
hurt anyone, and the answer would be Class A for a reason that teaches nothing.

This document therefore classifies **the intended use as stated in `docs/01`** — a
pre-read for a supervised reading-centre grader in a retrospective research or
clinical-trial workflow — as if that use were real. Every conclusion below should be
read with that framing. The actual residual risk of this repository as it exists is
nil, because it is not used; the residual risk assessed here is the residual risk the
stated intended use would carry.

### 1.2 Sources this classification was developed against

This classification was **not** developed against the normative text of IEC 62304. No
licensed copy of the standard was available to the author while drafting it. It was
developed against the publicly documented clause structure of IEC 62304:2006+A1:2015
and secondary literature describing it.

The consequence is specific and worth stating rather than burying: **the clause numbers
and the class applicability in §6 are reported from that secondary understanding and
have not been checked against the standard.** The reasoning in §3 to §5 does not depend
on them — it depends on the §4.3 decision logic, which is quoted in substance and
widely reproduced — but §6 is the part of this document most likely to contain an error
of citation. It is recorded as open item 7 and must be checked against a licensed copy
before this document is relied on. Substituting a confident-looking clause list for a
verified one would be the same failure this project refuses elsewhere when it declines
to invent a DICOM tag.

### 1.3 Governing assumption

IEC 62304 requires that, for classification purposes, the **probability of a software
failure be taken as 100%**. No argument below may rest on a failure being unlikely.
Only the severity of the resulting harm, and the effectiveness of risk control
measures *external to the software*, may reduce the class.

## 2. Software system and items

The software system is the whole OcuVal pipeline. Its software items are the
subpackages under `src/ocuval`, each allocated to requirements in `docs/02` §3.10.

| Software item | Function | Can it contribute to an output a grader sees? |
|---|---|---|
| `io/` | RETOUCH reading, DICOM conversion, de-identification, DICOMweb | Yes |
| `data/` | Patient-level splitting, transforms, datamodule | Yes — indirectly, via the trained model |
| `models/` | Network construction, MC-dropout uncertainty | Yes |
| `eval/` | Metrics, subgroup analysis, report rendering | Yes — via the performance claims that set grader trust |
| `report/` | SEG and SR construction | Yes |
| `service/` | Inference API | Yes |

No item is isolated from the output path. This matters in §7.

## 3. Hazardous situations arising from software failure

The harm pathway in the intended use is **endpoint corruption**, not point-of-care
error. The software's output informs a grader's recorded assessment; that assessment
becomes a data point in a research study or a clinical-trial dataset; that dataset
informs a conclusion which may eventually influence how patients are treated. No
output of this software reaches a patient directly, and by `docs/01` §5 none may
inform an individual treatment decision.

| ID | Hazardous situation | Software failure that contributes | Resulting harm |
|---|---|---|---|
| HS-1 | Fluid present but reported as absent or smaller than it is, and the under-segmentation is accepted at review | Under-segmentation, particularly of small or boundary lesions | Recorded endpoint understates disease; if systematic, study conclusion is biased |
| HS-2 | Fluid absent or small but reported as larger, accepted at review | Over-segmentation, spurious foreground in noisy volumes | Recorded endpoint overstates disease; same downstream effect as HS-1 in the opposite direction |
| HS-3 | Fluid assigned to the wrong compartment | IRF / SRF / PED class confusion; label index misuse | The three compartments carry different meaning; an endpoint defined on one is silently computed on another |
| HS-4 | A result is attributed to the wrong patient, eye or acquisition | Pseudonym collision, UID collision, vendor or identity metadata lost in conversion or de-identification | A measurement is recorded against a subject it did not come from — the most direct corruption available, and the hardest to detect downstream |
| HS-5 | A vendor-correlated systematic bias is present and undetected | Model performs materially worse on one scanner platform; evaluation fails to surface it per vendor | If imaging platform correlates with site or with study arm, the bias is confounded with the effect under study and does not average out |
| HS-6 | An out-of-scope acquisition is processed and returns a confident-looking result | Failure to reject DME, OCTA, en-face, non-macular, or an unlisted platform | A measurement is produced outside any validated domain and carries no indication that it is |
| HS-7 | A low-confidence result is not flagged for closer review | Confidence value wrong, absent, or not carried into the SR | The one signal designed to counteract over-acceptance is missing exactly when it is needed |

### 3.1 The severity question

For every situation above, the realised harm is in the first instance to **data
integrity**. Physical injury requires the corrupted endpoint to survive trial or study
quality control, statistical review, and — for a trial — regulatory scrutiny, and then
to change a clinical decision affecting patients. Those are real pathways, but each
step is governed by controls wholly outside this software and outside its
manufacturer's authority.

Two properties of this hazard set matter more than the list itself:

1. **Systematic error does not average out.** HS-5 is qualitatively worse than HS-1 and
   HS-2 taken individually. Random per-case error is diluted by aggregation across
   subjects; a vendor-correlated bias is not, and it is invisible in any single case.
2. **The most likely failures are the least visible ones.** A grossly wrong
   segmentation is obvious. A boundary that is consistently two voxels tight, or a
   small IRF pocket consistently missed, is not — and it is precisely that failure
   which biases a quantitative endpoint.

## 4. External risk control measures

"External" means outside the software system. Controls implemented *in* the software
(URS-005 confidence reporting, URS-006 vendor preservation, URS-009 out-of-scope
rejection) are not external controls and cannot reduce the class — they are the
software whose failure is assumed.

| ID | External control | What it addresses | Honest assessment of effectiveness |
|---|---|---|---|
| ERC-1 | Mandatory grader review and correction before any result is recorded (URS-003) | HS-1, HS-2, HS-3, HS-6 | **Partial, and weakest where it is most needed.** See §4.1 |
| ERC-2 | Retinal specialist supervision with escalation available (`docs/01` §3) | HS-3, HS-6 | Partial. Supervision is not per-case review; it raises the ceiling on competence, not the detection rate on any given scan |
| ERC-3 | The output informs no individual treatment decision, and no longitudinal comparison (`docs/01` §5) | All | **Strong, and structural.** This is what bounds the severity of the harm, and it is a property of the workflow, not of the software |
| ERC-4 | No point-of-care use, no live acquisition, no automated downstream action (`docs/01` §4) | All | Strong and structural, on the same basis as ERC-3 |
| ERC-5 | Statistical aggregation across subjects in any study using the output | HS-1, HS-2 | Partial for random error. **Ineffective against HS-5**, which is the situation that most needs it |
| ERC-6 | Reading-centre quality control — second reading, adjudication, audit trail | HS-1..HS-4 | **Not claimed.** Such controls exist in well-run reading centres, but `docs/01` does not require them and this project cannot assume a control it has not specified |

### 4.1 Why grader review is not treated as fully mitigating

ERC-1 is the control most likely to be over-credited, and the temptation is to let it
carry the entire safety argument: a human sees every output, therefore no bad output
can escape. That argument does not survive contact with how people actually review
machine output.

- **Automation bias is well documented.** A reviewer presented with a plausible
  candidate is more likely to accept it than to construct the answer independently.
  The presence of a proposed segmentation changes the reviewer's task from *measure
  this* to *check this*, and those are not the same task.
- **A plausible wrong answer is more readily accepted than an obviously wrong one.**
  This is the specific asymmetry that matters here, and it is the inverse of what a
  review control needs: review catches gross failures well and subtle ones poorly.
- **The dominant failure mode is the subtle one.** Per §3.1, the errors most likely to
  occur and most damaging to a quantitative endpoint are small, consistent and
  individually plausible. ERC-1 is at its weakest precisely there.
- **Correction is itself unverified.** Nothing in `docs/01` establishes that a grader's
  correction of a machine proposal is as accurate as unaided grading. The reference
  standard this software learned from was not double-graded (`docs/06` §1.2), so the
  project has no measurement of grader agreement to reason from.

ERC-1 therefore **reduces the probability of an undetected error and does not
eliminate it**. It is credited as a partial control. It is not credited as reducing the
risk from HS-1, HS-2 or HS-5 to an acceptable level.

## 5. Classification decision

IEC 62304 §4.3 assigns the class by asking whether the software can contribute to a
hazardous situation, whether external risk controls reduce the resulting risk to
acceptable, and what harm remains possible: Class A where no injury is possible or the
risk is acceptable after external controls, Class B where non-serious injury is
possible, Class C where death or serious injury is possible.

| Question | Answer | Consequence |
|---|---|---|
| Can a software failure contribute to a hazardous situation? | **Yes.** HS-1 through HS-7. Probability of failure is taken as 100% per §1.2, so this cannot be answered "no" on reliability grounds | Class A is not available by the "cannot contribute" route |
| Do external risk controls reduce it below the threshold of unacceptable risk? | **No — not for HS-1, HS-2 and HS-5.** ERC-3 and ERC-4 bound the severity but do not prevent the corruption; ERC-1 is partial and weakest against the dominant failure mode (§4.1); ERC-5 is ineffective against systematic bias; ERC-6 is not claimed | Class A is not available by the "acceptable after external controls" route either |
| Is the resulting possible harm non-serious injury, or death / serious injury? | **Non-serious injury.** The intended use interposes a grader's recorded assessment and an aggregated study endpoint between the software and any patient. No individual treatment decision may depend on an output (ERC-3), longitudinal use is excluded, and point-of-care use is excluded (ERC-4). Death or serious injury would require an output to drive care for an individual, which the intended use structurally forbids | Class C is not reached |

**Assigned class: B.**

### 5.1 Why not Class A

The available Class A argument is that every output is reviewed by a competent human,
so no erroneous result can reach a study record. This document declines that argument.
It credits ERC-1 as partial rather than complete for the reasons in §4.1, and it notes
that the Class A route would require the residual risk from HS-5 — an undetected,
vendor-correlated, systematically biased measurement — to be acceptable. It is not: it
is the failure this project exists to measure, it is invisible case by case, and the
per-vendor reporting that would surface it is *inside* the software and therefore
cannot be credited as an external control. `docs/05` §5.2 reaches the same conclusion
from the risk side and carries the residual as HAZ-005; the two are one argument stated
twice, not two independent findings.

### 5.2 Why not Class C

Class C would require that death or serious injury be possible. In the stated intended
use, the software produces a candidate measurement for a retrospective research or
trial reading, which a grader must act on before it exists as data, which then enters
an aggregated endpoint. It informs no individual's care. The causal chain from a
software failure to serious physical injury runs through several independent
organisations and control systems that this manufacturer neither owns nor can claim
credit for — but equally, that chain is long enough that attributing serious injury to
this software system would overstate its role.

This conclusion is contingent on the intended use. **If `docs/01` is ever widened to
point-of-care use, to treatment monitoring, or to any workflow in which an individual's
care depends on a single output, this classification is void and Class C must be
reconsidered from the start.** That is recorded as a change-control trigger.

## 6. Processes in scope for this class

Class B brings the following into scope, in addition to everything required of Class A.
The table summarises the clause applicability of IEC 62304:2006+A1:2015 as understood
from the sources in §1.2. **The clause numbers below are unverified against the
normative text** (open item 7); the standard governs wherever it and this summary
disagree.

| Clause | Process | Class B | Status in this project |
|---|---|---|---|
| 5.1 | Software development planning | Required | Partial — milestone order in `CLAUDE.md`; no separate plan document yet |
| 5.2 | Software requirements analysis | Required | `docs/02`, SRS-001..SRS-049 |
| 5.3 | **Software architectural design** | **Required for B, not for A** | **Not yet drafted — gap** |
| 5.4 | Software detailed design | Class C only | Out of scope |
| 5.5.1 | Implement each software unit | Required (all classes) | Partial — `src/` is stubs |
| 5.5.2 | **Establish software unit verification process** | **Required for B, not for A** | **Not recorded — gap** |
| 5.5.3 | **Software unit acceptance criteria** | **Required for B, not for A** | **Not recorded — gap** |
| 5.5.4 | Additional software unit acceptance criteria | Class C only | Out of scope |
| 5.5.5 | **Software unit verification** | **Required for B, not for A** | Partial — `pytest` suite exists but no unit verification process or acceptance criteria govern it |
| 5.6 | **Software integration and integration testing** | **Required for B, not for A** | **Not yet drafted — gap** |
| 5.7 | Software system testing | Required (all classes, under A1:2015) | `docs/07` planned, not drafted |
| 5.8 | Software release | Required | Not yet applicable |
| 6 | Software maintenance | Required | `docs/13` serves as the change record |
| 7 | **Software risk management** | **Required for B, not for A** | `docs/05` planned, not drafted |
| 8 | Software configuration management | Required | Git, pinned dependencies, `docs/04` SOUP list |
| 9 | Software problem resolution | Required | Not yet drafted |

Choosing B rather than A therefore has a concrete cost, which is the point of choosing
it honestly. It obliges an architectural design document (5.3), integration testing
(5.6), a full software risk management file (clause 7), and — the part easiest to
overlook — a defined **software unit verification process and unit acceptance criteria**
(5.5.2, 5.5.3) governing the unit verification itself (5.5.5). Of the 5.5 group, only
5.5.1 would apply under Class A.

**Software system testing (5.7) is not among those costs.** Under IEC 62304
Amendment 1 (2015) it is mandatory for every class including A, so `docs/07` was owed
regardless of how this classification came out. Counting it as a consequence of choosing
B would overstate what the decision costs, and §6's job is to state that cost accurately.
This is an amendment-dependent point: the obligation follows from A1:2015, not from the
2006 text alone.

A passing `pytest` suite does not discharge 5.5.2 and 5.5.3. Tests existing is not the
same as a documented process stating what unit verification must cover and what a unit
must satisfy to be accepted. `docs/07` as currently scoped is a system-level V&V
protocol and does not carry unit-level criteria.

Three of the obligations above are already planned milestones. **5.3, 5.6 and the 5.5
unit verification clauses are new gaps created by this classification**, recorded in
§8 as items 1, 2 and 3.

## 7. Segregation rationale

**No segregation is claimed. Every software item inherits Class B.**

IEC 62304 permits software items to be classified below the system class where the
manufacturer documents that segregation between items is adequate to prevent one from
contributing to the hazardous situation. Two candidate arguments were considered and
both are rejected:

1. **"The training pipeline is offline and produces no grader-visible artefact."**
   Rejected. `data/` and `models/` produce the trained weights, and the weights are the
   thing that fails in HS-1, HS-2, HS-3 and HS-5. Being upstream of the failure is not
   segregation from it.
2. **"The evaluation and reporting code produces documents, not measurements."**
   Rejected. `eval/` produces the performance claims on which a grader's trust in the
   output is founded. A reporting failure that overstates performance makes ERC-1
   weaker, which is a contribution to every hazardous situation in §3.

There is in any case no structural basis for a segregation claim: the pipeline runs in
a single process with shared in-memory data structures and no enforced barrier between
items. A segregation argument would require demonstrable independence — separate
execution contexts, a defined and checked interface, and evidence that a failure on one
side cannot propagate. None of that exists, and manufacturing it to lower the class of
part of the system would be the same move as crediting ERC-1 fully: convenient, and not
true.

## 8. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | Software architectural design (62304 §5.3) is required for Class B and does not exist. A document must be added to the set, or an existing one extended to carry it. | Milestone 3 |
| 2 | Integration testing (62304 §5.6) is required for Class B and is not planned in `docs/07` as currently scoped. | `docs/07` |
| 3 | Software unit verification process and unit acceptance criteria (62304 §5.5.2 and §5.5.3) are required for Class B and are not recorded anywhere. `docs/07` as scoped is a **system-level** V&V protocol; it owes unit-level acceptance criteria and a statement of what unit verification (§5.5.5) must cover. A passing `pytest` suite is evidence of verification having been run, not the process or the criteria that govern it. | `docs/07` |
| 4 | Software problem resolution (62304 §9) has no process recorded. | — |
| 5 | HS-1..HS-7 and ERC-1..ERC-6 are local identifiers. `docs/05` allocates HAZ-nnn and RC-nnn and may merge or split them; the RC identifiers that follow supersede the interim `DMP-C` entries in `docs/09`. | `docs/05` |
| 6 | Any widening of `docs/01` intended use voids this classification (§5.2), and nothing yet enforces re-classification beyond the change control log. **Intended resolution:** a test case in `docs/07` that records a hash of `docs/01` §2 (indications for use) and fails when that hash changes unless `docs/03` was modified in the same commit. `docs/07` allocates the TC number and settles the mechanism — in particular how "the same commit" is established under a CI checkout. Not implemented; specified here so it is owned rather than remembered. | `docs/07` |
| 7 | The clause numbers and class applicability in §6 are **corroborated across multiple independent secondary sources but remain unverified against the normative text** of IEC 62304 (§1.2). Corroborated: 5.3 and 5.5–5.7 as documented processes for Class B, 5.4 detailed design as Class C only, unit implementation for all classes, unit verification for B and C, and 5.7 as mandatory for all classes under A1:2015. Convergence of independent sources is evidence of a weaker kind than the standard — it does not discharge the check. A licensed copy must still be consulted before this document is relied on. | — |
