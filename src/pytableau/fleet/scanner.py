"""Fleet scanner — bulk analysis of a directory of Tableau workbooks."""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pytableau.fleet.report import FleetReport


@dataclass
class WorkbookScan:
    """Result of scanning a single workbook."""

    path: Path
    status: str  # "ok" | "error"
    error: str | None = None
    version: str | None = None
    complexity_grade: str | None = None
    complexity_score: int = 0
    datasource_count: int = 0
    worksheet_count: int = 0
    dashboard_count: int = 0
    field_count: int = 0
    calc_field_count: int = 0
    connection_types: list[str] = field(default_factory=list)
    has_deprecated_functions: bool = False
    has_live_connections: bool = False
    has_extract: bool = False
    unused_field_count: int = 0
    custom_sql_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "status": self.status,
            "error": self.error,
            "version": self.version,
            "complexity_grade": self.complexity_grade,
            "complexity_score": self.complexity_score,
            "datasource_count": self.datasource_count,
            "worksheet_count": self.worksheet_count,
            "dashboard_count": self.dashboard_count,
            "field_count": self.field_count,
            "calc_field_count": self.calc_field_count,
            "connection_types": self.connection_types,
            "has_deprecated_functions": self.has_deprecated_functions,
            "has_live_connections": self.has_live_connections,
            "has_extract": self.has_extract,
            "unused_field_count": self.unused_field_count,
            "custom_sql_count": self.custom_sql_count,
        }


def _scan_one(path: Path) -> WorkbookScan:
    """Open and analyse a single workbook, returning a WorkbookScan."""
    try:
        from pytableau.calculations.linter import lint_workbook
        from pytableau.core.workbook import Workbook
        from pytableau.inspect.catalog import WorkbookCatalog
        from pytableau.inspect.complexity import analyze_complexity

        wb = Workbook.open(path)
        complexity = analyze_complexity(wb)
        catalog = WorkbookCatalog(wb)

        connection_types: list[str] = []
        has_live = False
        has_extract = False
        for ds in wb.datasources:
            if ds.is_parameters:
                continue
            for conn in ds.connections:
                ct = conn.class_ or "unknown"
                if ct not in connection_types:
                    connection_types.append(ct)
                if ct == "hyper":
                    has_extract = True
                else:
                    has_live = True

        field_count = sum(len(ds.all_fields) for ds in wb.datasources if not ds.is_parameters)
        calc_count = sum(len(ds.calculated_fields) for ds in wb.datasources if not ds.is_parameters)

        lint_issues = lint_workbook(wb)
        has_deprecated = any("deprecated" in (i.message or "").lower() for i in lint_issues)

        try:
            unused = catalog.unused_fields()
        except Exception:
            unused = []

        try:
            custom_sql = catalog.custom_sql_audit()
        except Exception:
            custom_sql = []

        return WorkbookScan(
            path=path,
            status="ok",
            version=wb.version,
            complexity_grade=complexity.grade,
            complexity_score=complexity.total_score,
            datasource_count=sum(1 for ds in wb.datasources if not ds.is_parameters),
            worksheet_count=len(wb.worksheets),
            dashboard_count=len(wb.dashboards),
            field_count=field_count,
            calc_field_count=calc_count,
            connection_types=connection_types,
            has_deprecated_functions=has_deprecated,
            has_live_connections=has_live,
            has_extract=has_extract,
            unused_field_count=len(unused),
            custom_sql_count=len(custom_sql),
        )
    except Exception as exc:
        return WorkbookScan(
            path=path,
            status="error",
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}",
        )


class FleetScanner:
    """Scan a directory of Tableau workbooks and collect health metrics.

    Example::

        scanner = FleetScanner("./workbooks/")
        scanner.scan()
        print(scanner.summary())
        scanner.report().to_html("fleet_health.html")
    """

    def __init__(self, directory: str | Path, *, pattern: str = "**/*.tw[bx]") -> None:
        self._directory = Path(directory)
        self._pattern = pattern
        self._scans: list[WorkbookScan] = []

    def scan(self) -> FleetScanner:
        """Scan all matching workbooks.  Returns ``self`` for chaining."""
        paths = sorted(self._directory.glob(self._pattern))
        self._scans = [_scan_one(p) for p in paths]
        return self

    def scans(self) -> list[WorkbookScan]:
        """Return the list of :class:`WorkbookScan` results."""
        return list(self._scans)

    def summary(self) -> dict[str, Any]:
        """Return a summary dict of fleet health metrics."""
        ok = [s for s in self._scans if s.status == "ok"]
        grades: dict[str, int] = {}
        for s in ok:
            g = s.complexity_grade or "?"
            grades[g] = grades.get(g, 0) + 1

        conn_types: dict[str, int] = {}
        for s in ok:
            for ct in s.connection_types:
                conn_types[ct] = conn_types.get(ct, 0) + 1

        return {
            "total": len(self._scans),
            "ok": len(ok),
            "errors": len(self._scans) - len(ok),
            "complexity_distribution": grades,
            "connection_types": conn_types,
            "workbooks_with_live_connections": sum(1 for s in ok if s.has_live_connections),
            "workbooks_with_extract": sum(1 for s in ok if s.has_extract),
            "workbooks_with_deprecated_functions": sum(1 for s in ok if s.has_deprecated_functions),
            "workbooks_with_custom_sql": sum(1 for s in ok if s.custom_sql_count > 0),
            "total_fields": sum(s.field_count for s in ok),
            "total_calc_fields": sum(s.calc_field_count for s in ok),
            "total_unused_fields": sum(s.unused_field_count for s in ok),
        }

    def report(self) -> FleetReport:
        """Return a :class:`~pytableau.fleet.report.FleetReport` for HTML/dict output."""
        from pytableau.fleet.report import FleetReport

        return FleetReport(self._scans)
