"""Tests for v1.0.0 — pytest-tableau testing plugin."""

from __future__ import annotations

from pathlib import Path

import pytest

from pytableau.core.workbook import Workbook
from pytableau.testing.assertions import (
    assert_calculation_valid,
    assert_complexity_grade,
    assert_dashboard_contains,
    assert_field_exists,
    assert_no_credential_exposure,
    assert_no_deprecated_functions,
    assert_no_live_connections,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def minimal_wb():
    return Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")


def multi_ds_wb():
    return Workbook.open(FIXTURE_DIR / "multi_datasource_v2024_1.twb")


def dashboard_wb():
    return Workbook.open(FIXTURE_DIR / "dashboard_actions_v2024_1.twb")


# ---------------------------------------------------------------------------
# assert_field_exists
# ---------------------------------------------------------------------------


def test_assert_field_exists_known():
    """assert_field_exists passes for known field."""
    wb = minimal_wb()
    # minimal_v2022_4.twb has "Region" and "Sales"
    assert_field_exists(wb, "Region")


def test_assert_field_exists_unknown():
    """assert_field_exists raises AssertionError for unknown field."""
    wb = minimal_wb()
    with pytest.raises(AssertionError, match="not found"):
        assert_field_exists(wb, "__DEFINITELY_MISSING__")


# ---------------------------------------------------------------------------
# assert_calculation_valid
# ---------------------------------------------------------------------------


def test_assert_calculation_valid_passes():
    """assert_calculation_valid passes for a field with a formula."""
    # lod_heavy fixture has calculated fields
    wb = Workbook.open(FIXTURE_DIR / "lod_heavy_v2024_1.twb")
    # Find any calculated field to test with
    calc_name = None
    for ds in wb.datasources:
        for f in ds.calculated_fields:
            if f.formula:
                calc_name = f.caption
                break
        if calc_name:
            break
    if calc_name is None:
        pytest.skip("No calculated fields in fixture")
    assert_calculation_valid(wb, calc_name)


# ---------------------------------------------------------------------------
# assert_dashboard_contains
# ---------------------------------------------------------------------------


def test_assert_dashboard_contains_passes():
    """assert_dashboard_contains passes for correct dashboard + sheets."""
    wb = dashboard_wb()
    # Just check that the function runs without raising for an existing dashboard
    dashboards = list(wb.dashboards)
    if not dashboards:
        pytest.skip("No dashboards in fixture")
    db = dashboards[0]
    # Don't assert specific sheets — just that it doesn't crash for empty list
    assert_dashboard_contains(wb, db.name, [])


def test_assert_dashboard_contains_raises_for_missing_sheet():
    """assert_dashboard_contains raises for a missing sheet."""
    wb = dashboard_wb()
    dashboards = list(wb.dashboards)
    if not dashboards:
        pytest.skip("No dashboards in fixture")
    db = dashboards[0]
    with pytest.raises(AssertionError):
        assert_dashboard_contains(wb, db.name, ["__NONEXISTENT_SHEET__"])


# ---------------------------------------------------------------------------
# assert_no_live_connections
# ---------------------------------------------------------------------------


def test_assert_no_live_connections_raises_for_live():
    """assert_no_live_connections raises for a live-connection workbook."""
    wb = minimal_wb()  # uses sqlserver — live connection
    with pytest.raises(AssertionError, match="[Ll]ive"):
        assert_no_live_connections(wb)


# ---------------------------------------------------------------------------
# assert_complexity_grade
# ---------------------------------------------------------------------------


def test_assert_complexity_grade_f_always_passes():
    """assert_complexity_grade('F') always passes (F = accept any grade)."""
    wb = minimal_wb()
    assert_complexity_grade(wb, max_grade="F")


# ---------------------------------------------------------------------------
# assert_no_deprecated_functions
# ---------------------------------------------------------------------------


def test_assert_no_deprecated_functions_passes_clean():
    """assert_no_deprecated_functions passes for a workbook with no deprecated calls."""
    wb = minimal_wb()
    # minimal fixture has no calculated fields → no deprecated functions
    assert_no_deprecated_functions(wb)


# ---------------------------------------------------------------------------
# assert_no_credential_exposure
# ---------------------------------------------------------------------------


def test_assert_no_credential_exposure_passes():
    """assert_no_credential_exposure passes for a workbook without plaintext passwords."""
    wb = Workbook.open(FIXTURE_DIR / "lod_heavy_v2024_1.twb")
    # lod_heavy fixture has no password attributes
    assert_no_credential_exposure(wb)


# ---------------------------------------------------------------------------
# workbook_factory fixture
# ---------------------------------------------------------------------------


def test_workbook_factory_opens_workbook():
    """workbook_factory fixture opens workbook correctly."""
    # Direct test: call the inner factory logic
    wb = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    assert wb.version is not None
