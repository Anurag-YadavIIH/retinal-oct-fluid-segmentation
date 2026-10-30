<!--
Document: Traceability Matrix
Status: LIVING — updated per commit
Owner: Anurag Yadav
Last reviewed: 2026-09-19
Change history: docs/13_change_control_log.md
-->

# Traceability Matrix

Updated in the same commit as any change to a requirement, hazard, or test.
A stale matrix is worse than no matrix (CLAUDE.md rule 5).

| URS | SRS | HAZ | RC | TC | Implemented in |
|---|---|---|---|---|---|
| URS-001 | SRS-001, SRS-002, SRS-005, SRS-006, SRS-011, SRS-027, SRS-038, SRS-050 | HAZ-003 | RC-020 | TBD | `docs/02` §3 |
| URS-002 | SRS-003, SRS-040, SRS-046, SRS-054, SRS-055, SRS-056, SRS-057, SRS-058, SRS-059 | HAZ-012 | RC-021, RC-022, RC-023, RC-024, RC-025, RC-026 | TBD | `docs/02` §3 |
| URS-003 | SRS-045, SRS-047, SRS-060, NFR-006 | HAZ-001, HAZ-002, HAZ-003, HAZ-014 | RC-017, RC-027 | TBD | `docs/02` §3 |
| URS-004 | SRS-038, SRS-039, SRS-095 | HAZ-004, HAZ-010 | RC-013 | TBD | `docs/02` §3 |
| URS-005 | SRS-028, SRS-029, SRS-030, SRS-041, SRS-046, SRS-052 | HAZ-001, HAZ-002, HAZ-007 | RC-009 | TBD | `docs/02` §3 |
| URS-006 | SRS-001, SRS-009, SRS-017, SRS-054 | HAZ-004, HAZ-005, HAZ-012 | RC-008, RC-021 | TBD | `docs/02` §3 |
| URS-007 | SRS-018, SRS-019, SRS-020, SRS-021, SRS-022, SRS-024, SRS-032, SRS-033, SRS-035, SRS-036, SRS-037, SRS-050, SRS-051, SRS-052, SRS-053, SRS-092, SRS-093, SRS-096, SRS-097, SRS-098, SRS-102, SRS-103, SRS-104, SRS-105, SRS-106, SRS-107, SRS-108, SRS-110, SRS-111, NFR-003, NFR-005 | HAZ-001, HAZ-002, HAZ-003, HAZ-005, HAZ-008, HAZ-009, HAZ-016 | RC-001, RC-002, RC-003, RC-005, RC-006, RC-007, RC-030, RC-032 | TBD | `docs/02` §3 |
| URS-008 | SRS-003, SRS-010, SRS-025, SRS-026 | HAZ-005 | RC-016 | TBD | `docs/02` §3 |
| URS-009 | SRS-004, SRS-048, SRS-056 | HAZ-006, HAZ-012 | RC-010, RC-023 | TBD | `docs/02` §3 |
| URS-010 | SRS-007, SRS-008, SRS-012, SRS-013, SRS-014, SRS-015, SRS-016, SRS-023, SRS-031, SRS-034, SRS-043, SRS-044, SRS-049, SRS-051, SRS-057, SRS-059, SRS-060, SRS-061, SRS-094, SRS-096, SRS-097, SRS-098, SRS-099, SRS-102, SRS-103, SRS-105, SRS-106, SRS-107, NFR-001, NFR-002, NFR-004, NFR-007, NFR-008 | HAZ-004, HAZ-008, HAZ-009, HAZ-010, HAZ-011, HAZ-012, HAZ-013, HAZ-014, HAZ-016 | RC-004, RC-011, RC-012, RC-015, RC-018, RC-019, RC-024, RC-026, RC-027, RC-028, RC-032 | TBD | `docs/02` §3 |
| URS-011 | SRS-042, SRS-044, SRS-095 | HAZ-006, HAZ-011 | RC-014 | TBD | `docs/02` §3 |
| — | — | — | — | TC-000 | `src/ocuval/__init__.py` — smoke test, allocated to no requirement (`docs/02` §3) |
| URS-001 | SRS-002 | HAZ-003 | RC-020 | TC-001 | `configs/data.yaml` |
| URS-007 | SRS-019, SRS-020, SRS-021 | HAZ-008 | RC-002, RC-003, RC-005 | TC-004 | `src/ocuval/data/splits.py` |
| URS-007 | SRS-087, SRS-033, SRS-034 | HAZ-008 | RC-006 | TC-124 | `src/ocuval/eval/metrics.py`, `eval/subgroup.py` — patient-level cluster bootstrap |
| URS-007 | SRS-088 | HAZ-008 | RC-006 | TC-125 | `src/ocuval/eval/sealed.py` — the test split is read once, and the count is durable |
| URS-007 | SRS-089 | HAZ-008 | RC-006 | TC-126 | `src/ocuval/eval/pipeline.py` — per-volume rows, from which every aggregate is recomputable |
| URS-004, URS-011 | SRS-095 | — | — | TC-136 | `io/dicom_writer.py`, `report/seg_object.py`, `report/sr_object.py`, `report/coding.py` — every text value in an emitted object is encodable in its declared character set, ASCII where none is declared, with no substitution |
| URS-010 | SRS-094 | HAZ-004 | — | TC-135 | `.github/workflows/ci.yml`, job `pacs` — the PACS round-trip runs in CI against an ephemeral Orthanc at the SOUP-014 digest, bound to loopback, receiving synthetic objects only and destroyed with the job (`docs/06` §7.2.1) |
| URS-010 | SRS-090 | HAZ-016 | RC-032 | TC-127 | `scripts/compare_evaluation_records.py` — exact record comparison; NaN in both is equal, NaN in one is a difference |
| URS-007 | SRS-093 | HAZ-009, HAZ-016 | RC-030, RC-032 | TC-132, TC-133, TC-134, TC-146 | `scripts/09_illustrative_bscans.py` (and its `--record-set audited` run of §21.10) — at most six B-scans selected by `docs/07` §21, saved only if each regenerated prediction reproduces its sealed record exactly, with no metadata or identifier |
| URS-007 | SRS-092 | HAZ-005, HAZ-009 | RC-006, RC-030 | TC-129, TC-130, TC-131 | `scripts/08_build_site.py`, `site/` — the report page is generated from the records, every number on it from the generated data, with no image data and nothing that relinks a row to a subject |
| URS-007, URS-010 | SRS-097, SRS-098 | HAZ-005, HAZ-016 | RC-006, RC-032 | TC-138, TC-139, TC-140, TC-141, TC-142, TC-143, TC-144 | `src/ocuval/eval/report.py`, `scripts/11_report_tables.py` — every derived figure in `docs/10` generated from the records by committed code, and a check that fails when `docs/10`, `docs/12` or the README differ from it |
| URS-010 | SRS-099 | HAZ-016 | RC-032 | TC-145 | `scripts/check_report_tables_hook.py`, `.pre-commit-config.yaml` — runs the check when those documents change; blocks on a difference, warns and never skips silently when the records are absent |
| URS-002, URS-008 | SRS-074 | — | — | TC-151 | `tests/test_oracle_round_trip.py` against `data/transforms.py`, `io/retouch_reader.py`, `eval/pipeline.py` — oracle round trip on every vendor geometry: surviving fluid exact, swept bands without systematic shift; a strict expected failure while D1 stands |
| URS-007, URS-010 | SRS-103 | — | — | TC-152 | `scripts/13_crosscheck_val.py` — independent recomputation of every metric on the open `val` buckets, compared with the pipeline and the stored records |
| URS-007 | SRS-104 | — | — | TC-153 | `src/ocuval/eval/pipeline.py`, `src/ocuval/eval/report.py` — a secondary HD95 without both-empty volumes beside the pre-registered primary |
| URS-007, URS-010 | SRS-105 | — | — | TC-154 | `scripts/14_final_reevaluation.py` — the final re-evaluation of `docs/07` §17.13 and the §21.10 B-scans; after every evaluation, stops unless the population and the reference are unchanged |
| URS-007, URS-010 | SRS-106 | — | — | TC-155 | `src/ocuval/eval/predictions.py`, `scripts/05_evaluate.py`, `scripts/14_final_reevaluation.py` — every predicted label map saved locally with a checksum manifest in the record, re-measurable without the model |
| URS-007, URS-010 | SRS-107 | — | — | TC-156 | `src/ocuval/eval/sealed.py` — no sealed bucket opens without a completed dry-run certificate at the current commit; `src/ocuval/sandbox.py` — the synthetic root a dry run runs in |
| URS-007 | SRS-108 | — | — | TC-157 | `scripts/09_illustrative_bscans.py --record-set final`, `scripts/15_final_bscans.py` — the §21.11 B-scans from the saved maps, checked by checksum, no model, behind the mandatory dry run |
| URS-007, URS-010 | SRS-109 | — | — | TC-158 | `pyproject.toml` `[tool.mypy]`, `.github/workflows/ci.yml` step *Type check* — zero type findings over `src/` and `scripts/`, unannotated bodies included |
| URS-007 | SRS-110 | — | — | TC-159 | `scripts/09_illustrative_bscans.py --record-set presentation` (`crop_rows`, `PRESENTATION`), `scripts/16_presentation_bscans.py` — the §21.12 re-rendering for presentation from the saved maps, behind the mandatory dry run |
| URS-007 | SRS-111 | — | — | TC-160 | `scripts/09_illustrative_bscans.py --record-set sharper` (`SHARPER`), `scripts/17_sharper_bscans.py` — the §21.13 re-rendering: the whole B-scan, sharper, from the saved maps, behind the mandatory dry run |
| URS-007 | SRS-032 | HAZ-005 | RC-006 | TC-149 | `src/ocuval/eval/pipeline.py` `measure_volume` — HD95 with each spacing component on its own array axis, (separation, axial, lateral) for a (B-scans, rows, columns) volume |
| URS-007, URS-010 | SRS-102 | HAZ-005, HAZ-016 | RC-006, RC-032 | TC-150 | `scripts/12_reevaluate_hd95.py` — the §17.12 HD95 re-evaluation; after each sealed bucket, stops unless everything but HD95 equals the 24 October corrected record |
| URS-007, URS-010 | SRS-096 | HAZ-005, HAZ-016 | RC-006, RC-032 | TC-137 | `scripts/10_reevaluate.py` — the §17.11 re-evaluation chain: access counts checked first, the seeded reproducibility check must be IDENTICAL, then the open `val` buckets, then the six sealed buckets, writing only new files under `corrected/` |
| URS-010 | SRS-091 | HAZ-016 | RC-032 | TC-128 | `scripts/05_evaluate.py`, `src/ocuval/models/uncertainty.py` — evaluation requests determinism and reseeds each volume's MC-dropout passes from `(seed, subject)` |
| URS-010 | SRS-076, SRS-077, SRS-083 | HAZ-016 | RC-032 | TC-123 | `artifacts/runs/cirrus_holdout_stage1b` against `_stage2` — two differently configured GPU runs agree exactly while their schedules coincide |
| URS-010 | SRS-031, SRS-086 | HAZ-016 | RC-018, RC-032 | TC-122 | `src/ocuval/runs.py`, `scripts/04_train.py` — the run record identifies the code, and a fold run refuses a dirty tree |
| URS-010 | SRS-076, SRS-077, SRS-084, SRS-085 | HAZ-016 | RC-032 | TC-121 | `src/ocuval/training/{loop,losses,checkpoint}.py`, `src/ocuval/data/datamodule.py` — two GPU runs compared byte for byte; the evidence for CLAUDE.md rule 4 on GPU |

The eleven `URS` rows carry their software requirements from `docs/02` §3, and their
hazard and risk-control columns are **derived, not authored**: an RC appears against a
URS when it implements a requirement that URS derives, and a HAZ appears when one of
those RCs controls it. Test allocation is held per row in `docs/02` and `docs/05`, from
`docs/07`, and is summarised under Coverage.

The `TC` rows below the URS block are the test cases that predate the requirement set.
TC-000 is a smoke test allocated to no requirement by design — it asserts only that the
package exposes a version identifier, which is a precondition of SRS-031 and SRS-049
rather than a verification of either.

`docs/03` assigns the system **software safety class B**. `docs/05` allocates
HAZ-001..HAZ-016 and RC-001..RC-032. The interim identifiers used before it existed are
superseded: HS-1..HS-7 in `docs/03` §3 map to HAZ-001..HAZ-007, and DMP-C1..C10 in
`docs/06` map to RC-019, RC-001, RC-002, RC-003 and RC-004. HAZ-012..HAZ-015 and
RC-021..RC-029 are new in `docs/05` and supersede nothing. `docs/05` §3.1 and §4.1 carry
both mappings; the source documents keep their own labels.

URS-002 previously had no risk control at all. `docs/05` HAZ-012 and RC-021..RC-026 now
cover the volume derivation path — the metadata half of it, which is where the invisible
failure lives (`docs/05` §5.4). HAZ-015 and RC-029 cover the related case of acquisition
context the source never recorded being fabricated to satisfy a mandatory attribute.

HAZ-016 and RC-032 (added 2026-10-05) cover a result that cannot be reproduced from the
committed configuration. Training determinism, run provenance, seeded evaluation and the exact
comparison that gates a sealed unlock all trace to them. **Until then, the TC-121..TC-123 rows
traced to HAZ-009 (de-identification) and RC-028 (checkpoint provenance)**, neither of which
concerns determinism, because no hazard existed for it. The rows are re-traced, and the
correction is recorded in `docs/13`.

## Coverage

Regenerated from `docs/01`, `docs/02`, `docs/05` and `docs/07`, and from the test suite
itself — implemented counts are read from the `test_TC_nnn_` function names, not from a
memory of what was written. TC-104 is allocated to keep this section honest once
implemented.

- User requirements with at least one software requirement: **11 of 11**. Every URS in
  `docs/01` derives at least one SRS or NFR in `docs/02`.
- Software requirements with a verifying test case **allocated**: **109 of 109**
  SRS and **8 of 8** NFR. Every SRS names a test case in its own row; each NFR is named by
  at least one row of `docs/07` §6 instead, the allocation running in that direction.
- Test cases **registered** in `docs/07` §6: **144**.
  Test cases **written**: **120**. Of those,
  **120 are executed** by the suite and
  **0 have never been run**. TC-080, TC-081 and TC-082 need a PACS, which is not available
  on this workstation; until 2026-10-16 they had never been run. CI's `pacs` job now runs them
  against an ephemeral Orthanc (SRS-094), and their first run passed (`docs/08` §5h). A
  written test that nobody has executed is not verification, and is not counted as such here.
  The remaining
  **24** are registered and unwritten.

> **These figures are recomputed by TC-104, not maintained by hand** (since 2026-10-01).
> `tests/test_traceability_current.py` parses the numbers this section claims, recomputes
> them from `docs/02`, `docs/07` §6 and the `test_TC_nnn_` function names, and fails when the
> two disagree — in either direction. Editing this section without changing the repository
> fails; adding a test without updating this section fails too.
>
> It was overdue. These counts had drifted to "50 of 85 written, 47 executed", understating
> the written count by 26, and the drift was found by a person reading them because nothing
> else could. TC-104 was registered for precisely this and stayed unwritten long enough that
> the defect recurred on the same artefact (`docs/07` §3 rule 8; `docs/13` 2026-09-30).
>
> Markers are resolved with `ast`, not by searching the source for a marker's name. The first
> draft of TC-104 did the latter and counted eight never-executed cases instead of three,
> because one file mentions `requires_pacs` in a comment and TC-104's own docstring names it
> — rule 8 reappearing inside the test written to enforce rule 8.

- Hazards with at least one risk control: **16 of 16** — every HAZ in `docs/05`
  §3.2 carries at least one RC.
- Risk controls with a verifying test **allocated**: **32 of 32**;
  **verified by an executed test: 28 of 32** (RC-002, RC-003, RC-004, RC-005, RC-006, RC-007, RC-008, RC-009, RC-011, RC-012, RC-013, RC-015, RC-016, RC-017, RC-018, RC-020, RC-021, RC-022, RC-023, RC-024, RC-025, RC-026, RC-027, RC-028, RC-029, RC-030, RC-031, RC-032).
  Recomputed 2026-10-05 from the `docs/05` §4.2 table and the `test_TC_nnn_` function names;
  the previous "29 of 29, 22 of 29" had not been updated since RC-030 and RC-031 were added,
  and TC-104 does not check these risk-control counts. **Updated 2026-10-16:** RC-017 is
  verified by TC-082, first executed that day in CI (`docs/08` §5h). **RC-014 is not counted,
  although TC-081 now runs:** it is allocated to TC-077, unwritten, and TC-081, which checks
  pixel data, spacing, identity and source references but **not the research-use
  designation** that RC-014 is about. Counting it would claim a verification that did not take
  place (`docs/13`, 2026-10-16). The rest name an allocated but unwritten test case
  (`docs/05` §5.3, `docs/07` §1.2).

**Allocation and implementation are kept as separate numbers throughout.** They are very
different claims, and a single figure covering both would flatter the project.
