# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.0.0] — Unreleased

### Added
- Complete document and working-asset diffs, serializable snapshot patches, strict stale-input fingerprints, package-layout changes and atomic rollback. Manual structural patch operations accept full XML payloads and preserve their actual scope.
- Lossless datasource-qualified field and instance references; scoped calculation, worksheet, action, join and relationship impact analysis. Implicit metadata fields and worksheet-local calculations resolve without modifying XML on read.
- Semantic validation for references, cycles, assets, named connections, logical endpoints/keys, joins and native instance types. Capability reports distinguish supported, unsupported and unverified targets and allow custom documented capability rules.
- Durable migration preparation, per-file installation journals, source/output preflight hashes, interruption recovery, and rollback that restores previous destinations and rejects external edits.
- Typed extract contracts for schema/table identity, nullability, keys, decimals, dates and timezones; strict/additive/replace schema policies, combined-data key validation, explicit backfills, preservation of unrelated tables and staged XML metadata.
- Native physical join trees/custom SQL, logical objects and relationships with named physical connections, independent mark panes, synchronized dual axes, quick table calculations with addressing/partitioning, formatting read/write, and builder/spec parity.

### Breaking changes
- `migrate_version()` refuses unverified downgrades by default. `allow_unverified=True` allows a header update when the report is unverified; known unsupported capabilities always fail. API, CLI and fleet plans expose the override.
- Workbook transactions isolate owned extract writes until `save()` after commit. Saving within a transaction and using uncaptured external extracts are rejected. File-based recovery belongs to migration manifests.
- `validate()` performs semantic checks by default. `semantic=False` retains structural validation. Patches with `validate=True` roll back on semantic errors; unsupported operations and incomplete structural payloads fail.

### Fixed
- Native field renames/removals respect datasource identity and instance definitions; calculation strings/comments and static formatted text are preserved. Referenced relationship keys cannot be deleted silently.
- Build version detection reads release/patch strings and retains unknown parsed release versions. Physical fields present only in metadata now appear in field inventories.
- Working asset inventories include additions/deletions and referenced images; deleting an owned plain-workbook asset persists through save/reopen, including nested package layouts. Failed plain saves restore all installed sidecars and XML. XML comments, processing instructions and pending-deletion baselines survive rollback.
- Cached workbook Hyper handles follow isolated transaction storage. Native extract contracts preserve live federated connections and logical models; dropped physical fields are checked against dependent calculations.
- Decimal values retain exact precision independently of the caller context; wider numerics upgrade staged files to Hyper format 3. Sub-microsecond timestamps are rejected instead of truncated. The Hyper API minimum is 0.0.19484.

- Source distributions include explicit project artifacts and exclude local agent instructions, review gates and Hyper runtime logs.

### Validation boundaries
- Automated tests exercise XML/package round trips and real Hyper operations. Tableau Desktop/Server rendering acceptance has not been performed in this environment. XML capability checks are conservative and do not claim universal proprietary-format conversion.

---

## [2.0.2] — Unreleased

### Fixed
- `Workbook.save_as()` preserves the source, stages the workbook file atomically, and rebases extract paths; nested output directories and deterministic new TWBX archives work correctly.
- Standalone TWB packaging includes adjacent `Data/` assets, and plain TWB copies retain packaged assets. Generated workbooks retain attached extracts; package preparation cleans up failed extraction state and can restart after `close()`.
- Saves retain the active selection in multi-TWB packages and correctly copy extracts relative to a nested active TWB. Plain output rejects extract layouts it cannot preserve.
- Tableau version detection accepts build variants from the same release instead of requiring one exact build number.
- Fleet scanning, compliance, migration, and CLI discovery include TWBX packages, exclude non-workbook files, and close workbook resources.
- Migration applies `target_version()` and `validate_all()` in dry runs, applies mappings once to original values, matches complete hostnames, preserves relative subdirectories, excludes nested output directories from subsequent runs, and rejects paths that escape the output through child symlinks.
- Hyper I/O uses supported pantab and Tableau APIs, preserves unrelated tables, retains query column names, and reads metadata through the Hyper catalog.
- Hyper upserts support composite and null keys and absent target tables; upserts, bulk replacements, and rolling refreshes stage changes so failed writes preserve the original extract. Empty bulk inserts clear stale rows; invalid batch sizes fail explicitly.
- Missing optional dependencies provide actionable installation errors without deleting existing extracts.
- Spec building preserves caller dictionaries and zero filter bounds and accepts long inline specs. Empty `<columns/>` containers receive calculated fields correctly.
- Field renames preserve unrelated datasource calculations and worksheet references, and reject ambiguous worksheet ownership before mutation.
- README transaction, extract, fleet, compliance, and migration examples match the public API.

### Changed
- Patch version advanced to 2.0.2; Python tooling and CI align with the supported Python 3.11+ minimum.
- The `hyper` extra includes pandas, and development no longer requires a sibling `tooli` checkout. The uv lockfile is synchronized with current package metadata.
- CI includes a separate job exercising real Hyper operations with published dependencies.

---

## [2.0.1] — 2026-02-24

### Fixed
- 28 mypy type errors across `build/`, `agents/`, and `fleet/` modules (loop variable shadowing, missing return type annotations, `__exit__` return type, `Optional` element guards in `shortcuts.py`).

### Changed
- PyPI metadata: removed Python 3.10 classifier, expanded keywords (14 new: `etl`, `bi`, `governance`, `fleet`, `migration`, `automation`, `pandas`, `sdk`, …), added topic and audience classifiers.
- README updated to reflect the full v2.0.0 feature set.
- CHANGELOG updated with complete v2.0.0 release notes.

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
