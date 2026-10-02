"""Preview or execute a source-preserving fleet migration.

Usage:
    python examples/11_fleet_migration.py SOURCE OUTPUT --server dev-db=prod-db
    python examples/11_fleet_migration.py SOURCE OUTPUT --server dev-db=prod-db --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pytableau.fleet import MigrationEngine, MigrationPlan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--server", help="Exact old=new server hostname mapping")
    parser.add_argument("--version", help="Supported target Tableau release, e.g. 2024.1")
    parser.add_argument("--apply", action="store_true", help="Write files; default is a dry run")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Choose a separate output directory to preserve source workbooks.")

    plan = (
        MigrationPlan().source_directory(args.source).output_directory(args.output).validate_all()
    )
    if args.server:
        old, separator, new = args.server.partition("=")
        if not separator or not old or not new:
            parser.error("--server must be an old=new hostname pair")
        plan.swap_connections({old: new})
    if args.version:
        plan.target_version(args.version)
    if not args.server and not args.version:
        parser.error("Specify --server and/or --version")

    report = MigrationEngine(plan).execute(dry_run=not args.apply)
    print(json.dumps(report.to_dict(), indent=2))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
