"""TC-004 — no patient may appear in more than one split.

This is the CI gate described in CLAUDE.md rule 2. If this test ever fails, the data
pipeline is wrong — fix the pipeline, never the test.

The invariant, stated precisely:

    For a resolved Split s and its manifest m, the sets of patient identifiers
    appearing in s.train, s.val, s.test and s.in_domain_ref are pairwise disjoint.
    Additionally, every sample in s.test whose vendor differs from s.held_out_vendor
    is a defect, and every patient in the manifest appears in exactly one split.

Also covers TC-040 (in-domain reference disjoint), TC-041 (seeded, persisted,
reproducible) and TC-042 (construction is patient-level from the manifest).

The xfail marker was removed on 2026-09-17 when ocuval.data.splits was implemented. It
was strict, so it failed loudly the moment the test started passing — which is what it
was for.
"""

from __future__ import annotations

import pytest

from ocuval.data.splits import (
    Sample,
    Split,
    assert_no_patient_overlap,
    assert_no_patient_overlap_after_expansion,
    expand_to_frames,
    frame_id,
    leave_one_vendor_out,
    load,
    save,
)

VENDORS = ("cirrus", "spectralis", "topcon")
SEED = 20260916


def build_manifest(patients_per_vendor: int = 8, slices_per_patient: int = 12) -> list[Sample]:
    """A synthetic manifest with several near-duplicate slices per patient.

    Multiple slices per patient is the point: a slice-level partition would look
    perfectly valid on a manifest with one sample per patient, so a fixture like that
    could not fail the way real data fails.
    """
    manifest: list[Sample] = []
    for vendor in VENDORS:
        for p in range(patients_per_vendor):
            patient_id = f"{vendor}-P{p:03d}"
            for s in range(slices_per_patient):
                manifest.append(
                    Sample(sample_id=f"{patient_id}-S{s:03d}", patient_id=patient_id, vendor=vendor)
                )
    return manifest


def patients_in(split_ids, manifest):
    lookup = {s.sample_id: s.patient_id for s in manifest}
    return {lookup[i] for i in split_ids}


# --- TC-004 -----------------------------------------------------------------------


@pytest.mark.parametrize("held_out", VENDORS)
def test_TC_004_patients_are_disjoint_across_splits(held_out):
    manifest = build_manifest()
    split = leave_one_vendor_out(manifest, held_out, val_fraction=0.15, seed=SEED)

    buckets = {
        "train": patients_in(split.train, manifest),
        "val": patients_in(split.val, manifest),
        "test": patients_in(split.test, manifest),
        "in_domain_ref": patients_in(split.in_domain_ref, manifest),
    }
    names = sorted(buckets)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            assert not buckets[left] & buckets[right], f"{left} and {right} share a patient"


@pytest.mark.parametrize("held_out", VENDORS)
def test_TC_004_every_patient_appears_exactly_once(held_out):
    manifest = build_manifest()
    split = leave_one_vendor_out(manifest, held_out, val_fraction=0.15, seed=SEED)
    assigned = [
        p
        for ids in (split.train, split.val, split.test, split.in_domain_ref)
        for p in patients_in(ids, manifest)
    ]
    assert sorted(assigned) == sorted({s.patient_id for s in manifest})


@pytest.mark.parametrize("held_out", VENDORS)
def test_TC_004_test_split_contains_only_the_held_out_vendor(held_out):
    manifest = build_manifest()
    split = leave_one_vendor_out(manifest, held_out, val_fraction=0.15, seed=SEED)
    vendor_of = {s.sample_id: s.vendor for s in manifest}
    assert {vendor_of[i] for i in split.test} == {held_out}


def test_TC_004_no_slice_of_a_training_patient_reaches_the_test_split():
    """The failure this gate exists for, stated at slice level."""
    manifest = build_manifest()
    split = leave_one_vendor_out(manifest, "spectralis", val_fraction=0.15, seed=SEED)
    train_patients = patients_in(split.train, manifest)
    lookup = {s.sample_id: s.patient_id for s in manifest}
    assert not any(lookup[i] in train_patients for i in split.test)


def test_TC_004_assertion_detects_a_deliberately_leaking_split():
    """An assertion that never fires has not been shown to work."""
    manifest = build_manifest()
    split = leave_one_vendor_out(manifest, "topcon", val_fraction=0.15, seed=SEED)
    leaked = Split(
        fold_id=split.fold_id,
        train=split.train,
        val=split.val,
        test=split.test + split.train[:1],  # one training slice into test
        in_domain_ref=split.in_domain_ref,
        held_out_vendor=split.held_out_vendor,
        seed=split.seed,
    )
    with pytest.raises(ValueError, match="patient overlap"):
        assert_no_patient_overlap(leaked, manifest)


def test_TC_004_assertion_operates_on_patients_not_sample_ids():
    """A sample-ID check would pass here; a patient-level check must not."""
    manifest = [
        Sample("uid-1", "P1", "cirrus"),
        Sample("uid-2", "P1", "cirrus"),
        Sample("uid-3", "P2", "topcon"),
    ]
    split = Split(
        fold_id="f",
        train=["uid-1"],
        val=[],
        test=["uid-2", "uid-3"],  # different sample IDs, same patient as train
        in_domain_ref=[],
        held_out_vendor="topcon",
        seed=1,
    )
    with pytest.raises(ValueError, match="patient overlap"):
        assert_no_patient_overlap(split, manifest)


def test_TC_004_unassigned_patient_is_rejected():
    manifest = build_manifest(patients_per_vendor=2, slices_per_patient=2)
    split = Split(
        fold_id="f",
        train=[],
        val=[],
        test=[s.sample_id for s in manifest if s.vendor == "topcon"],
        in_domain_ref=[],
        held_out_vendor="topcon",
        seed=1,
    )
    with pytest.raises(ValueError, match="appear in no split"):
        assert_no_patient_overlap(split, manifest)


def test_TC_004_wrong_vendor_in_test_split_is_rejected():
    manifest = build_manifest(patients_per_vendor=2, slices_per_patient=2)
    ids = {v: [s.sample_id for s in manifest if s.vendor == v] for v in VENDORS}
    split = Split(
        fold_id="f",
        train=ids["cirrus"],
        val=[],
        test=ids["topcon"] + ids["spectralis"],
        in_domain_ref=[],
        held_out_vendor="topcon",
        seed=1,
    )
    with pytest.raises(ValueError, match="vendor other than"):
        assert_no_patient_overlap(split, manifest)


# --- TC-040 -----------------------------------------------------------------------


def test_TC_040_in_domain_reference_is_drawn_from_training_vendors():
    manifest = build_manifest()
    split = leave_one_vendor_out(manifest, "cirrus", val_fraction=0.15, seed=SEED)
    vendor_of = {s.sample_id: s.vendor for s in manifest}
    assert split.in_domain_ref
    assert "cirrus" not in {vendor_of[i] for i in split.in_domain_ref}


def test_TC_040_in_domain_reference_is_disjoint_from_train_and_val():
    manifest = build_manifest()
    split = leave_one_vendor_out(manifest, "cirrus", val_fraction=0.15, seed=SEED)
    ref = patients_in(split.in_domain_ref, manifest)
    assert not ref & patients_in(split.train, manifest)
    assert not ref & patients_in(split.val, manifest)


# --- TC-041 -----------------------------------------------------------------------


def test_TC_041_same_seed_reproduces_the_split_exactly():
    manifest = build_manifest()
    first = leave_one_vendor_out(manifest, "topcon", val_fraction=0.15, seed=SEED)
    second = leave_one_vendor_out(manifest, "topcon", val_fraction=0.15, seed=SEED)
    assert first == second


def test_TC_041_different_seed_changes_the_partition():
    manifest = build_manifest()
    first = leave_one_vendor_out(manifest, "topcon", val_fraction=0.15, seed=1)
    second = leave_one_vendor_out(manifest, "topcon", val_fraction=0.15, seed=2)
    assert first.val != second.val


def test_TC_041_save_and_load_round_trip(tmp_path):
    manifest = build_manifest()
    split = leave_one_vendor_out(manifest, "spectralis", val_fraction=0.15, seed=SEED)
    path = tmp_path / "nested" / "split.json"
    save(split, path)
    assert load(path) == split


def test_TC_041_saved_file_is_byte_identical_across_runs(tmp_path):
    manifest = build_manifest()
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    save(leave_one_vendor_out(manifest, "cirrus", val_fraction=0.15, seed=SEED), a)
    save(leave_one_vendor_out(manifest, "cirrus", val_fraction=0.15, seed=SEED), b)
    assert a.read_bytes() == b.read_bytes()


def test_TC_041_load_rejects_a_file_with_the_wrong_fields(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"fold_id": "f", "train": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="expected"):
        load(path)


# --- TC-042 -----------------------------------------------------------------------


def test_TC_042_all_slices_of_a_patient_land_in_one_bucket():
    manifest = build_manifest()
    split = leave_one_vendor_out(manifest, "spectralis", val_fraction=0.15, seed=SEED)
    lookup = {s.sample_id: s.patient_id for s in manifest}
    location: dict[str, str] = {}
    for name, ids in (
        ("train", split.train),
        ("val", split.val),
        ("test", split.test),
        ("in_domain_ref", split.in_domain_ref),
    ):
        for i in ids:
            patient = lookup[i]
            assert location.setdefault(patient, name) == name


def test_TC_042_patient_spanning_two_vendors_is_rejected():
    manifest = [
        Sample("uid-1", "P1", "cirrus"),
        Sample("uid-2", "P1", "topcon"),
        Sample("uid-3", "P2", "spectralis"),
    ]
    with pytest.raises(ValueError, match="two vendors"):
        leave_one_vendor_out(manifest, "spectralis", val_fraction=0.0, seed=1)


def test_TC_042_unknown_held_out_vendor_is_rejected():
    with pytest.raises(ValueError, match="no samples in the manifest"):
        leave_one_vendor_out(build_manifest(), "nidek", val_fraction=0.15, seed=1)


def test_TC_042_empty_manifest_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        leave_one_vendor_out([], "cirrus", val_fraction=0.15, seed=1)


def test_TC_042_training_set_survives_a_small_manifest():
    """Rounding must not empty the training set on a manifest of a few patients."""
    manifest = build_manifest(patients_per_vendor=2, slices_per_patient=2)
    split = leave_one_vendor_out(manifest, "cirrus", val_fraction=0.15, seed=SEED)
    assert split.train


# --- TC-043: disjointness must survive volume-to-frame expansion -------------------
#
# The DICOM layer produces one multi-frame instance per volume while training consumes
# 2-D B-scans, so an expansion step exists that did not when leave_one_vendor_out was
# written. A correct volume-level split followed by a wrong expansion reaches HAZ-008 by
# a second path, and the two failures are indistinguishable downstream.


def frame_counts_for(manifest, per_volume=7):
    return {s.sample_id: per_volume for s in manifest}


@pytest.mark.parametrize("held_out", VENDORS)
def test_TC_043_patients_stay_disjoint_after_expansion(held_out):
    manifest = build_manifest(patients_per_vendor=5, slices_per_patient=1)
    split = leave_one_vendor_out(manifest, held_out, val_fraction=0.2, seed=SEED)
    frames = expand_to_frames(split, frame_counts_for(manifest))
    assert_no_patient_overlap_after_expansion(frames, manifest)


def test_TC_043_every_frame_traces_to_a_volume_in_the_same_bucket():
    manifest = build_manifest(patients_per_vendor=5, slices_per_patient=1)
    split = leave_one_vendor_out(manifest, "topcon", val_fraction=0.2, seed=SEED)
    frames = expand_to_frames(split, frame_counts_for(manifest))
    for name, volume_ids, frame_ids in (
        ("train", split.train, frames.train),
        ("val", split.val, frames.val),
        ("test", split.test, frames.test),
        ("in_domain_ref", split.in_domain_ref, frames.in_domain_ref),
    ):
        assert {frames.volume_of[f] for f in frame_ids} == set(volume_ids), name


def test_TC_043_every_frame_of_every_volume_appears_exactly_once():
    manifest = build_manifest(patients_per_vendor=4, slices_per_patient=1)
    split = leave_one_vendor_out(manifest, "cirrus", val_fraction=0.25, seed=SEED)
    counts = frame_counts_for(manifest, per_volume=5)
    frames = expand_to_frames(split, counts)
    everything = frames.train + frames.val + frames.test + frames.in_domain_ref
    assert len(everything) == len(set(everything))
    assigned = set(split.train + split.val + split.test + split.in_domain_ref)
    assert len(everything) == sum(counts[v] for v in assigned)


def test_TC_043_expansion_is_deterministic():
    manifest = build_manifest(patients_per_vendor=4, slices_per_patient=1)
    split = leave_one_vendor_out(manifest, "spectralis", val_fraction=0.25, seed=SEED)
    counts = frame_counts_for(manifest)
    assert expand_to_frames(split, counts) == expand_to_frames(split, counts)


def test_TC_043_expansion_of_a_leaking_split_is_caught():
    """The assertion must fire on a split whose expansion is wrong, not merely exist."""
    manifest = build_manifest(patients_per_vendor=4, slices_per_patient=1)
    split = leave_one_vendor_out(manifest, "topcon", val_fraction=0.25, seed=SEED)
    leaked = Split(
        fold_id=split.fold_id,
        train=split.train,
        val=split.val,
        test=split.test + split.train[:1],
        in_domain_ref=split.in_domain_ref,
        held_out_vendor=split.held_out_vendor,
        seed=split.seed,
    )
    frames = expand_to_frames(leaked, frame_counts_for(manifest))
    with pytest.raises(ValueError, match="patient overlap after expansion"):
        assert_no_patient_overlap_after_expansion(frames, manifest)


def test_TC_043_missing_frame_count_is_refused_rather_than_dropped():
    """A silently dropped volume is data missing from training with nothing to show it."""
    manifest = build_manifest(patients_per_vendor=4, slices_per_patient=1)
    split = leave_one_vendor_out(manifest, "cirrus", val_fraction=0.25, seed=SEED)
    counts = frame_counts_for(manifest)
    del counts[split.train[0]]
    with pytest.raises(ValueError, match="no frame count for"):
        expand_to_frames(split, counts)


def test_TC_043_zero_frame_volume_is_refused():
    manifest = build_manifest(patients_per_vendor=4, slices_per_patient=1)
    split = leave_one_vendor_out(manifest, "cirrus", val_fraction=0.25, seed=SEED)
    counts = frame_counts_for(manifest)
    counts[split.train[0]] = 0
    with pytest.raises(ValueError, match="reports 0 frames"):
        expand_to_frames(split, counts)


def test_TC_043_frame_identifier_carries_its_volume():
    assert frame_id("uid-123", 7).startswith("uid-123")
    with pytest.raises(ValueError, match="non-negative"):
        frame_id("uid-123", -1)
