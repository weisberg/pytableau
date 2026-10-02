"""Run all six 3.0 workflows locally; optional --hyper exercises real extracts.

    python examples/12_workbook_engineering.py --output /tmp/engineering-demo
    python examples/12_workbook_engineering.py --output /tmp/engineering-hyper --hyper

Requires pytableau>=3.0.0; --hyper requires pytableau[hyper].
The output demonstrates XML authoring and recovery, not Tableau rendering acceptance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pytableau import Patch, Workbook
from pytableau.build import from_spec
from pytableau.fleet import MigrationEngine, MigrationManifest, MigrationPlan


def run(output: Path, *, hyper: bool = False) -> None:
    output.mkdir(parents=True, exist_ok=True)
    spec = {
        "version": "2024.3",
        "datasources": [
            {
                "caption": "Sales",
                "connection": {"class": "sqlserver", "server": "dev.example", "dbname": "sales"},
                "columns": [
                    {"caption": "Region"},
                    {"caption": "Sales", "datatype": "real", "role": "measure"},
                    {"caption": "Profit", "datatype": "real", "role": "measure"},
                ],
                "calculated_fields": [{"caption": "Margin", "formula": "[Profit]/[Sales]"}],
                "logical_tables": [
                    {
                        "id": "orders",
                        "caption": "Orders",
                        "relation": {"table": "[Orders]", "alias": "Orders"},
                    },
                    {
                        "id": "regions",
                        "caption": "Regions",
                        "relation": {"table": "[Regions]", "alias": "Regions"},
                    },
                ],
                "relationships": [
                    {"left": "orders", "right": "regions", "keys": [["[Region]", "[Region]"]]}
                ],
            }
        ],
        "worksheets": [
            {
                "name": "Sales and Profit",
                "datasource": "Sales",
                "columns": ["Region"],
                "dual_axis": {
                    "primary": "SUM(Sales)",
                    "secondary": "SUM(Profit)",
                    "synchronized": True,
                },
                "panes": [
                    {"mark_type": "Bar", "axis": "SUM(Sales)", "encodings": {"color": ["Region"]}},
                    {"mark_type": "Line", "axis": "SUM(Profit)"},
                ],
                "table_calculations": [
                    {"field": "SUM(Sales)", "function": "running_total", "addressing": ["Region"]}
                ],
                "format": {"font": {"family": "Arial", "size": 11}, "text_color": "#223344"},
            }
        ],
    }
    source = output / "input"
    source.mkdir(exist_ok=True)
    wb = from_spec(spec)
    assert not [i for i in wb.validate() if i.level == "error"]
    wb.save_as(source / "original.twb")
    report = wb.compatibility("2020.1")
    assert report.status == "unsupported"  # Logical relationships require 2020.2.
    impact = [use.to_dict() for use in wb.impact("Profit", datasource="Sales")]
    (output / "impact.json").write_text(json.dumps(impact, indent=2))
    with Workbook.open(source / "original.twb") as target:
        target.datasources["Sales"].rename_field("Profit", "Net Profit")
        patch = Patch.from_diff(wb.diff(target))
        (output / "patch.json").write_text(patch.to_json())
        wb.apply(Patch.from_dict(json.loads(patch.to_json())))
        assert wb.diff(target).is_empty()
    wb.save_as(output / "patched.twbx")
    plan = (
        MigrationPlan()
        .source_directory(source)
        .output_directory(output / "migrated")
        .rename_fields({"Profit": "Net Profit"})
        .validate_all()
    )
    manifest = MigrationEngine(plan).prepare(output / "journal")
    manifest.apply()
    MigrationManifest(manifest.path).resume()
    manifest.rollback()
    assert not (output / "migrated/original.twb").exists()
    if hyper:
        from decimal import Decimal

        import pandas as pd

        from pytableau.data import ColumnContract, ExtractContract, TableIdentity

        contract = ExtractContract(
            (
                ColumnContract("id", "integer", False),
                ColumnContract("amount", "decimal", False, 12, 2),
            ),
            TableIdentity("Extract", "Orders"),
            ("id",),
        )
        frame = pd.DataFrame(
            {"id": pd.Series([1, 2], dtype="Int64"), "amount": [Decimal("12.34"), Decimal("56.78")]}
        )
        contract.write(output / "typed.hyper", frame)
        contract.require(frame)
        # Use a separate extract datasource so its metadata describes the data.
        extract_wb = from_spec(
            {"datasources": [{"caption": "Extract", "connection": {"class": "hyper"}}]}
        )
        extract_wb.save_as(output / "extract.twb")
        extract_wb.datasources[0].write_extract(frame, contract)
        extract_wb.save_as(output / "extract.twbx")
        extract_wb.close()
    wb.close()
    print(
        f"Patch convergence, impact, compatibility, native authoring and journal recovery passed: {output}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hyper", action="store_true")
    arguments = parser.parse_args()
    run(arguments.output, hyper=arguments.hyper)
