"""M4 Polish — tests for the 4 genuinely new features resolving open issues:
#74 audit_connections, #87 to_changelog, #91 upsert_extract API, #115 apply_theme."""

from __future__ import annotations

import pytest

from pytableau import Workbook
from pytableau.build.theme import Theme
from pytableau.inspect.diff import diff_workbooks

MINIMAL = "tests/fixtures/minimal_v2022_4.twb"


@pytest.fixture
def wb():
    return Workbook.open(MINIMAL)


# ---------------------------------------------------------------------------
# #74 — Connection string audit
# ---------------------------------------------------------------------------


class TestAuditConnections:
    def test_returns_list(self, wb):
        result = wb.audit_connections()
        assert isinstance(result, list)

    def test_each_entry_has_required_keys(self, wb):
        for entry in wb.audit_connections():
            for key in ("datasource", "class_", "server", "dbname", "username", "port"):
                assert key in entry

    def test_no_passwords_in_audit(self, wb):
        for entry in wb.audit_connections():
            assert "password" not in entry
            assert "token" not in entry

    def test_non_parameter_datasources_only(self, wb):
        names = [e["datasource"] for e in wb.audit_connections()]
        assert "Parameters" not in names

    def test_returns_empty_for_new_workbook(self):
        new_wb = Workbook.new()
        assert new_wb.audit_connections() == []


# ---------------------------------------------------------------------------
# #87 — Changelog generation (WorkbookDiff.to_changelog)
# ---------------------------------------------------------------------------


class TestToChangelog:
    def test_no_changes_returns_no_changes(self, wb):
        diff = diff_workbooks(wb, wb)
        log = diff.to_changelog()
        assert "No changes" in log or "no changes" in log.lower()

    def test_returns_markdown_string(self, wb):
        diff = diff_workbooks(wb, wb)
        log = diff.to_changelog(version="1.2.0", date="2026-02-24")
        assert "## [1.2.0]" in log
        assert "2026-02-24" in log

    def test_added_field_appears(self):
        before = Workbook.open(MINIMAL)
        after = Workbook.open(MINIMAL)
        ds = after.datasources["sqlserver.sales"]
        ds.add_calculated_field("New KPI", "[Region]")
        diff = diff_workbooks(before, after)
        log = diff.to_changelog(version="2.0.0")
        assert "New KPI" in log
        assert "Added" in log

    def test_removed_field_appears(self):
        before = Workbook.open(MINIMAL)
        after = Workbook.open(MINIMAL)
        ds_after = after.datasources["sqlserver.sales"]
        # remove a field from the after workbook
        field = ds_after.all_fields[0]
        ds_after.remove_field(field.caption)
        diff = diff_workbooks(before, after)
        log = diff.to_changelog()
        assert "Removed" in log

    def test_unreleased_header_by_default(self, wb):
        diff = diff_workbooks(wb, wb)
        log = diff.to_changelog()
        assert "[Unreleased]" in log


# ---------------------------------------------------------------------------
# #115 — Programmatic formatting: apply_theme
# ---------------------------------------------------------------------------


class TestApplyTheme:
    def test_apply_theme_does_not_raise(self, wb):
        theme = Theme(name="test", font_family="Arial", font_size=12)
        wb.apply_theme(theme)  # must not raise

    def test_apply_theme_writes_preferences_node(self, wb):
        theme = Theme(name="corp", font_family="Calibri", font_size=10)
        wb.apply_theme(theme)
        prefs = wb.xml_root.find("preferences")
        assert prefs is not None

    def test_apply_theme_is_idempotent(self, wb):
        theme = Theme(name="corp", font_family="Arial", font_size=11)
        wb.apply_theme(theme)
        wb.apply_theme(theme)
        prefs = [el for el in wb.xml_root if el.tag == "preferences"]
        assert len(prefs) == 1  # only one preferences node

    def test_apply_theme_with_colors(self, wb):
        theme = Theme(name="brand", colors=["#FF0000", "#00FF00"])
        wb.apply_theme(theme)
        prefs = wb.xml_root.find("preferences")
        assert prefs is not None

    def test_apply_default_theme_works(self, wb):
        theme = Theme(name="default")
        wb.apply_theme(theme)


# ---------------------------------------------------------------------------
# #91 — upsert_extract API exists on Datasource
# ---------------------------------------------------------------------------


class TestUpsertExtractAPI:
    def test_method_exists_on_datasource(self, wb):
        ds = wb.datasources["sqlserver.sales"]
        assert hasattr(ds, "upsert_extract")
        assert callable(ds.upsert_extract)

    def test_upsert_raises_hyper_error_without_extract(self, wb):
        from pytableau.exceptions import HyperError

        ds = wb.datasources["sqlserver.sales"]
        # Datasource has no hyper extract attached, should raise HyperError
        with pytest.raises(HyperError):
            ds.upsert_extract(object())
