"""Contract testing framework — validate workbook structure against YAML contracts.

Example::

    from pytableau.fleet import ContractRunner

    runner = ContractRunner("./contracts/")
    results = runner.run("./workbooks/")
    print(runner.to_junit_xml(results))
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ContractResult:
    """Result of checking one contract against a workbook."""

    contract_file: str
    workbook: str
    passed: bool
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_file": self.contract_file,
            "workbook": self.workbook,
            "passed": self.passed,
            "failures": self.failures,
        }


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required for contract testing. "
            "Install with: pip install 'pytableau[governance]'"
        ) from exc
    return yaml.safe_load(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _check_contract(contract: dict[str, Any], wb: Any) -> list[str]:
    """Evaluate a parsed contract dict against an open workbook.  Returns failure messages."""
    failures: list[str] = []
    contracts = contract.get("contracts", {})

    # --- datasources ---
    for ds_spec in contracts.get("datasources", []):
        ds_name = ds_spec.get("name", "")
        ds = wb.datasources.get(ds_name)
        if ds is None:
            failures.append(f"Datasource not found: {ds_name!r}")
            continue
        field_names = {f.caption for f in ds.all_fields}
        for req in ds_spec.get("required_fields", []):
            if req not in field_names:
                failures.append(f"Datasource {ds_name!r}: required field {req!r} not found")
        if ds_spec.get("no_live_connections"):
            for conn in ds.connections:
                if (conn.class_ or "") != "hyper":
                    failures.append(
                        f"Datasource {ds_name!r}: live connection found ({conn.class_!r})"
                    )

    # --- worksheets ---
    ws_names = {ws.name for ws in wb.worksheets}
    for ws_spec in contracts.get("worksheets", []):
        ws_name = ws_spec.get("name", "")
        if ws_name not in ws_names:
            failures.append(f"Worksheet not found: {ws_name!r}")

    # --- dashboards ---
    db_names = {db.name for db in wb.dashboards}
    for db_spec in contracts.get("dashboards", []):
        db_name = db_spec.get("name", "")
        if db_name not in db_names:
            failures.append(f"Dashboard not found: {db_name!r}")
            continue
        db = next(d for d in wb.dashboards if d.name == db_name)
        sheet_names = {z.get("name") for z in getattr(db, "zones", []) if z.get("name")}
        for req_sheet in db_spec.get("must_contain", []):
            if req_sheet not in sheet_names and req_sheet not in ws_names:
                failures.append(f"Dashboard {db_name!r}: required sheet {req_sheet!r} not found")

    # --- formulas ---
    formula_spec = contracts.get("formulas", {})
    if formula_spec.get("valid"):
        from pytableau.calculations.linter import lint_workbook

        issues = lint_workbook(wb)
        errors = [i for i in issues if i.severity == "error"]
        if errors:
            failures.append(f"Formula errors: {'; '.join(i.message for i in errors[:3])}")
    if formula_spec.get("no_deprecated"):
        from pytableau.calculations.linter import lint_workbook

        issues = lint_workbook(wb)
        dep = [i for i in issues if "deprecated" in (i.message or "").lower()]
        if dep:
            failures.append(f"Deprecated functions used: {'; '.join(i.message for i in dep[:3])}")

    return failures


class ContractRunner:
    """Run YAML contract files against a directory of workbooks.

    Contract YAML format::

        workbook: Sales Dashboard.twbx
        contracts:
          datasources:
            - name: Sales Data
              required_fields: [Revenue, Cost, Profit]
              no_live_connections: true
          worksheets:
            - name: Revenue by Region
          dashboards:
            - name: Executive Summary
              must_contain: [Revenue by Region]
          formulas:
            valid: true
            no_deprecated: true
    """

    def __init__(self, contracts_dir: str | Path) -> None:
        self._contracts_dir = Path(contracts_dir)

    def run(
        self,
        workbooks_dir: str | Path,
        *,
        contract_pattern: str = "**/*.yml",
    ) -> list[ContractResult]:
        """Check every contract file against its referenced workbook."""
        from pytableau.core.workbook import Workbook

        workbooks_dir = Path(workbooks_dir)
        results: list[ContractResult] = []

        for contract_path in sorted(self._contracts_dir.glob(contract_pattern)):
            try:
                contract = _load_yaml(contract_path)
                wb_name = contract.get("workbook", "")
                # Find the workbook file
                candidates = list(workbooks_dir.glob(f"**/{wb_name}"))
                if not candidates:
                    results.append(
                        ContractResult(
                            contract_file=str(contract_path),
                            workbook=wb_name,
                            passed=False,
                            failures=[f"Workbook file not found: {wb_name!r}"],
                        )
                    )
                    continue
                wb = Workbook.open(candidates[0])
                failures = _check_contract(contract, wb)
                results.append(
                    ContractResult(
                        contract_file=str(contract_path),
                        workbook=str(candidates[0]),
                        passed=not failures,
                        failures=failures,
                    )
                )
            except Exception as exc:
                results.append(
                    ContractResult(
                        contract_file=str(contract_path),
                        workbook="",
                        passed=False,
                        failures=[f"Contract load error: {exc}"],
                    )
                )
        return results

    def passed(self, results: list[ContractResult]) -> bool:
        """Return ``True`` if every contract passed."""
        return all(r.passed for r in results)

    def to_junit_xml(self, results: list[ContractResult]) -> str:
        """Render *results* as JUnit XML."""
        suite = ET.Element(
            "testsuite",
            name="pytableau-contracts",
            tests=str(len(results)),
            failures=str(sum(1 for r in results if not r.passed)),
        )
        for result in results:
            case = ET.SubElement(
                suite,
                "testcase",
                name=Path(result.contract_file).stem,
                classname="contracts",
            )
            if not result.passed:
                ET.SubElement(
                    case, "failure", message="Contract assertions failed"
                ).text = "\n".join(result.failures)
        return ET.tostring(suite, encoding="unicode")
