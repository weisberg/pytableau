# Combined Roadmap

*Synthesized from five independent deep-research efforts — Claude Opus, Gemini, ChatGPT, ChatGPT Pro Deep Think, and [Manus.ai](http://Manus.ai) — into a single implementation-ready plan.*

------

## Strategic Context

**The opportunity:** The Python-Tableau ecosystem is fragmented across 12+ libraries, none of which provide comprehensive, maintained access to Tableau workbook internals. The official `tableaudocumentapi` covers ~15% of `.twb` XML structure and hasn't been updated since 2022. `tableau_tools` declared its final version. **TabPy was archived December 2025.** No single library handles the full lifecycle of Tableau content.

**pytableau's thesis:** Own "local workbook = AST + diff + safe patch" as the defensible moat. Build a version-aware, testable, inspectable, patchable workbook abstract syntax tree for Tableau. Server support becomes an optional transport layer, not the SDK's identity.

**Novelty:** Across all five research sources, approximately **60% of proposed features are entirely novel** — not available in any existing open-source Python library. The remaining 40% exist but are scattered across stale or abandoned tools.

------

## Architecture & Engineering Principles

### Five-Layer Design

| Layer                      | Responsibility                                               | Dependencies                                                 |
| -------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| **L0 — Core XML & ZIP**    | Raw XML parsing (`lxml`), ZIP manipulation (`zipfile`), in-memory XML tree with full round-trip fidelity | `lxml` (required)                                            |
| **L1 — Object Model**      | `Workbook` → `Datasource` → `Field`, `Worksheet` → `Dashboard`; each object holds an `lxml.etree.Element` reference for write-through mutations | `pydantic` (required)                                        |
| **L2 — Data Layer**        | DataFrame ↔ Hyper conversion, `.hyper` file management within `.twbx` packages | `tableauhyperapi`, `pantab` (optional via `pip install pytableau[hyper]`) |
| **L3 — Server Layer**      | Workflow-oriented server operations wrapping `tableauserverclient` | `tableauserverclient` (optional via `pip install pytableau[server]`) |
| **L4 — Application Layer** | Docs generation, semantic diff, governance linting, performance analysis, lineage, templates, testing | `lark-parser`, `networkx`, `deepdiff`, `jinja2` (all optional) |

### Core Technical Decisions

- **`lxml`-based XML with full tree preservation** — follow the `python-pptx` pattern: maintain the complete `lxml` tree in memory, modify elements in-place. Every object holds a direct reference to its `lxml.etree.Element` so property setters write through immediately. This preserves unknown elements and guarantees round-trip fidelity. **Never use** `ElementTree` (loses namespaces), BeautifulSoup (imprecise for XML), or string substitution (fragile).
- **`pydantic` v2 for all data models** — runtime validation, JSON serialization, IDE-friendly type hints. Significant upgrade over Document API's raw XML element references.
- **Optional pip extras** — core installs only `lxml` + `pydantic`. `[hyper]` adds `tableauhyperapi` + `pantab`; `[server]` adds `tableauserverclient`; `[pandas]` adds pandas; `[analysis]` adds `lark-parser`, `networkx`, `deepdiff`; `[cli]` adds `click`.
- **Fail loud, fail early** — raise clear, descriptive custom exceptions (`TableauXMLParseError`, `TableauVersionNotSupportedException`) on invalid input or unexpected XML structures. Never silently produce corrupt output.
- **Version awareness** — parse the `version` attribute on `<workbook>` root. Build version profiles (e.g., `2022.1+`). Emit non-fatal warnings for unsupported versions rather than hard failures, since Tableau XML generally maintains backward compatibility.
- **Secure XML parsing defaults** — disable network/entity resolution, limit huge trees. Provide `strict` and `compatibility` modes. Automated credential scrubbing before save (strip `username`, `password`, `odbc-connect-string-extras` from `<connection>` nodes).
- **Golden fixture corpus** — `tests/fixtures/` with representative `.twb`/`.twbx` files across Tableau versions and workbook styles (multi-datasource, dashboards-heavy, extract-backed, custom SQL, LOD-heavy). This is the only reliable defense against XML schema drift and is **non-negotiable**.

### Recommended Package Structure

```
pytableau/
├── core/
│   ├── workbook.py           # Workbook class (entry point)
│   ├── worksheet.py          # Worksheet with shelves, marks, encodings
│   ├── dashboard.py          # Dashboard with zones and layout
│   ├── datasource.py         # Datasource with connections and fields
│   ├── connection.py         # Database connection properties
│   ├── field.py              # Field with metadata and calculations
│   ├── filter.py             # Categorical and quantitative filters
│   ├── parameter.py          # Parameter definitions
│   └── action.py             # Filter/highlight/URL actions
├── archive/
│   ├── package_manager.py    # .twbx/.tdsx ZIP read/write with asset index
│   └── path_resolver.py      # Relative path enforcement (prevent 403132)
├── hyper/
│   ├── hyper_bridge.py       # High-level .hyper operations
│   ├── schema.py             # Table/column definitions + type mapping
│   └── dataframe_bridge.py   # DataFrame ↔ Hyper via pantab
├── server/
│   ├── client.py             # REST API client (wraps TSC)
│   ├── metadata.py           # Metadata API (GraphQL)
│   └── webhooks.py           # Webhook management
├── analysis/
│   ├── diff.py               # Workbook structural diffing
│   ├── lineage.py            # Data lineage graph extraction
│   ├── optimizer.py          # Performance anti-pattern detection
│   ├── search.py             # Cross-workbook search/indexing
│   └── accessibility.py      # WCAG compliance checking
├── calculations/
│   ├── parser.py             # Lark-based formula parser
│   ├── ast.py                # AST node definitions
│   ├── linter.py             # Lint rules engine
│   └── functions.py          # Tableau function registry
├── testing/
│   ├── plugin.py             # pytest plugin
│   └── assertions.py         # Workbook assertion helpers
├── templates/
│   ├── generator.py          # Template-based workbook generation
│   └── chart_templates/      # Pre-built chart type templates
├── docs/
│   └── generator.py          # Auto-documentation from workbooks
├── governance/
│   ├── index.py              # WorkbookIndex (SQLite store)
│   ├── linter.py             # Configurable rules engine
│   └── scanner.py            # Sensitive data / credential detection
├── xml_utils/
│   ├── reader.py             # Namespace-aware XML reading
│   ├── writer.py             # Format-preserving XML writing
│   └── canonical.py          # Deterministic serialization for diffs
└── models/
    ├── types.py              # Enums: DataType, Role, FieldType, etc.
    └── base.py               # Base pydantic models
```

------

## Milestone 0 — Harden the Foundation (Weeks 1–2)

*No flashy features — prevents foundational bugs from propagating into later milestones.*

### Deliverables

- [ ]  **Version consistency** — fix version discrepancies (CLI vs `_version.py`); single source of truth via packaging tooling
- [ ]  **Optional dependency resilience** — robust `_MissingDependency` error messages with feature flags for `hyper`, `server`, `cli`, `analysis` extras
- [ ]  **Secure XML parsing defaults** — hardened `lxml` parsing (disable network/entity resolution, limit huge trees); `strict` mode rejects dangerous constructs, `compatibility` mode attempts best-effort loading with warnings
- [ ]  **Golden fixture corpus** — `tests/fixtures/` with `.twb`/`.twbx` files across ≥3 Tableau versions and ≥5 workbook patterns (multi-datasource, parameters, actions, extracts, custom SQL, LOD-heavy, dashboard-heavy)
- [ ]  **Round-trip test harness** — for each fixture: open → save → reopen → assert byte-equivalent XML (after canonical normalization)

### Technical Notes

- Use `lxml.etree.iterparse` for streaming, node-by-node DOM traversal to keep memory low on gigabyte-scale workbooks
- Custom exception hierarchy: `TableauXMLParseError`, `TableauVersionNotSupportedException`, `PackageCorruptionError`

------

## Milestone 1 — Industrial-Strength `.twbx` Support (Weeks 2–4)

`*PackageManager` must handle real corporate workbooks with multiple assets and extract files.*

### Deliverables

- [ ]  **Package index abstraction** — extend `PackageManager` into a filesystem abstraction with `root_dir`, `twb_path`, `data_dir` discovery, `find(path_like)`, `glob()`, `list_assets()`
- [ ]  **Deterministic repackaging** — stable ZIP ordering, preserved relative paths, stripped volatile metadata. Minimizes noisy diffs for source-control workflows
- [ ]  **Path normalization and asset mapping** — APIs for `resolve("Data/Extract.hyper")`, consistency rules for how connections reference on-disk assets
- [ ]  **Context manager semantics** — `with Workbook.open('file.twbx') as wb:` with guaranteed cleanup under exceptions
- [ ]  **Transparent archive handling** — `.twb` vs `.twbx` invisible to user; auto-detect, extract, and repackage

### Technical Notes

- `.twbx` is a standard ZIP archive. When repackaging, **strictly enforce relative paths** to prevent the Tableau Server `403132` error ("Failed to establish a connection to your datasource"). This error occurs when absolute local paths are hardcoded into the XML during re-zipping.
- Preserve caches, thumbnails, custom shapes, and images during repackaging
- Handle multiple `.twb` candidates inside a single archive; define resolution rules
- Support `.tds`/`.tdsx` with the same approach (`.tds` = single `<datasource>` element, `.tdsx` = ZIP wrapper)

------

## Milestone 2 — Complete Read Model (Weeks 4–9)

*Parse ~90% of TWB XML structure vs the Document API's ~15%. This is pytableau's core value proposition.*

### 2A. Core XML Parsing Engine (Weeks 4–5)

- [ ]  Namespace-aware XML reading with `lxml.etree.parse()`
- [ ]  Parse `<workbook>` root: `source-build`, `version` (schema version like `18.1`), `source-platform` (`win`/`mac`), `locale`
- [ ]  Build `Workbook` entry point with lazy population (worksheets, dashboards loaded on first access)

### 2B. Datasource & Connection Parsing (Weeks 5–6)

- [ ]  Parse all `<datasource>` elements into rich objects: connections, relations/joins (including recursive join trees for multi-table joins), column mappings, metadata records, extract definitions
- [ ]  **Connection details**: `class` (connector type — `excel-direct`, `sqlserver`, `postgres`, `snowflake`, `dataengine`), `server`, `port`, `dbname`, `username`, `filename`
- [ ]  **Relation parsing**: single tables, custom SQL (`<relation type='text'>`), and nested joins with ON clauses
- [ ]  **Connector-specific normalization**: `dbname` vs `dbName`, Snowflake warehouse/role fields, OAuth tokens
- [ ]  **Parameters**: special datasource `name='Parameters'` with `hasconnection='false'`; parse `param-domain-type` (`range`/`list`/`all`), `<range>` children, value lists

### 2C. Field & Calculation Extraction (Weeks 6–7)

- [ ]  Parse every `<column>` element with full metadata: `caption` (display name), `datatype` (`string`/`integer`/`real`/`datetime`/`date`/`boolean`), `name` (internal bracket form `[Calculation_XXXXXXXXXXXXXXXXXXX]`), `role` (`dimension`/`measure`), `type` (`nominal`/`ordinal`/`quantitative`), default format, semantic role
- [ ]  **Calculated fields**: identified by `<calculation>` child with `formula` attribute; formulas are plain text with XML entity encoding
- [ ]  **Metadata records**: `<remote-name>`, `<remote-type>` (numeric code), `<local-name>`, `<parent-name>`, `<local-type>`, `<aggregation>`, `<contains-null>`
- [ ]  **Hierarchies**: parse `<drill-paths>`
- [ ]  **Sets and groups**: parse group definitions and set computation rules

### 2D. Worksheet Parsing — **Entirely Novel** (Weeks 7–8)

*No existing Python library exposes worksheet internals.*

- [ ]  Parse `<worksheet>` elements: datasource references, `<datasource-dependencies>` (which fields from which source)
- [ ]  **Shelf contents**: `<rows>` and `<cols>` with fully-qualified field references (`[DataSourceName].[sum:Sales:qk]`)
- [ ]  **Mark type**: `<mark class='Bar'|'Line'|'Automatic'>` and encoding channels (size, color, detail, tooltip, LOD)
- [ ]  **Filters**: `<filter class='categorical'|'quantitative'>` with all filter configurations
- [ ]  **Sort definitions**, styles, panes/axes

### 2E. Dashboard Parsing — **Entirely Novel** (Weeks 8–9)

- [ ]  Parse `<dashboard>` elements: fixed `<size>` dimensions
- [ ]  **Zone layout hierarchy**: nested `<zone>` elements defining containers, worksheet placements, text objects, images, web pages, filter controls; zone positioning (`x`, `y`, `w`, `h`)
- [ ]  **Actions**: filter, highlight, URL actions with source/target sheet mapping
- [ ]  **Device layouts**: `<devicelayouts>` for responsive design (phone, tablet, desktop)

### 2F. Inspection & Documentation Utilities

- [ ]  **Workbook-wide metadata graph** — standardized JSON schema export: datasources, connections, tables/relations/custom SQL, all fields, worksheets (shelves/marks/filters), dashboards (zones/actions), extract attachments
- [ ]  **Fast search utilities**: `find_fields()`, `find_calculations()`, `find_custom_sql()`, `find_connections()`, `grep_xml(pattern)`
- [ ]  **Field catalog**: all fields with types, roles, formulas — output as table/DataFrame
- [ ]  **Data lineage DAG**: parse calculated field formulas, extract `[field]` bracket references using regex `\\[([^\\]]+)\\]`, build directed dependency graph: field → calc → worksheet → dashboard. Export as JSON, Mermaid, GraphViz DOT
- [ ]  **Unused field detection**: compare defined fields vs fields referenced in worksheets
- [ ]  **Unused worksheet detection**: compare all worksheets vs worksheets referenced in dashboards
- [ ]  **Orphaned calculated field detection**: find calcs not used in any worksheet or other calc
- [ ]  **Data source inventory**: summarize all datasources with connection types and field counts
- [ ]  **Connection string audit**: list all connection details for security review
- [ ]  **Custom SQL audit**: list all custom SQL queries with their datasource context
- [ ]  **Complexity scoring**: configurable weighted algorithm combining LOD count, nested calc depth, filter count per view, custom SQL usage, dashboard container depth, wide tables, file size components. Output scored reports with prioritized recommendations
- [ ]  **Report generation**: Markdown, JSON, HTML formats

------

## Milestone 3 — Validation Engine (Weeks 9–11)

*To safely mutate workbooks, validation is the "seatbelt."*

### Deliverables

- [ ]  **Two-layer validation**:
  - **Structural**: XML sanity, required nodes present, well-formed tree
  - **Semantic**: references resolve, no dangling field refs, connection attributes valid, filter targets exist
- [ ]  **Version profiles** (e.g., `2022.1+`, `2024.1+`) — versioned rulesets for the XML regions pytableau mutates
- [ ]  **Pluggable rule engine**: `Rule` objects returning `ValidationIssue(level, message, path)`
- [ ]  **Auto-fixers** for common issues: normalize connection attribute casing, normalize bracket formatting, strip credentials
- [ ]  **Unknown tag tolerance**: warn on unknown tags, do not error — preserve during round-trips
- [ ]  **Pre-save validation gate**: `wb.validate()` returns issues; errors block `save()`

------

## Milestone 4 — Mutation Primitives (Weeks 11–15)

### 4A. Connection Mutation (Weeks 11–12)

- [ ]  Swap `server`, `dbname`, `username`, `port`, `filename` on `<connection>` elements
- [ ]  **Environment promotion**: YAML/JSON-driven config mapping `dev → staging → prod` applied as a single function call
- [ ]  **Batch connection swap** across all datasources in a workbook
- [ ]  **Connection templating** with explicit "connection policy" files
- [ ]  Change connection type (e.g., live to extract)
- [ ]  Connector-specific attribute normalization

### 4B. Field & Semantic Model Mutation (Weeks 12–14)

*The most complex and valuable mutation feature set.*

- [ ]  Add, modify, remove **calculated fields** with formula
- [ ]  **Reference cascading** — the critical challenge: when a field is renamed or removed, update ALL bracket references in other formulas, shelf definitions (`[datasource].[field_name]`), filter elements, tooltip markup, and action configurations in a single atomic pass
- [ ]  Add/modify/remove **parameters** as first-class objects: domain type (list/range), values, formatting, show/hide, safe renaming
- [ ]  Add/modify/remove **filters** (categorical, range, relative-date, topN)
- [ ]  Change field roles (dimension/measure), types (nominal/ordinal/quantitative), default aggregation, number format
- [ ]  Hide/unhide fields, add field aliases
- [ ]  **Field metadata maintenance**: update captions/descriptions/folders/default formats at scale with crosschecks to `metadata-records`

### 4C. Packaging & File Operations (Weeks 14–15)

- [ ]  Save `.twb` and `.twbx` with format-preserving XML serialization
- [ ]  Convert `.twb` ↔ `.twbx` in both directions
- [ ]  Extract or replace `.hyper` files and image/shape assets within `.twbx`
- [ ]  Validate XML structural integrity before save
- [ ]  **Round-trip fidelity guarantee**: open → unmodified save produces semantically equivalent output

------

## Milestone 5 — Semantic Diff & Patch (Weeks 15–18)

*The feature that makes engineering teams adopt pytableau: Git-friendly diffs and repeatable patches.*

**Entirely novel — no existing Python library provides this.**

### Deliverables

- [ ]  **Canonical JSON serialization** of workbook model: stable ordering, stripped volatile IDs, normalized whitespace and brackets
- [ ]  **Git normalization hook** (`git_clean()`): strip Base64-encoded `<thumbnails>`, enforce alphabetical tag ordering of `<datasource>` and `<worksheet>` elements — eliminates version control bloat from Tableau's arbitrary tag reordering on save
- [ ]  **Structural diff** between two workbooks: recursively compare object models, matching elements by name/ID
- [ ]  **Semantic diff** (not just text diff): report added/removed/modified datasources, fields, calculations, worksheets, dashboards, filters, parameters, connections, actions
- [ ]  **Diff output formats**: human-readable text, JSON (machine-parseable), HTML
- [ ]  **Patch system**: `wb.diff(other) -> Patch`, `wb.apply(patch, validate=True)`
- [ ]  **CLI commands**: `pytableau diff a.twbx b.twbx --json`, `pytableau patch a.twbx changes.json`
- [ ]  **Changelog generation** between versions

### Technical Notes

- Use `deepdiff` for structural comparison with custom serialization of pytableau domain objects
- "Same logical workbook, different XML" is extremely common in Tableau — canonicalization is everything
- This enables Git hooks and CI/CD integration for Tableau content version control

------

## Milestone 6 — Hyper Extract Management (Weeks 18–22)

*Delegate, don't reinvent. The novel value is the glue between workbook XML and Hyper schema.*

### 6A. High-Level Hyper API Wrapper (Weeks 18–19)

- [ ]  `pytableau.hyper.HyperFile` — context-managed wrapper simplifying `HyperProcess` → `Connection` → operation → cleanup into a single entry point
- [ ]  Schema introspection: `list_tables()`, `get_schema()`
- [ ]  SQL queries returning Python objects
- [ ]  Bulk insert from iterables

### 6B. DataFrame Integration (Weeks 19–20)

- [ ]  `workbook.extract_data()` → DataFrame from embedded `.hyper` via `pantab.frame_from_hyper()`
- [ ]  `workbook.replace_data(df)` → swap extract data within `.twbx` via `pantab.frame_to_hyper()`
- [ ]  **Context manager bridge**: `with pytableau.Workbook('report.twbx') as wb:` → access `wb.data_frames` property backed by `pantab` → modified DataFrames written back on context exit
- [ ]  Multi-table extract support via `pantab.frames_to_hyper()`
- [ ]  **Type mapping layer**: comprehensive `pandas dtype ↔ Hyper type ↔ Tableau XML datatype` mapping table as an explicit, tested artifact

### 6C. Extract Lifecycle & XML Consistency (Weeks 20–22)

*The hardest local feature — and the one most libraries hand-wave.*

- [ ]  **Inject DataFrame into `.twbx`**: combine `pantab` for `.hyper` creation with packaging to inject a refreshed extract and **automatically synchronize** the workbook XML's `<column>` and `<metadata-records>` elements so Tableau recognizes the new schema
- [ ]  Extract provenance metadata: what DataFrame/table was written, when, row counts, schema hash
- [ ]  Legacy `.tde` detection and upgrade guidance
- [ ]  `datasource.extract.refresh_incremental(...)` patterns (rolling windows, upserts) via Hyper SQL
- [ ]  **Extract contract tests**: generate hyper → attach into `.twbx` → reopen → verify catalog consistency
- [ ]  `.tds`/`.tdsx` full read/write support including creating data source files from scratch

------

## Milestone 7 — Template Engine (Weeks 22–25)

### Deliverables

- [ ]  **Token-replacement strategy**: define placeholder field names in template workbooks (e.g., `[__PLACEHOLDER_DIMENSION__]`), use mutation infrastructure to replace throughout full XML tree. Safer than Jinja2-style XML templating which risks breaking XML structure
- [ ]  **Structured remapping**: map a field AND update its role, datatype, and default format simultaneously
- [ ]  **Template linting**: `validate_all_mapped` ensures all placeholders are fully resolved before save
- [ ]  **Built-in template library**: pre-built `.twb` templates for common chart types (bar, line, scatter, map, treemap, KPI dashboard) with field mapping recipes
- [ ]  **Custom template creation**: save any workbook as a reusable template
- [ ]  **Datasource replacement**: swap entire datasource definition in a template
- [ ]  **Environment switch patterns**: `dev → prod` as a template application
- [ ]  Test cases for each template across multiple Tableau versions

------

## Milestone 8 — Calculated Field Parser & Linter (Weeks 25–28)

### Deliverables

- [ ]  **`lark-parser` grammar** for Tableau's full expression language:
  - Field references: `[Field Name]`
  - LOD expressions: `{FIXED/INCLUDE/EXCLUDE [Dim] : SUM([Measure])}`
  - IF/THEN/ELSE/END and CASE/WHEN blocks
  - Function calls (100+ Tableau functions)
  - Table calculations
  - Operators with precedence
  - String/date/number/boolean literals and date literals (`#2023-01-01#`)
- [ ]  **AST node definitions** — clean abstract syntax tree for programmatic analysis
- [ ]  **Lint rules engine**:
  - Unused field references
  - Nested-IF anti-patterns (prefer CASE/WHEN)
  - Excessive LOD nesting depth
  - Deprecated function usage
  - Field reference validation against datasource schema
  - Cycle detection in calculation dependencies
- [ ]  **Tableau function registry**: all 100+ functions with signatures, return types, and deprecation status

### Technical Notes

- The `ts_migration` project uses ANTLR grammar to parse Tableau calculated fields — reference for grammar coverage
- Current regex-based lineage (`\\[([^\\]]+)\\]`) works until it doesn't — even a partial AST is a massive improvement for dependency graphs, refactoring safety, and calc linting
- **No parser exists** for Tableau's expression language in open source — this is a Very High novelty feature

------

## Milestone 9 — Server Integration (Weeks 28–34)

*Wrap TSC, don't rewrite it. Add workflow-level abstractions.*

### S1: Download & Upload as Transport (Weeks 28–30)

- [ ]  **Unified publish**: `wb.publish(server, project)` — auto-detect file size, monolithic POST under 64MB, chunked multipart above; inject `asJob=True` for async publication to prevent HTTP timeouts
- [ ]  **Unified download**: `Workbook.from_server(server, workbook_id)` — download, extract, and parse in one call
- [ ]  Authentication: username/password (`TSC.TableauAuth`), Personal Access Tokens (`TSC.PersonalAccessTokenAuth`), Connected Apps JWT
- [ ]  Multi-site support via `server.auth.switch_site()`

### S2: Metadata-Aware Workflows (Weeks 30–32)

- [ ]  **Metadata API integration**: typed GraphQL query builders for lineage queries via `server.metadata.query()`
- [ ]  **"Join local + server" mode**: compare a parsed `.twbx` against published workbook's server metadata to detect drift, broken extracts, or mismatched connections
- [ ]  **Batch operations**: bulk download, bulk inspect, bulk connection swap, bulk republish
- [ ]  **Governance gates**: refuse to publish if validation fails; publish with a change summary (diff report)
- [ ]  **Environment promotion workflow**: `promote_workbook(path, from_env, to_env)` handles download, connection swap, validation, and republish

### S3: Advanced Server Features (Weeks 32–34)

- [ ]  Webhook management helpers and event payload parsing (22 event types)
- [ ]  Bulk user provisioning from DataFrame with rate-limit backoff
- [ ]  **Admin Insights correlation**: merge server-side telemetry (viz load times, query tags) with local XML analysis to pinpoint which calculated fields or layouts cause warehouse slowdowns
- [ ]  Optional Migration SDK pipeline integration — pytableau as the transform layer

------

## Milestone 10 — Governance, Testing & Advanced Features (Weeks 34–42)

### 10A. Governance Mode — Lint, Inventory, Search (Weeks 34–36)

- [ ]  **`WorkbookIndex`** (SQLite): index multiple `.twb`/`.twbx` files storing workbook ID/path, version, datasources, connections, fields, calcs, actions
- [ ]  **Cross-workbook search**: "which workbooks use field `[Customer ID]`?", "which connect to database X?", "find all LOD expressions"
- [ ]  **Configurable linting engine**: naming conventions, insecure connection patterns (plain-text passwords), PII detection in calculated field formulas via regex, `SCRIPT_*` TabPy dependency auditing, unused fields, excessive complexity
- [ ]  **Pass/fail governance report** suitable for CI/CD gates
- [ ]  **CLI**: `pytableau index ./workbooks`, `pytableau search --field "Customer ID"`, `pytableau lint --ruleset corp.yml`

### 10B. Automated Testing Framework (Weeks 36–38)

- [ ]  **`pytest-tableau` plugin** with fixtures and assertion helpers:
  - `assert_field_exists(workbook, 'Profit Ratio')`
  - `assert_calculation_valid(workbook, 'Profit Ratio')`
  - `assert_dashboard_contains(workbook, 'Sales Dashboard', ['Revenue Chart', 'Trend Line'])`
  - `assert_no_live_connections(workbook)`
  - `assert_accessibility_compliant(workbook)`
- [ ]  **Workbook contract testing**: define expected structure in YAML/JSON, validate in CI

### 10C. Accessibility Compliance Checking (Weeks 38–39)

- [ ]  WCAG 2.2 AA checks against workbook XML:
  - Color palette contrast ratios (using `colormath` for WCAG 1.4.3)
  - Alt text presence on elements
  - Mark count per view (>1,000 triggers server-side rendering, breaking accessibility)
  - Filter type compatibility (screen-reader friendliness)
  - Dashboard tab/focus ordering (determined by XML node sequence)
- [ ]  Compliance reports with pass/fail status and remediation guidance

### 10D. Documentation Generation (Weeks 39–40)

- [ ]  Auto-generate comprehensive workbook documentation:
  - Data sources with connection details
  - Complete field catalog with types and calculations
  - Worksheet descriptions with shelf assignments
  - Dashboard compositions
  - Parameter definitions and filter configurations
  - Lineage diagrams
- [ ]  Output formats: Markdown, HTML, PDF
- [ ]  Custom templates via Jinja2 for organization-specific standards

### 10E. Advanced Workbook Operations (Weeks 40–42)

- [ ]  **Worksheet mutation**: programmatically add/remove fields on `<rows>`/`<cols>` shelves, change mark types — the most XML-schema-sensitive work
- [ ]  **Dashboard mutation**: reposition `<zone>` elements, add/remove actions, manage `<devicelayouts>`, flatten redundant nested layout containers
- [ ]  **Workbook merge**: combine worksheets from multiple workbooks, resolve datasource and field name conflicts
- [ ]  **Version migration**: transform XML elements between Tableau version-specific schemas (Very High complexity)
- [ ]  **Programmatic formatting**: inject corporate color palettes into `<preferences>`, global font-family swaps, conditional formatting generation

------

## Summary Timeline

| Milestone                        | Weeks | Core Deliverable                                             | Novelty   |
| -------------------------------- | ----- | ------------------------------------------------------------ | --------- |
| **M0 — Foundation**              | 1–2   | Golden fixtures, secure parsing, version hygiene             | —         |
| **M1 — `.twbx` Support**         | 2–4   | Industrial-strength package handling with relative-path enforcement | Medium    |
| **M2 — Complete Read Model**     | 4–9   | ~90% TWB XML coverage: datasources, fields, worksheets, dashboards, lineage, catalogs | High      |
| **M3 — Validation Engine**       | 9–11  | Structural + semantic validation with version profiles       | High      |
| **M4 — Mutation Primitives**     | 11–15 | Connection swap, field mutation with reference cascading, env promotion | High      |
| **M5 — Semantic Diff & Patch**   | 15–18 | Git-friendly workbook diffs, canonical serialization, patch system | Very High |
| **M6 — Extract Management**      | 18–22 | DataFrame → `.twbx` with XML/Hyper schema consistency        | High      |
| **M7 — Template Engine**         | 22–25 | Parameterized workbook generation with built-in template library | High      |
| **M8 — Formula Parser & Linter** | 25–28 | `lark-parser` grammar for Tableau expressions, lint rules engine | Very High |
| **M9 — Server Integration**      | 28–34 | TSC wrapper with workflow orchestration, metadata API, governance gates | Medium    |
| **M10 — Governance & Advanced**  | 34–42 | Cross-workbook search, pytest plugin, accessibility, docs gen, advanced mutations | Very High |

------

## Highest-ROI Immediate Tasks (Top 5)

1. **Canonical serialization + semantic diff** — unlocks governance, patching, reviewability, and long-term confidence in the SDK
2. **Complete datasource and relation parsing** — connections and table lineage are the #1 reason people automate Tableau files
3. **Robust formula parser (even a partial AST)** — current regex-based lineage works until it doesn't; even a token stream is a major improvement
4. **Extract attach/refresh that updates XML metadata** — Hyper I/O is already easy; making the workbook truly consistent after a write is the defensible moat
5. **Test fixtures across Tableau versions** — bugs will ship without this because the XML schema is unpredictable across versions

------

## Existing Ecosystem Reference

| Library               | Focus             | Stars  | Status              | pytableau Relationship                                   |
| --------------------- | ----------------- | ------ | ------------------- | -------------------------------------------------------- |
| `tableauserverclient` | REST API          | ~704   | ✅ Active (v0.40)    | Wrap as transport layer                                  |
| `tableauhyperapi`     | .hyper files      | N/A    | ✅ Active            | Authoritative backend for extracts                       |
| `pantab`              | DataFrame ↔ Hyper | 121    | ✅ Active            | Delegate DataFrame I/O                                   |
| `tableaudocumentapi`  | Workbook XML      | 355    | ⚠️ Abandoned (2022)  | Coverage reference only — **primary replacement target** |
| `tableau_tools`       | REST + Docs       | ~220   | ⚠️ Final version     | Reference for manipulation patterns                      |
| `TableauDesktopPy`    | Metadata          | N/A    | ⚠️ Inactive (2021)   | Reference for expected metadata                          |
| TabPy                 | Analytics ext.    | ~1,600 | ⚠️ Archived Dec 2025 | Audit for `SCRIPT_*` usage only                          |

------

> **Core thesis:** If pytableau stays focused on "local workbook = AST + diff + safe patch," it fills a real gap that neither the Document API nor ad-hoc scripts provide. Server support becomes an optional transport layer, not the SDK's identity. Each milestone delivers standalone value, and Phase 1 alone — comprehensive `.twb`/`.twbx` parsing — would make pytableau the most capable open-source Tableau file library ever built.