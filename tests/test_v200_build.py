"""Tests for pytableau.build — programmatic viz authoring (v2.0 Pillar III)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from lxml import etree

from pytableau.build import (
    DashboardBuilder,
    DatasourceBuilder,
    WorksheetBuilder,
    from_spec,
    quick_chart,
    quick_dashboard,
)
from pytableau.build._xml import (
    ds_internal_name,
    encode_shelf_field,
    encode_shelf_list,
    make_column_type,
    slugify,
)
from pytableau.build.theme import Theme
from pytableau.constants import DataType, FilterType, MarkType, Role
from pytableau.core.workbook import Workbook
from pytableau.exceptions import DuplicateFieldError, InvalidWorkbookError


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------


class TestXmlHelpers:
    def test_slugify(self):
        assert slugify("Sales Data") == "sales_data"
        assert slugify("  Region  ") == "region"
        assert slugify("My--Field!!") == "my_field"

    def test_encode_shelf_field_bare(self):
        assert encode_shelf_field("Region") == "[Region]"

    def test_encode_shelf_field_already_bracketed(self):
        assert encode_shelf_field("[SUM(Sales)]") == "[SUM(Sales)]"

    def test_encode_shelf_field_aggregated(self):
        assert encode_shelf_field("SUM(Sales)") == "[SUM(Sales)]"

    def test_encode_shelf_list(self):
        result = encode_shelf_list(["Region", "SUM(Sales)"])
        assert result == "[Region], [SUM(Sales)]"

    def test_encode_shelf_list_empty(self):
        assert encode_shelf_list([]) == ""

    def test_make_column_type(self):
        assert make_column_type("measure") == "quantitative"
        assert make_column_type("dimension") == "nominal"

    def test_ds_internal_name(self):
        assert ds_internal_name("hyper", "Sales Data") == "hyper.sales_data"


# ---------------------------------------------------------------------------
# DatasourceBuilder
# ---------------------------------------------------------------------------


class TestDatasourceBuilder:
    def test_basic_columns(self):
        ds = (
            DatasourceBuilder("Sales")
            .connection("hyper", dbname="sales.hyper")
            .column("Region", DataType.STRING, Role.DIMENSION)
            .column("Sales", DataType.REAL, Role.MEASURE)
            .build()
        )
        assert ds.tag == "datasource"
        cols = ds.find("columns")
        assert cols is not None
        col_nodes = list(cols)
        captions = [c.get("caption") for c in col_nodes]
        assert "Region" in captions
        assert "Sales" in captions

    def test_calculated_field(self):
        ds = (
            DatasourceBuilder("Sales")
            .connection("hyper", dbname="sales.hyper")
            .column("Sales", DataType.REAL, Role.MEASURE)
            .column("Cost", DataType.REAL, Role.MEASURE)
            .calculated_field("Margin", "SUM([Sales]) - SUM([Cost])")
            .build()
        )
        cols = ds.find("columns")
        calc_nodes = [c for c in cols if c.find("calculation") is not None]
        assert len(calc_nodes) == 1
        assert calc_nodes[0].get("caption") == "Margin"

    def test_duplicate_column_error(self):
        with pytest.raises(DuplicateFieldError):
            DatasourceBuilder("Sales").column("Region", DataType.STRING, Role.DIMENSION).column(
                "Region", DataType.STRING, Role.DIMENSION
            )

    def test_duplicate_calc_error(self):
        with pytest.raises(DuplicateFieldError):
            (
                DatasourceBuilder("Sales")
                .calculated_field("Margin", "[Sales]-[Cost]")
                .calculated_field("Margin", "[Sales]-[Cost]")
            )

    def test_hidden_column(self):
        ds = (
            DatasourceBuilder("Sales")
            .connection("hyper")
            .column("__id__", DataType.INTEGER, Role.DIMENSION, hidden=True)
            .build()
        )
        cols = ds.find("columns")
        hidden_col = next(c for c in cols if c.get("caption") == "__id__")
        assert hidden_col.get("hidden") == "true"

    def test_connection_class_variations(self):
        ds = (
            DatasourceBuilder("DB")
            .connection("sqlserver", server="db.corp.com", dbname="prod")
            .build()
        )
        conn = ds.find("connection")
        assert conn.get("class") == "sqlserver"
        assert conn.get("server") == "db.corp.com"

    def test_name_property(self):
        b = DatasourceBuilder("Sales Data")
        b.connection("hyper")
        assert b.name == "hyper.sales_data"

    def test_raw_alias(self):
        b = (
            DatasourceBuilder("Sales")
            .connection("hyper")
            .column("x", DataType.STRING, Role.DIMENSION)
        )
        assert b.raw().tag == b.build().tag


# ---------------------------------------------------------------------------
# WorksheetBuilder
# ---------------------------------------------------------------------------


class TestWorksheetBuilder:
    def test_bar_chart_basic(self):
        ws = (
            WorksheetBuilder("Revenue by Region")
            .datasource("hyper.sales")
            .mark_type("bar")
            .rows("Region")
            .columns("SUM(Sales)")
            .build()
        )
        assert ws.tag == "worksheet"
        assert ws.get("name") == "Revenue by Region"
        rows_el = ws.find("rows")
        assert "[Region]" in rows_el.text
        cols_el = ws.find("cols")
        assert "[SUM(Sales)]" in cols_el.text

    def test_line_chart_with_date_axis(self):
        ws = (
            WorksheetBuilder("Trend")
            .mark_type(MarkType.LINE)
            .columns("Order Date")
            .rows("SUM(Sales)")
            .build()
        )
        style = ws.find("style")
        assert style is not None
        assert style.get("mark") == MarkType.LINE.value

    def test_scatter_plot_two_measures(self):
        ws = (
            WorksheetBuilder("Scatter")
            .mark_type("circle")
            .columns("SUM(Sales)")
            .rows("SUM(Profit)")
            .build()
        )
        assert ws.find("cols").text == "[SUM(Sales)]"
        assert ws.find("rows").text == "[SUM(Profit)]"

    def test_mark_type_sets_style(self):
        ws = WorksheetBuilder("X").mark_type("bar").rows("A").columns("B").build()
        style = ws.find("style")
        assert style is not None
        assert style.get("mark") == "bar"

    def test_automatic_mark_no_style(self):
        ws = WorksheetBuilder("X").mark_type(MarkType.AUTOMATIC).rows("A").columns("B").build()
        # automatic mark should produce no <style> element
        assert ws.find("style") is None

    def test_multiple_shelf_fields(self):
        ws = WorksheetBuilder("X").rows("Region", "Category").columns("SUM(Sales)").build()
        rows_text = ws.find("rows").text
        assert "[Region]" in rows_text
        assert "[Category]" in rows_text

    def test_all_mark_channels(self):
        ws = (
            WorksheetBuilder("Full")
            .rows("Region")
            .columns("SUM(Sales)")
            .color("Category")
            .size("SUM(Profit)")
            .detail("Sub-Category")
            .tooltip("SUM(Quantity)")
            .label("SUM(Sales)")
            .build()
        )
        marks = ws.find("marks")
        tags = {el.tag for el in marks}
        assert {"color", "size", "detail", "tooltip", "label"} <= tags

    def test_filter_categorical(self):
        ws = (
            WorksheetBuilder("X")
            .rows("Region")
            .columns("SUM(Sales)")
            .filter("Region", values=["East", "West"])
            .build()
        )
        filters = ws.find("filters")
        assert filters is not None
        f = filters[0]
        assert f.get("class") == FilterType.CATEGORICAL.value
        values_el = f.find("values")
        assert values_el is not None
        vals = [v.text for v in values_el]
        assert "East" in vals

    def test_filter_range(self):
        ws = (
            WorksheetBuilder("X")
            .rows("Region")
            .columns("SUM(Sales)")
            .filter("Sales", minimum=100, maximum=5000)
            .build()
        )
        f = ws.find("filters")[0]
        assert f.get("class") == FilterType.RANGE.value
        assert f.get("min") == "100"
        assert f.get("max") == "5000"

    def test_sort_specification(self):
        ws = (
            WorksheetBuilder("X")
            .rows("Region")
            .columns("SUM(Sales)")
            .sort("Sales", descending=True)
            .build()
        )
        sorts = ws.find("sorts")
        assert sorts is not None
        s = sorts[0]
        assert s.get("direction") == "DESC"

    def test_title(self):
        ws = WorksheetBuilder("X").rows("A").columns("B").title("My Chart Title").build()
        title_el = ws.find("title")
        assert title_el is not None
        assert title_el.text == "My Chart Title"

    def test_empty_worksheet_error(self):
        with pytest.raises(InvalidWorkbookError):
            WorksheetBuilder("Empty").build()

    def test_chained_rows_accumulate(self):
        ws = WorksheetBuilder("X").rows("A").rows("B").columns("C").build()
        rows_text = ws.find("rows").text
        assert "[A]" in rows_text
        assert "[B]" in rows_text


# ---------------------------------------------------------------------------
# DashboardBuilder
# ---------------------------------------------------------------------------


class TestDashboardBuilder:
    def test_basic_two_zones(self):
        dash = (
            DashboardBuilder("Summary", width=1200, height=800)
            .sheet("Revenue by Region", x=0, y=0, w=600, h=400)
            .sheet("Trend Over Time", x=600, y=0, w=600, h=400)
            .build()
        )
        assert dash.tag == "dashboard"
        assert dash.get("name") == "Summary"
        zones = dash.find("zones")
        assert zones is not None
        assert len(list(zones)) == 2

    def test_action_filter(self):
        dash = (
            DashboardBuilder("D")
            .sheet("A", x=0, y=0, w=600, h=400)
            .sheet("B", x=600, y=0, w=600, h=400)
            .action("filter", source="A", target="B", field="Region")
            .build()
        )
        actions = dash.find("actions")
        assert actions is not None
        a = actions[0]
        assert a.get("type") == "filter"
        assert a.get("source-sheet") == "A"

    def test_action_highlight(self):
        dash = (
            DashboardBuilder("D")
            .sheet("A", x=0, y=0, w=600, h=400)
            .action("highlight", source="A", target="A")
            .build()
        )
        a = dash.find("actions")[0]
        assert a.get("type") == "highlight"

    def test_text_zone(self):
        dash = DashboardBuilder("D").text("Hello World", x=0, y=0, w=300, h=50).build()
        zones = dash.find("zones")
        z = zones[0]
        assert z.get("type") == "text"
        assert z.text == "Hello World"

    def test_phone_layout(self):
        dash = (
            DashboardBuilder("D")
            .sheet("Sheet1", x=0, y=0, w=600, h=400)
            .phone_layout([("Sheet1", 0, 0, 320, 300)])
            .build()
        )
        layouts = dash.find("devicelayouts")
        assert layouts is not None
        phone = next(l for l in layouts if l.get("name") == "phone")
        assert phone is not None

    def test_tablet_layout(self):
        dash = (
            DashboardBuilder("D")
            .sheet("S", x=0, y=0, w=600, h=400)
            .tablet_layout([("S", 0, 0, 768, 500)])
            .build()
        )
        layouts = dash.find("devicelayouts")
        tablet = next(l for l in layouts if l.get("name") == "tablet")
        assert tablet is not None

    def test_blank_zone(self):
        dash = DashboardBuilder("D").blank(x=0, y=400, w=600, h=50).build()
        z = dash.find("zones")[0]
        assert z.get("type") == "blank"

    def test_filter_zone(self):
        dash = DashboardBuilder("D").filter_zone("Region", x=0, y=0, w=200, h=50).build()
        z = dash.find("zones")[0]
        assert z.get("type") == "filter"


# ---------------------------------------------------------------------------
# from_spec
# ---------------------------------------------------------------------------


class TestSpecLoader:
    def test_minimal_spec_dict(self):
        spec = {
            "datasources": [
                {
                    "name": "Sales",
                    "connection": {"class": "hyper", "dbname": "sales.hyper"},
                    "columns": [
                        {"caption": "Region", "datatype": "string", "role": "dimension"},
                        {"caption": "Sales", "datatype": "real", "role": "measure"},
                    ],
                }
            ],
            "worksheets": [
                {
                    "name": "Revenue by Region",
                    "datasource": "Sales",
                    "mark_type": "bar",
                    "rows": "Region",
                    "columns": "SUM(Sales)",
                }
            ],
        }
        wb = from_spec(spec)
        assert isinstance(wb, Workbook)
        assert len(wb.worksheets) == 1
        assert wb.worksheets[0].name == "Revenue by Region"

    def test_spec_with_dashboard(self):
        spec = {
            "datasources": [
                {
                    "name": "Data",
                    "connection": {"class": "hyper", "dbname": "data.hyper"},
                    "columns": [
                        {"caption": "Cat", "datatype": "string", "role": "dimension"},
                        {"caption": "Val", "datatype": "real", "role": "measure"},
                    ],
                }
            ],
            "worksheets": [
                {"name": "Sheet1", "datasource": "Data", "rows": "Cat", "columns": "SUM(Val)"}
            ],
            "dashboards": [
                {
                    "name": "MyDash",
                    "width": 1200,
                    "height": 800,
                    "zones": [{"worksheet": "Sheet1", "x": 0, "y": 0, "w": 1200, "h": 800}],
                }
            ],
        }
        wb = from_spec(spec)
        assert len(wb.dashboards) == 1
        assert wb.dashboards[0].name == "MyDash"

    def test_spec_with_calculated_fields(self):
        spec = {
            "datasources": [
                {
                    "name": "Sales",
                    "connection": {"class": "hyper", "dbname": "sales.hyper"},
                    "columns": [
                        {"caption": "Sales", "datatype": "real", "role": "measure"},
                        {"caption": "Cost", "datatype": "real", "role": "measure"},
                    ],
                    "calculated_fields": [
                        {"caption": "Margin", "formula": "SUM([Sales]) - SUM([Cost])"}
                    ],
                }
            ],
            "worksheets": [
                {
                    "name": "Margin Sheet",
                    "datasource": "Sales",
                    "rows": "Margin",
                    "columns": "SUM(Sales)",
                }
            ],
        }
        wb = from_spec(spec)
        assert isinstance(wb, Workbook)

    def test_spec_with_filters_and_sorts(self):
        spec = {
            "datasources": [
                {
                    "name": "Sales",
                    "connection": {"class": "hyper"},
                    "columns": [
                        {"caption": "Region", "datatype": "string", "role": "dimension"},
                        {"caption": "Sales", "datatype": "real", "role": "measure"},
                    ],
                }
            ],
            "worksheets": [
                {
                    "name": "Filtered",
                    "datasource": "Sales",
                    "rows": "Region",
                    "columns": "SUM(Sales)",
                    "filters": [{"field": "Region", "values": ["East", "West"]}],
                    "sorts": [{"field": "Sales", "descending": True}],
                }
            ],
        }
        wb = from_spec(spec)
        assert isinstance(wb, Workbook)

    def test_spec_from_json_file(self, tmp_path):
        spec = {
            "datasources": [
                {
                    "name": "D",
                    "connection": {"class": "hyper", "dbname": "d.hyper"},
                    "columns": [
                        {"caption": "X", "datatype": "string", "role": "dimension"},
                        {"caption": "Y", "datatype": "real", "role": "measure"},
                    ],
                }
            ],
            "worksheets": [{"name": "S", "datasource": "D", "rows": "X", "columns": "SUM(Y)"}],
        }
        json_file = tmp_path / "spec.json"
        json_file.write_text(json.dumps(spec))
        wb = from_spec(json_file)
        assert isinstance(wb, Workbook)

    def test_spec_single_string_shelf(self):
        # rows/columns can be a single string (not a list)
        spec = {
            "datasources": [
                {
                    "name": "S",
                    "connection": {"class": "hyper"},
                    "columns": [
                        {"caption": "Region", "datatype": "string", "role": "dimension"},
                        {"caption": "Sales", "datatype": "real", "role": "measure"},
                    ],
                }
            ],
            "worksheets": [
                {"name": "W", "datasource": "S", "rows": "Region", "columns": "SUM(Sales)"}
            ],
        }
        wb = from_spec(spec)
        assert len(wb.worksheets) == 1


# ---------------------------------------------------------------------------
# Round-trip: build → save → open
# ---------------------------------------------------------------------------


class TestBuildRoundTrip:
    def test_build_save_reopen_bar_chart(self, tmp_path):
        ds = (
            DatasourceBuilder("Sales")
            .connection("hyper", dbname="sales.hyper")
            .column("Region", DataType.STRING, Role.DIMENSION)
            .column("Sales", DataType.REAL, Role.MEASURE)
            .build()
        )
        ws = (
            WorksheetBuilder("Revenue by Region")
            .datasource("hyper.sales")
            .mark_type("bar")
            .rows("Region")
            .columns("SUM(Sales)")
            .build()
        )

        wb = Workbook.new()
        wb.xml_root.find("datasources").append(ds)
        wb.xml_root.find("worksheets").append(ws)
        wb._load_tree(wb.xml_tree)

        out = tmp_path / "bar.twb"
        wb.save_as(str(out))
        wb2 = Workbook.open(str(out))
        assert wb2.worksheets[0].name == "Revenue by Region"

    def test_build_save_reopen_with_dashboard(self, tmp_path):
        ds = (
            DatasourceBuilder("D")
            .connection("hyper", dbname="d.hyper")
            .column("Cat", DataType.STRING, Role.DIMENSION)
            .column("Val", DataType.REAL, Role.MEASURE)
            .build()
        )
        ws = (
            WorksheetBuilder("Sheet1").datasource("hyper.d").rows("Cat").columns("SUM(Val)").build()
        )
        dash = DashboardBuilder("Dash1").sheet("Sheet1", x=0, y=0, w=1200, h=800).build()

        wb = Workbook.new()
        wb.xml_root.find("datasources").append(ds)
        wb.xml_root.find("worksheets").append(ws)
        wb.xml_root.find("dashboards").append(dash)
        wb._load_tree(wb.xml_tree)

        out = tmp_path / "dash.twb"
        wb.save_as(str(out))
        wb2 = Workbook.open(str(out))
        assert wb2.dashboards[0].name == "Dash1"

    def test_from_spec_save_reopen(self, tmp_path):
        spec = {
            "datasources": [
                {
                    "name": "Sales",
                    "connection": {"class": "hyper", "dbname": "sales.hyper"},
                    "columns": [
                        {"caption": "Region", "datatype": "string", "role": "dimension"},
                        {"caption": "Sales", "datatype": "real", "role": "measure"},
                    ],
                }
            ],
            "worksheets": [
                {
                    "name": "Revenue",
                    "datasource": "Sales",
                    "mark_type": "bar",
                    "rows": "Region",
                    "columns": "SUM(Sales)",
                }
            ],
        }
        wb = from_spec(spec)
        out = tmp_path / "spec.twb"
        wb.save_as(str(out))
        wb2 = Workbook.open(str(out))
        assert wb2.worksheets[0].name == "Revenue"

    def test_quick_chart_save_reopen(self, tmp_path):
        wb = quick_chart(dimension="Region", measure="Sales", chart_type="bar")
        out = tmp_path / "quick.twb"
        wb.save_as(str(out))
        wb2 = Workbook.open(str(out))
        assert len(wb2.worksheets) >= 1

    def test_quick_dashboard_save_reopen(self, tmp_path):
        wb = quick_dashboard(
            caption="Sales",
            worksheets=[
                {"name": "By Region", "dimension": "Region", "measure": "Sales"},
                {"name": "By Category", "dimension": "Category", "measure": "Revenue"},
            ],
            columns=[
                ("Region", DataType.STRING.value, Role.DIMENSION.value),
                ("Category", DataType.STRING.value, Role.DIMENSION.value),
                ("Sales", DataType.REAL.value, Role.MEASURE.value),
                ("Revenue", DataType.REAL.value, Role.MEASURE.value),
            ],
        )
        out = tmp_path / "qdash.twb"
        wb.save_as(str(out))
        wb2 = Workbook.open(str(out))
        assert len(wb2.worksheets) == 2
        assert len(wb2.dashboards) == 1

    def test_builder_plus_mutation(self, tmp_path):
        """Build a workbook then apply a v1.0 mutation (add_calculated_field)."""
        ds_node = (
            DatasourceBuilder("Sales")
            .connection("hyper", dbname="sales.hyper")
            .column("Region", DataType.STRING, Role.DIMENSION)
            .column("Sales", DataType.REAL, Role.MEASURE)
            .column("Cost", DataType.REAL, Role.MEASURE)
            .build()
        )
        ws_node = (
            WorksheetBuilder("Revenue")
            .datasource("hyper.sales")
            .rows("Region")
            .columns("SUM(Sales)")
            .build()
        )
        wb = Workbook.new()
        wb.xml_root.find("datasources").append(ds_node)
        wb.xml_root.find("worksheets").append(ws_node)
        wb._load_tree(wb.xml_tree)

        # v1.0 mutation API on top of built workbook
        ds = wb.datasources[0]
        ds.add_calculated_field("Margin", "SUM([Sales]) - SUM([Cost])")
        out = tmp_path / "mutated.twb"
        wb.save_as(str(out))
        wb2 = Workbook.open(str(out))
        field_captions = [f.caption for f in wb2.datasources[0].calculated_fields]
        assert "Margin" in field_captions


# ---------------------------------------------------------------------------
# Workbook convenience methods
# ---------------------------------------------------------------------------


class TestWorkbookConvenienceMethods:
    def test_add_worksheet_from_builder(self):
        wb = Workbook.new()
        ws_builder = WorksheetBuilder("MySheet").rows("Region").columns("SUM(Sales)")
        wb.add_worksheet(ws_builder)
        assert len(wb.worksheets) == 1
        assert wb.worksheets[0].name == "MySheet"

    def test_add_worksheet_from_element(self):
        wb = Workbook.new()
        node = WorksheetBuilder("Raw").rows("A").columns("B").build()
        wb.add_worksheet(node)
        assert wb.worksheets[0].name == "Raw"

    def test_add_dashboard_from_builder(self):
        wb = Workbook.new()
        dash_builder = DashboardBuilder("MyDash").sheet("Sheet1", x=0, y=0, w=1200, h=800)
        wb.add_dashboard(dash_builder)
        assert len(wb.dashboards) == 1
        assert wb.dashboards[0].name == "MyDash"

    def test_workbook_from_spec_classmethod(self):
        spec = {
            "datasources": [
                {
                    "name": "Data",
                    "connection": {"class": "hyper", "dbname": "data.hyper"},
                    "columns": [
                        {"caption": "X", "datatype": "string", "role": "dimension"},
                        {"caption": "Y", "datatype": "real", "role": "measure"},
                    ],
                }
            ],
            "worksheets": [
                {"name": "Chart", "datasource": "Data", "rows": "X", "columns": "SUM(Y)"}
            ],
        }
        wb = Workbook.from_spec(spec)
        assert isinstance(wb, Workbook)
        assert wb.worksheets[0].name == "Chart"


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


class TestTheme:
    def test_theme_defaults(self):
        t = Theme()
        assert t.name == "default"
        assert t.font_family == "Tableau Book"
        assert t.font_size == 10

    def test_theme_custom(self):
        t = Theme(name="Corporate", font_family="Helvetica Neue", colors={"primary": "#003366"})
        assert t.name == "Corporate"
        assert t.colors["primary"] == "#003366"

    def test_theme_to_dict(self):
        t = Theme(name="test", colors={"bg": "#ffffff"})
        d = t.to_dict()
        assert d["name"] == "test"
        assert "colors" in d
        assert d["colors"]["bg"] == "#ffffff"

    def test_theme_from_workbook(self):
        wb = Workbook.new()
        t = Theme.from_workbook(wb)
        assert isinstance(t, Theme)


# ---------------------------------------------------------------------------
# Breaking changes
# ---------------------------------------------------------------------------


class TestBreakingChanges:
    def test_tableau_connection_error_exists(self):
        from pytableau.exceptions import TableauConnectionError

        assert TableauConnectionError is not None

    def test_connection_error_compat_alias(self):
        from pytableau.exceptions import ConnectionError, TableauConnectionError

        assert ConnectionError is TableauConnectionError

    def test_version_is_2_alpha(self):
        import pytableau

        assert pytableau.__version__.startswith("2.")
