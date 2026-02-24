"""02_field_dependency_tree.py

Print an ASCII dependency tree for every calculated field in a workbook,
showing which fields each calculation depends on (and transitively, which
fields those depend on).

Usage:
    python examples/02_field_dependency_tree.py <workbook> [datasource_name]
    python examples/02_field_dependency_tree.py tests/fixtures/single_datasource_v2023_1.twb

Requirements: pip install pytableau
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from pytableau import Workbook


def build_dep_map(wb: Workbook) -> dict[str, list[str]]:
    """Return {field_caption: [direct_dependency_captions]} for all calc fields."""
    dep_map: dict[str, list[str]] = {}
    for ds in wb.datasources:
        for cf in ds.calculated_fields:
            if not cf.caption:
                continue
            entry = wb.lineage()
            # Find this field's entry in the lineage graph
            for e in entry.entries:
                if e.field == cf.caption:
                    dep_map[cf.caption] = list(e.depends_on)
                    break
            else:
                dep_map[cf.caption] = []
    return dep_map


def print_tree(
    field: str,
    dep_map: dict[str, list[str]],
    visited: set[str],
    prefix: str = "",
    is_last: bool = True,
) -> None:
    connector = "└── " if is_last else "├── "
    tag = " (cyclic)" if field in visited else ""
    print(f"{prefix}{connector}{field}{tag}")

    if field in visited:
        return
    visited = visited | {field}

    children = dep_map.get(field, [])
    child_prefix = prefix + ("    " if is_last else "│   ")
    for i, child in enumerate(children):
        print_tree(child, dep_map, visited, child_prefix, i == len(children) - 1)


def main(workbook_path: str, datasource_name: str | None = None) -> None:
    wb = Workbook.open(workbook_path)
    print(f"\nField Dependency Tree — {Path(workbook_path).name}  (v{wb.version})\n")

    for ds in wb.datasources:
        if datasource_name and ds.name != datasource_name and ds.caption != datasource_name:
            continue
        calcs = list(ds.calculated_fields)
        if not calcs:
            continue

        print(f"  Datasource: {ds.caption or ds.name}")
        print(f"  {'─' * 50}")

        lineage = wb.lineage()
        dep_map: dict[str, list[str]] = {}
        for entry in lineage.entries:
            dep_map[entry.field] = list(entry.depends_on)

        # Find root calculations (not depended on by any other calc)
        all_deps: set[str] = set()
        for deps in dep_map.values():
            all_deps.update(deps)
        roots = [c.caption for c in calcs if c.caption and c.caption not in all_deps]

        if not roots:
            roots = [c.caption for c in calcs if c.caption]

        for i, root in enumerate(roots):
            print_tree(root, dep_map, set(), "  ", i == len(roots) - 1)

        print()

    # Summary table
    print(f"  {'Field':<40} {'# Deps':>6}  Formula (truncated)")
    print(f"  {'─' * 40} {'──────':>6}  {'─' * 30}")
    for ds in wb.datasources:
        for cf in ds.calculated_fields:
            if not cf.caption:
                continue
            deps = dep_map.get(cf.caption, [])
            formula_preview = (cf.formula or "")[:30].replace("\n", " ")
            if len(cf.formula or "") > 30:
                formula_preview += "…"
            print(f"  {cf.caption:<40} {len(deps):>6}  {formula_preview}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ds_name = sys.argv[2] if len(sys.argv) > 2 else None
    main(sys.argv[1], ds_name)
