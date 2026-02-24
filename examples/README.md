# pytableau Examples

Ten self-contained example scripts that demonstrate real-world usage patterns.
Each script is runnable from the repository root and includes inline documentation.

| # | Script | What it demonstrates |
|---|---|---|
| 01 | `01_connection_promoter.py` | Promote a workbook across environments (dev → staging → prod) using `PromotionConfig` |
| 02 | `02_field_dependency_tree.py` | Print an ASCII dependency tree of all calculated fields via `wb.lineage()` |
| 03 | `03_lod_expression_auditor.py` | Parse every formula with the lark AST and inventory all `{FIXED}` / `{INCLUDE}` / `{EXCLUDE}` expressions |
| 04 | `04_diff_html_report.py` | Compare two workbook versions and generate a self-contained HTML change report |
| 05 | `05_canonical_snapshot.py` | Create `.canonical.json` + `.clean.twb` sidecars for version-control-friendly storage |
| 06 | `06_batch_report_generator.py` | Generate N workbooks from a single template and a configuration table |
| 07 | `07_workbook_health_check.py` | Run a comprehensive terminal health check: complexity grade, lint, validation, catalog, connections |
| 08 | `08_deprecated_function_scanner.py` | Scan a workbook (or directory) for deprecated `SCRIPT_*` / `RAWSQL_*` functions |
| 09 | `09_patch_roundtrip.py` | Full Patch lifecycle: diff → serialize → store → restore → apply |
| 10 | `10_formula_complexity_scorer.py` | Score and rank every calculated field by formula complexity (LOD depth, IF nesting, node count) |

---

## Requirements

```bash
# Core examples (01–02, 04–06, 09)
pip install pytableau

# Formula parser examples (03, 07, 08, 10)
pip install "pytableau[analysis]"

# Health check (07) uses both core and analysis
pip install "pytableau[analysis]"
```

---

## Quick Start

All scripts accept a workbook path as the first argument. The repository
ships with several fixtures you can use immediately:

```bash
# Environment promotion (uses connection swap — works on any workbook)
python examples/01_connection_promoter.py tests/fixtures/minimal_v2022_4.twb dev prod

# Field dependency tree
python examples/02_field_dependency_tree.py tests/fixtures/single_datasource_v2023_1.twb

# LOD expression audit (works best with the LOD-heavy fixture)
python examples/03_lod_expression_auditor.py tests/fixtures/lod_heavy_v2024_1.twb

# HTML diff report
python examples/04_diff_html_report.py \
    tests/fixtures/minimal_v2022_4.twb \
    tests/fixtures/modified_v2024_1.twb \
    diff_report.html

# Canonical snapshot (creates sidecar files next to the source)
python examples/05_canonical_snapshot.py tests/fixtures/minimal_v2022_4.twb

# Batch report generator
python examples/06_batch_report_generator.py \
    tests/fixtures/minimal_v2022_4.twb \
    /tmp/batch_output

# Workbook health check (requires pytableau[analysis])
python examples/07_workbook_health_check.py tests/fixtures/lod_heavy_v2024_1.twb

# Deprecated function scanner — scan entire fixtures directory
python examples/08_deprecated_function_scanner.py tests/fixtures/

# Patch roundtrip demo
python examples/09_patch_roundtrip.py \
    tests/fixtures/minimal_v2022_4.twb \
    tests/fixtures/modified_v2024_1.twb

# Formula complexity scorer (requires pytableau[analysis])
python examples/10_formula_complexity_scorer.py tests/fixtures/lod_heavy_v2024_1.twb
```

---

## Notes

- Scripts are designed to be read as well as run — each is ~60–120 lines with explanatory comments.
- No script modifies the `tests/fixtures/` files; all output goes to temp paths or a specified output directory.
- Script 07 (`health_check`) uses ANSI color codes — pipe through `cat` if your terminal doesn't support them.
