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

## 6. Conclusion

**Not drafted.** The validation conclusion requires the cross-vendor result, which is
Stage 3. What can be concluded now is scoped to Stage 1 and is in §5.3.
