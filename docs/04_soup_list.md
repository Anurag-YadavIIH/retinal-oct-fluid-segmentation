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

### 2.4 Disposition — remediate or accept, with rationale

Identifying an anomaly does not oblige a version bump. The obligation is to assess
whether it affects the device **in its intended use** and to record the reasoning.
Justified acceptance is a valid outcome; an unexamined bump is not a better one.

| Component | Disposition | Rationale |
|---|---|---|
| python-multipart 0.0.9 → **0.0.31** | **Remediated** | Direct hit on SRS-046, which accepts an uploaded volume over HTTP — the exact entry point the DoS targets. No in-code mitigation exists for a parser defect, so remediation was the only route. 0.0.31 is the lowest version clearing all six advisory families OSV names for 0.0.9; confirmed clean by re-query on 2026-09-17 and confirmed published. Version taken from OSV's `fixed` events, not assumed |
| requests 2.32.3 | **Remediated in code, pin unchanged** — RC-027 / SRS-060 | The DICOMweb client now takes its entire configuration from the run configuration, with `trust_env=False`. Chosen over the 2.32.4 bump because it is strictly broader: it removes ambient `.netrc`, proxy *and* certificate pickup, so client behaviour no longer depends on machine state at all. That serves NFR-002 reproducibility as well as the advisory, and it is verifiable by a test this project owns rather than by trusting a version number. The pin may still move to ≥ 2.32.4 opportunistically; it is not load-bearing. **Known limitation — see §2.6** |
| PyTorch 2.3.1 | **Accepted** — RC-028 / SRS-061 | See §2.5 |
| MONAI 1.3.2 | **Accepted** — RC-028 / SRS-061 | See §2.5 |
| FastAPI 0.111.1 | No action | OSV reports nothing at this version. The secondary claim in §2.1 remains uncorroborated and is not acted on |
| pydicom 2.4.4 | No action now | The advisory is reachable only through FileSet / DICOMDIR operations, which no requirement uses. A 2.4.5 patch bump remains cheap and is recommended when the pin is next touched — but acting on an unreachable defect ahead of the reachable ones would be theatre |

### 2.5 PyTorch and MONAI — accepted, and why

Both findings are deserialisation of an untrusted model file: `torch.load` reaching code
execution, including with `weights_only=True` (CVE-2025-32434), and MONAI's pickle and
`torch.load` paths.

**The intended use excludes the threat.** This system loads exactly one class of file:
checkpoints it produced itself. SRS-061 makes that a requirement rather than a
convention — checkpoints load only from the project's own `artifacts/` directory, with a
hash recorded at write time and verified before load, and a mismatch or missing hash
aborts. `docs/05` RC-028 carries it, and HAZ-013 is the hazard.

**The alternative is a bad trade.** PyTorch 2.6 moves MONAI with it, invalidates the SOUP
assessment of both, and changes the numerical behaviour of every trained model — a large
coupled change to close a threat the intended use already excludes.

The acceptance is conditional on RC-028 existing. It does not yet: `src/` is stubs. Until
then the acceptance rests on a requirement rather than a control, and `docs/05` §5.3 and
§5.5 say so.

### 2.6 RC-027 — known limitation of `trust_env=False`

`trust_env=False` is not a targeted `.netrc` switch. It disables **all** environment-derived
HTTP configuration in the client: `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` and
`REQUESTS_CA_BUNDLE` as well as `.netrc`.

Against a localhost Orthanc that is harmless, and for this project it is the desired
behaviour — it is exactly why the control was chosen over the patch bump (§2.4).

**But it would break the client in the deployment the intended use describes.** A reading
centre sits behind a corporate proxy with an internal certificate authority, and a client
that ignores `HTTPS_PROXY` and `REQUESTS_CA_BUNDLE` cannot reach a PACS through it. The
control as written is correct for this project and wrong for the environment `docs/01` §4
describes.

This is stated rather than fixed. Changing the control to a narrower one — passing
`auth=None` per request, or clearing only `.netrc` — would weaken the reproducibility
property that justified choosing it. If this software were ever deployed into a real
reading centre, RC-027 and SRS-060 would need proxy and CA settings moved into the run
configuration as explicit fields rather than simply re-enabled from the environment.

## 3. Shipped components

These execute as part of the software system.

| ID | Component | Version | Purpose | Requirements supported | Anomalies reviewed | Risk notes |
|---|---|---|---|---|---|---|
| SOUP-001 | pydicom | 2.4.4 | DICOM read and write; de-identification primitives | SRS-006, SRS-011, SRS-012..SRS-017, SRS-044 | Yes — 2026-09-17, OSV. **Affected**, not reachable; no action (§2.4) | Carries the de-identification path. **Confirmed on implementation (2026-09-17):** the profile table and its verification share one source of truth, so verification cannot detect an attribute the table omits — a limitation of the control, not of the library. The table is keyed by DICOM keyword rather than tag number, so pydicom resolves every tag and none can be invented |
| SOUP-002 | highdicom | 0.22.0 | SEG and SR construction | SRS-006, SRS-038..SRS-042 | Yes — 2026-09-17, OSV. None found | Sole implementer of SRS-042, whose mechanism is still unresolved (`docs/11` §10 item 2). What this library exposes for algorithm identification is one of the candidate mechanisms and has not been examined |
| SOUP-003 | MONAI | 1.3.2 | Transforms, networks, metrics | SRS-025..SRS-029, SRS-032, SRS-061 | Yes — 2026-09-17, OSV. **Affected**, **accepted** on RC-028 (§2.5) | Supplies both the Dice metric and the training loss. A defect common to both would not be caught by comparing them |
| SOUP-004 | PyTorch | 2.3.1 | Tensor operations, training and inference | SRS-027, SRS-028, SRS-029, SRS-061 | Yes — 2026-09-17, OSV. **Affected**, **accepted** on RC-028 (§2.5) | Determinism under NFR-002 depends on this library's seeding and on non-deterministic kernel selection being disabled; `configs/train_seg.yaml` sets `deterministic: true` but nothing yet verifies it takes effect |
| SOUP-005 | SimpleITK | 2.3.1 | MetaImage (`.mhd`/`.raw`) reading | SRS-001, SRS-003 | Yes — 2026-09-17, OSV. None found | **The template described this as "MetaImage reading, resampling". Resampling is the concern:** SRS-010 and SRS-026 forbid resampling volumes onto a common cross-vendor geometry, and this library makes that easy to do by accident. Its resampling API must not be used for geometric harmonisation |
| SOUP-006 | NumPy | 1.26.4 | Array operations throughout | SRS-001, SRS-040 | Yes — 2026-09-17, OSV. None found | Volume computation in SRS-040 depends on dtype and rounding behaviour |
| SOUP-007 | SciPy | 1.13.1 | Distance transforms underlying HD95 | SRS-032 | Yes — 2026-09-17, OSV. None found | HD95 is sensitive to how an empty prediction or empty reference is handled; that is a definition decision for `docs/07`, not a library default to inherit silently |
| SOUP-008 | scikit-learn | 1.5.1 | AUROC for volume-level detection | SRS-053 | Yes — 2026-09-17, OSV. None found | Supports the detection arm only. That arm is derived from the segmentation output (SRS-050), so this library scores an existing prediction — it does not fit or train anything |
| SOUP-009 | FastAPI | 0.111.1 | Inference API and request validation | SRS-046..SRS-049 | Yes — 2026-09-17, OSV. None found | Request model validation is the first line of SRS-048 out-of-scope rejection |
| SOUP-010 | uvicorn | 0.30.3 | ASGI server | SRS-046 | Yes — 2026-09-17, OSV. None found | Transport only; no requirement depends on its behaviour beyond serving |
| SOUP-011 | pandas | 2.2.2 | Manifest handling and results tables | SRS-037 | Yes — 2026-09-17, OSV. None found | Manifest indexing errors are a contributing failure for HS-4 (wrong-subject attribution) |
| SOUP-012 | requests | 2.32.3 | DICOMweb client | SRS-043, SRS-044, SRS-060 | Yes — 2026-09-17, OSV. **Affected**, **remediated in code** by RC-027 (§2.4) | Multipart handling for STOW-RS is the part most likely to fail silently on a partial store |
| SOUP-013 | PyYAML | 6.0.2 | Configuration loading | SRS-002, SRS-012, SRS-023, SRS-031 | Yes — 2026-09-17, OSV. None found | `safe_load` only. Configuration is the frozen contract TC-001 defends |
| SOUP-015 | python-multipart | 0.0.31 | Multipart form parsing for file upload to the API | SRS-046 | Yes — 2026-09-17, OSV. **Clean at 0.0.31** | Was pinned at 0.0.9 and absent from the template list. **Remediated 2026-09-17** (§2.5): 0.0.31 is the lowest version clearing all six advisory families OSV names for 0.0.9, confirmed clean by re-query. No in-code mitigation exists for a parser DoS, so remediation was the only route |

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
| 2 | ~~scikit-learn supports no allocated requirement.~~ **Resolved 2026-09-17:** `docs/02` SRS-050..SRS-053 specify volume-level detection derived from the segmentation output, and SOUP-008 now supports SRS-053. | — closed |
| 3 | ~~SOUP-017 is pinned by tag, not by digest.~~ **Resolved 2026-09-17:** both `python:3.11-slim` and `orthancteam/orthanc:24.7.3` are now pinned by digest, resolved from the registry and recorded in their rows. Remaining sub-item: nothing checks that the digest in the Dockerfile still matches the digest in this document — they can drift silently. | — closed; drift check owed to `docs/07` |
| 4 | SOUP-016 pins CPython to `3.11.*`, not to a patch version. Whether that is acceptable under NFR-002 needs deciding rather than inheriting. | — |
| 5 | No component in this list has a recorded supplier support or end-of-life status, and no upgrade policy exists. 62304 expects SOUP to be monitored over the product lifecycle, not identified once. | `docs/13` |
| 6 | The `Requirements supported` column is maintained by hand and nothing checks it against `docs/02`. It will drift. **Allocated as TC-103** in `docs/07` §8. | `docs/07` |
| 7 | ~~PyTorch and MONAI deserialisation findings unaddressed.~~ **Resolved 2026-09-17: accepted** on the basis of RC-028 / SRS-061 (§2.5), with HAZ-013 in `docs/05`. Conditional on RC-028 being implemented — it is not yet. | `docs/05` §5.5 |
| 8 | ~~python-multipart and requests findings unaddressed.~~ **Resolved 2026-09-17:** python-multipart remediated to 0.0.31; requests remediated in code by RC-027 / SRS-060 with the pin unchanged, rationale in §2.4. | — closed |
| 9 | Nothing checks that the image digests recorded in SOUP-014 and SOUP-017 still match `docker/Dockerfile.api` and `docker/docker-compose.yml`. They can drift silently. ~~Digest drift unchecked.~~ **Resolved 2026-09-17: TC-106 implemented**, asserting both files use the digests recorded here and that neither has been repinned to a tag. | — closed |
