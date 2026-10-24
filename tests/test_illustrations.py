"""TC-132..TC-134: the illustrative B-scans of `docs/07` §21 (SRS-093).

Synthetic data only. Nothing here reads RETOUCH data, opens a sealed bucket or touches the
GPU: the selection, the B-scan rule, the gate, the rendering and the captions are pure
functions of their inputs, and are tested as such. Each check is shown able to fail
(`docs/07` §3 rule 8).
"""

from __future__ import annotations

import importlib.util
import math
import random
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "illustrations", REPO / "scripts" / "09_illustrative_bscans.py"
)
ILL = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ILL)
REASON = "illustration only: docs/07 section 21.9, after the section 17.11 re-evaluation"


def scan(run, subject, present=None, absent_voxels=None, threshold_voxels=0):
    """Rows for one scan. `present` maps fluid to Dice where the reference contains it;
    `absent_voxels` maps fluid to predicted voxels where it does not."""
    present, absent_voxels = present or {}, absent_voxels or {}
    rows = []
    for fluid in ("IRF", "SRF", "PED"):
        if fluid in present:
            rows.append({"run": run, "patient_id": subject, "fluid_class": fluid,
                         "dice": present[fluid], "reference_present": True,
                         "predicted_voxels": 500})  # fmt: skip
        else:
            v = absent_voxels.get(fluid, threshold_voxels)
            rows.append({"run": run, "patient_id": subject, "fluid_class": fluid,
                         "dice": 1.0 if v == 0 else 0.0, "reference_present": False,
                         "predicted_voxels": v})  # fmt: skip
    return rows


def roles(picks):
    return {p["role"]: (p["run"], p["subject"]) for p in picks}


# --- TC-132: selection follows docs/07 §21 and is deterministic -----------------------------


def test_TC_132_worst_median_best_by_mean_dice_over_the_fluid_types_present():
    rows = (
        scan("cirrus", "T01", {"IRF": 0.2, "SRF": 0.4})  # mean 0.3
        + scan("cirrus", "T02", {"IRF": 0.9})  # 0.9
        + scan("spectralis", "T03", {"SRF": 0.5})  # 0.5
        + scan("topcon", "T04", {"PED": 0.1})  # 0.1
        + scan("topcon", "T05")  # nothing present: not eligible
    )
    got = roles(ILL.select(rows, threshold=10))
    assert got["worst"] == ("topcon", "T04")
    assert got["median"] == ("cirrus", "T01"), "lower median of four is position 1"
    assert got["best"] == ("cirrus", "T02")
    assert ("topcon", "T05") not in {got["worst"], got["median"], got["best"]}


def test_TC_132_ties_break_by_run_then_identifier():
    rows = (
        scan("spectralis", "T07", {"IRF": 0.1})
        + scan("cirrus", "T08", {"IRF": 0.1})
        + scan("topcon", "T09", {"SRF": 0.5})
        + scan("topcon", "T10", {"SRF": 0.9})
    )
    worst = roles(ILL.select(rows, threshold=10))["worst"]
    assert worst == ("cirrus", "T08"), "run order outranks the identifier"


def test_TC_132_false_positive_cases_are_the_largest_above_threshold_and_distinct():
    rows = (
        scan("cirrus", "T01", {"IRF": 0.3}, {"SRF": 40, "PED": 10})  # PED at threshold: not > 10
        + scan("cirrus", "T02", {"IRF": 0.6}, {"SRF": 900})  # best; largest SRF, already chosen
        + scan("spectralis", "T03", {"IRF": 0.5}, {"SRF": 300, "PED": 11})
        + scan("topcon", "T04", {"IRF": 0.1})
    )
    picks = ILL.select(rows, threshold=10)
    got = roles(picks)
    assert got["fp_srf"] == ("spectralis", "T03"), "T02 has more SRF but is already the best"
    # PED: T03 (11 voxels) is already the SRF case, and T01's 10 voxels are not above 10.
    assert "fp_ped" not in got, "no eligible PED case remains, so PED gets no image"
    assert "fp_irf" not in got, "no scan lacks IRF, so IRF gets no image"
    assert len(picks) <= 6 and len({(p["run"], p["subject"]) for p in picks}) == len(picks)


def test_TC_132_the_same_rows_in_any_order_give_the_same_picks():
    rows = []
    for i in range(30):
        absent = {"SRF": (i * 53) % 700, "PED": (i * 71) % 500}
        if i % 5 == 0:  # some scans without IRF, so all three false-positive cases exist
            rows += scan(ILL.FOLDS[i % 3], f"T{i:03d}", {"SRF": (i * 37 % 100) / 100},
                         {"IRF": (i * 29) % 400 + 11, "PED": absent["PED"]})  # fmt: skip
        else:
            rows += scan(ILL.FOLDS[i % 3], f"T{i:03d}", {"IRF": (i * 37 % 100) / 100}, absent)
    first = ILL.select(rows, threshold=10)
    for seed in range(5):
        shuffled = list(rows)
        random.Random(seed).shuffle(shuffled)
        assert ILL.select(shuffled, threshold=10) == first
    assert [p["role"] for p in first] == ["worst", "median", "best", "fp_irf", "fp_srf", "fp_ped"]


def test_TC_132_the_bscan_is_the_most_fluid_or_most_predicted_lowest_index_on_ties():
    reference = np.zeros((4, 6, 6), dtype=np.uint8)
    reference[1, :2, :2] = 2  # 4 voxels
    reference[2, :3, :2] = 1  # 6 voxels: most fluid
    reference[3, :3, :2] = 3  # 6 voxels: a tie, higher index
    prediction = np.zeros_like(reference)
    prediction[0, :1, :1] = 2
    prediction[3, :2, :2] = 2  # most predicted SRF
    assert ILL.bscan_index({"fluid": None}, reference, prediction) == 2
    assert ILL.bscan_index({"fluid": "SRF"}, reference, prediction) == 3
    assert ILL.bscan_index({"fluid": "PED"}, reference, np.zeros_like(reference)) == 0


# --- TC-133: no metadata and no identifier ---------------------------------------------------


def synthetic_slice():
    display = np.linspace(0, 1, 40 * 30).reshape(40, 30)
    reference = np.zeros((40, 30), dtype=np.uint8)
    reference[10:20, 5:15] = 1
    prediction = np.zeros_like(reference)
    prediction[12:22, 6:16] = 1
    prediction[30:34, 20:25] = 3
    return display, reference, prediction


def test_TC_133_the_image_carries_only_titles_and_key_and_no_metadata(tmp_path):
    fig = ILL.figure(*synthetic_slice())
    assert ILL.unexpected_text(fig) == set()
    ILL.save(fig, tmp_path / "b.png")
    assert ILL.forbidden_chunks(tmp_path / "b.png") == set()


def test_TC_133_the_text_and_metadata_checks_can_fail(tmp_path):
    fig = ILL.figure(*synthetic_slice())
    fig.axes[0].text(1, 1, "TRAIN001")
    assert ILL.unexpected_text(fig) == {"TRAIN001"}
    with pytest.raises(ValueError, match="beyond titles and key"):
        ILL.save(fig, tmp_path / "refused.png")
    assert not (tmp_path / "refused.png").exists()
    plain = plt.figure()
    plain.savefig(tmp_path / "tagged.png", format="png", metadata={"Software": "x"})
    plt.close(plain)
    assert ILL.forbidden_chunks(tmp_path / "tagged.png") == {"tEXt"}


ROLES = [
    {"role": "worst", "fluid": None},
    {"role": "median", "fluid": None},
    {"role": "best", "fluid": None},
    {"role": "fp_irf", "fluid": "IRF"},
    {"role": "fp_srf", "fluid": "SRF"},
    {"role": "fp_ped", "fluid": "PED"},
]


@pytest.mark.parametrize("pick", ROLES, ids=[r["role"] for r in ROLES])
def test_TC_133_captions_carry_no_identifier_brand_filename_or_date(pick):
    text = ILL.caption(pick)
    assert not re.search(r"TRAIN\d{3}|\b1\.2\.826", text)
    assert not re.search(r"cirrus|spectralis|topcon|zeiss|heidelberg", text, re.I)
    assert not re.search(r"\.(png|mhd|raw|dcm|json)\b", text, re.I)
    assert not re.search(r"\b20\d\d-\d\d-\d\d\b", text)
    assert "docs/07` §21" in text
    if pick["fluid"]:
        assert "largest false-positive case" in text and "not a typical one" in text
        assert "predicted-voxel figure" in text
    else:
        assert "largest" not in text


def test_TC_133_the_published_illustrations_respect_the_cap_and_carry_no_metadata():
    """What is committed and deployed: at most six B-scans (DMP-C2), no metadata, clean captions.

    Runs in CI on the committed files. Reads PNG chunk types and caption text only, never
    the pixels, and checks that the Pages workflow deploys exactly the files the page shows.
    """
    site = importlib.util.spec_from_file_location(
        "site_builder", REPO / "scripts" / "08_build_site.py"
    )
    builder = importlib.util.module_from_spec(site)
    site.loader.exec_module(builder)
    figures = REPO / "docs" / "figures"
    on_disk = sorted(p.name for p in figures.glob("bscan_*.png"))
    assert len(on_disk) <= 6, f"{len(on_disk)} B-scans exceed the cap of six (docs/06 §2.2.2)"
    assert on_disk == sorted(builder.ILLUSTRATIONS)
    for name in on_disk:
        assert ILL.forbidden_chunks(figures / name) == set(), name
    captions = (figures / "illustrations.md").read_text(encoding="utf-8")
    assert not re.search(r"TRAIN\d{3}|cirrus|spectralis|topcon|20\d\d-\d\d-\d\d", captions, re.I)
    workflow = (REPO / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    page = (REPO / "site" / "index.html").read_text(encoding="utf-8")
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    if builder.ILLUSTRATIONS_WITHDRAWN:
        # Withdrawn until regenerated (docs/13, 2026-10-16): nothing may deploy or show them.
        assert not any(f"docs/figures/{name}" in workflow for name in on_disk), "still deployed"
        assert not any(name in page for name in on_disk), "still shown on the page"
        assert not any(name in readme for name in on_disk), "still shown in the README"
    else:
        assert all(f"docs/figures/{name}" in workflow for name in on_disk), "not all deployed"


# --- TC-134: nothing is saved unless every prediction reproduces its record ------------------


PICKS = [
    {"role": "worst", "run": "cirrus", "subject": "T1", "fluid": None},
    {"role": "best", "run": "topcon", "subject": "T2", "fluid": None},
    {"role": "fp_srf", "run": "spectralis", "subject": "T3", "fluid": "SRF"},
]


def records():
    rec = {
        (p["run"], p["subject"]): {"IRF": (0.25, 120), "SRF": (0.0, 40), "PED": (1.0, 0)}
        for p in PICKS
    }
    regen = {k: dict(v) for k, v in rec.items()}
    return rec, regen


def test_TC_134_the_gate_passes_only_on_exact_equality():
    rec, regen = records()
    assert ILL.gate(PICKS, regen, rec) == []
    regen[("topcon", "T2")]["SRF"] = (0.0, 41)
    assert ILL.gate(PICKS, regen, rec) == ["best"], "one voxel off must fail"
    rec, regen = records()
    regen[("cirrus", "T1")]["IRF"] = (math.nextafter(0.25, 1.0), 120)
    assert ILL.gate(PICKS, regen, rec) == ["worst"], "the next representable double must fail"
    rec, regen = records()
    del regen[("spectralis", "T3")]
    assert ILL.gate(PICKS, regen, rec) == ["fp_srf"], "a scan not regenerated must fail"


def test_TC_134_one_failure_saves_no_image_for_any_scan(tmp_path):
    rec, regen = records()
    slices = {(p["run"], p["subject"]): (0, *synthetic_slice()) for p in PICKS}
    regen[("spectralis", "T3")]["PED"] = (1.0, 1)
    assert ILL.finish(PICKS, slices, regen, rec, tmp_path / "fail") == ["fp_srf"]
    written = sorted(p.name for p in (tmp_path / "fail").iterdir())
    assert written == ["selection.json"], "no image and no caption may be written"

    rec, regen = records()
    assert ILL.finish(PICKS, slices, regen, rec, tmp_path / "pass") == []
    names = sorted(p.name for p in (tmp_path / "pass").iterdir())
    assert names == ["bscan_best.png", "bscan_fp_srf.png", "bscan_worst.png", "captions.md",
                     "selection.json"]  # fmt: skip
    for name in names[:3]:
        assert ILL.forbidden_chunks(tmp_path / "pass" / name) == set()


@pytest.mark.parametrize(
    "argv",
    [
        ["--unlock-reason", REASON, "--approved-by", "a", "--device", "cpu"],
        ["--unlock-reason", "  ", "--approved-by", "a"],
        ["--unlock-reason", "r"],
        ["--approved-by", "a"],
    ],
    ids=["cpu-device", "blank-reason", "no-approver", "no-reason"],
)
def test_TC_134_the_script_refuses_before_anything_runs(argv, tmp_path, monkeypatch):
    monkeypatch.setenv("OCUVAL_ARTIFACTS", str(tmp_path))
    with pytest.raises(SystemExit):
        ILL.parse_args(argv)
    assert not (tmp_path / "sealed_access.jsonl").exists(), "nothing may be logged or opened"


# --- TC-146: the section 21.9 regeneration, on arguments and inputs only --------------------


@pytest.mark.parametrize(
    "reason",
    ["illustration only, docs/07 section 21", "illustration only, docs/07 section 17.11",
     "illustration only, section 21.17"],
    ids=["no-17.11", "no-21", "21-only-inside-another-number"],
)  # fmt: skip
def test_TC_146_a_reason_not_citing_17_11_and_21_is_refused(reason, tmp_path):
    with pytest.raises(SystemExit):
        ILL.parse_args(["--unlock-reason", reason, "--approved-by", "a",
                        "--output-dir", str(tmp_path / "new")])  # fmt: skip


def test_TC_146_a_reason_citing_both_is_accepted(tmp_path):
    args = ILL.parse_args(["--unlock-reason", REASON, "--approved-by", "a",
                           "--output-dir", str(tmp_path / "new")])  # fmt: skip
    assert args.unlock_reason == REASON


def test_TC_146_an_output_directory_holding_files_is_refused(tmp_path):
    (tmp_path / "bscan_best.png").write_bytes(b"x")
    with pytest.raises(SystemExit):
        ILL.parse_args(["--unlock-reason", REASON, "--approved-by", "a",
                        "--output-dir", str(tmp_path)])  # fmt: skip
    empty = tmp_path / "empty"
    empty.mkdir()
    ILL.parse_args(["--unlock-reason", REASON, "--approved-by", "a", "--output-dir", str(empty)])


def test_TC_146_the_default_output_is_a_new_directory():
    assert ILL.OUT == REPO / "artifacts" / "illustrations_corrected"


def test_TC_146_selection_and_gate_read_only_the_corrected_held_out_records():
    figures = importlib.util.module_from_spec(
        spec := importlib.util.spec_from_file_location(
            "figs_tc146", REPO / "scripts" / "07_make_figures.py"
        )
    )
    spec.loader.exec_module(figures)
    paths = ILL.held_out_records(figures)
    assert set(paths) == set(ILL.FOLDS)
    assert all(p.parent.name == "corrected" and p.name == "evaluation_test.json"
               for p in paths.values())  # fmt: skip

    class Superseded:
        RECORDS = {f: {"test": REPO / "artifacts" / "runs" / f / "evaluation_test.json"}
                   for f in ILL.FOLDS}  # fmt: skip

    with pytest.raises(SystemExit, match="not a corrected held-out record"):
        ILL.held_out_records(Superseded)
