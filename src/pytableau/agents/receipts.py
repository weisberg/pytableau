"""Structured operation receipts for pytableau mutations.

Every workbook mutation can return an :class:`OperationReceipt` that describes
what happened — whether a field was created, already existed, or was updated —
along with an optional corrective hint when something went wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OperationReceipt:
    """Result of a single workbook mutation operation.

    Attributes:
        status: One of ``"created"``, ``"already_exists"``, ``"updated"``,
            ``"removed"``, or ``"skipped"``.
        field_name: Caption of the affected field, if applicable.
        datasource: Name of the affected datasource, if applicable.
        suggestion: A corrective hint when an operation encounters an error,
            e.g. ``"Did you mean 'Revenue'?"``
    """

    status: str
    field_name: str = ""
    datasource: str = ""
    suggestion: str | None = field(default=None)

    @property
    def ok(self) -> bool:
        """Return ``True`` if the operation succeeded (created, updated, or removed)."""
        return self.status in ("created", "updated", "removed")

    def __str__(self) -> str:
        parts = [f"[{self.status}]"]
        if self.field_name:
            parts.append(self.field_name)
        if self.datasource:
            parts.append(f"in '{self.datasource}'")
        if self.suggestion:
            parts.append(f"(hint: {self.suggestion})")
        return " ".join(parts)
