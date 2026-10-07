"""Draw the Stage 3 result figures into docs/figures/ from the recorded evaluations.

Serves: `docs/10`. Computes no reported number. Every value drawn here is already tabulated in
`docs/08` §5g or `docs/10`, and the script **refuses to draw** if what it computes from the
records disagrees with them:

- every per-fold Dice value and interval must equal the stored record exactly;
- every pooled Dice value and interval must equal the one printed in `docs/10` §5.2;
- every difference interval must equal the one printed in `docs/10` §5.4 (to its 4 decimals);
- every interval must lie inside its axis, so none is clipped, and every count a caption states
  is computed and asserted, not typed.

**Inputs**, read only: the seeded evaluation records of the three folds (`test` and
`in_domain_ref`), their per-volume rows (SRS-089), and each fold's `epochs.jsonl`. No sealed
bucket is opened -- these are the records the sealed runs already wrote. **No image, B-scan,
reference mask or patient identifier appears in any figure.**

**Deterministic.** Point jitter is a fixed function of position, not random; PNG metadata
(which carries the matplotlib version) is stripped; the same records always give byte-identical
files. **One look throughout:** held-out vermillion, in-domain blue (Okabe-Ito, colour-blind
safe); folds cirrus, spectralis, topcon; classes IRF, SRF, PED.

**Not drawn: ROC curves.** They need each volume's detection score, which no sealed record
persisted (`docs/08` D9). Drawing ROC from predicted voxel counts would plot a different score
from the one the reported AUROC ranks.

Usage:
    python scripts/07_make_figures.py            # writes docs/figures/*.png, *.svg, captions.md
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from ocuval.eval import subgroup  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "figures"
RUNS = REPO / "artifacts" / "runs"
SEED, B = 20260916, 2000

FOLDS = ("cirrus", "spectralis", "topcon")
CLASSES = ("IRF", "SRF", "PED")
HELD, REF = "#D55E00", "#0072B2"  # Okabe-Ito vermillion, blue
GREY = "#555555"
PRESENT = "#009E73"  # Okabe-Ito bluish green: class-present differences, Figure 4
BAND = "#efefef"
NAME = {"cirrus": "Cirrus", "spectralis": "Spectralis", "topcon": "Topcon", "pooled": "Pooled"}
LARGE = {  # Figures 2 and 4, sized to stay legible at README width
    "font.size": 13,
    "axes.labelsize": 13,
    "xtick.labelsize": 13,
    "ytick.labelsize": 13,
    "legend.fontsize": 13,
    "figure.titlesize": 15,
}
OPAQUE = {"facecolor": "white", "transparent": False}
RECORDS = {
    "cirrus": {
        "dir": RUNS / "cirrus_holdout_stage2",
        "test": RUNS / "cirrus_holdout_stage2/repro/evaluation_test_seeded.json",
        "in_domain_ref": RUNS / "cirrus_holdout_stage2/repro/evaluation_in_domain_ref_seeded.json",
    },
    "spectralis": {
        "dir": RUNS / "spectralis_holdout_stage3",
        "test": RUNS / "spectralis_holdout_stage3/evaluation_test.json",
        "in_domain_ref": RUNS / "spectralis_holdout_stage3/evaluation_in_domain_ref.json",
    },
    "topcon": {
        "dir": RUNS / "topcon_holdout_stage3",
        "test": RUNS / "topcon_holdout_stage3/evaluation_test.json",
        "in_domain_ref": RUNS / "topcon_holdout_stage3/evaluation_in_domain_ref.json",
    },
}
PNG = {"dpi": 150, "metadata": {"Software": None}}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def est(values, patients) -> dict:
    return subgroup.estimate(values, patients, seed=SEED, n_resamples=B, alpha=0.05)


def rows(fold: str, arm: str, cls: str, present_only: bool = False) -> list[dict]:
    out = [r for r in load(RECORDS[fold][arm])["per_volume"] if r["fluid_class"] == cls]
    return [r for r in out if r["reference_present"]] if present_only else out


def per_patient(folds, arm, cls, present_only=False):
    """One value per patient: the mean of its Dice across the given folds (docs/07 §19.5)."""
    values: dict[str, list[float]] = {}
    for fold in folds:
        for r in rows(fold, arm, cls, present_only):
            values.setdefault(r["patient_id"], []).append(r["dice"])
    patients = sorted(values)
    return patients, np.array([sum(values[p]) / len(values[p]) for p in patients], dtype=float)


def difference(h_pts, h, i_pts, i) -> tuple[float, float, float]:
    """docs/10 §5.4: arms resampled independently, held-out draws first; held-out − in-domain."""
    rng = np.random.default_rng(SEED)
    dh = rng.integers(0, len(h), size=(B, len(h)))
    di = rng.integers(0, len(i), size=(B, len(i)))
    d = h[dh].mean(axis=1) - i[di].mean(axis=1)
    low, high = np.percentile(d, [2.5, 97.5])
    return float(h.mean() - i.mean()), float(low), float(high)


def docs10_differences() -> dict:
    """The §5.4 table as printed in docs/10, parsed, so the figure cannot drift from the report."""
    text = (REPO / "docs/10_analytical_validation_report.md").read_text(encoding="utf-8")
    table = {}
    pattern = re.compile(
        r"^\| (all-volume|class-present) \| (?:\*\*)?(\w+)(?:\*\*)? \| (IRF|SRF|PED) \| "
        r"([+-]\d\.\d{4}) \[([+-]\d\.\d{4}), ([+-]\d\.\d{4})\]",
        re.M,
    )
    for view, comp, cls, p, lo, hi in pattern.findall(text):
        table[(view, comp, cls)] = (float(p), float(lo), float(hi))
    assert len(table) == 24, f"expected 24 difference rows in docs/10 §5.4, parsed {len(table)}"
    return table


def docs10_pooled() -> dict:
    """The pooled arms printed in docs/10 §5.2: Figure 2's pooled rows must equal them."""
    text = (REPO / "docs/10_analytical_validation_report.md").read_text(encoding="utf-8")
    arm = r"\*\*(\d\.\d{4})\*\* \[(\d\.\d{4}), (\d\.\d{4})\] n=(\d+)"
    pattern = re.compile(rf"^\| (IRF|SRF|PED) \| {arm} \| [^|]+ \| {arm} \|", re.M)
    table = {}
    for cls, *v in pattern.findall(text):
        f = [float(x) for x in v]
        table[cls] = ((f[0], f[1], f[2], int(f[3])), (f[4], f[5], f[6], int(f[7])))
    assert len(table) == 3, f"expected 3 pooled rows in docs/10 §5.2, parsed {len(table)}"
    return table


def gather() -> dict:
    """Every value drawn, computed once and checked against the records and docs/10."""
    printed = docs10_differences()
    data = {"arms": {}, "diff": {}}
    for view, present in (("all-volume", False), ("class-present", True)):
        for comp in (*FOLDS, "pooled"):
            folds = FOLDS if comp == "pooled" else (comp,)
            for cls in CLASSES:
                hp, h = per_patient(folds, "test", cls, present)
                ip, i = per_patient(folds, "in_domain_ref", cls, present)
                data["arms"][(view, comp, cls)] = (est(h, hp), est(i, ip))
                got = difference(hp, h, ip, i)
                want = printed[(view, comp, cls)]
                assert all(
                    abs(round(g, 4) - w) < 1e-12 for g, w in zip(got, want, strict=True)
                ), f"difference for {view} {comp} {cls} disagrees with docs/10: {got} {want}"
                data["diff"][(view, comp, cls)] = got
    # The per-fold all-volume arms must equal the stored records exactly.
    for fold in FOLDS:
        for arm, k in (("test", 0), ("in_domain_ref", 1)):
            stored = load(RECORDS[fold][arm])["segmentation"]["all_vendors"]
            for cls in CLASSES:
                mine = data["arms"][("all-volume", fold, cls)][k]
                ref = stored[cls]["dice"]
                assert all(mine[f] == ref[f] for f in ("value", "ci_low", "ci_high", "n")), (
                    fold,
                    arm,
                    cls,
                )
    # The pooled arms have no stored record; they must equal the table docs/10 §5.2 prints.
    for cls, want in docs10_pooled().items():
        for k in (0, 1):
            e = data["arms"][("all-volume", "pooled", cls)][k]
            got = (round(e["value"], 4), round(e["ci_low"], 4), round(e["ci_high"], 4), e["n"])
            assert got == want[k], f"pooled {cls} arm {k} disagrees with docs/10 §5.2: {got}"
    return data


def row_layout() -> tuple[list[tuple[str, str]], np.ndarray]:
    """Rows of Figures 2 and 4, top to bottom: each fold's three classes, then the pooled rows."""
    labels = [(c, cls) for c in (*FOLDS, "pooled") for cls in CLASSES]
    y = np.arange(len(labels))[::-1].astype(float)
    y[len(FOLDS) * 3 :] -= 0.6  # a gap before the pooled rows
    return labels, y


def frame_rows(ax, labels, y) -> None:
    """Shared furniture of Figures 2 and 4: fold bands, pooled separator, row labels, grid."""
    for k in range(0, len(FOLDS) + 1, 2):  # cirrus and topcon shaded, spectralis and pooled not
        ys = y[k * 3 : k * 3 + 3]
        ax.axhspan(ys.min() - 0.5, ys.max() + 0.5, color=BAND, lw=0, zorder=0)
    ax.axhline((y[len(FOLDS) * 3 - 1] + y[len(FOLDS) * 3]) / 2, color="#333333", lw=1.8)
    ax.set_yticks(y, [f"{NAME[c]}  {cls}" for c, cls in labels])
    ax.tick_params(axis="y", length=0)
    ax.set_ylim(y.min() - 0.5, y.max() + 0.5)
    ax.grid(axis="x", color="#d9d9d9", lw=0.9)
    ax.set_axisbelow(True)


def interval(ax, e: tuple[float, float, float], yy: float, **style):
    p, lo, hi = e
    return ax.errorbar(
        p, yy, xerr=[[p - lo], [hi - p]], ms=10, capsize=6, capthick=2.5, elinewidth=2.5,
        ls="none", clip_on=False, zorder=3, **style,
    )  # fmt: skip


def key(color: str, marker: str, dashed: bool = False) -> Line2D:
    """A legend entry drawn as the plot draws it: marker on a thick line, dashed if invalid."""
    return Line2D(
        [], [], color=color, marker=marker, ms=10, lw=2.5, ls=(0, (2, 1.5)) if dashed else "-",
        mfc="white" if dashed else color,
    )  # fmt: skip


def place(fig, title, handles, names, ncol, top=0.85, bottom=0.12) -> None:
    """Fixed layout of Figures 2 and 4: title, then the legend, then the data area below both."""
    fig.subplots_adjust(left=0.18, right=0.97, top=top, bottom=bottom)
    fig.suptitle(title, y=0.975)
    fig.legend(handles, names, loc="upper center", bbox_to_anchor=(0.5, 0.935), ncol=ncol,
               frameon=False, handlelength=2.6, columnspacing=1.6)  # fmt: skip


def save(fig, stem: str) -> None:
    """SVG and 200 dpi PNG, white and opaque, with no date, version or software metadata."""
    fig.savefig(OUT / f"{stem}.svg", metadata={"Date": None, "Creator": None}, **OPAQUE)
    fig.savefig(OUT / f"{stem}.png", dpi=200, metadata={"Software": None}, **OPAQUE)
    plt.close(fig)


def dice_intervals(data: dict) -> str:
    """Figure 2: held-out and in-domain Dice with intervals, per fold and pooled (§3, §5.1)."""
    labels, y = row_layout()
    arms = [data["arms"][("all-volume", c, cls)] for c, cls in labels]
    lims = (0.0, 0.8)
    assert all(lims[0] <= e[k] <= lims[1] for a in arms for e in a for k in ("ci_low", "ci_high"))
    with plt.rc_context(LARGE):
        fig, ax = plt.subplots(figsize=(10, 8))
        frame_rows(ax, labels, y)
        for yy, (held, ref) in zip(y, arms, strict=True):
            for e, off, col in ((held, 0.17, HELD), (ref, -0.17, REF)):
                interval(ax, (e["value"], e["ci_low"], e["ci_high"]), yy + off, fmt="o", color=col)
        ax.set_xlim(*lims)
        ax.set_xticks(np.arange(0, 0.81, 0.1))
        ax.set_xlabel("Dice over all scans, 95% interval (0 = no overlap, 1 = perfect)")
        place(
            fig,
            "Unseen scanner brand vs familiar brands: Dice with 95% intervals",
            [key(HELD, "o"), key(REF, "o")],
            ["Unseen brand (held-out)", "Familiar brands, new patients (in-domain)"],
            ncol=2,
            bottom=0.1,
        )
        save(fig, "fig2_dice_intervals")
    overlap = [h["ci_low"] <= r["ci_high"] and r["ci_low"] <= h["ci_high"] for h, r in arms]
    assert all(overlap), "the caption below says every row overlaps"
    n = {c: tuple(data["arms"][("all-volume", c, "IRF")][k]["n"] for k in (0, 1)) for c in NAME}
    (hc, ic), (hs, _), (ht, _), (hp, ip) = (n[c] for c in (*FOLDS, "pooled"))
    return (
        "**Figure 2. Held-out and in-domain Dice with 95% intervals.** In all "
        f"{len(overlap)} rows the held-out interval (orange) overlaps the in-domain one (blue), so "
        "no difference is established; the in-domain intervals are wide because those arms are "
        "small. Per-fold rows are the primary, pre-registered figures of §3 (held-out n = "
        f"{hc}, {hs}, {ht} patients; in-domain n = {ic} per fold). The pooled rows (n = {hp} and "
        f"{ip}) use the patient-as-unit rule decided after the per-fold results (§5.1, `docs/07` "
        "§19.5): **post-hoc**."
    )


def dice_differences(data: dict) -> str:
    """Figure 4: held-out − in-domain Dice, bootstrapped directly (§5.4)."""
    labels, y = row_layout()
    views = (("all-volume", 0.17, "o", "black"), ("class-present", -0.17, "D", PRESENT))
    lims = (-0.75, 0.75)
    assert all(lims[0] <= v <= lims[1] for d in data["diff"].values() for v in d[1:])
    with plt.rc_context(LARGE):
        fig, ax = plt.subplots(figsize=(10, 8))
        frame_rows(ax, labels, y)
        ax.axvline(0, color="black", lw=2.4, zorder=2)
        for yy, (comp, cls) in zip(y, labels, strict=True):
            for view, off, marker, col in views:
                eb = interval(ax, data["diff"][(view, comp, cls)], yy + off, fmt=marker, color=col)
                if data["arms"][(view, comp, cls)][1]["n"] == 1:
                    eb[2][0].set_linestyle((0, (2, 1.5)))
                    eb[0].set_markerfacecolor("white")
        ax.set_xlim(*lims)
        ax.set_xticks(np.arange(-0.6, 0.61, 0.2))
        ax.set_xlabel("Held-out minus in-domain Dice, 95% interval", labelpad=30)
        for x, ha, text in (
            (0, "left", "← unseen brand worse"),
            (1, "right", "unseen brand better →"),
        ):
            ax.text(x, -0.075, text, transform=ax.transAxes, ha=ha, va="top", style="italic")
        place(
            fig,
            "Unseen scanner brand minus familiar brands: difference in Dice",
            # Legends fill by column: this order reads row by row, the invalid entry alone below.
            [key("black", "o"), key(PRESENT, "D", dashed=True), key(PRESENT, "D")],
            [
                "All scans",
                "Only 1 in-domain patient: not a valid interval",
                "Only scans containing the fluid type",
            ],
            ncol=2,
            top=0.82,
        )
        save(fig, "fig4_dice_differences")
    rows = [(k, d, data["arms"][k][1]["n"]) for k, d in data["diff"].items()]
    excl = [(k, d, n) for k, d, n in rows if d[1] > 0 or d[2] < 0]
    pooled = [r for r in rows if r[0][1] == "pooled"]
    assert {d[0] > 0 for _, d, _ in excl} == {True, False}, "the caption says both directions"
    assert not any(r in excl for r in pooled), "the caption says no pooled interval excludes 0"
    ns = sorted(n for _, _, n in excl)
    return (
        "**Figure 4. Held-out minus in-domain Dice, bootstrapped directly.** "
        f"Of the {len(rows)} intervals, {len(excl)} exclude zero, pointing both ways and resting "
        f"on in-domain arms of {ns[0]} to {ns[-1]} patients, and none of the {len(pooled)} pooled "
        "intervals does, so no cross-vendor difference is concluded (§5.4). The whole figure is "
        "**post-hoc** (§5.4), and its pooled rows also use the post-hoc pooling rule (§5.1); the "
        "dashed interval has a single in-domain patient, ignores in-domain variance and is not a "
        "valid interval."
    )


def jitter(n: int, width: float = 0.32) -> np.ndarray:
    return np.zeros(1) if n == 1 else np.linspace(-width / 2, width / 2, n)


def per_volume(data: dict) -> str:
    """Figure 5: every volume's Dice, by arm, class present vs absent (§19.1)."""
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.4), sharey=True)
    counts = {}
    for ax, cls in zip(axes, CLASSES, strict=True):
        ticks, names = [], []
        for k, fold in enumerate(FOLDS):
            for j, (arm, col) in enumerate((("test", HELD), ("in_domain_ref", REF))):
                x = k * 3.2 + j * 1.35
                rs = sorted(
                    rows(fold, arm, cls), key=lambda r: (not r["reference_present"], r["dice"])
                )
                pres = [r["dice"] for r in rs if r["reference_present"]]
                absn = [r["dice"] for r in rs if not r["reference_present"]]
                counts[(fold, arm, cls)] = (len(pres), len(absn))
                ax.scatter(x - 0.2 + jitter(len(pres), 0.25), pres, s=16, color=col, zorder=3)
                ax.scatter(
                    x + 0.2 + jitter(len(absn), 0.25),
                    absn,
                    s=16,
                    facecolors="white",
                    edgecolors=col,
                    zorder=3,
                )
                ticks.append(x)
                names.append(f"{fold}\n{'held-out' if arm == 'test' else 'in-domain'}")
        ax.set_xticks(ticks, names, fontsize=7)
        ax.set_title(cls, fontsize=11)
        ax.set_ylim(-0.05, 1.05)
        ax.grid(axis="y", color="#dddddd", lw=0.6)
    axes[0].set_ylabel("Dice per volume")
    axes[0].scatter([], [], s=16, color="black", label="class present in reference")
    axes[0].scatter([], [], s=16, facecolors="white", edgecolors="black", label="class absent")
    axes[0].legend(loc="upper left", fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "fig5_per_volume_dice.png", **PNG)
    plt.close(fig)
    absent_zero = sum(
        1
        for (fold, arm, cls) in counts
        if counts[(fold, arm, cls)][1]
        and all(r["dice"] == 0.0 for r in rows(fold, arm, cls) if not r["reference_present"])
    )
    return (
        "**Figure 5. Dice of every volume, split by whether the class is present in the "
        "reference.** One point per patient (held-out arms 22–24, in-domain arms 7). Filled: "
        "class present. Open: class absent, where Dice is 1 if nothing is predicted and 0 if "
        f"anything is (`metrics.py:104-117`). In {absent_zero} of 18 arm × class cells every "
        "class-absent volume scores 0, which is the false-positive pattern of §7.1. The present/"
        "absent split is the §19.1 decomposition: pre-registered for spectralis and topcon, "
        "**post-hoc for cirrus**."
    )


def voxels(data: dict) -> str:
    """Figure 3: predicted voxel count against reference presence, log scale; ROC omitted (D9)."""
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.4), sharey=True)
    floor = 0.5  # zero predicted voxels drawn here, below the axis's 1
    for ax, cls in zip(axes, CLASSES, strict=True):
        ticks, names = [], []
        for k, fold in enumerate(FOLDS):
            for j, (arm, col) in enumerate((("test", HELD), ("in_domain_ref", REF))):
                x = k * 3.2 + j * 1.35
                rs = rows(fold, arm, cls)
                for present, dx, face in ((True, -0.2, col), (False, 0.2, "white")):
                    v = sorted(
                        max(r["predicted_voxels"], floor)
                        for r in rs
                        if r["reference_present"] == present
                    )
                    ax.scatter(
                        x + dx + jitter(len(v), 0.25),
                        v,
                        s=16,
                        facecolors=face,
                        edgecolors=col,
                        zorder=3,
                    )
                ticks.append(x)
                names.append(f"{fold}\n{'held-out' if arm == 'test' else 'in-domain'}")
        ax.axhline(10, color=GREY, lw=0.9, ls="--")
        ax.set_yscale("log")
        ax.set_xticks(ticks, names, fontsize=7)
        ax.set_title(cls, fontsize=11)
        ax.grid(axis="y", color="#dddddd", lw=0.6)
    axes[0].set_ylabel("predicted voxels in the volume (log)")
    axes[0].scatter([], [], s=16, color="black", label="class present in reference")
    axes[0].scatter([], [], s=16, facecolors="white", edgecolors="black", label="class absent")
    axes[0].plot([], [], color=GREY, ls="--", label="presence threshold, 10 voxels")
    axes[0].legend(loc="lower left", fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "fig3_predicted_voxels.png", **PNG)
    plt.close(fig)
    return (
        "**Figure 3. Predicted voxel count by reference presence, log scale.** One point per "
        "patient and class; a volume with no predicted voxels is drawn at 0.5. The dashed line "
        "is the pre-registered presence threshold of 10 voxels (§17.7a). Volumes without the "
        "class (open) mostly sit far above it, which is why specificity at that threshold is "
        "0.0000 in 13 of 18 cells (§4). **ROC curves are not shown:** they need each volume's "
        "detection score, which the sealed records did not persist (`docs/08` D9). A curve built "
        "from voxel counts would rank a different score from the one the reported AUROC uses."
    )


def training() -> str:
    """Figure 1: training loss and validation Dice per fold, best epoch and early stop."""
    fig, axes = plt.subplots(2, 3, figsize=(12, 5.6), sharex="col")
    stats = {}
    for k, fold in enumerate(FOLDS):
        events = [
            json.loads(line)
            for line in (RECORDS[fold]["dir"] / "epochs.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        ep = [e for e in events if e.get("event") == "epoch"]
        x = [e["epoch"] for e in ep]
        best = ep[-1]["best_epoch"]
        resumes = [
            e["from_epoch"]
            for e in events
            if e.get("event") == "session_start" and e.get("resumed")
        ]
        stats[fold] = (len(ep), best, x[-1])
        for row, key, label in (
            (0, "train_loss", "training loss"),
            (1, "val_dice", "validation Dice (in-domain)"),
        ):
            ax = axes[row, k]
            ax.plot(x, [e[key] for e in ep], color="black", lw=1.2)
            ax.axvline(best, color=REF, lw=1.0, ls="--")
            ax.axvline(x[-1], color=GREY, lw=1.0, ls=":")
            for r in resumes:
                ax.axvline(r, color=HELD, lw=0.8, ls="-.")
            ax.grid(color="#eeeeee", lw=0.6)
            if k == 0:
                ax.set_ylabel(label)
        axes[0, k].set_title(f"{fold} held out", fontsize=11)
        axes[1, k].set_xlabel("epoch")
    axes[0, 0].plot([], [], color=REF, ls="--", label="best epoch (checkpoint used)")
    axes[0, 0].plot([], [], color=GREY, ls=":", label="early stop")
    axes[0, 0].plot([], [], color=HELD, ls="-.", label="session resumed")
    axes[0, 0].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "fig1_training_curves.png", **PNG)
    plt.close(fig)
    s = "; ".join(
        f"{f}: {n} epochs, best {b}, stopped after {last}" for f, (n, b, last) in stats.items()
    )
    return (
        "**Figure 1. Training loss and in-domain validation Dice per fold.** From each fold's "
        f"`epochs.jsonl` ({s}). Every fold ended by early stopping, after 25 epochs without "
        "improvement. The checkpoint evaluated is the best epoch, chosen on in-domain validation "
        "only (§17.1). The dash-dot line marks where the spectralis run was resumed after an "
        "external interruption (`docs/08` D8). Validation Dice here is a training record, a "
        "point value with no interval, and is not a result."
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "svg.hashsalt": "ocuval"})
    data = gather()
    # In the reading order of docs/10: §2, §3, §4, §5.4, §7.1.
    captions = [
        training(),
        dice_intervals(data),
        voxels(data),
        dice_differences(data),
        per_volume(data),
    ]
    (OUT / "captions.md").write_text(
        "<!-- Generated by scripts/07_make_figures.py. Do not edit by hand. -->\n\n"
        + "\n\n".join(captions)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(captions)} figures and captions.md to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
