# pytableau — PLAN.md

## The Unified Python SDK for Tableau Workbook Engineering

**Version:** 0.4.1 (in progress)
**Author:** Brian
**License:** MIT
**Target PyPI name:** `pytableau`
**Target import:** `import pytableau`

---

## 1. Vision

`pytableau` is a single Python package that unifies every layer of Tableau workbook manipulation — data, connections, semantic model, presentation, packaging, and server lifecycle — behind one coherent, Pythonic API.

**The one-liner pitch:** *"What pandas did for tabular data, pytableau does for Tableau workbooks."*

**Core thesis:** Own "local workbook = AST + diff + safe patch" as the defensible moat. Build a version-aware, testable, inspectable, patchable workbook abstract syntax tree for Tableau. Server support is an optional transport layer, not the SDK's identity.

**The opportunity:** The Python-Tableau ecosystem is fragmented across 12+ libraries, none of which provide comprehensive, maintained access to Tableau workbook internals. The official `tableaudocumentapi` covers ~15% of `.twb` XML structure and hasn't been updated since 2022. `tableau_tools` declared its final version. **TabPy was archived December 2025.** No single library handles the full lifecycle of Tableau content. Approximately **60% of pytableau's planned features are entirely novel** — not available in any existing open-source Python library.

### 1.1 Existing Ecosystem

| Library | Focus | Status | pytableau Relationship |
|---|---|---|---|
| `tableauserverclient` | REST API | ✅ Active (v0.40) | Wrap as transport layer |
| `tableauhyperapi` | .hyper files | ✅ Active | Authoritative backend for extracts |
| `pantab` | DataFrame ↔ Hyper | ✅ Active | Delegate DataFrame I/O |
| `tableaudocumentapi` | Workbook XML | ⚠️ Abandoned (2022) | **Primary replacement target** (~15% coverage) |
| `tableau_tools` | REST + Docs | ⚠️ Final version | Reference for manipulation patterns |
| TabPy | Analytics ext. | ⚠️ Archived Dec 2025 | Audit for `SCRIPT_*` usage only |

### 1.2 Design Principles

1. **Layer cake, not monolith.** Each Tableau layer maps to a distinct internal submodule.
2. **Batteries included, escape hatches available.** Pythonic API covers 90% of use cases; raw `lxml` nodes available for power users.
3. **Template-first for presentation.** Build in Desktop, parameterize with pytableau.
4. **Fail loud, fail early.** Validate XML mutations before writing. A corrupt `.twb` that only errors in Desktop is the worst outcome.
5. **Dependency-light by default.** Core requires only `lxml`. All extras are optional.
6. **Version-aware.** Track Tableau Desktop version. Warn on incompatible XML.
7. **Secure defaults.** Disable network/entity resolution in XML parsing. Credential scrubbing before save.

---

## 2. Architecture

### 2.1 Five-Layer Design

| Layer | Responsibility | Dependencies |
|---|---|---|
| **L0 — Core XML & ZIP** | Raw XML parsing, ZIP manipulation, in-memory XML tree with full round-trip fidelity | `lxml` (required) |
| **L1 — Object Model** | `Workbook → Datasource → Field`, `Worksheet → Dashboard`; write-through mutations via `lxml` element references | `lxml` (required) |
| **L2 — Data Layer** | DataFrame ↔ Hyper conversion, `.hyper` file management within `.twbx` | `tableauhyperapi`, `pantab` (optional `[hyper]`) |
| **L3 — Server Layer** | Workflow-oriented server operations wrapping `tableauserverclient` | `tableauserverclient` (optional `[server]`) |
| **L4 — Application Layer** | Docs generation, semantic diff, governance linting, performance analysis, lineage, templates, testing | `lark-parser`, `networkx`, `deepdiff`, `jinja2` (optional `[analysis]`) |

### 2.2 Module Map

```
pytableau/
├── core/                        # Object model
│   ├── workbook.py              # Workbook: top-level entry point
│   ├── datasource.py            # Datasource, Connection, Relation
│   ├── fields.py                # Field, CalculatedField, Parameter, Group, Set, Bin
│   ├── worksheet.py             # Worksheet, Shelf, MarkCard, Encoding
│   ├── dashboard.py             # Dashboard, Zone, Action, DashboardObject
│   ├── filters.py               # CategoricalFilter, RangeFilter, RelativeDateFilter
│   └── formatting.py            # Style, ColorPalette, Font, Tooltip
│
├── xml/                         # XML engine
│   ├── engine.py                # XMLSchemaEngine: validation, version rules
│   ├── proxy.py                 # XMLNodeProxy: safe mutation base class
│   ├── writer.py                # XML generation helpers
│   ├── differ.py                # Structural diff between two .twb XML trees
│   ├── canonical.py             # Deterministic serialization for diffs [NEW]
│   ├── schemas/                 # Version-specific schema knowledge (v2022–v2025)
│   └── discovery/               # Schema reverse-engineering (corpus, controlled diff)
│
├── data/                        # Data layer (.hyper files)
│   ├── bridge.py                # HyperBridge: unified pantab + hyperapi wrapper
│   ├── types.py                 # Type mapping: pandas ↔ Hyper ↔ Tableau XML
│   └── extract.py               # Extract lifecycle (create, refresh, attach)
│
├── package/                     # .twbx/.tdsx packaging [EXTENDED]
│   ├── manager.py               # PackageManager: transparent .twbx ↔ temp dir
│   └── assets.py                # Image, shape, and asset handling
│
├── templates/                   # Template engine
│   ├── engine.py                # TemplateEngine: parameterized workbook generation
│   ├── mapping.py               # FieldMapping: placeholder → real field
│   └── library/                 # 7 built-in starter templates
│
├── server/                      # Tableau Server/Cloud integration
│   ├── client.py                # ServerClient: wraps tableauserverclient
│   ├── workflows.py             # High-level: publish, download, refresh, round-trip
│   └── metadata.py              # Metadata API (GraphQL) [NEW]
│
├── inspect/                     # Read-only analysis & reporting
│   ├── catalog.py               # List all fields, calcs, connections
│   ├── lineage.py               # Field lineage: calculated field dependency graph
│   ├── report.py                # Generate markdown/HTML/PDF documentation
│   └── diff.py                  # Semantic diff between two workbooks
│
├── calculations/                # Formula parser & linter [NEW]
│   ├── parser.py                # lark-parser grammar for Tableau expressions
│   ├── ast.py                   # AST node definitions
│   ├── linter.py                # Lint rules engine
│   └── functions.py             # Tableau function registry (100+ functions)
│
├── governance/                  # Cross-workbook governance [NEW]
│   ├── index.py                 # WorkbookIndex (SQLite store)
│   ├── linter.py                # Configurable rules engine
│   └── scanner.py               # Sensitive data / credential detection
│
├── testing/                     # pytest plugin [NEW]
│   ├── plugin.py                # pytest-tableau plugin
│   └── assertions.py            # Workbook assertion helpers
│
├── cli/                         # Agent-ready CLI (tooli-powered)
│   └── main.py                  # 14 commands: inspect, validate, diff, catalog, ...
│
├── exceptions.py                # Custom exception hierarchy
├── constants.py                 # Enums: MarkType, DataType, Role, FilterType, etc.
├── _compat.py                   # Optional dependency import helpers
└── _version.py                  # Version string
```

---

## 3. Dependency Strategy

```
pytableau (core)
├── Required: lxml (XML engine)
│
├── Optional extra [cli]:         tooli (agent-ready CLI)
├── Optional extra [hyper]:       tableauhyperapi + pantab
├── Optional extra [server]:      tableauserverclient
├── Optional extra [pandas]:      pandas
├── Optional extra [analysis]:    lark-parser, networkx, deepdiff, jinja2
└── Optional extra [all]:         everything above
```

---

## 4. Development Phases

### ✅ Phase 0: Foundation (COMPLETE — v0.1.0)
- Package scaffolding, pyproject.toml, CI, enums, exceptions, _compat

### ✅ Phase 1: Read & Inspect (COMPLETE)
- `Workbook.open()`, `PackageManager`, `Datasource`/`Worksheet`/`Dashboard` read model
- `inspect/catalog.py`, `inspect/lineage.py`, `inspect/report.py`
- CLI: `pytableau inspect`, `pytableau diff`, `pytableau validate`

### ✅ Phase 2: Connection & Field Mutation (COMPLETE)
- Connection mutation: swap server, database, username, connection type
- `Datasource.add_calculated_field()`, `rename_field()`, `remove_field()`
- Parameter and filter mutation
- `Workbook.save()` / `save_as()` with validation gate
- CLI: `pytableau swap-connection`, `pytableau rename-field`

### ✅ Phase 4: Template Engine (COMPLETE)
- `TemplateEngine`, `Workbook.from_template()`
- 7 built-in templates (bar, line, scatter, heatmap, treemap, map, KPI)
- CLI: `pytableau template-list`, `pytableau template-apply`

### ✅ Phase CLI: tooli Integration (COMPLETE — v0.4.0)
- Full 14-command CLI via tooli: inspect, validate, diff, catalog, lineage, report,
  swap-connection, rename-field, version-migrate, merge, template-list, template-apply,
  publish, download
- MCP server, --json output, dry-run, structured errors, agent help

---

## 5. Active & Upcoming Milestones

### Milestone 0+: Harden the Foundation

*Non-negotiable infrastructure — prevents bugs from propagating.*

- [ ] **Secure XML parsing** — harden `lxml` (disable network/entity resolution, limit huge trees); `strict` mode rejects dangerous constructs, `compatibility` mode loads with warnings
- [ ] **Credential scrubbing** — auto-strip `username`, `password`, `odbc-connect-string-extras` from `<connection>` nodes before save
- [ ] **Golden fixture corpus** — `tests/fixtures/` with `.twb`/`.twbx` files across ≥3 Tableau versions and ≥5 workbook patterns (multi-datasource, parameters, actions, extracts, LOD-heavy, dashboard-heavy)
- [ ] **Round-trip test harness** — for each fixture: open → save → reopen → assert byte-equivalent XML (canonical normalization)
- [ ] **`streaming parse`** — `lxml.etree.iterparse` for gigabyte-scale workbooks

---

### Milestone 1: Industrial-Strength `.twbx` Support

*PackageManager must handle real corporate workbooks with multiple assets.*

- [ ] **Package index abstraction** — `PackageManager.list_assets()`, `glob()`, `find(path_like)`, `data_dir` discovery
- [ ] **Deterministic repackaging** — stable ZIP ordering, preserved relative paths, stripped volatile metadata; minimizes noisy diffs for source-control workflows
- [ ] **Path normalization** — `resolve("Data/Extract.hyper")`, enforce relative paths to prevent Tableau Server error 403132
- [ ] **`.tds`/`.tdsx` full read/write** — `Datasource.open("mydata.tds")` and `Datasource.save_as("mydata.tdsx")`
- [ ] **Multiple `.twb` candidates** — resolution rules when archive contains >1 workbook file

---

### Milestone 2+: Extended Read Model

*Push from current ~60% to ~90% TWB XML coverage.*

- [ ] **Relation parsing** — joins, custom SQL (`<relation type='text'>`), recursive nested join trees with ON clauses
- [ ] **Metadata records** — `<remote-name>`, `<remote-type>`, `<local-name>`, `<aggregation>`, `<contains-null>`
- [ ] **Hierarchies, sets, groups** — `<drill-paths>`, group definitions, set computation rules
- [ ] **Dashboard device layouts** — `<devicelayouts>` for phone/tablet/desktop responsive design
- [ ] **Unused field detection** — fields defined but not referenced in any worksheet
- [ ] **Unused worksheet detection** — worksheets not referenced in any dashboard
- [ ] **Orphaned calculated field detection** — calcs unused in any worksheet or other calc
- [ ] **Custom SQL audit** — list all custom SQL queries with datasource context
- [ ] **Complexity scoring** — configurable weighted algorithm: LOD count, nested calc depth, filter count, custom SQL, dashboard container depth; scored reports with recommendations
- [ ] **Connection string audit** — list all connection details for security review

---

### Milestone 3+: Validation Engine Improvements

- [ ] **Pluggable rule engine** — `Rule` objects returning `ValidationIssue(level, message, path)` with version profiles
- [ ] **Auto-fixers** — normalize connection attribute casing, bracket formatting, strip credentials
- [ ] **Unknown tag tolerance** — warn, do not error; preserve unknown tags during round-trips

---

### Milestone 4+: Mutation Improvements

- [ ] **Environment promotion** — YAML/JSON-driven config mapping `dev → staging → prod` applied as a single function call
- [ ] **Batch connection swap** — across all datasources in a workbook in one call
- [ ] **Field metadata bulk maintenance** — update captions, descriptions, folders, default formats at scale with `metadata-records` crosschecks

---

### Milestone 5: Semantic Diff & Patch ⭐ NOVEL

*The feature that makes engineering teams adopt pytableau: Git-friendly diffs and repeatable patches. No existing Python library provides this.*

- [ ] **Canonical JSON serialization** — stable ordering, stripped volatile IDs, normalized whitespace and brackets
- [ ] **Git normalization hook** (`git_clean()`) — strip Base64-encoded `<thumbnails>`, enforce alphabetical tag ordering; eliminates VCS bloat from Tableau's arbitrary tag reordering on save
- [ ] **Semantic diff** — recursively compare object models: report added/removed/modified datasources, fields, calculations, worksheets, dashboards, filters, parameters, connections, actions
- [ ] **Diff output formats** — human-readable text, JSON (machine-parseable), HTML
- [ ] **Patch system** — `wb.diff(other) → Patch`, `wb.apply(patch, validate=True)`
- [ ] **CLI** — `pytableau diff a.twbx b.twbx --json`, `pytableau patch a.twbx changes.json`
- [ ] **Changelog generation** between workbook versions

---

### Milestone 6: Hyper Extract Management

- [ ] **`HyperFile` wrapper** — context-managed `HyperProcess → Connection → operation → cleanup`; `list_tables()`, `get_schema()`, bulk insert from iterables
- [ ] **DataFrame → `.twbx` with XML sync** — inject refreshed extract AND automatically synchronize `<column>` and `<metadata-records>` elements so Tableau recognizes the new schema
- [ ] **Extract provenance metadata** — what DataFrame was written, when, row counts, schema hash
- [ ] **Incremental refresh patterns** — rolling windows, upserts via Hyper SQL
- [ ] **Extract contract tests** — generate hyper → attach into `.twbx` → reopen → verify catalog consistency

---

### Milestone 7+: Template Engine Extensions

- [ ] **Template linting** — `validate_all_mapped` ensures all placeholders resolved before save
- [ ] **Custom template creation** — `wb.save_as_template("my_template.twb")`
- [ ] **Datasource replacement** — swap entire datasource definition in a template
- [ ] **Environment switch patterns** — `dev → prod` as template application

---

### Milestone 8: Calculated Field Parser & Linter ⭐ NOVEL

*No parser exists for Tableau's expression language in open source.*

- [ ] **`lark-parser` grammar** for Tableau's full expression language: field references `[Field]`, LOD expressions `{FIXED/INCLUDE/EXCLUDE}`, IF/THEN/ELSE/CASE/WHEN, 100+ function calls, table calculations, date literals `#2023-01-01#`
- [ ] **AST node definitions** — clean abstract syntax tree for programmatic analysis
- [ ] **Lint rules engine**:
  - Unused field references
  - Nested-IF anti-patterns (prefer CASE/WHEN)
  - Excessive LOD nesting depth
  - Deprecated function usage
  - Field reference validation against datasource schema
  - **Cycle detection** in calculation dependencies
- [ ] **Tableau function registry** — all 100+ functions with signatures, return types, deprecation status

---

### Milestone 9: Server Integration Extensions

- [ ] **Unified publish** — auto-detect file size; monolithic POST under 64MB, chunked multipart above; `asJob=True` for async to prevent HTTP timeouts
- [ ] **Metadata API (GraphQL)** — typed query builders for lineage queries via `server.metadata.query()`
- [ ] **Local-vs-server drift detection** — compare parsed `.twbx` against published workbook's server metadata; detect broken extracts or mismatched connections
- [ ] **Environment promotion workflow** — `promote_workbook(path, from_env, to_env)`: download → connection swap → validate → republish
- [ ] **Webhook management** — helpers for all 22 event types + payload parsing
- [ ] **Admin Insights correlation** — merge server-side telemetry (viz load times, query tags) with local XML analysis to pinpoint which calculated fields cause warehouse slowdowns

---

### Milestone 10: Governance, Testing & Advanced Features ⭐ NOVEL

#### 10A. Governance & Cross-Workbook Search
- [ ] **`WorkbookIndex`** (SQLite) — index multiple `.twb`/`.twbx` files; cross-workbook search: "which workbooks use `[Customer ID]`?", "which connect to database X?", "find all LOD expressions"
- [ ] **Configurable linting engine** — naming conventions, insecure connection patterns (plain-text passwords), PII detection in calc formulas via regex, `SCRIPT_*` TabPy dependency auditing, unused fields, excessive complexity
- [ ] **CI/CD governance gate** — pass/fail report suitable for pipeline integration
- [ ] **CLI** — `pytableau index ./workbooks`, `pytableau search --field "Customer ID"`, `pytableau lint --ruleset corp.yml`

#### 10B. pytest-tableau Plugin
- [ ] **`pytest-tableau`** plugin with fixtures and assertion helpers:
  - `assert_field_exists(workbook, 'Profit Ratio')`
  - `assert_calculation_valid(workbook, 'Profit Ratio')`
  - `assert_dashboard_contains(workbook, 'Sales Dashboard', ['Revenue Chart'])`
  - `assert_no_live_connections(workbook)`
  - `assert_accessibility_compliant(workbook)`
- [ ] **Workbook contract testing** — define expected structure in YAML/JSON, validate in CI

#### 10C. Accessibility Compliance
- [ ] **WCAG 2.2 AA checks** — color palette contrast ratios, alt text presence, mark count per view (>1,000 breaks accessibility), filter type compatibility, dashboard tab/focus ordering
- [ ] **Compliance reports** with pass/fail status and remediation guidance

#### 10D. Documentation Generation
- [ ] **Auto-generate workbook docs** — data sources, field catalog, worksheet descriptions, dashboard compositions, parameter definitions, lineage diagrams
- [ ] **Output formats** — Markdown, HTML, PDF
- [ ] **Custom templates** via Jinja2 for organization-specific standards

#### 10E. Advanced Workbook Mutations
- [ ] **Worksheet shelf mutation** — add/remove fields on `<rows>`/`<cols>` shelves, change mark types
- [ ] **Dashboard mutation** — reposition `<zone>` elements, add/remove actions, manage `<devicelayouts>`, flatten redundant nested layout containers
- [ ] **Programmatic formatting** — inject corporate color palettes into `<preferences>`, global font-family swaps, conditional formatting generation

---

## 6. Release Roadmap

| Milestone | Target Version | Core Deliverable | Novelty |
|---|---|---|---|
| M0+ Foundation | v0.5.0 | Secure parsing, credential scrubbing, golden fixtures | — |
| M1 .twbx | v0.5.0 | Industrial-strength packaging, .tds/.tdsx support | Medium |
| M2+ Read Model | v0.6.0 | ~90% TWB XML: relations, metadata records, complexity scoring | High |
| M3+ Validation | v0.6.0 | Pluggable rules, auto-fixers, unknown tag tolerance | High |
| M4+ Mutation | v0.6.0 | Env promotion, batch ops, metadata maintenance | High |
| M5 Diff & Patch | v0.7.0 | Git-friendly diffs, canonical JSON, patch system | **Very High** |
| M6 Extracts | v0.8.0 | DataFrame → .twbx with XML/Hyper schema sync | High |
| M7+ Templates | v0.8.0 | Template linting, custom templates, datasource swap | High |
| M8 Formula Parser | v0.9.0 | lark-parser grammar, AST, lint rules, function registry | **Very High** |
| M9 Server | v0.9.0 | Chunked publish, GraphQL metadata API, env promotion | Medium |
| M10 Governance | v1.0.0 | WorkbookIndex, pytest plugin, accessibility, docs gen | **Very High** |

**v1.0.0 success criteria:** 500+ GitHub stars, 10,000+ monthly PyPI downloads, used in 2+ enterprise CI/CD pipelines, template library covers 10+ chart types.

---

## 7. Top-5 Highest-ROI Immediate Tasks

1. **Canonical serialization + semantic diff** — unlocks governance, patching, reviewability, and long-term confidence in the SDK
2. **Complete datasource and relation parsing** — connections and table lineage are the #1 reason people automate Tableau files
3. **Robust formula parser (even a partial AST)** — current regex-based lineage works until it doesn't; even a token stream is a major improvement
4. **Extract attach/refresh that updates XML metadata** — Hyper I/O is already easy; making the workbook truly consistent after a write is the defensible moat
5. **Test fixtures across Tableau versions** — bugs will ship without this because the XML schema is unpredictable across versions

---

## 8. Testing Strategy

### Test Pyramid
```
                    ┌──────────────┐
                    │  Integration │  Open in Tableau Desktop (manual / CI-optional)
                    ├──────────────┤
                ┌───┤  Round-trip  ├───┐  Open → mutate → save → reopen → assert
                │   ├──────────────┤   │
            ┌───┤   │  Functional  │   ├───┐  API-level tests
            │   │   ├──────────────┤   │   │
        ┌───┤   │   │    Unit      │   │   ├───┐  XML node manipulation, type mapping
        └───┴───┴──────────────────┴───┴───┘
```

### Round-Trip Invariant
Any workbook pytableau opens and saves without modification must be byte-level or semantically identical to the original. This is the primary defense against accidental XML corruption.

### Test Assets
- `tests/fixtures/` — real `.twb`/`.twbx` files across ≥3 Tableau versions (to be populated)
- `sample_workbook.twbx` — real Premier League stats workbook (local only, gitignored)
- `sample_workbook_fungible.twbx` — mutation test copy (local only, gitignored)

---

## 9. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Tableau changes XML schema in new version | High | Version-aware schema engine; test against multiple versions; schema discovery tooling |
| `tableauhyperapi` binary breaks on new OS/arch | Medium | Salesforce-maintained; we just wrap it; pantab as fallback |
| Trademark challenge on "pytableau" name | Medium | "py" prefix convention; pivot name ready if needed |
| Scope creep into full viz generation | High | Template engine is the pragmatic boundary; raw XML escape hatch for power users |
| XML corruption goes undetected | Critical | Validation engine; round-trip tests; never save without validation pass |

---

## 10. References

### Upstream Libraries
- [tableau/document-api-python](https://github.com/tableau/document-api-python) — MIT, XML read/write (limited, abandoned)
- [innobi/pantab](https://github.com/innobi/pantab) — BSD-3, DataFrame ↔ Hyper
- [tableauhyperapi](https://pypi.org/project/tableauhyperapi/) — Apache 2.0, official Hyper engine
- [tableau/server-client-python](https://github.com/tableau/server-client-python) — MIT, Server REST API

### XML Schema Knowledge
- [ranvithm/tableau.xml](https://github.com/ranvithm/tableau.xml) — Community-documented TWB XML structure
- [cmtoomey/fully-documented-twb](https://gist.github.com/cmtoomey/96342ba07dd5cba6ecc6) — Annotated workbook XML
- [tableauandbehold.com](https://tableauandbehold.com/2016/06/29/how-tds-twb-files-work-xml/) — Deep dive on TDS/TWB XML

### Design Inspiration
- [python-pptx](https://python-pptx.readthedocs.io/) — Template-based approach to Office XML (same problem domain)
- [openpyxl](https://openpyxl.readthedocs.io/) — How they handle Excel's complex XML
- [pandas](https://pandas.pydata.org/) — API ergonomics and optional dependency patterns
