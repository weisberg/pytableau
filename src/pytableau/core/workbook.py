"""Workbook: top-level entry point for pytableau operations."""

from __future__ import annotations

import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from lxml import etree

from pytableau.constants import DEFAULT_TABLEAU_VERSION, TABLEAU_VERSION_MAP
from pytableau.exceptions import (
    CorruptWorkbookError,
    InvalidWorkbookError,
    SchemaValidationError,
)
from pytableau.inspect.catalog import WorkbookCatalog
from pytableau.inspect.lineage import FieldLineage
from pytableau.inspect.report import WorkbookReport
from pytableau.package.manager import PackageManager
from pytableau.xml.engine import XMLSchemaEngine
from pytableau.templates.engine import TemplateEngine
from pytableau.templates.library import get_template_path

from .dashboard import Dashboard, DashboardCollection
from .datasource import Datasource, DatasourceCollection
from .worksheet import Worksheet, WorksheetCollection

if TYPE_CHECKING:
    from pytableau.exceptions import ValidationIssue


_SOURCE_BUILD_TO_VERSION = {v: k for k, v in TABLEAU_VERSION_MAP.items()}


def _normalize_version(source_build: str | None) -> str:
    if not source_build:
        return DEFAULT_TABLEAU_VERSION
    if source_build in TABLEAU_VERSION_MAP:
        return source_build
    if source_build in _SOURCE_BUILD_TO_VERSION:
        return _SOURCE_BUILD_TO_VERSION[source_build]
    return DEFAULT_TABLEAU_VERSION


def _collect_top_level(parent: etree._Element, tag: str) -> list[etree._Element]:
    container = parent.find(f"{tag}s")
    if container is not None:
        return [node for node in container if node.tag == tag]
    return list(parent.findall(tag))


class Workbook:
    """Top-level entry point for all pytableau operations."""

    def __init__(self) -> None:
        self._path: Path | None = None
        self._package_manager: PackageManager | None = None
        self._tree: etree._ElementTree
        self._version = DEFAULT_TABLEAU_VERSION
        self.source_platform: str | None = None
        self.datasources: DatasourceCollection = DatasourceCollection([])
        self.worksheets: WorksheetCollection = WorksheetCollection([])
        self.dashboards: DashboardCollection = DashboardCollection([])
        self.parameters: Datasource | None = None
        self._template_engine: TemplateEngine | None = None

    @property
    def version(self) -> str:
        return self._version

    def close(self) -> None:
        """Release package-management resources, if any."""
        if self._package_manager is not None:
            self._package_manager.close()
            self._package_manager = None

    def __enter__(self) -> "Workbook":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def xml_root(self) -> etree._Element:
        return self.xml_tree.getroot()

    @property
    def xml_tree(self) -> etree._ElementTree:
        return self._tree

    @classmethod
    def open(cls, path: str | Path) -> "Workbook":
        """Open an existing ``.twb`` or ``.twbx`` file."""
        workbook_path = Path(path).expanduser()
        manager = PackageManager(workbook_path)
        try:
            twb_path = manager.twb_path
        except (OSError, ValueError) as exc:
            raise InvalidWorkbookError(f"Unable to open workbook: {workbook_path}") from exc

        try:
            tree = etree.parse(str(twb_path))
        except (OSError, etree.XMLSyntaxError) as exc:
            manager.close()
            raise CorruptWorkbookError(f"Workbook XML cannot be parsed: {twb_path}") from exc

        root = tree.getroot()
        if root.tag != "workbook":
            manager.close()
            raise InvalidWorkbookError(f"Not a Tableau workbook file: {workbook_path}")

        wb = cls()
        wb._path = workbook_path
        wb._package_manager = manager
        wb._load_tree(tree)
        return wb

    @classmethod
    def new(cls, version: str = DEFAULT_TABLEAU_VERSION) -> "Workbook":
        """Create a new, empty workbook."""
        source_build = TABLEAU_VERSION_MAP.get(
            version,
            TABLEAU_VERSION_MAP[DEFAULT_TABLEAU_VERSION],
        )
        root = etree.Element(
            "workbook",
            attrib={
                "source-build": source_build,
                "source-platform": "python",
            },
        )
        etree.SubElement(root, "datasources")
        etree.SubElement(root, "worksheets")
        etree.SubElement(root, "dashboards")
        tree = etree.ElementTree(root)

        wb = cls()
        wb._load_tree(tree)
        return wb

    @classmethod
    def from_template(cls, template: str | Path, **kwargs: object) -> "Workbook":
        """Construct a workbook from a built-in or custom template."""
        template_path = Path(template).expanduser() if isinstance(template, Path) else Path(str(template))
        if not template_path.suffix:
            template_path = get_template_path(str(template))
        elif template_path.suffix.lower() != ".twb":
            raise InvalidWorkbookError("Template path must point to a .twb file")

        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        try:
            tree = etree.parse(str(template_path))
        except (OSError, etree.XMLSyntaxError) as exc:
            raise InvalidWorkbookError(f"Unable to parse template workbook: {template_path}") from exc

        wb = cls()
        wb._load_tree(tree)
        wb._template_engine = TemplateEngine(tree)
        if kwargs:
            wb._template_engine.map_fields(
                {str(k): str(v) for k, v in kwargs.items()},
                strict=False,
            )
        return wb

    @property
    def template(self) -> TemplateEngine:
        if self._template_engine is None:
            self._template_engine = TemplateEngine(self._tree)
        return self._template_engine

    def migrate_version(self, version: str) -> None:
        """Update workbook metadata for a different Tableau version."""
        source_build = TABLEAU_VERSION_MAP.get(version)
        if source_build is None:
            raise ValueError(f"Unsupported Tableau version: {version}")
        self._version = version
        self.xml_root.set("source-build", source_build)

    def merge(self, other: "Workbook", *, conflict_suffix: str = " (imported)") -> None:
        """Merge datasource, worksheet, and dashboard nodes from another workbook."""
        if not isinstance(other, Workbook):
            raise TypeError("Workbook.merge() accepts only Workbook instances")
        self._merge_collection(self.xml_root, other.xml_root, "datasource")
        self._merge_collection(self.xml_root, other.xml_root, "worksheet")
        self._merge_collection(self.xml_root, other.xml_root, "dashboard")
        self._load_tree(self.xml_tree)

    def _merge_collection(
        self,
        target_root: etree._Element,
        source_root: etree._Element,
        tag: str,
        *,
        container_name: str | None = None,
        key_attr: str = "name",
        conflict_suffix: str = " (imported)",
    ) -> None:
        source_container = source_root.find(f"{container_name or tag}s")
        if source_container is None:
            return
        target_container = target_root.find(f"{container_name or tag}s")
        if target_container is None:
            target_container = etree.SubElement(target_root, f"{container_name or tag}s")

        existing_names = {node.get(key_attr, "") for node in target_container.findall(tag)}
        for node in source_container.findall(tag):
            clone = etree.fromstring(etree.tostring(node))
            name = node.get(key_attr)
            if name is not None and name in existing_names:
                clone.set(key_attr, f"{name}{conflict_suffix}")
            target_container.append(clone)

    def catalog(self) -> WorkbookCatalog:
        """Collect metadata and field references for read-only inspection."""
        return WorkbookCatalog(self)

    def lineage(self) -> FieldLineage:
        """Build a calculated-field dependency graph."""
        return FieldLineage(self)

    def report(self) -> WorkbookReport:
        """Generate documentation content for the workbook."""
        return WorkbookReport(self)

    def _load_tree(self, tree: etree._ElementTree) -> None:
        self._tree = tree
        root = tree.getroot()
        source_build = root.get("source-build")
        self._version = _normalize_version(source_build)
        self.source_platform = root.get("source-platform")

        datasources: list[Datasource] = []
        parameters: Datasource | None = None
        for node in _collect_top_level(root, "datasource"):
            ds = Datasource(node, workbook=self)
            if ds.is_parameters:
                parameters = ds
                continue
            datasources.append(ds)
        self.parameters = parameters
        self.datasources = DatasourceCollection(datasources)

        worksheets: list[Worksheet] = []
        for node in _collect_top_level(root, "worksheet"):
            worksheets.append(Worksheet(node, workbook=self))
        self.worksheets = WorksheetCollection(worksheets)

        dashboards: list[Dashboard] = []
        for node in _collect_top_level(root, "dashboard"):
            dashboards.append(Dashboard(node, workbook=self))
        self.dashboards = DashboardCollection(dashboards)

    def _validate_for_save(self) -> list["ValidationIssue"]:
        engine = XMLSchemaEngine(self.version)
        return engine.validate_workbook(self._tree)

    def _write_twb(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._tree.write(
            str(path),
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True,
        )

    def save(self) -> None:
        """Save the workbook to its original path."""
        if not self._path:
            raise InvalidWorkbookError("Workbook path is unknown; use save_as().")

        self.save_as(self._path)

    def save_as(self, path: str | Path) -> None:
        """Save the workbook to a new path."""
        destination = Path(path).expanduser()
        if destination.suffix.lower() not in {".twb", ".twbx"}:
            raise InvalidWorkbookError("Workbook path must end with .twb or .twbx")

        issues = self._validate_for_save()
        for issue in issues:
            if issue.level == "error":
                raise SchemaValidationError(f"Workbook is invalid: {issue}")

        if self._package_manager is not None:
            working_twb = self._package_manager.twb_path
            self._write_twb(working_twb)
            self._package_manager.save_as(destination)
            self._path = destination
            return

        if destination.suffix.lower() == ".twb":
            self._write_twb(destination)
            self._path = destination
            return

        with TemporaryDirectory(prefix="pytableau-") as temp_dir:
            work_twb = Path(temp_dir) / "workbook.twb"
            self._write_twb(work_twb)
            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(work_twb, work_twb.name)

        self._path = destination

    def publish(self, server: str, project: str, **auth: object) -> None:
        """Publish this workbook to Tableau Server or Cloud."""
        from pytableau.server.client import ServerClient

        if self._path is None:
            with TemporaryDirectory(prefix="pytableau-") as temp_dir:
                publish_path = Path(temp_dir) / "workbook.twbx"
                self.save_as(publish_path)
                with ServerClient(server, **auth) as client:
                    client.publish_workbook(publish_path, project_id=project)
                return

        with TemporaryDirectory(prefix="pytableau-") as temp_dir:
            publish_path = Path(temp_dir) / "workbook.twbx"
            self.save_as(publish_path)
            with ServerClient(server, **auth) as client:
                client.publish_workbook(publish_path, project_id=project)

    def download(self, server: str, workbook_id: str, **auth: object) -> "Workbook":
        """Download a workbook from Tableau Server or Cloud and return it as a Workbook."""
        from pytableau.server.client import ServerClient

        with TemporaryDirectory(prefix="pytableau-") as temp_dir:
            downloaded = Path(temp_dir) / f"{workbook_id}.twb"
            with ServerClient(server, **auth) as client:
                client.download_workbook(workbook_id, destination=downloaded)
            return self.__class__.open(downloaded)

    def __del__(self) -> None:
        self.close()

    def to_xml_string(self) -> str:
        """Serialize workbook XML as a UTF-8 string."""
        xml = etree.tostring(
            self._tree.getroot(),
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True,
        )
        return xml.decode("utf-8")

    def validate(self) -> list["ValidationIssue"]:
        """Validate the workbook XML against known schema rules."""
        return self._validate_for_save()
