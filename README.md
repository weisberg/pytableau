# pytableau

> **What pandas did for tabular data, pytableau does for Tableau workbooks.**

`pytableau` is the unified Python SDK for Tableau workbook engineering. It brings every layer of Tableau workbook manipulation — data, connections, semantic model, presentation, packaging, fleet operations, and governance — under one coherent, Pythonic API.

[![PyPI version](https://img.shields.io/pypi/v/pytableau)](https://pypi.org/project/pytableau/)
[![Python 3.11+](https://img.shields.io/pypi/pyversions/pytableau)](https://pypi.org/project/pytableau/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Why pytableau?

The Tableau Python ecosystem is fragmented. Tableau/Salesforce maintains several narrow libraries, each covering a single concern:

| Library | Layer | Limitation |
|---------|-------|-----------|
| `tableaudocumentapi` | Connection XML | No calc fields, no viz edits, abandoned 2021 |
| `tableauhyperapi` | `.hyper` data files | No XML awareness |
| `pantab` | DataFrame ↔ `.hyper` bridge | No XML awareness |
| `tableauserverclient` | Server REST API | No local file manipulation |

`pytableau` wraps and integrates all of them behind a single API — and adds a build layer, governance engine, fleet scanner, and pytest plugin that none of them provide.

---

## Install

```bash
# Core (XML + ZIP only)
pip install pytableau

# With Hyper / extract support
pip install "pytableau[hyper]"

# With pandas convenience methods
pip install "pytableau[pandas]"

# With Tableau Server/Cloud integration
pip install "pytableau[server]"

# With calculation analysis (lark parser + networkx)
pip install "pytableau[analysis]"

# With governance linting (YAML rulesets)
pip install "pytableau[governance]"

# With pytest plugin
pip install "pytableau[testing]"

# Everything
pip install "pytableau[all]"
```

---

## Quick Start

### Open and inspect a workbook

```python
from pytableau import Workbook

wb = Workbook.open("sales_dashboard.twbx")

print(wb.version)                    # "2024.1"
print(wb.datasources.names)          # ["Sales Data", "Parameters"]
print(wb.worksheets.names)           # ["Revenue by Region", "Trend"]
print(wb.dashboards.names)           # ["Executive Summary"]

catalog = wb.catalog()
for field in catalog.calculated_fields:
    print(f"{field.caption}: {field.formula}")
```

### Build a workbook from scratch

```python
from pytableau.build import DatasourceBuilder, WorksheetBuilder, DashboardBuilder
from pytableau.constants import DataType, Role

ds = (
    DatasourceBuilder("Sales Data")
    .connection("hyper", dbname="Data/sales.hyper")
    .column("Region", DataType.STRING, Role.DIMENSION)
    .column("Revenue", DataType.REAL, Role.MEASURE)
    .calculated_field("Margin %", "SUM([Revenue]) / SUM([Cost]) - 1")
    .build()
)

ws = (
    WorksheetBuilder("Revenue by Region")
    .datasource("federated.Sales Data")
    .mark_type("bar")
    .rows("Region")
    .columns("SUM(Revenue)")
    .color("Region")
    .sort("Revenue", descending=True)
    .build()
)

dash = (
    DashboardBuilder("Executive Summary", width=1200, height=800)
    .sheet("Revenue by Region", x=0, y=0, w=1200, h=800)
    .build()
)
```

### Build from a YAML spec

```python
from pytableau.build import from_spec

wb = from_spec("workbook_spec.yml")
wb.save_as("output.twbx")
```

```yaml
# workbook_spec.yml
datasources:
  - caption: Sales Data
    connection: {class: hyper, dbname: Data/sales.hyper}
    columns:
      - {caption: Region, datatype: string, role: dimension}
      - {caption: Revenue, datatype: real, role: measure}

worksheets:
  - name: Revenue by Region
    datasource: Sales Data
    mark_type: bar
    rows: [Region]
    columns: [SUM(Revenue)]

dashboards:
  - name: Executive Summary
    width: 1200
    height: 800
    zones:
      - {worksheet: Revenue by Region, x: 0, y: 0, w: 1200, h: 800}
```

### One-liner charts and dashboards

```python
from pytableau.build import quick_chart, quick_dashboard
import pandas as pd

df = pd.read_csv("q4_revenue.csv")

wb = quick_chart(df, title="Q4 Revenue", mark_type="bar",
                 rows=["Region"], columns=["SUM(Revenue)"])

wb = quick_dashboard(
    [("Revenue by Region", df), ("Trend", trend_df)],
    title="Sales Dashboard",
)
wb.save_as("q4_dashboard.twbx")
```

### Swap database connections (CI/CD promotion)

```python
from pytableau import Workbook

wb = Workbook.open("report.twbx")
for ds in wb.datasources:
    for conn in ds.connections:
        conn.server = "prod-db.corp.com"
        conn.dbname = "analytics_prod"
wb.save_as("report_prod.twbx")
```

### Safe mutations with transactions

```python
from pytableau import Workbook

wb = Workbook.open("report.twbx")

with wb.transaction() as txn:
    txn.rename_field("Old Name", "New Name", datasource="Sales Data")
    txn.swap_connection("dev-db.corp.com", "prod-db.corp.com")
    # raises → XML is rolled back automatically
```

### Inject or refresh a DataFrame extract

```python
import pandas as pd
from pytableau import Workbook

wb = Workbook.open("template.twbx")
df = pd.read_csv("fresh_data.csv")
ds = wb.datasources["Sales Data"]
ds.hyper.create(ds, df)          # create extract
# or ds.hyper.refresh(ds, df)    # replace existing extract
# or ds.upsert_extract(df, key_columns=["id"])  # incremental upsert
wb.save_as("refreshed_report.twbx")
```

### Governance linting

```python
from pytableau import Workbook
from pytableau.governance import GovernanceRuleset, lint_with_ruleset

wb = Workbook.open("report.twbx")
ruleset = GovernanceRuleset.from_yaml("rules.yml")
issues = lint_with_ruleset(wb, ruleset)

for issue in issues:
    print(f"[{issue.severity.upper()}] {issue.rule}: {issue.message}")
```

```yaml
# rules.yml
rules:
  naming_conventions:
    enabled: true
    field_pattern: "^[A-Z][a-zA-Z0-9 ]+$"
  no_live_connections:
    enabled: true
    severity: error
  no_pii_fields:
    enabled: true
    patterns: [email, ssn, credit_card]
    severity: error
  max_complexity:
    enabled: true
    max_score: 150
```

### Cross-workbook field search (WorkbookIndex)

```python
from pytableau.governance import WorkbookIndex

with WorkbookIndex("catalog.db") as idx:
    idx.add_directory("/workbooks/", pattern="**/*.twb")
    results = idx.search_field("revenue")
    for r in results:
        print(f"{r['workbook']} / {r['datasource']}: {r['caption']}")
```

### Fleet scanning and migration

```python
from pytableau.fleet import FleetScanner, MigrationPlan, MigrationEngine, ComplianceRunner

# Scan a directory of workbooks
scanner = FleetScanner("/workbooks/")
report = scanner.report()
report.to_html("fleet_health.html")

# Bulk connection swap (dry run first)
plan = (
    MigrationPlan()
    .source_directory("/workbooks/")
    .output_directory("/migrated/")
    .swap_connections("dev-db.corp.com", "prod-db.corp.com")
)
result = MigrationEngine(plan).execute(dry_run=True)
print(result.summary())

# Compliance check against a governance ruleset
runner = ComplianceRunner("/workbooks/", "rules.yml")
runner.run()
runner.to_junit_xml("compliance.xml")   # for CI/CD
```

### pytest plugin

```python
# conftest.py — plugin auto-registers via pytest11 entry point
# just install pytableau[testing]

# test_workbook.py
from pytableau.testing.assertions import (
    assert_field_exists,
    assert_no_live_connections,
    assert_complexity_grade,
    assert_no_pii_fields,
)
from pytableau import Workbook

def test_workbook_quality():
    wb = Workbook.open("report.twbx")
    assert_field_exists(wb, "Revenue")
    assert_no_live_connections(wb)
    assert_complexity_grade(wb, max_grade="C")
```

### Describe a workbook for agents/LLMs

```python
from pytableau import Workbook

wb = Workbook.open("report.twbx")
info = wb.describe()
# Returns a structured dict ready to pass to an LLM:
# {version, datasources: [{name, fields, connections}], worksheets, dashboards, parameters}

caps = wb.capabilities()
# {has_hyper, has_server, has_calculations, counts: {...}, extras: [...]}
```

---

## CLI

`pytableau` ships a 30-command CLI:

```bash
# Inspect & diff
pytableau inspect workbook.twbx
pytableau diff before.twb after.twb
pytableau catalog workbook.twb

# Connection management
pytableau swap workbook.twb --server prod-db.corp.com --db analytics_prod
pytableau audit-connections workbook.twb

# Calculation linting
pytableau lint-calcs workbook.twb

# Governance
pytableau governance-lint workbook.twb --ruleset rules.yml --exit-code
pytableau index-workbooks ./workbooks/ --db catalog.db
pytableau search-index revenue --db catalog.db

# Fleet operations
pytableau fleet-scan ./workbooks/
pytableau comply ./workbooks/ --ruleset rules.yml
pytableau migrate ./workbooks/ --output ./migrated/ --swap dev-db:prod-db
pytableau contract-test workbook.twb --contract contracts.yml

# Packaging
pytableau package workbook.twb
pytableau unpackage workbook.twbx
```

---

## Feature Matrix

| Module | Capability | Status |
|--------|-----------|--------|
| `core` | Open/save `.twb` / `.twbx`, full object model | ✅ |
| `core` | Datasource, field, connection, filter mutation | ✅ |
| `core` | Worksheet shelf mutation, dashboard zone mutation | ✅ |
| `build` | `DatasourceBuilder`, `WorksheetBuilder`, `DashboardBuilder` | ✅ |
| `build` | `from_spec()` — YAML/JSON/dict → Workbook | ✅ |
| `build` | `quick_chart()`, `quick_dashboard()`, `Theme` | ✅ |
| `data` | Hyper extract create / refresh / attach / upsert | ✅ |
| `data` | DataFrame ↔ `.hyper` bridge (via pantab) | ✅ |
| `templates` | 10 built-in viz templates (bar, line, scatter, …) | ✅ |
| `calculations` | Lark-based formula parser + AST | ✅ |
| `calculations` | 6 calculation lint rules | ✅ |
| `inspect` | Catalog, lineage, complexity analysis | ✅ |
| `inspect` | `WorkbookDiff` / `WorkbookPatch` + changelog | ✅ |
| `governance` | 6 configurable lint rules, YAML rulesets | ✅ |
| `governance` | `WorkbookIndex` — SQLite cross-workbook search | ✅ |
| `agents` | `describe()`, `available_fields()`, `capabilities()` | ✅ |
| `agents` | `WorkbookTransaction` with XML rollback | ✅ |
| `fleet` | `FleetScanner` — scan directory, grade workbooks | ✅ |
| `fleet` | `MigrationPlan` / `MigrationEngine` — bulk migration | ✅ |
| `fleet` | `ComplianceRunner` + JUnit XML for CI/CD | ✅ |
| `fleet` | `ContractRunner` — schema contract testing | ✅ |
| `fleet` | `FleetReport` — HTML dashboard | ✅ |
| `testing` | 8 assertion helpers for pytest | ✅ |
| `testing` | `pytest11` entry point (auto-registers fixtures) | ✅ |
| `server` | Tableau Server / Cloud REST client | ✅ |
| `server` | Publish, download, refresh, permissions workflows | ✅ |
| `xml` | Canonical serialization, differ, fixers, schema discovery | ✅ |
| `package` | Asset management (images, extracts in `.twbx`) | ✅ |
| `cli` | 30-command CLI (`pytableau <command>`) | ✅ |

---

## Design Principles

1. **Layer cake, not monolith.** Each Tableau layer maps to a distinct submodule. Engage at any abstraction level.
2. **Batteries included, escape hatches available.** The Pythonic API covers 90% of use cases; raw `lxml` nodes are always accessible via `.xml_node`.
3. **Template-first for presentation.** Build a viz in Desktop, then parameterize it with pytableau — or build from a YAML spec.
4. **Fail loud, fail early.** Validate XML mutations before writing; `WorkbookTransaction` rolls back on any exception.
5. **Dependency-light by default.** Core requires only `lxml`. Hyper, server, pandas, analysis, governance, and testing are optional extras.
6. **Fleet-ready.** Scan, lint, migrate, and report across hundreds of workbooks in a single command.

---

## Requirements

- Python ≥ 3.11
- `lxml ≥ 4.9` (always installed)
- Optional: `tableauhyperapi`, `pantab`, `pandas`, `tableauserverclient`, `lark`, `networkx`, `pyyaml`, `pytest`

---

## License

MIT — see [LICENSE](LICENSE)
