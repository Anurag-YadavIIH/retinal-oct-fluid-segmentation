"""Render the illustrative B-scans selected by the rule pre-registered in `docs/07` §21.

Traces to: SRS-093. Verifies: TC-132, TC-133, TC-134.

Authority: the organiser's written permission of 2026-10-08, capped by the author at six
B-scans (`docs/06` §2.2.2, DMP-C2). The rule was committed before this script existed.

**What it does, in order.**

1. Makes the same determinism request evaluation makes, before anything reaches the GPU.
2. **Selects** from the seeded held-out evaluation records alone, by `docs/07` §21.2: the
   worst, median and best scan by mean Dice over the fluid types each reference contains,
   and the largest false-positive case per fluid type. No image is read to select.
3. **Regenerates** each chosen scan's prediction through the evaluation path of
   `scripts/05_evaluate.py`, unchanged: that script's own `predict_volume`, the same
   checkpoint, transforms, seeding, passes, chunking and inversion. Each run's sealed `test`
   bucket is opened with an `Unlock` naming the reason and the approver, and logged (SRS-088).
4. **Gates.** Every chosen scan's regenerated Dice and predicted voxel count, for all three
   fluid types, must equal the sealed record exactly. If any one differs, **nothing is saved**
   and the failure is named by role, never by identifier.
5. **Renders** one B-scan per scan (`docs/07` §21.3): the expert's outline beside the
   model's, in the figures' colours, as PNGs with no metadata, under `artifacts/illustrations/`.

**What it never does.** It prints no pixel content (DMP-C12): only roles, gate results and
file names. Images and captions carry no case identifier, filename, brand or date. Nothing is
written outside `artifacts/`; images reach `docs/figures` only after the author approves them.

Usage (from the author's own terminal; the GPU run is a long run, `docs/07` §17.8):
    python scripts/09_illustrative_bscans.py --unlock-reason "..." --approved-by "..."
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import struct
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.text import Text  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FOLDS = ("cirrus", "spectralis", "topcon")
CLASSES = ("IRF", "SRF", "PED")  # label index = position + 1 (configs/data.yaml)
COLOURS = {"IRF": "#D55E00", "SRF": "#0072B2", "PED": "#009E73"}  # the figures' colours
TITLES = ("Expert outline", "Model outline")
ALLOWED_TEXT = frozenset(TITLES) | frozenset(CLASSES)
FORBIDDEN_CHUNKS = frozenset({b"tEXt", b"iTXt", b"zTXt", b"tIME", b"eXIf"})
FRAMES_PER_CHUNK = 8  # as the sealed evaluations ran; checked against each record's notes
# docs/07 section 21.9: a new directory, so the images of section 21.7 are never overwritten.
OUT = REPO / "artifacts" / "illustrations_corrected"
CITED = (re.compile(r"17\.11"), re.compile(r"(?<![\d.])21(?![\d])"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- selection: docs/07 §21.2 and §21.3 ----------------------------------------------------


def _key(scan: tuple[str, str]) -> tuple[int, str]:
    run, subject = scan
    return (FOLDS.index(run), subject)


def select(rows: list[dict], threshold: int) -> list[dict]:
    """The picks of `docs/07` §21.2, from per-scan rows of the held-out records.

    Each row carries `run`, `patient_id`, `fluid_class`, `dice`, `reference_present` and
    `predicted_voxels`. Returns at most six picks, each `{role, run, subject, fluid}`, where
    `fluid` names the type for a false-positive case and is None otherwise. Depends on the
    values only, never on the order of `rows`.
    """
    by_scan: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        by_scan.setdefault((r["run"], r["patient_id"]), []).append(r)

    eligible = []
    for scan, scan_rows in by_scan.items():
        present = [r["dice"] for r in scan_rows if r["reference_present"]]
        if present:
            eligible.append((sum(present) / len(present), *_key(scan), scan))
    eligible.sort()
    if len(eligible) < 3:
        raise ValueError("fewer than three eligible scans: worst, median and best need three")
    picks = []
    for role, position in (("worst", 0), ("median", (len(eligible) - 1) // 2), ("best", -1)):
        scan = eligible[position][-1]
        picks.append({"role": role, "run": scan[0], "subject": scan[1], "fluid": None})

    chosen = {(p["run"], p["subject"]) for p in picks}
    for fluid in CLASSES:
        candidates = sorted(
            (-r["predicted_voxels"], *_key((r["run"], r["patient_id"])))
            for r in rows
            if r["fluid_class"] == fluid
            and not r["reference_present"]
            and r["predicted_voxels"] > threshold
        )
        for _, run_index, subject in candidates:
            scan = (FOLDS[run_index], subject)
            if scan not in chosen:
                picks.append(
                    {"role": f"fp_{fluid.lower()}", "run": scan[0], "subject": subject,
                     "fluid": fluid}
                )  # fmt: skip
                chosen.add(scan)
                break
    return picks


def bscan_index(pick: dict, reference: np.ndarray, prediction: np.ndarray) -> int:
    """`docs/07` §21.3: the B-scan with the most reference fluid, or for a false-positive case
    the most predicted voxels of its type. `np.argmax` takes the lowest index on ties."""
    if pick["fluid"] is None:
        counts = (reference > 0).sum(axis=(1, 2))
    else:
        counts = (prediction == CLASSES.index(pick["fluid"]) + 1).sum(axis=(1, 2))
    return int(np.argmax(counts))


# --- the exact-match gate: docs/07 §21.4 ---------------------------------------------------


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


def gate(picks: list[dict], regenerated: dict, recorded: dict) -> list[str]:
    """Roles whose regenerated Dice or predicted voxel count differs from the sealed record.

    `regenerated` and `recorded` map `(run, subject)` to `{fluid: (dice, predicted_voxels)}`.
    Compared with `==`, no tolerance: the image must show the very prediction evaluated.
    """
    failed = []
    for p in picks:
        scan = (p["run"], p["subject"])
        mine, ref = regenerated.get(scan), recorded.get(scan)
        ok = (
            mine is not None
            and ref is not None
            and all(_same(mine[c][0], ref[c][0]) and mine[c][1] == ref[c][1] for c in CLASSES)
        )
        if not ok:
            failed.append(p["role"])
    return failed


# --- rendering and captions: docs/07 §21.5 -------------------------------------------------


def figure(display: np.ndarray, reference: np.ndarray, prediction: np.ndarray):
    """One B-scan twice: the expert's outline left, the model's right. No other text."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4))
    for ax, mask, title in zip(axes, (reference, prediction), TITLES, strict=True):
        ax.imshow(display, cmap="gray", vmin=0.0, vmax=1.0, aspect="auto",
                  interpolation="nearest")  # fmt: skip
        for index, fluid in enumerate(CLASSES, start=1):
            region = mask == index
            if region.any():
                ax.contour(region.astype(float), levels=[0.5], colors=[COLOURS[fluid]],
                           linewidths=1.4)  # fmt: skip
        ax.set_title(title, fontsize=12)
        ax.set_axis_off()
    key = [Line2D([], [], color=COLOURS[f], lw=2.5, label=f) for f in CLASSES]
    fig.legend(handles=key, loc="lower center", ncol=3, frameon=False, fontsize=11)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    return fig


def drawn_text(fig) -> set[str]:
    """Every piece of text the saved figure will draw.

    Collected from what is drawn, not from every `Text` object: axes switched off still hold
    tick-label objects that are never rendered, and counting them would make the check fail
    on text nobody can see.
    """
    found = {t.get_text() for t in fig.texts}
    for legend in fig.legends:
        found |= {t.get_text() for t in legend.get_texts()}
    for ax in fig.axes:
        found |= {ax.get_title(loc) for loc in ("left", "center", "right")}
        found |= {t.get_text() for t in ax.texts if isinstance(t, Text)}
        if ax.get_legend() is not None:
            found |= {t.get_text() for t in ax.get_legend().get_texts()}
        if ax.axison:
            found |= {ax.get_xlabel(), ax.get_ylabel()}
            found |= {t.get_text() for t in ax.get_xticklabels() + ax.get_yticklabels()}
    return {s for s in found if s.strip()}


def unexpected_text(fig) -> set[str]:
    """Any drawn text beyond the panel titles and the fluid-type key."""
    return drawn_text(fig) - ALLOWED_TEXT


def forbidden_chunks(path: Path) -> set[str]:
    """PNG chunk types that would carry text, time or EXIF metadata."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    found, at = set(), 8
    while at < len(data):
        (length,) = struct.unpack(">I", data[at : at + 4])
        kind = data[at + 4 : at + 8]
        if kind in FORBIDDEN_CHUNKS:
            found.add(kind.decode())
        at += 12 + length
    return found


def save(fig, path: Path) -> None:
    """Save as PNG with no metadata, and refuse the file if any metadata chunk got in."""
    extra = unexpected_text(fig)
    if extra:
        plt.close(fig)
        raise ValueError(f"figure carries text beyond titles and key: {sorted(extra)}")
    fig.savefig(path, format="png", dpi=150, metadata={"Software": None}, facecolor="white")
    plt.close(fig)
    leaked = forbidden_chunks(path)
    if leaked:
        path.unlink()
        raise ValueError(f"{path.name} carried metadata chunks {sorted(leaked)}; removed")


ROLE_TEXT = {
    "worst": "The lowest-scoring held-out scan",
    "median": "The median held-out scan",
    "best": "The highest-scoring held-out scan",
}


def caption(pick: dict) -> str:
    """What the image shows and the rule that chose it. No identifier, brand, file or date."""
    tail = (
        " Left, the expert's outline; right, the model's. Chosen by the rule pre-registered in "
        "`docs/07` §21, from the numbers alone, before any image was rendered."
    )
    if pick["fluid"] is None:
        return (
            f"{ROLE_TEXT[pick['role']]} by mean Dice over the fluid types its expert outline "
            "contains, shown on its B-scan with the most expert-outlined fluid." + tail
        )
    f = pick["fluid"]
    return (
        f"The largest false-positive case for {f} among the held-out scans: of the scans whose "
        f"expert outline contains no {f}, the one in which the model marked the most {f}, "
        f"shown on its B-scan with the most model-marked {f}. **This is the largest such case, "
        "not a typical one**; for typical sizes, see the predicted-voxel figure." + tail
    )


def finish(picks, slices, regenerated, recorded, out_dir: Path) -> list[str]:
    """Gate first; save every image only if every pick passes. Returns the failed roles.

    `slices` maps `(run, subject)` to `(bscan_index, display, reference, prediction)` for the
    chosen B-scan. On any failure nothing is written but the local selection record, which
    holds identifiers and stays under `artifacts/` (`docs/07` §21.5).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    failed = gate(picks, regenerated, recorded)
    index_of = {scan: entry[0] for scan, entry in slices.items()}
    record = {
        "rule": "docs/07 section 21",
        "gate": "passed" if not failed else "failed",
        "failed_roles": failed,
        "picks": [{**p, "bscan_index": index_of.get((p["run"], p["subject"]))} for p in picks],
    }
    if failed:
        (out_dir / "selection.json").write_text(json.dumps(record, indent=1) + "\n")
        return failed
    captions = []
    for p in picks:
        _, display, reference, prediction = slices[(p["run"], p["subject"])]
        name = f"bscan_{p['role']}.png"
        save(figure(display, reference, prediction), out_dir / name)
        captions.append(f"**{name}**: {caption(p)}")
    (out_dir / "captions.md").write_text("\n\n".join(captions) + "\n", encoding="utf-8")
    (out_dir / "selection.json").write_text(json.dumps(record, indent=1) + "\n")
    return []


# --- the run -------------------------------------------------------------------------------


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--unlock-reason", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--config", type=Path, default=REPO / "configs" / "train_seg.yaml")
    parser.add_argument("--data-config", type=Path, default=REPO / "configs" / "data.yaml")
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args(argv)
    if not (args.unlock_reason.strip() and args.approved_by.strip()):
        parser.error("--unlock-reason and --approved-by must say something; they are logged")
    if not all(p.search(args.unlock_reason) for p in CITED):
        parser.error("the unlock reason must cite docs/07 section 17.11 and section 21 (21.9)")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error(f"{args.output_dir} already holds files; an earlier run is never overwritten")
    if args.device != "cuda":
        parser.error(
            "the sealed records were produced on the GPU, and the exact-match gate compares "
            "with ==; a CPU run cannot reproduce them, so it is refused before anything runs"
        )
    return args


def held_out_records(records: dict) -> dict[str, Path]:
    """The held-out records the run selects and gates from: the corrected ones, and only them.

    `records` is `{fold: {"test": path}}`. Section 21.9 ran on the 24 October records under
    `corrected/`. Since docs/07 section 17.12 the current figures come from `corrected_hd95/`,
    which differ in HD95 only; the selection reads no HD95, but the run keeps its own records.
    """
    paths = {f: Path(records[f]["test"]) for f in FOLDS}
    for fold, path in paths.items():
        if path.parent.name != "corrected" or path.name != "evaluation_test.json":
            raise SystemExit(f"{fold}: {path} is not a corrected held-out record (section 21.9)")
    return paths


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    import torch
    import yaml

    if not torch.cuda.is_available():
        raise SystemExit("no CUDA device; refusing before any sealed bucket is opened")
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    data_cfg = yaml.safe_load(args.data_config.read_text(encoding="utf-8"))
    seed = int(cfg["run"]["seed"])

    from ocuval.training.checkpoint import request_determinism

    request_determinism(seed)  # first, before any CUDA context (as 05_evaluate.py:145)

    from ocuval.data.transforms import axial_target, eval_transforms, invert_axial_resample
    from ocuval.eval import sealed
    from ocuval.eval.pipeline import measure_volume
    from ocuval.io.retouch_reader import apply_intensity_window, read_volume
    from ocuval.models.seg_unet import build_model, load_verified
    from ocuval.models.uncertainty import reseed_for_volume
    from ocuval.runs import load_manifest, manifest_path

    figures = load_module("make_figures", REPO / "scripts" / "07_make_figures.py")
    evaluation = load_module("evaluate", REPO / "scripts" / "05_evaluate.py")
    run_records = figures.report.record_paths(figures.RUNS)["wrong_axes"]  # section 17.11's
    records = {f: figures.load(p) for f, p in held_out_records(run_records).items()}
    threshold = int(cfg["inference"]["presence_voxel_threshold"])
    passes = int(cfg["inference"]["mc_dropout_passes"])
    for f, rec in records.items():
        notes = rec["notes"]
        assert rec["mc_passes"] == passes and rec["presence_voxel_threshold"] == threshold, f
        assert notes["frames_per_chunk"] == FRAMES_PER_CHUNK and notes["checkpoint"] == "best.pt", f

    rows = [{**r, "run": f} for f in FOLDS for r in records[f]["per_volume"]]
    picks = select(rows, threshold)
    recorded = {}
    for r in rows:
        recorded.setdefault((r["run"], r["patient_id"]), {})[r["fluid_class"]] = (
            r["dice"], r["predicted_voxels"]
        )  # fmt: skip
    print(f"{len(picks)} picks by docs/07 section 21: {', '.join(p['role'] for p in picks)}")

    manifest = {row["patient_id"]: row for row in load_manifest(manifest_path(data_cfg))}
    chain = eval_transforms(cfg)
    regenerated, slices = {}, {}
    for fold in FOLDS:
        mine = [p for p in picks if p["run"] == fold]
        if not mine:
            continue
        unlock = sealed.Unlock(bucket="test", reason=args.unlock_reason,
                               approved_by=args.approved_by)  # fmt: skip
        sealed.require_unsealed("test", unlock, fold_id=records[fold]["fold_id"])
        print(f"opened and logged: test bucket of {records[fold]['fold_id']}", flush=True)
        model = build_model(cfg).to("cuda")
        load_verified(figures.RECORDS[fold]["dir"] / "best.pt", model, map_location="cuda",
                      restore_rng=False)  # fmt: skip
        for p in mine:
            row = manifest[p["subject"]]
            native = read_volume(Path(row["source_path"]), row["vendor"])
            reference = np.asarray(native.label_array)
            frames = [
                np.asarray(
                    chain({"image": native.pixel_array[i], "label": reference[i],
                           "intensity_window": row["intensity_window"],
                           "spacing_mm": row["spacing_mm"], "vendor": row["vendor"]})["image"]
                ).squeeze()
                for i in range(native.pixel_array.shape[0])
            ]  # fmt: skip
            reseed_for_volume(seed, p["subject"])  # as 05_evaluate.py:202, nothing in between
            labels, _scores = evaluation.predict_volume(
                model, np.stack(frames), "cuda", passes, FRAMES_PER_CHUNK
            )
            prediction = invert_axial_resample(
                labels,
                tuple(row["spacing_mm"]),
                (reference.shape[1], reference.shape[2]),
                target_axial_mm=axial_target(cfg),
            )
            prediction = np.asarray(prediction).astype(np.uint8).reshape(reference.shape)
            seg = measure_volume(prediction, reference, tuple(row["spacing_mm"]))
            dice_of = {r["fluid_class"]: r["value"] for r in seg if r["metric"] == "dice"}
            voxels_of = {
                r["fluid_class"]: int(r["voxels"])
                for r in seg
                if r["metric"] == "volume_mm3_predicted"
            }
            regenerated[(fold, p["subject"])] = {c: (dice_of[c], voxels_of[c]) for c in CLASSES}
            index = bscan_index(p, reference, prediction)
            display = apply_intensity_window(native.pixel_array[index], row["intensity_window"])
            slices[(fold, p["subject"])] = (index, display, reference[index], prediction[index])
            print(f"  {p['role']}: regenerated", flush=True)
        del model
        torch.cuda.empty_cache()

    failed = finish(picks, slices, regenerated, recorded, args.output_dir)
    if failed:
        print(f"GATE FAILED for {', '.join(failed)}: no image saved (docs/07 section 21.4)")
        return 1
    print(f"gate passed for all {len(picks)}; images and captions in {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
