# pytableau — PLAN.md

## The Unified Python SDK for Tableau Workbook Engineering

**Version:** 0.9.0 (released)
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
│   ├── datasource.py            # Datasource, Connection, Relation, MetadataRecord, Hierarchy, Set
│   ├── fields.py                # Field, CalculatedField, Parameter, Group, Set, Bin
│   ├── worksheet.py             # Worksheet, Shelf, MarkCard, Encoding
│   ├── dashboard.py             # Dashboard, Zone, Action, DeviceLayout
│   ├── filters.py               # CategoricalFilter, RangeFilter, RelativeDateFilter
│   └── formatting.py            # Style, ColorPalette, Font, Tooltip
│
├── xml/                         # XML engine
│   ├── engine.py                # XMLSchemaEngine: validation, version rules, unknown tag tracking
│   ├── proxy.py                 # XMLNodeProxy: safe mutation base class
│   ├── writer.py                # XML generation helpers
│   ├── differ.py                # Structural diff between two .twb XML trees
│   ├── rules.py                 # ValidationProfile + 10 built-in Rule classes [v0.6.0]
│   ├── fixers.py                # AutoFixer + 3 built-in fixers (bracket, credentials, whitespace) [v0.6.0]
│   ├── canonical.py             # Deterministic serialization for diffs [PLANNED]
│   ├── schemas/                 # Version-specific schema knowledge (v2022–v2025)
│   └── discovery/               # Schema reverse-engineering (corpus, controlled diff)
│
├── data/                        # Data layer (.hyper files)
│   ├── bridge.py                # HyperBridge: unified pantab + hyperapi wrapper
│   ├── types.py                 # Type mapping: pandas ↔ Hyper ↔ Tableau XML
│   └── extract.py               # Extract lifecycle (create, refresh, attach)
│
├── package/                     # .twbx/.tdsx packaging
│   ├── manager.py               # PackageManager: transparent .twbx ↔ temp dir, asset listing, path guard
│   ├── promotion.py             # PromotionConfig, EnvironmentSpec, PromotionChange [v0.6.0]
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
│   └── metadata.py              # Metadata API (GraphQL) [PLANNED]
│
├── inspect/                     # Read-only analysis & reporting
│   ├── catalog.py               # Field catalog, unused/orphaned detection, SQL/connection audit
│   ├── complexity.py            # ComplexityReport, grade A–F scoring [v0.6.0]
│   ├── lineage.py               # Field lineage: calculated field dependency graph
│   ├── report.py                # Generate markdown/HTML/PDF documentation
│   └── diff.py                  # Semantic diff between two workbooks
│
├── calculations/                # Formula parser & linter [PLANNED]
│   ├── parser.py                # lark-parser grammar for Tableau expressions
│   ├── ast.py                   # AST node definitions
│   ├── linter.py                # Lint rules engine
│   └── functions.py             # Tableau function registry (100+ functions)
│
├── governance/                  # Cross-workbook governance [PLANNED]
│   ├── index.py                 # WorkbookIndex (SQLite store)
│   ├── linter.py                # Configurable rules engine
│   └── scanner.py               # Sensitive data / credential detection
│
├── testing/                     # pytest plugin [PLANNED]
│   ├── plugin.py                # pytest-tableau plugin
│   └── assertions.py            # Workbook assertion helpers
│
├── cli/                         # Agent-ready CLI (tooli-powered)
│   └── main.py                  # 17 commands: inspect, validate, diff, catalog, lineage, report,
│                                #   swap-connection, rename-field, version-migrate, merge,
│                                #   template-list, template-apply, publish, download,
│                                #   complexity, auto-fix, promote [v0.6.0]
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

### ✅ v0.5.0 + v0.6.0: Hardening & Extended Model (COMPLETE — v0.6.0)
24 GitHub issues implemented across two milestone groups:

**Security & Hardening (#57–#66):**
- Hardened XML parser: `strict=`, `compatibility=` modes; entity/network resolution disabled
- Credential scrubbing: `Datasource.scrub_credentials()`, `save_as(scrub_credentials=True)` default
- Streaming mode: `Workbook.open(streaming=True)` with `LazyNotMaterializedError` sentinels
- `AmbiguousWorkbookError` + `twb_hint=` for multi-TWB archives
- `PackageManager`: `list_assets()`, `glob()`, `find()`, `data_dir`, `resolve()` path guard
- Deterministic ZIP: epoch timestamps, sorted entries, stripped volatile metadata
- `Datasource.open/save/save_as` for standalone `.tds` / `.tdsx` files
- 6 golden fixture `.twb` files + `canonicalize_twb()` round-trip harness

**Extended Read Model & Validation (#67–#80):**
- `Relation`: `join_type`, `left`, `right`, `on_clause`, `list_custom_sql()`
- `MetadataRecord` with lazy-cached `datasource.metadata_records`
- `Hierarchy`, `Set` parsing from drill-paths and group nodes
- `Dashboard.device_layouts`, `has_phone_layout` (devicelayouts support)
- `WorkbookCatalog`: `unused_fields()`, `unused_worksheets()`, `orphaned_calcs()`, `custom_sql_audit()`, `connection_audit()`
- `inspect/complexity.py`: `ComplexityReport`, grade A–F, `Workbook.complexity_report()`
- `xml/rules.py`: `ValidationProfile` + 10 built-in rules; `Workbook.validate(profile=)`
- `xml/fixers.py`: `AutoFixer`, `FixAction`, 3 built-in fixers; `Workbook.auto_fix(dry_run=)`
- Unknown XML tag tolerance: `info`-level issues, `engine.unknown_elements` tracking
- `package/promotion.py`: `PromotionConfig.from_dict/from_yaml`, `Workbook.promote()`
- Workbook-level `swap_connection(where=)` returning `SwapResult`
- `bulk_update_fields()`, `bulk_rename_fields()` on `Datasource`
- CLI: `complexity`, `auto-fix`, `promote` commands; `catalog --connections`

**Test count:** 297 passed, 10 skipped (was 219 before v0.7.0–v0.9.0)

---

## 5. Completed Milestones

### ✅ M6: Semantic Diff & Patch (v0.7.0) ⭐ NOVEL

*Git-friendly diffs and repeatable patches.*

- [x] **Canonical JSON serialization** (`xml/canonical.py`) — stable ordering, stripped volatile IDs
- [x] **Git normalization hook** (`git_clean()`) — strip Base64-encoded `<thumbnails>`, volatile attrs
- [x] **Semantic diff** (`inspect/diff.py`) — `WorkbookDiff`, `DatasourceDiff`, `FieldDiff`
- [x] **Diff output formats** — `to_text()`, `to_dict()`, `to_html()`
- [x] **Patch system** — `Patch`, `PatchOp`, `PatchAction`, `apply_patch()`
- [x] **CLI** — `diff`, `patch`, `git-clean`, `to-json` commands
- [x] **Structural XML diff** (`xml/differ.py`) — unified diff via difflib

### ✅ M7: Hyper Extract Management (v0.8.0)

- [x] **`HyperFile` wrapper** — context-managed; `list_tables()`, `schema()`, `row_count()`
- [x] **Bulk insert** — `bulk_insert(df, batch_size=10_000)`
- [x] **Incremental refresh** — rolling windows, upserts
- [x] **Extract contract tests** — `ExtractManager.contract_test(datasource)`
- [x] **`incremental_refresh()`** on `ExtractManager`

### ✅ M8: Template Engine Extensions (v0.8.0)

- [x] **`replace_datasource()`** on `TemplateEngine` — swap entire datasource node
- [x] **`save_as_template()`** on `Workbook` — replace captions with `__FIELDN__` placeholders
- [x] **Environment switch patterns** via datasource replacement

### ✅ M9: Formula Parser & Linter (v0.9.0) ⭐ NOVEL

*First open-source parser for Tableau's expression language.*

- [x] **`lark`-based grammar** (`calculations/parser.py`) — field refs, LOD, IF/CASE, 100+ functions
- [x] **AST node definitions** (`calculations/ast.py`) — `FieldRef`, `FuncCall`, `LodExpr`, etc.
- [x] **6 lint rules** (`calculations/linter.py`): UnknownFunction, ExcessiveLodNesting, NestedIf, DeprecatedFunction, UnknownFieldReference, CyclicDependency
- [x] **Function registry** (`calculations/functions.py`) — 100+ functions with deprecation status
- [x] **`lint_workbook()`** — lint all calculated fields across all datasources

### ✅ M10: Server Integration Extensions (v0.9.0)

- [x] **`list_workbooks()`**, **`refresh_extract()`** on `ServerClient`
- [x] **`publish_workbook_chunked()`** — auto-detect file size
- [x] **`detect_drift()`** — compare local connections to server metadata
- [x] **`MetadataClient`** (`server/metadata.py`) — GraphQL client for Tableau Metadata API
- [x] **`detect_drift_workflow()`** in `server/workflows.py`

---

## 6. Active & Upcoming Milestones

### Milestone 9: Server Integration Extensions (continued)

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

| Milestone | Version | Core Deliverable | Status |
|---|---|---|---|
| M0+ Foundation | v0.1.0 | Scaffolding, CI, enums, exceptions | ✅ Released |
| M1 Read & Inspect | v0.2.0 | Workbook.open, Datasource, Worksheet, Dashboard, CLI (14 cmds) | ✅ Released |
| M2 Mutation | v0.3.0 | Field/connection mutation, save/save_as, validation gate | ✅ Released |
| M3 Templates | v0.4.0 | TemplateEngine, 7 templates, tooli CLI migration | ✅ Released |
| M4 Hardening | v0.5.0 | Secure parsing, credential scrubbing, golden fixtures, .tds/.tdsx | ✅ Released |
| M5 Extended Model | v0.6.0 | Relations, MetadataRecords, hierarchies, device layouts, complexity, ValidationProfile, AutoFixer, promote | ✅ Released |
| M6 Diff & Patch | v0.7.0 | Git-friendly diffs, canonical JSON, patch system | 🔲 Next |
| M7 Extracts | v0.8.0 | DataFrame → .twbx with XML/Hyper schema sync | 🔲 Planned |
| M8 Templates+ | v0.8.0 | Template linting, custom templates, datasource swap | 🔲 Planned |
| M9 Formula Parser | v0.9.0 | lark-parser grammar, AST, lint rules, function registry | 🔲 Planned |
| M10 Server | v0.9.0 | Chunked publish, GraphQL metadata API, env promotion | 🔲 Planned |
| M11 Governance | v1.0.0 | WorkbookIndex, pytest plugin, accessibility, docs gen | 🔲 Planned |

**v1.0.0 success criteria:** 500+ GitHub stars, 10,000+ monthly PyPI downloads, used in 2+ enterprise CI/CD pipelines, template library covers 10+ chart types.

---

## 7. Top-5 Highest-ROI Immediate Tasks

1. **Canonical serialization + semantic diff** — unlocks governance, patching, reviewability, and long-term confidence in the SDK
2. **Complete datasource and relation parsing** — connections and table lineage are the #1 reason people automate Tableau files *(partially complete: relation tree, custom SQL, metadata records all landed in v0.6.0)*
3. **Robust formula parser (even a partial AST)** — current regex-based lineage works until it doesn't; even a token stream is a major improvement
4. **Extract attach/refresh that updates XML metadata** — Hyper I/O is already easy; making the workbook truly consistent after a write is the defensible moat
5. **Test fixtures across Tableau versions** — bugs will ship without this *(6 golden fixtures landed in v0.5.0; real-version corpus still needed)*

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
- `tests/fixtures/` — 6 synthetic `.twb` files across v2022.4–v2024.1 patterns (minimal, single-ds, multi-ds, parameters, LOD-heavy, dashboard-actions) ✅
- `tests/helpers.py` — `canonicalize_twb()` C14N round-trip helper ✅
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
