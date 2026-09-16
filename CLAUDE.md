# CLAUDE.md — OcuVal

Project context for Claude Code. Read this before touching anything in this repo.

---

## 1. What this project is

**OcuVal** is a DICOM-native retinal OCT fluid segmentation pipeline, validated across
scanner vendors and documented as if it were regulated medical device software.

It is a **portfolio project**, not a deployed device. It is never used on real patients
and makes no clinical claims. But every artefact in it must be written as though it
would be reviewed — because the point of the project is to demonstrate that the author
can work inside a medical device software lifecycle, not just train a model.

**The headline result** is cross-vendor generalisation: train on two OCT vendors,
report performance on the held-out third. Quantifying the degradation *is* the
contribution. A high in-domain Dice score with no vendor breakdown is a failed project.

**Author:** Anurag Yadav — M.Tech Ophthalmic Engineering, IIT Hyderabad.

---

## 2. Non-negotiable rules

These are ordered by how badly violating them damages the project.

1. **Requirements before code.** Every module in `src/` must trace to a numbered
   requirement in `docs/02_software_requirements_spec.md`. If you are asked to write
   code that has no requirement, write the requirement first and say so.

2. **Patient-level splits only.** No patient, volume, or B-scan may appear in more than
   one split. `tests/test_splits_no_leakage.py` enforces this and gates CI. Never weaken,
   skip, or `xfail` that test. If it fails, the data pipeline is wrong — fix the pipeline.

3. **No real PHI, ever.** All data is public research data. De-identification is
   implemented and tested anyway, because demonstrating the control is the point.
   Never commit anything under `data/` or `artifacts/`.

4. **Determinism.** Every split, every training run, every bootstrap resample is seeded
   and the seed is recorded in the run config. Results must be reproducible from the
   committed config alone.

5. **The traceability matrix stays current.** Any change to a requirement, hazard, or
   test means `docs/09_traceability_matrix.md` is updated in the same commit. A stale
   matrix is worse than no matrix.

6. **No silent metric changes.** If an evaluation definition changes, it goes in
   `docs/13_change_control_log.md` with a date and rationale.

---

## 3. Identifier conventions

Used throughout `docs/` and referenced in code docstrings and test names.

| Prefix | Meaning | Lives in |
|---|---|---|
| `URS-nnn` | User requirement | `01_intended_use.md` |
| `SRS-nnn` | Software requirement | `02_software_requirements_spec.md` |
| `HAZ-nnn` | Identified hazard | `05_risk_management_file.md` |
| `RC-nnn`  | Risk control measure | `05_risk_management_file.md` |
| `TC-nnn`  | Test case | `07_vv_protocol.md` |
| `SOUP-nnn`| Third-party component | `04_soup_list.md` |

Every risk control must trace to at least one software requirement, and every software
requirement to at least one test case. Test functions carry the ID in the name:
`def test_TC_012_deident_removes_patient_name():`

---

## 4. Technical decisions (already made — do not relitigate)

- **Python 3.11**, dependencies managed in `pyproject.toml`. Pin exact versions;
  every pinned version also appears in the SOUP list.
- **MONAI** for transforms, datasets, networks, and metrics. Not raw torchvision.
- **2D / 2.5D segmentation.** Full 3D UNet is explicitly out of scope — the dataset is
  small and the vendor-shift question does not need it.
- **pydicom** for reading and de-identification; **highdicom** for writing SEG and SR
  objects. Do not hand-roll DICOM encoding.
- **Orthanc** in Docker as the local PACS, spoken to over DICOMweb (STOW-RS / WADO-RS).
- **FastAPI** for the inference service. No web UI — this is an API and a document set.
- **pytest** for everything. `pytest-cov` reported in CI.
- Data lives under `data/`, run outputs under `artifacts/`. Both gitignored.

### Fluid classes
Three, per the RETOUCH challenge definition:
`IRF` (intraretinal fluid), `SRF` (subretinal fluid), `PED` (pigment epithelial detachment).
Label indices are fixed in `configs/data.yaml` and must never be reordered.

### Vendors
`cirrus`, `spectralis`, `topcon`. Vendor is a first-class field on every sample and must
survive the whole pipeline into the evaluation output — subgroup reporting depends on it.

---

## 5. Metrics — what counts as a result

Segmentation: **Dice** and **HD95**, per fluid class, reported separately.
Classification arm: **sensitivity, specificity, AUROC**.

Every metric is reported with a **bootstrap 95% confidence interval** and broken down
**per vendor**. A bare point estimate is not an acceptable result anywhere in this repo —
not in a notebook, not in a README, not in a commit message.

Accuracy alone is never reported. The classes are imbalanced and it is misleading.

---

## 6. Working agreement

- **Explain before generating.** The author is deliberately strengthening fundamentals in
  classical ML, computer vision, and MLOps. When introducing an unfamiliar pattern
  (MONAI transform composition, MC-dropout, DICOM IOD structure, CI caching), explain
  what it does and why this approach over the alternatives — then write the code.
  Do not produce large blocks of unexplained scaffolding.
- **Small commits, one concern each.** Conventional commit style.
- **Do not train models in-session.** Training runs on Kaggle. Claude Code's job is the
  pipeline, the tests, the DICOM layer, the service, and the documents.
- **Do not download datasets.** `scripts/00_fetch_data.py` documents the manual steps;
  RETOUCH requires registration and is fetched by hand.
- **Ask before adding a dependency.** Every new package means a SOUP entry and a
  justification. Prefer the standard library.
- **When uncertain about a DICOM detail, say so** rather than inventing a tag or UID.
  Incorrect DICOM that looks plausible is the most expensive failure mode in this repo.

---

## 7. Current status

**Phase: 0 — scaffolding.**

Next milestones, in order:
1. ~~Repo skeleton, tooling, CI green on an empty test suite.~~ **done** — 2026-09-16.
   Package imports, ruff clean, 5 passed / 1 xfailed (the leakage gate placeholder).
2. `docs/01`, `docs/02`, `docs/03` drafted — intended use, SRS, safety classification.
3. RETOUCH reader + DICOM conversion + de-identification, with tests.
4. Splits and leakage gate.
5. Training on Kaggle; evaluation and subgroup reporting local.
6. SEG/SR output and Orthanc round-trip.
7. FastAPI service, Docker, full document set, GitHub Pages.

Update this section at the end of each working session.
