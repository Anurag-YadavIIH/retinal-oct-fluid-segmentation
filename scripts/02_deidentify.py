"""Apply the PS3.15 Basic Application Confidentiality Profile to the converted DICOM.

Traces to: SRS-012, SRS-013, SRS-014, SRS-031
Implements risk control: RC-012

Verifies every output instance before continuing. Any instance that fails verification
aborts the run rather than being skipped: a skipped instance is one that still carries
an identifying attribute, and a run that reports success having skipped it has reported
the wrong thing.

The salt is read from the environment variable named in the configuration and is never
written to the manifest or the provenance file. The run records that a salt was present,
not what it was.

Usage:
    OCUVAL_DEID_SALT=... python scripts/02_deidentify.py --config configs/data.yaml
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from collections import Counter
from pathlib import Path

import pydicom

from ocuval.io import deident
from ocuval.runs import (
    load_manifest,
    manifest_path,
    parse_args,
    resolve,
    save_manifest,
    write_provenance,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(__doc__.splitlines()[0], argv)
    config = resolve(args.config, Path("."))
    output_root = args.output or config.path("deident_root")
    config = resolve(args.config, output_root)

    salt_env = config.config["deidentification"]["pseudonym_salt_env"]
    salt = os.environ.get(salt_env)
    if not salt:
        print(
            f"!! {salt_env} is not set. Aborting rather than inventing a salt "
            f"(SRS-013): an unsalted pseudonym over a small identifier space is "
            f"reversible by enumeration, which is a control that looks like a control.",
            file=sys.stderr,
        )
        return 2

    source = manifest_path(config.config)
    if not source.is_file():
        print(f"!! no manifest at {source}; run 01_convert_to_dicom.py first", file=sys.stderr)
        return 2
    rows = load_manifest(source)

    # Recorded so a later run can tell whether it used the same salt, without the salt
    # itself ever being written down. A digest of the salt is not the salt.
    salt_fingerprint = hashlib.sha256(salt.encode()).hexdigest()[:16]
    write_provenance(
        "02_deidentify", config, {"salt_env": salt_env, "salt_fingerprint": salt_fingerprint}
    )

    started = time.time()
    pseudonyms: Counter[str] = Counter()
    for row in rows:
        src = Path(row["path"])
        dst = output_root / row["vendor"] / src.name
        deident.deidentify_instance(src, dst, salt)

        offending = deident.verify_deidentified(dst)
        if offending:
            print(
                f"!! de-identification verification failed for {dst}: {offending}. "
                f"Aborting; failing instances are never skipped.",
                file=sys.stderr,
            )
            return 1

        dataset = pydicom.dcmread(str(dst), stop_before_pixels=True)
        row["deident_path"] = str(dst)
        row["pseudonym"] = str(dataset.PatientID)
        pseudonyms[row["pseudonym"]] += 1
        print(f"  {row['vendor']:11} {row['patient_id']} -> {row['pseudonym']}", flush=True)

    collisions = {p: n for p, n in pseudonyms.items() if n > 1}
    if collisions:
        print(
            f"!! pseudonym collision: {collisions}. Two subjects sharing a pseudonym is "
            f"HAZ-004 — a result recorded against the wrong person — and also breaks "
            f"patient-level splitting.",
            file=sys.stderr,
        )
        return 1

    save_manifest(rows, source)
    write_provenance(
        "02_deidentify",
        config,
        {
            "salt_env": salt_env,
            "salt_fingerprint": salt_fingerprint,
            "instances": len(rows),
            "distinct_pseudonyms": len(pseudonyms),
            "elapsed_seconds": round(time.time() - started, 1),
        },
    )
    print(f"\nde-identified {len(rows)} instances in {time.time() - started:.0f}s")
    print(f"distinct pseudonyms: {len(pseudonyms)} for {len(rows)} volumes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
