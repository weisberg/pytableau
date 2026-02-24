"""Introspection helpers that return plain dicts — ideal for AI agents.

These standalone functions underpin the :meth:`~pytableau.core.workbook.Workbook.describe`
and :meth:`~pytableau.core.workbook.Workbook.capabilities` convenience methods.

Example::

    from pytableau import Workbook
    from pytableau.agents.discovery import describe, capabilities

    wb = Workbook.open("dashboard.twb")
    schema = describe(wb)
    caps = capabilities(wb)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pytableau.core.datasource import Datasource
    from pytableau.core.workbook import Workbook


def describe(workbook: Workbook) -> dict[str, Any]:
    """Return a complete structured schema of *workbook* as a plain dict.

    The returned dict has the following top-level keys:

    - ``version`` — Tableau source version string
    - ``datasources`` — list of datasource descriptors
    - ``worksheets`` — list of ``{"name": ...}`` dicts
    - ``dashboards`` — list of ``{"name": ...}`` dicts
    - ``parameters`` — list of parameter descriptors (from the Parameters datasource)

    Each datasource descriptor contains:

    - ``name``, ``caption``, ``connection_type``
    - ``fields`` — list of field descriptors with name, caption, datatype, role,
      is_calculated, and (for calculated fields) formula
    """
    from pytableau.core.fields import CalculatedField

    datasources = []
    for ds in workbook.datasources:
        if ds.is_parameters:
            continue
        conn_type = None
        if ds.connections:
            conn_type = ds.connections[0].class_

        fields = []
        for f in ds.all_fields:
            entry: dict[str, Any] = {
                "name": f.name,
                "caption": f.caption,
                "datatype": f.datatype,
                "role": getattr(f, "role", None),
                "is_calculated": isinstance(f, CalculatedField),
            }
            if isinstance(f, CalculatedField):
                entry["formula"] = f.formula
            fields.append(entry)

        datasources.append(
            {
                "name": ds.name,
                "caption": getattr(ds, "caption", ds.name),
                "connection_type": conn_type,
                "fields": fields,
            }
        )

    parameters = []
    if workbook.parameters:
        for p in workbook.parameters.parameters:
            parameters.append(
                {
                    "caption": p.caption,
                    "datatype": p.datatype,
                    "domain_type": p.domain_type,
                }
            )

    return {
        "version": workbook.version,
        "datasources": datasources,
        "worksheets": [{"name": ws.name} for ws in workbook.worksheets],
        "dashboards": [{"name": db.name} for db in workbook.dashboards],
        "parameters": parameters,
    }


def available_fields(datasource: Datasource) -> list[dict[str, Any]]:
    """Return a flat list of field descriptors for *datasource*.

    Each entry is a dict with keys: ``name``, ``caption``, ``datatype``,
    ``role``, ``is_calculated``, and (for calculated fields) ``formula``.

    This is intentionally simpler than the full :class:`~pytableau.core.fields.Field`
    objects — it is safe to serialise to JSON and easy for agents to reason about.
    """
    from pytableau.core.fields import CalculatedField

    result = []
    for f in datasource.all_fields:
        entry: dict[str, Any] = {
            "name": f.name,
            "caption": f.caption,
            "datatype": f.datatype,
            "role": getattr(f, "role", None),
            "is_calculated": isinstance(f, CalculatedField),
        }
        if isinstance(f, CalculatedField):
            entry["formula"] = f.formula
        result.append(entry)
    return result


def capabilities(workbook: Workbook) -> dict[str, Any]:
    """Return a capability summary for *workbook*.

    Checks which optional pytableau extras are installed and summarises
    the workbook's contents. Useful for agents deciding which operations are
    available at runtime.

    The returned dict has:

    - ``has_extract`` — ``True`` if any datasource has a ``.hyper`` extract
    - ``datasource_count``, ``worksheet_count``, ``dashboard_count``, ``parameter_count``
    - ``extras`` — ``{"hyper": bool, "pandas": bool, "server": bool, "governance": bool}``
    """
    has_extract = any(
        any(getattr(c, "class_", None) == "hyper" for c in ds.connections)
        for ds in workbook.datasources
        if not ds.is_parameters and ds.connections
    )

    def _has(module: str) -> bool:
        try:
            __import__(module)
            return True
        except ImportError:
            return False

    extras: dict[str, bool] = {
        "hyper": _has("tableauhyperapi"),
        "pandas": _has("pandas"),
        "server": _has("tableauserverclient"),
        "governance": _has("yaml"),
    }

    return {
        "has_extract": has_extract,
        "datasource_count": sum(1 for ds in workbook.datasources if not ds.is_parameters),
        "worksheet_count": len(workbook.worksheets),
        "dashboard_count": len(workbook.dashboards),
        "parameter_count": len(workbook.parameters.parameters) if workbook.parameters else 0,
        "extras": extras,
    }
