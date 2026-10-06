# OcuVal

**Does a retinal OCT fluid segmentation model trained on two scanner vendors still work on the
third?**

Trained on two of three OCT vendors and evaluated once on the held-out third, under a
pre-registered and reproducible protocol, this model shows **no cross-vendor difference in Dice
that can be established at 95%, in either direction**. That is not evidence that it
generalises. The in-domain comparison arms hold 7 patients per fold, so the design cannot detect
a difference smaller than about 0.14 Dice. The full answer, with every interval, is in
[`docs/10`](docs/10_analytical_validation_report.md).

> **Not for clinical use.** This is a research and portfolio project built on public challenge
> data. It has never been used on patients, has not been validated for patient care, and makes
> no clinical claim of any kind.

The pipeline is DICOM-native, and the software is documented as if it were regulated medical
device software (IEC 62304, ISO 14971). The documentation set covers intended use, numbered
requirements, a risk file, a verification protocol, a traceability matrix and a change-control
log, all under [`docs/`](docs/). That documentation is the point of the project as much as the
model is.

---

## What is worth your attention

**A cross-check that caught a real defect before any result existed.** HD95 was first
implemented by pooling both directed surface distances into one distribution. Every test passed,
because every test was written from the same understanding as the code. A back-to-back check
against MONAI (TC-120) disagreed on 5 of 12 random mask pairs, while Dice agreed on all 12. The
standard definition, the larger of the two directed 95th percentiles, was adopted before any
figure was reported. The pooled version gave plausible numbers comparable to nothing published.
→ [`docs/13`](docs/13_change_control_log.md), 2026-09-17.

**Refusing to fabricate DICOM acquisition metadata.** RETOUCH does not record which eye was
scanned, but DICOM requires `ImageLaterality`, Type 1, with no "unknown" value. The easy fix is
to write a plausible value. The writer refuses instead, or under an explicit research exception
omits the module and logs it. A detectable non-conformance is safer than an invented anatomical
fact that every downstream reader would trust. → [`docs/05`](docs/05_risk_management_file.md)
RC-029 and HAZ-015; [`docs/11`](docs/11_dicom_conformance_statement.md).

**A spacing axis-order defect that only real data could reveal.** MetaImage stores voxel
spacing as (x, y, z). This project uses (axial, lateral, separation). Every synthetic test
fixture was written in the project's own order, so none ever exercised the conversion. For
Cirrus, a transposed pair makes a correct segmentation's volume wrong by a factor of **6.0**.
Measured afterwards, a 0.5 mm physical plausibility bound catches **0 of 210** axis-order cases,
while per-vendor spacing ranges catch all 210. The general lesson: a fixture written in the
consuming code's convention cannot test a conversion. → [`docs/13`](docs/13_change_control_log.md),
2026-09-23 and 2026-09-25; [`docs/07`](docs/07_vv_protocol.md) §3 rule 7 and §13.3.

**A data-use question settled by asking, not by interpretation.** The project's own reading of
the RETOUCH agreement concluded that publishing results here might not be permitted. Rather than
pick the convenient reading, the author asked a challenge organiser, and was told the same day
that publishing results is permitted. The more restrictive reading is kept in the record as the
reasoning that prompted the question. → [`docs/06`](docs/06_data_management_plan.md) §2.2 and
§2.2.1.

**Determinism found to be false, then made true and proven across runs.**

- **Resume.** The resume check passed while a resumed run was actually drawing a different
  sample order and augmentation (D2). Fixed by deriving all per-epoch randomness from
  `(seed, epoch)` instead of saving generator state.
- **Training kernels.** One operation silently fell back to a non-deterministic kernel 1308
  times (D3). Fixed by replacing that loss term with a deterministic equivalent.
- **Proof across runs.** Two runs now produce byte-identical weights (TC-121). Two differently
  configured runs nine hours apart agree to every recorded digit until their learning-rate
  schedules diverge (TC-123).
- **Evaluation.** It turned out not to be reproducible: two runs of one checkpoint differed in 49
  figures. It was seeded per volume, and two runs were then required to match exactly before any
  sealed split was opened. They matched on 466 of 466 values.

→ [`docs/08`](docs/08_vv_report.md) D2, D3, §5g.1; [`docs/13`](docs/13_change_control_log.md),
2026-10-04.

**A sealed, pre-registered evaluation.** The analysis plan was committed before any held-out
result existed. The test and in-domain splits sit behind an unlock that requires a reason and
an approver, and every access is appended to a durable log. When a pre-registered assertion
turned out to be false, the analysis built on it was not run as specified. The fix was decided
by the author, committed before computing, and labelled post-hoc. Every analysis in the report
is marked primary, secondary or post-hoc. → [`docs/07`](docs/07_vv_protocol.md) §17, §17.10,
§19, §19.5; [`docs/08`](docs/08_vv_report.md) §5g.

---

## Status

All three leave-one-vendor-out folds are trained and evaluated (2026-10-05). The figures below
are as recorded in the documents on that date. `docs/09`'s coverage counts are recomputed by
TC-104 on every test run.

| Area | State |
|---|---|
| Data | RETOUCH training partition: 70 volumes, one per patient (cirrus 24, spectralis 24, topcon 22), converted to DICOM, de-identified and verified |
| Training | three folds, locally on a GTX 1050; all ended by early stopping ([`docs/08`](docs/08_vv_report.md) §5c, §5e, §5f) |
| Evaluation | each sealed split evaluated once under a seeded, deterministic procedure ([`docs/08`](docs/08_vv_report.md) §5g) |
| Analytical validation report | [`docs/10`](docs/10_analytical_validation_report.md), draft v0.1 |
| DICOM SEG and SR objects | written and tested; the Orthanc round-trip (TC-080..TC-082) has **never been run**, because Docker is not installed |
| Inference service, `eval/report.py`, `06_push_to_pacs.py` | stubs; not started |
| Requirements | SRS-001..SRS-091, each with a verifying test case allocated |
| Test cases | 114 registered, 90 written, 87 executed, 3 written but never run, 24 registered and not yet written |
| Risk | 16 hazards, 32 risk controls, 27 of them verified by an executed test |
| Suite | 562 passed, 17 skipped, 42 deselected (`requires_pacs`, `slow`); measured locally on CPU, 2026-10-05 |

**CI state is not asserted here.** Read it from the Actions tab.

---

## Setup

Python 3.11. Install from the lock, not from `pyproject.toml` alone, because the lock is the
environment results were produced in, and TC-099 fails if the installed environment drifts from
it:

```bash
git clone https://github.com/Anurag-YadavIIH/retinal-oct-fluid-segmentation.git
cd retinal-oct-fluid-segmentation
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.lock
pip install -e ".[dev]" --no-deps
```

**The CUDA build of PyTorch cannot be expressed in the lock.** Training used
`torch==2.3.1+cu121`, which is not on PyPI, so it is installed explicitly:

```bash
pip install --index-url https://download.pytorch.org/whl/cu121 \
    --force-reinstall --no-deps "torch==2.3.1"
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"   # 2.3.1+cu121 True
```

**Machine-specific settings** are environment variables, never committed:
`OCUVAL_CACHE_DIR` (frame cache location) and `OCUVAL_DEID_SALT` (see
[`docs/06`](docs/06_data_management_plan.md) §5.1). **The dataset is not downloaded
automatically.** RETOUCH requires registration; `scripts/00_fetch_data.py` documents the manual
steps.

Tests, as CI runs them:

```bash
ruff check src tests scripts && ruff format --check src tests scripts
pytest -m "not requires_data and not requires_pacs"
```

### Pipeline

```bash
python scripts/01_convert_to_dicom.py --config configs/data.yaml
OCUVAL_DEID_SALT=... python scripts/02_deidentify.py --config configs/data.yaml
python scripts/03_make_splits.py --config configs/folds
python scripts/04_train.py --fold configs/folds/cirrus_holdout.yaml --run-dir artifacts/runs/<run> --epochs 150
python scripts/05_evaluate.py --run artifacts/runs/<run> --bucket val
```

`test` and `in_domain_ref` are sealed. `05_evaluate.py` refuses them unless given
`--unlock-bucket` with a reason and an approver, and records every access. Long runs are
launched from an interactive terminal that is kept open
([`docs/07`](docs/07_vv_protocol.md) §17.8). DICOM objects produced here must stay on a local
PACS: the UID root is unregistered, by declaration ([`docs/06`](docs/06_data_management_plan.md)
§7.2).

---

## Repository map

| Path | Contents |
|---|---|
| [`docs/`](docs/) | The document set, `01` intended use to `13` change-control log |
| `src/ocuval/io/` | RETOUCH and MetaImage reading, DICOM writing, de-identification, DICOMweb client |
| `src/ocuval/data/` | Patient-level splits, MONAI transforms, datamodule and frame cache |
| `src/ocuval/models/` | Segmentation network, MC-dropout uncertainty |
| `src/ocuval/training/` | Training loop, deterministic loss, checkpoints, accelerator telemetry |
| `src/ocuval/eval/` | Metrics (numpy/scipy, cross-checked against MONAI), patient-level bootstrap, sealed splits, evaluation pipeline |
| `src/ocuval/report/` | DICOM Segmentation and Structured Report objects |
| `src/ocuval/service/` | FastAPI inference service (stub) |
| `scripts/` | Numbered pipeline entry points `00`–`06`, the evaluation chain, the exact record comparison |
| `configs/` | Data, training, and per-fold configuration |
| `tests/` | pytest suite; each test name carries its `TC-nnn` identifier |

---

## How this was built

The author, **Anurag Yadav** (M.Tech Ophthalmic Engineering, IIT Hyderabad), set the question,
the protocol and every decision recorded in `docs/`. Much of the code and documentation was
written with **Claude Code** (Anthropic), working under a written agreement in
[`CLAUDE.md`](CLAUDE.md):

- requirements before code;
- every statement about code cites the file and line it was read from;
- every number says whether it was measured or derived;
- long runs are launched by the author, never by the assistant.

Mistakes on both sides are recorded rather than removed: the deviations D1–D9 in `docs/08`, and
the retractions and corrections in `docs/13`. Commits carry a `Co-Authored-By: Claude` trailer
from 2026-09-30 onward. Before that, a project rule that has since been reversed kept trailers
out, so the trailers **understate** the assistant's share (`docs/13`, 2026-10-01). Training and
every sealed evaluation ran locally on one GTX 1050, and the data never left the workstation.

---

## Licence

MIT for the code. The RETOUCH dataset carries its own terms, and no data is redistributed here.
