"""Validation rules engine — #75."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pytableau.exceptions import ValidationIssue

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


class Rule(ABC):
    """Abstract base class for a validation rule."""

    @abstractmethod
    def check(self, workbook: Workbook) -> list[ValidationIssue]:
        """Run this rule against *workbook* and return any issues found."""
        ...


class CredentialExposureRule(Rule):
    """Warn when plaintext passwords are present in connection nodes."""

    def check(self, workbook: Workbook) -> list[ValidationIssue]:
        issues = []
        for ds in workbook.datasources:
            for idx, conn in enumerate(ds.connections):
                if "password" in conn.xml_node.attrib:
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"Plaintext password found in datasource '{ds.name}' connection {idx}.",
                            path=f"/datasource[@name='{ds.name}']/connection[{idx}]/@password",
                        )
                    )
        return issues


class VersionCompatRule(Rule):
    """Warn when source-build is unrecognized."""

    def check(self, workbook: Workbook) -> list[ValidationIssue]:
        from pytableau.constants import TABLEAU_VERSION_MAP

        issues = []
        source_build = workbook.xml_root.get("source-build", "")
        if source_build and source_build not in TABLEAU_VERSION_MAP.values():
            issues.append(
                ValidationIssue(
                    "warning",
                    f"Unrecognized source-build '{source_build}'.",
                    path="/workbook/@source-build",
                )
            )
        return issues


class BracketFormattingRule(Rule):
    """Warn when field references in formulas lack brackets."""

    _UNBR = re.compile(r"(?<!\[)\b([A-Za-z][A-Za-z0-9_ ]{2,})\b(?!\])")

    def check(self, workbook: Workbook) -> list[ValidationIssue]:
        issues = []
        for ds in workbook.datasources:
            for calc in ds.calculated_fields:
                formula = calc.formula or ""
                # simple heuristic: flag formulas with likely unbracketed refs
                # (skip known functions like SUM, AVG, IF, etc.)
                _FUNCTIONS = {
                    "SUM",
                    "AVG",
                    "MIN",
                    "MAX",
                    "COUNT",
                    "IF",
                    "THEN",
                    "ELSE",
                    "END",
                    "AND",
                    "OR",
                    "NOT",
                    "FIXED",
                    "INCLUDE",
                    "EXCLUDE",
                    "ATTR",
                    "YEAR",
                    "MONTH",
                    "DAY",
                    "NOW",
                    "TODAY",
                    "IIF",
                    "ISNULL",
                    "STR",
                    "INT",
                    "FLOAT",
                    "DATE",
                    "DATEPART",
                }
                matches = self._UNBR.findall(formula)
                for m in matches:
                    if m.upper() not in _FUNCTIONS:
                        issues.append(
                            ValidationIssue(
                                "warning",
                                f"Possible unbracketed field reference '{m}' in calc '{calc.caption}'.",
                                path=f"/datasource[@name='{ds.name}']/column[@caption='{calc.caption}']",
                            )
                        )
                        break  # one warning per calc is enough
        return issues


class UnknownRootRule(Rule):
    """Error when root element is not ``<workbook>``."""

    def check(self, workbook: Workbook) -> list[ValidationIssue]:
        if workbook.xml_root.tag != "workbook":
            return [
                ValidationIssue(
                    "error",
                    f"Root element is '{workbook.xml_root.tag}', expected 'workbook'.",
                    path=f"/{workbook.xml_root.tag}",
                )
            ]
        return []


class LiveConnectionRule(Rule):
    """Warn when live (non-extract) connections are present."""

    def check(self, workbook: Workbook) -> list[ValidationIssue]:
        issues = []
        extract_classes = {"hyper", "excel-direct", "textscan", "csv"}
        for ds in workbook.datasources:
            for conn in ds.connections:
                cls = (conn.class_ or "").lower()
                if cls and cls not in extract_classes:
                    issues.append(
                        ValidationIssue(
                            "info",
                            f"Live connection '{cls}' in datasource '{ds.name}'.",
                            path=f"/datasource[@name='{ds.name}']/connection[@class='{cls}']",
                        )
                    )
        return issues


class EmptyCalcRule(Rule):
    """Warn when a calculated field has an empty formula."""

    def check(self, workbook: Workbook) -> list[ValidationIssue]:
        issues = []
        for ds in workbook.datasources:
            for calc in ds.calculated_fields:
                if not (calc.formula or "").strip():
                    issues.append(
                        ValidationIssue(
                            "warning",
                            f"Calculated field '{calc.caption}' in '{ds.name}' has an empty formula.",
                            path=f"/datasource[@name='{ds.name}']/column[@caption='{calc.caption}']",
                        )
                    )
        return issues


class AbsolutePathRule(Rule):
    """Warn when connection attributes contain absolute file paths."""

    _ABS_RE = re.compile(r"^(/|[A-Za-z]:[/\\])")

    def check(self, workbook: Workbook) -> list[ValidationIssue]:
        issues = []
        for ds in workbook.datasources:
            for conn in ds.connections:
                for attr in ("filename", "path", "dbname", "dbName"):
                    val = conn.xml_node.get(attr, "")
                    if val and self._ABS_RE.match(val):
                        issues.append(
                            ValidationIssue(
                                "warning",
                                f"Absolute path '{val}' in connection attribute '{attr}' of '{ds.name}'.",
                                path=f"/datasource[@name='{ds.name}']/connection/@{attr}",
                            )
                        )
        return issues


class MissingCaptionRule(Rule):
    """Info when fields lack a caption (shows internal name to users)."""

    def check(self, workbook: Workbook) -> list[ValidationIssue]:
        issues = []
        for ds in workbook.datasources:
            for field in ds.all_fields:
                if not field.xml_node.get("caption"):
                    issues.append(
                        ValidationIssue(
                            "info",
                            f"Field '{field.name}' in '{ds.name}' has no caption.",
                            path=f"/datasource[@name='{ds.name}']/column[@name='{field.name}']",
                        )
                    )
        return issues


class DuplicateWorksheetNameRule(Rule):
    """Error when two worksheets share the same name."""

    def check(self, workbook: Workbook) -> list[ValidationIssue]:
        seen: set[str] = set()
        issues = []
        for ws in workbook.worksheets:
            if ws.name in seen:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"Duplicate worksheet name '{ws.name}'.",
                        path=f"/worksheets/worksheet[@name='{ws.name}']",
                    )
                )
            seen.add(ws.name)
        return issues


class OdbcSecretRule(Rule):
    """Error when ODBC connect string extras contain credentials."""

    def check(self, workbook: Workbook) -> list[ValidationIssue]:
        issues = []
        for ds in workbook.datasources:
            for conn in ds.connections:
                val = conn.xml_node.get("odbc-connect-string-extras", "")
                if re.search(r"(password|pwd|secret)=", val, re.IGNORECASE):
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"ODBC connection string in '{ds.name}' contains credential.",
                            path=f"/datasource[@name='{ds.name}']/connection/@odbc-connect-string-extras",
                        )
                    )
        return issues


# ---------------------------------------------------------------------------
# ValidationProfile
# ---------------------------------------------------------------------------

_ALL_RULES: list[Rule] = [
    CredentialExposureRule(),
    VersionCompatRule(),
    BracketFormattingRule(),
    UnknownRootRule(),
    LiveConnectionRule(),
    EmptyCalcRule(),
    AbsolutePathRule(),
    MissingCaptionRule(),
    DuplicateWorksheetNameRule(),
    OdbcSecretRule(),
]

_STRICT_RULES: list[Rule] = [
    CredentialExposureRule(),
    UnknownRootRule(),
    EmptyCalcRule(),
    DuplicateWorksheetNameRule(),
    OdbcSecretRule(),
]


class ValidationProfile:
    """A named collection of :class:`Rule` instances."""

    def __init__(self, rules: list[Rule]) -> None:
        self.rules = list(rules)

    def check(self, workbook: Workbook) -> list[ValidationIssue]:
        """Run all rules and return combined issues."""
        issues: list[ValidationIssue] = []
        for rule in self.rules:
            issues.extend(rule.check(workbook))
        return issues

    @classmethod
    def strict(cls) -> ValidationProfile:
        """Return the strict profile (errors only, no informational rules)."""
        return cls(list(_STRICT_RULES))

    @classmethod
    def for_version(cls, version: str) -> ValidationProfile:
        """Return a profile appropriate for *version* (currently returns default)."""
        return cls(list(_ALL_RULES))

    @classmethod
    def default(cls) -> ValidationProfile:
        """Return the default profile with all built-in rules."""
        return cls(list(_ALL_RULES))
