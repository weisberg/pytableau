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
from pytableau.package.manager import PackageManager
from pytableau.xml.engine import XMLSchemaEngine

if TYPE_CHECKING:
    from pytableau.exceptions import ValidationIssue


_SOURCE_BUILD_TO_VERSION = {v: k for k, v in TABLEAU_VERSION_MAP.items()}


class _XMLCollection:
    """Small helper for workbook-level collections like datasources/worksheets."""

    def __init__(self, nodes: list[etree._Element]) -> None:
        self._nodes = nodes

    @property
    def names(self) -> list[str]:
        return [node.get("name", "") for node in self._nodes if node.get("name")]

    def __iter__(self):
        return iter(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)

    def __getitem__(self, key: int | str) -> etree._Element:
        if isinstance(key, int):
            return self._nodes[key]
        if not isinstance(key, str):
            raise TypeError("collection keys must be int index or element name")

        for node in self._nodes:
            if node.get("name") == key:
                return node
        raise KeyError(key)


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
        return list(container.findall(tag))

    return list(parent.findall(tag))


class Workbook:
    """Top-level entry point for all pytableau operations."""

    def __init__(self) -> None:
        self._path: Path | None = None
        self._package_manager: PackageManager | None = None
        self._tree: etree._ElementTree
        self._version = DEFAULT_TABLEAU_VERSION
        self.source_platform: str | None = None
        self.datasources = _XMLCollection([])
        self.worksheets = _XMLCollection([])
        self.dashboards = _XMLCollection([])
        self._node_map: dict[str, etree._Element] = {}

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
            version, TABLEAU_VERSION_MAP[DEFAULT_TABLEAU_VERSION]
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
        wb._version = version
        wb._load_tree(tree)
        return wb

    @classmethod
    def from_template(cls, template: str | Path, **kwargs: object) -> "Workbook":
        """Construct a workbook from a built-in or custom template."""
        raise NotImplementedError("Workbook.from_template() is implemented in Phase 4")

    def _load_tree(self, tree: etree._ElementTree) -> None:
        self._tree = tree
        root = tree.getroot()
        source_build = root.get("source-build")
        self._version = _normalize_version(source_build)
        self.source_platform = root.get("source-platform")

        self.datasources = _XMLCollection(_collect_top_level(root, "datasource"))
        self.worksheets = _XMLCollection(_collect_top_level(root, "worksheet"))
        self.dashboards = _XMLCollection(_collect_top_level(root, "dashboard"))
        self._node_map = {
            node.get("name", f"{node.tag}:{i}"): node for i, node in enumerate(root.iter())
            if node.get("name")
        }

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

        errors = self._validate_for_save()
        for issue in errors:
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
