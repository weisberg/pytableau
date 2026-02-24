"""Formula linter for Tableau calculated field expressions.

Provides six built-in lint rules and a :func:`lint` entry point.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pytableau.calculations.ast import (
    FieldRef,
    FormulaNode,
    FuncCall,
    IfExpr,
    LodExpr,
    find_nodes,
    walk,
)
from pytableau.calculations.functions import DEPRECATED_FUNCTIONS, FUNCTION_REGISTRY

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# LintIssue + LintContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintIssue:
    """A single lint finding for a formula."""

    rule: str
    message: str
    severity: str  # "error" | "warning" | "info"
    formula: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule": self.rule,
            "message": self.message,
            "severity": self.severity,
            "formula": self.formula,
        }


@dataclass
class LintContext:
    """Context for field reference and dependency validation."""

    field_caption: str = ""
    datasource_name: str = ""
    all_field_captions: set[str] = field(default_factory=set)
    known_dependencies: dict[str, set[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class LintRule(ABC):
    @abstractmethod
    def check(self, formula: str, ast: FormulaNode | None, ctx: LintContext) -> list[LintIssue]: ...


# ---------------------------------------------------------------------------
# Built-in rules
# ---------------------------------------------------------------------------


class UnknownFunctionRule(LintRule):
    """Warn when a formula calls a function not in the Tableau registry."""

    def check(self, formula: str, ast: FormulaNode | None, ctx: LintContext) -> list[LintIssue]:
        if ast is None:
            return []
        issues = []
        for node in find_nodes(ast, FuncCall):
            if node.name not in FUNCTION_REGISTRY:
                issues.append(
                    LintIssue(
                        rule="UnknownFunctionRule",
                        message=f"Unknown function: {node.name!r}",
                        severity="warning",
                        formula=formula,
                    )
                )
        return issues


class ExcessiveLodNestingRule(LintRule):
    """Flag LOD expressions nested more than 2 levels deep."""

    def check(self, formula: str, ast: FormulaNode | None, ctx: LintContext) -> list[LintIssue]:
        if ast is None:
            return []
        max_depth = _max_lod_depth(ast)
        if max_depth > 2:
            return [
                LintIssue(
                    rule="ExcessiveLodNestingRule",
                    message=f"LOD expression nesting depth {max_depth} exceeds recommended maximum of 2.",
                    severity="warning",
                    formula=formula,
                )
            ]
        return []


def _max_lod_depth(node: FormulaNode, current: int = 0) -> int:
    if isinstance(node, LodExpr):
        current += 1
        child_max = current
        if node.body is not None:
            child_max = _max_lod_depth(node.body, current)
        for dim in node.dimensions:
            child_max = max(child_max, _max_lod_depth(dim, current))
        return child_max

    depths = [current]
    if hasattr(node, "__dataclass_fields__"):
        import dataclasses

        for f in dataclasses.fields(node):
            val = getattr(node, f.name)
            if isinstance(val, FormulaNode):
                depths.append(_max_lod_depth(val, current))
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, FormulaNode):
                        depths.append(_max_lod_depth(item, current))
                    elif isinstance(item, tuple):
                        for sub in item:
                            if isinstance(sub, FormulaNode):
                                depths.append(_max_lod_depth(sub, current))
    return max(depths)


class NestedIfAntiPattern(LintRule):
    """Suggest CASE/WHEN for nested IF expressions."""

    def check(self, formula: str, ast: FormulaNode | None, ctx: LintContext) -> list[LintIssue]:
        if ast is None:
            return []
        issues = []

        def _check_node(node: FormulaNode) -> None:
            if isinstance(node, IfExpr) and (
                isinstance(node.then_expr, IfExpr) or isinstance(node.else_expr, IfExpr)
            ):
                issues.append(
                    LintIssue(
                        rule="NestedIfAntiPattern",
                        message=(
                            "Nested IF expression detected. "
                            "Consider using CASE/WHEN/THEN for readability."
                        ),
                        severity="info",
                        formula=formula,
                    )
                )

        walk(ast, _check_node)
        return issues


class DeprecatedFunctionRule(LintRule):
    """Error on use of deprecated functions (SCRIPT_REAL, RAWSQL_*, etc.)."""

    def check(self, formula: str, ast: FormulaNode | None, ctx: LintContext) -> list[LintIssue]:
        if ast is None:
            return []
        issues = []
        for node in find_nodes(ast, FuncCall):
            if node.name in DEPRECATED_FUNCTIONS:
                info = FUNCTION_REGISTRY.get(node.name)
                note = info.deprecation_note if info else ""
                issues.append(
                    LintIssue(
                        rule="DeprecatedFunctionRule",
                        message=f"Deprecated function {node.name!r}. {note}".strip(),
                        severity="error",
                        formula=formula,
                    )
                )
        return issues


class UnknownFieldReferenceRule(LintRule):
    """Warn when a formula references a field not in the datasource.

    Only active when ``ctx.all_field_captions`` is non-empty.
    """

    def check(self, formula: str, ast: FormulaNode | None, ctx: LintContext) -> list[LintIssue]:
        if ast is None or not ctx.all_field_captions:
            return []
        issues = []
        seen: set[str] = set()
        for node in find_nodes(ast, FieldRef):
            name = node.name
            if name in seen:
                continue
            seen.add(name)
            if name not in ctx.all_field_captions:
                issues.append(
                    LintIssue(
                        rule="UnknownFieldReferenceRule",
                        message=f"Field reference [{name}] not found in datasource.",
                        severity="warning",
                        formula=formula,
                    )
                )
        return issues


class CyclicDependencyRule(LintRule):
    """Error when calculated field dependencies form a cycle.

    Only active when ``ctx.known_dependencies`` is non-empty.
    ``known_dependencies`` should map ``field_caption → set of field captions it uses``.
    """

    def check(self, formula: str, ast: FormulaNode | None, ctx: LintContext) -> list[LintIssue]:
        if not ctx.known_dependencies or not ctx.field_caption:
            return []
        if _has_cycle(ctx.field_caption, ctx.known_dependencies):
            return [
                LintIssue(
                    rule="CyclicDependencyRule",
                    message=f"Cyclic dependency detected for field {ctx.field_caption!r}.",
                    severity="error",
                    formula=formula,
                )
            ]
        return []


def _has_cycle(start: str, deps: dict[str, set[str]]) -> bool:
    """DFS cycle detection in dependency graph."""
    visited: set[str] = set()
    path: set[str] = set()

    def _dfs(node: str) -> bool:
        if node in path:
            return True
        if node in visited:
            return False
        visited.add(node)
        path.add(node)
        for neighbor in deps.get(node, set()):
            if _dfs(neighbor):
                return True
        path.discard(node)
        return False

    return _dfs(start)


# ---------------------------------------------------------------------------
# Default rule set
# ---------------------------------------------------------------------------

_ALL_LINT_RULES: list[LintRule] = [
    UnknownFunctionRule(),
    ExcessiveLodNestingRule(),
    NestedIfAntiPattern(),
    DeprecatedFunctionRule(),
    UnknownFieldReferenceRule(),
    CyclicDependencyRule(),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def lint(
    formula: str,
    context: LintContext | None = None,
    rules: list[LintRule] | None = None,
) -> list[LintIssue]:
    """Lint a single Tableau formula string.

    Args:
        formula: The formula text to lint.
        context: Optional :class:`LintContext` for field reference and
            dependency checks.
        rules: Override the active rule set (default: all 6 built-in rules).

    Returns:
        List of :class:`LintIssue` objects (empty = no problems found).
    """
    from pytableau.calculations.parser import parse_safe

    ast = parse_safe(formula)
    ctx = context or LintContext()
    active_rules = rules if rules is not None else _ALL_LINT_RULES
    issues: list[LintIssue] = []
    for rule in active_rules:
        issues.extend(rule.check(formula, ast, ctx))
    return issues


def lint_workbook(workbook: Any, rules: list[LintRule] | None = None) -> list[LintIssue]:
    """Lint all calculated fields across all datasources in *workbook*.

    Args:
        workbook: A :class:`~pytableau.core.workbook.Workbook` instance.
        rules: Override the active rule set.

    Returns:
        Flat list of :class:`LintIssue` objects across all calcs.
    """
    issues: list[LintIssue] = []
    for ds in workbook.datasources:
        all_captions: set[str] = {f.caption for f in ds.fields if f.caption}
        # Build dependency map from calculated fields
        dep_map: dict[str, set[str]] = {}
        for cf in ds.calculated_fields:
            from pytableau.calculations.parser import parse_safe

            ast = parse_safe(cf.formula or "")
            if ast is not None:
                from pytableau.calculations.ast import FieldRef, find_nodes

                refs = {n.name for n in find_nodes(ast, FieldRef)}
                dep_map[cf.caption] = refs

        for cf in ds.calculated_fields:
            ctx = LintContext(
                field_caption=cf.caption,
                datasource_name=ds.name or "",
                all_field_captions=all_captions,
                known_dependencies=dep_map,
            )
            issues.extend(lint(cf.formula or "", context=ctx, rules=rules))
    return issues
