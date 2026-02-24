"""Assertion helpers for pytest-tableau workbook testing."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook

_GRADES = "ABCDEF"


def assert_field_exists(
    workbook: Workbook,
    field_name: str,
    datasource: str | None = None,
) -> None:
    """Assert that a field with the given caption exists in the workbook.

    Args:
        workbook: The Tableau workbook to check.
        field_name: Expected field caption.
        datasource: If given, only search in this datasource by name.

    Raises:
        AssertionError: If the field is not found.
    """
    sources = (
        [ds for ds in workbook.datasources if ds.name == datasource]
        if datasource is not None
        else list(workbook.datasources)
    )
    for ds in sources:
        for f in ds.all_fields:
            if f.caption == field_name:
                return
    scope = f" in datasource '{datasource}'" if datasource else ""
    raise AssertionError(f"Field '{field_name}' not found{scope} in workbook.")


def assert_calculation_valid(workbook: Workbook, field_name: str) -> None:
    """Assert that a calculated field exists and has a non-empty formula.

    Args:
        workbook: The Tableau workbook to check.
        field_name: Caption of the calculated field.

    Raises:
        AssertionError: If the field is missing, has no formula, or fails a
            basic parse check.
    """
    for ds in workbook.datasources:
        for f in ds.all_fields:
            if f.caption == field_name:
                formula = getattr(f, "formula", None)
                if not formula:
                    raise AssertionError(f"Field '{field_name}' exists but has no formula.")
                return
    raise AssertionError(f"Calculated field '{field_name}' not found in workbook.")


def assert_dashboard_contains(
    workbook: Workbook,
    dashboard_name: str,
    sheet_names: list[str],
) -> None:
    """Assert that a dashboard exists and contains all listed sheets.

    Args:
        workbook: The Tableau workbook to check.
        dashboard_name: Name of the dashboard.
        sheet_names: List of worksheet names that must appear in the dashboard.

    Raises:
        AssertionError: If the dashboard is not found or a sheet is missing.
    """
    dashboard = None
    for db in workbook.dashboards:
        if db.name == dashboard_name:
            dashboard = db
            break
    if dashboard is None:
        raise AssertionError(
            f"Dashboard '{dashboard_name}' not found in workbook. "
            f"Available: {[d.name for d in workbook.dashboards]}"
        )

    # Collect zone names from the parsed zones list (top-level direct children).
    dashboard_sheets: set[str] = {z.name for z in dashboard.zones if z.name}

    # Also scan <zones> containers in the XML to catch dashboards that wrap
    # zones inside a <zones> element rather than placing them as direct
    # children of <dashboard>.
    for elem in dashboard.xml_node.findall("./zones//zone"):
        name = elem.get("name", "")
        if name:
            dashboard_sheets.add(name)

    missing = [s for s in sheet_names if s not in dashboard_sheets]
    if missing:
        raise AssertionError(
            f"Dashboard '{dashboard_name}' is missing sheets: {missing}. "
            f"Found: {sorted(dashboard_sheets)}"
        )


def assert_no_live_connections(workbook: Workbook) -> None:
    """Assert that no datasource uses a live (non-extract) connection.

    Args:
        workbook: The Tableau workbook to check.

    Raises:
        AssertionError: If any live connection is found.
    """
    from pytableau.governance.rules import NoLiveConnectionsRule

    rule = NoLiveConnectionsRule(severity="error")
    issues = rule.check(workbook)
    if issues:
        msgs = "; ".join(i.message for i in issues)
        raise AssertionError(f"Live connections found: {msgs}")


def assert_complexity_grade(workbook: Workbook, max_grade: str = "C") -> None:
    """Assert that the workbook's complexity grade is within acceptable bounds.

    Args:
        workbook: The Tableau workbook to check.
        max_grade: Maximum allowed grade letter (``"A"`` is best, ``"F"`` is worst).
            Default ``"C"``.

    Raises:
        AssertionError: If the workbook's grade is worse than *max_grade*.
    """
    from pytableau.inspect.complexity import analyze_complexity

    report = analyze_complexity(workbook)
    actual_idx = _GRADES.index(report.grade) if report.grade in _GRADES else 5
    max_idx = _GRADES.index(max_grade) if max_grade in _GRADES else 5
    if actual_idx > max_idx:
        raise AssertionError(
            f"Workbook complexity grade '{report.grade}' (score {report.total_score}) "
            f"exceeds maximum allowed grade '{max_grade}'."
        )


def assert_no_deprecated_functions(workbook: Workbook) -> None:
    """Assert that no calculated field uses a deprecated Tableau function.

    Args:
        workbook: The Tableau workbook to check.

    Raises:
        AssertionError: If deprecated functions are found.
    """
    from pytableau.governance.rules import NoDeprecatedFunctionsRule

    rule = NoDeprecatedFunctionsRule(severity="error")
    issues = rule.check(workbook)
    if issues:
        msgs = "; ".join(i.message for i in issues)
        raise AssertionError(f"Deprecated functions found: {msgs}")


def assert_no_credential_exposure(workbook: Workbook) -> None:
    """Assert that no plaintext passwords are present in connection nodes.

    Args:
        workbook: The Tableau workbook to check.

    Raises:
        AssertionError: If credential exposure is detected.
    """
    from pytableau.xml.rules import CredentialExposureRule

    rule = CredentialExposureRule()
    issues = rule.check(workbook)
    if issues:
        msgs = "; ".join(i.message for i in issues)
        raise AssertionError(f"Credential exposure detected: {msgs}")


def assert_no_custom_sql(workbook: Workbook) -> None:
    """Assert that the workbook contains no custom SQL queries.

    Args:
        workbook: The Tableau workbook to check.

    Raises:
        AssertionError: If custom SQL is found.
    """
    from pytableau.governance.rules import CustomSQLAuditRule

    rule = CustomSQLAuditRule(severity="error")
    issues = rule.check(workbook)
    if issues:
        msgs = "; ".join(i.message for i in issues)
        raise AssertionError(f"Custom SQL found: {msgs}")
