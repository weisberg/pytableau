"""01_connection_promoter.py

Promote a Tableau workbook from one environment to another using a plain
dictionary config. Useful in CI/CD pipelines where you need to swap dev
→ staging → prod connections before publishing.

Usage:
    python examples/01_connection_promoter.py <workbook> <from_env> <to_env>
    python examples/01_connection_promoter.py tests/fixtures/minimal_v2022_4.twb dev prod

Requirements: pip install pytableau
"""

from __future__ import annotations

import sys
from pathlib import Path

from pytableau import Workbook
from pytableau.package.promotion import EnvironmentSpec, PromotionConfig

# ---------------------------------------------------------------------------
# Environment registry — in a real project this would come from a YAML file
# or environment variables.
# ---------------------------------------------------------------------------

ENVIRONMENTS: dict[str, dict] = {
    "dev": {
        "server": "dev-db.example.com",
        "dbname": "analytics_dev",
        "username": "dev_user",
        "port": 5432,
    },
    "staging": {
        "server": "stg-db.example.com",
        "dbname": "analytics_stg",
        "username": "stg_user",
        "port": 5432,
    },
    "prod": {
        "server": "prod-db.example.com",
        "dbname": "analytics_prod",
        "username": "svc_tableau",
        "port": 5432,
    },
}


def promote(workbook_path: str, from_env: str, to_env: str) -> Path:
    if from_env not in ENVIRONMENTS:
        raise ValueError(f"Unknown environment '{from_env}'. Choose from: {list(ENVIRONMENTS)}")
    if to_env not in ENVIRONMENTS:
        raise ValueError(f"Unknown environment '{to_env}'. Choose from: {list(ENVIRONMENTS)}")

    config = PromotionConfig(
        environments={
            name: EnvironmentSpec(name=name, **spec)
            for name, spec in ENVIRONMENTS.items()
        }
    )

    src = Path(workbook_path)
    wb = Workbook.open(src)

    print(f"  Source:  {src.name}")
    print(f"  Version: {wb.version}")
    print(f"  Datasources: {len(list(wb.datasources))}")
    print()

    # Show current connection state
    for ds in wb.datasources:
        for conn in ds.connections:
            print(f"  [{from_env}] {ds.caption or ds.name}  →  "
                  f"{conn.server or '(no server)'}  /  {conn.dbname or '(no db)'}")

    changes = wb.promote(from_env=from_env, to_env=to_env, config=config)

    print()
    for change in changes:
        print(f"  ✓ {change}")

    # Show promoted connection state
    print()
    for ds in wb.datasources:
        for conn in ds.connections:
            print(f"  [{to_env}] {ds.caption or ds.name}  →  "
                  f"{conn.server or '(no server)'}  /  {conn.dbname or '(no db)'}")

    dest = src.with_stem(f"{src.stem}_{to_env}")
    wb.save_as(dest, scrub_credentials=True)
    print(f"\n  Saved: {dest}")
    return dest


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    workbook, from_env, to_env = sys.argv[1], sys.argv[2], sys.argv[3]
    print(f"\nPromoting '{workbook}'  {from_env} → {to_env}\n")
    promote(workbook, from_env, to_env)
