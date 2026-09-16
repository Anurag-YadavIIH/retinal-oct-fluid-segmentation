"""Deterministic, patient-level dataset splitting.

Traces to: SRS-TBD (dataset splitting)
Implements risk control: RC-TBD (prevention of optimistically biased performance
estimates caused by patient overlap between training and evaluation sets)

This module is the single source of truth for which sample goes into which split.
Nothing elsewhere in the codebase may partition data. See CLAUDE.md rule 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Split:
    """One resolved split. Sample IDs are DICOM SOP Instance UIDs."""

    fold_id: str
    train: list[str]
    val: list[str]
    test: list[str]
    held_out_vendor: str
    seed: int


def leave_one_vendor_out(
    manifest: object,
    held_out_vendor: str,
    val_fraction: float,
    seed: int,
) -> Split:
    """Build a leave-one-vendor-out split, partitioned at patient level.

    Every patient appears in exactly one of train / val / test.
    """
    raise NotImplementedError


def assert_no_patient_overlap(split: Split, manifest: object) -> None:
    """Raise if any patient appears in more than one split.

    Called at the end of every split construction and again at the start of
    training. Never bypass, and never catch the exception it raises.
    """
    raise NotImplementedError


def save(split: Split, path: Path) -> None:
    """Persist a split so a run is reproducible from the committed config alone."""
    raise NotImplementedError


def load(path: Path) -> Split:
    """Load a previously saved split."""
    raise NotImplementedError
