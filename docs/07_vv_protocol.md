<!--
Document: Verification and Validation Protocol
Status: DRAFT v0.1
Owner: Anurag Yadav
Last reviewed: 2026-09-19
Change history: docs/13_change_control_log.md

Allocates TC-000..TC-120 (80 cases) across unit, integration and system levels. Carries the
IEC 62304 §5.5.2 unit verification process and §5.5.3 unit acceptance criteria that
docs/03 open item 3 records as owed, and the §5.6 integration testing that open item
2 records. Clause references carry the docs/03 §1.2 caveat.
-->

# Verification and Validation Protocol

## 1. Purpose and scope

This protocol defines how every requirement in `docs/02` and every risk control in
`docs/05` is verified. It covers the three levels IEC 62304 distinguishes for a Class B
system — unit verification (§5.5), integration testing (§5.6) and system testing (§5.7)
— and adds a fourth category this project needs and the standard does not name:
**document and configuration integrity** (§8), which tests the documents against each
other and against the code.

### 1.1 Verification, not validation

Almost everything here is **verification**: does the software meet its specification.
Validation — does the specification meet the user's need — cannot be performed by this
project. It would require the intended use in `docs/01` to be real, with real graders in
a real reading workflow. `docs/08` records that gap; nothing in this document closes it.

### 1.2 Status

**35 of 80 test cases are implemented** as of 2026-09-17 — TC-000..TC-002, TC-004,
TC-014, TC-015, TC-030..TC-035, TC-040..TC-042, TC-060..TC-062, TC-068, TC-072,
TC-105 and TC-106, covering `eval/metrics.py`, `data/splits.py`, `io/deident.py`, the spacing guard in
`io/retouch_reader.py`, and the two document-integrity gates. The
rest specify what will be written when the corresponding module exists. A protocol
written ahead of the code is the right order — it is what CLAUDE.md rule 1 asks for —
but it means §10's coverage figures describe a plan, not a result.

## 2. Test environment

| | |
|---|---|
| Runtime | Python 3.11, dependencies exactly as pinned in `pyproject.toml` (SOUP-016, NFR-001) |
| Runner | `pytest`, with `--strict-markers` |
| Markers | `slow`, `requires_data`, `requires_pacs` — CI excludes the last two, never the leakage gate |
| PACS | Orthanc at the digest pinned in SOUP-014, via `docker compose` |
| Hardware | CPU only. No test in this protocol requires a GPU (NFR-003) |
| Data | Synthetic fixtures by default. Tests needing RETOUCH carry `requires_data` and do not run in CI |

**Synthetic-first is a deliberate choice.** A test that needs the real dataset cannot
run in CI, cannot run on a fresh clone, and cannot run at all until registration
completes (`docs/06` §10 item 1). Every test below that can be written against a
constructed fixture is.

## 3. Unit verification process — IEC 62304 §5.5.2

Required for Class B. This section is the process; §4 is the criteria.

1. **A unit is a module under `src/ocuval`.** The unit boundary is the module, not the
   function, because `docs/02` §3.10 allocates requirements at module granularity.
2. **Verification is by automated test** unless a row in §6 states otherwise and gives a
   reason. Manual verification is a deviation and is recorded under §9.
3. **Every unit test names the requirement it verifies** in its function name, using the
   `TC-nnn` identifier: `def test_TC_012_reader_raises_on_malformed_input():`. The
   identifier is the link to this document; a test without one is unallocated work.
4. **Tests are written against the requirement, not against the implementation.** A test
   that reproduces the implementation's logic verifies nothing. Where a requirement
   states a numeric outcome, the expected value is computed independently — TC-072 is
   the worked example.
5. **A failing unit test blocks merge.** There is no triage step in which a failure is
   accepted without either fixing the code or changing the requirement under §9.
6. **Coverage is reported but is not an acceptance criterion.** `pytest-cov` runs in CI
   (SOUP-019). Line coverage measures what executed, not what was verified; §4 states
   what acceptance actually requires.
7. **A fixture written in the consuming code's convention cannot test a conversion.**
   Where a unit converts between two representations — units, axis order, coordinate
   frame, encoding — the fixture must be expressed in the *source* convention and the
   assertion in the *target* one. A fixture already in the target convention makes the
   conversion a no-op that passes whatever the implementation does, including nothing.

   Two consequences for how such a test is written:

   - **Make the conversion non-identity in the fixture.** If every component of the
     input happens to be symmetric under the transformation, a broken implementation
     passes. Assert explicitly that the output differs from the input.
   - **Assert a property the target convention implies**, not only the literal expected
     value. `spacing_from_header` asserts that the axial component ends up the finest of
     the three, which is true of any real OCT acquisition and false under a wrong
     permutation, so the test survives a change of fixture values.

   This rule exists because of a real defect class found on 2026-09-23 and recorded in
   `docs/13`: the synthetic fixtures for the DICOM writer were written in this project's
   `(axial, lateral, separation)` order, so they exercised every downstream use of
   spacing and never the MetaImage `(x, y, z)` conversion that real ingestion performs.
   The conversion was written correctly, but nothing in the suite would have caught it
   had it not been.
8. **A test for a mechanism must inspect the mechanism, not only its observable
   output.** Where a unit exists to make something happen *behind* an interface — a
   cache, a hook, a scheduler, a counter — asserting only that the interface still
   returns the right answer will pass when the mechanism is absent, because the
   fallback path usually produces the same answer more slowly.

   The test must therefore reach the artefact: open the cache file, run the hook,
   read the recorded state, count the calls.

   **Six instances of this in this project, all found by something other than the
   test that should have caught them:**

   | Mechanism | What the test asserted | Why it passed while broken | Found by |
   |---|---|---|---|
   | `pre-commit` change-control hook | The config file listed the hook | The hook was never installed, so it could not run | A commit that should have failed, succeeding |
   | Coverage figures in `docs/09` | A hand-maintained number | Nothing recomputed it, so it drifted in both directions at once | Reading it against pytest |
   | Frame cache (TC-039) | Cached and uncached values matched | They match when the cache is empty and the transform simply re-runs | Benchmarking, when entries turned out to be 4 KB of metadata |
   | `optim.warmup_epochs` | Nothing — the key was read by no code at all | A configured warmup that never happens looks exactly like no warmup | Writing a test that had to cross a warmup boundary |
   | Per-epoch shuffle seeding (TC-059) | Which epoch scored best after a resume | Sample order changes *which* epoch is best only sometimes; it passed 2 times in 3 with the defect present | Asking why a passing test was flaky |
   | Per-epoch augmentation seeding (TC-059) | The sequence of frame **ids** each epoch served | The ids were right and the pixels were not — the transform chain's own RNG is in neither global generator | The order test passing while the run was still not reproducible |

   The common shape: **the observable output is identical whether the mechanism works
   or is missing entirely.** That is precisely when a black-box assertion is worthless,
   and precisely when the mechanism is easiest to leave unwired.

   Two consequences for how such a test is written:

   - **Assert against the artefact the mechanism produces**, not against what the system
     returns. TC-039 now opens the cache file and asserts an image is in it, counts
     decodes, and asserts a warm cache decodes zero times.
   - **Assert the mechanism can fail.** If disabling it does not break the test, the
     test was not testing it. TC-039 checks that a nested `Compose` truncates the cached
     prefix; TC-059 checks that discarding the RNG state makes a resumed run diverge.

9. **Assert the invariant, not a consequence the trajectory happens to produce.** A
   corollary of rule 8, added 2026-09-30 because two tests in one file broke this way and
   the second broke it while being rewritten to fix the first.

   Both were resume tests. One asserted *which epoch scored best* after a resume; the
   other asserted that the patience counter at the first resumed epoch was not lower than
   at the interruption. Each is a real consequence of the invariant, and each also depends
   on what the metric happened to do:

   | Test | The consequence it asserted | Why it was not the invariant |
   |---|---|---|
   | `..._preserves_the_best` | `best_metric` after a resume equals the uninterrupted value | A different sample order changes which epoch wins only when two epochs are close. 7 passes in 20 with the defect present |
   | `..._mid_patience_carries_the_counter` | `since_improvement >= before` at the first resumed epoch | When that epoch *improves*, the counter resets to 0 and the run is correct. 17 passes in 20 on correct code — it failed the code for behaving as specified |

   **A flaky test is not a test that needs rerunning; it is a test asserting something
   that is not always true.** The second case is the instructive one: the flakiness was in
   the assertion, not the system, so rerunning until green would have hidden nothing and
   still taught nothing.

   The invariant behind both is one sentence — *a resumed run is the same run* — and it is
   assertable directly: compare the resumed run's whole epoch log against an uninterrupted
   run's, field by field, and interrupt at **every** epoch rather than one chosen epoch,
   because which boundary lands mid-patience depends on the trajectory and so cannot be
   fixed in advance. Both rewritten tests now pass 20 times in 20.

   Two practical tests of an assertion, before writing it:

   - **Could this fail while the system is correct?** If yes, it is a consequence.
   - **Does it depend on a number the run produced?** Then compare it against the same
     number from a reference run, not against a bound chosen by hand.

   And the vacuity guard that belongs with it: assert the run was *in* the state the test
   is named for. The rewritten patience test fails loudly if no epoch of the reference run
   was inside a patience window at all, rather than passing on a trajectory that never
   exercised the thing.

10. **A fixture for a determinism test must itself be deterministic — across processes,
    not merely within one.** Added 2026-10-01.

    Three fixtures seeded their synthetic images from `abs(hash(frame_id))`. Python salts
    `str` hashing per process (`PYTHONHASHSEED`), so **every test process trained on
    different data**. Measured: the same key hashed to 768840219, 640343991 and 2869603707
    in three consecutive interpreters.

    Nothing about the resume invariant broke — a resumed run still matched an uninterrupted
    one in each process, because both halves saw the same data *within* that process. What
    broke was rule 9's **vacuity guard**: the patience test asserts that the reference run
    entered a patience window at all, and on 1 run in 40 that process's trajectory improved
    on every epoch, so the precondition genuinely did not hold and the test correctly said
    so.

    **The failure was in the fixture, not in either assertion**, which is why it took two
    rewrites and a 40-run capture loop to see: the test was rewritten twice for asserting
    the wrong thing, and then failed for a third reason neither rewrite touched. The
    diagnosis needed the actual assertion text, which was lost on the first two failures
    because the output was not kept — **capture the failure before theorising about it.**

    The fix is the one `epoch_seed` already uses: derive from a stable function.
    `hashlib.sha256(key.encode())` gives the same seed in every process, so the trajectory
    is now a fixed property of the test rather than a per-process draw, and the guard's
    outcome is decided once instead of sampled.

    The general form: **a test that asserts reproducibility cannot rest on anything the
    runtime randomises per process** — `hash()` of a str, `set` or `dict` iteration order
    derived from one, `id()`, address-dependent ordering, or an unseeded temporary path. A
    pass count over such a fixture measures how often the precondition held, not whether
    the property does.

## 4. Unit acceptance criteria — IEC 62304 §5.5.3

A unit is accepted when **all** of the following hold:

| # | Criterion |
|---|---|
| A1 | Every requirement allocated to the unit in `docs/02` §3.10 has at least one passing test case in §6 |
| A2 | Every error path the requirement names is exercised — specifically, each requirement using "shall abort", "shall reject" or "shall raise" has a test asserting that behaviour, not only the success path |
| A3 | No test is skipped or `xfail`ed. **No exception remains:** the one permitted `xfail` was TC-004 before `splits.py` existed, and it was removed on 2026-09-17 when the module landed. It was `strict=True`, so it would have failed the moment it started passing by accident |
| A4 | `ruff check` and `ruff format --check` pass over the unit |
| A5 | Any risk control in `docs/05` implemented by the unit has a test that exercises the control, not merely the feature it protects |
| A6 | The unit's docstring names the SRS identifiers it implements, and those identifiers exist in `docs/02` (TC-102 enforces this) |

A5 is the one that does real work. A feature test asks whether the happy path produces
the right answer; a control test asks whether the guard fires when it should. RC-023
rejecting an implausible spacing is a control; computing a volume correctly is a feature.

## 5. Integration testing — IEC 62304 §5.6

Required for Class B and absent from this project's plan until now.

**What integration testing is for here.** Every hazard in `docs/05` that matters most —
HAZ-004 wrong-subject attribution, HAZ-012 metadata corruption — is a *cross-stage*
failure. Each stage can be individually correct while the chain loses or corrupts what
it passes. Unit tests cannot see that by construction.

**Integration strategy: incremental, along the pipeline.** Stages are integrated in
pipeline order — ingestion → conversion → de-identification → splitting → inference →
SEG/SR → PACS — and the integration test at each step asserts that the fields which must
survive the whole pipeline have survived that step: **patient identity, vendor, and
voxel spacing**. Those three are the ones `docs/02` requires to be carried end to end
(SRS-054, SRS-009, SRS-017), and they are the three whose loss is invisible downstream.

Integration tests are TC-110..TC-113 and carry the `slow` marker.

## 6. Test case register

Method is **U**nit, **I**ntegration, **S**ystem or **D**ocument-integrity. "Verifies"
lists SRS, NFR and RC identifiers.

### 6.1 Gates and frozen contracts

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-000 | Package imports and reports a version | — (precondition only) | U | Import succeeds, `__version__` non-empty | yes |
| TC-001 | Label and vendor contract frozen | SRS-002, RC-020 | U | Config matches the frozen indices, names, vendor list and seed exactly | yes |
| TC-002 | No accuracy metric exists | SRS-035, RC-007 | U | `eval.metrics` exposes no accuracy function; source contains no accuracy computation | yes |
| TC-003 | Splitting confined to one module | SRS-018, RC-001 | U | Static check: no module other than `data.splits` assigns samples to train/val/test | yes |
| TC-004 | No patient overlap across splits | SRS-019, SRS-020, SRS-021, NFR-005, RC-002, RC-003, RC-005 | U | Train, val and test patient sets pairwise disjoint; every manifest patient in exactly one; test contains only the held-out vendor | yes |
| TC-005 | No default voxel spacing anywhere | SRS-055, RC-022 | U | Static check: no spacing literal or fallback default in `src/`; absence of spacing raises | yes |

### 6.2 Data ingestion and acquisition metadata

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-010 | Reader returns a complete record | SRS-001, SRS-054 | U | Pixel array, label array, patient id, vendor, spacing and source path all populated; record immutable | yes |
| TC-011 | Spacing taken from the header, anisotropy preserved | SRS-003 | U | Anisotropic fixture returns its three distinct components unchanged, in millimetres | yes |
| TC-012 | Malformed input raises, naming the path | SRS-004 | U | Raises; message contains the offending path; no partial record returned; no silent skip | yes |
| TC-013 | Layout knowledge confined to the reader | SRS-005 | U | Static check: no module other than the reader references the RETOUCH directory structure | yes |
| TC-014 | Missing spacing aborts | SRS-055, RC-022 | U | Fixture with no spacing aborts the run; no default substituted | yes |
| TC-015 | **Implausible spacing is rejected, not warned** | SRS-056, RC-023 | U | See §7.2. Includes the micrometre-valued case, which must be **rejected** | yes |
| TC-016 | Spacing is first-class through ingestion | SRS-054, RC-021 | U | Spacing present and unchanged on the record after each ingestion-stage operation | yes |
| TC-017 | MetaImage format handling | SRS-001, SRS-004, SRS-066 | U | `DimSize` (x,y,z) reshaped to (z,y,x); element type honoured rather than assumed; unknown type, truncated payload, compressed data, non-3-D and missing files all raise naming the path | yes |
| TC-018 | The archive matches what `docs/06` §3 records | SRS-001, SRS-003 | D | Subject counts 24/24/22, subject identifiers unique across vendors, per-vendor element types, and every volume's spacing passing the guard — a regression check on the figures measured 2026-09-23 | yes (`requires_data`) |

### 6.3 DICOM conversion

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-020 | Instances written as the configured SOP class | SRS-006 | U | Written objects carry `dicom.sop_class` from config; encoding via pydicom/highdicom only | yes |
| TC-021 | UIDs generated under the configured root | SRS-007, RC-015 | U | Every generated UID is prefixed by `dicom.uid_root` | yes |
| TC-022 | Conversion deterministic except UIDs | SRS-008, RC-015 | U | Two conversions of one volume differ only in UIDs; generated UIDs present in run output | yes |
| TC-023 | Vendor recoverable from the object | SRS-009, RC-008 | U | Vendor readable from the converted object without reference to directory layout | yes |
| TC-024 | Native geometry preserved | SRS-010, RC-016 | U | Slice count and spacing identical to source; no resample, pad, crop or interpolate | yes |
| TC-025 | Unestablished DICOM detail fails loudly | SRS-011 | U | With a required tag unresolved, conversion raises stating the uncertainty; no value invented | yes |
| TC-026 | Absent acquisition context aborts conversion | SRS-062, RC-029 | U | Conversion without caller-supplied context raises, naming every missing attribute and its module; no value substituted. Covers laterality, acquisition date-time, scanner model and serial | yes |
| TC-027 | Research exception omits rather than invents | SRS-063, RC-029 | U | With the exception enabled, the object is written with the affected module **absent**, not present-and-invented; a warning names every omission and the omissions appear in the run output | yes |
| TC-028 | Emitted object checked against the published IOD module table | SRS-064, RC-029 | U | Every mandatory module of the Ophthalmic Tomography Image IOD is complete, or absent by a recorded SRS-063 omission; checked against highdicom's standard-derived tables rather than against this project's own expectations | yes |

### 6.4 De-identification

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-030 | Confidentiality profile applied | SRS-012, RC-011 | U | PS3.15 Annex E applied with no retention options, per config | yes |
| TC-031 | Pseudonyms salted, salt never written | SRS-013, RC-012 | U | Pseudonym differs under a different salt; salt absent from every output file and log | yes |
| TC-032 | Pseudonyms stable across runs, not only within one | SRS-014, RC-012 | U | Same identifier and salt yield the same pseudonym in a separate process, not merely across instances in one run; a different salt yields a different pseudonym | yes |
| TC-033 | Verification reports residual tags | SRS-015, RC-011 | U | Returns the offending tag for a doctored instance; returns empty for a clean one | yes |
| TC-034 | Non-empty verification aborts the run | SRS-016, RC-011 | U | Run aborts; failing instance not skipped, quarantined or logged-and-continued | yes |
| TC-035 | Vendor survives de-identification | SRS-017, RC-008 | U | Vendor readable after the profile is applied; its loss aborts | yes |

### 6.5 Dataset splitting

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-039 | **The frame cache cannot change a value** | SRS-078 | U | Frames served from a pre-pass-populated cache are bit-identical to frames produced with caching disabled; the pre-pass decodes each volume once rather than once per frame | yes |
| TC-040 | In-domain reference set disjoint | SRS-022 | U | Reference patients drawn from training vendors, disjoint from train and val | yes |
| TC-041 | Splits seeded, persisted, reproducible | SRS-023, RC-004 | U | Same config and seed reproduce the split exactly; save/load round-trips | yes |
| TC-042 | Split construction is patient-level from the manifest | SRS-019, RC-002 | U | No B-scan assigned independently of its patient | yes |
| TC-043 | **Disjointness survives volume-to-frame expansion** | SRS-067, SRS-068, SRS-069, RC-031 | U | After expansion, no patient's frames appear in more than one split; every frame traces to a volume in the same bucket; every frame of every assigned volume is present exactly once; expansion is deterministic across executions; and expanding a deliberately overlapping split is refused | yes |
| TC-044 | Per-volume intensity window is computed at ingestion | SRS-070 | U | The window equals the 1st and 99th percentiles of the raw volume; applying it maps those to 0 and 1 and clips outside; it is present on the volume record and survives into the manifest; an 8-bit and a 16-bit volume of the same underlying signal normalise to the same values | yes |
| TC-045 | Frames inherit the volume's window | SRS-071 | U | Every expanded frame carries its source volume's window; no frame-level percentile is computed; a frame whose window differs from its volume's is rejected | yes |
| TC-046 | Target axial spacing is declared, not derived | SRS-072 | U | The target is read from `configs/train_seg.yaml`; the transform chain built for two different folds uses the identical target; no code path computes a target from the data; the value appears in the resolved run configuration | yes |
| TC-047 | Only the axial axis is resampled | SRS-073 | U | Lateral spacing is unchanged by the chain; B-scan separation is not read by any transform; a volume differing only in separation produces identical frames | yes |
| TC-048 | Metrics are computed in native geometry | SRS-074, SRS-057 | U | A prediction made at the resampled spacing and inverted returns to the native shape; the spacing used for mm³ is bit-identical to the ingestion spacing; a metric computed without inverting is detectably different | yes |
| TC-049 | **The DICOM instance and the MetaImage source agree** | SRS-010, SRS-054, SRS-066; HAZ-004 | D | For a sampled subject per vendor, the written instance and the raw volume carry bit-identical pixel data, identical shape, identical element type and bit-identical spacing. Training reads MetaImage while results are reported against DICOM, so a divergence between the two paths would attribute a measurement to an acquisition it did not come from | yes (`requires_data`) |

### 6.6 Training, uncertainty and checkpoints

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-050 | Dataloaders only from a resolved split | SRS-024 | U | Construction from an ad-hoc sample list is refused | yes |
| TC-051 | Per-volume intensity normalisation | SRS-025 | U | Normalisation statistics derive from one volume; no dataset- or vendor-level statistic used | yes |
| TC-052 | No cross-vendor geometric harmonisation | SRS-026, RC-016 | U | Preprocessing of two vendors' volumes preserves their differing geometry | yes |
| TC-053 | 2D/2.5D only | SRS-027 | U | Mode honoured from config; no 3D architecture constructible | yes |
| TC-054 | Zero dropout rejected | SRS-028 | U | Config with `dropout: 0` is refused with a reason naming MC-dropout | yes |
| TC-055 | MC-dropout returns mean and per-voxel std | SRS-029, RC-009 | U | N passes produce mean probabilities and a non-degenerate std map | yes |
| TC-056 | Scan-level confidence and review flag | SRS-030, RC-009 | U | Confidence in [0,1]; review flag set exactly when below the configured threshold | yes |
| TC-057 | Run provenance written | SRS-031, RC-018 | U | Seed, resolved config and version present in the run directory before training starts | yes |
| TC-058 | **Checkpoint provenance and integrity** | SRS-061, RC-028 | U | Checkpoint outside `artifacts/` refused; altered checkpoint fails hash check and aborts; checkpoint with no recorded hash aborts | yes |
| TC-059 | **Resuming equals not being interrupted** | SRS-075, SRS-076, SRS-077 | U | Five epochs uninterrupted against three-plus-resume-two: on CPU the resulting weights are **bit-identical**; the checkpoint carries every generator's state and restoring it reproduces the next batch order; an atomic write survives a kill mid-write; the recorded fallback list is present. On GPU the comparison is within the stated tolerance and bit-exactness is not asserted | yes |
| TC-078 | **Accumulated gradient equals the whole-batch gradient** | SRS-079 | U | On CPU, one step over 8 samples and four accumulated micro-batches of 2 produce gradients agreeing within the tolerance in §14; a micro-batch that does not divide the batch is refused; the effective batch recorded in the run output is `batch_size`, not the micro-batch. **The number lies outside this section's original TC-050..TC-059 range because that range is full**; placement here is by subject, and traceability is by identifier rather than by numeric order | yes |
| TC-079 | **Session bounds, warmup and the continuous log** | SRS-080, SRS-081, SRS-083 | U | `--max-epochs-this-session` stops after exactly that many epochs having checkpointed; a `STOP` file finishes the current epoch, checkpoints, removes the file and exits successfully, never mid-epoch; the per-epoch log is **appended** across sessions and never truncated, and each session records a boundary in it; the learning rate rises across `optim.warmup_epochs` and the schedule after warmup matches an uninterrupted one. Numbered outside §6.6's range for the reason given against TC-078 | yes |
| TC-095 | **Accelerator telemetry is recorded for the whole run** | SRS-082 | U | A telemetry file appears in the run directory, is appended at the configured interval, carries temperature, clock, utilisation and memory with timestamps, survives the sampler being unable to reach `nvidia-smi`, and stops when the run does | yes |
| TC-096 | **Stage 1 smoke run acceptance** | SRS-024, SRS-031, SRS-075, SRS-080, SRS-081, SRS-082 | D | The four criteria in §15, all of which were committed before the run | no — read from the run output |

### 6.7 Evaluation and detection

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-060 | Dice and HD95 per class | SRS-032, RC-006 | U | Both computed separately for IRF, SRF and PED against a known fixture | yes |
| TC-061 | Every metric carries CI and n | SRS-033, RC-006 | U | No metric can be emitted without a bootstrap 95% interval and sample size | yes |
| TC-062 | Bootstrap seeded and reproducible | SRS-034 | U | Two runs at one seed produce identical intervals | yes |
| TC-063 | Per-vendor breakdown with in-domain gap | SRS-036, RC-006 | U | Held-out, in-domain and their difference reported per class | yes |
| TC-064 | Results table states class, vendor, CI and n | SRS-037, RC-006 | U | Every rendered figure carries all four | yes |
| TC-065 | Detection derived, not a second model | SRS-050 | U | Static check: no classifier is trained, stored or served; no forward pass beyond the MC-dropout passes | yes |
| TC-066 | Presence threshold from configuration | SRS-051 | U | Threshold read from config, not hard-coded; resolved value written to run output | yes |
| TC-067 | AUROC score from MC-dropout mean | SRS-052 | U | Continuous score traced to the mean class probability, per class per volume | yes |
| TC-068 | Detection metrics per class and vendor | SRS-053, RC-006 | U | Sensitivity, specificity and AUROC with CI and n, broken out per class and vendor | yes |
| TC-069 | Report generation runs on CPU | NFR-003 | S | Full evaluation and report complete with no GPU present | yes |

### 6.8 SEG and SR output

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-070 | SEG written via highdicom, one segment per class | SRS-038 | U | Three segments at the frozen label indices | yes |
| TC-071 | SEG references its source instances | SRS-039, RC-013 | U | Referenced instance UIDs match the source series | yes |
| TC-072 | **Volume arithmetic from known spacing** | SRS-040, RC-024, RC-026 | U | See §7.1. Exactly predictable mm³ from a synthetic mask and anisotropic spacing | yes |
| TC-073 | Spacing bit-identical at computation | SRS-057, RC-024 | U | Spacing used for the volume compared to the ingestion value; any difference aborts before emission | yes |
| TC-074 | SR declares units explicitly | SRS-058, RC-025 | U | Every quantity in the SR carries an explicit unit; none implied | yes |
| TC-075 | SR records voxel count and voxel volume | SRS-059, RC-026 | U | Derivation recomputable from the object alone | yes |
| TC-076 | SR carries confidence and review flag | SRS-041, RC-009 | U | Both present in the SR, not only in logs | yes |
| TC-077 | Research-use designation present | SRS-042, RC-014 | U | Designation present in SEG and SR, readable by software and by a person | yes |

### 6.9 PACS communication

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-080 | STOW-RS store and WADO-RS retrieve | SRS-043 | S | Object stored and retrieved against the pinned Orthanc | written, **never executed** (`requires_pacs`) |
| TC-081 | Round-trip fidelity | SRS-044, RC-014 | S | Retrieved object matches sent in pixel data, spacing, vendor and source references | written, **never executed** (`requires_pacs`) |
| TC-082 | No action beyond store and retrieve | SRS-045, RC-017 | S | No delete, modify or reconcile; retrieving twice yields the same object | written, **never executed** (`requires_pacs`) |
| TC-083 | Client ignores ambient environment | SRS-060, RC-027 | U | With `.netrc`, proxy and certificate variables set in the environment, the client uses none of them | yes |
| TC-084 | DICOMweb URL construction and multipart wire format | SRS-043, SRS-044 | U | Instance URLs built from all three UIDs with an empty segment refused; multipart/related assembled with CRLF delimiters, per-part media type and length, and a closing boundary; parsing round-trips binary payloads exactly and **raises on a truncated body** rather than returning the parts received so far | yes |
| TC-085 | STOW-RS response parsing | SRS-043 | U | Referenced and failed instance UIDs both read; a response reporting failures is not treated as success | yes |
| TC-086 | Client exposes no mutating operation | SRS-045, RC-017 | U | Static check: no delete, modify, reconcile or sign-off method, and the source issues only GET and POST | yes |

**TC-080, TC-081 and TC-082 have never been run.** They were written on 2026-09-19 in
an environment with no Docker, so no Orthanc existed to execute them against. They are
written against the DICOMweb specification rather than against observed server
behaviour, which is the better order — a test written against a live server encodes what
that server happens to accept — but it means their first execution may fail for either
of two reasons: the client is wrong, or the specification requires something Orthanc does
not implement. The second is a `docs/11` finding, not a defect.

Until someone reports a run, these three carry no evidence and must not be counted as
verification.

### 6.10 Inference API

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-090 | Inference response contents | SRS-046 | S | Object identifiers, per-class mm³, confidence and review flag all present | yes |
| TC-091 | Response is a candidate; no sign-off | SRS-047, RC-017 | S | Response marked as requiring review; no endpoint records, finalises or approves | yes |
| TC-092 | Out-of-scope input rejected | SRS-048, RC-010 | S | Rejected with a stated reason; no segmentation returned | yes |
| TC-093 | Health endpoint | SRS-049, RC-018 | S | Reports status, software version and loaded model identifier | yes |
| TC-094 | Inference reaches no network but the configured PACS | NFR-006 | S | With outbound traffic blocked except the configured DICOMweb endpoint, inference completes; any other host attempted is a failure | yes |
| TC-087 | **Multipart form handling through a real FastAPI route** | SOUP-009, SOUP-015, SRS-046 | U | A form carrying a text field and a file round-trips with the bytes unaltered; a missing required part is rejected with 422 rather than accepted; `python-multipart` imports under whichever module name this Starlette uses; the installed versions are the pinned ones. **Registered here on 2026-09-30**: the identifier was used by `tests/test_multipart_upload.py` from 2026-09-28 with no row in this register — see TC-109 | yes |

## 7. Protocols for the cases that need stating precisely

### 7.1 TC-072 — volume arithmetic

The test that would have caught HAZ-012. Constructed so the expected value is arrived at
independently of the implementation, per §3 rule 4.

**Fixture.** A synthetic label volume, deliberately anisotropic, with a known voxel
count per class:

| | Value |
|---|---|
| Spacing | 0.0039 mm axial × 0.0117 mm lateral × 0.047 mm between B-scans |
| Voxel volume | 0.0039 × 0.0117 × 0.047 = 2.14461 × 10⁻⁶ mm³ |
| IRF voxels | 1,000 → expected 2.14461 × 10⁻³ mm³ |
| SRF voxels | 10,000 → expected 2.14461 × 10⁻² mm³ |
| PED voxels | 0 → expected 0.0 mm³ |

**Acceptance.** Reported volume equals the expected value to within floating-point
tolerance, for each class; the reported voxel count equals the fixture count (SRS-059);
and the reported voxel volume equals the product above.

**Why anisotropic.** Isotropic spacing hides the entire class of defect where components
are transposed or collapsed to a single value: with equal spacings, a wrong axis order
gives the right answer.

### 7.2 TC-015 — the micrometre case

**The defect.** Axial resolution is conventionally quoted in micrometres. A spacing of
3.9 — the micrometre value of 0.0039 mm — is not implausible-looking to a reader and is
a 1000× volume error.

| Case | Spacing offered | Required outcome |
|---|---|---|
| Valid | 0.0039 mm axial | Accepted |
| **Micrometre-valued** | **3.9** (µm read as mm) | **Rejected**, naming the component and the permitted range |
| Zero | 0.0 | Rejected |
| Negative | −0.0039 | Rejected |
| Absent | field missing | Rejected (also TC-014) |
| Collapsed | three equal components where the vendor's are anisotropic | Rejected |

**Acceptance.** Every non-valid case **rejects the volume**. A warning, a log line or a
clamped value is a failure of this test. The per-vendor permitted ranges come from
`configs/data.yaml` and are stated in millimetres with the unit declared.

### 7.3 TC-105 — intended use change gate

Resolves `docs/03` open item 6.

**Method.** A recorded hash of `docs/01` §2 (indications for use) is stored in the test.
The test fails when the current hash differs and `docs/03` has not been modified in the
same change.

**The detail this needs to settle.** "Modified in the same commit" is not directly
observable in CI, which tests a merge result rather than a commit. The mechanism adopted
is therefore: the test compares the stored hash against §2's current content and fails on
any difference, and the only way to make it pass is to update the stored hash — which is
a deliberate edit that the reviewer sees alongside whatever change to `docs/03`
accompanied it. The gate is a forcing function for review, not an automated proof of
re-classification. Stating that limit is part of the test's specification.

## 8. Document and configuration integrity

Not an IEC 62304 level. These tests exist because this project's documents make claims
about each other and about the code, and nothing else checks them.

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-100 | Nothing under `data/` or `artifacts/` is tracked | NFR-004, RC-019 | D | No tracked file under either path except `.gitkeep` | yes |
| TC-101 | Pins and SOUP list agree | NFR-001 | D | Every pin in `pyproject.toml` appears in `docs/04` at the same version, and conversely | yes |
| TC-102 | Module docstrings cite real requirements | NFR-008, A6 | D | Every `SRS-nnn` named in a module docstring exists in `docs/02`; every module in `docs/02` §3.10 exists | yes |
| TC-103 | SOUP list cites real requirements | — (`docs/04` open item 6) | D | Every SRS identifier in `docs/04` exists in `docs/02` | yes |
| TC-104 | Traceability matrix is current | NFR-008 | D | `docs/09` coverage counts recomputed from `docs/01`, `docs/02`, `docs/05` match what it states | yes |
| TC-105 | Intended use change gate | — (`docs/03` open item 6) | D | See §7.3 | yes |
| TC-106 | Image digests match the SOUP list | — (`docs/04` open item 9) | D | Digests in `docker/Dockerfile.api` and `docker/docker-compose.yml` equal SOUP-017 and SOUP-014 | yes |
| TC-107 | Change control log touched | NFR-007 | D | A commit introducing a new `URS`/`SRS`/`NFR`/`HAZ`/`RC`/`TC`/`SOUP` identifier in `docs/` also stages `docs/13`. Implemented as a `commit-msg` hook, `scripts/check_change_control.py` | partial — implemented 2026-09-19 |
| TC-108 | Cited commit SHAs resolve | NFR-008 | D | Every commit SHA cited in `docs/`, `scripts/`, `CLAUDE.md` or `.pre-commit-config.yaml` resolves to a commit reachable from `main` | yes |
| TC-097 | **The shipped config matches the recorded hardware decisions** | SRS-031; `docs/13` 2026-09-26 | D | `configs/train_seg.yaml` has `train.amp: false`, matching the measured AMP decision and the run conditions pre-registered in §15; `micro_batch_size` divides `batch_size`; `cache_dir` is not on the system volume. A decision recorded only in prose is one nothing enforces — §3 rule 8 | yes |
| TC-098 | **Every module under  imports** | NFR-001, NFR-008 | U | Walking the package and importing every module succeeds. A module that cannot be imported is not covered by any test that never imports it, so a green suite says nothing about it — §3 rule 8 | yes |
| TC-099 | **The installed environment matches `requirements.lock`** | NFR-002, NFR-001 | D | Every applicable locked entry is installed at the locked version and nothing installed is absent from the lock; the lock carries no local build label on torch; Windows-only entries carry platform markers; and where the installed torch build differs from the lock, the build variant is **recorded** in `docs/04` and the README rather than tolerated | yes |
| TC-088 | **Standing decisions are enforced where enforcement is possible** | NFR-008; `docs/07` §16 | D | The UID root is declared where conformance is stated; `batch_size` has exactly one home; the training data path references no `pydicom`; persisted splits name subjects not UIDs; no accuracy function exists; §15's pre-registered baselines are still stated. **Registered 2026-09-30** — used by tests from 2026-09-28 with no row, see TC-109 | yes |
| TC-089 | **The deterministic loss matches MONAI back to back** | SRS-084 | U | `DeterministicDiceCELoss` agrees with `monai.losses.DiceCELoss` on random inputs to `rtol=1e-5`, `atol=1e-7`, and their gradients to `rtol=1e-4`; a deliberately altered `lambda_ce` is rejected by that tolerance; and on CUDA under `use_deterministic_algorithms` the reference emits an `nll_loss2d` fallback while the replacement emits none. **Registered 2026-09-30** — see TC-109 | yes |
| TC-109 | **Every test's identifier is registered, and the run record cannot contradict itself** | NFR-008, SRS-077 | D | Every `TC-nnn` appearing in a test function name has a row in §6 or §8 of this document; and `run.json` may not report `deterministic_algorithms: true` while `determinism.json` lists any fallback. Added 2026-09-30 after TC-087 was used by a test for two days with no register row — the `commit-msg` hook passed it because the identifier appeared in the `docs/13` entry that the hook requires, so it satisfied its own condition | yes |

TC-107 is marked partial deliberately: it can check that a change control entry exists,
not that what was written there is true. That is a review activity, not a test, and
pretending otherwise would overstate what automation buys.

**It was implemented on 2026-09-19 in response to a real incident.** Commit `3c16231`
added SRS-065 to `docs/02` and did not touch `docs/13`; its message described an entry
its patch script had failed to write, and the commit proceeded anyway. Measured against
all 37 commits then in the repository, this rule fires exactly once — on that commit —
and the more obvious rule, failing a message that names an untouched `docs/` file, fires
zero times and would **not** have caught it, because `3c16231` did touch `docs/11`.
Both hooks are installed; only one of them earns its place on the evidence.

**The SHA above was reassigned on 2026-09-23.** The history was rewritten that day to
strip co-author trailers from 44 commit messages; content was untouched and every tree
hash is unchanged, but each commit from the root onward received a new SHA. The incident
commit was `104342b` before the rewrite and is `3c16231` after it. A clone taken before
that date resolves the old one and not the new.

The measurement in the paragraph above is unaffected — it counts commits by content, not
by name, and the contents did not move. **TC-108 now checks that every SHA cited in the
documents still resolves**, because nothing did when this one stopped resolving.

## 9. Integration test register — §5.6

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-110 | Identity, vendor and spacing survive ingestion → conversion → de-identification | SRS-054, SRS-009, SRS-017, RC-021, RC-008 | I | All three fields present and unchanged at every stage boundary | yes (`slow`) |
| TC-111 | Overlap assertion runs at training start | SRS-020, RC-002 | I | Training on a deliberately overlapping split aborts before the first step | yes (`slow`) |
| TC-112 | Inference → SEG/SR → PACS → retrieve | SRS-043, SRS-044 | I | End-to-end chain produces a retrievable object matching the inference result | yes (`slow`, `requires_pacs`) |
| TC-113 | Two runs from one config agree | NFR-002 | I | Identical seeds and config produce identical splits, metrics and intervals | yes (`slow`) |

## 9a. Independent cross-verification register

A block of its own, because these tests verify nothing about a requirement directly.
They check that an implementation agrees with a second, independently written one.

Two implementations agreeing is stronger evidence than either alone, and it is the
standard answer to the risk a reimplemented metric carries: that it is self-consistent,
passes every fixture written by the same person who wrote the code, and is wrong.

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-120 | Dice and HD95 agree with MONAI back to back | SRS-032, RC-006 | U | Over randomly generated mask pairs, `ocuval.eval.metrics` and the corresponding MONAI metric agree within tolerance for both Dice and HD95 | yes (`slow`) |
| TC-124 | **Confidence intervals resample patients, not measurements** | SRS-087, SRS-033, SRS-034 | U | `bootstrap_ci_grouped` reports `n` as the patient count with its unit named; on clustered data its interval is materially wider than the naive one (measured ~3.2x at cluster size 10, against sqrt(10)=3.16 expected), while on unclustered data the two agree within 25% -- a negative control, so the extra width is the correlation and not the implementation. Reproducible from the seed, and a patient whose only value is NaN does not count as evidence | yes |
| TC-125 | **The test and in-domain reference splits are sealed, and every access is counted** | SRS-088; `docs/07` §17.1, §17.5 | U | Both sealed buckets refuse without an `Unlock`; an `Unlock` opens one named bucket only and cannot be constructed without a reason and an approver; `val` needs nothing. Every access appends to a durable log carrying the time, bucket, fold, reason, approver and the count of prior accesses, and the count is read from the file so restarting cannot reset it. `evaluate` is gated, not merely gateable | yes |
| TC-126 | **The evaluation record carries per-volume rows from which every aggregate is recomputable** | SRS-089; `docs/08` D7 | U | `evaluate` emits one row per volume per class with identifiers, vendor, Dice, HD95, `reference_present` and both voxel counts. Recomputing each per-class, per-vendor Dice and HD95 aggregate from those rows reproduces the reported value exactly, and `reference_present` agrees with the detection arm's definition on every volume. Adding the rows changes no aggregate: the same inputs evaluated with and without them give identical segmentation and detection blocks | yes |
| TC-127 | **The exact record comparison treats NaN-in-both as equal, and nothing else as close** | SRS-090; `docs/13` 2026-10-04 | U | Two records identical except for metrics undefined in both compare as identical. NaN on one side only is a difference, in both directions. A change to the next representable double is a difference. A missing leaf is a difference. Only the four named top-level keys are excluded, and the same names deeper in the record are compared. Exit status is 0, 1 or 2 for identical, different or unreadable. The comparator before this fix fails the NaN case | yes |
| TC-123 | **Two independently configured GPU runs agree exactly while their schedules coincide** | SRS-076, SRS-077, SRS-083, SRS-084, SRS-085; CLAUDE.md rule 4 | U | `cirrus_holdout_stage1b` (`--epochs 20`, two sessions, resumed at epoch 3) and `cirrus_holdout_stage2` (`--epochs 150`, one session) agree **exactly** on `train_loss`, `val_dice` and `per_class_dice` for every epoch whose learning rate they share, and the mean training loss over epochs 0–2 is 1.648121 in both. Divergence begins at the first epoch trained under a differing rate and not before, which the test asserts as a boundary rather than merely tolerating. The strongest evidence for rule 4 on GPU: it spans different fold lengths, different session structures and a resume. Marked `requires_data` — the run directories are gitignored | yes (`requires_data`) |
| TC-122 | **The run record identifies the code, and a dirty tree refuses to run** | SRS-086, SRS-031; NFR-002 | U | `run.json` carries `source.commit`, `source.branch` and `source.dirty`; `commit` is never reported without `dirty` beside it; there is **no** top-level `seed` field, the seed having exactly one home in `resolved_config`; `require_clean_tree` raises on a dirty tree and on a missing commit, and permits both only under an explicit override that is itself recorded | yes |
| TC-121 | **Two GPU runs of one configuration agree bit-for-bit** | SRS-076, SRS-077, SRS-084, SRS-085; CLAUDE.md rule 4 | U | Two independent runs of the same fold, seed and configuration produce **byte-identical** model weights, optimiser state and per-epoch loss log, and `determinism.json` records **zero fallbacks**. Both halves are required: zero fallbacks means no operation announced non-determinism, which is not the same claim as two runs agreeing — §3 rule 8. Marked `requires_data` and `slow`; it is the evidence for rule 4 on GPU and rule 4 is not claimed achieved there without it | yes (`slow`, `requires_data`) |

TC-120 is marked `slow` because it imports the torch stack, which the rest of the metric
suite deliberately does not need (CLAUDE.md §4). It does **not** need `requires_data`: the
masks are generated, not read.

A disagreement is not automatically a defect in this project's implementation — the two
may define an edge case differently, and this project's definitions are fixed in `docs/13`
under rule 6. A disagreement is a finding to be explained, and the explanation belongs in
`docs/13` whichever way it resolves.

## 10. Traceability summary

Coverage is computed from the documents, not asserted here — TC-104 exists to keep this
section honest, and `docs/09` carries the authoritative counts.

| Level | Allocated |
|---|---|
| Independent cross-verification (§9a) | TC-120 |
| Unit (§5.5) | TC-000..TC-005, TC-010..TC-016, TC-020..TC-025, TC-030..TC-035, TC-040..TC-042, TC-050..TC-058, TC-060..TC-068, TC-070..TC-077, TC-083 |
| Integration (§5.6) | TC-110..TC-113 |
| System (§5.7) | TC-069, TC-080..TC-082, TC-090..TC-094 |
| Document integrity (§8) | TC-100..TC-107 |

## 11. Deviations and their handling

A deviation is any departure from this protocol during execution: a test not run, a test
run differently, or an acceptance criterion changed.

1. Deviations are recorded in `docs/08` against the test case, with the reason.
2. A deviation that changes an acceptance criterion is a change to this document and
   goes in `docs/13` with a rationale (NFR-007).
3. **TC-004 may not be deviated from** under any circumstance. CLAUDE.md rule 2, RC-003
   and `docs/05` §6.3 all depend on it running.
4. A test that cannot be run because its subject does not exist yet is not a deviation —
   it is the current state (§1.2). It becomes a deviation once the module exists.

## 12. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | 45 of the 80 allocated test cases are unimplemented (§1.2). This protocol is a specification, not a result. | Milestones 3–7 |
| 2 | TC-107 cannot verify that a change control entry is *correct*, only that one exists (§8). No automation closes that; it is a review activity. | — |
| 3 | TC-105's gate forces review rather than proving re-classification (§7.3). If a stronger guarantee is wanted it needs a commit-level check outside pytest. | — |
| 4 | Validation, as distinct from verification, is not performed and cannot be (§1.1). `docs/08` must state this rather than letting a full verification table imply it. | `docs/08` |
| 5 | No test verifies that a recorded checkpoint hash is itself correct — RC-028 degrades to trust-on-first-write (`docs/05` open item 7). TC-058 inherits that limit. | `docs/05` |
| 6 | ~~Per-vendor spacing plausibility ranges do not exist in `configs/data.yaml`.~~ **Closed 2026-09-25.** Measured from all 70 training volumes and implemented under SRS-056; the 0.5 mm physical bound is retained as an outer guard. §13 records the ranges and which bound rejects. | — closed |
| 7 | `io/deident.py` applies a **subset** of the PS3.15 Annex E attribute table, and its verification checks exactly that subset — so neither half can detect an identifying attribute the table omits. Closing this needs the standard's full table. | `docs/11` |

---

## 13. Per-vendor spacing plausibility ranges — closing item 6

Measured 2026-09-25 from all 70 volumes of the RETOUCH training partition, the only
partition held (`docs/06` §2.1). Implemented in `configs/data.yaml` under SRS-056 and
applied by `io.retouch_reader.validate_spacing`.

### 13.1 What was measured

Components are in this project's order, **(axial, lateral, separation)**, which is not
the MetaImage header order. Values in millimetres.

| Vendor | n | Axial | Lateral | Separation |
|---|---|---|---|---|
| cirrus | 24 | 0.001955 | 0.011742 | 0.046878 – 0.047244 |
| spectralis | 24 | 0.003872 | 0.010856 – 0.011950 | 0.116380 – 0.128624 |
| topcon | 22 | 0.002600 – 0.003500 | 0.011720 | 0.046880 |

Cirrus and Topcon are near-identical in lateral and separation and differ almost twofold
in axial. Spectralis separates from both on separation by a factor of about 2.5.

### 13.2 The configured range, and why the margin is two

Each configured range is the measured range **divided by two at the low end and
multiplied by two at the high end**. The margin exists because these are the training
partition's extremes, not the population's — the test partition was deliberately not
downloaded — so an unseen volume may legitimately fall outside what was observed.

The factor is measured, not chosen by taste. Three candidates were evaluated against
both properties the range has to satisfy at once:

| Margin | Real volumes accepted | Axial/lateral transposition rejected |
|---|---|---|
| ×1.5 | 70 / 70 | 70 / 70 |
| **×2** | **70 / 70** | **70 / 70** |
| ×3 | 70 / 70 | **3 / 24 on spectralis** |

Two sits inside the working band with room on both sides; three is past the edge, where
Spectralis's axial and lateral ranges begin to overlap and a transposed pair lands
inside the permitted range. ×1.5 works equally well but leaves less headroom for unseen
acquisitions, which is the whole reason a margin exists.

### 13.3 Which bound rejects

Each of the 70 real spacings was perturbed by each realistic defect class and passed to
the validator, recording which bound fired. "Structural" means the present / three
components / numeric / finite / positive / anisotropic checks.

| Defect | Outer 0.5 mm | Per-vendor | Structural | Missed |
|---|---|---|---|---|
| Micrometres read as millimetres (×1000) | **70** | 0 | 0 | 0 |
| Centimetres read as millimetres (×10) | 24 | **46** | 0 | 0 |
| Axial/lateral transposed | 0 | **70** | 0 | 0 |
| Lateral/separation transposed | 0 | **70** | 0 | 0 |
| Full reversal to MetaImage (x, y, z) order | 0 | **70** | 0 | 0 |
| Collapsed to isotropic | 0 | 0 | **70** | 0 |

Real volumes accepted by their own vendor's range: **70 / 70**. Nothing was missed by
every bound.

**The answer to "which bound rejected" is that it depends on the defect, and the split
is not incidental.** The outer bound catches gross unit errors and nothing else. It
rejects **zero** of the 210 axis-order cases, because a transposed spacing is physically
small in every component — 0.011742 mm is a perfectly plausible OCT number, it is simply
the wrong axis's number. The per-vendor range is the only control in the pipeline that
sees that class.

That class is HAZ-012, and it is the one `docs/13` (2026-09-23) records as producing a
volume in mm³ wrong by a factor of six from a segmentation that is entirely correct,
with nothing visible in the mask, the image or on a review screen. Before 2026-09-25 the
only thing standing between that defect and a reported number was `spacing_from_header`
being written correctly. There is now a second, independent check.

### 13.4 What these ranges are not

- **Not vendor specifications.** They are what this archive contains. A vendor may
  support modes RETOUCH does not include, and a volume from such a mode would be
  rejected as implausible when it is merely unrepresented. The failure is loud and names
  the vendor, axis and range, so it is diagnosable — which is the trade SRS-056 makes.
- **Not a substitute for the physical bound.** A vendor with no configured range falls
  back to the 0.5 mm bound rather than being refused, so the reader stays usable on new
  data. TC-015 asserts that the configured vendors and `vendors:` in `configs/data.yaml`
  are the same set, because a vendor silently dropping to the weaker bound would not
  otherwise fail anything.
- **Not stable if the archive changes.** They were measured from 70 volumes on one date.
  Re-measuring is a change control event under rule 6.

---

## 14. Gradient accumulation equivalence — the tolerance for TC-078

**Why accumulation is equivalent here at all.** Summing the gradients of four
micro-batches of two, each loss scaled by one quarter, equals the gradient of one batch
of eight **only if no operation in the network couples samples within a batch**. The
network built from `configs/train_seg.yaml` uses **`InstanceNorm2d` — eight layers, and
zero batch-normalisation layers**, verified 2026-09-25 by inspecting the constructed
module tree rather than by reading the MONAI defaults. Instance normalisation computes
its statistics per sample and per channel, so a sample's activations do not depend on
which other samples share its micro-batch.

**Had it been batch normalisation, accumulation would not be equivalent** and no
tolerance would have made it so: batch-norm statistics over two samples differ from
statistics over eight, so the accumulated gradient would be the gradient of a *different
function*, not a rounding-error approximation of the same one. That is why the layer is
checked before the equivalence is relied on, and why a batch-norm finding is a stop
rather than a tolerance adjustment.

**The tolerance is for floating-point summation order, nothing else.** The two paths add
the same quantities in different orders, and float addition is not associative. The
bound is therefore relative:

| Device | Tolerance | Basis |
|---|---|---|
| CPU, float32 | `rtol = 1e-4`, `atol = 1e-6` on each gradient tensor | Accumulated reordering over four additions at float32 |
| CUDA, float32 | `rtol = 1e-4`, `atol = 1e-6` — **unchanged** | Measured 2026-09-30: needs `atol = 1.3e-09`, three orders inside the bound |
| **CUDA, AMP** | **`rtol = 1e-4`, `atol = 5e-5`** | Measured 2026-09-30 over 72 cases: worst needs `1.96e-05`. See below |

**Re-measured 2026-09-30 after AMP was enabled and the loss replaced** (`docs/13`). The
quantity measured is the smallest `atol` that satisfies `torch.allclose` elementwise at
`rtol = 1e-4`, which is `max(|a-b| - rtol·|b|)` over every element — not a ratio against a
tensor's maximum, which says nothing about the element that actually violates.

| Configuration | max abs deviation | `atol` needed | Inside `atol = 1e-6`? |
|---|---|---|---|
| CPU fp32, `dice_ce` | 6.15e-08 | 1.88e-10 | yes |
| CPU fp32, `dice_ce_deterministic` | 6.15e-08 | 1.88e-10 | yes |
| CUDA fp32, `dice_ce` | 2.79e-09 | 1.34e-09 | yes |
| CUDA fp32, `dice_ce_deterministic` | 2.79e-09 | 1.34e-09 | yes |
| CUDA AMP, `dice_ce`, 12 seeds × 2/4/8 steps | 1.96e-05 | **1.96e-05** | **no** |
| CUDA AMP, `dice_ce_deterministic`, 12 seeds × 2/4/8 steps | 1.20e-05 | **1.20e-05** | **no** |

The AMP rows are the worst of **36 measurements each**; means were 4.5e-06 to 6.8e-06, so
the worst case is roughly 3× the typical one and a bound set near the mean would fail
intermittently.

**This bound was got wrong once, in the obvious way.** It was first set to `atol = 1e-5`
from a **single seed** that needed 6.0e-06. The very next seed measured needed 1.53e-05 and
the test failed. A tolerance derived from one sample is a guess wearing a measurement's
notation, and the correction is recorded here rather than quietly applied: the seeds are now
parametrised in TC-078, including the two that produced the worst deviations.

**Two conclusions, and the first is the one that was in doubt.** Replacing the loss does
**not** move the tolerance — the fp32 figures are identical to ten significant figures for
both losses, and under AMP the deterministic loss is if anything slightly *tighter*
(1.20e-05 against 1.96e-05). That is what a substitution rather than an approximation should
look like, and is independent evidence for the claim TC-089 makes, reached by a different
route. **AMP does** move it, by a factor of 50, and `atol = 5e-5` leaves 2.55× headroom over
the worst of the 72 measurements.

**Why this widening is not the thing CLAUDE.md forbids.** The standing decision says that
under batch normalisation accumulation is invalid and the response is to stop accumulating,
never to widen the tolerance. That case is categorically different: batch norm makes the
accumulated gradient the gradient of a *different function*, and no tolerance is correct.
Here the function is identical and only the arithmetic precision changed, which is exactly
what this tolerance has always been for. The structural precondition — instance norm, zero
batch-norm layers — is unchanged and still asserted first.

**And it is dormant.** `configs/train_seg.yaml` sets `micro_batch_size: 8` against
`batch_size: 8`, so `accumulation_steps` is 1: there is nothing to accumulate and no
summation to reorder. The AMP tolerance therefore binds no planned run. It is measured and
recorded now rather than when a smaller card forces accumulation, because that is when
nobody will want to stop and measure it.

**What the tolerance does not certify.** Staying inside it is not proof that
accumulation is implemented correctly — a bug that scaled every gradient identically
would also stay inside it. TC-078 therefore also asserts the negative case: omitting the
`1/steps` loss scaling produces a gradient that is **outside** the tolerance, so the test
can distinguish correct accumulation from no accumulation at all. **That negative case is
re-asserted at the wider AMP tolerance**, because a bound loosened by 50× is only a bound
if it still rejects the error it was written to catch.


---

## 15. Stage 1 smoke run — acceptance criteria, pre-registered

**Committed before the run.** These criteria exist to be failable. A criterion written
after seeing the numbers is a description, not a test, so the commit that adds this
section precedes the commit that records any result — the history is the evidence of
which came first.

**Run under test.** `cirrus_holdout`, the fold with the fewest training frames (2610
train, 580 in-domain validation), ~20 epochs, on the local GTX 1050 at micro-batch 8
with AMP off. Evaluated on the **in-domain validation split**: unseen patients from the
training vendors. The held-out vendor is not touched at Stage 1 — that is Stage 2, and
looking at it now would spend the result the project exists to report.

### 15.1 Criterion 1 — training loss decreases materially

The mean training loss of the **last three epochs** shall be **at least 10% below** the
mean of the first three.

Ten percent, not "decreases", because a loss that drifts down by a fraction of a percent
over twenty epochs is indistinguishable from noise and would pass a bare inequality. The
figure is deliberately modest: twenty epochs of a 2.64 M-parameter network on 2610 frames
is not expected to converge, only to show that optimisation is working at all.

### 15.2 Criterion 2 — validation Dice beats both baselines, per class

Per-class in-domain validation Dice shall exceed **both** of the following.

**Baseline A — the all-background predictor.** Predicts background everywhere. Its Dice
is **0.000** for every fluid class on every frame where that class is present. Beating it
means only that the model predicts the class somewhere, ever. It is the floor, not the
bar.

**Baseline B — the spatial prior.** A predictor that **ignores the image entirely**: for
each class, the fixed set of pixels where that class occurs in at least 2% of training
frames, the same mask predicted on every B-scan. The threshold was tuned on the training
split and the figure below measured on validation, so it is given the same fair treatment
any method would get. Computed 2026-09-26, before the run
(`artifacts/benchmarks/stage1_baseline.json`):

| Class | Prior pixels | Val frames with the class | **Baseline B val Dice** |
|---|---|---|---|
| IRF | 10 855 | 236 / 580 | **0.0451** |
| SRF | 12 748 | 173 / 580 | **0.0428** |
| PED | 22 669 | 126 / 580 | **0.0384** |

**Why this baseline and not a random or prevalence one.** Random and
predict-everything baselines score near zero and are trivially beaten, so they test
nothing. The spatial prior encodes the one thing a model could learn *without looking at
the pixels* — that fluid appears in characteristic retinal locations. Failing to beat it
means the network has learned anatomy-independent position and not image content.

**Expected difficulty, stated in advance.** PED occurs in 126 of 580 validation frames
and is the rarest. If PED alone falls short while the loss criterion passes and IRF and
SRF clear their bars, that is a **recorded observation about class rarity at twenty
epochs — not a pass**. The decision whether to proceed is the author's and is written
into `docs/13` with its reasoning. What is not permitted is quietly lowering this table.

### 15.3 Criterion 3 — no class collapses to always-empty

For each fluid class, the number of validation frames in which the model predicts **at
least one voxel** of that class shall be **greater than zero**, and the model shall not
predict a class on **zero** frames across the whole validation split.

A network can reach a respectable mean Dice by learning the two commoner classes and
never emitting the third, and a per-class mean that excludes absent-absent frames will
not reveal it. This criterion is checked by counting predicted frames per class, which is
a property of the mechanism rather than of the score — `docs/07` §3 rule 8.

### 15.4 Criterion 4 — the run's own records exist

All of the following shall be present in the run directory afterwards:

| Artefact | What its absence would mean |
|---|---|
| `last.pt` and `best.pt`, both in `checkpoints.sha256` | The run cannot be resumed or audited (SRS-061, SRS-075) |
| A successful **resume**: stopping via `STOP` or `--max-epochs-this-session`, restarting, and the epoch log continuing rather than restarting | The safety net is untested on a real run (SRS-080) |
| `determinism.json`, including its `fallbacks` list | Non-deterministic kernels went unrecorded (SRS-077) |
| `epochs.jsonl`, appended, with `session_start` and `session_end` boundaries | The training curve is not a single record (SRS-081) |
| `gpu_telemetry.csv`, covering the whole run | No thermal record, so a slow epoch cannot be explained and `docs/08` has no environment (SRS-082) |
| `run.json` with the resolved configuration and seed | The run is not reproducible from the repository (SRS-031) |

### 15.5 What a failure means

A failed criterion stops Stage 2. It does not get the criterion rewritten. The failure,
its investigation and its resolution go into `docs/13` in the ordinary way, and Stage 2
begins only once the cause is understood — which may legitimately conclude that the
criterion was wrong, but that conclusion is a recorded argument, not an edit.

### 15.6 Stage 1b — the same criteria under the final configuration

**Committed before the run, as §15 was.** Stage 1 passed (`docs/08` §5), and then three
things changed underneath it: resume equivalence was fixed, the deterministic loss was
adopted, and **AMP was reversed from off to on** because the AMP-off decision had been
priced without the determinism the loop requests (`docs/13`, 2026-09-30). Stage 1's result
was therefore produced under conditions Stage 2 will not use, and `docs/08` D2 records
that it is not reproducible by the current code at all.

Stage 1b re-establishes the smoke result under the configuration Stage 2 will actually
run: **`dice_ce_deterministic`, determinism requested, and AMP on**. It costs ≈1.4 h,
which is cheap against the ≈37 h the three folds need.

**§15's conditions are not edited to match.** A pre-registration records what was
committed before a run; Stage 1 ran with **AMP off** and §15 says so permanently. TC-088
asserts both strings are present, in their own subsections.

#### Conditions

| Field | Stage 1 | **Stage 1b** |
|---|---|---|
| Fold | `cirrus_holdout` | `cirrus_holdout` — unchanged |
| Epochs | ~20 | **20** |
| Loss | MONAI `DiceCELoss` | **`dice_ce_deterministic`** (SRS-084) |
| AMP | **off** | **on** |
| Micro-batch / effective | 8 / 8 | 8 / 8 — unchanged |
| Determinism | requested; **1 op fell back** | requested; **0 fallbacks expected** |
| Sessions | 2, stopped by `STOP` at epoch 16 | **2, stopped by `--max-epochs-this-session 3`** |
| Evaluation split | in-domain validation | in-domain validation — unchanged |

**The session split is deliberate and does double duty.** Stopping after epoch 2 and
relaunching puts the resume boundary **inside the warmup window** (`optim.warmup_epochs:
5`), which is the case `SequentialLR`'s position in its own sequence has to survive, and
which no run has yet exercised on GPU. `--max-epochs-this-session` rather than `STOP`,
because `STOP` is a race against a 30 s poll and landed thirteen epochs late on Stage 1
(`docs/08` D1).

#### Criteria — the four §15 thresholds, unchanged

1. **Loss decreases materially.** Mean training loss of the last three epochs at least
   **10%** below the mean of the first three.
2. **Validation Dice beats both baselines, per class.** Baseline A, the all-background
   predictor, **0.000**. Baseline B, the spatial prior measured before Stage 1 and not
   recomputed: **IRF 0.0451, SRF 0.0428, PED 0.0384**.
3. **No class collapses to always-empty.** Each fluid class predicted on more than zero
   validation frames.
4. **The run's own records exist**, per the §15.4 table.

**No threshold is relaxed, and none is tightened either.** Tightening would be as much a
rewrite as relaxing: the comparison Stage 1b exists to make is between configurations, and
it is only a comparison if the bar is the same. Stage 1's measured values are **not** the
bar — a criterion of "at least as good as Stage 1" would be a criterion invented after
seeing a result.

#### Criterion 5, new and specific to this stage — determinism is measured, not inferred

`determinism.json` shall record **zero fallbacks**, and, separately, **two runs of two
epochs under this configuration shall agree bit-for-bit** on model weights, optimiser
state and the per-epoch loss log.

The second half is the load-bearing one. Zero fallbacks means no operation *announced*
non-determinism; it does not establish that two runs agree, and the two are not the same
claim — an operation with no warning can still be order-dependent. This is `docs/07` §3
rule 8: the observable output of a deterministic run and a nearly deterministic one is
identical until you compare two of them. **TC-121** performs the comparison.

If TC-121 fails, CLAUDE.md rule 4 is **not** achieved on GPU, and the disposition is
recorded rather than the claim softened.

#### What a Stage 1b failure means

As §15.5. A failed criterion stops Stage 2 and goes into `docs/13`. Stage 1 having passed
does not license Stage 1b to be re-interpreted: if a criterion Stage 1 met is missed under
the faster configuration, that is a finding about the configuration.

---

## 16. Standing decisions — what enforces each one

**Why this audit exists.** On 2026-09-28 a Stage 1 run was launched under conditions
contradicting a standing decision, because the AMP decision lived only in `docs/13` and
`CLAUDE.md` and nothing compared it against the configuration that drives the run. That
is §3 rule 8, and it prompted the obvious question of every *other* standing decision:
is this enforced, or does it survive only because someone remembers it?

The answer for five of them was "nobody checks". Those now have tests. Four cannot be
enforced by a test at all, and saying so explicitly is the point of the table — **a
decision known to be unenforceable is a different thing from one assumed to be safe.**

### 16.1 Enforced

| Standing decision | Enforced by |
|---|---|
| Refuse, or omit — never fill (RC-029) | TC-026, TC-027 — the strict path refuses, and every omission is counted and recorded |
| Fluid classes use the declared private scheme `99OCUVAL` | TC-074, TC-076 — the scheme is declared in the object whenever its codes are used |
| **The UID root stays an unregistered placeholder, declared** | **TC-088 (new)** — the configured root appears in `docs/11` and that document describes it as unregistered |
| HD95 is max-of-directed, not pooled | TC-120 — independent cross-check against MONAI, which is how the defect was found |
| Per-vendor spacing ranges are the only control that sees an axis transposition | TC-015 — a transposed pair is rejected per vendor and accepted by the physical bound alone |
| Intensity normalisation is a per-volume percentile window computed at ingestion | TC-044, TC-045 — the window is a property of the volume, inherited by every frame, and the transform refuses to compute one |
| Axial resampling targets a declared coarsest common spacing | TC-046 — the target comes from the configuration, is identical across folds, and is at or above every measured axial spacing |
| B-scan separation is not used by the transform chain | TC-047 — two samples differing only in separation produce identical frames |
| **Training reads the archive's native MetaImage, not the DICOM** | **TC-088 (new)** — `data/datamodule.py` references no `pydicom` |
| Splits are keyed on the source subject, never the SOP Instance UID | TC-041, and **TC-088 (new)** checks the persisted split files themselves, not only the constructor |
| **Training reads `train.batch_size` and nowhere else** | **TC-088 (new)** — a second `data.batch_size` fails it |
| Resume equivalence is claimed per platform | TC-059 — bit-identical on CPU, within a stated tolerance on GPU, and negative-tested three ways: by discarding the RNG state, and by removing each half of the per-epoch reseed in turn |
| **Sample order and augmentation are pure functions of `(seed, epoch)`** | **TC-059 (extended 2026-09-30)** — the served order and the served *pixels* are each compared against an uninterrupted run at every epoch. Deriving the seed rather than saving generator state is what makes this assertable: there is no restore step that can be omitted |
| Resume is detected from the run directory; `last` is written every epoch | TC-059, TC-079 |
| AMP is not used on this GPU | TC-097 — added 2026-09-28 after the aborted launch; negative-tested |
| Gradient accumulation rests on instance norm, not batch norm | TC-078 — the structural precondition is asserted before the equivalence |
| `LoadFrame` is a `Transform` and chains stay flat | TC-039 — the cache artefact is opened and decodes are counted |
| Accuracy alone is never reported | TC-002, and **TC-088 (new)** as a second check |
| The environment is the one recorded | TC-099 — installed packages against `requirements.lock`, with the torch build treated as a recorded variant |

### 16.2 Partially enforced

| Standing decision | What is checked, and what is not |
|---|---|
| Pre-registered criteria are not edited after seeing results | **TC-088 (new)** asserts §15 still states its three measured baselines, the AMP-off condition and the 10% threshold — so silently deleting or altering the numbers fails. It is **not** a content hash of the whole section, which would be stronger and is what TC-105 does for `docs/01` §2. Presence was chosen because §15 is prose-heavy and a hash would fail on a typo fix, training everyone to update it reflexively; that habit is how a hash gate stops meaning anything. The trade is recorded rather than hidden |

### 16.3 Not enforceable by a test, and why

| Standing decision | Why no test can enforce it |
|---|---|
| **URS-011's research-use designation mechanism is still open** | This is the *absence* of a decision. A test asserting it stays open would have to fail the moment it is resolved, which would make resolving it look like a regression. It belongs in `docs/11`'s open items, where it is |
| **A fixture written in the consuming code's convention cannot test a conversion** (§3 rule 7) | A rule about how tests are written, not a property of the system. No assertion can distinguish a fixture in the source convention from one in the target convention without knowing the author's intent. It is enforced by review, and by the two tests it produced — TC-017 and TC-043 — carrying the reasoning in their docstrings |
| **A test for a mechanism must inspect the mechanism** (§3 rule 8) | Same shape, one level up: a meta-rule about test design. A test cannot assert that other tests are well designed. Its enforcement is that every instance found so far is recorded in `docs/13` with the shape named, so the pattern is recognisable the seventh time |
| **Assert the invariant, not a lucky consequence** (§3 rule 9) | Same shape again. The nearest mechanical control is not a test but a habit: a test suspected of flakiness is run 20 times and the count recorded, because a single green run is exactly the evidence a consequence-asserting test is best at producing. Both instances were found that way and both counts are in §3 rule 9 |
| **Training runs locally; the dataset never leaves this workstation** | An operational commitment about what is *not* done. No test can prove an upload did not happen. The nearest mechanical control is TC-100, which asserts nothing under `data/` is tracked by git — that closes the one vector this repository controls, and the rest rests on `docs/06` §7.1 and on the author |

### 16.3b Retired — a decision withdrawn, not an enforcement that lapsed

| Standing decision | Why it was retired |
|---|---|
| **Commits carry no Claude Code attribution** (retired 2026-10-01) | It contradicted a stronger decision this project applies everywhere else: **the record states what happened.** `docs/08` keeps Stage 1's `determinism.json` unedited with its 1308 fallbacks rather than correcting it; TC-109 scopes its invariant to records written after SRS-085 rather than rewriting earlier ones; `docs/13` carries the author's own retracted claims as findings rather than deletions. A test requiring tool attribution to be absent from history requires the history to say something other than what happened — and enforcing it meant *rewriting* history, which broke nine cited SHAs on 2026-09-23 and is the reason TC-108 exists. The check is **deleted, not skipped** (§4 A3 permits no skipped test). **TC-108 remains** and is the control that actually matters about commit history here: every SHA cited in `docs/` and `scripts/` must resolve |

This row is kept rather than the decision being silently dropped. A standing decision that
disappears without a trace is indistinguishable from one nobody is enforcing any more,
which is the distinction §16 exists to make.

### 16.4 What this audit changed

Five decisions moved from prose to enforced, one was recorded as partial with its
trade-off stated, and four were confirmed unenforceable with reasons. The count that
matters is the middle one: before 2026-09-28 the AMP decision would have been listed in
§16.1 by anyone reading `docs/13`, because it *looked* settled. It was in §16.3 and
nobody had asked.

---

## 17. Stage 2 evaluation protocol — pre-registered

**Committed before any Stage 2 training starts.** The cross-vendor number is the result
this project exists to report, and it is reportable exactly once. Everything below is
fixed now, while no result is visible, because every choice here — which checkpoint,
which split, how many resamples, what the resampling unit is — moves the headline figure,
and a choice made after seeing the figure is a choice made *because of* it.

Stage 1 and Stage 1b established that training works. Nothing here has been run.

### 17.1 What is evaluated, and when

| Step | Rule |
|---|---|
| **Checkpoint selection** | `best.pt`, selected on **in-domain validation only** — unseen patients from the two training vendors. The held-out vendor plays no part in selecting anything: not the epoch, not the threshold, not the architecture |
| **Test evaluation** | The held-out vendor's test set is evaluated **exactly once**, after training has ended and after the evaluation code is committed |
| **Order** | Evaluation code finished, tested and committed **before the test set is touched**. A pipeline written while its output is visible is a pipeline tuned on the test set, however honestly |
| **Re-running** | If the evaluation errors, it may be re-run. If it *succeeds*, its output stands. A second execution to "check something" after seeing a number is a second look at the test set |

**No retraining against the test set after seeing results.** Not a different epoch, not a
different threshold, not a different architecture, not "one more fold". If a change is
warranted after seeing the cross-vendor result, it is a **new experiment, pre-registered
as such in this document with its own section and its own date**, and the first result is
reported alongside it rather than replaced by it. The record must make it possible to
count how many times the test set was consulted.

### 17.2 Metrics

Per **fluid class** (IRF, SRF, PED) and per **vendor**, never pooled across either:

| Metric | Source | Requirement |
|---|---|---|
| Dice | `eval/metrics.py`, numpy | SRS-032 |
| HD95, **max-of-directed** | `eval/metrics.py`, numpy | SRS-032, `docs/13` |
| Sensitivity, specificity | derived from the segmentation, SRS-050 | SRS-053 |
| AUROC | MC-dropout mean probability, numpy | SRS-052, SRS-053 |

Every figure carries a **bootstrap 95% confidence interval and its n** (SRS-033). A bare
point estimate is not a result anywhere in this repository. **Accuracy is not reported**,
the classes being imbalanced enough to make it misleading.

`n` is stated as the number of units the interval was computed over, **and the unit is
named** — a "n = 420" that silently means frames when the reader assumes patients is a
misreported result rather than an imprecise one.

### 17.3 Bootstrap

| Parameter | Value |
|---|---|
| **Resampling unit** | the **patient** — a cluster bootstrap, resampling patients with replacement and taking all of each sampled patient's volumes and frames |
| Resamples | **2000** |
| Interval | percentile, **95%** (α = 0.05) |
| Seed | `run.seed` from the evaluation configuration, recorded in the output |

**Why the patient and not the frame.** B-scans within a volume and volumes within a
patient are strongly correlated: neighbouring frames of one eye are close to repeated
measurements of the same thing. Resampling frames treats them as independent evidence and
**understates the interval**, by roughly the square root of the cluster size — which is
the direction that makes a result look more certain than it is. `eval/metrics.py`'s
current `bootstrap_ci` resamples elements, so a **grouped variant is required** and is
part of the evaluation code that must be committed before the test set is touched.

The seed is recorded and the resampling reproduces exactly on re-execution (SRS-034).
2000 resamples and α are fixed here so that neither can be chosen to move an interval
across a boundary.

### 17.4 Geometry

**Predictions are inverted to the acquisition's native grid before any metric is
computed** (SRS-074), and the spacing used is asserted bit-identical to the spacing
recorded at ingestion (**SRS-057**, TC-073); any difference aborts before a number is
emitted. `invert_axial_resample` exists for this.

A Dice computed at the resampled spacing is a Dice on a different object from the one
clinicians measure, and HD95 in particular is a **distance** — reporting it on a resampled
grid would report millimetres that are not the acquisition's millimetres. Since the
vendors' native axial spacings differ (cirrus 0.001955, spectralis 0.003872, topcon
0.0026–0.0035 mm), measuring on the common resampled grid would also make the *per-vendor
comparison itself* an artefact of preprocessing — which would corrupt precisely the
headline the project reports.

### 17.5 What the output must contain

| Item | Why |
|---|---|
| Per class × per vendor: metric, CI, n, and the **unit of n** | SRS-032, SRS-033 |
| The vendor held out, and the vendors trained on | the result is meaningless without it |
| Checkpoint identity: path, epoch, SHA-256 | which model produced this |
| `source.commit` and `source.dirty` of the evaluation run | SRS-086 |
| Bootstrap seed, resample count, resampling unit | SRS-034 |
| The in-domain validation figures **beside** the held-out ones | the degradation *is* the contribution; a held-out figure alone cannot show it |
| Count of test-set evaluations performed | §17.1 is only checkable if this is recorded |

### 17.6 What would make Stage 2 invalid

Stated now, so that none of it can be reasoned away later:

- The held-out vendor influencing **any** selection.
- Any metric computed on the resampled grid.
- A confidence interval resampled at frame or volume level and reported as though at
  patient level.
- A second evaluation of the test set after a first succeeded, without recording both.
- A pooled figure substituted for a per-class or per-vendor one.
- Evaluation code changed after the test set was seen, and the result re-generated
  without both versions being reported.

**A degraded cross-vendor result is a result.** The headline is the degradation, and a
large drop faithfully measured is the finding this project exists to produce — it is not a
failure to be recovered from by adjusting the protocol.

### 17.7 Amendments, made 2026-10-01 **before any sealed split was accessed**

Three clarifications, committed while `sealed.access_count("test")` and
`access_count("in_domain_ref")` were both **0** — verifiable from
`artifacts/sealed_access.jsonl`, which was empty, and from this section's position in the
history relative to the first access. An amendment to a pre-registration is only worth
anything if the record shows it preceded the result, so the ordering is the evidence and
not the assurance.

#### (a) The detection threshold stays as configured, and AUROC is primary

`inference.presence_voxel_threshold` remains **10** as committed. Sensitivity and
specificity are reported **at that threshold, as-is, whatever they show** — including a
specificity of zero, which the validation run already produced for two classes on `val`.

**AUROC is the primary detection metric, because it is threshold-free.** Sensitivity and
specificity at a single pre-registered threshold describe one operating point chosen before
any result was visible; AUROC describes the ranking across all of them and so cannot be
improved by having picked a better point. Reporting both, with AUROC primary, is what keeps
the threshold from becoming a free parameter after the fact.

**Any later threshold selection is labelled post-hoc and never replaces these figures.** It
may be reported *alongside* them, as a separate and clearly marked analysis, with the
pre-registered numbers retained in full. A sensitivity/specificity pair chosen after seeing
the test set is a description of that test set, not a measurement on it.

#### (b) A defect in the evaluation code may be fixed; the model may not be touched

If a defect in the **evaluation code** is found after unlocking, it may be fixed and the
evaluation re-run. **Both results are recorded**, along with the defect, its diagnosis and
which figures it changed. The access log already counts the accesses, so a re-run is visible
whether or not anyone chooses to mention it.

**No change to the model, the checkpoint, the threshold or any metric definition is
permitted after unlocking.** That line is where the distinction sits: fixing a measuring
instrument is legitimate and leaves both readings on the record; changing what is being
measured, after seeing the measurement, is not an evaluation at all. `best.pt` is selected
and fixed (§17.1), the threshold is fixed by (a), and the metric definitions are fixed by
§17.2 and CLAUDE.md rule 6.

#### (c) The one-time evaluation covers **both** sealed splits

`test` **and** `in_domain_ref` are evaluated in this one pass, because the pre-registered
headline is **the gap between them** (§17.5). A held-out figure alone cannot show
degradation — it needs the same model's performance on unseen patients from the *training*
vendors to be the comparison. Evaluating one now and the other later would make the gap a
comparison across two occasions rather than one, and would give two chances to look.

Each bucket is unlocked separately and each access is logged separately, so the count
remains per bucket and "exactly once" stays checkable for each.

### 17.8 How a long run is launched

**Added 2026-10-01 after the first `test` access was killed mid-run** (`docs/08` D5).
**Corrected 2026-10-03** after a run launched as "detached" died with a process it had not
been known to depend on (`docs/08` D8). The rule covers every run measured in hours —
training sessions as well as evaluations of a sealed split.

A long run is launched **from an interactive terminal the author keeps open** — a standalone
PowerShell window, or the VS Code integrated terminal. **In the latter case VS Code must stay
open for the whole run**, because the terminal is a child of it. It is never launched as a
single tool call that a time limit can terminate, and Claude Code does not launch it at all.

**A launch method may only be described as detached after verifying, from the process tree,
what the process depends on** — its parent, and anything whose lifetime ends the parent's.
"It no longer depends on X" is not "it depends on nothing". The 2026-10-01 wording permitted
"a detached background process", and on 2026-10-03 a training run launched through
`Win32_Process.Create` was described as surviving VS Code closing. It did survive that; it was
also parented by a WMI provider host, and it died within the hour when that host was torn down
(`docs/08` D8). The claim was checked against the risk it was meant to avoid and never against
the process tree, which is the only place the real dependency was visible.

Before a long run is left unattended, therefore, record its parent chain — the interpreter, its
launcher, and the terminal or service above them — so the conditions under which it ends are
known rather than assumed. And a remaining-time estimate is never given without first
confirming the process is alive: an estimate from the epoch log alone describes a run that may
already have stopped.

The first access to the held-out split was stopped by a harness background limit after 10 of
24 volumes. It produced no record and no results — the output file is written only at the end
— but it **consumed an unlock and left an entry in the access log**, so a protocol that
permits one evaluation now has a history showing two. Nothing was lost except the clarity of
the count, and that is exactly the thing the seal exists to provide.

The rule is about where the run's lifetime is owned. A run that outlives the thing that
started it cannot be ended by that thing's timeout, and an evaluation of a sealed split is the
last place to discover that a wrapper had an opinion about how long work may take.

### 17.9 Per-volume rows added to the record — the repair of `docs/08` D7

**Added 2026-10-03, after the Stage 2 results were seen.** §17.5 is left exactly as committed;
this section records what was added and on what authority, rather than editing a
pre-registered list after the fact.

The record now also carries **one row per volume per class** (SRS-089, TC-126): identifiers,
vendor, Dice, HD95, `reference_present`, and reference and predicted voxel counts. §17.5 did
not require them, and their absence is why §19.1's present/absent decomposition could not be
computed for cirrus without re-running inference on the sealed splits.

**This is an evaluation-code defect fix under §17.7b, and it changes no figure.** The rows are
read off the same measurements the aggregates are built from, the aggregate computation is
untouched, and TC-126 asserts that every aggregate is recomputable from the rows and that the
segmentation and detection blocks are identical with and without them. Nothing about the
model, checkpoint, threshold or metric definitions changed.

The cirrus re-run that uses these rows is authorised by the author under §17.7b with D7 as the
defect, and is scheduled **between training sessions, never concurrently with training**. Its
condition for proceeding is that **every aggregate reproduces the `767c8e5` results exactly**;
if any differs, the analysis stops and the difference is reported before anything else.

---

## 18. Stage 2 session plan

**110 epochs per night per fold**, resuming the next night, until the fold's 150 epochs
are done or early stopping ends it.

### 18.1 The number, and where it comes from

| Quantity | Value | Measured or derived |
|---|---|---|
| Per-epoch time, `cirrus_holdout` | **231.2 s** mean (228.3–238.3) | **measured**, all 20 epochs of Stage 1b |
| 110 epochs | **7.06 h** | derived from the above |
| 150 epochs | 9.63 h | derived |
| Night 2 remainder | 40 epochs, **2.57 h** | derived |

110 epochs is **7.06 h of a night**, which is the constraint the number exists to respect:
the workstation is the author's and the run has to be finished by morning. It is not a
property of the model and carries no scientific meaning — it is a wall-clock bound, and it
is recorded as one so that nobody later reads "110" as an epoch budget that was tuned.

`cirrus_holdout` is the **smallest** fold (2610 training frames). `spectralis_holdout`
(4032) and `topcon_holdout` (3088) will take proportionally longer per epoch, so 110
epochs will not fit one night for those; their session sizes are derived from their own
measured per-epoch times once each has run one night, not assumed from this one. **Do not
copy 110 to the other folds.**

### 18.2 How the nights compose

- `--epochs 150` is the **fold total** and never changes between sessions. It is the
  experiment.
- `--max-epochs-this-session 110` bounds **this invocation only** (SRS-080).
- The second night is the same command **without** `--max-epochs-this-session`, which
  lets the fold run to its 150 or to early stopping, whichever comes first.
- Resume is detected from the run directory, never requested by a flag. The second night
  is not told that it is a resume; it discovers it.
- `--max-epochs-this-session` rather than `STOP`, because `STOP` is a race against a 30 s
  poll and landed thirteen epochs late on Stage 1 (`docs/08` D1). `STOP` remains for an
  *unplanned* stop, which is what it is for.

**Early stopping may end the fold before 150** — `early_stopping_patience` is 25. If it
does, the fold is complete and the next night starts the next fold rather than continuing
this one. A resumed session carries the complete early-stopping state, so patience does
not restart at a session boundary (SRS-075, TC-059).

**What happened on `cirrus_holdout`, 2026-10-01: the second session was never needed.**
The fold ended by `early_stopping` at **epoch 58**, inside the first session's 110-epoch
bound, after 3.75 h. Validation Dice last improved at epoch 33 and the patience counter
reached 25 twenty-five epochs later. So the two-night composition in §18.2 was exercised
only in its first half, and there was no trajectory left to resume — night 2 was cancelled
rather than skipped. `docs/08` §5c is the record.

This is the plan working, not a deviation from it: §18.2 already said the fold is complete
if early stopping ends it. It is noted here because the 110-epoch session size is a
wall-clock bound and **a fold may well finish well inside it** — so the session size should
not be read as an expected epoch count for the remaining folds either.

### 18.3 What the night's evidence must show afterwards

Checked the next morning, before the following session is launched:

| Check | Where |
|---|---|
| The epoch log continued rather than restarted, with both session boundaries | `epochs.jsonl` |
| `determinism.json` records **zero** fallbacks | run directory |
| `source.dirty` is `false` and `source.commit` names a pushed commit | `run.json`, SRS-086 |
| Telemetry covers the whole session, with no thermal excursion | `gpu_telemetry.csv` |
| `last.pt` is current for its own epoch, and `best.pt` is not behind it | `checkpoints.sha256` |

A night that fails any of these is investigated before the next is launched. Training
through an unexplained anomaly to save a night costs the fold.

---

## 19. Stage 3 secondary analyses — pre-registered

**Committed before `spectralis_holdout` or `topcon_holdout` trains or evaluates anything.**
These are **secondary**. In every fold the **fixed-threshold, per-fold figures of §17 remain
primary**, for consistency across folds and because they are the only ones chosen before any
result was visible. Nothing here may replace a §17 figure, and every item below is labelled
as a secondary analysis wherever it appears.

The cirrus fold's §17 results are already recorded (`docs/08` §5d). Where an analysis here is
also applied retrospectively to cirrus, it is labelled **post-hoc** for that fold and
**pre-registered** for the other two — the same analysis having a different standing
depending on when it was declared relative to the result.

### 19.1 Present/absent decomposition of per-class Dice

For each fold, each class and **both arms** (held-out and in-domain reference), per-class Dice
is decomposed into:

| Stratum | Definition | What it measures |
|---|---|---|
| **present** | volumes where the class **is** in the reference | agreement where there is something to agree about |
| **absent** | volumes where the class is **not** in the reference | false-positive behaviour only |

Reported with **n for each stratum**, in patients, and with the patient-level interval where
n permits one. Also reported: **the share of the all-volume mean Dice attributable to the
absent stratum**, since a Dice of 0.0 on an absent volume where the model predicts anything is
arithmetically indistinguishable from poor overlap on a present one, and the two mean entirely
different things.

**This requires per-volume measurements to be persisted** — `docs/08` D7 records that the
Stage 2 record carried aggregates only, so the decomposition could not be computed from it.
The evaluator writes per-volume rows from now on.

### 19.2 A threshold selected on each fold's own validation set

**The rule is written here, before any Stage 3 result exists**, so that selection cannot be
steered by what it produces:

1. **Grid**, declared now: `[1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]` predicted voxels.
   Ten points spanning three orders of magnitude, the fixed threshold of 10 among them.
2. **Objective**: maximise **Youden's J** = sensitivity + specificity − 1, per class.
3. **Selected on**: that fold's **`val`** split only — never `test`, never `in_domain_ref`.
   `val` is already used for checkpoint selection, so it costs no additional independence.
4. **Ties**: the **smallest** threshold wins. Declared because ties are likely on a 7-patient
   validation split, and a tie broken by whichever value an implementation happened to visit
   first is not a rule.
5. **Degenerate case**: if a class has no positive or no negative volume in `val`, J is
   undefined and **the fixed threshold of 10 is used**, recorded as such.

The selected threshold is **reported alongside the fixed-threshold figures, never instead**,
and labelled as selected on validation. Sensitivity and specificity are given at both.
**AUROC is unchanged by either** — it is threshold-free, which is why §17.7a made it primary
and why this analysis cannot move the primary detection result at all.

### 19.3 A pooled cross-fold comparison

Across the three folds, held-out Dice against in-domain-reference Dice, **pooled over folds**,
per class.

**The motivation is n.** Each fold's in-domain reference arm holds 7 patients, which gave
intervals as wide as [0.0048, 0.5727] in Stage 2 — wide enough that no per-class difference
was established at 95% (`docs/08` §5d.4). Pooling the three folds' reference arms gives
**about 21 patients**, and the held-out arms about 70 volumes in total.

Three things fixed now, because each could otherwise be chosen to suit the answer:

- **Resampling stays patient-level** (SRS-087), and the cluster is the patient. A patient
  appears in the in-domain reference of at most one fold by construction, so pooling does not
  double-count anyone — but this is **asserted** at pooling time rather than assumed, because
  it is the property that makes the pooled interval meaningful.
- **The pooled figure is a secondary analysis**, reported beside the three per-fold results,
  never in place of them. A pooled number hides per-vendor variation, which is the thing this
  project exists to report (SRS-032's reasoning, extended across folds).
- **Folds are weighted equally by patient**, not by fold, and the per-fold n is reported with
  the pooled figure so a reader can see the composition.

**What a pooled result can and cannot settle.** It can narrow the interval on the *average*
degradation across vendors. It cannot establish anything about a *particular* vendor, and a
pooled difference that excludes zero does not imply any single fold's does.

### 19.4 What remains primary

| Report | Standing |
|---|---|
| §17 figures, fixed threshold, per fold | **primary**, in every fold |
| §19.1 present/absent decomposition | secondary; **post-hoc for cirrus**, pre-registered for the other two |
| §19.2 validation-selected threshold | secondary; reported alongside, never instead |
| §19.3 pooled cross-fold comparison | secondary |

A reader of `docs/10` must be able to tell which figures were fixed before the data was seen
and which were not, without having to reconstruct the chronology from commit dates.
