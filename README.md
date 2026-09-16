# OcuVal

**Does a retinal OCT fluid segmentation model trained on one scanner still work on another?**

OcuVal trains a fluid segmentation model on retinal OCT volumes from two scanner vendors
and reports its performance on a held-out third vendor. The size of that gap — not the
in-domain score — is the result. Every metric in this repository is reported per fluid
class, per vendor, with bootstrap confidence intervals.

The pipeline is DICOM-native end to end: volumes are converted to conformant Ophthalmic
Tomography Image objects, de-identified under the DICOM PS3.15 Basic Application
Confidentiality Profile, and results are written back as DICOM Segmentation and
Structured Report objects and pushed to a local PACS over DICOMweb.

The software is developed and documented against **IEC 62304** and **ISO 14971** —
intended use statement, numbered requirements, hazard analysis, verification protocol,
and a requirement-to-test traceability matrix — all under [`docs/`](docs/).

> **Not for clinical use.** This is a research and portfolio artefact built on public
> challenge data. It has not been validated for patient care and makes no clinical claims.

---

## Status

**Phase 0 — scaffolding.** No results yet. See `CLAUDE.md` for the milestone order.

| Component | State |
|---|---|
| Repo, tooling, CI | scaffolded |
| Intended use / SRS / safety classification | not started |
| RETOUCH reader + DICOM conversion | not started |
| De-identification | not started |
| Patient-level splits + leakage gate | not started |
| Training (Kaggle) | not started |
| Evaluation + subgroup reporting | not started |
| SEG / SR output + PACS round-trip | not started |
| Inference API + Docker | not started |

---

## Data

[RETOUCH](https://retouch.grand-challenge.org/) — retinal OCT fluid detection challenge.
Three fluid classes (IRF, SRF, PED) across three scanner vendors (Cirrus, Spectralis,
Topcon), which is what makes the cross-vendor question askable.

The dataset requires registration and is **not** downloaded automatically. See
`scripts/00_fetch_data.py` for the manual steps and the expected layout under `data/`.

---

## Setup

```bash
git clone https://github.com/Anurag-YadavIIH/ocuval.git
cd ocuval
python3.11 -m venv .venv && source .venv/bin/activate
make install
make test-fast
```

Local PACS (requires Docker):

```bash
make pacs-up      # Orthanc at http://localhost:8042, DICOMweb at /dicom-web
make pacs-down
```

---

## Repository map

| Path | Contents |
|---|---|
| `docs/` | Regulated-software document set — intended use, SRS, risk file, V&V, traceability |
| `src/ocuval/io/` | RETOUCH reading, DICOM writing, de-identification, DICOMweb client |
| `src/ocuval/data/` | Patient-level splits, MONAI transforms, datamodule |
| `src/ocuval/models/` | Segmentation network, MC-dropout uncertainty, MONAI Bundle export |
| `src/ocuval/eval/` | Metrics with bootstrap CIs, per-vendor subgroup analysis, reporting |
| `src/ocuval/report/` | DICOM SEG and Structured Report construction |
| `src/ocuval/service/` | FastAPI inference service |
| `scripts/` | Numbered pipeline entry points, `00_` through `06_` |
| `configs/` | Data, training, and cross-vendor fold configuration |
| `tests/` | pytest suite; test names carry their `TC-nnn` identifier |

---

## Pipeline

```bash
python scripts/01_convert_to_dicom.py --config configs/data.yaml
python scripts/02_deidentify.py       --config configs/data.yaml
python scripts/03_make_splits.py      --config configs/folds/spectralis_holdout.yaml
python scripts/04_train.py            --config configs/train_seg.yaml   # runs on Kaggle
python scripts/05_evaluate.py         --run artifacts/runs/<run_id>
python scripts/06_push_to_pacs.py     --run artifacts/runs/<run_id>
```

---

## Licence

MIT for the code. The RETOUCH dataset carries its own terms — see the challenge site.
