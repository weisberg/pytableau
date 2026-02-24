"""WorkbookReport: generate Markdown documentation for a workbook."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pytableau.inspect.catalog import WorkbookCatalog
from pytableau.inspect.lineage import FieldLineage

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


@dataclass
class WorkbookReport:
    """Generate human-readable markdown documentation for a workbook."""

    workbook: Workbook

    def to_markdown(self) -> str:
        payload = WorkbookCatalog(self.workbook).to_dict()
        lineage = FieldLineage(self.workbook)

        lines: list[str] = []
        lines.append("# Workbook Report")
        lines.append("")
        lines.append(f"- Path: {self.workbook._path or 'unsaved'}")
        lines.append(f"- Version: {payload['version']}")
        if payload.get("source_platform"):
            lines.append(f"- Source platform: {payload['source_platform']}")
        lines.append(f"- Datasource count: {payload['datasource_count']}")
        lines.append(f"- Worksheet count: {len(self.workbook.worksheets)}")
        lines.append(f"- Dashboard count: {len(self.workbook.dashboards)}")

        lines.append("")
        lines.append("## Datasources")
        for datasource in payload["datasources"]:
            lines.append(f"- **{datasource['name']}**")
            lines.append(f"  - Caption: {datasource['caption']}")
            lines.append(f"  - Fields: {datasource['field_count']}")
            if datasource["fields"]:
                lines.append("  - Field list:")
                for field_name in datasource["fields"]:
                    lines.append(f"    - `{field_name}`")
            if datasource["calculated_fields"]:
                lines.append("  - Calculated fields:")
                for calc_name in datasource["calculated_fields"]:
                    lines.append(f"    - `{calc_name}`")
            if datasource["connections"]:
                lines.append("  - Connections:")
                for connection in datasource["connections"]:
                    lines.append(
                        "    - "
                        f"class={connection['class']}, "
                        f"server={connection['server']}, "
                        f"dbname={connection['dbname']}, "
                        f"username={connection['username']}, "
                        f"port={connection['port']}"
                    )

        lines.append("")
        lines.append("## Parameters")
        if payload["parameters"]:
            for parameter in payload["parameters"]:
                lines.append(f"- **{parameter['caption']}**")
                lines.append(f"  - Datatype: `{parameter['datatype']}`")
                lines.append(f"  - Domain: {parameter['domain_type']}")
                lines.append(f"  - Value: `{parameter['value']}`")
                if "list" in str(parameter["domain_type"]).lower():
                    if parameter["allowable_values"]:
                        lines.append(
                            "  - Allowable values: "
                            + ", ".join(f"`{value}`" for value in parameter["allowable_values"])
                        )
                    else:
                        lines.append("  - Allowable values: none")
                if parameter["range_min"] is not None or parameter["range_max"] is not None:
                    lines.append(
                        "  - Range: "
                        f"min={parameter['range_min']}, max={parameter['range_max']}, "
                        f"step={parameter['range_step']}"
                    )
        else:
            lines.append("No parameters found.")

        lines.append("")
        lines.append("## Worksheets")
        for worksheet in self.workbook.worksheets:
            lines.append(f"- **{worksheet.name}**")
            lines.append(f"  - Mark type: `{worksheet.mark_type}`")
            if worksheet.filters:
                lines.append("  - Filters:")
                for filter_obj in worksheet.filters:
                    lines.append(f"    - `{filter_obj.field}` ({filter_obj.filter_type})")

        lines.append("")
        lines.append("## Dashboards")
        for dashboard in self.workbook.dashboards:
            lines.append(f"- **{dashboard.name}**")
            lines.append(f"  - Size: `{dashboard.size.width}x{dashboard.size.height}` ({dashboard.size.type})")
            lines.append(f"  - Zones: {len(dashboard.zones)}")
            lines.append(f"  - Actions: {len(dashboard.actions)}")

        lines.append("")
        lines.append("## Calculated Field Lineage")
        lineage_dict = lineage.to_dict()
        if lineage_dict:
            for entry_key, refs in lineage_dict.items():
                rendered_refs = ", ".join(refs) if refs else "(none)"
                lines.append(f"- {entry_key} depends on {rendered_refs}")
        else:
            lines.append("No calculated fields detected.")

        return "\n".join(lines)
