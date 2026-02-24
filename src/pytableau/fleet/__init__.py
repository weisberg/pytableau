"""Fleet-scale Tableau workbook operations.

Scan, migrate, validate compliance, and report across hundreds of workbooks in one pass.

Example::

    from pytableau.fleet import FleetScanner

    scanner = FleetScanner("./all_workbooks/")
    scanner.scan()
    report = scanner.report()
    report.to_html("fleet_health.html")
    print(report.summary())
"""

from __future__ import annotations

from pytableau.fleet.compliance import ComplianceRunner, load_compliance_config
from pytableau.fleet.contracts import ContractRunner
from pytableau.fleet.migrator import MigrationEngine, MigrationPlan
from pytableau.fleet.report import FleetReport
from pytableau.fleet.scanner import FleetScanner, WorkbookScan

__all__ = [
    "FleetScanner",
    "WorkbookScan",
    "MigrationPlan",
    "MigrationEngine",
    "ComplianceRunner",
    "load_compliance_config",
    "ContractRunner",
    "FleetReport",
]
