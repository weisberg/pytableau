"""Build complete workbooks from YAML or dict specifications.

Example::

    from pytableau.build import from_spec

    wb = from_spec("workbook_spec.yml")
    wb.save_as("output.twbx")

Or from a Python dict::

    wb = from_spec({
        "datasources": [{
            "caption": "Sales",
            "connection": {"class": "hyper", "dbname": "sales.hyper"},
            "columns": [
                {"caption": "Region", "datatype": "string", "role": "dimension"},
                {"caption": "Sales", "datatype": "real", "role": "measure"},
            ],
        }],
        "worksheets": [{
            "name": "Chart",
            "datasource": "Sales",
            "mark_type": "bar",
            "rows": ["Region"],
            "columns": ["SUM(Sales)"],
        }],
    })
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pytableau.constants import DataType, FilterType, Role
from pytableau.exceptions import InvalidWorkbookError

from .dashboard import DashboardBuilder
from .datasource import DatasourceBuilder
from .worksheet import WorksheetBuilder


def _load_data(spec: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Resolve a spec to a Python dict."""
    if isinstance(spec, dict):
        return spec

    path = Path(spec) if not isinstance(spec, Path) else spec

    # Try as a file path first
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        # Treat as a raw YAML/JSON string
        text = str(spec)

    # Try YAML first (superset of JSON)
    try:
        import yaml

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except ImportError:
        pass
    except Exception:
        pass

    # Fall back to JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    raise InvalidWorkbookError(
        "Could not parse spec. Provide a dict, a path to a YAML/JSON file, "
        "or a YAML/JSON string. For YAML support, install pyyaml."
    )


def _resolve_datatype(raw: str | None) -> DataType:
    """Map spec datatype strings to DataType enum."""
    if raw is None:
        return DataType.STRING
    mapping = {
        "string": DataType.STRING,
        "str": DataType.STRING,
        "text": DataType.STRING,
        "integer": DataType.INTEGER,
        "int": DataType.INTEGER,
        "real": DataType.REAL,
        "float": DataType.REAL,
        "double": DataType.REAL,
        "number": DataType.REAL,
        "boolean": DataType.BOOLEAN,
        "bool": DataType.BOOLEAN,
        "date": DataType.DATE,
        "datetime": DataType.DATETIME,
    }
    return mapping.get(raw.lower().strip(), DataType.STRING)


def _resolve_role(raw: str | None) -> Role:
    """Map spec role strings to Role enum."""
    if raw is None:
        return Role.DIMENSION
    return Role.MEASURE if raw.lower().strip() in {"measure", "meas"} else Role.DIMENSION


def _build_datasource(ds_spec: dict[str, Any]) -> DatasourceBuilder:
    """Build a DatasourceBuilder from a spec dict."""
    caption = ds_spec.get("caption") or ds_spec.get("name", "Data")
    builder = DatasourceBuilder(caption)

    # Connection
    conn = ds_spec.get("connection", {})
    if isinstance(conn, dict):
        cls = conn.pop("class", conn.pop("cls", "hyper"))
        builder.connection(cls, **{k: str(v) for k, v in conn.items()})

    # Columns
    for col in ds_spec.get("columns", []):
        builder.column(
            caption=col["caption"],
            datatype=_resolve_datatype(col.get("datatype")),
            role=_resolve_role(col.get("role")),
            hidden=col.get("hidden", False),
        )

    # Calculated fields
    for calc in ds_spec.get("calculated_fields", []):
        builder.calculated_field(
            caption=calc["caption"],
            formula=calc["formula"],
            datatype=_resolve_datatype(calc.get("datatype", "real")),
            role=_resolve_role(calc.get("role", "measure")),
        )

    return builder


def _build_worksheet(ws_spec: dict[str, Any], ds_internal_name: str | None) -> WorksheetBuilder:
    """Build a WorksheetBuilder from a spec dict."""
    name = ws_spec.get("name", "Sheet")
    builder = WorksheetBuilder(name)

    if ds_internal_name:
        builder.datasource(ds_internal_name)

    # Mark type
    mt = ws_spec.get("mark_type") or ws_spec.get("mark")
    if mt:
        builder.mark_type(str(mt))

    # Shelves — accept either a list or a single string
    def _as_list(val: Any) -> list[str]:
        if val is None:
            return []
        if isinstance(val, str):
            return [val]
        return [str(v) for v in val]

    for field in _as_list(ws_spec.get("rows")):
        builder.rows(field)
    for field in _as_list(ws_spec.get("columns") or ws_spec.get("cols")):
        builder.columns(field)
    for field in _as_list(ws_spec.get("color")):
        builder.color(field)
    for field in _as_list(ws_spec.get("size")):
        builder.size(field)
    for field in _as_list(ws_spec.get("detail")):
        builder.detail(field)
    for field in _as_list(ws_spec.get("tooltip")):
        builder.tooltip(field)
    for field in _as_list(ws_spec.get("label")):
        builder.label(field)

    # Sorts
    for sort in ws_spec.get("sort", ws_spec.get("sorts", [])):
        if isinstance(sort, str):
            builder.sort(sort)
        elif isinstance(sort, dict):
            builder.sort(
                sort["field"],
                descending=sort.get("descending", sort.get("desc", False)),
                by=sort.get("by"),
            )

    # Filters
    for filt in ws_spec.get("filters", []):
        builder.filter(
            filt["field"],
            values=filt.get("values"),
            minimum=filt.get("minimum") or filt.get("min"),
            maximum=filt.get("maximum") or filt.get("max"),
            filter_type=filt.get("filter_type") or filt.get("type"),
        )

    # Title
    title = ws_spec.get("title")
    if title:
        builder.title(str(title))

    return builder


def _build_dashboard(dash_spec: dict[str, Any]) -> DashboardBuilder:
    """Build a DashboardBuilder from a spec dict."""
    name = dash_spec.get("name", "Dashboard")
    width = int(dash_spec.get("width", 1200))
    height = int(dash_spec.get("height", 800))
    builder = DashboardBuilder(name, width=width, height=height)

    # Zones
    for zone in dash_spec.get("zones", []):
        ws_name = zone.get("worksheet") or zone.get("sheet")
        text_content = zone.get("text")
        x = int(zone.get("x", zone.get("position", [0])[0] if "position" in zone else 0))
        y = int(zone.get("y", zone.get("position", [0, 0])[1] if "position" in zone else 0))
        w = int(
            zone.get(
                "w",
                zone.get(
                    "width", zone.get("position", [0, 0, 600])[2] if "position" in zone else 600
                ),
            )
        )
        h = int(
            zone.get(
                "h",
                zone.get(
                    "height", zone.get("position", [0, 0, 0, 400])[3] if "position" in zone else 400
                ),
            )
        )

        if ws_name:
            builder.sheet(ws_name, x=x, y=y, w=w, h=h)
        elif text_content:
            builder.text(text_content, x=x, y=y, w=w, h=h)

    # Actions
    for act in dash_spec.get("actions", []):
        builder.action(
            act.get("type", "filter"),
            source=act["source"],
            target=act["target"],
            name=act.get("name"),
            field=act.get("field"),
        )

    # Phone layout
    phone = dash_spec.get("phone_layout")
    if phone:
        tuples = []
        for z in phone:
            if isinstance(z, dict):
                tuples.append(
                    (
                        z.get("worksheet", z.get("sheet", "")),
                        int(z.get("x", 0)),
                        int(z.get("y", 0)),
                        int(z.get("w", z.get("width", 320))),
                        int(z.get("h", z.get("height", 300))),
                    )
                )
            elif isinstance(z, (list, tuple)) and len(z) >= 5:
                tuples.append(tuple(z[:5]))
        if tuples:
            builder.phone_layout(tuples)

    # Tablet layout
    tablet = dash_spec.get("tablet_layout")
    if tablet:
        tuples = []
        for z in tablet:
            if isinstance(z, dict):
                tuples.append(
                    (
                        z.get("worksheet", z.get("sheet", "")),
                        int(z.get("x", 0)),
                        int(z.get("y", 0)),
                        int(z.get("w", z.get("width", 768))),
                        int(z.get("h", z.get("height", 500))),
                    )
                )
            elif isinstance(z, (list, tuple)) and len(z) >= 5:
                tuples.append(tuple(z[:5]))
        if tuples:
            builder.tablet_layout(tuples)

    return builder


def from_spec(spec: str | Path | dict[str, Any]) -> Any:
    """Build a complete :class:`~pytableau.core.workbook.Workbook` from a spec.

    Args:
        spec: A Python dict, a path to a YAML/JSON file, or a raw
            YAML/JSON string describing the workbook.

    Returns:
        A :class:`~pytableau.core.workbook.Workbook` instance.

    Raises:
        InvalidWorkbookError: If the spec cannot be parsed.

    The spec format supports ``datasources``, ``worksheets``, and
    ``dashboards`` keys at the top level.  See the module docstring for
    the full schema.
    """
    # Deferred import to avoid circular dependency
    from pytableau.core.workbook import Workbook

    data = _load_data(spec)
    version = str(data.get("version", "2024.3"))
    wb = Workbook.new(version=version)

    # Phase 1: datasources
    ds_caption_to_name: dict[str, str] = {}
    for ds_spec in data.get("datasources", []):
        builder = _build_datasource(ds_spec)
        node = builder.build()
        # Attach to workbook XML tree
        container = wb.xml_root.find("datasources")
        if container is None:
            from lxml import etree

            container = etree.SubElement(wb.xml_root, "datasources")
        container.append(node)
        caption = ds_spec.get("caption") or ds_spec.get("name", "Data")
        ds_caption_to_name[caption] = builder.name

    # Phase 2: worksheets
    for ws_spec in data.get("worksheets", []):
        ds_caption = ws_spec.get("datasource")
        ds_internal = ds_caption_to_name.get(ds_caption, ds_caption) if ds_caption else None
        builder = _build_worksheet(ws_spec, ds_internal)
        node = builder.build()
        container = wb.xml_root.find("worksheets")
        if container is None:
            from lxml import etree

            container = etree.SubElement(wb.xml_root, "worksheets")
        container.append(node)

    # Phase 3: dashboards
    for dash_spec in data.get("dashboards", []):
        builder = _build_dashboard(dash_spec)
        node = builder.build()
        container = wb.xml_root.find("dashboards")
        if container is None:
            from lxml import etree

            container = etree.SubElement(wb.xml_root, "dashboards")
        container.append(node)

    # Re-parse collections so Workbook object model is in sync
    wb._load_tree(wb.xml_tree)

    return wb
