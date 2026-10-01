"""Generate requirements.lock from the working environment, with platform markers.

Generated on Windows. Two classes of package cannot simply be frozen:

  * torch 2.3.1+cu121 does not exist on PyPI. The lock records `torch==2.3.1`, the
    version; the build variant is recorded separately in the header and in every run's
    run.json, because it is a property of how torch was installed rather than of which
    torch was installed.
  * mkl, intel-openmp, tbb and colorama are required by their parents only on Windows,
    and torch pulls eleven nvidia-*-cu12 packages on Linux that are absent here. Markers
    keep the Windows set from being installed on Linux; the Linux CUDA set is NOT added
    here, because this machine has never resolved it and writing versions it has not
    installed would be asserting something unverified.
"""

import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path(r"C:\Users\rites_ljry4pu\Documents\Projects\ocuval")

# Verified from installed metadata, not assumed: each is required by its parent only
# under a Windows marker. See the dependency-marker scan in docs/13, 2026-09-28.
WINDOWS_ONLY = {"mkl", "intel-openmp", "tbb", "colorama"}

# The mirror problem, and the harder half: packages that are NOT installed here but ARE
# installed on Linux, so `pip freeze` on this machine cannot see them. They must be carried
# explicitly or every regeneration silently drops them, which is how CI came to install a
# package the lock did not record (docs/13, 2026-10-01).
#
# Versions are taken from the CI install log, because this machine cannot resolve them --
# and that is stated rather than hidden, since it is the one part of this file that is not
# a reading of the local environment. Each needs re-checking when its parent pin moves.
NOT_ON_WINDOWS = {
    # fastapi 0.111.1 -> fastapi-cli[standard] -> uvicorn[standard] -> uvloop.
    # No Windows wheel exists, so pip skips it here.
    "uvloop": ("0.22.1", 'sys_platform != "win32"'),
}

TORCH_BUILD = "2.3.1+cu121"

frozen = subprocess.run(
    [sys.executable, "-m", "pip", "freeze", "--exclude-editable"],
    capture_output=True,
    text=True,
    check=True,
).stdout.splitlines()

entries = []
for line in sorted(frozen, key=str.lower):
    line = line.strip()
    if not line or line.startswith("-") or " @ " in line:
        continue
    name = line.split("==")[0].strip()
    if name.lower() == "torch":
        entries.append("torch==2.3.1")
        continue
    if name.lower() in WINDOWS_ONLY:
        entries.append(f'{line} ; platform_system == "Windows"')
        continue
    entries.append(line)

# Added after the freeze, since `pip freeze` here cannot see them, then the whole list is
# re-sorted so the file stays in one order regardless of where an entry came from.
for name, (version, marker) in NOT_ON_WINDOWS.items():
    if name.lower() not in {e.split("==")[0].strip().lower() for e in entries}:
        entries.append(f"{name}=={version} ; {marker}")
entries.sort(key=str.lower)

header = f"""# requirements.lock - the exact environment, for NFR-002.
#
# Generated {date.today().isoformat()} on Windows from the virtual environment that
# produces this project's training results. Regenerate with scripts/make_lock.py.
#
# WHY THIS EXISTS. pyproject.toml pins direct dependencies only; every transitive
# dependency floated, so this workstation and a CI install could differ without either
# changing. They already had: CI installed with dependencies while this venv had been
# built with --no-deps and was missing six of fourteen runtime pins (docs/13,
# 2026-09-28).
#
# TORCH IS RECORDED AS A VERSION, NOT A BUILD. The installed build is {TORCH_BUILD},
# which does not exist on PyPI and cannot be expressed here. The lock therefore pins
# torch==2.3.1 and the build variant is recorded separately: in SOUP-004 section 4.1, in
# the README install steps, and in every training run's run.json. A machine that
# installs torch==2.3.1 from PyPI gets the CPU build and satisfies this lock; that is a
# real limitation of the lock and is the reason the build is recorded per run.
#
# PLATFORM MARKERS. Entries marked platform_system == "Windows" are required by their
# parents only on Windows - verified from installed metadata, not assumed. On Linux,
# torch additionally requires eleven nvidia-*-cu12 packages that are absent here. They
# are deliberately NOT listed: this machine has never resolved them, and writing
# versions it has not installed would be recording something unverified. CI resolves
# them from torch's own metadata, which pins them exactly.
#
# SCOPE. This file is the environment that produced the results. It is not a claim that
# a Linux install will be byte-identical to it; it cannot be, because the accelerator
# differs.
"""

(REPO / "requirements.lock").write_text(header + "\n".join(entries) + "\n", encoding="utf-8")
print(f"requirements.lock written with {len(entries)} entries")
print("windows-marked:", sorted(WINDOWS_ONLY))
