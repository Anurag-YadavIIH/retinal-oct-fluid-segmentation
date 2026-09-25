"""Convert native RETOUCH volumes into conformant DICOM OPT objects.

Traces to: SRS-001, SRS-010, SRS-031, SRS-062, SRS-063, SRS-070
Implements risk control: RC-021, RC-029

Writes the volume manifest as a stage output, under the configured dicom_root, with the
resolved configuration beside it. The manifest carries the per-volume intensity window
computed at ingestion (SRS-070) and the source path, so training can be traced back to
the acquisition a result is reported against.

RETOUCH records no laterality, no acquisition date-time, no device serial and no model
name, so the SRS-063 research exception is the only path for this dataset and is enabled
here. It omits those attributes rather than inventing them (RC-029); every omission is
counted and recorded in the provenance file. See docs/11 section 10 item 3.

Usage:
    python scripts/01_convert_to_dicom.py --config configs/data.yaml
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

from ocuval.io import dicom_writer as dw
from ocuval.io.retouch_reader import read_volume, subject_directories
from ocuval.runs import manifest_path, parse_args, resolve, save_manifest, write_provenance


def main(argv: list[str] | None = None) -> int:
    args = parse_args(__doc__.splitlines()[0], argv)
    config = resolve(args.config, Path("."))
    output_root = args.output or config.path("dicom_root")
    config = resolve(args.config, output_root)

    raw_root = config.path("raw_root")
    if not raw_root.is_dir():
        print(f"!! raw_root {raw_root} does not exist", file=sys.stderr)
        return 2

    write_provenance("01_convert_to_dicom", config)

    uid_root = config.config["dicom"]["uid_root"]
    vendors = config.config["vendors"]
    started = time.time()
    omissions: Counter[str] = Counter()
    depths: Counter[str] = Counter()
    rows = []

    for vendor in vendors:
        for directory in subject_directories(raw_root, vendor):
            volume = read_volume(directory, vendor)
            result = dw.write_volume(
                volume,
                output_root / vendor,
                uid_root,
                research_exception=True,
                series_instance_uid=None,
            )
            for omission in result.omissions:
                omissions[omission] += 1
            depths[f"{vendor}:{volume.pixel_array.dtype}"] += 1
            rows.append(
                {
                    "sample_id": result.sop_instance_uids[0],
                    "patient_id": volume.patient_id,
                    "vendor": vendor,
                    "shape": list(volume.pixel_array.shape),
                    "dtype": str(volume.pixel_array.dtype),
                    "spacing_mm": list(volume.spacing_mm),
                    "intensity_window": list(volume.intensity_window),
                    "source_path": str(directory),
                    "path": str(result.paths[0]),
                    "study_instance_uid": result.study_instance_uid,
                    "series_instance_uid": result.series_instance_uid,
                }
            )
            print(
                f"  {vendor:11} {volume.patient_id}  {volume.pixel_array.shape} "
                f"{volume.pixel_array.dtype}  window={volume.intensity_window}",
                flush=True,
            )

    destination = save_manifest(rows, manifest_path(config.config))
    write_provenance(
        "01_convert_to_dicom",
        config,
        {
            "volumes_converted": len(rows),
            "bit_depths": dict(depths),
            "omissions": dict(omissions),
            "elapsed_seconds": round(time.time() - started, 1),
            "manifest": str(destination),
        },
    )
    print(f"\nconverted {len(rows)} volumes in {time.time() - started:.0f}s")
    print(f"bit depths: {dict(depths)}")
    print(f"omissions (SRS-063, per attribute): {dict(omissions)}")
    print(f"manifest: {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
