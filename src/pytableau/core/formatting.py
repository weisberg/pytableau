"""Style, ColorPalette, Font, and FormatSpec value objects."""

from __future__ import annotations

from dataclasses import dataclass, field


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
