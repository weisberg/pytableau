"""Isolated XML and asset mutations with rollback.

A :class:`WorkbookTransaction` captures XML and owned assets on entry.
Workbook-managed extract handles resolve against isolated storage. Exceptions
restore the snapshot; successful changes remain staged until an explicit save.
Raw independent file/SQL handles are outside this transaction boundary.

Example::

    with wb.transaction() as tx:
        tx.swap_connection("Sales Data", server="prod-db.corp.com")
        tx.rename_field("Sales Data", "Rev", "Revenue")
        tx.add_calculated_field("Sales Data", "Margin", "[Revenue] - [Cost]")
    # All three mutations succeed or the workbook is rolled back to its prior state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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

    def __enter__(self) -> WorkbookTransaction:
        from pytableau.core.state import install, snapshot
        from pytableau.exceptions import InvalidPathError

        wb = self._workbook
        pm = wb._package_manager
        root = pm.twb_path.parent if pm else (wb._path.parent if wb._path else None)
        original_tree = wb.xml_tree
        original_sources = list(wb.datasources)
        for ds in original_sources:
            if (
                root
                and ds._hyper_path
                and not ds._hyper_path.resolve().is_relative_to(root.resolve())
            ):
                raise InvalidPathError(
                    "Transaction extract is outside the captured asset directory"
                )
        self._state = snapshot(wb)
        from pathlib import Path

        for ds in original_sources:
            if ds._hyper_path is None:
                continue
            if (
                root is None
                or ds._hyper_path.relative_to(root).as_posix() not in self._state["assets"]
            ):
                raise InvalidPathError("Transaction extract is not captured as an owned asset")
            for connection in ds.connections:
                for attr in ("filename", "dbname"):
                    value = connection.xml_node.get(attr)
                    if value and Path(value).is_absolute():
                        raise InvalidPathError("Transactions require relative extract references")
        install(wb, self._state)
        # Keep existing field/datasource handles attached to the same XML nodes,
        # while redirecting their data writes into isolated package storage.
        wb._load_tree(original_tree)
        for ds in original_sources:
            fresh = wb.datasources.get(ds.name)
            if fresh is not None:
                ds._set_hyper_path(fresh._hyper_path)
        wb._transaction_depth += 1
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self._workbook._transaction_depth -= 1
        if exc_type is not None:
            from pytableau.core.state import install

            install(self._workbook, self._state, restore_tombstones=True)

    # ------------------------------------------------------------------
    # Delegation helpers — keep parity with common Datasource mutations
    # ------------------------------------------------------------------

    def _ds(self, datasource_name: str) -> Any:
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
