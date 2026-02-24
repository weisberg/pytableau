"""Worksheet, Shelf, MarkCard, and Encoding objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lxml import etree

from pytableau.constants import FilterType, MarkType
from pytableau.exceptions import FieldNotFoundError
from pytableau.xml.proxy import XMLNodeProxy

from .datasource import _normalise_field_name
from .fields import FieldReference
from .filters import (
    CategoricalFilter,
    Filter,
    RangeFilter,
    RelativeDateFilter,
    TopNFilter,
    parse_filter_node,
)

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


_FIELD_PATTERN = re.compile(r"\[([^\]]+)\]")


def _normalise_ref(value: str | FieldReference) -> str:
    if isinstance(value, FieldReference):
        return value.name
    return _normalise_field_name(value)


def _parse_ref_text(raw: str | None) -> list[FieldReference]:
    if not raw:
        return []
    return [FieldReference.parse(match.group(0)) for match in _FIELD_PATTERN.finditer(raw)]


def _encode_refs(refs: list[FieldReference]) -> str:
    return ", ".join(str(reference) for reference in refs)


@dataclass
class Shelf:
    """Ordered list of shelf references."""

    fields: list[FieldReference]


@dataclass
class MarkCard:
    """Parsed shelf-like channels from the mark card."""

    color: list[FieldReference]
    size: list[FieldReference]
    detail: list[FieldReference]
    tooltip: list[FieldReference]
    label: list[FieldReference]


class Worksheet(XMLNodeProxy):
    """Read-only worksheet wrapper with basic mutation helpers."""

    _MARK_CHANNELS = ("color", "size", "detail", "tooltip", "label")

    def __init__(self, node: etree._Element, workbook: Workbook | None = None) -> None:
        super().__init__(node)
        self._workbook = workbook
        self.name: str = self.xml_node.get("name", "")
        self._mark_type = self._parse_mark_type()
        self._rows: list[FieldReference] = self._read_shelf("rows")
        self._cols: list[FieldReference] = self._read_shelf("cols")
        self.filters: list[Filter] = self._read_filters()
        self.marks: MarkCard = self._read_mark_card()
        self.datasource_dependencies: list[str] = self._read_datasource_dependencies()

    @property
    def mark_type(self) -> str | None:
        if not self._mark_type:
            return None
        try:
            return str(MarkType(self._mark_type))
        except ValueError:
            return self._mark_type

    @property
    def rows(self) -> list[FieldReference]:
        return list(self._rows)

    @rows.setter
    def rows(self, value: list[FieldReference]) -> None:
        self._rows = list(value)
        self._write_shelf_text("rows", self._rows)

    @property
    def cols(self) -> list[FieldReference]:
        return list(self._cols)

    @cols.setter
    def cols(self, value: list[FieldReference]) -> None:
        self._cols = list(value)
        self._write_shelf_text("cols", self._cols)

    def _parse_mark_type(self) -> str:
        style = self.xml_node.find("style")
        if style is not None:
            return style.get("mark", style.get("class", ""))
        mark_node = self.xml_node.find("mark")
        if mark_node is not None:
            return mark_node.get("class", "")
        return ""

    def _get_shelf_lists(self, shelf: str) -> list[FieldReference] | list[FieldReference] | None:
        if shelf == "rows":
            return self._rows
        if shelf == "cols":
            return self._cols
        if shelf == "color":
            return self.marks.color
        if shelf == "size":
            return self.marks.size
        if shelf == "detail":
            return self.marks.detail
        if shelf == "tooltip":
            return self.marks.tooltip
        if shelf == "label":
            return self.marks.label
        return None

    def add_to_shelf(
        self,
        shelf: str,
        field: str,
        *,
        index: int | None = None,
    ) -> None:
        """Append ``field`` to a shelf or mark channel."""
        shelf_key = _normalise_ref(shelf)
        targets = self._get_shelf_lists(shelf_key)
        if targets is None:
            raise ValueError(f"Unsupported shelf '{shelf}'")

        ref = FieldReference(field)
        normalized = _normalise_field_name(ref.name)
        ref = FieldReference(normalized)
        if any(_normalise_field_name(f.name) == normalized for f in targets):
            return

        if index is None or index >= len(targets):
            targets.append(ref)
        else:
            if index < 0:
                index = 0
            targets.insert(index, ref)

        if shelf_key in {"rows", "cols"}:
            if shelf_key == "rows":
                self.rows = targets
            else:
                self.cols = targets
            return

        self._write_mark_text(shelf_key, targets)

    def remove_from_shelf(self, shelf: str, field: str) -> int:
        """Remove ``field`` from a shelf or mark channel."""
        shelf_key = _normalise_field_name(shelf)
        targets = self._get_shelf_lists(shelf_key)
        if targets is None:
            raise ValueError(f"Unsupported shelf '{shelf}'")
        target_key = _normalise_field_name(field)
        removed = [ref for ref in targets if _normalise_field_name(ref.name) == target_key]
        if not removed:
            return 0

        kept = [ref for ref in targets if _normalise_field_name(ref.name) != target_key]
        if shelf_key in {"rows", "cols"}:
            if shelf_key == "rows":
                self.rows = kept
            else:
                self.cols = kept
        else:
            self._write_mark_text(shelf_key, kept)
            if shelf_key in {"color", "size", "detail", "tooltip", "label"}:
                setattr(self.marks, shelf_key, kept)
        return len(removed)

    def move_within_shelf(self, shelf: str, field: str, index: int) -> None:
        """Reorder a field inside a shelf or mark channel."""
        shelf_key = _normalise_field_name(shelf)
        targets = self._get_shelf_lists(shelf_key)
        if targets is None:
            raise ValueError(f"Unsupported shelf '{shelf}'")
        target_key = _normalise_field_name(field)
        for i, ref in enumerate(targets):
            if _normalise_field_name(ref.name) == target_key:
                item = targets.pop(i)
                break
        else:
            raise FieldNotFoundError(f"Field '{field}' not present in shelf '{shelf}'.")

        index = max(0, min(index, len(targets)))
        targets.insert(index, item)
        if shelf_key in {"rows", "cols"}:
            if shelf_key == "rows":
                self.rows = targets
            else:
                self.cols = targets
            return
        self._write_mark_text(shelf_key, targets)

    def add_filter_to_shelf(self, shelf: str, field: str) -> None:
        """Deprecated convenience for compatibility."""
        self.add_to_shelf(shelf, field)

    def _read_shelf(self, tag: str) -> list[FieldReference]:
        node = self.xml_node.find(tag)
        if node is None:
            return []

        refs = _parse_ref_text(node.text)
        for field_node in node.findall("field"):
            if field_node.get("name"):
                refs.extend(_parse_ref_text(field_node.get("name")))
            elif field_node.text:
                refs.extend(_parse_ref_text(field_node.text))
        return refs

    def _read_shelf_text(self, tag: str) -> str:
        node = self.xml_node.find(tag)
        if node is None or node.text is None:
            return ""
        return node.text.strip()

    def _write_shelf_text(self, tag: str, refs: list[FieldReference]) -> None:
        node = self.xml_node.find(tag)
        if node is None:
            node = etree.SubElement(self.xml_node, tag)
        node.text = _encode_refs(refs)

    def _read_filters(self) -> list[Filter]:
        filters_node = self.xml_node.find("filters")
        if filters_node is None:
            return []
        out: list[Filter] = []
        for node in filters_node.findall("filter"):
            out.append(parse_filter_node(node))
        return out

    def _read_mark_card(self) -> MarkCard:
        marks_node = self.xml_node.find("marks")
        if marks_node is None:
            return MarkCard([], [], [], [], [])

        channels: dict[str, list[FieldReference]] = {
            "color": [],
            "size": [],
            "detail": [],
            "tooltip": [],
            "label": [],
        }
        for channel_name in self._MARK_CHANNELS:
            for channel in marks_node.findall(channel_name):
                if channel.text:
                    channels[channel_name].extend(_parse_ref_text(channel.text))
                for field_node in channel.findall("field"):
                    if field_node.text:
                        channels[channel_name].extend(_parse_ref_text(field_node.text))
        return MarkCard(**channels)

    def _write_mark_text(self, channel: str, refs: list[FieldReference]) -> None:
        marks_node = self.xml_node.find("marks")
        if marks_node is None:
            return
        nodes = marks_node.findall(channel)
        if not nodes and not refs:
            return
        if not nodes:
            marks_node.append(etree.Element(channel))
            nodes = marks_node.findall(channel)
        for node in nodes:
            node.text = _encode_refs(refs)

    def _read_datasource_dependencies(self) -> list[str]:
        container = self.xml_node.find("datasource-dependencies")
        if container is None:
            return []
        names: list[str] = []
        for node in container.findall("datasource"):
            if node.get("name"):
                names.append(node.get("name") or "")
        return names

    def _field_exists(self, field: str) -> bool:
        if self._workbook is None:
            return True

        target = _normalise_ref(field)
        if self.datasource_dependencies:
            datasources = [
                ds
                for ds in self._workbook.datasources
                if ds.name in self.datasource_dependencies
            ]
            if not datasources:
                datasources = list(self._workbook.datasources)
        else:
            datasources = list(self._workbook.datasources)

        return any(ds.get_field(target) is not None for ds in datasources)

    def add_filter(self, field: str, filter_type: FilterType | str, **kwargs) -> Filter:
        if not self._field_exists(field):
            raise FieldNotFoundError(
                f"Cannot add filter for unknown field '{field}' in worksheet '{self.name}'."
            )

        raw = filter_type.value if isinstance(filter_type, FilterType) else str(filter_type)
        kind = raw.replace("_", "-").lower()

        if kind == FilterType.CATEGORICAL.value:
            values = kwargs.get("values", [])
            if isinstance(values, str):
                values = [values]
            filter_obj = CategoricalFilter.create(field=field, values=list(values))
        elif kind in {FilterType.QUANTITATIVE.value, FilterType.RANGE.value}:
            filter_obj = RangeFilter.create(
                field,
                minimum=kwargs.get("minimum"),
                maximum=kwargs.get("maximum"),
                include_min=kwargs.get("include_min", True),
                include_max=kwargs.get("include_max", True),
            )
        elif kind == FilterType.RELATIVE_DATE.value:
            filter_obj = RelativeDateFilter.create(
                field,
                range_size=int(kwargs["range_size"]),
                range_unit=str(kwargs["range_unit"]),
            )
        elif kind == FilterType.TOP.value:
            filter_obj = TopNFilter.create(
                field,
                measure=str(kwargs["measure"]),
                n=int(kwargs["n"]),
                direction=str(kwargs.get("direction", "top")),
            )
        else:
            raise ValueError(f"Unsupported filter type '{filter_type}'.")

        filters_node = self.xml_node.find("filters")
        if filters_node is None:
            filters_node = etree.SubElement(self.xml_node, "filters")
        filters_node.append(filter_obj.xml_node)
        self.filters.append(filter_obj)
        return filter_obj

    def remove_filter(self, field: str) -> int:
        target = _normalise_ref(field)
        removable: list[Filter] = [
            candidate for candidate in self.filters if _normalise_ref(candidate.field) == target
        ]
        for candidate in removable:
            parent = candidate.xml_node.getparent()
            if parent is not None:
                parent.remove(candidate.xml_node)
            self.filters.remove(candidate)
        return len(removable)

    def rename_field_reference(self, old: str, new: str) -> None:
        old_name = _normalise_ref(old)
        new_name = _normalise_ref(new)

        self.rows = [
            FieldReference(new_name) if _normalise_ref(ref) == old_name else ref
            for ref in self.rows
        ]
        self.cols = [
            FieldReference(new_name) if _normalise_ref(ref) == old_name else ref
            for ref in self.cols
        ]

        self.marks.color = [
            FieldReference(new_name) if _normalise_ref(ref) == old_name else ref
            for ref in self.marks.color
        ]
        self.marks.size = [
            FieldReference(new_name) if _normalise_ref(ref) == old_name else ref
            for ref in self.marks.size
        ]
        self.marks.detail = [
            FieldReference(new_name) if _normalise_ref(ref) == old_name else ref
            for ref in self.marks.detail
        ]
        self.marks.tooltip = [
            FieldReference(new_name) if _normalise_ref(ref) == old_name else ref
            for ref in self.marks.tooltip
        ]
        self.marks.label = [
            FieldReference(new_name) if _normalise_ref(ref) == old_name else ref
            for ref in self.marks.label
        ]
        self._write_mark_text("color", self.marks.color)
        self._write_mark_text("size", self.marks.size)
        self._write_mark_text("detail", self.marks.detail)
        self._write_mark_text("tooltip", self.marks.tooltip)
        self._write_mark_text("label", self.marks.label)

        for candidate in self.filters:
            if _normalise_ref(candidate.field) == old_name:
                candidate.field = new_name

    def remove_field_reference(self, field: str) -> None:
        target = _normalise_ref(field)
        self.rows = [ref for ref in self.rows if _normalise_ref(ref) != target]
        self.cols = [ref for ref in self.cols if _normalise_ref(ref) != target]
        self.marks.color = [ref for ref in self.marks.color if _normalise_ref(ref) != target]
        self.marks.size = [ref for ref in self.marks.size if _normalise_ref(ref) != target]
        self.marks.detail = [ref for ref in self.marks.detail if _normalise_ref(ref) != target]
        self.marks.tooltip = [ref for ref in self.marks.tooltip if _normalise_ref(ref) != target]
        self.marks.label = [ref for ref in self.marks.label if _normalise_ref(ref) != target]
        self._write_mark_text("color", self.marks.color)
        self._write_mark_text("size", self.marks.size)
        self._write_mark_text("detail", self.marks.detail)
        self._write_mark_text("tooltip", self.marks.tooltip)
        self._write_mark_text("label", self.marks.label)

        self.remove_filter(field)


class WorksheetCollection:
    """Ordered, dict-like worksheet collection."""

    def __init__(self, worksheets: list[Worksheet]) -> None:
        self._items = list(worksheets)

    @property
    def names(self) -> list[str]:
        return [worksheet.name for worksheet in self._items]

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, key: int | str) -> Worksheet:
        if isinstance(key, int):
            return self._items[key]
        if not isinstance(key, str):
            raise TypeError("worksheet key must be index or worksheet name")
        for worksheet in self._items:
            if worksheet.name == key:
                return worksheet
        raise KeyError(key)
