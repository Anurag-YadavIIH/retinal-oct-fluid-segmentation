"""Apply the PS3.15 Basic Application Confidentiality Profile to the converted DICOM.

Verifies every output instance before writing. Any instance that fails
verification aborts the run rather than being skipped.

Usage:
    OCUVAL_DEID_SALT=... python scripts/02_deidentify.py --config configs/data.yaml
"""

from __future__ import annotations

import sys


def main() -> int:
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
