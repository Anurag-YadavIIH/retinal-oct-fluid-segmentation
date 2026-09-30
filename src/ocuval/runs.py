"""Stage entry points: config resolution, provenance, and the volume manifest.

Traces to: SRS-031 (run provenance), SRS-070 (intensity window on the manifest)
Verifies: TC-057

Every pipeline stage resolves its configuration here and records what it resolved
alongside its output. SRS-031 requires the seed, the resolved configuration and the
software version to be written into the run output at the start of every run, and
CLAUDE.md rule 4 requires results to be reproducible from the committed config alone.

**Why a stage writes its resolved config rather than the caller recording the command.**
A command line records what was asked for; a resolved config records what was used.
Between the two sits every default, every environment variable and every path that a
config file leaves implicit. The first run of this pipeline on real data was driven by
an ad-hoc script with its manifest in a scratch directory, and the resulting artefacts
could not be regenerated from anything in the repository -- which is precisely what
SRS-031 exists to prevent. See docs/13, 2026-09-25.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ocuval import __version__

MANIFEST_NAME = "manifest.json"
PROVENANCE_NAME = "run.json"

# Fields every manifest row carries. Duplicated deliberately in data.datamodule as
# REQUIRED_FIELDS: the producer and the consumer each state what they need, so a change
# to one without the other fails a test rather than silently dropping a field.
MANIFEST_FIELDS = (
    "sample_id",
    "patient_id",
    "vendor",
    "shape",
    "dtype",
    "spacing_mm",
    "intensity_window",
    "source_path",
    "path",
)


@dataclass(frozen=True)
class StageConfig:
    """A resolved configuration plus where its outputs go."""

    config_path: Path
    config: dict[str, Any]
    output_root: Path

    def path(self, key: str) -> Path:
        return Path(self.config["paths"][key])


def parse_args(description: str, argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data.yaml"),
        help="configuration to resolve; the resolved copy is written to the output",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="where to write stage outputs; defaults to the stage's configured path",
    )
    return parser.parse_args(argv)


def resolve(config_path: Path, output_root: Path) -> StageConfig:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    return StageConfig(Path(config_path), config, Path(output_root))


def environment_record() -> dict[str, Any]:
    """Identify the environment a run executed in (NFR-002).

    Two things, because neither alone is enough:

    - **The lock's SHA-256.** `requirements.lock` is the committed environment. Its
      digest ties a result to an exact dependency set without copying 73 lines into
      every run directory, and changes if any pin does.
    - **The torch build.** The lock pins `torch==2.3.1` and cannot carry `+cu121`,
      because that build does not exist on PyPI and CI must be able to install from the
      lock. A machine satisfying the lock may therefore be running the CPU build. The
      build is the one part of the environment the lock cannot express, so it is
      recorded per run instead. See `docs/04` §4.1.
    """
    record: dict[str, Any] = {"lock_sha256": None, "lock_path": None, "torch_build": None}

    lock = Path(__file__).resolve().parents[2] / "requirements.lock"
    if lock.is_file():
        record["lock_sha256"] = hashlib.sha256(lock.read_bytes()).hexdigest()
        record["lock_path"] = str(lock)

    try:
        import torch
    except ImportError:
        pass
    else:
        record["torch_build"] = torch.__version__
        record["cuda_runtime"] = torch.version.cuda
        record["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            record["gpu_name"] = torch.cuda.get_device_name(0)
            record["gpu_capability"] = "%d.%d" % torch.cuda.get_device_capability(0)
    return record


def write_provenance(
    stage: str, resolved: StageConfig, extra: dict[str, Any] | None = None
) -> Path:
    """Record seed, resolved configuration and version beside the stage's output.

    Written at the START of the stage (SRS-031), so a run that aborts halfway still
    leaves evidence of what it was attempting. A provenance file written on success
    would be absent exactly when it is most needed.
    """
    resolved.output_root.mkdir(parents=True, exist_ok=True)
    record = {
        "stage": stage,
        "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "ocuval_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "config_path": str(resolved.config_path),
        "seed": resolved.config.get("seed"),
        "environment": environment_record(),
        "resolved_config": resolved.config,
    }
    if extra:
        record.update(extra)
    destination = resolved.output_root / PROVENANCE_NAME
    destination.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def save_manifest(rows: list[dict[str, Any]], destination: Path) -> Path:
    """Write the volume manifest as a stage output.

    Sorted by sample_id and written with sorted keys, so two runs of the same stage over
    the same archive produce a byte-identical file. A manifest that differed run to run
    in ordering alone would make every downstream diff useless for telling whether
    anything had actually changed.
    """
    for row in rows:
        missing = [field for field in MANIFEST_FIELDS if field not in row]
        if missing:
            raise KeyError(f"manifest row {row.get('sample_id')!r} is missing {missing}")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda r: (r["vendor"], r["patient_id"]))
    destination.write_text(json.dumps(ordered, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def load_manifest(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"{path} does not contain a list of manifest rows")
    return rows


CACHE_DIR_ENV = "OCUVAL_CACHE_DIR"


def resolve_cache_dir(config: dict[str, Any], override: Path | None = None) -> Path:
    """Where the frame cache lives, resolved at run time rather than committed.

    Precedence: an explicit `--cache-dir`, then the `OCUVAL_CACHE_DIR` environment
    variable, then `data.cache_dir` from the configuration.

    **The committed configuration holds a relative path deliberately.** It is shared by
    every machine that checks out this repository, so an absolute path in it would be
    one laptop's filesystem asserted as everyone's — and on any other machine it would
    either fail or, worse, silently write gigabytes somewhere unintended. The per-machine
    choice belongs to the machine; SRS-031 writes the resolved path into `run.json`, so
    the run still records exactly where its cache was.
    """
    data_cfg = config.get("data", config)
    if override is not None:
        return Path(override)
    from os import environ

    if environ.get(CACHE_DIR_ENV):
        return Path(environ[CACHE_DIR_ENV])
    return Path(data_cfg.get("cache_dir", "artifacts/cache"))


def manifest_path(config: dict[str, Any]) -> Path:
    """Where the manifest lives: a stage output under data/, not a scratch directory."""
    return Path(config["paths"]["dicom_root"]) / MANIFEST_NAME
