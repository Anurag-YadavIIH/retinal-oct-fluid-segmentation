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
| URS-002 | SRS-003, SRS-040, SRS-046 | — | **none — gap** | TBD | `docs/02` §3 |
| URS-003 | SRS-045, SRS-047, NFR-006 | HAZ-001, HAZ-002, HAZ-003 | RC-017 | TBD | `docs/02` §3 |
| URS-004 | SRS-038, SRS-039 | HAZ-004, HAZ-010 | RC-013 | TBD | `docs/02` §3 |
| URS-005 | SRS-028, SRS-029, SRS-030, SRS-041, SRS-046, SRS-052 | HAZ-001, HAZ-002, HAZ-007 | RC-009 | TBD | `docs/02` §3 |
| URS-006 | SRS-001, SRS-009, SRS-017 | HAZ-004, HAZ-005 | RC-008 | TBD | `docs/02` §3 |
| URS-007 | SRS-018, SRS-019, SRS-020, SRS-021, SRS-022, SRS-024, SRS-032, SRS-033, SRS-035, SRS-036, SRS-037, SRS-050, SRS-051, SRS-052, SRS-053, NFR-003, NFR-005 | HAZ-001, HAZ-002, HAZ-003, HAZ-005, HAZ-008 | RC-001, RC-002, RC-003, RC-005, RC-006, RC-007 | TBD | `docs/02` §3 |
| URS-008 | SRS-003, SRS-010, SRS-025, SRS-026 | HAZ-005 | RC-016 | TBD | `docs/02` §3 |
| URS-009 | SRS-004, SRS-048 | HAZ-006 | RC-010 | TBD | `docs/02` §3 |
| URS-010 | SRS-007, SRS-008, SRS-012, SRS-013, SRS-014, SRS-015, SRS-016, SRS-023, SRS-031, SRS-034, SRS-043, SRS-044, SRS-049, SRS-051, NFR-001, NFR-002, NFR-004, NFR-007, NFR-008 | HAZ-004, HAZ-008, HAZ-009, HAZ-010, HAZ-011 | RC-004, RC-011, RC-012, RC-015, RC-018, RC-019 | TBD | `docs/02` §3 |
| URS-011 | SRS-042, SRS-044 | HAZ-006, HAZ-011 | RC-014 | TBD | `docs/02` §3 |
| — | — | — | — | TC-000 | `src/ocuval/__init__.py` — smoke test, allocated to no requirement (`docs/02` §3) |
| URS-001 | SRS-002 | HAZ-003 | RC-020 | TC-001 | `configs/data.yaml` |
| URS-007 | SRS-019, SRS-020, SRS-021 | HAZ-008 | RC-002, RC-003, RC-005 | TC-004 | `src/ocuval/data/splits.py` |

The eleven `URS` rows now carry their software requirements from `docs/02` §3.
Hazard and risk-control columns remain TBD: `docs/05` does not exist, so there is
nothing to allocate to. Test allocation is held in `docs/02` per requirement rather
than duplicated here, and is summarised under Coverage below.

The `TC` rows are the three existing tests. TC-000 is a smoke test allocated to no
requirement by design — it asserts only that the package exposes a version
identifier, which is a precondition of SRS-031 and SRS-049 rather than a
verification of either.

`docs/03` assigns the system **software safety class B**. `docs/05` allocates
HAZ-001..HAZ-011 and RC-001..RC-020, and the interim identifiers used before it existed
are now superseded: HS-1..HS-7 in `docs/03` §3 map to HAZ-001..HAZ-007, and DMP-C1..C10
in `docs/06` map to RC-019, RC-001, RC-002, RC-003 and RC-004. `docs/05` §3.1 and §4.1
carry both mappings; the source documents keep their own labels.

**URS-002 has no risk control.** That empty cell is the finding, not an omission in the
table: the volume derivation path carries no RC although a wrong volume is the harm in
HAZ-001 and HAZ-002. `docs/05` open item 5 owns it.

The HAZ and RC columns on the URS rows are derived, not authored: an RC appears against
a URS when it implements a requirement that URS derives, and a HAZ appears when one of
those RCs controls it.

## Coverage

- User requirements with at least one software requirement: **11 of 11**. Every URS in
  `docs/01` derives at least one SRS or NFR in `docs/02`.
- Software requirements with at least one test case: **4 of 53** — SRS-002 (TC-001),
  SRS-019, SRS-020 and SRS-021 (all TC-004). The remaining 49 await `docs/07`. This is
  now the largest coverage gap in the project and is the work of milestone 3 onward.
- Hazards with at least one risk control: **11 of 11** — HAZ-001..HAZ-011 in `docs/05`
  §3.2 each carry at least one RC.
- Risk controls with at least one verifying test: **4 of 20** — RC-002, RC-003 and RC-005
  by TC-004, RC-020 by TC-001. The other 16 are specified but unverified (`docs/05` §5.3),
  which is the same `docs/07` gap as the SRS coverage above.
