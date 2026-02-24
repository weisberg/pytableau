"""M3 Fleet Operations — 32 tests covering FleetScanner, MigrationPlan/Engine,
ComplianceRunner, ContractRunner, and FleetReport."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from pytableau.fleet import (
    ComplianceRunner,
    ContractRunner,
    FleetReport,
    FleetScanner,
    MigrationEngine,
    MigrationPlan,
    WorkbookScan,
)

FIXTURES = Path("tests/fixtures")
MINIMAL = FIXTURES / "minimal_v2022_4.twb"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tmp_workbook_dir():
    """Return a temp dir with a copy of the minimal fixture."""
    d = tempfile.mkdtemp()
    shutil.copy(MINIMAL, Path(d) / MINIMAL.name)
    return Path(d)


# ---------------------------------------------------------------------------
# 1. WorkbookScan dataclass
# ---------------------------------------------------------------------------


class TestWorkbookScan:
    def test_to_dict_has_required_keys(self):
        scan = WorkbookScan(path=MINIMAL, status="ok")
        d = scan.to_dict()
        for key in ("path", "status", "complexity_grade", "field_count", "connection_types"):
            assert key in d

    def test_error_scan_has_error_field(self):
        scan = WorkbookScan(path=MINIMAL, status="error", error="boom")
        assert scan.error == "boom"

    def test_default_connection_types_is_empty_list(self):
        scan = WorkbookScan(path=MINIMAL, status="ok")
        assert scan.connection_types == []


# ---------------------------------------------------------------------------
# 2. FleetScanner
# ---------------------------------------------------------------------------


class TestFleetScanner:
    def test_scan_returns_self(self):
        scanner = FleetScanner(FIXTURES)
        result = scanner.scan()
        assert result is scanner

    def test_scans_returns_list(self):
        scanner = FleetScanner(FIXTURES).scan()
        scans = scanner.scans()
        assert isinstance(scans, list)
        assert len(scans) >= 1

    def test_ok_workbook_has_grade(self):
        scanner = FleetScanner(FIXTURES, pattern="minimal_v2022_4.twb").scan()
        ok = [s for s in scanner.scans() if s.status == "ok"]
        assert len(ok) >= 1
        assert ok[0].complexity_grade in ("A", "B", "C", "D", "F")

    def test_summary_has_required_keys(self):
        scanner = FleetScanner(FIXTURES).scan()
        s = scanner.summary()
        for key in ("total", "ok", "errors", "complexity_distribution"):
            assert key in s

    def test_summary_total_matches_scan_count(self):
        scanner = FleetScanner(FIXTURES).scan()
        assert scanner.summary()["total"] == len(scanner.scans())

    def test_error_workbook_captured(self, tmp_path):
        # Write a broken TWB
        bad = tmp_path / "broken.twb"
        bad.write_text("<not-valid-xml>", encoding="utf-8")
        scanner = FleetScanner(tmp_path, pattern="*.twb").scan()
        errors = [s for s in scanner.scans() if s.status == "error"]
        assert len(errors) == 1

    def test_empty_directory_returns_empty(self, tmp_path):
        scanner = FleetScanner(tmp_path).scan()
        assert scanner.summary()["total"] == 0

    def test_report_returns_fleet_report(self):
        scanner = FleetScanner(FIXTURES, pattern="minimal_v2022_4.twb").scan()
        report = scanner.report()
        assert isinstance(report, FleetReport)


# ---------------------------------------------------------------------------
# 3. FleetReport
# ---------------------------------------------------------------------------


class TestFleetReport:
    def test_to_dict_has_summary_and_workbooks(self):
        scanner = FleetScanner(FIXTURES, pattern="minimal_v2022_4.twb").scan()
        d = scanner.report().to_dict()
        assert "summary" in d
        assert "workbooks" in d

    def test_to_html_returns_string(self):
        scanner = FleetScanner(FIXTURES, pattern="minimal_v2022_4.twb").scan()
        html = scanner.report().to_html()
        assert "<html" in html
        assert "Fleet Health Report" in html

    def test_to_html_writes_file(self, tmp_path):
        scanner = FleetScanner(FIXTURES, pattern="minimal_v2022_4.twb").scan()
        out = tmp_path / "report.html"
        scanner.report().to_html(out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_summary_method(self):
        report = FleetReport([WorkbookScan(path=MINIMAL, status="ok", complexity_grade="B")])
        s = report.summary()
        assert s["total"] == 1
        assert s["ok"] == 1
        assert "B" in s["complexity_distribution"]


# ---------------------------------------------------------------------------
# 4. MigrationPlan / MigrationEngine
# ---------------------------------------------------------------------------


class TestMigrationPlan:
    def test_fluent_builder_returns_self(self, tmp_path):
        plan = MigrationPlan().source_directory(tmp_path).output_directory(tmp_path)
        assert isinstance(plan, MigrationPlan)

    def test_swap_connections_stored(self, tmp_path):
        plan = MigrationPlan().source_directory(tmp_path).swap_connections({"old": "new"})
        assert plan._connection_swaps == {"old": "new"}

    def test_rename_fields_stored(self, tmp_path):
        plan = MigrationPlan().source_directory(tmp_path).rename_fields({"Rev": "Revenue"})
        assert plan._field_renames == {"Rev": "Revenue"}


class TestMigrationEngine:
    def test_dry_run_no_files_written(self, tmp_path):
        src = _tmp_workbook_dir()
        plan = (
            MigrationPlan()
            .source_directory(src)
            .output_directory(tmp_path)
            .swap_connections({"sqlserver": "snowflake"})
        )
        report = MigrationEngine(plan).execute(dry_run=True)
        # no files written to tmp_path
        assert not any(tmp_path.iterdir())
        assert report.dry_run is True

    def test_report_str(self, tmp_path):
        src = _tmp_workbook_dir()
        plan = MigrationPlan().source_directory(src).output_directory(tmp_path)
        report = MigrationEngine(plan).execute(dry_run=True)
        assert "scanned" in str(report)

    def test_missing_source_raises(self, tmp_path):
        plan = MigrationPlan().output_directory(tmp_path)
        with pytest.raises(ValueError, match="source_directory"):
            MigrationEngine(plan).execute()

    def test_no_matching_changes_skipped(self, tmp_path):
        src = _tmp_workbook_dir()
        plan = (
            MigrationPlan()
            .source_directory(src)
            .output_directory(tmp_path)
            .swap_connections({"nonexistent-host": "new-host"})
        )
        report = MigrationEngine(plan).execute(dry_run=True)
        skipped = [r for r in report.results if r.status == "skipped"]
        assert len(skipped) >= 1

    def test_field_rename_dry_run(self, tmp_path):
        src = _tmp_workbook_dir()
        plan = (
            MigrationPlan()
            .source_directory(src)
            .output_directory(tmp_path)
            .rename_fields({"Region": "Territory"})
        )
        report = MigrationEngine(plan).execute(dry_run=True)
        migrated = [r for r in report.results if r.status == "migrated"]
        assert len(migrated) >= 1
        assert any("Territory" in c for r in migrated for c in r.changes)

    def test_to_dict_serialisable(self, tmp_path):
        import json

        src = _tmp_workbook_dir()
        plan = MigrationPlan().source_directory(src).output_directory(tmp_path)
        report = MigrationEngine(plan).execute(dry_run=True)
        json.dumps(report.to_dict())  # must not raise


# ---------------------------------------------------------------------------
# 5. ComplianceRunner
# ---------------------------------------------------------------------------


class TestComplianceRunner:
    def test_run_returns_list(self):
        from pytableau.governance.rules import GovernanceRuleset

        rs = GovernanceRuleset.default()
        runner = ComplianceRunner(rs)
        results = runner.run(FIXTURES, pattern="minimal_v2022_4.twb")
        assert isinstance(results, list)
        assert len(results) == 1

    def test_passed_method(self):
        from pytableau.governance.rules import GovernanceRuleset

        rs = GovernanceRuleset.default()
        runner = ComplianceRunner(rs)
        results = runner.run(FIXTURES, pattern="minimal_v2022_4.twb")
        assert isinstance(runner.passed(results), bool)

    def test_to_junit_xml_returns_string(self):
        from pytableau.governance.rules import GovernanceRuleset

        rs = GovernanceRuleset.default()
        runner = ComplianceRunner(rs)
        results = runner.run(FIXTURES, pattern="minimal_v2022_4.twb")
        xml = runner.to_junit_xml(results)
        assert "<testsuite" in xml
        assert "pytableau-compliance" in xml

    def test_result_has_workbook_field(self):
        from pytableau.governance.rules import GovernanceRuleset

        rs = GovernanceRuleset.default()
        runner = ComplianceRunner(rs)
        results = runner.run(FIXTURES, pattern="minimal_v2022_4.twb")
        assert results[0].workbook != ""

    def test_empty_directory_returns_empty(self, tmp_path):
        from pytableau.governance.rules import GovernanceRuleset

        runner = ComplianceRunner(GovernanceRuleset.default())
        results = runner.run(tmp_path)
        assert results == []


# ---------------------------------------------------------------------------
# 6. ContractRunner
# ---------------------------------------------------------------------------


class TestContractRunner:
    def test_run_empty_contracts_dir(self, tmp_path):
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        runner = ContractRunner(contracts_dir)
        results = runner.run(FIXTURES)
        assert results == []

    def test_passing_contract(self, tmp_path):
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        # Write a contract that the minimal fixture satisfies
        (contracts_dir / "minimal.yml").write_text(
            "workbook: minimal_v2022_4.twb\ncontracts:\n  worksheets:\n    - name: Sheet 1\n",
            encoding="utf-8",
        )
        runner = ContractRunner(contracts_dir)
        results = runner.run(FIXTURES)
        assert len(results) == 1
        # Sheet1 exists in minimal fixture
        assert results[0].passed

    def test_failing_contract_missing_workbook(self, tmp_path):
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        (contracts_dir / "missing.yml").write_text(
            "workbook: nonexistent.twb\ncontracts: {}\n", encoding="utf-8"
        )
        runner = ContractRunner(contracts_dir)
        results = runner.run(FIXTURES)
        assert len(results) == 1
        assert not results[0].passed

    def test_to_junit_xml_returns_string(self, tmp_path):
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        runner = ContractRunner(contracts_dir)
        results = runner.run(FIXTURES)
        xml = runner.to_junit_xml(results)
        assert "<testsuite" in xml

    def test_passed_all_empty(self, tmp_path):
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        runner = ContractRunner(contracts_dir)
        results = runner.run(FIXTURES)
        assert runner.passed(results) is True
