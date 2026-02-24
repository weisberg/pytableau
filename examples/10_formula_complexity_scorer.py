"""10_formula_complexity_scorer.py

Score every calculated field by formula complexity and rank them from
most to least complex. Complexity is a composite of:

  • AST node count        — raw formula size
  • LOD depth            — {FIXED} nesting = expensive query
  • IF nesting depth     — hard to read, often sign of CASE refactor needed
  • Distinct function calls — breadth of Tableau API surface used
  • Unique field refs    — coupling: how many fields does this touch?

Outputs a ranked table and flags the top offenders.

Usage:
    python examples/10_formula_complexity_scorer.py <workbook>
    python examples/10_formula_complexity_scorer.py tests/fixtures/lod_heavy_v2024_1.twb

Requirements: pip install "pytableau[analysis]"
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from pytableau import Workbook
from pytableau.calculations.ast import (
    FieldRef,
    FuncCall,
    IfExpr,
    LodExpr,
    FormulaNode,
    find_nodes,
    walk,
)
from pytableau.calculations.parser import parse_safe


@dataclass
class FormulaScore:
    datasource: str
    field: str
    formula: str

    node_count: int = 0
    lod_max_depth: int = 0
    if_max_depth: int = 0
    distinct_functions: int = 0
    unique_field_refs: int = 0

    @property
    def composite(self) -> float:
        """Weighted composite complexity score."""
        return (
            self.node_count * 1.0
            + self.lod_max_depth * 15.0
            + self.if_max_depth * 8.0
            + self.distinct_functions * 3.0
            + self.unique_field_refs * 2.0
        )


def _lod_depth(node: LodExpr) -> int:
    nested = find_nodes(node.body, LodExpr)
    return 1 + (max((_lod_depth(n) for n in nested), default=0))


def _if_depth(node: FormulaNode, depth: int = 0) -> int:
    if isinstance(node, IfExpr):
        depth += 1
        child_max = max(
            (_if_depth(child, depth) for child in
             [node.condition, node.then_expr]
             + [e for pair in node.elseif_clauses for e in pair]
             + ([node.else_expr] if node.else_expr else [])),
            default=depth,
        )
        return child_max
    return depth


def score_formula(datasource: str, field: str, formula: str) -> FormulaScore | None:
    ast = parse_safe(formula)
    if ast is None:
        return None

    score = FormulaScore(datasource=datasource, field=field, formula=formula)

    # Count all AST nodes
    all_nodes: list[FormulaNode] = []
    walk(ast, all_nodes.append)
    score.node_count = len(all_nodes)

    # LOD nesting
    lods = find_nodes(ast, LodExpr)
    score.lod_max_depth = max((_lod_depth(lod) for lod in lods), default=0)

    # IF nesting
    score.if_max_depth = _if_depth(ast)

    # Distinct function names
    funcs = find_nodes(ast, FuncCall)
    score.distinct_functions = len({f.name.upper() for f in funcs})

    # Unique field references
    refs = find_nodes(ast, FieldRef)
    score.unique_field_refs = len({r.name for r in refs})

    return score


def main(workbook_path: str) -> None:
    wb = Workbook.open(workbook_path)
    name = Path(workbook_path).name

    print(f"\nFormula Complexity Scorer — {name}  (v{wb.version})\n")

    scores: list[FormulaScore] = []
    parse_errors = 0

    for ds in wb.datasources:
        for cf in ds.calculated_fields:
            if not cf.formula or not cf.caption:
                continue
            s = score_formula(ds.caption or ds.name, cf.caption, cf.formula)
            if s is None:
                parse_errors += 1
            else:
                scores.append(s)

    if not scores:
        print("  No scoreable calculated fields found.")
        return

    scores.sort(key=lambda s: s.composite, reverse=True)

    # Header
    print(f"  {'#':>3}  {'Field':<35} {'Score':>7}  "
          f"{'Nodes':>6} {'LOD':>4} {'IF':>4} {'Fns':>4} {'Refs':>5}")
    print(f"  {'─'*3}  {'─'*35} {'─'*7}  "
          f"{'─'*6} {'─'*4} {'─'*4} {'─'*4} {'─'*5}")

    for rank, s in enumerate(scores, 1):
        flag = " ⚠" if s.composite > 80 else ""
        field_str = s.field[:34] + "…" if len(s.field) > 35 else s.field
        print(f"  {rank:>3}  {field_str:<35} {s.composite:>7.1f}  "
              f"{s.node_count:>6} {s.lod_max_depth:>4} {s.if_max_depth:>4} "
              f"{s.distinct_functions:>4} {s.unique_field_refs:>5}{flag}")

    print()

    # Top offenders deep-dive
    offenders = [s for s in scores if s.composite > 80]
    if offenders:
        print(f"  Top Offenders ({len(offenders)} field(s) with score > 80):")
        for s in offenders[:3]:
            print(f"\n  ► {s.field}  [{s.datasource}]  score={s.composite:.1f}")
            if s.lod_max_depth > 1:
                print(f"    LOD nesting depth {s.lod_max_depth} — consider splitting into intermediate calcs")
            if s.if_max_depth > 2:
                print(f"    IF nesting depth {s.if_max_depth} — CASE/WHEN would improve readability")
            if s.node_count > 50:
                print(f"    {s.node_count} AST nodes — formula is very large, consider decomposing")
            snippet = s.formula[:100].replace("\n", " ")
            print(f"    Formula: {snippet}{'…' if len(s.formula)>100 else ''}")

    print(f"\n  {'─'*55}")
    print(f"  Fields scored:   {len(scores)}")
    print(f"  Parse errors:    {parse_errors}")
    avg = sum(s.composite for s in scores) / len(scores)
    print(f"  Average score:   {avg:.1f}")
    print(f"  Max score:       {scores[0].composite:.1f}  ({scores[0].field})")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
