# Workbook I/O and maintenance guarantees

## Saving and packaging

`Workbook.save_as(path)` validates the XML, stages a complete workbook file in the
destination directory, and atomically replaces that file. A failed workbook write
leaves the existing XML or ZIP file intact. Saving to a different path does not modify
the source `.twb` or `.twbx`; `save()` then uses the last successful destination.
Parent directories are created automatically. Credential scrubbing remains enabled
by default and modifies connection XML in the in-memory workbook.

TWBX output uses sorted archive entries and fixed ZIP timestamps. When packaging a
standalone TWB, files beneath its adjacent `Data/` directory are included with their
relative paths. This includes retained extract files after detaching an extract.
Files outside `Data/` are not automatically gathered for standalone TWB packaging.
For an existing TWBX, every extracted file is preserved while the active TWB's XML
is replaced. Plain TWB output copies those assets beside the destination; asset
files are installed individually before the XML, so the complete set of files is
not replaced atomically. Saving rebases extract paths to the new destination.
Plain workbooks saved in the same directory can share relative asset paths; use
separate directories or TWBX packages when independent extract updates are needed.
Package resources should be released using a workbook context manager.
The active TWB selection is retained across saves, including packages with several
TWB entries. Plain output rebases assets inside a nested active TWB directory;
extracts outside that directory require TWBX output to retain their layout.

Tableau's `source-build` begins with the release identifier, for example `20224`
for 2022.4. Build timestamps vary across patches. Version detection reads that
prefix for supported releases and keeps the default fallback for unrecognized
headers. `migrate_version()` updates the header; it does not convert version-specific
XML features or prove compatibility with an older Tableau Desktop release.

## Fleet operations

Scanner, compliance runner, and migration engine discover `.twb` and `.twbx` files
with the default `**/*.twb*` pattern. Directories and other suffixes are excluded.
A custom pattern such as `**/*.twb` can select only plain XML workbooks. A missing
source directory raises `NotADirectoryError` instead of reporting an empty fleet.

Migration matches full server hostnames, preserves the source directory's relative
structure beneath the output directory, and excludes that output directory from
subsequent scans when it is nested beneath the source. This prevents workbooks
with the same filename in different directories from overwriting each other.
Server and field mappings are applied once to the original values, including
field-name swaps. Output paths that escape through a child symlink are rejected
in both dry runs and live runs. Omitting `output_directory()` requests an in-place
migration.
Field renames update calculations in the owning datasource and references in its
bound worksheets and actions. An unqualified worksheet reference shared by several
possible datasources raises an error before mutation instead of guessing ownership.

`target_version()` must name a supported release. `validate_all()` runs after
planned mutations, including during a dry run; validation failures become error
results. A dry run writes no workbook files. Run a dry run first and inspect each
result before executing the same plan. See the
[fleet migration example](https://github.com/weisberg/pytableau/blob/main/examples/11_fleet_migration.py).

## Hyper extracts

Install `pytableau[hyper]` for pandas, pantab, and Tableau Hyper API support.
`HyperBridge.from_dataframe()` keeps its `replace` and `append` modes. It maps those
to pantab's supported `table_mode` interface; replacement affects the requested
table and preserves other tables in the database. Bare table names use the
`public` schema. `query()` accepts Hyper SQL: quote identifiers with double quotes,
for example `SELECT "Revenue" FROM "Extract"`. Tableau formula brackets are not
SQL identifier quotes.

`HyperFile.upsert()` matches all specified key columns, including nulls, and returns
`(deleted, inserted)` counts. It uses a staging table and a database transaction in
a copy of the extract, then replaces the original file after success. Rolling
refreshes and bulk replacements likewise stage every batch before replacing the
original. These file-copy operations require
extra disk space proportional to the extract size and assume a single writer;
concurrent updates to one extract are not coordinated. Empty bulk replacement
clears old rows, and nonpositive batch sizes raise `ValueError`.

In 3.0, workbook transactions isolate XML and owned asset changes. Hyper writes remain
in working storage until `save()` after commit; exceptions restore the snapshot.
Saving inside a transaction and uncaptured external extract writes are rejected.
Use durable migration manifests for file installation and recovery. See the
[engineering guide](engineering.md).

## Verification scope

The maintenance regression suite covers source preservation, interrupted writes,
package cleanup, spec reuse, fleet selection and migration behavior, and real
Hyper database operations. CI tests Python 3.11–3.13 and includes a Linux Hyper job.
These tests do not validate rendered Tableau Desktop dashboards or authenticate
against a live Tableau Server or Cloud instance.

For the local Apple Silicon review, the installed pantab ARM wheels bundled an
Intel-only `hyperd` executable. Real integration tests used the native ARM executable
from Tableau Hyper API inside an isolated temporary environment; the project
environment was unchanged. Linux CI exercises the normal published dependency
installation. Users encountering that startup failure should inspect their
dependency wheels and use a compatible Hyper runtime.

Relevant API references: [pantab usage](https://pantab.readthedocs.io/en/stable/examples.html)
and [Tableau Hyper SQL](https://tableau.github.io/hyper-db/docs/guides/sql_commands/).
