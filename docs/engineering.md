# Workbook engineering in 3.0

These APIs implement complete patches, scoped references, semantic checks, recoverable
fleet migrations, typed extracts, and advanced authoring. Install version 3.0 with
`pip install 'pytableau==3.0.0'`. Core workflows require only `lxml`.
Extract contracts require `pip install 'pytableau[hyper]'`.

## Changes when upgrading from 2.x

- `validate()` includes semantic checks. `validate(semantic=False)` runs the previous
  structural check. Saving retains structural validation so existing workbooks with
  semantic diagnostics can still be preserved and inspected.
- `migrate_version()` refuses unverified downgrades by default. The explicit
  `allow_unverified=True` override permits unverified header changes; it cannot bypass
  a known unsupported capability. CLI `version-set --allow-unverified` and fleet
  `MigrationPlan.target_version(..., allow_unverified=True)` expose the same choice.
- Transactions isolate XML and owned assets. Successful changes remain staged until
  `save()` after the context exits; saving inside a transaction raises an error.
- Unsupported patch operations, missing structural payloads, stale preconditions,
  and invalid results fail explicitly. Manual missing targets retain the legacy
  skip-with-warning behavior. Generated snapshot patches require an exact source.
- Physical fields declared only in datasource metadata now appear in field inventories.
  Native release and patch build strings are recognized without one exact build number.

## 1. Complete diffs and executable patches

```python
from pytableau import Workbook, Patch

with Workbook.open('before.twbx') as before, Workbook.open('after.twbx') as after:
    diff = before.diff(after)
    print(diff.to_text())
    patch = Patch.from_diff(diff)
    payload = patch.to_json()
    restored = Patch.from_dict(__import__('json').loads(payload))
    before.apply(restored)
    assert before.diff(after).is_empty()
    before.save_as('patched.twbx')
```

Diffs retain the familiar field/datasource summaries and add document/component and
asset changes. Generated patches contain the complete target XML document and current
asset bytes, including unknown XML, dashboards, actions, formatting, pre/post-root
comments and processing instructions. The precondition fingerprints canonical XML,
asset hashes, package status and active workbook member. ZIP timestamps/compression
and incidental XML indentation are not part of semantic identity.

`apply()` installs into isolated working storage, validates the complete proposal,
and restores the original state on failure. `validate=False` permits preserving a
workbook with known semantic errors; it does not relax stale snapshot preconditions.
Asset additions and deletions persist through save/reopen. For plain workbooks, a
pending deletion checks the destination's original hash before removing the file.

A plain workbook owns its adjacent `Data/` files and existing relative `filename`/
`path` references within its directory, such as `Images/logo.png`. A packaged workbook
owns all current package members. Absolute/external references are not portable owned
assets; normalize them before packaging. Snapshot payloads include full data files and
XML, so their size is proportional to workbook contents.

Manual `PatchOp` structural additions require complete XML elements, not a name alone.
Manual modifications check supplied old values and count actual changes. Generated
patches use one complete snapshot operation rather than pretending a partial list of
field edits represents the entire target workbook.

## 2. Qualified references and impact analysis

```python
from pytableau import FieldReference

ref = FieldReference.parse('[hyper.sales].[pcto:sum:Revenue:qk]')
assert str(ref) == '[hyper.sales].[pcto:sum:Revenue:qk]'
uses = wb.impact('Revenue', datasource='Sales', transitive=True)
for use in uses:
    print(use.owner, use.kind, use.path)
wb.datasources['Sales'].rename_field('Revenue', 'Net Revenue')
```

References preserve datasource qualifiers, instance encodings, aggregation codes,
quick-calculation prefixes and escaped brackets. The graph resolves internal IDs
before captions and reports ambiguity instead of choosing the first match. It tracks
calculations, worksheet shelves/marks/filters, actions, groups, joins and logical
relationships; transitive impact includes downstream calculated fields.

A caption rename preserves native internal IDs and updates dependency captions.
Explicit internal renames update native instance definitions. Formula literals,
comments, and static formatted text remain untouched. Physical join keys retain their
remote identities. Removing a field reports dependent calculations and refuses to
silently delete a referenced join/relationship key.

Worksheet shelf edits accept complete references. If several distinct references have
the same basename, a bare-name removal/reorder raises `ValueError`; supply the exact
qualified/encoded reference. Native authoring is currently limited to one datasource
per worksheet; inspection and scoped editing support multiple datasource references.

## 3. Semantic validation and compatibility

```python
errors = [issue for issue in wb.validate() if issue.level == 'error']
report = wb.compatibility('2024.1')
print(report.to_dict())
# Inspect an unverified downgrade before explicitly allowing a header update:
# wb.migrate_version('2024.1', allow_unverified=True)
```

Semantic checks include unresolved/ambiguous fields, calculation cycles, datasource
bindings, missing local assets, binary joins and key aliases, logical table IDs,
relationship endpoints/keys, named physical connections, and native instance types.
Worksheet dependency copies cannot invent physical fields; genuine worksheet-local
calculated columns are recognized. Stale dynamic tooltip/title placeholders are
warnings, since some exported workbooks retain those placeholders.

The capability registry has documented minimums for relationships (2020.2), dynamic
zone visibility (2022.3), and multi-fact relationships/viz extensions (2024.2).
It recognizes native element-name format manifests as well as named change elements.
Unknown downgrade flags remain unverified. These minimums follow Tableau's
[relationship documentation](https://help.tableau.com/current/pro/desktop/en-us/relate_tables.htm),
[2022.3 release](https://www.tableau.com/2022-3-features), and
[2024.2 release](https://www.tableau.com/2024-2-features).

`CompatibilityReport.status` is `supported`, `unsupported`, or `unverified` for the
registered checks. It is not certification of the entire proprietary XML format or a
rendering test. Downgrades always require Tableau acceptance: header changes do not
convert unsupported XML. `allow_unverified` cannot bypass a known incompatible feature.
Custom documented `Capability` entries can extend the registry through the
`capabilities=` argument to `compatibility()`.

Extract formats have independent compatibility. For older targets, available Hyper
files are inspected; unavailable Hyper dependencies produce an unverified diagnostic.
Format 3 requires Server 2023.1 or newer; format 4 requires 2024.3. This is conservative
for Server deployment: Desktop can read format 3 starting at 2022.4.1. See Tableau's
[Hyper format matrix](https://tableau.github.io/hyper-db/docs/hyper-api/hyper_process/#default_database_version).

## 4. Durable migration plans, resume and rollback

```python
from pytableau.fleet import MigrationPlan, MigrationEngine, MigrationManifest

plan = (MigrationPlan()
        .source_directory('input')
        .output_directory('output')
        .rename_fields({'Revenue': 'Net Revenue'})
        .validate_all())
manifest = MigrationEngine(plan).prepare('journals/revenue-change')
print(manifest.data)  # Review exact paths, hashes and prepared results.
manifest.apply()
# In a later process after interruption:
MigrationManifest(manifest.path).resume()
# Restore previous output bytes, including pre-existing destinations:
MigrationManifest(manifest.path).rollback()
```

Preparation creates exact output files, input/asset hashes, output preconditions,
backups and `manifest.json`; it does not install into the output directory. Use a
fresh journal directory outside both input and output trees. Omitting the output
setting prepares an in-place migration with recoverable original bytes.

Apply/resume preflights every input and destination before writing. A per-file journal
records installation. Resume recognizes interruption after replacement but before
status recording. Rollback preflights the whole set, verifies backups, restores old
outputs and removes newly created outputs. External edits cause a conflict instead of
being overwritten. Rolled-back plans require fresh preparation before applying again.
Only one cooperating process may write a manifest, using an OS advisory lock.

A fleet is installed one file at a time, not as one filesystem transaction. The
journal supports process-interruption recovery; storage-device/power-loss atomicity
across directories is not promised. Ordinary `save()` stages output and restores XML,
sidecars and deletions on recoverable I/O failure; use migration manifests for durable
multi-file recovery.

## 5. Extract contracts and schema evolution

```python
from decimal import Decimal
import pandas as pd
from pytableau.data import ColumnContract, ExtractContract, TableIdentity

contract = ExtractContract(
    columns=(ColumnContract('id', 'integer', nullable=False),
             ColumnContract('amount', 'decimal', nullable=False, precision=12, scale=2)),
    table=TableIdentity('Extract', 'Orders'),
    keys=('id',),
)
df = pd.DataFrame({'id': pd.Series([1, 2], dtype='Int64'),
                   'amount': [Decimal('12.34'), Decimal('56.78')]})
wb.datasources['Sales'].write_extract(df, contract, policy='strict')
# Or write just the database, without workbook XML:
# contract.write('orders.hyper', df)
```

`TableIdentity` keeps schema and table separate, including identifiers containing
literal dots. Supported contract types are string, integer, real, boolean, date,
datetime and decimal. Validation checks column identity, nulls, actual value types,
finite numbers, unique/non-null keys, decimal representability and declared timezone.
It does not infer/coerce values or round excessive fractional precision. Datetimes
must be exactly representable at Hyper's microsecond resolution; nonzero pandas
nanosecond remainders are rejected. Use `Decimal` for decimals, not floats.

| Policy | Existing schema behavior |
|---|---|
| `strict` (default) | Names, SQL types and nullability must match; a new table may be created. |
| `additive` | Existing columns/types/nullability remain; new columns are allowed. Required additions need `backfill={...}` when appending existing rows. |
| `replace` | Explicitly replace the selected table's schema; unrelated tables remain. |

`mode='replace'` replaces the selected table's rows; `mode='append'` validates the
combined old/new data, including duplicate keys. Append reads the selected table into
memory and stages a complete database copy; it is not a streaming bulk loader.
Named timezone values are restored to their declared zone when validating old rows.
Decimal processing is independent of the caller's decimal context.

Decimals above precision 18 require database format 3. New files use that format when
needed; existing files are upgraded on the staged copy, preserving other tables.
Workbook-attached writes require Tableau 2023.1+ for this format's Server compatibility.
Precision up to 38 is supported with the current Hyper API.

The datasource helper stages the database and proposed XML metadata, validates the
proposal, updates physical column types and removes dropped physical definitions,
and then installs. Native extract connections are updated without replacing the live
federated connection or object graph. Multi-table relation updates require an identifiable
matching physical table. A dropped column with dependent calculations is rejected before
changing the extract. Rejected data/schema/metadata leaves the original extract intact.
A custom `prepare_metadata=` callback on `contract.write()` must prepare without
mutation and return a no-fail commit closure; external side effects of caller callbacks
are the caller's responsibility.

Workbook transactions isolate owned extract writes, including cached `ds.hyper`
handles. External extracts and absolute extract references require normalization
before a transaction. Independent raw file/SQL handles are outside the boundary.
Reacquire worksheet/field/datasource wrappers after rollback. Call `save()` after a
successful transaction to install the staged data.

## 8. Native authoring

```python
from pytableau.build import RelationBuilder, LogicalTable, Relationship
from pytableau.build import WorksheetBuilder, Pane, TableCalculation
from pytableau.core.formatting import FormatSpec

join = RelationBuilder.table('[Orders]', alias='Orders').join(
    RelationBuilder.table('[Customers]', alias='Customers'),
    keys=(('[Orders].[Customer ID]', '[Customers].[Customer ID]'),), how='left')
# DatasourceBuilder('Sales').relation(join)
# A logical model instead uses .logical_model(
#     [LogicalTable('orders', 'Orders', ...), LogicalTable('customers', 'Customers', ...)],
#     [Relationship('orders', 'customers', (('[Customer ID]', '[Customer ID]'),))])

builder = (WorksheetBuilder('Sales and Profit')
    .datasource(wb.datasources['Sales'].name)
    .columns('Region')
    .dual_axis('SUM(Sales)', 'SUM(Profit)', synchronized=True)
    .panes(Pane('Bar', 'SUM(Sales)', {'color': ('Region',)}),
           Pane('Line', 'SUM(Profit)'))
    .table_calculation(TableCalculation('SUM(Sales)', 'running_total',
                                      addressing=('Region',)))
    .format(FormatSpec.from_dict({'font': {'family': 'Arial', 'size': 11},
                                 'text_color': '#223344'})))
wb.add_worksheet(builder)
```

Relations support tables, custom SQL and nested binary inner/left/right/full joins.
Join keys must use actual relation aliases. Logical models generate federated named
connections, physical collections, object properties and relationship endpoints.
Use `.named_connection(name, cls, **attrs)` for explicit connection bindings.
Relationship cardinality/referential-integrity tuning is not exposed: generated
relationships use Tableau's default assumptions.

Native worksheets write `table/view`, datasource dependency columns/instances,
independent panes, native axis space encodings, shelves, quick-calculation instances,
and style rules. `Workbook.add_worksheet(builder)` and `from_spec()` bind real
physical/calculated identities and formulas. If using `builder.build()` standalone,
provide actual column metadata with `.field_definition(name, **attributes)`; inferred
metadata cannot prove a field exists. `validate()` catches absent physical fields.

Quick calculations cover running total, difference, percent difference, percent of
total and rank. Addressing is serialized as ordered native fields; partitioning
is represented by remaining view dimensions. Restart/custom rank/difference options,
arbitrary nested table calculations, relationship optimization hints and multi-fact
model authoring are outside these APIs. Existing XML is preserved by inspection/patching.
`FormatSpec.apply()`/`read()` merge/read worksheet, field or dashboard style rules;
choose `element='column'` or `element='dashboard'` for those targets. Unknown style
attributes are retained.

`from_spec()` supports `relation`, `logical_tables`, `relationships`,
`named_connections`, `dual_axis`, `panes`, `table_calculations`, `field_definitions`
and `format`, alongside the existing basic spec keys. See the runnable
[engineering example](https://github.com/weisberg/pytableau/blob/feature/workbook-engineering-v3/examples/12_workbook_engineering.py).

## Verification and acceptance boundary

Automated tests exercise generated XML, complete patch convergence, stale-input
conflicts, rollback/failure injection, journal recovery, actual typed Hyper operations,
and native-shaped authoring round trips. The local sample corpus also checks preservation
of complete documents and package assets, while reporting source semantic diagnostics.

Tableau Desktop/Server rendering acceptance has not been performed in this environment.
Before a release, open generated joins/relationships, dual axes and quick calculations
in the intended Tableau version, verify panes and calculations visually, and save/reopen
there. A library XML round trip alone does not establish Tableau rendering acceptance.

Detailed local results and platform limitations are recorded in the [validation report](engineering-validation.md).
