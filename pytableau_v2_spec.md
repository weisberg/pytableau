# pytableau 2.0 Spec

**Date:** February 23, 2026
**Author:** Brian Weisberg
**Baseline:** v1.0.0 — ~9,500 LOC, 35+ modules, 350+ tests, PyPI stable
**Target:** v2.0.0

---

## Thesis

v1.0 proved that a `.twb` is not opaque XML — it's a parseable, diffable, patchable abstract syntax tree. pytableau is the only library that treats Tableau workbooks this way.

v2.0 expands the thesis from **workbook as AST** to **Tableau content as infrastructure**: buildable from code, manageable at fleet scale, queryable through cloud APIs, and operable by AI agents through MCP.

The Tableau platform shift creates the opening. Salesforce shipped the official Tableau MCP Server (November 2025) and VizQL Data Service went GA (2025.1), but both are read-only. They can list content and query data. They cannot create, modify, govern, or lifecycle-manage workbook content. pytableau v2.0 owns the write side. Together with the official read-side tooling, agents and pipelines get full lifecycle control over Tableau content for the first time.

---

## Architecture

Four pillars, five new top-level modules.

```
                    ┌──────────────────────────────────────────────┐
                    │              pytableau v2.0                  │
                    ├──────────────────────────────────────────────┤
                    │                                              │
  Pillar I          │   mcp/         MCP server (write-side)       │
  Agent-Native      │   agents/      Discovery, transactions,      │
                    │                receipts, SKILL.md gen        │
                    │                                              │
                    ├──────────────────────────────────────────────┤
                    │                                              │
  Pillar II         │   cloud/       VizQL Data Service client,    │
  Cloud-Native      │                Tableau Semantics, sync,      │
                    │                activity log, themes          │
                    │                                              │
                    ├──────────────────────────────────────────────┤
                    │                                              │
  Pillar III        │   build/       DatasourceBuilder,            │  ✅ IMPLEMENTED
  Viz Authoring     │                WorksheetBuilder,             │
                    │                DashboardBuilder,             │
                    │                from_spec(), quick_chart()    │
                    │                                              │
                    ├──────────────────────────────────────────────┤
                    │                                              │
  Pillar IV         │   fleet/       Migration engine, compliance  │
  Fleet Ops         │                automation, contract testing, │
                    │                fleet health reporting        │
                    │                                              │
                    ├──────────────────────────────────────────────┤
                    │                                              │
  v1.0 Foundation   │   core/  xml/  data/  package/  inspect/     │
                    │   calculations/  templates/  server/         │
                    │   governance/  testing/  cli/                │
                    │                                              │
                    └──────────────────────────────────────────────┘
```

---

## Current State

Pillar III is already implemented. The `build/` module ships 7 files, ~900 lines of production code, and 49 passing tests with zero regressions against the existing 258-test suite. Everything below reflects this progress.

| Module | Status | LOC | Tests |
|--------|--------|-----|-------|
| `build/_xml.py` | ✅ Done | 60 | 8 |
| `build/datasource.py` | ✅ Done | 220 | 8 |
| `build/worksheet.py` | ✅ Done | 250 | 14 |
| `build/dashboard.py` | ✅ Done | 230 | 8 |
| `build/spec.py` | ✅ Done | 220 | 7 |
| `build/shortcuts.py` | ✅ Done | 170 | 4 |
| `build/__init__.py` | ✅ Done | 60 | — |
| `cloud/` | 🔲 Not started | — | — |
| `mcp/` | 🔲 Not started | — | — |
| `agents/` | 🔲 Not started | — | — |
| `fleet/` | 🔲 Not started | — | — |

---

## Pillar I — Agent-Native SDK

### Problem

Agents can read Tableau content through the official MCP server but cannot create, modify, or manage it. pytableau has the full mutation API but no agent-facing interface. The gap is a structured tool layer between the two.

### Modules

#### `mcp/` — MCP Server

A standalone MCP server exposable via stdio or streamable-http that wraps pytableau as a set of typed tools.

**Entry points:**

```bash
pip install "pytableau[mcp]"
pytableau mcp serve --transport stdio
pytableau mcp serve --transport streamable-http --port 8080
```

**Tool surface (25+ tools across 6 categories):**

| Category | Tools |
|----------|-------|
| Inspect | `inspect_workbook`, `catalog_fields`, `list_datasources`, `list_worksheets`, `complexity_report` |
| Mutate | `swap_connection`, `add_calculated_field`, `rename_field`, `remove_field`, `add_filter` |
| Create | `build_worksheet`, `build_dashboard`, `create_from_spec`, `create_from_template`, `quick_chart` |
| Govern | `lint_workbook`, `diff_workbooks`, `search_index`, `validate`, `compliance_check` |
| Lifecycle | `promote_environment`, `publish`, `apply_patch`, `save_as` |
| Extract | `create_extract`, `refresh_extract`, `attach_hyper` |

Each tool returns structured JSON with typed input/output schemas. Agents discover parameters and response shapes without parsing docs.

**Files:**

| File | Purpose |
|------|---------|
| `mcp/server.py` | MCP server entry point, transport selection, tool registration |
| `mcp/tools.py` | Tool definitions with JSON Schema for every parameter and return type |
| `mcp/skill.py` | Auto-generates a SKILL.md from the tool registry for Claude Code |

**Dependency:** `mcp>=1.0.0` (optional extra `[mcp]`)

#### `agents/` — Agent Ergonomics

Enhancements to the core API surface that make pytableau easier for agents to use correctly.

**`agents/discovery.py` — Introspection**

```python
wb.describe()          # Structured schema: datasources, fields, worksheets, dashboards
ds.available_fields()  # Field names, types, roles — not Field objects
wb.capabilities()      # What can this workbook do given installed extras?
```

**`agents/transactions.py` — Atomic Batching**

```python
with wb.transaction() as tx:
    tx.swap_connection(server="prod-db.corp.com")
    tx.rename_field("Sales Data", "Rev", "Revenue")
    tx.add_calculated_field("Sales Data", "Margin", "[Revenue] - [Cost]")
# All succeed or the workbook is unchanged
```

Implementation: deep-copy the XML tree on enter, restore on exception.

**`agents/receipts.py` — Structured Results**

Every mutation returns a receipt:

```python
result = ds.add_calculated_field("Profit Ratio", "SUM([Profit])/SUM([Sales])")
# result.status = "created" | "already_exists" | "updated"
# result.field_name = "Profit Ratio"
# result.suggestion = None  (or a corrective hint on error)
```

**Enhanced exceptions** — every `PyTableauError` gets a `suggestion` field:

```python
class FieldNotFoundError(FieldError, KeyError):
    suggestion: str  # "Available fields: Revenue, Cost, Profit. Did you mean 'Profit'?"
```

**`agents/skill.py` — SKILL.md Generation**

```bash
pytableau mcp generate-skill > SKILL.md
```

Produces a complete Claude Code skill definition: every CLI command, parameter schema, usage examples, and behavioral contracts.

---

## Pillar II — Cloud-Native Integration

### Problem

v1.0's `server/` module wraps `tableauserverclient` for REST publish/download. The platform has moved beyond REST: VizQL Data Service (programmatic data queries), Tableau Semantics (governed semantic layer), Activity Log API (dashboard telemetry), and Custom Themes (2025.1). pytableau must become a peer of these APIs.

### Modules

#### `cloud/vizql.py` — VizQL Data Service Client

```python
from pytableau.cloud import VizQLClient

vds = VizQLClient(server="https://10az.online.tableau.com", site="mysite",
                  token_name="pytableau", token_value="...")

# Query → DataFrame
df = vds.query("Superstore",
    fields=["Category", "SUM(Sales)", "SUM(Profit)"],
    filters=[{"field": "Region", "values": ["East", "West"]}])

# Metadata
meta = vds.metadata("Superstore")
```

**Why it matters:** VDS lets pytableau validate local workbook changes against live server data. Build locally → verify schema matches the published datasource → publish with confidence.

#### `cloud/sync.py` — Bidirectional Sync

```python
from pytableau.cloud import SyncClient

sync = SyncClient(server="...", token_name="...", token_value="...")

with sync.checkout("project/Sales Dashboard") as wb:
    wb.swap_connection(server="prod-db.corp.com")
    # On exit: validates, publishes, logs

drift = sync.detect_drift("project/Sales Dashboard", local_wb)
```

#### `cloud/semantics.py` — Tableau Semantics Validation

```python
from pytableau.cloud import SemanticsClient

sem = SemanticsClient(server="...", token_name="...", token_value="...")
issues = sem.validate_workbook(wb, model="Revenue Analytics")
# Fields not in model, type mismatches, deprecated dimensions
```

#### `cloud/themes.py` — Custom Theme Management

```python
from pytableau.cloud import Theme

theme = Theme.from_workbook(wb)
theme = Theme(name="Corporate Q4", font_family="Helvetica Neue",
              colors={"primary": "#003366", "secondary": "#CC6600"})
wb.apply_theme(theme)
```

Leverages the 2025.1 Custom Themes API.

#### `cloud/activity.py` — Activity Log

Wraps the `vizql_http_requests` event stream for dashboard performance monitoring and usage analytics.

**Dependency:** `httpx>=0.27` (optional extra `[cloud]`)

---

## Pillar III — Programmatic Viz Authoring

### Status: ✅ Core Implementation Complete

The `build/` module is implemented, tested, and passing. It delivers:

**`DatasourceBuilder`** — Fluent builder for `<datasource>` XML. Columns, calculated fields, connection class/attrs. Classmethods `from_dataframe()` (infers schema from pandas dtypes with dimension heuristics) and `from_hyper()` (reads Hyper file schema).

**`WorksheetBuilder`** — Fluent builder for `<worksheet>` XML. Rows/columns shelves, all five mark channels (color/size/detail/tooltip/label), categorical + range filters, sort specs, mark type, datasource binding, title. Validates at build time.

**`DashboardBuilder`** — Fluent builder for `<dashboard>` XML. Sheet/text/filter/blank zones with pixel positioning, filter + highlight + URL actions, phone and tablet device layouts.

**`from_spec()`** — Takes a Python dict, YAML file, or JSON file and builds a complete `Workbook`. Auto-resolves datasource caption → internal name wiring. Primary agent-facing entry point.

**`quick_chart()`** / **`quick_dashboard()`** — One-liner convenience functions.

All builders produce raw `lxml.etree._Element` nodes, validate on build, and pass through the existing `XMLSchemaEngine` on save. Zero new required dependencies.

### Remaining Work (Pillar III Enhancements)

These extend the implemented foundation:

| Item | What | Effort |
|------|------|--------|
| `build/theme.py` | Programmatic theme creation and application via builder pattern | 1 session |
| `Workbook.add_worksheet()` / `add_dashboard()` convenience methods | Accept Builder or Element directly on the Workbook class | 1 session |
| `.twbx` packaging shortcut | `quick_chart()` auto-writes .hyper and packages as .twbx | 1 session |
| 3 additional template types via spec | stacked_bar, dual_axis precursor, waterfall | 2 sessions |
| `from_dataframe()` end-to-end | DataFrame → .hyper → .twbx in one call (needs HyperBridge integration) | 2 sessions |
| Workbook-level `from_spec()` registration | `Workbook.from_spec()` as a classmethod alias | Trivial |

### Explicit Scope Boundaries

These are valid extensions but not part of the v2.0 scope:

| Deferred | Reason |
|----------|--------|
| Formatting (colors, fonts, number formats) | Separate feature; `core/formatting.py` stub exists |
| Custom shapes and images | Requires asset management in `.twbx` ZIP |
| Viz-in-tooltip | Complex XML; Desktop-specific |
| Dual-axis charts | Requires `<pane>` XML not in the object model |
| Table calculations on shelves | Undocumented shelf encoding |
| Reference lines and bands | Separate `<reflines>` subtree |
| Parameter controls on dashboards | Needs `<zone type="paramctrl">` |
| Pages shelf | Rarely used; complex XML |

---

## Pillar IV — Fleet Operations

### Problem

v1.0 governance handles one workbook at a time. Enterprise Tableau deployments have hundreds or thousands. v2.0 scales governance to fleet level.

### Modules

#### `fleet/scanner.py` — Fleet Scanner

```python
from pytableau.fleet import FleetScanner

scanner = FleetScanner("./all_workbooks/")
scanner.scan()
report = scanner.report()
report.to_html("fleet_health.html")

# Stats: total workbooks, complexity distribution, deprecated function usage,
# connection topology, unused field density, cross-workbook field lineage
```

#### `fleet/migrator.py` — Content Migration Engine

```python
from pytableau.fleet import MigrationPlan, MigrationEngine

plan = (
    MigrationPlan()
    .source_directory("./legacy/")
    .target_version("2025.2")
    .swap_connections({"old-warehouse.corp.com": "snowflake.corp.com"})
    .rename_fields({"Cust ID": "Customer ID", "Rev": "Revenue"})
    .apply_theme("corporate_2026")
    .validate_all()
    .output_directory("./migrated/")
)

report = MigrationEngine(plan).execute(dry_run=True)
# 47 scanned, 43 clean, 4 issues
```

#### `fleet/compliance.py` — YAML-Driven Compliance Automation

```yaml
# compliance.yml
ruleset: vanguard-analytics-2026
rules:
  - id: no-live-connections
    severity: error
    check: no_live_connections
  - id: naming-convention
    severity: warning
    check: field_name_pattern
    pattern: "^[A-Z][a-z]+(\\s[A-Z][a-z]+)*$"
  - id: no-hardcoded-credentials
    severity: error
    check: no_embedded_credentials
  - id: max-complexity
    severity: warning
    check: max_complexity_grade
    grade: C
  - id: no-deprecated-functions
    severity: error
    check: no_deprecated_functions
    patterns: ["SCRIPT_*", "RAWSQL_*"]
exit_code_on: error
```

```bash
pytableau comply --ruleset compliance.yml ./workbooks/ --format junit-xml > results.xml
echo $?  # 0 = pass, 1 = fail
```

JUnit XML output integrates directly into CI/CD pipelines (Jenkins, GitHub Actions, GitLab CI).

#### `fleet/contracts.py` — Contract Testing Framework

Extends the v1.0 pytest plugin:

```yaml
# contracts/sales_dashboard.yml
workbook: Sales Dashboard.twbx
contracts:
  datasources:
    - name: Sales Data
      required_fields: [Revenue, Cost, Profit, Region]
      no_live_connections: true
  worksheets:
    - name: Revenue by Region
      must_use_fields: [Revenue, Region]
      max_marks: 5000
  dashboards:
    - name: Executive Summary
      must_contain: [Revenue by Region, Trend Over Time]
      has_phone_layout: true
  formulas:
    valid: true
    no_deprecated: true
    max_lod_depth: 2
```

```bash
pytableau contract-test contracts/ ./workbooks/ --format junit-xml
```

#### `fleet/report.py` — Fleet Health Dashboard

Generates a standalone HTML report summarizing fleet health. Complexity grade distribution, deprecated function heatmap, connection topology graph, unused field density per workbook.

---

## Module Map

```
pytableau/
│
│  ── v1.0 Foundation ──────────────────────────────────────────
├── core/                        # Object model
├── xml/                         # XML engine, validation, rules, fixers
├── data/                        # HyperBridge, extract management
├── package/                     # .twb/.twbx packaging
├── inspect/                     # Catalog, lineage, complexity, reports
├── calculations/                # Formula parser, AST, linter
├── templates/                   # Template engine, 10+ built-in templates
├── server/                      # REST API (publish, download, metadata)
├── governance/                  # WorkbookIndex, lint engine, CI gate
├── testing/                     # pytest-tableau plugin
├── cli/                         # 17+ commands via tooli
│
│  ── v2.0 New Modules ─────────────────────────────────────────
├── build/                       # ✅ Programmatic viz authoring
│   ├── __init__.py              #   Public API re-exports
│   ├── _xml.py                  #   Internal XML generation helpers
│   ├── datasource.py            #   DatasourceBuilder
│   ├── worksheet.py             #   WorksheetBuilder
│   ├── dashboard.py             #   DashboardBuilder
│   ├── spec.py                  #   from_spec() — YAML/dict/JSON → Workbook
│   ├── shortcuts.py             #   quick_chart(), quick_dashboard()
│   └── theme.py                 #   Theme builder (planned)
│
├── cloud/                       # 🔲 Cloud-native APIs
│   ├── vizql.py                 #   VizQL Data Service client
│   ├── semantics.py             #   Tableau Semantics validation
│   ├── sync.py                  #   Bidirectional checkout/publish
│   ├── themes.py                #   Custom Theme management
│   └── activity.py              #   Activity Log API
│
├── mcp/                         # 🔲 MCP server
│   ├── server.py                #   Server entry point (stdio + streamable-http)
│   ├── tools.py                 #   25+ tool definitions with JSON Schema
│   └── skill.py                 #   SKILL.md auto-generator
│
├── agents/                      # 🔲 Agent ergonomics
│   ├── discovery.py             #   wb.describe(), capabilities()
│   ├── transactions.py          #   Atomic multi-step mutations with rollback
│   └── receipts.py              #   Structured operation results
│
└── fleet/                       # 🔲 Fleet-scale operations
    ├── scanner.py               #   FleetScanner (bulk analysis)
    ├── migrator.py              #   MigrationPlan + MigrationEngine
    ├── compliance.py            #   YAML-driven compliance automation
    ├── contracts.py             #   Contract testing framework
    └── report.py                #   Fleet health HTML dashboard
```

---

## Breaking Changes

A major version bump allows cleaning up API debt accumulated during the v0.x–v1.0 cycle.

| Change | Rationale | Migration Path |
|--------|-----------|----------------|
| Minimum Python → 3.11 | 3.10 EOL October 2026 | Document in migration guide |
| `ConnectionError` → `TableauConnectionError` | Conflicts with Python builtin | Find-and-replace import |
| `server/` split into `server/` + `cloud/` | Cloud APIs (VDS, Semantics) don't belong in the REST wrapper | `from pytableau.server import ServerClient` still works |
| Collection properties → `Sequence` protocol | Consistent iteration contract | Existing iteration code unchanged |
| Template engine gains `from_spec()` | Placeholder templates are limiting for agent workflows | `from_template()` still works; `from_spec()` preferred |
| `Workbook.open()` gains async variant | Cloud operations need async | Sync path unchanged; `await Workbook.aopen()` for async |
| Pydantic v2 optional | Install friction for casual users | Core stays lxml-only; `pytableau.models` uses pydantic if present |

---

## Dependency Strategy

```
pytableau (core)
├── Required: lxml
│
├── [cli]       tooli>=6.0
├── [hyper]     tableauhyperapi + pantab
├── [server]    tableauserverclient + requests
├── [cloud]     httpx>=0.27                        ← NEW
├── [mcp]       mcp>=1.0.0                         ← NEW
├── [pandas]    pandas
├── [build]     pyyaml>=6.0                        ← NEW (for YAML specs; dict/JSON need nothing)
├── [analysis]  lark + networkx + jinja2
├── [all]       everything above
```

Zero new required dependencies. Every new module is an optional extra.

---

## Delivery Schedule

### M1: Housekeeping + Build Polish (v2.0-alpha.1)

**Scope:** Apply breaking changes, polish the build module, add `Workbook.add_worksheet()` / `add_dashboard()` convenience methods, `build/theme.py`, `Workbook.from_spec()` classmethod registration.

**Also:** Migration guide from v1.0, CHANGELOG entries, Python 3.11 floor, exception rename.

**Estimated:** 2 weeks

### M2: Agent Ergonomics (v2.0-alpha.2)

**Scope:** `agents/discovery.py`, `agents/transactions.py`, `agents/receipts.py`. Enhanced exceptions with `suggestion` field across the hierarchy.

**Estimated:** 3 weeks

### M3: Cloud — VDS + Sync (v2.0-alpha.3)

**Scope:** `cloud/vizql.py` (VDS client with DataFrame return, metadata introspection), `cloud/sync.py` (checkout/publish workflow, drift detection via VDS).

**Estimated:** 4 weeks

### M4: Cloud — Semantics + Themes + Activity (v2.0-beta.1)

**Scope:** `cloud/semantics.py`, `cloud/themes.py`, `cloud/activity.py`. Validate local workbooks against published semantic models. Programmatic theme creation.

**Estimated:** 3 weeks

### M5: MCP Server (v2.0-beta.2)

**Scope:** `mcp/server.py`, `mcp/tools.py`, `mcp/skill.py`. Full MCP server with 25+ tools. SKILL.md auto-generation. CLI commands: `pytableau mcp serve`, `pytableau mcp generate-skill`.

**Depends on:** M2 (agent ergonomics feed into tool responses).

**Integration testing:** Claude Code, Claude Desktop, VS Code + MCP extension.

**Estimated:** 4 weeks

### M6: Fleet Operations (v2.0-beta.3)

**Scope:** `fleet/scanner.py`, `fleet/migrator.py`, `fleet/compliance.py`, `fleet/contracts.py`, `fleet/report.py`. CLI commands: `pytableau comply`, `pytableau migrate`, `pytableau contract-test`.

**Estimated:** 4 weeks

### M7: Polish + Release (v2.0-rc.1 → v2.0.0)

**Scope:** Full documentation for all new modules (mkdocstrings auto-gen). 10+ example scripts. Performance benchmarks (fleet scanning at 100+ workbooks). Community feedback from alpha/beta incorporated.

**Estimated:** 3 weeks

**Total: ~23 weeks from v1.0 to v2.0.0 GA.**

```
Week  1─2     M1  Housekeeping + Build Polish          alpha.1
Week  3─5     M2  Agent Ergonomics                     alpha.2
Week  6─9     M3  Cloud: VDS + Sync                    alpha.3
Week 10─12    M4  Cloud: Semantics + Themes            beta.1
Week 13─16    M5  MCP Server                           beta.2
Week 17─20    M6  Fleet Operations                     beta.3
Week 21─23    M7  Polish + Release                     rc.1 → 2.0.0
```

---

## Test Targets

| Module | Unit Tests | Integration Tests | Total |
|--------|-----------|-------------------|-------|
| `build/` (existing) | 40 | 9 | 49 |
| `build/` enhancements | 8 | 4 | 12 |
| `agents/` | 15 | 5 | 20 |
| `cloud/` | 20 | 10 | 30 |
| `mcp/` | 15 | 10 | 25 |
| `fleet/` | 25 | 10 | 35 |
| **v2.0 new total** | **123** | **48** | **171** |
| **v1.0 existing** | | | **~350** |
| **v2.0 grand total** | | | **~520** |

---

## Success Criteria

| Metric | v1.0 Baseline | v2.0 Target |
|--------|---------------|-------------|
| PyPI monthly downloads | — | 50,000+ |
| Test count | ~350 | 520+ |
| MCP server tools | 0 | 25+ |
| Cloud API coverage | REST only | REST + VDS + Semantics + Activity Log |
| Chart types buildable from code | 0 | 10+ (via builder + spec) |
| Fleet workbooks scannable | 1 | 500+ per run |
| CI pipeline integrations | lint only | lint + comply + contract-test (JUnit XML) |

---

## Competitive Position

```
                         Local File       Cloud API        Agent-Native
                         Manipulation     Integration      (MCP + Skills)
                         ────────────     ───────────      ──────────────
tableaudocumentapi       ◐  15% XML      ✗                ✗
tableau-mcp (official)   ✗               ◐  read-only     ◐  read-only
tableauserverclient      ✗               ◐  REST only     ✗
VizQL Data Service SDK   ✗               ◐  data only     ✗
pytableau v2.0           ●  full AST     ●  REST+VDS+Sem  ●  full MCP
```

Only library spanning all three columns. That's the moat.

---

## What v2.0 Does Not Cover

These are real features deferred to v2.1+ or beyond:

| Feature | Why Deferred |
|---------|-------------|
| Accessibility compliance (WCAG 2.2 AA) | Complex; better as standalone beta |
| Webhook management (22 event types) | Low demand relative to other pillars |
| Admin Insights correlation | Requires Tableau+ licensing |
| Advanced formatting (conditional colors, custom fonts) | Separate feature; `core/formatting.py` stub exists |
| Viz-in-tooltip, annotations, pages shelf | Desktop-specific XML; low programmatic value |
| Dual-axis charts in builder | Requires `<pane>` XML not in the object model |
| Table calculations on builder shelves | Undocumented shelf encoding for RUNNING_TOTAL etc. |
| Real-time streaming workbook mutations | Research; no clear API pattern yet |
