"""The installed environment must match requirements.lock (TC-099, NFR-002).

**Why a lock at all.** `pyproject.toml` pins direct dependencies only. Every transitive
dependency floated, so this workstation and a CI install could differ without either
repository changing -- and they already had: CI installed with dependencies while this
venv had been built with `--no-deps` and was missing six of fourteen runtime pins. A
result is only reproducible from the committed configuration if the environment is part
of what is committed.

**Why torch is a special case and not an exception.** The installed build is
`2.3.1+cu121`, which does not exist on PyPI and cannot be written in a lock that a Linux
CI must install from. The lock therefore pins the *version*, `torch==2.3.1`, and the
*build* is recorded separately -- in SOUP-004 §4.1, in the README, and in every training
run's `run.json`. This test treats a differing local build label as a **recorded
variant** rather than a mismatch, and asserts that the variant is recorded rather than
merely tolerated.
"""

from __future__ import annotations

import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK = REPO_ROOT / "requirements.lock"

# Distribution names whose import name differs, or which pip reports under a
# normalised spelling. Compared case-insensitively with '-' and '_' folded.
ENTRY = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)==(?P<version>[^;\s]+)\s*(?:;\s*(?P<marker>.+))?$")


def normalise(name: str) -> str:
    return name.lower().replace("_", "-")


def marker_applies(marker: str | None) -> bool:
    """Evaluate the entry's environment marker for this interpreter."""
    if not marker:
        return True
    from packaging.markers import Marker

    return Marker(marker).evaluate()


def lock_entries() -> list[tuple[str, str, str | None]]:
    assert LOCK.is_file(), f"{LOCK} is missing; generate it with scripts/make_lock.py"
    out = []
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = ENTRY.match(line)
        assert match, f"unparsable lock entry: {line!r}"
        out.append((match["name"], match["version"], match["marker"]))
    return out


def applicable_entries():
    return [(n, v) for n, v, m in lock_entries() if marker_applies(m)]


# --- the lock itself --------------------------------------------------------------


def test_TC_099_lock_exists_and_is_not_trivial():
    """Guards the guard: an empty lock would satisfy every comparison below."""
    entries = lock_entries()
    assert len(entries) >= 40, f"lock has only {len(entries)} entries"
    names = {normalise(n) for n, _, _ in entries}
    for required in ("torch", "monai", "numpy", "pydicom", "highdicom", "pytest"):
        assert required in names, f"{required} missing from the lock"


def test_TC_099_torch_is_locked_without_a_local_build_label():
    """A '+cu121' in the lock would make it uninstallable on any machine but this one."""
    locked = {normalise(n): v for n, v, _ in lock_entries()}
    assert "+" not in locked["torch"], (
        f"lock pins torch=={locked['torch']}, which carries a local build label. That "
        f"build does not exist on PyPI, so a Linux CI could not install from this lock."
    )


def test_TC_099_windows_only_entries_carry_a_marker():
    """Without markers these would be attempted on Linux, where their parents do not
    require them."""
    marked = {normalise(n): m for n, _, m in lock_entries() if m}
    for name in ("mkl", "intel-openmp", "tbb", "colorama"):
        assert name in marked, f"{name} is Windows-only and needs a platform marker"
        assert "Windows" in marked[name]


# --- the environment against the lock ------------------------------------------------


def test_TC_099_installed_environment_matches_the_lock():
    """Every applicable locked entry is installed at the locked version.

    torch is compared on its base version: the local build label is a recorded variant,
    checked separately below.
    """
    mismatches, missing = [], []
    for name, locked in applicable_entries():
        try:
            installed = version(name)
        except PackageNotFoundError:
            missing.append(f"{name}=={locked}")
            continue
        base = installed.split("+")[0]
        if base != locked:
            mismatches.append(f"{name}: locked {locked}, installed {installed}")

    assert not missing, (
        f"{len(missing)} locked package(s) are not installed: {missing[:6]}. The "
        f"environment does not match requirements.lock, so a result produced here is "
        f"not reproducible from the committed environment (NFR-002)."
    )
    assert not mismatches, f"{len(mismatches)} version mismatch(es): {mismatches[:6]}"


def test_TC_099_nothing_installed_is_absent_from_the_lock():
    """Drift in the other direction: a package present here and unlocked would travel
    into a result without being recorded."""
    import subprocess

    frozen = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--exclude-editable"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    locked = {normalise(n) for n, _, _ in lock_entries()}
    extra = sorted(
        normalise(line.split("==")[0])
        for line in frozen
        if "==" in line and normalise(line.split("==")[0]) not in locked
    )
    assert not extra, (
        f"installed but not in requirements.lock: {extra}. Regenerate with "
        f"scripts/make_lock.py, or the environment has drifted from the record."
    )


# --- the torch build variant ----------------------------------------------------------


def test_TC_099_the_torch_build_variant_is_recorded_not_merely_tolerated():
    """If the local build differs from the lock, the difference must be written down.

    This is what keeps 'the lock pins the version' from becoming 'the build is
    unspecified'.
    """
    import torch

    installed = torch.__version__
    if "+" not in installed:
        pytest.skip(f"no local build label on torch=={installed}; nothing to record")

    soup = (REPO_ROOT / "docs" / "04_soup_list.md").read_text(encoding="utf-8")
    assert installed in soup, (
        f"torch build {installed} is installed but is not recorded in docs/04. The lock "
        f"deliberately omits the build label, so docs/04 §4.1 is where it is stated; an "
        f"unrecorded build makes the environment unreproducible in the one respect the "
        f"lock cannot capture."
    )


def test_TC_099_readme_documents_how_to_install_the_cuda_build():
    """The lock cannot express it, so the instructions have to."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "cu121" in readme, "README does not say how to obtain the CUDA torch build"
    assert "requirements.lock" in readme, "README does not mention the lock file"
