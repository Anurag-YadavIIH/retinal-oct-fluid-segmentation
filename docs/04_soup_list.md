<!--
Document: SOUP List
Status: DRAFT v0.1
Owner: Anurag Yadav
Last reviewed: 2026-09-17
Change history: docs/13_change_control_log.md

Allocates SOUP-001..SOUP-022. SOUP-001..SOUP-014 keep the identifiers and versions
the template assigned; SOUP-015..SOUP-022 are added to close the gap between this
list and what is actually pinned. Clause references to IEC 62304 carry the same
caveat as docs/03 §1.2: they are unverified against the normative text.
-->

# SOUP List

Software of Unknown Provenance. Every pinned dependency in `pyproject.toml` appears
here. Adding a dependency without adding a row is a defect.

## 1. Scope and what counts as SOUP

IEC 62304 treats as SOUP any software item already developed and generally available,
not developed for this device, and incorporated into the device software. Under that
definition the three tables below are not equivalent, and conflating them would
overstate what has been assessed:

- **§3 Shipped components** are SOUP proper. They execute as part of the software
  system and a defect in them is a defect in the device software.
- **§4 Runtime environment** is what the shipped components execute on. Not SOUP in the
  strict sense, but a version change here changes the behaviour of everything in §3.
- **§5 Development and test tools** do not ship. They are not SOUP; they are
  configuration-managed tools. They are listed because CLAUDE.md requires every pinned
  version to appear here, and because a defect in a *test* tool does not corrupt an
  output — it conceals that an output is already corrupt, which is its own hazard.

The classification assigned in `docs/03` is **Class B**. Class B obliges more of a SOUP
process than Class A does, including evaluation of published anomaly lists. §6 records
that this has not been done.

## 2. Anomaly review status — read this before relying on any row below

**No published anomaly list, security advisory, or known-defect list has been reviewed
for any component in this document.** The "Anomalies reviewed" column reads `No` in
every row, and that is a statement of fact rather than a placeholder to be tidied.

Writing plausible-looking anomaly assessments without performing them would be worse
than leaving the column empty, for the same reason `docs/03` §1.2 declines to cite
clause numbers it has not checked and `docs/11` declines to name a DICOM tag it has not
established. A reviewer can act on a declared gap. A reviewer cannot act on a fabricated
assurance.

This is open item 1 in §6 and is the single largest deficiency in this document.

## 3. Shipped components

These execute as part of the software system.

| ID | Component | Version | Purpose | Requirements supported | Anomalies reviewed | Risk notes |
|---|---|---|---|---|---|---|
| SOUP-001 | pydicom | 2.4.4 | DICOM read and write; de-identification primitives | SRS-006, SRS-011, SRS-012..SRS-017, SRS-044 | No | Carries the de-identification path. A silent failure to remove a tag is invisible unless SRS-015 verification is correct and independent of the same library — it is not, which is a limitation of the control, not of the library |
| SOUP-002 | highdicom | 0.22.0 | SEG and SR construction | SRS-006, SRS-038..SRS-042 | No | Sole implementer of SRS-042, whose mechanism is still unresolved (`docs/11` §10 item 2). What this library exposes for algorithm identification is one of the candidate mechanisms and has not been examined |
| SOUP-003 | MONAI | 1.3.2 | Transforms, networks, metrics | SRS-025..SRS-029, SRS-032 | No | Supplies both the Dice metric and the training loss. A defect common to both would not be caught by comparing them |
| SOUP-004 | PyTorch | 2.3.1 | Tensor operations, training and inference | SRS-027, SRS-028, SRS-029 | No | Determinism under NFR-002 depends on this library's seeding and on non-deterministic kernel selection being disabled; `configs/train_seg.yaml` sets `deterministic: true` but nothing yet verifies it takes effect |
| SOUP-005 | SimpleITK | 2.3.1 | MetaImage (`.mhd`/`.raw`) reading | SRS-001, SRS-003 | No | **The template described this as "MetaImage reading, resampling". Resampling is the concern:** SRS-010 and SRS-026 forbid resampling volumes onto a common cross-vendor geometry, and this library makes that easy to do by accident. Its resampling API must not be used for geometric harmonisation |
| SOUP-006 | NumPy | 1.26.4 | Array operations throughout | SRS-001, SRS-040 | No | Volume computation in SRS-040 depends on dtype and rounding behaviour |
| SOUP-007 | SciPy | 1.13.1 | Distance transforms underlying HD95 | SRS-032 | No | HD95 is sensitive to how an empty prediction or empty reference is handled; that is a definition decision for `docs/07`, not a library default to inherit silently |
| SOUP-008 | scikit-learn | 1.5.1 | AUROC, calibration | **None currently allocated** | No | **See §6 open item 2.** `docs/02` §3.6 specifies segmentation metrics only. The classification arm named in CLAUDE.md §5 has no SRS, so this pin supports no allocated requirement |
| SOUP-009 | FastAPI | 0.111.1 | Inference API and request validation | SRS-046..SRS-049 | No | Request model validation is the first line of SRS-048 out-of-scope rejection |
| SOUP-010 | uvicorn | 0.30.3 | ASGI server | SRS-046 | No | Transport only; no requirement depends on its behaviour beyond serving |
| SOUP-011 | pandas | 2.2.2 | Manifest handling and results tables | SRS-037 | No | Manifest indexing errors are a contributing failure for HS-4 (wrong-subject attribution) |
| SOUP-012 | requests | 2.32.3 | DICOMweb client | SRS-043, SRS-044 | No | Multipart handling for STOW-RS is the part most likely to fail silently on a partial store |
| SOUP-013 | PyYAML | 6.0.2 | Configuration loading | SRS-002, SRS-012, SRS-023, SRS-031 | No | `safe_load` only. Configuration is the frozen contract TC-001 defends |
| SOUP-015 | python-multipart | 0.0.9 | Multipart form parsing for file upload to the API | SRS-046 | No | **Added by this draft.** Pinned in `pyproject.toml` but absent from the template list — the gap the §1 rule exists to catch |

## 4. Runtime environment

Not SOUP in the strict sense, but every component in §3 executes on these.

| ID | Component | Version | Purpose | Requirements supported | Anomalies reviewed | Risk notes |
|---|---|---|---|---|---|---|
| SOUP-016 | CPython | 3.11 (`requires-python = "==3.11.*"`) | Language runtime | NFR-001 | No | The pin is a range within 3.11, not an exact patch version. Reproducibility under NFR-002 is therefore not pinned to the patch level |
| SOUP-017 | `python:3.11-slim` base image | `sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534` (digest resolved from registry 2026-09-17) | Container base for the API service | NFR-001 | See §2 | Pinned by digest in `docker/Dockerfile.api`, not by tag. A tag resolves to different contents over time and defeats reproducible builds; the digest does not. Changing it requires a change control entry. The digest identifies an image, not a reviewed inventory of the OS packages inside it — those are not enumerated here |
| SOUP-014 | Orthanc | 24.7.3, `sha256:57a3d037729897331027ddc00c12695b50f1effbbf805f855396f3d0248d2d5f` (digest resolved from registry 2026-09-17) | Local PACS — test and demonstration environment only | SRS-043, SRS-044, SRS-045 | Out of scope — see §2 | Does not ship as part of the device software. It is the DICOMweb peer against which SRS-043..SRS-045 are exercised, so a defect in it can cause a passing round-trip test to mean less than it appears to. Pinned by digest in `docker/docker-compose.yml` |

## 5. Development and test tools

These do not ship. A defect here does not corrupt an output; it conceals one.

| ID | Component | Version | Purpose | Requirements supported | Anomalies reviewed | Risk notes |
|---|---|---|---|---|---|---|
| SOUP-018 | pytest | 8.3.2 | Test execution | NFR-005 | No | Carries TC-004, the leakage gate. A collection error that silently skips it would remove the project's most important control — `--strict-markers` is set, which helps, but nothing asserts that TC-004 actually ran |
| SOUP-019 | pytest-cov | 5.0.0 | Coverage measurement | — | No | Reporting only; no requirement depends on it |
| SOUP-020 | ruff | 0.5.7 | Lint and format, via CLI and pre-commit (`ruff-pre-commit` rev `v0.5.7`) | — | No | Style and static checks only. The two pins are kept equal deliberately; they can drift |
| SOUP-021 | pre-commit | 3.8.0 | Git hook execution | DMP-C1 | No | Hooks are local. A contributor who has not run `pre-commit install` is not protected by any of them |
| SOUP-022 | pre-commit-hooks | v4.6.0 | `check-added-large-files`, `no-commit-to-branch`, YAML and whitespace checks | DMP-C1 | No | `check-added-large-files --maxkb=2000` is cited in `docs/06` §2.3 as implementing DMP-C1. That control therefore depends on a pinned third-party hook and on the hook being installed locally |

## 6. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | **No anomaly or advisory review has been performed for any component (§2).** Class B obliges it. The review must record, per component, what source was consulted, on what date, and what was found — and be repeated when any pin changes. Until then no row in §3 to §5 carries an assurance, only an identification. | `docs/05`, release |
| 2 | **scikit-learn (SOUP-008) supports no allocated requirement.** CLAUDE.md §5 names a classification arm — sensitivity, specificity, AUROC — but `docs/02` §3.6 specifies segmentation metrics only. Either the classification arm receives SRS requirements or the dependency is removed. A pinned dependency with no requirement behind it is the inverse of CLAUDE.md rule 1. | `docs/02` |
| 3 | ~~SOUP-017 is pinned by tag, not by digest.~~ **Resolved 2026-09-17:** both `python:3.11-slim` and `orthancteam/orthanc:24.7.3` are now pinned by digest, resolved from the registry and recorded in their rows. Remaining sub-item: nothing checks that the digest in the Dockerfile still matches the digest in this document — they can drift silently. | — closed; drift check owed to `docs/07` |
| 4 | SOUP-016 pins CPython to `3.11.*`, not to a patch version. Whether that is acceptable under NFR-002 needs deciding rather than inheriting. | — |
| 5 | No component in this list has a recorded supplier support or end-of-life status, and no upgrade policy exists. 62304 expects SOUP to be monitored over the product lifecycle, not identified once. | `docs/13` |
| 6 | The `Requirements supported` column is maintained by hand and nothing checks it against `docs/02`. It will drift. A test comparing the SRS identifiers cited here against those defined in `docs/02` would close this. | `docs/07` |
