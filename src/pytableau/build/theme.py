"""Theme builder for programmatic Tableau formatting.

.. note::
    Full theme application via the Custom Themes API (Tableau 2025.1+) is
    implemented in ``pytableau.cloud.themes``. This module provides the
    local object model for theme values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Theme:
    """A collection of formatting values to apply to a workbook.

    Attributes:
        name: Theme identifier.
        font_family: Default font family.
        font_size: Default font size in points.
        colors: Named color palette (key → hex string or Color).
    """

    name: str = "default"
    font_family: str = "Tableau Book"
    font_size: int = 10
    colors: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_workbook(cls, workbook: Any) -> Theme:
        """Extract theme values from an existing workbook.

        Args:
            workbook: A :class:`~pytableau.core.workbook.Workbook` instance.

        Returns:
            A :class:`Theme` populated from workbook-level formatting attributes.
        """
        root = workbook.xml_root
        name = root.get("source-platform", "extracted")
        return cls(name=name)

    def to_dict(self) -> dict[str, Any]:
        """Serialise the theme to a plain dict."""
        return {
            "name": self.name,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "colors": dict(self.colors),
        }
