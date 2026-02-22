"""Read-only analysis and reporting for Tableau workbooks.

The inspect subpackage provides non-destructive tools for cataloguing,
documenting, and diffing workbooks.
"""

from __future__ import annotations

from pytableau.inspect.catalog import WorkbookCatalog
from pytableau.inspect.lineage import CalculatedFieldLineage, FieldLineage, LineageField
from pytableau.inspect.report import WorkbookReport

__all__ = [
    "WorkbookCatalog",
    "FieldLineage",
    "CalculatedFieldLineage",
    "LineageField",
    "WorkbookReport",
]
