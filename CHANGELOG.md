# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] — 2026-02-24

### Added

#### Programmatic Viz Authoring (`build/`)
- `DatasourceBuilder`, `WorksheetBuilder`, `DashboardBuilder` — fluent APIs for building workbooks entirely from code.
- `from_spec()` — load a full workbook from a Python dict, YAML file, or JSON file.
- `quick_chart()`, `quick_dashboard()` — one-liner shortcuts for common chart types.
- `Theme` — apply font families and color palettes programmatically.
- `Workbook.add_worksheet()` and `Workbook.add_dashboard()` — accept builder instances or raw lxml elements.
- `Workbook.from_spec()` — classmethod alias for `pytableau.build.from_spec()`.

#### Agent Ergonomics (`agents/`)
- `wb.describe()` — structured workbook schema as a JSON-safe dict, ready to pass to an LLM or automation layer.
- `wb.capabilities()` — installed extras + content summary (counts of fields, sheets, etc.).
- `wb.transaction()` — atomic multi-step mutations with automatic XML rollback on any exception.
- `ds.available_fields()` — flat field list for agents and automation pipelines.
- `OperationReceipt` — structured mutation result with `status`, `field_name`, `datasource`, `suggestion`, and `.ok` property.
- `PyTableauError.suggestion` — corrective hints propagated across the full exception hierarchy; `FieldNotFoundError` now suggests close-match field names.

#### Fleet Operations (`fleet/`)
- `FleetScanner` — scan hundreds of workbooks in one pass: complexity grade, connection inventory, deprecated function detection, lint issues.
- `WorkbookScan` — per-workbook result dataclass (path, status, complexity_grade, issue counts, etc.).
- `MigrationPlan` — fluent builder for bulk migrations: `swap_connections()`, `rename_fields()`, `validate_all()`.
- `MigrationEngine` — execute a `MigrationPlan` with full dry-run support; returns `MigrationReport`.
- `ComplianceRunner` — run a `GovernanceRuleset` against an entire directory; exports JUnit XML for CI/CD.
- `ContractRunner` — validate workbooks against YAML contract files (required datasources, worksheets, dashboards, formulas); exports JUnit XML.
- `FleetReport` — standalone HTML fleet health dashboard with summary cards, issue table, and per-workbook detail.
- CLI commands: `pytableau fleet-scan`, `pytableau comply`, `pytableau migrate`, `pytableau contract-test`.

#### Polish
- `Workbook.audit_connections()` — returns all connection strings (server, dbname, username, port) without passwords, for security review.
- `WorkbookDiff.to_changelog()` — render any semantic diff as Keep-a-Changelog Markdown (Added / Changed / Removed sections).
- `Datasource.upsert_extract()` — incremental extract refresh via DELETE+INSERT pattern; delegates to `ExtractManager.upsert()`.
- `Workbook.apply_theme()` — write a `Theme` object into the workbook's `<preferences>` XML node.

### Changed
- **BREAKING**: Minimum Python version raised to 3.11 (Python 3.10 dropped).
- **BREAKING**: `pytableau.exceptions.ConnectionError` renamed to `TableauConnectionError` (backwards-compat alias retained for one major cycle).
- `WorkbookDiff._diff_datasource` now uses `ds.all_fields` instead of `ds.fields` so calculated fields appear in diffs and changelogs.
- Development status classifier updated to `5 - Production/Stable`.
- `[build]` optional extra added (`pyyaml>=6.0`) for YAML spec support.
- `[all]` extra now includes `build`.
- 56 GitHub issues closed across v1.0.0 through v2.0.0.

### Migration from v1.x
- Replace `from pytableau.exceptions import ConnectionError` with `from pytableau.exceptions import TableauConnectionError`.
- Ensure Python ≥ 3.11 is installed.

---

## [2.0.0a2] — 2026-02-24

### Added
- `agents/` package: `describe()`, `available_fields()`, `capabilities()`, `WorkbookTransaction`, `OperationReceipt`.
- `PyTableauError.suggestion` field with close-match hints on `FieldNotFoundError`.

---

## [2.0.0a1] — 2026-02-24

### Added
- `pytableau.build` — Programmatic viz authoring: `DatasourceBuilder`, `WorksheetBuilder`, `DashboardBuilder`, `from_spec()`, `quick_chart()`, `quick_dashboard()`, `Theme` (Pillar III).
- `Workbook.add_worksheet()` and `Workbook.add_dashboard()` — Accept builder instances or raw lxml elements.
- `Workbook.from_spec()` — Classmethod alias for `pytableau.build.spec.from_spec()`.
- `[build]` optional extra: `pip install "pytableau[build]"` for YAML spec support.

### Changed
- **BREAKING**: Minimum Python version raised to 3.11.
- **BREAKING**: `pytableau.exceptions.ConnectionError` renamed to `TableauConnectionError` (backwards-compat alias retained for one major cycle).
- Version bumped to `2.0.0a1` (alpha 1 of v2.0).
- Development status classifier updated to Beta.

### Migration from v1.0
- Replace `from pytableau.exceptions import ConnectionError` with `from pytableau.exceptions import TableauConnectionError`.
- Ensure Python ≥ 3.11 is installed.

## [1.0.0] — 2026-02-23

### Added
- `governance` optional extra (`pyyaml>=6.0`) and `pytableau.governance` package with SQLite-backed workbook index and configurable lint rules
- `testing` optional extra (`pytest>=8.0`) and `pytableau.testing` package with pytest plugin, fixtures, and assertion helpers (`pytest11` entry point)
- Three new built-in templates: `stacked_bar`, `dual_axis`, `area_chart` (10 built-in templates total)
- Full implementations for three previously-stubbed modules: `xml/writer.py` (`to_string`, `write`, `indent`), `core/formatting.py` (`Color`, `Font`, `ColorPalette`, `FormatSpec`), `package/assets.py` (`list_assets`, `extract_asset`, `add_asset`)
- CHANGELOG.md (this file)

### Changed
- Version bumped to `1.0.0`
- Development Status classifier: `2 - Pre-Alpha` → `5 - Production/Stable`
- GitHub URLs corrected from `brianlwb/pytableau` → `weisberg/pytableau`
- `all` extra now includes `governance` and `testing`
- `dev` extra now includes `pyyaml>=6.0`
- MkDocs nav updated with Governance and Testing Plugin API sections

---

## [0.9.0] — 2026-01-15

### Added
- `calculations/` package: Lark-based formula parser, AST node types, 100+ built-in function registry, 6 lint rules (`NullComparison`, `HardcodedCredential`, `DivisionByZero`, etc.)
- `server/` extensions: `MetadataClient` for GraphQL Metadata API queries
- CLI commands: `formula-lint`, `formula-parse`, `server-list`, `diff`, `patch`, `git-clean`, `to-json`

### Changed
- Version bumped to `0.9.0`

---

## [0.8.0] — 2025-12-01

### Added
- `data/` package: `HyperFile` bridge wrapping `tableauhyperapi` + `pantab`; `ExtractManager` for create/append/refresh workflows
- `templates/` engine: `TemplateEngine`, `TemplateMapping`, `save_as_template`, `replace_datasource`
- `package/promotion.py`: `PromotionConfig`, `EnvironmentSpec`, `PromotionChange` for environment-to-environment workbook promotion
- CLI commands: `template-list`, `template-apply`, `promote`

### Changed
- Version bumped to `0.8.0`
- `hyper` optional extra added (`tableauhyperapi>=0.0.19`, `pantab>=5.0`)

---

## [0.7.0] — 2025-10-15

### Added
- `xml/canonical.py`: `git_clean()` for VCS-friendly diffs; canonical JSON serialisation
- `inspect/diff.py`: `WorkbookDiff`, `WorkbookPatch`, semantic diff/patch API
- `xml/differ.py`: low-level unified-diff wrapper for raw `.twb` comparison

### Changed
- Version bumped to `0.7.0`

---

## [0.6.0] — 2025-08-20

### Added
- `xml/rules.py`: `ValidationProfile`, 10 built-in `Rule` classes for workbook linting
- `xml/fixers.py`: `AutoFixer`, `FixAction`, 3 built-in fixers (`_ALL_FIXERS`)
- `inspect/complexity.py`: `ComplexityConfig`, `ComplexityReport`, `analyze_complexity()`
- CLI commands: `auto-fix`, `complexity`

### Changed
- Version bumped to `0.6.0`

---

## [0.5.0] — 2025-06-10

### Added
- `server/` package: `ServerClient` wrapping `tableauserverclient`; `publish`, `download`, `list_workbooks` workflows
- `inspect/` package: `WorkbookCatalog`, `FieldLineage` (networkx graph), `WorkbookReport` (markdown)
- CLI commands: `catalog`, `lineage`, `report`, `publish`, `download`, `server-list`

### Changed
- Version bumped to `0.5.0`
- `server` optional extra added (`tableauserverclient>=0.30`, `requests>=2.28`)
- `analysis` optional extra added (`lark>=1.1`, `networkx>=3.0`, `jinja2>=3.0`)

---

## [0.4.0] — 2025-04-05

### Added
- `xml/` engine: `XmlEngine`, `XmlProxy`, namespace-aware XPath helpers
- `xml/schemas/`: bundled Tableau XSD schemas for version-aware validation
- `xml/discovery/`: auto-detection of workbook version from XML attributes
- `core/filters.py`: filter object model (`DimensionFilter`, `MeasureFilter`, `RelativeDateFilter`)
- CLI commands: `inspect`, `validate`, `swap-connection`, `rename-field`, `version-migrate`, `merge`, `diff`

### Changed
- Version bumped to `0.4.0`
- CLI framework migrated from `click` to `tooli`

### Fixed
- Round-trip XML encoding now preserves Tableau's original attribute ordering

---

## [0.1.0] — 2025-01-20

### Added
- Initial project scaffold with `src/` layout and `hatchling` build backend
- `core/` package: `Workbook`, `Datasource`, `Field`, `Worksheet`, `Dashboard` object model
- `constants.py`: all enums (`MarkType`, `DataType`, `Role`, `AggregationType`, etc.)
- `exceptions.py`: full exception hierarchy + `ValidationIssue`
- `_compat.py`: `import_optional()` helper for optional dependencies
- `package/` package: `ZipManager` (`is_twb`, `is_twbx`, asset helpers)
- `cli/` skeleton powered by `tooli`
- CI workflow (GitHub Actions) for Python 3.10–3.13
- MIT license, README, and pyproject.toml with optional extras `[cli,hyper,pandas,server,analysis,dev]`
