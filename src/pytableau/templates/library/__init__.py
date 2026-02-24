"""Built-in starter templates for common Tableau chart types.

Available templates:

- ``bar_chart`` — Horizontal/vertical bar chart
- ``line_chart`` — Time series line chart
- ``scatter_plot`` — X/Y scatter with optional size encoding
- ``heatmap`` — Cross-tab heatmap with color encoding
- ``treemap`` — Hierarchical treemap
- ``map`` — Filled geographical map
- ``kpi_dashboard`` — Multi-KPI dashboard layout
- ``stacked_bar`` — Stacked bar chart with color dimension
- ``dual_axis`` — Dual-axis bar + line combo chart
- ``area_chart`` — Area chart with date dimension and color encoding

.. note::
    Template ``.twb`` files are created in Tableau Desktop 2024.1+.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

#: Names of all built-in templates.
BUILTIN_TEMPLATES: tuple[str, ...] = (
    "bar_chart",
    "line_chart",
    "scatter_plot",
    "heatmap",
    "treemap",
    "map",
    "kpi_dashboard",
    "stacked_bar",
    "dual_axis",
    "area_chart",
)


def get_template_path(name: str) -> Path:
    """Return the filesystem path to a built-in template file.

    Args:
        name: Template name (one of :data:`BUILTIN_TEMPLATES`).

    Returns:
        :class:`~pathlib.Path` pointing to the ``.twb`` file.

    Raises:
        :exc:`~pytableau.exceptions.TemplateNotFoundError`: If *name*
            is not a recognised built-in template.
    """
    from pytableau.exceptions import TemplateNotFoundError

    if name not in BUILTIN_TEMPLATES:
        raise TemplateNotFoundError(
            f"No built-in template named {name!r}. "
            f"Available templates: {', '.join(BUILTIN_TEMPLATES)}"
        )

    pkg = files("pytableau.templates.library")
    template_file = pkg / f"{name}.twb"
    return Path(str(template_file))
