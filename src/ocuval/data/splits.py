"""Deterministic, patient-level dataset splitting.

Traces to: SRS-018, SRS-019, SRS-020, SRS-021, SRS-022, SRS-023 (dataset splitting)
Implements risk control: RC-001, RC-002, RC-004, RC-005 (prevention of optimistically
biased performance estimates caused by patient overlap between training and evaluation
sets — HAZ-008)

This module is the single source of truth for which sample goes into which split.
Nothing elsewhere in the codebase may partition data. See CLAUDE.md rule 2.

The structural guarantee is that **patients are the unit of assignment and slices never
are**: every function here partitions a set of patient identifiers and expands to sample
identifiers only at the end. There is no code path in which a B-scan is assigned
independently of the patient it came from, so slice-level leakage is impossible by
construction rather than caught after the fact. That is what makes
`assert_no_patient_overlap` a real check instead of a restatement of the construction.
"""

from __future__ import annotations

import json
import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sample:
    """One B-scan, carrying the identity that must survive the whole pipeline.

    `sample_id` is a DICOM SOP Instance UID in a real manifest and an arbitrary stable
    string in a synthetic one.
    """

    sample_id: str
    patient_id: str
    vendor: str


@dataclass(frozen=True)
class Split:
    """One resolved split. Sample IDs are DICOM SOP Instance UIDs.

    `in_domain_ref` holds patients drawn from the *training* vendors and held out from
    both train and val (SRS-022). The gap between performance on `test` and on
    `in_domain_ref` is the project's headline result: the first is a different vendor,
    the second is the same vendors and unseen patients.
    """

    fold_id: str
    train: list[str]
    val: list[str]
    test: list[str]
    in_domain_ref: list[str]
    held_out_vendor: str
    seed: int


def _patients_by_vendor(manifest: Sequence[Sample]) -> dict[str, set[str]]:
    """Map vendor to its patient set, rejecting a patient that spans vendors.

    RETOUCH is one volume per subject, so a patient under two vendors should not occur.
    That is precisely why it raises: leave-one-vendor-out would otherwise place the same
    patient in train and test with no assertion able to see it as a vendor problem.
    """
    owner: dict[str, str] = {}
    by_vendor: dict[str, set[str]] = {}
    for sample in manifest:
        previous = owner.setdefault(sample.patient_id, sample.vendor)
        if previous != sample.vendor:
            raise ValueError(
                f"patient {sample.patient_id!r} appears under two vendors "
                f"({previous!r} and {sample.vendor!r}); leave-one-vendor-out is undefined"
            )
        by_vendor.setdefault(sample.vendor, set()).add(sample.patient_id)
    return by_vendor


def _samples_for(manifest: Sequence[Sample], patients: set[str]) -> list[str]:
    """Expand a patient set to its sample IDs, in manifest order."""
    return [s.sample_id for s in manifest if s.patient_id in patients]


def leave_one_vendor_out(
    manifest: Sequence[Sample],
    held_out_vendor: str,
    val_fraction: float,
    seed: int,
    *,
    fold_id: str | None = None,
    ref_fraction: float = 0.15,
) -> Split:
    """Build a leave-one-vendor-out split, partitioned at patient level.

    Every patient appears in exactly one of train / val / test / in_domain_ref.

    The held-out vendor's patients become `test` entire. The remaining vendors' patients
    are sorted, shuffled under `seed`, and divided into the in-domain reference set, the
    validation set and the training set.

    Sorting before shuffling is not decoration. Patient identifiers arrive via a set, and
    set iteration order for strings is not stable across processes, so seeding a shuffle
    over an unsorted list produces a result that looks reproducible and is not.
    """
    if not manifest:
        raise ValueError("manifest is empty")
    if not 0.0 <= val_fraction < 1.0:
        raise ValueError(f"val_fraction must be in [0, 1), got {val_fraction}")
    if not 0.0 <= ref_fraction < 1.0:
        raise ValueError(f"ref_fraction must be in [0, 1), got {ref_fraction}")
    if val_fraction + ref_fraction >= 1.0:
        raise ValueError(
            f"val_fraction + ref_fraction must leave patients for training, "
            f"got {val_fraction} + {ref_fraction}"
        )

    by_vendor = _patients_by_vendor(manifest)
    if held_out_vendor not in by_vendor:
        raise ValueError(
            f"held-out vendor {held_out_vendor!r} has no samples in the manifest; "
            f"present vendors are {sorted(by_vendor)}"
        )

    test_patients = by_vendor[held_out_vendor]
    training_patients = sorted(
        {p for vendor, patients in by_vendor.items() if vendor != held_out_vendor for p in patients}
    )
    if not training_patients:
        raise ValueError(f"no training patients remain after holding out {held_out_vendor!r}")

    shuffled = list(training_patients)
    random.Random(seed).shuffle(shuffled)

    n = len(shuffled)
    n_ref = int(round(n * ref_fraction))
    n_val = int(round(n * val_fraction))
    # Training must not be emptied by rounding on a small manifest.
    while n_ref + n_val >= n and (n_ref or n_val):
        if n_val >= n_ref:
            n_val -= 1
        else:
            n_ref -= 1

    ref_patients = set(shuffled[:n_ref])
    val_patients = set(shuffled[n_ref : n_ref + n_val])
    train_patients = set(shuffled[n_ref + n_val :])

    split = Split(
        fold_id=fold_id or f"{held_out_vendor}_holdout",
        train=_samples_for(manifest, train_patients),
        val=_samples_for(manifest, val_patients),
        test=_samples_for(manifest, test_patients),
        in_domain_ref=_samples_for(manifest, ref_patients),
        held_out_vendor=held_out_vendor,
        seed=seed,
    )
    assert_no_patient_overlap(split, manifest)
    return split


def assert_no_patient_overlap(split: Split, manifest: Sequence[Sample]) -> None:
    """Raise if any patient appears in more than one split.

    Called at the end of every split construction and again at the start of training.
    Never bypass, and never catch the exception it raises.

    Operates on the **patient** identifier, never the sample identifier (SRS-020,
    RC-002). Checking sample IDs would pass trivially for exactly the failure this
    exists to prevent: adjacent B-scans from one patient have different sample IDs and
    are near-duplicate images.
    """
    patient_of = {s.sample_id: s.patient_id for s in manifest}
    vendor_of = {s.sample_id: s.vendor for s in manifest}

    buckets = {
        "train": split.train,
        "val": split.val,
        "test": split.test,
        "in_domain_ref": split.in_domain_ref,
    }

    unknown = {sid for ids in buckets.values() for sid in ids if sid not in patient_of}
    if unknown:
        raise ValueError(f"split references samples absent from the manifest: {sorted(unknown)}")

    patients = {name: {patient_of[sid] for sid in ids} for name, ids in buckets.items()}

    names = sorted(buckets)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            shared = patients[left] & patients[right]
            if shared:
                raise ValueError(
                    f"patient overlap between {left} and {right}: {sorted(shared)}. "
                    f"The data pipeline is wrong — fix the pipeline, never this assertion."
                )

    assigned = set().union(*patients.values()) if patients else set()
    missing = set(patient_of.values()) - assigned
    if missing:
        raise ValueError(f"patients in the manifest appear in no split: {sorted(missing)}")

    wrong_vendor = {sid for sid in split.test if vendor_of[sid] != split.held_out_vendor}
    if wrong_vendor:
        raise ValueError(
            f"test split contains samples from a vendor other than "
            f"{split.held_out_vendor!r}: {sorted(wrong_vendor)}"
        )


def save(split: Split, path: Path) -> None:
    """Persist a split so a run is reproducible from the committed config alone.

    Written with sorted keys and an indent so the file is diffable, and so that two
    runs producing the same split produce byte-identical files (SRS-023, RC-004).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(split), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load(path: Path) -> Split:
    """Load a previously saved split."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = set(Split.__dataclass_fields__)
    if set(data) != expected:
        raise ValueError(f"split file has fields {sorted(data)}, expected {sorted(expected)}")
    return Split(**data)


@dataclass(frozen=True)
class FrameSplit:
    """A split expanded from volumes to individual B-scans.

    Produced only by `expand_to_frames`, only from an already-resolved `Split`, and
    never assembled by hand. `volume_of` is carried so that any downstream check can
    recover which acquisition a frame came from without re-deriving it from the
    identifier string.
    """

    fold_id: str
    train: list[str]
    val: list[str]
    test: list[str]
    in_domain_ref: list[str]
    held_out_vendor: str
    seed: int
    volume_of: dict[str, str]


def frame_id(sample_id: str, index: int) -> str:
    """Identifier for one frame of one volume.

    The volume's identifier is the prefix, so a frame is traceable to its acquisition
    by construction. `volume_of` on `FrameSplit` is the authoritative mapping; this
    format exists so that a frame identifier appearing in a log is legible.
    """
    if index < 0:
        raise ValueError(f"frame index must be non-negative, got {index}")
    return f"{sample_id}#{index:04d}"


def expand_to_frames(split: Split, frame_counts: dict[str, int]) -> FrameSplit:
    """Expand a resolved volume-level split into frames (SRS-067, SRS-068, SRS-069).

    **Expansion happens after splitting and never before.** This function takes a
    `Split` that already exists, so there is no ordering in which frames are assigned
    first; the type signature is the enforcement. Every frame inherits the bucket of its
    volume and no frame acquires one by any other route.

    This matters because the DICOM layer produces one multi-frame instance per volume
    while training consumes 2-D B-scans, so an expansion step exists that did not when
    `leave_one_vendor_out` was written. A correct volume-level split followed by a wrong
    expansion reaches HAZ-008 by a second path: adjacent B-scans from one retina, microns
    apart, on both sides of the split.

    Deterministic: volumes are taken in the order the split records them and frames in
    ascending index, so the same split and counts always produce the same lists in the
    same order (SRS-069). No randomness is involved, which is why no seed is taken —
    `split.seed` is carried through for provenance only.

    Raises if any assigned volume has no frame count, rather than silently dropping it:
    a volume missing from the expansion is a volume missing from training or evaluation,
    and its absence would be invisible in the resulting lengths.
    """
    buckets = {
        "train": split.train,
        "val": split.val,
        "test": split.test,
        "in_domain_ref": split.in_domain_ref,
    }

    missing = sorted({sid for ids in buckets.values() for sid in ids if sid not in frame_counts})
    if missing:
        raise ValueError(
            f"no frame count for {len(missing)} assigned volume(s): {missing[:5]}. "
            f"Dropping them would remove data from training or evaluation without "
            f"changing anything observable about the split."
        )

    expanded: dict[str, list[str]] = {}
    volume_of: dict[str, str] = {}
    for name, ids in buckets.items():
        frames: list[str] = []
        for sample_id in ids:
            count = frame_counts[sample_id]
            if count <= 0:
                raise ValueError(f"volume {sample_id!r} reports {count} frames")
            for index in range(count):
                fid = frame_id(sample_id, index)
                frames.append(fid)
                volume_of[fid] = sample_id
        expanded[name] = frames

    return FrameSplit(
        fold_id=split.fold_id,
        train=expanded["train"],
        val=expanded["val"],
        test=expanded["test"],
        in_domain_ref=expanded["in_domain_ref"],
        held_out_vendor=split.held_out_vendor,
        seed=split.seed,
        volume_of=volume_of,
    )


def assert_no_patient_overlap_after_expansion(
    frame_split: FrameSplit, manifest: Sequence[Sample]
) -> None:
    """Re-assert disjointness at patient level on the expanded frames (RC-031).

    Inheritance is checked rather than assumed. The volume-level assertion having passed
    says nothing about whether the expansion preserved it, and the two failures look
    identical downstream — a Dice score that reflects memorisation.
    """
    patient_of = {s.sample_id: s.patient_id for s in manifest}

    buckets = {
        "train": frame_split.train,
        "val": frame_split.val,
        "test": frame_split.test,
        "in_domain_ref": frame_split.in_domain_ref,
    }

    unknown = {
        fid
        for ids in buckets.values()
        for fid in ids
        if frame_split.volume_of.get(fid) not in patient_of
    }
    if unknown:
        raise ValueError(
            f"expanded frames reference volumes absent from the manifest: {sorted(unknown)[:5]}"
        )

    patients = {
        name: {patient_of[frame_split.volume_of[fid]] for fid in ids}
        for name, ids in buckets.items()
    }
    names = sorted(buckets)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            shared = patients[left] & patients[right]
            if shared:
                raise ValueError(
                    f"patient overlap after expansion between {left} and {right}: "
                    f"{sorted(shared)}. The volume-level split may have been correct; the "
                    f"expansion was not. Fix the expansion, never this assertion."
                )
