"""Workbook: top-level entry point for pytableau operations."""

from __future__ import annotations

import warnings
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, NamedTuple

from lxml import etree

from pytableau.constants import DEFAULT_TABLEAU_VERSION, TABLEAU_VERSION_MAP
from pytableau.exceptions import (
    CorruptWorkbookError,
    InvalidWorkbookError,
    LazyNotMaterializedError,
    SchemaValidationError,
)
from pytableau.inspect.catalog import WorkbookCatalog
from pytableau.inspect.lineage import FieldLineage
from pytableau.inspect.report import WorkbookReport
from pytableau.package.manager import PackageManager
from pytableau.templates.engine import TemplateEngine
from pytableau.templates.library import get_template_path
from pytableau.xml.engine import XMLSchemaEngine

from .dashboard import Dashboard, DashboardCollection
from .datasource import Datasource, DatasourceCollection
from .worksheet import Worksheet, WorksheetCollection

if TYPE_CHECKING:
    from pytableau.agents.transactions import WorkbookTransaction
    from pytableau.exceptions import ValidationIssue
    from pytableau.inspect.diff import Patch, WorkbookDiff
    from pytableau.package.promotion import PromotionChange, PromotionConfig


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


# ---------------------------------------------------------------------------
# Lazy sentinel collections for streaming mode (#61)
# ---------------------------------------------------------------------------


class _LazyWorksheetCollection:
    """Placeholder collection that raises when accessed in streaming mode."""

    def __iter__(self):
        raise LazyNotMaterializedError(
            "Worksheets are not loaded in streaming mode. "
            "Open without streaming=True to access worksheets."
        )

    def __len__(self) -> int:
        raise LazyNotMaterializedError("Worksheets are not loaded in streaming mode.")

    def __getitem__(self, key):
        raise LazyNotMaterializedError("Worksheets are not loaded in streaming mode.")

    @property
    def names(self) -> list[str]:
        raise LazyNotMaterializedError("Worksheets are not loaded in streaming mode.")


class _LazyDashboardCollection:
    """Placeholder collection that raises when accessed in streaming mode."""

    def __iter__(self):
        raise LazyNotMaterializedError(
            "Dashboards are not loaded in streaming mode. "
            "Open without streaming=True to access dashboards."
        )

    def __len__(self) -> int:
        raise LazyNotMaterializedError("Dashboards are not loaded in streaming mode.")

    def __getitem__(self, key):
        raise LazyNotMaterializedError("Dashboards are not loaded in streaming mode.")

    @property
    def names(self) -> list[str]:
        raise LazyNotMaterializedError("Dashboards are not loaded in streaming mode.")


# ---------------------------------------------------------------------------
# swap_connection result type (#79)
# ---------------------------------------------------------------------------


class SwapResult(NamedTuple):
    updated_count: int
    skipped_count: int
    details: list[dict]


# ---------------------------------------------------------------------------
# Workbook
# ---------------------------------------------------------------------------


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
        self._is_streaming: bool = False

    @property
    def version(self) -> str:
        return self._version

    def close(self) -> None:
        """Release package-management resources, if any."""
        if self._package_manager is not None:
            self._package_manager.close()
            self._package_manager = None

    def __enter__(self) -> Workbook:
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
    def open(
        cls,
        path: str | Path,
        *,
        strict: bool = False,
        compatibility: bool = False,
        streaming: bool = False,
        twb_hint: str | None = None,
    ) -> Workbook:
        """Open an existing ``.twb`` or ``.twbx`` file.

        Args:
            path: Path to the workbook file.
            strict: If ``True``, reject huge trees (>500 000 nodes) and unknown
                root elements outright.
            compatibility: If ``True``, issue a warning (instead of raising) for
                non-``workbook`` root elements.
            streaming: If ``True``, only parse datasources; worksheets and
                dashboards are replaced by lazy sentinel collections.
            twb_hint: Filename hint for resolving ambiguous multi-TWB archives.
        """
        workbook_path = Path(path).expanduser()
        manager = PackageManager(workbook_path, twb_hint=twb_hint)
        try:
            twb_path = manager.twb_path
        except (OSError, ValueError) as exc:
            raise InvalidWorkbookError(f"Unable to open workbook: {workbook_path}") from exc

        # Hardened parser (#57)
        _parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            huge_tree=not strict,
        )
        try:
            tree = etree.parse(str(twb_path), parser=_parser)
        except (OSError, etree.XMLSyntaxError) as exc:
            manager.close()
            raise CorruptWorkbookError(f"Workbook XML cannot be parsed: {twb_path}") from exc

        root = tree.getroot()

        # Strict mode: node count limit
        if strict:
            node_count = sum(1 for _ in root.iter())
            if node_count > 500_000:
                manager.close()
                raise InvalidWorkbookError(
                    f"Workbook exceeds 500 000 nodes ({node_count}) in strict mode."
                )

        if root.tag != "workbook":
            if compatibility:
                warnings.warn(
                    f"Expected <workbook> root element, found <{root.tag}>. "
                    "Processing with compatibility mode.",
                    stacklevel=2,
                )
            elif not strict:
                manager.close()
                raise InvalidWorkbookError(f"Not a Tableau workbook file: {workbook_path}")
            else:
                manager.close()
                raise InvalidWorkbookError(f"Not a Tableau workbook file: {workbook_path}")

        wb = cls()
        wb._path = workbook_path
        wb._package_manager = manager

        if streaming:
            wb._is_streaming = True
            wb._tree = tree
            wb._load_datasources_only(tree)
            wb.worksheets = _LazyWorksheetCollection()  # type: ignore[assignment]
            wb.dashboards = _LazyDashboardCollection()  # type: ignore[assignment]
            return wb

        wb._load_tree(tree)
        return wb

    def _load_datasources_only(self, tree: etree._ElementTree) -> None:
        """Parse only datasources (used in streaming mode)."""
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

    @classmethod
    def new(cls, version: str = DEFAULT_TABLEAU_VERSION) -> Workbook:
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

    def add_worksheet(self, worksheet: Any) -> None:
        """Add a worksheet to this workbook.

        Args:
            worksheet: Either a :class:`~pytableau.build.worksheet.WorksheetBuilder`
                instance (``build()`` is called automatically) or a raw
                ``lxml.etree._Element`` node.
        """
        from lxml import etree as _etree

        if hasattr(worksheet, "build"):
            node: _etree._Element = worksheet.build()
        else:
            node = worksheet

        container = self.xml_root.find("worksheets")
        if container is None:
            container = _etree.SubElement(self.xml_root, "worksheets")
        container.append(node)
        self._load_tree(self.xml_tree)

    def add_dashboard(self, dashboard: Any) -> None:
        """Add a dashboard to this workbook.

        Args:
            dashboard: Either a :class:`~pytableau.build.dashboard.DashboardBuilder`
                instance (``build()`` is called automatically) or a raw
                ``lxml.etree._Element`` node.
        """
        from lxml import etree as _etree

        if hasattr(dashboard, "build"):
            node: _etree._Element = dashboard.build()
        else:
            node = dashboard

        container = self.xml_root.find("dashboards")
        if container is None:
            container = _etree.SubElement(self.xml_root, "dashboards")
        container.append(node)
        self._load_tree(self.xml_tree)

    def describe(self) -> dict[str, Any]:
        """Return a complete structured schema of this workbook as a plain dict.

        Delegates to :func:`pytableau.agents.discovery.describe`.
        Safe to serialise to JSON; ideal for AI agents that need a quick overview.
        """
        from pytableau.agents.discovery import describe as _describe

        return _describe(self)

    def capabilities(self) -> dict[str, Any]:
        """Return a capability summary for this workbook.

        Checks which optional extras are installed and summarises the workbook
        contents.  Delegates to :func:`pytableau.agents.discovery.capabilities`.
        """
        from pytableau.agents.discovery import capabilities as _capabilities

        return _capabilities(self)

    def transaction(self) -> WorkbookTransaction:
        """Return an atomic transaction context manager for this workbook.

        On entry the XML tree is deep-copied.  If an exception propagates
        through the ``with`` block the tree is restored, leaving the workbook
        completely unchanged::

            with wb.transaction() as tx:
                tx.rename_field("Sales", "Rev", "Revenue")
                tx.add_calculated_field("Sales", "Margin", "[Revenue] - [Cost]")
        """
        from pytableau.agents.transactions import WorkbookTransaction

        return WorkbookTransaction(self)

    @classmethod
    def from_spec(cls, spec: Any) -> Workbook:
        """Build a complete workbook from a spec dict, YAML file, or JSON file.

        Convenience classmethod that delegates to
        :func:`pytableau.build.spec.from_spec`.

        Args:
            spec: A dict, a path to a YAML/JSON file, or a YAML/JSON string.

        Returns:
            Fully constructed :class:`Workbook`.
        """
        from pytableau.build.spec import from_spec as _from_spec

        return _from_spec(spec)

    @classmethod
    def from_template(cls, template: str | Path, **kwargs: object) -> Workbook:
        """Construct a workbook from a built-in or custom template."""
        template_path = (
            Path(template).expanduser() if isinstance(template, Path) else Path(str(template))
        )
        if not template_path.suffix:
            template_path = get_template_path(str(template))
        elif template_path.suffix.lower() != ".twb":
            raise InvalidWorkbookError("Template path must point to a .twb file")

        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        try:
            tree = etree.parse(str(template_path))
        except (OSError, etree.XMLSyntaxError) as exc:
            raise InvalidWorkbookError(
                f"Unable to parse template workbook: {template_path}"
            ) from exc

        wb = cls()
        wb._template_engine = TemplateEngine(tree)
        if kwargs:
            wb._template_engine.map_fields(
                {str(k): str(v) for k, v in kwargs.items()},
                strict=False,
            )
        wb._load_tree(tree)
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

    def merge(self, other: Workbook, *, conflict_suffix: str = " (imported)") -> None:
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

    def complexity_report(self, config=None):
        """Analyze workbook complexity and return a :class:`ComplexityReport`."""
        from pytableau.inspect.complexity import analyze_complexity

        return analyze_complexity(self, config)

    def auto_fix(self, rules=None, dry_run: bool = False) -> list:
        """Apply auto-fixers to this workbook.

        Args:
            rules: List of :class:`AutoFixer` instances (default: all built-in fixers).
            dry_run: If ``True``, plan changes but do not apply them.

        Returns:
            List of :class:`FixAction` describing all changes.
        """
        from pytableau.xml.fixers import _ALL_FIXERS

        fixers = rules if rules is not None else _ALL_FIXERS
        return [action for fixer in fixers for action in fixer.fix(self, dry_run=dry_run)]

    def swap_connection(self, where=None, **kwargs) -> SwapResult:
        """Swap connection properties across all (or matching) datasources.

        Args:
            where: Optional callable ``(Datasource) -> bool`` to filter datasources.
            **kwargs: Connection attributes to update (server, dbname, username, port).

        Returns:
            A :class:`SwapResult` with counts and per-datasource details.
        """
        updated = 0
        skipped = 0
        details = []
        for ds in self.datasources:
            if where is not None and not where(ds):
                skipped += 1
                continue
            ds.swap_connection(**kwargs)
            updated += 1
            details.append({"datasource": ds.name, "applied": kwargs})
        return SwapResult(updated_count=updated, skipped_count=skipped, details=details)

    def promote(
        self,
        from_env: str,
        to_env: str,
        config: PromotionConfig,
        *,
        dry_run: bool = False,
    ) -> list[PromotionChange]:
        """Promote this workbook from one environment to another.

        Args:
            from_env: Name of the source environment in *config*.
            to_env: Name of the target environment in *config*.
            config: A :class:`PromotionConfig` describing environment specs.
            dry_run: If ``True``, plan changes but do not apply them.

        Returns:
            List of :class:`PromotionChange` describing each attribute change.
        """
        from pytableau.package.promotion import PromotionChange

        target = config.environments.get(to_env)
        if target is None:
            raise ValueError(f"Unknown environment '{to_env}' in promotion config.")

        changes: list[PromotionChange] = []

        for ds in self.datasources:
            for idx, conn in enumerate(ds.connections):
                spec_attrs = {
                    "server": target.server,
                    "dbname": target.dbname,
                    "username": target.username,
                    "port": str(target.port) if target.port is not None else None,
                }
                for attr, new_val in spec_attrs.items():
                    if new_val is None:
                        continue
                    old_val = conn.xml_node.get(attr) or conn.xml_node.get(
                        "dbName" if attr == "dbname" else attr
                    )
                    if old_val == new_val:
                        continue
                    changes.append(
                        PromotionChange(
                            datasource=ds.name,
                            connection=idx,
                            attribute=attr,
                            old_value=old_val,
                            new_value=new_val,
                        )
                    )
                    if not dry_run:
                        conn.xml_node.set(attr, new_val)

        return changes

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

    def _validate_for_save(self) -> list[ValidationIssue]:
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

    def save(self, *, scrub_credentials: bool = True) -> None:
        """Save the workbook to its original path."""
        if not self._path:
            raise InvalidWorkbookError("Workbook path is unknown; use save_as().")
        self.save_as(self._path, scrub_credentials=scrub_credentials)

    def save_as(self, path: str | Path, *, scrub_credentials: bool = True) -> None:
        """Save the workbook to a new path."""
        destination = Path(path).expanduser()
        if destination.suffix.lower() not in {".twb", ".twbx"}:
            raise InvalidWorkbookError("Workbook path must end with .twb or .twbx")

        if scrub_credentials:
            for ds in self.datasources:
                ds.scrub_credentials()

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

    def download(self, server: str, workbook_id: str, **auth: object) -> Workbook:
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

    def validate(self, profile=None) -> list[ValidationIssue]:
        """Validate the workbook XML against known schema rules.

        Args:
            profile: Optional :class:`ValidationProfile` to run additional rules.
        """
        issues = self._validate_for_save()
        if profile is not None:
            issues.extend(profile.check(self))
        return issues

    # ------------------------------------------------------------------
    # v0.7.0 — Diff, Patch, canonical JSON, git_clean
    # ------------------------------------------------------------------

    def diff(self, other: Workbook) -> WorkbookDiff:
        """Compute a semantic diff between this workbook and *other*.

        Returns:
            A :class:`~pytableau.inspect.diff.WorkbookDiff` describing
            added/removed/modified datasources, fields, and worksheets.
        """
        from pytableau.inspect.diff import diff_workbooks

        return diff_workbooks(self, other)

    def apply(self, patch: Patch, *, validate: bool = True) -> int:
        """Apply a :class:`~pytableau.inspect.diff.Patch` to this workbook.

        Unknown or missing targets are skipped with a warning.

        Args:
            patch: The patch to apply.
            validate: If ``True`` (default), raise on schema errors after applying.

        Returns:
            Number of ops successfully applied.
        """
        from pytableau.inspect.diff import apply_patch

        return apply_patch(self, patch, validate=validate)

    def git_clean(self) -> None:
        """Strip thumbnails and volatile attributes from the source file on disk.

        Requires that the workbook was opened from or saved to a ``.twb`` file.
        """
        from pytableau.xml.canonical import git_clean as _gc

        if self._path is None:
            raise ValueError("Workbook has no source path; save to a .twb file first.")
        _gc(self._path)

    def to_json(self) -> str:
        """Serialize workbook to a canonical, deterministic JSON string.

        Suitable for storing alongside workbooks in version control to
        enable human-readable field/connection diffs.
        """
        from pytableau.xml.canonical import to_json

        return to_json(self)

    # ------------------------------------------------------------------
    # v0.8.0 — save_as_template
    # ------------------------------------------------------------------

    def save_as_template(
        self,
        path: str | Path,
        *,
        field_placeholder_prefix: str = "FIELD",
    ) -> dict[str, str]:
        """Save workbook as a reusable template with field caption placeholders.

        Replaces all ``caption`` attributes on datasource columns with
        ``__FIELDN__`` tokens and writes the result to *path*.
        Does NOT modify the live workbook.

        Args:
            path: Destination ``.twb`` path.
            field_placeholder_prefix: Prefix for generated placeholder names.

        Returns:
            Mapping of ``{placeholder: original_caption}`` for caller reference.
        """
        import copy

        mapping: dict[str, str] = {}
        tree_copy = copy.deepcopy(self._tree)
        root = tree_copy.getroot()

        for counter, col in enumerate(root.xpath("//datasource/columns/column[@caption]")):
            orig = col.get("caption", "")
            placeholder = f"__{field_placeholder_prefix}{counter}__"
            col.set("caption", placeholder)
            mapping[placeholder] = orig

        dest = Path(path).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        from lxml import etree as _etree

        dest.write_bytes(
            _etree.tostring(root, encoding="utf-8", xml_declaration=True, pretty_print=True)
        )
        return mapping
