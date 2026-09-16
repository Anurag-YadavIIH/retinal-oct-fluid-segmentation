"""Per-vendor subgroup analysis — the headline result of the project.

Traces to: SRS-TBD (subgroup reporting)

Reports held-out-vendor performance against the in-domain reference and the gap
between them, per fluid class. A results table without this breakdown is
incomplete and must not be published.
"""

from __future__ import annotations


def by_vendor(per_sample_metrics: object, vendor_field: str = "vendor") -> dict:
    """Group per-sample metrics by vendor and return estimates with intervals."""
    raise NotImplementedError


def generalisation_gap(in_domain: dict, held_out: dict) -> dict:
    """Difference between in-domain and held-out-vendor performance, per class."""
    raise NotImplementedError
