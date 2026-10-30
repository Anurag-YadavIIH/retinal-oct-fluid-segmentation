"""TC-160 — the §21.13 B-scans are the whole B-scan, sharper, from the saved maps.

Traces to: SRS-111

The §21.12 crop filled each panel and stretched every short crop (`docs/07` §21.13). This
rendering keeps the whole B-scan at the §21.5 shape: the test is that both panels show every row
and column, and that the saved images are twice §21.5's pixel size. Sizes come from PNG headers,
never from pixels (`docs/06` DMP-C12).
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
REASON = "B-scans re-rendered under docs/07 section 21 (21.13), for presentation only"
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


ILL = load("bscans_tc160", BSCANS)
CHAIN = load("sharper_chain_tc160", REPO / "scripts" / "17_sharper_bscans.py")


def test_TC_160_the_profile_is_sharper_with_no_crop():
    s, standard = ILL.SHARPER, ILL.STANDARD
    assert (s.dpi, s.outline_px, s.title_pt, s.key_pt, s.crop) == (300, 2.5, 16, 15, False)
    assert s.dpi == 2 * standard.dpi
    assert ILL.RENDERINGS["sharper"] is s


def test_TC_160_both_panels_show_every_row_and_column():
    display = np.zeros((300, 50))
    display[150, :] = 1.0
    reference = np.zeros((300, 50), np.uint8)
    reference[140:145, 0:3] = 1
    prediction = np.zeros_like(reference)
    fig = ILL.figure(display, reference, prediction, ILL.SHARPER)
    try:
        shown = [ax.images[0].get_array().shape for ax in fig.axes]
    finally:
        import matplotlib.pyplot as plt

        plt.close(fig)
    assert shown == [(300, 50)] * 2


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def test_TC_160_main_renders_six_whole_bscans_at_twice_the_resolution_with_no_torch(tmp_path):
    root = tmp_path / "root"
    sandbox.build_final_bscans(root)
    env = {k: v for k, v in os.environ.items()
           if k != sealed.CERTIFICATE_ENV and not k.startswith("COV_CORE")}  # fmt: skip
    env["OCUVAL_ARTIFACTS"] = str(root / "artifacts")
    argv = [sys.executable, "-c", NO_TORCH, str(BSCANS), "--record-set", "sharper",
            "--unlock-reason", REASON, "--approved-by", "a"]  # fmt: skip
    result = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    out = root / ILL.OUT_SHARPER
    selection = json.loads((out / "selection.json").read_text(encoding="utf-8"))
    images = sorted(out.glob("bscan_*.png"))
    assert selection["gate"] == "passed" and len(images) == len(selection["picks"])
    for image in images:
        assert png_size(image) == (3000, 1320), image.name
        assert ILL.forbidden_chunks(image) == set(), image.name


def test_TC_160_the_chain_steps_are_in_order_cite_21_13_and_state_its_counts():
    plan = CHAIN.build_plan(CHAIN.parse_args(["--approved-by", "Anurag Yadav"]))
    assert [s.name for s in plan] == ["access_counts", "dry_run", "bscans", "access_counts_after"]
    argv = next(s.argv for s in plan if s.kind == "bscans")
    assert argv[argv.index("--record-set") + 1] == "sharper"
    assert re.search(r"21\.13", argv[argv.index("--unlock-reason") + 1])
    assert CHAIN.OUTPUT == ILL.OUT_SHARPER
    protocol = (REPO / "docs" / "07_vv_protocol.md").read_text(encoding="utf-8")
    section = protocol.split("### 21.13", 1)[1]
    stated = {
        (f"{fold}_holdout", bucket): int(now)
        for fold, bucket, now in re.findall(
            r"^\| (cirrus|spectralis|topcon) \| `(test|in_domain_ref)` \| \*\*(\d+) → ",
            section,
            re.M,
        )
    }
    assert stated == CHAIN.EXPECTED_COUNTS


def test_TC_160_the_dry_run_completes_in_a_sandbox(tmp_path, monkeypatch):
    for key in [k for k in os.environ if k.startswith("COV_CORE")]:
        monkeypatch.delenv(key)
    plan = CHAIN.build_plan(CHAIN.parse_args(["--approved-by", "Anurag Yadav"]))
    steps = CHAIN.dry_run(plan, tmp_path / "sandbox", tmp_path / "logs")
    assert steps == [
        {"name": n, "exit": 0} for n in ("access_counts", "bscans", "access_counts_after")
    ]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
