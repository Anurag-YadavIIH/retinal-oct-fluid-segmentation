"""Per-vendor subgroup analysis — the headline result of the project.

Traces to: SRS-087 (patient-level intervals), SRS-032, SRS-033, SRS-053
Verifies: TC-124

Reports held-out-vendor performance against the in-domain reference and the gap between
them, per fluid class. A results table without this breakdown is incomplete and must not
be published.

**Every aggregate here goes through the patient-level cluster bootstrap** (SRS-087). That
matters most precisely in the subgroups: a per-vendor slice has fewer patients than the
whole, so the naive interval is both narrower than it should be *and* narrower than the
reader expects from the frame count they can see. The gap between two such intervals is
the number `docs/10` reports.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ocuval.eval.metrics import Estimate, bootstrap_ci_grouped

# The unit `n` counts, carried beside every estimate. `docs/07` §17.2 requires the unit to
# be named wherever `n` appears: an `n` of 420 read as patients when it means frames
# overstates the evidence by two orders of magnitude.
UNIT = "patients"


def estimate(
    values: Sequence[float],
    patients: Sequence[str],
    *,
    seed: int,
    n_resamples: int = 2000,
    alpha: float = 0.05,
) -> dict:
    """One metric as a recordable dict: value, interval, n, and the unit n counts."""
    est = bootstrap_ci_grouped(
        np.asarray(values, dtype=float),
        np.asarray(patients),
        seed=seed,
        n_resamples=n_resamples,
        alpha=alpha,
    )
    return {
        "value": est.value,
        "ci_low": est.ci_low,
        "ci_high": est.ci_high,
        "n": est.n,
        "n_unit": UNIT,
        "n_measurements": int(len(values)),
        "bootstrap": {"n_resamples": n_resamples, "alpha": alpha, "seed": seed, "unit": UNIT},
    }


def by_vendor(per_sample_metrics: Sequence[dict], vendor_field: str = "vendor") -> dict:
    """Group per-sample metrics by vendor and return estimates with intervals.

    `per_sample_metrics` is a sequence of rows, each carrying at least `vendor`,
    `patient_id`, `fluid_class`, the metric name and its value. The return is nested
    vendor -> class -> metric -> estimate, plus an `all_vendors` block computed over
    everything.

    **Pooling is offered but never substituted.** `all_vendors` sits beside the per-vendor
    blocks, never in place of them: SRS-032 forbids a foreground aggregate standing in for
    per-class figures, and the same reasoning applies across vendors -- a pooled number
    hides exactly the variation this project exists to report.
    """
    seed = _one_seed(per_sample_metrics)
    out: dict = {"n_unit": UNIT, "by_vendor": {}, "all_vendors": {}}

    vendors = sorted({row[vendor_field] for row in per_sample_metrics})
    for vendor in vendors:
        rows = [row for row in per_sample_metrics if row[vendor_field] == vendor]
        out["by_vendor"][vendor] = _by_class(rows, seed)
    out["all_vendors"] = _by_class(list(per_sample_metrics), seed)
    out["vendors"] = vendors
    return out


def _by_class(rows: Sequence[dict], seed: int) -> dict:
    classes = sorted({row["fluid_class"] for row in rows})
    metrics = sorted({row["metric"] for row in rows})
    result: dict = {}
    for fluid in classes:
        result[fluid] = {}
        for metric in metrics:
            selected = [r for r in rows if r["fluid_class"] == fluid and r["metric"] == metric]
            if not selected:
                continue
            result[fluid][metric] = estimate(
                [r["value"] for r in selected],
                [r["patient_id"] for r in selected],
                seed=seed,
            )
    return result


def _one_seed(rows: Sequence[dict]) -> int:
    seeds = {row["seed"] for row in rows if "seed" in row}
    if len(seeds) != 1:
        raise ValueError(
            f"expected exactly one bootstrap seed across the rows, found {sorted(seeds)}. "
            f"A resampling seed that varies by row makes the intervals irreproducible "
            f"(SRS-034)."
        )
    return int(next(iter(seeds)))


def generalisation_gap(in_domain: dict, held_out: dict) -> dict:
    """Difference between in-domain and held-out-vendor performance, per class.

    `gap = in_domain - held_out`, so a **positive gap means degradation** on the unseen
    vendor, which is the direction the project expects and the sign a reader will assume.
    The sign convention is stated because getting it backwards inverts the headline.

    **No confidence interval is reported on the gap itself**, and that is a deliberate
    refusal rather than an omission. A correct interval for a difference requires
    resampling both arms *jointly* under one patient draw; subtracting two independently
    bootstrapped intervals, or combining their widths, gives a number that looks like a
    confidence interval and is not one. Both arms' intervals are carried through so a
    reader can see the overlap, and the gap is reported as a point difference labelled as
    such. A joint-resample interval on the gap is a separate, pre-registered change.
    """
    out: dict = {
        "note": (
            "gap = in_domain - held_out; positive means degradation on the unseen vendor. "
            "Point difference only: no interval, because a difference of two independently "
            "bootstrapped intervals is not a confidence interval."
        ),
        "by_class": {},
    }
    classes = sorted(set(in_domain) & set(held_out))
    for fluid in classes:
        out["by_class"][fluid] = {}
        for metric in sorted(set(in_domain[fluid]) & set(held_out[fluid])):
            a, b = in_domain[fluid][metric], held_out[fluid][metric]
            out["by_class"][fluid][metric] = {
                "in_domain": a,
                "held_out": b,
                "gap": a["value"] - b["value"],
                "intervals_overlap": not (a["ci_low"] > b["ci_high"] or b["ci_low"] > a["ci_high"]),
            }
    return out


__all__ = ["UNIT", "Estimate", "by_vendor", "estimate", "generalisation_gap"]
