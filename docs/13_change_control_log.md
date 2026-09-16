<!--
Document: Change Control Log
Status: LIVING — updated per commit
Owner: Anurag Yadav
Last reviewed: 2026-09-16
Change history: this document
-->

# Change Control Log

Any change to a requirement, hazard, risk control, evaluation definition, or
frozen contract is recorded here with a date and rationale. Metrics never change
silently (CLAUDE.md rule 6).

| Date | Change | Affected IDs | Rationale | Author |
|---|---|---|---|---|
| 2026-09-16 | Repository scaffolded; document set created as templates | — | Project initiation | Anurag Yadav |
| 2026-09-16 | Working tree placed under version control (`git init`, initial commit `35027a3`). Milestone 1 status in `CLAUDE.md` §7 qualified: the recorded run (5 passed / 1 xfailed, ruff clean) pre-dates the repository, so no commit carried it and CI had never run. Result re-confirmed from inside the repo. | — | The scaffolding was complete but untracked, so no change to it was attributable or reversible, and rule 5 had no commit boundary to attach to | Anurag Yadav |
| 2026-09-16 | `docs/06_data_management_plan.md` drafted to v0.1, replacing the template (commit `8c2086b`). Establishes DMP-C1..C10 and records the §2.2 licence interpretation as a judgment. Drafted ahead of `docs/01`-`03`, out of milestone order. | DMP-C1..DMP-C10 | The §2 licence analysis is a go/no-go gate on RETOUCH and had to be answered before committing weeks of work to the dataset. No code depends on the document, so rule 1 is not engaged. Five open items remain in §10; items 2 and 3 need the data downloaded | Anurag Yadav |
| 2026-09-16 | `docs/01_intended_use.md` drafted to v0.1, replacing the template. Allocates URS-001..URS-010 and states limitations L1..L7. Intended user fixed as a supervised reading-centre grader; workflow position fixed as pre-read in a retrospective research context. `docs/09` updated in the same commit per rule 5. | URS-001..URS-010 | Milestone 2. Clinical context supplied by the author rather than assumed. Scope deliberately excludes treatment monitoring and longitudinal change: RETOUCH has one volume per subject and no repeat acquisitions, so repeatability is uncharacterised (L4) and any such claim would be unsupported | Anurag Yadav |
