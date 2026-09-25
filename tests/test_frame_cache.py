"""Verification of the frame cache and its pre-pass (TC-039, SRS-078).

**Rewritten 2026-09-25.** The previous version compared the values a cached dataset
served against an uncached one. They matched, and it passed, while the cache stored no
pixels at all -- the transform simply re-ran on every read. A cache test that never
inspects the cache verifies the wrong property. These tests inspect the artefact and
count decodes. See docs/13.
"""

from __future__ import annotations

import numpy as np
import torch
from monai.transforms import (
    Compose,
    EnsureChannelFirstd,
    RandomizableTrait,
    ToTensord,
    Transform,
)

from ocuval.data.datamodule import LoadFrame, flat_chain, prepare_cache
from ocuval.data.transforms import ApplyStoredIntensityWindowd


def synthetic_records(volumes: int = 3, frames: int = 4) -> list[dict]:
    return [
        {
            "frame_id": f"TRAIN{v:03d}#{i:04d}",
            "sample_id": f"uid-{v}",
            "subject_id": f"TRAIN{v:03d}",
            "vendor": "cirrus",
            "source_path": f"/raw/vol{v}",
            "frame_index": i,
            "spacing_mm": (0.001955, 0.011742, 0.046878),
            "intensity_window": (float(v), 200.0 + v),
        }
        for v in range(volumes)
        for i in range(frames)
    ]


class CountingLoader(Transform):
    """Stands in for LoadFrame, memoising one volume and counting decodes as it does.

    A Transform subclass deliberately. A plain callable makes PersistentDataset cache
    nothing, which is the defect these tests exist to catch.
    """

    def __init__(self, frames: int = 4, size: tuple[int, int] = (64, 32)):
        super().__init__()
        self.frames, self.size = frames, size
        self.decodes = 0
        self._path: str | None = None
        self._volume: np.ndarray | None = None

    def __call__(self, record: dict) -> dict:
        path = record["source_path"]
        if self._path != path:
            rng = np.random.default_rng(abs(hash(path)) % (2**32))
            self._volume = rng.integers(0, 200, (self.frames, *self.size)).astype(np.uint8)
            self._path = path
            self.decodes += 1
        out = dict(record)
        out["image"] = np.array(self._volume[record["frame_index"]], copy=True)
        return out


def deterministic_chain(loader: Transform) -> Compose:
    return flat_chain(
        loader,
        EnsureChannelFirstd(keys=("image",), channel_dim="no_channel"),
        ApplyStoredIntensityWindowd(keys=("image",)),
        ToTensord(keys=("image",)),
    )


def cache_boundary(chain: Compose) -> int | None:
    """Where PersistentDataset stops caching, by its own rule.

    None means nothing matched, i.e. the whole chain is cacheable.
    """
    return chain.get_index_of_first(
        lambda t: isinstance(t, RandomizableTrait) or not isinstance(t, Transform)
    )


# --- the mechanism that makes caching possible at all --------------------------------


def test_TC_039_load_frame_is_a_monai_transform():
    """Not cosmetic.

    `PersistentDataset._pre_transform` stops at the first transform that is
    RandomizableTrait *or not a Transform*, so a plain callable at position zero means
    the cache stores the input record and every epoch re-decodes.
    """
    assert isinstance(LoadFrame(), Transform)


def test_TC_039_a_nested_compose_truncates_the_cached_prefix():
    """Why flat_chain exists, asserted rather than left as a comment.

    Compose is itself Randomizable, so nesting one inside another stops caching at it.
    """
    inner = Compose(
        [
            EnsureChannelFirstd(keys=("image",), channel_dim="no_channel"),
            ToTensord(keys=("image",)),
        ]
    )
    nested = Compose([CountingLoader(), inner])
    flat = flat_chain(CountingLoader(), inner)

    assert cache_boundary(nested) == 1, "nesting should truncate at the inner Compose"
    assert cache_boundary(flat) is None, (
        "a flattened deterministic chain should be cacheable end to end; None means no "
        "transform in it stops the cache"
    )


def test_TC_039_the_training_chain_caches_up_to_the_first_random_transform():
    """The boundary must land where it belongs, not earlier and not later."""
    from pathlib import Path

    import yaml

    from ocuval.data.transforms import train_transforms

    cfg = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "configs" / "train_seg.yaml").read_text(
            encoding="utf-8"
        )
    )
    chain = flat_chain(LoadFrame(), train_transforms(cfg, seed=1))
    boundary = cache_boundary(chain)

    assert 0 < boundary < len(chain.transforms), "expected a genuine deterministic prefix"
    assert isinstance(chain.transforms[boundary], RandomizableTrait)
    assert all(
        not isinstance(t, RandomizableTrait) for t in chain.transforms[:boundary]
    ), "a random transform is inside the cached prefix, which would freeze augmentation"


# --- TC-039: the artefact ---------------------------------------------------------------


def test_TC_039_the_cache_actually_contains_the_transformed_frame(tmp_path):
    """Inspect the artefact, not what the dataset serves."""
    from monai.data import PersistentDataset

    records = synthetic_records()
    chain = deterministic_chain(CountingLoader())
    dataset = PersistentDataset(records, transform=chain, cache_dir=str(tmp_path / "c"))
    for index in range(len(dataset)):
        dataset[index]

    files = sorted((tmp_path / "c").glob("*.pt"))
    assert len(files) == len(records), "one cache entry per frame"

    payload = torch.load(files[0], map_location="cpu", weights_only=False)
    assert "image" in payload, (
        "the cache entry holds no image, so PersistentDataset cached the raw record and "
        "the expensive work re-runs every epoch (SRS-078)"
    )
    assert payload["image"].shape[0] == 1, "cached frame is not channel-first"
    assert payload["image"].dtype == torch.float32, "cached frame is not normalised"


def test_TC_039_prepass_decodes_each_volume_once(tmp_path):
    """SRS-078's actual claim, counted.

    The earlier version asserted only that volumes were *visited* contiguously, which
    the ordering guarantees and which says nothing about whether decoding was avoided.
    """
    loader = CountingLoader()
    prepare_cache(
        synthetic_records(volumes=3, frames=4), deterministic_chain(loader), tmp_path / "c"
    )
    assert loader.decodes == 3, (
        f"decoded {loader.decodes} times for 3 volumes of 4 frames; the pre-pass must "
        f"decode each source volume once (SRS-078)"
    )


def test_TC_039_a_warm_cache_performs_no_decode(tmp_path):
    from monai.data import PersistentDataset

    records = synthetic_records()
    loader = CountingLoader()
    chain = deterministic_chain(loader)
    prepare_cache(records, chain, tmp_path / "c")

    loader.decodes = 0
    dataset = PersistentDataset(records, transform=chain, cache_dir=str(tmp_path / "c"))
    for index in range(len(dataset)):
        dataset[index]
    assert loader.decodes == 0, "a warm cache re-decoded; the cache is not being hit"


def test_TC_039_cached_frames_are_identical_to_uncached(tmp_path):
    """The original property, kept: a cache is an optimisation and cannot change a value."""
    from monai.data import Dataset, PersistentDataset

    records = synthetic_records()
    uncached = Dataset(records, transform=deterministic_chain(CountingLoader()))
    reference = [uncached[i]["image"].clone() for i in range(len(records))]

    chain = deterministic_chain(CountingLoader())
    prepare_cache(records, chain, tmp_path / "c")
    cached = PersistentDataset(records, transform=chain, cache_dir=str(tmp_path / "c"))

    for index, expected in enumerate(reference):
        assert torch.equal(
            expected, cached[index]["image"]
        ), "a frame served from the cache differs from the uncached one (SRS-078)"


def test_TC_039_frames_do_not_alias_the_memoised_volume():
    """Consecutive frames must not share a buffer the next decode overwrites."""
    loader = CountingLoader()
    records = synthetic_records(volumes=1, frames=3)
    first = loader(records[0])["image"]
    snapshot = first.copy()
    loader(records[1])
    loader(records[2])
    assert np.array_equal(first, snapshot), "an earlier frame changed when a later one loaded"
    assert loader.decodes == 1, "one volume should decode once across its frames"
