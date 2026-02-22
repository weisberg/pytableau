"""WorkbookCatalog: list all fields, calcs, and connections in a workbook.

.. note::
    Full implementation is tracked in Phase 1 of the development plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pytableau.constants import ParameterDomainType

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


@dataclass
class WorkbookCatalog:
    """Aggregate read-only catalog for a workbook."""

    workbook: "Workbook"

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
