# pytableau — PLAN.md

## The Unified Python SDK for Tableau Workbook Engineering

**Version:** 0.1.0 (initial planning)
**Author:** Brian
**License:** MIT
**Target PyPI name:** `pytableau`
**Target import:** `import pytableau`

---

## 1. Vision

`pytableau` is a single Python package that unifies every layer of Tableau workbook manipulation — data, connections, semantic model, presentation, packaging, and server lifecycle — behind one coherent, Pythonic API. It replaces the need to juggle `tableaudocumentapi`, `pantab`, `tableauhyperapi`, `tableauserverclient`, raw `lxml`, and manual ZIP handling by wrapping and integrating all of them.

**The one-liner pitch:** *"What pandas did for tabular data, pytableau does for Tableau workbooks."*

### 1.1 Why This Doesn't Exist Yet

The Tableau Python ecosystem is fragmented by design. Tableau/Salesforce maintains several narrow, officially "unsupported" libraries, each covering a single concern:

| Library | Layer | Limitation |
|---------|-------|-----------|
| `tableaudocumentapi` (MIT) | Connection XML | Cannot create from scratch, no calc fields, no viz edits |
| `tableauhyperapi` (Apache 2.0) | .hyper data files | No XML awareness at all |
| `pantab` (BSD-3) | DataFrame ↔ .hyper bridge | No XML awareness at all |
| `tableauserverclient` (MIT) | Server REST API | No local file manipulation |
| `lxml` / raw XML | Everything (in theory) | Undocumented schema, fragile, version-dependent |

No project has attempted to span all layers because the **XML presentation layer is undocumented and fragile**. pytableau solves this with a pragmatic architecture: full programmatic control over data + connections + semantic model, plus a **template engine** for the presentation layer, plus escape hatches to raw XML for power users.

### 1.2 Design Principles

1. **Layer cake, not monolith.** Each Tableau layer (data, connection, semantic, presentation, package, server) maps to a distinct internal submodule. Users can engage at any level of abstraction.
2. **Batteries included, escape hatches available.** The Pythonic API covers 90% of use cases. For the remaining 10%, expose the underlying `lxml` nodes directly so power users can do raw XML surgery.
3. **Template-first for presentation.** Instead of trying to reverse-engineer Tableau's rendering engine, embrace templates: build a viz in Desktop, then parameterize it with pytableau.
4. **Fail loud, fail early.** Validate XML mutations against known schema rules before writing. A corrupt `.twb` that only errors when opened in Desktop is the worst possible outcome.
5. **Dependency-light by default.** Core functionality (XML + ZIP) requires only `lxml`. Hyper, server, and pandas features are optional extras (`pip install pytableau[hyper]`, `pytableau[server]`, `pytableau[all]`).
6. **Version-aware.** Track Tableau Desktop version in every operation. Warn or error when generating XML that may be incompatible with the target Tableau version.

---

## 2. Dependency Strategy

### 2.1 Dependency Tiers

```
pytableau (core)
├── Required: lxml (XML engine — same dep as tableaudocumentapi)
│
├── Optional extra [hyper]:
│   ├── tableauhyperapi (official Hyper engine, Apache 2.0)
│   └── pantab (fast DataFrame ↔ Hyper bridge, BSD-3)
│
├── Optional extra [server]:
│   └── tableauserverclient (official REST API client, MIT)
│
├── Optional extra [pandas]:
│   └── pandas (for DataFrame convenience methods)
│
└── Optional extra [all]: everything above
```

### 2.2 Integration Philosophy

pytableau **wraps but does not fork** upstream libraries. We depend on them as runtime imports, adding our unified API layer on top. This means:

- We inherit upstream fixes and improvements automatically
- We don't carry maintenance burden for Hyper engine internals or REST API changes
- Users who already have these packages installed get pytableau for free (no conflicts)
- If an optional dependency is missing, we raise a clear `ImportError` with install instructions

### 2.3 What We Absorb vs. What We Wrap

| Component | Strategy | Rationale |
|-----------|----------|-----------|
| `tableaudocumentapi` | **Absorb & extend** (rewrite) | Too limited, abandoned since 2021, we need full XML control |
| `tableauhyperapi` | **Wrap** (thin adapter) | Closed-source binary, well-maintained, just needs ergonomic API |
| `pantab` | **Wrap** (delegate) | Excellent performance, actively maintained, don't reinvent |
| `tableauserverclient` | **Wrap** (thin adapter) | Actively maintained by Tableau, just needs integration glue |
| `lxml` | **Use directly** | Our XML engine, no abstraction needed |
| ZIP handling | **Own** (stdlib `zipfile`) | Trivial, no dependency needed |

### 2.4 License Compatibility

All upstream licenses (MIT, BSD-3, Apache 2.0) are compatible with our MIT license. No copyleft obligations. The `tableauhyperapi` binary (Apache 2.0) is a runtime dependency, not bundled.

---

## 3. Architecture

### 3.1 Layered Model

```
┌──────────────────────────────────────────────────────────────┐
│                    pytableau Public API                       │
│  Workbook · Datasource · Worksheet · Dashboard · HyperData  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ xml/    │ │ data/    │ │ server/  │ │ templates/     │  │
│  │         │ │          │ │          │ │                │  │
│  │ Schema  │ │ Hyper    │ │ TSC      │ │ Template       │  │
│  │ Engine  │ │ Bridge   │ │ Adapter  │ │ Engine         │  │
│  │         │ │          │ │          │ │                │  │
│  │ Node    │ │ pandas ↔ │ │ publish/ │ │ Field mapping  │  │
│  │ Proxy   │ │ .hyper   │ │ download │ │ Parameterize   │  │
│  │         │ │          │ │          │ │                │  │
│  │ Migrate │ │ SQL on   │ │ auth     │ │ Built-in       │  │
│  │         │ │ .hyper   │ │          │ │ library        │  │
│  └────┬────┘ └────┬─────┘ └────┬─────┘ └───────┬────────┘  │
│       │           │            │                │           │
├───────┴───────────┴────────────┴────────────────┴───────────┤
│                    package/ (ZIP I/O)                         │
│              .twb ←→ .twbx ←→ temp directory                 │
├──────────────────────────────────────────────────────────────┤
│                External Dependencies                          │
│    lxml    tableauhyperapi    pantab    tableauserverclient   │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Module Map

```
pytableau/
├── __init__.py                  # Public API re-exports
├── py.typed                     # PEP 561 marker
│
├── core/                        # Object model
│   ├── __init__.py
│   ├── workbook.py              # Workbook: top-level entry point
│   ├── datasource.py            # Datasource, Connection, Relation
│   ├── fields.py                # Field, CalculatedField, Parameter, Group, Set, Bin
│   ├── worksheet.py             # Worksheet, Shelf, MarkCard, Encoding
│   ├── dashboard.py             # Dashboard, Zone, Action, DashboardObject
│   ├── filters.py               # CategoricalFilter, RangeFilter, RelativeDateFilter
│   └── formatting.py            # Style, ColorPalette, Font, Tooltip
│
├── xml/                         # XML engine
│   ├── __init__.py
│   ├── engine.py                # XMLSchemaEngine: validation, version rules
│   ├── proxy.py                 # XMLNodeProxy: safe mutation base class
│   ├── writer.py                # XML generation helpers (indent, namespace, encoding)
│   ├── differ.py                # Structural diff between two .twb XML trees
│   ├── schemas/                 # Version-specific schema knowledge
│   │   ├── __init__.py
│   │   ├── base.py              # Common elements across all versions
│   │   ├── v2022.py             # Tableau 2022.x specifics
│   │   ├── v2023.py             # Tableau 2023.x specifics
│   │   ├── v2024.py             # Tableau 2024.x specifics
│   │   └── v2025.py             # Tableau 2025.x specifics
│   └── discovery/               # Schema reverse-engineering tools
│       ├── __init__.py
│       ├── corpus.py            # Infer schema from .twb corpus
│       └── controlled_diff.py   # Build schema from controlled Desktop diffs
│
├── data/                        # Data layer (.hyper files)
│   ├── __init__.py
│   ├── bridge.py                # HyperBridge: unified pantab + hyperapi wrapper
│   ├── types.py                 # Type mapping: pandas ↔ Hyper ↔ Tableau XML
│   └── extract.py               # Extract lifecycle (create, refresh, attach)
│
├── package/                     # .twbx packaging
│   ├── __init__.py
│   ├── manager.py               # PackageManager: transparent .twbx ↔ temp dir
│   └── assets.py                # Image, shape, and asset handling
│
├── templates/                   # Template engine
│   ├── __init__.py
│   ├── engine.py                # TemplateEngine: parameterized workbook generation
│   ├── mapping.py               # FieldMapping: placeholder → real field
│   └── library/                 # Pre-built starter templates
│       ├── __init__.py
│       ├── bar_chart.twb
│       ├── line_chart.twb
│       ├── scatter_plot.twb
│       ├── heatmap.twb
│       ├── treemap.twb
│       ├── map.twb
│       └── kpi_dashboard.twb
│
├── server/                      # Tableau Server/Cloud integration
│   ├── __init__.py
│   ├── client.py                # ServerClient: wraps tableauserverclient
│   └── workflows.py             # High-level: publish, download, refresh, round-trip
│
├── inspect/                     # Read-only analysis & reporting
│   ├── __init__.py
│   ├── catalog.py               # List all fields, calcs, connections in a workbook
│   ├── lineage.py               # Field lineage: which calcs use which fields
│   ├── report.py                # Generate documentation for a workbook
│   └── diff.py                  # Semantic diff between two workbooks
│
├── cli/                         # Optional CLI interface
│   ├── __init__.py
│   └── main.py                  # `pytableau inspect`, `pytableau diff`, `pytableau swap`
│
├── exceptions.py                # Custom exception hierarchy
├── constants.py                 # Enums: MarkType, DataType, Role, FilterType, etc.
├── _compat.py                   # Optional dependency import helpers
└── _version.py                  # Version string
```

### 3.3 Object Model Detail

#### Workbook (top-level)

```python
class Workbook:
    """Entry point for all pytableau operations."""

    # Construction
    @classmethod
    def open(cls, path: str | Path) -> "Workbook": ...        # .twb or .twbx
    @classmethod
    def new(cls, version: str = "2024.1") -> "Workbook": ...   # From scratch
    @classmethod
    def from_template(cls, template: str | Path, **kwargs) -> "Workbook": ...

    # Properties
    version: str                           # Tableau version string
    datasources: DatasourceCollection      # dict-like, keyed by name
    worksheets: WorksheetCollection        # dict-like, keyed by name
    dashboards: DashboardCollection        # dict-like, keyed by name
    parameters: ParameterCollection        # shortcut into Parameters datasource

    # Raw XML access (escape hatch)
    @property
    def xml_root(self) -> etree.Element: ...
    @property
    def xml_tree(self) -> etree.ElementTree: ...

    # I/O
    def save(self) -> None: ...
    def save_as(self, path: str | Path) -> None: ...
    def to_xml_string(self) -> str: ...

    # Server integration (requires [server] extra)
    def publish(self, server: str, project: str, **auth) -> None: ...
    def download(self, server: str, workbook_id: str, **auth) -> "Workbook": ...

    # Inspection
    def catalog(self) -> WorkbookCatalog: ...          # All fields, calcs, connections
    def lineage(self, field: str) -> FieldLineage: ... # Dependency graph
    def diff(self, other: "Workbook") -> WorkbookDiff: ...

    # Validation
    def validate(self) -> list[ValidationIssue]: ...
```

#### Datasource

```python
class Datasource:
    name: str
    caption: str
    connections: list[Connection]
    fields: FieldCollection              # All fields (base + calculated)
    calculated_fields: CalcFieldCollection
    relations: list[Relation]            # Tables, joins, custom SQL

    # Hyper integration (requires [hyper] extra)
    @property
    def hyper(self) -> HyperBridge: ...  # Lazy, only if .hyper exists

    # Field operations
    def add_field(self, name, datatype, role, ...) -> Field: ...
    def add_calculated_field(self, caption, formula, datatype, ...) -> CalculatedField: ...
    def remove_field(self, name_or_field) -> None: ...
    def rename_field(self, old_name, new_name) -> None: ...

    # Connection operations
    def swap_connection(self, **kwargs) -> None: ...    # server, dbname, etc.
    def set_custom_sql(self, sql: str) -> None: ...

    # Raw XML
    @property
    def xml_node(self) -> etree.Element: ...
```

#### HyperBridge (data layer)

```python
class HyperBridge:
    """Unified interface to .hyper file within a workbook."""

    # DataFrame I/O (requires [pandas] or [hyper] extra)
    def from_dataframe(self, df, table="Extract", mode="replace") -> None: ...
    def to_dataframe(self, table="Extract") -> pd.DataFrame: ...
    def append_dataframe(self, df, table="Extract") -> None: ...

    # Raw SQL on .hyper
    def execute(self, sql: str) -> None: ...
    def query(self, sql: str) -> pd.DataFrame: ...

    # Introspection
    def tables(self) -> list[str]: ...
    def schema(self, table: str) -> list[ColumnInfo]: ...
    def row_count(self, table: str) -> int: ...
```

#### Worksheet

```python
class Worksheet:
    name: str
    datasources: list[Datasource]        # Which datasources this sheet uses
    mark_type: MarkType                   # bar, line, circle, etc.
    rows: list[FieldReference]            # Fields on Rows shelf
    cols: list[FieldReference]            # Fields on Columns shelf
    filters: FilterCollection             # Active filters
    marks: MarkCard                       # color, size, detail, tooltip, label

    # Shelf operations
    def add_to_rows(self, field: str | Field) -> None: ...
    def add_to_cols(self, field: str | Field) -> None: ...
    def add_filter(self, field, filter_type, **kwargs) -> Filter: ...
    def set_sort(self, field: str, order: str = "desc") -> None: ...

    # Raw XML
    @property
    def xml_node(self) -> etree.Element: ...
```

#### Dashboard

```python
class Dashboard:
    name: str
    size: tuple[int, int]                # (width, height)
    zones: list[Zone]                    # Layout zones
    actions: list[Action]                # Filter, highlight, URL actions

    # Layout operations
    def add_sheet(self, worksheet, x, y, w, h) -> Zone: ...
    def add_text(self, text, x, y, w, h) -> Zone: ...
    def add_image(self, path, x, y, w, h) -> Zone: ...
    def set_size(self, width, height) -> None: ...

    # Action operations
    def add_filter_action(self, source, target, fields) -> Action: ...
    def add_url_action(self, name, url_template) -> Action: ...

    # Raw XML
    @property
    def xml_node(self) -> etree.Element: ...
```

---

## 4. XML Schema Strategy

This is the **hardest technical challenge** in the project. Tableau's XML is undocumented, version-dependent, and deeply nested. Our strategy is multi-pronged:

### 4.1 Phase 1: Curated Schema Knowledge (Manual)

Start with **hand-coded schema rules** for the most common operations, derived from:

1. The [ranvithm/tableau.xml](https://github.com/ranvithm/tableau.xml) community documentation
2. The [cmtoomey gist](https://gist.github.com/cmtoomey/96342ba07dd5cba6ecc6) (fully annotated .twb)
3. Tableau's own `tableaudocumentapi` source code (MIT — we can study their XPath patterns)
4. The [tableauandbehold.com](https://tableauandbehold.com/2016/06/29/how-tds-twb-files-work-xml/) blog series on XML internals
5. Controlled experiments: make a single change in Desktop, diff the `.twb` before/after

This gives us reliable knowledge for:

- `<workbook>` root attributes and version mapping
- `<datasource>`, `<connection>`, `<relation>` structure
- `<column>` / `<calculation>` for fields and calculated fields
- `<metadata-records>` structure
- Parameters datasource conventions
- `<worksheet>` → `<table>` → `<view>` → shelf structure
- `<dashboard>` → `<zone>` layout model
- `<filter>` types and their XML representations

### 4.2 Phase 2: Automated Schema Discovery (Corpus Analysis)

Build tooling to **infer schema rules** from a corpus of real `.twb` files:

```python
class CorpusAnalyzer:
    """
    Analyzes many .twb files to build a probabilistic schema:
    - Which elements appear under which parents?
    - Which attributes are required vs optional?
    - What are the valid value sets for enum-like attributes?
    - What changed between Tableau versions?
    """
    def analyze(self, twb_paths: list[Path]) -> SchemaReport: ...
```

Sources for the corpus:
- Tableau Public workbooks (freely downloadable)
- Tableau's own sample workbooks (shipped with Desktop)
- User-contributed workbooks (with permission)

### 4.3 Phase 3: Controlled Differential Schema Building

The most reliable approach for specific operations:

1. Open a minimal workbook in Tableau Desktop
2. Make exactly ONE change (add a filter, change mark type, etc.)
3. Save as `.twb`
4. Diff the before/after XML
5. Record exactly which XML nodes that change touches
6. Codify that diff as a pytableau operation

This produces a **mapping: user action → XML mutations** that is version-pinned and testable.

### 4.4 Validation Engine

Every XML mutation in pytableau goes through a validation layer:

```python
class XMLSchemaEngine:
    def validate_element(self, tag, parent_tag, attributes, version) -> list[Issue]: ...
    def validate_workbook(self, tree: etree.ElementTree) -> list[Issue]: ...
    def is_compatible(self, tree: etree.ElementTree, target_version: str) -> bool: ...
```

Validation levels:
- **ERROR**: Will definitely produce a corrupt file (missing required element, wrong parent)
- **WARNING**: May work but could cause issues in some Tableau versions
- **INFO**: Unusual but valid (e.g., empty worksheet, unused datasource)

---

## 5. The Template Engine

The presentation layer (viz types, mark configurations, color encoding, dashboard layout) is too complex to generate from pure code for v1. The template engine is our pragmatic answer.

### 5.1 How It Works

```python
from pytableau import Workbook

# 1. Start from a template (created in Tableau Desktop)
wb = Workbook.from_template("bar_chart")  # built-in library
# OR
wb = Workbook.from_template("my_custom_template.twb")

# 2. Swap the data
wb.datasources["placeholder"].hyper.from_dataframe(my_df)

# 3. Map template field names → real field names
wb.template.map_field("__DIMENSION__", "Product Category")
wb.template.map_field("__MEASURE__", "Revenue")
wb.template.map_field("__COLOR__", "Region")

# 4. Override properties
wb.worksheets["Sheet 1"].mark_type = MarkType.BAR
wb.parameters["Title Text"].value = "Q4 Revenue by Category"

# 5. Save
wb.save_as("quarterly_report.twbx")
```

### 5.2 Template Conventions

Templates use placeholder names with double-underscore prefix:
- `__DIMENSION__`, `__MEASURE__`, `__DATE__`, `__COLOR__`, `__SIZE__`, etc.
- Parameter placeholders: `__PARAM_TITLE__`, `__PARAM_CUTOFF__`, etc.
- Data source named `__PLACEHOLDER_DS__`

The template engine performs bulk find-and-replace across all XML nodes, handling both field references in shelves and `[datasource].[field:qualifier]` format strings.

### 5.3 Built-in Template Library

Ship a small but useful set of pre-built templates covering common chart types:

| Template | Description | Placeholders |
|----------|-------------|-------------|
| `bar_chart` | Horizontal/vertical bars | `__DIMENSION__`, `__MEASURE__`, `__COLOR__` |
| `line_chart` | Time series line | `__DATE__`, `__MEASURE__`, `__COLOR__` |
| `scatter_plot` | X/Y scatter with size | `__X__`, `__Y__`, `__SIZE__`, `__COLOR__` |
| `heatmap` | Cross-tab with color | `__ROW__`, `__COL__`, `__VALUE__` |
| `treemap` | Hierarchical treemap | `__CATEGORY__`, `__SIZE__`, `__COLOR__` |
| `map` | Filled map | `__GEO__`, `__MEASURE__` |
| `kpi_dashboard` | Multi-KPI layout | `__KPI1__` through `__KPI4__`, `__DATE__` |

Templates are created in Tableau Desktop 2024.1+ (our minimum supported version for templates) and stored as `.twb` files in the package.

---

## 6. Development Phases

### Phase 0: Foundation (Weeks 1–2)
**Goal: Project scaffolding and packaging**

- [ ] Initialize repo structure (see Module Map above)
- [ ] Set up `pyproject.toml` with optional dependency groups
- [ ] Configure pytest, mypy, ruff
- [ ] Set up GitHub Actions CI (lint, type-check, test)
- [ ] Register `pytableau` name on PyPI (publish placeholder 0.0.1)
- [ ] Write `README.md` with vision statement and install instructions
- [ ] Implement `_compat.py` optional import helpers with clear error messages
- [ ] Implement `constants.py` with all enums (MarkType, DataType, Role, etc.)
- [ ] Implement `exceptions.py` with exception hierarchy

**Deliverable:** `pip install pytableau` works, imports cleanly, does nothing yet.

### Phase 1: Read & Inspect (Weeks 3–5)
**Goal: Read any .twb/.twbx and expose its contents programmatically**

- [ ] `PackageManager`: transparent .twbx ↔ temp dir handling
- [ ] `Workbook.open()`: parse .twb XML into object model
- [ ] `Datasource` read: connections, fields, calculated fields, parameters
- [ ] `Worksheet` read: shelves, filters, mark types, encodings
- [ ] `Dashboard` read: zones, layout, actions, sizes
- [ ] `inspect/catalog.py`: list all fields, calcs, connections in a workbook
- [ ] `inspect/lineage.py`: which calcs depend on which fields
- [ ] `inspect/report.py`: generate markdown documentation for a workbook
- [ ] CLI: `pytableau inspect workbook.twbx` → structured output
- [ ] Tests against Tableau sample workbooks (Superstore, etc.)

**Deliverable:** Full read-only introspection of any Tableau workbook. This alone is useful for documentation, auditing, and governance workflows.

### Phase 2: Connection & Field Mutation (Weeks 6–8)
**Goal: Programmatic edits to data sources and the semantic model**

- [ ] `Connection` mutation: swap server, database, username, connection type
- [ ] `Datasource.add_calculated_field()`: inject calcs with formula validation
- [ ] `Datasource.remove_field()`: clean removal from all references
- [ ] `Datasource.rename_field()`: cascade rename through all worksheets
- [ ] `Parameter` mutation: change value, range, domain type
- [ ] `Filter` mutation: add/remove/modify filters on worksheets
- [ ] `Workbook.save()` / `save_as()`: write back valid XML
- [ ] XML validation engine: catch corrupt mutations before save
- [ ] CLI: `pytableau swap workbook.twb --server NEW_SERVER --db NEW_DB`
- [ ] CLI: `pytableau diff before.twb after.twb` → semantic diff
- [ ] Tests: round-trip (open → mutate → save → reopen → verify)

**Deliverable:** Full CI/CD environment promotion workflows. Replace tableaudocumentapi for connection swapping PLUS add calc field management, parameter editing, and filter manipulation.

### Phase 3: Data Layer Integration (Weeks 9–11)
**Goal: Unified .hyper file management within workbooks**

- [ ] `HyperBridge`: wrap pantab + tableauhyperapi
- [ ] `Datasource.hyper.from_dataframe()`: inject DataFrame into .hyper
- [ ] `Datasource.hyper.to_dataframe()`: extract data back to DataFrame
- [ ] `Datasource.hyper.query()`: arbitrary SQL on .hyper
- [ ] `Datasource.hyper.schema()`: introspect tables and columns
- [ ] `data/types.py`: comprehensive type mapping (pandas ↔ Hyper ↔ Tableau XML)
- [ ] `data/extract.py`: create, attach, and refresh extracts within .twbx
- [ ] Auto-wire: when writing a DataFrame, auto-update XML metadata-records to match
- [ ] Tests: DataFrame → .hyper → .twbx → open in Tableau verification

**Deliverable:** One-liner data refresh: `wb.datasources["Sales"].hyper.from_dataframe(df); wb.save()`

### Phase 4: Template Engine (Weeks 12–15)
**Goal: Parameterized workbook generation from templates**

- [ ] `TemplateEngine`: field mapping, placeholder substitution
- [ ] `Workbook.from_template()`: construct from built-in or custom template
- [ ] Create 7 built-in templates (bar, line, scatter, heatmap, treemap, map, KPI)
- [ ] Template field convention: `__PLACEHOLDER__` naming
- [ ] Bulk field substitution across all XML nodes (shelves, filters, encodings, tooltips)
- [ ] Datasource replacement within templates
- [ ] Parameterized dashboard titles and text objects
- [ ] Tests: generate workbook from template → open in Tableau → verify viz renders

**Deliverable:** Programmatic report generation. "Give me a bar chart of this DataFrame, grouped by Region."

### Phase 5: Server Integration (Weeks 16–18)
**Goal: Full round-trip with Tableau Server/Cloud**

- [ ] `ServerClient`: wrap tableauserverclient with pytableau conventions
- [ ] `Workbook.publish()`: one-call publish to Server/Cloud
- [ ] `Workbook.download()`: download .twbx from Server
- [ ] `workflows.py`: high-level patterns (download → modify → republish)
- [ ] Auth: username/password, personal access token, connected apps (JWT)
- [ ] Bulk operations: swap connections across all workbooks in a project
- [ ] Tests: mock server tests + optional live integration tests (env-gated)

**Deliverable:** Full lifecycle automation. Download from Server, modify data + connections + fields, republish.

### Phase 6: Advanced Features (Weeks 19+)
**Goal: Power-user capabilities and ecosystem maturity**

- [ ] `Worksheet` shelf mutation: programmatically add fields to rows/cols/marks
- [ ] `Dashboard` layout mutation: add/remove/reposition zones
- [ ] `Action` creation: filter actions, URL actions, highlight actions
- [ ] Workbook merge: combine worksheets/dashboards from multiple workbooks
- [ ] Schema discovery tooling: corpus analyzer, controlled differ
- [ ] Version migration: convert workbook XML between Tableau versions
- [ ] Performance profiling: identify slow calcs, wide joins, excessive filters
- [ ] Documentation site (MkDocs or Sphinx)
- [ ] Cookbook / recipe collection for common workflows
- [ ] Community template submissions

---

## 7. API Quick Reference

### 7.1 Open, Inspect, Save

```python
from pytableau import Workbook

# Open
wb = Workbook.open("sales_dashboard.twbx")

# Inspect
print(wb.version)                        # "2024.1"
print(wb.datasources.names)              # ["Sales Data", "Parameters"]
print(wb.worksheets.names)               # ["Revenue by Region", "Trend"]
print(wb.dashboards.names)               # ["Executive Summary"]

# Catalog
catalog = wb.catalog()
for field in catalog.calculated_fields:
    print(f"{field.caption}: {field.formula}")

# Save
wb.save_as("modified.twbx")
```

### 7.2 Swap Connections

```python
from pytableau import Workbook

wb = Workbook.open("report.twbx")
for ds in wb.datasources:
    for conn in ds.connections:
        conn.server = "prod-db.corp.com"
        conn.dbname = "analytics_prod"
        conn.username = "svc_tableau"
wb.save_as("report_prod.twbx")
```

### 7.3 Manage Calculated Fields

```python
from pytableau import Workbook

wb = Workbook.open("report.twbx")
ds = wb.datasources["Sales Data"]

# Add
ds.add_calculated_field(
    caption="Profit Ratio",
    formula="SUM([Profit]) / SUM([Sales])",
    datatype="real",
    role="measure",
    default_format="p0%"
)

# Modify
ds.calculated_fields["Profit Ratio"].formula = "[Profit] / [Sales]"

# Remove
ds.remove_field("Obsolete Metric")

wb.save("report.twbx")
```

### 7.4 Inject Data

```python
from pytableau import Workbook
import pandas as pd

wb = Workbook.open("template.twbx")
df = pd.read_csv("fresh_data.csv")

wb.datasources["Sales Data"].hyper.from_dataframe(df)
wb.save_as("refreshed_report.twbx")
```

### 7.5 Generate from Template

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

### 7.6 Publish to Server

```python
from pytableau import Workbook

wb = Workbook.open("report.twbx")
wb.publish(
    server="https://tableau.corp.com",
    project="Marketing Analytics",
    token_name="my-pat",
    token_secret="xxxx-xxxx-xxxx"
)
```

### 7.7 Workbook Diff

```python
from pytableau import Workbook

before = Workbook.open("v1.twb")
after  = Workbook.open("v2.twb")
diff = before.diff(after)

print(diff.added_fields)       # Fields in v2 not in v1
print(diff.removed_fields)     # Fields in v1 not in v2
print(diff.changed_calcs)      # Calc fields with different formulas
print(diff.connection_changes)  # Connection property diffs
```

---

## 8. Testing Strategy

### 8.1 Test Pyramid

```
                    ┌──────────────┐
                    │  Integration │  Open in Tableau Desktop (manual, CI-optional)
                    ├──────────────┤
                ┌───┤  Round-trip  ├───┐  Open → mutate → save → reopen → assert
                │   ├──────────────┤   │
            ┌───┤   │  Functional  │   ├───┐  API-level: Workbook.open(), .save(), etc.
            │   │   ├──────────────┤   │   │
        ┌───┤   │   │    Unit      │   │   ├───┐  XML node manipulation, type mapping
        │   │   │   └──────────────┘   │   │   │
        └───┴───┴──────────────────────┴───┴───┘
```

### 8.2 Test Assets

- `tests/assets/` contains real `.twb` and `.twbx` files for testing
- Include Tableau's Superstore sample workbook (freely distributable)
- Generate minimal test workbooks in Desktop for specific feature tests
- Each Tableau version we support gets its own test workbook

### 8.3 Round-Trip Invariant

The most critical test pattern: any workbook that pytableau opens and saves without modification must be byte-level or semantically identical to the original. This catches accidental XML corruption.

```python
def test_roundtrip_identity(sample_workbook):
    """Opening and saving without changes should not corrupt the file."""
    wb = Workbook.open(sample_workbook)
    wb.save_as("roundtrip.twb")
    assert_xml_equivalent(sample_workbook, "roundtrip.twb")
```

### 8.4 Tableau Desktop Verification (Manual / CI-Optional)

For critical releases, we open generated `.twbx` files in Tableau Desktop to verify they render correctly. This can't be fully automated (Desktop has no headless mode), but we document the manual verification procedure and maintain a "verified workbook" set.

---

## 9. Packaging & Distribution

### 9.1 pyproject.toml (Key Sections)

```toml
[project]
name = "pytableau"
description = "The unified Python SDK for Tableau workbook engineering"
license = "MIT"
requires-python = ">=3.10"
dependencies = ["lxml>=4.9"]

[project.optional-dependencies]
hyper = ["tableauhyperapi>=0.0.19", "pantab>=5.0"]
pandas = ["pandas>=2.0"]
server = ["tableauserverclient>=0.30"]
all = ["pytableau[hyper,pandas,server]"]
dev = ["pytest", "mypy", "ruff", "pre-commit", "coverage"]

[project.scripts]
pytableau = "pytableau.cli.main:app"
```

### 9.2 Python Version Support

- **Minimum:** Python 3.10 (for `match` statements, union types `X | Y`, `ParamSpec`)
- **Tested:** 3.10, 3.11, 3.12, 3.13
- **Type-checked:** Full `py.typed` support, strict mypy configuration

### 9.3 Release Strategy

- Semantic versioning: `MAJOR.MINOR.PATCH`
- `0.x.y` during development (API may break between minors)
- `1.0.0` when Phase 3 (Data Layer) is stable and tested
- Publish to PyPI via GitHub Actions on tag push
- Changelog maintained in `CHANGELOG.md` (Keep-a-Changelog format)

---

## 10. Risks & Mitigations

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Tableau changes XML schema in new version | High | Certain (happens yearly) | Version-aware schema engine; test against multiple versions; schema discovery tooling |
| `tableauhyperapi` binary breaks on new OS/arch | Medium | Low | It's Salesforce-maintained; we just wrap it; pantab as fallback |
| Trademark challenge from Salesforce on "pytableau" name | Medium | Low-Medium | Name uses "py" prefix convention (like pytest, pyarrow); doesn't impersonate Tableau; pivot name ready if needed |
| Scope creep into full viz generation | High | Medium | Template engine is the pragmatic boundary; raw XML escape hatch for power users; resist the urge to reverse-engineer VizQL |
| Community adoption insufficient to sustain | Medium | Medium | Target real enterprise pain points (CI/CD, documentation, governance); ship useful read-only tools in Phase 1 |
| XML corruption goes undetected | Critical | Medium | Validation engine; round-trip tests; never save without validation pass |

---

## 11. Success Criteria

### 11.1 Phase 1 Success (Minimum Viable)
- [ ] `Workbook.open()` successfully parses 95%+ of real-world .twb/.twbx files
- [ ] `catalog()` output matches what Tableau Desktop shows
- [ ] Round-trip test passes for all sample workbooks
- [ ] 50+ GitHub stars within first month (measures discoverability)

### 11.2 Phase 3 Success (Compelling Product)
- [ ] One-command connection swap works for all common database types
- [ ] DataFrame → .twbx pipeline runs end-to-end in <10 lines of code
- [ ] calc field creation produces Tableau-valid XML
- [ ] 3+ external blog posts or conference mentions

### 11.3 v1.0 Success (Industry Standard)
- [ ] 500+ GitHub stars
- [ ] 10,000+ monthly PyPI downloads
- [ ] Used in at least 2 known enterprise CI/CD pipelines
- [ ] Template library covers 10+ chart types
- [ ] Community contributions to template library

---

## 12. Open Questions

1. **Minimum Tableau version support?** Proposal: 2022.1+ (version='18.1' XML). Older versions have significantly different XML schemas and diminishing user base.

2. **Should we vendor `tableaudocumentapi` source or start fresh?** Proposal: Start fresh, inspired by their patterns. Their codebase is small (~1500 lines), Python 3 only since 2021, and we need fundamentally different architecture (they don't support calc fields, filters, worksheets, dashboards).

3. **Template file format — `.twb` or custom `.pytab`?** Proposal: Plain `.twb` files. Users can create templates in Tableau Desktop (zero learning curve). The placeholder convention (`__FIELD__`) is the only pytableau-specific layer.

4. **CLI framework?** Proposal: `click` (lightweight, well-known). Could also use `typer` for auto-generated help. The CLI is secondary to the library API.

5. **Should the `inspect` module output structured data (dict/dataclass) or formatted strings?** Proposal: Both. `catalog()` returns dataclasses; `report()` returns formatted markdown. CLI renders either as table or JSON.

6. **How do we handle Tableau's `.tds` and `.tdsx` files?** Proposal: Phase 2 add-on. The `Datasource` class should be usable standalone (not just embedded in a Workbook). `Datasource.open("mydata.tds")` and `Datasource.save_as("mydata.tdsx")`.

---

## 13. References

### Upstream Libraries
- [tableau/document-api-python](https://github.com/tableau/document-api-python) — MIT, XML read/write (limited)
- [innobi/pantab](https://github.com/innobi/pantab) — BSD-3, DataFrame ↔ Hyper
- [tableauhyperapi](https://pypi.org/project/tableauhyperapi/) — Apache 2.0, official Hyper engine
- [tableau/server-client-python](https://github.com/tableau/server-client-python) — MIT, Server REST API
- [bryanthowell-tableau/tableau_tools](https://github.com/bryanthowell-tableau/tableau_tools) — REST API + XML (reference, not dependency)

### XML Schema Knowledge
- [ranvithm/tableau.xml](https://github.com/ranvithm/tableau.xml) — Community-documented TWB XML structure
- [cmtoomey/fully-documented-twb](https://gist.github.com/cmtoomey/96342ba07dd5cba6ecc6) — Annotated workbook XML
- [tableauandbehold.com](https://tableauandbehold.com/2016/06/29/how-tds-twb-files-work-xml/) — Deep dive on TDS/TWB XML
- [bitips.blog](https://bitips.blog/2023/09/01/unravel-tableau-workbook-structure-twb-twbx/) — TWB/TWBX structure guide
- [coenterprise.com](https://www.coenterprise.com/blog/uncovering-the-value-of-tableaus-workbook-xml-metadata/) — XML metadata analysis

### Design Inspiration
- [openpyxl](https://openpyxl.readthedocs.io/) — How they handle Excel's complex XML (similar problem domain)
- [python-pptx](https://python-pptx.readthedocs.io/) — Template-based approach to PowerPoint generation
- [pandas](https://pandas.pydata.org/) — API ergonomics and optional dependency patterns