"""Style, ColorPalette, Font, and FormatSpec value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Color:
    """An RGBA colour value.

    Attributes:
        r: Red channel (0–255).
        g: Green channel (0–255).
        b: Blue channel (0–255).
        a: Alpha channel (0–255, default 255 = fully opaque).
    """

    r: int
    g: int
    b: int
    a: int = 255

    @classmethod
    def from_hex(cls, hex_str: str) -> Color:
        """Parse a hex colour string (``#RRGGBB`` or ``#RRGGBBAA``).

        Args:
            hex_str: Hex string with leading ``#``.

        Returns:
            :class:`Color` instance.

        Raises:
            ValueError: If *hex_str* is not a valid hex colour.
        """
        s = hex_str.lstrip("#")
        if len(s) == 6:
            r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
            return cls(r, g, b)
        if len(s) == 8:
            r, g, b, a = (
                int(s[0:2], 16),
                int(s[2:4], 16),
                int(s[4:6], 16),
                int(s[6:8], 16),
            )
            return cls(r, g, b, a)
        raise ValueError(f"Invalid hex colour: {hex_str!r}")

    def to_hex(self) -> str:
        """Return the colour as an uppercase ``#RRGGBB`` string (alpha ignored)."""
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"

    def __str__(self) -> str:
        return self.to_hex()


@dataclass(frozen=True)
class Font:
    """Font style descriptor.

    Attributes:
        family: Font family name.
        size: Font size in points.
        bold: Bold weight.
        italic: Italic style.
        underline: Underline decoration.
    """

    family: str = "Tableau Book"
    size: int = 10
    bold: bool = False
    italic: bool = False
    underline: bool = False


@dataclass
class ColorPalette:
    """A named palette of :class:`Color` values.

    Attributes:
        name: Palette name.
        colors: Ordered list of colours.
    """

    name: str
    colors: list[Color] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialise to a JSON-compatible dictionary."""
        return {
            "name": self.name,
            "colors": [c.to_hex() for c in self.colors],
        }


@dataclass
class FormatSpec:
    """Combined formatting specification for a workbook element.

    Attributes:
        font: Optional font settings.
        text_color: Optional foreground colour.
        background_color: Optional background colour.
    """

    font: Font | None = None
    text_color: Color | None = None
    background_color: Color | None = None

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> FormatSpec:
        """Parse a JSON/YAML formatting specification."""
        return cls(
            Font(**spec["font"]) if spec.get("font") else None,
            Color.from_hex(spec["text_color"]) if spec.get("text_color") else None,
            Color.from_hex(spec["background_color"]) if spec.get("background_color") else None,
        )

    def apply(self, target: Any, *, element: str = "worksheet") -> None:
        """Merge native style-rule/format values without discarding other styling."""
        from lxml import etree

        node = target.xml_node if hasattr(target, "xml_node") else target
        if node.tag == "worksheet" and node.find("table") is not None:
            node = node.find("table")
        style = node.find("style")
        if style is None:
            style = etree.SubElement(node, "style")
            if node.tag == "table":
                node.remove(style)
                node.insert(1, style)
        rules = [n for n in style.findall("style-rule") if n.get("element") == element]
        rule = rules[0] if rules else etree.SubElement(style, "style-rule", element=element)
        attributes = {}
        if self.font:
            attributes.update(
                {
                    "font-family": self.font.family,
                    "font-size": str(self.font.size),
                    "font-weight": "bold" if self.font.bold else "normal",
                    "font-style": "italic" if self.font.italic else "normal",
                    "text-decoration": "underline" if self.font.underline else "none",
                }
            )
        if self.text_color:
            attributes["color"] = self.text_color.to_hex()
        if self.background_color:
            attributes["background-color"] = self.background_color.to_hex()
        for attribute, value in attributes.items():
            formats = [n for n in rule.findall("format") if n.get("attr") == attribute]
            node = formats[0] if formats else etree.SubElement(rule, "format", attr=attribute)
            node.set("value", value)

    @classmethod
    def read(cls, target: Any, *, element: str = "worksheet") -> FormatSpec:
        """Read the native style rule written by apply, leaving unknown settings intact."""
        node = target.xml_node if hasattr(target, "xml_node") else target
        if node.tag == "worksheet" and node.find("table") is not None:
            node = node.find("table")
        values = {
            n.get("attr"): n.get("value")
            for r in node.findall("style/style-rule")
            if r.get("element") == element
            for n in r.findall("format")
        }
        font = None
        if any(k.startswith("font-") for k in values):
            font = Font(
                values.get("font-family", "Tableau Book"),
                int(values.get("font-size", "10")),
                values.get("font-weight") == "bold",
                values.get("font-style") == "italic",
                values.get("text-decoration") == "underline",
            )
        return cls(
            font,
            Color.from_hex(values["color"]) if "color" in values else None,
            Color.from_hex(values["background-color"]) if "background-color" in values else None,
        )

    def to_dict(self) -> dict[str, object]:
        """Serialise to a JSON-compatible dictionary."""
        return {
            "font": (
                {
                    "family": self.font.family,
                    "size": self.font.size,
                    "bold": self.font.bold,
                    "italic": self.font.italic,
                    "underline": self.font.underline,
                }
                if self.font is not None
                else None
            ),
            "text_color": self.text_color.to_hex() if self.text_color is not None else None,
            "background_color": (
                self.background_color.to_hex() if self.background_color is not None else None
            ),
        }
