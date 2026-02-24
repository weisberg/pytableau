"""03_lod_expression_auditor.py

Parse every calculated field in a workbook and extract a detailed inventory
of all LOD expressions ({FIXED}, {INCLUDE}, {EXCLUDE}) — the most complex
and performance-sensitive constructs in Tableau.

For each LOD found, reports:
  • Which field it lives in
  • The LOD type (FIXED / INCLUDE / EXCLUDE)
  • The dimension(s) it locks to
  • Nesting depth (LOD inside LOD is a performance red flag)

Usage:
    python examples/03_lod_expression_auditor.py <workbook>
    python examples/03_lod_expression_auditor.py tests/fixtures/lod_heavy_v2024_1.twb

Requirements: pip install "pytableau[analysis]"
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from pytableau import Workbook
from pytableau.calculations.ast import FieldRef, LodExpr, find_nodes
from pytableau.calculations.parser import ParseError, parse_safe


@dataclass
class LodFinding:
    datasource: str
    field: str
    lod_type: str
    dimensions: list[str]
    nesting_depth: int
    snippet: str  # formula context around the LOD


def lod_nesting_depth(node: LodExpr) -> int:
    """Recursively compute the maximum LOD nesting depth."""
    nested = find_nodes(node.body, LodExpr)
    if not nested:
        return 1
    return 1 + max(lod_nesting_depth(n) for n in nested)


def audit_workbook(wb: Workbook) -> list[LodFinding]:
    findings: list[LodFinding] = []

    for ds in wb.datasources:
        for cf in ds.calculated_fields:
            if not cf.formula or not cf.caption:
                continue
            ast = parse_safe(cf.formula)
            if ast is None:
                continue

            lod_nodes = find_nodes(ast, LodExpr)
            for lod in lod_nodes:
                dims = [ref.name for ref in lod.dimensions if isinstance(ref, FieldRef)]
                depth = lod_nesting_depth(lod)
                snippet = cf.formula[:80].replace("\n", " ")
                findings.append(
                    LodFinding(
                        datasource=ds.caption or ds.name,
                        field=cf.caption,
                        lod_type=lod.lod_type,
                        dimensions=dims,
                        nesting_depth=depth,
                        snippet=snippet,
                    )
                )

    return findings


def main(workbook_path: str) -> None:
    wb = Workbook.open(workbook_path)
    findings = audit_workbook(wb)

    print(f"\nLOD Expression Audit — {Path(workbook_path).name}  (v{wb.version})")
    print(f"{'=' * 65}\n")

    if not findings:
        print("  No LOD expressions found.")
        return

    # Group by datasource
    by_ds: dict[str, list[LodFinding]] = {}
    for f in findings:
        by_ds.setdefault(f.datasource, []).append(f)

    total_nested = sum(1 for f in findings if f.nesting_depth > 1)

    for ds_name, ds_findings in by_ds.items():
        print(f"  Datasource: {ds_name}  ({len(ds_findings)} LOD expression(s))")
        print(f"  {'─' * 60}")
        for f in ds_findings:
            depth_flag = f"  ⚠ depth={f.nesting_depth}" if f.nesting_depth > 1 else ""
            dim_str = ", ".join(f.dimensions) if f.dimensions else "(no dimensions)"
            print(f"  Field:  {f.field}")
            print(f"  Type:   {{{f.lod_type} [{dim_str}] : ...}}{depth_flag}")
            print(f"  Formula: {f.snippet}{'…' if len(f.snippet) == 80 else ''}")
            print()

    # Summary
    print(f"{'─' * 65}")
    print(f"  Total LODs:            {len(findings)}")
    print(f"  FIXED:                 {sum(1 for f in findings if f.lod_type == 'FIXED')}")
    print(f"  INCLUDE:               {sum(1 for f in findings if f.lod_type == 'INCLUDE')}")
    print(f"  EXCLUDE:               {sum(1 for f in findings if f.lod_type == 'EXCLUDE')}")
    print(f"  Nested LODs (depth>1): {total_nested}"
          + ("  ← consider refactoring" if total_nested else ""))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
