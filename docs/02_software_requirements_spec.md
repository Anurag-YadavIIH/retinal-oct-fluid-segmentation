<!--
Document: Software Requirements Specification
Status: DRAFT v0.1
Owner: Anurag Yadav
Last reviewed: 2026-09-16
Change history: docs/13_change_control_log.md

Allocates SRS-001..SRS-099, SRS-102..SRS-105 and NFR-001..NFR-008 (SRS-100 and SRS-101 are reserved for branch `wire-dicom`, not yet merged). Every requirement here derives
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
| **Volume-level record** | One acquisition, which is what a manifest row and a DICOM instance correspond to. Splitting operates here; a resolved split lists volumes, not B-scans |
| **Expansion** | Deriving the frame-level samples of a split from its volume-level records (SRS-067..SRS-069). It happens after splitting and never before |
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
| SRS-066 | The pixel element type shall be taken from the source header and carried unchanged through conversion. The software shall not widen, narrow or otherwise cast pixel data to a fixed depth. **Clarified 2026-10-29 (finding D12):** what is carried unchanged is the values and their depth, not the byte order. A source stored most-significant byte first shall be written as the same values in the transfer syntax's little-endian order. Until 2026-10-29 such a source was refused as an unwritable type. | URS-001, URS-010 | TC-017, TC-024 |
| SRS-004 | The reader shall raise on unreadable or malformed input, naming the offending path. It shall not return a partially populated record, and it shall not skip a volume silently. | URS-009 | TC-012 |
| SRS-005 | Knowledge of the RETOUCH on-disk directory layout shall be confined to the reader module. No other module shall depend on that layout. | URS-001 | TC-013 |
| SRS-054 | Voxel spacing shall be carried as a first-class field of every sample, on the same terms as vendor, and shall survive ingestion, DICOM conversion, de-identification, inference and volume computation. | URS-002, URS-006 | TC-010, TC-016, TC-110 |
| SRS-055 | Voxel spacing shall be asserted present at ingestion. No default, fallback or assumed value shall exist anywhere in the codebase, and absence shall abort the run naming the offending volume. | URS-002 | TC-005, TC-014 |
| SRS-056 | Each spacing component shall be checked against a per-vendor plausibility range held in `configs/data.yaml`. A value outside the range shall **reject the volume**, not warn and continue. The ranges shall be expressed in millimetres and the units stated in the configuration. | URS-002, URS-009 | TC-015 |

### 3.2 DICOM conversion

| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-006 | Each volume shall be written as DICOM instances of the SOP class configured in `configs/data.yaml` (`dicom.sop_class`), using `pydicom` and `highdicom`. DICOM encoding shall not be hand-rolled. | URS-001 | TC-020 |
| SRS-007 | Instance, series and study UIDs shall be generated under the UID root configured in `configs/data.yaml` (`dicom.uid_root`). **Amended 2026-10-30 (the author's decision, finding D6):** the Tracking Unique Identifiers of the Structured Report's measurement groups are the one exception. Each shall be a name-based UUID (uuid5 over the device UID and the group's position) in the `2.25.<integer>` form of PS3.5 §B.2, so that it is valid, at most 64 characters, and repeatable from the same inputs. A value under the root cannot be all three: the device UID already takes all 64 characters the root allows. | URS-010 | TC-021, TC-076 |
| SRS-008 | Conversion of the same source volume with the same configuration shall produce the same set of instances, differing only in the generated UIDs, which shall themselves be recorded in the run output. | URS-010 | TC-022 |
| SRS-009 | The scanner vendor shall be written into the converted object and shall be recoverable from it without reference to the source directory layout. | URS-006 | TC-023, TC-110 |
| SRS-010 | Conversion shall preserve the acquisition's native slice count and voxel spacing. It shall not resample, pad, crop or interpolate the volume to a common geometry. **Amended 2026-10-29 (finding D12):** the B-scan separation shall also be written as Spacing Between Slices (0018,0088) in the Pixel Measures functional group, the attribute that names the distance between slices, beside Slice Thickness. | URS-008 | TC-024 |
| SRS-011 | Where a required tag, UID or IOD constraint is not established, conversion shall fail with that uncertainty stated, rather than writing a plausible value. The behaviour implemented shall match `docs/11_dicom_conformance_statement.md`. | URS-001 | TC-025 |
| SRS-062 | Ocular acquisition context that the source data does not supply — at minimum image laterality — shall be provided explicitly by the caller. The writer shall not default, infer or derive any such value, and shall abort naming the missing attribute and the module requiring it. | URS-002, URS-009 | TC-026 |
| SRS-063 | A research exception, disabled by default and settable only in configuration, shall permit conversion to proceed by **omitting** any module or functional group macro that cannot be populated from available data, rather than populating it with invented values. When enabled it shall be permitted only where the designation of SRS-042 is applied, shall emit a warning naming every omitted module, and shall record the omissions in the run output. | URS-009, URS-010, URS-011 | TC-027 |
| SRS-064 | Every emitted object shall be checked against the module and attribute requirements of its IOD as published in the DICOM standard, and conversion shall abort if a mandatory module is incomplete other than by a recorded SRS-063 omission. | URS-001 | TC-028 |

### 3.3 De-identification

| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-012 | De-identification shall apply the DICOM PS3.15 Annex E Basic Application Confidentiality Profile with no retention options, as configured in `configs/data.yaml` (`deidentification`). | URS-010 | TC-030 |
| SRS-013 | Patient identifiers shall be replaced by a salted-hash pseudonym. The salt shall be read from the environment variable named in `configs/data.yaml` (`deidentification.pseudonym_salt_env`) and shall never be written to any committed file or run output. | URS-010 | TC-031 |
| SRS-014 | A pseudonym shall be a deterministic function of the patient identifier and the salt alone. The same identifier and salt shall yield the same pseudonym in **every** run and on every machine, not merely within one run. | URS-010 | TC-032 |
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
| SRS-023 | Split construction shall be seeded, and the resolved split shall be persisted such that it can be reconstructed from the committed configuration alone. The persisted split shall be keyed on the **source subject identifier** — the archive's own anonymous case label — and not on any identifier minted by a run, so that two runs over the same archive with the same configuration produce **byte-identical** split files. SOP Instance UIDs, pseudonyms and file paths are all excluded by this: the first is minted per conversion, the second depends on an uncommitted salt, the third on the machine. | URS-010 | TC-041 |
| SRS-067 | Expansion from volume to frame shall occur **strictly after** splitting. No frame shall be presented to training, validation or evaluation before the volume it belongs to has been assigned to a split. | URS-007 | TC-043 |
| SRS-068 | Every frame shall inherit the split assignment of the volume it came from. No other mechanism shall assign a frame to a split, and `ocuval.data.splits` shall remain the only module that performs the expansion. | URS-007 | TC-043 |
| SRS-069 | Expansion shall be deterministic: the same split and the same frame counts shall produce the same frames in the same order on every execution. | URS-010 | TC-043 |
| SRS-070 | Intensity shall be normalised by a **per-volume percentile window**: the 1st and 99th percentiles of the raw volume shall be mapped to 0.0 and 1.0 and values outside the window clipped. The window shall be computed **at ingestion, from the raw volume, before any other transform**, and recorded as a field of the volume record and of the manifest. No transform shall recompute it. | URS-006, URS-010 | TC-044 |
| SRS-071 | Every frame shall inherit the intensity window of the volume it came from. No frame-level intensity statistic shall be computed anywhere in the pipeline, and inheritance shall be **asserted** after expansion rather than assumed. | URS-006 | TC-045 |
| SRS-072 | Axial resampling shall use a **target spacing declared as a constant in `configs/train_seg.yaml`**. The target shall not be derived from the data at run time, shall not depend on fold membership, and shall be written into the run output with the resolved configuration. | URS-010 | TC-046 |
| SRS-073 | Only the **axial** axis shall be resampled. Lateral spacing shall not be resampled, and B-scan separation shall not be resampled or otherwise used by the transform chain: training is 2D and frames are independent. Separation becomes relevant only if 2.5D mode is enabled, which is a separate decision. | URS-008 | TC-047 |
| SRS-074 | Every segmentation metric and every volume in mm³ shall be computed in the acquisition's **native geometry**. A prediction produced at the resampled spacing shall be inverted back to the native grid before any metric is computed, and the spacing used shall satisfy SRS-057. **The inversion shall remove any padding the preprocessing added before resizing, so that every predicted voxel returns to its native position. Amended 2026-10-16**, after the inversion resized padded frames whole and misplaced every cirrus and spectralis prediction (`docs/13`). **Amended 2026-10-29 (finding D1):** the labels the models were trained on were taken by nearest-neighbour resampling from native rows `floor(i × rows / prepared)`, so a prediction at prepared row i stands for that native row. **The inversion shall give each native row the prediction of the prepared row whose sampled native row is nearest to it, ties going to the even prepared row, with the sampled rows taken from the forward resampling itself and not from a second resize.** A model that reproduces its training labels then measures them in place: fluid built to survive resampling comes back exactly, and no band moves systematically (TC-151). Until 2026-10-29 the inversion resized with torch's legacy nearest mode, which moved every prediction about one native row deeper (`docs/13`). **Limitation, not repaired:** the same label sampling paired each training label with an image resampled centre-aligned, so training labels sat on average s/2 native rows shallower than their images, where s is the target over the native axial spacing (derived: cirrus about 1.02, spectralis 0.52, topcon 0.57 to 0.77 native rows). The models are not retrained; retraining would be a new pre-registered experiment. | URS-002, URS-008 | TC-048, TC-151 |
| SRS-075 | Training shall write a checkpoint at the end of every epoch containing **everything that changes behaviour after a resume**, not only the weights: the model state; the optimiser state; the learning-rate scheduler state **including its position within any warmup phase**; the gradient-scaler state whenever AMP is enabled; the epoch index; the **complete early-stopping state** — best metric, the epoch at which it occurred, and epochs elapsed since improvement; and the state of **every** random generator that affects training — Python's `random`, NumPy, torch CPU and torch CUDA. Omitting the early-stopping state silently resets patience on resume, which changes when training ends without changing anything visible. The write shall be atomic, so that a process killed mid-write leaves the previous checkpoint intact. | URS-010 | TC-059 |
| SRS-076 | A run resumed from a checkpoint shall be equivalent to an uninterrupted run of the same length. **On CPU the equivalence shall be bit-identical.** On GPU it shall be within a tolerance stated in the run output, because several CUDA kernels used by this network — among them some interpolation and upsampling backward passes — have no deterministic implementation, so bit-exactness is not achievable and shall not be claimed. | URS-010 | TC-059 |
| SRS-077 | Training shall request deterministic algorithms via `torch.use_deterministic_algorithms`. Where an operation has no deterministic implementation, the run shall fall back rather than abort, and shall **record in the run output which operations forced a fallback**. An undocumented fallback is an undocumented source of run-to-run variation. | URS-010 | TC-059 |
| SRS-078 | The frame cache shall be populated by a **volume-wise pre-pass** that decodes each source volume once. Frames served from the cache shall be bit-identical to the frames the same configuration produces without it: the cache is an optimisation and shall not be able to change a value. | URS-010 | TC-039 |
| SRS-079 | `train.batch_size` shall remain the **effective** batch — the number of samples contributing to each optimiser step — regardless of how many samples pass through the accelerator at once. A separate `train.micro_batch_size` shall control the latter, shall divide `batch_size` exactly, and shall default to it. The gradient from one step of `batch_size` samples and the gradient accumulated over `batch_size / micro_batch_size` micro-batches shall agree to within a stated tolerance. Both values shall be written to the run output. | URS-010 | TC-078 |
| SRS-080 | Training shall be bounded within a session by two independent means: a `--max-epochs-this-session` option that trains that many epochs, checkpoints and exits cleanly; and a **`STOP` file** in the run directory, which shall cause the current epoch to finish, a checkpoint to be written, the file to be removed and the process to exit with success. Neither shall terminate an epoch part-way, because a half-completed epoch leaves the optimiser in a state no checkpoint describes. | URS-010 | TC-079 |
| SRS-081 | Per-epoch metrics shall be appended to **one continuous log per fold**, never restarted, so that a fold's training curve is a single record however many sessions it took. Each session shall record its own boundary in that log. | URS-010 | TC-079 |
| SRS-082 | Every training run shall sample accelerator telemetry — at least temperature, clock frequency, utilisation and memory — at a fixed interval into the run directory, for the whole duration of the run. A laptop GPU throttles under sustained load, so a throughput figure measured over minutes does not describe a run lasting hours, and the record is also the execution environment `docs/08` must report. | URS-010, NFR-002 | TC-095 |
| SRS-083 | The learning-rate schedule shall honour `optim.warmup_epochs`: the rate shall rise linearly from a fraction of the configured rate to the configured rate across that many epochs, then follow the declared decay. A configured warmup that the schedule ignores is a run that did not do what its configuration says. | URS-010 | TC-079 |
| SRS-084 | The training loss shall have a deterministic implementation on the training accelerator. Where a term of the reference loss does not, it shall be replaced by an equivalent formulation that does, and the replacement shall be verified **back to back against the reference** on random inputs within a tolerance stated in `docs/07`. A run shall record zero determinism fallbacks, or record why it does not. | URS-010, NFR-002 | TC-089 |
| SRS-085 | The run record shall not be able to contradict itself: `run.json` shall not report deterministic algorithms as active while `determinism.json` records a fallback. Fallbacks shall be stored deduplicated as operation, count and first occurrence, not as one line per occurrence. | URS-010, NFR-008 | TC-109 |
| SRS-086 | The run record shall identify **the code that produced the run**, not only its configuration: `run.json` shall carry the commit identifier and whether the working tree was clean at the moment the run started. A run whose results will be reported shall **refuse to start on a dirty tree** unless the caller explicitly overrides, and the override shall itself be recorded. A configuration pinned against unidentified code is not reproducible, and a commit identifier recorded beside uncommitted edits names code that was not run. Each value shall have exactly one home in the record. | URS-010, NFR-002, NFR-008 | TC-122 |
| SRS-087 | Every reported confidence interval shall be a **cluster bootstrap resampled at the patient level**, taking all of a drawn patient's measurements, and the reported `n` shall be the **number of patients** with its unit named. Frames within a volume and volumes within a patient are near-repeated measurements, so resampling measurements independently narrows the interval by roughly the square root of the cluster size — in the direction that overstates certainty. The resample count, alpha and seed shall be recorded with the result. **Clarified 2026-10-29 (finding D8):** the recorded values shall be the ones used, for every interval in the record; segmentation intervals took the defaults of `subgroup.estimate` whatever the plan stated. | URS-007, URS-010 | TC-124 |
| SRS-088 | The held-out-vendor **test** split and the **in-domain reference** split shall be sealed: any code path that would read either shall refuse unless an explicit unlock is supplied, the unlock shall name a reason, and every access shall be appended to a durable access log recording the time, the bucket, the reason and an identifier for the run that made it. The reported access count shall be **the number of evaluation runs**, derived from those identifiers — not the number of times the gate was called, since a single run checks the seal more than once. The raw log shall never be rewritten to correct a count. `docs/07` §17.1 permits exactly one evaluation of the test set, and a limit nobody counts is not a limit; a limit counted in the wrong unit is not one either. **Corrected 2026-10-01**, see `docs/08` D6. | URS-007, URS-010, NFR-008 | TC-125 |
| SRS-089 | The evaluation record shall persist **one row per volume per fluid class**, carrying the volume and patient identifiers, the vendor, Dice, HD95, whether the class is present in the reference, the reference and predicted voxel counts, and **the detection score** (the MC-dropout mean probability AUROC ranks; added 2026-10-05, `docs/08` D9). These rows shall be derived from the same measurements as the aggregate figures, and every aggregate shall be recomputable from them. A record holding aggregates only can answer only the questions asked before it was written, so every later question about a sealed split would spend another unlock. **Added 2026-10-03** as the repair of `docs/08` D7. | URS-007, URS-010, NFR-002 | TC-126 |
| SRS-090 | Whether two evaluation records report the same result shall be decided by an **exact, leaf-by-leaf comparison**: every scalar compared by equality with no tolerance, list lengths compared, and a leaf present in only one record counted as a difference. Only the run's own provenance shall be excluded: `utc`, `notes`, `bucket_access_count`, and `per_volume`, which records written before SRS-089 lack. **A value undefined (NaN) in both records shall count as equal; NaN in only one shall count as a difference.** The comparison decides whether a sealed bucket may be unlocked for a re-run (`docs/07` §17.7b), so a spurious difference and a missed one are both failures. **Added 2026-10-04**, after its first use reported `nan -> nan` as a difference (`docs/13`). | URS-010, NFR-002 | TC-127 |
| SRS-091 | Evaluation shall be **reproducible from the committed configuration**. Before any tensor reaches the device, the evaluation path shall make the same determinism request training makes (seeded from `run.seed`) and record what was requested and achieved, including every non-deterministic fallback, in the evaluation record. Each volume's MC-dropout passes shall draw from a generator **re-seeded from `(run.seed, the volume's source subject identifier)`**, so that a volume's result does not depend on processing order, `--limit`, or which other volumes were evaluated. The derived seed shall be recorded per volume. The subject identifier is used rather than the SOP Instance UID, because UIDs are minted per conversion (SRS-023). **The method is unchanged:** the mean of the configured passes, the same threshold and the same metrics. **Added 2026-10-04**, after two unseeded evaluations of one checkpoint differed in 49 aggregate figures (`docs/13`). | URS-010, NFR-002 | TC-128 |
| SRS-096 | The re-evaluation of `docs/07` §17.11 shall run through one chain that performs its steps in §17.11's order and stops at the first failure without retrying: (1) refuse to start unless the working tree is clean, the inversion fix is an ancestor of `HEAD`, every checkpoint is present, no output exists and the chain has not run before; (2) read `sealed.access_count` for all six sealed buckets and stop on any difference from the counts §17.11 states; (3) run two seeded evaluations of `cirrus_holdout`'s open `val` bucket and stop unless both are seeded and IDENTICAL under SRS-090; (4) evaluate the open `val` buckets of `spectralis_holdout` and `topcon_holdout`; (5) evaluate the six sealed buckets, each opened with an `Unlock` naming §17.11. Every output shall be a new file under a `corrected/` folder of its run directory. **Added 2026-10-22.** | URS-007, URS-010 | TC-137 |
| SRS-102 | The HD95 re-evaluation of `docs/07` §17.12 shall run through one chain with the steps, refusals and order of SRS-096, taking the HD95 fix as the required ancestor and writing only new files under a `corrected_hd95/` folder of each run directory. **It shall stop, after each evaluation and before the next unlock, unless every value of the new record other than HD95 equals the 24 October corrected record exactly**: every Dice, sensitivity, specificity and AUROC with its interval and `n`, every per-volume row's Dice, predicted and reference voxel counts, reference presence and detection score, and every record field outside segmentation, provenance excepted. **Only HD95 may change.** **Added 2026-10-26.** | URS-007, URS-010 | TC-150 |
| SRS-103 | An **independent cross-check** shall recompute every segmentation metric of every volume in the **open `val` buckets only**, refusing any sealed bucket through the SRS-088 gate with no unlock. It shall use an implementation that shares no code with the project's reader or metrics: its own MetaImage parse, Dice from counts, mm³ from the header's spacings, and HD95 by a different algorithm (surface points and a nearest-neighbour tree). It shall compare the result per volume and class with the pipeline's and with the stored record: Dice and voxel counts exactly, mm³ to 1e-12 relative, HD95 to 1e-9 mm. It shall write numbers only, never a mask or pixel value. **Added 2026-10-29** from the audit of 2026-10-28, step 2. | URS-007, URS-010 | TC-152 |
| SRS-104 | Beside the pre-registered HD95, in which a volume whose prediction and reference are both empty scores 0 mm and is averaged in, the evaluation record shall carry a **secondary HD95** per fluid class and per vendor that **excludes those volumes**, with its patient-level interval and `n` (SRS-087), in a block of its own labelled secondary. The pre-registered HD95 shall stay the primary figure and shall not change. The report generator shall print the secondary HD95 beside the primary, labelled secondary, wherever the records carry it. Both-empty is decided from the volume's own predicted and reference voxel counts, so the figure is recomputable from the per-volume rows (SRS-089). **Added 2026-10-29** (finding D3): the both-empty zeros pull a mean HD95 toward 0 in proportion to the class-absent case mix, which differs by vendor and arm. | URS-007 | TC-153 |
| SRS-105 | The final re-evaluation of `docs/07` §17.13 shall run through one chain that performs §17.13's steps in order and stops at the first failure without retrying. (0) It shall refuse to start on a dirty tree, when any fix §17.13 names is absent by its behaviour, when a checkpoint or a previous record is missing, when any output exists, or when it has run before. (1) It shall stop on any access count differing from §17.13's table. (2) It shall run two seeded `cirrus_holdout` `val` evaluations and stop unless they are IDENTICAL under SRS-090. (3) It shall evaluate the `spectralis_holdout` and `topcon_holdout` `val` buckets. (4) It shall evaluate the six sealed buckets, each opened with an `Unlock` naming §17.13 and §17.7(b). (5) It shall regenerate the illustrative B-scans of §21.10. (6) It shall check the access counts after. **After every evaluation it shall stop unless the population and the reference are unchanged from the bucket's previous record**: the fold, bucket, patient and volume counts, vendors, unit, bootstrap block, threshold and passes; the per-volume rows as a set, with each row's reference presence and reference voxel count; and every AUROC's counts of positives and negatives. Every output shall be a new file under an `audited/` folder of its run directory, or under `artifacts/illustrations_audited/`. **Added 2026-10-29.** | URS-007, URS-010 | TC-154 |
| SRS-106 | When given an output folder, the evaluation shall **save every predicted label map** it measures, in native geometry and exactly as measured, one compressed file per volume holding the map, the spacing it was measured with and the per-class detection scores, written with the standard library and NumPy only, with a fixed timestamp so that identical maps give identical files. It shall refuse a folder that already holds a file, and never overwrite one. The evaluation record shall carry a **manifest**: per volume, the file name, its SHA-256, the SHA-256 of the map's bytes, its shape and type. **Re-measuring a saved map against the volume's reference shall reproduce that volume's per-volume rows exactly**, through the same function the evaluation uses, so that a defect found later in measurement is corrected by re-measuring, without the model or the GPU. The files are local derived data (`docs/06` DMP-C13): never committed, uploaded or published. Re-measuring a sealed bucket's maps reads its reference and so is an access of that bucket under SRS-088; this requirement grants none. **In the chain of SRS-105**, every evaluation shall save its maps; the gate shall also stop unless the manifest names exactly the record's volumes and every file exists and matches its SHA-256; and the chain shall refuse to start when the drive holding `artifacts/` has less free space than the maps would take uncompressed. **Added 2026-10-29**, before the final run of `docs/07` §17.13. | URS-007, URS-010 | TC-155 |
| SRS-107 | **No sealed bucket shall be opened without a completed dry run of the code that opens it.** The SRS-088 gate shall refuse a sealed bucket unless the process names a dry-run certificate that: records every step of its chain as completed on synthetic data; was written at the repository's current commit, on a clean working tree; and lists that fold and bucket among the buckets the chain may open. A refusal shall happen before anything is logged or read. The one exception is an access log marked as a synthetic sandbox, which is where a dry run opens its own synthetic buckets; the repository's own `artifacts/` shall never be accepted as a sandbox, whatever it contains. Every chain that opens a sealed bucket shall, before its first unlock, run every one of its steps in such a sandbox, through the same scripts and arguments, and write the certificate only if all of them complete. **Added 2026-10-30** after the §21.10 run opened three sealed buckets and then failed on a defect any synthetic run of its `main` would have shown. | URS-007, URS-010 | TC-156 |
| SRS-108 | The illustrative B-scans of `docs/07` §21.11 shall be drawn **from the label maps saved by the final run (SRS-106), with no model and no GPU**. Each pick, chosen by the §21.2 rule from the §17.13 held-out records, shall have its saved map checked against the record's manifest, by the file's SHA-256 before any bucket is opened and by the map's SHA-256 after loading. Its saved spacing shall equal the spacing checked from the archive (SRS-057), its shape the reference's, and its Dice and predicted voxel count, re-measured against the reference, the record's exactly. Any difference saves no image. The chain that runs it shall check the access counts before and after and run the SRS-107 dry run before the first unlock. **Added 2026-10-30.** | URS-007 | TC-157 |
| SRS-109 | **Every module under `src/` and every script under `scripts/` shall pass a static type check with zero findings**, in CI and before every commit, under the configuration in `pyproject.toml`: mypy at the pinned version, the bodies of unannotated functions checked too, and no finding silenced by an inline ignore. A name shall not be rebound to a value of another type in the same scope. **Added 2026-10-30** after the §21.10 run failed on exactly that: a name holding the records the gate compared with was rebound to the spacing, which a type checker reports and no test of the parts had exercised. | NFR-005 | TC-158 |

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
| SRS-032 | Segmentation performance shall be computed as Dice and HD95, separately for each of IRF, SRF and PED. A foreground-aggregate figure shall not be reported in place of the per-class figures. **Amended 2026-10-26:** HD95 shall be computed in millimetres with **each array axis given its own physical spacing**: for a volume stored as (B-scans, rows, columns), that is (B-scan separation, axial, lateral), reordered from the project's (axial, lateral, separation). Until 2026-10-26 the spacing reached HD95 in project order, which put it on the wrong axes (`docs/13`, finding of 2026-10-25). | URS-007 | TC-060, TC-149 |
| SRS-033 | Every reported metric shall be accompanied by a bootstrap 95% confidence interval and the number of units it was computed over. A point estimate shall not be emitted without both. | URS-007 | TC-061 |
| SRS-034 | Bootstrap resampling shall be seeded from the run configuration and shall reproduce exactly on re-execution. | URS-010 | TC-062 |
| SRS-035 | No accuracy metric shall be provided or reported. | URS-007 | TC-002 |
| SRS-036 | Results shall be broken down by vendor, reporting held-out-vendor performance, in-domain reference performance, and the difference between them, per fluid class. | URS-007 | TC-063 |
| SRS-037 | The rendered results table shall state, for every figure, the fluid class, the vendor, the confidence interval and the sample size. | URS-007 | TC-064 |
| SRS-050 | Volume-level detection of each fluid class shall be **derived from the segmentation output of the same model**. No separate classifier shall be trained, stored or served, and no forward pass shall be required beyond the MC-dropout passes of SRS-029. | URS-001, URS-007 | TC-065 |
| SRS-051 | A fluid class shall be reported present in a volume when the number of voxels predicted for that class exceeds a threshold read from the run configuration. The threshold shall not be hard-coded, and its resolved value shall be written to the run output with the rest of the configuration. | URS-007, URS-010 | TC-066 |
| SRS-052 | The continuous score used for AUROC shall be derived, per class and per volume, from the MC-dropout mean class probability produced by SRS-029. **AUROC shall be computed in numpy in `eval/metrics.py`**, on the same terms as every other reported metric: `docs/10`'s credibility rests on the figures being independently computable without a torch or scikit-learn runtime. scikit-learn shall be used **only as an independent reference in a back-to-back test**, never as the source of a reported number — the arrangement TC-120 already uses for MONAI. **Amended 2026-10-29 (finding D4):** the score is the highest mean probability **over the native content of each frame only**: the rows and columns the inversion of SRS-074 keeps, computed by the same function. The padding added to reach `roi_size` holds no acquisition, and a score taken over it could rank a volume on probability no native voxel carries, while presence (SRS-051) is counted on the native grid. Until 2026-10-29 the maximum ran over the padded frame (`docs/13`). | URS-005, URS-007 | TC-067 |
| SRS-092 | The published report page (`site/`) shall be **generated from the recorded evaluations, never typed**. A build step shall read the evaluation records, epoch logs and split files, and the measured values in `docs/06`, and write data files and CSV downloads; the page shall render every table, chart and number in its prose from those files, and its template shall carry no hand-typed number outside a stated allowlist. Every value shall equal its record, and every count the prose states shall be computed and checked against the document that states it. **The page shall carry no image data and nothing that relinks a row to a subject**: no B-scan, mask or predicted segmentation; no source subject identifier, SOP Instance UID or reference voxel count; and per-scan rows ordered by value, so that their order cannot stand in for the identifier removed (`docs/06` DMP-C2, DMP-C11). Per-scan reference presence is used by the charts only: it shall not appear in any downloadable file, as a field or through row order (`docs/06` §2.5, J2). The chart library shall be loaded at an exact version with an integrity hash, and every chart shall have a static fallback. Two builds from the same inputs shall be byte-identical. **Added 2026-10-07.** | URS-007, NFR-002 | TC-129, TC-130, TC-131 |
| SRS-093 | The illustrative B-scans (`docs/06` §2.2.2) shall be selected, regenerated and rendered by a script that implements `docs/07` §21 exactly. **Selection** shall be a deterministic function of the seeded held-out records alone, the same for any order of their rows, and shall yield at most six distinct scans. **Regeneration** shall reuse the evaluation path of `scripts/05_evaluate.py` unchanged, run on the GPU, and open each held-out run's sealed bucket only with an `Unlock` naming the reason and the approver (SRS-088). **No image shall be saved unless every chosen scan's regenerated Dice and predicted voxel count, for all three fluid types, equal its sealed record exactly**; on any mismatch nothing is saved and the failure is reported by role, never by identifier. **Each image** shall be a PNG with no text, time or other metadata chunk, whose only text is the panel titles and the fluid-type key; **captions** shall carry no case identifier, filename, brand or date. Everything shall be written under `artifacts/`, and the script shall print no pixel content (DMP-C12). **Added 2026-10-14.** **Amended 2026-10-24 for the regeneration of `docs/07` §21.9:** selection and the exact-match gate shall use the corrected records of §17.11 and no other; the `Unlock` reason shall cite both §17.11 and §21, and a reason that does not shall be refused before anything runs; and the script shall refuse an output directory that already holds files, so that no earlier run's images are overwritten. | URS-007, NFR-002 | TC-132, TC-133, TC-134, TC-146 |
| SRS-053 | Detection performance shall be reported as sensitivity, specificity and AUROC, per fluid class and per scanner platform, each accompanied by a bootstrap 95% confidence interval and the sample size, on the same terms as SRS-032 and SRS-033. | URS-007 | TC-068 |
| SRS-097 | Every **derived** figure in `docs/10` shall be generated by committed code, `eval/report.py`, from the evaluation records, and never by analysis outside the repository. A derived figure is one computed from records, not copied from one. The generator shall produce, in the report's own row formats: the per-fold overlap verdicts and gap directions (§3); the cirrus draw comparison (§3.1); the post-hoc AUROC intervals, with "not estimable" where every resample scores 1, and the unstratified comparison stated beside them (§4); the pooled all-volume Dice and class-absent shares (§5.2); the class-present Dice per fold and pooled (§5.3); the directly bootstrapped differences, their half-widths and exclusion counts (§5.4); the absent-volume Dice counts and the count of cells where class-present exceeds all-volume Dice (§7.1); the fragility shift (§7.2); the validation-selected threshold of `docs/07` §19.2 (§7.3); the in-domain interval widths (§8.3); and the superseded tables of §10, from the records measured through the inversion defect. **Each bootstrap shall take its seed, replicate count and α from the record's own `bootstrap` block**, and the §19.2 grid shall equal the one `docs/07` §19.2 declares. It shall read only records already written and open no sealed bucket. **Added 2026-10-24.** **Amended 2026-10-29 (finding D2):** a difference between two arms shall be bootstrapped under **one patient draw**, as SRS-087 and `subgroup.generalisation_gap` require. Patients are grouped by the arms they belong to (held-out only, in-domain only, both); each group is resampled with its size fixed, in that order; and a patient drawn counts in every arm it belongs to, with that arm's value. Where the arms share no patient, as in every per-fold comparison, this is exactly the earlier independent resample, held-out first. The pooled arms share patients (every in-domain patient is also a held-out patient in its own vendor's fold), and the independent resample ignored that pairing. **Amended 2026-10-30 (the author's decision):** the superseded figures of `docs/10` §10 and of `docs/12`'s last section are kept as published, so they shall be regenerated with the estimator they were published with, the independent resample, held-out first, and the documents shall say beside them that the joint draw would give different pooled intervals. Every current figure uses the joint draw. **Amended 2026-10-29 (finding D9):** every figure the generator or the page states shall be rounded **once, from the unrounded value**, and percentages rounded **half up**, as a reader rounds. A half-width rounded to two places and then to one could print 0.2 for 0.251. | URS-007, URS-010, NFR-002 | TC-138, TC-139, TC-140, TC-141, TC-142 |
| SRS-098 | The generator shall provide a **check** that compares every derived row and count it produces with what `docs/10`, `docs/12` and `README.md` state. It shall exit non-zero on any difference in value or text, on a generated row the document lacks, and on a current-figure row the document carries that the generator does not produce. Rows labelled as measured through the defect shall be compared only with the superseded records, and rows labelled as HD95 measured on the wrong spacing axes only with the 24 October records; every other figure shall be compared with the records of `docs/07` §17.12. It shall report each difference with its document and location, and it shall **never edit a document**. The report page build (SRS-092) shall take its derived figures from the same generator, not from its own copy of the arithmetic. **Added 2026-10-24; the record sets amended 2026-10-28 for the §17.12 records.** **Amended 2026-10-29 (finding D10):** a statement shall be found only as a whole: not inside a longer number or word, so that "5% against" is not found in "15% against" nor "about 0.14" in "about 0.145". The generator shall produce its statements, without failing, for any record set, including counts of zero and empty lists. | URS-007, URS-010, NFR-002 | TC-143, TC-144 |
| SRS-099 | A **pre-commit hook** shall run the check of SRS-098 whenever a commit changes `docs/10`, `docs/12` or `README.md`. When the evaluation records are present it shall **block** the commit on any difference. When they are absent it shall let the commit proceed, but print a warning that names the check, says it **did not run** and says why. It shall **never skip silently**. **When the records are present but no interpreter available to the hook can import the project, it shall block the commit**, because the machine that should run the check has a broken environment. **Added 2026-10-24; the blocking case amended the same day by the author's decision.** | URS-010, NFR-002 | TC-145 |

### 3.7 Segmentation and structured report output

| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-038 | Segmentation results shall be written as DICOM Segmentation objects via `highdicom`, with one segment per fluid class using the label indices of SRS-002. **Clarified 2026-10-29 (finding D11):** each segment's number is its label index read from `configs/data.yaml`, whatever order the caller passes the segments in. Since highdicom numbers segments consecutively from 1, a Segmentation carries every configured fluid class (an absent class as an empty segment), and the writer refuses a subset, a repeated class or an unknown label rather than renumber. Until 2026-10-29 segments were numbered by their position in the caller's list. | URS-001, URS-004 | TC-070 |
| SRS-039 | The Segmentation object shall reference the source image instances it was derived from, so that it can be opened and reviewed against those images in standard DICOM tooling. | URS-004 | TC-071 |
| SRS-040 | A Structured Report shall record, for the imaged eye, the volume in cubic millimetres of each fluid class, computed from the segmentation and the acquisition's own voxel spacing. | URS-002 | TC-072 |
| SRS-057 | The voxel spacing used to compute a volume shall be asserted bit-identical to the spacing recorded at ingestion for that acquisition. Any difference shall abort before a volume is emitted. **Clarified 2026-10-29 (finding D5):** the assertion compares the spacing **read from the source at the time of measurement** with the manifest's ingestion record, and the value it returns is the one measured with. Comparing the recorded value with itself, as `05_evaluate.py` did, cannot fail and does not satisfy this requirement. | URS-002, URS-010 | TC-073 |
| SRS-058 | The Structured Report shall state the units of every quantity it carries explicitly. Units shall not be implied by convention or inferred by a consumer. | URS-002 | TC-074 |
| SRS-059 | The Structured Report shall record, for each fluid class, the predicted voxel count and the voxel volume used, alongside the resulting volume in cubic millimetres, so that the derivation can be recomputed from the object alone. | URS-002, URS-010 | TC-075 |
| SRS-041 | The Structured Report shall record the scan-level confidence and the review-recommended indication of SRS-030. These shall not appear only in run logs. **Clarified 2026-10-29 (finding D6):** every Tracking Unique Identifier the report carries, the confidence group's included, shall be a valid UI value: digits and full stops only, no component with a leading zero, at most 64 characters. Each is derived from the device UID and the group's position as a name-based UUID in the `2.25.<integer>` form of PS3.5 §B.2, which is valid whatever the device UID's length. Until 2026-10-29 each finding's was `{device UID}.{n}`, longer than 64 characters for a device UID of full length, and the confidence group's `{device UID}.confidence`. | URS-005 | TC-076 |
| SRS-042 | Every emitted Segmentation and Structured Report object shall carry, within the object, a designation readable both by software and by a person that the result is research-use-only, not clinically validated, and produced by an automated method requiring human review. The means of expressing this is specified in `docs/11` and is unresolved at the time of this draft (§6, item 1). | URS-011 | TC-077 |
| SRS-065 | Where a coded concept has no verified code in a standard scheme, the software shall use a coded value from a declared private coding scheme and shall identify that scheme within the emitted object. It shall not borrow an approximately-fitting standard code. A caller-supplied coded concept shall always take precedence. | URS-001, URS-011 | TC-076 |
| SRS-095 | Every text value in an emitted Ophthalmic Tomography Image, Segmentation or Structured Report object shall be representable in the object's declared character set; where Specific Character Set (0008,0005) is absent, that is the default repertoire, so every text value shall be ASCII. Encoding an object shall never substitute a character. **Added 2026-10-16**, after an em dash in the private coding scheme's declaration was stored as `?` in every SEG and SR (`docs/11` §10 item 7). | URS-004, URS-011 | TC-136 |

### 3.8 PACS communication

| ID | Requirement | Trace (URS) | Verified by (TC) |
|---|---|---|---|
| SRS-043 | The software shall store objects to, and retrieve objects from, a DICOMweb endpoint configured at runtime, using STOW-RS and WADO-RS. | URS-010 | TC-080, TC-112 |
| SRS-044 | A stored object shall be retrievable and shall match what was sent in its pixel data, its fluid volumes, its confidence value and its research-use designation. | URS-010, URS-011 | TC-081, TC-112 |
| SRS-045 | The software shall perform no action against the PACS beyond storing and retrieving its own objects. It shall not delete, modify or reconcile existing content, and it shall not mark any object as final, verified or signed off. | URS-003 | TC-082 |
| SRS-060 | The DICOMweb client shall take its entire configuration from the run configuration and shall not read ambient environment configuration — no `.netrc`, no environment-supplied proxy or certificate settings. Sessions shall be constructed with `trust_env=False`. | URS-003, URS-010 | TC-083 |
| SRS-094 | Continuous integration shall execute the PACS round-trip tests (`requires_pacs`) in a job of their own that gates CI, against an Orthanc container started from the image digest pinned in SOUP-014 and configured from `docker/orthanc/orthanc.json`. The container's HTTP port shall be published on the runner's loopback address only, and no other port shall be published. The job shall send only synthetic objects created by its tests, shall upload no artifact, and shall remove the container when it ends, pass or fail (`docs/06` §7.2.1). **Added 2026-10-15.** | URS-010 | TC-135 |

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
| `io/retouch_reader.py` | SRS-001, SRS-003, SRS-004, SRS-005, SRS-054, SRS-055, SRS-056, SRS-070 |
| `io/metaimage.py` | SRS-001, SRS-003, SRS-004, SRS-005 |
| `io/dicom_writer.py` | SRS-006..SRS-011, SRS-054, SRS-062, SRS-063, SRS-064, SRS-066, SRS-095 |
| `io/deident.py` | SRS-012..SRS-017, SRS-054 |
| `io/dicomweb.py` | SRS-043, SRS-044, SRS-045, SRS-060 |
| `data/splits.py` | SRS-018..SRS-023, SRS-067, SRS-068, SRS-069, SRS-071 |
| `data/transforms.py` | SRS-070, SRS-072, SRS-073, SRS-074 |
| `data/datamodule.py` | SRS-070, SRS-071, SRS-073, SRS-078 |
| `training/checkpoint.py` | SRS-075, SRS-076, SRS-077 |
| `training/loop.py` | SRS-024, SRS-031, SRS-075..SRS-077, SRS-079, SRS-080, SRS-081, SRS-083 |
| `training/telemetry.py` | SRS-082 |
| `training/losses.py` | SRS-084 |
| `runs.py` | SRS-031, SRS-086 |
| `eval/metrics.py` | SRS-032..SRS-035, SRS-052, SRS-053, SRS-087 |
| `eval/sealed.py` | SRS-088 |
| `eval/pipeline.py` | SRS-050..SRS-053, SRS-074, SRS-087, SRS-088, SRS-089, SRS-104 |
| `eval/subgroup.py` | SRS-087 |
| `models/uncertainty.py` | SRS-029, SRS-030, SRS-091 |
| `scripts/benchmark_device.py` | SRS-031 |
| `scripts/compare_evaluation_records.py` | SRS-090 |
| `scripts/05_evaluate.py` | SRS-091 |
| `scripts/10_reevaluate.py` | SRS-096 |
| `scripts/12_reevaluate_hd95.py` | SRS-102 |
| `scripts/13_crosscheck_val.py` | SRS-103 |
| `scripts/14_final_reevaluation.py` | SRS-105 |
| `eval/report.py`, `scripts/11_report_tables.py` | SRS-097, SRS-098, SRS-104 |
| `scripts/check_report_tables_hook.py`, `.pre-commit-config.yaml` hook `report-tables` | SRS-099 |
| `scripts/08_build_site.py` | SRS-092 |
| `scripts/09_illustrative_bscans.py` | SRS-093 |
| `.github/workflows/ci.yml`, job `pacs` | SRS-094 |
| `data/datamodule.py` | SRS-024 |
| `data/transforms.py` | SRS-025, SRS-026 |
| `models/seg_unet.py` | SRS-027, SRS-028, SRS-061 |
| `models/uncertainty.py` | SRS-029, SRS-030 |
| `eval/metrics.py` | SRS-032, SRS-033, SRS-034, SRS-035, SRS-040, SRS-050, SRS-051, SRS-052, SRS-053, SRS-059 |
| `eval/subgroup.py` | SRS-036, SRS-053 |
| `eval/report.py` | SRS-037 |
| `report/seg_object.py` | SRS-038, SRS-039, SRS-042, SRS-065, SRS-095 |
| `report/coding.py` | SRS-065, SRS-095 |
| `report/sr_object.py` | SRS-040, SRS-041, SRS-042, SRS-054, SRS-057, SRS-058, SRS-059, SRS-095 |

SRS-040 and SRS-059 appear against two modules deliberately: `eval/metrics.py` performs
the arithmetic as a pure function over arrays, and `report/sr_object.py` records the
result and its terms in the SR. Splitting them is what lets the volume derivation be
verified by TC-072 without a DICOM runtime.
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
3. Training executes on the author's local workstation, and the dataset is never uploaded anywhere (`docs/06` §7.1); this specification governs the pipeline, not the training host. **Corrected 2026-10-15:** this item previously read "Training executes on Kaggle", which the local-training decision of 2026-09-25 superseded and this item was not updated for (`docs/13`, 2026-10-15). The Kaggle notebook is kept, never used, as `docs/06` §7.1 records.
4. Orthanc in Docker is the DICOMweb peer for SRS-043..SRS-045. No other PACS is assumed conformant.
5. MONAI provides transforms, networks and metrics; `pydicom` and `highdicom` provide DICOM read, write and de-identification primitives. SOUP entries in `docs/04` govern.
6. The UID root in `configs/data.yaml` is a placeholder, as that file states, and will remain one. SRS-007 requires UIDs to be generated under the configured root; it asserts nothing about that root being registered, and the objects this software creates are confined to the local Orthanc instance in consequence (`docs/06` §7.2). The one exception, from 2026-10-15, is synthetic test objects sent to an ephemeral Orthanc in CI that is destroyed with its job (`docs/06` §7.2.1, SRS-094).

## 6. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | SRS-042: the conformant means of expressing the research-use-only designation inside a SEG and an SR is unresolved. Carried from `docs/01` §8 item 1; to be settled in `docs/11` before milestone 6. | `docs/11`, milestone 6 |
| 2 | SRS-048: the criteria for judging a volume in or out of scope depend on what the converted DICOM objects carry, which is not known until milestone 3. The requirement is deliberately not narrowed on speculation. Carried from `docs/01` §8 item 2. | Milestone 3 |
| 3 | ~~SRS-007: the UID root is a placeholder.~~ **Resolved 2026-09-16:** the placeholder is documented rather than replaced, and no root will be registered. UIDs under it carry no claim of global uniqueness and objects must not leave the local Orthanc instance. Recorded in `docs/06` §7.1, `docs/11` §7 and §10, and the README. | — closed |
| 4 | SRS-030: the confidence threshold for recommending review has no value yet. It cannot be chosen before evaluation data exists, and choosing it will be a change-controlled decision under NFR-007. | Milestone 5 |
| 6 | ~~§3.6 specifies segmentation metrics only.~~ **Resolved 2026-09-17:** SRS-050..SRS-053 specify volume-level detection derived from the segmentation output — no second model, no second training run. scikit-learn (SOUP-008) now supports SRS-053. | — closed |
| 5 | Hazard and test allocations are absent throughout §3. They are filled as `docs/05` and `docs/07` are drafted; `docs/09` carries the coverage count until then. | `docs/05`, `docs/07` |
