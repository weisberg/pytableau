"""FieldMapping: placeholder → real field name mapping for templates.

Template placeholders follow the ``__PLACEHOLDER__`` naming convention.
The :class:`FieldMapping` class tracks the mapping and validates that all
placeholders are resolved before a workbook is saved.

.. note::
    Full implementation is tracked in Phase 4 of the development plan.
"""

from __future__ import annotations

#: Regex pattern that matches template placeholder names.
PLACEHOLDER_PATTERN = r"__[A-Z][A-Z0-9_]*__"
