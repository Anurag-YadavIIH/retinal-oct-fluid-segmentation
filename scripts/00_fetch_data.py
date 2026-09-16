"""Document and verify the manual RETOUCH acquisition. Downloads nothing.

RETOUCH requires registration and acceptance of the challenge terms, so the data
cannot be fetched programmatically. This script exists to (a) record the steps so
the project is reproducible by someone else, and (b) verify that what landed on
disk matches what the pipeline expects.

Manual steps:
  1. Register at https://retouch.grand-challenge.org/ and accept the data terms.
  2. Download the training archives for all three vendors.
  3. Extract into data/raw/retouch/ so that the layout is:

       data/raw/retouch/
         cirrus/TRAIN00x/{oct.mhd,oct.raw,reference.mhd,reference.raw}
         spectralis/...
         topcon/...

  4. Run this script to verify.
"""

from __future__ import annotations

import sys


def main() -> int:
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
