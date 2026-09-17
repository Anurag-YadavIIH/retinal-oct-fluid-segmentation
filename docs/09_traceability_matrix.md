<!--
Document: Traceability Matrix
Status: LIVING — updated per commit
Owner: Anurag Yadav
Last reviewed: 2026-09-16
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
| URS-004 | SRS-038, SRS-039 | HAZ-004, HAZ-010 | RC-013 | TBD | `docs/02` §3 |
| URS-005 | SRS-028, SRS-029, SRS-030, SRS-041, SRS-046, SRS-052 | HAZ-001, HAZ-002, HAZ-007 | RC-009 | TBD | `docs/02` §3 |
| URS-006 | SRS-001, SRS-009, SRS-017, SRS-054 | HAZ-004, HAZ-005, HAZ-012 | RC-008, RC-021 | TBD | `docs/02` §3 |
| URS-007 | SRS-018, SRS-019, SRS-020, SRS-021, SRS-022, SRS-024, SRS-032, SRS-033, SRS-035, SRS-036, SRS-037, SRS-050, SRS-051, SRS-052, SRS-053, NFR-003, NFR-005 | HAZ-001, HAZ-002, HAZ-003, HAZ-005, HAZ-008 | RC-001, RC-002, RC-003, RC-005, RC-006, RC-007 | TBD | `docs/02` §3 |
| URS-008 | SRS-003, SRS-010, SRS-025, SRS-026 | HAZ-005 | RC-016 | TBD | `docs/02` §3 |
| URS-009 | SRS-004, SRS-048, SRS-056 | HAZ-006, HAZ-012 | RC-010, RC-023 | TBD | `docs/02` §3 |
| URS-010 | SRS-007, SRS-008, SRS-012, SRS-013, SRS-014, SRS-015, SRS-016, SRS-023, SRS-031, SRS-034, SRS-043, SRS-044, SRS-049, SRS-051, SRS-057, SRS-059, SRS-060, SRS-061, NFR-001, NFR-002, NFR-004, NFR-007, NFR-008 | HAZ-004, HAZ-008, HAZ-009, HAZ-010, HAZ-011, HAZ-012, HAZ-013, HAZ-014 | RC-004, RC-011, RC-012, RC-015, RC-018, RC-019, RC-024, RC-026, RC-027, RC-028 | TBD | `docs/02` §3 |
| URS-011 | SRS-042, SRS-044 | HAZ-006, HAZ-011 | RC-014 | TBD | `docs/02` §3 |
| — | — | — | — | TC-000 | `src/ocuval/__init__.py` — smoke test, allocated to no requirement (`docs/02` §3) |
| URS-001 | SRS-002 | HAZ-003 | RC-020 | TC-001 | `configs/data.yaml` |
| URS-007 | SRS-019, SRS-020, SRS-021 | HAZ-008 | RC-002, RC-003, RC-005 | TC-004 | `src/ocuval/data/splits.py` |

The eleven `URS` rows now carry their software requirements from `docs/02` §3.
Hazard and risk-control columns remain TBD: `docs/05` does not exist, so there is
nothing to allocate to. Test allocation is held in `docs/02` and `docs/05` per row,
from `docs/07`, and is summarised under Coverage below.

The `TC` rows are the three existing tests. TC-000 is a smoke test allocated to no
requirement by design — it asserts only that the package exposes a version
identifier, which is a precondition of SRS-031 and SRS-049 rather than a
verification of either.

`docs/03` assigns the system **software safety class B**. `docs/05` allocates
HAZ-001..HAZ-011 and RC-001..RC-020, and the interim identifiers used before it existed
are now superseded: HS-1..HS-7 in `docs/03` §3 map to HAZ-001..HAZ-007, and DMP-C1..C10
in `docs/06` map to RC-019, RC-001, RC-002, RC-003 and RC-004. HAZ-012..HAZ-014 and
RC-021..RC-028 are new in `docs/05` and supersede nothing. `docs/05` §3.1 and §4.1
carry both mappings; the source documents keep their own labels.

URS-002 previously had no risk control at all. `docs/05` HAZ-012 and RC-021..RC-026 now
cover the volume derivation path — the metadata half of it, which is where the invisible
failure lives (`docs/05` §5.4).

The HAZ and RC columns on the URS rows are derived, not authored: an RC appears against
a URS when it implements a requirement that URS derives, and a HAZ appears when one of
those RCs controls it.

## Coverage

- User requirements with at least one software requirement: **11 of 11**. Every URS in
  `docs/01` derives at least one SRS or NFR in `docs/02`.
- Software requirements with at least one test case: **61 of 61** — `docs/07` allocates
  TC-000..TC-113 and every SRS, NFR and RC now names a verifying test case. **24 of those
  77 test cases are implemented** (TC-000..TC-002, TC-004, TC-014, TC-015,
  TC-030..TC-035, TC-040..TC-042, TC-060..TC-062, TC-068, TC-072, TC-105,
  TC-106, TC-120 — `eval/metrics.py`, `data/splits.py`, `io/deident.py`, the spacing guard and
  the document-integrity gates, 2026-09-17); the rest are specified and
  unwritten, so this line measures allocation, not evidence.
- Hazards with at least one risk control: **14 of 14** — HAZ-001..HAZ-014 in `docs/05`
  §3.2 each carry at least one RC.
- Risk controls with a verifying test allocated: **28 of 28**; implemented: **13 of 28** — RC-002, RC-003 and RC-005
  by TC-004, RC-020 by TC-001. (`docs/05` §5.3, `docs/07` §1.2).
