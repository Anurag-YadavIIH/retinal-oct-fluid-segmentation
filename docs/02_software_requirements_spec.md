<!--
Document: Software Requirements Specification
Status: DRAFT v0.1
Owner: Anurag Yadav
Last reviewed: 2026-09-16
Change history: docs/13_change_control_log.md

Allocates SRS-001..SRS-061 and NFR-001..NFR-008. Every requirement here derives
from a user requirement in docs/01. Hazard and test allocations are TBD until
docs/05 and docs/07 exist; docs/09 tracks the gap. Section 3.10 maps every module
under src/ocuval to the requirements it implements, which is the check CLAUDE.md
rule 1 demands.
-->

# Software Requirements Specification

## 1. Scope

This document specifies the software behaviour required to satisfy URS-001 through
URS-011 in `docs/01_intended_use.md`. It covers the whole pipeline: reading RETOUCH
volumes, converting them to DICOM, de-identifying them, splitting them at patient
level, training a segmentation model, evaluating it with per-vendor subgroup
reporting, emitting DICOM Segmentation and Structured Report objects, communicating
with a local PACS, and serving inference over HTTP.

Out of scope, per `docs/01` §5 and §6.2: any clinical use, longitudinal or
treatment-monitoring functionality, triage or prioritisation, full 3D segmentation,
and any user interface beyond the HTTP API.

## 2. Definitions

| Term | Meaning in this document |
|---|---|
| **Sample** | One B-scan presented to the network, carrying patient, vendor and source-volume identity |
| **Volume** | One OCT acquisition — an ordered stack of B-scans from one eye, one visit |
| **Manifest** | The record of all available samples with their patient, vendor and provenance fields |
| **Split** | A resolved assignment of samples to train / validation / test for one fold |
| **Fold** | One leave-one-vendor-out configuration, named for the held-out vendor |
| **In-domain reference** | Held-out patients drawn from the *training* vendors, evaluated by the same model |
| **Candidate** | Any output of this software, prior to grader action (`docs/01` URS-003) |
| **Shall** | Mandatory. Every "shall" in §3 is verifiable and carries a test allocation |

## 3. Requirements

Each requirement must be **verifiable**. A requirement containing "appropriate",
"robust", "efficient", "user-friendly", or any other unmeasurable adjective is a
defect and must be rewritten.

TC allocations reading `TBD` await `docs/07`. Two existing test cases are allocated
below: TC-001 (frozen config contract) and TC-004 (patient-level split disjointness).
TC-000 is a smoke test and is deliberately allocated to no requirement — it asserts
only that the package exposes a version identifier, which is a precondition of
SRS-031 and SRS-049 rather than a verification of either.

### 3.1 Data ingestion

SRS-054 through SRS-056 govern **acquisition metadata**, not pixels. They are separated
from the image requirements deliberately: SRS-010 and SRS-026 forbid harmonising the
*image* across vendors but say nothing about the metadata that turns a mask into a
measurement, and that gap is HAZ-012.


| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-001 | The reader shall load a RETOUCH MetaImage volume and return the pixel array, the reference label array where one exists, the patient identifier, the vendor, the voxel spacing in millimetres, and the source path, as a single immutable record. | URS-001, URS-006 | TC-010 |
| SRS-002 | Label indices and vendor keys shall be read from `configs/data.yaml` and shall not be redefined anywhere else in the codebase. Changing either is a requirements change, not an edit. | URS-001 | TC-001 |
| SRS-003 | Voxel spacing shall be taken from the source volume header. The software shall not assume, default, or hard-code a spacing value. | URS-002, URS-008 | TC-011 |
| SRS-004 | The reader shall raise on unreadable or malformed input, naming the offending path. It shall not return a partially populated record, and it shall not skip a volume silently. | URS-009 | TC-012 |
| SRS-005 | Knowledge of the RETOUCH on-disk directory layout shall be confined to the reader module. No other module shall depend on that layout. | URS-001 | TC-013 |
| SRS-054 | Voxel spacing shall be carried as a first-class field of every sample, on the same terms as vendor, and shall survive ingestion, DICOM conversion, de-identification, inference and volume computation. | URS-002, URS-006 | TC-010, TC-016, TC-110 |
| SRS-055 | Voxel spacing shall be asserted present at ingestion. No default, fallback or assumed value shall exist anywhere in the codebase, and absence shall abort the run naming the offending volume. | URS-002 | TC-005, TC-014 |
| SRS-056 | Each spacing component shall be checked against a per-vendor plausibility range held in `configs/data.yaml`. A value outside the range shall **reject the volume**, not warn and continue. The ranges shall be expressed in millimetres and the units stated in the configuration. | URS-002, URS-009 | TC-015 |

### 3.2 DICOM conversion

| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-006 | Each volume shall be written as DICOM instances of the SOP class configured in `configs/data.yaml` (`dicom.sop_class`), using `pydicom` and `highdicom`. DICOM encoding shall not be hand-rolled. | URS-001 | TC-020 |
| SRS-007 | Instance, series and study UIDs shall be generated under the UID root configured in `configs/data.yaml` (`dicom.uid_root`). | URS-010 | TC-021 |
| SRS-008 | Conversion of the same source volume with the same configuration shall produce the same set of instances, differing only in the generated UIDs, which shall themselves be recorded in the run output. | URS-010 | TC-022 |
| SRS-009 | The scanner vendor shall be written into the converted object and shall be recoverable from it without reference to the source directory layout. | URS-006 | TC-023, TC-110 |
| SRS-010 | Conversion shall preserve the acquisition's native slice count and voxel spacing. It shall not resample, pad, crop or interpolate the volume to a common geometry. | URS-008 | TC-024 |
| SRS-011 | Where a required tag, UID or IOD constraint is not established, conversion shall fail with that uncertainty stated, rather than writing a plausible value. The behaviour implemented shall match `docs/11_dicom_conformance_statement.md`. | URS-001 | TC-025 |

### 3.3 De-identification

| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-012 | De-identification shall apply the DICOM PS3.15 Annex E Basic Application Confidentiality Profile with no retention options, as configured in `configs/data.yaml` (`deidentification`). | URS-010 | TC-030 |
| SRS-013 | Patient identifiers shall be replaced by a salted-hash pseudonym. The salt shall be read from the environment variable named in `configs/data.yaml` (`deidentification.pseudonym_salt_env`) and shall never be written to any committed file or run output. | URS-010 | TC-031 |
| SRS-014 | Pseudonyms shall be stable within a run, so that patient-level splitting remains valid after de-identification. | URS-010 | TC-032 |
| SRS-015 | A verification function shall return the identity of every tag that the profile requires to be removed and that remains present. An empty result shall be the only condition under which an instance passes. | URS-010 | TC-033 |
| SRS-016 | A non-empty verification result shall abort the run. Failing instances shall never be skipped, quarantined or logged-and-continued. | URS-010 | TC-034 |
| SRS-017 | The vendor attribute shall survive de-identification. Its loss shall abort the run on the same terms as SRS-016. | URS-006 | TC-035, TC-110 |

### 3.4 Dataset splitting

| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-018 | `ocuval.data.splits` shall be the only module that assigns samples to splits. No other module shall partition data. | URS-007 | TC-003 |
| SRS-019 | Splits shall be constructed at patient level. Every patient shall appear in exactly one of train, validation and test, and no B-scan from a patient shall appear in a split other than that patient's. | URS-007 | TC-004 |
| SRS-020 | The disjointness assertion shall operate on the patient identifier and shall be executed both at the end of split construction and at the start of training. The exception it raises shall never be caught. | URS-007 | TC-004 |
| SRS-021 | Each fold shall hold out exactly one vendor. The test split shall contain no sample whose vendor differs from the fold's held-out vendor. | URS-007 | TC-004 |
| SRS-022 | Each fold shall additionally resolve an in-domain reference set of held-out patients drawn from the training vendors, disjoint from train and validation on the same terms as SRS-019. | URS-007 | TC-040 |
| SRS-023 | Split construction shall be seeded, and the resolved split shall be persisted such that it can be reconstructed from the committed configuration alone. | URS-010 | TC-041 |

### 3.5 Training

| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-024 | Datasets and dataloaders shall be constructed only from a resolved, persisted split. Training shall not accept an unresolved or ad-hoc sample list. | URS-007 | TC-050 |
| SRS-025 | Intensity normalisation shall be computed per volume. No statistic derived across the dataset or across vendors shall be used to normalise. | URS-008 | TC-051 |
| SRS-026 | Preprocessing shall not resample volumes from different vendors onto a common geometry. Patch or ROI extraction for training shall not be construed as such resampling. | URS-008 | TC-052 |
| SRS-027 | The network shall be 2D or 2.5D as selected by `configs/train_seg.yaml` (`data.mode`). Full 3D architectures shall not be provided. | URS-001 | TC-053 |
| SRS-028 | The network shall be constructed with non-zero dropout, and the configuration shall be rejected if dropout is zero, since MC-dropout inference depends on it. | URS-005 | TC-054 |
| SRS-029 | Inference shall support repeated stochastic forward passes with dropout active, returning the mean class probabilities and the per-voxel standard deviation across passes. | URS-005 | TC-055 |
| SRS-030 | A scan-level confidence value in the range 0 to 1 shall be derived from the per-voxel uncertainty, together with a boolean indication of whether review is recommended, determined against a threshold recorded in the run configuration. | URS-005 | TC-056 |
| SRS-031 | The random seed, the resolved configuration and the software version shall be written into the run output directory at the start of every run. | URS-010 | TC-057 |
| SRS-061 | Model checkpoints shall be loaded only from the project's own `artifacts/` directory. A cryptographic hash of every checkpoint shall be recorded when it is written and verified before it is loaded; a mismatch, or a checkpoint with no recorded hash, shall abort without loading. No checkpoint from any other source shall be loaded. | URS-010 | TC-058 |

### 3.6 Evaluation and reporting

Covers both the segmentation metrics and the volume-level **detection** metrics. The
detection figures are a second view of one model's output, not a second model:
SRS-050 fixes that, so that nothing in this specification can be read as authorising a
separate classifier or a second training run. SRS-035 applies to both — accuracy is not
reported for detection either, and the prevalence figures in `docs/06` §3.2 are why.


| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-032 | Segmentation performance shall be computed as Dice and HD95, separately for each of IRF, SRF and PED. A foreground-aggregate figure shall not be reported in place of the per-class figures. | URS-007 | TC-060 |
| SRS-033 | Every reported metric shall be accompanied by a bootstrap 95% confidence interval and the number of units it was computed over. A point estimate shall not be emitted without both. | URS-007 | TC-061 |
| SRS-034 | Bootstrap resampling shall be seeded from the run configuration and shall reproduce exactly on re-execution. | URS-010 | TC-062 |
| SRS-035 | No accuracy metric shall be provided or reported. | URS-007 | TC-002 |
| SRS-036 | Results shall be broken down by vendor, reporting held-out-vendor performance, in-domain reference performance, and the difference between them, per fluid class. | URS-007 | TC-063 |
| SRS-037 | The rendered results table shall state, for every figure, the fluid class, the vendor, the confidence interval and the sample size. | URS-007 | TC-064 |
| SRS-050 | Volume-level detection of each fluid class shall be **derived from the segmentation output of the same model**. No separate classifier shall be trained, stored or served, and no forward pass shall be required beyond the MC-dropout passes of SRS-029. | URS-001, URS-007 | TC-065 |
| SRS-051 | A fluid class shall be reported present in a volume when the number of voxels predicted for that class exceeds a threshold read from the run configuration. The threshold shall not be hard-coded, and its resolved value shall be written to the run output with the rest of the configuration. | URS-007, URS-010 | TC-066 |
| SRS-052 | The continuous score used for AUROC shall be derived, per class and per volume, from the MC-dropout mean class probability produced by SRS-029. | URS-005, URS-007 | TC-067 |
| SRS-053 | Detection performance shall be reported as sensitivity, specificity and AUROC, per fluid class and per scanner platform, each accompanied by a bootstrap 95% confidence interval and the sample size, on the same terms as SRS-032 and SRS-033. | URS-007 | TC-068 |

### 3.7 Segmentation and structured report output

| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-038 | Segmentation results shall be written as DICOM Segmentation objects via `highdicom`, with one segment per fluid class using the label indices of SRS-002. | URS-001, URS-004 | TC-070 |
| SRS-039 | The Segmentation object shall reference the source image instances it was derived from, so that it can be opened and reviewed against those images in standard DICOM tooling. | URS-004 | TC-071 |
| SRS-040 | A Structured Report shall record, for the imaged eye, the volume in cubic millimetres of each fluid class, computed from the segmentation and the acquisition's own voxel spacing. | URS-002 | TC-072 |
| SRS-057 | The voxel spacing used to compute a volume shall be asserted bit-identical to the spacing recorded at ingestion for that acquisition. Any difference shall abort before a volume is emitted. | URS-002, URS-010 | TC-073 |
| SRS-058 | The Structured Report shall state the units of every quantity it carries explicitly. Units shall not be implied by convention or inferred by a consumer. | URS-002 | TC-074 |
| SRS-059 | The Structured Report shall record, for each fluid class, the predicted voxel count and the voxel volume used, alongside the resulting volume in cubic millimetres, so that the derivation can be recomputed from the object alone. | URS-002, URS-010 | TC-075 |
| SRS-041 | The Structured Report shall record the scan-level confidence and the review-recommended indication of SRS-030. These shall not appear only in run logs. | URS-005 | TC-076 |
| SRS-042 | Every emitted Segmentation and Structured Report object shall carry, within the object, a designation readable both by software and by a person that the result is research-use-only, not clinically validated, and produced by an automated method requiring human review. The means of expressing this is specified in `docs/11` and is unresolved at the time of this draft (§6, item 1). | URS-011 | TC-077 |

### 3.8 PACS communication

| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-043 | The software shall store objects to, and retrieve objects from, a DICOMweb endpoint configured at runtime, using STOW-RS and WADO-RS. | URS-010 | TC-080, TC-112 |
| SRS-044 | A stored object shall be retrievable and shall match what was sent in its pixel data, its fluid volumes, its confidence value and its research-use designation. | URS-010, URS-011 | TC-081, TC-112 |
| SRS-045 | The software shall perform no action against the PACS beyond storing and retrieving its own objects. It shall not delete, modify or reconcile existing content, and it shall not mark any object as final, verified or signed off. | URS-003 | TC-082 |
| SRS-060 | The DICOMweb client shall take its entire configuration from the run configuration and shall not read ambient environment configuration — no `.netrc`, no environment-supplied proxy or certificate settings. Sessions shall be constructed with `trust_env=False`. | URS-003, URS-010 | TC-083 |

### 3.9 Inference API

| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-046 | The service shall accept one OCT volume per inference request and return the identifiers of the objects it produced, the per-class volumes in cubic millimetres, the scan-level confidence, and the review-recommended indication. | URS-002, URS-005 | TC-090 |
| SRS-047 | Every inference response shall be identified as a candidate requiring grader review. The service shall expose no endpoint that records, finalises, approves or signs off a result. | URS-003 | TC-091 |
| SRS-048 | The service shall determine whether the submitted volume falls within the indications of `docs/01` §2 and shall reject an out-of-scope volume with a stated reason and no segmentation. The criteria are unresolved pending milestone 3 (§6, item 2). | URS-009 | TC-092 |
| SRS-049 | A health endpoint shall report the service status, the software version, and the identifier of the loaded model. | URS-010 | TC-093 |

### 3.10 Module allocation

CLAUDE.md rule 1 requires every module under `src/` to trace to a numbered
requirement. This table is that check. A module absent from this table, or a module
whose docstring names an SRS identifier not listed here, is a defect.

| Module | Implements |
|---|---|
| `io/retouch_reader.py` | SRS-001, SRS-003, SRS-004, SRS-005, SRS-054, SRS-055, SRS-056 |
| `io/dicom_writer.py` | SRS-006..SRS-011, SRS-054 |
| `io/deident.py` | SRS-012..SRS-017, SRS-054 |
| `io/dicomweb.py` | SRS-043, SRS-044, SRS-045, SRS-060 |
| `data/splits.py` | SRS-018..SRS-023 |
| `data/datamodule.py` | SRS-024 |
| `data/transforms.py` | SRS-025, SRS-026 |
| `models/seg_unet.py` | SRS-027, SRS-028, SRS-061 |
| `models/uncertainty.py` | SRS-029, SRS-030 |
| `eval/metrics.py` | SRS-032, SRS-033, SRS-034, SRS-035, SRS-050, SRS-051, SRS-052, SRS-053 |
| `eval/subgroup.py` | SRS-036, SRS-053 |
| `eval/report.py` | SRS-037 |
| `report/seg_object.py` | SRS-038, SRS-039, SRS-042 |
| `report/sr_object.py` | SRS-040, SRS-041, SRS-042, SRS-054, SRS-057, SRS-058, SRS-059 |
| `service/api.py` | SRS-046, SRS-047, SRS-048, SRS-049, SRS-061 |
| `service/schemas.py` | SRS-046 |
| `ocuval/__init__.py` | SRS-031 (version identifier) |

SRS-002 appears against no module deliberately. Its positive half is satisfied by
`configs/data.yaml`, which holds the values; its negative half — that they shall not
be redefined anywhere else — binds every module in the table above rather than being
implemented by one of them. TC-001 verifies it.

## 4. Non-functional requirements

| ID | Requirement | Trace (URS) |
|---|---|---|
| NFR-001 | The software shall run on Python 3.11 with the exact dependency versions pinned in `pyproject.toml`. Every pinned version shall have a matching entry in `docs/04_soup_list.md`. | URS-010 |
| NFR-002 | Every split, training run and bootstrap resample shall be seeded, and the seed shall be recorded in the run configuration. A run shall be reproducible from the committed configuration alone. | URS-010 |
| NFR-003 | Evaluation and report generation shall run to completion on CPU, without accelerated hardware. | URS-007 |
| NFR-004 | No file under `data/` or `artifacts/` shall be committed to version control. | URS-010 |
| NFR-005 | The patient-overlap test shall gate continuous integration and shall never be skipped, xfailed or weakened once `ocuval.data.splits` is implemented. | URS-007 |
| NFR-006 | Inference shall require no network access other than to the configured DICOMweb endpoint. | URS-003 |
| NFR-007 | Any change to a metric definition, requirement, hazard or frozen contract shall be recorded in `docs/13_change_control_log.md` with a date and rationale in the same commit. | URS-010 |
| NFR-008 | Each module's docstring shall name the SRS identifiers it implements, and `docs/09_traceability_matrix.md` shall be updated in the same commit as any change to a requirement, hazard or test. | URS-010 |

## 5. Assumptions and dependencies

1. RETOUCH is obtained by manual registered download (`docs/06` §2.1); no requirement here implies automated acquisition.
2. The reference standard's fluid definitions are inherited, not independently specified (`docs/01` §2).
3. Training executes on Kaggle; this specification governs the pipeline, not the training host.
4. Orthanc in Docker is the DICOMweb peer for SRS-043..SRS-045. No other PACS is assumed conformant.
5. MONAI provides transforms, networks and metrics; `pydicom` and `highdicom` provide DICOM read, write and de-identification primitives. SOUP entries in `docs/04` govern.
6. The UID root in `configs/data.yaml` is a placeholder, as that file states, and will remain one. SRS-007 requires UIDs to be generated under the configured root; it asserts nothing about that root being registered, and the objects this software creates are confined to the local Orthanc instance in consequence (`docs/06` §7.1).

## 6. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | SRS-042: the conformant means of expressing the research-use-only designation inside a SEG and an SR is unresolved. Carried from `docs/01` §8 item 1; to be settled in `docs/11` before milestone 6. | `docs/11`, milestone 6 |
| 2 | SRS-048: the criteria for judging a volume in or out of scope depend on what the converted DICOM objects carry, which is not known until milestone 3. The requirement is deliberately not narrowed on speculation. Carried from `docs/01` §8 item 2. | Milestone 3 |
| 3 | ~~SRS-007: the UID root is a placeholder.~~ **Resolved 2026-09-16:** the placeholder is documented rather than replaced, and no root will be registered. UIDs under it carry no claim of global uniqueness and objects must not leave the local Orthanc instance. Recorded in `docs/06` §7.1, `docs/11` §7 and §10, and the README. | — closed |
| 4 | SRS-030: the confidence threshold for recommending review has no value yet. It cannot be chosen before evaluation data exists, and choosing it will be a change-controlled decision under NFR-007. | Milestone 5 |
| 6 | ~~§3.6 specifies segmentation metrics only.~~ **Resolved 2026-09-17:** SRS-050..SRS-053 specify volume-level detection derived from the segmentation output — no second model, no second training run. scikit-learn (SOUP-008) now supports SRS-053. | — closed |
| 5 | Hazard and test allocations are absent throughout §3. They are filled as `docs/05` and `docs/07` are drafted; `docs/09` carries the coverage count until then. | `docs/05`, `docs/07` |
