"""Template engine for parameterized Tableau workbook generation.

The template engine lets you build a visualization in Tableau Desktop,
save it as a ``.twb`` template with placeholder field names, and then
use pytableau to substitute real field names and data at runtime.

.. note::
    Full implementation is tracked in Phase 4 of the development plan.
"""

from __future__ import annotations

from pytableau.templates.engine import TemplateEngine
from pytableau.templates.mapping import FieldMapping, PLACEHOLDER_PATTERN, find_placeholders
from pytableau.templates.library import BUILTIN_TEMPLATES, get_template_path

__all__ = [
    "TemplateEngine",
    "FieldMapping",
    "PLACEHOLDER_PATTERN",
    "find_placeholders",
    "BUILTIN_TEMPLATES",
    "get_template_path",
]
