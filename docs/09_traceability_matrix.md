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
| URS-001 | SRS-001, SRS-002, SRS-005, SRS-006, SRS-011, SRS-027, SRS-050, SRS-038 | TBD | TBD | TBD | `docs/02` §3 |
| URS-002 | SRS-003, SRS-040, SRS-046 | TBD | TBD | TBD | `docs/02` §3 |
| URS-003 | SRS-045, SRS-047, NFR-006 | TBD | TBD | TBD | `docs/02` §3 |
| URS-004 | SRS-038, SRS-039 | TBD | TBD | TBD | `docs/02` §3 |
| URS-005 | SRS-028, SRS-029, SRS-030, SRS-052, SRS-041, SRS-046 | TBD | TBD | TBD | `docs/02` §3 |
| URS-006 | SRS-001, SRS-009, SRS-017 | TBD | TBD | TBD | `docs/02` §3 |
| URS-007 | SRS-018, SRS-019, SRS-020, SRS-021, SRS-022, SRS-024, SRS-032, SRS-033, SRS-035, SRS-036, SRS-037, SRS-050, SRS-051, SRS-052, SRS-053, NFR-003, NFR-005 | TBD | TBD | TBD | `docs/02` §3 |
| URS-008 | SRS-003, SRS-010, SRS-025, SRS-026 | TBD | TBD | TBD | `docs/02` §3 |
| URS-009 | SRS-004, SRS-048 | TBD | TBD | TBD | `docs/02` §3 |
| URS-010 | SRS-007, SRS-008, SRS-012, SRS-013, SRS-014, SRS-015, SRS-016, SRS-023, SRS-031, SRS-034, SRS-051, SRS-043, SRS-044, SRS-049, NFR-001, NFR-002, NFR-004, NFR-007, NFR-008 | TBD | TBD | TBD | `docs/02` §3 |
| URS-011 | SRS-042, SRS-044 | TBD | TBD | TBD | `docs/02` §3 |
| — | — | — | — | TC-000 | `src/ocuval/__init__.py` — smoke test, allocated to no requirement (`docs/02` §3) |
| URS-001 | SRS-002 | TBD | TBD | TC-001 | `configs/data.yaml` |
| URS-007 | SRS-019, SRS-020, SRS-021 | TBD | DMP-C7, DMP-C8 | TC-004 | `src/ocuval/data/splits.py` |

The eleven `URS` rows now carry their software requirements from `docs/02` §3.
Hazard and risk-control columns remain TBD: `docs/05` does not exist, so there is
nothing to allocate to. Test allocation is held in `docs/02` per requirement rather
than duplicated here, and is summarised under Coverage below.

The `TC` rows are the three existing tests. TC-000 is a smoke test allocated to no
requirement by design — it asserts only that the package exposes a version
identifier, which is a precondition of SRS-031 and SRS-049 rather than a
verification of either.

`docs/03` assigns the system **software safety class B** and identifies hazardous
situations HS-1..HS-7. `HS-n` are local to `docs/03`; `docs/05` allocates the `HAZ-nnn`
identifiers and may merge or split them, at which point the HAZ column here is filled
and the interim `DMP-C` entries below are superseded by `RC-nnn`.

`DMP-C7` and `DMP-C8` are the data management plan's control identifiers
(`docs/06` §6), used here as interim entries because `docs/05` does not yet exist
and no `RC-nnn` has been allocated. They are re-issued as `RC-nnn` when the risk
management file is drafted — `docs/06` §10 item 5 tracks that.

## Coverage

- User requirements with at least one software requirement: **11 of 11**. Every URS in
  `docs/01` derives at least one SRS or NFR in `docs/02`.
- Software requirements with at least one test case: **4 of 53** — SRS-002 (TC-001),
  SRS-019, SRS-020 and SRS-021 (all TC-004). The remaining 49 await `docs/07`. This is
  now the largest coverage gap in the project and is the work of milestone 3 onward.
- Hazardous situations with at least one risk control: **0 of 7 formally** — HS-1..HS-7
  in `docs/03` §3 are identified but carry no allocated `HAZ-nnn` or `RC-nnn` until
  `docs/05` is drafted. External controls ERC-1..ERC-6 are assessed in `docs/03` §4.
- Risk controls with at least one verifying test: 2 of the 10 `DMP-C` controls
  (C7 and C8, both by TC-004). C9 and C10 are marked `TC-TBD` in `docs/06` §6;
  C1–C6 are verified by review or configuration rather than by test.
