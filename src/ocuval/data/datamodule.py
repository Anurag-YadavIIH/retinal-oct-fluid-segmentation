"""Dataset and dataloader construction from a resolved Split.

Traces to: SRS-TBD (data loading)

Choose the cache backend from configs/train_seg.yaml. MONAI's CacheDataset holds
decoded volumes in RAM and will exhaust a 16 GB machine — PersistentDataset is
the default for that reason.
"""

from __future__ import annotations

from ocuval.data.splits import Split


def build_datasets(split: Split, cfg: dict):
    """Return (train_ds, val_ds, test_ds). Vendor and patient_id survive as fields."""
    raise NotImplementedError


def build_loaders(split: Split, cfg: dict):
    """Return (train_loader, val_loader, test_loader)."""
    raise NotImplementedError
