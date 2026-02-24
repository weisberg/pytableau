"""Tableau formula parser using the lark parsing library.

Requires the optional ``[analysis]`` extra::

    pip install "pytableau[analysis]"

Usage::

    from pytableau.calculations.parser import parse, parse_safe

    ast = parse("SUM([Sales]) / COUNT([Orders])")
    ast_or_none = parse_safe("invalid |||")
"""

from __future__ import annotations

from typing import Any

from pytableau.calculations.ast import (
    BinOp,
    BoolLiteral,
    CaseExpr,
    DateLiteral,
    FieldRef,
    FormulaNode,
    FuncCall,
    IfExpr,
    LodExpr,
    NullLiteral,
    NumberLiteral,
    StringLiteral,
    UnaryOp,
)

# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------

_GRAMMAR = r"""
?start: expr

?expr: or_expr

?or_expr: and_expr
        | or_expr _OR and_expr  -> or_op

?and_expr: not_expr
         | and_expr _AND not_expr -> and_op

?not_expr: compare_expr
         | _NOT not_expr         -> not_op

?compare_expr: add_expr
             | compare_expr _EQ  add_expr -> eq_op
             | compare_expr _NEQ add_expr -> neq_op
             | compare_expr _LT  add_expr -> lt_op
             | compare_expr _LTE add_expr -> lte_op
             | compare_expr _GT  add_expr -> gt_op
             | compare_expr _GTE add_expr -> gte_op

?add_expr: mul_expr
         | add_expr "+" mul_expr -> add_op
         | add_expr "-" mul_expr -> sub_op

?mul_expr: unary_expr
         | mul_expr "*" unary_expr -> mul_op
         | mul_expr "/" unary_expr -> div_op
         | mul_expr "%" unary_expr -> mod_op

?unary_expr: primary
           | "-" unary_expr     -> neg_op
           | "+" unary_expr     -> pos_op

?primary: field_ref
        | func_call
        | if_expr
        | case_expr
        | lod_expr
        | number
        | string
        | date_literal
        | bool_literal
        | null_literal
        | "(" expr ")"

// ----- Field references -----
field_ref: "[" FIELD_CHARS "]" "." "[" FIELD_CHARS "]"  -> field_ref_ds
         | "[" FIELD_CHARS "]"                            -> field_ref_simple

FIELD_CHARS: /[^\]]+/

// ----- Function calls -----
func_call: NAME "(" arg_list? ")"
arg_list: expr ("," expr)*

// ----- IF expression -----
if_expr: _IF expr _THEN expr (_ELSEIF expr _THEN expr)* (_ELSE expr)? _END

// ----- CASE expression -----
case_expr: _CASE expr (_WHEN expr _THEN expr)+ (_ELSE expr)? _END

// ----- LOD expression -----
lod_expr: "{" _FIXED field_list ":" expr "}"   -> lod_fixed
        | "{" _INCLUDE field_list ":" expr "}"  -> lod_include
        | "{" _EXCLUDE field_list ":" expr "}"  -> lod_exclude
        | "{" _FIXED ":" expr "}"               -> lod_fixed_no_dims
        | "{" _INCLUDE ":" expr "}"             -> lod_include_no_dims
        | "{" _EXCLUDE ":" expr "}"             -> lod_exclude_no_dims

field_list: field_ref ("," field_ref)*

// ----- Literals -----
number: SIGNED_FLOAT -> float_lit
      | SIGNED_INT   -> int_lit

string: ESCAPED_STRING -> dq_string
      | SQ_STRING      -> sq_string

SQ_STRING: "'" /[^']*/ "'"

date_literal: /#[^#]*#/

bool_literal: TRUE_KW | FALSE_KW

null_literal: _NULL

// ----- Keywords (case-insensitive via terminals) -----
_IF.2:      /(?i:IF)(?!\w)/
_THEN.2:    /(?i:THEN)(?!\w)/
_ELSEIF.2:  /(?i:ELSEIF)(?!\w)/
_ELSE.2:    /(?i:ELSE)(?!\w)/
_END.2:     /(?i:END)(?!\w)/
_CASE.2:    /(?i:CASE)(?!\w)/
_WHEN.2:    /(?i:WHEN)(?!\w)/
_FIXED.2:   /(?i:FIXED)(?!\w)/
_INCLUDE.2: /(?i:INCLUDE)(?!\w)/
_EXCLUDE.2: /(?i:EXCLUDE)(?!\w)/
_AND.2:     /(?i:AND)(?!\w)/
_OR.2:      /(?i:OR)(?!\w)/
_NOT.2:     /(?i:NOT)(?!\w)/
TRUE_KW.2:  /(?i:TRUE)(?!\w)/
FALSE_KW.2: /(?i:FALSE)(?!\w)/
_NULL.2:    /(?i:NULL)(?!\w)/

_EQ:  "=" | "=="
_NEQ: "!=" | "<>"
_LT:  "<"
_LTE: "<="
_GT:  ">"
_GTE: ">="

NAME: /[A-Za-z_][A-Za-z0-9_]*/

%import common.SIGNED_FLOAT
%import common.SIGNED_INT
%import common.ESCAPED_STRING
%import common.WS
%ignore WS
%ignore /\/\/[^\n]*/
"""


class ParseError(Exception):
    """Raised when a formula cannot be parsed."""

    def __init__(self, message: str, formula: str = "") -> None:
        super().__init__(message)
        self.formula = formula


# ---------------------------------------------------------------------------
# Transformer
# ---------------------------------------------------------------------------

def _build_transformer():
    """Build the lark Transformer that converts parse trees to AST nodes."""
    from lxml import etree  # noqa: F401 (just ensure lxml available)
    try:
        from lark import Transformer
    except ImportError as exc:
        raise ImportError(
            "Formula parsing requires lark: pip install 'pytableau[analysis]'"
        ) from exc

    class _T(Transformer):
        # Operators
        def or_op(self, args): return BinOp("OR", args[0], args[1])
        def and_op(self, args): return BinOp("AND", args[0], args[1])
        def not_op(self, args): return UnaryOp("NOT", args[0])
        def eq_op(self, args): return BinOp("=", args[0], args[1])
        def neq_op(self, args): return BinOp("!=", args[0], args[1])
        def lt_op(self, args): return BinOp("<", args[0], args[1])
        def lte_op(self, args): return BinOp("<=", args[0], args[1])
        def gt_op(self, args): return BinOp(">", args[0], args[1])
        def gte_op(self, args): return BinOp(">=", args[0], args[1])
        def add_op(self, args): return BinOp("+", args[0], args[1])
        def sub_op(self, args): return BinOp("-", args[0], args[1])
        def mul_op(self, args): return BinOp("*", args[0], args[1])
        def div_op(self, args): return BinOp("/", args[0], args[1])
        def mod_op(self, args): return BinOp("%", args[0], args[1])
        def neg_op(self, args): return UnaryOp("-", args[0])
        def pos_op(self, args): return UnaryOp("+", args[0])

        # Field references
        def field_ref_simple(self, args): return FieldRef(name=str(args[0]))
        def field_ref_ds(self, args): return FieldRef(datasource=str(args[0]), name=str(args[1]))

        # Function call
        def func_call(self, args):
            name = str(args[0]).upper()
            arg_list = args[1] if len(args) > 1 else []
            return FuncCall(name=name, args=arg_list)

        def arg_list(self, args): return list(args)

        # IF expression
        def if_expr(self, args):
            it = iter(args)
            cond = next(it)
            then = next(it)
            elseif_clauses = []
            else_expr = None
            remaining = list(it)
            # Pairs of (cond, then) for ELSEIF, possibly followed by ELSE
            idx = 0
            while idx + 1 < len(remaining):
                # Check if last element is orphaned (the ELSE)
                if idx + 2 == len(remaining):
                    elseif_clauses.append((remaining[idx], remaining[idx + 1]))
                    idx += 2
                    break
                elseif_clauses.append((remaining[idx], remaining[idx + 1]))
                idx += 2
            if idx < len(remaining):
                else_expr = remaining[idx]
            return IfExpr(
                condition=cond, then_expr=then,
                elseif_clauses=elseif_clauses, else_expr=else_expr
            )

        # CASE expression
        def case_expr(self, args):
            it = iter(args)
            subject = next(it)
            when_clauses = []
            else_expr = None
            remaining = list(it)
            idx = 0
            while idx + 1 < len(remaining):
                if idx + 2 == len(remaining):
                    when_clauses.append((remaining[idx], remaining[idx + 1]))
                    idx += 2
                    break
                when_clauses.append((remaining[idx], remaining[idx + 1]))
                idx += 2
            if idx < len(remaining):
                else_expr = remaining[idx]
            return CaseExpr(subject=subject, when_clauses=when_clauses, else_expr=else_expr)

        # LOD expressions
        def field_list(self, args): return list(args)

        def lod_fixed(self, args): return LodExpr("FIXED", dimensions=list(args[0]) if isinstance(args[0], list) else [args[0]], body=args[1])
        def lod_include(self, args): return LodExpr("INCLUDE", dimensions=list(args[0]) if isinstance(args[0], list) else [args[0]], body=args[1])
        def lod_exclude(self, args): return LodExpr("EXCLUDE", dimensions=list(args[0]) if isinstance(args[0], list) else [args[0]], body=args[1])
        def lod_fixed_no_dims(self, args): return LodExpr("FIXED", dimensions=[], body=args[0])
        def lod_include_no_dims(self, args): return LodExpr("INCLUDE", dimensions=[], body=args[0])
        def lod_exclude_no_dims(self, args): return LodExpr("EXCLUDE", dimensions=[], body=args[0])

        # Literals
        def float_lit(self, args): return NumberLiteral(float(args[0]))
        def int_lit(self, args): return NumberLiteral(float(int(args[0])))
        def dq_string(self, args): return StringLiteral(str(args[0])[1:-1])  # strip quotes
        def sq_string(self, args): return StringLiteral(str(args[0])[1:-1])
        def date_literal(self, args): return DateLiteral(str(args[0])[1:-1])  # strip #...#
        def bool_literal(self, args): return BoolLiteral(str(args[0]).upper() == "TRUE")
        def null_literal(self, args): return NullLiteral()

        # field_ref (alias)
        def field_ref(self, args):
            if len(args) == 2:
                return FieldRef(datasource=str(args[0]), name=str(args[1]))
            return FieldRef(name=str(args[0]))

    return _T()


# Lazy-initialized parser
_parser_instance: Any = None
_transformer_instance: Any = None


def _get_parser() -> Any:
    global _parser_instance, _transformer_instance
    if _parser_instance is None:
        try:
            from lark import Lark
        except ImportError as exc:
            raise ImportError(
                "Formula parsing requires lark: pip install 'pytableau[analysis]'"
            ) from exc
        _parser_instance = Lark(
            _GRAMMAR,
            parser="earley",
            ambiguity="resolve",
            start="start",
        )
        _transformer_instance = _build_transformer()
    return _parser_instance, _transformer_instance


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse(formula: str) -> FormulaNode:
    """Parse a Tableau formula string and return the root AST node.

    Raises:
        ParseError: If the formula cannot be parsed.
        ImportError: If lark is not installed.
    """
    lark_parser, transformer = _get_parser()
    try:
        tree = lark_parser.parse(formula.strip())
        return transformer.transform(tree)
    except Exception as exc:
        raise ParseError(f"Cannot parse formula: {exc}", formula=formula) from exc


def parse_safe(formula: str) -> FormulaNode | None:
    """Parse a formula, returning ``None`` on any error (no exception raised)."""
    try:
        return parse(formula)
    except Exception:
        return None
