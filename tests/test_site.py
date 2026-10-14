"""TC-129..TC-131: the report page is generated from the records, and carries nothing else.

SRS-092. The page states several hundred numbers. Each must come from an evaluation record,
an epoch log, a split file or a measured value in `docs/06`, never from a hand typing a figure
into HTML, which is exactly where a published number drifts from its record.

- **TC-129** (`requires_data`): the extraction stage, run twice, gives byte-identical files equal
  to the committed `site/data`, and the results and per-scan rows equal the sealed records when
  read **independently of the builder**.
- **TC-130** (runs in CI, no records needed): rendering the committed data reproduces the
  committed page byte for byte, and the template's visible text holds no digit outside a stated
  allowlist and no em or en dash.
- **TC-131** (runs in CI): the page carries no image data and nothing that relinks a row to a
  subject, the chart library is pinned with an integrity hash, and every chart has a static
  fallback.

Each check is written as a function of its input and shown able to fail (`docs/07` §3 rule 8).
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILD = _load("build_site", REPO / "scripts" / "08_build_site.py")


# --- helpers that the assertions use, each shown able to fail --------------------------------


class _Visible(HTMLParser):
    """Text a reader sees: outside script, style and elements marked `data-verbatim`."""

    SKIP = {"script", "style"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.stack: list[bool] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        skip = tag in self.SKIP or any(k == "data-verbatim" for k, _ in attrs)
        if tag in ("meta", "link", "br", "img", "input", "path", "rect"):
            return
        self.stack.append(skip)
        self.depth += skip

    def handle_endtag(self, tag):
        if tag in ("meta", "link", "br", "img", "input", "path", "rect") or not self.stack:
            return
        self.depth -= self.stack.pop()

    def handle_data(self, data):
        if self.depth == 0:
            self.parts.append(data)


def visible_text(markup: str) -> str:
    parser = _Visible()
    parser.feed(markup)
    return " ".join(parser.parts)


# Digits a reader may see that are not results: the interval level, names of standards and
# documents, identifiers, section references, and the definition of Dice's 0-to-1 scale.
ALLOWED = (
    r"95%",
    r"HD95",
    r"IEC 62304",
    r"ISO 14971",
    r"docs/\d\d",
    r"§\d+(?:\.\d+)*[a-z]?",
    r"\b(?:TC|SRS|HAZ|RC|URS|SOUP)-\d{3}\b",
    r"\bD\d\b",
    r"scripts/08_build_site\.py",
    r"from 0 \(no overlap\) to 1 \(perfect\)",
    r"scores 1 if the model marks none of it, and 0 if it marks any",
    r"Dice is 1 if the model marks nothing and 0 if it marks anything",
    r"Dice jumps from 1 to 0",
)


def typed_numbers(template: str) -> list[str]:
    """Digits in a template's visible text that are neither placeholders nor allowlisted."""
    text = visible_text(BUILD.PLACEHOLDER.sub(" ", template))
    for pattern in ALLOWED:
        text = re.sub(pattern, " ", text)
    return [text[max(0, m.start() - 30) : m.end() + 30] for m in re.finditer(r"\d", text)]


def identifying_leaks(text: str, uid_root: str) -> list[str]:
    found = re.findall(r"TRAIN\d{3}", text)
    found += [uid_root] if uid_root in text else []
    found += re.findall(r'"(?:patient_id|sample_id|reference_voxels)"', text)
    return found


def unsorted_groups(rows: list[dict], key=None) -> list[tuple]:
    """Groups whose rows are not in value order: the order a reader could relink by."""
    key = key or BUILD.scan_order
    return [key(a)[:4] for a, b in zip(rows, rows[1:], strict=False) if key(a) > key(b)]


def presence_in_downloads(folder: Path = SITE / "data") -> list[str]:
    """Downloadable files that carry reference presence as a field or a column (J2)."""
    found = []
    for p in sorted(folder.iterdir()):
        body = p.read_text(encoding="utf-8")
        header = body.splitlines()[0] if p.suffix == ".csv" else ""
        if '"present"' in body or "present" in header.split(","):
            found.append(p.name)
    return found


def tracked_site_files() -> list[Path]:
    """Every file under site/ that git tracks or would commit: tracked, or untracked and not
    ignored. The ignored fallback copies under site/figures/ are excluded by construction."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "site"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.split()  # fmt: skip
    return [REPO / p for p in sorted(set(out)) if (REPO / p).exists()]


# --- TC-129: the data equals the records -----------------------------------------------------


@pytest.mark.requires_data
def test_TC_129_two_extractions_are_byte_identical_and_equal_the_committed_data():
    first, second = BUILD.extract(), BUILD.extract()
    assert first == second, "two extractions from the same records differ"
    committed = {p.relative_to(REPO).as_posix() for p in (SITE / "data").iterdir()}
    committed.add(BUILD.CHART_INPUT.relative_to(REPO).as_posix())
    assert committed == set(first), "a file the builder writes is not committed, or the reverse"
    for rel, content in first.items():
        assert (REPO / rel).read_bytes() == content, f"committed {rel} is stale"


def _none_if_nan(x):
    return None if isinstance(x, float) and math.isnan(x) else x


@pytest.mark.requires_data
def test_TC_129_results_and_per_scan_rows_equal_the_sealed_records():
    """Read the records directly, not through the builder, and compare every published value."""
    figures = _load("make_figures_tc129", REPO / "scripts" / "07_make_figures.py")
    results = json.loads((SITE / "data" / "results.json").read_text(encoding="utf-8"))
    per_scan = json.loads((SITE / "data" / "per_scan.json").read_text(encoding="utf-8"))
    chart = json.loads(BUILD.CHART_INPUT.read_text(encoding="utf-8"))
    arm_of = {"held_out": "test", "in_domain": "in_domain_ref"}
    expected_rows = []
    for row in results["per_run"]:
        path = figures.RECORDS[row["run"]][arm_of[row["arm"]]]
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        seg = record["segmentation"]["all_vendors"][row["fluid"]]
        det = record["detection"]["all_vendors"][row["fluid"]]
        for metric, source in (("dice", seg), ("hd95", seg), ("sensitivity", det),
                               ("specificity", det)):  # fmt: skip
            for k in ("value", "ci_low", "ci_high", "n"):
                assert row[metric][k] == _none_if_nan(source[metric][k]), (row["run"], metric, k)
        for k in ("value", "positives", "negatives"):
            assert row["auroc"][k] == det["auroc"][k]
        if row["fluid"] == "IRF":
            expected_rows += [
                {"run": row["run"], "arm": row["arm"], "vendor": r["vendor"],
                 "fluid": r["fluid_class"], "present": r["reference_present"],
                 "dice": _none_if_nan(r["dice"]), "hd95": _none_if_nan(r["hd95"]),
                 "predicted_voxels": r["predicted_voxels"]}
                for r in record["per_volume"]
            ]  # fmt: skip

    def key(t):
        return tuple(-1 if v is None else v for v in t)

    for published, fields in ((per_scan, BUILD.SCAN_FIELDS), (chart, BUILD.CHART_FIELDS)):
        got = [tuple(r[k] for k in fields) for r in published["rows"]]
        want = [tuple(e[k] for k in fields) for e in expected_rows]
        assert sorted(got, key=key) == sorted(want, key=key), fields


# --- TC-130: every number on the page comes from the data ------------------------------------


def test_TC_130_rendering_the_committed_data_reproduces_the_committed_page():
    assert BUILD.render(BUILD.load_data()) == (SITE / "index.html").read_bytes(), (
        "site/index.html is not what the committed data and template render to; "
        "run scripts/08_build_site.py"
    )


def test_TC_130_the_template_types_no_number_by_hand():
    found = typed_numbers(BUILD.TEMPLATE.read_text(encoding="utf-8"))
    assert not found, f"numbers typed into the template: {found}"


def test_TC_130_the_page_has_no_em_or_en_dash():
    for name, markup in (
        ("template", BUILD.TEMPLATE.read_text(encoding="utf-8")),
        ("page", (SITE / "index.html").read_text(encoding="utf-8")),
    ):
        text = visible_text(markup)
        assert "—" not in text and "–" not in text, f"dash in the {name}'s text"


def test_TC_130_the_checks_can_fail():
    assert typed_numbers("<p>I trained 12 models.</p>"), "a typed number went unnoticed"
    assert not typed_numbers("<p>I trained {{facts.n_runs}} models, 95% intervals.</p>")
    assert typed_numbers("<p data-x='1'>Dice jumps from 1 to 0.3</p>"), "allowlist too loose"
    assert not typed_numbers("<blockquote data-verbatim>2019;38(8)</blockquote>")


# --- TC-131: no image data, nothing that relinks, pinned library, fallbacks ------------------


def test_TC_131_tracked_site_files_are_text_only():
    files = tracked_site_files()
    assert files, "no tracked files under site/"
    allowed = {".html", ".css", ".js", ".json", ".csv"}
    assert sorted({p.suffix for p in files} - allowed) == [], [p.name for p in files]


def test_TC_131_no_subject_identifier_or_uid_root_in_any_site_file(data_config):
    uid_root = data_config["dicom"]["uid_root"]
    leaks = {
        p.name: identifying_leaks(p.read_text(encoding="utf-8"), uid_root)
        for p in [*tracked_site_files(), BUILD.CHART_INPUT]
    }
    assert not {k: v for k, v in leaks.items() if v}, leaks
    assert identifying_leaks('{"patient_id": "TRAIN001"}', uid_root), "the check cannot fail"
    assert identifying_leaks(f"uid {uid_root}.1.2", uid_root)


def test_TC_131_per_scan_rows_carry_only_permitted_fields_and_are_ordered_by_value():
    per_scan = json.loads((SITE / "data" / "per_scan.json").read_text(encoding="utf-8"))
    chart = json.loads(BUILD.CHART_INPUT.read_text(encoding="utf-8"))
    for published, fields, order in (
        (per_scan, BUILD.SCAN_FIELDS, BUILD.scan_order),
        (chart, BUILD.CHART_FIELDS, BUILD.chart_order),
    ):
        assert tuple(published["fields"]) == fields
        assert all(tuple(r) == fields for r in published["rows"])
        assert unsorted_groups(published["rows"], order) == []
        swapped = list(published["rows"])
        swapped[0], swapped[1] = swapped[1], swapped[0]
        if order(swapped[0]) != order(swapped[1]):
            assert unsorted_groups(swapped, order), "the order check cannot fail"


def test_TC_131_downloads_carry_no_reference_presence_and_their_order_cannot_either(tmp_path):
    """J2 (docs/06 §2.5): presence stays in the charts and out of every downloadable file.

    Dropping the column is not enough if the rows are still grouped by presence, so the
    download order is checked directly: two rows that differ only in presence sort together.
    """
    assert "present" not in BUILD.SCAN_FIELDS
    assert presence_in_downloads() == [], presence_in_downloads()
    (tmp_path / "planted.csv").write_text("run,fluid,present,dice\n", encoding="utf-8")
    (tmp_path / "planted.json").write_text('{"rows": [{"present": true}]}', encoding="utf-8")
    assert presence_in_downloads(tmp_path) == ["planted.csv", "planted.json"], "cannot fail"
    row = {"run": "cirrus", "arm": "held_out", "vendor": "cirrus", "fluid": "SRF", "dice": 0.0,
           "hd95": None, "predicted_voxels": 120}  # fmt: skip
    assert BUILD.scan_order({**row, "present": True}) == BUILD.scan_order({**row, "present": False})
    assert BUILD.chart_order({**row, "present": True}) != BUILD.chart_order(
        {**row, "present": False}
    ), "the chart order is meant to group on presence; this check would pass vacuously"
    assert "/" not in BUILD.CHART_INPUT.relative_to(REPO / "site_src").as_posix()
    assert not BUILD.CHART_INPUT.is_relative_to(SITE), "chart input must not be deployed"


def test_TC_131_chart_library_is_pinned_with_an_integrity_hash():
    page = (SITE / "index.html").read_text(encoding="utf-8")
    external = re.findall(r"<script src=\"(https?://[^\"]+)\"([^>]*)>", page)
    assert len(external) == 1, external
    url, attrs = external[0]
    assert url == (
        "https://cdn.jsdelivr.net/npm/plotly.js-basic-dist-min@2.35.2/plotly-basic.min.js"
    )
    integrity = re.search(r'integrity="(sha384-[A-Za-z0-9+/=]+)"', attrs)
    assert integrity and 'crossorigin="anonymous"' in attrs
    soup = (REPO / "docs" / "04_soup_list.md").read_text(encoding="utf-8")
    row = next(ln for ln in soup.splitlines() if ln.startswith("| SOUP-025 |"))
    assert "2.35.2" in row and integrity.group(1) in row, "docs/04 SOUP-025 disagrees with the page"


def test_TC_131_every_chart_has_a_static_fallback_from_docs_figures():
    page = (SITE / "index.html").read_text(encoding="utf-8")
    charts = re.findall(r'<figure class="chart" data-chart="(\w+)">(.*?)</figure>', page, re.S)
    assert len(charts) == len(BUILD.FALLBACKS)
    for name, body in charts:
        src = re.search(r'<img class="fallback" src="figures/([\w.]+)"', body)
        assert src, f"chart {name} has no static fallback"
        assert src.group(1) in BUILD.FALLBACKS
        assert (REPO / "docs" / "figures" / src.group(1)).exists()


def test_TC_131_copied_fallback_figures_are_ignored_by_git():
    probe = subprocess.run(
        ["git", "check-ignore", "-q", "site/figures/fig2_dice_intervals.svg"], cwd=REPO
    )
    assert probe.returncode == 0, "site/figures/ is not ignored: figures would be committed twice"
