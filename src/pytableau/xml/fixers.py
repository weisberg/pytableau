"""Auto-fixer engine for Tableau workbooks — #76."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


class FixAction(NamedTuple):
    fixer_name: str
    path: str
    old_value: str
    new_value: str


class AutoFixer(ABC):
    """Abstract base class for auto-fixers."""

    @abstractmethod
    def fix(self, workbook: Workbook, *, dry_run: bool = False) -> list[FixAction]:
        """Apply fixes to *workbook* (or plan them if *dry_run*).

        Returns a list of :class:`FixAction` describing each change.
        """
        ...


class BracketFormatter(AutoFixer):
    """Ensure field references in formulas are bracketed."""

    # Match identifiers that look like unbracketed field names
    _UNBR = re.compile(r'(?<!\[)\b([A-Z][A-Za-z0-9_ ]{2,})\b(?!\])')
    _FUNCTIONS = frozenset({
        "SUM", "AVG", "MIN", "MAX", "COUNT", "COUNTD", "IF", "THEN", "ELSE",
        "ELSEIF", "END", "AND", "OR", "NOT", "FIXED", "INCLUDE", "EXCLUDE",
        "ATTR", "YEAR", "MONTH", "DAY", "NOW", "TODAY", "IIF", "ISNULL",
        "STR", "INT", "FLOAT", "DATE", "DATEPART", "DATETRUNC", "DATEDIFF",
        "TRUE", "FALSE", "NULL", "CASE", "WHEN", "CONTAINS", "STARTSWITH",
        "ENDSWITH", "LEFT", "RIGHT", "MID", "LEN", "TRIM", "UPPER", "LOWER",
        "REPLACE", "SPLIT", "REGEXP_MATCH", "ZN", "IFNULL", "LOOKUP",
        "WINDOW_SUM", "WINDOW_AVG", "INDEX", "RANK", "RUNNING_SUM",
    })

    def fix(self, workbook: Workbook, *, dry_run: bool = False) -> list[FixAction]:
        actions = []
        all_captions = set()
        for ds in workbook.datasources:
            for f in ds.all_fields:
                all_captions.add(f.caption)

        for ds in workbook.datasources:
            for calc in ds.calculated_fields:
                formula = calc.formula or ""
                new_formula = formula
                for m in self._UNBR.finditer(formula):
                    token = m.group(1)
                    if token.upper() in self._FUNCTIONS:
                        continue
                    if token in all_captions:
                        new_formula = new_formula.replace(token, f"[{token}]", 1)
                if new_formula != formula:
                    path = f"/datasource[@name='{ds.name}']/column[@caption='{calc.caption}']"
                    actions.append(FixAction("BracketFormatter", path, formula, new_formula))
                    if not dry_run:
                        calc.formula = new_formula
        return actions


class CredentialScrubber(AutoFixer):
    """Remove credential attributes from all connections."""

    def fix(self, workbook: Workbook, *, dry_run: bool = False) -> list[FixAction]:
        from pytableau.core.datasource import _ALWAYS_SCRUB, _CREDENTIAL_ATTR_RE

        actions = []
        for ds in workbook.datasources:
            for idx, conn in enumerate(ds.connections):
                node = conn.xml_node
                to_remove = [
                    attr for attr in list(node.attrib)
                    if attr in _ALWAYS_SCRUB or _CREDENTIAL_ATTR_RE.search(attr)
                ]
                for attr in to_remove:
                    old_val = node.attrib[attr]
                    path = f"/datasource[@name='{ds.name}']/connection[{idx}]/@{attr}"
                    actions.append(FixAction("CredentialScrubber", path, old_val, ""))
                    if not dry_run:
                        del node.attrib[attr]
        return actions


class WhitespaceNormalizer(AutoFixer):
    """Normalize excess whitespace in calculated field formulas."""

    _MULTI_SPACE = re.compile(r"[ \t]{2,}")

    def fix(self, workbook: Workbook, *, dry_run: bool = False) -> list[FixAction]:
        actions = []
        for ds in workbook.datasources:
            for calc in ds.calculated_fields:
                formula = calc.formula or ""
                normalized = self._MULTI_SPACE.sub(" ", formula).strip()
                if normalized != formula:
                    path = f"/datasource[@name='{ds.name}']/column[@caption='{calc.caption}']"
                    actions.append(FixAction("WhitespaceNormalizer", path, formula, normalized))
                    if not dry_run:
                        calc.formula = normalized
        return actions


_ALL_FIXERS: list[AutoFixer] = [
    BracketFormatter(),
    CredentialScrubber(),
    WhitespaceNormalizer(),
]
