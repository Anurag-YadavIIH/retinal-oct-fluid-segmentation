<!--
Document: Data Management Plan
Status: DRAFT v0.1
Owner: Anurag Yadav
Last reviewed: 2026-09-16
Change history: docs/13_change_control_log.md

Ordering note: this document is drafted ahead of docs/01-03, out of the
milestone sequence. This is deliberate and is not a violation of CLAUDE.md
rule 1. Rule 1 governs code, not documents: no code depends on this file.
The licence analysis in section 2 determines whether the project's chosen
dataset is usable at all, and that question must be answered before four
weeks of work are committed to it. Trace columns referencing SRS and RC
identifiers are left as TBD until docs/02 and docs/05 exist.
-->

# Data Management Plan

## 1. Data sources and provenance

### 1.1 Primary dataset — RETOUCH

**RETOUCH** (Retinal OCT Fluid Detection and Segmentation Benchmark and Challenge),
organised in conjunction with MICCAI 2017 and hosted at
`https://retouch.grand-challenge.org/`.

| Property | Value |
|---|---|
| Modality | Spectral-domain optical coherence tomography (SD-OCT), macular volumes |
| Tasks supported | Fluid detection; fluid segmentation |
| Public training volumes | 70 |
| Subjects | One volume per subject |
| Vendors | Zeiss Cirrus, Heidelberg Spectralis, Topcon |
| Diseases | Macular edema secondary to AMD and to retinal vein occlusion (RVO) |
| Classes | IRF (intraretinal fluid), SRF (subretinal fluid), PED (pigment epithelial detachment) |
| Format | ITK MetaImage — ASCII header plus separate raw binary (`oct.mhd` / `oct.raw`, `reference.mhd` / `reference.raw`) |
| Label encoding | Voxel-wise; all non-fluid voxels labelled 0 |

### 1.2 Reference standard provenance

Annotations are manual, voxel-wise, produced at two clinical centres:

| Centre | Graders | Supervision |
|---|---|---|
| Medical University of Vienna, Austria | 4 | One ophthalmology resident; all graders trained by two retinal specialists |
| Radboud University Medical Center, Nijmegen, Netherlands | 2 | One retinal specialist |

**Known limitation (carry into `docs/10` §8):** the challenge publication does not
provide per-case inter-rater agreement for the released training annotations, and
cases were not double-graded. Reference-standard variability is therefore an
unquantified component of every metric reported by this project. This must be
stated in the analytical validation report rather than left implicit.

### 1.3 Test set availability

Only the **training** partition carries public reference annotations. The official
test partition is withheld for challenge submission scoring. All cross-vendor
folds in this project are therefore constructed **within the 70 public volumes**.

Consequence: each held-out vendor fold has an evaluation set of roughly 22–24
subjects. Confidence intervals will be wide and must be reported with the sample
size visible in every results table. Narrow intervals from this dataset would
indicate a bug, not a good model.

---

## 2. Licence and terms of use

### 2.1 Terms as stated by the organisers

**Superseded source.** This section previously quoted the challenge rules page. The
governing document is the **signed Agreement of Data Confidentiality**, emailed to the
organisers on 2026-09-20; registration was submitted 2026-09-20 17:35 and accepted
2026-09-21. Where the two differ, the signed agreement governs, and it is narrower.

The agreement's purpose clause:

> the dataset is to be used solely for evaluating fluid detection and segmentation
> methods through the RETOUCH Challenge and for no other purpose.

The agreement further obliges the recipient:

- not to give or distribute the data to any person outside the single named recipient;
- **not to reidentify, or attempt to reidentify, the data or any individual within it**;
- to delete the data if the organisers withdraw authorisation, which they may do at any
  time (see §8).

For comparison, the rules page wording this section previously relied on was: data "may
be used only for evaluating fluid segmentation methods and participating in the
challenge, and may not be used to train or develop other algorithms". The difference
that matters is analysed in §2.2.

Only the **training** partition was downloaded, on 2026-09-21. The test partition was
deliberately not taken: it carries no public reference annotations and §1.3 already
scopes all evaluation to the 70 training volumes. Declining data that cannot be used is
the narrowest reading of "for no other purpose" available at the point of download.

### 2.2 Analysis — reassessed against the signed agreement, 2026-09-23

The interpretation below was written against the rules page. It has been re-examined
against the agreement wording and **it does not survive intact.** The qualification is
recorded rather than the conclusion quietly adjusted.

**What still holds.** Training a fluid segmentation model on these volumes and measuring
its performance is *evaluating a fluid detection and segmentation method*. That is the
literal activity the purpose clause permits, it is what the RETOUCH benchmark paper
describes participants doing, and it is what the downstream literature does. Nothing in
the agreement prohibits the technical work this project performs. DMP-C4 keeps the scope
to fluid segmentation and detection and nothing else.

**What no longer holds.** The previous position was that publishing a method and its
results in a public repository "falls within participation in the challenge". Two
phrases in the agreement make that materially harder to sustain:

- **"through the RETOUCH Challenge"** binds the permitted evaluation to the challenge
  *mechanism*, not merely to the challenge's subject matter. This project has made no
  submission, so its evaluation is not conducted through the challenge in any ordinary
  reading.
- **"and for no other purpose"** closes the interpretive gap the rules page left open.
  A portfolio artefact demonstrating the author's capability is a second purpose,
  running alongside the evaluation, even though the technical activity is identical.

The honest summary is that **the activity conforms and the publication may not.** The
earlier text treated a genuine ambiguity as settled in the project's favour, which is the
error this document exists to avoid.

### 2.2.1 Resolved by the organiser, 2026-09-23

**Question asked.** On 2026-09-23 the author wrote to **Dr Hrvoje Bogunović**, a RETOUCH
challenge organiser, asking whether publishing the method and its results in a public
code repository — with no data redistributed — falls within the Agreement's permitted
use.

**Answer received.** The same day, Dr Bogunović confirmed that **publishing results
outside the challenge itself is permitted.**

**Scope of what this settles, and what it does not.** The answer covers the publication
of results derived from the data. It is not a general waiver: everything else in the
agreement stands unchanged — no redistribution of the data (DMP-C1), single-recipient
access (DMP-C5, §7), no reidentification (DMP-C11), scope limited to fluid segmentation
and detection (DMP-C4), and retention at the organisers' discretion (§8). Nothing here
permits sharing the dataset, and nothing here changes what §8 requires on a withdrawal
of authorisation.

**This supersedes the reading in §2.2; it does not confirm it.** That distinction
matters and is recorded rather than smoothed over. §2.2 examined the agreement's wording
— "through the RETOUCH Challenge and for no other purpose" — and concluded the
publication **may not be permitted**. The organiser's answer is that it is. The
project's own interpretation of the binding document was therefore **more restrictive
than the rights-holder's**, and it is the organiser's reading that governs, because they
are the party the obligation is owed to. §2.2 is retained above as the reasoning that
prompted the question, not as a position the project still holds.

**Consequence.** `docs/10` and `docs/12` are **unblocked** and may be published. The
online challenge submission remains planned, and is no longer a dependency of
publication — it was previously the only option that removed the question outright.
`docs/08` was never affected; it reports test execution rather than dataset-derived
findings.

### 2.3 Controls adopted as a consequence

| ID | Control | Implementation |
|---|---|---|
| DMP-C1 | No redistribution of source data | `data/` is excluded in `.gitignore`; `check-added-large-files` pre-commit hook; no data in container images |
| DMP-C2 | No redistribution of derived imagery at volume scale | Only illustrative single B-scans appear in figures, in the quantity conventional for a publication |
| DMP-C3 | No commercial use | Repository licensed MIT for **code only**; README states the dataset carries separate terms |
| DMP-C4 | Scope limited to fluid segmentation and detection | No secondary task, no pretraining for unrelated models, no derivative dataset published |
| DMP-C5 | Single registered user | Data accessed under one registration by a single named recipient; not shared with any third party (§7) |
| DMP-C11 | **No reidentification, and no attempt at it** | No linkage to any external dataset, no demographic inference, no attempt to recover subject identity from image content or metadata. Technically, the salted-hash pseudonyms of SRS-013 are one-way and the salt is never committed, so this project's own outputs cannot be relinked to source identifiers by anyone reading the repository. Carried as RC-030 in `docs/05` |

### 2.4 Decision gate — closed 2026-09-23, not triggered

The gate: if the interpretation in §2.2 were judged untenable, the project would migrate
to the alternative sources in §9 rather than proceed. It was placed before milestone 3
so that reversal would cost days rather than weeks.

**It is closed without being triggered.** The condition was an interpretation that could
not be sustained. The interpretation was indeed not sustainable — §2.2 says so — but the
question it turned on was answered directly by the rights-holder (§2.2.1) rather than
resolved by further reasoning, and the answer permits the use. There is nothing left for
the gate to protect against.

The gate is judged to have worked. Its function was to force the question to be settled
**before** weeks of work depended on the answer, and that is what happened: the
uncertainty was identified at the point the binding document was first read, and
resolved the same week, before any model was trained on the data. §9 remains documented
as a contingency should authorisation ever be withdrawn under §8.

---

## 3. Dataset characteristics

### 3.1 Per-vendor composition

**Measured from the archive on 2026-09-23, replacing literature-derived figures.**
The subject counts and slice totals were correct. The Topcon per-volume figures were
not, and the reason they were wrong is instructive — see the note below the table.

| Vendor | Subjects | B-scan size (px) | B-scans/volume | Total slices |
|---|---|---|---|---|
| Cirrus | 24 | 512 × 1024 | 128 | 3,072 |
| Spectralis | 24 | 512 × 496 | 49 | 1,176 |
| Topcon | 22 | **512 × 650** (10 vols) and **512 × 885** (12 vols) | **128** (20 vols), **64** (2 vols) | 2,688 |
| **Total** | **70** | — | — | **6,936** |

Topcon in detail, because no single row describes it:

| Geometry | Volumes | Subjects |
|---|---|---|
| 512 × 650 × 128 | 10 | — |
| 512 × 885 × 128 | 10 | — |
| 512 × 885 × 64 | 2 | — |

**Why the old figure was wrong, and why that matters.** §3.1 previously recorded Topcon
as "512 × 885, ~122 B-scans". No Topcon volume has 122 B-scans; they have 128 or 64. The
figure was the total slice count divided by the subject count — 2,688 / 22 = 122.2 — an
average presented as though it described a volume. The total was right, which is exactly
why the error survived: every aggregate derived from it checked out. A mean over a
bimodal distribution names a value that nothing in the dataset has.

**Heterogeneity is intra-vendor, not only cross-vendor.** Topcon alone spans three
geometries, including a two-fold difference in slice count. The previous text argued
that geometric heterogeneity across vendors is part of the domain shift and must not be
normalised away; that argument now applies *within* Topcon as well, and SRS-010 and
SRS-026 are correspondingly more load-bearing than when they were written.

### 3.1.1 Pixel element types

Not previously recorded, and the reader must honour it:

| Vendor | `oct.raw` | `reference.raw` |
|---|---|---|
| Cirrus | `MET_UCHAR` (8-bit) | `MET_UCHAR` |
| Spectralis | **`MET_USHORT` (16-bit)** | `MET_UCHAR` |
| Topcon | `MET_UCHAR` (8-bit) | `MET_UCHAR` |

Reading a Spectralis volume as 8-bit, or a Cirrus volume as 16-bit, produces an array of
the wrong length and wrong values. The type must be taken from the header rather than
assumed, on exactly the grounds SRS-003 gives for voxel spacing.

In all 70 volumes the `oct` and `reference` headers agree on `DimSize` and
`ElementSpacing`, so no volume has a reference standard misaligned with its image.

### 3.1.2 Voxel spacing, measured per vendor

`ElementSpacing` is ordered (x, y, z) = (lateral within a B-scan, axial, B-scan
separation), all in millimetres.

| Vendor | Lateral (x) | Axial (y) | B-scan separation (z) |
|---|---|---|---|
| Cirrus | 0.011742 (constant) | 0.001955 (constant) | 0.046878 – 0.047244 |
| Spectralis | 0.010856 – 0.011950 | 0.003872 (constant) | 0.116380 – 0.128624 |
| Topcon | 0.011720 (constant) | 0.002600 **or** 0.003500 | 0.046880 (constant) |

Three observations that bear on requirements:

- **Every volume is strongly anisotropic**, so the isotropy rejection in
  `retouch_reader.validate_spacing` cannot fire on valid data.
- **Every component is far below the 0.5 mm physical bound** that guard uses — the
  largest is Spectralis B-scan separation at 0.129 mm. The bound is loose by roughly
  four-fold against real data, which is what it was designed to be.
- **Spectralis spacing varies per subject** in two of three axes, so per-vendor ranges
  must be ranges rather than constants. These figures are what `docs/07` open item 6
  needs to tighten the bound.

### 3.2 Class prevalence (voxel-wise, % of all voxels)

**Measured from all 70 reference volumes on 2026-09-23. The previous figures were
literature-derived and every fluid-class value was wrong**, several by large factors.
Both the pooled voxel count and the mean of per-volume percentages were computed; they
agree, so the discrepancy is not a difference of statistic.

| Vendor | Background | IRF | SRF | PED |
|---|---|---|---|---|
| Cirrus | 98.8437 | 0.4019 | 0.3515 | 0.4029 |
| Spectralis | 98.5173 | 0.5821 | 0.5777 | 0.3229 |
| Topcon | 99.4011 | 0.2043 | 0.0963 | 0.2983 |

Superseded figures, retained so the size of the correction is visible:

| Vendor | Background | IRF | SRF | PED |
|---|---|---|---|---|
| Cirrus | 98.95 | 0.04 (**10.0×** low) | 0.18 (2.0× low) | 0.83 (2.1× high) |
| Spectralis | 98.74 | 0.15 (3.9× low) | 0.39 (1.5× low) | 0.72 (2.2× high) |
| Topcon | 99.45 | 0.03 (**6.8×** low) | 0.06 (1.6× low) | 0.46 (1.5× high) |

The errors are not random: **IRF and SRF were understated in every vendor and PED was
overstated in every vendor.** That is a systematic pattern, which suggests the source
figures described something other than voxel-wise prevalence across the training
partition — a different partition, a per-lesion count, or a different definition — rather
than being noisy transcription. The source has not been re-identified and the measured
values govern.

**Foreground occupies between 0.60% and 1.48% of voxels.** This is the governing
constraint on evaluation design and drives three decisions recorded elsewhere:

1. **Accuracy is never reported.** A trivial all-background predictor scores
   **98.52% to 99.40%** on the measured data. The correction moved this figure by
   fractions of a percent and changed nothing about the conclusion: the prohibition was
   never close to marginal, and `src/ocuval/eval/metrics.py` still provides no accuracy
   function.
2. **Dice excludes background** (`loss.include_background: false` in
   `configs/train_seg.yaml`), otherwise the background term dominates the gradient.
3. **Per-class reporting is mandatory.** The rarest class is now **SRF on Topcon at
   0.0963%** rather than IRF on Topcon; an aggregate foreground Dice would let
   near-total failure on it hide behind the others. The conclusion is unchanged and the
   class it protects is different, which is a good illustration of why a requirement
   should be written against a property rather than against a number.

**Prevalence shift, remeasured.** The claim that prevalence varies "by a factor of
five across vendors for the same class" was based on the superseded IRF figures. Measured
cross-vendor ratios are:

| Class | Lowest vendor | Highest vendor | Ratio |
|---|---|---|---|
| IRF | Topcon 0.2043% | Spectralis 0.5821% | 2.8× |
| SRF | Topcon 0.0963% | Spectralis 0.5777% | **6.0×** |
| PED | Spectralis 0.3229% | Cirrus 0.4029% | 1.2× |

So the qualitative claim survives and its subject changes: the five-fold spread is real
but belongs to **SRF**, not IRF, and PED is nearly uniform across vendors. Cross-vendor
performance differences still conflate **appearance shift** with **prevalence shift**,
and `docs/10` must still say so — but the statement should now name SRF, where the
confound is strongest, and note that a PED difference across vendors cannot be explained
by prevalence at all.

### 3.2.1 Most volumes do not contain all three classes

Not previously recorded, and it governs how every metric behaves in practice:

| | Volumes containing the class |
|---|---|
| IRF | 55 of 70 |
| SRF | 37 of 70 |
| PED | 33 of 70 |
| **All three** | **12 of 70** |
| None at all | 0 of 70 |

**58 of 70 volumes lack at least one fluid class.** The empty-reference case is therefore
the common case, not an edge case, and the metric conventions fixed in `docs/13` are
exercised on most of the dataset rather than occasionally:

- Dice returns 1.0 when prediction and reference are both empty — correct agreement that
  a class is absent, and it will be the honest outcome for a large share of per-class
  evaluations.
- HD95 returns NaN when exactly one of the two is empty. For PED that arises whenever
  the model predicts anything in the 37 volumes with no PED, so **a substantial fraction
  of per-class HD95 values will be NaN by construction**.
- `bootstrap_ci` excludes NaN and reports the n actually used, which is why the sample
  size is carried alongside every figure. Without it a PED HD95 could be quoted over a
  handful of volumes and read as though it covered 70.

This is the strongest vindication available of the decision to return NaN rather than
inf: on this dataset, inf would have destroyed the majority of per-class HD95 aggregates
rather than a rare one.

### 3.3 Absent acquisition context

RETOUCH ships pixel data, a reference segmentation and voxel spacing. It does **not**
ship the ocular acquisition context a native DICOM OCT object would carry:

| Absent | Consequence |
|---|---|
| Image laterality (which eye) | No conformant `ImageLaterality` can be written; per-eye behaviour is untestable on this data (`docs/01` L8) |
| Fundus / reference photography image | Plane Position and Plane Orientation become required rather than optional, and neither can be populated (`docs/11` §10 item 3) |
| Patient coordinate frame | No meaningful `ImagePositionPatient` or `ImageOrientationPatient` |
| Acquisition date and time | `AcquisitionDateTime` is Type 1 and unconditional in the OPT IOD, so its absence is a conformance break, not a convenience |
| Scanner model and serial number | Type 1 in Enhanced General Equipment. Only the vendor is recorded, which is what `Manufacturer` carries |
| Operator identity | Not needed, and its absence is a de-identification benefit rather than a loss |

This is a property of a converted archive, not a defect in the dataset. It is recorded
here because the absence is a dataset characteristic, and its consequences are recorded
in `docs/11` (conformance) and `docs/01` L8 (limitation).

### 3.4 Image quality

Cirrus volumes are reported in the literature as lower in image quality than the
other two vendors. If held-out-Cirrus performance is the worst of the three folds,
quality is a candidate explanation alongside appearance shift, and the report
should say so rather than attributing the gap to domain shift alone.

---

## 4. On-disk layout and lifecycle

Stages are one-directional; each is produced by a numbered script and is
reproducible from the one before it.

**Corrected 2026-09-23 against the extracted archive.** The layout below previously
showed a vendor directory holding subjects directly. The archive nests one level deeper
and uses the organisers' own directory names, which are not the lowercase vendor keys
`configs/data.yaml` uses.

```
data/
├── raw/retouch/                          # 00 — manual download, immutable
│   ├── TrainingCirrus/RETOUCH-TrainingSet-Cirrus/TRAIN001..TRAIN024/
│   ├── TrainingSpectralis/RETOUCH-TrainingSet-Spectralis/TRAIN025..TRAIN048/
│   └── TrainingTopcon/RETOUCH-TrainingSet-Topcon/TRAIN049..TRAIN070/
│       └── each subject: oct.mhd, oct.raw, reference.mhd, reference.raw
├── dicom/                                # 01 — Ophthalmic Tomography Image objects
├── dicom_deident/                        # 02 — after confidentiality profile applied
└── splits/                               # 03 — resolved Split records, one per fold
```

**Subject identifiers are globally unique across vendors** — Cirrus holds TRAIN001–024,
Spectralis TRAIN025–048, Topcon TRAIN049–070, with no repetition. The directory name
alone therefore identifies a subject and no manifest is required to disambiguate it.
This closes open item 3 and matters to `splits.py`, which raises when one patient appears
under two vendors: had the organisers restarted numbering per vendor, every subject would
have tripped that assertion.

### 4.1 Local storage arrangement

`data/raw/retouch` is **not a directory in this repository**. It is a Windows directory
junction pointing at `D:\RETOUCH_DATA\retouch_traning_data_extracted`, where the
extracted archive actually lives. The indirection exists because the archive is large
and sits on a separate volume.

Every tool in this project treats it as an ordinary path and none needs to know it is a
link. Two properties make that safe: git does not follow it and `.gitignore` excludes
`data/` regardless (DMP-C1), and `data/raw/` is read-only once extracted, so nothing
here writes through the junction to the archive.

The junction is a local convenience and is **not reproducible from the repository**. A
fresh clone on another machine has an empty `data/raw/`, which is the correct outcome:
the data is not ours to distribute, and `scripts/00_fetch_data.py` documents the manual
steps to obtain it.

`data/raw/` is treated as read-only once extracted. Any transformation writes to a
new stage directory. Re-running a stage overwrites only its own output, so a
corrupted stage is recoverable without re-downloading.

All of `data/` and `artifacts/` are excluded from version control (DMP-C1), which was
re-confirmed on 2026-09-23: the only tracked paths under `data/` and `artifacts/` are
their two `.gitkeep` files.

---

## 5. De-identification

Applied profile: **DICOM PS3.15 Annex E, Basic Application Confidentiality
Profile**, with no retention options enabled.

The source data is public challenge data and contains no PHI. De-identification is
implemented and verified regardless, for two reasons: the DICOM objects this
project generates must be conformant to be meaningful, and the control is a
demonstrable capability independent of whether this particular dataset needs it.

Patient identifiers are replaced by salted-hash pseudonyms. The salt is read from
the environment variable named in `configs/data.yaml` and is never committed.
Pseudonyms are stable within a run so that patient-level splitting remains valid
after de-identification.

Verification: `io/deident.verify_deidentified()` returns any tag that should have
been removed and was not. Any non-empty return aborts the conversion run; failing
instances are never silently skipped.

---

## 6. Splitting policy and leakage prevention

**Policy:** splits are constructed at **subject/volume level**, never at B-scan
level. Every subject appears in exactly one of train, validation, or test.

**The specific hazard.** This project trains in 2D on individual B-scans. Adjacent
B-scans within one volume are near-duplicates — consecutive slices through the
same retina, microns apart. A random slice-level partition places near-identical
images on both sides of the split, producing a Dice score that reflects
memorisation rather than generalisation and that will not reproduce on any new
subject. This is the most likely way for this project to produce a confidently
wrong result, and it would not announce itself: the metrics would simply look good.

**Controls:**

| ID | Control | Verified by |
|---|---|---|
| DMP-C6 | `ocuval.data.splits` is the only module permitted to partition data | Code review |
| DMP-C7 | `assert_no_patient_overlap()` operates on the subject identifier, never the slice identifier | TC-004 |
| DMP-C8 | TC-004 gates CI and is never skipped, xfailed (after milestone 4), or weakened | `.github/workflows/ci.yml` |
| DMP-C9 | Overlap assertion runs at split construction **and** again at the start of training | TC-TBD |
| DMP-C10 | Splits are seeded, persisted, and committed; runs are reproducible from config alone | TC-TBD |

Fold design is leave-one-vendor-out: train on two vendors, evaluate on the third.
The validation set is carved from the training vendors, also at subject level. An
in-domain reference — held-out subjects from the *training* vendors — is evaluated
by the same model, and the gap between in-domain and held-out-vendor performance
is the project's headline result.

---

## 7. Access control and storage

**Access is single-recipient.** The signed agreement names one recipient, and that is
the fact DMP-C5 rests on: the constraint is not "few people" or "the project team" but
one named individual. There is no team, no collaborator, and no mechanism by which a
second person could obtain the data through this project. Any future collaborator would
need their own registration and their own signed agreement; the data cannot be passed
along with the repository.

Data resides on a single local workstation — see §4.1 for the on-disk arrangement — and,
for training, in a **private** Kaggle Dataset attached to the training notebook. The
Kaggle dataset must be private; a public one would breach DMP-C1 and the distribution
clause of the agreement simultaneously.

No cloud object storage, no shared drives, no third-party annotation services.

### 7.1 UID root — unregistered, and declared as such

The UID root configured in `configs/data.yaml` (`dicom.uid_root`) is **not registered**
to this project, to its author, or to any organisation. This is a recorded limitation,
not an oversight awaiting repair. It is deliberately not remedied by substituting a
different-looking root: a plausible but unregistered root is worse than a declared one,
because it invites the reader to assume someone checked.

Consequences, binding on the whole project:

- UIDs generated under this root are structurally valid but carry **no claim of global
  uniqueness**. They may collide with UIDs generated elsewhere.
- Objects produced by this project **must not be transmitted beyond the local Orthanc
  instance**. They must not be sent to a shared, institutional or third-party PACS, and
  must not be published as DICOM files.
- Any use outside those bounds requires a registered root first, recorded under change
  control.

Carried into `docs/11` §7 and §10. Resolves `docs/02` §6 item 3.

---

## 8. Retention and disposal

**Retention is conditional, not fixed.** The signed agreement permits the organisers to
withdraw authorisation **at any time** and to require deletion. The project therefore
holds the data at the organisers' discretion rather than for a term of its own choosing,
and no plan here may assume continued access.

Two consequences follow, and both are design constraints rather than paperwork:

- **The project must remain able to delete on request at any point**, including
  mid-training. That is why every derived stage is reproducible from the one before it
  (§4) and why nothing downstream embeds source image data.
- **No result may depend on data the project might have to destroy before the result is
  reproduced.** Metrics, resolved configurations and split records are committed;
  because subject identifiers are pseudonymised (§5) and no image data is committed, they
  survive deletion of the source without carrying any of it.

### 8.1 Deletion on request

On notice from the organisers withdrawing authorisation, and without waiting for any
milestone to complete:

1. Delete `data/raw/` — in this deployment that means the archive at the junction target
   in §4.1, not merely the link, which would leave the data in place while appearing to
   remove it.
2. Delete `data/dicom/` and `data/dicom_deident/`, which contain image data derived from
   the source and are equally covered.
3. Delete the private Kaggle Dataset and any training artefacts containing image data.
4. Delete trained checkpoints. They are derived from the data and are not published in
   any case (excluded by `.gitignore`).
5. Record the deletion, its date and the request that prompted it in
   `docs/13_change_control_log.md`.

Retained after such a deletion: metrics, resolved configurations, split records and the
document set. None contains image data or a source identifier. If the organisers require
those too, they go as well — the agreement governs, not this list.

### 8.2 Ordinary disposal

Absent a withdrawal, the data is retained for the active life of the project. On
completion or abandonment the same five steps run. Trained checkpoints derived from the
data are not published; only metrics, resolved configs and split records — none of which
contain image data — are committed.

Disposal is recorded in `docs/13_change_control_log.md`.

---

## 9. Contingency — alternative sources

Invoked if §2.4 triggers. Preserves the cross-vendor question at the cost of
harmonisation work.

| Dataset | Vendor | Content | Role |
|---|---|---|---|
| AROI | Zeiss Cirrus | AMD, fluid and layer annotations | Cirrus arm |
| Duke DME (Chiu et al.) | Heidelberg Spectralis | 110 B-scans, 10 DME subjects, two graders | Spectralis arm |
| UMN | — | 600 B-scans, exudative AMD | Supplementary |

Costs to accept if this path is taken: label conventions differ between sources
and must be mapped explicitly; disease mix differs (DME vs AMD vs RVO), which
confounds vendor shift with disease shift; and 2D B-scan datasets cannot support
volumetric metrics. The benefit is that harmonising independently collected
sources is a closer analogue of real multi-site deployment than a single curated
challenge dataset, and the mapping decisions are themselves documentable work.

---

## 10. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | ~~Complete grand-challenge registration; record acceptance date.~~ **Closed 2026-09-23.** Registration submitted 2026-09-20 17:35, accepted 2026-09-21. Signed Agreement of Data Confidentiality emailed to the organisers 2026-09-20. Training partition downloaded 2026-09-21; test partition deliberately not taken (§2.1). | — closed |
| 2 | ~~Confirm actual Topcon B-scan count per volume.~~ **Closed 2026-09-23: the figure was wrong.** No Topcon volume has ~122 B-scans; 20 have 128 and 2 have 64, across three distinct geometries. §3.1 corrected, along with §3.1.1 element types, §3.1.2 measured spacing and the whole of §3.2 prevalence. | — closed |
| 3 | ~~Confirm whether subject identifiers are recoverable from directory names alone.~~ **Closed 2026-09-23: yes, directory names suffice.** Subject numbering is continuous and unique across vendors (TRAIN001–024 Cirrus, TRAIN025–048 Spectralis, TRAIN049–070 Topcon), so no manifest is needed to disambiguate. See §4. | — closed |
| 4 | ~~Decide whether a registration acceptance date belongs in `docs/13`.~~ **Closed 2026-09-23: yes, and it is recorded there.** The dates establish when the agreement's obligations began, and §8 makes retention contingent on an authorisation that has a start date — an obligation whose commencement is undated cannot be audited. | — closed |
| 5 | ~~Populate the SRS and RC trace columns once `docs/02` and `docs/05` exist~~ **Resolved 2026-09-17:** both drafted; `docs/09` carries SRS and RC columns. DMP-C1..C5 are superseded by RC-019, C6 by RC-001, C7 and C9 by RC-002, C8 by RC-003, C10 by RC-004 (`docs/05` §4.1). | — closed |
