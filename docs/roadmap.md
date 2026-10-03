# pytableau roadmap

**Updated October 3, 2026. Baseline: released 3.0.0.** This is the forward plan for
workbook engineering, not a list of promises already fulfilled. Release targets below
are proposed sequencing, with no committed dates or staffing. Owners are unassigned
until a maintainer accepts an issue. Size estimates are relative and confidence in
future effort is lower than confidence in the audited current baseline.

The priority is to make workbook changes trustworthy, then deepen automation and
native authoring. Keep the Python core small (`lxml`, Python 3.11+) and optional Hyper,
Server, analysis, governance, CLI and testing integrations separate. Preserve unknown
XML and assets; fail explicitly on ambiguous or unsupported mutation.

**Live tracker:** [roadmap overview #146](https://github.com/weisberg/pytableau/issues/146). [Machine-readable plan](roadmap.json). [3.0 engineering guide](engineering.md).

## Released baseline and evidence

| Area | Shipped in 3.0 or earlier | Remaining boundary | Evidence |
|---|---|---|---|
| XML and packaging | TWB/TWBX reads, unknown XML preservation, deterministic packaging, owned assets and safe saves | Resource limits and complete native corpus need strengthening | [Package implementation](https://github.com/weisberg/pytableau/blob/v3.0.0/src/pytableau/package/manager.py) |
| Diff, patch and impact | Complete document/working-asset snapshots, fingerprints, rollback and datasource-qualified graph | No general three-way merge or compact delta format | [Patches](https://github.com/weisberg/pytableau/blob/v3.0.0/src/pytableau/inspect/diff.py), [references](https://github.com/weisberg/pytableau/blob/v3.0.0/src/pytableau/core/references.py) |
| Validation and version awareness | Structural/semantic checks and conservative capability reports | Universal proprietary XML conversion is not implemented | [Semantic checks](https://github.com/weisberg/pytableau/blob/v3.0.0/src/pytableau/xml/semantic.py) |
| Recovery and extracts | Prepared migration journals, resume/rollback, typed extract contracts and exact schema policies | Per-file recovery is not whole-fleet atomicity; general streaming evolution remains planned | [Journal](https://github.com/weisberg/pytableau/blob/v3.0.0/src/pytableau/fleet/journal.py), [contracts](https://github.com/weisberg/pytableau/blob/v3.0.0/src/pytableau/data/contracts.py) |
| Source-control cleaning | `git_clean()` API/CLI exist | Shipped cleaning deletes native styles; P0 R30 corrects this before normalization research | [Normalizer](https://github.com/weisberg/pytableau/blob/v3.0.0/src/pytableau/xml/canonical.py) |
| Authoring and templates | Builders/specs, joins/relationships, panes/dual axes, quick calculations, styles and ten packaged templates | One datasource per authored worksheet; rendering acceptance remains unverified | [Engineering guide](engineering.md), [release validation](engineering-validation.md) |
| Server and metadata | PAT/credential auth, publish/download/refresh, basic drift and GraphQL helpers | Transport, identity, pagination and result-completeness gaps remain | [Server client](https://github.com/weisberg/pytableau/blob/v3.0.0/src/pytableau/server/client.py), [metadata client](https://github.com/weisberg/pytableau/blob/v3.0.0/src/pytableau/server/metadata.py) |
| Governance and developer tools | SQLite index, lint, compliance/contracts, pytest plugin, CLI, agent discovery/receipts and docs | Unified schemas, strict public typing and some promised integrations remain partial | [Package metadata](https://github.com/weisberg/pytableau/blob/v3.0.0/pyproject.toml), [governance](https://github.com/weisberg/pytableau/tree/v3.0.0/src/pytableau/governance) |
| Accessibility and telemetry | Local complexity heuristics; historical proposals | Accessibility diagnostics and evidence-based performance correlation remain planned | Existing issues [#111](https://github.com/weisberg/pytableau/issues/111), [#104](https://github.com/weisberg/pytableau/issues/104) |

The 3.0 release passed 600 local tests, including optional integrations and a locally
stored sample corpus; six CI jobs covered Python 3.11–3.13, Linux Hyper, lint/types,
strict documentation and an installed wheel. These are the recorded release results,
not a promise that every environment or future checkout has that test count. The local
Apple Silicon pantab workaround and unverified Desktop/Server rendering are documented
in the [validation report](engineering-validation.md). Closed legacy issues record
historical implementation decisions, not proof that every originally proposed criterion
or hypothetical API is complete.

## Priority and delivery policy

| Priority | Meaning | Sequencing rule |
|---|---|---|
| P0 | Integrity risk or evidence missing for advertised mutation | Address before expanding the affected native mutation surface |
| P1 | Reliability and user-visible operational capability | Next release planning after relevant P0 dependencies |
| P2 | Broader authoring, scale or specialist capability | Schedule after dependencies and a scoped design |
| P3 | Ecosystem experiment needing a demonstrated consumer | Run only with a named use case and bounded spike |

**M** means one bounded cross-module change; **L** means multiple interfaces, native
fixtures, external environment requirements or a staged design. Neither is a week
estimate. A target milestone can move; semver takes precedence: 3.0.x contains fixes and
evidence, new public APIs move to a minor release, and changed compatibility contracts
require a major release. Research items have no promised release.

Start the five P0 items first: rendering acceptance (R01), reproducible corpus (R02),
archive/resource protections (R04), safe existing merge behavior (R29) and style-preserving
Git cleaning (R30). Full merge reconciliation (R05) is a 3.1 API. A safe bug-fix
rejection of unsupported behavior can ship while a richer merge API awaits native
acceptance. R01 needs a licensed Tableau environment; telemetry research needs
anonymized data and appropriate access. Neither unknown is converted into a completion
claim. Do not start all 30 items concurrently: finish bounded slices, record evidence
and only then widen the supported surface.

## Release sequence and exit criteria

### v3.0.x — Validation and release hardening

Prove and protect the shipped 3.0 surface before broadening it. Patch releases contain fixes, fixtures and evidence; additive APIs move to 3.1.

**Exit criteria:** P0 merge/normalization/archive risks resolved with negative tests; a licensed native fixture corpus and explicit rendering matrix published; supported release artifacts install and pass their declared platform tests.

[GitHub milestone](https://github.com/weisberg/pytableau/milestone/14).

| ID | Work item | Priority | Size | Dependencies | Tracking |
|---|---|---|---|---|---|
| R01 | Establish Tableau Desktop/Server rendering acceptance matrix | P0 | L | None | [#119](https://github.com/weisberg/pytableau/issues/119) |
| R02 | Promote native workbook corpus into reproducible CI fixtures | P0 | M | None | [#120](https://github.com/weisberg/pytableau/issues/120) |
| R03 | Expand supported platform, extras and release artifact checks | P1 | M | R02 | [#121](https://github.com/weisberg/pytableau/issues/121) |
| R04 | Bound and validate archive/XML resource consumption | P0 | L | None | [#122](https://github.com/weisberg/pytableau/issues/122) |
| R29 | Reject unsafe existing merge cases before mutation and honor conflicts | P0 | M | None | [#144](https://github.com/weisberg/pytableau/issues/144) |
| R30 | Fix destructive git_clean style removal and preserve semantic content | P0 | M | R02 | [#145](https://github.com/weisberg/pytableau/issues/145) |

### v3.1.0 — Operational confidence

Make server diagnostics, CLI automation, contracts and public API results reliable and complete.

**Exit criteria:** Unknown and partial results are explicit; drift matching is identity based; paginated REST/GraphQL data and job outcomes are covered; API/CLI workflows, versioned reports and upgrade docs are exercised.

[GitHub milestone](https://github.com/weisberg/pytableau/milestone/15).

| ID | Work item | Priority | Size | Dependencies | Tracking |
|---|---|---|---|---|---|
| R05 | Make workbook merge reconcile identities, references and assets | P1 | L | R01, R02, R29 | [#123](https://github.com/weisberg/pytableau/issues/123) |
| R06 | Harden server transport, pagination, authentication and job outcomes | P1 | L | R03 | [#124](https://github.com/weisberg/pytableau/issues/124) |
| R07 | Make Metadata API queries paginated, schema-aware and completeness-aware | P1 | L | R06 | [#125](https://github.com/weisberg/pytableau/issues/125) |
| R08 | Complete local/published drift reports with explicit unknown states | P1 | L | R02, R06, R07, R09 | [#102](https://github.com/weisberg/pytableau/issues/102) |
| R09 | Expose 3.0 workflows through CLI and versioned JSON schemas | P1 | M | R02 | [#126](https://github.com/weisberg/pytableau/issues/126) |
| R10 | Add reviewable extract schema-change plans and provenance | P1 | M | R09 | [#127](https://github.com/weisberg/pytableau/issues/127) |
| R11 | Unify governance findings and CI report formats | P1 | M | R09 | [#128](https://github.com/weisberg/pytableau/issues/128) |
| R12 | Make agent discovery and mutation plans consistently typed and bounded | P1 | M | R09, R10, R11 | [#129](https://github.com/weisberg/pytableau/issues/129) |
| R28 | Publish typed API contracts, support policy and upgrade documentation | P1 | M | R03, R09 | [#143](https://github.com/weisberg/pytableau/issues/143) |

### v3.2.0 — Native authoring and accessibility

Expand authoring only through native fixtures and target-version rendering evidence.

**Exit criteria:** Supported dashboards, panes, calculations, formatting and templates survive native save/reopen; accessibility reports distinguish static evidence from required rendered checks.

[GitHub milestone](https://github.com/weisberg/pytableau/milestone/16).

| ID | Work item | Priority | Size | Dependencies | Tracking |
|---|---|---|---|---|---|
| R13 | Complete native dashboard layout, device-layout and action authoring | P1 | L | R01, R02 | [#130](https://github.com/weisberg/pytableau/issues/130) |
| R14 | Expand worksheet authoring with explicit multi-source and table-calc semantics | P2 | L | R01, R02, R17 | [#131](https://github.com/weisberg/pytableau/issues/131) |
| R15 | Publish a rendering-verified template gallery and recipes | P1 | M | R01, R13 | [#132](https://github.com/weisberg/pytableau/issues/132) |
| R16 | Implement evidence-based accessibility diagnostics and rendered checks | P1 | L | R01, R13 | [#111](https://github.com/weisberg/pytableau/issues/111) |
| R17 | Extend formula grammar, versioned functions and scoped AST analysis | P2 | L | R02 | [#133](https://github.com/weisberg/pytableau/issues/133) |
| R18 | Verify native formatting, palette inheritance and conditional encoding | P2 | M | R01, R02 | [#134](https://github.com/weisberg/pytableau/issues/134) |

### v3.3.0 — Fleet scale and governed promotion

Scale local workflows and deploy workbook changes with reviewable plans, bounded resources and recoverable operations.

**Exit criteria:** Benchmarks and resource budgets published; cross-platform interruption recovery demonstrated; promotion previews, permissions, revision checks, job outcomes and rollback limits documented and tested.

[GitHub milestone](https://github.com/weisberg/pytableau/milestone/17).

| ID | Work item | Priority | Size | Dependencies | Tracking |
|---|---|---|---|---|---|
| R19 | Strengthen migration durability and cross-platform interruption guarantees | P1 | L | R03 | [#135](https://github.com/weisberg/pytableau/issues/135) |
| R20 | Benchmark and scale fleet workflows with bounded concurrency | P2 | L | R02, R19 | [#136](https://github.com/weisberg/pytableau/issues/136) |
| R21 | Add incremental scoped indexing and cross-workbook lineage | P2 | L | R02, R07 | [#137](https://github.com/weisberg/pytableau/issues/137) |
| R22 | Add governed publish/promotion plans with revision checks and recovery | P1 | L | R06, R08, R11, R19 | [#138](https://github.com/weisberg/pytableau/issues/138) |
| R23 | Add bounded-memory multi-table extract evolution and refresh | P2 | L | R10, R19, R20 | [#139](https://github.com/weisberg/pytableau/issues/139) |

### Research backlog — Evidence and interoperability

Run bounded experiments before committing expensive or uncertain capabilities to a release. No delivery date or version commitment.

**Exit criteria:** Each spike produces representative inputs, a reproducible result, explicit limits and a go/no-go decision. A production feature requires a separately scoped implementation issue.

[GitHub milestone](https://github.com/weisberg/pytableau/milestone/18).

| ID | Work item | Priority | Size | Dependencies | Tracking |
|---|---|---|---|---|---|
| R24 | Validate performance telemetry adapters and evidence-based correlation | P2 | L | R07, R08, R20 | [#104](https://github.com/weisberg/pytableau/issues/104) |
| R25 | Research evidence-backed XML transforms and compatibility profiles | P2 | L | R01, R02, R17 | [#140](https://github.com/weisberg/pytableau/issues/140) |
| R26 | Research Git-friendly normalization and three-way patch conflict handling | P2 | L | R02, R05, R09, R30 | [#141](https://github.com/weisberg/pytableau/issues/141) |
| R27 | Evaluate optional event-driven and ecosystem workflow adapters | P3 | M | R06, R12, R22 | [#142](https://github.com/weisberg/pytableau/issues/142) |

## Why this ordering

R02 supplies the test evidence for later semantic changes. R01 provides the native
acceptance required by authoring and compatibility work; it is not replaced by XML
round trips. R06 and R07 establish transport and completeness semantics before R08
can honestly report drift. R09 establishes reusable machine-readable contracts before
extract plans, agent plans and shared governance outputs. R19 defines recovery limits
before concurrent migrations or governed promotion. The dependency lists in the plan
are prerequisite work, not an instruction to serialize every independent task.

Accessibility checks can identify static evidence and remediation candidates, but
keyboard/focus/screen-reader behavior requires the rendered experience. The exact text
case matters for [WCAG contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html);
Tableau-specific mark-count advice is not itself a WCAG success criterion. See
[Tableau accessibility guidance](https://help.tableau.com/current/pro/desktop/en-us/accessibility_best_practice.htm).

Metadata results may be incomplete, permission-filtered or disabled even when an HTTP
request succeeds; diagnostics must expose those states and record principal, site and
visibility scope. Permission-filtered emptiness only means empty within that scope;
site-wide completeness needs independent evidence. See [Metadata permissions](https://help.tableau.com/current/api/metadata_api/en-us/docs/meta_api_permissions.html). See
[Tableau Metadata API common errors](https://help.tableau.com/current/api/metadata_api/en-us/docs/meta_api_errors.html).
Telemetry adapters must separate
[Cloud Admin Insights](https://help.tableau.com/current/online/en-us/adminview_insights_manage.htm)
from Server repository/performance-recording sources. Correlation and complexity
heuristics identify candidates; they do not establish calculation-level causation.

## Definition of done

A roadmap issue is implemented only after its acceptance checklist is met and evidence
is linked. Close it with the implementing PR, released version (or explicit unreleased
status), tests, docs and remaining supported-scope limits. All work stays on feature
branches and follows the repository's review/merge procedure.

- Run the relevant positive and negative tests plus required full-suite/CI checks.
- Test save/reopen and XML/asset rollback for mutation; use native acceptance when
  claiming Tableau rendering or version compatibility.
- Cover core installs and declared optional dependencies/platforms without hidden fixes.
- Document public signatures, reports/errors, upgrade behavior, runnable examples and
  resource/security assumptions. Include built artifacts when packaging changes.
- Fail or report unknown explicitly for unsupported, ambiguous, partial or inaccessible
  evidence. Logs and exported artifacts must redact secrets.
- Record performance baselines before setting budgets or claiming improvements.

Maintain the overview, issue links, priorities, dependency graph and milestone membership
together at each planning/release review. Link follow-up work for partial delivery instead
of checking off the entire scope. Historical completed milestones are archived; active
work uses the current release sequence. No recurring job or external owner assignment is
implied by this planning policy.

## Deliberate limits

This plan does not make pytableau a full Tableau REST API clone, hosted automation
platform, legal accessibility certification service or universal XML converter. It does
not add mandatory pydantic, an AI service or a web framework to the core. Preserve the
existing TSC/Hyper/pantab integration boundaries; prefer explicit optional adapters over
reimplementing upstream products. Multi-workbook/server global atomicity and automatic
lossy downgrade conversion are outside current guarantees.

## Summary

The next investment is in verified, recoverable changes. Broaden native authoring and
server automation only after evidence, identity and failure handling are dependable.

| TLDR | Plan |
|---|---|
| Already shipped | 3.0 patch/impact/validation/journal/contract/authoring foundations |
| First | P0 rendering evidence, corpus, archive protections, merge guards and style-safe cleaning |
| Next | 3.1 operational confidence; 3.2 native authoring/accessibility; 3.3 scale/promotion |
| Explore | Telemetry, real format transforms, Git/three-way patches and optional adapters |
| Commitments | No dates or assigned owners; version targets remain proposals |
