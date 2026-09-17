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

## 2. Anomaly review

### 2.1 Method, scope and limits

| | |
|---|---|
| **Date performed** | 2026-09-17 |
| **Scope** | Shipped components (§3) only. The runtime environment (§4) and the development and test tools (§5) were **not** reviewed — they do not ship, and Orthanc is a test peer rather than part of the device software |
| **Primary source** | OSV (`api.osv.dev`), queried programmatically for each component at its **exact pinned version**. OSV aggregates GitHub Security Advisories, PyPA advisories (PYSEC) and NVD/CVE records |
| **Relevance filter** | Only findings bearing on the requirements the component supports are carried into the row. A defect in an unused subsystem is recorded as present but not borne |
| **Not done** | Per-project issue trackers were not read exhaustively. For components with large advisory sets this review characterises the **classes** of defect, not each advisory individually — see §2.3 |

Querying by exact version matters: it distinguishes "this project has had CVEs" from
"this pinned version is affected", which are different statements and only the second
one is actionable here.

One secondary claim was encountered and **not** carried into this document: a blog post
asserting a critical FastAPI RCE affecting versions below 0.115.8. OSV returns no
advisory for FastAPI 0.111.1. The claim is recorded here as uncorroborated rather than
propagated.

### 2.2 Findings

| Component | Affected at pinned version | Nature | Bears on allocated requirements? |
|---|---|---|---|
| pydicom 2.4.4 | Yes — `GHSA-v856-2rf8-9f28` (CVE-2026-32711), `PYSEC-2026-2266` | Path traversal via a crafted `ReferencedFileID` in DICOMDIR / FileSet operations. Fixed in 2.4.5 | **Not currently reachable.** No requirement uses FileSet or DICOMDIR: SRS-001 reads MetaImage and SRS-006 writes instances directly. Becomes reachable the moment a DICOMDIR is read. Upgrade to 2.4.5 is a patch bump and is recommended |
| highdicom 0.22.0 | **None found** | — | No |
| MONAI 1.3.2 | Yes — 12 advisories incl. `GHSA-p8cm-mm2v-gwjm` (CVE-2025-58757), CVE-2025-58756, CVE-2026-21851 | Unsafe pickle deserialisation; `torch.load` used without `weights_only`; zip-slip in the NGC download path | **Yes.** Model loading is on the path to SRS-049. Not triggered by trusted, self-produced checkpoints, which is the only thing this project loads — but that is a usage constraint, not a fix, and it must hold for the MONAI Bundle export too |
| PyTorch 2.3.1 | Yes — 23 advisories incl. `GHSA-53q9-r3pm-6pq6` (CVE-2025-32434) | `torch.load` remote code execution **even with `weights_only=True`**, affecting ≤ 2.5.1, fixed in 2.6.0 | **Yes.** Same path as MONAI above. The mitigation widely recommended before this CVE — `weights_only=True` — is precisely what it defeats, so it cannot be cited as the control |
| SimpleITK 2.3.1 | **None found** | — | No |
| NumPy 1.26.4 | **None found** | — | No |
| SciPy 1.13.1 | **None found** | — | No |
| scikit-learn 1.5.1 | **None found** | — | No |
| FastAPI 0.111.1 | **None found** | — | No. See the uncorroborated blog claim in §2.1 |
| uvicorn 0.30.3 | **None found** | — | No |
| pandas 2.2.2 | **None found** | — | No |
| requests 2.32.3 | Yes — `GHSA-9hjg-9r4m-mvj7` (CVE-2024-47081) and 3 others | `.netrc` credentials leaked to a third party via a crafted URL; fixed in 2.32.4 | **Yes, conditionally.** SRS-043 and SRS-044 use this as the DICOMweb client. Not exploitable where no `.netrc` exists, and disarmed by `trust_env=False` on the session. Either that setting becomes a requirement or the pin moves to ≥ 2.32.4 |
| PyYAML 6.0.2 | **None found** | — | No. `safe_load` is required by SRS-013's usage regardless |
| python-multipart 0.0.9 | Yes — 16 advisories incl. CVE-2024-53981 (fixed 0.0.18) and the unbounded-header family (fixed 0.0.27) | Denial of service: a single crafted upload can stall the ASGI event loop and block all other requests | **Yes.** SRS-046 accepts an uploaded volume over HTTP, which is exactly the entry point. Of all findings here this is the one most directly on an allocated requirement |

### 2.3 Time-boxing — what this review does not cover

PyTorch (23 advisories), python-multipart (16) and MONAI (12) each carry advisory sets
too large to assess individually inside this review. For those three the finding above
characterises the **class** of defect and identifies the one advisory most relevant to
an allocated requirement. It does not assert that every advisory in the set has been
read, and no row should be read as claiming that.

Saying so is the point. A row implying per-advisory coverage that was not performed
would be the fabricated assurance §1 exists to avoid.

### 2.4 Consequence

Four components are affected at their pinned versions in a way that bears on an
allocated requirement: PyTorch, MONAI, requests and python-multipart. **No pin has been
changed by this review.** Changing a pin means a new SOUP assessment, a compatibility
question — a PyTorch 2.6 bump moves MONAI too — and a change control entry. Those are
decisions to take deliberately, recorded as open items 7 and 8, not side effects of
writing a document.

## 3. Shipped components

These execute as part of the software system.

| ID | Component | Version | Purpose | Requirements supported | Anomalies reviewed | Risk notes |
|---|---|---|---|---|---|---|
| SOUP-001 | pydicom | 2.4.4 | DICOM read and write; de-identification primitives | SRS-006, SRS-011, SRS-012..SRS-017, SRS-044 | Yes — 2026-09-17, OSV. **Affected**, not reachable (§2.2) | Carries the de-identification path. A silent failure to remove a tag is invisible unless SRS-015 verification is correct and independent of the same library — it is not, which is a limitation of the control, not of the library |
| SOUP-002 | highdicom | 0.22.0 | SEG and SR construction | SRS-006, SRS-038..SRS-042 | Yes — 2026-09-17, OSV. None found | Sole implementer of SRS-042, whose mechanism is still unresolved (`docs/11` §10 item 2). What this library exposes for algorithm identification is one of the candidate mechanisms and has not been examined |
| SOUP-003 | MONAI | 1.3.2 | Transforms, networks, metrics | SRS-025..SRS-029, SRS-032 | Yes — 2026-09-17, OSV. **Affected**, borne (§2.2, §2.3) | Supplies both the Dice metric and the training loss. A defect common to both would not be caught by comparing them |
| SOUP-004 | PyTorch | 2.3.1 | Tensor operations, training and inference | SRS-027, SRS-028, SRS-029 | Yes — 2026-09-17, OSV. **Affected**, borne (§2.2, §2.3) | Determinism under NFR-002 depends on this library's seeding and on non-deterministic kernel selection being disabled; `configs/train_seg.yaml` sets `deterministic: true` but nothing yet verifies it takes effect |
| SOUP-005 | SimpleITK | 2.3.1 | MetaImage (`.mhd`/`.raw`) reading | SRS-001, SRS-003 | Yes — 2026-09-17, OSV. None found | **The template described this as "MetaImage reading, resampling". Resampling is the concern:** SRS-010 and SRS-026 forbid resampling volumes onto a common cross-vendor geometry, and this library makes that easy to do by accident. Its resampling API must not be used for geometric harmonisation |
| SOUP-006 | NumPy | 1.26.4 | Array operations throughout | SRS-001, SRS-040 | Yes — 2026-09-17, OSV. None found | Volume computation in SRS-040 depends on dtype and rounding behaviour |
| SOUP-007 | SciPy | 1.13.1 | Distance transforms underlying HD95 | SRS-032 | Yes — 2026-09-17, OSV. None found | HD95 is sensitive to how an empty prediction or empty reference is handled; that is a definition decision for `docs/07`, not a library default to inherit silently |
| SOUP-008 | scikit-learn | 1.5.1 | AUROC, calibration | **None currently allocated** | Yes — 2026-09-17, OSV. None found | **See §6 open item 2.** `docs/02` §3.6 specifies segmentation metrics only. The classification arm named in CLAUDE.md §5 has no SRS, so this pin supports no allocated requirement |
| SOUP-009 | FastAPI | 0.111.1 | Inference API and request validation | SRS-046..SRS-049 | Yes — 2026-09-17, OSV. None found | Request model validation is the first line of SRS-048 out-of-scope rejection |
| SOUP-010 | uvicorn | 0.30.3 | ASGI server | SRS-046 | Yes — 2026-09-17, OSV. None found | Transport only; no requirement depends on its behaviour beyond serving |
| SOUP-011 | pandas | 2.2.2 | Manifest handling and results tables | SRS-037 | Yes — 2026-09-17, OSV. None found | Manifest indexing errors are a contributing failure for HS-4 (wrong-subject attribution) |
| SOUP-012 | requests | 2.32.3 | DICOMweb client | SRS-043, SRS-044 | Yes — 2026-09-17, OSV. **Affected**, conditional (§2.2) | Multipart handling for STOW-RS is the part most likely to fail silently on a partial store |
| SOUP-013 | PyYAML | 6.0.2 | Configuration loading | SRS-002, SRS-012, SRS-023, SRS-031 | Yes — 2026-09-17, OSV. None found | `safe_load` only. Configuration is the frozen contract TC-001 defends |
| SOUP-015 | python-multipart | 0.0.9 | Multipart form parsing for file upload to the API | SRS-046 | Yes — 2026-09-17, OSV. **Affected**, borne (§2.2, §2.3) | **Added by this draft.** Pinned in `pyproject.toml` but absent from the template list — the gap the §1 rule exists to catch |

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
| 1 | ~~No anomaly review performed.~~ **Performed 2026-09-17 against OSV for shipped components (§2).** Remaining: it covers §3 only, it is not exhaustive per advisory for PyTorch, MONAI and python-multipart (§2.3), and nothing repeats it when a pin changes. A review is a point-in-time statement and this one will go stale. | release |
| 2 | **scikit-learn (SOUP-008) supports no allocated requirement.** CLAUDE.md §5 names a classification arm — sensitivity, specificity, AUROC — but `docs/02` §3.6 specifies segmentation metrics only. Either the classification arm receives SRS requirements or the dependency is removed. A pinned dependency with no requirement behind it is the inverse of CLAUDE.md rule 1. | `docs/02` |
| 3 | ~~SOUP-017 is pinned by tag, not by digest.~~ **Resolved 2026-09-17:** both `python:3.11-slim` and `orthancteam/orthanc:24.7.3` are now pinned by digest, resolved from the registry and recorded in their rows. Remaining sub-item: nothing checks that the digest in the Dockerfile still matches the digest in this document — they can drift silently. | — closed; drift check owed to `docs/07` |
| 4 | SOUP-016 pins CPython to `3.11.*`, not to a patch version. Whether that is acceptable under NFR-002 needs deciding rather than inheriting. | — |
| 5 | No component in this list has a recorded supplier support or end-of-life status, and no upgrade policy exists. 62304 expects SOUP to be monitored over the product lifecycle, not identified once. | `docs/13` |
| 6 | The `Requirements supported` column is maintained by hand and nothing checks it against `docs/02`. It will drift. A test comparing the SRS identifiers cited here against those defined in `docs/02` would close this. | `docs/07` |
| 7 | **PyTorch 2.3.1 and MONAI 1.3.2 are affected by deserialisation defects that bear on model loading (§2.2).** The current mitigation is a usage constraint — only self-produced checkpoints are ever loaded — which is not recorded as a requirement anywhere. Either it becomes one in `docs/02`, or the pins move. A PyTorch 2.6 bump moves MONAI with it, so this is a coupled decision, not two independent ones. | `docs/02`, `docs/05` |
| 8 | **python-multipart 0.0.9 and requests 2.32.3 are affected in ways bearing directly on SRS-046 and SRS-043/044 (§2.2).** python-multipart is the clearest case in this document: a single crafted upload can stall the service. `requests` is disarmed by `trust_env=False`, which is either a requirement or a pin bump. Neither pin has been changed by this review. | `docs/02`, milestone 7 |
| 9 | Nothing checks that the image digests recorded in SOUP-014 and SOUP-017 still match `docker/Dockerfile.api` and `docker/docker-compose.yml`. They can drift silently. | `docs/07` |
