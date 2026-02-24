"""07_workbook_health_check.py

Run a comprehensive health check on a Tableau workbook and print a
structured terminal report covering:

  • Complexity grade (A–F)
  • Validation issues (errors / warnings / info)
  • Formula lint issues (deprecated functions, cyclic deps, unknown fields)
  • Catalog stats (unused fields, orphaned calculations, custom SQL)
  • Connection inventory

Think of it as `pylint` or `ruff check`, but for Tableau workbooks.

Usage:
    python examples/07_workbook_health_check.py <workbook>
    python examples/07_workbook_health_check.py tests/fixtures/lod_heavy_v2024_1.twb

Requirements: pip install "pytableau[analysis]"
"""

from __future__ import annotations

import sys
from pathlib import Path


def severity_icon(level: str) -> str:
    return {"error": "✗", "warning": "⚠", "info": "ℹ"}.get(level.lower(), "•")


def grade_color(grade: str) -> str:
    return {"A": "\033[92m", "B": "\033[92m", "C": "\033[93m",
            "D": "\033[93m", "E": "\033[91m", "F": "\033[91m"}.get(grade, "")


RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"


def section(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")
    print("─" * 55)


def main(workbook_path: str) -> None:
    from pytableau import Workbook

    wb = Workbook.open(workbook_path)
    name = Path(workbook_path).name

    print(f"\n{BOLD}Workbook Health Check{RESET}  —  {name}")
    print(f"{DIM}Version {wb.version}  •  "
          f"{len(list(wb.datasources))} datasource(s)  •  "
          f"{len(list(wb.worksheets))} worksheet(s)  •  "
          f"{len(list(wb.dashboards))} dashboard(s){RESET}")

    # ── Complexity ──────────────────────────────────────────────────────────
    section("Complexity")
    report = wb.complexity_report()
    color = grade_color(report.grade)
    print(f"  Grade:   {color}{BOLD}{report.grade}{RESET}   Score: {report.score:.0f}/100")
    print(f"  {report.summary}")

    # ── Validation ──────────────────────────────────────────────────────────
    section("Validation")
    val_issues = wb.validate()
    if not val_issues:
        print("  ✓ No validation issues")
    else:
        counts = {"error": 0, "warning": 0, "info": 0}
        for i in val_issues:
            lvl = getattr(i, "level", "info").lower()
            counts[lvl] = counts.get(lvl, 0) + 1
        print(f"  Errors: {counts['error']}  Warnings: {counts['warning']}  Info: {counts['info']}")
        for i in sorted(val_issues, key=lambda x: x.level)[:10]:
            icon = severity_icon(getattr(i, "level", "info"))
            print(f"    {icon} [{getattr(i,'level','?'):7}] {i.message}")
        if len(val_issues) > 10:
            print(f"    {DIM}… and {len(val_issues)-10} more{RESET}")

    # ── Formula Lint ────────────────────────────────────────────────────────
    section("Formula Lint")
    try:
        from pytableau.calculations.linter import lint_workbook
        lint_issues = lint_workbook(wb)
        if not lint_issues:
            print("  ✓ No lint issues")
        else:
            counts: dict[str, int] = {}
            for i in lint_issues:
                counts[i.rule] = counts.get(i.rule, 0) + 1
            for rule, cnt in sorted(counts.items(), key=lambda x: -x[1]):
                print(f"  {severity_icon('warning')} {rule}: {cnt} occurrence(s)")
    except ImportError:
        print(f"  {DIM}(skipped — install pytableau[analysis]){RESET}")

    # ── Catalog ─────────────────────────────────────────────────────────────
    section("Field Catalog")
    catalog = wb.catalog()
    unused   = catalog.unused_fields()
    orphaned = catalog.orphaned_calcs()
    sql      = catalog.custom_sql_audit()

    all_fields = sum(len(ds.all_fields) for ds in wb.datasources)
    all_calcs  = sum(len(ds.calculated_fields) for ds in wb.datasources)

    print(f"  Total fields:      {all_fields}")
    print(f"  Calculated fields: {all_calcs}")
    print(f"  Unused fields:     {len(unused)}"
          + (f"  ← consider removing" if unused else "  ✓"))
    print(f"  Orphaned calcs:    {len(orphaned)}"
          + (f"  ← broken dependencies" if orphaned else "  ✓"))
    print(f"  Custom SQL blocks: {len(sql)}"
          + (f"  ← review for injection risk" if sql else "  ✓"))

    if orphaned:
        for c in orphaned[:5]:
            print(f"    ⚠ {getattr(c,'caption','?')}")

    # ── Connections ─────────────────────────────────────────────────────────
    section("Connections")
    for ds in wb.datasources:
        if ds.is_parameters:
            continue
        for conn in ds.connections:
            server = conn.server or "(embedded)"
            db     = conn.dbname or "(no db)"
            cls    = conn.class_ or "unknown"
            print(f"  {ds.caption or ds.name:<28}  {cls:<12}  {server}  /  {db}")

    # ── Overall score ───────────────────────────────────────────────────────
    error_count  = sum(1 for i in val_issues if getattr(i, "level", "") == "error")
    lint_count   = len(lint_issues) if "lint_issues" in dir() else 0
    health_score = max(0, 100 - error_count * 20 - lint_count * 5 - len(orphaned) * 3)
    color = "\033[92m" if health_score >= 80 else "\033[93m" if health_score >= 50 else "\033[91m"

    print(f"\n{'═' * 55}")
    print(f"  Overall Health: {color}{BOLD}{health_score}/100{RESET}")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
