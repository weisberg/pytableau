"""AST node definitions for Tableau formula expressions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


@dataclass
class FormulaNode:
    """Base class for all Tableau formula AST nodes."""


# ---------------------------------------------------------------------------
# Leaf nodes
# ---------------------------------------------------------------------------


@dataclass
class NumberLiteral(FormulaNode):
    value: float


@dataclass
class StringLiteral(FormulaNode):
    value: str


@dataclass
class DateLiteral(FormulaNode):
    value: str  # raw text between # ... #


@dataclass
class BoolLiteral(FormulaNode):
    value: bool


@dataclass
class NullLiteral(FormulaNode):
    pass


@dataclass
class FieldRef(FormulaNode):
    """Reference to a field, e.g. ``[Sales]`` or ``[Orders].[Region]``."""

    name: str
    datasource: str | None = None


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------


@dataclass
class BinOp(FormulaNode):
    """Binary operation: ``left op right``."""

    op: str
    left: FormulaNode
    right: FormulaNode


@dataclass
class UnaryOp(FormulaNode):
    """Unary operation: ``op operand``."""

    op: str
    operand: FormulaNode


@dataclass
class FuncCall(FormulaNode):
    """Function call: ``NAME(arg, ...)``."""

    name: str
    args: list[FormulaNode] = field(default_factory=list)


@dataclass
class IfExpr(FormulaNode):
    """IF/THEN/ELSEIF/ELSE/END expression."""

    condition: FormulaNode
    then_expr: FormulaNode
    elseif_clauses: list[tuple[FormulaNode, FormulaNode]] = field(default_factory=list)
    else_expr: FormulaNode | None = None


@dataclass
class CaseExpr(FormulaNode):
    """CASE/WHEN/THEN/ELSE/END expression."""

    subject: FormulaNode
    when_clauses: list[tuple[FormulaNode, FormulaNode]] = field(default_factory=list)
    else_expr: FormulaNode | None = None


@dataclass
class LodExpr(FormulaNode):
    """Level-of-Detail expression: ``{FIXED [dim,...] : body}``."""

    lod_type: str  # "FIXED" | "INCLUDE" | "EXCLUDE"
    dimensions: list[FieldRef] = field(default_factory=list)
    body: FormulaNode | None = None


# ---------------------------------------------------------------------------
# AST walker
# ---------------------------------------------------------------------------


def walk(node: FormulaNode, visitor: Callable[[FormulaNode], None]) -> None:
    """Depth-first pre-order walk of an AST tree, calling *visitor* on each node."""
    visitor(node)
    if isinstance(node, BinOp):
        walk(node.left, visitor)
        walk(node.right, visitor)
    elif isinstance(node, UnaryOp):
        walk(node.operand, visitor)
    elif isinstance(node, FuncCall):
        for arg in node.args:
            walk(arg, visitor)
    elif isinstance(node, IfExpr):
        walk(node.condition, visitor)
        walk(node.then_expr, visitor)
        for cond, expr in node.elseif_clauses:
            walk(cond, visitor)
            walk(expr, visitor)
        if node.else_expr is not None:
            walk(node.else_expr, visitor)
    elif isinstance(node, CaseExpr):
        walk(node.subject, visitor)
        for when, then in node.when_clauses:
            walk(when, visitor)
            walk(then, visitor)
        if node.else_expr is not None:
            walk(node.else_expr, visitor)
    elif isinstance(node, LodExpr):
        for dim in node.dimensions:
            walk(dim, visitor)
        if node.body is not None:
            walk(node.body, visitor)


def find_nodes(node: FormulaNode, node_type: type) -> list[Any]:
    """Collect all nodes of *node_type* in the AST."""
    results: list[Any] = []

    def _collect(n: FormulaNode) -> None:
        if isinstance(n, node_type):
            results.append(n)

    walk(node, _collect)
    return results
