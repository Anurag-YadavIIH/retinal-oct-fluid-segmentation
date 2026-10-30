"""TC-159 — the §21.12 B-scans follow the presentation rule fixed before rendering, from saved maps.

Traces to: SRS-110

The crop rule is a pure function, tested on synthetic B-scans. The rendering runs as the chain
runs it, as a separate process from a sandbox root with torch unimportable. Image sizes are read
from each PNG's header, never from its pixels (`docs/06` DMP-C12).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from ocuval import sandbox
from ocuval.eval import sealed

REPO = Path(__file__).resolve().parents[1]
BSCANS = REPO / "scripts" / "09_illustrative_bscans.py"
REASON = "B-scans re-rendered under docs/07 section 21 (21.12), for presentation only"
NO_TORCH = (
    "import runpy, sys; sys.modules['torch'] = None; sys.argv = sys.argv[1:]; "
    "runpy.run_path(sys.argv[0], run_name='__main__')"
)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ILL = load("bscans_tc159", BSCANS)
CHAIN = load("presentation_chain_tc159", REPO / "scripts" / "16_presentation_bscans.py")


def frame(rows=300, cols=50):
    return (
        np.zeros((rows, cols)),
        np.zeros((rows, cols), np.uint8),
        np.zeros((rows, cols), np.uint8),
    )


# --- the crop rule ------------------------------------------------------------------------


def test_TC_159_the_crop_runs_40_rows_beyond_the_outermost_outline_or_brightest_row():
    display, reference, prediction = frame()
    display[150, :] = 1.0  # the brightest row
    reference[120:126, 10:20] = 1  # expert outline, topmost at 120
    prediction[170:181, 5:9] = 3  # model outline, bottommost at 180
    assert ILL.crop_rows(display, reference, prediction) == slice(80, 221)


def test_TC_159_the_brightest_row_counts_even_outside_every_outline():
    display, reference, prediction = frame()
    reference[100:110, :] = 1
    display[250, :] = 0.9  # well below the outlines
    assert ILL.crop_rows(display, reference, prediction) == slice(60, 291)


def test_TC_159_ties_for_the_brightest_row_go_to_the_lowest_index():
    display, reference, prediction = frame()
    display[200, :] = display[260, :] = 1.0
    reference[150, 0] = 1
    assert ILL.crop_rows(display, reference, prediction) == slice(110, 241)


def test_TC_159_the_crop_is_clipped_at_both_edges_of_the_bscan():
    display, reference, prediction = frame(rows=100)
    display[5, :] = 1.0
    prediction[95, 0] = 2
    assert ILL.crop_rows(display, reference, prediction) == slice(0, 100)


def test_TC_159_the_rendering_constants_are_those_fixed_in_section_21_12():
    p, s = ILL.PRESENTATION, ILL.STANDARD
    assert (p.dpi, p.outline_px, p.title_pt, p.key_pt, p.crop) == (300, 2.5, 16, 15, True)
    assert p.dpi == 2 * s.dpi and s.crop is False
    assert p.outline_pt == pytest.approx(2.5 * 72 / 300)
    assert ILL.CROP_MARGIN_ROWS == 40
    assert ILL.COLOURS == {"IRF": "#D55E00", "SRF": "#0072B2", "PED": "#009E73"}


def test_TC_159_the_crop_cuts_no_column_and_both_panels_show_the_same_rows():
    display, reference, prediction = frame()
    display[150, :] = 1.0
    reference[140:145, 0:3] = 1
    fig = ILL.figure(display, reference, prediction, ILL.PRESENTATION)
    try:
        shown = [ax.images[0].get_array().shape for ax in fig.axes]
    finally:
        import matplotlib.pyplot as plt

        plt.close(fig)
    rows = ILL.crop_rows(display, reference, prediction)
    assert shown == [(rows.stop - rows.start, 50)] * 2


# --- the rendering, end to end ------------------------------------------------------------


def clean_environment() -> dict:
    return {k: v for k, v in os.environ.items()
            if k != sealed.CERTIFICATE_ENV and not k.startswith("COV_CORE")}  # fmt: skip


def run_presentation(root: Path) -> subprocess.CompletedProcess:
    env = clean_environment()
    env["OCUVAL_ARTIFACTS"] = str(root / "artifacts")
    argv = [sys.executable, "-c", NO_TORCH, str(BSCANS), "--record-set", "presentation",
            "--unlock-reason", REASON, "--approved-by", "a"]  # fmt: skip
    return subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, check=False)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


@pytest.fixture
def root(tmp_path):
    sandbox.build_final_bscans(tmp_path / "root")
    return tmp_path / "root"


def test_TC_159_main_renders_six_images_at_twice_the_resolution_with_no_torch(root):
    result = run_presentation(root)
    assert result.returncode == 0, result.stdout + result.stderr
    out = root / ILL.OUT_PRESENTATION
    selection = json.loads((out / "selection.json").read_text(encoding="utf-8"))
    assert selection["gate"] == "passed"
    images = sorted(out.glob("bscan_*.png"))
    assert len(images) == len(selection["picks"])
    for image in images:
        assert png_size(image) == (3000, 1320), image.name  # 10 x 4.4 inches at 300 dpi
        assert ILL.forbidden_chunks(image) == set(), image.name


def test_TC_159_a_saved_file_off_its_checksum_is_refused_before_any_bucket_opens(root):
    for path in (root / "artifacts" / "predictions_final").rglob("*.npz"):
        path.write_bytes(path.read_bytes() + b"\0")
    result = run_presentation(root)
    assert result.returncode != 0 and "SHA-256" in result.stderr
    assert not (root / "artifacts" / "sealed_access.jsonl").exists()


# --- the chain ----------------------------------------------------------------------------


def test_TC_159_the_chain_steps_are_in_order_and_cite_21_12():
    plan = CHAIN.build_plan(CHAIN.parse_args(["--approved-by", "Anurag Yadav"]))
    assert [s.name for s in plan] == ["access_counts", "dry_run", "bscans", "access_counts_after"]
    argv = next(s.argv for s in plan if s.kind == "bscans")
    assert argv[argv.index("--record-set") + 1] == "presentation"
    assert re.search(r"21\.12", argv[argv.index("--unlock-reason") + 1])
    assert argv[argv.index("--output-dir") + 1] == str(CHAIN.OUTPUT)
    assert CHAIN.OUTPUT == ILL.OUT_PRESENTATION


def test_TC_159_the_expected_counts_are_the_ones_section_21_12_states():
    protocol = (REPO / "docs" / "07_vv_protocol.md").read_text(encoding="utf-8")
    section = protocol.split("### 21.12", 1)[1].split("### 21.13", 1)[0]
    stated = {
        (f"{fold}_holdout", bucket): int(now)
        for fold, bucket, now in re.findall(
            r"^\| (cirrus|spectralis|topcon) \| `(test|in_domain_ref)` \| \*\*(\d+) → ",
            section,
            re.M,
        )
    }
    assert stated == CHAIN.EXPECTED_COUNTS


def test_TC_159_the_dry_run_completes_in_a_sandbox(tmp_path, monkeypatch):
    for key in [k for k in os.environ if k.startswith("COV_CORE")]:
        monkeypatch.delenv(key)
    plan = CHAIN.build_plan(CHAIN.parse_args(["--approved-by", "Anurag Yadav"]))
    steps = CHAIN.dry_run(plan, tmp_path / "sandbox", tmp_path / "logs")
    assert steps == [
        {"name": n, "exit": 0} for n in ("access_counts", "bscans", "access_counts_after")
    ]
