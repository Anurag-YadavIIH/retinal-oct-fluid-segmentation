"""Write SEG and SR objects for a run and push them to the local Orthanc PACS.

Requires `make pacs-up`.

Usage:
    python scripts/06_push_to_pacs.py --run artifacts/runs/spectralis_v1 \
        --pacs http://localhost:8042/dicom-web
"""

from __future__ import annotations

import sys


def main() -> int:
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
