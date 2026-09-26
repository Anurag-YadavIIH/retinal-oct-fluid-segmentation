"""Accelerator telemetry sampled for the duration of a run.

Traces to: SRS-082
Verifies: TC-095

**Why a run needs this and a benchmark does not.** The throughput figures in `docs/13`
were measured over seconds on a cold, idle GPU. A fold runs for hours on a laptop, where
the same card will heat up, drop its clocks and deliver less. Without a record there is
no way to tell a slow epoch caused by thermal throttling from one caused by anything
else, and no way to know whether two folds ran under comparable conditions -- which
NFR-002 needs, because a cross-vendor comparison between folds trained under different
thermal regimes is comparing more than the vendors.

It is also the execution-environment record `docs/08` has to report. Collecting it
during the run is the only time it can be collected.

**Failure is never fatal.** If `nvidia-smi` is missing, slow or fails, the sampler
records the failure and keeps going. Telemetry is evidence about a run, not part of it;
aborting hours of training because a monitoring subprocess failed would be the tail
wagging the dog.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

TELEMETRY_NAME = "gpu_telemetry.csv"

# Queried in this order; the CSV columns follow it.
FIELDS = (
    "timestamp",
    "name",
    "temperature.gpu",
    "clocks.current.graphics",
    "clocks.current.sm",
    "utilization.gpu",
    "utilization.memory",
    "memory.used",
    "memory.total",
    "power.draw",
)
_QUERY = ",".join(f for f in FIELDS if f != "timestamp")

COLUMNS = ("timestamp_utc", "elapsed_s", *[f for f in FIELDS if f != "timestamp"], "error")


def nvidia_smi_available() -> bool:
    return shutil.which("nvidia-smi") is not None


def sample_once(timeout: float = 10.0) -> tuple[list[str], str | None]:
    """One `nvidia-smi` reading, or an explanation of why there is none."""
    if not nvidia_smi_available():
        return [], "nvidia-smi not on PATH"
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={_QUERY}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return [], f"{type(error).__name__}: {error}"
    if result.returncode != 0:
        return [], f"nvidia-smi exited {result.returncode}: {result.stderr.strip()[:120]}"
    line = result.stdout.strip().splitlines()
    if not line:
        return [], "nvidia-smi returned no rows"
    # First GPU only. This project targets one device and averaging across several
    # would hide exactly the per-card thermal behaviour the log exists to show.
    return [value.strip() for value in line[0].split(",")], None


class GpuTelemetry:
    """Appends a reading to `gpu_telemetry.csv` every `interval` seconds.

    A daemon thread rather than a subprocess: it must not outlive the run, and a
    background process surviving a crashed training run would keep writing to a
    directory nobody is watching.

    Appends rather than rewrites, for the same reason the per-epoch log does (SRS-081):
    a run resumed on a second evening is the same run, and its telemetry should be one
    record.
    """

    def __init__(self, run_dir: Path, interval: float = 30.0, name: str = TELEMETRY_NAME):
        self.path = Path(run_dir) / name
        self.interval = float(interval)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.samples = 0
        self.errors = 0

    def _write_header_if_new(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(COLUMNS)

    def write_sample(self, started: float) -> None:
        values, error = sample_once()
        row = [
            datetime.now(UTC).isoformat(timespec="seconds"),
            round(time.time() - started, 1),
            *(values if values else [""] * (len(COLUMNS) - 3)),
            error or "",
        ]
        # Pad or trim so a malformed nvidia-smi reply cannot corrupt the column layout.
        row = row[: len(COLUMNS)] + [""] * (len(COLUMNS) - len(row))
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(row)
        self.samples += 1
        if error:
            self.errors += 1

    def _loop(self, started: float) -> None:
        while not self._stop.is_set():
            try:
                self.write_sample(started)
            except Exception:  # noqa: BLE001 - telemetry must never end a run
                self.errors += 1
            self._stop.wait(self.interval)

    def start(self) -> GpuTelemetry:
        self._write_header_if_new()
        started = time.time()
        self.write_sample(started)  # one reading immediately, so a short run is not empty
        self._thread = threading.Thread(target=self._loop, args=(started,), daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 5)
            self._thread = None

    def __enter__(self) -> GpuTelemetry:
        return self.start()

    def __exit__(self, *exc_info) -> None:
        self.stop()
