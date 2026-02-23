"""Integration tests against sample_workbook.twbx.

These tests exercise pytableau against a real, complex Tableau workbook:
  - Premier League statistics dashboard
  - 1 federated datasource (excel-direct + hyper extract)
  - 78 fields, 65 calculated fields
  - 18 worksheets, 1 dashboard
  - 3 parameters
  - 65 lineage entries

Run from the pytableau project root (where sample_workbook.twbx lives).
"""

from __future__ import annotations

from pathlib import Path

import pytest

SAMPLE = Path(__file__).parent.parent / "sample_workbook.twbx"

# Skip the entire module if the sample workbook is not present
pytestmark = pytest.mark.skipif(
    not SAMPLE.exists(),
    reason="sample_workbook.twbx not found in project root",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def wb():
    from pytableau.core.workbook import Workbook

    workbook = Workbook.open(SAMPLE)
    yield workbook
    workbook.close()


@pytest.fixture(scope="module")
def ds(wb):
    return list(wb.datasources)[0]


@pytest.fixture(scope="module")
def cat(wb):
    from pytableau.inspect.catalog import WorkbookCatalog

    return WorkbookCatalog(wb)


@pytest.fixture(scope="module")
def lineage(wb):
    from pytableau.inspect.lineage import FieldLineage

    return FieldLineage(wb)


# ---------------------------------------------------------------------------
# 1. Basic workbook metadata
# ---------------------------------------------------------------------------


class TestWorkbookMetadata:
    def test_version(self, wb):
        assert wb.version == "2024.1"

    def test_source_platform(self, wb):
        assert wb.source_platform == "mac"

    def test_datasource_count(self, wb):
        assert len(wb.datasources) == 1

    def test_worksheet_count(self, wb):
        assert len(wb.worksheets) == 18

    def test_dashboard_count(self, wb):
        assert len(wb.dashboards) == 1

    def test_worksheet_names_include_key_sheets(self, wb):
        names = set(wb.worksheets.names)
        assert "Premier League Tables Club 1" in names
        assert "Premier League Tables Club 2" in names
        assert "Decade Box Plots" in names
        assert "Table Position" in names
        assert "Points of Interest" in names

    def test_dashboard_name(self, wb):
        assert wb.dashboards.names == ["Three Decades of the Premier League"]

    def test_dashboard_size_is_automatic(self, wb):
        dash = list(wb.dashboards)[0]
        assert dash.size.type == "automatic"

    def test_workbook_has_parameters(self, wb):
        assert wb.parameters is not None
        assert len(list(wb.parameters.parameters)) == 3


# ---------------------------------------------------------------------------
# 2. Datasource structure
# ---------------------------------------------------------------------------


class TestDatasource:
    def test_datasource_name_is_federated(self, ds):
        assert ds.name.startswith("federated.")

    def test_datasource_caption(self, ds):
        assert "Premier" in ds.caption or "Season" in ds.caption or "Master" in ds.caption

    def test_total_field_count(self, ds):
        assert len(list(ds.all_fields)) == 78

    def test_calculated_field_count(self, ds):
        assert len(list(ds.calculated_fields)) == 65

    def test_connection_count(self, ds):
        # federated wrapper + excel-direct + hyper
        assert len(list(ds.connections)) == 3

    def test_has_hyper_connection(self, ds):
        classes = {c.class_ for c in ds.connections}
        assert "hyper" in classes

    def test_has_excel_direct_connection(self, ds):
        classes = {c.class_ for c in ds.connections}
        assert "excel-direct" in classes

    def test_hyper_connection_dbname(self, ds):
        hyper_conn = next(c for c in ds.connections if c.class_ == "hyper")
        assert hyper_conn.dbname is not None
        assert hyper_conn.dbname.endswith(".hyper")

    def test_non_calc_fields_present(self, ds):
        non_calc = [f for f in ds.all_fields if not getattr(f, "formula", None)]
        captions = {f.caption for f in non_calc}
        # Core football stats columns
        assert "[Season]" in captions or "Season" in captions or "[Points]" in captions

    def test_is_not_parameters_datasource(self, ds):
        assert not ds.is_parameters


# ---------------------------------------------------------------------------
# 3. Calculated field formulas
# ---------------------------------------------------------------------------


class TestCalculatedFields:
    def _calcs_by_caption(self, ds):
        return {cf.caption: cf for cf in ds.calculated_fields}

    def test_gd_int_formula_uses_int(self, ds):
        calcs = self._calcs_by_caption(ds)
        assert "GD Int" in calcs
        assert "INT" in (calcs["GD Int"].formula or "").upper()

    def test_boolean_club_highlight_1_references_team(self, ds):
        calcs = self._calcs_by_caption(ds)
        assert "Boolean | Club Highlight 1" in calcs
        formula = calcs["Boolean | Club Highlight 1"].formula or ""
        assert "[Team]" in formula

    def test_promoted_flag_references_initial_rank(self, ds):
        calcs = self._calcs_by_caption(ds)
        assert "Promoted | Flag" in calcs
        formula = calcs["Promoted | Flag"].formula or ""
        assert "Initial_Rank" in formula or "Rank" in formula

    def test_season_bin_uses_year(self, ds):
        calcs = self._calcs_by_caption(ds)
        assert "Season | Bin" in calcs
        formula = calcs["Season | Bin"].formula or ""
        assert "YEAR" in formula.upper()

    def test_area_colour_position_uses_fixed(self, ds):
        calcs = self._calcs_by_caption(ds)
        assert "Area | Colour Position" in calcs
        formula = calcs["Area | Colour Position"].formula or ""
        assert "FIXED" in formula.upper()

    def test_season_gf_uses_fixed_lod(self, ds):
        calcs = self._calcs_by_caption(ds)
        assert "Season | GF" in calcs
        formula = calcs["Season | GF"].formula or ""
        assert "FIXED" in formula.upper()
        assert "SUM" in formula.upper()

    def test_calculated_fields_without_formulas_are_group_types(self, ds):
        # Tableau "group" fields use <calculation class="categorical-bin"> instead of a
        # formula string — they are legitimate calculated fields with no formula attribute.

        no_formula = [cf for cf in ds.calculated_fields if not (cf.formula or "").strip()]
        for cf in no_formula:
            calc_el = cf.xml_node.find("calculation")
            assert calc_el is not None, (
                f"Field {cf.caption!r} has no formula and no <calculation> child element"
            )
            calc_class = calc_el.get("class", "")
            assert calc_class != "", f"Field {cf.caption!r} <calculation> has no class attribute"


# ---------------------------------------------------------------------------
# 4. Parameters
# ---------------------------------------------------------------------------


class TestParameters:
    def _params_by_caption(self, wb):
        return {p.caption: p for p in wb.parameters.parameters}

    def test_parameter_names(self, wb):
        params = self._params_by_caption(wb)
        assert "Club Highlight 1" in params
        assert "Club Highlight 2" in params
        assert "Initial or Final Param" in params

    def test_club_highlight_1_is_string_list(self, wb):
        params = self._params_by_caption(wb)
        p = params["Club Highlight 1"]
        assert p.datatype == "string"
        assert p.domain_type == "list"

    def test_club_highlight_2_is_string_list(self, wb):
        params = self._params_by_caption(wb)
        p = params["Club Highlight 2"]
        assert p.datatype == "string"
        assert p.domain_type == "list"

    def test_initial_or_final_param_default_is_final(self, wb):
        params = self._params_by_caption(wb)
        p = params["Initial or Final Param"]
        assert "Final" in (p.value or "")

    def test_club_highlight_default_is_none(self, wb):
        params = self._params_by_caption(wb)
        assert "None" in (params["Club Highlight 1"].value or "")


# ---------------------------------------------------------------------------
# 5. Catalog
# ---------------------------------------------------------------------------


class TestCatalog:
    def test_catalog_to_dict_keys(self, cat):
        data = cat.to_dict()
        assert set(data.keys()) >= {"version", "datasource_count", "datasources", "parameters"}

    def test_catalog_version(self, cat):
        assert cat.to_dict()["version"] == "2024.1"

    def test_catalog_datasource_count(self, cat):
        assert cat.to_dict()["datasource_count"] == 1

    def test_catalog_datasource_has_fields(self, cat):
        ds_data = cat.to_dict()["datasources"][0]
        assert ds_data["field_count"] == 78
        assert len(ds_data["fields"]) == 78

    def test_catalog_datasource_has_calcs(self, cat):
        ds_data = cat.to_dict()["datasources"][0]
        assert len(ds_data["calculated_fields"]) == 65

    def test_catalog_datasource_has_connections(self, cat):
        ds_data = cat.to_dict()["datasources"][0]
        assert len(ds_data["connections"]) == 3

    def test_catalog_parameter_count(self, cat):
        data = cat.to_dict()
        assert data["parameter_count"] == 3

    def test_catalog_parameters_have_expected_fields(self, cat):
        params = cat.to_dict()["parameters"]
        captions = {p["caption"] for p in params}
        assert "Club Highlight 1" in captions
        assert "Club Highlight 2" in captions
        assert "Initial or Final Param" in captions


# ---------------------------------------------------------------------------
# 6. Lineage
# ---------------------------------------------------------------------------


class TestLineage:
    def test_lineage_entry_count(self, lineage):
        assert len(lineage.entries) == 65

    def test_lineage_to_dict_keys_are_dsname_field(self, lineage):
        d = lineage.to_dict()
        # All keys should be "datasource_name::field_name"
        for key in d:
            assert "::" in key, f"Unexpected lineage key format: {key}"

    def test_gd_int_depends_on_gd(self, lineage):
        d = lineage.to_dict()
        gd_int_key = next((k for k in d if k.endswith("::GD Int")), None)
        assert gd_int_key is not None
        deps = d[gd_int_key]
        assert any("GD" in dep for dep in deps)

    def test_boolean_club_highlight_1_depends_on_team(self, lineage):
        d = lineage.to_dict()
        key = next((k for k in d if k.endswith("::Boolean | Club Highlight 1")), None)
        assert key is not None
        deps = d[key]
        assert any("Team" in dep for dep in deps)

    def test_area_colour_position_has_multiple_deps(self, lineage):
        d = lineage.to_dict()
        key = next((k for k in d if k.endswith("::Area | Colour Position")), None)
        assert key is not None
        assert len(d[key]) >= 3  # Season, a calc, GF, GA

    def test_for_field_lookup_by_caption(self, lineage):
        entry = lineage.for_field("GD Int")
        assert entry is not None
        assert entry.field == "GD Int"
        assert entry.formula is not None

    def test_row_placement_deps_on_inner_calc(self, lineage):
        d = lineage.to_dict()
        key = next((k for k in d if k.endswith("::Row Placement")), None)
        assert key is not None
        assert len(d[key]) >= 1


# ---------------------------------------------------------------------------
# 7. Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_validate_returns_no_errors(self, wb):
        issues = wb.validate()
        errors = [i for i in issues if i.level == "error"]
        assert errors == [], f"Unexpected validation errors: {errors}"

    def test_validate_returns_list(self, wb):
        issues = wb.validate()
        assert isinstance(issues, list)


# ---------------------------------------------------------------------------
# 8. Markdown report
# ---------------------------------------------------------------------------


class TestReport:
    def test_report_generates_markdown(self, wb):
        from pytableau.inspect.report import WorkbookReport

        rpt = WorkbookReport(wb)
        md = rpt.to_markdown()
        assert isinstance(md, str)
        assert len(md) > 500

    def test_report_contains_workbook_version(self, wb):
        from pytableau.inspect.report import WorkbookReport

        md = WorkbookReport(wb).to_markdown()
        assert "2024.1" in md

    def test_report_contains_datasource_caption(self, wb):
        from pytableau.inspect.report import WorkbookReport

        ds = list(wb.datasources)[0]
        md = WorkbookReport(wb).to_markdown()
        assert ds.caption in md or ds.name in md

    def test_report_contains_worksheets_section(self, wb):
        from pytableau.inspect.report import WorkbookReport

        md = WorkbookReport(wb).to_markdown()
        assert "## Worksheets" in md
        assert "Premier League Tables Club 1" in md

    def test_report_contains_parameters_section(self, wb):
        from pytableau.inspect.report import WorkbookReport

        md = WorkbookReport(wb).to_markdown()
        assert "## Parameters" in md
        assert "Club Highlight 1" in md

    def test_report_contains_lineage_section(self, wb):
        from pytableau.inspect.report import WorkbookReport

        md = WorkbookReport(wb).to_markdown()
        assert "## Calculated Field Lineage" in md

    def test_report_write_to_file(self, wb, tmp_path):
        from pytableau.inspect.report import WorkbookReport

        out = tmp_path / "report.md"
        rpt = WorkbookReport(wb)
        out.write_text(rpt.to_markdown(), encoding="utf-8")
        assert out.exists()
        assert out.stat().st_size > 1000


# ---------------------------------------------------------------------------
# 9. Round-trip save/open
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_save_as_twb_and_reopen(self, wb, tmp_path):
        from pytableau.core.workbook import Workbook

        out = tmp_path / "copy.twb"
        wb.save_as(out)
        wb2 = Workbook.open(out)
        assert wb2.version == wb.version
        assert len(wb2.datasources) == len(wb.datasources)
        assert wb2.worksheets.names == wb.worksheets.names
        assert wb2.dashboards.names == wb.dashboards.names

    def test_save_as_twbx_and_reopen(self, wb, tmp_path):
        from pytableau.core.workbook import Workbook

        out = tmp_path / "copy.twbx"
        wb.save_as(out)
        assert out.exists()
        wb2 = Workbook.open(out)
        assert wb2.version == wb.version
        assert len(wb2.worksheets) == len(wb.worksheets)

    def test_xml_roundtrip_preserves_calc_count(self, wb, tmp_path):
        from pytableau.core.workbook import Workbook

        out = tmp_path / "rt.twb"
        wb.save_as(out)
        wb2 = Workbook.open(out)
        ds2 = list(wb2.datasources)[0]
        assert len(list(ds2.calculated_fields)) == 65


# ---------------------------------------------------------------------------
# 10. Mutation: swap_connection
# ---------------------------------------------------------------------------


class TestSwapConnection:
    def test_swap_connection_updates_server(self, tmp_path):
        from pytableau.core.workbook import Workbook

        src = tmp_path / "wb.twb"
        out = tmp_path / "swapped.twb"

        # Write a .twb copy first
        wb = Workbook.open(SAMPLE)
        wb.save_as(src)
        wb.close()

        # Run swap via app.call()
        from pytableau.cli.main import app

        result = app.call(
            "swap_connection",
            workbook=src,
            server="prod-tableau.corp.com",
            output=out,
        )
        assert result.ok, f"swap_connection failed: {result.error}"
        assert out.exists()

        # Confirm server was written
        content = out.read_text(encoding="utf-8")
        assert "prod-tableau.corp.com" in content

    def test_swap_connection_dry_run_does_not_write(self, tmp_path):
        from pytableau.cli.main import app
        from pytableau.core.workbook import Workbook

        src = tmp_path / "wb2.twb"
        wb = Workbook.open(SAMPLE)
        wb.save_as(src)
        wb.close()

        out = tmp_path / "should_not_exist.twb"
        result = app.call(
            "swap_connection",
            workbook=src,
            server="dry-run-server.corp.com",
            output=out,
            dry_run=True,
        )
        assert result.ok
        assert result.result.get("dry_run") is True
        assert not out.exists()


# ---------------------------------------------------------------------------
# 11. Mutation: rename_field
# ---------------------------------------------------------------------------


class TestRenameField:
    def test_rename_calc_field(self, tmp_path):
        from pytableau.cli.main import app
        from pytableau.core.workbook import Workbook

        src = tmp_path / "wb.twb"
        out = tmp_path / "renamed.twb"

        wb = Workbook.open(SAMPLE)
        wb.save_as(src)
        wb.close()

        result = app.call(
            "rename_field",
            workbook=src,
            old_name="GD Int",
            new_name="GD Integer",
            output=out,
        )
        assert result.ok, f"rename_field failed: {result.error}"
        assert result.result["old_name"] == "GD Int"
        assert result.result["new_name"] == "GD Integer"
        assert out.exists()


# ---------------------------------------------------------------------------
# 12. Mutation: version_migrate
# ---------------------------------------------------------------------------


class TestVersionMigrate:
    def test_migrate_to_2023_1(self, tmp_path):
        from pytableau.cli.main import app
        from pytableau.core.workbook import Workbook

        src = tmp_path / "wb.twb"
        out = tmp_path / "migrated.twb"

        wb = Workbook.open(SAMPLE)
        wb.save_as(src)
        wb.close()

        result = app.call(
            "version_migrate",
            workbook=src,
            target_version="2023.1",
            output=out,
        )
        assert result.ok, f"version_migrate failed: {result.error}"
        assert result.result["target_version"] == "2023.1"
        assert result.result["original_version"] == "2024.1"

        wb2 = Workbook.open(out)
        assert wb2.version == "2023.1"
        wb2.close()


# ---------------------------------------------------------------------------
# 13. CLI: inspect command via app.call()
# ---------------------------------------------------------------------------


class TestCLIInspect:
    def test_inspect_ok(self):
        from pytableau.cli.main import app

        result = app.call("inspect", workbook=SAMPLE)
        assert result.ok, f"inspect failed: {result.error}"

    def test_inspect_version(self):
        from pytableau.cli.main import app

        data = app.call("inspect", workbook=SAMPLE).result
        assert data["version"] == "2024.1"

    def test_inspect_counts(self):
        from pytableau.cli.main import app

        data = app.call("inspect", workbook=SAMPLE).result
        assert data["datasource_count"] == 1
        assert data["worksheet_count"] == 18
        assert data["dashboard_count"] == 1

    def test_inspect_worksheet_names(self):
        from pytableau.cli.main import app

        data = app.call("inspect", workbook=SAMPLE).result
        assert "Premier League Tables Club 1" in data["worksheets"]
        assert "Table Position" in data["worksheets"]

    def test_validate_no_errors(self):
        from pytableau.cli.main import app

        result = app.call("validate", workbook=SAMPLE)
        assert result.ok
        data = result.result
        errors = [i for i in data["issues"] if i["level"] == "error"]
        assert errors == []

    def test_catalog_returns_datasource_list(self):
        from pytableau.cli.main import app

        result = app.call("catalog", workbook=SAMPLE)
        assert result.ok
        items = result.result
        assert isinstance(items, list)
        assert len(items) == 1
        assert items[0]["field_count"] == 78

    def test_lineage_returns_dict(self):
        from pytableau.cli.main import app

        result = app.call("lineage", workbook=SAMPLE)
        assert result.ok
        data = result.result
        assert isinstance(data, dict)
        assert len(data) == 65

    def test_diff_identical_returns_no_changes(self):
        from pytableau.cli.main import app

        result = app.call("diff", before=SAMPLE, after=SAMPLE)
        assert result.ok
        data = result.result
        assert data["added_count"] == 0
        assert data["removed_count"] == 0

    def test_report_returns_markdown(self):
        from pytableau.cli.main import app

        result = app.call("report", workbook=SAMPLE)
        assert result.ok
        md = result.result["markdown"]
        assert "# Workbook Report" in md
        assert "2024.1" in md
