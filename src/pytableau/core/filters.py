"""CategoricalFilter, RangeFilter, RelativeDateFilter, and related objects."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lxml import etree

from pytableau.constants import FilterType
from pytableau.xml.proxy import XMLNodeProxy

if TYPE_CHECKING:
    from pytableau.core.fields import FieldReference


_FIELD_RE = re.compile(r"\[(?P<name>[^\]]+)\]")


def _normalise_field_name(value: str | None) -> str:
    if value is None:
        return ""
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        return text[1:-1]
    return text


def _format_field_name(value: str | FieldReference) -> str:
    text = value if isinstance(value, str) else value.name
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return text
    return f"[{text}]"


def _extract_values(node: etree._Element) -> list[str]:
    values_node = node.find("values")
    if values_node is None:
        return []
    values: list[str] = []
    for child in values_node.findall("value"):
        if child.text is not None:
            values.append(child.text.strip())
    if not values:
        direct = values_node.get("values")
        if direct:
            values.extend([v.strip() for v in direct.split(",") if v.strip()])
    return values


def parse_filter_node(node: etree._Element) -> Filter:
    raw_type = node.get("class", "wildcard")
    return Filter.from_xml(node, raw_type=_normalise_filter_type(raw_type))


def _normalise_filter_type(value: str) -> str:
    return value.replace("_", "-").lower()


@dataclass
class FilterSpec:
    """Pure data representation of a filter request."""

    field: str
    filter_type: FilterType | str


class Filter(XMLNodeProxy):
    """Base class for all filter wrappers."""

    def __init__(
        self,
        node: etree._Element,
        *,
        filter_type: FilterType | str = FilterType.WILDCARD,
        field: str | None = None,
    ) -> None:
        super().__init__(node)
        self.filter_type = filter_type
        if field is not None:
            self.field = field

    @classmethod
    def from_xml(
        cls, node: etree._Element, raw_type: str | None = None
    ) -> Filter:
        discovered = _normalise_filter_type(raw_type or node.get("class", FilterType.WILDCARD.value))
        if discovered == FilterType.CATEGORICAL.value:
            return CategoricalFilter(node)
        if discovered in {FilterType.RANGE.value, FilterType.QUANTITATIVE.value}:
            return RangeFilter(node)
        if discovered == FilterType.RELATIVE_DATE.value:
            return RelativeDateFilter(node)
        if discovered == FilterType.TOP.value:
            return TopNFilter(node)
        return Filter(node, filter_type=discovered)

    @property
    def field(self) -> str:
        raw = self.xml_node.get("field") or self.xml_node.get("column") or ""
        return _normalise_field_name(raw)

    @field.setter
    def field(self, value: str) -> None:
        self.xml_node.set("field", _format_field_name(value))

    @property
    def raw_xml(self) -> etree._Element:
        return self.xml_node

    @property
    def filter_type(self) -> str:
        return self.xml_node.get("class", FilterType.WILDCARD.value)

    @filter_type.setter
    def filter_type(self, value: FilterType | str) -> None:
        raw_type = value.value if isinstance(value, FilterType) else str(value)
        self.xml_node.set("class", _normalise_filter_type(raw_type))


class CategoricalFilter(Filter):
    """Inclusion / exclusion filter."""

    @classmethod
    def create(
        cls,
        field: str,
        values: Iterable[str],
        include: bool = True,
    ) -> CategoricalFilter:
        node = etree.Element(
            "filter",
            attrib={
                "class": FilterType.CATEGORICAL.value,
                "field": _format_field_name(field),
            },
        )
        if not include:
            node.set("include", "false")
        values_node = etree.SubElement(node, "values")
        for value in values:
            etree.SubElement(values_node, "value").text = str(value)
        return cls(node)

    @classmethod
    def from_xml(cls, node: etree._Element) -> CategoricalFilter:
        return cls(node)

    @property
    def values(self) -> list[str]:
        return _extract_values(self.xml_node)

    @values.setter
    def values(self, values: list[str]) -> None:
        values_node = self.xml_node.find("values")
        if values_node is None:
            values_node = etree.SubElement(self.xml_node, "values")
        for child in list(values_node):
            values_node.remove(child)
        for value in values:
            etree.SubElement(values_node, "value").text = str(value)

    @property
    def include(self) -> bool:
        return self.xml_node.get("include", "true").lower() not in {"false", "0", "no"}

    @include.setter
    def include(self, value: bool) -> None:
        self.xml_node.set("include", "true" if value else "false")


class RangeFilter(Filter):
    """Numeric or date range filter."""

    @classmethod
    def create(
        cls,
        field: str,
        minimum: float | int | str | None = None,
        maximum: float | int | str | None = None,
        include_min: bool = True,
        include_max: bool = True,
    ) -> RangeFilter:
        node = etree.Element(
            "filter",
            attrib={
                "class": FilterType.RANGE.value,
                "field": _format_field_name(field),
            },
        )
        if minimum is not None:
            node.set("min", str(minimum))
            node.set("include-min", "true" if include_min else "false")
        if maximum is not None:
            node.set("max", str(maximum))
            node.set("include-max", "true" if include_max else "false")
        return cls(node)

    @classmethod
    def from_xml(cls, node: etree._Element) -> RangeFilter:
        return cls(node)

    @property
    def minimum(self) -> str | None:
        return self.xml_node.get("min")

    @minimum.setter
    def minimum(self, value: str | int | float | None) -> None:
        if value is None:
            self.xml_node.attrib.pop("min", None)
            self.xml_node.attrib.pop("include-min", None)
            return
        self.xml_node.set("min", str(value))

    @property
    def maximum(self) -> str | None:
        return self.xml_node.get("max")

    @maximum.setter
    def maximum(self, value: str | int | float | None) -> None:
        if value is None:
            self.xml_node.attrib.pop("max", None)
            self.xml_node.attrib.pop("include-max", None)
            return
        self.xml_node.set("max", str(value))


class RelativeDateFilter(Filter):
    """Relative date filter."""

    @classmethod
    def create(
        cls,
        field: str,
        range_size: int,
        range_unit: str,
    ) -> RelativeDateFilter:
        node = etree.Element(
            "filter",
            attrib={
                "class": FilterType.RELATIVE_DATE.value,
                "field": _format_field_name(field),
                "range-size": str(range_size),
                "range-unit": range_unit,
            },
        )
        return cls(node)

    @classmethod
    def from_xml(cls, node: etree._Element) -> RelativeDateFilter:
        return cls(node)

    @property
    def range_size(self) -> str | None:
        return self.xml_node.get("range-size")

    @range_size.setter
    def range_size(self, value: int | str | None) -> None:
        if value is None:
            self.xml_node.attrib.pop("range-size", None)
            return
        self.xml_node.set("range-size", str(value))

    @property
    def range_unit(self) -> str | None:
        return self.xml_node.get("range-unit")

    @range_unit.setter
    def range_unit(self, value: str | None) -> None:
        if value is None:
            self.xml_node.attrib.pop("range-unit", None)
            return
        self.xml_node.set("range-unit", str(value))


class TopNFilter(Filter):
    """Top-N / Bottom-N filter."""

    @classmethod
    def create(
        cls,
        field: str,
        measure: str,
        n: int,
        direction: str = "top",
    ) -> TopNFilter:
        node = etree.Element(
            "filter",
            attrib={
                "class": FilterType.TOP.value,
                "field": _format_field_name(field),
                "measure": _format_field_name(measure),
                "n": str(n),
                "direction": direction,
            },
        )
        return cls(node)

    @classmethod
    def from_xml(cls, node: etree._Element) -> TopNFilter:
        return cls(node)

    @property
    def n(self) -> int | None:
        raw = self.xml_node.get("n")
        return int(raw) if raw else None

    @n.setter
    def n(self, value: int | None) -> None:
        if value is None:
            self.xml_node.attrib.pop("n", None)
        else:
            self.xml_node.set("n", str(value))


__all__ = [
    "Filter",
    "FilterSpec",
    "CategoricalFilter",
    "RangeFilter",
    "RelativeDateFilter",
    "TopNFilter",
    "parse_filter_node",
]
