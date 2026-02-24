"""Datasource, Connection, and Relation objects."""

from __future__ import annotations

import re
import warnings
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from lxml import etree

from pytableau.constants import DataType, Role
from pytableau.data.extract import ExtractManager
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


# ---------------------------------------------------------------------------
# Credential scrubbing (#58)
# ---------------------------------------------------------------------------

class ScrubAction(NamedTuple):
    datasource: str
    connection: int
    attribute: str
    old_value: str


_CREDENTIAL_ATTR_RE = re.compile(r"(password|secret)", re.IGNORECASE)
_ALWAYS_SCRUB = {"password", "odbc-connect-string-extras"}


# ---------------------------------------------------------------------------
# Hierarchy and Set dataclasses (#69)
# ---------------------------------------------------------------------------

@dataclass
class Hierarchy:
    name: str
    levels: list[str]


@dataclass
class Set:
    name: str
    caption: str
    field_name: str | None = None


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Relation (#67)
# ---------------------------------------------------------------------------

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
            # type='text' stores SQL as element text
            if self.relation_type == "text":
                return (self.xml_node.text or "").strip() or None
            return None
        return (node.text or "").strip() or node.get("text")

    @property
    def joins(self) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for join in self.xml_node.findall("join"):
            out.append(dict(join.attrib))
        return out

    # --- Enhanced join-tree properties (#67) ---

    @property
    def join_type(self) -> str | None:
        """Return the join type from a ``<clause type=...>`` or ``join`` attribute."""
        clause = self.xml_node.find("clause")
        if clause is not None:
            return clause.get("type")
        return self.xml_node.get("join")

    @property
    def left(self) -> Relation | None:
        """Return the first child ``<relation>`` (left side of a join)."""
        children = self.xml_node.findall("relation")
        if children:
            return Relation(children[0])
        return None

    @property
    def right(self) -> Relation | None:
        """Return the second child ``<relation>`` (right side of a join)."""
        children = self.xml_node.findall("relation")
        if len(children) >= 2:
            return Relation(children[1])
        return None

    @property
    def on_clause(self) -> str | None:
        """Return the ON-clause expression from ``<clause>`` element text."""
        clause = self.xml_node.find("clause")
        if clause is not None:
            expr = clause.find("expression")
            if expr is not None:
                return expr.get("op") or (expr.text or "").strip() or None
            return (clause.text or "").strip() or None
        return None


# ---------------------------------------------------------------------------
# MetadataRecord (#68)
# ---------------------------------------------------------------------------

class MetadataRecord(XMLNodeProxy):
    """Wrap a ``<metadata-record>`` node."""

    @property
    def remote_name(self) -> str:
        node = self.xml_node.find("remote-name")
        return (node.text or "").strip() if node is not None else ""

    @property
    def remote_type(self) -> str:
        node = self.xml_node.find("remote-type")
        return (node.text or "").strip() if node is not None else ""

    @property
    def local_name(self) -> str:
        node = self.xml_node.find("local-name")
        return (node.text or "").strip() if node is not None else ""

    @property
    def aggregation(self) -> str:
        node = self.xml_node.find("aggregation")
        return (node.text or "").strip() if node is not None else ""

    @property
    def contains_null(self) -> bool:
        node = self.xml_node.find("contains-null")
        if node is None:
            return True
        return (node.text or "").strip().lower() not in {"false", "0", "no"}


# ---------------------------------------------------------------------------
# Datasource
# ---------------------------------------------------------------------------

class Datasource(XMLNodeProxy):
    """Read/write wrapper for a Tableau ``<datasource>`` node."""

    def __init__(self, node: etree._Element, workbook: Workbook | None = None) -> None:
        super().__init__(node)
        self._workbook = workbook
        self.name: str = self.xml_node.get("name", "")
        self.caption: str = self.xml_node.get("caption", self.name)
        self.connections = [Connection(conn) for conn in self.xml_node.findall(".//connection")]
        self.relations = [Relation(rel) for rel in self.xml_node.findall(".//relations/relation")]
        self._fields = self._read_fields()
        self._calculated_fields = [f for f in self._fields if isinstance(f, CalculatedField)]
        self._parameters = [f for f in self._fields if isinstance(f, Parameter)]
        self._regular_fields = [f for f in self._fields if isinstance(f, Field) and not isinstance(f, CalculatedField | Parameter)]
        self._hyper_path = self._discover_hyper_path()
        self._hyper_bridge = None
        self._extract_manager = ExtractManager()
        self._source_path: Path | None = None
        self._metadata_records_cache: list[MetadataRecord] | None = None

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

    def _discover_hyper_path(self) -> Path | None:
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

    def _set_hyper_path(self, path: Path | str | None) -> None:
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
            f for f in self._fields if isinstance(f, Field) and not isinstance(f, CalculatedField | Parameter)
        ]

    # ------------------------------------------------------------------
    # Credential scrubbing (#58)
    # ------------------------------------------------------------------

    def scrub_credentials(self) -> list[ScrubAction]:
        """Remove credential attributes from all connections.

        Returns a list of :class:`ScrubAction` describing each removal.
        """
        actions: list[ScrubAction] = []
        for idx, conn in enumerate(self.connections):
            node = conn.xml_node
            to_remove = []
            for attr in list(node.attrib):
                if attr in _ALWAYS_SCRUB or _CREDENTIAL_ATTR_RE.search(attr):
                    to_remove.append(attr)
            for attr in to_remove:
                old_value = node.attrib.pop(attr)
                actions.append(ScrubAction(
                    datasource=self.name,
                    connection=idx,
                    attribute=attr,
                    old_value=old_value,
                ))
        return actions

    # ------------------------------------------------------------------
    # Relation tree helpers (#67)
    # ------------------------------------------------------------------

    @property
    def relation(self) -> Relation | None:
        """Return the root ``<relation>`` node."""
        node = self.xml_node.find(".//relation")
        return Relation(node) if node is not None else None

    def list_custom_sql(self) -> list[str]:
        """Return all custom SQL strings across all ``type='text'`` relations."""
        results: list[str] = []
        for rel_node in self.xml_node.findall(".//relation"):
            r = Relation(rel_node)
            if r.relation_type == "text":
                sql = r.custom_sql
                if sql:
                    results.append(sql)
            # also check <custom-sql> children
            cs_node = rel_node.find("custom-sql")
            if cs_node is not None:
                text = (cs_node.text or "").strip()
                if text and text not in results:
                    results.append(text)
        return results

    # ------------------------------------------------------------------
    # MetadataRecords (#68)
    # ------------------------------------------------------------------

    @property
    def metadata_records(self) -> list[MetadataRecord]:
        """Return all ``<metadata-record>`` nodes (lazily cached)."""
        if self._metadata_records_cache is None:
            records = []
            for node in self.xml_node.findall(".//metadata-record"):
                records.append(MetadataRecord(node))
            self._metadata_records_cache = records
        return self._metadata_records_cache

    # ------------------------------------------------------------------
    # Hierarchies and Sets (#69)
    # ------------------------------------------------------------------

    @property
    def hierarchies(self) -> list[Hierarchy]:
        """Parse ``<drill-paths>`` into :class:`Hierarchy` objects."""
        result: list[Hierarchy] = []
        drill_paths = self.xml_node.find(".//drill-paths")
        if drill_paths is None:
            return result
        for path_node in drill_paths.findall("drill-path"):
            name = path_node.get("name", "")
            levels = []
            for field_node in path_node.findall("field"):
                val = (field_node.text or "").strip() or field_node.get("name", "")
                if val:
                    levels.append(_normalise_field_name(val))
            result.append(Hierarchy(name=name, levels=levels))
        return result

    @property
    def sets(self) -> list[Set]:
        """Parse set groups from ``<group class='groupfilter'>`` nodes."""
        result: list[Set] = []
        for group in self.xml_node.findall(".//group"):
            if group.get("class") == "groupfilter":
                name = group.get("name", "")
                caption = group.get("caption", name)
                field_name = group.get("field")
                if field_name:
                    field_name = _normalise_field_name(field_name)
                result.append(Set(name=name, caption=caption, field_name=field_name))
        return result

    # ------------------------------------------------------------------
    # Bulk field operations (#80)
    # ------------------------------------------------------------------

    def bulk_update_fields(self, where: Callable[[Field], bool], updates: dict) -> int:
        """Update attributes on all fields matching *where*.

        *updates* is a mapping of attribute name → new value.
        Returns the number of fields updated.
        """
        count = 0
        for field in list(self._fields):
            if where(field):
                for attr, val in updates.items():
                    setattr(field, attr, val)
                count += 1
        return count

    def bulk_rename_fields(self, mapping: dict[str, str]) -> int:
        """Rename multiple fields at once using *mapping* (old→new caption).

        Returns the number of fields renamed.
        """
        count = 0
        for old_caption, new_caption in mapping.items():
            field = self.get_field(old_caption)
            if field is not None:
                self.rename_field(old_caption, new_caption)
                count += 1
        return count

    # ------------------------------------------------------------------
    # swap_connection / add_calculated_field / remove_field / rename_field
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # .tds / .tdsx standalone open/save (#65)
    # ------------------------------------------------------------------

    @classmethod
    def open(cls, path: Path | str) -> Datasource:
        """Open a standalone ``.tds`` or ``.tdsx`` file."""
        from pytableau.exceptions import InvalidWorkbookError

        source = Path(path).expanduser()
        suffix = source.suffix.lower()

        if suffix == ".tds":
            try:
                tree = etree.parse(str(source))
            except (OSError, etree.XMLSyntaxError) as exc:
                raise InvalidWorkbookError(f"Cannot parse .tds file: {source}") from exc
            root = tree.getroot()
            ds = cls(root)
            ds._source_path = source
            return ds

        if suffix == ".tdsx":
            try:
                with zipfile.ZipFile(source) as zf:
                    tds_names = [n for n in zf.namelist() if n.lower().endswith(".tds")]
                    if not tds_names:
                        raise InvalidWorkbookError(f"No .tds file found in .tdsx: {source}")
                    tds_bytes = zf.read(tds_names[0])
            except (OSError, zipfile.BadZipFile) as exc:
                raise InvalidWorkbookError(f"Cannot open .tdsx archive: {source}") from exc
            try:
                root = etree.fromstring(tds_bytes)
            except etree.XMLSyntaxError as exc:
                raise InvalidWorkbookError(f"Cannot parse .tds inside .tdsx: {source}") from exc
            ds = cls(root)
            ds._source_path = source
            return ds

        raise InvalidWorkbookError(f"Unsupported datasource path: {source}")

    def save(self, path: Path | str | None = None) -> None:
        """Save this datasource to its source path (or *path*)."""
        destination = Path(path).expanduser() if path else self._source_path
        if destination is None:
            from pytableau.exceptions import InvalidWorkbookError
            raise InvalidWorkbookError("Datasource path is unknown; use save_as().")
        self.save_as(destination)

    def save_as(self, path: Path | str) -> None:
        """Save this datasource to *path* (``.tds`` or ``.tdsx``)."""
        from pytableau.exceptions import InvalidWorkbookError

        destination = Path(path).expanduser()
        suffix = destination.suffix.lower()

        xml_bytes = etree.tostring(
            self.xml_node,
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True,
        )

        if suffix == ".tds":
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(xml_bytes)
            self._source_path = destination
            return

        if suffix == ".tdsx":
            destination.parent.mkdir(parents=True, exist_ok=True)
            tds_name = destination.stem + ".tds"
            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(tds_name, xml_bytes)
            self._source_path = destination
            return

        raise InvalidWorkbookError(f"Unsupported datasource path: {destination}")


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
    "MetadataRecord",
    "Hierarchy",
    "Set",
    "ScrubAction",
    "_normalise_field_name",
]
