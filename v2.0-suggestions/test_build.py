"""Tests for pytableau.build — programmatic viz authoring."""

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
from pytableau.constants import DataType, FilterType, MarkType, Role
from pytableau.core.workbook import Workbook
from pytableau.exceptions import DuplicateFieldError, InvalidWorkbookError


# ── XML helpers ────────────────────────────────────────────────────────────


class TestXmlHelpers:
    def test_slugify(self):
        assert slugify("Sales Data") == "sales_data"
        assert slugify("  Revenue & Profit!!  ") == "revenue_profit"
        assert slugify("simple") == "simple"

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
        assert ds_internal_name("sqlserver", "Revenue") == "sqlserver.revenue"


# ── DatasourceBuilder ──────────────────────────────────────────────────────


class TestDatasourceBuilder:
    def test_basic_columns(self):
        node = (
            DatasourceBuilder("Sales")
            .connection("hyper", dbname="sales.hyper")
            .column("Region", DataType.STRING, Role.DIMENSION)
            .column("Sales", DataType.REAL, Role.MEASURE)
            .build()
        )
        assert node.tag == "datasource"
        assert node.get("name") == "hyper.sales"
        assert node.get("caption") == "Sales"

        conn = node.find("connection")
        assert conn is not None
        assert conn.get("class") == "hyper"
        assert conn.get("dbname") == "sales.hyper"

        columns = node.findall("columns/column")
        assert len(columns) == 2
        assert columns[0].get("caption") == "Region"
        assert columns[0].get("datatype") == "string"
        assert columns[0].get("role") == "dimension"
        assert columns[0].get("type") == "nominal"
        assert columns[1].get("caption") == "Sales"
        assert columns[1].get("role") == "measure"
        assert columns[1].get("type") == "quantitative"

    def test_calculated_field(self):
        node = (
            DatasourceBuilder("Sales")
            .column("Sales", DataType.REAL, Role.MEASURE)
            .column("Cost", DataType.REAL, Role.MEASURE)
            .calculated_field("Margin", "SUM([Sales]) - SUM([Cost])")
            .build()
        )
        columns = node.findall("columns/column")
        assert len(columns) == 3

        calc_col = columns[2]
        assert calc_col.get("caption") == "Margin"
        calc = calc_col.find("calculation")
        assert calc is not None
        assert calc.get("formula") == "SUM([Sales]) - SUM([Cost])"

    def test_duplicate_column_error(self):
        builder = DatasourceBuilder("Sales").column("Region")
        with pytest.raises(DuplicateFieldError):
            builder.column("Region")

    def test_duplicate_calc_error(self):
        builder = DatasourceBuilder("Sales").column("Margin")
        with pytest.raises(DuplicateFieldError):
            builder.calculated_field("Margin", "1+1")

    def test_hidden_column(self):
        node = (
            DatasourceBuilder("Sales")
            .column("Internal ID", DataType.INTEGER, Role.DIMENSION, hidden=True)
            .build()
        )
        col = node.find("columns/column")
        assert col.get("hidden") == "true"

    def test_connection_class_variations(self):
        for cls in ("hyper", "sqlserver", "postgres", "snowflake"):
            node = (
                DatasourceBuilder("D")
                .connection(cls, server="host.com")
                .column("X")
                .build()
            )
            conn = node.find("connection")
            assert conn.get("class") == cls
            assert conn.get("server") == "host.com"

    def test_name_property(self):
        builder = DatasourceBuilder("My Data").connection("sqlserver")
        assert builder.name == "sqlserver.my_data"

    def test_raw_alias(self):
        builder = DatasourceBuilder("X").column("A")
        assert etree.tostring(builder.raw()) == etree.tostring(builder.build())


# ── WorksheetBuilder ───────────────────────────────────────────────────────


class TestWorksheetBuilder:
    def test_bar_chart_basic(self):
        node = (
            WorksheetBuilder("Revenue by Region")
            .datasource("hyper.sales")
            .mark_type("bar")
            .rows("Region")
            .columns("SUM(Sales)")
            .build()
        )
        assert node.tag == "worksheet"
        assert node.get("name") == "Revenue by Region"

        rows = node.find("rows")
        assert rows is not None
        assert rows.text == "[Region]"

        cols = node.find("cols")
        assert cols.text == "[SUM(Sales)]"

        deps = node.find("datasource-dependencies/datasource")
        assert deps is not None
        assert deps.get("name") == "hyper.sales"

    def test_line_chart_with_date_axis(self):
        node = (
            WorksheetBuilder("Trend")
            .mark_type(MarkType.LINE)
            .columns("MONTH(Order Date)")
            .rows("SUM(Sales)")
            .color("Region")
            .build()
        )
        cols = node.find("cols")
        assert "[MONTH(Order Date)]" in cols.text

        color = node.find("marks/color")
        assert color is not None
        assert "[Region]" in color.text

    def test_scatter_plot_two_measures(self):
        node = (
            WorksheetBuilder("Scatter")
            .mark_type("circle")
            .columns("SUM(Sales)")
            .rows("SUM(Profit)")
            .size("SUM(Quantity)")
            .build()
        )
        size = node.find("marks/size")
        assert size is not None
        assert "[SUM(Quantity)]" in size.text

    def test_mark_type_sets_style(self):
        node = (
            WorksheetBuilder("Bars")
            .mark_type("bar")
            .rows("X")
            .columns("Y")
            .build()
        )
        style = node.find("style")
        assert style is not None
        assert style.get("mark") == "bar"

    def test_automatic_mark_no_style(self):
        node = (
            WorksheetBuilder("Auto")
            .mark_type(MarkType.AUTOMATIC)
            .rows("X")
            .columns("Y")
            .build()
        )
        style = node.find("style")
        assert style is None

    def test_multiple_shelf_fields(self):
        node = (
            WorksheetBuilder("Multi")
            .rows("Region", "Segment")
            .columns("SUM(Sales)", "SUM(Profit)")
            .build()
        )
        assert node.find("rows").text == "[Region], [Segment]"
        assert node.find("cols").text == "[SUM(Sales)], [SUM(Profit)]"

    def test_all_mark_channels(self):
        node = (
            WorksheetBuilder("Full")
            .rows("X")
            .columns("Y")
            .color("A")
            .size("B")
            .detail("C")
            .tooltip("D")
            .label("E")
            .build()
        )
        marks = node.find("marks")
        assert marks.find("color").text == "[A]"
        assert marks.find("size").text == "[B]"
        assert marks.find("detail").text == "[C]"
        assert marks.find("tooltip").text == "[D]"
        assert marks.find("label").text == "[E]"

    def test_filter_categorical(self):
        node = (
            WorksheetBuilder("Filtered")
            .rows("Region")
            .columns("SUM(Sales)")
            .filter("Year", values=[2024, 2025])
            .build()
        )
        filt = node.find("filters/filter")
        assert filt is not None
        assert filt.get("class") == "categorical"
        assert filt.get("field") == "[Year]"
        values = [v.text for v in filt.findall("values/value")]
        assert values == ["2024", "2025"]

    def test_filter_range(self):
        node = (
            WorksheetBuilder("Ranged")
            .rows("Region")
            .columns("SUM(Sales)")
            .filter("Sales", minimum=100, maximum=1000)
            .build()
        )
        filt = node.find("filters/filter")
        assert filt.get("class") == "range"
        assert filt.get("min") == "100"
        assert filt.get("max") == "1000"

    def test_sort_specification(self):
        node = (
            WorksheetBuilder("Sorted")
            .rows("Region")
            .columns("SUM(Sales)")
            .sort("SUM(Sales)", descending=True)
            .build()
        )
        sort = node.find("sorts/sort")
        assert sort is not None
        assert sort.get("field") == "[SUM(Sales)]"
        assert sort.get("direction") == "DESC"

    def test_title(self):
        node = (
            WorksheetBuilder("Sheet")
            .rows("X")
            .columns("Y")
            .title("My Title")
            .build()
        )
        title = node.find("title")
        assert title is not None
        assert title.text == "My Title"

    def test_empty_worksheet_error(self):
        with pytest.raises(InvalidWorkbookError, match="no rows or columns"):
            WorksheetBuilder("Empty").build()

    def test_chained_rows_accumulate(self):
        node = (
            WorksheetBuilder("Chain")
            .rows("A")
            .rows("B")
            .columns("C")
            .build()
        )
        assert node.find("rows").text == "[A], [B]"


# ── DashboardBuilder ──────────────────────────────────────────────────────


class TestDashboardBuilder:
    def test_basic_two_zones(self):
        node = (
            DashboardBuilder("Dash", width=1200, height=800)
            .sheet("Sheet1", x=0, y=0, w=600, h=800)
            .sheet("Sheet2", x=600, y=0, w=600, h=800)
            .build()
        )
        assert node.tag == "dashboard"
        assert node.get("name") == "Dash"

        size = node.find("size")
        assert size.get("maxwidth") == "1200"
        assert size.get("maxheight") == "800"

        zones = node.findall("zones/zone")
        assert len(zones) == 2
        assert zones[0].get("name") == "Sheet1"
        assert zones[0].get("type") == "sheet"
        assert zones[0].get("x") == "0"
        assert zones[1].get("name") == "Sheet2"
        assert zones[1].get("x") == "600"

    def test_action_filter(self):
        node = (
            DashboardBuilder("Dash")
            .sheet("A", x=0, y=0, w=600, h=400)
            .sheet("B", x=600, y=0, w=600, h=400)
            .action("filter", source="A", target="B", field="Region")
            .build()
        )
        action = node.find("actions/action")
        assert action is not None
        assert action.get("type") == "filter"
        assert action.get("source-sheet") == "A"
        assert action.get("target-sheet") == "B"
        assert action.get("field") == "[Region]"

    def test_action_highlight(self):
        node = (
            DashboardBuilder("Dash")
            .sheet("A", x=0, y=0, w=600, h=400)
            .sheet("B", x=600, y=0, w=600, h=400)
            .action("highlight", source="A", target="B")
            .build()
        )
        action = node.find("actions/action")
        assert action.get("type") == "highlight"

    def test_text_zone(self):
        node = (
            DashboardBuilder("Dash")
            .text("Hello World", x=0, y=0, w=1200, h=50)
            .build()
        )
        zone = node.find("zones/zone")
        assert zone.get("type") == "text"
        assert zone.text == "Hello World"

    def test_phone_layout(self):
        node = (
            DashboardBuilder("Dash")
            .sheet("S", x=0, y=0, w=1200, h=800)
            .phone_layout([("S", 0, 0, 320, 300)])
            .build()
        )
        layouts = node.find("devicelayouts")
        assert layouts is not None
        phone = layouts.find("devicelayout[@name='phone']")
        assert phone is not None
        zone = phone.find("zones/zone")
        assert zone.get("name") == "S"
        assert zone.get("w") == "320"

    def test_tablet_layout(self):
        node = (
            DashboardBuilder("Dash")
            .sheet("S", x=0, y=0, w=1200, h=800)
            .tablet_layout([("S", 0, 0, 768, 500)])
            .build()
        )
        tablet = node.find("devicelayouts/devicelayout[@name='tablet']")
        assert tablet is not None

    def test_blank_zone(self):
        node = DashboardBuilder("Dash").blank(x=0, y=0, w=100, h=50).build()
        zone = node.find("zones/zone")
        assert zone.get("type") == "blank"

    def test_filter_zone(self):
        node = (
            DashboardBuilder("Dash")
            .filter_zone("Year", x=0, y=0, w=200, h=30)
            .build()
        )
        zone = node.find("zones/zone")
        assert zone.get("type") == "filter"
        assert zone.get("name") == "Year"


# ── Spec Loader ────────────────────────────────────────────────────────────


class TestSpecLoader:
    MINIMAL_SPEC = {
        "datasources": [
            {
                "caption": "Sales",
                "connection": {"class": "hyper", "dbname": "sales.hyper"},
                "columns": [
                    {"caption": "Region", "datatype": "string", "role": "dimension"},
                    {"caption": "Sales", "datatype": "real", "role": "measure"},
                ],
            }
        ],
        "worksheets": [
            {
                "name": "Chart",
                "datasource": "Sales",
                "mark_type": "bar",
                "rows": ["Region"],
                "columns": ["SUM(Sales)"],
            }
        ],
    }

    def test_minimal_spec_dict(self):
        wb = from_spec(self.MINIMAL_SPEC)
        assert isinstance(wb, Workbook)
        assert len(wb.datasources) == 1
        assert len(wb.worksheets) == 1
        assert wb.worksheets[0].name == "Chart"
        assert wb.datasources[0].caption == "Sales"

    def test_spec_with_dashboard(self):
        spec = {
            **self.MINIMAL_SPEC,
            "dashboards": [
                {
                    "name": "Overview",
                    "width": 1000,
                    "height": 600,
                    "zones": [
                        {"worksheet": "Chart", "x": 0, "y": 0, "w": 1000, "h": 600},
                    ],
                }
            ],
        }
        wb = from_spec(spec)
        assert len(wb.dashboards) == 1
        assert wb.dashboards[0].name == "Overview"

    def test_spec_with_calculated_fields(self):
        spec = {
            "datasources": [
                {
                    "caption": "Data",
                    "columns": [
                        {"caption": "Sales", "datatype": "real", "role": "measure"},
                        {"caption": "Cost", "datatype": "real", "role": "measure"},
                    ],
                    "calculated_fields": [
                        {"caption": "Margin", "formula": "[Sales] - [Cost]"},
                    ],
                }
            ],
            "worksheets": [
                {
                    "name": "Sheet",
                    "datasource": "Data",
                    "rows": ["Margin"],
                    "columns": ["SUM(Sales)"],
                }
            ],
        }
        wb = from_spec(spec)
        ds = wb.datasources[0]
        assert len(ds.calculated_fields) == 1
        assert ds.calculated_fields[0].caption == "Margin"

    def test_spec_with_filters_and_sorts(self):
        spec = {
            "datasources": [
                {
                    "caption": "Sales",
                    "columns": [
                        {"caption": "Region", "datatype": "string", "role": "dimension"},
                        {"caption": "Sales", "datatype": "real", "role": "measure"},
                        {"caption": "Year", "datatype": "string", "role": "dimension"},
                    ],
                }
            ],
            "worksheets": [
                {
                    "name": "Chart",
                    "datasource": "Sales",
                    "rows": ["Region"],
                    "columns": ["SUM(Sales)"],
                    "filters": [{"field": "Year", "values": ["2024", "2025"]}],
                    "sort": [{"field": "SUM(Sales)", "descending": True}],
                }
            ],
        }
        wb = from_spec(spec)
        ws = wb.worksheets[0]
        assert len(ws.filters) == 1
        assert ws.filters[0].field == "Year"

    def test_spec_from_json_file(self, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(self.MINIMAL_SPEC))
        wb = from_spec(spec_file)
        assert len(wb.worksheets) == 1

    def test_spec_single_string_shelf(self):
        """Shelves accept a single string instead of a list."""
        spec = {
            "datasources": [
                {
                    "caption": "D",
                    "columns": [
                        {"caption": "X", "role": "dimension"},
                        {"caption": "Y", "role": "measure", "datatype": "real"},
                    ],
                }
            ],
            "worksheets": [
                {
                    "name": "S",
                    "datasource": "D",
                    "rows": "X",
                    "columns": "SUM(Y)",
                }
            ],
        }
        wb = from_spec(spec)
        assert len(wb.worksheets) == 1


# ── Integration: round-trip build → save → reopen ─────────────────────────


class TestBuildRoundTrip:
    def test_build_save_reopen_bar_chart(self, tmp_path):
        wb = Workbook.new()

        ds_node = (
            DatasourceBuilder("Sales")
            .connection("hyper", dbname="Data/sales.hyper")
            .column("Region", DataType.STRING, Role.DIMENSION)
            .column("Sales", DataType.REAL, Role.MEASURE)
            .build()
        )
        ws_node = (
            WorksheetBuilder("Revenue by Region")
            .datasource("hyper.sales")
            .mark_type("bar")
            .rows("Region")
            .columns("SUM(Sales)")
            .label("SUM(Sales)")
            .build()
        )

        wb.xml_root.find("datasources").append(ds_node)
        wb.xml_root.find("worksheets").append(ws_node)
        wb._load_tree(wb.xml_tree)

        out = tmp_path / "test.twb"
        wb.save_as(out)
        assert out.exists()

        # Reopen
        wb2 = Workbook.open(out)
        assert len(wb2.datasources) == 1
        assert wb2.datasources[0].caption == "Sales"
        assert len(wb2.worksheets) == 1
        assert wb2.worksheets[0].name == "Revenue by Region"

    def test_build_save_reopen_with_dashboard(self, tmp_path):
        wb = Workbook.new()

        ds_node = (
            DatasourceBuilder("Data")
            .connection("hyper", dbname="data.hyper")
            .column("A", DataType.STRING, Role.DIMENSION)
            .column("B", DataType.REAL, Role.MEASURE)
            .build()
        )
        ws1 = (
            WorksheetBuilder("Sheet1")
            .datasource("hyper.data")
            .rows("A")
            .columns("SUM(B)")
            .build()
        )
        ws2 = (
            WorksheetBuilder("Sheet2")
            .datasource("hyper.data")
            .mark_type("line")
            .columns("A")
            .rows("SUM(B)")
            .build()
        )
        dash = (
            DashboardBuilder("Dashboard", width=1200, height=800)
            .sheet("Sheet1", x=0, y=0, w=600, h=800)
            .sheet("Sheet2", x=600, y=0, w=600, h=800)
            .action("filter", source="Sheet1", target="Sheet2", field="A")
            .build()
        )

        wb.xml_root.find("datasources").append(ds_node)
        wb.xml_root.find("worksheets").append(ws1)
        wb.xml_root.find("worksheets").append(ws2)
        wb.xml_root.find("dashboards").append(dash)
        wb._load_tree(wb.xml_tree)

        out = tmp_path / "dashboard.twb"
        wb.save_as(out)

        wb2 = Workbook.open(out)
        assert len(wb2.worksheets) == 2
        assert len(wb2.dashboards) == 1
        assert wb2.dashboards[0].name == "Dashboard"
        assert len(wb2.dashboards[0].actions) == 1

    def test_from_spec_save_reopen(self, tmp_path):
        spec = {
            "datasources": [
                {
                    "caption": "Sales",
                    "connection": {"class": "hyper", "dbname": "Data/sales.hyper"},
                    "columns": [
                        {"caption": "Region", "datatype": "string", "role": "dimension"},
                        {"caption": "Sales", "datatype": "real", "role": "measure"},
                    ],
                }
            ],
            "worksheets": [
                {
                    "name": "Chart",
                    "datasource": "Sales",
                    "mark_type": "bar",
                    "rows": ["Region"],
                    "columns": ["SUM(Sales)"],
                }
            ],
        }
        wb = from_spec(spec)
        out = tmp_path / "from_spec.twb"
        wb.save_as(out)

        wb2 = Workbook.open(out)
        assert wb2.worksheets[0].name == "Chart"
        assert wb2.datasources[0].caption == "Sales"

    def test_quick_chart_save_reopen(self, tmp_path):
        wb = quick_chart(
            dimension="Region",
            measure="Sales",
            chart_type="bar",
            color="Category",
        )
        out = tmp_path / "quick.twb"
        wb.save_as(out)

        wb2 = Workbook.open(out)
        assert len(wb2.worksheets) == 1
        assert len(wb2.datasources) == 1

    def test_quick_dashboard_save_reopen(self, tmp_path):
        wb = quick_dashboard(
            caption="Sales",
            worksheets=[
                {"name": "Bar", "chart_type": "bar", "dimension": "Region", "measure": "Sales"},
                {"name": "Line", "chart_type": "line", "dimension": "Region", "measure": "Sales"},
            ],
            columns=[
                ("Region", "string", "dimension"),
                ("Sales", "real", "measure"),
            ],
        )
        out = tmp_path / "quick_dash.twb"
        wb.save_as(out)

        wb2 = Workbook.open(out)
        assert len(wb2.worksheets) == 2
        assert len(wb2.dashboards) == 1

    def test_builder_plus_mutation(self, tmp_path):
        """Build a workbook, then add a calculated field via the existing API."""
        wb = from_spec({
            "datasources": [
                {
                    "caption": "Data",
                    "columns": [
                        {"caption": "Sales", "datatype": "real", "role": "measure"},
                        {"caption": "Cost", "datatype": "real", "role": "measure"},
                    ],
                }
            ],
            "worksheets": [
                {
                    "name": "Sheet",
                    "datasource": "Data",
                    "rows": ["SUM(Sales)"],
                    "columns": ["SUM(Cost)"],
                }
            ],
        })

        # Now use the existing pytableau API to mutate
        ds = wb.datasources[0]
        ds.add_calculated_field("Profit", "[Sales] - [Cost]")
        assert ds.get_field("Profit") is not None

        out = tmp_path / "mutated.twb"
        wb.save_as(out)
        wb2 = Workbook.open(out)
        assert wb2.datasources[0].get_field("Profit") is not None
