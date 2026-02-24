"""08_deprecated_function_scanner.py

Scan a workbook (or a whole directory of workbooks) for usage of deprecated
Tableau functions — especially the SCRIPT_* and RAWSQL_* family, which were
silently archived when TabPy was archived in December 2025.

For each hit, shows the field name, the deprecated function, and a suggested
modern replacement.

Usage:
    python examples/08_deprecated_function_scanner.py <workbook_or_dir>
    python examples/08_deprecated_function_scanner.py tests/fixtures/
    python examples/08_deprecated_function_scanner.py tests/fixtures/lod_heavy_v2024_1.twb

Requirements: pip install "pytableau[analysis]"
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from pytableau import Workbook
from pytableau.calculations.ast import FuncCall, find_nodes
from pytableau.calculations.functions import FUNCTION_REGISTRY
from pytableau.calculations.parser import parse_safe

# Map deprecated function → suggested replacement
REPLACEMENTS: dict[str, str] = {
    "SCRIPT_REAL":    "Use Python analytics extensions or a pre-computed field",
    "SCRIPT_STR":     "Use Python analytics extensions or a pre-computed field",
    "SCRIPT_INT":     "Use Python analytics extensions or a pre-computed field",
    "SCRIPT_BOOL":    "Use Python analytics extensions or a pre-computed field",
    "RAWSQL_REAL":    "Use a native database connection with RAWSQL disabled",
    "RAWSQL_STR":     "Use a native database connection with RAWSQL disabled",
    "RAWSQL_INT":     "Use a native database connection with RAWSQL disabled",
    "RAWSQL_BOOL":    "Use a native database connection with RAWSQL disabled",
    "RAWSQLAGG_REAL": "Replace with a certified datasource custom SQL query",
    "RAWSQLAGG_STR":  "Replace with a certified datasource custom SQL query",
}


@dataclass
class Hit:
    workbook: str
    datasource: str
    field: str
    function: str
    note: str
    formula_snippet: str


def scan_workbook(path: Path) -> list[Hit]:
    hits: list[Hit] = []
    try:
        wb = Workbook.open(path)
    except Exception as e:
        print(f"  WARN: could not open {path.name}: {e}")
        return []

    for ds in wb.datasources:
        for cf in ds.calculated_fields:
            if not cf.formula or not cf.caption:
                continue
            ast = parse_safe(cf.formula)
            if ast is None:
                continue
            for call in find_nodes(ast, FuncCall):
                fn_upper = call.name.upper()
                info = FUNCTION_REGISTRY.get(fn_upper)
                if info and info.deprecated:
                    snippet = cf.formula[:60].replace("\n", " ")
                    hits.append(Hit(
                        workbook=path.name,
                        datasource=ds.caption or ds.name,
                        field=cf.caption,
                        function=fn_upper,
                        note=REPLACEMENTS.get(fn_upper, info.deprecation_note or "No replacement noted"),
                        formula_snippet=snippet,
                    ))
    return hits


def scan(target: str) -> None:
    target_path = Path(target)
    files: list[Path] = []

    if target_path.is_dir():
        files = sorted(target_path.glob("**/*.twb")) + sorted(target_path.glob("**/*.twbx"))
    elif target_path.exists():
        files = [target_path]
    else:
        print(f"Error: path not found: {target}")
        sys.exit(1)

    print(f"\nDeprecated Function Scanner")
    print(f"Target: {target_path}  ({len(files)} workbook(s))\n")

    all_hits: list[Hit] = []
    for f in files:
        hits = scan_workbook(f)
        all_hits.extend(hits)

    if not all_hits:
        print("  ✓ No deprecated functions found across all workbooks.\n")
        return

    # Group by workbook
    by_wb: dict[str, list[Hit]] = {}
    for h in all_hits:
        by_wb.setdefault(h.workbook, []).append(h)

    for wb_name, hits in by_wb.items():
        print(f"  {wb_name}  ({len(hits)} hit(s))")
        print(f"  {'─' * 60}")
        for h in hits:
            print(f"  ✗ {h.field}")
            print(f"      Function:  {h.function}")
            print(f"      Formula:   {h.formula_snippet}{'…' if len(h.formula_snippet)==60 else ''}")
            print(f"      Guidance:  {h.note}")
            print()

    # Summary by function
    func_counts: dict[str, int] = {}
    for h in all_hits:
        func_counts[h.function] = func_counts.get(h.function, 0) + 1

    print(f"{'─' * 60}")
    print(f"  Total hits: {len(all_hits)}  across {len(by_wb)} workbook(s)\n")
    print(f"  By function:")
    for fn, cnt in sorted(func_counts.items(), key=lambda x: -x[1]):
        print(f"    {fn:<20} {cnt} occurrence(s)")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    scan(sys.argv[1])
