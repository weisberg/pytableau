"""pytableau.calculations — Tableau formula parser and linter.

Requires the optional ``[analysis]`` extra::

    pip install "pytableau[analysis]"
"""

from __future__ import annotations

from pytableau.calculations.functions import DEPRECATED_FUNCTIONS, FUNCTION_REGISTRY
from pytableau.calculations.linter import LintContext, LintIssue, LintRule, lint, lint_workbook

# Parser is intentionally not imported at top level to avoid hard dependency on lark.
# Use: from pytableau.calculations.parser import parse, parse_safe

__all__ = [
    "FUNCTION_REGISTRY",
    "DEPRECATED_FUNCTIONS",
    "LintContext",
    "LintIssue",
    "LintRule",
    "lint",
    "lint_workbook",
]
