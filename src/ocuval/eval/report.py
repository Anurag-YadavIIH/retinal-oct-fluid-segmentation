"""Render evaluation output into docs/10_analytical_validation_report.md and figures.

Traces to: SRS-TBD (reporting)

Runs on CPU. Inference over the full test set takes minutes without a GPU, so
report generation never needs accelerated hardware.
"""

from __future__ import annotations

from pathlib import Path


def write_results_table(results: dict, out_path: Path) -> None:
    """Write the per-class, per-vendor results table with confidence intervals."""
    raise NotImplementedError


def write_failure_gallery(results: dict, out_dir: Path, n: int = 12) -> None:
    """Render the worst-performing cases with overlays, for the failure-mode section."""
    raise NotImplementedError


def write_calibration_curve(results: dict, out_path: Path) -> None:
    """Reliability diagram for the detection arm."""
    raise NotImplementedError
