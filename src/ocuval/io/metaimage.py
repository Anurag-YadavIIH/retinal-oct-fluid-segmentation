"""Minimal MetaImage (.mhd/.raw) header reader.

Traces to: SRS-001, SRS-003, SRS-004, SRS-005 (data ingestion)

Separated from `retouch_reader` so that the file format and the dataset layout are two
concerns rather than one: this module knows MetaImage and nothing about RETOUCH, and
`retouch_reader` knows RETOUCH and delegates the format.

**Why not SimpleITK**, which is pinned as SOUP-005 and reads MetaImage perfectly well.
Two reasons, and neither is that the library is inadequate:

1. `docs/04` SOUP-005 records the risk that its resampling API makes cross-vendor
   geometric harmonisation easy to do by accident, which SRS-010 and SRS-026 forbid.
   Not importing it into the ingestion path removes that possibility rather than
   relying on care.
2. The header is a dozen `key = value` lines. Reading them explicitly means the
   element type, byte order and dimension order are visible in this repository rather
   than inside a dependency, and those three are exactly what a silent wrong-volume
   defect is made of.

SimpleITK remains available for anything that genuinely needs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

#: MetaImage element types to numpy dtypes. Only the types this project has actually
#: seen are listed; an unlisted type raises rather than being guessed at.
ELEMENT_TYPES: dict[str, np.dtype] = {
    "MET_CHAR": np.dtype("i1"),
    "MET_UCHAR": np.dtype("u1"),
    "MET_SHORT": np.dtype("i2"),
    "MET_USHORT": np.dtype("u2"),
    "MET_INT": np.dtype("i4"),
    "MET_UINT": np.dtype("u4"),
    "MET_FLOAT": np.dtype("f4"),
    "MET_DOUBLE": np.dtype("f8"),
}


class MetaImageError(ValueError):
    """The header is absent, malformed, or describes something this reader will not
    silently accept."""


@dataclass(frozen=True)
class MetaImageHeader:
    """A parsed .mhd header.

    `dim_size` and `element_spacing` are in MetaImage's own (x, y, z) order and are
    **not** reordered here. Reordering is the caller's decision and is made explicitly
    in `retouch_reader`, where it can be named and tested.
    """

    dim_size: tuple[int, int, int]
    element_spacing: tuple[float, float, float]
    element_type: str
    data_file: str
    msb_first: bool
    raw: dict[str, str]

    @property
    def dtype(self) -> np.dtype:
        base = ELEMENT_TYPES[self.element_type]
        return base.newbyteorder(">") if self.msb_first else base.newbyteorder("<")

    @property
    def voxel_count(self) -> int:
        return self.dim_size[0] * self.dim_size[1] * self.dim_size[2]


def parse_header(path: Path) -> MetaImageHeader:
    """Parse a .mhd header, refusing anything it cannot represent faithfully."""
    path = Path(path)
    if not path.is_file():
        raise MetaImageError(f"{path}: no such header file")

    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()

    def require(key: str) -> str:
        if key not in fields:
            raise MetaImageError(f"{path}: header has no {key}")
        return fields[key]

    ndims = int(require("NDims"))
    if ndims != 3:
        raise MetaImageError(f"{path}: NDims is {ndims}; this reader handles 3-D volumes only")

    if fields.get("CompressedData", "False").strip().lower() == "true":
        raise MetaImageError(
            f"{path}: CompressedData is True. This reader does not decompress, and "
            f"reading a compressed file as raw would silently yield noise."
        )

    channels = int(fields.get("ElementNumberOfChannels", "1"))
    if channels != 1:
        raise MetaImageError(f"{path}: ElementNumberOfChannels is {channels}; expected 1")

    element_type = require("ElementType")
    if element_type not in ELEMENT_TYPES:
        raise MetaImageError(
            f"{path}: unsupported ElementType {element_type!r}. Known types are "
            f"{sorted(ELEMENT_TYPES)}. Guessing a width would misread every voxel."
        )

    dims = tuple(int(v) for v in require("DimSize").split())
    spacing = tuple(float(v) for v in require("ElementSpacing").split())
    if len(dims) != 3 or len(spacing) != 3:
        raise MetaImageError(
            f"{path}: DimSize has {len(dims)} and ElementSpacing {len(spacing)} components; "
            f"both must have 3"
        )
    if any(d <= 0 for d in dims):
        raise MetaImageError(f"{path}: DimSize must be positive, got {dims}")

    return MetaImageHeader(
        dim_size=dims,  # type: ignore[arg-type]
        element_spacing=spacing,  # type: ignore[arg-type]
        element_type=element_type,
        data_file=require("ElementDataFile"),
        msb_first=fields.get("BinaryDataByteOrderMSB", "False").strip().lower() == "true",
        raw=fields,
    )


def read_volume_array(header_path: Path) -> np.ndarray:
    """Read the raw payload a header describes, as (z, y, x) — (slices, rows, columns).

    MetaImage stores x fastest, then y, then z, and `DimSize` is given as (x, y, z). The
    array is therefore reshaped to the reverse, `(z, y, x)`, which for this dataset means
    (B-scans, rows, columns). The transposition is the whole reason this function exists
    rather than callers reshaping inline: getting it backwards produces an array of the
    right size and the wrong content, which no size check can catch.

    The element count is checked against the header. A file that is short or long is a
    truncated or mismatched download, and returning what was read would hand back a
    volume that is partly another volume.
    """
    header_path = Path(header_path)
    header = parse_header(header_path)
    data_path = header_path.parent / header.data_file
    if not data_path.is_file():
        raise MetaImageError(f"{header_path}: ElementDataFile {header.data_file!r} not found")

    data = np.fromfile(data_path, dtype=header.dtype)
    if data.size != header.voxel_count:
        raise MetaImageError(
            f"{data_path}: contains {data.size} elements but the header describes "
            f"{header.voxel_count} ({header.dim_size} of {header.element_type}). "
            f"The file is truncated or does not match its header."
        )

    x, y, z = header.dim_size
    return data.reshape((z, y, x))
