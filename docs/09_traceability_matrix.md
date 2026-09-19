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
HAZ-001..HAZ-015 and RC-001..RC-029. The interim identifiers used before it existed are
superseded: HS-1..HS-7 in `docs/03` §3 map to HAZ-001..HAZ-007, and DMP-C1..C10 in
`docs/06` map to RC-019, RC-001, RC-002, RC-003 and RC-004. HAZ-012..HAZ-015 and
RC-021..RC-029 are new in `docs/05` and supersede nothing. `docs/05` §3.1 and §4.1 carry
both mappings; the source documents keep their own labels.

URS-002 previously had no risk control at all. `docs/05` HAZ-012 and RC-021..RC-026 now
cover the volume derivation path — the metadata half of it, which is where the invisible
failure lives (`docs/05` §5.4). HAZ-015 and RC-029 cover the related case of acquisition
context the source never recorded being fabricated to satisfy a mandatory attribute.

## Coverage

Regenerated from `docs/01`, `docs/02`, `docs/05` and `docs/07`, and from the test suite
itself — implemented counts are read from the `test_TC_nnn_` function names, not from a
memory of what was written. TC-104 is allocated to keep this section honest once
implemented.

- User requirements with at least one software requirement: **11 of 11**. Every URS in
  `docs/01` derives at least one SRS or NFR in `docs/02`.
- Software requirements with a verifying test case **allocated**: **65 of 65**
  SRS and **8 of 8** NFR. `docs/07` allocates 80 test cases
  and every SRS, NFR and RC names one.
- Test cases **implemented**: **36 of 80**, covering
  `eval/metrics.py`, `data/splits.py`, `io/deident.py`, `io/dicom_writer.py`, the spacing
  guard in `io/retouch_reader.py`, the two document-integrity gates and the MONAI
  cross-check. The remaining 44 are specified and
  unwritten.
- Hazards with at least one risk control: **15 of 15** — every HAZ in `docs/05`
  §3.2 carries at least one RC.
- Risk controls with a verifying test **allocated**: **29 of 29**;
  **implemented: 20 of 29** (RC-002, RC-003, RC-004, RC-005, RC-006, RC-007, RC-008, RC-009, RC-011, RC-012, RC-013, RC-015, RC-016, RC-020, RC-022, RC-023, RC-024, RC-025, RC-026, RC-029). The rest name an
  allocated but unwritten test case (`docs/05` §5.3, `docs/07` §1.2).

**Allocation and implementation are kept as separate numbers throughout.** They are very
different claims, and a single figure covering both would flatter the project.
