"""Train the segmentation model. Intended to run on Kaggle, not locally.

Writes the resolved config, the seed, and the split into the run directory so the
run is reproducible from the committed configuration alone.

Usage:
    python scripts/04_train.py --config configs/train_seg.yaml --run-name spectralis_v1
"""

from __future__ import annotations

import sys


def main() -> int:
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
