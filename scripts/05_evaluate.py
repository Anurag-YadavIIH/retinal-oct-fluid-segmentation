"""Evaluate a finished run and produce the analytical validation report.

CPU-only. Emits per-class, per-vendor metrics with bootstrap confidence
intervals, the in-domain reference, the generalisation gap, the calibration
curve, and the failure gallery.

Usage:
    python scripts/05_evaluate.py --run artifacts/runs/spectralis_v1
"""

from __future__ import annotations

import sys


def main() -> int:
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
