"""Tests for v0.9.0 — Formula Parser & Linter (M9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pytableau.calculations.functions import DEPRECATED_FUNCTIONS, FUNCTION_REGISTRY
from pytableau.calculations.linter import LintContext, LintIssue, lint, lint_workbook
from pytableau.core.workbook import Workbook

FIXTURE_DIR = Path(__file__).parent / "fixtures"

lark = pytest.importorskip("lark", reason="lark not installed — skip formula tests")


# ---------------------------------------------------------------------------
# Import parser here (after lark is confirmed available)
# ---------------------------------------------------------------------------

from pytableau.calculations.ast import (  # noqa: E402
    BinOp,
    BoolLiteral,
    CaseExpr,
    FieldRef,
    FuncCall,
    IfExpr,
    LodExpr,
    NullLiteral,
    NumberLiteral,
    StringLiteral,
    find_nodes,
    walk,
)
from pytableau.calculations.parser import ParseError, parse, parse_safe  # noqa: E402

# ---------------------------------------------------------------------------
# Basic parsing
# ---------------------------------------------------------------------------


def test_parse_field_ref():
    node = parse("[Sales]")
    assert isinstance(node, FieldRef)
    assert node.name == "Sales"
    assert node.datasource is None


def test_parse_datasource_field_ref():
    node = parse("[Orders].[Profit]")
    assert isinstance(node, FieldRef)
    assert node.name == "Profit"
    assert node.datasource == "Orders"


def test_parse_function_call():
    node = parse("SUM([Sales])")
    assert isinstance(node, FuncCall)
    assert node.name.upper() == "SUM"
    assert len(node.args) == 1
    assert isinstance(node.args[0], FieldRef)
    assert node.args[0].name == "Sales"


def test_parse_function_no_args():
    node = parse("TODAY()")
    assert isinstance(node, FuncCall)
    assert node.name.upper() == "TODAY"
    assert node.args == []


def test_parse_number_literal():
    node = parse("42")
    assert isinstance(node, NumberLiteral)
    assert node.value == pytest.approx(42.0)


def test_parse_string_literal():
    node = parse('"hello"')
    assert isinstance(node, StringLiteral)
    assert node.value == "hello"


def test_parse_null_literal():
    node = parse("NULL")
    assert isinstance(node, NullLiteral)


def test_parse_bool_literal():
    t_node = parse("TRUE")
    f_node = parse("FALSE")
    assert isinstance(t_node, BoolLiteral)
    assert t_node.value is True
    assert isinstance(f_node, BoolLiteral)
    assert f_node.value is False


def test_parse_if_expr():
    node = parse("IF [x] THEN [y] ELSE [z] END")
    assert isinstance(node, IfExpr)
    assert isinstance(node.condition, FieldRef)
    assert node.condition.name == "x"
    assert isinstance(node.then_expr, FieldRef)
    assert node.then_expr.name == "y"
    assert node.else_expr is not None
    assert isinstance(node.else_expr, FieldRef)
    assert node.else_expr.name == "z"


def test_parse_case_expr():
    node = parse("CASE [Dim] WHEN 'A' THEN 1 ELSE 0 END")
    assert isinstance(node, CaseExpr)
    assert isinstance(node.subject, FieldRef)
    assert len(node.when_clauses) == 1
    assert node.else_expr is not None


def test_parse_fixed_lod():
    node = parse("{FIXED [Region] : SUM([Sales])}")
    assert isinstance(node, LodExpr)
    assert node.lod_type.upper() == "FIXED"
    assert len(node.dimensions) == 1
    assert node.dimensions[0].name == "Region"
    assert isinstance(node.body, FuncCall)


def test_parse_lod_multiple_dims():
    node = parse("{FIXED [Region], [Category] : AVG([Price])}")
    assert isinstance(node, LodExpr)
    assert len(node.dimensions) == 2
    dim_names = {d.name for d in node.dimensions}
    assert dim_names == {"Region", "Category"}


def test_parse_nested_lod():
    node = parse("{FIXED [R] : {FIXED [C] : SUM([S])}}")
    assert isinstance(node, LodExpr)
    assert isinstance(node.body, LodExpr)


def test_parse_safe_returns_none_on_error():
    result = parse_safe("invalid ||| formula ^^^")
    assert result is None


def test_parse_raises_parse_error():
    with pytest.raises(ParseError):
        parse("invalid ||| formula ^^^")


def test_parse_binop_precedence():
    node = parse("1 + 2 * 3")
    # 1 + (2 * 3) — multiplication binds tighter
    assert isinstance(node, BinOp)
    assert node.op == "+"
    assert isinstance(node.right, BinOp)
    assert node.right.op == "*"


# ---------------------------------------------------------------------------
# walk() / find_nodes()
# ---------------------------------------------------------------------------


def test_walk_visits_all_nodes():
    node = parse("SUM([Sales]) + AVG([Profit])")
    visited = []
    walk(node, visited.append)
    types = {type(n).__name__ for n in visited}
    assert "BinOp" in types
    assert "FuncCall" in types
    assert "FieldRef" in types


def test_find_nodes_returns_correct_type():
    node = parse("SUM([Sales]) + [Profit]")
    refs = find_nodes(node, FieldRef)
    assert len(refs) == 2
    names = {r.name for r in refs}
    assert names == {"Sales", "Profit"}


# ---------------------------------------------------------------------------
# FUNCTION_REGISTRY
# ---------------------------------------------------------------------------


def test_function_registry_size():
    assert len(FUNCTION_REGISTRY) >= 100


def test_function_registry_aggregate_functions():
    for name in ("SUM", "AVG", "COUNT", "COUNTD", "MAX", "MIN", "MEDIAN", "ATTR"):
        assert name in FUNCTION_REGISTRY


def test_script_real_deprecated():
    assert "SCRIPT_REAL" in FUNCTION_REGISTRY
    assert FUNCTION_REGISTRY["SCRIPT_REAL"].deprecated is True


def test_deprecated_functions_set():
    assert "SCRIPT_REAL" in DEPRECATED_FUNCTIONS
    assert "SCRIPT_STR" in DEPRECATED_FUNCTIONS


# ---------------------------------------------------------------------------
# Linter
# ---------------------------------------------------------------------------


def test_lint_unknown_function():
    issues = lint("FOOBAR([Sales])")
    rule_names = {i.rule for i in issues}
    assert "UnknownFunctionRule" in rule_names


def test_lint_deprecated_function():
    issues = lint("SCRIPT_REAL('return 1')")
    rule_names = {i.rule for i in issues}
    assert "DeprecatedFunctionRule" in rule_names


def test_lint_nested_if_antipattern():
    formula = "IF [A] THEN IF [B] THEN 1 ELSE 0 END ELSE 2 END"
    issues = lint(formula)
    rule_names = {i.rule for i in issues}
    assert "NestedIfAntiPattern" in rule_names


def test_lint_unknown_field_with_context():
    ctx = LintContext(all_field_captions={"Sales", "Profit"})
    issues = lint("[NonExistentField]", context=ctx)
    rule_names = {i.rule for i in issues}
    assert "UnknownFieldReferenceRule" in rule_names


def test_lint_unknown_field_without_context_no_issue():
    # Without context, UnknownFieldReferenceRule should not fire
    issues = lint("[NonExistentField]", context=None)
    rule_names = {i.rule for i in issues}
    assert "UnknownFieldReferenceRule" not in rule_names


def test_lint_workbook_returns_list():
    wb = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    issues = lint_workbook(wb)
    assert isinstance(issues, list)
    # All should be LintIssue instances
    for issue in issues:
        assert isinstance(issue, LintIssue)


def test_lint_issue_to_dict():
    issues = lint("SCRIPT_REAL('return 1')")
    assert len(issues) > 0
    d = issues[0].to_dict()
    assert "rule" in d
    assert "message" in d
    assert "severity" in d
