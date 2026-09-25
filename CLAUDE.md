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
- **MONAI** for transforms, datasets, networks, and losses. Not raw torchvision.
  **Metrics are the exception and are numpy/scipy** (`src/ocuval/eval/metrics.py`):
  `docs/10`'s credibility rests on the metrics being independently computable, and pure
  array functions are verifiable without a torch runtime. MONAI's implementations are
  used as an independent cross-check, not as the source — see the back-to-back test.
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

Detection: **sensitivity, specificity, AUROC**, per fluid class. This is *derived from
the segmentation output* — a class counts as present when its predicted voxel count
exceeds a configured threshold, and the AUROC score comes from the MC-dropout mean
probability. It is a second view of one model, not a second model: there is no separate
classifier and no second training run. See `docs/02` SRS-050..SRS-053.

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

**Phase: 1 — pipeline and DICOM layer. No results yet, and none are possible until the
dataset arrives.**

### Milestones

1. ~~Repo skeleton, tooling, CI green.~~ **done** — 2026-09-16. That first run pre-dated
   version control; `git init` and the initial commit followed the same day and the
   result was re-confirmed from inside the repo.
2. ~~`docs/01`, `docs/02`, `docs/03`.~~ **done** — 2026-09-17, plus `docs/04` (SOUP and
   anomaly review), `docs/05` (risk file), `docs/06` (data plan) and `docs/07` (V&V
   protocol). **The document set is paused here by decision**, not oversight: `docs/08`,
   `docs/10`, `docs/11` and `docs/12` report on execution, results, DICOM output and a
   model. `docs/11` is partially populated where decisions have actually been taken.
3. ~~RETOUCH reader + DICOM conversion + de-identification.~~ **done** — 2026-09-23.
   Run end to end on the real training partition: 70 volumes converted, de-identified
   and verified, three folds written. Per-vendor spacing ranges measured and enforced
   2026-09-25, closing `docs/07` item 6.
4. ~~Splits and leakage gate.~~ **done** — 2026-09-17. TC-004 passes for real; its
   `strict` xfail was removed when `splits.py` landed.
5. Training on Kaggle; evaluation and subgroup reporting. **Preprocessing done
   2026-09-25** — `data/transforms.py` and `data/datamodule.py` are implemented and
   verified against the real archive (4032 train / 896 val / 1176 test frames on the
   spectralis fold). `models/`, the training loop and `eval/subgroup.py` remain.
6. SEG/SR output and Orthanc round-trip. **Objects done; round-trip blocked on Docker.**
7. FastAPI service, Docker, full document set, GitHub Pages. **Not started.**

### What is actually blocked, and on what

| Blocked on | What it blocks |
|---|---|
| ~~RETOUCH download~~ | **Unblocked 2026-09-21.** Training partition only; the test partition was deliberately not taken (`docs/06` §2.1) |
| **Docker not installed** | TC-080, TC-081, TC-082 — written and **never executed**. The Orthanc round-trip is unverified |
| **Kaggle quota** (30 h/week) | The three primary folds. The optional dtype-scaling comparison fold (`docs/10` §8.1) runs only if they finish comfortably, and never before them |
| **Neither** — these are simply next | `models/`, the training loop, `eval/subgroup.py`, `eval/report.py`, `service/api.py`, and wiring `scripts/01`–`03` (still stubs; the real run went through an ad-hoc driver) |

### Numbers, as of 2026-09-25

Identifiers: URS-001..011, SRS-001..074, NFR-001..008, HAZ-001..015, RC-001..031,
SOUP-001..022, TC-000..TC-120 (92 allocated).

**92 test cases allocated, 57 written, 54 executed, 3 written but never run.** Those
three states are kept separate deliberately and `docs/09` regenerates them from the
documents and from pytest's own marker resolution — a hand-maintained figure drifted in
both directions at once and was replaced. A written test nobody has executed is not
verification. The three are TC-080..082, blocked on Docker.

Suite: **318 passing, 8 deselected** (`requires_pacs`). Risk controls: 31 allocated a
test.

### Standing decisions a future session should not relitigate

- **Refuse, or omit — never fill** (RC-029). Acquisition context RETOUCH does not record
  is caller-supplied or omitted, never substituted. A detectable non-conformance is safer
  than an undetectable fabrication.
- **Fluid classes use a declared private coding scheme** `99OCUVAL`, identified in the
  object. No verified standard code exists for IRF, SRF or PED; a borrowed code would look
  interoperable and mean something different to every reader (`docs/11` §10 item 5).
- **The UID root stays an unregistered placeholder**, declared. Objects must not leave the
  local Orthanc instance.
- **HD95 is max-of-directed**, not pooled — found by the MONAI cross-check, TC-120.
- **URS-011's research-use designation mechanism is still open.** Do not resolve it by
  picking a mechanism; it is a `docs/11` decision.
- **A fixture written in the consuming code's convention cannot test a conversion**
  (`docs/07` §3 rule 7). Found via the MetaImage spacing axis order, which no synthetic
  fixture exercised because every fixture was already in the project's own order.
- **Per-vendor spacing ranges are the only control that sees an axis transposition.**
  The 0.5 mm physical bound catches 0 of 210 such cases; the per-vendor range catches
  all of them (`docs/07` §13.3). Do not weaken the ranges to the physical bound alone.
- **Intensity normalisation is a per-volume percentile window computed at ingestion**,
  never dtype scaling and never recomputed in a transform. Topcon carries a p1 = 35/255
  detector pedestal perfectly correlated with vendor; dtype scaling preserves it. The
  consequence is stated in `docs/10` §8.1: **the measured cross-vendor gap is a lower
  bound** on the raw-data gap.
- **Axial resampling targets the coarsest common spacing (0.004 mm, declared in
  `configs/train_seg.yaml`).** Never derived from the data — that would make
  preprocessing depend on fold membership. Never upsample: fabricated detail would
  substitute a smoothness signature for the brightness one the windowing removes.
- **B-scan separation is not used by the transform chain** (SRS-073). Training is 2D and
  frames are independent. Enabling 2.5D is a separate, visible decision.
- **Training reads the archive's native MetaImage, not the DICOM.** The instances this
  pipeline writes carry no segmentation; DICOM is the output interface, not the input.
- **Commits carry no Claude Code attribution.** History was rewritten 2026-09-23 to
  strip the trailers and force-pushed; content was unchanged and all 51 tree hashes were
  verified identical. Cited SHAs are checked by TC-108 because that rewrite broke nine
  of them.

Update this section at the end of each working session.
