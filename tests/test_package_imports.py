"""Every module under src/ocuval must import (TC-098).

**Why this exists.** On 2026-09-28 the suite passed 403 tests while
`ocuval.service.api` and `ocuval.service.schemas` could not be imported at all --
`fastapi` and `pydantic` were absent from the virtual environment. Nothing noticed,
because there are no service tests, and a module no test imports is a module the suite
is silent about. A green run was therefore compatible with two broken modules.

That is `docs/07` §3 rule 8 again: the observable output -- a passing suite -- was
identical whether those modules were importable or not. The mechanism here is the walk
itself; it cannot be satisfied by testing something else.

Deliberately imports rather than merely parses. A syntax check would pass on a module
whose *dependency* is missing, which is exactly the failure that occurred.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import ocuval


def module_names() -> list[str]:
    return sorted(
        info.name for info in pkgutil.walk_packages(ocuval.__path__, prefix=f"{ocuval.__name__}.")
    )


def test_TC_098_the_walk_finds_the_packages_it_should():
    """Guards the guard: a walk that found nothing would pass vacuously."""
    names = module_names()
    assert len(names) >= 10, f"expected the whole package, found {names}"
    for expected in (
        "ocuval.data.splits",
        "ocuval.io.retouch_reader",
        "ocuval.models.seg_unet",
        "ocuval.training.loop",
        "ocuval.service.api",
        "ocuval.service.schemas",
    ):
        assert expected in names, f"{expected} was not discovered by the walk"


@pytest.mark.parametrize("name", module_names())
def test_TC_098_module_imports(name: str):
    try:
        importlib.import_module(name)
    except ImportError as error:
        pytest.fail(
            f"{name} cannot be imported: {error}. A module no test imports is a module "
            f"the suite is silent about, so a green run does not cover it. If the cause "
            f"is a missing dependency, the environment does not match pyproject.toml."
        )
