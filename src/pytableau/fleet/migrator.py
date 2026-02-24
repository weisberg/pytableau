"""Migration engine — apply bulk transformations across a fleet of workbooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MigrationResult:
    """Result of migrating a single workbook."""

    path: Path
    output_path: Path | None
    status: str  # "migrated" | "skipped" | "error"
    changes: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "output_path": str(self.output_path) if self.output_path else None,
            "status": self.status,
            "changes": self.changes,
            "error": self.error,
        }


@dataclass
class MigrationReport:
    """Aggregated result of a migration run."""

    results: list[MigrationResult]
    dry_run: bool

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def migrated(self) -> int:
        return sum(1 for r in self.results if r.status == "migrated")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "skipped")

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.status == "error")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "total": self.total,
            "migrated": self.migrated,
            "skipped": self.skipped,
            "errors": self.errors,
            "results": [r.to_dict() for r in self.results],
        }

    def __str__(self) -> str:
        prefix = "[DRY RUN] " if self.dry_run else ""
        return (
            f"{prefix}{self.total} scanned, {self.migrated} migrated, "
            f"{self.skipped} skipped, {self.errors} errors"
        )


class MigrationPlan:
    """Fluent builder for a fleet migration plan.

    Example::

        plan = (
            MigrationPlan()
            .source_directory("./legacy/")
            .swap_connections({"old-db.corp.com": "new-db.corp.com"})
            .rename_fields({"Cust ID": "Customer ID"})
            .output_directory("./migrated/")
        )
        report = MigrationEngine(plan).execute(dry_run=True)
    """

    def __init__(self) -> None:
        self._source: Path | None = None
        self._output: Path | None = None
        self._pattern: str = "**/*.tw[bx]"
        self._target_version: str | None = None
        self._connection_swaps: dict[str, str] = {}
        self._field_renames: dict[str, str] = {}
        self._validate: bool = False

    def source_directory(self, path: str | Path) -> MigrationPlan:
        """Set the source directory to scan for workbooks."""
        self._source = Path(path)
        return self

    def output_directory(self, path: str | Path) -> MigrationPlan:
        """Set the directory where migrated workbooks are written."""
        self._output = Path(path)
        return self

    def pattern(self, glob: str) -> MigrationPlan:
        """Override the glob pattern used to find workbooks (default ``**/*.tw[bx]``)."""
        self._pattern = glob
        return self

    def target_version(self, version: str) -> MigrationPlan:
        """Pin the ``source-build`` attribute to a known Tableau version string."""
        self._target_version = version
        return self

    def swap_connections(self, mapping: dict[str, str]) -> MigrationPlan:
        """Map old server hostnames → new hostnames across all datasources."""
        self._connection_swaps.update(mapping)
        return self

    def rename_fields(self, mapping: dict[str, str]) -> MigrationPlan:
        """Map old field captions → new captions across all datasources."""
        self._field_renames.update(mapping)
        return self

    def validate_all(self) -> MigrationPlan:
        """Validate each workbook after migration; skip saving if invalid."""
        self._validate = True
        return self


class MigrationEngine:
    """Execute a :class:`MigrationPlan` against a fleet of workbooks."""

    def __init__(self, plan: MigrationPlan) -> None:
        self._plan = plan

    def execute(self, *, dry_run: bool = False) -> MigrationReport:
        """Run the migration.

        Args:
            dry_run: If ``True``, analyse and report changes without writing files.

        Returns:
            :class:`MigrationReport` summarising what happened.
        """
        plan = self._plan
        if plan._source is None:
            raise ValueError("MigrationPlan.source_directory() is required.")

        paths = sorted(plan._source.glob(plan._pattern))
        results: list[MigrationResult] = []

        for path in paths:
            result = self._migrate_one(path, dry_run=dry_run)
            results.append(result)

        return MigrationReport(results=results, dry_run=dry_run)

    def _migrate_one(self, path: Path, *, dry_run: bool) -> MigrationResult:
        plan = self._plan
        changes: list[str] = []
        try:
            from pytableau.core.workbook import Workbook

            wb = Workbook.open(path)

            # Connection swaps
            for old_server, new_server in plan._connection_swaps.items():
                for ds in wb.datasources:
                    if ds.is_parameters:
                        continue
                    for conn in ds.connections:
                        if conn.server and old_server in (conn.server or ""):
                            conn.server = new_server
                            changes.append(
                                f"swap_connection: {old_server!r} → {new_server!r} in {ds.name!r}"
                            )

            # Field renames
            for old_caption, new_caption in plan._field_renames.items():
                for ds in wb.datasources:
                    if ds.is_parameters:
                        continue
                    if ds.get_field(old_caption) is not None:
                        ds.rename_field(old_caption, new_caption)
                        changes.append(
                            f"rename_field: {old_caption!r} → {new_caption!r} in {ds.name!r}"
                        )

            if not changes:
                return MigrationResult(path=path, output_path=None, status="skipped", changes=[])

            if not dry_run:
                output_dir = plan._output or path.parent
                output_dir.mkdir(parents=True, exist_ok=True)
                out_path = output_dir / path.name
                wb.save_as(out_path)
                return MigrationResult(
                    path=path, output_path=out_path, status="migrated", changes=changes
                )
            else:
                return MigrationResult(
                    path=path, output_path=None, status="migrated", changes=changes
                )

        except Exception as exc:
            return MigrationResult(
                path=path,
                output_path=None,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
