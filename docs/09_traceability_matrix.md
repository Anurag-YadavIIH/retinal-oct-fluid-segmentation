<!--
Document: Traceability Matrix
Status: NOT DRAFTED — template only
Owner: Anurag Yadav
Last reviewed: -
Change history: docs/13_change_control_log.md
-->

# Traceability Matrix

> **Status: template.** This document has not been drafted. Fill it in before
> writing any code that depends on it — see CLAUDE.md rule 1.

Updated in the same commit as any change to a requirement, hazard, or test.
A stale matrix is worse than no matrix (CLAUDE.md rule 5).

| URS | SRS | HAZ | RC | TC | Implemented in |
|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TC-000 | `src/ocuval/__init__.py` |
| TBD | TBD | TBD | TBD | TC-001 | `configs/data.yaml` |
| TBD | TBD | TBD | DMP-C7, DMP-C8 | TC-004 | `src/ocuval/data/splits.py` |

`DMP-C7` and `DMP-C8` are the data management plan's control identifiers
(`docs/06` §6), used here as interim entries because `docs/05` does not yet exist
and no `RC-nnn` has been allocated. They are re-issued as `RC-nnn` when the risk
management file is drafted — `docs/06` §10 item 5 tracks that.

## Coverage

- User requirements with at least one software requirement: _n/a — `docs/01` not drafted_
- Software requirements with at least one test case: _n/a — `docs/02` not drafted_
- Risk controls with at least one verifying test: 2 of the 10 `DMP-C` controls
  (C7 and C8, both by TC-004). C9 and C10 are marked `TC-TBD` in `docs/06` §6;
  C1–C6 are verified by review or configuration rather than by test.
