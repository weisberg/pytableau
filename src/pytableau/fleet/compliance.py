"""YAML-driven compliance automation for a fleet of workbooks.

Produces JUnit XML output suitable for CI/CD pipelines (GitHub Actions, Jenkins, GitLab CI).

Example::

    from pytableau.fleet import ComplianceRunner, load_compliance_config

    ruleset = load_compliance_config("compliance.yml")
    runner = ComplianceRunner(ruleset)
    results = runner.run("./workbooks/")
    print(runner.to_junit_xml(results))
    sys.exit(0 if runner.passed(results) else 1)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pytableau.governance.rules import GovernanceRuleset


@dataclass
class ComplianceResult:
    """Compliance check result for a single workbook."""

    workbook: str  # display name / path
    passed: bool
    issues: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workbook": self.workbook,
            "passed": self.passed,
            "issues": self.issues,
        }


def load_compliance_config(path: str | Path) -> GovernanceRuleset:
    """Load a YAML compliance config and return a :class:`~pytableau.governance.GovernanceRuleset`.

    The YAML format mirrors the governance module's ruleset format::

        rules:
          no_live_connections:
            enabled: true
            severity: error
          naming_conventions:
            enabled: true
            field_pattern: "^[A-Z]"
            severity: warning
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required for compliance config loading. "
            "Install with: pip install 'pytableau[governance]'"
        ) from exc

    from pytableau.governance.rules import GovernanceRuleset

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return GovernanceRuleset.from_dict(data)


class ComplianceRunner:
    """Run a governance ruleset against a fleet of workbooks.

    Args:
        ruleset: A :class:`~pytableau.governance.GovernanceRuleset` instance.
        error_on: Severity levels that count as failures for :meth:`passed`.
            Defaults to ``["error"]``.
    """

    def __init__(self, ruleset: Any, *, error_on: list[str] | None = None) -> None:
        self._ruleset = ruleset
        self._error_on: set[str] = set(error_on or ["error"])

    def run(
        self,
        directory: str | Path,
        *,
        pattern: str = "**/*.tw[bx]",
    ) -> list[ComplianceResult]:
        """Check every workbook in *directory* against the ruleset."""
        from pytableau.core.workbook import Workbook

        results: list[ComplianceResult] = []
        for path in sorted(Path(directory).glob(pattern)):
            try:
                wb = Workbook.open(path)
                issues = self._ruleset.check(wb)
                result_issues = [
                    {"rule": i.rule, "severity": i.severity, "message": i.message} for i in issues
                ]
                has_failure = any(i["severity"] in self._error_on for i in result_issues)
                results.append(
                    ComplianceResult(
                        workbook=str(path),
                        passed=not has_failure,
                        issues=result_issues,
                    )
                )
            except Exception as exc:
                results.append(
                    ComplianceResult(
                        workbook=str(path),
                        passed=False,
                        issues=[
                            {
                                "rule": "load",
                                "severity": "error",
                                "message": f"Failed to open workbook: {exc}",
                            }
                        ],
                    )
                )
        return results

    def passed(self, results: list[ComplianceResult]) -> bool:
        """Return ``True`` if all workbooks passed."""
        return all(r.passed for r in results)

    def to_junit_xml(self, results: list[ComplianceResult]) -> str:
        """Render *results* as a JUnit XML string for CI/CD integration."""
        suite = ET.Element(
            "testsuite",
            name="pytableau-compliance",
            tests=str(len(results)),
            failures=str(sum(1 for r in results if not r.passed)),
        )
        for result in results:
            case = ET.SubElement(
                suite,
                "testcase",
                name=Path(result.workbook).name,
                classname="compliance",
            )
            if not result.passed:
                failure_msgs = "\n".join(
                    f"[{i['severity'].upper()}] {i['rule']}: {i['message']}"
                    for i in result.issues
                    if i["severity"] in self._error_on
                )
                ET.SubElement(
                    case, "failure", message="Compliance check failed"
                ).text = failure_msgs
        return ET.tostring(suite, encoding="unicode")
