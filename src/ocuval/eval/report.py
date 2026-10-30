"""Generate the derived figures of `docs/10` from the evaluation records, and check documents.

Traces to: SRS-097 (generation), SRS-098 (the check), SRS-104 (secondary HD95), SRS-037.

A *derived* figure is computed from records rather than copied from one: the pooled and
class-present comparisons, the directly bootstrapped differences, the counts the prose states,
the validation-selected threshold of `docs/07` section 19.2, and the post-hoc AUROC intervals.
Until this module they were produced by analysis scripts outside the repository, so they could
not be reproduced from committed code (`docs/13`, 2026-10-24).

Three rules hold throughout:

- **Records in, text out.** Every number comes from an evaluation record already written; the
  module opens no sealed bucket and edits no document.
- **Each bootstrap is seeded from the record it describes** (its `bootstrap` block), never from
  a default here, and every record of one table must agree on it.
- **The output is the document's own text.** Tables are generated row for row in the format the
  document prints, and the prose counts as the exact statements the document makes, so the
  check compares strings, not numbers re-parsed from prose.

Pure functions over record dicts, numpy only, so every figure is computable without a torch
runtime (CLAUDE.md section 4).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import cast

import numpy as np

from ocuval.eval import subgroup
from ocuval.eval.metrics import auroc

FOLDS = ("cirrus", "spectralis", "topcon")
CLASSES = ("IRF", "SRF", "PED")
ARMS = ("test", "in_domain_ref")
TRAINED_ON = {
    "cirrus": "spectralis + topcon",
    "spectralis": "cirrus + topcon",
    "topcon": "cirrus + spectralis",
}
RUN_DIRS = {
    "cirrus": "cirrus_holdout_stage2",
    "spectralis": "spectralis_holdout_stage3",
    "topcon": "topcon_holdout_stage3",
}
# docs/07 section 19.2, declared before any Stage 3 result. TC-140 compares it with the text.
THRESHOLD_GRID = (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000)
DEFECT = "through the defect"
# HD95 of the 24 October records, measured with the spacing on the wrong axes (docs/13,
# finding of 2026-10-25). Its own first column, so its header differs from section 10's.
WRONG_AXES = "wrong spacing axes"
# docs/07 section 17.12's records, the record until section 17.13: measured through D1 (and,
# for AUROC, D4). Kept in docs/10 section 10.3 under their own first column.
THROUGH_D1 = "through D1"
RECORD_COLUMN = "| Record "
# SRS-104: HD95 without both-empty volumes, beside the primary and labelled secondary.
SECONDARY = "secondary"
SECONDARY_HD95 = "hd95_excluding_both_empty"
NOT_DEFINED = "not defined: every volume both empty"
DOCS = {
    "docs/10": "docs/10_analytical_validation_report.md",
    "docs/12": "docs/12_model_card.md",
    "README": "README.md",
}
WORDS = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
    8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
    15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
}  # fmt: skip


# --- records -------------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordSets:
    """The record sets one generation reads, each `{fold: {arm: record}}`."""

    corrected: dict
    superseded: dict
    unseeded_cirrus: dict
    val: dict
    # The 24 October corrected records, kept for their HD95 measured on the wrong spacing axes.
    wrong_axes: dict | None = None
    # docs/07 section 17.12's records, measured through D1: docs/10 section 10.3.
    through_d1: dict | None = None


def record_paths(runs: Path) -> dict:
    """Where each record set lives under `artifacts/runs`."""
    d = {f: runs / RUN_DIRS[f] for f in FOLDS}
    return {
        # The record of record since 2026-10-30: the final re-evaluation of docs/07 section
        # 17.13, after the audit (D1 and D4 fixed), gated on an unchanged population.
        "corrected": {
            f: {a: d[f] / "audited" / f"evaluation_{a}.json" for a in ARMS} for f in FOLDS
        },
        # The record until then, section 17.12's: measured through D1 (docs/10 section 10.3).
        "through_d1": {
            f: {a: d[f] / "corrected_hd95" / f"evaluation_{a}.json" for a in ARMS} for f in FOLDS
        },
        # The 24 October records of section 17.11: HD95 measured with the spacing on the wrong
        # axes (docs/13, finding of 2026-10-25); every other value equals `corrected`.
        "wrong_axes": {
            f: {a: d[f] / "corrected" / f"evaluation_{a}.json" for a in ARMS} for f in FOLDS
        },
        # The seeded records of 2026-10-05, measured through the inversion defect.
        "superseded": {
            f: {
                a: d[f] / "repro" / f"evaluation_{a}_seeded.json"
                if f == "cirrus"
                else d[f] / f"evaluation_{a}.json"
                for a in ARMS
            }
            for f in FOLDS
        },
        # The same final records with the open `val` buckets, as the B-scan scripts read them.
        "audited": {
            f: {a: d[f] / "audited" / f"evaluation_{a}.json" for a in (*ARMS, "val")} for f in FOLDS
        },
        # Cirrus's single unseeded draw of 2026-10-01, also through the defect (docs/10 3.1).
        "unseeded_cirrus": {a: d["cirrus"] / f"evaluation_{a}.json" for a in ARMS},
        # Section 19.2 selects its threshold on `val`: the final run's open records.
        "val": {f: d[f] / "audited" / "evaluation_val.json" for f in FOLDS},
    }


def records_present(runs: Path) -> bool:
    paths = record_paths(runs)
    sets = ("corrected", "through_d1", "wrong_axes", "superseded")
    files = [p for s in sets for f in FOLDS for p in paths[s][f].values()]
    files += list(paths["unseeded_cirrus"].values()) + list(paths["val"].values())
    return all(p.is_file() for p in files)


def load_records(runs: Path) -> RecordSets:
    def load(p: Path) -> dict:
        return json.loads(Path(p).read_text(encoding="utf-8"))

    paths = record_paths(runs)
    return RecordSets(
        corrected={f: {a: load(p) for a, p in paths["corrected"][f].items()} for f in FOLDS},
        superseded={f: {a: load(p) for a, p in paths["superseded"][f].items()} for f in FOLDS},
        unseeded_cirrus={a: load(p) for a, p in paths["unseeded_cirrus"].items()},
        val={f: load(p) for f, p in paths["val"].items()},
        wrong_axes={f: {a: load(p) for a, p in paths["wrong_axes"][f].items()} for f in FOLDS},
        through_d1={f: {a: load(p) for a, p in paths["through_d1"][f].items()} for f in FOLDS},
    )


# --- computation ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Boot:
    seed: int
    n_resamples: int
    alpha: float


def boot_of(records: dict) -> Boot:
    """The one bootstrap block every record of a set shares; differing blocks are refused."""
    blocks = {
        (r["bootstrap"]["seed"], r["bootstrap"]["n_resamples"], r["bootstrap"]["alpha"])
        for arms in records.values()
        for r in arms.values()
    }
    if len(blocks) != 1:
        raise ValueError(f"records disagree on their bootstrap: {sorted(blocks)}")
    return Boot(*blocks.pop())


def rows_of(record: dict, cls: str, present_only: bool = False) -> list[dict]:
    rows = [r for r in record["per_volume"] if r["fluid_class"] == cls]
    return [r for r in rows if r["reference_present"]] if present_only else rows


def per_patient(records: dict, folds, arm: str, cls: str, present_only: bool = False):
    """One value per patient: the mean of its Dice over the given folds (docs/07 section 19.5)."""
    values: dict[str, list[float]] = {}
    for fold in folds:
        for r in rows_of(records[fold][arm], cls, present_only):
            values.setdefault(r["patient_id"], []).append(r["dice"])
    patients = sorted(values)
    return patients, np.array([sum(values[p]) / len(values[p]) for p in patients], dtype=float)


def estimate(values, patients, b: Boot) -> dict:
    return subgroup.estimate(
        values, patients, seed=b.seed, n_resamples=b.n_resamples, alpha=b.alpha
    )


def difference(
    held_patients, held: np.ndarray, ref_patients, ref: np.ndarray, b: Boot
) -> tuple[float, float, float]:
    """Held-out minus in-domain mean, with its interval under one patient draw (SRS-097, D2).

    Patients are grouped by the arms they belong to: held-out only, in-domain only, both.
    Each group is resampled with its size fixed, in that order, and a patient drawn counts in
    every arm it belongs to with that arm's value. The pooled arms share patients: every
    in-domain patient is a held-out patient in its own vendor's fold. Until 2026-10-29 the arms
    were resampled independently, which ignores that pairing (`docs/13`). With no shared
    patient, as in every per-fold comparison, the draws are exactly the earlier ones.
    """
    held_at = {p: k for k, p in enumerate(held_patients)}
    ref_at = {p: k for k, p in enumerate(ref_patients)}
    held_only = [held_at[p] for p in held_patients if p not in ref_at]
    ref_only = [ref_at[p] for p in ref_patients if p not in held_at]
    both = [(held_at[p], ref_at[p]) for p in held_patients if p in ref_at]
    rng = np.random.default_rng(b.seed)

    def draw(size: int) -> np.ndarray | None:
        return rng.integers(0, size, size=(b.n_resamples, size)) if size else None

    dh, di, db = draw(len(held_only)), draw(len(ref_only)), draw(len(both))
    held_sum = np.zeros(b.n_resamples)
    ref_sum = np.zeros(b.n_resamples)
    if dh is not None:
        held_sum += held[np.asarray(held_only)][dh].sum(axis=1)
    if di is not None:
        ref_sum += ref[np.asarray(ref_only)][di].sum(axis=1)
    if db is not None:
        pairs = np.asarray(both)
        held_sum += held[pairs[:, 0]][db].sum(axis=1)
        ref_sum += ref[pairs[:, 1]][db].sum(axis=1)
    d = held_sum / len(held) - ref_sum / len(ref)
    low, high = np.percentile(d, [100 * b.alpha / 2, 100 * (1 - b.alpha / 2)])
    return float(held.mean() - ref.mean()), float(low), float(high)


def difference_as_published(
    held: np.ndarray, ref: np.ndarray, b: Boot
) -> tuple[float, float, float]:
    """The estimator `docs/10` section 10 was published with: arms resampled independently,
    held-out draws first. Kept for those superseded figures alone, by the author's decision of
    2026-10-30 (SRS-097); every current figure uses `difference`, the joint draw (D2)."""
    rng = np.random.default_rng(b.seed)
    dh = rng.integers(0, len(held), size=(b.n_resamples, len(held)))
    di = rng.integers(0, len(ref), size=(b.n_resamples, len(ref)))
    d = held[dh].mean(axis=1) - ref[di].mean(axis=1)
    low, high = np.percentile(d, [100 * b.alpha / 2, 100 * (1 - b.alpha / 2)])
    return float(held.mean() - ref.mean()), float(low), float(high)


def overlaps(a: dict, b: dict) -> bool:
    """Closed-interval overlap. A one-patient estimate stores its value as both ends."""
    return a["ci_low"] <= b["ci_high"] and b["ci_low"] <= a["ci_high"]


def arms(records: dict, comp: str, cls: str, present_only: bool, b: Boot):
    """Held-out and in-domain arms of one comparison: patients, values and estimates."""
    folds = FOLDS if comp == "pooled" else (comp,)
    hp, h = per_patient(records, folds, "test", cls, present_only)
    ip, i = per_patient(records, folds, "in_domain_ref", cls, present_only)
    return (hp, h, estimate(h, hp, b)), (ip, i, estimate(i, ip, b))


def comparisons(records: dict, as_published: bool = False) -> dict:
    """Every arm estimate and direct difference, keyed (view, comparison, class).

    `as_published` uses the independent resample the superseded figures were published with.
    """
    b = boot_of(records)
    out = {}
    for view, present in (("all-volume", False), ("class-present", True)):
        for comp in (*FOLDS, "pooled"):
            for cls in CLASSES:
                (hp, h, he), (ip, i, ie) = arms(records, comp, cls, present, b)
                diff = (
                    difference_as_published(h, i, b)
                    if as_published
                    else difference(hp, h, ip, i, b)
                )
                out[(view, comp, cls)] = {"held": he, "ref": ie, "diff": diff}
    return out


def auroc_interval(scores, labels, b: Boot):
    """Stratified percentile interval; None when every resample scores 1 (not estimable).

    Positives and negatives are resampled separately with their counts fixed, so no
    replicate lacks either. Where every positive outranks every negative, every resample
    does too, and the percentile interval would only repeat the observed 1.
    """
    s, y = np.asarray(scores, dtype=float), np.asarray(labels, dtype=bool)
    pos, neg = np.flatnonzero(y), np.flatnonzero(~y)
    rng = np.random.default_rng(b.seed)
    reps = np.empty(b.n_resamples)
    for k in range(b.n_resamples):
        idx = np.concatenate([rng.choice(pos, pos.size), rng.choice(neg, neg.size)])
        reps[k] = auroc(s[idx], y[idx])
    if np.all(reps == 1.0):
        return None
    low, high = np.percentile(reps, [100 * b.alpha / 2, 100 * (1 - b.alpha / 2)])
    return float(low), float(high)


def auroc_interval_unstratified(scores, labels, b: Boot):
    """For comparison only: patients resampled together, replicates lacking a class dropped."""
    s, y = np.asarray(scores, dtype=float), np.asarray(labels, dtype=bool)
    rng = np.random.default_rng(b.seed)
    kept = []
    for _ in range(b.n_resamples):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].all() or (~y[idx]).all():
            continue
        kept.append(auroc(s[idx], y[idx]))
    low, high = np.percentile(kept, [100 * b.alpha / 2, 100 * (1 - b.alpha / 2)])
    return float(low), float(high), b.n_resamples - len(kept)


@dataclass(frozen=True)
class Selection:
    threshold: int
    j: Fraction | None
    ties: int
    positives: int
    negatives: int
    degenerate: str | None


def select_threshold(rows: list[dict], fixed: int, grid=THRESHOLD_GRID) -> Selection:
    """docs/07 section 19.2: Youden's J on `val`, smallest threshold on a tie, fixed if degenerate.

    Presence means more predicted voxels than the threshold (SRS-051). J is kept as an exact
    fraction, so a tie is decided by equality rather than by floating-point accident.
    """
    y = [bool(r["reference_present"]) for r in rows]
    v = [r["predicted_voxels"] for r in rows]
    p, n = sum(y), len(y) - sum(y)
    if p == 0 or n == 0:
        missing = "no `val` negative" if n == 0 else "no `val` positive"
        return Selection(fixed, None, 0, p, n, missing)
    scores = {}
    for t in grid:
        tp = sum(1 for yy, vv in zip(y, v, strict=True) if yy and vv > t)
        tn = sum(1 for yy, vv in zip(y, v, strict=True) if not yy and vv <= t)
        scores[t] = Fraction(tp, p) + Fraction(tn, n) - 1
    best = max(scores.values())
    tied = [t for t in grid if scores[t] == best]
    return Selection(min(tied), best, len(tied), p, n, None)


def specificity_at(rows: list[dict], threshold: int, b: Boot) -> dict:
    """Specificity at a threshold over the class-absent volumes, with its patient interval."""
    negatives = [r for r in rows if not r["reference_present"]]
    correct = [float(r["predicted_voxels"] <= threshold) for r in negatives]
    return estimate(correct, [r["patient_id"] for r in negatives], b)


# --- formatting ----------------------------------------------------------------------------


def f4(x: float) -> str:
    return f"{x:.4f}"


def signed(x: float) -> str:
    return f"{x:+.4f}"


def minus(text: str) -> str:
    """Prose writes negatives with U+2212; tables keep the ASCII hyphen."""
    return text.replace("-", "−")


def iv(e: dict, bold: bool = False, single: bool = True) -> str:
    """`0.4834 [0.3582, 0.5991] n=24`; one patient as "(single patient, no spread)"."""
    b = "**" if bold else ""
    if single and e["n"] == 1:
        return f"{b}{f4(e['value'])}{b} (single patient, no spread) n=1"
    return f"{b}{f4(e['value'])}{b} [{f4(e['ci_low'])}, {f4(e['ci_high'])}] n={e['n']}"


def interval_text(d: tuple[float, float, float]) -> str:
    """A difference as `+0.1023 [-0.4096, +0.6134]`."""
    return f"{signed(d[0])} [{signed(d[1])}, {signed(d[2])}]"


def word(n: int, capital: bool = False) -> str:
    w = WORDS.get(n, str(n))  # beyond eighteen the document writes digits
    return w.capitalize() if capital else w


def listing(items: list[str]) -> str:
    """`a`, `a and b`, `a, b and c`; "none" for an empty list (D10: `names[-1]` raised)."""
    if not items:
        return "none"
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def pct(k: int, n: int) -> int:
    """A percentage rounded half up, as a reader rounds (D9): 1 of 8 is 13%, not 12%."""
    return (200 * k + n) // (2 * n)


def span(values, digits: int = 2) -> str:
    return f"{min(values):.{digits}f}–{max(values):.{digits}f}"


# --- generation ----------------------------------------------------------------------------


@dataclass
class Table:
    header: str
    rows: list[str]


@dataclass
class Generated:
    """What the documents must contain: tables by exact header line, and exact statements."""

    tables: dict[str, list[Table]] = field(default_factory=dict)
    statements: dict[str, list[str]] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)

    def table(self, doc: str, header: str, rows: list[str]) -> None:
        self.tables.setdefault(doc, []).append(Table(header, rows))

    def say(self, doc: str, *texts: str) -> None:
        self.statements.setdefault(doc, []).extend(texts)


def status(prefix: str | None, header: str) -> str:
    return f"| Status {header}" if prefix else header


def lead(prefix: str | None) -> str:
    return f"| {prefix} " if prefix else ""


H_DICE = "| Held-out vendor (trained on) | Class | Held-out Dice | In-domain reference Dice | Gap | Intervals overlap |"  # noqa: E501
H_HD95 = "| Held-out vendor (trained on) | Class | Held-out HD95 (mm) | In-domain reference HD95 (mm) | Gap | Intervals overlap |"  # noqa: E501
H_POOLED = "| Class | Pooled held-out Dice | Held-out class-absent | Pooled in-domain Dice | In-domain class-absent | Gap |"  # noqa: E501
H_POOLED4 = "| Class | Pooled held-out Dice | Pooled in-domain Dice | Gap |"
H_PRESENT = "| Comparison | Class | Held-out, class present | In-domain, class present | Gap | Intervals overlap |"  # noqa: E501
H_PRESENT4 = "| Class | Held-out, class present | In-domain, class present | Gap |"
H_DIFF = "| View | Comparison | Class | Held-out − in-domain [95% interval] | Width | n (held-out / in-domain) | Excludes 0 |"  # noqa: E501
H_HALF = "| View | Half-width |"
H_SHARES = "| Class | cirrus held-out | cirrus in-domain | spectralis held-out | spectralis in-domain | topcon held-out | topcon in-domain |"  # noqa: E501
H_DRAWS = "| Class | Arm | Seeded, corrected (the record) | Seeded, through the defect | Unseeded 2026-10-01 (single draw, through the defect) |"  # noqa: E501
H_DETECT = "| Held-out vendor | Class | Arm | AUROC (positives/negatives) | AUROC 95% interval, **post-hoc** | Sensitivity | Specificity |"  # noqa: E501
H_DETECT6 = (
    "| Held-out vendor | Class | Arm | AUROC (positives/negatives) | Sensitivity | Specificity |"
)
H_ABSENT = "| Held-out vendor | Arm | IRF absent: Dice 0 / Dice 1 | SRF absent: Dice 0 / Dice 1 | PED absent: Dice 0 / Dice 1 |"  # noqa: E501
H_SELECT = "| Held-out vendor | Class | `val` +/− | Selected (J) | Held-out spec: fixed 10 → selected | In-domain spec: fixed 10 → selected |"  # noqa: E501
ARM_LABEL = {"test": "held-out", "in_domain_ref": "in-domain"}


def per_fold_rows(records: dict, metric: str, prefix: str | None = None) -> list[str]:
    """docs/10 section 3: one row per fold and class, copied from the records."""
    out = []
    for fold in FOLDS:
        for cls in CLASSES:
            h = records[fold]["test"]["segmentation"]["all_vendors"][cls][metric]
            r = records[fold]["in_domain_ref"]["segmentation"]["all_vendors"][cls][metric]
            bold = metric == "dice"
            verdict = "yes" if overlaps(h, r) else "**no**"
            out.append(
                f"{lead(prefix)}| {fold} ({TRAINED_ON[fold]}) | {cls} | {iv(h, bold)} | "
                f"{iv(r, bold)} | {signed(r['value'] - h['value'])} | {verdict} |"
            )
    return out


def secondary_hd95_rows(records: dict) -> list[str] | None:
    """SRS-104: the per-fold HD95 without both-empty volumes, or None if a record lacks it."""
    if any("segmentation_secondary" not in records[f][a] for f in FOLDS for a in ARMS):
        return None
    out = []
    for fold in FOLDS:
        for cls in CLASSES:
            h, r = (
                records[fold][arm]["segmentation_secondary"]["all_vendors"]
                .get(cls, {})
                .get(SECONDARY_HD95)
                for arm in ARMS
            )
            cells = [iv(h) if h else NOT_DEFINED, iv(r) if r else NOT_DEFINED]
            if h and r:
                cells += [signed(r["value"] - h["value"]), "yes" if overlaps(h, r) else "**no**"]
            else:
                cells += ["—", "—"]
            out.append(f"| {SECONDARY} | {fold} ({TRAINED_ON[fold]}) | {cls} | " + " | ".join(cells)
                       + " |")  # fmt: skip
    return out


def absent_counts(records: dict, cls: str, arm: str) -> tuple[int, int]:
    """Class-absent patients, and all patients, of one arm pooled over folds (patient as unit)."""
    present: dict[str, bool] = {}
    for fold in FOLDS:
        for r in rows_of(records[fold][arm], cls):
            present.setdefault(r["patient_id"], r["reference_present"])
    return sum(not v for v in present.values()), len(present)


def pooled_rows(records: dict, comps: dict, prefix: str | None = None) -> list[str]:
    out = []
    for cls in CLASSES:
        c = comps[("all-volume", "pooled", cls)]
        ah, nh = absent_counts(records, cls, "test")
        ai, ni = absent_counts(records, cls, "in_domain_ref")
        out.append(
            f"{lead(prefix)}| {cls} | {iv(c['held'], True)} | {ah}/{nh} ({pct(ah, nh)}%) | "
            f"{iv(c['ref'], True)} | {ai}/{ni} ({pct(ai, ni)}%) | "
            f"{signed(c['ref']['value'] - c['held']['value'])} |"
        )
    return out


def pooled4_rows(comps: dict, view: str, prefix: str | None = None) -> list[str]:
    """docs/12's four-column pooled tables."""
    return [
        f"{lead(prefix)}| {cls} | {iv(c['held'], True)} | {iv(c['ref'], True)} | "
        f"{signed(c['ref']['value'] - c['held']['value'])} |"
        for cls in CLASSES
        for c in [comps[(view, "pooled", cls)]]
    ]


def present_rows(comps: dict, prefix: str | None = None) -> list[str]:
    out = []
    for comp in (*FOLDS, "pooled"):
        for cls in CLASSES:
            c = comps[("class-present", comp, cls)]
            bold = comp == "pooled"
            name = "**pooled** (patient as unit)" if bold else comp
            verdict = "yes" if overlaps(c["held"], c["ref"]) else "**no**"
            out.append(
                f"{lead(prefix)}| {name} | {cls} | {iv(c['held'], bold)} | {iv(c['ref'], bold)} | "
                f"{signed(c['ref']['value'] - c['held']['value'])} | {verdict} |"
            )
    return out


def excludes_zero(d: tuple[float, float, float]) -> bool:
    return d[1] > 0 or d[2] < 0


def diff_rows(comps: dict, prefix: str | None = None) -> list[str]:
    out = []
    for view in ("all-volume", "class-present"):
        for comp in (*FOLDS, "pooled"):
            for cls in CLASSES:
                c = comps[(view, comp, cls)]
                p, lo, hi = c["diff"]
                name = "**pooled**" if comp == "pooled" else comp
                verdict = "**yes**" if excludes_zero(c["diff"]) else "no"
                if excludes_zero(c["diff"]) and c["ref"]["n"] == 1:
                    verdict += " (in-domain n=1: interval ignores in-domain variance)"
                out.append(
                    f"{lead(prefix)}| {view} | {name} | {cls} | {signed(p)} [{signed(lo)}, "
                    f"{signed(hi)}] | {hi - lo:.4f} | {c['held']['n']} / {c['ref']['n']} | "
                    f"{verdict} |"
                )
    return out


def half_widths(comps: dict) -> dict[str, tuple[float, float]]:
    out = {}
    for key, view, pooled in (
        ("all-volume, per fold", "all-volume", False),
        ("all-volume, pooled", "all-volume", True),
        ("class-present, pooled", "class-present", True),
    ):
        w = [
            (c["diff"][2] - c["diff"][1]) / 2
            for (v, comp, _), c in comps.items()
            if v == view and (comp == "pooled") == pooled
        ]
        out[key] = (min(w), max(w))  # unrounded: each stated figure is rounded once (D9)
    return out


def unreliable_below(hw: dict[str, tuple[float, float]]) -> str:
    """The per-fold maximum half-width to one place, rounded once from the unrounded value."""
    return f"{hw['all-volume, per fold'][1]:.1f}"


def half_rows(comps: dict, prefix: str | None = None) -> list[str]:
    return [
        f"{lead(prefix)}| {k} | {lo:.2f}–{hi:.2f} |" for k, (lo, hi) in half_widths(comps).items()
    ]


def detection_rows(records: dict, intervals: dict | None) -> list[str]:
    """docs/10 section 4 (with the post-hoc interval column) or docs/12 (without)."""
    out = []
    for fold in FOLDS:
        for cls in CLASSES:
            for arm in ARMS:
                det = records[fold][arm]["detection"]["all_vendors"][cls]
                a = det["auroc"]
                cells = [
                    fold,
                    cls,
                    ARM_LABEL[arm],
                    f"**{f4(a['value'])}** (+{a['positives']}/−{a['negatives']})",
                ]
                if intervals is not None:
                    ci = intervals[(fold, arm, cls)]["stratified"]
                    cells.append("not estimable (see note)" if ci is None else
                                 f"[{f4(ci[0])}, {f4(ci[1])}]")  # fmt: skip
                cells += [iv(det["sensitivity"]), iv(det["specificity"])]
                out.append("| " + " | ".join(cells) + " |")
    return out


def auroc_intervals(records: dict) -> dict:
    b = boot_of(records)
    out = {}
    for fold in FOLDS:
        for arm in ARMS:
            for cls in CLASSES:
                rows = rows_of(records[fold][arm], cls)
                if len({r["patient_id"] for r in rows}) != len(rows):
                    raise ValueError("an AUROC cell holds more than one volume of a patient")
                s = [r["score"] for r in rows]
                y = [r["reference_present"] for r in rows]
                point = auroc(np.asarray(s, dtype=float), np.asarray(y, dtype=bool))
                out[(fold, arm, cls)] = {
                    "point": point,
                    "stored": records[fold][arm]["detection"]["all_vendors"][cls]["auroc"],
                    "stratified": auroc_interval(s, y, b),
                    "unstratified": auroc_interval_unstratified(s, y, b),
                    "positives": sum(y),
                    "negatives": len(y) - sum(y),
                }
    return out


def absent_split(records: dict) -> dict:
    """Class-absent volumes per fold, arm and class, split into Dice 0 and Dice 1."""
    out = {}
    for fold in FOLDS:
        for arm in ARMS:
            for cls in CLASSES:
                dice = [r["dice"] for r in rows_of(records[fold][arm], cls)
                        if not r["reference_present"]]  # fmt: skip
                out[(fold, arm, cls)] = (sum(d == 0.0 for d in dice), sum(d == 1.0 for d in dice))
    return out


def present_beats_all(records: dict) -> int:
    count = 0
    for fold in FOLDS:
        for arm in ARMS:
            for cls in CLASSES:
                rows = rows_of(records[fold][arm], cls)
                present = [r["dice"] for r in rows if r["reference_present"]]
                if present:  # a cell with no class-present volume has no class-present Dice
                    count += sum(present) / len(present) > sum(r["dice"] for r in rows) / len(rows)
    return count


def selection_rows(corrected: dict, val: dict) -> tuple[list[str], list[str]]:
    """docs/10 section 7.3. Also returns findings where the fixed-threshold rate disagrees."""
    b = boot_of(corrected)
    fixed = corrected["cirrus"]["test"]["presence_voxel_threshold"]
    rows, findings = [], []
    for fold in FOLDS:
        for cls in CLASSES:
            sel = select_threshold(rows_of(val[fold], cls), fixed)
            if sel.degenerate:
                chosen = f"**{sel.threshold}** (degenerate: {sel.degenerate}; fixed threshold used)"
            elif sel.ties > 1:
                chosen = (
                    f"**{sel.threshold}** ({f4(float(cast(Fraction, sel.j)))}; "
                    f"tie across {sel.ties} grid points, smallest wins)"
                )
            else:
                chosen = f"**{sel.threshold}** ({f4(float(cast(Fraction, sel.j)))})"
            cells = []
            for arm in ARMS:
                vol = rows_of(corrected[fold][arm], cls)
                at_fixed = specificity_at(vol, fixed, b)
                stored = corrected[fold][arm]["detection"]["all_vendors"][cls]["specificity"]
                if (at_fixed["value"], at_fixed["n"]) != (stored["value"], stored["n"]):
                    findings.append(
                        f"{fold} {cls} {arm}: fixed-threshold specificity "
                        f"{at_fixed['value']} differs from the record {stored['value']}"
                    )
                at_sel = specificity_at(vol, sel.threshold, b)
                cells.append(f"{iv(at_fixed, single=False)} → {iv(at_sel, single=False)}")
            rows.append(f"| {fold} | {cls} | {sel.positives}/{sel.negatives} | {chosen} | "
                        f"{cells[0]} | {cells[1]} |")  # fmt: skip
    return rows, findings


def generate(sets: RecordSets) -> Generated:
    """Every table and statement the documents must carry, from the records alone."""
    g = Generated()
    cur, old = sets.corrected, sets.superseded
    # Section 10 stays as published, with the estimator it was published with (SRS-097).
    comps, comps_old = comparisons(cur), comparisons(old, as_published=True)
    keys9 = [(f, c) for f in FOLDS for c in CLASSES]

    # --- section 3: per-fold Dice and HD95, overlap and directions --------------------------
    dice_rows, hd95_rows = per_fold_rows(cur, "dice"), per_fold_rows(cur, "hd95")
    for doc in ("docs/10", "docs/12"):
        g.table(doc, H_DICE, dice_rows)
        g.table(doc, H_HD95, hd95_rows)
    # HD95's overlap verdicts, stated in the prose and so checked like every other count.
    hd95_apart = [
        f"{f} {c}"
        for f, c in keys9
        if not overlaps(
            cur[f]["test"]["segmentation"]["all_vendors"][c]["hd95"],
            cur[f]["in_domain_ref"]["segmentation"]["all_vendors"][c]["hd95"],
        )
    ]
    if hd95_apart:
        listed = listing(hd95_apart)
        for doc in ("docs/10", "docs/12"):
            g.say(doc, f"**HD95: {word(len(hd95_apart))} do not overlap**, {listed}")
    secondary = secondary_hd95_rows(cur)
    if secondary is not None:
        g.table("docs/10", f"| HD95 {H_HD95}", secondary)
    if sets.wrong_axes is not None:
        rows = per_fold_rows(sets.wrong_axes, "hd95", WRONG_AXES)
        for doc in ("docs/10", "docs/12"):
            g.table(doc, f"| Spacing {H_HD95}", rows)
    fold_cmp = [comps[("all-volume", f, c)] for f, c in keys9]
    n_overlap = sum(overlaps(c["held"], c["ref"]) for c in fold_cmp)
    worse = sum(c["diff"][0] < 0 for c in fold_cmp)
    g.say(
        "docs/10",
        f"the held-out and in-domain intervals overlap: {n_overlap} of {len(keys9)} comparisons",
        f"worse on the unseen vendor in {worse} of 9 and better in {9 - worse} of 9",
    )
    g.say("docs/12", f"**Dice: {n_overlap} of 9 comparisons overlap;")
    pooled_cmp = [comps[("all-volume", "pooled", c)] for c in CLASSES]
    pooled_overlap = sum(overlaps(c["held"], c["ref"]) for c in pooled_cmp)
    rows12 = len(keys9) + len(CLASSES)
    g.say("README", f"They overlapped in {n_overlap} of the 9 comparisons",
          f"In {n_overlap + pooled_overlap} of the {rows12} rows")  # fmt: skip
    apart = [(f, c) for (f, c), x in zip(keys9, fold_cmp, strict=True)
             if not overlaps(x["held"], x["ref"])]  # fmt: skip
    g.say("README", f"in {len(apart)} of 9 comparisons")
    if len(apart) == 1:
        f, c = apart[0]
        x = comps[("all-volume", f, c)]
        g.say(
            "docs/10",
            f"{word(len(apart))} of nine comparisons establishes a difference in Dice: {f} {c}",
            f"{f4(x['held']['value'])} [{f4(x['held']['ci_low'])}, {f4(x['held']['ci_high'])}] "
            f"n={x['held']['n']}, against {f4(x['ref']['value'])} [{f4(x['ref']['ci_low'])}, "
            f"{f4(x['ref']['ci_high'])}] n={x['ref']['n']}",
        )
        a0, a1 = absent_split(cur)[(f, "in_domain_ref", c)], absent_split(cur)[(f, "test", c)]
        n_ref = x["ref"]["n"]
        absent_ref = a0[0] + a0[1]
        cp = comps[("class-present", f, c)]["diff"]
        g.say(
            "docs/10",
            f"the in-domain arm is {pct(absent_ref, n_ref)}% {c}-absent ({absent_ref} of {n_ref} "
            f"volumes), and all {a0[0]} of those volumes scored Dice 0",
            f"{a1[1]} of the {a1[0] + a1[1]} {c}-absent volumes scored Dice 1",
            minus(f"difference interval includes zero: {interval_text(cp)}"),
        )
        g.say("docs/10", f"{f.capitalize()} {c}, {signed(comps[('all-volume', f, c)]['diff'][0])}")

    # --- section 3.1: the cirrus draws ------------------------------------------------------
    draws = []
    for cls in CLASSES:
        for arm in ARMS:
            e = [s[arm]["segmentation"]["all_vendors"][cls]["dice"]
                 for s in (cur["cirrus"], old["cirrus"], sets.unseeded_cirrus)]  # fmt: skip
            draws.append(f"| {cls} | {ARM_LABEL[arm]} | {iv(e[0])} | {iv(e[1])} | {iv(e[2])} |")
    g.table("docs/10", H_DRAWS, draws)
    shift = {
        (cls, arm): sets.unseeded_cirrus[arm]["segmentation"]["all_vendors"][cls]["dice"]["value"]
        - old["cirrus"][arm]["segmentation"]["all_vendors"][cls]["dice"]["value"]
        for cls in CLASSES
        for arm in ARMS
    }
    srf = shift.pop(("SRF", "in_domain_ref"))
    g.say(
        "docs/10",
        f"differ by at most {max(abs(v) for v in shift.values()):.4f} everywhere except "
        f"in-domain SRF, where they differ by {abs(srf):.4f}",
        f"moved by {abs(srf):.4f}",
    )

    # --- section 4: detection, and the post-hoc AUROC intervals ------------------------------
    ints = auroc_intervals(cur)
    for key, x in ints.items():
        if x["point"] != x["stored"]["value"] or (x["positives"], x["negatives"]) != (
            x["stored"]["positives"],
            x["stored"]["negatives"],
        ):
            g.findings.append(f"AUROC {key}: recomputed {x['point']} differs from the record")
    g.table("docs/10", H_DETECT, detection_rows(cur, ints))
    g.table("docs/12", H_DETECT6, detection_rows(cur, None))
    none = [k for k, x in ints.items() if x["stratified"] is None]
    informative = {k: x for k, x in ints.items() if x["stratified"] is not None}
    held_inf = {k: x for k, x in informative.items() if k[1] == "test"}
    lows = [x["stratified"][0] for x in held_inf.values()]
    ref_inf = {k: x for k, x in informative.items() if k[1] == "in_domain_ref"}
    g.say("docs/10", f"**{word(len(none), True)} cells have AUROC 1.0000, and their interval is "
                     "not estimable**")  # fmt: skip
    g.say("docs/10", f"In these {word(len(none))} cells every positive volume outranks every "
                     f"negative")  # fmt: skip
    g.say("docs/10", f"**{word(len(informative), True)} cells have AUROC below 1**, "
                     f"{word(len(held_inf))} of them held-out")  # fmt: skip
    if lows:
        g.say("docs/10", f"lower bounds {span(lows, 4)} in the held-out arms")
        g.say("docs/12", f"lower bounds {span(lows, 4)}")
    g.say("docs/12", f"{word(len(none), True)} of the eighteen cells have AUROC")
    g.say("README", f"for {word(len(none))} of the eighteen the interval is not estimable")
    gap = max(
        (
            abs(a - b)
            for x in held_inf.values()
            for a, b in zip(x["stratified"], x["unstratified"][:2], strict=True)
        ),
        default=0.0,
    )
    if gap >= 0.005:
        g.findings.append(f"unstratified AUROC bounds differ by {gap:.4f} in a held-out cell, "
                          "not within 0.005 as docs/10 section 4 states")  # fmt: skip
    for (fold, _, cls), x in ref_inf.items():
        lo, hi = x["stratified"]
        g.say(
            "docs/10",
            f"[{f4(lo)}, {f4(hi)}] for {fold} in-domain {cls} (+{x['positives']}/−"
            f"{x['negatives']})",
            f"{f4(x['unstratified'][0])} rather than {f4(lo)} as the lower bound for {fold} "
            f"in-domain {cls}",
        )
        g.say("docs/12", f"{fold} in-domain {cls}, [{f4(lo)}, {f4(hi)}]")
    spec = [cur[f][a]["detection"]["all_vendors"][c]["specificity"]["value"]
            for f in FOLDS for a in ARMS for c in CLASSES]  # fmt: skip
    held_auroc = [cur[f]["test"]["detection"]["all_vendors"][c]["auroc"]["value"]
                  for f in FOLDS for c in CLASSES]  # fmt: skip
    g.say("docs/10", f"specificity is 0.0000 in {sum(v == 0.0 for v in spec)} of {len(spec)}",
          f"AUROC {span(held_auroc)} in every held-out arm")  # fmt: skip

    # --- section 5.2: pooled all-volume, and the per-fold class-absent shares ----------------
    g.table("docs/10", H_POOLED, pooled_rows(cur, comps))
    g.table("docs/12", H_POOLED4, pooled4_rows(comps, "all-volume"))
    shares = []
    for cls in CLASSES:
        cells = []
        for fold in FOLDS:
            for arm in ARMS:
                arm_rows = rows_of(cur[fold][arm], cls)
                k = sum(not r["reference_present"] for r in arm_rows)
                cells.append(f"{k}/{len(arm_rows)} ({pct(k, len(arm_rows))}%)")
        shares.append(f"| {cls} | " + " | ".join(cells) + " |")
    g.table("docs/10", H_SHARES, shares)
    s_h, s_i = absent_counts(cur, "SRF", "test"), absent_counts(cur, "SRF", "in_domain_ref")
    p_h, p_i = absent_counts(cur, "PED", "test"), absent_counts(cur, "PED", "in_domain_ref")
    g.say("docs/10", f"{pct(*s_i)}% against {pct(*s_h)}% for SRF and {pct(*p_i)}% against "
                     f"{pct(*p_h)}% for PED")  # fmt: skip

    # --- section 5.3: class-present ---------------------------------------------------------
    g.table("docs/10", H_PRESENT, present_rows(comps))
    g.table("docs/12", H_PRESENT4, pooled4_rows(comps, "class-present"))
    pooled_present = [comps[("class-present", "pooled", c)] for c in CLASSES]
    gaps = [signed(c["ref"]["value"] - c["held"]["value"]) for c in pooled_present]
    g.say(
        "docs/10",
        minus(f"The gaps are {gaps[0]} (IRF), {gaps[1]} (SRF) and {gaps[2]} (PED)"),
        "**The in-domain class-present arms hold "
        f"{', '.join(str(c['ref']['n']) for c in pooled_present[:2])} and "
        f"{pooled_present[2]['ref']['n']} patients**",
        f"the intervals on that side are {span([c['ref']['ci_high'] - c['ref']['ci_low'] for c in pooled_present])} wide",  # noqa: E501
    )
    fold_apart = [(f, c) for f in FOLDS for c in CLASSES
                  if not overlaps(comps[("class-present", f, c)]["held"],
                                  comps[("class-present", f, c)]["ref"])]  # fmt: skip
    names = [f"{f} {c}" for f, c in fold_apart]
    strata = [comps[("class-present", f, c)]["ref"]["n"] for f, c in fold_apart]
    g.say(
        "docs/10",
        f"Per fold, {word(len(fold_apart))} comparisons do not overlap: {listing(names)}",
        f"with {listing([str(n) for n in strata])} in-domain patients",
    )

    # --- section 5.4: differences, exclusions, detection limit ------------------------------
    g.table("docs/10", H_DIFF, diff_rows(comps))
    g.table("docs/10", H_HALF, half_rows(comps))
    excl = {k: c for k, c in comps.items() if excludes_zero(c["diff"])}
    lower = sum(c["diff"][0] < 0 for c in excl.values())
    pooled_excl = {k: c for k, c in excl.items() if k[1] == "pooled"}
    hw = half_widths(comps)
    limit = min(hw["all-volume, per fold"][0], hw["all-volume, pooled"][0])
    g.say(
        "docs/10",
        f"**{word(len(excl), True)} of {len(comps)} exclude zero",
        f"Of all {len(comps)} difference intervals, {len(excl)} exclude zero, and {lower} of "
        f"those {len(excl)} have the held-out vendor lower",
        f"**per fold:** {span(hw['all-volume, per fold'])} Dice",
        f"**pooled across folds:** {span(hw['all-volume, pooled'])} Dice",
        f"smaller than about {limit:.2f} Dice cannot be detected",
        f"cross-vendor Dice differences below about {limit:.2f}",
        f"per-fold differences below about {unreliable_below(hw)}",
        f"half-widths of about {hw['class-present, pooled'][0]:.2f}",
    )
    g.say(
        "docs/12",
        f"{span(hw['all-volume, per fold'])} Dice per fold, or {span(hw['all-volume, pooled'])} "
        "pooled",
        f"smaller than about {limit:.2f} Dice cannot be detected",
    )
    g.say("README", f"smaller than about {limit:.2f} on that scale")
    # The README's other record-derived counts: the scans, and the familiar-brand group size.
    total = sum(cur[f]["test"]["n_patients"] for f in FOLDS)
    ref_n = {cur[f]["in_domain_ref"]["n_patients"] for f in FOLDS}
    if len(ref_n) == 1:
        (n_ref_each,) = ref_n
        g.say("README", f"conversion of all {total} scans",
              f"Each familiar-brand group held only {n_ref_each} patients",
              f"each familiar-brand comparison group holds {n_ref_each} patients")  # fmt: skip
    else:
        g.findings.append(f"in-domain arms differ in size: {sorted(ref_n)}")
    for (_, _, cls), excluded in pooled_excl.items():
        point, lo, hi = excluded["diff"]
        text = minus(f"{cls} {signed(point)} [{signed(lo)}, {signed(hi)}]")
        g.say("docs/10", text)
        g.say("docs/12", text)
    present_pooled_lower = [k for k, c in pooled_excl.items()
                            if k[0] == "class-present" and c["diff"][0] < 0]  # fmt: skip
    g.say("README", f"lower for {word(len(present_pooled_lower))} of the three fluid types")
    if pooled_excl:
        smallest = min(pooled_excl.values(), key=lambda c: c["ref"]["n"])
        g.say("README", f"rests on {smallest['ref']['n']} familiar-brand patients")

    # --- section 7.1 and 8.3 ----------------------------------------------------------------
    split = absent_split(cur)
    g.table("docs/10", H_ABSENT, [
        f"| {f} | {ARM_LABEL[a]} | " + " | ".join(f"{split[(f, a, c)][0]} / {split[(f, a, c)][1]}"
                                                  for c in CLASSES) + " |"
        for f in FOLDS for a in ARMS
    ])  # fmt: skip
    all_zero = sum(1 for z, o in split.values() if z + o > 0 and o == 0)
    g.say(
        "docs/10",
        f"In **{all_zero} of {len(split)}** cells every class-absent volume scored 0",
        f"Class-present Dice exceeds the all-volume figure in {present_beats_all(cur)} of "
        f"{len(split)} cells",
    )
    widths = sorted(
        (e["ci_high"] - e["ci_low"], f, c, e)
        for f in FOLDS
        for c in CLASSES
        for e in [cur[f]["in_domain_ref"]["segmentation"]["all_vendors"][c]["dice"]]
    )
    w_lo, w_hi = widths[0][0], widths[-1][0]
    _, wf, wc, we = widths[-1]
    g.say(
        "docs/10",
        f"Its Dice intervals are {w_lo:.2f}–{w_hi:.2f} wide; the widest is {wf} {wc}, "
        f"[{f4(we['ci_low'])}, {f4(we['ci_high'])}]",
    )
    g.say("docs/12", f"Dice intervals {w_lo:.2f}–{w_hi:.2f} wide")

    # --- section 7.2: fragility -------------------------------------------------------------
    u = sets.unseeded_cirrus["in_domain_ref"]["segmentation"]["all_vendors"]["SRF"]["dice"]
    s = old["cirrus"]["in_domain_ref"]["segmentation"]["all_vendors"]["SRF"]["dice"]
    corrected_srf = cur["cirrus"]["in_domain_ref"]["segmentation"]["all_vendors"]["SRF"]["dice"]
    n_ref = cur["cirrus"]["in_domain_ref"]["n_patients"]
    srf_absent = sum(1 for r in rows_of(old["cirrus"]["in_domain_ref"], "SRF")
                     if not r["reference_present"])  # fmt: skip
    draws_text = (
        f"{f4(u['value'])} in the unseeded draw and {f4(s['value'])} in the seeded one: "
        f"{signed(s['value'] - u['value'])}"
    )
    g.say(
        "docs/10",
        minus(draws_text),
        f"1/{n_ref} = {1 / n_ref:.4f}",
        f"The arm has {srf_absent} SRF-absent volumes",
        f"The corrected seeded figure is {f4(corrected_srf['value'])}",
    )

    # --- section 7.3: the validation-selected threshold -------------------------------------
    sel_rows, sel_findings = selection_rows(cur, sets.val)
    g.table("docs/10", H_SELECT, sel_rows)
    g.findings += sel_findings

    # --- section 8.8: lowest fold per class -------------------------------------------------
    def held_out_dice(fold: str, cls: str) -> float:
        return cur[fold]["test"]["segmentation"]["all_vendors"][cls]["dice"]["value"]

    lowest: dict[str, str] = {}
    for cls in CLASSES:
        lowest[cls] = min(FOLDS, key=lambda fold: held_out_dice(fold, cls))
    if lowest["SRF"] == lowest["PED"] != lowest["IRF"]:
        g.say("docs/10", f"{lowest['SRF']} is lowest for SRF and PED, and {lowest['IRF']} for IRF")

    # --- section 10 and docs/12's last section: the superseded figures ----------------------
    for doc in ("docs/10", "docs/12"):
        g.table(doc, status(DEFECT, H_DICE), per_fold_rows(old, "dice", DEFECT))
        g.table(doc, status(DEFECT, H_HD95), per_fold_rows(old, "hd95", DEFECT))
    g.table("docs/10", status(DEFECT, H_POOLED), pooled_rows(old, comps_old, DEFECT))
    g.table("docs/10", status(DEFECT, H_PRESENT), present_rows(comps_old, DEFECT))
    g.table("docs/10", status(DEFECT, H_DIFF), diff_rows(comps_old, DEFECT))
    g.table("docs/10", status(DEFECT, H_HALF), half_rows(comps_old, DEFECT))
    g.table("docs/12", status(DEFECT, H_POOLED4), pooled4_rows(comps_old, "all-volume", DEFECT))
    g.table("docs/12", status(DEFECT, H_PRESENT4),
            pooled4_rows(comps_old, "class-present", DEFECT))  # fmt: skip
    excl_old = sum(excludes_zero(c["diff"]) for c in comps_old.values())
    hw_old = half_widths(comps_old)
    limit_old = min(hw_old["all-volume, per fold"][0], hw_old["all-volume, pooled"][0])
    old_widths = sorted(
        (e["ci_high"] - e["ci_low"], f, c, e)
        for f in FOLDS
        for c in CLASSES
        for e in [old[f]["in_domain_ref"]["segmentation"]["all_vendors"][c]["dice"]]
    )
    _, of, oc, oe = old_widths[-1]
    g.say(
        "docs/10",
        f"{word(excl_old)} of the 24 difference intervals excluding zero",
        f"a detection limit of about {limit_old:.2f} Dice",
        f"{old_widths[0][0]:.2f}–{old_widths[-1][0]:.2f} with {of} {oc} widest at "
        f"[{f4(oe['ci_low'])}, {f4(oe['ci_high'])}]",
        f"class-present Dice above all-volume in {present_beats_all(old)} of 18 cells",
    )
    g.say("docs/12", f"detection limit was about {limit_old:.2f} Dice")

    # --- section 10.3: the section 17.12 records, measured through D1, as published ----------
    if sets.through_d1 is not None:
        d1 = sets.through_d1
        # The audit's largest effect on an arm's mean Dice, which the README states.
        moved = max(
            abs(cur[f][a]["segmentation"]["all_vendors"][c]["dice"]["value"]
                - d1[f][a]["segmentation"]["all_vendors"][c]["dice"]["value"])
            for f in FOLDS for a in ARMS for c in CLASSES
        )  # fmt: skip
        g.say("README", f"No average score moved by more than {moved:.4f}")
        comps_d1 = comparisons(d1, as_published=True)
        labelled = RECORD_COLUMN.rstrip() + " "
        for doc in ("docs/10", "docs/12"):
            g.table(doc, labelled + H_DICE, per_fold_rows(d1, "dice", THROUGH_D1))
            g.table(doc, labelled + H_HD95, per_fold_rows(d1, "hd95", THROUGH_D1))
        g.table("docs/10", labelled + H_POOLED, pooled_rows(d1, comps_d1, THROUGH_D1))
        g.table("docs/10", labelled + H_DIFF, diff_rows(comps_d1, THROUGH_D1))
    return g


# --- the check ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Difference:
    doc: str
    where: str
    what: str

    def __str__(self) -> str:
        return f"{self.doc}: {self.where}: {self.what}"


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def table_body(lines: list[str], header: str) -> tuple[int, list[str]] | None:
    """Line number (1-based) of the first body row, and the body rows, of the table `header`."""
    try:
        start = lines.index(header)
    except ValueError:
        return None
    body = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        body.append(line)
    return start + 3, body


def whole(statement: str, text: str) -> bool:
    """`statement` occurs in `text` and not as part of a longer number or word (D10).

    A statement that starts with a word character must not follow one, nor a digit-led one a
    decimal point; one that ends with a word character must not be followed by one, nor by a
    decimal point and a digit. "5% against" is then not found in "15% against", nor "about
    0.14" in "about 0.145"; a statement followed by a comma or full stop still is.
    """
    before = (
        r"(?<![\w.])" if statement[:1].isdigit() else r"(?<!\w)" if statement[:1].isalnum() else ""
    )
    after = r"(?!\w|\.\d)" if statement[-1:].isalnum() else ""
    return re.search(before + re.escape(statement) + after, text) is not None


def check(generated: Generated, texts: dict[str, str]) -> list[Difference]:
    """Every difference between what the records give and what the documents say.

    Reads `texts` only; never writes. A table is compared row for row, so a changed, missing
    or extra row is each reported; a statement must occur verbatim, whitespace aside.
    """
    out: list[Difference] = []
    for doc, tables in generated.tables.items():
        lines = texts[doc].splitlines()
        for t in tables:
            found = table_body(lines, t.header)
            if found is None:
                out.append(Difference(doc, t.header[:60], "table not found"))
                continue
            first, body = found
            for k in range(max(len(body), len(t.rows))):
                want = t.rows[k] if k < len(t.rows) else None
                have = body[k] if k < len(body) else None
                where = f"line {first + k}" if have is not None else f"after line {first + k - 1}"
                if want is None:
                    out.append(Difference(doc, where, f"row the records do not give: {have}"))
                elif have is None:
                    out.append(Difference(doc, where, f"row missing: {want}"))
                elif want != have:
                    out.append(Difference(doc, where, f"row differs:\n  doc:     {have}\n  "
                                                      f"records: {want}"))  # fmt: skip
    for doc, statements in generated.statements.items():
        flat = normalise(texts[doc])
        for s in statements:
            if not whole(normalise(s), flat):
                out.append(Difference(doc, "statement", f"not found: {s}"))
    for f in generated.findings:
        out.append(Difference("records", "consistency", f))
    return out


def read_documents(repo: Path) -> dict[str, str]:
    return {k: (repo / v).read_text(encoding="utf-8") for k, v in DOCS.items()}
