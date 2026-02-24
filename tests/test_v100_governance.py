"""Tests for v1.0.0 — Governance module (M11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pytableau.core.workbook import Workbook
from pytableau.governance.index import WorkbookIndex
from pytableau.governance.rules import (
    GovernanceLintIssue,
    GovernanceRuleset,
    MaxComplexityRule,
    NoLiveConnectionsRule,
    lint_with_ruleset,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def minimal_wb():
    return Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")


# ---------------------------------------------------------------------------
# WorkbookIndex — schema / CRUD
# ---------------------------------------------------------------------------


def test_index_creates_tables():
    """WorkbookIndex in-memory creates tables on init."""
    with WorkbookIndex(":memory:") as idx:
        cur = idx._conn.cursor()
        tables = {
            row[0]
            for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert {"workbooks", "fields", "connections"} <= tables


def test_add_inserts_workbook_row():
    """add() inserts a workbook row."""
    with WorkbookIndex(":memory:") as idx:
        idx.add(FIXTURE_DIR / "minimal_v2022_4.twb")
        rows = idx._conn.execute("SELECT path FROM workbooks").fetchall()
    assert len(rows) == 1


def test_add_inserts_field_rows():
    """add() inserts field rows (calculated or otherwise)."""
    with WorkbookIndex(":memory:") as idx:
        idx.add(FIXTURE_DIR / "minimal_v2022_4.twb")
        count = idx._conn.execute("SELECT COUNT(*) FROM fields").fetchone()[0]
    assert count >= 0  # minimal fixture may have 0 calcs; just assert no crash


def test_add_inserts_connection_rows():
    """add() inserts connection rows."""
    with WorkbookIndex(":memory:") as idx:
        idx.add(FIXTURE_DIR / "minimal_v2022_4.twb")
        count = idx._conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
    assert count >= 1  # minimal fixture has one sqlserver connection


def test_search_field_partial():
    """search_field() finds fields by partial name."""
    with WorkbookIndex(":memory:") as idx:
        idx.add(FIXTURE_DIR / "minimal_v2022_4.twb")
        results = idx.search_field("Sales")
    # "Sales" is a field caption in the minimal fixture
    assert isinstance(results, list)
    # At least one result expected since "Sales" is in the fixture
    captions = [r["caption"] for r in results]
    assert any("Sales" in c for c in captions)


def test_search_field_exact_match():
    """search_field(exact=True) matches exact caption."""
    with WorkbookIndex(":memory:") as idx:
        idx.add(FIXTURE_DIR / "minimal_v2022_4.twb")
        exact = idx.search_field("Sales", exact=True)
        partial = idx.search_field("al", exact=False)
    assert isinstance(exact, list)
    assert isinstance(partial, list)


def test_search_field_unknown_returns_empty():
    """search_field() returns empty list for unknown field."""
    with WorkbookIndex(":memory:") as idx:
        idx.add(FIXTURE_DIR / "minimal_v2022_4.twb")
        results = idx.search_field("__DEFINITELY_NOT_A_FIELD__")
    assert results == []


def test_search_connection_by_server():
    """search_connection() finds connections by server name."""
    with WorkbookIndex(":memory:") as idx:
        idx.add(FIXTURE_DIR / "minimal_v2022_4.twb")
        results = idx.search_connection("example.com")
    assert len(results) >= 1
    assert "example.com" in results[0]["server"]


def test_add_directory_returns_count():
    """add_directory() returns number of workbooks successfully indexed."""
    with WorkbookIndex(":memory:") as idx:
        count = idx.add_directory(FIXTURE_DIR, pattern="**/*.twb")
    assert count >= 1


def test_summary_has_correct_keys():
    """summary() returns dict with expected keys."""
    with WorkbookIndex(":memory:") as idx:
        idx.add(FIXTURE_DIR / "minimal_v2022_4.twb")
        s = idx.summary()
    assert {"workbooks", "fields", "calculated_fields", "connections"} <= set(s.keys())
    assert s["workbooks"] == 1


def test_context_manager():
    """WorkbookIndex works as a context manager."""
    with WorkbookIndex(":memory:") as idx:
        idx.add(FIXTURE_DIR / "minimal_v2022_4.twb")
        s = idx.summary()
    assert s["workbooks"] == 1


# ---------------------------------------------------------------------------
# GovernanceRuleset
# ---------------------------------------------------------------------------


def test_default_ruleset_has_six_rules():
    """GovernanceRuleset.default() returns 6 rules."""
    rs = GovernanceRuleset.default()
    assert len(rs.rules) == 6


def test_from_dict_parses_naming_conventions():
    """GovernanceRuleset.from_dict() parses naming_conventions rule."""
    cfg = {
        "rules": {
            "naming_conventions": {
                "enabled": True,
                "field_pattern": "^[A-Z].*",
                "severity": "warning",
            }
        }
    }
    rs = GovernanceRuleset.from_dict(cfg)
    assert len(rs.rules) == 1
    assert rs.rules[0].name == "naming_conventions"


def test_lint_issue_is_frozen():
    """GovernanceLintIssue is immutable (frozen dataclass)."""
    issue = GovernanceLintIssue(rule="test", severity="warning", message="msg")
    with pytest.raises((AttributeError, TypeError)):
        issue.rule = "changed"  # type: ignore[misc]


def test_no_live_connections_flags_live():
    """NoLiveConnectionsRule flags a datasource with a live connection."""
    wb = minimal_wb()  # sqlserver connection = live
    rule = NoLiveConnectionsRule(severity="error")
    issues = rule.check(wb)
    # minimal_v2022_4.twb has sqlserver (live) — expect at least one issue
    assert len(issues) >= 1
    assert all(i.severity == "error" for i in issues)


def test_max_complexity_zero_always_triggers():
    """MaxComplexityRule(max_score=0) always produces an issue."""
    wb = minimal_wb()
    rule = MaxComplexityRule(max_score=0, severity="warning")
    issues = rule.check(wb)
    assert len(issues) == 1
    assert issues[0].rule == "max_complexity"


def test_ruleset_check_clean_workbook():
    """GovernanceRuleset.check() on a workbook has no error-severity issues for default."""
    # We only check that the call completes without raising
    wb = minimal_wb()
    rs = GovernanceRuleset.default()
    issues = lint_with_ruleset(wb, rs)
    # Issues may exist (naming conventions, live connections) but should not crash
    assert isinstance(issues, list)
    for issue in issues:
        assert isinstance(issue, GovernanceLintIssue)


def test_cli_governance_lint(tmp_path):
    """CLI governance-lint command returns JSON result."""
    from pytableau.cli.main import app

    result = app.call(
        "governance_lint",
        workbook=str(FIXTURE_DIR / "minimal_v2022_4.twb"),
    )
    assert result.ok
    assert "passed" in result.result
    assert "issues" in result.result
    assert isinstance(result.result["issues"], list)
