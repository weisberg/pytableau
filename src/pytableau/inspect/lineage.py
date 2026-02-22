"""FieldLineage: dependency graph showing which calcs use which fields.

.. note::
    Full implementation is tracked in Phase 1 of the development plan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pytableau.core.datasource import _normalise_field_name

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


_FIELD_REF_RE = re.compile(r"\[(?P<first>[^\]]+)\](?:\.\[(?P<second>[^\]]+)\])?")


@dataclass(frozen=True)
class LineageField:
    """A single dependency reference from a calculated field formula."""

    datasource: str | None
    field: str

    def as_token(self) -> str:
        if not self.datasource:
            return f"[{self.field}]"
        return f"[{self.datasource}].[{self.field}]"


@dataclass(frozen=True)
class CalculatedFieldLineage:
    """Dependency information for one calculated field."""

    datasource: str
    field: str
    formula: str
    depends_on: list[LineageField]

    @property
    def key(self) -> str:
        return f"{self.datasource}::{self.field}"


class FieldLineage:
    """Build and query calculated-field dependency graphs for a workbook."""

    def __init__(self, workbook: Workbook) -> None:
        self.workbook = workbook
        self._entries: list[CalculatedFieldLineage] = self._build()

    @staticmethod
    def _extract_dependencies(formula: str | None) -> list[LineageField]:
        if not formula:
            return []
        seen: set[tuple[str | None, str]] = set()
        out: list[LineageField] = []
        for match in _FIELD_REF_RE.finditer(formula):
            source_token = match.group("first")
            target_token = match.group("second")
            if source_token is None:
                continue

            if target_token is not None:
                datasource = _normalise_field_name(source_token)
                field_name = _normalise_field_name(target_token)
            else:
                datasource = None
                field_name = _normalise_field_name(source_token)

            key = (datasource, field_name)
            if key in seen:
                continue
            seen.add(key)
            out.append(LineageField(datasource=datasource, field=field_name))
        return out

    def _build(self) -> list[CalculatedFieldLineage]:
        entries: list[CalculatedFieldLineage] = []
        for datasource in self.workbook.datasources:
            for field in datasource.calculated_fields:
                entries.append(
                    CalculatedFieldLineage(
                        datasource=datasource.name,
                        field=field.caption,
                        formula=field.formula,
                        depends_on=self._extract_dependencies(field.formula),
                    )
                )
        return entries

    @property
    def entries(self) -> list[CalculatedFieldLineage]:
        """Return all detected calculated-field lineage entries."""
        return list(self._entries)

    def for_field(self, field: str, datasource: str | None = None) -> CalculatedFieldLineage | None:
        """Return lineage for a specific calculated field.

        If *datasource* is omitted and the field name is ambiguous, this
        returns ``None`` so callers can resolve the ambiguity explicitly.
        """
        normalized = _normalise_field_name(field)
        candidates = [
            entry
            for entry in self._entries
            if _normalise_field_name(entry.field) == normalized
            and (datasource is None or entry.datasource == datasource)
        ]
        return candidates[0] if len(candidates) == 1 else None

    def to_dict(self) -> dict[str, list[str]]:
        """Serialize lineage to a compact dictionary representation."""
        result: dict[str, list[str]] = {}
        for entry in self._entries:
            result[entry.key] = [ref.as_token() for ref in entry.depends_on]
        return result
