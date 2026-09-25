"""Dataset and dataloader construction from a resolved Split.

Traces to: SRS-070, SRS-071, SRS-073 (data loading)
Implements risk control: RC-031 (frames inherit, never acquire)
Verifies: TC-045, TC-047

This module turns a volume-level `Split` into frame-level samples the network can
consume, and it is the only place where that turn is made. Two properties have to hold
across it, and neither is a convention:

**Split assignment is inherited** (SRS-067, SRS-068, RC-031). `splits.expand_to_frames`
does the expansion; nothing here assigns a frame to a bucket by any other route.

**The intensity window is inherited** (SRS-071). The window is a property of the volume,
computed once at ingestion from the raw array. Every frame of that volume carries the
same one. Nothing here computes a percentile, and `assert_window_inheritance` checks the
result rather than trusting the lookup that produced it -- the same reasoning that made
`assert_no_patient_overlap_after_expansion` an assertion rather than a comment.

**Training reads the archive's native MetaImage, not the DICOM.** The de-identified
instances this pipeline writes are Ophthalmic Tomography *images* and carry no
segmentation -- the reference masks exist only in RETOUCH's `reference.mhd`. Reading the
image from DICOM and the label from the raw archive would mean two sources for one
training pair, with nothing checking that they still correspond. The DICOM layer is the
output interface (SEG, SR, PACS), not the training input, and `source_path` on each
manifest row is what ties a trained-on volume back to the instance a result is reported
against.

B-scan separation is deliberately unused. Training is 2D and frames are independent, so
the only geometry reaching a transform is axial and lateral spacing (SRS-073). Enabling
2.5D would change that, and is a separate decision.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ocuval.data.splits import (
    FrameSplit,
    Sample,
    Split,
    assert_no_patient_overlap_after_expansion,
    expand_to_frames,
    frame_id,
)

# One record per volume, as written by the conversion stage.
VolumeRecord = dict[str, Any]

# Fields a manifest row must carry for training. Named explicitly so a row missing one
# fails here, naming it, rather than raising a KeyError deep inside a worker process.
REQUIRED_FIELDS = (
    "sample_id",
    "patient_id",
    "vendor",
    "shape",
    "spacing_mm",
    "intensity_window",
    "source_path",
)


def check_manifest(manifest: Sequence[VolumeRecord]) -> None:
    """Every row carries what training needs, before anything is built from it."""
    for row in manifest:
        missing = [field for field in REQUIRED_FIELDS if field not in row]
        if missing:
            raise KeyError(
                f"manifest row {row.get('sample_id', '<no sample_id>')!r} is missing "
                f"{missing}. intensity_window is computed at ingestion (SRS-070) and has "
                f"no default; source_path is what makes a frame traceable to its volume."
            )


def frame_counts_from_manifest(manifest: Sequence[VolumeRecord]) -> dict[str, int]:
    """Number of B-scans per volume, from the recorded shape.

    Read from the manifest rather than by opening each file: the manifest is what the
    split was built against, and a count taken from the file could disagree with it
    without anything failing.
    """
    counts: dict[str, int] = {}
    for row in manifest:
        shape = row["shape"]
        if len(shape) != 3:
            raise ValueError(f"volume {row['sample_id']!r} has shape {shape!r}, expected 3-D")
        subject = row["patient_id"]
        if subject in counts:
            # Splits are keyed on the subject (SRS-023), which assumes one acquisition
            # per subject. RETOUCH satisfies that -- 70 subjects, 70 volumes, identifiers
            # unique across vendors -- and if it ever stops being true the expansion
            # would silently drop a volume, so fail here instead.
            raise ValueError(
                f"subject {subject!r} has more than one volume in the manifest. Splits "
                f"are keyed on the subject identifier, so the expansion cannot tell the "
                f"volumes apart. This needs a decision, not a default."
            )
        counts[subject] = int(shape[0])
    return counts


def samples_from_manifest(manifest: Sequence[VolumeRecord]) -> list[Sample]:
    return [
        Sample(sample_id=row["sample_id"], patient_id=row["patient_id"], vendor=row["vendor"])
        for row in manifest
    ]


def build_frame_split(split: Split, manifest: Sequence[VolumeRecord]) -> FrameSplit:
    """Expand a volume-level split to frames, with the leakage check applied.

    The assertion is not optional here. TC-004 gates the volume-level split in CI, and a
    split correct at volume level can still leak if expansion misassigns frames -- that
    is HAZ-008's second mechanism, and TC-004 cannot see it.
    """
    check_manifest(manifest)
    frame_split = expand_to_frames(split, frame_counts_from_manifest(manifest))
    assert_no_patient_overlap_after_expansion(frame_split, samples_from_manifest(manifest))
    return frame_split


def frame_records(
    manifest: Sequence[VolumeRecord],
    frame_split: FrameSplit,
    bucket: str,
) -> list[dict[str, Any]]:
    """Frame-level sample dictionaries for one bucket of an expanded split.

    Every field a transform or a metric needs is attached here from the volume's own
    manifest row: the intensity window (SRS-070, SRS-071), the spacing (SRS-074, so a
    prediction can be returned to native geometry), and vendor and patient identity,
    which must survive into the evaluation output because subgroup reporting depends on
    it (CLAUDE.md section 4).

    A frame whose volume is absent from the manifest raises rather than being skipped.
    Skipping would silently shrink a split, changing a reported metric without changing
    anything observable about the run.
    """
    by_subject = {row["patient_id"]: row for row in manifest}
    records = []
    for fid in getattr(frame_split, bucket):
        subject_id = frame_split.volume_of[fid]
        row = by_subject.get(subject_id)
        if row is None:
            raise KeyError(
                f"frame {fid!r} belongs to subject {subject_id!r}, which is not in the "
                f"manifest. Dropping it would remove data from {bucket} without changing "
                f"the split's apparent size."
            )
        records.append(
            {
                "frame_id": fid,
                "sample_id": row["sample_id"],
                "subject_id": subject_id,
                "frame_index": _index_of(fid),
                "patient_id": row["patient_id"],
                "vendor": row["vendor"],
                "source_path": str(row["source_path"]),
                "spacing_mm": tuple(float(v) for v in row["spacing_mm"]),
                # Inherited, never recomputed (SRS-071).
                "intensity_window": tuple(float(v) for v in row["intensity_window"]),
            }
        )
    return records


def _index_of(fid: str) -> int:
    """Frame index from a frame identifier produced by `splits.frame_id`."""
    head, _, tail = fid.rpartition("#")
    if not head or not tail.isdigit():
        raise ValueError(f"{fid!r} is not a frame identifier produced by splits.frame_id")
    return int(tail)


def assert_window_inheritance(
    records: Sequence[dict[str, Any]],
    manifest: Sequence[VolumeRecord],
) -> None:
    """Every frame carries exactly its volume's window (SRS-071).

    Checked rather than assumed. Inheritance is one dictionary lookup, easy to write and
    easy to get subtly wrong -- a stale row, a default, a frame attributed to the wrong
    volume -- and the failure is invisible downstream, because a frame normalised against
    another volume's window is still a perfectly plausible B-scan. The check costs one
    pass over the frames.
    """
    expected = {
        row["patient_id"]: tuple(float(v) for v in row["intensity_window"]) for row in manifest
    }
    wrong = [
        (record["frame_id"], record["intensity_window"], expected.get(record["subject_id"]))
        for record in records
        if record["intensity_window"] != expected.get(record["subject_id"])
    ]
    if wrong:
        raise AssertionError(
            f"{len(wrong)} frame(s) do not carry their volume's intensity window "
            f"(SRS-071). First: {wrong[:3]}. A frame normalised against another volume's "
            f"window is still a plausible image, so this cannot be caught by inspection."
        )


class LoadFrame:
    """Read one B-scan and its reference mask from the archive's native volume.

    Whole volumes are decoded and the requested frame taken from them, which is wasteful
    per frame and irrelevant in practice: every frame passes through here once, because
    `PersistentDataset` caches the transformed result to disk. A per-frame reader would
    be faster on a cold cache and would need its own correctness argument about frame
    ordering, which this does not.

    The volume's own spacing and intensity window are NOT read here. They arrive on the
    record from the manifest, so that what training normalises against is the value that
    was recorded at ingestion and can be audited, not one recomputed at load time.
    """

    def __init__(self, image_key: str = "image", label_key: str = "label"):
        self.image_key = image_key
        self.label_key = label_key

    def __call__(self, record: dict[str, Any]) -> dict[str, Any]:
        from ocuval.io.retouch_reader import read_volume

        out = dict(record)
        volume = read_volume(Path(record["source_path"]), record["vendor"])
        index = record["frame_index"]
        out[self.image_key] = volume.pixel_array[index]
        if volume.label_array is not None:
            out[self.label_key] = volume.label_array[index]
        return out


def prepare_cache(records: Sequence[dict[str, Any]], transform, cache_dir: Path) -> dict[str, int]:
    """Populate a PersistentDataset cache volume-wise (SRS-078).

    **Why this exists.** `LoadFrame` decodes a whole volume to serve one frame, measured
    at 1.67 s. Letting the dataloader fill the cache frame by frame therefore costs about
    1.9 hours of decoding per epoch, or roughly half an hour spread over four workers,
    before the second epoch can start. Grouping by volume decodes each of a fold's ~32
    volumes once -- about 53 seconds -- because one decode serves all 128 of its frames.

    **Why it cannot change a value.** This calls the same transform on the same records
    that the dataloader would; it only controls the order in which they are visited, and
    the transform chain up to the first random operation is a pure function of the
    record. TC-039 asserts the frames are bit-identical to the uncached path, because an
    optimisation that can alter a value is not an optimisation.

    Returns the number of frames prepared per volume, for the run log.
    """
    from monai.data import PersistentDataset

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Group by source volume, then order by frame index within it, so each volume is
    # decoded once and consecutively rather than revisited.
    ordered = sorted(
        range(len(records)), key=lambda i: (records[i]["source_path"], records[i]["frame_index"])
    )
    grouped = [records[i] for i in ordered]

    dataset = PersistentDataset(grouped, transform=transform, cache_dir=str(cache_dir))
    counts: dict[str, int] = {}
    for position in range(len(dataset)):
        dataset[position]  # noqa: B018 - the indexing IS the work; it writes the cache
        counts[grouped[position]["source_path"]] = (
            counts.get(grouped[position]["source_path"], 0) + 1
        )
    return counts


def build_datasets(
    split: Split,
    cfg: dict,
    manifest: Sequence[VolumeRecord],
):
    """Return (train_ds, val_ds, test_ds). Vendor and patient_id survive as fields.

    Cache backend comes from the configuration. `PersistentDataset` is the default
    because `CacheDataset` holds decoded volumes in RAM, and this archive is 5.9 GB of
    MetaImage that will not fit alongside training on a 16 GB machine.
    """
    from monai.data import CacheDataset, Dataset, PersistentDataset
    from monai.transforms import Compose

    from ocuval.data.transforms import eval_transforms, train_transforms

    data_cfg = cfg.get("data", cfg)
    seed = cfg.get("run", {}).get("seed")
    mode = data_cfg.get("mode", "2d")
    if mode != "2d":
        raise NotImplementedError(
            f"mode {mode!r}: only 2D is implemented. 2.5D changes what B-scan separation "
            f"means to the transform chain (SRS-073) and is a separate decision."
        )

    frame_split = build_frame_split(split, manifest)
    buckets = {}
    for name in ("train", "val", "test"):
        records = frame_records(manifest, frame_split, name)
        assert_window_inheritance(records, manifest)
        buckets[name] = records

    chain_for = {
        "train": Compose([LoadFrame(), train_transforms(cfg, seed=seed)]),
        "val": Compose([LoadFrame(), eval_transforms(cfg)]),
        "test": Compose([LoadFrame(), eval_transforms(cfg)]),
    }

    backend = data_cfg.get("cache", "persistent")
    cache_root = Path(data_cfg.get("cache_dir", "artifacts/cache")) / split.fold_id

    def make(name: str):
        records, chain = buckets[name], chain_for[name]
        if backend == "memory":
            return CacheDataset(
                records, transform=chain, cache_rate=float(data_cfg.get("cache_rate", 0.2))
            )
        if backend == "persistent":
            directory = cache_root / name
            directory.mkdir(parents=True, exist_ok=True)
            return PersistentDataset(records, transform=chain, cache_dir=str(directory))
        return Dataset(records, transform=chain)

    return make("train"), make("val"), make("test")


def build_loaders(split: Split, cfg: dict, manifest: Sequence[VolumeRecord]):
    """DataLoaders for the three buckets, seeded so a run is reproducible.

    Shuffling is on for training only. Validation and test keep manifest order: a metric
    computed over a shuffled loader is identical in expectation and different in
    floating-point detail, which would make two runs of one checkpoint disagree in the
    last digits for no reason (CLAUDE.md rule 4).
    """
    import torch
    from monai.data import DataLoader

    data_cfg = cfg.get("data", cfg)
    seed = cfg.get("run", {}).get("seed")
    train_ds, val_ds, test_ds = build_datasets(split, cfg, manifest)

    generator = torch.Generator()
    if seed is not None:
        generator.manual_seed(int(seed))

    # Batch size lives under `train:` and nowhere else. Reading it from `data:` as well
    # would give the configuration two places to say one thing, which is how a run ends
    # up reporting a batch size it did not use.
    train_cfg = cfg.get("train", {})
    if "batch_size" not in train_cfg:
        raise KeyError(
            "configs/train_seg.yaml has no train.batch_size. It is a declared constant "
            "(SRS-031 records it in the run output) and has no default."
        )
    common = {
        "batch_size": int(train_cfg["batch_size"]),
        "num_workers": int(data_cfg.get("num_workers", 4)),
        "pin_memory": False,
    }
    return (
        DataLoader(train_ds, shuffle=True, generator=generator, **common),
        DataLoader(val_ds, shuffle=False, **common),
        DataLoader(test_ds, shuffle=False, **common),
    )


__all__ = [
    "LoadFrame",
    "prepare_cache",
    "assert_window_inheritance",
    "build_datasets",
    "build_frame_split",
    "build_loaders",
    "check_manifest",
    "frame_counts_from_manifest",
    "frame_id",
    "frame_records",
    "samples_from_manifest",
]
