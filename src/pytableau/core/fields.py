"""Field, CalculatedField, Parameter, Group, Set, and Bin objects."""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lxml import etree

from pytableau.constants import DataType, ParameterDomainType, Role
from pytableau.xml.proxy import XMLNodeProxy

if TYPE_CHECKING:
    from pytableau.core.datasource import Datasource


_FIELD_REF_RE = re.compile(r"\[(?P<name>[^\]]+)\]")


def _normalise_field_caption(caption: str) -> str:
    text = caption.strip()
    if text.startswith("[") and text.endswith("]"):
        return text[1:-1]
    return text


def _format_field_caption(caption: str) -> str:
    normalized = caption.strip()
    if normalized.startswith("[") and normalized.endswith("]"):
        return normalized
    return f"[{normalized}]"


def _coerce_value(value: object | None, datatype: str | DataType | None) -> object | None:
    if value is None:
        return None
    target = datatype.value if isinstance(datatype, DataType) else datatype
    if target is None:
        return value
    if target == DataType.STRING:
        return str(value)
    if target == DataType.INTEGER:
        return int(str(value))
    if target == DataType.REAL:
        return float(str(value))
    if target == DataType.BOOLEAN:
        raw = str(value).strip().lower()
        if raw in {"true", "1", "yes", "y"}:
            return True
        if raw in {"false", "0", "no", "n"}:
            return False
        raise ValueError(f"Cannot coerce '{value}' to boolean")
    if target == DataType.DATE:
        return str(value)
    if target == DataType.DATETIME:
        return str(value)
    return str(value)


@dataclass(frozen=True)
class FieldReference:
    """Reference to a Tableau field in shelf/filter markup.

    The name intentionally stores the bracketless field caption.
    """

    name: str

    @classmethod
    def parse(cls, text: str) -> FieldReference:
        normalized = _normalise_field_caption(text)
        return cls(normalized)

    def __str__(self) -> str:
        return _format_field_caption(self.name)


class FieldCollection:
    """Dictionary-like collection of fields keyed by caption."""

    def __init__(self, fields: list[Field] | None = None) -> None:
        self._fields: list[Field] = list(fields or [])
        self._by_caption: dict[str, Field] = {}
        self._index()

    def _index(self) -> None:
        self._by_caption = {field.caption: field for field in self._fields}

    @property
    def names(self) -> list[str]:
        return [field.caption for field in self._fields]

    def __iter__(self):
        return iter(self._fields)

    def __len__(self) -> int:
        return len(self._fields)

    def __getitem__(self, key: int | str) -> Field:
        if isinstance(key, int):
            return self._fields[key]
        if not isinstance(key, str):
            raise TypeError("collection key must be int or field caption")
        if key not in self._by_caption:
            raise KeyError(key)
        return self._by_caption[key]

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str):
            return item in self._by_caption
        if isinstance(item, Field):
            return item in self._fields
        return False

    def add(self, field: Field) -> None:
        self._fields.append(field)
        self._index()

    def remove(self, caption: str) -> None:
        key = _normalise_field_caption(caption)
        target = self._by_caption.pop(key)
        self._fields = [f for f in self._fields if f is not target]
        self._index()

    def get(self, caption: str, default: Field | None = None) -> Field | None:
        return self._by_caption.get(_normalise_field_caption(caption), default)


class CalcFieldCollection(FieldCollection):
    """Collection for calculated fields."""

    def add(self, field: CalculatedField) -> None:
        if not isinstance(field, CalculatedField):
            raise TypeError("calc field collection accepts only CalculatedField instances")
        super().add(field)


class Field(XMLNodeProxy):
    """A Tableau field represented by a ``<column>`` element."""

    def __init__(self, node: etree._Element, datasource: Datasource | None = None) -> None:
        super().__init__(node)
        self._datasource = datasource

    @property
    def name(self) -> str:
        return self.xml_node.get("name", "")

    @property
    def caption(self) -> str:
        return self.xml_node.get("caption", self.name)

    @caption.setter
    def caption(self, value: str) -> None:
        self.xml_node.set("caption", value)

    @property
    def datatype(self) -> str:
        return self.xml_node.get("datatype", DataType.STRING)

    @datatype.setter
    def datatype(self, value: DataType | str) -> None:
        if isinstance(value, DataType):
            value = value.value
        self.xml_node.set("datatype", str(value))

    @property
    def role(self) -> str:
        return self.xml_node.get("role", Role.DIMENSION)

    @role.setter
    def role(self, value: Role | str) -> None:
        if isinstance(value, Role):
            value = value.value
        self.xml_node.set("role", str(value))

    @property
    def hidden(self) -> bool:
        return self.xml_node.get("hidden", "false").lower() in {"1", "true", "yes", "on"}

    @hidden.setter
    def hidden(self, value: bool) -> None:
        self.xml_node.set("hidden", "true" if value else "false")


class CalculatedField(Field):
    """A field with an embedded calculated formula."""

    @property
    def formula(self) -> str:
        calc_node = self.xml_node.find("calculation")
        if calc_node is None:
            return ""
        return calc_node.get("formula", "")

    @formula.setter
    def formula(self, value: str) -> None:
        calc_node = self.xml_node.find("calculation")
        if calc_node is None:
            calc_node = etree.SubElement(
                self.xml_node,
                "calculation",
                attrib={"class": "tableau", "formula": value},
            )
            return
        calc_node.set("formula", value)

    @property
    def calculation_class(self) -> str | None:
        calc_node = self.xml_node.find("calculation")
        if calc_node is None:
            return None
        return calc_node.get("class")


class Parameter(Field):
    """A parameter stored in the special ``Parameters`` datasource."""

    @property
    def domain_type(self) -> str:
        return self.xml_node.get("param-domain-type", ParameterDomainType.ALL)

    @domain_type.setter
    def domain_type(self, value: ParameterDomainType | str) -> None:
        if isinstance(value, ParameterDomainType):
            value = value.value
        new_value = str(value)
        self.xml_node.set("param-domain-type", new_value)
        if new_value == ParameterDomainType.ALL:
            domain = self._find_domain_node(create=False)
            if domain is not None:
                for child in list(domain):
                    domain.remove(child)
            self.xml_node.attrib.pop("value", None)
            return
        if new_value == ParameterDomainType.RANGE:
            domain = self._find_domain_node(create=True)
            for child in list(domain):
                domain.remove(child)
            return
        if new_value == ParameterDomainType.LIST:
            domain = self._find_domain_node(create=True)
            for child in list(domain):
                domain.remove(child)
            return

    @property
    def value(self) -> object | None:
        raw = self.xml_node.get("value")
        if raw is None:
            value_node = self.xml_node.find("value")
            if value_node is not None:
                raw = (value_node.text or "").strip()
        if raw is None:
            return None
        return _coerce_value(raw, self.xml_node.get("datatype"))

    @value.setter
    def value(self, value: object | None) -> None:
        if value is None:
            self.xml_node.set("value", "")
            value_node = self.xml_node.find("value")
            if value_node is not None:
                value_node.text = ""
            return
        coerced = _coerce_value(value, self.xml_node.get("datatype"))
        self.xml_node.set("value", "" if coerced is None else str(coerced))
        value_node = self.xml_node.find("value")
        if value_node is None:
            value_node = etree.SubElement(self.xml_node, "value")
        value_node.text = "" if coerced is None else str(coerced)

    @property
    def allowable_values(self) -> list[str]:
        node = self._find_domain_node(create=False)
        if node is None:
            return []
        values = []
        for member in node.findall("member"):
            values.append(member.get("value") or (member.text or "").strip())
        if not values:
            for value_node in node.findall("value"):
                if value_node is not None:
                    val = (value_node.text or "").strip()
                    if val:
                        values.append(val)
        return values

    @allowable_values.setter
    def allowable_values(self, values: list[str]) -> None:
        if self.domain_type != ParameterDomainType.LIST:
            self.domain_type = ParameterDomainType.LIST
        domain_node = self._find_domain_node(create=True)
        for child in list(domain_node):
            domain_node.remove(child)
        for value in values:
            etree.SubElement(domain_node, "member", attrib={"value": str(value)})

    @property
    def range_min(self) -> str | None:
        node = self._find_domain_node(create=False)
        if node is None:
            return None
        return node.get("range-min")

    @range_min.setter
    def range_min(self, value: str | float | int | None) -> None:
        if self.domain_type != ParameterDomainType.RANGE:
            self.domain_type = ParameterDomainType.RANGE
        node = self._find_domain_node(create=True)
        if value is None:
            node.attrib.pop("range-min", None)
        else:
            node.set("range-min", str(value))

    @property
    def range_max(self) -> str | None:
        node = self._find_domain_node(create=False)
        if node is None:
            return None
        return node.get("range-max")

    @range_max.setter
    def range_max(self, value: str | float | int | None) -> None:
        if self.domain_type != ParameterDomainType.RANGE:
            self.domain_type = ParameterDomainType.RANGE
        node = self._find_domain_node(create=True)
        if value is None:
            node.attrib.pop("range-max", None)
        else:
            node.set("range-max", str(value))

    @property
    def range_step(self) -> str | None:
        node = self._find_domain_node(create=False)
        if node is None:
            return None
        return node.get("range-step")

    @range_step.setter
    def range_step(self, value: str | float | int | None) -> None:
        if self.domain_type != ParameterDomainType.RANGE:
            self.domain_type = ParameterDomainType.RANGE
        node = self._find_domain_node(create=True)
        if value is None:
            node.attrib.pop("range-step", None)
        else:
            node.set("range-step", str(value))

    @property
    def datatype(self) -> str:
        return self.xml_node.get("datatype", DataType.STRING)

    @datatype.setter
    def datatype(self, value: DataType | str) -> None:
        old_value = self.value
        normalized = value.value if isinstance(value, DataType) else value
        if old_value is not None:
            try:
                coerced = _coerce_value(old_value, normalized)
            except ValueError as exc:
                raise ValueError(
                    f"Cannot coerce current parameter value '{old_value}' "
                    f"to datatype '{normalized}'"
                ) from exc
        else:
            coerced = None
        self.xml_node.set("datatype", str(normalized))
        if old_value is not None:
            self.value = coerced
        warnings.warn(
            f"Parameter datatype changed to '{normalized}' for '{self.caption}'.",
            stacklevel=2,
        )

    def _find_domain_node(self, create: bool = False) -> etree._Element | None:
        domain = self.xml_node.find("domain")
        if domain is not None:
            return domain
        if create:
            return etree.SubElement(self.xml_node, "domain")
        return None


__all__ = [
    "Field",
    "CalculatedField",
    "Parameter",
    "FieldCollection",
    "CalcFieldCollection",
    "FieldReference",
]
