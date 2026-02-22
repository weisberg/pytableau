# pytableau

> **What pandas did for tabular data, pytableau does for Tableau workbooks.**

`pytableau` is the unified Python SDK for Tableau workbook engineering. It brings every layer of Tableau workbook manipulation — data, connections, semantic model, presentation, packaging, and server lifecycle — under one coherent, Pythonic API.

## Why pytableau?

The Tableau Python ecosystem is fragmented. Tableau/Salesforce maintains several narrow libraries, each covering a single concern:

| Library | Layer | Limitation |
|---------|-------|-----------|
| `tableaudocumentapi` | Connection XML | No calc fields, no viz edits, abandoned 2021 |
| `tableauhyperapi` | `.hyper` data files | No XML awareness |
| `pantab` | DataFrame ↔ `.hyper` bridge | No XML awareness |
| `tableauserverclient` | Server REST API | No local file manipulation |

`pytableau` wraps and integrates all of them behind a single API.

## Install

```bash
# Core (XML + ZIP only — no optional dependencies)
pip install pytableau

# With Hyper / extract support
pip install "pytableau[hyper]"

# With pandas convenience methods
pip install "pytableau[pandas]"

# With Tableau Server/Cloud integration
pip install "pytableau[server]"

# Everything
pip install "pytableau[all]"
```

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

### Inject a DataFrame

```python
from pytableau import Workbook
import pandas as pd

wb = Workbook.open("template.twbx")
df = pd.read_csv("fresh_data.csv")
wb.datasources["Sales Data"].hyper.from_dataframe(df)
wb.save_as("refreshed_report.twbx")
```

### Generate a workbook from a template

```python
from pytableau import Workbook
import pandas as pd

df = pd.read_csv("q4_revenue.csv")

wb = Workbook.from_template("bar_chart")
wb.datasources["__PLACEHOLDER_DS__"].hyper.from_dataframe(df)
wb.template.map_fields({
    "__DIMENSION__": "Product Category",
    "__MEASURE__":   "Revenue",
    "__COLOR__":     "Region",
})
wb.parameters["__PARAM_TITLE__"].value = "Q4 2025 Revenue"
wb.save_as("q4_report.twbx")
```

### CLI

```bash
pytableau inspect workbook.twbx
pytableau diff before.twb after.twb
pytableau swap workbook.twb --server prod-db.corp.com --db analytics_prod
```

## Development Status

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Foundation: scaffolding, packaging, constants | In Progress |
| 1 | Read & Inspect: parse any `.twb`/`.twbx` | Planned |
| 2 | Connection & Field Mutation | Planned |
| 3 | Data Layer: `.hyper` integration | Planned |
| 4 | Template Engine | Planned |
| 5 | Server Integration | Planned |
| 6 | Advanced Features | Planned |

## Design Principles

1. **Layer cake, not monolith.** Each Tableau layer maps to a distinct submodule. Engage at any abstraction level.
2. **Batteries included, escape hatches available.** The Pythonic API covers 90% of use cases; raw `lxml` nodes are always accessible.
3. **Template-first for presentation.** Build a viz in Desktop, then parameterize it with pytableau.
4. **Fail loud, fail early.** Validate XML mutations before writing — a corrupt `.twb` is the worst outcome.
5. **Dependency-light by default.** Core requires only `lxml`. Hyper, server, and pandas are optional extras.
6. **Version-aware.** Track Tableau Desktop version; warn on incompatible XML.

## License

MIT — see [LICENSE](LICENSE)
