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
- **Every number in a report states whether it was measured or derived, and from what.**
  A projection and a measurement are the same shape — a number with units — so nothing
  distinguishes them unless the text does. On 2026-09-30 a benchmark *projection* was
  reported as an observed throughput and two false claims followed from it, one of which
  nearly became the top blocker for Stage 2 (`docs/13`). Write "measured, 25 telemetry
  samples" or "derived from the 150-epoch budget at 30 img/s", never a bare figure.
- **Any statement about what code does cites the file and line it was read from.**
  Three errors in one session came from describing code from memory rather than opening
  it. `datamodule.py:472`, `torch sampler.py:167`. If it was not read this session, it is
  a guess, and it is labelled one.
- **A flaky test is a test asserting something that is not always true** (`docs/07` §3
  rule 9). Do not rerun it until green — that is the evidence such a test is best at
  producing. Run it 20 times, report the count, then fix the assertion.
- **Long runs — training sessions and sealed evaluations — are launched by the author from
  an interactive terminal kept open: a standalone PowerShell window, or the VS Code
  integrated terminal, in which case VS Code must stay open for the whole run** (`docs/07`
  §17.8, corrected 2026-10-03). Never as a tool call a time limit can kill, and not by
  Claude Code. Two failures produced this rule. On 2026-10-01 a harness time limit killed
  the first sealed `test` access after 10 of 24 volumes, costing an unlock (`docs/08` D5,
  D6). On 2026-10-03 Claude Code launched spectralis night 1 through `Win32_Process.Create`
  and **called it detached**; it was parented by a WMI provider host and died within the
  hour when that host was torn down, along with the watcher launched the same way
  (`docs/08` D8).
- **A launch method may only be called detached after verifying, from the process tree,
  what the process depends on.** "No longer depends on VS Code" was checked; "depends on
  nothing" was assumed, and that assumption was the defect. Record the parent chain of
  every unattended run.
- **Never give a remaining-time estimate without first confirming the process is alive.**
  On 2026-10-03 "6.7 more hours" was computed from `epochs.jsonl` a minute after the run
  had died. The epoch log describes what a run did, not whether it is still doing it.
- **Training runs locally on this workstation's GTX 1050, in-session when asked.** The
  dataset never leaves this machine (`docs/06` §7.1); the Kaggle path stays documented
  and marked not used. Claude Code's job is also the pipeline, the tests, the DICOM
  layer, the service, and the documents.
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
5. ~~Training locally; evaluation and subgroup reporting.~~ **`cirrus_holdout` trained and
   evaluated end to end, 2026-10-01.** The fold completed by **early stopping at epoch 58**
   of 150 in one 3.75 h session, best epoch 33 (`docs/08` §5c). The one-time evaluation of
   the held-out vendor and the in-domain reference is **done and recorded** (`docs/08` §5d):
   **no per-class Dice difference is established at 95%**, five of six intervals overlapping.
   `models/uncertainty.py`, `eval/subgroup.py`, `eval/pipeline.py` and `eval/sealed.py` are
   implemented. **`eval/report.py` is still a stub** — `docs/10` is not written.
6. SEG/SR output and Orthanc round-trip. **Objects done; round-trip blocked on Docker.**
7. FastAPI service, Docker, full document set, GitHub Pages. **Not started.**

### What is actually blocked, and on what

| Blocked on | What it blocks |
|---|---|
| ~~RETOUCH download~~ | **Unblocked 2026-09-21.** Training partition only; the test partition was deliberately not taken (`docs/06` §2.1) |
| ~~Kaggle quota / a Kaggle session~~ | **Void since 2026-09-25.** Training runs locally; the Kaggle path stays documented and marked not used. The old budget figures in this file's "Measured on this workstation" note are superseded by the AMP reversal |
| **Docker not installed** | TC-080, TC-081, TC-082 — written and **never executed**. The Orthanc round-trip is unverified |
| ~~An author decision~~ | **Decided 2026-10-03: approved.** One more unlock on each sealed cirrus bucket under §17.7b, with `docs/08` D7 as the defect. The code is done (`6295bd0`, SRS-089, TC-126); the re-run itself waits for a gap between spectralis sessions — see "Next session" below |
| **The GPU being free** | The cirrus sealed re-run. **Never concurrently with training** — it would compete for a 4 GiB card the trainer peaks near 2.9 GiB on |
| **Neither** — these are simply next | Stage 3 (`spectralis_holdout`, then `topcon_holdout`), `eval/report.py`, `docs/10`, `service/api.py` |

### Numbers, measured 2026-10-01

Identifiers: URS-001..011, **SRS-001..088**, NFR-001..008, HAZ-001..015, RC-001..031,
SOUP-001..022, TC-000..TC-125 (**111 registered**).

**111 test cases registered, 87 written, 84 executed, 3 written but never run, 24
registered and unwritten.** Those states are kept separate deliberately. A written test
nobody has executed is not verification. The three are TC-080..082, blocked on Docker.

**These figures are now recomputed by TC-104, not maintained by hand.** It parses what
`docs/09` claims, recomputes it from `docs/02`, `docs/07` §6 and the `test_TC_nnn_` function
names, and fails when the two disagree **in either direction**. It was written 2026-10-01
after being registered and left unwritten long enough that the drift it was meant to prevent
happened twice on the same artefact; on its first run it caught `docs/09` claiming 66 SRS
against 88, plus two bugs of its own (`docs/13`, 2026-10-01). Do not recount by hand — run
the test.

Suite, measured locally 2026-10-01: **558 passing, 0 failed, 42 deselected**
(`requires_pacs` and `slow`). Risk controls: 31 allocated a test.

**CI state is not asserted here.** The previous version of this line read "CI is green on
`main`" and was **false**: the two most recent runs before 2026-10-01 both failed on TC-099,
because `requirements.lock` was generated on Windows and omitted `uvloop`, which Linux
installs (`docs/13`, 2026-10-01). A claim about CI that nothing recomputes goes stale exactly
as the coverage counts did. **Read it from `gh run list`**, never from this file.

### Stage plan for training (agreed 2026-09-25)

| Stage | Content | State |
|---|---|---|
| **0** | CUDA torch 2.3.1 (cu121, `sm_61` verified), AMP on/off benchmark, gradient accumulation with the norm-layer check, benchmark including the real loader | **done** |
| **1** | Smoke run, `cirrus_holdout`, ~20 epochs. **Criteria pre-registered in `docs/07` §15 and committed 2026-09-26, before any run** | **done** — PASS on all four criteria (`docs/08` §5) |
| **1b** | Re-run under the final configuration after the AMP reversal and the loss adoption. **Criteria pre-registered in `docs/07` §15.6 before the run** | **done** — PASS on all five, resume crossed the warmup boundary (`docs/08` §5b) |
| **2** | `cirrus_holdout` trained fully **and evaluated end to end** before any other fold begins | **done 2026-10-01.** Early stop at epoch 58, best epoch 33; one-time evaluation of `test` and `in_domain_ref` complete (`docs/08` §5c, §5d) |
| **3** | `spectralis_holdout`, then `topcon_holdout` | **In progress.** `spectralis_holdout` night 1, session 1: launched 2026-10-03 19:56 local by Claude Code through WMI from `5f66359`, **terminated externally after epoch 9** when its WMI provider host was torn down (`docs/08` D8); checkpoints verified intact. Session 2: resumed by the author at 21:03 from the VS Code integrated terminal, from `7be924f`, `--max-epochs-this-session 70`; training path unchanged between the two commits. Run dir `artifacts/runs/spectralis_holdout_stage3`. **342.5 s/epoch measured** over session 1's 10 epochs. Secondary analyses pre-registered in `docs/07` §19 before it trained. **topcon not started** |
| **4** | Uncertainty, subgroup analysis, `docs/10` | `eval/` is implemented; **`eval/report.py` is still a stub and `docs/10` is unwritten** |

### Next session — the plan, written 2026-10-03 while spectralis night 1 trained

**First, read how night 1 ended.** `artifacts/monitor/stage3_night1.md` holds the status
lines and a final summary written by the detached watcher — epochs completed, `stopped_by`,
trajectory, best epoch, patience, peak temperature, any action taken. Confirm against
`artifacts/runs/spectralis_holdout_stage3/epochs.jsonl` before acting on it.

**1. Spectralis session 2 — only if night 1 hit the 80-epoch limit.** If `stopped_by` is
`session_epoch_limit`, session 2 is **the same command without `--max-epochs-this-session`**,
launched the next night, detached (§17.8). If `stopped_by` is `early_stopping`, the fold is
complete and there is no session 2. Anything else is an anomaly to investigate, not a session
to relaunch.

```powershell
.venv\Scripts\python.exe scripts\04_train.py --fold configs\folds\spectralis_holdout.yaml `
  --run-dir artifacts\runs\spectralis_holdout_stage3 --epochs 150
```

Same `--run-dir`, so it resumes. It will record a newer commit than night 1's `5f66359`; the
`docs/13` entry of 2026-10-03 shows no training-path file changed between them, so the two
sessions run the same training code. Re-check that before launching if anything has been
committed since `6295bd0`.

**2. The cirrus sealed re-run — between sessions, in daytime, never concurrently with
training.** Confirm no training process is alive and the GPU is idle first. Then re-run both
sealed cirrus buckets from a **detached** process, reasons naming **D7** and **§17.7b**:

- **Write to new files, not over the originals.** `scripts/05_evaluate.py` defaults to
  `evaluation_{bucket}.json` in the run directory, which would overwrite the `767c8e5` records
  the re-run is being compared against. Pass `--output` to a new path for both buckets.
- **Every aggregate must reproduce the `767c8e5` results exactly** — every per-class,
  per-vendor and pooled Dice, HD95, sensitivity, specificity and AUROC, value and interval.
  TC-121 and TC-123 establish determinism and the evaluation path has changed only by adding
  rows. **If any figure differs, stop and report before doing anything else**, including the
  decomposition. A difference would mean the determinism claim does not cover evaluation.
- **If all reproduce**, produce §19.1's present/absent decomposition for both arms from the
  new `per_volume` rows — **labelled post-hoc everywhere**, never replacing a pre-registered
  figure — with n per stratum and the share of the low mean Dice attributable to
  false-positive predictions in class-absent volumes.
- **Record in `docs/08`** that the decomposition came from a deterministic re-run made after
  the Stage 3 analysis plan was already committed in **`cae1f36`**.

Two things to carry into the decomposition. A class absent from the reference scores Dice
**0.0** for even one predicted voxel and **1.0** only when nothing is predicted
(`metrics.py:104-117`), while detection calls a class present only above **10** voxels — so
the two can disagree on volumes with 1–10 predicted voxels, and that is expected rather than a
defect. And the access log will show one more run per bucket; with `run_id` now recorded,
each counts once.

**Owed before Stage 1 — all delivered 2026-09-26** (SRS-080..083, TC-079, TC-095):
`--max-epochs-this-session`; a `STOP` file that ends the session after the current epoch
is complete and checkpointed; the checkpoint now carries the **complete early-stopping
state** (best metric, best epoch, epochs since improvement) alongside scheduler, scaler
and all RNG states, with TC-059 extended across a warmup boundary and mid-patience; one
continuous appended `epochs.jsonl` per fold with session boundaries; and accelerator
telemetry every 30 s for the whole run.

**`optim.warmup_epochs` was configured and read by no code until 2026-09-26.** Every run
would have started at the full learning rate while its recorded configuration said
otherwise. Now implemented with `SequentialLR`, whose `state_dict` carries the position
in the sequence.

**Stage 1 criteria are pre-registered and committed** (`docs/07` §15, TC-096). The
trivial baseline is a measured number, not an intention: a spatial prior ignoring the
image scores **IRF 0.0451, SRF 0.0428, PED 0.0384** on in-domain validation. A failed
criterion stops Stage 2 and does not get rewritten.

**Measured on this workstation (GTX 1050, 2026-09-25), micro-batch 8, AMP off:**
25.6 img/s through the real cached loader, 1.29 GiB peak of 4 GiB. Per 8-hour night:
**cirrus 263 epochs, topcon 223, spectralis 170.** Three folds at 150 epochs is ~17 h.

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
- **Splits are keyed on the source subject (`TRAIN001`..`TRAIN070`), never the SOP
  Instance UID.** UIDs are minted per conversion, so a split keyed on one is a different
  file every re-conversion (SRS-023). UIDs stay random — a re-conversion is a new
  instance, and deterministic UIDs would make separate objects share an identity.
- **Training reads `train.batch_size` and nowhere else.** A second `data.batch_size` was
  added and removed the same day; two places to state one value is how a run reports a
  batch size it did not use.
- **Resume equivalence is claimed per platform**: bit-identical on CPU (SRS-076),
  within a stated tolerance on GPU, because several CUDA kernels here have no
  deterministic implementation. Never claim bit-exactness on GPU.
- **Resume is detected from the run directory, never requested by a flag**, and `last`
  is written every epoch, unconditionally — including the epoch that triggers early
  stopping. `best` selects a model; `last` continues a trajectory. **Corrected
  2026-09-30:** this previously read "before any early-stopping decision", which is what
  the code did and was the defect. `last` is written *after* the best-check, so the
  early-stopping state it carries belongs to its own epoch. Written before, it recorded
  the *previous* epoch's best, and a resumed run could overwrite `best.pt` with a worse
  model. Unconditional and current are both required; they are not in tension.
- **Per-epoch randomness is derived, never saved and restored** (SRS-076). Sample order
  and augmentation are seeded from `(seed, epoch, stream)` at the top of every epoch, so
  a resume reproduces them by construction with nothing to restore. The reason is not
  elegance: a save-and-restore guarantee is bounded by the inventory of generators
  someone remembered, and that inventory is unbounded — **every MONAI `Randomizable`
  holds its own `np.random.RandomState` (monai `transform.py:186`) that no checkpoint can
  see**, which is how the augmentation stream stayed broken after the sampler was fixed.
  Do not answer a future divergence by saving more state.
- **`persistent_workers` is not used**, and the throughput cost is accepted. Persistent
  workers draw `_base_seed` once per process (torch `dataloader.py:602`, not redrawn by
  `_reset` at `:610`, and `__iter__` reuses the live iterator at `:433-437`), so their
  augmentation would again depend on how many epochs the process had run. No
  `worker_init_fn` is added either: torch already seeds `random`, `torch` and `numpy` per
  worker from `_base_seed` (`worker.py:223-229`).
- **Training runs locally; the dataset never leaves this workstation** (`docs/06` §7.1).
  A private Kaggle dataset is still third-party storage: private controls who can read
  it, not where it is held, and the Agreement speaks to custody. DMP-C1 applied. The
  Kaggle path stays documented and marked not used.
- **AMP IS used on this GPU** (reversed 2026-09-30). The 2026-09-26 decision to disable it
  was **wrong, not merely outdated**: the benchmark that produced it never called
  `request_determinism`, so it priced kernels no run selects — a correct measurement of a
  configuration that does not exist. Measured under determinism: **AMP off 9.2 img/s at
  2.30 GiB peak, AMP on 17.1 img/s at 1.00 GiB.** Without determinism the two are within
  3%, which is what the original measurement saw. Three folds at 150 epochs: 37.4 h with
  AMP against 57.7 h without (derived from those rates plus 39 s/epoch measured overhead).
  *Why* fp16 wins on a card with no tensor cores is an **unmeasured hypothesis** —
  probably the deterministic fp32 conv-backward kernels being far slower than the fp16
  ones. Kernel selection has not been profiled; the decision rests on the throughput
  number, not on the explanation.
- **The training loss is `dice_ce_deterministic`** (SRS-084). MONAI's `DiceCELoss` reaches
  `nll_loss2d_forward_out_cuda_template`, the one operation on this network with no
  deterministic CUDA kernel, so under `warn_only=True` torch used the non-deterministic one
  and warned 1308 times in Stage 1. Measured cost of the substitution: −8.1% throughput at
  AMP on, for **zero** fallbacks. The Dice term stays MONAI's, untouched.
- **Zero fallbacks is not determinism.** It means no operation *announced*
  non-determinism; it is not the claim that two runs agree, and an operation that never
  warns can still be order-dependent. Never infer the second claim from the first.
- **Rule 4's strongest evidence on GPU is TC-123, not TC-121** (measured 2026-10-01).
  `cirrus_holdout_stage1b` (`--epochs 20`, two sessions, **resumed at epoch 3**, cosine
  `T_max` 15) and `cirrus_holdout_stage2` (`--epochs 150`, one session, `T_max` 145),
  launched nine hours apart, agree to **every recorded digit** on `train_loss`, `val_dice`
  and `per_class_dice` for **epochs 0–5**, with epochs 0–2 mean loss 1.648121 in both.
  Nothing was arranged to make them comparable. Stage 1b's epochs 3–5 came from a process
  that rebuilt sample order and augmentation from `(seed, epoch)` with nothing restored;
  Stage 2's from a process that never stopped. **Agreement runs to epoch 5, not 4**: the
  `lr` logged at epoch N is the rate epoch N+1 uses (`scheduler.step()` at `loop.py:353`,
  the log at `:399`), so epoch 5 trained under the shared warmup endpoint and epoch 6 is
  the first to differ. TC-123 asserts the divergence at 6 as well as the agreement through
  5 — identical runs throughout would mean the cosine horizon was ignored and SRS-083 was
  broken.
- **Rule 4 IS achieved on GPU, and TC-121 was its first evidence** (measured
  2026-09-30). Two runs of `cirrus_holdout` under the committed configuration produced
  **byte-identical** model weights, optimiser state and epoch logs — `train_loss 2.264524`
  then `1.236142`, `val_dice 0.021399` then `0.153961`, per-class Dice identical — with
  zero recorded fallbacks. Wall time differed (247.9 s against 234.5 s) and is excluded,
  being the one thing that legitimately varies. **The claim is exactly as wide as the
  test:** this network, this fold, this configuration, two epochs, on a GTX 1050. It is
  not a claim about CUDA, about other networks, or about other cards. If the network, the
  loss or the torch build changes, TC-121 is the thing to re-run, and until it passes again
  rule 4 is unproven rather than assumed.
- **Gradient accumulation is implemented but not needed here** (micro-batch 8 peaks at
  1.00 GiB of 4 under AMP). Its equivalence rests on the network having **instance norm
  and no batch norm**; under batch norm it is invalid and the response is to stop
  accumulating, never to widen the tolerance (`docs/07` §14).
- **`LoadFrame` must remain a `monai.transforms.Transform`, and transform chains must
  stay flat.** `PersistentDataset` caches only up to the first transform that is
  Randomizable *or not a Transform*, and `Compose` is itself Randomizable — so a plain
  callable, or a nested Compose, silently caches nothing at all. TC-039 now inspects the
  stored artefact rather than comparing served values.
- **A test for a mechanism must inspect the mechanism** (`docs/07` §3 rule 8). Four
  instances here shared one shape — the observable output is identical whether the
  mechanism works or is absent: the uninstalled pre-commit hook, the hand-maintained
  coverage figures, the frame cache that stored no pixels while TC-039 passed, and
  `optim.warmup_epochs` that no code read. Assert against the artefact, and assert the
  mechanism can fail.
- **Pre-registered criteria are not edited after seeing results.** `docs/07` §15 was
  committed before any run. A failure stops the next stage and goes in `docs/13`;
  concluding a criterion was wrong is a recorded argument, never a quiet edit.
- **Attribution trailers are allowed, and history is not rewritten to remove them**
  (reversed 2026-10-01). The earlier decision — no Claude Code attribution in any commit —
  contradicted the stronger one this project applies everywhere else: **the record states
  what happened.** `docs/08` keeps Stage 1's `determinism.json` unedited with its 1308
  fallbacks; TC-109 scopes its invariant to records written after SRS-085 rather than
  rewriting earlier ones; `docs/13` carries retracted claims as findings rather than
  deletions. Requiring the trailers to be absent required history to say something other
  than what happened, and enforcing it meant rewriting history — which on 2026-09-23 broke
  nine cited SHAs and is why **TC-108** exists. TC-088's trailer check is deleted, not
  skipped. `4737b05` keeps its trailer. **TC-108 stays**, and is the control that actually
  matters here: every SHA cited in `docs/` and `scripts/` must resolve. Do not rewrite
  history to tidy trailers.

Update this section at the end of each working session.
