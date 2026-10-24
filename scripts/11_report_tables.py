"""Regenerate the derived figures of docs/10 from the records, and check the documents.

Serves: SRS-097, SRS-098. The arithmetic lives in `ocuval.eval.report`; this is the command line.

    python scripts/11_report_tables.py            # --check: exit 1 on any difference
    python scripts/11_report_tables.py --print    # the generated tables and statements

**Never edits a document.** A difference is printed with its document and line for a person
to resolve, because a figure that disagrees with its record is a finding, not a typo to be
overwritten (`docs/13`, 2026-10-24).

Exit codes: 0 no difference; 1 at least one difference; 2 the records are absent, so nothing
was checked. The records never leave this workstation, so CI always gets 2.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ocuval.eval import report

REPO = Path(__file__).resolve().parents[1]
RUNS = REPO / "artifacts" / "runs"
ABSENT = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--print", action="store_true", help="print what the records give")
    parser.add_argument("--runs", type=Path, default=RUNS, help="artifacts/runs directory")
    args = parser.parse_args(argv)
    if not report.records_present(args.runs):
        print(f"report tables: records absent under {args.runs}; nothing was checked")
        return ABSENT
    generated = report.generate(report.load_records(args.runs))
    if args.print:
        for doc, tables in generated.tables.items():
            for t in tables:
                print(f"\n[{doc}]\n{t.header}\n" + "\n".join(t.rows))
        for doc, statements in generated.statements.items():
            print(f"\n[{doc}] statements")
            print("\n".join(f"- {s}" for s in statements))
        return 0
    differences = report.check(generated, report.read_documents(REPO))
    for d in differences:
        print(d)
    n_tables = sum(len(t) for t in generated.tables.values())
    n_statements = sum(len(s) for s in generated.statements.values())
    print(f"report tables: {len(differences)} difference(s) across {n_tables} tables and "
          f"{n_statements} statements in {', '.join(report.DOCS)}")  # fmt: skip
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main())
