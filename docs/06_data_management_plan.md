<!--
Document: Data Management Plan
Status: DRAFT v0.2 — audited against the agreement 2026-10-08 (§2.5)
Owner: Anurag Yadav
Last reviewed: 2026-10-15
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

### 2.2.2 Illustrative images permitted, 2026-10-08

**Permission received.** On 8 October 2026 the organiser gave written permission, in these
words: *"adding a very small amount of illustrative images is fine."*

**The cap the author committed to.** In reply, the author confirmed that the project will
use **six B-scans at most**. The cap is the author's own undertaking, given to the organiser
in writing, and it binds this project: the organiser's wording is "a very small amount",
and six is the number the author named against it.

**Scope.** This permits a small number of illustrative single B-scans in the published
documents. It is not permission to publish volumes, masks as files, or any other image
derived from the data, and it changes nothing else in the agreement or in §2.2.1. Which
B-scans are shown is decided by a rule committed before any is rendered (`docs/07` §21),
by the numbers in the sealed records and never by viewing, so the selection cannot be
steered towards flattering examples. Carried into DMP-C2 below.

### 2.3 Controls adopted as a consequence

| ID | Control | Implementation |
|---|---|---|
| DMP-C1 | No redistribution of source data | `data/` is excluded in `.gitignore`; `check-added-large-files` pre-commit hook; no data in container images |
| DMP-C2 | No redistribution of derived imagery at volume scale | **At most six** illustrative single B-scans, under the organiser's written permission of 2026-10-08 (§2.2.2), each chosen by the pre-registered rule of `docs/07` §21 and shown with no case identifier, filename, date or other metadata. No volume, mask file or other image derived from the data is published. Until 2026-10-08 no B-scan appeared anywhere (amended 2026-10-13; previously "in the quantity conventional for a publication", a quantity no one had fixed) |
| DMP-C3 | No commercial use | Repository licensed MIT for **code only**; README states the dataset carries separate terms |
| DMP-C4 | Scope limited to fluid segmentation and detection | No secondary task, no pretraining for unrelated models, no derivative dataset published |
| DMP-C5 | Single registered user | Data accessed under one registration by a single named recipient; not shared with any third party (§7) |
| DMP-C12 | **No image, mask or pixel content enters a coding-assistant session** | Added 2026-10-13 (§7.3). Scripts that read pixel data print only shapes, types, value ranges and label sets. Images rendered from the data, including the illustrative B-scans of §2.2.2, are reviewed by the author outside any session and are never opened, read or described in one |
| DMP-C11 | **No reidentification, and no attempt at it** | No linkage to any external dataset, no demographic inference, no attempt to recover subject identity from image content or metadata. Technically, the salted-hash pseudonyms of SRS-013 are one-way and the salt is never committed, so this project's own outputs cannot be relinked to source identifiers by anyone reading the repository. Carried as RC-030 in `docs/05` |
| DMP-C13 | **Saved predicted label maps are local derived data, never redistributed** | Added 2026-10-29 (SRS-106). The final evaluation of `docs/07` §17.13 saves every predicted label map, one compressed file per volume, under `<repo>\artifacts\predictions_final`, with a checksum manifest in each evaluation record. They are mask volumes derived from the data and keyed on RETOUCH subject identifiers, so DMP-C1 and DMP-C2 apply to them as to the source: `artifacts/` is excluded by `.gitignore` (checked by TC-155), no code uploads them, and none is committed, pushed, published or attached anywhere. DMP-C12 applies too: a coding-assistant session reads only their checksums, shapes and the metrics measured from them, never their content. Their only purpose is re-measurement on this workstation: a measurement defect found later is corrected by re-measuring them against the references, without running the model. They are deleted with everything else (§8.1 step 7a) |

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

### 2.5 Compliance audit against the agreement — 2026-10-08

Requested by the author before the report page was published. Read-only: nothing was
changed while it ran. Each item was checked in the repository or on this workstation, not
recalled. Two issues and two judgement calls were found, all in this plan; the author
decided them on 2026-10-13 and the corrections are in this change.

| Item | Outcome | Evidence, and what was done |
|---|---|---|
| Git history and tags | Compliant | 189 commits across all refs. Nothing under `data/` or `artifacts/` was ever committed beyond the two `.gitkeep` files. No volume, DICOM file, archive or PDF was ever committed; the only images are the plots in `docs/figures`. GitHub holds `main` and `v1.0` only; a local backup branch was never pushed |
| Current repository and the report page | Compliant | The page's files are text only, with no subject identifier, UID root or identifying field |
| `docs/` text | Compliant | `TRAINnnn` appears only as the archive's naming scheme (§4) and as synthetic test fixtures; no subject is linked to any value, and no document shows a B-scan |
| Where data lives on this machine | **Issue, fixed** | Five locations were missing from §4.1. All locations are now in §4.2, on the two internal disks, none synchronised |
| OneDrive and other synchronisation | Compliant | Documents is redirected to OneDrive, but the repository is in the separate local folder; neither OneDrive root holds a project or dataset file; no other client present |
| RETOUCH images, masks or renderings in a Claude Code session | Compliant | None, across the full session record from 2026-09-16 (§7.3) |
| Dataset-derived text in sessions | **Judgement call, recorded** | Identifiers, metrics, headers and value ranges did pass through sessions. Recorded in §7.3, with the rule DMP-C12 |
| The signed agreement PDF | Compliant | Never in git history; kept in the author's Downloads folder only |
| Licence | Compliant | MIT, code only; the README and the report page say it does not extend to the data |
| §8 retention statement | **Issue, fixed** | It said split and evaluation records are committed and pseudonymised; both are local and keyed on RETOUCH identifiers. Corrected in §8, and §8.1 is now a path-by-path deletion list |
| Per-scan reference presence in the report page's downloads | **Judgement call, decided** | Presence derives from the reference annotations (DMP-C4). The author decided to keep it in the page's charts and drop it from the downloadable files; applied in the commit that publishes the page. **Found 2026-10-14:** dropping the column did not keep it out of the downloads, because the remaining columns determine it exactly (§2.5.1) |

### 2.5.1 Per-scan reference presence is public, unlinked — recorded 2026-10-14

**Where it is.** Whether each fluid type is present in each scan's reference is public in
two places: in `site_src/chart_scans.json`, which is committed and readable in the public
repository though not deployed, and embedded in the report page, which needs it for its
charts. That is 273 yes-or-no values: 70 held-out and 21 familiar-brand scans, times three
fluid types.

**It is also in the downloads, by derivation.** The downloadable `per_scan.csv` and
`per_scan.json` carry no presence column, as J2 decided, but they carry each scan's Dice,
HD95 and predicted voxel count, and those determine presence exactly. With nothing
predicted, Dice is 1 when the reference is empty and 0 when it is not; with something
predicted, HD95 is undefined only when the reference is empty. Checked on 2026-10-14: the
rule recovers presence for all 273 rows. So J2 removed a column, not the information, and
the downloads disclose nothing beyond what the chart input already does. Per-scan Dice and
HD95 are themselves computed against the reference: they are the results whose publication
the organiser confirmed in §2.2.1.

**Unlinked.** No row carries a RETOUCH subject identifier, a UID or a reference voxel count.
Rows are sorted by value, every published field is in the sort key, and every tie on the
key is between rows identical in every published field, so the row order carries nothing of
the records' subject order. One scan's three fluid rows cannot be joined to one another.
TC-131 checks all of this, and is shown able to fail.

**Why this is acceptable.**

- It is a result of the evaluation, not part of the dataset. Publishing results outside the
  challenge is permitted (§2.2.1).
- It is a yes-or-no per scan and fluid type. It carries no image, no mask, no location, no
  extent and no volume, so nothing of the annotations can be rebuilt from it, and it cannot
  stand in for the dataset (DMP-C4).
- The same information is already published in aggregate: the counts of scans containing
  each fluid type per brand (`docs/10` §5.2, the report page's dataset table).
- It cannot be joined to a subject, to a scan's other fluid types or to anything outside this
  project (DMP-C11).

If the organisers ask for it to be withdrawn, it goes with the chart input and the
per-scan downloads, and the agreement governs (§8.1).

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
Both the pooled voxel count and the mean of per-volume percentages were computed. They agree
exactly for Cirrus and Spectralis, whose volumes each share one geometry. For Topcon, whose
volumes have three geometries, they differ: IRF 0.2043% pooled against 0.1955% as a
per-volume mean, SRF 0.0963% against 0.1071%, PED 0.2983% against 0.3360%. The table below
gives the pooled figures. Neither statistic comes near the superseded figures, so the
discrepancy is not a difference of statistic. **Corrected 2026-10-14:** this sentence
previously said the two "agree" without qualification, which was exact only for Cirrus and
Spectralis (`docs/13`, 2026-10-14).

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

**The derived stages are junctioned the same way**, from 2026-09-23:

| Path in the repository | Target |
|---|---|
| `data/raw/retouch` | `D:\RETOUCH_DATA\retouch_traning_data_extracted` |
| `data/dicom` | `D:\RETOUCH_DATA\ocuval_dicom` |
| `data/dicom_deident` | `D:\RETOUCH_DATA\ocuval_dicom_deident` |

The first end-to-end run produced 3.1 GB of DICOM and 3.1 GB of de-identified copies
against 23 GB free on the system volume. That is enough to complete but not enough to
add a training cache on top, so the derived stages were moved before the next stage
rather than after it ran out. `data/splits` stays on the system volume: it is 28 KB of
JSON.

Two consequences follow from §8.1: a deletion must remove the junction **targets**, and
`data/splits` is on a different volume from everything else it describes.

**A junction is not a symlink, and some tools do not cross it.** Verified 2026-09-25 on
the populated tree, which holds 70 instances in each of `data/dicom` and
`data/dicom_deident`:

| Tool | Sees through the junction |
|---|---|
| Python `pathlib.glob` / `rglob`, `os.walk`, `Path.is_dir` | yes — 70 of 70 |
| Git Bash / MSYS `find` | **no — reports 0** |
| `du`, `ls` on the target path | yes |

Python is what the pipeline uses, so nothing in the codebase is affected. The hazard is
operational: a shell one-liner counting files under `data/` returns zero and looks like
an answer rather than a failure. **A zero from `find` under `data/` means the tool, not
the data** — count on the target path instead. `git status` and TC-100 are unaffected,
because git is told about these paths by `.gitignore` and never walks them.

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

### 4.2 Every location holding RETOUCH-derived data — inventory, 2026-10-08

**Added 2026-10-13 after the audit of 2026-10-08 (§2.5)**, which found that §4.1 named only
three of these locations. A deletion that followed §4.1 would have left the original
archives, three frame caches and the run records in place. Sizes were measured in the audit;
"not measured" means exactly that.

All of it is on this workstation's two internal disks: `C:` (NVMe) and `D:` (SATA). None is
under a synchronised folder: the Windows Documents folder is redirected to OneDrive, but the
repository sits in the separate local folder `C:\Users\rites_ljry4pu\Documents`, which is
not a link to it, and the audit found no project or dataset file in either OneDrive root.
`<repo>` is `C:\Users\rites_ljry4pu\Documents\Projects\ocuval`.

| Location | What it holds | Size |
|---|---|---|
| `D:\RETOUCH_DATA\Retouch_zipped_data` | The archives as downloaded | 3.7 GB |
| `D:\RETOUCH_DATA\retouch_traning_data_extracted` (`data\raw\retouch`) | The extracted training partition: images and reference masks | 5.9 GB |
| `D:\RETOUCH_DATA\ocuval_dicom` (`data\dicom`) | Converted DICOM images | 6.1 GB |
| `D:\RETOUCH_DATA\ocuval_dicom_deident` (`data\dicom_deident`) | De-identified DICOM images | 6.1 GB |
| ~~`D:\RETOUCH_DATA\ocuval_cache`~~ | An earlier training frame cache (Cirrus fold): image and label arrays. **Deleted 2026-10-14** | 4.4 GB, now none |
| ~~`D:\ocuval_cache`~~ | The Topcon fold's frame cache, image and label arrays, placed there via `OCUVAL_CACHE_DIR` on 2026-10-04. **Deleted 2026-10-14** | 5.2 GB, now none |
| ~~`<repo>\artifacts\cache`~~ | The Cirrus and Spectralis folds' frame caches: image and label arrays, each frame carrying its subject identifier. **Deleted 2026-10-14** | 12 GB, now none |
| `<repo>\artifacts\runs` | Trained checkpoints, and evaluation records whose per-scan rows are keyed on RETOUCH subject identifiers | not measured |
| `<repo>\artifacts\predictions_final` | **From the final run of `docs/07` §17.13 (2026-10-29 onwards):** every predicted label map in native geometry, one compressed file per volume named by its RETOUCH subject identifier, with its spacing and detection scores (DMP-C13) | not yet written; at most 8.0 GB uncompressed (derived: 119 maps of at most 128 × 1024 × 512 bytes each), compressed size not measured |
| `<repo>\artifacts` (everything else) | Run logs, the evaluation chain's logs, benchmarks, telemetry, the sealed-access log | not measured |
| `<repo>\data\splits` | Split records, keyed on RETOUCH subject identifiers | 28 KB (measured 2026-09-23, §4.1) |
| `C:\Users\rites_ljry4pu\.claude\projects\c--Users-rites-ljry4pu-Documents-Projects-ocuval`, and the session's temporary folder under `%LOCALAPPDATA%\Temp\claude` | Claude Code session records and scratch files: dataset-derived text only (§7.3), no image data | not measured |

The signed agreement itself is kept outside the repository, in the author's Downloads
folder; it is not data and is not in this inventory.

**Frame caches deleted, 2026-10-14, by the author's decision.** All three training frame
caches were removed: `<repo>\artifacts\cache` (Cirrus and Spectralis folds, 12 GB on `C:`),
`D:\RETOUCH_DATA\ocuval_cache` (an earlier Cirrus cache, 4.4 GB) and `D:\ocuval_cache`
(Topcon fold, 5.2 GB). Each held only per-fold `train`, `val` and `test` frame folders,
checked before deletion. **Why they could go:** training is finished, and the code was
checked before deleting. Only training reads a frame cache: `datamodule.py` builds and
serves it through `resolve_cache_dir` (`runs.py:262`), `04_train.py` fills it, and
`benchmark_device.py` and `evaluate_stage1.py` read it. Evaluation (`05_evaluate.py`) and the
illustration script (`09_illustrative_bscans.py`) read the original volumes with
`read_volume` and import neither; no test reads a real cache. **Why it is good, not only
safe:** three fewer copies of RETOUCH-derived image data. A future training run rebuilds a
cache wherever `OCUVAL_CACHE_DIR` or `data.cache_dir` points, and that location must then be
added back to this inventory.

---

## 5. De-identification

Applied profile: **DICOM PS3.15 Annex E, Basic Application Confidentiality
Profile**, with no retention options enabled.

The source data is public challenge data and contains no PHI. De-identification is
implemented and verified regardless, for two reasons: the DICOM objects this
project generates must be conformant to be meaningful, and the control is a
demonstrable capability independent of whether this particular dataset needs it.

Patient identifiers are replaced by salted-hash pseudonyms. The salt is read from
the environment variable named in `configs/data.yaml` (`OCUVAL_DEID_SALT`) and is never
committed.

### 5.1 The salt is persistent, and lives outside the repository

A **persistent salt exists** as of 2026-09-23. It is 32 random bytes, base64-encoded,
generated once and stored at:

```
%USERPROFILE%\.ocuval\deid_salt          (outside this repository, outside data/)
```

Its **value is never committed, never logged, and never written to any run output**. It
is not under `data/`, so it survives the deletion in §8.1 — and must, because deleting
it would make every pseudonym already issued unreproducible while achieving nothing for
confidentiality: the salt protects the *mapping*, and the source identifiers are
destroyed by that deletion anyway.

**Why persistence is required rather than convenient.** An ephemeral salt satisfies the
letter of "stable within a run" and defeats the purpose. Two runs would issue different
pseudonyms for the same subject, so a result recorded in one run could not be matched to
the volume it came from in another — provenance, which URS-010 exists for, would hold
only inside a single process. SRS-014 previously required within-run stability only;
that was a requirements defect and was corrected on 2026-09-25 to require the pseudonym
to be a deterministic function of the identifier and salt alone, in every run and on
every machine.

**What losing the salt costs.** Nothing about confidentiality — the hash is one-way in
either case. It costs the ability to reproduce existing pseudonyms, so previously
written objects could no longer be matched to a re-run. Treat it as run configuration
worth backing up, not as a secret whose disclosure is catastrophic.

Pseudonyms remain stable within a run for the original reason as well: patient-level
splitting must stay valid after de-identification.

### 5.2 First run under the persistent salt — 2026-09-25

The whole pipeline was re-run under the persistent salt on 2026-09-25: 70 volumes
converted, 70 instances de-identified and verified, three folds rewritten. Five checks
were made against the written objects, not against the run's own bookkeeping:

| Check | Result |
|---|---|
| Pseudonym equals `sha256(salt:patient_id)` recomputed independently | 70 / 70 |
| Same, re-read from the de-identified instances on disk | 70 / 70 |
| Pseudonyms distinct (a collision would break patient-level splitting) | 70 / 70 |
| Salt value present anywhere in a written object | 0 |
| Changed from the previous run's pseudonyms | 70 / 70 |

The last row is the point. **Every pseudonym issued before 2026-09-25 is unreproducible**,
because the run that issued them read an ephemeral salt that no longer exists. Nothing is
lost — those objects were superseded by this run and no result was recorded against them —
but it is exactly the failure the corrected SRS-014 forbids, and it is recorded here rather
than left as an absence. From this run forward a pseudonym can be recomputed from the
patient identifier and the stored salt by anyone holding both.

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

### 7.1 Training runs on the local workstation — decision, 2026-09-25

**Decision.** All training, validation and evaluation run on the author's own machine.
The dataset is never uploaded anywhere. The Kaggle path remains documented below as an
alternative that was prepared and **not used**.

**Reasoning.** The signed Agreement of Data Confidentiality restricts disclosure to the
registered team (§2.1). A Kaggle dataset marked private is still **stored on a third
party's servers**, which is a disclosure to that third party regardless of who can view
it: the data leaves the registered team's custody, is processed under terms the team
does not set, and its deletion cannot be verified from outside. Marking it private
controls *who can read it*, not *where it is*. The Agreement speaks to the second.

This is **DMP-C1** applied rather than a new commitment: the constraint always said the
data stays within the registered team's control, and the local-training decision is what
that requires once training hardware is in question.

**Cost accepted.** A GTX 1050 with 4 GB is slower than a Kaggle P100 and has no weekly
quota to work against. Measured 2026-09-25 at **25.6 images/second** through the real
cached loader, the three folds at 150 epochs total **≈17 hours** — roughly two overnight
sessions. That is acceptable, and the checkpoint-resume path (SRS-075) exists so the
work can be split across nights. Paying two nights to keep the archive on one machine is
a straightforward trade.

**What this does not change.** The de-identification pipeline still runs and is still
verified (§5). Not needing a control is not a reason to remove it; demonstrating it is
part of the point.

**Status of the Kaggle path.** `docs/06` and the training entry point remain
Kaggle-compatible and the notebook is **not used**. It is kept because the alternative
should be visible and because a reader assessing this decision should be able to see the
option that was declined, not only the one taken.


**Access is single-recipient.** The signed agreement names one recipient, and that is
the fact DMP-C5 rests on: the constraint is not "few people" or "the project team" but
one named individual. There is no team, no collaborator, and no mechanism by which a
second person could obtain the data through this project. Any future collaborator would
need their own registration and their own signed agreement; the data cannot be passed
along with the repository.

Data resides on a single local workstation and nowhere else — see §4.1 for the on-disk
arrangement and §7.1 for the decision.

~~and, for training, in a **private** Kaggle Dataset attached to the training
notebook.~~ **Superseded 2026-09-25.** This plan previously anticipated a private Kaggle
Dataset for training. It is not used, and the reasoning is in §7.1: private controls who
may read the data, not where it is held, and the agreement speaks to custody. The
sentence is struck rather than deleted so that the earlier position, and the fact that it
changed, remain visible.

No cloud object storage, no shared drives, no third-party annotation services.

### 7.2 UID root — unregistered, and declared as such

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

#### 7.2.1 Amendment, 2026-10-15: an ephemeral Orthanc in CI

**What changes.** One further destination is permitted for objects this project produces: an
Orthanc container started for a single CI job, under all of the following conditions. TC-135
checks each of them against the workflow file (SRS-094).

- It is started from the image digest pinned in SOUP-014 and configured from
  `docker/orthanc/orthanc.json`, the same image and configuration as the local instance.
- Its HTTP port is published on the runner's loopback address only, and no other port is
  published.
- It receives only synthetic objects created by the tests in that job. No RETOUCH data, and no
  object derived from it, can reach the job: the CI checkout holds nothing under `data/` but
  `.gitkeep`, nothing in CI downloads the dataset, and the job has no secrets.
- No artifact is uploaded from the job.
- It is removed when the job ends, pass or fail. Independently, a GitHub-hosted runner is a fresh
  virtual machine for each job and is discarded afterwards.

Every other use beyond the local Orthanc instance still requires a registered root first.

**Why this is an amendment, not an interpretation.** The rule above says objects must not be
transmitted beyond "the local Orthanc instance", and that means the one on this workstation. A
container on a GitHub-hosted runner is the same software at the same digest, but it runs on
third-party hardware. The letter of the rule does not cover it, so the rule is changed here,
with its reasoning, rather than read as already permitting it.

**Why the purpose of the rule is kept.** The rule exists because UIDs under an unregistered root
carry no claim of global uniqueness. They could collide with, or be mistaken for, other parties'
objects in an archive that holds anything else, or keep circulating if published. An Orthanc that
exists for one job, holds only that job's synthetic objects, is reachable only from inside the
runner and is destroyed with the job has nothing to collide with and nothing that outlives it.

**What it adds to existing exposure.** The CI suite already writes synthetic DICOM files on the
same runners, in the DICOM writer, SEG and SR tests. The round-trip adds sending them over
loopback to a process on the same machine. Nothing is published as a DICOM file.

**Not a custody question.** §7.1 declined Kaggle because the RETOUCH data would have been stored
on a third party's servers. That argument concerns who holds the dataset. It does not arise here,
because no RETOUCH data is involved.

**Loopback, rather than an assumption about the runner's network.** Whether a port published on
all interfaces of a GitHub-hosted runner is reachable from outside it has not been verified here.
Binding to 127.0.0.1 removes the question instead of resting on an answer to it.

**The root itself.** The configured root, `1.2.826.0.1.3680043.10.9999`, sits under the arc
`1.2.826.0.1.3680043`, whose holder issues sub-roots to others: pydicom's own prefix,
`1.2.826.0.1.3680043.8.498.`, was obtained from that service (pydicom 2.4.4, `uid.py:238-240`).
**Whether `.10.9999` has been issued to anyone is not known.** Nothing above depends on it,
since the root is already treated as unregistered, but it is the concrete reason a collision
cannot be ruled out.

### 7.3 What has passed through coding-assistant sessions — recorded 2026-10-13

This project is built with Claude Code (Anthropic) as a coding assistant. What a session
reads or prints is sent to Anthropic's service to run the session, and is kept on this
workstation in the session record. This plan said nothing about that until the audit of
2026-10-08 (§2.5) asked. Recorded here as a fact, not characterised.

**What has entered sessions, all as text:**

- RETOUCH subject identifiers (`TRAINnnn`), from split lists and from evaluation record rows;
- per-scan metrics: Dice, HD95, predicted voxel counts and reference presence;
- file headers: MetaImage header text, and DICOM headers read without pixel data;
- array shapes, data types, intensity value ranges, and the set of label values present in a
  volume.

**What has not:** no image, no reference mask, no pixel array and no rendering of the data.
Evidence, from the audit of the full session record from the project's first day,
2026-09-16: every one of the 33 images that entered a session is a plot from `docs/figures`
or a screenshot of the report page; no session read a file under a data path; the 18
commands that loaded volumes or cached frames printed only summaries, with no run of 40 or
more consecutive numbers in any output; no subagent was used.

**The rule from here (DMP-C12): no image, mask or pixel content enters a session.**

**What cannot be verified from here.** The copy Anthropic's service received is outside this
workstation, and its retention is governed by Anthropic's terms rather than by anything this
project can inspect or delete. The local session record is in the §4.2 inventory and the
§8.1 deletion list.

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
  reproduced.** What is committed is the document set, with its aggregate results, the
  result figures in `docs/figures`, and the report page's data (`site/data`) once
  published: per-scan scores with no identifier and no image data (DMP-C11). These survive
  deletion of the source without carrying any of it. **The evaluation records and the split
  records are not committed.** They stay on this workstation (`<repo>\artifacts\runs`,
  `<repo>\data\splits`, §4.2), and they are keyed on the RETOUCH subject identifiers, not on
  the pseudonyms of §5.

**Corrected 2026-10-13.** This paragraph previously read: "Metrics, resolved configurations
and split records are committed; because subject identifiers are pseudonymised (§5) and no
image data is committed, they survive deletion of the source without carrying any of it."
Two parts of that were false, as the audit of 2026-10-08 found (§2.5): neither the
evaluation records nor the split records are committed (only the two `.gitkeep` files are
tracked under `data/` and `artifacts/`), and both carry the RETOUCH identifiers. The
pseudonyms of §5 are applied to the de-identified DICOM instances, not to these records.

### 8.1 Deletion on request

On notice from the organisers withdrawing authorisation, and without waiting for any
milestone to complete, delete every copy, **path by path**, from the §4.2 inventory.
Deleting a junction in `data\` removes only the link and leaves the data in place while
appearing to remove it, so the targets are named here, not the links. `<repo>` is
`C:\Users\rites_ljry4pu\Documents\Projects\ocuval`.

1. `D:\RETOUCH_DATA\Retouch_zipped_data`: the archives as downloaded.
2. `D:\RETOUCH_DATA\retouch_traning_data_extracted`: the extracted partition, target of
   `data\raw\retouch`.
3. `D:\RETOUCH_DATA\ocuval_dicom` and `D:\RETOUCH_DATA\ocuval_dicom_deident`: the DICOM
   stages, targets of `data\dicom` and `data\dicom_deident`.
4. `D:\RETOUCH_DATA\ocuval_cache`: an earlier frame cache. **Deleted 2026-10-14** (§4.2).
5. `D:\ocuval_cache`: the Topcon fold's frame cache, outside `D:\RETOUCH_DATA`. **Deleted
   2026-10-14** (§4.2).
6. `<repo>\artifacts\cache`: the Cirrus and Spectralis folds' frame caches. **Deleted
   2026-10-14** (§4.2). Steps 4 to 6 stay in this list because a future training run
   recreates a cache: delete wherever `OCUVAL_CACHE_DIR` or `data.cache_dir` then points.
7. `<repo>\artifacts\runs`: trained checkpoints and evaluation records.
7a. `<repo>\artifacts\predictions_final`: the saved predicted label maps (DMP-C13). Step 8
    covers it too; it is named because it holds mask volumes, not only text.
8. Everything else under `<repo>\artifacts` except `.gitkeep`: logs, the chain's logs,
   benchmarks, telemetry and the sealed-access log.
9. `<repo>\data\splits`, then the three junctions in `<repo>\data`.
10. The Claude Code session records and scratch files for this project (§4.2, §7.3). They
    hold dataset-derived text, not image data. The copy Anthropic's service received cannot
    be deleted from this workstation (§7.3).
11. **The illustrative B-scans, if any have been published (§2.2.2):** their files in
    `docs/figures` and every place they are shown, in `docs/10`, the README and the report
    page. A committed image also stays in git history. Removing it from history means
    rewriting history, which this project otherwise refuses (TC-108); on a request, the
    agreement governs, and the rewrite and every cited SHA it breaks are recorded.
12. Confirm: no file named `oct.mhd` or `reference.mhd` and no path in this list remains,
    on `C:` or `D:`.
13. Record the deletion, its date and the request that prompted it in
    `docs/13_change_control_log.md`.

The private Kaggle Dataset this list once named has no step: the data was never uploaded
anywhere (§7.1), so no such copy exists.

Retained after such a deletion: the committed document set, the result figures and the
report page's data. None contains image data or a source identifier, apart from the
illustrative B-scans, which step 11 removes. If the organisers require the rest too, it goes
as well: the agreement governs, not this list.

### 8.2 Ordinary disposal

Absent a withdrawal, the data is retained for the active life of the project. On
completion or abandonment the same steps run, except that step 11 applies only if the
organisers ask for it. Trained checkpoints derived from the data are not published.

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
