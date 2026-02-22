"""Dashboard, Zone, Action, and DashboardObject objects.

.. note::
    Full implementation is tracked in Phases 1–2 of the development plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lxml import etree

from pytableau.constants import ActionType, DashboardSizeType
from pytableau.core.fields import _normalise_field_name
from pytableau.xml.proxy import XMLNodeProxy

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


@dataclass
class DashboardSize:
    width: int | float | None
    height: int | float | None
    type: str


@dataclass
class Zone:
    zone_type: str
    name: str
    x: int | float | None
    y: int | float | None
    w: int | float | None
    h: int | float | None
    children: list["Zone"]

    def replace_field_reference(self, old: str, new: str) -> None:
        _ = old, new  # future extension point


@dataclass
class Action:
    action_type: str
    name: str | None
    target_sheet: str | None
    source_sheet: str | None
    xml_node: etree._Element

    @property
    def fields(self) -> list[str]:
        field = self.xml_node.get("field")
        if field:
            return [_normalise_field_name(field)]
        out: list[str] = []
        for field_node in self.xml_node.findall("field"):
            if field_node.get("name"):
                out.append(_normalise_field_name(field_node.get("name") or ""))
            elif field_node.text:
                out.append(_normalise_field_name(field_node.text))
        return out

    def replace_field_reference(self, old: str, new: str) -> None:
        old_norm = _normalise_field_name(old)
        new_token = _normalise_field_name(new)
        if self.xml_node.get("field"):
            if _normalise_field_name(self.xml_node.get("field", "")) == old_norm:
                self.xml_node.set("field", f"[{new_token}]")
        for node in self.xml_node.findall("field"):
            if _normalise_field_name(node.get("name", node.text or "")) == old_norm:
                if node.get("name") is not None:
                    node.set("name", f"[{new_token}]")
                if node.text is not None:
                    node.text = f"[{new_token}]"

    def remove_field_reference(self, field: str) -> None:
        target = _normalise_field_name(field)
        if self.xml_node.get("field") and _normalise_field_name(self.xml_node.get("field") or "") == target:
            self.xml_node.attrib.pop("field", None)
        for node in self.xml_node.findall("field"):
            if _normalise_field_name(node.get("name", node.text or "")) == target:
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)


class Dashboard(XMLNodeProxy):
    """Read-only dashboard wrapper with simple parsing helpers."""

    def __init__(self, node: etree._Element, workbook: "Workbook | None" = None) -> None:
        super().__init__(node)
        self._workbook = workbook
        self.name = self.xml_node.get("name", "")
        self.size = self._read_size()
        self.zones = self._read_zones()
        self.actions = self._read_actions()

    def _read_size(self) -> DashboardSize:
        size_node = self.xml_node.find("size")
        if size_node is None:
            return DashboardSize(None, None, DashboardSizeType.AUTOMATIC.value)
        return DashboardSize(
            width=_to_number(size_node.get("width")),
            height=_to_number(size_node.get("height")),
            type=size_node.get("type", DashboardSizeType.AUTOMATIC.value),
        )

    def _read_zones(self) -> list[Zone]:
        zone_nodes = self.xml_node.findall("zone")
        return [self._read_zone(node) for node in zone_nodes]

    def _read_zone(self, node: etree._Element) -> Zone:
        children = [self._read_zone(child) for child in node.findall("zone")]
        return Zone(
            zone_type=node.get("type", ""),
            name=node.get("name", ""),
            x=_to_number(node.get("x")),
            y=_to_number(node.get("y")),
            w=_to_number(node.get("w")),
            h=_to_number(node.get("h")),
            children=children,
        )

    def _read_actions(self) -> list[Action]:
        actions_node = self.xml_node.find("actions")
        if actions_node is None:
            return []
        out: list[Action] = []
        for action in actions_node.findall("action"):
            out.append(
                Action(
                    action_type=action.get("type") or action.get("class") or ActionType.FILTER.value,
                    name=action.get("name"),
                    target_sheet=action.get("target-sheet") or action.get("targetSheet"),
                    source_sheet=action.get("source-sheet") or action.get("sourceSheet"),
                    xml_node=action,
                )
            )
        return out

    def replace_field_reference(self, old: str, new: str) -> None:
        old_norm = _normalise_field_name(old)
        new_token = _normalise_field_name(new)
        for action in self.actions:
            action.replace_field_reference(old_norm, new_token)

    def remove_field_reference(self, field: str) -> None:
        for action in list(self.actions):
            action.remove_field_reference(field)


class DashboardCollection:
    """Ordered, dict-like dashboard collection."""

    def __init__(self, dashboards: list[Dashboard]) -> None:
        self._items = list(dashboards)

    @property
    def names(self) -> list[str]:
        return [dashboard.name for dashboard in self._items]

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, key: int | str) -> Dashboard:
        if isinstance(key, int):
            return self._items[key]
        if not isinstance(key, str):
            raise TypeError("dashboard key must be int index or dashboard name")
        for dashboard in self._items:
            if dashboard.name == key:
                return dashboard
        raise KeyError(key)


def _to_number(value: str | None) -> int | float | None:
    if value is None:
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return None


__all__ = [
    "Dashboard",
    "DashboardCollection",
    "DashboardSize",
    "Zone",
    "Action",
]
