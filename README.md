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
git clone https://github.com/Anurag-YadavIIH/retinal-oct-fluid-segmentation.git
cd retinal-oct-fluid-segmentation
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.lock   # the exact environment, transitives included
pip install -e ".[dev]" --no-deps  # the package itself, without re-resolving
```

**Install from the lock, not from `pyproject.toml` alone.** `pyproject.toml` pins direct
dependencies only; every transitive dependency floats. That is how this project's CI and
its development workstation came to differ without either changing — CI installed with
dependencies while the local virtual environment had been built with `--no-deps` and was
missing six of fourteen runtime pins (`docs/13`, 2026-09-28). `requirements.lock` is the
environment results were produced in, and `tests/test_environment_lock.py` (TC-099)
fails if the installed environment drifts from it.

`--no-deps` on the editable install is deliberate: the lock has already resolved
everything, and letting pip re-resolve would defeat the point of having a lock.

### The CUDA build of PyTorch

**The lock cannot express it.** Training uses `torch==2.3.1+cu121`, and no such build
exists on PyPI. The lock pins `torch==2.3.1`, which from PyPI resolves to a build that
**satisfies the lock while being unable to train on a GPU**. The build is therefore
recorded separately — in `docs/04` §4.1 and in every training run's `run.json` — and
installed explicitly:

```bash
pip install --index-url https://download.pytorch.org/whl/cu121 \
    --force-reinstall --no-deps "torch==2.3.1"
```

`--force-reinstall --no-deps` is required, not decorative: pip treats an already
installed `2.3.1+cpu` as satisfying `torch==2.3.1` and will otherwise silently leave it
in place. Verify afterwards:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), 'sm_61' in torch.cuda.get_arch_list())"
# 2.3.1+cu121 True True
```

`sm_61` matters on the GTX 1050 this project trains on (compute capability 6.1): a wheel
without that architecture still runs, via PTX JIT, with a different kernel-selection
path — a silent difference between machines that NFR-002 cannot tolerate.

**CI installs the CPU build deliberately**, from the PyTorch CPU index rather than PyPI.
It runs tests, not training, and the runner has no GPU; the PyPI Linux wheel would pull
the CUDA build and eleven `nvidia-*-cu12` packages the lock does not carry. TC-099
treats both `+cu121` and `+cpu` as recorded build variants of the locked `2.3.1` rather
than as mismatches.

### Per-machine paths

Nothing machine-specific belongs in a committed config. The frame cache defaults to a
relative `artifacts/cache`; point it elsewhere with `OCUVAL_CACHE_DIR` or `--cache-dir`,
and the resolved location is written into `run.json`.

```bash
export OCUVAL_CACHE_DIR=/mnt/fast/ocuval_cache   # Windows: set it to a non-system drive
export OCUVAL_DEID_SALT=...                      # never committed; see docs/06 §5.1
```

Local PACS (requires Docker):

```bash
make pacs-up      # Orthanc at http://localhost:8042, DICOMweb at /dicom-web
make pacs-down
```

The `Makefile` is a convenience for Unix-like shells and is not required. Where `make`
is unavailable — a plain Windows shell, for instance — run the recipe bodies directly;
they are ordinary `ruff`, `pytest`, `pip` and `docker compose` calls. CI does not use
`make` either, it invokes those tools itself:

```bash
ruff check src tests scripts          # make lint
ruff format --check src tests scripts
pytest -m "not slow and not requires_data and not requires_pacs"   # make test-fast
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

### DICOM output stays local

The UID root in `configs/data.yaml` is **not registered** to this project or to anyone
else. UIDs generated under it are structurally valid but carry no claim of global
uniqueness, so DICOM objects produced here must not be sent anywhere but the local
Orthanc instance — not to a shared or institutional PACS, and not published as files.
This is a declared limitation rather than an oversight; see `docs/06` §7.2 and
`docs/11` §7. Substituting a different-looking root would be worse, not better.

---

## Licence

MIT for the code. The RETOUCH dataset carries its own terms — see the challenge site.
