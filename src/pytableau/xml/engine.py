"""XML schema validation and version-aware compatibility helpers."""

from __future__ import annotations

from lxml import etree

from pytableau.constants import (
    DEFAULT_TABLEAU_VERSION,
    TABLEAU_VERSION_MAP,
    ValidationLevel,
)
from pytableau.exceptions import ValidationIssue

_KNOWN_TAGS = {
    "workbook",
    "datasources",
    "datasource",
    "relations",
    "relation",
    "worksheets",
    "worksheet",
    "dashboards",
    "dashboard",
    "column",
    "parameter",
    "filter",
}


class XMLSchemaEngine:
    """Validates XML mutations against known Tableau schema rules."""

    def __init__(self, version: str = DEFAULT_TABLEAU_VERSION) -> None:
        self.version = version
        self.unknown_elements: set[str] = set()

    def _normalise_version(self, version: str | None) -> str:
        if not version:
            return self.version
        if version in TABLEAU_VERSION_MAP:
            return version
        if version in TABLEAU_VERSION_MAP.values():
            return next(
                (k for k, v in TABLEAU_VERSION_MAP.items() if v == version),
                self.version,
            )
        return self.version

    def validate_element(
        self,
        tag: str,
        parent_tag: str,
        attributes: dict[str, str],
        version: str | None = None,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        resolved_version = self._normalise_version(version)

        if tag not in _KNOWN_TAGS:
            self.unknown_elements.add(tag)
            issues.append(
                ValidationIssue(
                    ValidationLevel.INFO.value,
                    f"Unknown Tableau XML tag '{tag}' under <{parent_tag}>.",
                    path=f"/{parent_tag}/{tag}",
                )
            )

        if resolved_version not in TABLEAU_VERSION_MAP:
            issues.append(
                ValidationIssue(
                    ValidationLevel.WARNING.value,
                    f"Unknown or unsupported Tableau version '{resolved_version}'.",
                    path=f"/{parent_tag}/{tag}",
                )
            )

        if tag == "workbook" and "name" in attributes:
            issues.append(
                ValidationIssue(
                    ValidationLevel.INFO.value,
                    "Workbench 'name' attribute on <workbook> is ignored by Tableau.",
                    path=f"/{tag}",
                )
            )

        return issues

    def validate_workbook(self, tree: etree._ElementTree) -> list[ValidationIssue]:
        root = tree.getroot()
        issues: list[ValidationIssue] = []

        if root.tag != "workbook":
            issues.append(
                ValidationIssue(
                    ValidationLevel.ERROR.value,
                    f"Invalid Tableau root node '{root.tag}'. Expected <workbook>.",
                    path=f"/{root.tag}",
                )
            )
            return issues

        issues.extend(self.validate_element("workbook", "/", root.attrib, self.version))

        for node in root.iterchildren():
            if node.tag not in {"datasources", "worksheets", "dashboards"}:
                continue
            for child in node.iterchildren():
                issues.extend(
                    self.validate_element(child.tag, node.tag, dict(child.attrib), self.version)
                )

        source_build = root.attrib.get("source-build")
        if source_build and source_build not in TABLEAU_VERSION_MAP.values():
            issues.append(
                ValidationIssue(
                    ValidationLevel.WARNING.value,
                    f"Workbook source-build '{source_build}' is not recognized.",
                    path="/workbook/@source-build",
                )
            )

        return issues

    def is_compatible(self, tree: etree._ElementTree, target_version: str) -> bool:
        issues = self.validate_workbook(tree)
        is_known_target = target_version in TABLEAU_VERSION_MAP
        if not is_known_target:
            return False
        return all(issue.level != ValidationLevel.ERROR.value for issue in issues)
