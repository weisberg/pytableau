"""Phase 1 read/inspect and phase 2 mutation behavior tests."""

from __future__ import annotations

from pathlib import Path
from lxml import etree

from pytableau.constants import FilterType
from pytableau.core.fields import FieldReference
from pytableau.core.filters import CategoricalFilter
from pytableau.core.workbook import Workbook


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
        attrib={"name": "sales_id", "caption": "Sales ID", "datatype": "integer", "role": "dimension"},
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
    etree.SubElement(calc, "calculation", attrib={"class": "tableau", "formula": "[Sales] / [Cost] + [Region]"})

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
    etree.SubElement(dashboard, "size", attrib={"type": "automatic", "width": "1200", "height": "800"})
    root_zone = etree.SubElement(
        dashboard,
        "zone",
        attrib={"type": "layout-basic", "name": "root", "x": "0", "y": "0", "w": "100", "h": "100"},
    )
    etree.SubElement(
        root_zone,
        "zone",
        attrib={"type": "worksheet", "name": "overview", "x": "0", "y": "0", "w": "100", "h": "100"},
    )
    actions = etree.SubElement(dashboard, "actions")
    etree.SubElement(
        actions,
        "action",
        attrib={"type": "filter", "name": "FilterByRegion", "field": "[Region]", "target-sheet": "Overview"},
    )

    path.write_text(
        etree.tostring(workbook, encoding="utf-8", xml_declaration=True, pretty_print=True).decode("utf-8"),
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
