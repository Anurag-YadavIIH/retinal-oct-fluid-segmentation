"""Build the project report page, `site/`, from the recorded evaluations (SRS-092).

Serves: the GitHub Pages report. Computes no new result. Every figure on the page is copied
from an evaluation record, an epoch log or a split file, or computed exactly as `docs/10`
computes it, by reusing `07_make_figures.gather()`, which already refuses to proceed unless
the per-fold arms equal their records, the pooled arms equal `docs/10` §5.2 and the
differences equal `docs/10` §5.4. Every count the page states is computed here and asserted
against the document that states it.

The records are the corrected ones of the `docs/07` §17.11 re-evaluation, through
`07_make_figures.RECORDS`. The one exception is the fragility shift of `docs/10` §7.2, which is
between two draws measured through the inversion defect and is read from those records.

Two stages, so the page can be rebuilt and tested where the records are absent:

1. **extract** (needs `artifacts/` and `data/splits/`, so it runs on this workstation only):
   writes `site/data/*.json` and a CSV of every table. The downloadable per-scan rows carry
   run, arm, brand, fluid type, Dice, HD95 and predicted voxel count. They never carry the
   subject identifier, the SOP Instance UID or the reference voxel count, and they are
   **sorted by value**: the records list scans in subject order, so keeping that order
   would relink rows to subjects through position alone (`docs/06` DMP-C11, RC-030).
   **Reference presence is not in the downloads** (`docs/06` §2.5, J2), and is not in their
   sort key either, or row order would carry it. The charts need it, so the extractor also
   writes `site_src/chart_scans.json`: the same rows with presence and without HD95, which
   is chart input only and is never deployed or offered as a file.
2. **render** (needs only `site/data` and `site_src`): fills `site_src/index.template.html`
   and writes `site/index.html`, embedding the chart input for the charts. Every number in
   the page's text comes from a placeholder resolved against the data; TC-130 checks that
   the template holds none typed by hand.

Both stages are deterministic, and a file is rewritten only when its bytes change. The
static fallback figures are copied from `docs/figures` into `site/figures/`, which git
ignores; the Pages workflow copies them the same way.

Usage:
    python scripts/08_build_site.py            # extract, then render
    python scripts/08_build_site.py --render   # render from the committed site/data only
"""

from __future__ import annotations

import argparse
import csv
import html
import importlib.util
import io
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"
DATA = SITE / "data"
TEMPLATE = REPO / "site_src" / "index.template.html"
CHART_INPUT = REPO / "site_src" / "chart_scans.json"
FIGURES = REPO / "docs" / "figures"
RUNS = REPO / "artifacts" / "runs"
SPLITS = REPO / "data" / "splits"
GITHUB = "https://github.com/Anurag-YadavIIH/retinal-oct-fluid-segmentation"

FOLDS = ("cirrus", "spectralis", "topcon")
CLASSES = ("IRF", "SRF", "PED")
ARMS = (("test", "held_out"), ("in_domain_ref", "in_domain"))
BRAND = {"cirrus": "Cirrus", "spectralis": "Spectralis", "topcon": "Topcon", "pooled": "Pooled"}
# The fields a downloadable per-scan row may carry, in this order. Nothing else.
SCAN_FIELDS = ("run", "arm", "vendor", "fluid", "dice", "hd95", "predicted_voxels")
# The fields of the chart input, which is embedded in the page and never offered as a file.
CHART_FIELDS = ("run", "arm", "vendor", "fluid", "present", "dice", "predicted_voxels")
# Figures copied as static fallbacks for the charts, from docs/figures.
FALLBACKS = (
    "fig1_training_curves.png",
    "fig2_dice_intervals.svg",
    "fig3_predicted_voxels.png",
    "fig4_dice_differences.svg",
    "fig5_per_volume_dice.png",
)
# The illustrative B-scans of docs/07 section 21, in the order docs/10 section 7.4 shows them.
# They live in docs/figures and are copied in at build and deploy time, like the fallbacks, so
# site/ itself stays text only (TC-131). Captions come from the file the script generated.
ILLUSTRATIONS = (
    "bscan_worst.png",
    "bscan_median.png",
    "bscan_best.png",
    "bscan_fp_irf.png",
    "bscan_fp_srf.png",
    "bscan_fp_ped.png",
)
ILLUSTRATION_CAPTIONS = FIGURES / "illustrations.md"
# True from 2026-10-22: the B-scans show predictions misplaced by the inversion defect
# (docs/13, 2026-10-16), so they are neither shown on the page nor deployed until
# regenerated. TC-133 checks both directions of this flag.
ILLUSTRATIONS_WITHDRAWN = True
WORDS = {6: "Six", 7: "Seven", 9: "nine"}
# The cirrus in-domain record of the seeded evaluation of 2026-10-05, measured through the
# inversion defect. Section 7.2's fragility is the shift between two draws that were both
# measured that way, so it is read from this record and not from the corrected one.
FRAGILITY_SEEDED = "cirrus_holdout_stage2/repro/evaluation_in_domain_ref_seeded.json"
CURVES = ("epoch", "train_loss", "val_dice")


# --- small utilities -----------------------------------------------------------------------


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_if_changed(path: Path, content: bytes) -> bool:
    """Write only when the bytes differ, so an unchanged output is never touched."""
    if path.exists() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return True


def finite(x):
    """JSON has no NaN: a metric undefined for a scan or an arm is published as null."""
    return None if isinstance(x, float) and math.isnan(x) else x


def dumps(obj) -> bytes:
    return (json.dumps(obj, indent=1, ensure_ascii=False, allow_nan=False) + "\n").encode()


def csv_bytes(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if v is None else v for v in row])
    return buf.getvalue().encode()


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def claim(path: Path, pattern: str) -> tuple[str, ...]:
    """The groups of one statement in a document; fails if the statement is gone."""
    match = re.search(pattern, text(REPO / path))
    assert match, f"{path} no longer states {pattern!r}"
    return match.groups()


def md_table(path: str, header_prefix: str) -> list[list[str]]:
    """Body rows of the first Markdown table whose header starts with `header_prefix`."""
    lines = text(REPO / path).splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(header_prefix))
    body = []
    for ln in lines[start + 2 :]:
        if not ln.startswith("|"):
            break
        body.append([c.strip() for c in ln.strip().strip("|").split("|")])
    return body


def plain(cell: str) -> str:
    """A docs/06 cell as page text: no bold markers, and ranges written with 'to'."""
    cell = cell.replace("**", "").replace(" – ", " to ").replace("–", " to ")
    return cell.replace(" vols", " scans")


def interval(d: dict) -> dict:
    return {k: finite(d[k]) for k in ("value", "ci_low", "ci_high", "n")}


def _group(s: dict) -> tuple:
    return (
        FOLDS.index(s["run"]),
        [label for _, label in ARMS].index(s["arm"]),
        CLASSES.index(s["fluid"]),
        s["vendor"],
    )


def scan_order(s: dict) -> tuple:
    """Order of the downloadable rows: group by run, test set, fluid and brand, then by value.

    Never by subject: the records list scans in subject order, so that order would relink a
    published row to the identifier removed from it (SRS-092, RC-030). Never by presence
    either: presence is not in the downloads (J2), and grouping on it would carry it in the
    row order.
    """
    hd95 = math.inf if s["hd95"] is None else s["hd95"]
    return (*_group(s), s["dice"], hd95, s["predicted_voxels"])


def chart_order(s: dict) -> tuple:
    """Order of the chart input: as the downloads, with presence grouped, which the charts need."""
    return (*_group(s), not s["present"], s["dice"], s["predicted_voxels"])


def epochs(run_dir: Path) -> tuple[list[dict], list[dict]]:
    events = [json.loads(ln) for ln in text(run_dir / "epochs.jsonl").splitlines() if ln.strip()]
    return events, [e for e in events if e.get("event") == "epoch"]


def docs_counts() -> dict:
    """The engineering and documentation counts the page states, as `docs/09` states them.

    Needs no records, so TC-130 compares the published counts with `docs/09` in CI. They go
    stale whenever a requirement or test case is added, which on 2026-10-14 left the live
    page two commits behind until TC-129, run locally, caught it (`docs/13`).
    """
    matrix = "docs/09_traceability_matrix.md"
    counts = {
        "srs": int(claim(matrix, r"\*\*(\d+) of \d+\*\*\s+SRS")[0]),
        "registered": int(claim(matrix, r"registered\*\* in `docs/07` §6: \*\*(\d+)\*\*")[0]),
        "written": int(claim(matrix, r"\*\*written\*\*: \*\*(\d+)\*\*")[0]),
        "executed": int(claim(matrix, r"\*\*(\d+) are executed\*\*")[0]),
        "hazards": int(claim(matrix, r"Hazards with at least one risk control: \*\*(\d+) of")[0]),
        "controls": int(
            claim(matrix, r"Risk controls with a verifying test \*\*allocated\*\*: \*\*(\d+) of")[0]
        ),
        "safety_class": claim(matrix, r"software safety class ([ABC])\*\*")[0],
    }
    counts["never_run"] = counts["written"] - counts["executed"]
    return counts


# --- stage 1: extract ----------------------------------------------------------------------


def extract() -> dict[str, bytes]:
    """Every data file of the page, from the records. Returns {path from the repo root: bytes}."""
    figs = load_module("make_figures", REPO / "scripts" / "07_make_figures.py")
    comparator = load_module("compare_records", REPO / "scripts" / "compare_evaluation_records.py")
    data = figs.gather()  # asserts against the records, docs/10 §5.2 and §5.4
    records = {f: {a: figs.load(figs.RECORDS[f][a]) for a, _ in ARMS} for f in FOLDS}
    out: dict[str, bytes] = {}
    facts: dict = {}

    # Results per run, fluid type and arm, copied from the sealed records.
    per_run = []
    for fold in FOLDS:
        for cls in CLASSES:
            for arm, label in ARMS:
                rec = records[fold][arm]
                seg = rec["segmentation"]["all_vendors"][cls]
                det = rec["detection"]["all_vendors"][cls]
                per_run.append(
                    {
                        "run": fold,
                        "fluid": cls,
                        "arm": label,
                        "n": rec["n_patients"],
                        "dice": interval(seg["dice"]),
                        "hd95": interval(seg["hd95"]),
                        "sensitivity": interval(det["sensitivity"]),
                        "specificity": interval(det["specificity"]),
                        "auroc": {k: det["auroc"][k] for k in ("value", "positives", "negatives")},
                    }
                )
    pooled = []
    for cls in CLASSES:
        arms = data["arms"][("all-volume", "pooled", cls)]
        for k, (_, label) in enumerate(ARMS):
            pooled.append({"fluid": cls, "arm": label, "dice": interval(arms[k])})
    differences = []
    for (view, comp, cls), (p, lo, hi) in data["diff"].items():
        held, ref = data["arms"][(view, comp, cls)]
        differences.append(
            {
                "view": view,
                "comparison": comp,
                "fluid": cls,
                "value": p,
                "ci_low": lo,
                "ci_high": hi,
                "n_held_out": held["n"],
                "n_in_domain": ref["n"],
                "excludes_zero": lo > 0 or hi < 0,
            }
        )
    threshold = records["cirrus"]["test"]["presence_voxel_threshold"]
    boot = records["cirrus"]["test"]["bootstrap"]
    out["site/data/results.json"] = dumps(
        {"per_run": per_run, "pooled": pooled, "differences": differences}
    )

    # Per-scan rows: permitted fields only, sorted by value (SRS-092, RC-030).
    scans = []
    for fold in FOLDS:
        for arm, label in ARMS:
            for r in records[fold][arm]["per_volume"]:
                scans.append(
                    {
                        "run": fold,
                        "arm": label,
                        "vendor": r["vendor"],
                        "fluid": r["fluid_class"],
                        "present": r["reference_present"],
                        "dice": finite(r["dice"]),
                        "hd95": finite(r["hd95"]),
                        "predicted_voxels": r["predicted_voxels"],
                    }
                )
    published = sorted(({k: s[k] for k in SCAN_FIELDS} for s in scans), key=scan_order)
    chart = sorted(({k: s[k] for k in CHART_FIELDS} for s in scans), key=chart_order)
    out["site/data/per_scan.json"] = dumps({"fields": list(SCAN_FIELDS), "rows": published})
    out["site_src/chart_scans.json"] = dumps({"fields": list(CHART_FIELDS), "rows": chart})

    # Training curves, from each fold's epoch log.
    training = {}
    for fold in FOLDS:
        events, ep = epochs(figs.RECORDS[fold]["dir"])
        end = [e for e in events if e.get("event") == "session_end"][-1]
        training[fold] = {
            "epoch": [e["epoch"] for e in ep],
            "train_loss": [e["train_loss"] for e in ep],
            "val_dice": [e["val_dice"] for e in ep],
            "best_epoch": ep[-1]["best_epoch"],
            "last_epoch": ep[-1]["epoch"],
            "since_improvement": ep[-1]["since_improvement"],
            "stopped_by": end["stopped_by"],
            "resumed_at": [
                e["from_epoch"]
                for e in events
                if e.get("event") == "session_start" and e.get("resumed")
            ],
        }
        assert training[fold]["best_epoch"] == records[fold]["test"]["notes"]["checkpoint_epoch"]
    out["site/data/training.json"] = dumps(training)
    facts["best_epoch"] = {f: training[f]["best_epoch"] for f in FOLDS}
    patience = {training[f]["since_improvement"] for f in FOLDS}
    assert len(patience) == 1 and all(training[f]["stopped_by"] == "early_stopping" for f in FOLDS)
    facts["patience"] = patience.pop()

    # Dataset per brand: docs/06 measured values, and scan-level presence from the records.
    geometry = {r[0]: r for r in md_table("docs/06_data_management_plan.md", "| Vendor | Subjects")}
    spacing = {r[0]: r for r in md_table("docs/06_data_management_plan.md", "| Vendor | Lateral")}
    voxels = {r[0]: r for r in md_table("docs/06_data_management_plan.md", "| Vendor | Background")}
    absent_10 = {r[0]: r[1:] for r in md_table("docs/10_analytical_validation_report.md",
                                               "| Class | cirrus held-out")}  # fmt: skip
    dataset = []
    for k, fold in enumerate(FOLDS):
        name = BRAND[fold]
        held = [s for s in scans if s["run"] == fold and s["arm"] == "held_out"]
        n = records[fold]["test"]["n_patients"]
        assert int(geometry[name][1]) == n, f"docs/06 subjects for {name} disagree with record"
        with_fluid = {}
        for cls in CLASSES:
            present = sum(s["present"] for s in held if s["fluid"] == cls)
            stated = absent_10[cls][2 * k]  # e.g. "6/24 (25%)": absent / n
            assert stated.startswith(f"{n - present}/{n} "), (name, cls, stated)
            with_fluid[cls] = present
        dataset.append(
            {
                "brand": name,
                "patients": n,
                "bscan_size_px": plain(geometry[name][2]),
                "bscans_per_scan": plain(geometry[name][3]),
                "spacing_mm": {
                    "lateral": plain(spacing[name][1]),
                    "axial": plain(spacing[name][2]),
                    "bscan_separation": plain(spacing[name][3]),
                },
                "scans_with_fluid": with_fluid,
                "voxel_percent": {cls: float(voxels[name][2 + j]) for j, cls in enumerate(CLASSES)},
            }
        )
    out["site/data/dataset.json"] = dumps(dataset)

    # Study flow per run, from the split files; the vendor map is used here and never written.
    vendor_of = {}
    for fold in FOLDS:
        for r in records[fold]["test"]["per_volume"]:
            vendor_of[r["patient_id"]] = r["vendor"]
    flow = []
    for fold in FOLDS:
        split = json.loads(text(SPLITS / f"{fold}_holdout.json"))
        buckets = {b: split[b] for b in ("train", "val", "in_domain_ref", "test")}
        everyone = [p for ids in buckets.values() for p in ids]
        assert len(everyone) == len(set(everyone)) == len(vendor_of), "splits must partition"
        assert len(buckets["test"]) == records[fold]["test"]["n_patients"]
        assert len(buckets["in_domain_ref"]) == records[fold]["in_domain_ref"]["n_patients"]
        flow.append(
            {
                "run": fold,
                "total": len(everyone),
                "seed": split["seed"],
                **{
                    b: {
                        "n": len(ids),
                        "by_brand": {
                            BRAND[v]: sum(vendor_of[p] == v for p in ids)
                            for v in FOLDS
                            if any(vendor_of[p] == v for p in ids)
                        },
                    }
                    for b, ids in buckets.items()
                },
            }
        )
    out["site/data/flow.json"] = dumps(flow)

    # --- facts: every number the page's text states ------------------------------------------
    held_n = {f: records[f]["test"]["n_patients"] for f in FOLDS}
    ref_n = {f: records[f]["in_domain_ref"]["n_patients"] for f in FOLDS}
    facts["n_scans"] = sum(held_n.values())
    facts["n_brands"] = len(FOLDS)
    facts["n_runs"] = len(FOLDS)
    facts["n_sealed"] = sum(1 for f in FOLDS for a, _ in ARMS if records[f][a]["sealed"])
    facts["held_n"] = held_n
    facts["in_domain_n"] = sorted(set(ref_n.values()))[0]
    assert len(set(ref_n.values())) == 1
    pooled_arms = data["arms"][("all-volume", "pooled", "IRF")]
    facts["pooled_held_n"], facts["pooled_in_domain_n"] = pooled_arms[0]["n"], pooled_arms[1]["n"]
    facts["n_resamples"], facts["seed"] = boot["n_resamples"], boot["seed"]
    facts["threshold"] = threshold
    facts["mc_passes"] = records["cirrus"]["test"]["mc_passes"]
    facts["familiar_n"] = flow[0]["total"] - held_n["cirrus"]

    # Overlap of the per-fold and pooled Dice intervals (the pre-registered criterion).
    def overlaps(a, b):
        return a["ci_low"] <= b["ci_high"] and b["ci_low"] <= a["ci_high"]

    fold_pairs = [data["arms"][("all-volume", f, c)] for f in FOLDS for c in CLASSES]
    pooled_pairs = [data["arms"][("all-volume", "pooled", c)] for c in CLASSES]
    facts["overlap_folds"] = sum(overlaps(*p) for p in fold_pairs)
    facts["n_fold_comparisons"] = len(fold_pairs)
    facts["overlap_pooled"] = sum(overlaps(*p) for p in pooled_pairs)
    # The page's wording names one non-overlapping row, with the unseen brand higher, and says
    # every pooled row overlaps; it must be rewritten if the data says otherwise.
    facts["apart"] = [
        {"run": BRAND[f], "fluid": c, "unseen_higher": h["ci_low"] > r["ci_high"]}
        for (f, c), (h, r) in zip([(f, c) for f in FOLDS for c in CLASSES], fold_pairs, strict=True)
        if not overlaps(h, r)
    ]
    assert len(facts["apart"]) == 1 and facts["apart"][0]["unseen_higher"], facts["apart"]
    facts["n_apart"] = len(facts["apart"])
    assert facts["overlap_pooled"] == len(pooled_pairs), "the page says every pooled row overlaps"
    claim("docs/10_analytical_validation_report.md",
          rf"held-out and in-domain intervals overlap: {facts['overlap_folds']} of "
          rf"{facts['n_fold_comparisons']} comparisons")  # fmt: skip
    worse = sum(d["value"] < 0 for d in differences
                if d["view"] == "all-volume" and d["comparison"] != "pooled")  # fmt: skip
    facts["worse_unseen"] = worse
    facts["better_unseen"] = facts["n_fold_comparisons"] - worse
    claim("docs/10_analytical_validation_report.md",
          rf"worse on the unseen vendor in {worse} of 9 and better in "
          rf"{facts['better_unseen']} of 9")  # fmt: skip

    # Direct difference intervals (post-hoc, docs/10 §5.4).
    excl = [d for d in differences if d["excludes_zero"]]
    facts["n_differences"] = len(differences)
    facts["n_excluding"] = len(excl)
    facts["n_pooled_differences"] = sum(d["comparison"] == "pooled" for d in differences)
    facts["n_pooled_excluding"] = sum(d["comparison"] == "pooled" for d in excl)
    facts["n_excluding_lower"] = sum(d["value"] < 0 for d in excl)
    # The page names the pooled exclusions as class-present, with the unseen brand lower.
    pooled_excl = [d for d in excl if d["comparison"] == "pooled"]
    assert all(d["view"] == "class-present" and d["value"] < 0 for d in pooled_excl)
    assert len(pooled_excl) == 2, "the page's wording names exactly two pooled exclusions"
    facts["pooled_present_excluding"] = [
        {k: d[k] for k in ("fluid", "value", "ci_low", "ci_high", "n_held_out", "n_in_domain")}
        for d in pooled_excl
    ]
    av = [d for d in excl if d["view"] == "all-volume" and d["comparison"] != "pooled"]
    assert len(av) == 1
    facts["spectralis_srf"] = {k: av[0][k] for k in ("comparison", "fluid", "value", "ci_low",
                                                     "ci_high")}  # fmt: skip
    cp = [d for d in excl if d["view"] == "class-present" and d["comparison"] != "pooled"]
    facts["n_class_present_excluding"] = len(cp)
    facts["class_present_strata"] = sorted({d["n_in_domain"] for d in cp})
    claim("docs/10_analytical_validation_report.md",
          rf"\*\*{WORDS[len(excl)]} of {len(differences)} exclude zero")  # fmt: skip

    def half_widths(view, pooled_rows):
        return [
            (d["ci_high"] - d["ci_low"]) / 2
            for d in differences
            if d["view"] == view and (d["comparison"] == "pooled") == pooled_rows
        ]

    for key, view, pooled_rows, label in (
        ("halfwidth_fold", "all-volume", False, "all-volume, per fold"),
        ("halfwidth_pooled", "all-volume", True, "all-volume, pooled"),
        ("halfwidth_present_pooled", "class-present", True, "class-present, pooled"),
    ):
        hw = half_widths(view, pooled_rows)
        lo, hi = round(min(hw), 2), round(max(hw), 2)
        facts[key] = [lo, hi]
        claim("docs/10_analytical_validation_report.md",
              rf"\| {label} \| {lo:.2f}–{hi:.2f} \|")  # fmt: skip
    facts["detection_limit"] = min(facts["halfwidth_fold"][0], facts["halfwidth_pooled"][0])
    facts["unreliable_below"] = round(facts["halfwidth_fold"][1], 1)
    claim("docs/10_analytical_validation_report.md",
          rf"ifferences\s+smaller than about {facts['detection_limit']:.2f} Dice cannot be\s+"
          r"detected")  # fmt: skip

    # False positives in class-absent scans (§19.1), case mix (§5.2), detection (§4).
    cells = [(f, a, c) for f in FOLDS for _, a in ARMS for c in CLASSES]
    all_zero = 0
    for f, a, c in cells:
        absent = [s for s in scans if (s["run"], s["arm"], s["fluid"]) == (f, a, c)
                  and not s["present"]]  # fmt: skip
        all_zero += bool(absent) and all(s["dice"] == 0.0 for s in absent)
    facts["n_cells"] = len(cells)
    facts["fp_cells"] = all_zero
    claim(
        "docs/10_analytical_validation_report.md",
        rf"In \*\*{all_zero} of {len(cells)}\*\* cells every class-absent volume scored 0",
    )
    spec = [r["specificity"]["value"] for r in per_run]
    sens = [r["sensitivity"]["value"] for r in per_run]
    facts["spec_zero_cells"] = sum(v == 0.0 for v in spec)
    facts["sens_one_cells"] = sum(v == 1.0 for v in sens)
    claim("docs/10_analytical_validation_report.md",
          rf"specificity is 0\.0000 in {facts['spec_zero_cells']} of {len(cells)}")  # fmt: skip
    auroc_held = [r["auroc"]["value"] for r in per_run if r["arm"] == "held_out"]
    facts["auroc_held_range"] = [min(auroc_held), max(auroc_held)]
    claim(
        "docs/10_analytical_validation_report.md",
        rf"AUROC {min(auroc_held):.2f}–{max(auroc_held):.2f} in every\s+held-out arm",
    )
    case_mix = md_table("docs/10_analytical_validation_report.md", "| Class | Pooled held-out")
    for cls in ("SRF", "PED"):
        row = next(r for r in case_mix if r[0] == cls)
        facts[f"absent_{cls.lower()}"] = [
            int(re.search(r"\((\d+)%\)", row[2]).group(1)),
            int(re.search(r"\((\d+)%\)", row[4]).group(1)),
        ]

    # Fragility (§7.2): the cirrus in-domain SRF draws, unseeded and seeded, both measured
    # through the inversion defect; the corrected seeded value is stated beside them.
    unseeded = figs.load(RUNS / "cirrus_holdout_stage2" / "evaluation_in_domain_ref.json")
    seeded = figs.load(RUNS / FRAGILITY_SEEDED)
    u = unseeded["segmentation"]["all_vendors"]["SRF"]["dice"]["value"]
    s = seeded["segmentation"]["all_vendors"]["SRF"]["dice"]["value"]
    corrected = records["cirrus"]["in_domain_ref"]["segmentation"]["all_vendors"]["SRF"]["dice"]
    srf_absent = sum(not r["reference_present"] for r in seeded["per_volume"]
                     if r["fluid_class"] == "SRF")  # fmt: skip
    facts["fragility"] = {
        "unseeded": u,
        "seeded": s,
        "shift": u - s,
        "one_flip": 1 / ref_n["cirrus"],
        "absent": srf_absent,
        "corrected": corrected["value"],
    }
    claim("docs/10_analytical_validation_report.md",
          rf"corrected seeded figure is\s+{corrected['value']:.4f}")  # fmt: skip
    claim("docs/10_analytical_validation_report.md", rf"moved by {u - s:.4f}")

    # Reproducibility evidence, recomputed from the records rather than copied.
    repro = RUNS / "cirrus_holdout_stage2" / "repro"
    va = figs.load(repro / "evaluation_val_seeded_a.json")
    vb = figs.load(repro / "evaluation_val_seeded_b.json")
    leaves, differ = comparator.compare(va, vb)
    rows_same = json.dumps(va["per_volume"], sort_keys=True) == json.dumps(
        vb["per_volume"], sort_keys=True
    )
    assert not differ and rows_same
    facts["step0"] = {"leaves": leaves, "rows": len(va["per_volume"])}  # one per scan and class
    claim("docs/08_vv_report.md",
          rf"\*\*IDENTICAL\*\* on {leaves} of {leaves} compared leaves; also all "
          rf"{facts['step0']['rows']} per-volume rows")  # fmt: skip
    _, a = epochs(RUNS / "cirrus_holdout_stage1b")
    _, b = epochs(RUNS / "cirrus_holdout_stage2")
    keys = ("train_loss", "val_dice", "per_class_dice")
    agree = 0
    while agree < min(len(a), len(b)) and all(a[agree][k] == b[agree][k] for k in keys):
        agree += 1
    facts["training_agreement"] = {"through": agree - 1, "first_difference": agree}
    determinism = [json.loads(text(figs.RECORDS[f]["dir"] / "determinism.json")) for f in FOLDS]
    determinism += [records[f][a]["notes"]["determinism"] for f in FOLDS for a, _ in ARMS]
    facts["fallbacks"] = {
        "total": sum(d["fallback_count"] for d in determinism),
        "records": len(determinism),
    }

    # Numbers the README states for the "worth a closer look" items, read from it.
    readme = "README.md"
    facts["closer"] = {
        "hd95": [int(x) for x in claim(readme, r"disagreed on (\d+) of (\d+) random cases")],
        "spacing_factor": float(claim(readme, r"wrong by a factor of (\d+\.\d+)")[0]),
        "spacing_checks": [
            int(x)
            for x in claim(readme, r"catches (\d+) of (\d+) swapped cases; .*? catches all (\d+)")
        ],
        "stage1_fallbacks": int(claim(readme, r"non-repeatable method (\d+) times")[0]),
        "eval_differ": int(claim(readme, r"differed in (\d+) figures")[0]),
    }

    facts["docs"] = docs_counts()
    out["site/data/facts.json"] = dumps(facts)

    # CSV downloads: one per table.
    def iv_cols(d):
        return [d["value"], d["ci_low"], d["ci_high"], d["n"]]

    def iv_names(m):
        return [m, f"{m}_ci_low", f"{m}_ci_high", f"{m}_n"]

    out["site/data/results_per_run.csv"] = csv_bytes(
        ["run_unseen_brand", "fluid", "arm", "n_patients"]
        + iv_names("dice")
        + iv_names("hd95_mm")
        + iv_names("sensitivity")
        + iv_names("specificity")
        + ["auroc", "auroc_positives", "auroc_negatives"],
        [
            [r["run"], r["fluid"], r["arm"], r["n"]]
            + iv_cols(r["dice"])
            + iv_cols(r["hd95"])
            + iv_cols(r["sensitivity"])
            + iv_cols(r["specificity"])
            + [r["auroc"]["value"], r["auroc"]["positives"], r["auroc"]["negatives"]]
            for r in per_run
        ],
    )
    out["site/data/results_pooled.csv"] = csv_bytes(
        ["fluid", "arm", "dice", "dice_ci_low", "dice_ci_high", "n_patients"],
        [[r["fluid"], r["arm"], *iv_cols(r["dice"])] for r in pooled],
    )
    diff_keys = ("view", "comparison", "fluid", "value", "ci_low", "ci_high", "n_held_out",
                 "n_in_domain", "excludes_zero")  # fmt: skip
    out["site/data/differences.csv"] = csv_bytes(
        ["held_out_minus_in_domain" if k == "value" else k for k in diff_keys],
        [[d[k] for k in diff_keys] for d in differences],
    )
    out["site/data/per_scan.csv"] = csv_bytes(
        list(SCAN_FIELDS), [[s[k] for k in SCAN_FIELDS] for s in published]
    )
    out["site/data/training.csv"] = csv_bytes(
        ["run_unseen_brand", "epoch", "train_loss", "val_dice"],
        [[f, *row] for f in FOLDS for row in zip(*(training[f][k] for k in CURVES), strict=True)],
    )
    out["site/data/dataset.csv"] = csv_bytes(
        ["brand", "patients", "bscan_size_px", "bscans_per_scan"]
        + ["lateral_spacing_mm", "axial_spacing_mm", "bscan_separation_mm"]
        + [f"scans_with_{c.lower()}" for c in CLASSES]
        + [f"voxel_percent_{c.lower()}" for c in CLASSES],
        [
            [d["brand"], d["patients"], d["bscan_size_px"], d["bscans_per_scan"]]
            + list(d["spacing_mm"].values())
            + list(d["scans_with_fluid"].values())
            + list(d["voxel_percent"].values())
            for d in dataset
        ],
    )
    out["site/data/flow.csv"] = csv_bytes(
        ["run_unseen_brand", "bucket", "patients", "by_brand"],
        [
            [f["run"], b, f[b]["n"], "; ".join(f"{k} {v}" for k, v in f[b]["by_brand"].items())]
            for f in flow
            for b in ("train", "val", "in_domain_ref", "test")
        ],
    )
    return out


# --- stage 2: render -----------------------------------------------------------------------


def load_data() -> dict:
    data = {p.stem: json.loads(text(p)) for p in sorted(DATA.glob("*.json"))}
    data["chart_scans"] = json.loads(text(CHART_INPUT))
    return data


def f4(x) -> str:
    return "not defined" if x is None else f"{x:.4f}"


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def iv_cell(d: dict, extra: str = "") -> str:
    """A value with its interval on a second line, so the table stays narrow."""
    if d["value"] is None:
        return "<td class='num'>not defined</td>"
    ci = "1 patient, no interval" if d["n"] == 1 else f"[{f4(d['ci_low'])}, {f4(d['ci_high'])}]"
    return f"<td class='num'>{f4(d['value'])}<span class='ci'>{ci}{extra}</span></td>"


def th(*names: str) -> str:
    return "<tr>" + "".join(f"<th scope='col'>{n}</th>" for n in names) + "</tr>"


def results_table(d: dict) -> str:
    head = th("Run (unseen brand), fluid, test set", "n", "Dice", "HD95 (mm)", "Sensitivity",
              "Specificity", "AUROC*")  # fmt: skip
    body = []
    for r in d["results"]["per_run"]:
        arm = "unseen brand" if r["arm"] == "held_out" else "familiar brands"
        cls = "held" if r["arm"] == "held_out" else "ref"
        body.append(
            f"<tr class='{cls}'><td>{esc(BRAND[r['run']])} {esc(r['fluid'])}"
            f"<span class='arm'>{arm}</span></td><td class='num'>{r['n']}</td>"
            + iv_cell(r["dice"])
            + iv_cell(r["hd95"], f"<br>n = {r['hd95']['n']}")
            + iv_cell(r["sensitivity"])
            + iv_cell(r["specificity"])
            + f"<td class='num'>{f4(r['auroc']['value'])}<span class='ci'>"
            f"+{r['auroc']['positives']} / −{r['auroc']['negatives']}</span></td></tr>"
        )
    return f"<thead>{head}</thead><tbody>{''.join(body)}</tbody>"


def geometry_table(d: dict) -> str:
    head = th("Brand", "Patients", "B-scan size (px)", "B-scans per scan",
              "Lateral spacing (mm)", "Axial spacing (mm)", "B-scan separation (mm)")  # fmt: skip
    body = [
        f"<tr><td>{esc(r['brand'])}</td><td class='num'>{r['patients']}</td>"
        f"<td>{esc(r['bscan_size_px'])}</td><td>{esc(r['bscans_per_scan'])}</td>"
        f"<td>{esc(r['spacing_mm']['lateral'])}</td><td>{esc(r['spacing_mm']['axial'])}</td>"
        f"<td>{esc(r['spacing_mm']['bscan_separation'])}</td></tr>"
        for r in d["dataset"]
    ]
    return f"<thead>{head}</thead><tbody>{''.join(body)}</tbody>"


def fluid_table(d: dict) -> str:
    head = th("Brand", *(f"Scans with {c}" for c in CLASSES),
              *(f"{c}, share of voxels" for c in CLASSES))  # fmt: skip
    body = [
        f"<tr><td>{esc(r['brand'])}</td>"
        + "".join(
            f"<td class='num'>{r['scans_with_fluid'][c]} of {r['patients']}</td>" for c in CLASSES
        )
        + "".join(f"<td class='num'>{r['voxel_percent'][c]:.4f}%</td>" for c in CLASSES)
        + "</tr>"
        for r in d["dataset"]
    ]
    return f"<thead>{head}</thead><tbody>{''.join(body)}</tbody>"


def flow_svg(f: dict) -> str:
    """One run as a STARD-style flow diagram: every patient lands in exactly one box."""
    held = BRAND[f["run"]]
    familiar = [b for b in f["train"]["by_brand"]]
    fam_n = f["train"]["n"] + f["val"]["n"] + f["in_domain_ref"]["n"]

    def box(x, y, w, h, title, lines, cls=""):
        t = [f"<text x='{x + w / 2}' y='{y + 22}' class='t'>{esc(title)}</text>"]
        for i, ln in enumerate(lines):
            t.append(f"<text x='{x + w / 2}' y='{y + 42 + i * 17}' class='s'>{esc(ln)}</text>")
        return (
            f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='6' class='box {cls}'/>"
            + "".join(t)
        )

    def by(b):
        return ", ".join(f"{k} {v}" for k, v in f[b]["by_brand"].items())

    top = f"RETOUCH training partition: {f['total']} patients"
    held_test = [f"{f['test']['n']} patients", "sealed until the end"]
    ref_test = [f"{f['in_domain_ref']['n']}", *by("in_domain_ref").split(", "), "sealed"]
    parts = [
        box(170, 10, 300, 52, top, ["one scan per patient"]),
        "<path d='M320 62 V82 M140 82 H500 M140 82 V100 M500 82 V100' class='edge'/>",
        box(20, 100, 240, 58, f"Unseen brand: {held}", [f"{f['test']['n']} patients"], "held"),
        box(380, 100, 240, 58, "Familiar brands", [f"{' and '.join(familiar)}: {fam_n} patients"]),
        "<path d='M140 158 V230 M500 158 V178 M393 178 H607 M393 178 V196 M500 178 V196 "
        "M607 178 V196' class='edge'/>",
        box(20, 230, 240, 78, "Unseen-brand test", held_test, "held"),
        box(343, 196, 100, 112, "Training", [f"{f['train']['n']}", *by("train").split(", ")]),
        box(450, 196, 100, 112, "Validation", [f"{f['val']['n']}", *by("val").split(", ")]),
        box(557, 196, 100, 112, "Familiar test", ref_test, "ref"),
    ]
    return (
        f"<svg viewBox='0 0 670 320' role='img' class='flow' aria-label='Flow of {f['total']} "
        f"patients in the run with {esc(held)} held out'>{''.join(parts)}</svg>"
    )


def flow_block(d: dict) -> str:
    return "".join(
        f"<figure class='flowfig'><figcaption>Run {k + 1}: {esc(BRAND[f['run']])} held out"
        f"</figcaption>{flow_svg(f)}</figure>"
        for k, f in enumerate(d["flow"])
    )


DOWNLOADS = (
    ("results_per_run.csv", "Results per run, fluid type and arm: Dice, HD95, sensitivity, "
     "specificity with 95% intervals and n, and AUROC with its positives and negatives"),
    ("results_pooled.csv", "Dice pooled across the three runs, patient as the unit (post-hoc)"),
    ("differences.csv", "Unseen minus familiar Dice, bootstrapped directly, all scans and "
     "fluid-present scans only (post-hoc)"),
    ("per_scan.csv", "Every scan's Dice, HD95 and predicted voxel count, per fluid type; "
     "no identifiers and no reference presence, sorted by value"),
    ("training.csv", "Training loss and validation Dice per epoch, per run"),
    ("dataset.csv", "Scan geometry, pixel spacing and fluid prevalence per brand"),
    ("flow.csv", "Patients per split bucket and brand, per run"),
)  # fmt: skip


def downloads(d: dict) -> str:
    items = [
        f"<li><a href='data/{name}' download>{name}</a>: {esc(desc)}</li>"
        for name, desc in DOWNLOADS
    ]
    json_links = ", ".join(
        f"<a href='data/{n}.json'>{n}.json</a>"
        for n in ("results", "per_scan", "training", "dataset", "flow", "facts")
    )
    items.append(f"<li>The same data as JSON: {json_links}</li>")
    return "<ul class='downloads'>" + "".join(items) + "</ul>"


def inline_markdown(s: str) -> str:
    """The two inline forms the generated captions use: `code` and **bold**. Escaped first."""
    s = esc(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)


def illustrations_block() -> str:
    """The illustrative B-scans with their generated captions, in `ILLUSTRATIONS` order.

    Each image links to its own file, so a click opens it at full resolution.
    """
    captions = dict(re.findall(r"^\*\*([\w.]+)\*\*: (.+)$", text(ILLUSTRATION_CAPTIONS), re.M))
    assert set(captions) == set(ILLUSTRATIONS), "illustrations.md and ILLUSTRATIONS disagree"
    figures = [
        f"<figure class='bscan'><a href='figures/{name}'><img src='figures/{name}' "
        f"alt='One B-scan: the expert outline on the left and the model outline on the right' "
        f"loading='lazy'></a><figcaption>{inline_markdown(captions[name])}</figcaption></figure>"
        for name in ILLUSTRATIONS
    ]
    return "<div class='bscans'>" + "".join(figures) + "</div>"


PLACEHOLDER = re.compile(r"\{\{\s*(!?)([\w.]+)(?::([^}]+))?\s*\}\}")


def resolve(ctx: dict, path: str):
    node = ctx
    for part in path.split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def render(d: dict) -> bytes:
    blocks = {
        "results_table": results_table(d),
        "geometry_table": geometry_table(d),
        "fluid_table": fluid_table(d),
        "flow": flow_block(d),
        "downloads": downloads(d),
        "illustrations": illustrations_block(),
        # The charts read per-scan rows with presence: the chart input, not the download.
        "data_json": json.dumps(
            {"per_scan": d["chart_scans"], **{k: d[k] for k in ("results", "training", "facts")}},
            separators=(",", ":"),
            ensure_ascii=False,
        ).replace("</", "<\\/"),
    }
    ctx = {"facts": d["facts"], "github": GITHUB}

    def fill(m):
        raw, path, spec = m.groups()
        if raw:
            return blocks[path]
        value = resolve(ctx, path)
        return esc(format(value, spec) if spec else value)

    page = PLACEHOLDER.sub(fill, text(TEMPLATE))
    assert "{{" not in page, "unresolved placeholder"
    return page.encode()


def build(do_extract: bool) -> list[str]:
    changed = []
    if do_extract:
        for rel, content in extract().items():
            if write_if_changed(REPO / rel, content):
                changed.append(rel)
    if write_if_changed(SITE / "index.html", render(load_data())):
        changed.append("site/index.html")
    # The illustrative B-scans are withdrawn from the page until regenerated: they show
    # predictions misplaced by the inversion defect (docs/13, 2026-10-16). Not copied here,
    # and not deployed by the Pages workflow; the files stay in docs/figures.
    for name in FALLBACKS:
        if write_if_changed(SITE / "figures" / name, (FIGURES / name).read_bytes()):
            changed.append(f"site/figures/{name}")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--render", action="store_true", help="render from site/data only")
    args = parser.parse_args(argv)
    changed = build(do_extract=not args.render)
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"{stamp} site built; changed: {', '.join(changed) if changed else 'nothing'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
