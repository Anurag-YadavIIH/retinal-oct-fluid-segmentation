<!--
Document: Model Card
Status: DRAFT v0.1 — drafted 2026-10-15 from docs/10 v0.4, docs/08, docs/06, docs/01 and docs/03; per-vendor fluid prevalence added 2026-10-15 (docs/06 §3.2)
Owner: Anurag Yadav
Last reviewed: 2026-10-15
Change history: docs/13_change_control_log.md
-->

# Model Card

> **Not for clinical use.** This is a research and portfolio project built on public challenge
> data. It has never been used on patients, has not been validated for patient care, and makes
> no clinical claim of any kind. It carries no regulatory clearance (`docs/01` §5).

> **How to read this card.** It adds no result. Every figure is copied from `docs/10` or
> `docs/08`, or for measured dataset figures from `docs/06` §3.2, and cited by section; where they differ in presentation, `docs/10` governs. Each
> figure keeps its standing from `docs/10`: **primary, pre-registered** (`docs/07` §17),
> **secondary, pre-registered** (`docs/07` §19) or **post-hoc**, declared after the results it
> touches were visible.

## Model details

| Item | Value | Source |
|---|---|---|
| What it does | Voxel-wise segmentation of three retinal fluid types in a macular SD-OCT volume: intraretinal fluid (IRF), subretinal fluid (SRF) and pigment epithelial detachment (PED), plus background. Label indices are fixed in `configs/data.yaml` | `docs/01` URS-001 |
| Models | **Three**, one per leave-one-vendor-out fold: `cirrus_holdout` (trained on spectralis + topcon), `spectralis_holdout` (cirrus + topcon), `topcon_holdout` (cirrus + spectralis). There is no single pooled model | `docs/10` §2 |
| Architecture | 2-D UNet with instance norm and dropout 0.2, applied to individual B-scans; a 2.64 M-parameter network | `docs/10` §2; `docs/08` §5.4 |
| Input preprocessing | Per-volume intensity window: each volume's 1st and 99th percentiles mapped to 0 and 1, values outside clipped. Frames resampled axially to 0.004 mm/pixel, so no vendor is upsampled | `docs/10` §8.1, §8.2 |
| Inference | Mean of 20 MC-dropout passes, seeded per volume, with deterministic kernels; predictions inverted to native geometry before any measurement | `docs/10` §2 |
| Training | Loss `dice_ce_deterministic` (SRS-084), AMP on, micro-batch 8, seed 20260916; early stopping with patience 25 on in-domain validation Dice | `docs/08` §5c.1, §5c.2 |
| Selected checkpoints | `best.pt` per fold, chosen on in-domain `val` only: cirrus epoch 33, spectralis epoch 29, topcon epoch 29. Every fold ended by early stopping | `docs/10` §2, Figure 1 |
| Training source | cirrus `a6d6edb`; spectralis `5f66359` (session 1) and `7be924f` (session 2), with no training-path file differing between them; topcon `d35e8e4`. All `dirty: false` | `docs/08` §5c.1, §5e.1, §5e.2, §5f.1 |
| Checkpoint identity | SHA-256 of each `best.pt` and `last.pt` is recorded | `docs/08` §5c.5, §5e.4, §5f.4 |
| Availability | **The trained checkpoints are not published.** They are derived from data held under the RETOUCH agreement | `docs/06` §8.2 |
| Package version | `0.1.0` | `docs/08` §1 |
| Safety class (as documented) | IEC 62304 software safety class **B**, every software item inheriting it. The classification is a documentation exercise for a portfolio project, not a regulatory determination | `docs/03` §5, §7 |
| Developer | Anurag Yadav. Built with Claude Code (Anthropic) as a coding assistant | `README.md` |
| Licence | Code: MIT. The licence does not extend to the data, which carries its own terms | `docs/06` DMP-C3 |

**What is not wired up.** The model's output is not yet written as DICOM by any pipeline step,
and the inference service has no `POST /infer`. The DICOM Segmentation and Structured Report
builders exist and are tested, but the round-trip through a PACS (TC-080..TC-082) has never been
executed. So the end-to-end path that `docs/01` §1 describes, from a volume to a reviewed DICOM
result, does not exist yet.

## Intended use

As stated in `docs/01` §1, and limited by `docs/01` §5:

- **What:** a **candidate** voxel-wise segmentation of IRF, SRF and PED from a single macular
  SD-OCT volume from a Zeiss Cirrus, Heidelberg Spectralis or Topcon scanner, with a per-class
  fluid volume in mm³ and a scan-level confidence estimate derived from it.
- **Who:** a trained reading-centre grader or image analyst, supervised by a retinal specialist
  (`docs/01` §3).
- **How:** as a **pre-read** in a retrospective research or clinical-trial reading workflow.
  The software proposes; the grader reviews, corrects and records. No output is an assessment
  until a grader has acted on it (URS-003).
- **Where:** an offline research workstation or reading-centre server, on retrospectively
  acquired, de-identified volumes, with results going to a local PACS only (`docs/01` §4;
  `docs/06` §7.2).

**What it is for in this repository:** measuring cross-vendor generalisation under a
pre-registered protocol (`docs/10` §1). The models were trained to answer that question, not to
be deployed.

## Out-of-scope use

**Any use in patient care, in any setting.** Beyond that, from `docs/01` §5 and §6.2:

- diagnosis, triage or prioritisation, treatment monitoring or any comparison between visits,
  and any autonomous action;
- diabetic macular edema, and any disease other than neovascular AMD and RVO;
- OCT angiography, en-face or projected views, and any modality other than SD-OCT B-scan
  volumes;
- non-macular OCT, non-standard scan patterns, and acquisitions that do not match the macular
  cube protocols of the three named platforms;
- scanner platforms other than Cirrus, Spectralis and Topcon, including later hardware or
  software revisions of those three not represented in RETOUCH;
- paediatric acquisitions;
- any claim about reducing grading time, workload or inter-grader variability: none is made or
  tested (`docs/01` §5).

**Two further limits that follow from this project's records:**

- **Not as a vendor-robust model.** No cross-vendor difference was established, and the design
  could not detect one smaller than about 0.14 Dice (`docs/10` Summary, §5.4). That is not
  evidence of robustness.
- **Not outside a local PACS.** DICOM objects carry UIDs under an unregistered root and must
  not leave the local Orthanc instance or be published as DICOM files (`docs/06` §7.2).

## Training data

| Item | Value | Source |
|---|---|---|
| Dataset | RETOUCH training partition (MICCAI 2017), the only partition with public annotations. The official test partition was not taken | `docs/10` §2, §8.5; `docs/06` §1.3, §2.1 |
| Volumes | 70, one per patient: cirrus 24, spectralis 24, topcon 22 | `docs/10` §2 |
| Disease | Macular edema secondary to AMD and to RVO | `docs/06` §1.1 |
| Reference standard | Manual, voxel-wise, from two clinical centres; not double-graded, with no published per-case inter-rater agreement | `docs/06` §1.2; `docs/10` §8.4 |
| Per model | Patients of the two training vendors, split at patient level into `train`, `val` (7 patients) and an in-domain reference (7 patients); the held-out vendor is not seen in training | `docs/10` §2; `docs/06` §6 |
| Training frames | cirrus fold 2610 train and 580 validation frames; spectralis fold 4032 train frames; topcon fold 3088 train and 659 validation frames | `docs/08` §5.1, §5e.4, §5f.1 |
| Class imbalance | Fluid occupies a very small fraction of voxels in every vendor (table below), and most volumes lack at least one fluid type | `docs/06` §3.2, §3.2.1 |

**Fluid prevalence per vendor**, voxel-wise, % of all voxels, pooled over all 70 reference
volumes. Measured 2026-09-23 and copied unchanged from `docs/06` §3.2:

| Vendor | Background | IRF | SRF | PED |
|---|---|---|---|---|
| Cirrus | 98.8437 | 0.4019 | 0.3515 | 0.4029 |
| Spectralis | 98.5173 | 0.5821 | 0.5777 | 0.3229 |
| Topcon | 99.4011 | 0.2043 | 0.0963 | 0.2983 |

These are pooled voxel counts. For Cirrus and Spectralis they equal the mean of per-volume
percentages. For Topcon, whose volumes have three geometries, the per-volume mean differs: IRF
0.1955%, SRF 0.1071%, PED 0.3360% (`docs/06` §3.2). A prevalence table that circulates in the
literature for this dataset does not match these measured figures and is not used here
(`docs/06` §3.2; `docs/13`, 2026-10-14 and 2026-10-15).

**Terms of use.** The data is used under a signed Agreement of Data Confidentiality with the
RETOUCH organisers (`docs/06` §2.1):

- **No redistribution, in any form** (DMP-C1). No volume, mask or dataset file is in this
  repository, and the trained checkpoints are not published (`docs/06` §8.2).
- **No reidentification, and no attempt at it** (DMP-C11).
- **Single named recipient** (DMP-C5). The data stayed on the author's workstation and was
  never uploaded anywhere, including Kaggle (`docs/06` §7.1).
- **Publishing results** outside the challenge was confirmed as permitted by an organiser
  (`docs/06` §2.2.1). A very small number of **illustrative images** was permitted in writing;
  the author capped this at six B-scans (`docs/06` §2.2.2, DMP-C2).
- The organisers may withdraw authorisation at any time, and deletion then follows `docs/06`
  §8.1.

## Evaluation data

| Item | Value | Source |
|---|---|---|
| Held-out arm (`test`) | All patients of the held-out vendor: cirrus n=24, spectralis n=24, topcon n=22 | `docs/10` §3 |
| In-domain reference arm | 7 unseen patients per fold from the two training vendors; 21 volumes from **13** distinct patients across the three folds | `docs/10` §2, §5.1 |
| Sealing | `test` and `in_domain_ref` were each evaluated once under the seeded procedure. Cirrus also has an earlier unseeded draw, kept on the record and labelled | `docs/10` §2, §3.1 |
| Reproducibility gate | Two seeded evaluations of the open `val` bucket were identical on every one of 466 compared values before any unlock | `docs/10` §2; `docs/08` §5g.1 |
| Geometry | Every metric computed in native geometry, so no reported number is at the resampled spacing | `docs/10` §8.2 |

## Metrics

- **Segmentation (primary):** Dice and HD95 per class. HD95 is the maximum of the two directed
  95th-percentile distances, in mm (`docs/10` §2).
- **Detection (primary, derived from the segmentation):** a class is present when predicted
  voxels exceed 10. Sensitivity and specificity at that fixed threshold; AUROC from the
  MC-dropout mean probability, primary because it is threshold-free (`docs/10` §2, §4).
- **Intervals:** patient-level bootstrap, 2000 resamples, α = 0.05, seed 20260916, with `n` in
  patients beside every figure (`docs/10` §2).
- **Empty cases:** a class-absent volume scores Dice 1.0 if nothing is predicted and 0.0
  otherwise. HD95 drops a volume where exactly one of prediction and reference is empty, so
  its `n` can be smaller (`docs/10` §2, §5.2).
- **Gap:** in-domain − held-out, a point difference with no interval, because the two arms are
  bootstrapped separately (`docs/10` §2).
- **Never reported:** accuracy. Fluid is so rare that a null predictor would score highly
  (`docs/06` §3.2).
- **Not evaluated:** calibration. No calibration claim is made (`docs/10` §6).

## Quantitative analyses, including per-vendor breakdown

### Headline — primary, pre-registered

**No cross-vendor difference in Dice is established at 95%, in either direction.** In all three
folds and for all three classes, the held-out and in-domain intervals overlap: 9 of 9
comparisons. The point differences point both ways. **The main limitation is the in-domain
arms of 7 patients per fold**, which leave Dice intervals 0.15–0.52 wide (`docs/10` Summary,
§8.3).

### Segmentation — primary, pre-registered (`docs/10` §3)

Copied unchanged. **Gap convention:** for Dice, a positive gap means worse on the unseen vendor.
For HD95, where lower is better, a positive gap means the in-domain arm is worse. `n` is
patients.

| Held-out vendor (trained on) | Class | Held-out Dice | In-domain reference Dice | Gap | Intervals overlap |
|---|---|---|---|---|---|
| cirrus (spectralis + topcon) | IRF | **0.3456** [0.2470, 0.4438] n=24 | **0.5561** [0.3369, 0.7291] n=7 | +0.2105 | yes |
| cirrus (spectralis + topcon) | SRF | **0.2478** [0.1428, 0.3627] n=24 | **0.1276** [0.0015, 0.3693] n=7 | -0.1201 | yes |
| cirrus (spectralis + topcon) | PED | **0.1915** [0.0956, 0.2987] n=24 | **0.2742** [0.0385, 0.5599] n=7 | +0.0827 | yes |
| spectralis (cirrus + topcon) | IRF | **0.2298** [0.1487, 0.3273] n=24 | **0.4721** [0.2269, 0.6937] n=7 | +0.2424 | yes |
| spectralis (cirrus + topcon) | SRF | **0.4971** [0.3429, 0.6544] n=24 | **0.1261** [0.0000, 0.3761] n=7 | -0.3710 | yes |
| spectralis (cirrus + topcon) | PED | **0.3125** [0.1783, 0.4618] n=24 | **0.1562** [0.0000, 0.3522] n=7 | -0.1563 | yes |
| topcon (cirrus + spectralis) | IRF | **0.4585** [0.3297, 0.5768] n=22 | **0.3133** [0.1376, 0.4815] n=7 | -0.1452 | yes |
| topcon (cirrus + spectralis) | SRF | **0.2687** [0.1380, 0.3951] n=22 | **0.1740** [0.0000, 0.3663] n=7 | -0.0947 | yes |
| topcon (cirrus + spectralis) | PED | **0.1955** [0.0928, 0.3051] n=22 | **0.0511** [0.0000, 0.1534] n=7 | -0.1444 | yes |

| Held-out vendor (trained on) | Class | Held-out HD95 (mm) | In-domain reference HD95 (mm) | Gap | Intervals overlap |
|---|---|---|---|---|---|
| cirrus (spectralis + topcon) | IRF | 1.4973 [0.3614, 3.0828] n=18 | 0.9594 [0.0446, 2.0126] n=6 | -0.5380 | yes |
| cirrus (spectralis + topcon) | SRF | 1.2215 [0.2693, 2.3118] n=12 | 7.6029 [0.0355, 17.1420] n=3 | +6.3813 | yes |
| cirrus (spectralis + topcon) | PED | 1.5850 [0.6284, 2.9064] n=12 | 0.0879 [0.0000, 0.2215] n=3 | -1.4971 | **no** |
| spectralis (cirrus + topcon) | IRF | 2.1144 [0.8778, 3.8042] n=21 | 1.2267 [0.0349, 3.5668] n=5 | -0.8877 | yes |
| spectralis (cirrus + topcon) | SRF | 1.6210 [0.2542, 3.8001] n=21 | 3.1980 [0.0156, 6.3804] n=2 | +1.5770 | yes |
| spectralis (cirrus + topcon) | PED | 0.7311 [0.1511, 1.5883] n=16 | 2.2425 [0.0369, 4.4482] n=2 | +1.5115 | yes |
| topcon (cirrus + spectralis) | IRF | 2.5188 [1.2436, 3.9942] n=17 | 1.6540 [0.1387, 4.6278] n=6 | -0.8647 | yes |
| topcon (cirrus + spectralis) | SRF | 3.9000 [1.6269, 6.5503] n=11 | 9.7733 [0.1212, 19.4254] n=2 | +5.8733 | yes |
| topcon (cirrus + spectralis) | PED | 1.3764 [0.6491, 2.1073] n=9 | 4.6798 (single patient, no spread) n=1 | +3.3035 | **no** |

**Dice: all nine comparisons overlap. HD95: two do not**, cirrus PED and topcon PED, with
in-domain arms of 3 and 1 patients; nothing is concluded from either (`docs/10` §3).

**Cirrus has a second, unseeded draw** from 2026-10-01, kept beside the seeded record in
`docs/10` §3.1. Only the seeded figures above are reproducible, and only they are carried into
any cross-fold statement.

### Detection — primary, pre-registered (`docs/10` §4)

Copied unchanged. Sensitivity and specificity at the fixed threshold of 10 predicted voxels.
**AUROC carries no interval**, because the per-volume detection score was not persisted in any
sealed record (`docs/08` D9). That is a gap against the project's own rule that every metric
carries an interval, stated rather than hidden (`docs/10` §8.7).

| Held-out vendor | Class | Arm | AUROC (positives/negatives) | Sensitivity | Specificity |
|---|---|---|---|---|---|
| cirrus | IRF | held-out | **1.0000** (+18/−6) | 1.0000 [1.0000, 1.0000] n=18 | 0.0000 [0.0000, 0.0000] n=6 |
| cirrus | IRF | in-domain | **1.0000** (+6/−1) | 1.0000 [1.0000, 1.0000] n=6 | 0.0000 (single patient, no spread) n=1 |
| cirrus | SRF | held-out | **0.9931** (+12/−12) | 1.0000 [1.0000, 1.0000] n=12 | 0.0000 [0.0000, 0.0000] n=12 |
| cirrus | SRF | in-domain | **1.0000** (+3/−4) | 1.0000 [1.0000, 1.0000] n=3 | 0.2500 [0.0000, 0.7500] n=4 |
| cirrus | PED | held-out | **0.9514** (+12/−12) | 1.0000 [1.0000, 1.0000] n=12 | 0.0000 [0.0000, 0.0000] n=12 |
| cirrus | PED | in-domain | **1.0000** (+2/−5) | 1.0000 [1.0000, 1.0000] n=2 | 0.2000 [0.0000, 0.6000] n=5 |
| spectralis | IRF | held-out | **1.0000** (+20/−4) | 1.0000 [1.0000, 1.0000] n=20 | 0.2500 [0.0000, 0.7500] n=4 |
| spectralis | IRF | in-domain | **1.0000** (+5/−2) | 1.0000 [1.0000, 1.0000] n=5 | 0.0000 [0.0000, 0.0000] n=2 |
| spectralis | SRF | held-out | **0.9929** (+14/−10) | 1.0000 [1.0000, 1.0000] n=14 | 0.9000 [0.7000, 1.0000] n=10 |
| spectralis | SRF | in-domain | **0.7000** (+2/−5) | 1.0000 [1.0000, 1.0000] n=2 | 0.0000 [0.0000, 0.0000] n=5 |
| spectralis | PED | held-out | **0.9931** (+12/−12) | 1.0000 [1.0000, 1.0000] n=12 | 0.4167 [0.1667, 0.6667] n=12 |
| spectralis | PED | in-domain | **1.0000** (+2/−5) | 1.0000 [1.0000, 1.0000] n=2 | 0.0000 [0.0000, 0.0000] n=5 |
| topcon | IRF | held-out | **1.0000** (+17/−5) | 1.0000 [1.0000, 1.0000] n=17 | 0.0000 [0.0000, 0.0000] n=5 |
| topcon | IRF | in-domain | **1.0000** (+6/−1) | 1.0000 [1.0000, 1.0000] n=6 | 0.0000 (single patient, no spread) n=1 |
| topcon | SRF | held-out | **0.9793** (+11/−11) | 1.0000 [1.0000, 1.0000] n=11 | 0.0000 [0.0000, 0.0000] n=11 |
| topcon | SRF | in-domain | **1.0000** (+2/−5) | 1.0000 [1.0000, 1.0000] n=2 | 0.0000 [0.0000, 0.0000] n=5 |
| topcon | PED | held-out | **1.0000** (+9/−13) | 1.0000 [1.0000, 1.0000] n=9 | 0.0000 [0.0000, 0.0000] n=13 |
| topcon | PED | in-domain | **1.0000** (+1/−6) | 1.0000 (single patient, no spread) n=1 | 0.0000 [0.0000, 0.0000] n=6 |

**Sensitivity is 1.0000 in every cell, and specificity is 0.0000 in 13 of 18.** At 10 voxels
the model calls almost every class present in almost every volume. The ranking is informative,
with AUROC 0.95–1.00 in every held-out arm; the fixed operating point is not. In-domain AUROC
rests on 1–6 positives per cell (`docs/10` §4).

### Secondary, pre-registered (`docs/07` §19)

- **False positives in class-absent volumes** (§19.1; post-hoc for cirrus). In 14 of 18 fold ×
  arm × class cells, every class-absent volume scored Dice 0. The exceptions come from the
  spectralis-held-out model on spectralis volumes, plus one cirrus in-domain PED volume
  (`docs/10` §7.1).
- **A threshold selected on validation** (§19.2; post-hoc for cirrus). Sensitivity stays 1.0000
  in every cell. Three classes are degenerate, with no `val` negative, and every non-degenerate
  selection rests on 1–4 `val` negatives, so several are not stable operating points. The
  fixed-threshold figures above remain the primary detection result (`docs/10` §7.3).

### Post-hoc analyses

**All post-hoc: declared after the per-fold results were visible.** They do not replace the
primary figures above.

**Pooled across folds, all volumes** (post-hoc pooling rule: the patient is the unit; `docs/10`
§5.1, §5.2):

| Class | Pooled held-out Dice | Pooled in-domain Dice | Gap |
|---|---|---|---|
| IRF | **0.3414** [0.2787, 0.4094] n=70 | **0.4201** [0.2595, 0.5669] n=13 | +0.0787 |
| SRF | **0.3398** [0.2563, 0.4259] n=70 | **0.1624** [0.0031, 0.3514] n=13 | -0.1774 |
| PED | **0.2343** [0.1686, 0.3098] n=70 | **0.1400** [0.0314, 0.2694] n=13 | -0.0942 |

All three pairs overlap. **The arms differ in case mix:** the in-domain arms carry more
class-absent volumes than the held-out arms, 62% against 47% for SRF and 77% against 53% for
PED, pooled. Because class-absent volumes nearly always score 0 here, part of the SRF and PED
gaps reflects composition, not vendor (`docs/10` §5.2).

**Class-present volumes only, pooled** (post-hoc; `docs/10` §5.3). This removes the
composition confound:

| Class | Held-out, class present | In-domain, class present | Gap |
|---|---|---|---|
| IRF | **0.4163** [0.3586, 0.4731] n=55 | **0.4965** [0.3542, 0.6320] n=11 | +0.0802 |
| SRF | **0.4537** [0.3753, 0.5259] n=37 | **0.4223** [0.1212, 0.7234] n=5 | -0.0315 |
| PED | **0.3757** [0.3075, 0.4461] n=33 | **0.4400** [0.2696, 0.6429] n=3 | +0.0643 |

All three overlap. Per fold, three class-present comparisons do not overlap, each resting on an
in-domain stratum of 5, 2 or 1 patients; no vendor-specific conclusion is drawn from them
(`docs/10` §5.3).

**The difference bootstrapped directly** (post-hoc; `docs/10` §5.4). Six of 24 difference
intervals exclude zero, with no multiplicity correction, pointing both ways and resting on
in-domain strata of 1–6 patients; none of the six pooled intervals does. One of the nine
pre-registered all-volume comparisons excludes zero: **spectralis SRF, held-out − in-domain
+0.3710 [+0.0537, +0.6045]**, where the held-out vendor scores *higher*, and which is the cell
most exposed to the case-mix confound. **No cross-vendor difference is concluded.**

**What the design can detect** (derived from the §5.4 interval widths): an observed difference
must exceed 0.14–0.29 Dice per fold, or 0.14–0.18 pooled, to exclude zero. **Differences smaller
than about 0.14 Dice cannot be detected**, and per-fold differences below about 0.3 are detected
unreliably (`docs/10` Summary, §5.4).

### Illustrative cases

Six B-scans, chosen by a rule committed before any was rendered, are shown in `docs/10` §7.4.
They are not results and not typical. A qualitative observation from the author's review of two
of them is recorded there, labelled as such: predicted fluid in locations where that fluid type
cannot occur. How often this happens has not been measured (`docs/10` §7.4).

## Ethical considerations

- **Data use is governed by an agreement, not by this card.** The obligations in Training data
  above apply to anyone holding the data. The data was never uploaded, and the checkpoints are
  not published (`docs/06` §7.1, §8.2).
- **No real patient data was handled beyond the public challenge data.** RETOUCH contains no
  protected health information. De-identification is implemented and verified anyway, as a
  demonstrated control (`docs/06` §5).
- **No reidentification.** No linkage to external data and no attempt to recover identity from
  image content or metadata. Pseudonyms are salted one-way hashes, and the salt is never
  committed (`docs/06` DMP-C11, §5).
- **No image content in assistant sessions.** No image, mask or pixel content entered a
  coding-assistant session; the illustrative B-scans were reviewed by the author outside any
  session (`docs/06` DMP-C12, §7.3).
- **Automation bias.** Grader review is not treated as fully mitigating. A plausible but wrong
  segmentation is more readily accepted than an obviously wrong one, and a systematic,
  vendor-correlated bias is invisible case by case (`docs/03` §4.1, §5.1).
- **Subgroups other than vendor are not assessable.** RETOUCH ships pixel data, a reference
  segmentation and voxel spacing only (`docs/06` §3.3). With no age, sex or ethnicity, performance
  across those groups cannot be measured, and nothing about it is claimed. Performance by
  disease (AMD against RVO) is not reported.
- **Selective reporting is guarded against by design.** The analysis was pre-registered, the test
  data was sealed, and every post-hoc analysis is labelled where it appears (`docs/10`
  introduction).

## Caveats and recommendations

**Caveats, from `docs/10` §7 and §8:**

1. **The in-domain arms are too small to resolve the question** (§8.3). Seven patients per
   fold; 13 pooled. Negative findings are underpowered, not reassuring.
2. **Every measured cross-vendor gap is a lower bound** on the raw-data gap (§8.1). Per-volume
   normalisation removed a Topcon detector offset that was perfectly correlated with vendor. The
   comparison run that would measure what it removed was not done.
3. **All-volume Dice is dominated by false positives in class-absent volumes** (§7.1) and is
   confounded with case mix (§5.2). Class-present Dice is the cleaner view.
4. **The metric is fragile in small arms** (§7.2). Two equally valid MC-dropout draws moved one
   in-domain SRF Dice by −0.1431; one class-absent volume flipping between Dice 1 and 0 moves a
   7-patient mean by 0.1429.
5. **The fixed detection threshold is not a usable operating point** (§4, §7.3): specificity is
   0.0000 in 13 of 18 cells.
6. **Axial downsampling has an unmeasured cost** (§8.2). Cirrus loses real axial detail; the
   native-resolution comparison was not run.
7. **The reference standard's variability is unquantified** (§8.4), and the official test
   partition was not used (§8.5).
8. **The pre-registered pooling assumption was false** (§8.6), so the pooled figures are
   post-hoc.
9. **Reproducibility is established on this machine only** (§8.7): one GTX 1050 and one torch
   build. AUROC has no interval.
10. **Image quality is not separated from appearance shift** (§8.8).
11. **Calibration is not evaluated** (§6), so the MC-dropout confidence is not shown to track
    error.

**Recommendations:**

- **Do not use these models, or this card, to support any clinical decision.**
- Treat every output as a candidate for grader review, never as a measurement (URS-003).
- Read any Dice figure here with its `n` and interval, per class and per vendor; never as an
  aggregate (URS-007).
- Prefer the class-present view when asking about segmentation quality, and say which view is
  used.
- Do not read "no difference established" as "generalises across vendors". A study that could
  answer the question needs more in-domain patients than this dataset holds (`docs/10` §9).
- Any reuse on other data, scanners or protocols needs its own pre-registered evaluation.
- Keep any DICOM output on a local PACS until the UID root is registered (`docs/06` §7.2).
