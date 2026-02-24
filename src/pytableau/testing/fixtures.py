"""pytest fixtures for Tableau workbook testing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    import pytest

    @pytest.fixture
    def workbook_factory() -> Callable[[Any], Any]:
        """Fixture that returns a factory function for opening workbooks.

        Usage::

            def test_something(workbook_factory):
                wb = workbook_factory("path/to/workbook.twb")
                assert wb.version
        """

        def _factory(path: Any) -> Any:
            from pytableau.core.workbook import Workbook

            return Workbook.open(path)

        return _factory

    @pytest.fixture
    def workbook(request: Any) -> Any:
        """Parametrised fixture that opens a workbook from ``request.param``.

        Usage::

            @pytest.mark.parametrize("workbook", ["sales.twb"], indirect=True)
            def test_something(workbook):
                assert workbook.version
        """
        from pytableau.core.workbook import Workbook

        return Workbook.open(request.param)

except ImportError:
    pass
