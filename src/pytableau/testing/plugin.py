"""pytest plugin entry point for pytest-tableau."""

from __future__ import annotations

import contextlib


def pytest_configure(config) -> None:  # type: ignore[no-untyped-def]
    """Register the ``tableau_workbook`` marker."""
    config.addinivalue_line(
        "markers",
        "tableau_workbook: marks tests that use Tableau workbooks",
    )


# Re-export fixtures so pytest discovers them via the plugin entry point
with contextlib.suppress(ImportError):
    from pytableau.testing.fixtures import workbook, workbook_factory  # noqa: F401
