"""Convenience shortcuts for common workbook-building patterns.

Example::

    from pytableau.build import quick_chart

    wb = quick_chart(
        caption="Sales Data",
        chart_type="bar",
        dimension="Region",
        measure="Sales",
        color="Product Category",
        title="Revenue by Region",
        columns=[
            ("Region", "string", "dimension"),
            ("Product Category", "string", "dimension"),
            ("Sales", "real", "measure"),
        ],
    )
    wb.save_as("chart.twb")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pytableau.constants import DataType, Role

from .datasource import DatasourceBuilder
from .worksheet import WorksheetBuilder

if TYPE_CHECKING:
    pass


def quick_chart(
    *,
    caption: str = "Data",
    chart_type: str = "bar",
    dimension: str,
    measure: str,
    color: str | None = None,
    size: str | None = None,
    label: bool = True,
    title: str | None = None,
    columns: list[tuple[str, str, str]] | None = None,
    datasource_builder: DatasourceBuilder | None = None,
) -> Any:
    """Build a single-worksheet workbook in one call.

    This is the fastest path from "I have data" to "I have a .twb".

    Args:
        caption: Datasource caption.
        chart_type: Mark type (``"bar"``, ``"line"``, ``"circle"``, etc.).
        dimension: Field name for the dimension axis.
        measure: Field name for the measure axis.
        color: Optional field for the color channel.
        size: Optional field for the size channel.
        label: Whether to label marks with the measure value.
        title: Worksheet title.
        columns: Column definitions as ``(caption, datatype, role)`` tuples.
            If omitted, the dimension/measure/color/size fields are inferred
            with default types.
        datasource_builder: Pre-built :class:`DatasourceBuilder` to use
            instead of auto-generating one.

    Returns:
        A :class:`~pytableau.core.workbook.Workbook` instance.
    """
    from pytableau.core.workbook import Workbook

    # Build or use provided datasource
    if datasource_builder is not None:
        ds_builder = datasource_builder
    else:
        ds_builder = DatasourceBuilder(caption)
        ds_builder.connection("hyper", dbname=f"Data/{DatasourceBuilder(caption).name.split('.')[-1]}.hyper")

        if columns:
            for col_caption, col_dt, col_role in columns:
                ds_builder.column(
                    col_caption,
                    DataType(col_dt) if col_dt in DataType.__members__.values() else DataType.STRING,
                    Role(col_role) if col_role in Role.__members__.values() else Role.DIMENSION,
                )
        else:
            # Infer minimal columns from the field names
            ds_builder.column(dimension, DataType.STRING, Role.DIMENSION)
            ds_builder.column(measure, DataType.REAL, Role.MEASURE)
            if color and color not in {dimension, measure}:
                ds_builder.column(color, DataType.STRING, Role.DIMENSION)
            if size and size not in {dimension, measure, color}:
                ds_builder.column(size, DataType.REAL, Role.MEASURE)

    ds_name = ds_builder.name

    # Build worksheet
    ws_title = title or f"{measure} by {dimension}"
    ws = WorksheetBuilder(ws_title)
    ws.datasource(ds_name)
    ws.mark_type(chart_type)

    # For bar charts: dimension on rows, measure on cols (horizontal bars)
    # For most others: dimension on cols, measure on rows
    if chart_type in ("bar",):
        ws.rows(dimension)
        ws.columns(f"SUM({measure})")
    else:
        ws.columns(dimension)
        ws.rows(f"SUM({measure})")

    if color:
        ws.color(color)
    if size:
        ws.size(f"SUM({size})")
    if label:
        ws.label(f"SUM({measure})")

    # Assemble workbook
    wb = Workbook.new()
    ds_node = ds_builder.build()
    ws_node = ws.build()

    # Attach elements
    ds_container = wb.xml_root.find("datasources")
    ds_container.append(ds_node)

    ws_container = wb.xml_root.find("worksheets")
    ws_container.append(ws_node)

    # Re-parse
    wb._load_tree(wb.xml_tree)

    return wb


def quick_dashboard(
    *,
    caption: str = "Data",
    worksheets: list[dict[str, Any]],
    dashboard_name: str = "Dashboard",
    width: int = 1200,
    height: int = 800,
    columns: list[tuple[str, str, str]] | None = None,
) -> Any:
    """Build a multi-worksheet dashboard workbook.

    Args:
        caption: Datasource caption.
        worksheets: List of worksheet specs, each a dict with keys:
            ``name``, ``chart_type``, ``dimension``, ``measure``,
            and optionally ``color``, ``size``.
        dashboard_name: Name for the dashboard tab.
        width: Dashboard width.
        height: Dashboard height.
        columns: Shared column definitions for the datasource.

    Returns:
        A :class:`~pytableau.core.workbook.Workbook` instance.
    """
    from pytableau.build.dashboard import DashboardBuilder
    from pytableau.core.workbook import Workbook

    # Build shared datasource
    ds_builder = DatasourceBuilder(caption)
    ds_builder.connection("hyper", dbname=f"Data/{DatasourceBuilder(caption).name.split('.')[-1]}.hyper")

    if columns:
        for col_caption, col_dt, col_role in columns:
            ds_builder.column(col_caption, col_dt, col_role)
    else:
        # Infer from all worksheet specs
        seen: set[str] = set()
        for ws_spec in worksheets:
            for field_name in [ws_spec["dimension"], ws_spec["measure"]]:
                if field_name not in seen:
                    seen.add(field_name)
                    role = "measure" if field_name == ws_spec["measure"] else "dimension"
                    dt = DataType.REAL if role == "measure" else DataType.STRING
                    ds_builder.column(field_name, dt, role)
            for extra in [ws_spec.get("color"), ws_spec.get("size")]:
                if extra and extra not in seen:
                    seen.add(extra)
                    ds_builder.column(extra, DataType.STRING, Role.DIMENSION)

    ds_name = ds_builder.name

    # Build worksheets and dashboard zones
    ws_nodes = []
    n = len(worksheets)
    zone_w = width // min(n, 2)
    zone_h = height // ((n + 1) // 2) if n > 2 else height

    dash_builder = DashboardBuilder(dashboard_name, width=width, height=height)

    for i, ws_spec in enumerate(worksheets):
        ws_name = ws_spec.get("name", f"Sheet {i + 1}")
        chart_type = ws_spec.get("chart_type", "bar")
        dim = ws_spec["dimension"]
        meas = ws_spec["measure"]

        ws = WorksheetBuilder(ws_name)
        ws.datasource(ds_name)
        ws.mark_type(chart_type)

        if chart_type in ("bar",):
            ws.rows(dim)
            ws.columns(f"SUM({meas})")
        else:
            ws.columns(dim)
            ws.rows(f"SUM({meas})")

        if ws_spec.get("color"):
            ws.color(ws_spec["color"])

        ws_nodes.append(ws.build())

        # Auto-layout zones in a grid
        col = i % 2
        row = i // 2
        dash_builder.sheet(
            ws_name,
            x=col * zone_w,
            y=row * zone_h,
            w=zone_w,
            h=zone_h,
        )

    # Assemble
    wb = Workbook.new()
    ds_container = wb.xml_root.find("datasources")
    ds_container.append(ds_builder.build())

    ws_container = wb.xml_root.find("worksheets")
    for node in ws_nodes:
        ws_container.append(node)

    dash_container = wb.xml_root.find("dashboards")
    dash_container.append(dash_builder.build())

    wb._load_tree(wb.xml_tree)
    return wb
