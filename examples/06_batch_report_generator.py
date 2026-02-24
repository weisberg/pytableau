"""06_batch_report_generator.py

Generate multiple workbook variants from a single template by applying a
table of configurations. Each row in the config produces one output file
with its own connection settings, title, and field mapping.

Simulates the common BI pattern of "one template, many regional/client
deployments" — each deployed from the same source of truth.

Usage:
    python examples/06_batch_report_generator.py [template.twb] [output_dir]
    python examples/06_batch_report_generator.py \\
        tests/fixtures/minimal_v2022_4.twb \\
        /tmp/batch_output

Requirements: pip install pytableau
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from pytableau import Workbook


@dataclass
class ReportConfig:
    name: str           # Output file stem
    region: str         # Human-readable region label
    server: str         # Database server for this deployment
    dbname: str         # Database name for this deployment
    filter_value: str   # Optional default filter value


# ---------------------------------------------------------------------------
# Configuration table — replace with a CSV/YAML load in production
# ---------------------------------------------------------------------------
CONFIGS: list[ReportConfig] = [
    ReportConfig("report_apac",   "Asia Pacific",    "apac-db.example.com", "analytics_apac",  "APAC"),
    ReportConfig("report_emea",   "EMEA",            "emea-db.example.com", "analytics_emea",  "EMEA"),
    ReportConfig("report_amer",   "Americas",        "amer-db.example.com", "analytics_amer",  "Americas"),
    ReportConfig("report_global", "Global Rollup",   "prod-db.example.com", "analytics_global", "All"),
]


def generate_batch(template_path: str, output_dir: str) -> list[Path]:
    template = Path(template_path)
    out_dir  = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []

    print(f"\nBatch Generator — template: {template.name}")
    print(f"Output directory: {out_dir}\n")

    for cfg in CONFIGS:
        # Re-open the template fresh for each variant so mutations don't bleed across
        wb = Workbook.open(template)

        # Swap connection to this deployment's database
        result = wb.swap_connection(
            where={},       # match all connections
            to={
                "server": cfg.server,
                "dbname": cfg.dbname,
            },
        )

        # Inject a parameter value (if the workbook has a Region parameter)
        params_ds = wb.parameters
        if params_ds:
            for param in params_ds.parameters:
                if "region" in (param.caption or "").lower():
                    try:
                        param.value = cfg.filter_value
                    except Exception:
                        pass  # Skip if parameter domain doesn't allow this value

        # Validate and save
        issues = wb.validate()
        errors = [i for i in issues if getattr(i, "level", "") == "error"]
        if errors:
            print(f"  ✗ {cfg.name:25}  {len(errors)} validation error(s) — skipped")
            for e in errors[:3]:
                print(f"      {e}")
            continue

        out_path = out_dir / f"{cfg.name}.twb"
        wb.save_as(out_path, scrub_credentials=True)
        generated.append(out_path)

        swapped = getattr(result, "updated_count", "?")
        print(f"  ✓ {cfg.name:25}  server={cfg.server:<30}  connections updated: {swapped}")

    print(f"\n  Generated {len(generated)} / {len(CONFIGS)} workbooks.")
    return generated


if __name__ == "__main__":
    template_path = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/minimal_v2022_4.twb"
    output_dir    = sys.argv[2] if len(sys.argv) > 2 else "/tmp/pytableau_batch"
    generate_batch(template_path, output_dir)
