"""Phase 1 read/inspect and phase 2 mutation behavior tests."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from pytableau.constants import FilterType
from pytableau.core.fields import FieldReference
from pytableau.core.filters import CategoricalFilter
from pytableau.core.workbook import Workbook
from pytableau.inspect import LineageField


def _write_sample_twb(path: Path) -> None:
    workbook = etree.Element(
        "workbook",
        attrib={
            "source-build": "20241.24.0312.0830",
            "source-platform": "test",
        },
    )

    datasources = etree.SubElement(workbook, "datasources")
    datasource = etree.SubElement(
        datasources,
        "datasource",
        attrib={
            "name": "Sales",
            "caption": "Sales Data",
        },
    )
    etree.SubElement(
        datasource,
        "connection",
        attrib={
            "class": "sqlserver",
            "server": "localhost",
            "dbname": "analytics",
            "username": "alice",
            "port": "1433",
        },
    )
    relations = etree.SubElement(datasource, "relations")
    etree.SubElement(relations, "relation", attrib={"type": "table", "table": "Orders"})

    columns = etree.SubElement(datasource, "columns")
    etree.SubElement(
        columns,
        "column",
        attrib={
            "name": "sales_id",
            "caption": "Sales ID",
            "datatype": "integer",
            "role": "dimension",
        },
    )
    etree.SubElement(
        columns,
        "column",
        attrib={"name": "region", "caption": "Region", "datatype": "string", "role": "dimension"},
    )
    calc = etree.SubElement(
        columns,
        "column",
        attrib={
            "name": "calc_1",
            "caption": "Margin",
            "datatype": "real",
            "role": "measure",
        },
    )
    etree.SubElement(
        calc, "calculation", attrib={"class": "tableau", "formula": "[Sales] / [Cost] + [Region]"}
    )

    parameters = etree.SubElement(
        datasources,
        "datasource",
        attrib={"name": "Parameters", "caption": "Parameters"},
    )
    parameter_columns = etree.SubElement(parameters, "columns")
    parameter = etree.SubElement(
        parameter_columns,
        "column",
        attrib={
            "name": "p_threshold",
            "caption": "Threshold",
            "datatype": "real",
            "role": "dimension",
            "param-domain-type": "range",
            "value": "10",
        },
    )
    etree.SubElement(
        parameter,
        "domain",
        attrib={
            "range-min": "0",
            "range-max": "100",
            "range-step": "1",
        },
    )

    worksheets = etree.SubElement(workbook, "worksheets")
    worksheet = etree.SubElement(worksheets, "worksheet", attrib={"name": "Overview"})
    etree.SubElement(worksheet, "rows").text = "[Sales ID], [Region]"
    etree.SubElement(worksheet, "cols").text = "[Margin]"

    marks = etree.SubElement(worksheet, "marks")
    etree.SubElement(marks, "color").text = "[Region]"
    etree.SubElement(marks, "detail").text = "[Sales ID]"

    ds_deps = etree.SubElement(worksheet, "datasource-dependencies")
    etree.SubElement(ds_deps, "datasource", attrib={"name": "Sales"})

    filters = etree.SubElement(worksheet, "filters")
    category_filter = etree.SubElement(
        filters,
        "filter",
        attrib={"class": "categorical", "field": "[Region]"},
    )
    values = etree.SubElement(category_filter, "values")
    etree.SubElement(values, "value").text = "North"

    dashboards = etree.SubElement(workbook, "dashboards")
    dashboard = etree.SubElement(dashboards, "dashboard", attrib={"name": "Dashboard"})
    etree.SubElement(
        dashboard, "size", attrib={"type": "automatic", "width": "1200", "height": "800"}
    )
    root_zone = etree.SubElement(
        dashboard,
        "zone",
        attrib={"type": "layout-basic", "name": "root", "x": "0", "y": "0", "w": "100", "h": "100"},
    )
    etree.SubElement(
        root_zone,
        "zone",
        attrib={
            "type": "worksheet",
            "name": "overview",
            "x": "0",
            "y": "0",
            "w": "100",
            "h": "100",
        },
    )
    actions = etree.SubElement(dashboard, "actions")
    etree.SubElement(
        actions,
        "action",
        attrib={
            "type": "filter",
            "name": "FilterByRegion",
            "field": "[Region]",
            "target-sheet": "Overview",
        },
    )

    path.write_text(
        etree.tostring(workbook, encoding="utf-8", xml_declaration=True, pretty_print=True).decode(
            "utf-8"
        ),
        encoding="utf-8",
    )


def test_read_workbook_catalog(tmp_path: Path) -> None:
    path = tmp_path / "sample.twb"
    _write_sample_twb(path)

    workbook = Workbook.open(path)
    assert workbook.version == "2024.1"
    assert list(workbook.datasources.names) == ["Sales"]
    assert list(workbook.worksheets.names) == ["Overview"]
    assert list(workbook.dashboards.names) == ["Dashboard"]

    sales = workbook.datasources["Sales"]
    assert sales.name == "Sales"
    assert len(sales.all_fields) == 3
    assert len(sales.calculated_fields) == 1
    assert sales.calculated_fields[0].caption == "Margin"

    assert workbook.parameters is not None
    assert len(workbook.parameters.parameters) == 1
    assert workbook.parameters.parameters[0].caption == "Threshold"

    payload = workbook.catalog().to_dict()
    assert payload["datasource_count"] == 1
    assert payload["datasources"][0]["name"] == "Sales"
    assert payload["datasources"][0]["calculated_fields"] == ["Margin"]


def test_worksheet_reads_shelves_filters_marks(tmp_path: Path) -> None:
    path = tmp_path / "sample.twb"
    _write_sample_twb(path)
    workbook = Workbook.open(path)
    worksheet = workbook.worksheets["Overview"]

    assert worksheet.rows == [FieldReference("Sales ID"), FieldReference("Region")]
    assert worksheet.cols == [FieldReference("Margin")]
    assert worksheet.marks.color == [FieldReference("Region")]
    assert worksheet.marks.detail == [FieldReference("Sales ID")]
    assert len(worksheet.filters) == 1
    assert isinstance(worksheet.filters[0], CategoricalFilter)
    assert worksheet.filters[0].values == ["North"]


def test_filter_mutations_and_catalog_updates(tmp_path: Path) -> None:
    path = tmp_path / "sample.twb"
    _write_sample_twb(path)
    workbook = Workbook.open(path)
    worksheet = workbook.worksheets["Overview"]

    original_filter_count = len(worksheet.filters)
    created = worksheet.add_filter("Sales ID", FilterType.CATEGORICAL, values=["A", "B"])
    assert isinstance(created, CategoricalFilter)
    assert len(worksheet.filters) == original_filter_count + 1
    assert created.field == "Sales ID"
    assert created.values == ["A", "B"]

    removed = worksheet.remove_filter("Sales ID")
    assert removed == 1
    assert len(worksheet.filters) == original_filter_count


def test_datasource_mutations_propagate(tmp_path: Path) -> None:
    path = tmp_path / "sample.twb"
    _write_sample_twb(path)
    workbook = Workbook.open(path)
    sales = workbook.datasources["Sales"]
    worksheet = workbook.worksheets["Overview"]
    dashboard = workbook.dashboards["Dashboard"]

    sales.rename_field("Region", "Territory")
    assert worksheet.rows == [FieldReference("Sales ID"), FieldReference("Territory")]
    assert dashboard.actions[0].fields == ["Territory"]
    assert "Territory" in sales.calculated_fields[0].formula
    assert "Region" not in sales.calculated_fields[0].formula

    sales.remove_field("Territory")
    assert sales.get_field("Territory") is None
    assert not any(ref.name == "Territory" for ref in worksheet.rows)
    assert not any(ref.name == "Territory" for ref in worksheet.cols)
    assert not any(ref.name == "Territory" for ref in worksheet.marks.color)
    assert not any(ref.name == "Territory" for ref in worksheet.marks.detail)
    assert dashboard.actions[0].fields == []


def _write_lineage_twb(path: Path) -> None:
    workbook = etree.Element(
        "workbook",
        attrib={
            "source-build": "20241.24.0312.0830",
            "source-platform": "test",
        },
    )

    datasources = etree.SubElement(workbook, "datasources")
    datasource = etree.SubElement(
        datasources,
        "datasource",
        attrib={
            "name": "Sales",
            "caption": "Sales Data",
        },
    )
    etree.SubElement(
        datasource,
        "connection",
        attrib={
            "class": "sqlserver",
            "server": "localhost",
            "dbname": "analytics",
        },
    )
    columns = etree.SubElement(datasource, "columns")
    etree.SubElement(
        columns,
        "column",
        attrib={
            "name": "sales_id",
            "caption": "Sales ID",
            "datatype": "integer",
            "role": "dimension",
        },
    )
    etree.SubElement(
        columns,
        "column",
        attrib={"name": "cost", "caption": "Cost", "datatype": "real", "role": "dimension"},
    )
    etree.SubElement(
        columns,
        "column",
        attrib={"name": "revenue", "caption": "Revenue", "datatype": "real", "role": "measure"},
    )
    base = etree.SubElement(
        columns,
        "column",
        attrib={"name": "gross", "caption": "Gross Profit", "datatype": "real", "role": "measure"},
    )
    etree.SubElement(
        base, "calculation", attrib={"class": "tableau", "formula": "[Sales].[Revenue] - [Cost]"}
    )
    derived = etree.SubElement(
        columns,
        "column",
        attrib={"name": "margin", "caption": "Margin", "datatype": "real", "role": "measure"},
    )
    etree.SubElement(
        derived, "calculation", attrib={"class": "tableau", "formula": "[Gross Profit] / [Cost]"}
    )

    worksheets = etree.SubElement(workbook, "worksheets")
    etree.SubElement(worksheets, "worksheet", name="Overview")

    dashboards = etree.SubElement(workbook, "dashboards")
    etree.SubElement(dashboards, "dashboard", name="Dashboard")

    path.write_text(
        etree.tostring(workbook, encoding="utf-8", xml_declaration=True, pretty_print=True).decode(
            "utf-8"
        ),
        encoding="utf-8",
    )


def test_field_lineage_reports_calculated_dependencies(tmp_path: Path) -> None:
    path = tmp_path / "lineage.twb"
    _write_lineage_twb(path)

    workbook = Workbook.open(path)
    lineage = workbook.lineage()

    gross = lineage.for_field("Gross Profit", datasource="Sales")
    assert gross is not None
    assert gross.depends_on == [
        # Parsed dependencies preserve datasource-qualified and local field references.
        LineageField(datasource="Sales", field="Revenue"),
        LineageField(datasource=None, field="Cost"),
    ]

    margin = lineage.for_field("Margin", datasource="Sales")
    assert margin is not None
    assert margin.depends_on == [
        LineageField(datasource=None, field="Gross Profit"),
        LineageField(datasource=None, field="Cost"),
    ]
    assert lineage.to_dict()["Sales::Margin"] == ["[Gross Profit]", "[Cost]"]


def test_workbook_report_generates_markdown(tmp_path: Path) -> None:
    path = tmp_path / "lineage.twb"
    _write_sample_twb(path)
    workbook = Workbook.open(path)

    markdown = workbook.report().to_markdown()
    assert "# Workbook Report" in markdown
    assert "## Datasources" in markdown
    assert "Sales" in markdown
    assert "## Calculated Field Lineage" in markdown
    assert "Sales::Margin" in markdown


def test_roundtrip_after_mutations(tmp_path: Path) -> None:
    path = tmp_path / "sample.twb"
    _write_sample_twb(path)
    workbook = Workbook.open(path)

    sales = workbook.datasources["Sales"]
    sales.rename_field("Region", "Territory")
    output = tmp_path / "renamed.twb"
    workbook.save_as(output)

    reopened = Workbook.open(output)
    assert reopened.version == "2024.1"
    assert reopened.worksheets["Overview"].rows[1] == FieldReference("Territory")
    assert reopened.datasources["Sales"].get_field("Territory") is not None


def test_connection_mutation(tmp_path: Path) -> None:
    path = tmp_path / "sample.twb"
    _write_sample_twb(path)

    workbook = Workbook.open(path)
    sales = workbook.datasources["Sales"]

    sales.swap_connection(
        server="analytics.internal",
        dbname="analytics_reporting",
        username="ci-bot",
        port=55443,
        class_="postgres",
    )

    connection = sales.connections[0]
    assert connection.server == "analytics.internal"
    assert connection.dbname == "analytics_reporting"
    assert connection.username == "ci-bot"
    assert connection.port == 55443
    assert connection.class_ == "postgres"


def test_parameter_mutation(tmp_path: Path) -> None:
    path = tmp_path / "sample.twb"
    _write_sample_twb(path)

    workbook = Workbook.open(path)
    params = workbook.parameters
    assert params is not None
    threshold = params.parameters[0]

    threshold.value = 20
    assert threshold.value == 20
    threshold.domain_type = "list"
    threshold.allowable_values = ["10", "20", "30"]
    assert threshold.allowable_values == ["10", "20", "30"]


def test_add_calculated_field(tmp_path: Path) -> None:
    path = tmp_path / "sample.twb"
    _write_sample_twb(path)

    workbook = Workbook.open(path)
    sales = workbook.datasources["Sales"]
    created = sales.add_calculated_field(
        caption="Sales Minus Cost",
        formula="[Sales] / [Cost]",
        datatype="real",
        role="measure",
    )

    assert created.caption == "Sales Minus Cost"
    assert any(field.caption == "Sales Minus Cost" for field in sales.calculated_fields)
    assert len(sales.calculated_fields) == 2
