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

The RETOUCH challenge rules state that the OCT data and associated reference
standard:

- may not be given or distributed to persons outside the registered team;
- are strictly limited to research purposes, with commercial use prohibited;
- may be used only for evaluating fluid segmentation methods and participating in
  the challenge, and **may not be used to train or develop other algorithms**,
  including algorithms used in commercial products.

Access requires registration on grand-challenge.org and acceptance of these terms.
As of 2026-09-16 the challenge remains open for submissions and registration is
available.

### 2.2 Analysis

The third clause is the restrictive one and warrants an explicit position rather
than silent assumption.

**Interpretation adopted by this project:** the clause is read as prohibiting
repurposing of the data toward unrelated or commercial models, not as prohibiting
the training of a fluid segmentation model. Training a fluid segmentation model
and reporting its performance is the activity the challenge exists to solicit, is
what the published RETOUCH benchmark paper describes participants doing, and is
what the substantial downstream literature using this dataset does.

**Residual uncertainty:** whether publication of a method and its results in a
public code repository, rather than as a challenge submission, falls within
"participation in the challenge." This project's position is that it does — the
repository publishes a method description and results and redistributes no data —
but the position is recorded here as a judgment rather than a certainty.

### 2.3 Controls adopted as a consequence

| ID | Control | Implementation |
|---|---|---|
| DMP-C1 | No redistribution of source data | `data/` is excluded in `.gitignore`; `check-added-large-files` pre-commit hook; no data in container images |
| DMP-C2 | No redistribution of derived imagery at volume scale | Only illustrative single B-scans appear in figures, in the quantity conventional for a publication |
| DMP-C3 | No commercial use | Repository licensed MIT for **code only**; README states the dataset carries separate terms |
| DMP-C4 | Scope limited to fluid segmentation and detection | No secondary task, no pretraining for unrelated models, no derivative dataset published |
| DMP-C5 | Single registered user | Data accessed under one registration; not shared with any third party |

### 2.4 Decision gate

If at any point the interpretation in §2.2 is judged untenable, the project
migrates to the alternative sources in §9 rather than proceeding. This gate is
placed here, before milestone 3, specifically so that reversal costs days rather
than weeks.

---

## 3. Dataset characteristics

### 3.1 Per-vendor composition

| Vendor | Subjects | B-scan size (px) | B-scans/volume | Total slices |
|---|---|---|---|---|
| Cirrus | 24 | 512 × 1024 | 128 | 3,072 |
| Spectralis | 24 | 512 × 496 | 49 | 1,176 |
| Topcon | 22 | 512 × 885 | ~122 | 2,688 |
| **Total** | **70** | — | — | **6,936** |

Vendors differ in both axial resolution and slice count. Spectralis volumes carry
fewer than half the B-scans of the other two. This geometric heterogeneity is not
noise to be normalised away — it is a component of the domain shift the project
exists to measure. Preprocessing must not resample all vendors into a single
common geometry, as doing so would remove part of the effect under study.

### 3.2 Class prevalence (voxel-wise, % of all voxels)

| Vendor | Background | IRF | SRF | PED |
|---|---|---|---|---|
| Cirrus | 98.95 | 0.04 | 0.18 | 0.83 |
| Spectralis | 98.74 | 0.15 | 0.39 | 0.72 |
| Topcon | 99.45 | 0.03 | 0.06 | 0.46 |

**Foreground occupies between 0.55% and 1.26% of voxels.** This is the governing
constraint on evaluation design and drives three decisions recorded elsewhere:

1. **Accuracy is never reported.** A trivial all-background predictor scores above
   98.7% on every vendor. `src/ocuval/eval/metrics.py` deliberately provides no
   accuracy function and none is to be added.
2. **Dice excludes background** (`loss.include_background: false` in
   `configs/train_seg.yaml`), otherwise the background term dominates the gradient.
3. **Per-class reporting is mandatory.** IRF on Topcon is 0.03% of voxels — an
   aggregate foreground Dice would let near-total failure on the rarest class hide
   behind performance on PED.

Note also that prevalence varies by a factor of five across vendors for the same
class (IRF: 0.15% Spectralis vs 0.03% Topcon). Cross-vendor performance
differences will therefore conflate **appearance shift** with **prevalence shift**.
`docs/10` must state this; the two are not separable with this dataset.

### 3.3 Image quality

Cirrus volumes are reported in the literature as lower in image quality than the
other two vendors. If held-out-Cirrus performance is the worst of the three folds,
quality is a candidate explanation alongside appearance shift, and the report
should say so rather than attributing the gap to domain shift alone.

---

## 4. On-disk layout and lifecycle

Stages are one-directional; each is produced by a numbered script and is
reproducible from the one before it.

```
data/
├── raw/retouch/              # 00 — manual download, immutable after extraction
│   ├── cirrus/TRAIN0xx/{oct.mhd,oct.raw,reference.mhd,reference.raw}
│   ├── spectralis/TRAIN0xx/...
│   └── topcon/TRAIN0xx/...
├── dicom/                    # 01 — Ophthalmic Tomography Image objects
├── dicom_deident/            # 02 — after confidentiality profile applied
└── splits/                   # 03 — resolved Split records, one per fold
```

`data/raw/` is treated as read-only once extracted. Any transformation writes to a
new stage directory. Re-running a stage overwrites only its own output, so a
corrupted stage is recoverable without re-downloading.

All of `data/` and `artifacts/` are excluded from version control (DMP-C1).

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

Data resides on a single local workstation and, for training, in a **private**
Kaggle Dataset attached to the training notebook. The Kaggle dataset must be
private; a public one would breach DMP-C1.

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

Retained for the active life of the project. On completion or abandonment,
`data/raw/`, `data/dicom*/` and the private Kaggle dataset are deleted. Trained
checkpoints derived from the data are not published (they are excluded by
`.gitignore`); only metrics, resolved configs, and split records — none of which
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
| 1 | Complete grand-challenge registration; record acceptance date | Milestone 3 |
| 2 | Confirm actual Topcon B-scan count per volume against downloaded data; table in §3.1 uses a literature-derived figure | `docs/10` |
| 3 | Confirm whether subject identifiers are recoverable from directory names alone, or require a manifest | `splits.py` |
| 4 | Decide and record whether a registration acceptance date belongs in `docs/13` | — |
| 5 | ~~Populate the SRS and RC trace columns once `docs/02` and `docs/05` exist~~ **Resolved 2026-09-17:** both drafted; `docs/09` carries SRS and RC columns. DMP-C1..C5 are superseded by RC-019, C6 by RC-001, C7 and C9 by RC-002, C8 by RC-003, C10 by RC-004 (`docs/05` §4.1). | — closed |
