"""Datasource, Connection, and Relation objects.

.. note::
    Full implementation is tracked in Phases 1–2 of the development plan.
"""

from __future__ import annotations

import re
from pathlib import Path
import warnings
from typing import TYPE_CHECKING, Iterable

from lxml import etree

from pytableau.data.extract import ExtractManager
from pytableau.constants import DataType, Role
from pytableau.exceptions import (
    ConnectionError,
    DuplicateFieldError,
    FieldNotFoundError,
    HyperError,
)
from pytableau.xml.proxy import XMLNodeProxy

from .fields import (
    CalcFieldCollection,
    CalculatedField,
    Field,
    FieldCollection,
    FieldReference,
    Parameter,
)

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


def _normalise_field_name(value: str) -> str:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        return text[1:-1]
    return text


def _build_calc_name(existing: set[str]) -> str:
    import time

    counter = 0
    while True:
        name = f"[Calculation_{int(time.time())}_{counter}]"
        if name not in existing:
            return name
        counter += 1


def _contains_field_reference(formula: str | None, caption: str) -> bool:
    if not formula:
        return False
    target = _normalise_field_name(caption)
    return f"[{target}]" in formula


def _rename_formula(formula: str | None, old_caption: str, new_caption: str) -> str:
    if not formula:
        return ""
    old = f"[{_normalise_field_name(old_caption)}]"
    new = f"[{_normalise_field_name(new_caption)}]"
    return formula.replace(old, new)


class Connection(XMLNodeProxy):
    """Wrap a Tableau connection entry."""

    @property
    def server(self) -> str | None:
        return self.xml_node.get("server")

    @server.setter
    def server(self, value: str | None) -> None:
        if value is None:
            self.xml_node.attrib.pop("server", None)
        else:
            self.xml_node.set("server", value)

    @property
    def dbname(self) -> str | None:
        return self.xml_node.get("dbname") or self.xml_node.get("dbName")

    @dbname.setter
    def dbname(self, value: str | None) -> None:
        if value is None:
            self.xml_node.attrib.pop("dbname", None)
            self.xml_node.attrib.pop("dbName", None)
            return
        self.xml_node.set("dbname", value)

    @property
    def username(self) -> str | None:
        return self.xml_node.get("username")

    @username.setter
    def username(self, value: str | None) -> None:
        if value is None:
            self.xml_node.attrib.pop("username", None)
        else:
            self.xml_node.set("username", value)

    @property
    def port(self) -> int | None:
        raw = self.xml_node.get("port")
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError as exc:
            raise ConnectionError(f"Invalid port value '{raw}' on connection node") from exc

    @port.setter
    def port(self, value: int | None) -> None:
        if value is None:
            self.xml_node.attrib.pop("port", None)
        else:
            self.xml_node.set("port", str(int(value)))

    @property
    def class_(self) -> str | None:
        return self.xml_node.get("class")

    @class_.setter
    def class_(self, value: str | None) -> None:
        current = self.class_
        if value is None:
            self.xml_node.attrib.pop("class", None)
            return
        if current is not None and current != value:
            warnings.warn(
                f"Changing connection class from '{current}' to '{value}' "
                "can change field semantics.",
                stacklevel=2,
            )
        self.xml_node.set("class", value)


class Relation(XMLNodeProxy):
    """A datasource relation node."""

    @property
    def relation_type(self) -> str | None:
        return self.xml_node.get("type")

    @property
    def table(self) -> str | None:
        return self.xml_node.get("table")

    @property
    def custom_sql(self) -> str | None:
        node = self.xml_node.find("custom-sql")
        if node is None:
            return None
        return (node.text or "").strip() or node.get("text")

    @property
    def joins(self) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for join in self.xml_node.findall("join"):
            out.append(dict(join.attrib))
        return out


class Datasource(XMLNodeProxy):
    """Read/write wrapper for a Tableau ``<datasource>`` node."""

    def __init__(self, node: etree._Element, workbook: "Workbook | None" = None) -> None:
        super().__init__(node)
        self._workbook = workbook
        self.name: str = self.xml_node.get("name", "")
        self.caption: str = self.xml_node.get("caption", self.name)
        self.connections = [Connection(conn) for conn in self.xml_node.findall(".//connection")]
        self.relations = [Relation(rel) for rel in self.xml_node.findall(".//relations/relation")]
        self._fields = self._read_fields()
        self._calculated_fields = [f for f in self._fields if isinstance(f, CalculatedField)]
        self._parameters = [f for f in self._fields if isinstance(f, Parameter)]
        self._regular_fields = [f for f in self._fields if isinstance(f, Field) and not isinstance(f, (CalculatedField, Parameter))]
        self._hyper_path = self._discover_hyper_path()
        self._hyper_bridge = None
        self._extract_manager = ExtractManager()

    @property
    def hyper(self):
        """Provide .hyper operations for extracted datasources."""
        if self._hyper_path is None:
            raise HyperError("No .hyper extract attached to this datasource.")
        if self._hyper_bridge is None:
            from pytableau.data.bridge import HyperBridge

            self._hyper_bridge = HyperBridge(
                self._hyper_path,
                on_write=self._sync_extracted_metadata,
            )
        return self._hyper_bridge

    def _discover_hyper_path(self) -> "Path | None":
        for connection in self.connections:
            if connection.class_ != "hyper":
                continue
            for attr in ("filename", "path", "dbName", "dbname", "name"):
                value = connection._node.get(attr)
                if value and str(value).lower().endswith(".hyper"):
                    return self._resolve_hyper_candidate(Path(value))
        return None

    def _resolve_hyper_candidate(self, value: Path) -> Path:
        if value.is_absolute():
            return value

        base = self._package_data_root()
        if base is None:
            return value

        candidates = [
            base / value,
            base / "Data" / value,
            base / "Data" / value.name,
            base / "Data" / "Datasources" / value.name,
            base / "datasources" / value.name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return base / "Data" / value.name

    def _package_data_root(self) -> Path | None:
        if self._workbook is None:
            return None
        if self._workbook._package_manager is not None:
            return self._workbook._package_manager.twb_path.parent
        return self._workbook._path.parent if self._workbook._path is not None else None

    def _connection_safe_name(self) -> str:
        text = re.sub(r"[^A-Za-z0-9_-]", "_", self.name or "datasource")
        return text[:32] or "datasource"

    def _set_hyper_path(self, path: "Path | str | None") -> None:
        if path is None:
            self._hyper_path = None
            self._hyper_bridge = None
            return
        self._hyper_path = Path(path)
        self._hyper_bridge = None

    def _sync_extracted_metadata(self, df, table: str = "Extract") -> None:
        self._extract_manager.sync_metadata_records(self, df)

    def create_extract(self, df, table: str = "Extract") -> None:
        self._extract_manager.create(self, df, table=table)

    def refresh_extract(self, df, table: str = "Extract") -> None:
        self._extract_manager.refresh(self, df, table=table)

    def attach_extract(self, path: Path | str) -> None:
        self._extract_manager.attach(self, path)

    def detach_extract(self) -> None:
        self._extract_manager.detach(self)

    @property
    def is_parameters(self) -> bool:
        return self.name == "Parameters"

    def _read_fields(self) -> list[Field]:
        columns = self.xml_node.find("columns") or self.xml_node
        fields: list[Field] = []
        for node in columns.findall("column"):
            field = self._field_from_node(node)
            if field is not None:
                fields.append(field)
        return fields

    def _field_from_node(self, node: etree._Element) -> Field:
        if node.get("param-domain-type") is not None or self.is_parameters:
            return Parameter(node)
        if node.find("calculation") is not None:
            return CalculatedField(node, self)
        return Field(node, self)

    @property
    def fields(self) -> FieldCollection:
        return FieldCollection(list(self._regular_fields))

    @property
    def calculated_fields(self) -> CalcFieldCollection:
        return CalcFieldCollection(list(self._calculated_fields))

    @property
    def parameters(self) -> list[Parameter]:
        return list(self._parameters)

    @property
    def all_fields(self) -> list[Field]:
        return list(self._fields)

    def get_field(self, name: str) -> Field | None:
        normal = _normalise_field_name(name)
        for field in self._fields:
            if field.caption == normal or _normalise_field_name(field.caption) == normal:
                return field
        return None

    @property
    def field_names(self) -> list[str]:
        return [field.caption for field in self._fields]

    def _sync_fields(self) -> None:
        self._fields = self._read_fields()
        self._calculated_fields = [f for f in self._fields if isinstance(f, CalculatedField)]
        self._parameters = [f for f in self._fields if isinstance(f, Parameter)]
        self._regular_fields = [
            f for f in self._fields if isinstance(f, Field) and not isinstance(f, (CalculatedField, Parameter))
        ]

    def swap_connection(self, **kwargs: str | int | None) -> None:
        for conn in self.connections:
            if "server" in kwargs and kwargs["server"] is not None:
                conn.server = str(kwargs["server"])
            if "dbname" in kwargs and kwargs["dbname"] is not None:
                conn.dbname = str(kwargs["dbname"])
            if "username" in kwargs and kwargs["username"] is not None:
                conn.username = str(kwargs["username"])
            if "port" in kwargs and kwargs["port"] is not None:
                conn.port = int(kwargs["port"])
            if "class_" in kwargs and kwargs["class_"] is not None:
                conn.class_ = str(kwargs["class_"])

    def add_calculated_field(
        self,
        caption: str,
        formula: str,
        datatype: DataType = DataType.REAL,
        role: Role = Role.MEASURE,
        default_format: str | None = None,
        hidden: bool = False,
    ) -> CalculatedField:
        normalised_caption = _normalise_field_name(caption)
        if self.get_field(caption) is not None:
            raise DuplicateFieldError(f"Field '{caption}' already exists in datasource '{self.name}'.")
        existing_names = {f.name for f in self._fields}
        existing_names.update({_normalise_field_name(f.caption) for f in self._fields})
        name = _build_calc_name(existing_names)
        columns = self.xml_node.find("columns") or self.xml_node
        attrs: dict[str, str] = {
            "name": name,
            "caption": normalised_caption,
            "datatype": datatype.value if isinstance(datatype, DataType) else str(datatype),
            "role": role.value if isinstance(role, Role) else str(role),
            "type": "quantitative",
            "hidden": "true" if hidden else "false",
        }
        if default_format is not None:
            attrs["default-format"] = default_format
        node = etree.SubElement(columns, "column", attrib=attrs)
        etree.SubElement(node, "calculation", attrib={"class": "tableau", "formula": formula})
        field = CalculatedField(node, self)
        self._fields.append(field)
        self._calculated_fields.append(field)
        return field

    def remove_field(self, name_or_field: str | Field) -> None:
        field = (
            name_or_field
            if isinstance(name_or_field, Field)
            else self.get_field(name_or_field)
        )
        if field is None:
            raise FieldNotFoundError(f"Field '{name_or_field}' not found in datasource '{self.name}'.")
        parent = field.xml_node.getparent()
        if parent is not None:
            parent.remove(field.xml_node)
        self._sync_fields()

        if self._workbook is not None:
            target = field.caption
            for worksheet in self._workbook.worksheets:
                worksheet.remove_field_reference(target)
            for dashboard in self._workbook.dashboards:
                dashboard.remove_field_reference(target)
            for datasource in self._workbook.datasources:
                if datasource is self:
                    continue
                for calc in datasource.calculated_fields:
                    formula = calc.formula
                    if _contains_field_reference(formula, target):
                        warnings.warn(
                            f"Removing '{target}' may break calculated field '{calc.caption}' "
                            f"in datasource '{datasource.name}'.",
                            stacklevel=2,
                        )

    def rename_field(self, old_caption: str, new_caption: str) -> None:
        old_key = _normalise_field_label(old_caption)
        new_key = _normalise_field_label(new_caption)
        if old_key == new_key:
            return
        if not old_key:
            raise FieldNotFoundError("Old field caption cannot be empty.")
        if self.get_field(new_caption) is not None:
            raise DuplicateFieldError(f"Field '{new_caption}' already exists in datasource '{self.name}'.")
        field = self.get_field(old_caption)
        if field is None:
            raise FieldNotFoundError(f"Field '{old_caption}' not found in datasource '{self.name}'.")

        field.caption = new_caption
        self._sync_fields()

        if self._workbook is not None:
            for datasource in self._workbook.datasources:
                for calc in datasource.calculated_fields:
                    calc.formula = _rename_formula(calc.formula, old_key, new_key)

            for worksheet in self._workbook.worksheets:
                worksheet.rename_field_reference(old_key, new_key)
            for dashboard in self._workbook.dashboards:
                dashboard.replace_field_reference(old_key, new_key)

class DatasourceCollection:
    """Dict-like ordered datasource collection."""

    def __init__(self, datasources: Iterable[Datasource]) -> None:
        self._items = list(datasources)

    @property
    def names(self) -> list[str]:
        return [ds.name for ds in self._items]

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, key: int | str) -> Datasource:
        if isinstance(key, int):
            return self._items[key]
        if not isinstance(key, str):
            raise TypeError("datasource key must be index or datasource name")
        for ds in self._items:
            if ds.name == key or ds.caption == key:
                return ds
        raise KeyError(key)

    def get(self, key: str, default: Datasource | None = None) -> Datasource | None:
        for ds in self._items:
            if ds.name == key or ds.caption == key:
                return ds
        return default


def _normalise_field_label(value: str) -> str:
    if value is None:
        return ""
    return _normalise_field_name(value)


__all__ = [
    "Datasource",
    "DatasourceCollection",
    "Connection",
    "Relation",
    "_normalise_field_name",
]
