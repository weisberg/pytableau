"""Semantic diagnostics and conservative, capability-based compatibility."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree

from pytableau.constants import TABLEAU_VERSION_MAP
from pytableau.core.references import FieldReference
from pytableau.exceptions import SchemaValidationError, ValidationIssue

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


@dataclass(frozen=True)
class Capability:
    name: str
    minimum_version: str
    xpath: str
    source: str = ""


# Public Tableau features, not a claim to have a complete proprietary XML schema.
CAPABILITIES = (
    Capability(
        "relationships",
        "2020.2",
        ".//object-graph/relationships/relationship",
        "https://help.tableau.com/current/pro/desktop/en-us/relate_tables.htm",
    ),
    Capability(
        "multi_fact_relationships",
        "2024.2",
        ".//document-format-change[@name='MultiFactRelationships'] | .//document-format-change-manifest/MultiFactRelationships",
        "https://help.tableau.com/current/pro/desktop/en-us/datasource_multitable_analysis_overview.htm",
    ),
    Capability(
        "dynamic_zone_visibility",
        "2022.3",
        ".//zone[@visibility-variable]",
        "https://help.tableau.com/current/pro/desktop/en-us/dynamic_zone_visibility.htm",
    ),
    Capability(
        "viz_extensions",
        "2024.2",
        ".//mark[@class='Extension']",
        "https://help.tableau.com/current/pro/desktop/en-us/viz_extensions.htm",
    ),
)


@dataclass(frozen=True)
class CompatibilityIssue:
    feature: str
    status: str
    message: str
    source: str = ""


@dataclass
class CompatibilityReport:
    source_version: str
    target_version: str
    issues: list[CompatibilityIssue] = field(default_factory=list)
    detected_features: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(i.status == "unsupported" for i in self.issues):
            return "unsupported"
        if any(i.status == "unverified" for i in self.issues):
            return "unverified"
        return "supported"

    @property
    def compatible(self) -> bool:
        return self.status == "supported"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "status": self.status, "compatible": self.compatible}


def compatibility(
    workbook: Workbook, target: str, capabilities: tuple[Capability, ...] = CAPABILITIES
) -> CompatibilityReport:
    report = CompatibilityReport(workbook.version, target)
    if target not in TABLEAU_VERSION_MAP:
        report.issues.append(
            CompatibilityIssue("version", "unsupported", f"Unknown target {target}")
        )
        return report
    known_flags = set()
    for capability in capabilities:
        if workbook.xml_root.xpath(capability.xpath):
            report.detected_features.append(capability.name)
            if version_key(target) < version_key(capability.minimum_version):
                report.issues.append(
                    CompatibilityIssue(
                        capability.name,
                        "unsupported",
                        f"Requires Tableau {capability.minimum_version} or later",
                        capability.source,
                    )
                )
        # Explicit registration is how unknown format flags gain a verified minimum.
        nodes = workbook.xml_root.xpath(capability.xpath)
        for node in nodes if isinstance(nodes, list) else []:
            if isinstance(node, etree._Element):
                if node.tag == "document-format-change":
                    known_flags.add(node.get("name"))
                else:
                    parent = node.getparent()
                    if parent is not None and parent.tag == "document-format-change-manifest":
                        known_flags.add(node.tag)
    # Extract formats have independent product compatibility. Inspect real files
    # when an old target could exclude newer numeric/file-format capabilities.
    if version_key(target) < version_key("2024.3"):
        checked = set()
        for datasource in workbook.datasources:
            path = datasource._hyper_path
            if path is None or path in checked or not path.is_file():
                continue
            checked.add(path)
            source = "https://tableau.github.io/hyper-db/docs/hyper-api/hyper_process/#default_database_version"
            try:
                from pytableau.data.bridge import HyperBridge

                with HyperBridge(path)._connection() as connection:
                    format_version = int(
                        connection.execute_scalar_query(
                            "SELECT database_version FROM pg_catalog.hyper_database"
                        )
                    )
                minimum = {3: "2023.1", 4: "2024.3"}.get(format_version)
                if minimum and version_key(target) < version_key(minimum):
                    report.issues.append(
                        CompatibilityIssue(
                            "hyper_format",
                            "unsupported",
                            f"Extract format {format_version} requires Tableau {minimum} or later for Server compatibility",
                            source,
                        )
                    )
            except Exception as error:
                report.issues.append(
                    CompatibilityIssue(
                        "hyper_format",
                        "unverified",
                        f"Cannot inspect extract format: {error}",
                        source,
                    )
                )
    if version_key(target) < version_key(workbook.version):
        flags = workbook.xml_root.findall(".//document-format-change") + workbook.xml_root.findall(
            ".//document-format-change-manifest/*"
        )
        for flag in flags:
            if not isinstance(flag.tag, str):
                continue
            name = flag.get("name", "unnamed") if flag.tag == "document-format-change" else flag.tag
            if name not in known_flags:
                report.issues.append(
                    CompatibilityIssue(
                        name,
                        "unverified",
                        "No verified capability rule for this format change; downgrade cannot be certified",
                    )
                )
        # XML feature detection is deliberately incomplete. Header changes do not convert XML.
        report.issues.append(
            CompatibilityIssue(
                "xml_conversion",
                "unverified",
                "Downgrade requires Tableau acceptance; pytableau preserves XML and cannot convert every feature",
            )
        )
    return report


def require_compatibility(report: CompatibilityReport, *, allow_unverified: bool = False) -> None:
    if report.status == "unsupported" or (report.status == "unverified" and not allow_unverified):
        raise SchemaValidationError("; ".join(f"{i.feature}: {i.message}" for i in report.issues))


def validate_semantics(workbook: Workbook) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def issue(message: str, path: str, level: str = "error") -> None:
        issues.append(ValidationIssue(level, message, path=path))

    for compatibility_issue in compatibility(workbook, workbook.version).issues:
        if compatibility_issue.status == "unsupported":
            issue(compatibility_issue.message, "/workbook")
    graph = workbook.references()
    for use in graph.uses:
        if use.error:
            level = (
                "warning"
                if use.kind == "formatted_text" or use.reference.name.startswith("Action (")
                else "error"
            )
            issue(use.error, use.path, level)
    for ws in workbook.worksheets:
        for source in ws.datasource_dependencies:
            if not any(source in {ds.name, ds.caption} for ds in graph._sources):
                issue(
                    f"Unknown worksheet datasource {source!r}",
                    workbook.xml_tree.getpath(ws.xml_node),
                )
    # Cycle detection operates on resolved identities, never caption substrings.
    edges: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for use in graph.uses:
        owner = graph._calc_owners.get(use.path)
        if owner and use.datasource and use.field_id and not use.error:
            edges.setdefault(owner, set()).add((use.datasource, use.field_id))
    active: set[tuple[str, str]] = set()
    visited: set[tuple[str, str]] = set()

    def visit(key: tuple[str, str]) -> None:
        if key in active:
            issue(
                f"Calculation dependency cycle involving {key[0]}.{key[1]}", "/workbook/datasources"
            )
            return
        if key in visited:
            return
        active.add(key)
        for dependency in edges.get(key, set()):
            visit(dependency)
        active.remove(key)
        visited.add(key)

    for key in edges:
        visit(key)
    for ds in graph._sources:
        objects = ds.xml_node.findall(".//object-graph/objects/object")
        ids = [n.get("id") for n in objects]
        if len(ids) != len(set(ids)):
            issue("Duplicate logical table object IDs", workbook.xml_tree.getpath(ds.xml_node))
        for relation in ds.xml_node.findall(".//relation[@type='join']"):
            if len(relation.findall("relation")) != 2 or relation.find("clause/expression") is None:
                issue(
                    "Join requires two relations and a predicate",
                    workbook.xml_tree.getpath(relation),
                )
            if relation.get("join") not in {"inner", "left", "right", "full"}:
                issue("Unsupported join type", workbook.xml_tree.getpath(relation))
        connection_ids = {n.get("name") for n in ds.xml_node.findall(".//named-connection")}
        for relation in ds.xml_node.findall(".//relation[@connection]"):
            if relation.get("connection") not in connection_ids:
                issue(
                    "Relation references a missing named connection",
                    workbook.xml_tree.getpath(relation),
                )
        field_names = {f.name.strip("[]") for f in ds.all_fields}
        for relation in ds.xml_node.findall(".//relation[@type='join']"):
            aliases = {n.get("name") for n in relation.findall(".//relation") if n.get("name")}
            for expression in relation.findall("clause//expression"):
                value = expression.get("op", "")
                if value.startswith("["):
                    ref = FieldReference.parse(value)
                    if ref.datasource not in aliases:
                        issue(
                            "Join key references a missing relation alias",
                            workbook.xml_tree.getpath(expression),
                        )
                    if ref.name not in field_names:
                        issue(
                            f"Unknown join key {ref.name!r}", workbook.xml_tree.getpath(expression)
                        )
        for relationship in ds.xml_node.findall(".//relationships/relationship"):
            for endpoint in ("first-end-point", "second-end-point"):
                node = relationship.find(endpoint)
                if node is None or node.get("object-id") not in ids:
                    issue(
                        "Relationship references a missing logical table",
                        workbook.xml_tree.getpath(relationship),
                    )
            for expression in relationship.findall(".//expression"):
                value = expression.get("op", "")
                if value.startswith("["):
                    ref = FieldReference.parse(value)
                    if ref.name not in field_names:
                        issue(
                            f"Unknown relationship key {ref.name!r}",
                            workbook.xml_tree.getpath(expression),
                        )
            if relationship.find("expression") is None:
                issue("Relationship requires a predicate", workbook.xml_tree.getpath(relationship))
    for instance in workbook.xml_root.findall(".//column-instance"):
        if instance.get("type") not in {None, "nominal", "ordinal", "quantitative"}:
            issue("Invalid native column-instance type", workbook.xml_tree.getpath(instance))
    for pane in workbook.xml_root.findall(".//pane"):
        for attr in ("x-axis-name", "y-axis-name"):
            if pane.get(attr):
                try:
                    FieldReference.parse(pane.get(attr, ""))
                except ValueError:
                    issue(f"Invalid {attr}", workbook.xml_tree.getpath(pane))
    for calc in workbook.xml_root.findall(".//table-calc"):
        addressing = {n.get("field") for n in calc.findall("addressing/field")}
        partitioning = {n.get("field") for n in calc.findall("partitioning/field")}
        if addressing & partitioning:
            issue(
                "Table calculation addressing and partitioning overlap",
                workbook.xml_tree.getpath(calc),
            )
    # Asset existence is checked without opening Hyper (optional dependency).
    pm = workbook._package_manager
    root = pm.twb_path.parent if pm else (workbook._path.parent if workbook._path else None)
    if root:
        for conn in workbook.xml_root.findall(".//connection[@filename]"):
            filename = conn.get("filename", "")
            if filename and not Path(filename).is_absolute() and not (root / filename).is_file():
                issue(f"Missing connection asset {filename!r}", workbook.xml_tree.getpath(conn))
    return issues
