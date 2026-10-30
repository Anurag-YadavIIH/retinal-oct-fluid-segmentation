# OcuVal

A study of whether software that outlines fluid in eye scans still works on a scanner brand it never saw while learning, built and documented the way medical device software is.

**Not for clinical use.**

The results were corrected and audited; see [Corrections and independent audit](https://anurag-yadaviih.github.io/retinal-oct-fluid-segmentation/#corrections) on the [project report page](https://anurag-yadaviih.github.io/retinal-oct-fluid-segmentation/).

## At a glance

- **What:** software that outlines three kinds of fluid in eye scans, tested and documented the way a medical device would be.
- **Question:** if it learns from two scanner brands, does it work as well on a third brand it has never seen?
- **Result:** the test I wrote down in advance found a difference in 1 of 9 comparisons, and there the unseen brand scored higher. No drop on the unseen brand was established, but the test could only detect large differences.
- **How:** the analysis was fixed before any result existed, the test scans stayed sealed until the end, every run can be repeated exactly, and an audit re-checked the whole pipeline.
- **Built with:** Python, PyTorch, MONAI, pydicom, highdicom, GitHub Actions.

![Overlap score with 95% intervals on the unseen scanner brand and on new patients from the familiar brands, for each run and fluid type, with the three runs combined in the bottom rows.](docs/figures/fig2_dice_intervals.svg)

*How well the outlines matched the expert's, on the unseen brand (orange) and on new patients from the familiar brands (blue), with the range each score could plausibly take. In 11 of the 12 rows the two ranges overlap. In the one that does not, the unseen brand scores higher. Figure 2 of [`docs/10`](docs/10_analytical_validation_report.md).*

## In plain words

An OCT scan uses light to take cross-section pictures of the back of the eye. In some common eye diseases, fluid collects in or under the retina, and doctors track how much there is to decide on treatment. I trained a model to outline three kinds of this fluid. Hospitals use scanners from different companies, and their pictures look different, so I asked whether a model that learned from two brands still works on a third. The test I planned in advance found no drop on the new brand, but it could only have seen a large one, so it does not prove the model works there. A check I chose afterwards hints at a smaller drop, but cannot prove it.

## What I found

The score I use is the **Dice score**: how much the model's outline overlaps the expert's, from 0 (no overlap) to 1 (a perfect match). The three kinds of fluid are **IRF** (fluid inside the retina), **SRF** (fluid under it) and **PED** (a pocket where the retina's bottom layer lifts away).

**1. No drop on the unseen brand was established, and the test could only see large differences.** I trained the model three times, each time leaving one scanner brand out, and tested it on the brand it had not seen. I compared that score with its score on new patients from the brands it had seen. The rule I wrote down in advance asks whether the two scores' 95% ranges overlap. They overlapped in 8 of the 9 comparisons (three brands, three kinds of fluid). In the ninth the unseen brand scored higher, in a group where most familiar-brand scans happened to contain none of that fluid. Each familiar-brand group held only 7 patients, so the test could not reliably see a difference smaller than about 0.14 on that scale.

**2. A check I chose afterwards points the other way, but cannot prove it.** Counting only scans that contain the fluid, and combining the three runs, the unseen brand scored lower for two of the three fluid types, and for both the range of plausible differences leaves out zero. I chose this check after seeing the results, it is not corrected for making several comparisons, and one of the two rests on 3 familiar-brand patients. So it is a hint, not a finding. The two views disagree because of how the score treats scans without fluid, described next.

**3. The model marks fluid in scans that have none of that kind.** In most scans without a given fluid, the model still marks a little of it, and the score counts that as a complete miss. The familiar-brand groups happened to contain more such scans, so part of those comparisons reflects which scans were in each group rather than the scanner brand. Looking at the largest false alarms, I saw some marked fluid in places where that kind of fluid cannot occur; I have not measured how often this happens. [`docs/10`](docs/10_analytical_validation_report.md) §5.2, §7.1, §7.4.

**4. An audit found twelve defects, and the results held.** After publishing, I had the whole pipeline audited. Two of the defects changed what was measured: each prediction sat about one pixel row too deep, and one score also read the blank border added around each image. I fixed all twelve, each with a test that failed before the fix, and evaluated every sealed test group once more. No average score moved by more than 0.0072 on the 0 to 1 scale, no detection result changed, and every conclusion above is the same. The earlier figures are kept, labelled, in [`docs/10`](docs/10_analytical_validation_report.md) section 10, and the audit is summarised in section 11.

## What the outlines look like

Six single slices from the unseen-brand scans, each showing the expert's outline on the left and the model's on the right. A rule I fixed before drawing any image chose them from the numbers alone, so none was picked for looking good. They illustrate; they are not results, and the false alarms are the worst cases, not typical ones. The challenge organiser gave written permission for a very small number of images.

| | |
|---|---|
| ![Lowest-scoring unseen-brand scan, expert's outline left and model's right.](docs/figures/bscan_worst.png) | ![Median unseen-brand scan, expert's outline left and model's right.](docs/figures/bscan_median.png) |
| **Lowest-scoring scan.** The model marks no fluid on this slice. | **Middle-scoring scan.** The model misses fluid pockets the expert marked clearly. |
| ![Highest-scoring unseen-brand scan, expert's outline left and model's right.](docs/figures/bscan_best.png) | ![Largest false alarm for IRF, expert's outline left and model's right.](docs/figures/bscan_fp_irf.png) |
| **Highest-scoring scan.** Close to the expert's outline, but about a quarter smaller. | **Largest false alarm for IRF.** IRF marked where the expert found none. |
| ![Largest false alarm for SRF, expert's outline left and model's right.](docs/figures/bscan_fp_srf.png) | ![Largest false alarm for PED, expert's outline left and model's right.](docs/figures/bscan_fp_ped.png) |
| **Largest false alarm for SRF.** SRF marked where the expert found none. | **Largest false alarm for PED.** PED marked where the expert found none. |

The full captions are in [`docs/10`](docs/10_analytical_validation_report.md) §7.4.

## Why you can trust it

- **The analysis was written down first.** Every test, threshold and statistic was fixed in [`docs/07`](docs/07_vv_protocol.md) before the results it covers existed. Anything decided afterwards is labelled post-hoc wherever it appears.
- **The test scans were sealed.** The code refuses to read them without a recorded reason and approval, and logs every access. Each later re-run of the evaluation was written down before any sealed scan was opened again.
- **Every run can be repeated exactly.** Two runs of the evaluation had to match value for value before any sealed scan was opened, and they did. A test on this machine showed two training runs producing byte-identical model weights.
- **The pipeline was audited.** The audit recomputed every score on the open validation scans with separately written code that shares nothing with the pipeline, and found no difference. Every derived number in the documents is regenerated from the evaluation records, and a commit is blocked if the documents disagree with them. Every prediction of the final evaluation is saved with a checksum, and no sealed test group can be opened until a dry run of the whole procedure has passed on made-up data.

[`docs/08`](docs/08_vv_report.md) records every run; [`docs/09`](docs/09_traceability_matrix.md) traces every requirement to a test.

## Worth a closer look

**A check that caught every prediction sitting one row too deep.** After publishing, I pushed made-up outlines of known shape through the real image preparation and back. They should have come back exactly where they started. On real outlines they came back about one to one and a half pixel rows lower, a shift no earlier test could see, because every earlier test compared the code with itself. I fixed it, re-ran the evaluation, and the results held. [`docs/13`](docs/13_change_control_log.md), 2026-10-29.

**A pixel-spacing mix-up that only real data could reveal.** The source files store pixel spacing in a different order from this project. Every made-up test used the project's own order, so none tested the conversion. For one brand, a swap would make a correct outline's fluid volume wrong by a factor of 6.0. A simple size check catches 0 of 210 swapped cases; checking against each brand's known spacing catches all 210. [`docs/13`](docs/13_change_control_log.md), 2026-09-23 and 2026-09-25.

**Refusing to make up scan details the data does not contain.** The dataset does not record which eye was scanned, but the medical imaging standard (DICOM) requires that field and has no "unknown" value. The easy fix is to write a plausible value. The code refuses instead, or under an explicit research setting leaves the field out and logs it. A visible gap is safer than an invented fact every later reader would trust. [`docs/05`](docs/05_risk_management_file.md) RC-029; [`docs/11`](docs/11_dicom_conformance_statement.md).

**A rule for illustrations that failed review.** I wrote a rule to crop the example images to the retina before drawing them. The rule was followed exactly, and the images came out stretched, because I had let each crop fill the whole frame. I rejected them, recorded the rule and the run, and drew the images again without the crop. [`docs/07`](docs/07_vv_protocol.md) §21.12 and §21.13.

## Quick start

Developed on Windows 11 with Python 3.11 and an NVIDIA GTX 1050; CI runs the tests on Ubuntu. Install from the lock file, which is the environment the results were produced in. A test (TC-099) fails if the installed environment drifts from it.

```bash
git clone https://github.com/Anurag-YadavIIH/retinal-oct-fluid-segmentation.git
cd retinal-oct-fluid-segmentation
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.lock
pip install -e ".[dev]" --no-deps
```

**The GPU build of PyTorch cannot be expressed in the lock.** Training used `torch==2.3.1+cu121`, which is not on PyPI, so install it explicitly:

```bash
pip install --index-url https://download.pytorch.org/whl/cu121 \
    --force-reinstall --no-deps "torch==2.3.1"
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"   # 2.3.1+cu121 True
```

**Machine-specific settings** are environment variables and are never committed: `OCUVAL_CACHE_DIR` (where the frame cache lives) and `OCUVAL_DEID_SALT` (see [`docs/06`](docs/06_data_management_plan.md) §5.1). **The dataset is not downloaded automatically.** RETOUCH requires registration; `scripts/00_fetch_data.py` documents the manual steps.

Checks, as CI runs them:

```bash
ruff check src tests scripts && ruff format --check src tests scripts
mypy src scripts
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

`test` and `in_domain_ref` are sealed: `05_evaluate.py` refuses them unless given `--unlock-bucket` with a reason and an approver, records every access, and needs a completed dry run of its chain. Long runs are launched from an interactive terminal that is kept open ([`docs/07`](docs/07_vv_protocol.md) §17.8). DICOM objects produced here must stay on a local archive, because their identifier root is unregistered by declaration ([`docs/06`](docs/06_data_management_plan.md) §7.2).

## Repository map

| Path | Contents |
|---|---|
| [`docs/`](docs/) | The document set, from `01` intended use to `13` change-control log; `figures/` holds the result figures |
| `src/ocuval/io/` | Reading the source scans, DICOM writing, de-identification, the archive client |
| `src/ocuval/data/` | Patient-level splits, image preparation, data loading |
| `src/ocuval/models/` | Segmentation network and its uncertainty estimate |
| `src/ocuval/training/` | Training loop, checkpoints, hardware telemetry |
| `src/ocuval/eval/` | Metrics, patient-level bootstrap, sealed splits, the evaluation and report pipeline, saved predictions |
| `src/ocuval/report/` | DICOM Segmentation and Structured Report objects |
| `src/ocuval/service/` | Inference service (stub) |
| `scripts/` | Numbered pipeline entry points `00` to `08`, and the evaluation and illustration chains `10` to `17` |
| `site/`, `site_src/` | The report page, generated from the evaluation records by `scripts/08_build_site.py`, and its template |
| `configs/` | Data, training and per-fold configuration |
| `tests/` | pytest suite; each test name carries its `TC-nnn` identifier |

## Status and limitations

**Works and is verified:** conversion of all 70 scans to DICOM, with de-identification; patient-level splits with a leakage test that gates CI; training and evaluation of all three runs; the sealed, reproducible evaluation and its report ([`docs/10`](docs/10_analytical_validation_report.md)); DICOM Segmentation and Structured Report objects; storing and retrieving DICOM objects through an archive in CI ([`docs/08`](docs/08_vv_report.md) §5h).

**Not done:**

- **Writing the model's results as DICOM files.** The builders exist and are tested, but no pipeline step calls them yet.
- **The inference service** is a stub.
- **Part of the archive round trip is unchecked:** the tests do not yet confirm that the fluid volumes, the confidence value and the research-use label survive it.
- **Optional analyses not run:** a RETOUCH leaderboard submission, and measuring how much of the brand difference the per-scan brightness adjustment removes ([`docs/10`](docs/10_analytical_validation_report.md) §8.1).

**Known weaknesses:** each familiar-brand comparison group holds 7 patients, so only large differences are detectable; the score is fragile when a fluid type is absent; the models were trained with labels about one pixel row off their images (half of a defect the audit found) and were not retrained, because retraining would be a new experiment; detection ranges were computed after the results were visible, and for twelve of the eighteen the interval is not estimable, because every resample scores a perfect 1; and the reproducibility claims are proven on this machine's GPU and software versions only.

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
