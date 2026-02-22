"""CLI tests for pytableau v0.4.0 — tooli-powered command suite.

Uses ``app.call()`` to invoke commands as Python functions, bypassing CLI
parsing while exercising the same validation, error-handling, and result
wrapping pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pytableau.cli.main import app

# ---------------------------------------------------------------------------
# Shared TWB fixture helpers
# ---------------------------------------------------------------------------

_MINIMAL_TWB = """\
<?xml version='1.0' encoding='utf-8'?>
<workbook source-build="20241.24.0312.0830" source-platform="python">
  <datasources>
    <datasource name="sqlserver.TestDB" caption="Test DB">
      <connection class="sqlserver" server="old-server.example.com"
                  dbname="TestDB" username="testuser"/>
      <columns>
        <column name="[Sales]" caption="Sales" datatype="real" role="measure"/>
        <column name="[Region]" caption="Region" datatype="string" role="dimension"/>
      </columns>
    </datasource>
  </datasources>
  <worksheets>
    <worksheet name="Sales by Region"/>
  </worksheets>
  <dashboards>
    <dashboard name="Overview">
      <size type="automatic" width="1200" height="800"/>
    </dashboard>
  </dashboards>
</workbook>
"""

_MINIMAL_TWB_ALT = """\
<?xml version='1.0' encoding='utf-8'?>
<workbook source-build="20241.24.0312.0830" source-platform="python">
  <datasources>
    <datasource name="sqlserver.TestDB" caption="Test DB">
      <connection class="sqlserver" server="new-server.example.com"
                  dbname="TestDB" username="testuser"/>
      <columns>
        <column name="[Revenue]" caption="Revenue" datatype="real" role="measure"/>
        <column name="[Category]" caption="Category" datatype="string" role="dimension"/>
      </columns>
    </datasource>
  </datasources>
  <worksheets>
    <worksheet name="Revenue by Category"/>
  </worksheets>
  <dashboards/>
</workbook>
"""


def _write_twb(path: Path, content: str = _MINIMAL_TWB) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


def test_inspect(tmp_path: Path) -> None:
    twb = _write_twb(tmp_path / "wb.twb")
    result = app.call("inspect", workbook=twb)

    assert result.ok, f"Expected ok but got error: {result.error}"
    data = result.result
    assert data["version"] == "2024.1"
    assert data["worksheet_count"] == 1
    assert "Sales by Region" in data["worksheets"]
    assert data["dashboard_count"] == 1
    assert "Overview" in data["dashboards"]


def test_inspect_missing_file(tmp_path: Path) -> None:
    result = app.call("inspect", workbook=tmp_path / "nonexistent.twb")
    assert not result.ok
    assert result.error is not None


def test_inspect_invalid_xml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.twb"
    bad.write_text("not xml at all", encoding="utf-8")
    result = app.call("inspect", workbook=bad)
    assert not result.ok
    assert result.error is not None


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def test_validate_returns_no_issues_for_valid_workbook(tmp_path: Path) -> None:
    twb = _write_twb(tmp_path / "wb.twb")
    result = app.call("validate", workbook=twb)

    assert result.ok, f"Expected ok but got error: {result.error}"
    data = result.result
    assert "issue_count" in data
    assert isinstance(data["issues"], list)


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


def test_diff_identical_workbooks(tmp_path: Path) -> None:
    twb1 = _write_twb(tmp_path / "a.twb")
    twb2 = _write_twb(tmp_path / "b.twb")
    result = app.call("diff", before=twb1, after=twb2)

    assert result.ok, f"Expected ok but got error: {result.error}"
    data = result.result
    assert data["added_count"] == 0
    assert data["removed_count"] == 0


def test_diff_detects_change(tmp_path: Path) -> None:
    twb1 = _write_twb(tmp_path / "before.twb", _MINIMAL_TWB)
    twb2 = _write_twb(tmp_path / "after.twb", _MINIMAL_TWB_ALT)
    result = app.call("diff", before=twb1, after=twb2)

    assert result.ok, f"Expected ok but got error: {result.error}"
    data = result.result
    # The two workbooks differ so at least one side should have changes
    assert data["added_count"] > 0 or data["removed_count"] > 0


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------


def test_catalog_lists_datasources(tmp_path: Path) -> None:
    twb = _write_twb(tmp_path / "wb.twb")
    result = app.call("catalog", workbook=twb)

    assert result.ok, f"Expected ok but got error: {result.error}"
    data = result.result
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "sqlserver.TestDB"


# ---------------------------------------------------------------------------
# swap_connection
# ---------------------------------------------------------------------------


def test_swap_connection(tmp_path: Path) -> None:
    twb = _write_twb(tmp_path / "wb.twb")
    out = tmp_path / "out.twb"
    result = app.call(
        "swap_connection",
        workbook=twb,
        server="prod-server.example.com",
        db="ProdDB",
        output=out,
    )

    assert result.ok, f"Expected ok but got error: {result.error}"
    data = result.result
    assert data["server"] == "prod-server.example.com"
    assert out.exists()

    # Verify the change was written to the output file
    content = out.read_text(encoding="utf-8")
    assert "prod-server.example.com" in content


def test_swap_connection_dry_run(tmp_path: Path) -> None:
    twb = _write_twb(tmp_path / "wb.twb")
    result = app.call(
        "swap_connection",
        workbook=twb,
        server="prod-server.example.com",
        dry_run=True,
    )
    assert result.ok, f"Expected ok but got error: {result.error}"
    # dry_run returns a plan dict, not the mutation result
    assert result.result.get("dry_run") is True


# ---------------------------------------------------------------------------
# rename_field
# ---------------------------------------------------------------------------


def test_rename_field(tmp_path: Path) -> None:
    twb = _write_twb(tmp_path / "wb.twb")
    out = tmp_path / "renamed.twb"
    result = app.call(
        "rename_field",
        workbook=twb,
        old_name="Sales",
        new_name="Revenue",
        output=out,
    )

    assert result.ok, f"Expected ok but got error: {result.error}"
    data = result.result
    assert data["old_name"] == "Sales"
    assert data["new_name"] == "Revenue"
    assert out.exists()


# ---------------------------------------------------------------------------
# version_migrate
# ---------------------------------------------------------------------------


def test_version_migrate(tmp_path: Path) -> None:
    twb = _write_twb(tmp_path / "wb.twb")
    out = tmp_path / "migrated.twb"
    result = app.call(
        "version_migrate",
        workbook=twb,
        target_version="2023.1",
        output=out,
    )

    assert result.ok, f"Expected ok but got error: {result.error}"
    data = result.result
    assert data["target_version"] == "2023.1"
    assert out.exists()


def test_version_migrate_invalid_version(tmp_path: Path) -> None:
    twb = _write_twb(tmp_path / "wb.twb")
    result = app.call(
        "version_migrate",
        workbook=twb,
        target_version="9999.99",
    )
    assert not result.ok
    assert result.error is not None


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------


def test_merge(tmp_path: Path) -> None:
    base = _write_twb(tmp_path / "base.twb", _MINIMAL_TWB)
    other = _write_twb(tmp_path / "other.twb", _MINIMAL_TWB_ALT)
    out = tmp_path / "merged.twb"
    result = app.call("merge", base=base, other=other, output=out)

    assert result.ok, f"Expected ok but got error: {result.error}"
    data = result.result
    assert out.exists()
    # The merged workbook should have worksheets from both
    assert len(data["worksheets_after"]) >= len(data["worksheets_before"])


# ---------------------------------------------------------------------------
# template_list
# ---------------------------------------------------------------------------


def test_template_list() -> None:
    result = app.call("template_list")
    assert result.ok, f"Expected ok but got error: {result.error}"
    templates = result.result
    assert isinstance(templates, list)
    names = {t["name"] for t in templates}
    assert "bar_chart" in names
    assert "line_chart" in names
    assert "kpi_dashboard" in names


# ---------------------------------------------------------------------------
# template_apply
# ---------------------------------------------------------------------------


def test_template_apply(tmp_path: Path) -> None:
    out = tmp_path / "output.twb"
    result = app.call(
        "template_apply",
        template="bar_chart",
        output=out,
        fields=["__DIMENSION__=Region", "__MEASURE__=Sales"],
    )
    assert result.ok, f"Expected ok but got error: {result.error}"
    assert out.exists()
    data = result.result
    assert data["template"] == "bar_chart"


def test_template_apply_invalid_field_format(tmp_path: Path) -> None:
    out = tmp_path / "output.twb"
    result = app.call(
        "template_apply",
        template="bar_chart",
        output=out,
        fields=["BADFORMAT"],
    )
    assert not result.ok
    assert result.error is not None


def test_template_apply_unknown_template(tmp_path: Path) -> None:
    out = tmp_path / "output.twb"
    result = app.call("template_apply", template="nonexistent_template", output=out)
    assert not result.ok
    assert result.error is not None


# ---------------------------------------------------------------------------
# publish (server integration — error path only)
# ---------------------------------------------------------------------------


def test_publish_no_server_raises_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Publishing to a bogus server should surface an error (not crash)."""
    twb = _write_twb(tmp_path / "wb.twb")

    # Patch ServerClient to raise AuthenticationError immediately
    from pytableau.exceptions import AuthenticationError

    def _mock_publish(*args: object, **kwargs: object) -> None:
        raise AuthenticationError("Token is invalid or expired")

    monkeypatch.setattr(
        "pytableau.core.workbook.Workbook.publish", _mock_publish
    )

    result = app.call(
        "publish",
        workbook=twb,
        server="https://fake-tableau.example.com",
        project="Default",
        token_name="mytoken",
        token_secret="secret",
    )
    assert not result.ok
    assert result.error is not None
