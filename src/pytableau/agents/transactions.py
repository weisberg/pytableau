"""Atomic multi-step workbook mutations with XML rollback.

A :class:`WorkbookTransaction` captures a deep copy of the workbook's XML
tree on entry and restores it if any exception propagates through the ``with``
block, leaving the workbook completely unchanged.

Example::

    with wb.transaction() as tx:
        tx.swap_connection("Sales Data", server="prod-db.corp.com")
        tx.rename_field("Sales Data", "Rev", "Revenue")
        tx.add_calculated_field("Sales Data", "Margin", "[Revenue] - [Cost]")
    # All three mutations succeed or the workbook is rolled back to its prior state.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


class WorkbookTransaction:
    """Context manager that provides atomic multi-step workbook mutations.

    Obtain an instance via :meth:`~pytableau.core.workbook.Workbook.transaction`::

        with wb.transaction() as tx:
            tx.rename_field("My DS", "old", "new")
            tx.add_calculated_field("My DS", "Ratio", "[A] / [B]")
    """

    def __init__(self, workbook: Workbook) -> None:
        self._workbook = workbook
        self._snapshot = None

    def __enter__(self) -> WorkbookTransaction:
        from lxml import etree

        root_copy = copy.deepcopy(self._workbook.xml_root)
        self._snapshot = etree.ElementTree(root_copy)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        if exc_type is not None and self._snapshot is not None:
            # Rollback to the snapshot taken on __enter__
            self._workbook._load_tree(self._snapshot)  # type: ignore[attr-defined]
        return False  # do not suppress the exception

    # ------------------------------------------------------------------
    # Delegation helpers — keep parity with common Datasource mutations
    # ------------------------------------------------------------------

    def _ds(self, datasource_name: str):  # type: ignore[return]
        """Resolve datasource by name (raises DatasourceNotFoundError on miss)."""
        return self._workbook.datasources[datasource_name]

    def swap_connection(self, datasource_name: str, **kwargs: str | int | None) -> None:
        """Swap the connection attributes of *datasource_name*.

        Keyword arguments are forwarded directly to
        :meth:`~pytableau.core.datasource.Datasource.swap_connection`.
        """
        self._ds(datasource_name).swap_connection(**kwargs)

    def rename_field(self, datasource_name: str, old_caption: str, new_caption: str) -> None:
        """Rename a field inside *datasource_name*."""
        self._ds(datasource_name).rename_field(old_caption, new_caption)

    def add_calculated_field(
        self,
        datasource_name: str,
        caption: str,
        formula: str,
        **kwargs: object,
    ) -> None:
        """Add a calculated field to *datasource_name*."""
        self._ds(datasource_name).add_calculated_field(caption, formula, **kwargs)

    def remove_field(self, datasource_name: str, name: str) -> None:
        """Remove a field from *datasource_name*."""
        self._ds(datasource_name).remove_field(name)
