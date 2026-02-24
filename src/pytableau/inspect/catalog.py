"""WorkbookCatalog: list all fields, calcs, and connections in a workbook."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pytableau.constants import ParameterDomainType

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


@dataclass
class WorkbookCatalog:
    """Aggregate read-only catalog for a workbook."""

    workbook: Workbook

    @property
    def datasources(self) -> list:
        return list(self.workbook.datasources)

    @property
    def calculated_fields(self) -> list:
        fields = []
        for ds in self.workbook.datasources:
            fields.extend(ds.calculated_fields)
        return fields

    @property
    def parameters(self) -> list:
        if self.workbook.parameters is None:
            return []
        return list(self.workbook.parameters.parameters)

    @property
    def connections(self) -> list:
        out: list = []
        for ds in self.workbook.datasources:
            out.extend(ds.connections)
        if self.workbook.parameters is not None:
            out.extend(self.workbook.parameters.connections)
        return out

    def unused_fields(self) -> list:
        """Fields not referenced in any worksheet shelf, filter, or formula."""

        # Collect all field names referenced in worksheet XML text
        referenced: set[str] = set()
        import re

        ref_re = re.compile(r"\[([^\]]+)\]")
        for ws in self.workbook.worksheets:
            text = ""
            try:
                from lxml import etree

                text = etree.tostring(ws.xml_node, encoding="unicode")
            except Exception:
                pass
            for m in ref_re.finditer(text):
                referenced.add(m.group(1).lower())
        # Also include calc formula references
        for ds in self.workbook.datasources:
            for field in ds.calculated_fields:
                for m in ref_re.finditer(field.formula or ""):
                    referenced.add(m.group(1).lower())

        unused = []
        for ds in self.workbook.datasources:
            for field in ds.all_fields:
                caption = field.caption.lower()
                if caption not in referenced:
                    unused.append(field)
        return unused

    def unused_worksheets(self) -> list:
        """Worksheets not referenced in any dashboard zone."""
        used_names: set[str] = set()
        for db in self.workbook.dashboards:
            for zone in db.xml_node.findall(".//zone"):
                name = zone.get("name", "")
                if name:
                    used_names.add(name)
        return [ws for ws in self.workbook.worksheets if ws.name not in used_names]

    def orphaned_calcs(self) -> list:
        """Calculated fields whose [refs] don't resolve to any known field."""
        import re

        ref_re = re.compile(r"\[([^\]]+)\]")
        all_captions: set[str] = set()
        for ds in self.workbook.datasources:
            for field in ds.all_fields:
                all_captions.add(field.caption.lower())
        orphaned = []
        for ds in self.workbook.datasources:
            for calc in ds.calculated_fields:
                formula = calc.formula or ""
                refs = [m.group(1).lower() for m in ref_re.finditer(formula)]
                if refs and not all(r in all_captions for r in refs):
                    orphaned.append(calc)
        return orphaned

    def custom_sql_audit(self) -> list[dict]:
        """Return all custom SQL strings across datasources."""
        result = []
        for ds in self.workbook.datasources:
            for sql in ds.list_custom_sql():
                result.append({"datasource": ds.name, "sql": sql})
        return result

    def connection_audit(self) -> list[dict]:
        """Return all connections with basic security flags."""
        result = []
        for ds in self.workbook.datasources:
            for conn in ds.connections:
                has_password = "password" in conn.xml_node.attrib
                result.append(
                    {
                        "datasource": ds.name,
                        "class": conn.class_,
                        "server": conn.server,
                        "dbname": conn.dbname,
                        "username": conn.username,
                        "port": conn.port,
                        "has_password": has_password,
                    }
                )
        return result

    def to_dict(self) -> dict:
        datasources = []
        for ds in self.workbook.datasources:
            datasources.append(
                {
                    "name": ds.name,
                    "caption": ds.caption,
                    "field_count": len(ds.all_fields),
                    "fields": [field.caption for field in ds.all_fields],
                    "calculated_fields": [field.caption for field in ds.calculated_fields],
                    "connections": [
                        {
                            "class": c.class_,
                            "server": c.server,
                            "dbname": c.dbname,
                            "username": c.username,
                            "port": c.port,
                        }
                        for c in ds.connections
                    ],
                }
            )

        parameter_payload: list[dict] = []
        if self.workbook.parameters is not None:
            for parameter in self.workbook.parameters.parameters:
                parameter_payload.append(
                    {
                        "caption": parameter.caption,
                        "value": parameter.value,
                        "datatype": parameter.datatype,
                        "domain_type": str(ParameterDomainType(parameter.domain_type)),
                        "allowable_values": (
                            parameter.allowable_values
                            if str(parameter.domain_type) == ParameterDomainType.LIST.value
                            else []
                        ),
                        "range_min": parameter.range_min,
                        "range_max": parameter.range_max,
                        "range_step": parameter.range_step,
                    }
                )

        return {
            "version": self.workbook.version,
            "source_platform": self.workbook.source_platform,
            "datasource_count": len(self.workbook.datasources),
            "datasources": datasources,
            "parameter_count": len(parameter_payload),
            "parameters": parameter_payload,
        }
