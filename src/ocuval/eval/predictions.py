"""Saved predicted label maps: written once by an evaluation, re-measurable without the model.

Traces to: SRS-106
Verified by: TC-155

**Why.** Every defect found in this project's measurement so far (the inversion, the HD95 axis
order, the detection score's padding) was corrected by re-running the model on every volume:
hours of GPU time and, for a sealed bucket, an unlock. The model's output does not change when a
measurement is corrected. Saving it means the next correction re-measures saved maps against the
references, on the CPU, with nothing re-run.

**What is saved**, one file per volume: the label map in native geometry exactly as it was
measured, the spacing it was measured with, the three detection scores, and the volume's identity.
That is everything `measured_volume` needs beside the reference, which stays in the archive and is
never copied here.

**The format is NumPy's `.npz`, written by hand with `zipfile`.** `np.savez_compressed` stamps the
current time into each zip entry, so two identical maps give different files and different
checksums. Here every entry carries the fixed timestamp 1980-01-01, the earliest zip allows, so
identical maps give identical bytes, and a checksum compares maps, not moments. `np.load` reads
the result as an ordinary `.npz`, with `allow_pickle=False`: every array is numeric or a fixed-width
string, so nothing in a saved file can execute on load.

**These files are mask volumes derived from the data** (`docs/06` DMP-C13). They stay under
`artifacts/`, which git ignores; nothing here uploads them, and no session reads their content.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from ocuval.eval.pipeline import CLASS_NAMES, detection_rows, measure_volume

FORMAT = "ocuval-prediction-npz-1"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
COMPRESSION_LEVEL = 6  # zlib's default, stated so a library default cannot change the bytes
SUFFIX = ".npz"


def measured_volume(
    *,
    sample_id: str,
    patient_id: str,
    vendor: str,
    prediction: np.ndarray,
    reference: np.ndarray,
    spacing_mm: Sequence[float],
    scores: Mapping[str, float],
    threshold: int,
) -> dict:
    """One volume's measurements, in the form `pipeline.evaluate` consumes.

    The evaluation and a re-measurement both call this, so "re-measuring reproduces the record"
    is a claim about the saved inputs, not about two copies of the measuring code agreeing.
    """
    seg = measure_volume(prediction, reference, spacing_mm)
    predicted_voxels = {
        r["fluid_class"]: r["voxels"] for r in seg if r["metric"] == "volume_mm3_predicted"
    }
    reference_voxels = {
        r["fluid_class"]: r["voxels"] for r in seg if r["metric"] == "volume_mm3_reference"
    }
    return {
        "sample_id": sample_id,
        "patient_id": patient_id,
        "vendor": vendor,
        "segmentation": seg,
        "detection": detection_rows(
            predicted_voxels, reference_voxels, dict(scores), threshold=threshold
        ),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def labels_sha256(labels: np.ndarray) -> str:
    """The checksum of the map's bytes, independent of how the file was compressed."""
    return hashlib.sha256(np.ascontiguousarray(labels, dtype=np.uint8).tobytes()).hexdigest()


def require_empty(folder: Path) -> None:
    """Refuse a folder that already holds anything. Creates nothing."""
    folder = Path(folder)
    if folder.exists() and any(folder.iterdir()):
        raise FileExistsError(
            f"{folder} already holds files; saved predictions are never overwritten (SRS-106)"
        )


def save_prediction(
    folder: Path,
    *,
    patient_id: str,
    sample_id: str,
    vendor: str,
    labels: np.ndarray,
    spacing_mm: Sequence[float],
    scores: Mapping[str, float],
) -> dict:
    """Write one volume's map and return its manifest entry. An existing file is an error."""
    if labels.dtype != np.uint8:
        raise TypeError(f"{patient_id}: a label map is uint8, not {labels.dtype}")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{patient_id}{SUFFIX}"
    arrays = {
        "labels": np.ascontiguousarray(labels),
        "spacing_mm": np.asarray([float(v) for v in spacing_mm], dtype=np.float64),
        "scores": np.asarray([float(scores[name]) for name in CLASS_NAMES], dtype=np.float64),
        "class_names": np.asarray(CLASS_NAMES),
        "patient_id": np.asarray(patient_id),
        "sample_id": np.asarray(sample_id),
        "vendor": np.asarray(vendor),
    }
    # Mode "x": the file must not exist, so nothing earlier is ever overwritten.
    with zipfile.ZipFile(path, "x") as archive:
        for name, array in arrays.items():
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, array, allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, buffer.getvalue(), compresslevel=COMPRESSION_LEVEL)
    return {
        "file": path.name,
        "sha256": sha256_file(path),
        "labels_sha256": labels_sha256(labels),
        "shape": list(labels.shape),
        "dtype": "uint8",
    }


def load_prediction(path: Path) -> dict:
    with np.load(Path(path), allow_pickle=False) as saved:
        names = tuple(str(n) for n in saved["class_names"])
        if names != tuple(CLASS_NAMES):
            raise ValueError(f"{path}: classes {names}, expected {tuple(CLASS_NAMES)}")
        return {
            "labels": saved["labels"],
            "spacing_mm": tuple(float(v) for v in saved["spacing_mm"]),
            "scores": {n: float(v) for n, v in zip(names, saved["scores"], strict=True)},
            "patient_id": str(saved["patient_id"]),
            "sample_id": str(saved["sample_id"]),
            "vendor": str(saved["vendor"]),
        }


def remeasure(path: Path, reference: np.ndarray, threshold: int) -> dict:
    """A saved map measured again against its reference, through the evaluation's own function.

    For a sealed bucket, reading `reference` is an access of that bucket (SRS-088): the caller
    goes through the gate. Nothing here reads a reference itself.
    """
    saved = load_prediction(path)
    return measured_volume(
        sample_id=saved["sample_id"],
        patient_id=saved["patient_id"],
        vendor=saved["vendor"],
        prediction=saved["labels"],
        reference=reference,
        spacing_mm=saved["spacing_mm"],
        scores=saved["scores"],
        threshold=threshold,
    )


def manifest(entries: Mapping[str, dict]) -> dict:
    """The block an evaluation record carries under `predictions`."""
    return {"format": FORMAT, "files": dict(entries)}


def manifest_problems(block: dict, folder: Path, per_volume: Sequence[dict]) -> list[str]:
    """Every way the saved files fail to match the record. Empty means they match."""
    folder = Path(folder)
    files = block.get("files", {})
    problems = []
    if block.get("format") != FORMAT:
        problems.append(f"format {block.get('format')!r}, expected {FORMAT!r}")
    measured = {row["patient_id"] for row in per_volume}
    for pid in sorted(measured - set(files)):
        problems.append(f"{pid}: measured but has no saved map")
    for pid in sorted(set(files) - measured):
        problems.append(f"{pid}: has a saved map but no per-volume rows")
    for pid, entry in sorted(files.items()):
        path = folder / entry["file"]
        if not path.is_file():
            problems.append(f"{pid}: {path} is missing")
        elif sha256_file(path) != entry["sha256"]:
            problems.append(f"{pid}: {path} does not match its SHA-256")
    listed = {entry["file"] for entry in files.values()}
    if folder.is_dir():
        for path in sorted(folder.iterdir()):
            if path.name not in listed:
                problems.append(f"{path.name}: in {folder} but not in the manifest")
    return problems


__all__ = [
    "FORMAT",
    "labels_sha256",
    "load_prediction",
    "manifest",
    "manifest_problems",
    "measured_volume",
    "remeasure",
    "require_empty",
    "save_prediction",
    "sha256_file",
]
