"""TC-000 — the package imports and reports a version."""

from __future__ import annotations


def test_TC_000_package_imports():
    import ocuval

    assert ocuval.__version__
