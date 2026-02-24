"""Template engine for parameterized Tableau workbook generation.

The template engine lets you build a visualization in Tableau Desktop,
save it as a ``.twb`` template with placeholder field names, and then
use pytableau to substitute real field names and data at runtime.
"""

from __future__ import annotations

from pytableau.templates.engine import TemplateEngine
from pytableau.templates.library import BUILTIN_TEMPLATES, get_template_path
from pytableau.templates.mapping import PLACEHOLDER_PATTERN, FieldMapping, find_placeholders

__all__ = [
    "TemplateEngine",
    "FieldMapping",
    "PLACEHOLDER_PATTERN",
    "find_placeholders",
    "BUILTIN_TEMPLATES",
    "get_template_path",
]
