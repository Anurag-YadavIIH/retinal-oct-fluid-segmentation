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
| URS-001 | TBD | TBD | TBD | TBD | TBD |
| URS-002 | TBD | TBD | TBD | TBD | TBD |
| URS-003 | TBD | TBD | TBD | TBD | TBD |
| URS-004 | TBD | TBD | TBD | TBD | TBD |
| URS-005 | TBD | TBD | TBD | TBD | TBD |
| URS-006 | TBD | TBD | TBD | TBD | TBD |
| URS-007 | TBD | TBD | TBD | TBD | TBD |
| URS-008 | TBD | TBD | TBD | TBD | TBD |
| URS-009 | TBD | TBD | TBD | TBD | TBD |
| URS-010 | TBD | TBD | TBD | TBD | TBD |
| URS-011 | TBD | TBD | TBD | TBD | TBD |
| TBD | TBD | TBD | TBD | TC-000 | `src/ocuval/__init__.py` |
| TBD | TBD | TBD | TBD | TC-001 | `configs/data.yaml` |
| TBD | TBD | TBD | DMP-C7, DMP-C8 | TC-004 | `src/ocuval/data/splits.py` |

The eleven `URS` rows carry no allocation yet: `docs/01` is drafted but `docs/02`,
`docs/05` and `docs/07` are not, so there is nothing to allocate to. The rows are
listed rather than omitted so the coverage gap is visible — that gap is the work
of milestone 2, and an empty matrix would hide it.

The three `TC` rows are the existing tests, which pre-date `docs/01` and are not
yet traced upward to a requirement.

`DMP-C7` and `DMP-C8` are the data management plan's control identifiers
(`docs/06` §6), used here as interim entries because `docs/05` does not yet exist
and no `RC-nnn` has been allocated. They are re-issued as `RC-nnn` when the risk
management file is drafted — `docs/06` §10 item 5 tracks that.

## Coverage

- User requirements with at least one software requirement: **0 of 11** — `docs/01`
  allocates URS-001..URS-011, `docs/02` does not yet exist. This is the milestone 2 gap.
- Software requirements with at least one test case: _n/a — `docs/02` not drafted_
- Risk controls with at least one verifying test: 2 of the 10 `DMP-C` controls
  (C7 and C8, both by TC-004). C9 and C10 are marked `TC-TBD` in `docs/06` §6;
  C1–C6 are verified by review or configuration rather than by test.
