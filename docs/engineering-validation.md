# 3.0 development validation

Development snapshot, October 2, 2026. Version 3.0.0 is unreleased.

| Check | Result |
|---|---|
| Full Python 3.13 suite with optional integrations | 600 passed; 11 expected mutation warnings |
| Ruff lint and formatting | Passed; 130 checked/formatted source, test and example files |
| Configured mypy checks | Passed; 91 source files |
| Strict MkDocs build | Passed |
| uv lock consistency | Passed |
| Source distribution and wheel build | Passed |
| Installed Python 3.11 core wheel without extras | Six-workflow example passed |
| Real Hyper example | Typed extract, patch, impact, compatibility, authoring and migration recovery passed |
| Sample corpus | 11/11 complete XML/package-asset round trips and empty post-round-trip diffs |
| Independent adversarial review | Reproduced failures fixed; no remaining reproduced critical failure |

The corpus includes one pre-existing error in `#RWFD Hospital ER Dashboard.twbx`:
`[Calculation_48695209525137412]` is referenced by a generated group without a field
declaration. Ten other samples pass semantic validation without errors. The validator
reports this source defect; serialization preserves it.

Regression tests cover stale/full patches, XML/asset rollback, failed saves, pending
and nested-layout deletions, source-qualified mutations, native dependency identity,
capability manifests, process-interruption recovery, source/output/backup conflicts,
duplicate symlink outputs, decimal precision and database-format upgrades, timestamp
representability, nullable/zone-aware append, native extract/live-model preservation,
and authoring bindings/quick calculations/style round trips.

Local environment: Apple Silicon, Python 3.13.13, pandas 3.0.6, pantab 5.3.0,
Hyper API 0.0.26479. The published pantab macOS wheel bundled an Intel Hyper executable;
local integration testing substituted the ARM executable from the installed Hyper API
in the temporary test environment. The project does not patch dependency binaries.
The Linux CI Hyper job uses published dependencies without this workaround and provides
the independent platform check. CI also checks Python 3.11, 3.12 and 3.13, documentation,
distribution builds and the core installed-wheel example.

**Tableau Desktop/Server rendering acceptance is unverified.** No rendering environment
was available for this run. Before release, validate generated joins, relationships,
independent panes, dual axes and table calculations in the target Tableau version and
save/reopen there. XML/package tests establish serialization and structural/semantic
checks; they do not prove Tableau renderability or universal downgrade conversion.

See [the engineering guide](engineering.md) for public contracts and supported scope.
