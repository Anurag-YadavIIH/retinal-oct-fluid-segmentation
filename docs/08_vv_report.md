<!--
Document: Verification and Validation Report
Status: PARTIAL — Stage 1 execution recorded; suite-level verification not yet drafted
Owner: Anurag Yadav
Last reviewed: 2026-09-30
Change history: docs/13_change_control_log.md
-->

# Verification and Validation Report

> **Status: partial, by intention.** This document reports on *execution*, so it can only
> be written where execution has happened. §5 records the Stage 1 smoke run against the
> criteria pre-registered in `docs/07` §15. §3, §4 and §6 are placeholders: the
> suite-level verification summary, the full TC-by-TC results table and the validation
> conclusion belong to Stage 2 and later, and drafting them now would mean writing
> results that do not exist. `docs/07` is the protocol and is complete; this is the
> report against it and is not.

**Convention used throughout this document.** Every figure states whether it was
**measured** and from what, or **derived** by arithmetic on a measurement. That
distinction is not decoration: on 2026-09-30 a benchmark projection was reported as an
observed throughput and two false claims followed from it (`docs/13`).

---

## 1. Software version under test

| Field | Value | Source |
|---|---|---|
| Repository | `Anurag-YadavIIH/retinal-oct-fluid-segmentation`, branch `main` | — |
| Package version | `0.1.0` | measured, `run.json` `ocuval_version` |
| Commit under test | **not recorded by the run** — see deviation D4 | — |
| Python | 3.11.15 | measured, `run.json` |
| torch | `2.3.1+cu121`, CUDA runtime 12.1 | measured, `run.json` `environment.torch_build` |
| Environment lock | `requirements.lock`, SHA-256 recorded in the run | measured, `run.json` `environment.lock_sha256` |

The lock hash is the stronger half of this table: it pins every dependency version the
run used, and TC-099 checks the installed set against it. The weaker half is that the
run records no commit SHA for the project's own code, which is deviation D4.

---

## 2. Environment

| Field | Value | Source |
|---|---|---|
| Host | Windows 11 Pro, `Windows-10-10.0.26200-SP0` | measured, `run.json` `platform` |
| Accelerator | NVIDIA GeForce GTX 1050, 4 GiB, compute capability 6.1 | measured, `run.json` `environment` |
| Tensor cores | none (Pascal is 6.x; tensor cores arrived with 7.0) | derived from the capability |
| AMP | off | measured, resolved `train.amp: false` |
| Peak GPU memory observed | **3993 MiB of 4096** | measured, 246 `gpu_telemetry.csv` samples |
| GPU temperature range | **44–68 °C** | measured, same samples |
| Telemetry coverage | 246 samples at 30 s, first at 06:46:04 UTC | measured |

**The memory figure is the one to note.** 3993 MiB of 4096 is 97.5% of the card, measured
at the peak — not a comfortable margin, and it is why AMP is being re-measured under
determinism rather than left settled (§5.5). The temperature range shows no thermal
throttling: 68 °C is well inside this card's limit, so no epoch's duration needs a
thermal explanation.

---

## 3. Suite-level verification summary

**Not drafted.** Placeholder for the TC-by-TC results table required by `docs/07` §6.
The current counts live in `docs/09`, which regenerates them from the documents and from
pytest's own marker resolution rather than by hand.

---

## 4. Deviations, anomalies, and dispositions

Numbered `D-nn` and carried forward; each is also recorded in `docs/13` where it changed
a requirement, a test or a decision.

### D1 — The `STOP` request landed at epoch 16, not epoch 3

**What happened.** The Stage 1 run was to be stopped early to exercise the resume path.
`STOP` was written, but the latency between deciding to stop and the file being observed
by the loop spanned thirteen epochs: the session ended after epoch 15 and resumed at
epoch 16, rather than after epoch 2 as intended.

**Disposition: accepted, no code change.** The mechanism behaved exactly as specified —
SRS-080 requires the session to end *after the current epoch is complete and
checkpointed*, and it did. What failed was the operator's control over *which* epoch,
and at ~365 s per epoch a decision made between polls is a decision made thirteen epochs
early or late.

**Corrective action.** `--max-epochs-this-session` is used for every planned stop from
now on, because it is a pre-declared bound rather than a race against a poll. `STOP`
remains for unplanned stops, which is what it is for. Recorded in `docs/13`.

### D2 — TC-059 passed while resume equivalence was broken

**What happened.** The run's resume was accepted as verified because TC-059 passed. It
was not: a resumed session served a different sample order and different augmentation
from an uninterrupted one, so **session 2 of this run (epochs 16–19) is not the
continuation an uninterrupted run would have produced.** Three defects, all fixed in
`4737b05`; the investigation and the general lesson are in `docs/13`.

**Disposition: accepted for Stage 1, blocking for Stage 2.** It is accepted here because
none of the four pre-registered criteria depends on the resumed epochs being the
canonical ones — criterion 1 compares the first three epochs to the last three of *this*
run, and criteria 2–4 are evaluated on the checkpoint this run actually produced. It is
blocking for Stage 2 because a fold reported as a result must be reproducible, and
before the fix it was not.

**Consequence for this run, stated plainly.** `artifacts/runs/cirrus_holdout` **cannot be
reproduced by the current code.** Re-running the committed configuration now would
produce a different trajectory from epoch 16 onward, because the defective ordering it
used no longer exists. The run is retained as the execution record of Stage 1 and is not
re-run: Stage 1's purpose was to establish that training works at all, which it did, and
spending a further ~2 h of GPU time to regenerate a smoke run would buy a reproducible
*smoke* run and nothing else. **No number from this run may be cited as a result.** Stage
2 is the first run whose output is reportable, and it starts from the fixed code.

### D3 — `determinism.json` recorded 1308 non-deterministic fallbacks

**What happened.** The run requested deterministic algorithms with `warn_only=True` and
the record reported `deterministic_algorithms: true`, above 1308 fallback lines — every
one the same operation, `nll_loss2d_forward_out_cuda_template`, the cross-entropy term
inside MONAI's `DiceCELoss`. **GPU training in this run was not deterministic**, and the
record's summary line said otherwise while its detail said so 1308 times.

**Disposition: the record is fixed, the run's own file is not edited.** SRS-085 added;
`DeterminismReport.as_dict` now reports *achieved* determinism, false whenever anything
fell back, and deduplicates fallbacks to `{op, count, first_seen}` — 465 KB becomes 379
bytes and the one fact a reader needs, that exactly one operation is responsible, becomes
visible. The Stage 1 file is left as written, because a run record states what happened;
TC-109 scopes its invariant to records written after SRS-085 rather than rewriting
history to satisfy a rule introduced afterwards.

**Open.** Whether to adopt the deterministic replacement loss (SRS-084, TC-089,
implemented and verified but **not adopted**) or to amend CLAUDE.md rule 4 for GPU runs
waits on measured cost. See §5.5.

### D4 — The run record does not identify the code that produced it

**What happened.** `run.json` records the resolved configuration, the seed, the platform,
the torch build and the lock file's SHA-256, but **no commit SHA for this repository**.
SRS-031 exists so that a run is reproducible from the committed configuration; without a
commit identifier, the configuration is pinned and the code that consumed it is not.

**A second, smaller defect in the same file.** `run.json` carries a top-level `seed` field
whose value is `null`, while `resolved_config.run.seed` is `20260916` — the seed the run
actually used. Two places state one value and one of them is wrong, which is the pattern
CLAUDE.md already forbids for `batch_size` and which `f1204e5` fixed for the determinism
record.

**Disposition: open, fix required before Stage 2.** Both are record defects rather than
training defects, and both make a Stage 2 result less defensible than it needs to be. The
top-level `seed: null` should be removed rather than populated — a single home for the
value, as with `train.batch_size`.

---

## 5. Stage 1 smoke run — execution and evaluation

### 5.1 What was run

| Field | Value | Source |
|---|---|---|
| Fold | `cirrus_holdout` — the fewest training frames of the three | pre-registered, `docs/07` §15 |
| Frames | 2610 train, 580 in-domain validation | measured, the split |
| Epochs completed | **20** of 150 configured; `--max-epochs 20` for Stage 1 | measured, `epochs.jsonl` |
| Seed | 20260916 | measured, `resolved_config.run.seed` |
| Micro-batch / effective batch | 8 / 8, accumulation 1 | measured, resolved config |
| Sessions | **2** — epochs 0–15, then 16–19 after a resume | measured, `session_start` / `session_end` |
| Wall clock | 06:46:04 → 08:48:49 UTC, ≈2 h 03 m including the gap | measured, session boundaries |
| Per-epoch time | **362.5 s min, 380.7 s max, 365.1 s mean** | measured, all 20 `seconds` fields |

**The per-epoch figures are given in full because a claim about them was wrong.** A
resumed-session slowdown of ~3.5× was reported and retracted: it came from treating this
script's *projected* rate as session 1's observed rate. The measured spread across both
sessions is 362.5–380.7 s, a 5% range, and **the two sessions do not differ materially.**
The same applies to memory: a ~1.5 GB increase was claimed by comparing an early sample
of one session against a late sample of the other; both sessions in fact rose from
2435 MiB to ~3980 MiB. Both retractions are recorded in `docs/13` as a finding, not only
as corrections.

### 5.2 Evaluation against the pre-registered criteria

Recomputed by `scripts/evaluate_stage1.py` from `best.pt`, using the **same metric
function** that produced the baseline figures, so the comparison is not between two
implementations of Dice. Full record: `artifacts/runs/cirrus_holdout/stage1_evaluation.json`.

#### Criterion 1 — training loss decreases materially

| Quantity | Value |
|---|---|
| Mean training loss, first three epochs | **1.647568** (measured) |
| Mean training loss, last three epochs | **0.843390** (measured) |
| Reduction | **48.81%** (derived) |
| Threshold | ≥ 10% |
| **Result** | **PASS** |

#### Criterion 2 — validation Dice beats both baselines, per class

| Class | Measured Dice | Frames scored | Baseline A | Baseline B | Result |
|---|---|---|---|---|---|
| IRF | **0.4198** | 373 | 0.0000 | 0.0451 | **PASS** |
| SRF | **0.5450** | 248 | 0.0000 | 0.0428 | **PASS** |
| PED | **0.3211** | 235 | 0.0000 | 0.0384 | **PASS** |

All three measured values; both baselines measured before the run and unchanged. PED was
named in advance as the class most likely to fall short, and did not: it clears baseline
B by a factor of 8.4.

#### Criterion 3 — no class collapses to always-empty

| Class | Frames predicted | Frames with the class in truth | Predicted voxels | Result |
|---|---|---|---|---|
| IRF | **371** | 236 | 783 833 | **PASS** |
| SRF | **248** | 173 | 602 024 | **PASS** |
| PED | **235** | 126 | 433 313 | **PASS** |

All measured, over 580 validation frames. Every class is predicted on more frames than it
truly occurs on, which at twenty epochs is over-prediction rather than collapse — the
direction this criterion exists to distinguish, and the benign one.

#### Criterion 4 — the run's own records exist

| Artefact | Present |
|---|---|
| `last.pt` and `best.pt`, both in `checkpoints.sha256` | yes |
| A successful resume, with the epoch log continuing | yes — epochs 16–19 appended, not restarted |
| `determinism.json` including its `fallbacks` list | yes — and see D3 |
| `epochs.jsonl` with `session_start` / `session_end` boundaries | yes — 20 epoch rows, 4 session events |
| `gpu_telemetry.csv` covering the run | yes — 246 samples |
| `run.json` with the resolved configuration and seed | partially — see D4 |

**Result: PASS**, with D4 recorded against it. Criterion 4 asks whether `run.json` exists
and carries the resolved configuration and seed; it does. It does not ask for a commit
SHA, which is why D4 is a deviation found by inspection rather than a criterion failure —
and the criterion is **not** amended after the fact to cover it.

### 5.3 Overall result

**Stage 1: PASS.** All four pre-registered criteria met, none reinterpreted, none
rewritten. The best checkpoint is **epoch 16**, validation mean Dice **0.6812** (measured,
`best.pt`).

### 5.4 What this result is not

- **Not a cross-vendor result.** These are **in-domain validation** figures: unseen
  patients from the *training* vendors. The held-out vendor was not touched, by design
  (`docs/07` §15). The cross-vendor number — the one this project exists to report — does
  not exist yet.
- **Not a converged model.** Twenty epochs of a 2.64 M-parameter network on 2610 frames.
  Criterion 1 asks whether optimisation works, not whether it finished.
- **Not reportable.** See D2: this run is not reproducible by the current code.

### 5.5 What blocks Stage 2

| Blocker | State |
|---|---|
| Resume equivalence (D2) | **cleared** — fixed in `4737b05`, verified against an uninterrupted run at every epoch, both the served order and the served pixels |
| Determinism on GPU (D3) | **open** — the cost of the three configurations is being measured; the decision on the loss and on CLAUDE.md rule 4 follows the numbers, not the other way round |
| Run-record identity (D4) | **open** — a commit SHA in `run.json`, and the duplicate `seed` field removed |
| AMP, previously settled as off | **reopened by measurement.** The AMP-off decision was measured *without* the determinism the loop requests, so it priced kernels the run does not select. A first re-measurement under determinism showed AMP faster, not slower, and peak memory 2.30 GiB against 0.81 — over a window too short to conclude from, which is why it is being re-run properly rather than reported. The standing decision stands until the measurement replaces it |

---

## 5b. Stage 1b — the same criteria under the final configuration

Run 2026-09-30 against the criteria committed in `docs/07` §15.6 **before it started**.
Full record: `artifacts/runs/cirrus_holdout_stage1b/stage1_evaluation.json`.

### 5b.1 What was run

| Field | Value | Source |
|---|---|---|
| Fold, epochs, seed | `cirrus_holdout`, 20, 20260916 | measured, `run.json` |
| Loss | `dice_ce_deterministic` | measured, resolved config |
| AMP | **on** | measured, `amp_enabled: true` in both session records |
| Sessions | **2** — epochs 0–2, then 3–19, stopped by `session_epoch_limit` | measured, session boundaries |
| Wall clock | 16:58:26 → 18:15:55 UTC | measured |
| Per-epoch time | **228.3 s min, 238.3 s max, 231.2 s mean**; 1.28 h total | measured, all 20 `seconds` fields |
| Peak GPU memory | **2895 MiB of 4096** (70.7%) | measured, 157 telemetry samples |
| Temperature range | 43–65 °C | measured, same samples |

**The configuration change is worth 1.58× on this fold, measured.** 231.2 s mean against
Stage 1's 365.1 s, for the same fold, epochs and seed. The projection that justified the
change said 249 s/epoch, so it was 8% conservative — derived from 60 s benchmark windows
and checked here against a 20-epoch run that did not inform it. Peak memory fell from
**3993 MiB (97.5% of the card) to 2895 MiB (70.7%)**, which matters independently of speed:
Stage 1 had no headroom.

### 5b.2 The resume crossed the warmup boundary

`optim.warmup_epochs` is 5 and the session split is after epoch 2, so **epoch 3 — the
first resumed epoch — is inside the warmup window**. This is the case `SequentialLR`'s
position in its own sequence has to survive, and no run had exercised it on GPU.

Measured learning rate per epoch, from `epochs.jsonl`:

| Epoch | 0 | 1 | 2 | **3 (resumed)** | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| lr | 8.40e-05 | 1.38e-04 | 1.92e-04 | **2.46e-04** | 3.00e-04 | 2.9672e-04 | 2.8703e-04 |

The ramp continues across the session boundary at its correct increment, reaches the full
`3.00e-04` at epoch 4 where warmup ends, and then decays under cosine. A resume that had
lost the scheduler's position would have restarted the ramp or jumped to full rate at epoch
3; neither happened. **`--max-epochs-this-session 3` rather than `STOP`**, so the boundary
landed where it was asked to — the correction from deviation D1.

### 5b.3 Evaluation against the pre-registered criteria

Recomputed by `scripts/evaluate_stage1.py --stage 1b`, using the same metric function that
produced the baselines.

| Criterion | Result |
|---|---|
| **1** — loss falls ≥10% | mean first three **1.648121**, last three **0.843333**, reduction **48.83%** — **PASS** |
| **2** — beats both baselines, per class | see below — **PASS** |
| **3** — no class collapses | see below — **PASS** |
| **4** — the run's records exist | all artefacts present — **PASS** |
| **5** — determinism measured | 0 fallbacks, achieved `true`; bit-identity by TC-121 — **PASS** |

| Class | Measured Dice | Baseline A | Baseline B | Result |
|---|---|---|---|---|
| IRF | **0.3539** | 0.0000 | 0.0451 | **PASS** |
| SRF | **0.5629** | 0.0000 | 0.0428 | **PASS** |
| PED | **0.2971** | 0.0000 | 0.0384 | **PASS** |

| Class | Frames predicted | Frames with the class in truth | Result |
|---|---|---|---|
| IRF | 443 / 580 | 236 | **PASS** |
| SRF | 240 / 580 | 173 | **PASS** |
| PED | 256 / 580 | 126 | **PASS** |

**Overall: Stage 1b PASS.** Best checkpoint **epoch 15**, mean validation Dice **0.683435**.

### 5b.4 Two observations, neither a criterion

**Per-class Dice moved in both directions against Stage 1**, and §15.6 is explicit that
Stage 1's values are **not** the bar — a criterion of "at least as good as Stage 1" would be
one invented after seeing a result. For the record: IRF 0.4198 → 0.3539, SRF 0.5450 →
0.5629, PED 0.3211 → 0.2971, and the selected checkpoint's mean Dice 0.6812 → 0.6834. Two
classes down, one up, the selection metric marginally up. At twenty epochs on 2610 frames
this is not a converged comparison of configurations and should not be read as one; the
loss-reduction figures are near-identical (48.81% against 48.83%).

**Validation Dice collapsed at epoch 1 and recovered**: 0.021399 → **0.000855** → 0.144526
→ 0.287870 → 0.544777. A single early epoch near zero while the loss fell monotonically
(2.264524 → 1.529642 → 1.150198). No criterion addresses it and none is added after the
fact. Recorded because it is the kind of transient that, seen for the first time during a
150-epoch fold, would otherwise prompt an unnecessary investigation mid-run.

### 5b.5 What Stage 1b changes for Stage 2

| Was | Now |
|---|---|
| Resume equivalence unverified (D2) | Verified, and exercised across the warmup boundary on GPU |
| Determinism claimed from zero fallbacks | Measured: TC-121, two runs byte-identical |
| 365 s/epoch, 97.5% of GPU memory | 231 s/epoch, 70.7% |
| Three folds ≈57.7 h (derived) | ≈**36.6 h** (derived from 231.2 s/epoch measured) |
| **D4 still open** | `run.json` still records no commit SHA, and still carries a duplicate `seed: null` |

D4 is the one item this stage did not clear, because it was found after Stage 1b had
started and changing code mid-run is not a thing this project does (`docs/13`).

---

## 5c. Stage 2 — `cirrus_holdout` training record

> **This is a training record, not a result.** No number in this section is a performance
> claim about OcuVal. Every figure here is **in-domain validation** — unseen patients from
> the two *training* vendors — and the held-out vendor has not been touched. The
> cross-vendor result, which is the one this project exists to report, does not exist yet
> and is governed by the protocol pre-registered in `docs/07` §17.

### 5c.1 The run

| Field | Value | Source |
|---|---|---|
| Fold | `cirrus_holdout` — trained on spectralis + topcon | `run.json` |
| Run directory | `artifacts/runs/cirrus_holdout_stage2` | — |
| Epochs run | **59 (0–58)** of 150 configured, 110 bounded this session | measured, `epochs.jsonl` |
| **Stopped by** | **`early_stopping`**, 11:31:46 UTC | measured, `session_end` |
| Sessions | **1** — no resume was needed | measured, one `session_start` |
| Seed | 20260916 | `resolved_config.run.seed` |
| Loss | `dice_ce_deterministic` (SRS-084) | resolved config |
| AMP | on | `amp_enabled: true` |
| Micro-batch / effective | 8 / 8, accumulation 1 | resolved config |
| **Source** | **`a6d6edb`, branch `main`, `dirty: false`, `allow_dirty: false`** | `run.json.source`, SRS-086 |
| Determinism | `deterministic_algorithms: true`, **0 fallbacks** | `determinism.json` |

`a6d6edb` is the first fold run to carry a commit identifier and a clean-tree flag, SRS-086
having landed the same day. The run is therefore reproducible from a named commit, which is
what `docs/08` D4 recorded as missing after Stage 1 — **D4 is closed.**

### 5c.2 Early stopping — the fold is complete, not truncated

`early_stopping_patience` is **25** and was configured before the run; `--epochs 150` was
always an upper bound, not a target. Validation Dice last improved at **epoch 33**, so the
counter reached 25 at epoch 58 and the fold ended.

This matters for how the record reads: a fold that stops at 58 of 150 is **not** a fold
that failed to finish. It is a fold whose own pre-set criterion decided that further
epochs were not earning anything, and `best.pt` holds epoch 33 regardless of how many
epochs followed it.

### 5c.3 Metrics at the best checkpoint

**Epoch 33**, selected on in-domain validation only (`docs/07` §17.1), 580 validation frames.

| Class | In-domain validation Dice |
|---|---|
| IRF | **0.705869** |
| SRF | **0.778664** |
| PED | **0.647028** |
| mean (foreground) | **0.710520** |

Training loss fell from a first-three-epoch mean of **1.648121** to a last-three mean of
**0.821170**, a 50.2% reduction. Learning rate at the best epoch was 2.7135e-04, decaying
under cosine from the 3.0e-04 reached at the end of warmup.

**These are point estimates with no confidence interval, and are therefore not reportable
as results** (CLAUDE.md §5, SRS-033). They are recorded here as the training record. The
bootstrap intervals, the per-vendor breakdown and the detection metrics come from the
evaluation pipeline governed by §17, and no figure from this section may be cited in
`docs/10` or anywhere else as a result.

### 5c.4 Timing and thermals

| Quantity | Value | Measured from |
|---|---|---|
| Wall clock | 07:46:21 → 11:31:46 UTC, **3.75 h** | session boundaries |
| Seconds per epoch | **227.6 min, 238.5 max, 229.0 mean** | all 59 `seconds` fields |
| GPU temperature | **37–68 °C** | 451 telemetry samples |
| GPU memory | **69–2875 MiB of 4096** (70.2% peak) | same samples |

229.0 s mean against Stage 1b's 231.2 s — the two agree to within 1%, on different fold
lengths, which is a small independent confirmation that the throughput figure the §18
budget rests on is stable rather than a one-off.

No thermal excursion: 68 °C peak is 22 °C below the 90 °C intervention threshold, so no
epoch's duration needs a thermal explanation. Peak memory of 70.2% leaves real headroom,
against Stage 1's 97.5% before AMP was enabled.

### 5c.5 Checkpoints

| File | SHA-256 (from `checkpoints.sha256`) |
|---|---|
| `best.pt` (epoch 33) | `bf609e63a16f729143baf219ba3a13f5e670fdee456c216c0f62f980e4efc17f` |
| `last.pt` (epoch 58) | `20410f4b9121c26c350d4f7e7e411e69f63574ebd5075f652f9a081f72622c15` |

They differ, as they must: `best` selects a model, `last` continues a trajectory, and this
fold's best was 25 epochs before its last.

### 5c.6 Monitoring

The run was monitored unattended at 20-minute intervals, 13:25 to 17:05 local, by a
detached watcher writing `artifacts/monitor/night1.md` (gitignored). **No intervention
occurred**: no non-finite metric at any epoch, and the GPU never reached 90 °C, so no STOP
file was created. The longest falling-Dice streak was 2 against a reporting threshold of
10, and no epoch exceeded 238.5 s against a threshold of 350.

One observation from the night is worth carrying into the next fold's monitoring, because
it would otherwise be re-discovered: **a single SM-clock sample is not a load measurement
on this machine.** Samples of 1189, 696 and 139 MHz appeared while seconds-per-epoch never
varied by more than 1.5 s, because the 30 s telemetry interval is uncorrelated with the
compute phase and lands in the gap between epochs. Seconds-per-epoch is the figure that
would show throttling.

---

## 5d. Stage 2 — the one-time evaluation of the held-out vendor

> **Label added 2026-10-04: these figures are a single unseeded draw.** Evaluation at
> `767c8e5` did not seed the MC-dropout passes or request deterministic kernels, and two
> evaluations of one checkpoint have since been shown to differ (`docs/13`, 2026-10-04). No
> figure below is changed or withdrawn. A seeded re-run under `docs/07` §17.10 is the
> reproducible record, and is reported beside these figures, not in place of them.

Run 2026-10-01 under the protocol pre-registered in `docs/07` §17 and amended in §17.7
**before any sealed split was accessed**. Records:
`artifacts/runs/cirrus_holdout_stage2/evaluation_test.json` and
`evaluation_in_domain_ref.json`.

### 5d.1 Provenance

| Field | Value |
|---|---|
| Evaluation code | **`767c8e571dc00b9db1907f569f15548c8399a358`**, branch `main`, `dirty: false` |
| Model | `best.pt`, **epoch 33**, trained from `a6d6edb` |
| Held-out vendor | **cirrus** — trained on spectralis + topcon |
| Presence threshold | **10 voxels**, as configured (SRS-051, §17.7a) |
| MC-dropout passes | 20 (SRS-029) |
| Bootstrap | 2000 resamples, α = 0.05, seed 20260916, **resampling unit: patients** (SRS-087) |
| Geometry | predictions inverted to native grid before measurement; spacing asserted bit-identical to ingestion (SRS-074, SRS-057) |
| Elapsed | 101.4 min (`test`, 24 volumes), 8.5 min (`in_domain_ref`, 7 volumes) |

### 5d.2 Segmentation — per class, native geometry, patient-level 95% intervals

| Class | Metric | Held-out cirrus | In-domain reference | Gap |
|---|---|---|---|---|
| IRF | Dice | **0.3452** [0.2461, 0.4433] n=24 | **0.5543** [0.3370, 0.7272] n=7 | +0.2091 |
| IRF | HD95 | 1.5191 [0.3766, 3.1149] n=18 | 1.0296 [0.0471, 2.2165] n=6 | −0.4895 |
| SRF | Dice | **0.2481** [0.1431, 0.3632] n=24 | **0.2707** [0.0048, 0.5727] n=7 | +0.0226 |
| SRF | HD95 | 1.1525 [0.2735, 2.1690] n=12 | 5.8591 [0.0176, 13.1262] n=4 | +4.7066 |
| PED | Dice | **0.1916** [0.0956, 0.2987] n=24 | **0.2740** [0.0387, 0.5598] n=7 | +0.0825 |
| PED | HD95 | 1.5771 [0.6368, 2.8785] n=12 | 0.0869 [0.0000, 0.2216] n=3 | −1.4901 |

**`n` is patients throughout** (SRS-087, §17.2). Dice `n` is the full 24 and 7. HD95 `n` is
lower — 18, 12, 6, 4, 3 — because HD95 is undefined where exactly one of prediction and
reference is empty and those volumes are dropped before resampling rather than counted as
evidence. **Gap = in-domain − held-out**, so positive means lower performance on the unseen
vendor.

### 5d.3 Detection — at the pre-registered threshold, AUROC primary

AUROC is the primary detection metric because it is threshold-free (§17.7a). Sensitivity and
specificity are reported at the fixed threshold of 10 voxels **as-is**.

| Class | Metric | Held-out cirrus | In-domain reference | Gap |
|---|---|---|---|---|
| IRF | **AUROC** | **1.0000** n=24 (+18/−6) | **1.0000** n=7 (+6/−1) | 0.0000 |
| IRF | sensitivity | 1.0000 n=18 | 1.0000 n=6 | 0.0000 |
| IRF | specificity | 0.0000 n=6 | 0.0000 n=1 | 0.0000 |
| SRF | **AUROC** | **1.0000** n=24 (+12/−12) | **0.9167** n=7 (+3/−4) | −0.0833 |
| SRF | sensitivity | 1.0000 n=12 | 1.0000 n=3 | 0.0000 |
| SRF | specificity | 0.0833 n=12 | 0.2500 n=4 | +0.1667 |
| PED | **AUROC** | **0.9514** n=24 (+12/−12) | **1.0000** n=7 (+2/−5) | +0.0486 |
| PED | sensitivity | 1.0000 n=12 | 1.0000 n=2 | 0.0000 |
| PED | specificity | 0.0000 n=12 | 0.2000 n=5 | +0.2000 |

Sensitivity `n` is the count of truly-present volumes and specificity `n` the truly-absent
ones — the denominators each rate is defined over. AUROC `n` is patients, with the
positive/negative volume split given.

### 5d.4 What these figures do and do not establish

**No per-class Dice difference is established at 95%.** Five of the six segmentation
comparisons have **overlapping** intervals between the two arms — IRF Dice, SRF Dice, PED
Dice, IRF HD95 and SRF HD95. IRF's gap of +0.2091 is the largest and its arms still overlap,
[0.2461, 0.4433] against [0.3370, 0.7272]. All three Dice point estimates are lower on the
unseen vendor, and that is the direction the project expected, but the intervals do not
separate them.

The one non-overlapping comparison is **PED HD95**, whose in-domain arm rests on **3
patients**. Nothing is concluded from it.

**The in-domain arm has 7 patients**, which is why its intervals are wide — SRF Dice spans
[0.0048, 0.5727] and SRF HD95 [0.0176, 13.1262]. Several HD95 figures rest on 3 or 4
patients and carry almost no information at that width.

**The gap figures carry no confidence intervals, by design** (§17.2, `eval/subgroup.py`). A
difference of two independently bootstrapped intervals is not a confidence interval: a
correct interval for a difference requires resampling both arms jointly under one patient
draw. Both arms' intervals are given so a reader can see the overlap, and the gap is a point
difference labelled as such. A joint-resample estimator is a separate, pre-registered change.

**Specificity is near zero at the fixed threshold in both arms** — 0.0000, 0.0833, 0.0000 on
held-out and 0.0000, 0.2500, 0.2000 in-domain — while sensitivity is 1.0000 throughout. At 10
voxels the model predicts every class present in nearly every volume. That is a measured fact
about this operating point, reported unchanged per §17.7a. **AUROC is nonetheless 0.95–1.00**,
which is consistent with the ranking being informative while that particular threshold is not
discriminative; the two are not in conflict. No threshold has been re-selected.

### 5d.5 Deviations

#### D5 — the `test` bucket was unlocked twice

**What happened.** The first access, 12:58:29 UTC, was **terminated by a harness background
time limit** after measuring **10 of 24 volumes**. It produced **no `evaluation_test.json`**
— the record is written only at the end of a run — and therefore **no results were produced
or seen**. The second access, 13:29:32 UTC, ran to completion and is the record reported
above.

**No change to the model, checkpoint, threshold or metric definitions was made between the
two runs** (§17.7b). The restart's logged `reason` states the timeout, the 10-of-24 progress,
that no JSON was produced, and that nothing was changed.

**Disposition: recorded, not reasoned away.** `docs/07` §17.1 permits the test split to be
evaluated once, and the access log shows more than one unlock. The author's reading is that
the pre-registered concern — looking at results more than once — is not breached, because the
first access yielded no results to look at. That is a reading of the protocol, not a fact the
log establishes, which is precisely why SRS-088 records the count instead of letting the
operator decide the question.

**Corrective action, §17.7's successor rule:** evaluation runs are launched from the author's
own terminal or as a detached background process, never as a single tool call a time limit can
kill (`docs/07` §17.8).

#### D6 — the access count counted gate calls, not evaluation runs

The logged counts read `test=3` and `in_domain_ref=2`, against two and one actual runs. The
seal is checked **twice per completed run** — once in `scripts/05_evaluate.py` before the
split is read, once in `eval/pipeline.py` at aggregation — so a completed run logged two
entries and the killed run logged one. 3 = 1 + 2 and 2 = 2.

**No reported figure depends on this**; it is an accounting defect, and the `reason` fields
distinguish the entries so no information was lost. But the headline number did not answer the
question §17.5 asks. SRS-088 is corrected and the accounting fixed so that each run counts
once. **The raw access log is kept exactly as written** — it is the primary evidence, and
rewriting it to make the count tidy is the one thing that would destroy its value.

#### D7 — per-volume measurements were not persisted

The evaluation record carries aggregates only. No secondary analysis — including the
present/absent Dice decomposition — can be computed from it without re-running inference on
the sealed splits. §17.5's field list did not require per-volume rows, and should have.
**Repaired 2026-10-03** in `6295bd0` (SRS-089, TC-126); the cirrus re-run that uses the rows
is scheduled between training sessions.

---

## 5e. Stage 3 — `spectralis_holdout` training record

> **A training record, not a result.** The held-out vendor here is spectralis; it has not been
> touched, and `docs/07` §17 and §19 govern its evaluation.

### 5e.1 Session 1 — interrupted after epoch 9 by external termination

| Field | Value | Source |
|---|---|---|
| Launched | 2026-10-03 19:56 local, **by Claude Code**, through `Win32_Process.Create` | — |
| Source | `5f66359`, `dirty: false`, `allow_dirty: false` | `run.json`, SRS-086 |
| Epochs completed | **10** (0–9) of 80 bounded this session | measured, `epochs.jsonl` |
| Seconds per epoch | **339.0–352.7, mean 342.5** | measured, 10 epochs |
| Best | epoch **8**, val Dice **0.643812** | measured |
| Patience at end | 1 of 25 | measured |
| GPU | 49–76 °C, peak memory 2875 MiB of 4096 | measured, telemetry |
| **How it ended** | **terminated externally around 20:56 local, mid-epoch 10. No `session_end`, no traceback, no crash report, no reboot, no logoff** | log, Windows event logs |

**Checkpoints verified read-only after the interruption.** `last.pt` (epoch 9) and `best.pt`
(epoch 8) both match `checkpoints.sha256`, and `last.pt` carries the early-stopping state of
its own epoch — best 8, one epoch since improvement, patience 25. Nothing was lost but the
partial epoch 10, roughly five minutes of compute. The unterminated first session stays in
`epochs.jsonl` as what happened.

### 5e.2 Session 2 — resumed by the author

Resumed 2026-10-03 21:03 local **by the author, from the VS Code integrated terminal**, into
the same run directory: `run.json` records `7be924f`, `dirty: false`,
`max_epochs_this_session: 70`, and `epochs.jsonl` records `session_start` from epoch 10 to 80
with `resumed: true`. **No file on the training path differs between `5f66359` and
`7be924f`** — the two commits between them changed only documents, `eval/pipeline.py` and its
test — so both sessions run the same training code under different identifiers.

| Field | Value | Source |
|---|---|---|
| Epochs completed | **45** (10–54); **55 across the fold** (0–54) of 150 configured | measured, `epochs.jsonl` |
| **Stopped by** | **`early_stopping`**, 19:47:29 UTC (01:17 local), `fold_complete: true` | measured, `session_end` |
| Wall clock | 15:33:51 → 19:47:29 UTC, **4.23 h** | session boundaries |
| Seconds per epoch | **334.7–348.0, mean 338.0** | measured, 45 epochs |
| GPU | **49–76 °C**, 507 telemetry samples, none at or above 90 °C | measured, telemetry |
| Determinism | `deterministic_algorithms: true`, **0 fallbacks** | `determinism.json` |

**The resume was continuous.** Epoch 10's logged learning rate, `0.0002987343436093454`,
equals the closed-form cosine value for that position exactly; the best epoch carried over as 8
and patience continued from 1 to 2. Validation Dice improved at epochs 13, 17, 20, 23 and last
at **epoch 29**, so the counter reached 25 at epoch 54 and the fold ended by its own
pre-set criterion, at 55 of 150, like `cirrus_holdout` at 59 (§5c.2).

### 5e.3 Metrics at the best checkpoint

**Epoch 29**, selected on in-domain validation only (`docs/07` §17.1).

| Class | In-domain validation Dice |
|---|---|
| IRF | **0.646696** |
| SRF | **0.728785** |
| PED | **0.611493** |
| mean (foreground) | **0.662325** |

Training loss fell from a first-three-epoch mean of **1.504528** to a last-three mean of
**0.843016**, a 44.0% reduction. It fell at every epoch through 54, while validation Dice stayed
at about 0.63–0.66 from epoch 13 onward, which is the pattern early stopping exists to cut off.
Learning rate at the best epoch was 2.7853e-04.

**Point estimates, no interval, not reportable as results** (CLAUDE.md §5, SRS-033), exactly as
in §5c.3. In particular, these figures are **not comparable to cirrus's 0.710520** as a vendor
claim: each is in-domain validation over a different pair of training vendors.

### 5e.4 Timing, thermals and checkpoints, whole fold

| Quantity | Value | Measured from |
|---|---|---|
| Train time | **5.18 h** | sum of 55 `seconds` fields |
| Seconds per epoch | **334.7 min, 352.7 max, 338.8 mean** | all 55 epochs |
| GPU temperature | **49–76 °C** | 623 telemetry samples, 0 error rows |
| GPU memory | **69–2895 MiB of 4096** (70.7% peak) | same samples |

338.8 s/epoch against cirrus's 229.0 s is a ratio of 1.48; the training-frame ratio is 4032
against 2610, 1.54, so the per-frame cost is broadly consistent across folds. Scaling cirrus's
229.0 s by that frame ratio predicted **353.8 s** (derived); the measurement came in 4% under
it. Per-epoch time is not purely proportional to training frames, since validation and the
fixed per-epoch overhead scale differently, which is why `docs/07` §18.1 sizes each fold's
sessions from its own measured time.

| File | SHA-256 (from `checkpoints.sha256`, verified 2026-10-04) |
|---|---|
| `best.pt` (epoch 29) | `ceac44a77c5730b710b27789351c5c59125a1001f368749f7affc9da89c6abec` |
| `last.pt` (epoch 54) | `fdc2c605735b0879c2f86641abfa880dce4c22cd1e7f3df1069d0472909c9f2b` |

**Monitoring.** Session 2 was checked read-only every 20 minutes by the Claude Code session,
each line written only after confirming the training process was alive
(`artifacts/monitor/stage3_night1.md`, gitignored). **No intervention**: no non-finite metric,
no temperature at or above 90 °C, no STOP file. The longest run of falling validation Dice was
2 epochs.

### D8 — a run described as detached was not, and died with its WMI parent

**What happened.** Session 1 and its watcher were launched by Claude Code through
`Win32_Process.Create`, and **described to the author as detached and able to survive VS Code
closing**. That part was true. But each was parented by a WMI provider host (`WmiPrvSE.exe`
10200 and 18048), and both processes ended at the same moment around 20:56 local. Afterwards
both hosts were gone; no crash, no Windows Error Reporting entry, no logoff (Explorer, Winlogon,
VS Code and Claude Code all still running from before) and no reboot. A `Kernel-Power` 566
session transition at 20:56:39 coincides, but an identical-looking transition at 20:01 caused
nothing.

**Most likely cause — inferred, not proven:** a process created through `Win32_Process.Create`
lives in the WMI provider host's job object, and Windows tears idle provider hosts down. The
launch escaped VS Code's job object and was placed in another.

**The defect is in the claim, not only the method.** "It no longer depends on VS Code" was
checked; "it depends on nothing" was assumed. The process tree showed the WMI parent at launch
and was read only to confirm the absence of VS Code.

**A second error from the same evening.** At 20:57, "about 6.7 more hours" was reported from
`epochs.jsonl` **without confirming the process was alive**; it had died a minute earlier. The
epoch log records what a run did, not whether it is still running.

**Disposition.** Not relaunched by Claude Code; the author relaunched. `docs/07` §17.8 and
CLAUDE.md are corrected: long runs are launched by the author from an interactive terminal kept
open, a launch method is called detached only after verifying its dependencies from the process
tree, and no remaining-time estimate is given without first confirming the process is alive.

---

## 5f. Stage 3 — `topcon_holdout` training record

> **A training record, not a result.** The held-out vendor here is topcon; it has not been
> touched, and `docs/07` §17 and §19 govern its evaluation.

### 5f.1 The run

| Field | Value | Source |
|---|---|---|
| Fold | `topcon_holdout` — trained on cirrus + spectralis | `run.json` |
| Run directory | `artifacts/runs/topcon_holdout_stage3` | — |
| Launched | 2026-10-04 12:57:40 local, **by the author**, as step 1 of `scripts/run_remaining.ps1` from the VS Code integrated terminal | `artifacts/chain/status.txt` |
| Source | **`d35e8e4`**, `dirty: false`, `allow_dirty: false` | `run.json`, SRS-086 |
| Epochs run | **55 (0–54)** of 150, no session limit | measured, `epochs.jsonl` |
| **Stopped by** | **`early_stopping`**, 11:34:09 UTC, `fold_complete: true` | measured, `session_end` |
| Sessions | **1** | measured, one `session_start` |
| Seed | 20260916 | `resolved_config.run.seed` |
| Frame cache | `D:\ocuval_cache` via `OCUVAL_CACHE_DIR`, because C: was short of space | `run.json.resolved_cache_dir` |
| Pre-pass | 3088 training and 659 validation frames, cache built in **3 min 7 s** | measured, `started_utc` to `session_start` |
| Determinism | `deterministic_algorithms: true`, **0 fallbacks** | `determinism.json` |

**The training configuration is that of the other two folds.** Verified before launch, on
2026-10-04:
- **Against spectralis:** no file on the training path, no fold file, `requirements.lock` or
  `pyproject.toml` differs between `7be924f` and the launch commit, so spectralis and topcon
  trained under byte-identical configuration.
- **Against cirrus:** the only difference from `a6d6edb` is
  `inference.presence_voxel_threshold`, added to `configs/train_seg.yaml` under §17.7a, and no
  training-path module reads it.
- **Fold files:** `topcon_holdout.yaml` equals `spectralis_holdout.yaml` apart from the vendor
  name.

The cache location is a per-machine path recorded in the run, not a configuration change
(`runs.py:262-282`).

### 5f.2 Early stopping — the fold is complete, not truncated

Validation Dice last improved at **epoch 29**, so the patience counter of 25 ran out at epoch
54. This is the same pattern as the other folds: cirrus stopped at 58 (best 33) and spectralis
at 54 (best 29). The longest run of falling validation Dice was 3 epochs.

### 5f.3 Metrics at the best checkpoint

**Epoch 29**, selected on in-domain validation only (`docs/07` §17.1).

| Class | In-domain validation Dice |
|---|---|
| IRF | **0.608839** |
| SRF | **0.775173** |
| PED | **0.640639** |
| mean (foreground) | **0.674884** |

Training loss fell from a first-three-epoch mean of **1.582979** to a last-three mean of
**0.818695**, a 48.3% reduction. Learning rate at the best epoch was 2.7853e-04, the same
schedule position as spectralis's best epoch.

**Point estimates with no interval, so not reportable as results** (CLAUDE.md §5, SRS-033). They
are not comparable with the other folds' validation figures as a vendor claim, because each fold
validates on a different pair of training vendors.

### 5f.4 Timing, thermals and checkpoints

| Quantity | Value | Measured from |
|---|---|---|
| Wall clock | 07:30:48 → 11:34:09 UTC, **4.06 h** | session boundaries |
| Seconds per epoch | **263.6 min, 270.4 max, 265.3 mean** | all 55 `seconds` fields |
| GPU temperature | **42–71 °C**, none at or above 90 °C | 487 telemetry samples, 0 error rows |
| GPU memory | **69–2875 MiB of 4096** (70.2% peak) | same samples |

The ~271 s/epoch expected before launch was **derived** by scaling cirrus's 229.0 s by training
frames (3088 against 2610). The measurement came in 2.1% under that figure.

| File | SHA-256 (from `checkpoints.sha256`, verified 2026-10-04) |
|---|---|
| `best.pt` (epoch 29) | `95bd0d5788185e511079e196051980622d7965125ccf55f37c0b3839c9107af6` |
| `last.pt` (epoch 54) | `6b0b91b86355874a5defd484bfb4ddd22909a47ffabb89a8c24e0039c3acf2a2` |

**Monitoring.** The run was checked read-only every 20 minutes by the Claude Code session, each
row written only after confirming the training process was alive
(`artifacts/monitor/chain_2026-10-04.md`, gitignored). **No intervention**: no non-finite
metric, no temperature at or above 90 °C, no STOP file, and no storage action. C: free space
moved between 8.50 and 14.65 GB with the page file, and no threshold was approached.

---

## 6. Conclusion

**Not drafted.** The validation conclusion requires the cross-vendor result, which is
Stage 3. What can be concluded now is scoped to Stage 1 and is in §5.3.
