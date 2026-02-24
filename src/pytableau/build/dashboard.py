"""Build dashboard XML elements programmatically.

Example::

    from pytableau.build import DashboardBuilder

    dash = (
        DashboardBuilder("Executive Summary", width=1200, height=800)
        .sheet("Revenue by Region", x=0, y=0, w=600, h=400)
        .sheet("Trend Over Time", x=600, y=0, w=600, h=400)
        .action("filter", source="Revenue by Region",
                target="Trend Over Time", field="Region")
        .phone_layout([
            ("Revenue by Region", 0, 0, 320, 300),
        ])
        .build()
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from pytableau.constants import ActionType

from ._xml import encode_shelf_field


@dataclass
class _ZoneSpec:
    """Internal zone specification."""

    zone_type: str  # "sheet", "text", "filter", "blank"
    name: str
    x: int
    y: int
    w: int
    h: int
    content: str | None = None  # text content for text zones

    def to_xml(self, parent: etree._Element) -> etree._Element:
        attrs: dict[str, str] = {
            "type": self.zone_type,
            "name": self.name,
            "x": str(self.x),
            "y": str(self.y),
            "w": str(self.w),
            "h": str(self.h),
        }
        node = etree.SubElement(parent, "zone", attrib=attrs)
        if self.content and self.zone_type == "text":
            node.text = self.content
        return node


@dataclass
class _ActionSpec:
    """Internal action specification."""

    action_type: str  # "filter", "highlight", "url"
    source: str
    target: str
    name: str | None = None
    field: str | None = None

    def to_xml(self, parent: etree._Element) -> etree._Element:
        attrs: dict[str, str] = {
            "type": self.action_type,
            "source-sheet": self.source,
            "target-sheet": self.target,
        }
        if self.name:
            attrs["name"] = self.name
        if self.field:
            attrs["field"] = encode_shelf_field(self.field)
        return etree.SubElement(parent, "action", attrib=attrs)


class DashboardBuilder:
    """Fluent builder for ``<dashboard>`` XML elements.

    Parameters:
        name: Dashboard tab name.
        width: Dashboard width in pixels (default 1200).
        height: Dashboard height in pixels (default 800).
    """

    def __init__(self, name: str, *, width: int = 1200, height: int = 800) -> None:
        self._name = name
        self._width = width
        self._height = height
        self._zones: list[_ZoneSpec] = []
        self._actions: list[_ActionSpec] = []
        self._device_layouts: dict[str, list[_ZoneSpec]] = {}

    # -- Zones ---------------------------------------------------------------

    def sheet(
        self,
        worksheet_name: str,
        *,
        x: int,
        y: int,
        w: int,
        h: int,
    ) -> DashboardBuilder:
        """Add a worksheet zone to the dashboard.

        Args:
            worksheet_name: Name of the worksheet (must match a worksheet tab name).
            x: Horizontal position in pixels.
            y: Vertical position in pixels.
            w: Width in pixels.
            h: Height in pixels.
        """
        self._zones.append(_ZoneSpec("sheet", worksheet_name, x, y, w, h))
        return self

    def text(
        self,
        content: str,
        *,
        x: int,
        y: int,
        w: int,
        h: int,
        name: str | None = None,
    ) -> DashboardBuilder:
        """Add a text zone.

        Args:
            content: The text content to display.
            x: Horizontal position in pixels.
            y: Vertical position in pixels.
            w: Width in pixels.
            h: Height in pixels.
            name: Optional zone name (defaults to ``"Text"``).
        """
        zone_name = name or "Text"
        self._zones.append(
            _ZoneSpec("text", zone_name, x, y, w, h, content=content)
        )
        return self

    def filter_zone(
        self,
        field: str,
        *,
        x: int,
        y: int,
        w: int,
        h: int,
    ) -> DashboardBuilder:
        """Add a filter control zone.

        Args:
            field: The field this filter controls.
            x: Horizontal position in pixels.
            y: Vertical position in pixels.
            w: Width in pixels.
            h: Height in pixels.
        """
        self._zones.append(_ZoneSpec("filter", field, x, y, w, h))
        return self

    def blank(
        self,
        *,
        x: int,
        y: int,
        w: int,
        h: int,
    ) -> DashboardBuilder:
        """Add a blank/spacer zone.

        Args:
            x: Horizontal position in pixels.
            y: Vertical position in pixels.
            w: Width in pixels.
            h: Height in pixels.
        """
        self._zones.append(_ZoneSpec("blank", "Blank", x, y, w, h))
        return self

    # -- Actions -------------------------------------------------------------

    def action(
        self,
        action_type: ActionType | str,
        *,
        source: str,
        target: str,
        name: str | None = None,
        field: str | None = None,
    ) -> DashboardBuilder:
        """Add a dashboard action (filter, highlight, or URL).

        Args:
            action_type: Type of action.
            source: Source worksheet name.
            target: Target worksheet name.
            name: Optional human-readable action name.
            field: Optional field the action operates on.
        """
        at = action_type.value if isinstance(action_type, ActionType) else str(action_type)
        auto_name = name or f"{at.title()} {source} → {target}"
        self._actions.append(
            _ActionSpec(action_type=at, source=source, target=target, name=auto_name, field=field)
        )
        return self

    # -- Device layouts ------------------------------------------------------

    def phone_layout(
        self,
        zones: list[tuple[str, int, int, int, int]],
    ) -> DashboardBuilder:
        """Define the phone device layout.

        Args:
            zones: List of ``(worksheet_name, x, y, w, h)`` tuples.
        """
        self._device_layouts["phone"] = [
            _ZoneSpec("sheet", name, x, y, w, h) for name, x, y, w, h in zones
        ]
        return self

    def tablet_layout(
        self,
        zones: list[tuple[str, int, int, int, int]],
    ) -> DashboardBuilder:
        """Define the tablet device layout.

        Args:
            zones: List of ``(worksheet_name, x, y, w, h)`` tuples.
        """
        self._device_layouts["tablet"] = [
            _ZoneSpec("sheet", name, x, y, w, h) for name, x, y, w, h in zones
        ]
        return self

    # -- Build ---------------------------------------------------------------

    def build(self) -> etree._Element:
        """Generate the ``<dashboard>`` XML element.

        Returns:
            An ``lxml.etree._Element`` ready to append to a workbook.
        """
        dash = etree.Element("dashboard", name=self._name)

        # Size
        etree.SubElement(
            dash,
            "size",
            attrib={
                "maxwidth": str(self._width),
                "minwidth": str(self._width),
                "maxheight": str(self._height),
                "minheight": str(self._height),
            },
        )

        # Zones
        if self._zones:
            zones_el = etree.SubElement(dash, "zones")
            for spec in self._zones:
                spec.to_xml(zones_el)

        # Device layouts
        if self._device_layouts:
            layouts_el = etree.SubElement(dash, "devicelayouts")
            for device_name, device_zones in self._device_layouts.items():
                layout = etree.SubElement(layouts_el, "devicelayout", name=device_name)
                dz_el = etree.SubElement(layout, "zones")
                for spec in device_zones:
                    spec.to_xml(dz_el)

        # Actions
        if self._actions:
            actions_el = etree.SubElement(dash, "actions")
            for spec in self._actions:
                spec.to_xml(actions_el)

        return dash

    def raw(self) -> etree._Element:
        """Return the built element (alias for :meth:`build`)."""
        return self.build()
