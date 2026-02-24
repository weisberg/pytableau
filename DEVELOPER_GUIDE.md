# pytableau Developer Guide

**Version:** 0.9.0
**Python:** 3.10+
**License:** MIT

---

## Table of Contents

1. [Introduction & Architecture](#1-introduction--architecture)
2. [Installation](#2-installation)
3. [Quick Start](#3-quick-start)
4. [Workbook Lifecycle](#4-workbook-lifecycle)
5. [Datasources, Connections & Fields](#5-datasources-connections--fields)
6. [Worksheets & Dashboards](#6-worksheets--dashboards)
7. [Mutations](#7-mutations)
8. [Inspection & Analysis](#8-inspection--analysis)
9. [Semantic Diff & Patch](#9-semantic-diff--patch)
10. [Formula Parser & Linter](#10-formula-parser--linter)
11. [Hyper Extract Management](#11-hyper-extract-management)
12. [Template Engine](#12-template-engine)
13. [Server Integration](#13-server-integration)
14. [Packaging & ZIP](#14-packaging--zip)
15. [Validation & Auto-Fix](#15-validation--auto-fix)
16. [Environment Promotion](#16-environment-promotion)
17. [CLI Reference](#17-cli-reference)
18. [Exceptions & Error Handling](#18-exceptions--error-handling)
19. [Enumerations](#19-enumerations)
20. [Testing Patterns](#20-testing-patterns)
21. [Architecture Reference](#21-architecture-reference)

---

## 1. Introduction & Architecture

`pytableau` is a unified Python SDK for every layer of Tableau workbook engineering. Where `tableaudocumentapi` covers roughly 15% of `.twb` XML structure and was abandoned in 2022, `pytableau` provides a complete, maintained, Pythonic API across five architectural layers:

| Layer | Module | Responsibility |
|---|---|---|
| **L0 — XML & ZIP** | `pytableau.xml.*`, `pytableau.package.*` | Raw XML parsing, ZIP management, round-trip fidelity, deterministic serialization |
| **L1 — Object Model** | `pytableau.core.*` | `Workbook → Datasource → Field`, `Worksheet → Dashboard`; write-through mutations |
| **L2 — Data** | `pytableau.data.*` | DataFrame ↔ Hyper conversion, extract lifecycle |
| **L3 — Server** | `pytableau.server.*` | REST API wrapper, GraphQL Metadata API |
| **L4 — Application** | `pytableau.inspect.*`, `pytableau.calculations.*`, `pytableau.templates.*` | Diff, lint, complexity, lineage, catalog, templates |

### Design Principles

- **Round-trip fidelity** — opening a `.twb` and saving without changes produces semantically equivalent output. Golden fixtures verify this on every commit.
- **Fail loud, fail early** — a validation gate blocks corrupt XML before it reaches disk. A workbook that errors only inside Tableau Desktop is the worst possible outcome.
- **Dependency-light** — core requires only `lxml`. Every optional feature (`hyper`, `server`, `analysis`, `cli`) is an explicit extra.
- **Secure defaults** — XML parsing disables entity resolution and network access. Credentials are scrubbed from connections before any `save_as()`.
- **Version-aware** — Tableau workbook version is tracked; version-specific rules apply.

---

## 2. Installation

```bash
# Core only (lxml)
pip install pytableau

# Formula parser + linter (adds lark, networkx, jinja2)
pip install "pytableau[analysis]"

# Hyper extract management (adds tableauhyperapi, pantab)
pip install "pytableau[hyper]"

# Server integration (adds tableauserverclient, requests)
pip install "pytableau[server]"

# CLI commands (adds tooli)
pip install "pytableau[cli]"

# Everything
pip install "pytableau[all]"
```

Verify the install:

```bash
python -c "import pytableau; print(pytableau.__version__)"
pytableau --help      # requires [cli]
```

---

## 3. Quick Start

```python
from pytableau import Workbook

# Open any Tableau workbook
wb = Workbook.open("sales_dashboard.twbx")

# Inspect
print(wb.version)                        # "2024.1"
print([ds.name for ds in wb.datasources])

# Swap a connection for deployment
result = wb.swap_connection(
    where={"server": "dev-db.example.com"},
    to={"server": "prod-db.example.com", "dbname": "analytics_prod"},
)
print(f"Updated {result.updated_count} connection(s)")

# Validate and save
issues = wb.validate()
errors = [i for i in issues if i.level == "error"]
if not errors:
    wb.save_as("sales_dashboard_prod.twbx", scrub_credentials=True)
```

---

## 4. Workbook Lifecycle

### Opening

```python
from pytableau import Workbook

# Standard open
wb = Workbook.open("report.twbx")

# With options
wb = Workbook.open(
    "report.twbx",
    strict=False,           # If True, rejects excessively large XML trees
    compatibility=False,    # If True, warns when root tag is not <workbook>
    streaming=False,        # If True, skips worksheets/dashboards (faster for data-only ops)
    twb_hint=None,          # Filename hint for archives containing multiple .twb files
)

# Context manager — automatically calls close() on exit
with Workbook.open("report.twbx") as wb:
    print(wb.version)
```

### Creating New Workbooks

```python
# Blank workbook at a given Tableau version
wb = Workbook.new(version="2024.1")

# From a built-in template (see §12)
wb = Workbook.from_template("bar_chart")

# From a custom template file
wb = Workbook.from_template("/path/to/my_template.twb")
```

### Saving

```python
wb.save()                            # Overwrite source file (requires source_path)
wb.save_as("output.twbx")           # Save to new path
wb.save_as("output.twbx", scrub_credentials=True)  # Strip passwords (default: True)
```

`save_as()` always runs the validation gate before writing. If errors are present, it raises `InvalidWorkbookError` unless you pass `validate=False`.

### Workbook Properties

```python
wb.version           # str: Tableau Desktop version, e.g. "2024.1"
wb.source_platform   # str | None: "win", "mac", or "python"
wb.datasources       # DatasourceCollection: list-like, keyed by name
wb.worksheets        # WorksheetCollection: list-like, keyed by name
wb.dashboards        # DashboardCollection: list-like, keyed by name
wb.parameters        # Datasource | None: the special Parameters datasource
wb.xml_tree          # etree._ElementTree: underlying lxml tree
wb.xml_root          # etree._Element: root <workbook> element
```

---

## 5. Datasources, Connections & Fields

### Accessing Datasources

```python
# List all names
names = wb.datasources.names        # list[str]

# By name (raises DatasourceNotFoundError if missing)
ds = wb.datasources["Sales Data"]

# Iterate
for ds in wb.datasources:
    print(ds.name, ds.caption)

# Parameters datasource (special)
params_ds = wb.parameters
```

### Datasource Properties

```python
ds.name              # str: internal XML identifier
ds.caption           # str: human-readable display name
ds.is_parameters     # bool: True only for the Parameters datasource
ds.connections       # list[Connection]
ds.relations         # list[Relation]: JOIN tree (v0.6+)
ds.fields            # list[Field]: non-calculated, non-parameter fields
ds.calculated_fields # list[CalculatedField]
ds.parameters        # list[Parameter]
ds.all_fields        # list[Field]: all three combined
ds.metadata_records  # list[MetadataRecord]: lazy-cached schema from XML (v0.6+)
ds.xml_node          # etree._Element: raw <datasource> XML node
```

### Connections

```python
conn = ds.connections[0]
conn.class_          # str | None: "sqlserver", "postgres", "mysql", "hyper", etc.
conn.server          # str | None: hostname or server address
conn.port            # int | None: TCP port
conn.dbname          # str | None: database name
conn.username        # str | None

# Mutate in-place (reflected immediately in the XML tree)
conn.server = "new-host.example.com"
conn.port = 5432
conn.dbname = "analytics"
conn.username = "svc_tableau"
```

### Fields

```python
from pytableau import DataType, Role

field = ds.fields[0]
field.caption        # str: display name shown in Tableau
field.role           # Role: "dimension" or "measure"
field.datatype       # DataType: "string", "integer", "real", "boolean", "date", "datetime"
field.remote_name    # str | None: database column name
field.hidden         # bool: hidden from field list
field.formula        # str | None: only set on CalculatedField instances
field.xml_node       # etree._Element: raw <column> element

# Field lookup (raises FieldNotFoundError if missing)
field = ds.get_field("Sales")           # by caption string
field = ds.get_field("[Sales]")         # bracket syntax also accepted
```

### Calculated Fields

```python
calc = ds.calculated_fields[0]
calc.caption         # str
calc.formula         # str: Tableau expression, e.g. "SUM([Revenue]) / [Units]"
calc.datatype        # DataType
```

### Parameters

```python
param = wb.parameters.parameters[0]
param.caption        # str: parameter name
param.datatype       # DataType
param.current_value  # Any: current active value
param.domain_type    # ParameterDomainType: "all", "list", "range"

# Mutate
param.value = "Q4 2024"
```

### Relations (Join Tree, v0.6+)

```python
rel = ds.relations[0]
rel.table            # str | None: table name
rel.custom_sql       # str | None: SQL text when relation-type="text"
rel.join_type        # str | None: "inner", "left", "right", "full"
rel.left             # Relation | None: left join source
rel.right            # Relation | None: right join source
rel.on_clause        # str | None: the ON expression
rel.list_custom_sql()  # list[str]: recursively collect all custom SQL blocks
```

### MetadataRecords (v0.6+)

```python
# Lazily cached from <metadata-records> XML
for rec in ds.metadata_records:
    print(rec.remote_name)     # Database column name
    print(rec.remote_type)     # Database type ("varchar", "int", etc.)
    print(rec.local_name)      # Tableau field caption
    print(rec.aggregation)     # Default aggregation ("Sum", "Attr", etc.)
    print(rec.contains_null)   # bool
```

---

## 6. Worksheets & Dashboards

### Worksheets

```python
ws = wb.worksheets[0]
ws = wb.worksheets["Revenue by Region"]

ws.name              # str: worksheet tab name
ws.mark_type         # MarkType: "automatic", "bar", "line", "area", "pie", etc.
ws.fields            # list[FieldReference]: all fields on shelves
ws.filters           # list[Filter]: worksheet-level filters
ws.rows              # Shelf: row shelf
ws.columns           # Shelf: column shelf

# Filter inspection
for f in ws.filters:
    print(f.filter_type)    # FilterType: "categorical", "quantitative", etc.
    print(f.field)          # str: field caption
```

### Dashboards

```python
db = wb.dashboards[0]
db = wb.dashboards["Executive Summary"]

db.name              # str: dashboard tab name
db.zones             # list[Zone]: layout containers
db.actions           # list[Action]: filter/highlight/URL actions
db.device_layouts    # list[DeviceLayout]: responsive layout definitions (v0.6+)
db.has_phone_layout  # bool: True if phone layout defined (v0.6+)

# Action inspection
for action in db.actions:
    print(action.name)
    print(action.action_type)   # "filter", "highlight", "url", "parameter"
    print(action.source_sheet)
    print(action.target_sheet)
```

---

## 7. Mutations

### Adding a Calculated Field

```python
from pytableau import Workbook, DataType

wb = Workbook.open("sales.twbx")
ds = wb.datasources["Sales Data"]

calc = ds.add_calculated_field(
    caption="Profit Margin",
    formula="[Profit] / [Sales]",
    datatype=DataType.REAL,   # optional; inferred from formula if omitted
)

wb.save_as("sales_enhanced.twbx")
```

### Renaming a Field

```python
ds.rename_field("[Old Caption]", "[New Caption]")
# Also updates all references in the datasource's formulas
```

### Removing a Field

```python
ds.remove_field("[Deprecated Metric]")
```

### Bulk Field Operations (v0.6+)

```python
# Rename multiple fields at once
ds.bulk_rename_fields({
    "[Old Name 1]": "[New Name 1]",
    "[Old Name 2]": "[New Name 2]",
})

# Update field properties
ds.bulk_update_fields({
    "[Date Field]": {"datatype": "date", "role": "dimension"},
    "[Revenue]":    {"role": "measure"},
})
```

### Swapping Connections

```python
# Swap all connections matching the `where` criteria
result = wb.swap_connection(
    where={"server": "dev-db.example.com"},
    to={
        "server": "prod-db.example.com",
        "dbname": "analytics_prod",
        "username": "analytics_svc",
    }
)
print(f"Updated: {result.updated_count}, Skipped: {result.skipped_count}")
print(f"Changes: {result.changes}")
```

### Direct Connection Mutation

```python
ds = wb.datasources["Orders"]
conn = ds.connections[0]
conn.server = "new-host.example.com"
conn.port = 5439   # Redshift
conn.dbname = "prod_warehouse"
```

### Version Migration

```python
wb.migrate_version("2024.1")   # Updates version metadata in XML
```

### Merging Workbooks

```python
# Import all datasources, worksheets, and dashboards from `other` into `wb`
wb.merge(other_wb)
wb.save_as("merged.twbx")
```

---

## 8. Inspection & Analysis

### Catalog (v0.6+)

The `WorkbookCatalog` aggregates all fields, calcs, connections, and unused-item analysis across the full workbook.

```python
catalog = wb.catalog()

catalog.datasources         # list[Datasource]
catalog.calculated_fields   # list[CalculatedField]: all across all datasources
catalog.parameters          # list[Parameter]
catalog.connections         # list[Connection]: all connections

# Audit queries
unused = catalog.unused_fields()        # Fields not on any shelf or in any formula
orphaned = catalog.orphaned_calcs()     # Calculations with broken field references
stale_ws = catalog.unused_worksheets()  # Worksheets not used in any dashboard
sql_blocks = catalog.custom_sql_audit() # list[str]: all custom SQL text
conn_info = catalog.connection_audit()  # list[dict]: connection metadata
```

### Field Lineage

The `FieldLineage` object maps every calculated field to its transitive dependencies and reverse-maps every field to the calculations that reference it.

```python
lineage = wb.lineage()

# Who does "Profit Ratio" depend on?
deps = lineage.dependencies_of("Profit Ratio")   # list[LineageField]

# What calculations reference "[Revenue]"?
calcs = lineage.dependents_of("Revenue")          # list[CalculatedField]

# Full traversal
for entry in lineage.entries:
    print(entry.key)           # "DatasourceName::FieldCaption"
    print(entry.formula)       # str
    print(entry.depends_on)    # list[str]: direct dependencies
```

### Complexity Report (v0.6+)

```python
from pytableau.inspect.complexity import ComplexityConfig

report = wb.complexity_report()
# or with custom thresholds:
config = ComplexityConfig(max_lod_depth=3, max_if_nesting=2)
report = wb.complexity_report(config=config)

report.grade         # str: "A" (best) through "F" (worst)
report.score         # float: 0–100
report.summary       # str: human-readable narrative
report.details       # dict[str, Any]: per-category breakdown
report.to_dict()     # JSON-serializable dict
```

### Workbook Report

```python
# Generate markdown documentation
report = wb.report()
print(report.to_markdown())
report.save("workbook_docs.md")
```

---

## 9. Semantic Diff & Patch

The diff and patch system provides git-friendly workbook comparison and repeatable automated edits. No equivalent exists in other open-source Python libraries.

### Diffing Two Workbooks

```python
from pytableau.inspect.diff import diff_workbooks

before = Workbook.open("v1/report.twbx")
after  = Workbook.open("v2/report.twbx")

diff = diff_workbooks(before, after)
# Equivalently:
diff = before.diff(after)
```

#### Inspecting the Diff

```python
diff.is_empty()             # bool: True if workbooks are semantically identical

# Added/removed at workbook level
diff.datasources_added      # list[str]: new datasource names
diff.datasources_removed    # list[str]: removed datasource names
diff.worksheets_added       # list[str]
diff.worksheets_removed     # list[str]
diff.dashboards_added       # list[str]
diff.dashboards_removed     # list[str]

# Per-datasource changes
for ds_name, ds_diff in diff.datasources_modified.items():
    ds_diff.name                   # str
    ds_diff.fields_added           # list[str]
    ds_diff.fields_removed         # list[str]
    ds_diff.fields_modified        # dict[str, list[FieldDiff]]
    ds_diff.connections_modified   # list[dict]: attribute-level connection changes
    ds_diff.is_empty()             # bool
```

#### Output Formats

```python
# Human-readable text
print(diff.to_text())

# JSON-serializable dict (for APIs, CI, etc.)
import json
print(json.dumps(diff.to_dict(), indent=2))

# HTML table (for reports, emails)
with open("diff_report.html", "w") as f:
    f.write(diff.to_html())
```

### Canonical JSON Serialization

```python
from pytableau.xml.canonical import canonicalize, to_json

# Stable dict with sorted keys and normalized structure
d = canonicalize(wb)

# Deterministic JSON string — identical output every run
json_str = wb.to_json()   # or to_json(wb)
```

### git_clean — VCS-Friendly Normalization

Tableau saves Base64-encoded thumbnails and session-specific attributes on every open/save, producing noisy diffs in version control. `git_clean` removes this noise.

```python
from pytableau.xml.canonical import git_clean

# Strip thumbnails + volatile attrs, overwrite in place
git_clean("workbook.twb", in_place=True)

# Return cleaned XML string without writing
clean_xml = git_clean("workbook.twb", in_place=False)
```

To use as a git filter, add to `.gitattributes`:

```
*.twb filter=tableau_clean
```

And register the filter:

```bash
git config filter.tableau_clean.clean "pytableau git-clean --dry-run %f"
```

### Structural XML Diff

When you need a line-level unified diff (e.g., for code review tools):

```python
from pytableau.xml.differ import xml_diff

lines = xml_diff("before.twb", "after.twb")
for line in lines:
    print(line)
```

This applies `git_clean` to both files before diffing, eliminating thumbnail noise.

### Patch System

A `Patch` is a portable, serializable sequence of `PatchOp` operations that can be applied to any workbook.

```python
from pytableau.inspect.diff import Patch, PatchOp, PatchAction, apply_patch

# Create a patch from a diff
diff = before.diff(after)
patch = Patch.from_diff(diff)

# Or hand-craft a patch
patch = Patch(ops=[
    PatchOp(
        action=PatchAction.MODIFY_CONNECTION,
        target="datasource:Sales Data/connection:0",
        attribute="server",
        old_value="dev-db.example.com",
        new_value="prod-db.example.com",
    ),
])

# Serialize / deserialize
import json
patch_json = patch.to_json()
patch2 = Patch.from_dict(json.loads(patch_json))

# Apply to a workbook
applied = apply_patch(wb, patch, validate=True)
print(f"Applied {applied} operation(s)")
wb.save_as("patched.twbx")
```

#### PatchAction Values

| Action | Description |
|---|---|
| `ADD_FIELD` | Add a new field to a datasource |
| `REMOVE_FIELD` | Remove a field |
| `MODIFY_FIELD` | Change a field attribute |
| `ADD_DATASOURCE` | Add a datasource |
| `REMOVE_DATASOURCE` | Remove a datasource |
| `MODIFY_CONNECTION` | Change a connection attribute |
| `ADD_WORKSHEET` | Add a worksheet |
| `REMOVE_WORKSHEET` | Remove a worksheet |
| `ADD_DASHBOARD` | Add a dashboard |
| `REMOVE_DASHBOARD` | Remove a dashboard |

---

## 10. Formula Parser & Linter

Requires: `pip install "pytableau[analysis]"`

### Parsing Formulas

```python
from pytableau.calculations.parser import parse, parse_safe, ParseError
from pytableau.calculations.ast import (
    FieldRef, FuncCall, BinOp, UnaryOp,
    IfExpr, CaseExpr, LodExpr,
    NumberLiteral, StringLiteral, DateLiteral,
    BoolLiteral, NullLiteral,
    walk, find_nodes,
)

# Parse — raises ParseError on invalid input
try:
    ast = parse("SUM([Sales]) / COUNT([Orders])")
except ParseError as e:
    print(f"Bad formula: {e.formula}")

# parse_safe — returns None instead of raising
ast = parse_safe("{FIXED [Region] : SUM([Sales])}")
if ast is None:
    print("Parse failed")
```

### AST Node Reference

| Node | Matches | Key Attributes |
|---|---|---|
| `FieldRef` | `[Field]` or `[DS].[Field]` | `.name`, `.datasource` |
| `FuncCall` | `SUM(...)` | `.name`, `.args: list` |
| `BinOp` | `a + b`, `a AND b` | `.op`, `.left`, `.right` |
| `UnaryOp` | `-x`, `NOT x` | `.op`, `.operand` |
| `IfExpr` | `IF ... THEN ... END` | `.condition`, `.then_expr`, `.elseif_clauses`, `.else_expr` |
| `CaseExpr` | `CASE x WHEN ...` | `.subject`, `.when_clauses`, `.else_expr` |
| `LodExpr` | `{FIXED [D] : expr}` | `.lod_type`, `.dimensions`, `.body` |
| `NumberLiteral` | `42`, `3.14` | `.value: float` |
| `StringLiteral` | `"hello"` or `'hello'` | `.value: str` |
| `DateLiteral` | `#2024-01-01#` | `.value: str` |
| `BoolLiteral` | `TRUE` / `FALSE` | `.value: bool` |
| `NullLiteral` | `NULL` | — |

### Traversal

```python
# Walk all nodes in depth-first order
visited = []
walk(ast, visited.append)

# Find all nodes of a specific type
field_refs = find_nodes(ast, FieldRef)
for ref in field_refs:
    print(ref.name)

func_calls = find_nodes(ast, FuncCall)
lod_exprs  = find_nodes(ast, LodExpr)
```

### Linting a Formula

```python
from pytableau.calculations.linter import lint, LintContext, LintIssue

# Context provides field knowledge for the UnknownFieldReference rule
ctx = LintContext(
    field_caption="Profit Ratio",
    datasource_name="Sales Data",
    all_field_captions={"Sales", "Profit", "Orders", "Region"},
    known_dependencies={},   # dict[str, set[str]] for cycle detection
)

issues = lint("FOOBAR([Sales])", context=ctx)
for issue in issues:
    print(f"[{issue.severity}] {issue.rule}: {issue.message}")
    print(f"  Formula: {issue.formula}")
    print(f"  Dict:    {issue.to_dict()}")
```

### Linting an Entire Workbook

```python
from pytableau.calculations.linter import lint_workbook

issues = lint_workbook(wb)   # Automatically builds LintContext from datasource schema
for issue in issues:
    print(f"{issue.rule}: {issue.message}")
```

### Built-in Lint Rules

| Rule | Severity | Description |
|---|---|---|
| `UnknownFunctionRule` | `warning` | Function name not in the Tableau function registry |
| `ExcessiveLodNestingRule` | `warning` | LOD expression nested more than 3 levels deep |
| `NestedIfAntiPattern` | `info` | `IF` inside the `THEN` or `ELSE` branch of another `IF` |
| `DeprecatedFunctionRule` | `warning` | Uses a deprecated function (`SCRIPT_REAL`, `RAWSQL_*`, etc.) |
| `UnknownFieldReferenceRule` | `warning` | Field reference not found in the datasource schema (requires `LintContext`) |
| `CyclicDependencyRule` | `error` | Circular calculation dependency detected |

### Function Registry

```python
from pytableau.calculations.functions import FUNCTION_REGISTRY, DEPRECATED_FUNCTIONS

# Check if a function name is known
assert "SUM" in FUNCTION_REGISTRY
assert "AVG" in FUNCTION_REGISTRY

# Function metadata
info = FUNCTION_REGISTRY["SUM"]
info.name            # str: "SUM"
info.category        # str: "aggregate"
info.min_args        # int: 1
info.max_args        # int | None: 1
info.return_type     # str | None: "number"
info.deprecated      # bool: False
info.deprecation_note  # str: ""

# Deprecated function set (100+ functions total, 8 deprecated)
assert "SCRIPT_REAL" in DEPRECATED_FUNCTIONS
assert "RAWSQL_STR"  in DEPRECATED_FUNCTIONS
```

**Registry coverage:** aggregate (14), string (20), number (26), date (16), type conversion (5), logical (5), table calculation (30), user (3), spatial (8), deprecated (8+).

---

## 11. Hyper Extract Management

Requires: `pip install "pytableau[hyper]"` (installs `tableauhyperapi` and `pantab`)

### HyperFile — Context Manager

`HyperFile` is a context-managed wrapper around `HyperBridge` for safe, transactional access to `.hyper` files.

```python
from pytableau.data.bridge import HyperFile
import pandas as pd

path = "extract.hyper"

# Write a DataFrame
with HyperFile(path) as hf:
    df = pd.read_csv("data.csv")
    rows_written = hf.bulk_insert(df, table="Extract", batch_size=5_000)
    print(f"Wrote {rows_written} rows")

# Read back
with HyperFile(path) as hf:
    tables = hf.list_tables()               # list[str]
    schema = hf.schema("Extract")           # list[dict] with "name" and "type"
    count  = hf.row_count("Extract")        # int
```

### Bulk Insert (Batched)

```python
with HyperFile("extract.hyper") as hf:
    # First batch uses mode="replace" (creates table)
    # Subsequent batches use mode="append"
    written = hf.bulk_insert(df, table="Extract", batch_size=10_000)
```

### Incremental Refresh Patterns

```python
# Rolling window: delete rows older than N days, append new data
with HyperFile("extract.hyper") as hf:
    written = hf.rolling_window_refresh(
        df,
        date_col="Order Date",
        window_days=90,
        table="Extract",
    )

# Upsert: delete rows matching key columns, insert updated rows
with HyperFile("extract.hyper") as hf:
    deleted, inserted = hf.upsert(
        df,
        key_cols=["Order ID", "Product ID"],
        table="Extract",
    )
    print(f"Deleted {deleted}, inserted {inserted}")
```

### ExtractManager

```python
from pytableau.data.extract import ExtractManager

wb = Workbook.open("report.twbx")
ds = wb.datasources["Sales Data"]

# Contract test: verify .hyper is consistent with XML metadata
issues = ExtractManager.contract_test(ds)
if issues:
    print("Extract inconsistencies found:")
    for issue in issues:
        print(f"  {issue}")

# Incremental refresh via workflow
written = ExtractManager.incremental_refresh(
    ds,
    df,
    mode="rolling",          # "rolling" or "upsert"
    date_col="Order Date",
    window_days=90,
)
```

---

## 12. Template Engine

### Built-in Templates

```python
from pytableau import Workbook

# Available templates: bar_chart, line_chart, scatter_plot,
#                      heatmap, treemap, map, kpi
wb = Workbook.from_template("bar_chart")
```

### Using the Template Engine

Templates contain named placeholders (e.g., `__MEASURE__`, `__DIMENSION__`) in field captions and connection attributes.

```python
engine = wb.template

# Discover what placeholders need to be filled
placeholders = engine.discover_placeholders()  # set[str]

# Map placeholders to real values
engine.map_fields({
    "__MEASURE__":   "Revenue",
    "__DIMENSION__": "Product Category",
    "__COLOR__":     "Region",
})

# Validate all placeholders are resolved before saving
issues = engine.validate_all_mapped()

wb.save_as("generated_report.twbx")
```

### Datasource Replacement

Swap an entire datasource XML node (e.g., to switch from dev to prod connection config):

```python
from lxml import etree

new_ds_xml = etree.fromstring(b"""
<datasource name="prod_sales" caption="Sales Data">
  <connection class="sqlserver" server="prod.example.com"
              dbname="analytics" username="svc_tableau"/>
</datasource>
""")

engine.replace_datasource("dev_sales", new_ds_xml)
wb.save_as("report_prod.twbx")
```

### Custom Templates (save_as_template)

Convert any workbook to a reusable template by replacing field captions with `__FIELDN__` placeholder tokens:

```python
wb = Workbook.open("existing_report.twbx")

# Returns the mapping of placeholder → original caption
mapping = wb.save_as_template(
    "my_template.twb",
    field_placeholder_prefix="FIELD",   # produces __FIELD0__, __FIELD1__, ...
)

print(mapping)
# {"__FIELD0__": "Revenue", "__FIELD1__": "Product", ...}

# Reload as a template
template_wb = Workbook.from_template("my_template.twb")
```

---

## 13. Server Integration

Requires: `pip install "pytableau[server]"`

### ServerClient

```python
from pytableau.server.client import ServerClient

# Context manager (recommended — ensures sign-out on exit)
with ServerClient("https://tableau.example.com", site_id="mysite") as client:

    # Authenticate — personal access token (preferred)
    client.sign_in_with_personal_access_token(
        token_name="MyToken",
        token_secret="s3cr3t",
    )

    # Or username/password
    client.sign_in_with_credentials("admin@example.com", "password")

    # Publish (auto-selects chunked upload for large files)
    client.publish_workbook_chunked(
        "report.twbx",
        project_id="proj-123",
        name="Q4 Sales Report",
        overwrite=True,
        chunk_size_mb=64,       # files > 64 MB use chunked upload
    )

    # List workbooks
    workbooks = client.list_workbooks()
    workbooks = client.list_workbooks(project_id="proj-123")  # filtered

    for wb_item in workbooks:
        print(wb_item["id"], wb_item["name"], wb_item["project_id"])

    # Trigger async extract refresh
    job = client.refresh_extract(workbook_id="wb-abc123")
    print(f"Job {job['job_id']} status: {job['status']}")

    # Detect connection drift
    local_wb = Workbook.open("local_copy.twbx")
    drift = client.detect_drift(local_wb, workbook_id="wb-abc123")
    for item in drift:
        print(f"Drift in {item['datasource']}.{item['attribute']}:")
        print(f"  local={item['local']!r}, server={item['server']!r}")

    # Download
    path = client.download_workbook("wb-abc123", destination="downloaded.twbx")
```

### Metadata API (GraphQL, v0.9+)

```python
from pytableau.server.metadata import MetadataClient

# Initialize with a Tableau personal access token
meta = MetadataClient(
    "https://tableau.example.com",
    token="my_pat_secret",
)

# Execute raw GraphQL
result = meta.query("""
{
  workbooksConnection {
    nodes {
      luid
      name
      projectName
      embeddedDatasourcesConnection {
        nodes { name }
      }
    }
  }
}
""")

# High-level helpers
result = meta.fields_for_datasource("Sales Data")
result = meta.search_fields("Revenue")
lineage = meta.workbook_lineage("workbook-luid-here")
```

### Drift Detection Workflow

```python
from pytableau.server.workflows import detect_drift_workflow
from pytableau import Workbook

local_wb = Workbook.open("report.twbx")
drift = detect_drift_workflow(
    "https://tableau.example.com",
    local_wb,
    workbook_id="wb-abc123",
    token_name="MyToken",
    token_secret="s3cr3t",
    site_id="mysite",
)
```

---

## 14. Packaging & ZIP

### PackageManager

`PackageManager` provides transparent access to the contents of `.twbx` packages without requiring manual ZIP extraction.

```python
from pytableau.package.manager import PackageManager, is_twb, is_twbx

# Type detection
is_twb("workbook.twb")     # True
is_twbx("workbook.twbx")   # True

# Open a package
mgr = PackageManager("report.twbx")
twb = mgr.twb_path          # Path: extracted .twb file
data = mgr.data_dir         # Path: Data/ subdirectory

# Asset listing
all_assets  = mgr.list_assets()            # list[str]: relative paths
hyper_files = mgr.glob("Data/**/*.hyper")  # list[Path]: pattern match
found       = mgr.find("extract.hyper")    # Path | None: first match by name

# Safe path resolution (prevents path traversal attacks)
safe = mgr.resolve("Data/extract.hyper")  # raises InvalidPathError on traversal

mgr.close()   # Cleans up temp directory
```

---

## 15. Validation & Auto-Fix

### Validation

`wb.validate()` runs the workbook through a set of `ValidationRule` objects and returns a list of `ValidationIssue` items with levels `"error"`, `"warning"`, and `"info"`.

```python
from pytableau.xml.rules import ValidationProfile

# Default profile (all rules)
issues = wb.validate()

# Strict profile
issues = wb.validate(profile=ValidationProfile.strict())

# Inspect issues
for issue in issues:
    print(f"[{issue.level}] {issue.message}")
    print(f"  Path: {issue.path}")
    print(f"  Rule: {issue.rule_name}")

errors   = [i for i in issues if i.level == "error"]
warnings = [i for i in issues if i.level == "warning"]
```

### Auto-Fix

```python
from pytableau.xml.fixers import AutoFixer

# Preview fixes without applying
plan = wb.auto_fix(dry_run=True)
for action in plan:
    print(f"Would {action.type}: {action.description}")

# Apply fixes in place
applied = wb.auto_fix(dry_run=False)
for action in applied:
    print(f"Fixed: {action.description}")

wb.save_as("fixed.twbx")
```

**Built-in fixers:**

| Fixer | Description |
|---|---|
| Bracket normalizer | Adds missing `[]` brackets to field references in formulas |
| Credential scrubber | Removes passwords from connection attributes |
| Whitespace cleaner | Normalizes whitespace in formula strings |

---

## 16. Environment Promotion

`PromotionConfig` maps a workbook's connections from one named environment to another.

```python
from pytableau.package.promotion import PromotionConfig, EnvironmentSpec

# Define environments
config = PromotionConfig.from_dict({
    "environments": {
        "dev":  {"server": "dev-db.example.com",  "dbname": "analytics_dev"},
        "staging": {"server": "stg-db.example.com", "dbname": "analytics_stg"},
        "prod": {"server": "prod-db.example.com", "dbname": "analytics_prod"},
    }
})

# Or build programmatically
config = PromotionConfig(environments={
    "dev":  EnvironmentSpec(name="dev",  server="dev.example.com",  dbname="analytics_dev"),
    "prod": EnvironmentSpec(name="prod", server="prod.example.com", dbname="analytics_prod"),
})

# Apply promotion
wb = Workbook.open("report.twbx")
changes = wb.promote(from_env="dev", to_env="prod", config=config)
wb.save_as("report_prod.twbx", scrub_credentials=True)

# Or via CLI:
# pytableau promote report.twbx --from dev --to prod --output report_prod.twbx
```

---

## 17. CLI Reference

Install: `pip install "pytableau[cli]"`

### Inspection Commands

```bash
# Summary of all datasources, fields, worksheets, dashboards
pytableau inspect report.twbx

# Validate XML and semantic rules
pytableau validate report.twbx

# Semantic diff between two workbooks
pytableau diff before.twbx after.twbx
pytableau diff before.twbx after.twbx --semantic      # object-model diff

# Canonical JSON
pytableau to-json report.twbx
pytableau to-json report.twbx --output canonical.json

# Full field/connection catalog
pytableau catalog report.twbx
pytableau catalog report.twbx --connections           # include connection details

# Field lineage graph
pytableau lineage report.twbx

# Complexity grade
pytableau complexity report.twbx

# Markdown documentation
pytableau report report.twbx --output docs.md
```

### Mutation Commands

```bash
# Swap connection attributes
pytableau swap-connection report.twb \
    --server prod-db.example.com \
    --dbname analytics_prod

# Rename a field
pytableau rename-field datasource.tds \
    --from "[Old Field Name]" \
    --to   "[New Field Name]"

# Migrate workbook version
pytableau version-migrate report.twb --to 2024.1

# Auto-fix issues (dry run)
pytableau auto-fix report.twb --dry-run
pytableau auto-fix report.twb --output fixed.twb

# Promote to production environment
pytableau promote report.twb \
    --from dev --to prod \
    --config environments.yaml

# Merge two workbooks
pytableau merge base.twb other.twb --output merged.twb
```

### Template Commands

```bash
# List built-in templates
pytableau template-list

# Apply a template
pytableau template-apply bar_chart output.twb

# Patch a workbook with a JSON patch file
pytableau patch report.twb changes.json --output patched.twb
```

### Formula Commands (requires `[analysis]`)

```bash
# Lint all calculated fields in a workbook
pytableau formula-lint report.twbx

# Parse a formula and print the AST as JSON
pytableau formula-parse "SUM([Sales]) / COUNT([Orders])"
```

### VCS Commands

```bash
# Strip thumbnails + volatile attrs (for git cleanliness)
pytableau git-clean workbook.twb          # in-place
pytableau git-clean workbook.twb --dry-run  # preview only
```

### Server Commands (requires `[server]` and `[cli]`)

```bash
# List workbooks on Tableau Server
pytableau server-list \
    --url https://tableau.example.com \
    --token-name MyToken \
    --token-secret s3cr3t \
    --site mysite

# Publish a workbook
pytableau publish report.twbx \
    --url https://tableau.example.com \
    --project "Finance Reports" \
    --token-name MyToken \
    --token-secret s3cr3t

# Download a workbook
pytableau download wb-abc123 \
    --url https://tableau.example.com \
    --output downloaded.twbx \
    --token-name MyToken \
    --token-secret s3cr3t
```

---

## 18. Exceptions & Error Handling

All exceptions inherit from `PyTableauError`.

```python
from pytableau import (
    PyTableauError,         # Base class for all pytableau errors

    # File & package errors
    FileError,              # Generic file I/O error
    InvalidWorkbookError,   # Not a valid Tableau workbook
    CorruptWorkbookError,   # Workbook XML is malformed
    PackageError,           # .twbx ZIP error
    AmbiguousWorkbookError, # Archive contains multiple .twb files
    InvalidPathError,       # Path traversal guard triggered

    # XML & schema errors
    XMLError,               # Generic XML parse error
    SchemaValidationError,  # Violates schema constraints
    IncompatibleVersionError, # Version incompatibility

    # Semantic field errors
    FieldError,             # Generic field error
    FieldNotFoundError,     # Caption not found in datasource
    DuplicateFieldError,    # Caption already exists
    FormulaError,           # Invalid calculation formula

    # Datasource errors
    DatasourceError,        # Generic datasource error
    DatasourceNotFoundError, # Datasource name not found
    ConnectionError,        # Connection configuration error

    # Data layer errors
    HyperError,             # tableauhyperapi error
    ExtractError,           # Extract lifecycle error

    # Server errors
    ServerError,            # Generic server error
    AuthenticationError,    # Sign-in failed
    PublishError,           # Workbook publish failed

    # Template errors
    TemplateError,          # Generic template error
    TemplateNotFoundError,  # Template name or path not found
    UnmappedPlaceholderError, # Template saved with unresolved placeholders

    # Streaming mode
    LazyNotMaterializedError, # Accessed a lazy field in streaming mode

    # Validation
    ValidationIssue,        # Single validation finding (level, message, path)
)
```

### Recommended Error Handling Pattern

```python
from pytableau import Workbook
from pytableau import (
    InvalidWorkbookError,
    FieldNotFoundError,
    DatasourceNotFoundError,
)

try:
    wb = Workbook.open("report.twbx")
    ds = wb.datasources["Orders"]
    field = ds.get_field("Revenue")
    wb.save_as("output.twbx")
except InvalidWorkbookError as e:
    print(f"Cannot open: {e}")
except DatasourceNotFoundError as e:
    print(f"Datasource not found: {e}")
except FieldNotFoundError as e:
    print(f"Field not found: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
    raise
```

---

## 19. Enumerations

All enumerations are string enums whose values match the raw Tableau XML attribute strings.

```python
from pytableau import (
    MarkType,
    DataType,
    Role,
    AggregationType,
    FilterType,
    SortOrder,
    ConnectionType,
    ValidationLevel,
    ParameterDomainType,
)

# MarkType — mark card visualization type
MarkType.AUTOMATIC   # "automatic"
MarkType.BAR         # "bar"
MarkType.LINE        # "line"
MarkType.AREA        # "area"
MarkType.CIRCLE      # "circle"
MarkType.SQUARE      # "square"
MarkType.PIE         # "pie"
MarkType.TEXT        # "text"
MarkType.MAP         # "map"

# DataType — field data type
DataType.STRING      # "string"
DataType.INTEGER     # "integer"
DataType.REAL        # "real"
DataType.BOOLEAN     # "boolean"
DataType.DATE        # "date"
DataType.DATETIME    # "datetime"

# Role — dimension vs. measure
Role.DIMENSION       # "dimension"
Role.MEASURE         # "measure"

# AggregationType
AggregationType.SUM   # "Sum"
AggregationType.AVG   # "Avg"
AggregationType.COUNT # "Count"
AggregationType.ATTR  # "Attr"
# ... and more

# FilterType
FilterType.CATEGORICAL     # "categorical"
FilterType.QUANTITATIVE    # "quantitative"
FilterType.RELATIVE_DATE   # "relative-date"
FilterType.RANGE           # "range"

# ParameterDomainType
ParameterDomainType.ALL    # "all"
ParameterDomainType.LIST   # "list"
ParameterDomainType.RANGE  # "range"
```

---

## 20. Testing Patterns

### Project Test Structure

```
tests/
├── conftest.py                        # Session-scoped fixtures for all .twb files
├── helpers.py                         # canonicalize_twb() round-trip helper
├── fixtures/
│   ├── minimal_v2022_4.twb            # Minimal workbook (1 datasource, 1 worksheet)
│   ├── single_datasource_v2023_1.twb  # Single datasource
│   ├── modified_v2024_1.twb           # Diff-test baseline (has Territory/Profit Ratio)
│   └── ...                            # Additional golden fixtures
├── test_imports.py                    # Phase 0 import smoke tests
├── test_cli.py                        # CLI command integration tests
├── test_roundtrip.py                  # Round-trip fidelity tests
├── test_v070_diff.py                  # Semantic diff, canonical, git_clean
├── test_v080_templates.py             # Template engine, save_as_template
├── test_v080_extracts.py              # HyperFile, contract_test (requires_hyper)
├── test_v090_formula_parser.py        # Parse, lint, function registry
└── test_v090_server.py                # ServerClient, MetadataClient (mocked)
```

### Running Tests

```bash
# All tests
pytest tests/

# Specific milestone
pytest tests/test_v070_diff.py -v
pytest tests/test_v090_formula_parser.py -v

# Skip Hyper tests (no tableauhyperapi installed)
pytest tests/ -m "not requires_hyper"

# With coverage
pytest tests/ --cov=pytableau --cov-report=html
```

### Common Patterns

#### Round-Trip Test

```python
def test_roundtrip(tmp_path):
    src = Path("tests/fixtures/minimal_v2022_4.twb")
    wb = Workbook.open(src)
    out = tmp_path / "output.twb"
    wb.save_as(out)

    # Re-open and verify semantic equivalence
    wb2 = Workbook.open(out)
    assert wb2.version == wb.version
    assert len(wb2.datasources) == len(wb.datasources)
```

#### Mutation + Verify

```python
def test_add_field(tmp_path):
    wb = Workbook.open("tests/fixtures/minimal_v2022_4.twb")
    ds = wb.datasources[0]

    calc = ds.add_calculated_field("Test Calc", "SUM([Sales])")
    out = tmp_path / "mutated.twb"
    wb.save_as(out)

    wb2 = Workbook.open(out)
    captions = [f.caption for f in wb2.datasources[0].calculated_fields]
    assert "Test Calc" in captions
```

#### CLI Test

```python
from pytableau.cli.main import app

def test_cli_inspect():
    result = app.call("inspect", workbook="tests/fixtures/minimal_v2022_4.twb")
    assert result.ok
    assert "datasource" in result.result.lower()
```

#### Mocking Server Tests

```python
from unittest.mock import MagicMock, patch
import pytableau.server.client as _client_module

def test_list_workbooks():
    mock_tsc = MagicMock()
    mock_item = MagicMock()
    mock_item.id = "wb-001"
    mock_item.name = "My Report"
    mock_item.project_id = "proj-001"
    mock_tsc.Server.return_value.workbooks.get.return_value = ([mock_item], MagicMock())

    with patch.object(_client_module, "_tsc", mock_tsc):
        from pytableau.server.client import ServerClient
        client = ServerClient("https://example.com")
        client._signed_in = True
        result = client.list_workbooks()

    assert result[0]["name"] == "My Report"
```

---

## 21. Architecture Reference

### Module Map

```
src/pytableau/
├── __init__.py            # Public re-exports: Workbook, enums, exceptions, WorkbookDiff, Patch, LintIssue
├── _version.py            # __version__ = "0.9.0"
├── constants.py           # All enumerations
├── exceptions.py          # Full exception hierarchy
├── _compat.py             # import_optional() — graceful optional dep handling
│
├── core/
│   ├── workbook.py        # Workbook: top-level entry point
│   ├── datasource.py      # Datasource, Connection, Relation, MetadataRecord
│   ├── fields.py          # Field, CalculatedField, Parameter, Group, Bin
│   ├── worksheet.py       # Worksheet, Shelf, MarkCard, Encoding
│   ├── dashboard.py       # Dashboard, Zone, Action, DeviceLayout
│   ├── filters.py         # CategoricalFilter, RangeFilter, RelativeDateFilter
│   └── formatting.py      # Style, ColorPalette, Font, Tooltip
│
├── xml/
│   ├── engine.py          # XMLSchemaEngine: version rules, unknown tag tracking
│   ├── proxy.py           # XMLNodeProxy: safe mutation base class
│   ├── writer.py          # XML generation helpers
│   ├── differ.py          # Structural XML diff (unified diff format)
│   ├── canonical.py       # canonicalize(), to_json(), git_clean()
│   ├── rules.py           # ValidationProfile + 10 built-in Rule classes
│   ├── fixers.py          # AutoFixer + 3 built-in fixers
│   ├── schemas/           # Version-specific schema knowledge (v2022–v2025)
│   └── discovery/         # Schema reverse-engineering utilities
│
├── data/
│   ├── bridge.py          # HyperBridge (pantab + tableauhyperapi), HyperFile
│   ├── types.py           # Tableau ↔ Python type mapping
│   └── extract.py         # ExtractManager: contract_test, incremental_refresh
│
├── package/
│   ├── manager.py         # PackageManager: .twbx ↔ temp directory
│   ├── promotion.py       # PromotionConfig, EnvironmentSpec
│   └── assets.py          # Asset listing, path safety
│
├── templates/
│   ├── engine.py          # TemplateEngine: placeholder discovery, mapping, replacement
│   ├── mapping.py         # FieldMapping helpers
│   └── library/           # 7 built-in .twb templates
│
├── server/
│   ├── client.py          # ServerClient: tableauserverclient wrapper
│   ├── metadata.py        # MetadataClient: Tableau Metadata API (GraphQL)
│   └── workflows.py       # High-level workflows (publish, promote, detect_drift)
│
├── inspect/
│   ├── catalog.py         # WorkbookCatalog: fields, calcs, connection inventory
│   ├── complexity.py      # ComplexityReport: grade A–F
│   ├── lineage.py         # FieldLineage: dependency graph
│   ├── report.py          # WorkbookReport: markdown generation
│   └── diff.py            # WorkbookDiff, DatasourceDiff, Patch, PatchOp, apply_patch
│
├── calculations/
│   ├── __init__.py        # Re-exports: FUNCTION_REGISTRY, lint, lint_workbook, LintIssue
│   ├── ast.py             # AST node dataclasses + walk() + find_nodes()
│   ├── parser.py          # lark Earley grammar, parse(), parse_safe(), ParseError
│   ├── linter.py          # 6 lint rules, lint(), lint_workbook(), LintContext
│   └── functions.py       # FunctionInfo, FUNCTION_REGISTRY, DEPRECATED_FUNCTIONS
│
└── cli/
    └── main.py            # 23 CLI commands via tooli
```

### Public API Surface (`pytableau.__init__`)

```python
from pytableau import (
    # Core
    Workbook,

    # Enumerations
    AggregationType, ConnectionType, DataType, FilterType,
    MarkType, ParameterDomainType, Role, SortOrder, ValidationLevel,

    # Exceptions
    AmbiguousWorkbookError, AuthenticationError, ConnectionError,
    CorruptWorkbookError, DatasourceError, DatasourceNotFoundError,
    DuplicateFieldError, ExtractError, FieldError, FieldNotFoundError,
    FileError, FormulaError, HyperError, IncompatibleVersionError,
    InvalidPathError, InvalidWorkbookError, LazyNotMaterializedError,
    PackageError, PublishError, PyTableauError, SchemaValidationError,
    ServerError, TemplateError, TemplateNotFoundError,
    UnmappedPlaceholderError, ValidationIssue, XMLError,

    # Analysis types
    WorkbookDiff,   # from inspect.diff
    Patch,          # from inspect.diff
    LintIssue,      # from calculations.linter

    # Version
    __version__,
)
```

### Optional Dependency Pattern

Optional features raise `ImportError` with a helpful install hint when the required extra is not installed:

```python
from pytableau._compat import import_optional

pandas = import_optional("pandas", "hyper")
# If pandas is not installed: raises ImportError("pip install 'pytableau[hyper]'")
```

---

## Common Recipes

### Recipe 1 — CI/CD Connection Swap

```python
import sys
from pytableau import Workbook

SOURCE = sys.argv[1]       # e.g. "report.twbx"
TARGET = sys.argv[2]       # e.g. "report_prod.twbx"
ENV    = sys.argv[3]       # "staging" or "prod"

CONFIGS = {
    "staging": {"server": "stg.example.com", "dbname": "analytics_stg"},
    "prod":    {"server": "prod.example.com", "dbname": "analytics_prod"},
}

wb = Workbook.open(SOURCE)
result = wb.swap_connection(
    where={"server": "dev.example.com"},
    to=CONFIGS[ENV],
)
print(f"Swapped {result.updated_count} connection(s)")

issues = wb.validate()
if any(i.level == "error" for i in issues):
    for i in issues:
        if i.level == "error":
            print(f"ERROR: {i.message}")
    sys.exit(1)

wb.save_as(TARGET, scrub_credentials=True)
print(f"Saved: {TARGET}")
```

### Recipe 2 — Governance Audit

```python
from pytableau import Workbook
from pytableau.calculations.linter import lint_workbook

wb = Workbook.open("dashboard.twbx")

# Catalog
catalog = wb.catalog()
print(f"Unused fields:    {len(catalog.unused_fields())}")
print(f"Orphaned calcs:   {len(catalog.orphaned_calcs())}")
print(f"Custom SQL count: {len(catalog.custom_sql_audit())}")

# Complexity
report = wb.complexity_report()
print(f"Complexity grade: {report.grade} ({report.score:.0f}/100)")

# Formula lint
lint_issues = lint_workbook(wb)
errors = [i for i in lint_issues if i.severity == "error"]
print(f"Lint issues: {len(lint_issues)} ({len(errors)} errors)")

# Validation
val_issues = wb.validate()
print(f"Validation issues: {len(val_issues)}")
```

### Recipe 3 — DataFrame → Published Workbook

```python
import pandas as pd
from pytableau import Workbook
from pytableau.data.bridge import HyperFile
from pytableau.server.client import ServerClient

# Build extract
df = pd.read_sql("SELECT * FROM sales WHERE quarter = 'Q4'", con)
with HyperFile("q4.hyper") as hf:
    hf.bulk_insert(df, table="Extract")

# Attach to workbook
wb = Workbook.open("template.twbx")
ds = wb.datasources["Sales Data"]
ds.attach_extract("q4.hyper")
wb.save_as("q4_dashboard.twbx")

# Publish
with ServerClient("https://tableau.example.com") as client:
    client.sign_in_with_personal_access_token("MyToken", "s3cr3t")
    client.publish_workbook_chunked(
        "q4_dashboard.twbx",
        project_id="fin-reports",
        name="Q4 Sales Dashboard",
        overwrite=True,
    )
```

### Recipe 4 — Version Control Integration

```python
# pre-commit hook: normalize a workbook before git add
import sys
from pytableau.xml.canonical import git_clean

for path in sys.argv[1:]:
    if path.endswith((".twb", ".twbx")):
        git_clean(path, in_place=True)
        print(f"Cleaned: {path}")
```

---

*For bug reports and feature requests, open an issue at https://github.com/brianlwb/pytableau/issues.*
