"""Build and persist a leave-one-vendor-out, patient-level split.

Asserts no patient overlap before writing. See CLAUDE.md rule 2.

Usage:
    python scripts/03_make_splits.py --config configs/folds/spectralis_holdout.yaml
"""

from __future__ import annotations

import sys


def main() -> int:
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
