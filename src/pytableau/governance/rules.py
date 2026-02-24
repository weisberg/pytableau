"""Configurable governance lint rules for Tableau workbooks.

Ruleset YAML format::

    rules:
      naming_conventions:
        enabled: true
        field_pattern: "^[A-Z][a-zA-Z0-9 ]+$"
        severity: warning
      no_live_connections:
        enabled: true
        severity: error
      no_pii_fields:
        enabled: true
        patterns: ["email", "ssn", "credit.card"]
        severity: error
      max_complexity:
        enabled: true
        max_score: 150
        severity: warning
      no_deprecated_functions:
        enabled: true
        severity: error
      custom_sql_audit:
        enabled: true
        severity: warning
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


@dataclass(frozen=True)
class GovernanceLintIssue:
    """A single governance lint finding.

    Attributes:
        rule: Name of the rule that raised this issue.
        severity: ``"error"`` or ``"warning"``.
        message: Human-readable description.
        workbook: Optional workbook path for context.
    """

    rule: str
    severity: str
    message: str
    workbook: str = ""


class GovernanceRule(ABC):
    """Abstract base class for governance rules."""

    name: str = ""
    default_severity: str = "warning"

    @abstractmethod
    def check(self, workbook: Workbook) -> list[GovernanceLintIssue]:
        """Run this rule against *workbook*.

        Args:
            workbook: The workbook to check.

        Returns:
            List of :class:`GovernanceLintIssue` findings.
        """
        ...


class NamingConventionRule(GovernanceRule):
    """Flag fields whose caption does not match a regex pattern.

    Args:
        field_pattern: Regex that valid captions must match.
        severity: Issue severity (default ``"warning"``).
    """

    name = "naming_conventions"

    def __init__(
        self,
        field_pattern: str = r"^[A-Z][a-zA-Z0-9 ]+$",
        severity: str = "warning",
    ) -> None:
        self._pattern = re.compile(field_pattern)
        self.severity = severity

    def check(self, workbook: Workbook) -> list[GovernanceLintIssue]:
        issues: list[GovernanceLintIssue] = []
        for ds in workbook.datasources:
            for f in ds.fields:
                caption = f.caption or ""
                if caption and not self._pattern.match(caption):
                    issues.append(
                        GovernanceLintIssue(
                            rule=self.name,
                            severity=self.severity,
                            message=f"Field '{caption}' in datasource '{ds.name}' does not match naming convention.",
                        )
                    )
        return issues


class NoLiveConnectionsRule(GovernanceRule):
    """Flag datasources that use live (non-extract) connections.

    Args:
        severity: Issue severity (default ``"warning"``).
    """

    name = "no_live_connections"

    def __init__(self, severity: str = "warning") -> None:
        self.severity = severity

    def check(self, workbook: Workbook) -> list[GovernanceLintIssue]:
        issues: list[GovernanceLintIssue] = []
        for ds in workbook.datasources:
            # Skip parameters datasource (class="parameters")
            if ds.name == "Parameters":
                continue
            conns = ds.connections
            if not conns:
                continue
            # Check if any connection lacks extract
            has_extract = any(
                conn.xml_node.get("class", "") == "hyper"
                or conn.xml_node.get("class", "") == "dataengine"
                for conn in conns
            )
            if not has_extract:
                issues.append(
                    GovernanceLintIssue(
                        rule=self.name,
                        severity=self.severity,
                        message=f"Datasource '{ds.name}' uses a live connection. Consider using an extract.",
                    )
                )
        return issues


class NoPIIFieldsRule(GovernanceRule):
    """Flag fields whose captions match PII-related patterns.

    Args:
        patterns: List of regex patterns (case-insensitive) to check.
        severity: Issue severity (default ``"error"``).
    """

    name = "no_pii_fields"

    def __init__(
        self,
        patterns: list[str] | None = None,
        severity: str = "error",
    ) -> None:
        self._patterns = [
            re.compile(p, re.IGNORECASE)
            for p in (patterns or ["email", "ssn", "credit.card", "password", "social.security"])
        ]
        self.severity = severity

    def check(self, workbook: Workbook) -> list[GovernanceLintIssue]:
        issues: list[GovernanceLintIssue] = []
        for ds in workbook.datasources:
            for f in ds.fields:
                caption = f.caption or ""
                for pat in self._patterns:
                    if pat.search(caption):
                        issues.append(
                            GovernanceLintIssue(
                                rule=self.name,
                                severity=self.severity,
                                message=f"Field '{caption}' in datasource '{ds.name}' may contain PII.",
                            )
                        )
                        break
        return issues


class MaxComplexityRule(GovernanceRule):
    """Flag workbooks whose complexity score exceeds a threshold.

    Args:
        max_score: Maximum allowed complexity score (default 200).
        severity: Issue severity (default ``"warning"``).
    """

    name = "max_complexity"

    def __init__(self, max_score: int = 200, severity: str = "warning") -> None:
        self.max_score = max_score
        self.severity = severity

    def check(self, workbook: Workbook) -> list[GovernanceLintIssue]:
        from pytableau.inspect.complexity import analyze_complexity

        report = analyze_complexity(workbook)
        if report.total_score > self.max_score:
            return [
                GovernanceLintIssue(
                    rule=self.name,
                    severity=self.severity,
                    message=(
                        f"Workbook complexity score {report.total_score} exceeds "
                        f"maximum {self.max_score} (grade {report.grade})."
                    ),
                )
            ]
        return []


class NoDeprecatedFunctionsRule(GovernanceRule):
    """Flag calculated fields that use deprecated Tableau functions.

    Args:
        severity: Issue severity (default ``"error"``).
    """

    name = "no_deprecated_functions"

    def __init__(self, severity: str = "error") -> None:
        self.severity = severity

    def check(self, workbook: Workbook) -> list[GovernanceLintIssue]:
        try:
            from pytableau.calculations.linter import lint_workbook
        except ImportError:
            return []

        lint_issues = lint_workbook(workbook)
        dep_issues = [i for i in lint_issues if i.rule == "deprecated_function"]
        return [
            GovernanceLintIssue(
                rule=self.name,
                severity=self.severity,
                message=i.message,
            )
            for i in dep_issues
        ]


class CustomSQLAuditRule(GovernanceRule):
    """Flag workbooks that contain custom SQL queries.

    Args:
        severity: Issue severity (default ``"warning"``).
    """

    name = "custom_sql_audit"

    def __init__(self, severity: str = "warning") -> None:
        self.severity = severity

    def check(self, workbook: Workbook) -> list[GovernanceLintIssue]:
        from pytableau.inspect.catalog import WorkbookCatalog

        cat = WorkbookCatalog(workbook)
        try:
            sql_items = cat.custom_sql_audit()
        except AttributeError:
            # Fallback: scan XML for custom SQL nodes
            sql_items = []
            for elem in workbook.xml_tree.findall(".//.//custom-sql"):
                sql_items.append({"query": elem.text or ""})

        if sql_items:
            return [
                GovernanceLintIssue(
                    rule=self.name,
                    severity=self.severity,
                    message=f"Workbook contains {len(sql_items)} custom SQL query(ies). Review for security and performance.",
                )
            ]
        return []


@dataclass
class GovernanceRuleset:
    """A collection of :class:`GovernanceRule` objects to run together.

    Attributes:
        rules: Ordered list of rules to apply.
    """

    rules: list[GovernanceRule] = field(default_factory=list)

    def check(self, workbook: Workbook) -> list[GovernanceLintIssue]:
        """Run all rules against *workbook*.

        Args:
            workbook: Workbook to lint.

        Returns:
            Flat list of all issues found.
        """
        issues: list[GovernanceLintIssue] = []
        for rule in self.rules:
            issues.extend(rule.check(workbook))
        return issues

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GovernanceRuleset:
        """Build a ruleset from a configuration dictionary.

        Expected format::

            {"rules": {"naming_conventions": {"enabled": True, ...}, ...}}

        Args:
            data: Configuration dictionary.

        Returns:
            Configured :class:`GovernanceRuleset`.
        """
        _RULE_MAP: dict[str, type[GovernanceRule]] = {
            "naming_conventions": NamingConventionRule,
            "no_live_connections": NoLiveConnectionsRule,
            "no_pii_fields": NoPIIFieldsRule,
            "max_complexity": MaxComplexityRule,
            "no_deprecated_functions": NoDeprecatedFunctionsRule,
            "custom_sql_audit": CustomSQLAuditRule,
        }
        rules_cfg: dict[str, Any] = data.get("rules", {})
        built: list[GovernanceRule] = []
        for rule_name, cfg in rules_cfg.items():
            if not cfg.get("enabled", True):
                continue
            rule_cls = _RULE_MAP.get(rule_name)
            if rule_cls is None:
                continue
            kwargs: dict[str, Any] = {k: v for k, v in cfg.items() if k not in ("enabled",)}
            built.append(rule_cls(**kwargs))
        return cls(rules=built)

    @classmethod
    def from_yaml(cls, path: str | Path) -> GovernanceRuleset:
        """Load a ruleset from a YAML file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            Configured :class:`GovernanceRuleset`.

        Raises:
            ImportError: If ``pyyaml`` is not installed
                (``pip install pytableau[governance]``).
        """
        from pytableau._compat import import_optional

        yaml = import_optional("yaml", "governance")
        text = Path(path).read_text(encoding="utf-8")
        data: dict[str, Any] = yaml.safe_load(text)
        return cls.from_dict(data)

    @classmethod
    def default(cls) -> GovernanceRuleset:
        """Return a ruleset with all six built-in rules at default configuration.

        Returns:
            :class:`GovernanceRuleset` with all rules enabled.
        """
        return cls(
            rules=[
                NamingConventionRule(),
                NoLiveConnectionsRule(),
                NoPIIFieldsRule(),
                MaxComplexityRule(),
                NoDeprecatedFunctionsRule(),
                CustomSQLAuditRule(),
            ]
        )


def lint_with_ruleset(
    workbook: Workbook, ruleset: GovernanceRuleset
) -> list[GovernanceLintIssue]:
    """Convenience wrapper: run *ruleset* against *workbook*.

    Args:
        workbook: Workbook to lint.
        ruleset: Ruleset to apply.

    Returns:
        List of governance lint issues found.
    """
    return ruleset.check(workbook)
