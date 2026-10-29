"""TC-138..TC-144 — docs/10's derived figures come from committed code, and the check can fail.

Traces to: SRS-097, SRS-098

Every test but TC-144 runs on synthetic records small enough to work out by hand, so CI runs
them. TC-144 needs the evaluation records, which never leave this workstation, and is marked
`requires_data`.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from ocuval.eval import report
from ocuval.eval.metrics import auroc

REPO = Path(__file__).resolve().parents[1]
B = report.Boot(seed=20260916, n_resamples=200, alpha=0.05)
BOOT_BLOCK = {"seed": 20260916, "n_resamples": 200, "alpha": 0.05}


def row(patient, cls, dice, present=True, voxels=100, score=0.5):
    return {
        "patient_id": patient,
        "fluid_class": cls,
        "dice": dice,
        "reference_present": present,
        "predicted_voxels": voxels,
        "score": score,
    }


def record(rows, boot=BOOT_BLOCK):
    return {"bootstrap": dict(boot), "presence_voxel_threshold": 10, "per_volume": rows}


# --- TC-138: pooling and the difference bootstrap ------------------------------------------


def test_TC_138_a_patient_in_two_folds_is_one_unit_with_its_mean_dice():
    records = {
        "cirrus": {"in_domain_ref": record([row("p1", "IRF", 0.2), row("p2", "IRF", 1.0)])},
        "spectralis": {"in_domain_ref": record([row("p1", "IRF", 0.6)])},
        "topcon": {"in_domain_ref": record([row("p3", "IRF", 0.0)])},
    }
    patients, values = report.per_patient(records, report.FOLDS, "in_domain_ref", "IRF")
    assert patients == ["p1", "p2", "p3"]
    assert values.tolist() == pytest.approx([0.4, 1.0, 0.0])


def test_TC_138_the_class_present_view_drops_exactly_the_absent_rows():
    rec = record([row("a", "SRF", 0.5), row("b", "SRF", 0.0, present=False), row("c", "IRF", 1)])
    assert [r["patient_id"] for r in report.rows_of(rec, "SRF", present_only=True)] == ["a"]
    assert [r["patient_id"] for r in report.rows_of(rec, "SRF")] == ["a", "b"]


def test_TC_138_the_difference_is_seeded_held_out_first_and_reproducible():
    """With no shared patient, the joint draw is the independent one, held-out first."""
    held, ref = np.array([0.2, 0.4, 0.9, 0.1]), np.array([0.5, 0.7])
    hp, ip = ["a", "b", "c", "d"], ["e", "f"]
    first = report.difference(hp, held, ip, ref, B)
    second = report.difference(hp, held, ip, ref, B)
    assert first == second
    assert first[0] == pytest.approx(held.mean() - ref.mean())
    rng = np.random.default_rng(B.seed)  # the documented order: held-out draws, then in-domain
    dh = rng.integers(0, 4, size=(B.n_resamples, 4))
    di = rng.integers(0, 2, size=(B.n_resamples, 2))
    d = held[dh].mean(axis=1) - ref[di].mean(axis=1)
    assert first[1:] == pytest.approx(tuple(np.percentile(d, [2.5, 97.5])))
    constant = report.difference(
        ["a", "b", "c"], np.full(3, 0.5), ["d", "e", "f"], np.full(3, 0.2), B
    )
    assert constant == pytest.approx((0.3, 0.3, 0.3))


def test_TC_138_shared_patients_are_drawn_once_for_both_arms():
    """D2: the pooled arms share patients, and one draw must keep each patient's pair together.

    Every held-out value sits 0.1 above the same patient's in-domain value, so every joint
    replicate differs by exactly 0.1. The independent resample breaks the pairs and spreads.
    """
    patients = [f"p{k}" for k in range(10)]
    ref = np.linspace(0.0, 0.9, 10)
    point, low, high = report.difference(patients, ref + 0.1, patients, ref, B)
    assert (point, low, high) == pytest.approx((0.1, 0.1, 0.1))
    some = patients[:6] + ["q1", "q2"]  # two held-out-only patients as well
    held = np.concatenate([ref[:6] + 0.1, [0.5, 0.6]])
    p2, l2, h2 = report.difference(some, held, patients[:6], ref[:6], B)
    assert p2 == pytest.approx(held.mean() - ref[:6].mean()) and l2 <= p2 <= h2


def test_TC_138_overlap_is_closed_and_a_single_patient_is_its_point():
    a = {"ci_low": 0.1, "ci_high": 0.3}
    assert report.overlaps(a, {"ci_low": 0.3, "ci_high": 0.5})
    assert not report.overlaps(a, {"ci_low": 0.31, "ci_high": 0.5})
    assert report.overlaps(a, {"ci_low": 0.2, "ci_high": 0.2})  # one patient, inside
    assert not report.overlaps(a, {"ci_low": 0.4, "ci_high": 0.4})  # one patient, outside


def test_TC_138_records_that_disagree_on_their_bootstrap_are_refused():
    same = {"f": {"test": record([]), "in_domain_ref": record([])}}
    assert report.boot_of(same) == report.Boot(20260916, 200, 0.05)
    other = dict(BOOT_BLOCK, seed=1)
    with pytest.raises(ValueError, match="bootstrap"):
        report.boot_of({"f": {"test": record([]), "in_domain_ref": record([], other)}})


# --- TC-139: the counts the prose states ---------------------------------------------------


def three_folds(test_rows, ref_rows):
    return {f: {"test": record(test_rows), "in_domain_ref": record(ref_rows)} for f in report.FOLDS}


def test_TC_139_absent_volumes_split_into_dice_0_and_dice_1():
    rows = [row("a", c, 0.0, present=False) for c in report.CLASSES]
    rows += [row("b", "SRF", 1.0, present=False), row("c", "PED", 0.4)]
    split = report.absent_split(three_folds(rows, rows))
    assert split[("cirrus", "test", "IRF")] == (1, 0)
    assert split[("cirrus", "test", "SRF")] == (1, 1)
    assert split[("topcon", "in_domain_ref", "PED")] == (1, 0)
    every_zero = sum(1 for z, o in split.values() if z + o and o == 0)
    assert every_zero == 12  # IRF and PED in each of six arms; SRF has a Dice-1 absent volume


def test_TC_139_class_present_beats_all_volume_is_counted_per_cell():
    # Present mean 0.5, all-volume mean 0.25: exceeds. Present 0.5 with an absent 1.0: not.
    beats = [row("a", c, 0.5) for c in report.CLASSES] + [
        row("b", c, 0.0, present=False) for c in report.CLASSES
    ]
    ties = [row("a", c, 0.5) for c in report.CLASSES] + [
        row("b", c, 1.0, present=False) for c in report.CLASSES
    ]
    assert report.present_beats_all(three_folds(beats, ties)) == 9


def test_TC_139_half_widths_are_half_the_difference_interval_rounded():
    comps = {}
    for view in ("all-volume", "class-present"):
        for comp in (*report.FOLDS, "pooled"):
            for cls in report.CLASSES:
                width = 0.4 if comp == "cirrus" else 0.3
                comps[(view, comp, cls)] = {"diff": (0.0, -width / 2, width / 2)}
    hw = report.half_widths(comps)
    assert hw["all-volume, per fold"] == pytest.approx((0.15, 0.2))
    assert hw["all-volume, pooled"] == pytest.approx((0.15, 0.15))


def test_TC_139_a_stated_figure_is_rounded_once_and_percentages_round_half_up():
    """D9: rounding to two places and then to one printed 0.2 for 0.251."""
    comps = {}
    for view in ("all-volume", "class-present"):
        for comp in (*report.FOLDS, "pooled"):
            for cls in report.CLASSES:
                half = 0.251 if comp == "cirrus" else 0.1
                comps[(view, comp, cls)] = {"diff": (0.0, -half, half)}
    hw = report.half_widths(comps)
    assert hw["all-volume, per fold"][1] == pytest.approx(0.251)
    assert report.unreliable_below(hw) == "0.3"
    comps[("all-volume", "cirrus", "IRF")]["diff"] = (0.0, -0.351, 0.351)
    assert report.unreliable_below(report.half_widths(comps)) == "0.4"
    assert [report.pct(1, 8), report.pct(5, 8), report.pct(1, 3), report.pct(2, 3)] == [
        13,
        63,
        33,
        67,
    ]


# --- TC-140: the section 19.2 threshold ----------------------------------------------------


def test_TC_140_the_grid_is_the_one_docs_07_declares():
    text = (REPO / "docs" / "07_vv_protocol.md").read_text(encoding="utf-8")
    section = text.split("### 19.2", 1)[1].split("### 19.3", 1)[0]
    declared = re.search(r"\*\*Grid\*\*, declared now: `\[([\d, ]+)\]`", section).group(1)
    assert tuple(int(x) for x in declared.split(",")) == report.THRESHOLD_GRID


def test_TC_140_youden_is_maximised_with_presence_meaning_more_than_the_threshold():
    rows = [row("p1", "IRF", 1, voxels=30), row("p2", "IRF", 1, voxels=600),
            row("n1", "IRF", 0, present=False, voxels=20),
            row("n2", "IRF", 0, present=False, voxels=5)]  # fmt: skip
    sel = report.select_threshold(rows, fixed=10)
    # At 20, n1's 20 voxels are not "more than 20": both negatives absent, both positives present.
    assert (sel.threshold, sel.j, sel.ties, sel.degenerate) == (20, Fraction(1), 1, None)


def test_TC_140_a_tie_goes_to_the_smallest_threshold():
    rows = [row("p", "SRF", 1, voxels=5000), row("n", "SRF", 0, present=False, voxels=0)]
    sel = report.select_threshold(rows, fixed=10)
    assert sel.threshold == 1 and sel.ties == len(report.THRESHOLD_GRID)


def test_TC_140_a_class_without_a_val_negative_uses_the_fixed_threshold():
    sel = report.select_threshold([row("p", "IRF", 1, voxels=3)], fixed=10)
    assert sel.threshold == 10 and sel.j is None and sel.degenerate == "no `val` negative"
    sel = report.select_threshold([row("n", "IRF", 0, present=False)], fixed=10)
    assert sel.degenerate == "no `val` positive"


def test_TC_140_specificity_at_a_threshold_carries_the_patient_interval():
    rows = [
        row("n1", "PED", 0, present=False, voxels=5),
        row("n2", "PED", 0, present=False, voxels=50),
        row("p", "PED", 1, voxels=900),
    ]
    at10, at100 = report.specificity_at(rows, 10, B), report.specificity_at(rows, 100, B)
    assert (at10["value"], at10["n"]) == (0.5, 2)
    assert (at100["value"], at100["ci_low"], at100["ci_high"]) == (1.0, 1.0, 1.0)


# --- TC-141: post-hoc AUROC intervals ------------------------------------------------------


def test_TC_141_perfect_separation_is_not_estimable_not_an_interval():
    scores, labels = [0.9, 0.8, 0.7, 0.2, 0.1], [True, True, True, False, False]
    assert auroc(np.array(scores), np.array(labels)) == 1.0
    assert report.auroc_interval(scores, labels, B) is None


def test_TC_141_imperfect_separation_gives_an_interval_around_the_point():
    scores, labels = [0.9, 0.3, 0.7, 0.4, 0.1, 0.6], [True, True, True, False, False, False]
    point = auroc(np.array(scores), np.array(labels))
    low, high = report.auroc_interval(scores, labels, B)
    assert 0.0 <= low <= point <= high <= 1.0 and low < high


def test_TC_141_the_stratified_resample_keeps_both_counts():
    calls = []
    real = np.random.default_rng

    class Spy:
        def __init__(self, seed):
            self.rng = real(seed)

        def choice(self, a, size):
            calls.append((len(a), size))
            return self.rng.choice(a, size)

    mp = pytest.MonkeyPatch()
    mp.setattr(np.random, "default_rng", Spy)  # Generator is a C type and cannot be patched
    try:
        report.auroc_interval([0.9, 0.3, 0.7, 0.4, 0.1], [True, True, True, False, False], B)
    finally:
        mp.undo()
    assert set(calls) == {(3, 3), (2, 2)}  # positives drawn from positives, counts fixed


def test_TC_141_the_unstratified_comparison_drops_replicates_lacking_a_class():
    scores, labels = [0.9, 0.3, 0.7, 0.4, 0.1], [True, True, True, False, False]
    low, high, dropped = report.auroc_interval_unstratified(scores, labels, B)
    assert 0 < dropped < B.n_resamples and 0.0 <= low <= high <= 1.0


# --- TC-142: the report's own row formats --------------------------------------------------


def est(value, low, high, n):
    return {"value": value, "ci_low": low, "ci_high": high, "n": n}


def test_TC_142_intervals_print_as_docs_10_prints_them():
    assert report.iv(est(0.4834, 0.3582, 0.5991, 24), bold=True) == (
        "**0.4834** [0.3582, 0.5991] n=24"
    )
    assert report.iv(est(4.412, 4.412, 4.412, 1)) == "4.4120 (single patient, no spread) n=1"
    assert report.iv(est(0.0, 0.0, 0.0, 1), single=False) == "0.0000 [0.0000, 0.0000] n=1"


def per_fold_records(held, ref):
    seg = {c: {"dice": held, "hd95": held} for c in report.CLASSES}
    seg_ref = {c: {"dice": ref, "hd95": ref} for c in report.CLASSES}
    return {
        f: {
            "test": {"segmentation": {"all_vendors": seg}},
            "in_domain_ref": {"segmentation": {"all_vendors": seg_ref}},
        }
        for f in report.FOLDS
    }


def test_TC_142_a_per_fold_row_matches_docs_10_character_for_character():
    recs = per_fold_records(est(0.6057, 0.4571, 0.7496, 24), est(0.1246, 0.0, 0.3713, 7))
    rows = report.per_fold_rows(recs, "dice")
    assert rows[0] == (
        "| cirrus (spectralis + topcon) | IRF | **0.6057** [0.4571, 0.7496] n=24 | "
        "**0.1246** [0.0000, 0.3713] n=7 | -0.4811 | **no** |"
    )
    old = report.per_fold_rows(recs, "hd95", report.DEFECT)
    assert old[0].startswith("| through the defect | cirrus (spectralis + topcon) | IRF | 0.6057 ")


def test_TC_153_the_secondary_hd95_prints_in_the_per_fold_format_and_only_when_recorded():
    held, ref = est(0.6517, 0.5, 0.8, 14), est(0.4, 0.3, 0.5, 6)
    recs = per_fold_records(held, ref)
    assert report.secondary_hd95_rows(recs) is None, "no record carries the block: no table"
    for f in report.FOLDS:
        for arm, e in (("test", held), ("in_domain_ref", ref)):
            block = {c: {report.SECONDARY_HD95: e} for c in ("IRF", "PED")}
            recs[f][arm]["segmentation_secondary"] = {"all_vendors": block}
    rows = report.secondary_hd95_rows(recs)
    assert rows[0] == (
        "| secondary | cirrus (spectralis + topcon) | IRF | 0.6517 [0.5000, 0.8000] n=14 | "
        "0.4000 [0.3000, 0.5000] n=6 | -0.2517 | yes |"
    )
    assert rows[1] == (
        "| secondary | cirrus (spectralis + topcon) | SRF | not defined: every volume both empty "
        "| not defined: every volume both empty | — | — |"
    )


def test_TC_142_prose_negatives_use_the_minus_sign():
    assert report.minus("IRF -0.1232 [-0.2100, -0.0347]") == "IRF −0.1232 [−0.2100, −0.0347]"
    assert report.signed(0.0881) == "+0.0881" and report.signed(-0.0339) == "-0.0339"


# --- TC-143: the check fails on every kind of difference -----------------------------------

HEADER = "| A | B |"
OLD = "| Status | A | B |"
DOC = "\n".join([
    "Intro: 3 of 9 comparisons overlap.",
    "", HEADER, "|---|---|", "| x | 0.1000 |", "| y | 0.2000 |",
    "", OLD, "|---|---|---|", "| through the defect | x | 0.9000 |", "",
])  # fmt: skip


def generated():
    g = report.Generated()
    g.table("docs/10", HEADER, ["| x | 0.1000 |", "| y | 0.2000 |"])
    g.table("docs/10", OLD, ["| through the defect | x | 0.9000 |"])
    g.say("docs/10", "3 of 9 comparisons overlap")
    return g


def test_TC_143_an_unaltered_document_passes():
    assert report.check(generated(), {"docs/10": DOC}) == []


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (("| y | 0.2000 |", "| y | 0.2001 |"), "row differs"),  # one digit
        (("| y | 0.2000 |\n", ""), "row missing"),
        (("| y | 0.2000 |\n", "| y | 0.2000 |\n| z | 0.3000 |\n"), "row the records do not give"),
        (("3 of 9", "4 of 9"), "not found: 3 of 9"),  # a stated count
        (("| A | B |\n", "| A | C |\n"), "table not found"),
    ],
)
def test_TC_143_each_kind_of_difference_is_reported(mutation, expected):
    old, new = mutation
    differences = report.check(generated(), {"docs/10": DOC.replace(old, new, 1)})
    assert differences, "the check did not fail"
    assert any(expected in d.what for d in differences), [str(d) for d in differences]
    assert all(d.doc == "docs/10" for d in differences)


def test_TC_143_a_superseded_row_is_compared_only_with_the_superseded_table():
    old_row = "| through the defect | x | 0.9000 |"
    changed = DOC.replace(old_row, old_row.replace("0.9000", "0.1000"))
    differences = report.check(generated(), {"docs/10": changed})
    assert len(differences) == 1 and "0.9000" in differences[0].what
    lines = changed.splitlines()
    assert differences[0].where == f"line {lines.index('| through the defect | x | 0.1000 |') + 1}"


def test_TC_143_current_hd95_and_wrong_axes_hd95_come_from_their_own_records():
    # docs/07 section 17.12: the current figures are the gated re-evaluation's; the 24 October
    # records are read only for the HD95 kept as measured on the wrong spacing axes.
    paths = report.record_paths(Path("runs"))
    for fold in report.FOLDS:
        for arm in report.ARMS:
            assert paths["corrected"][fold][arm].parent.name == "corrected_hd95"
            assert paths["wrong_axes"][fold][arm].parent.name == "corrected"
            assert paths["corrected"][fold][arm].name == paths["wrong_axes"][fold][arm].name
    # The page and figures read what the documents are checked against, not their own copy.
    figs = load_script("make_figures_tc143", "07_make_figures.py")
    current = report.record_paths(figs.RUNS)["corrected"]
    assert {f: {a: figs.RECORDS[f][a] for a in report.ARMS} for f in report.FOLDS} == current


def test_TC_143_findings_from_the_records_are_reported_too():
    g = generated()
    g.findings.append("AUROC differs from the record")
    assert [d.doc for d in report.check(g, {"docs/10": DOC})] == ["records"]


def test_TC_143_a_statement_is_not_found_inside_a_longer_number_or_word():
    """D10: substring matching found "5% against 30%" inside "15% against 30%"."""
    g = report.Generated()
    g.say("docs/10", "5% against 30% for SRF", "smaller than about 0.14 Dice")
    found = report.check(g, {"docs/10": "It is 15% against 30% for SRF; about 0.145 Dice."})
    assert len(found) == 2, [str(d) for d in found]
    fine = report.check(
        g, {"docs/10": "It is 5% against 30% for SRF, smaller than about 0.14 Dice."}
    )
    assert fine == []


def _synthetic_sets(tmp_path):
    """Complete record sets from `pipeline.evaluate`: arms identical, every AUROC 1.

    Each fold's held-out and in-domain arms carry the same Dice, so no difference excludes zero
    and no per-fold comparison is apart; every class-present volume outscores every absent one.
    """
    from ocuval.eval.pipeline import EvaluationPlan, detection_rows, evaluate

    def volume(patient, vendor, k):
        seg, pv, rv, scores = [], {}, {}, {}
        for c, cls in enumerate(report.CLASSES):
            present = (k + c) % 3 != 0
            voxels = 50 if present else 0
            seg += [
                {"fluid_class": cls, "metric": "dice", "value": 0.6 if present else 1.0},
                {"fluid_class": cls, "metric": "hd95", "value": 0.3 if present else 0.0},
                {
                    "fluid_class": cls,
                    "metric": "volume_mm3_predicted",
                    "value": 1e-3,
                    "voxels": voxels,
                },
                {
                    "fluid_class": cls,
                    "metric": "volume_mm3_reference",
                    "value": 1e-3,
                    "voxels": voxels,
                },
            ]
            pv[cls], rv[cls], scores[cls] = voxels, voxels, 0.9 if present else 0.1
        detection = detection_rows(pv, rv, scores, threshold=10)
        return {"sample_id": f"s{patient}", "patient_id": patient, "vendor": vendor,
                "segmentation": seg, "detection": detection}  # fmt: skip

    def rec(prefix, vendor):
        vols = [volume(f"{prefix}{k}", vendor, k) for k in range(6)]
        plan = EvaluationPlan(fold_id="f", bucket="val", seed=20260916, n_resamples=50)
        return evaluate(plan, vols, artifacts_root=tmp_path)

    fold_sets = {
        f: {"test": rec(f"{f}H", f), "in_domain_ref": rec(f"{f}R", "other")} for f in report.FOLDS
    }
    return report.RecordSets(
        corrected=fold_sets,
        superseded=fold_sets,
        unseeded_cirrus=fold_sets["cirrus"],
        val={f: fold_sets[f]["test"] for f in report.FOLDS},
    )


def test_TC_143_the_generator_states_zero_and_empty_without_failing(tmp_path):
    """D10: `word(0)` raised KeyError and empty lists raised IndexError or ValueError."""
    g = report.generate(_synthetic_sets(tmp_path))
    said = " ".join(s for texts in g.statements.values() for s in texts)
    assert "Per fold, zero comparisons do not overlap: none" in said
    assert "zero of the 24 difference intervals excluding zero" in said


def test_TC_143_neither_the_module_nor_the_script_can_write_a_document():
    for path in (REPO / "src/ocuval/eval/report.py", REPO / "scripts/11_report_tables.py"):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"write_text|write_bytes|open\([^)]*['\"][wa]", source), path


# --- TC-144: the committed documents agree with the records --------------------------------


@pytest.mark.requires_data
def test_TC_144_the_committed_documents_agree_with_the_records(capsys):
    path = REPO / "scripts" / "11_report_tables.py"
    spec = importlib.util.spec_from_file_location("report_tables", path)
    script = importlib.util.module_from_spec(spec)
    sys.modules["report_tables"] = script
    spec.loader.exec_module(script)
    docs = {k: (REPO / v).read_bytes() for k, v in report.DOCS.items()}
    if not report.records_present(script.RUNS):
        pytest.skip("evaluation records absent")
    assert script.main([]) == 0, capsys.readouterr().out
    assert {k: (REPO / v).read_bytes() for k, v in report.DOCS.items()} == docs


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.requires_data
def test_TC_144_the_figures_and_page_take_their_figures_from_the_generator():
    runs = REPO / "artifacts" / "runs"
    if not report.records_present(runs):
        pytest.skip("evaluation records absent")
    figs = load_script("make_figures_tc144", "07_make_figures.py")
    data = figs.gather()
    records = report.load_records(runs).corrected
    for key, c in report.comparisons(records).items():
        assert data["arms"][key] == (c["held"], c["ref"]) and data["diff"][key] == c["diff"]


@pytest.mark.requires_data
def test_TC_144_the_page_build_refuses_documents_that_disagree(monkeypatch):
    runs = REPO / "artifacts" / "runs"
    if not report.records_present(runs):
        pytest.skip("evaluation records absent")
    build = load_script("build_site_tc144", "08_build_site.py")
    real = report.read_documents

    def altered(repo):
        texts = real(repo)
        texts["README"] = texts["README"].replace("in 1 of 9 comparisons", "in 2 of 9 comparisons")
        return texts

    monkeypatch.setattr(report, "read_documents", altered)
    with pytest.raises(AssertionError, match="in 1 of 9 comparisons"):
        build.extract()
