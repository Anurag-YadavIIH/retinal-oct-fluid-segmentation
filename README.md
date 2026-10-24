# OcuVal

A study of whether software that finds fluid in eye scans still works on a scanner brand it was never trained on, built and documented the way medical device software is.

**Project report page:** [anurag-yadaviih.github.io/retinal-oct-fluid-segmentation](https://anurag-yadaviih.github.io/retinal-oct-fluid-segmentation/), with interactive charts and every table as a CSV download.

## At a glance

- **What:** a pipeline that outlines three types of fluid in retinal OCT scans, converts the scans to standard medical imaging (DICOM) files, and includes tested code for packaging results as DICOM.
- **Question:** does it work as well on a scanner brand it never saw in training?
- **Answer:** by the pre-registered test, no drop in performance on an unseen brand was established. The one difference found, in 1 of 9 comparisons, favoured the unseen brand and is consistent with which scans happened to be in each group. An analysis chosen after seeing the results, counting only scans that contain fluid, hints that the unseen brand does worse; that is suggestive, not proven. The study can only detect differences larger than about 0.16 Dice.
- **How:** test data sealed until the end, the analysis written down before any results, training and evaluation reproducible, documented following medical device software standards (IEC 62304, ISO 14971).
- **Built with:** Python, PyTorch, MONAI, pydicom, highdicom, GitHub Actions.

> **Earlier figures were measured through a defect; the results below are corrected.** The figures first published here came from an evaluation that put each prediction back into the scanner's own geometry without first removing the padding added during preprocessing, which misplaced the Cirrus and Spectralis predictions. I fixed that step and evaluated every sealed test group again with the same models, on 2026-10-24. The earlier figures are kept, labelled, in [Earlier figures](#earlier-figures-measured-through-the-defect) below and in [`docs/10`](docs/10_analytical_validation_report.md) section 10. The finding: [`docs/13`](docs/13_change_control_log.md), 2026-10-16.

> **Not for clinical use.** This is a research and portfolio project built on public challenge data. It has never been used on patients, has not been validated for patient care, and makes no clinical claim of any kind.

![Dice score with 95% intervals on the unseen scanner brand and on new patients from the familiar brands, for each run and fluid type, with the three runs combined in the bottom rows.](docs/figures/fig2_dice_intervals.svg)

*Figure 2 of [`docs/10`](docs/10_analytical_validation_report.md). In 11 of the 12 rows the unseen brand's interval (orange) overlaps the familiar brands' interval (blue). In the one that does not, the unseen brand scores higher, which is the one difference the pre-registered comparison established. The blue intervals are wide because each run's familiar-brand group has only 7 patients. The bottom three rows combine all three runs, an analysis I chose after seeing the results.*

The difference between the two arms, with its own interval for each row, is shown in [Figure 4 of `docs/10` (section 5.4)](docs/10_analytical_validation_report.md#54-the-difference-bootstrapped-directly--post-hoc).

## In plain words

An OCT scan uses light to take cross-section pictures of the back of the eye, a bit like an ultrasound but far finer. In some common eye diseases, fluid collects in or under the retina, and doctors watch how much there is to decide on treatment and to see whether it is working. I trained a model that outlines three kinds of this fluid in OCT scans. Hospitals use scanners from different companies whose images look different, so I asked: if the model learns from two brands, does it still work on a third it has never seen? The honest answer is that the test I planned in advance found no drop on the new brand, but it could only have detected a large one, so it does not show that the model works on the new brand. A check I chose after seeing the results hints at a drop, but cannot prove one. The aim was a trustworthy measurement rather than the highest score, and part of why the scores are modest is the pattern described in [finding 2](#what-i-found): the model marks fluid in scans that have none of that type, though even counting only scans that do contain it, the scores stay moderate.

## What I found

**1. No drop on the unseen brand was established, and the test was only sensitive to large differences.** I trained the model three times, each time leaving one scanner brand out, and tested it on the brand it had not seen. I compared that score with its score on new patients from the brands it had seen. The test I wrote down in advance asks whether the two scores' 95% intervals overlap. They did in 8 of the 9 comparisons (three brands, three kinds of fluid). In the ninth the unseen brand scored *higher*, for a fluid type where the familiar-brand group happened to hold mostly scans without that fluid (finding 2), so it is consistent with which scans were in each group. The gap went one way in some cases and the other way in others. Each comparison group from the familiar brands held only 7 patients, so the test could not reliably see a difference smaller than about 0.16 on the score used here (Dice, which runs from 0 to 1).

An analysis I chose after seeing the results points the other way. Counting only scans that contain the fluid, and combining the three runs, the unseen brand scored lower for two of the three fluid types, with intervals that exclude zero. That hints at a real drop. But it was chosen after the fact, it is not corrected for the number of comparisons, and one of the two rests on 3 familiar-brand patients, so it is suggestive, not proven. The two views disagree because of how the score treats scans without fluid (finding 2). The full answer, with every interval, is in [`docs/10`](docs/10_analytical_validation_report.md).

**2. The model marks fluid in scans that have none of that type.** In most scans without a given fluid type, the model still marks a little of it. The score treats that as a complete miss for the scan, which drags the average down. For two of the three fluid types (SRF and PED), the groups from the familiar brands happened to contain more such scans, so part of those comparisons reflects which scans were in each group rather than the scanner brand. [`docs/10`](docs/10_analytical_validation_report.md) §5.2 and §7.1.

**3. With only 7 patients, the score is fragile.** If one scan without fluid flips between "nothing marked" and "a few pixels marked", its score jumps from 1 to 0, and a 7-patient average moves by about 0.14. I saw a shift of about that size (0.1431) between two equally valid runs of the same model, before I made the evaluation reproducible. Both runs were measured through the defect described at the top, which does not change this arithmetic. The older run did not keep per-scan scores, so I cannot confirm that a single scan caused it. [`docs/10`](docs/10_analytical_validation_report.md) §7.2.

**What an outline looks like.** This is the median unseen-brand scan. I chose it by a rule I fixed before rendering any image, so it was not picked for looking good, and I regenerated it from the corrected results, replacing the image first shown here, which was drawn through the defect described at the top. The full set, including the worst scan and the largest false positives, is in [`docs/10`](docs/10_analytical_validation_report.md) §7.4. The challenge organiser gave written permission for a very small number of illustrative images.

![One B-scan from the median unseen-brand scan: the expert's fluid outline on the left and the model's on the right.](docs/figures/bscan_median.png)

*The median held-out scan by mean Dice over the fluid types its expert outline contains, shown on its B-scan with the most expert-outlined fluid. Left, the expert's outline; right, the model's. Chosen by the rule pre-registered in [`docs/07`](docs/07_vv_protocol.md) §21, from the numbers alone, before any image was rendered.*

### Earlier figures measured through the defect

Until 2026-10-24 this page reported results measured through the defect described at the top. They are kept here so the change is visible; they are not results. Read that way, all 9 comparisons overlapped, so no difference was established in either direction; the direct check found one difference in 9, in the unseen brand's favour; the post-hoc check counting only scans with fluid found no difference when the three runs were combined; and the study could detect differences larger than about 0.14 Dice. Every earlier figure, labelled, is in [`docs/10`](docs/10_analytical_validation_report.md) section 10.

## Why you can trust it

The test scans were sealed: the code refuses to read them without a recorded reason and approval, and every access is logged. I wrote down the analysis before seeing any result, and anything decided afterwards is labelled post-hoc wherever it appears. Training and evaluation are reproducible: two runs of the evaluation had to match exactly, value for value, before any sealed scan was opened, and they did. When I found a defect in the evaluation after publishing, I fixed it, wrote down the re-evaluation rule before re-opening any sealed scan, ran it once, and kept the old figures beside the new. Every requirement traces to a test, and the traceability counts are checked in CI. [`docs/07`](docs/07_vv_protocol.md) §17, §17.11; [`docs/08`](docs/08_vv_report.md) §5g, §5i; [`docs/09`](docs/09_traceability_matrix.md).

## Worth a closer look

**A cross-check that caught a real defect before any result existed.** I first computed HD95 by pooling both directions of boundary distance into one list. Every test passed, because every test was written from the same understanding as the code. A check against an independent library (MONAI, TC-120) disagreed on 5 of 12 random cases while Dice agreed on all 12. I adopted the standard definition, the larger of the two directions, before reporting anything. [`docs/13`](docs/13_change_control_log.md), 2026-09-17.

**Refusing to make up scan details the data does not contain.** The dataset does not record which eye was scanned, but the DICOM standard requires that field and has no "unknown" value. The easy fix is to write a plausible value. The code refuses instead, or under an explicit research setting leaves the section out and logs it. A visible gap is safer than an invented fact every later reader would trust. [`docs/05`](docs/05_risk_management_file.md) RC-029 and HAZ-015; [`docs/11`](docs/11_dicom_conformance_statement.md).

**A pixel-spacing mix-up that only real data could reveal.** The source files store pixel spacing in a different axis order from this project. Every synthetic test used the project's own order, so none ever tested the conversion. For one brand, a swap would make a correct outline's fluid volume wrong by a factor of 6.0. A simple size check catches 0 of 210 swapped cases; checking against each brand's known spacing catches all 210. The lesson: a test written in the code's own convention cannot test a conversion. [`docs/13`](docs/13_change_control_log.md), 2026-09-23 and 2026-09-25; [`docs/07`](docs/07_vv_protocol.md) §3 rule 7 and §13.3.

**A data-use question settled by asking.** My own reading of the dataset agreement said publishing results here might not be allowed. Rather than pick the convenient reading, I asked a challenge organiser, who confirmed the same day that publishing results is permitted. My stricter reading stays in the record as the reason I asked. [`docs/06`](docs/06_data_management_plan.md) §2.2 and §2.2.1.

**Reproducibility found to be false, then made true and proven.** A resume check passed while a resumed training run was actually seeing data in a different order (D2). One GPU operation fell back to a non-repeatable method 1308 times, with a warning each time that was easy to miss (D3). I fixed both, and two training runs now produce byte-identical weights (TC-121). Two differently configured runs started nine hours apart agree to every recorded digit until their learning-rate schedules diverge (TC-123). Evaluation then turned out not to be repeatable either: two runs of one model differed in 49 figures. I seeded it, and required two runs to match exactly before opening any sealed scan. They matched on 466 of 466 values. [`docs/08`](docs/08_vv_report.md) D2, D3, §5g.1; [`docs/13`](docs/13_change_control_log.md), 2026-10-04.

**A sealed, pre-registered evaluation.** The analysis plan was committed before any held-out result existed. The test scans sit behind an unlock that needs a reason and an approver, and every access is logged. When one assumption written into the plan turned out to be false, I did not run the analysis that depended on it. I decided the replacement, committed it before computing anything, and labelled it post-hoc. [`docs/07`](docs/07_vv_protocol.md) §17, §17.10, §19, §19.5; [`docs/08`](docs/08_vv_report.md) §5g.

## Glossary

- **OCT (optical coherence tomography):** a scan that uses light to image the layers of the retina in cross-section.
- **IRF (intraretinal fluid):** fluid collected within the layers of the retina.
- **SRF (subretinal fluid):** fluid collected under the retina, between it and the layer beneath.
- **PED (pigment epithelial detachment):** a pocket where the retina's bottom layer lifts away from the tissue under it.
- **Scanner brand:** the company that made the OCT machine, called the vendor in the code and documents. This data has three: Cirrus (Zeiss), Spectralis (Heidelberg) and Topcon.
- **Fold:** one round of training and testing. Here each fold leaves one brand out for testing.
- **Dice:** overlap between the model's outline and the expert's, from 0 (none) to 1 (perfect).
- **HD95:** how far, in millimetres, one outline's boundary strays from the other's: the distance that 95% of boundary points stay within, taking the worse of the two directions.
- **Pre-registration:** writing down the analysis before seeing results, so the results cannot shape the method.
- **Sealed test set:** test data the code will not read without a recorded, approved unlock, so it is used once and only as planned.

## Quick start

Developed on Windows 11 with Python 3.11 and an NVIDIA GTX 1050; CI runs the tests on Ubuntu. Install from the lock, which is the environment the results were produced in. TC-099 fails if the installed environment drifts from it.

```bash
git clone https://github.com/Anurag-YadavIIH/retinal-oct-fluid-segmentation.git
cd retinal-oct-fluid-segmentation
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.lock
pip install -e ".[dev]" --no-deps
```

**The CUDA build of PyTorch cannot be expressed in the lock.** Training used `torch==2.3.1+cu121`, which is not on PyPI, so install it explicitly:

```bash
pip install --index-url https://download.pytorch.org/whl/cu121 \
    --force-reinstall --no-deps "torch==2.3.1"
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"   # 2.3.1+cu121 True
```

**Machine-specific settings** are environment variables and are never committed: `OCUVAL_CACHE_DIR` (where the frame cache lives) and `OCUVAL_DEID_SALT` (see [`docs/06`](docs/06_data_management_plan.md) §5.1). **The dataset is not downloaded automatically.** RETOUCH requires registration; `scripts/00_fetch_data.py` documents the manual steps.

Tests, as CI runs them:

```bash
ruff check src tests scripts && ruff format --check src tests scripts
pytest -m "not requires_data and not requires_pacs"
```

Pipeline. **These commands need the RETOUCH training data, which is not included in this repository.** It must be requested from the challenge organisers, after registration, and used under their terms (see [Data, credits and licence](#data-credits-and-licence)).

```bash
python scripts/01_convert_to_dicom.py --config configs/data.yaml
OCUVAL_DEID_SALT=... python scripts/02_deidentify.py --config configs/data.yaml
python scripts/03_make_splits.py --config configs/folds
python scripts/04_train.py --fold configs/folds/cirrus_holdout.yaml --run-dir artifacts/runs/<run> --epochs 150
python scripts/05_evaluate.py --run artifacts/runs/<run> --bucket val
python scripts/07_make_figures.py
python scripts/08_build_site.py
```

`test` and `in_domain_ref` are sealed: `05_evaluate.py` refuses them unless given `--unlock-bucket` with a reason and an approver, and records every access. Long runs are launched from an interactive terminal that is kept open ([`docs/07`](docs/07_vv_protocol.md) §17.8). DICOM objects produced here must stay on a local PACS, because the UID root is unregistered by declaration ([`docs/06`](docs/06_data_management_plan.md) §7.2).

## Repository map

| Path | Contents |
|---|---|
| [`docs/`](docs/) | The document set, from `01` intended use to `13` change-control log; `figures/` holds the result figures |
| `src/ocuval/io/` | RETOUCH and MetaImage reading, DICOM writing, de-identification, DICOMweb client |
| `src/ocuval/data/` | Patient-level splits, MONAI transforms, datamodule and frame cache |
| `src/ocuval/models/` | Segmentation network, MC-dropout uncertainty |
| `src/ocuval/training/` | Training loop, deterministic loss, checkpoints, accelerator telemetry |
| `src/ocuval/eval/` | Metrics (numpy and scipy, cross-checked against MONAI), patient-level bootstrap, sealed splits, evaluation pipeline |
| `src/ocuval/report/` | DICOM Segmentation and Structured Report objects |
| `src/ocuval/service/` | FastAPI inference service (stub) |
| `scripts/` | Numbered pipeline entry points `00` to `08`, the evaluation chain, the exact record comparison |
| `site/`, `site_src/` | The report page, generated from the evaluation records by `scripts/08_build_site.py`, and its template |
| `configs/` | Data, training and per-fold configuration |
| `tests/` | pytest suite; each test name carries its `TC-nnn` identifier |

## Status and limitations

**Works and is verified:** data conversion to DICOM and de-identification on all 70 scans; patient-level splits with a leakage test that gates CI; training and evaluation of all three folds; the sealed, reproducible evaluation and its report ([`docs/10`](docs/10_analytical_validation_report.md)); DICOM Segmentation and Structured Report objects, built and tested; storing and retrieving DICOM objects through a PACS, run in CI ([`docs/08`](docs/08_vv_report.md) §5h).

**Not done:**

- **Part of the PACS round-trip is unchecked.** The tests that store and retrieve DICOM objects through a PACS (TC-080 to TC-082) first ran on 2026-10-16, in CI, against a throwaway Orthanc archive that receives synthetic objects only, and passed ([`docs/08`](docs/08_vv_report.md) §5h). They do not yet check that the fluid volumes, the confidence value and the research-use label survive the trip.
- **Writing the model's results as DICOM files.** The builders exist and are tested, but no pipeline step calls them yet; `scripts/06_push_to_pacs.py` is a stub.
- **The inference service and `eval/report.py`** are stubs.
- **Optional analyses not run:** a RETOUCH leaderboard submission; and the ablation that would measure how much of the brand difference the per-scan brightness normalisation removes ([`docs/10`](docs/10_analytical_validation_report.md) §8.1).
- **AUROC intervals exist only as a post-hoc analysis.** The corrected records keep each scan's detection score, so intervals were computed after the results were visible. For twelve of the eighteen the interval is not estimable: the model ranked every scan correctly in that group, so every resample scores a perfect 1, which says nothing about uncertainty ([`docs/10`](docs/10_analytical_validation_report.md) §4).

**Known weaknesses:** the familiar-brand comparison groups hold 7 patients per fold, so only large differences are detectable; the per-scan score is fragile when a fluid type is absent; the published results were re-measured after a defect was found, and the illustrative images were regenerated from the corrected results; and the reproducibility claims are proven on this machine's GPU and software versions only.

## How this was built

I designed this project and made its decisions: the research question and
cross-vendor design, the choice of dataset and how its data agreement was
handled, the safety classification, the evaluation protocol written before any
results existed, and the calls on what to report and how. I used Claude Code
(Anthropic) as a coding assistant.

## Data, credits and licence

This project uses the training data of the [RETOUCH challenge](https://retouch.grand-challenge.org/), the Retinal OCT Fluid Detection and Segmentation Benchmark and Challenge. I am grateful to the organisers for making the data available to researchers.

> Bogunović H, Venhuizen F, Klimscha S, et al. RETOUCH: The Retinal OCT Fluid Detection and Segmentation Benchmark and Challenge. *IEEE Transactions on Medical Imaging*. 2019;38(8):1858-1874. doi:[10.1109/TMI.2019.2901398](https://doi.org/10.1109/TMI.2019.2901398)

The data is not redistributed here, in any form. It is available from the organisers after registration and carries its own terms of use, which govern any use of it. The code in this repository is MIT-licensed; that licence does not extend to the data.

## Contact

Anurag Yadav: [LinkedIn](https://www.linkedin.com/in/anurag-yadav-ai) and [portfolio](https://ask-anurag.vercel.app).
