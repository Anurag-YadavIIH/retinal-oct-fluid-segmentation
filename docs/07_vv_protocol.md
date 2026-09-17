<!--
Document: Verification and Validation Protocol
Status: DRAFT v0.1
Owner: Anurag Yadav
Last reviewed: 2026-09-17
Change history: docs/13_change_control_log.md

Allocates TC-000..TC-113 (76 cases) across unit, integration and system levels. Carries the
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

**22 of 76 test cases are implemented** as of 2026-09-17 — TC-000..TC-002, TC-004,
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

### 6.3 DICOM conversion

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-020 | Instances written as the configured SOP class | SRS-006 | U | Written objects carry `dicom.sop_class` from config; encoding via pydicom/highdicom only | yes |
| TC-021 | UIDs generated under the configured root | SRS-007, RC-015 | U | Every generated UID is prefixed by `dicom.uid_root` | yes |
| TC-022 | Conversion deterministic except UIDs | SRS-008, RC-015 | U | Two conversions of one volume differ only in UIDs; generated UIDs present in run output | yes |
| TC-023 | Vendor recoverable from the object | SRS-009, RC-008 | U | Vendor readable from the converted object without reference to directory layout | yes |
| TC-024 | Native geometry preserved | SRS-010, RC-016 | U | Slice count and spacing identical to source; no resample, pad, crop or interpolate | yes |
| TC-025 | Unestablished DICOM detail fails loudly | SRS-011 | U | With a required tag unresolved, conversion raises stating the uncertainty; no value invented | yes |

### 6.4 De-identification

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-030 | Confidentiality profile applied | SRS-012, RC-011 | U | PS3.15 Annex E applied with no retention options, per config | yes |
| TC-031 | Pseudonyms salted, salt never written | SRS-013, RC-012 | U | Pseudonym differs under a different salt; salt absent from every output file and log | yes |
| TC-032 | Pseudonyms stable within a run | SRS-014, RC-012 | U | Same patient yields the same pseudonym across instances in one run | yes |
| TC-033 | Verification reports residual tags | SRS-015, RC-011 | U | Returns the offending tag for a doctored instance; returns empty for a clean one | yes |
| TC-034 | Non-empty verification aborts the run | SRS-016, RC-011 | U | Run aborts; failing instance not skipped, quarantined or logged-and-continued | yes |
| TC-035 | Vendor survives de-identification | SRS-017, RC-008 | U | Vendor readable after the profile is applied; its loss aborts | yes |

### 6.5 Dataset splitting

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-040 | In-domain reference set disjoint | SRS-022 | U | Reference patients drawn from training vendors, disjoint from train and val | yes |
| TC-041 | Splits seeded, persisted, reproducible | SRS-023, RC-004 | U | Same config and seed reproduce the split exactly; save/load round-trips | yes |
| TC-042 | Split construction is patient-level from the manifest | SRS-019, RC-002 | U | No B-scan assigned independently of its patient | yes |

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
| TC-080 | STOW-RS store and WADO-RS retrieve | SRS-043 | S | Object stored and retrieved against the pinned Orthanc | yes (`requires_pacs`) |
| TC-081 | Round-trip fidelity | SRS-044, RC-014 | S | Retrieved object matches sent in pixel data, fluid volumes, confidence and designation | yes (`requires_pacs`) |
| TC-082 | No action beyond store and retrieve | SRS-045, RC-017 | S | No delete, modify or reconcile; no endpoint marks anything verified or signed off | yes (`requires_pacs`) |
| TC-083 | Client ignores ambient environment | SRS-060, RC-027 | U | With `.netrc`, proxy and certificate variables set in the environment, the client uses none of them | yes |

### 6.10 Inference API

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-090 | Inference response contents | SRS-046 | S | Object identifiers, per-class mm³, confidence and review flag all present | yes |
| TC-091 | Response is a candidate; no sign-off | SRS-047, RC-017 | S | Response marked as requiring review; no endpoint records, finalises or approves | yes |
| TC-092 | Out-of-scope input rejected | SRS-048, RC-010 | S | Rejected with a stated reason; no segmentation returned | yes |
| TC-093 | Health endpoint | SRS-049, RC-018 | S | Reports status, software version and loaded model identifier | yes |
| TC-094 | Inference reaches no network but the configured PACS | NFR-006 | S | With outbound traffic blocked except the configured DICOMweb endpoint, inference completes; any other host attempted is a failure | yes |

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
| TC-107 | Change control log touched | NFR-007 | D | A change touching a requirement, hazard or test identifier also touches `docs/13` | partial |

TC-107 is marked partial deliberately: it can check that `docs/13` changed, not that what
was written there is true. That is a review activity, not a test, and pretending
otherwise would overstate what automation buys.

## 9. Integration test register — §5.6

| ID | Title | Verifies | Method | Acceptance criterion | Auto |
|---|---|---|---|---|---|
| TC-110 | Identity, vendor and spacing survive ingestion → conversion → de-identification | SRS-054, SRS-009, SRS-017, RC-021, RC-008 | I | All three fields present and unchanged at every stage boundary | yes (`slow`) |
| TC-111 | Overlap assertion runs at training start | SRS-020, RC-002 | I | Training on a deliberately overlapping split aborts before the first step | yes (`slow`) |
| TC-112 | Inference → SEG/SR → PACS → retrieve | SRS-043, SRS-044 | I | End-to-end chain produces a retrievable object matching the inference result | yes (`slow`, `requires_pacs`) |
| TC-113 | Two runs from one config agree | NFR-002 | I | Identical seeds and config produce identical splits, metrics and intervals | yes (`slow`) |

## 10. Traceability summary

Coverage is computed from the documents, not asserted here — TC-104 exists to keep this
section honest, and `docs/09` carries the authoritative counts.

| Level | Allocated |
|---|---|
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
| 1 | 54 of the 76 allocated test cases are unimplemented (§1.2). This protocol is a specification, not a result. | Milestones 3–7 |
| 2 | TC-107 cannot verify that a change control entry is *correct*, only that one exists (§8). No automation closes that; it is a review activity. | — |
| 3 | TC-105's gate forces review rather than proving re-classification (§7.3). If a stronger guarantee is wanted it needs a commit-level check outside pytest. | — |
| 4 | Validation, as distinct from verification, is not performed and cannot be (§1.1). `docs/08` must state this rather than letting a full verification table imply it. | `docs/08` |
| 5 | No test verifies that a recorded checkpoint hash is itself correct — RC-028 degrades to trust-on-first-write (`docs/05` open item 7). TC-058 inherits that limit. | `docs/05` |
| 6 | Per-vendor spacing plausibility ranges still do not exist in `configs/data.yaml`, and defining them needs the data. **Partly mitigated 2026-09-17:** `io.retouch_reader.validate_spacing` rejects on physical grounds instead — a voxel edge above 0.5 mm cannot be retinal OCT, and isotropic spacing cannot be OCT at all — so TC-015's rejection cases including the micrometre case are implemented now. The per-vendor ranges will tighten that bound, not replace it. | Milestone 3 |
| 7 | `io/deident.py` applies a **subset** of the PS3.15 Annex E attribute table, and its verification checks exactly that subset — so neither half can detect an identifying attribute the table omits. Closing this needs the standard's full table. | `docs/11` |
