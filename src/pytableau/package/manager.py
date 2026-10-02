"""PackageManager: transparent ``.twbx`` ↔ temp directory management.

A ``.twbx`` file is a ZIP archive containing a ``.twb`` XML file and
optional data files (e.g. ``.hyper`` extract).  :class:`PackageManager`
handles extraction, mutation, and re-packaging transparently.
"""

from __future__ import annotations

import fnmatch
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from pytableau.exceptions import (
    AmbiguousWorkbookError,
    InvalidPathError,
    InvalidWorkbookError,
    PackageError,
)

# Deterministic ZIP epoch — strips all timestamps for reproducible output.
_EPOCH = (1980, 1, 1, 0, 0, 0)


def is_twbx(path: Path) -> bool:
    """Return ``True`` if *path* is a valid ``.twbx`` ZIP archive."""
    return path.suffix.lower() == ".twbx" and zipfile.is_zipfile(path)


def is_twb(path: Path) -> bool:
    """Return ``True`` if *path* is a ``.twb`` XML file."""
    return path.suffix.lower() == ".twb"


class PackageManager:
    """Manage transparent package operations for a workbook path.

    For plain ``.twb`` files, ``twb_path`` is the source path itself.
    For ``.twbx`` files, content is extracted into a temporary directory
    and ``twb_path`` points at the extracted ``.twb`` entry.
    """

    def __init__(self, source: str | Path, *, twb_hint: str | None = None) -> None:
        self.source = Path(source).expanduser()
        self._twb_hint = twb_hint
        self._twb_path: Path | None = None
        self._working_dir: TemporaryDirectory[str] | None = None
        self._prepared = False
        self._snapshot_plain = False
        self._source_storage: TemporaryDirectory[str] | None = None

    @property
    def is_twbx(self) -> bool:
        """Whether the source package is a TWBX archive."""
        return is_twbx(self.source)

    @property
    def twb_path(self) -> Path:
        """Path to the active ``.twb`` file in the working space."""
        self._prepare()
        assert self._twb_path is not None
        return self._twb_path

    @property
    def twb_member_name(self) -> str:
        """Active XML member path, retaining its directory inside a TWBX."""
        path = self.twb_path
        if self._working_dir is not None:
            return path.relative_to(self._working_dir.name).as_posix()
        return path.name

    def _prepare(self) -> None:
        if self._prepared:
            return

        if is_twb(self.source):
            self._twb_path = self.source
            self._prepared = True
            return

        if self.is_twbx:
            self._working_dir = TemporaryDirectory(prefix="pytableau-")
            extracted = Path(self._working_dir.name)
            try:
                with zipfile.ZipFile(self.source) as zf:
                    zf.extractall(extracted)
                self._twb_path = self._select_twb(extracted)
            except (OSError, zipfile.BadZipFile) as exc:
                self.close()
                raise InvalidWorkbookError(f"Unable to read TWBX archive: {self.source}") from exc
            except Exception:
                self.close()
                raise
            self._prepared = True
            return

        raise InvalidWorkbookError(f"Unsupported workbook path: {self.source}")

    def _select_twb(self, extracted: Path) -> Path:
        twb_candidates = sorted(
            p for p in extracted.rglob("*") if p.is_file() and p.suffix.lower() == ".twb"
        )
        if not twb_candidates:
            raise PackageError(f"No .twb file found inside TWBX archive: {self.source}")
        if len(twb_candidates) == 1:
            return twb_candidates[0]

        if self._twb_hint is not None:
            matches = [
                p
                for p in twb_candidates
                if p.relative_to(extracted).as_posix().lower() == self._twb_hint.lower()
            ]
            if len(matches) == 1:
                return matches[0]
            matches = [p for p in twb_candidates if p.name.lower() == self._twb_hint.lower()]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise AmbiguousWorkbookError(
                    f"twb_hint '{self._twb_hint}' matched multiple files in {self.source}",
                    candidates=[str(p.relative_to(extracted)) for p in matches],
                )

        root_candidates = [p for p in twb_candidates if p.parent == extracted]
        if len(root_candidates) == 1:
            return root_candidates[0]
        raise AmbiguousWorkbookError(
            f"Multiple .twb files found in {self.source}; use twb_hint= to specify one.",
            candidates=[str(p.relative_to(extracted)) for p in twb_candidates],
        )

    def __enter__(self) -> PackageManager:
        self._prepare()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """Release temporary extraction state."""
        if self._working_dir is not None:
            self._working_dir.cleanup()
            self._working_dir = None
        self._twb_path = None
        self._prepared = False
        if self._source_storage is not None:
            self._source_storage.cleanup()
            self._source_storage = None

    def _write_twb(self, source_twb: Path) -> None:
        self._prepare()
        if not source_twb.exists():
            raise PackageError(f"Workbook XML file not found: {source_twb}")
        if self._twb_path != source_twb:
            # keep working copy in sync for .twbx scenarios.
            self.twb_path.write_bytes(source_twb.read_bytes())

    # ------------------------------------------------------------------
    # Asset listing helpers (#62)
    # ------------------------------------------------------------------

    def list_assets(self) -> list[str]:
        """Return sorted list of non-``.twb`` ZIP member paths."""
        if not self.is_twbx:
            return []
        self._prepare()
        assert self._working_dir is not None
        root = Path(self._working_dir.name)
        return sorted(
            p.relative_to(root).as_posix()
            for p in root.rglob("*")
            if p.is_file() and p != self.twb_path
        )

    def glob(self, pattern: str) -> list[str]:
        """Return assets matching *pattern* (fnmatch syntax)."""
        return [name for name in self.list_assets() if fnmatch.fnmatch(name, pattern)]

    def find(self, name: str) -> str | None:
        """Case-insensitive search for an asset by filename (basename only)."""
        name_lower = name.lower()
        for asset in self.list_assets():
            if PurePosixPath(asset).name.lower() == name_lower:
                return asset
        return None

    @property
    def data_dir(self) -> str | None:
        """Parent directory of the first ``.hyper`` asset, or ``None``."""
        for asset in self.list_assets():
            if asset.lower().endswith(".hyper"):
                parent = PurePosixPath(asset).parent
                return str(parent) if str(parent) != "." else ""
        return None

    # ------------------------------------------------------------------
    # Path traversal guard (#64)
    # ------------------------------------------------------------------

    def resolve(self, path: str) -> str:
        """Sanitize and validate an archive-relative path.

        Raises :exc:`InvalidPathError` if *path* contains ``..`` components
        or is an absolute Windows/Unix path.
        """
        cleaned = path.lstrip("/")
        # Reject Windows drive letters (e.g. C:/)
        if len(cleaned) >= 2 and cleaned[1] == ":":
            raise InvalidPathError(f"Absolute path not allowed: {path!r}")
        parts = PurePosixPath(cleaned).parts
        if ".." in parts:
            raise InvalidPathError(f"Path traversal not allowed: {path!r}")
        return cleaned

    # ------------------------------------------------------------------
    # save_as — deterministic ZIP (#63)
    # ------------------------------------------------------------------

    def save_as(self, destination: str | Path, *, source_twb: Path | None = None) -> Path:
        """Save current package state to ``destination``.

        Args:
            destination: output workbook path (``.twb`` or ``.twbx``).
            source_twb: Optional replacement XML, leaving the source file untouched.

        Returns:
            Normalized output path.
        """
        destination = Path(destination).expanduser()
        if destination.suffix.lower() not in {".twb", ".twbx"}:
            raise InvalidWorkbookError("Workbook output must end with .twb or .twbx")

        self._prepare()
        twb_source = source_twb if source_twb is not None else self.twb_path
        if not twb_source.is_file():
            raise PackageError(f"Workbook XML file not found: {twb_source}")
        destination.parent.mkdir(parents=True, exist_ok=True)

        if self.is_twbx:
            assert self._working_dir is not None
            root = Path(self._working_dir.name)
            entries = {
                entry.relative_to(root).as_posix(): entry
                for entry in root.rglob("*")
                if entry.is_file()
            }
            twb_name = self.twb_path.relative_to(root).as_posix()
        else:
            root = self.twb_path.parent
            from lxml import etree

            from .assets import owned_assets

            tree = etree.parse(
                str(twb_source), etree.XMLParser(resolve_entities=False, no_network=True)
            )
            entries = {
                name: entry
                for name, entry in owned_assets(
                    root, tree, reject_external=destination.suffix.lower() == ".twbx"
                ).items()
                if entry.resolve() != destination.resolve()
            }
            twb_name = self.twb_path.name
        entries[twb_name] = twb_source

        if destination.suffix.lower() == ".twb":
            targets: set[Path] = set()
            for name, asset in entries.items():
                if name.lower().endswith(".twb"):
                    continue
                # XML references are relative to the selected TWB, not ZIP root.
                from .assets import plain_asset_name

                relative = Path(plain_asset_name(twb_name, name))
                target = destination.parent / relative
                if target in targets:
                    raise PackageError(
                        f"Flattening the active TWB causes an asset collision: {target}"
                    )
                targets.add(target)
                if not target.resolve().is_relative_to(destination.parent.resolve()):
                    raise InvalidPathError(f"Asset output escapes destination directory: {target}")
                if target.resolve() != asset.resolve():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(asset, target)
            if twb_source.resolve() != destination.resolve():
                shutil.copy2(twb_source, destination)
            return destination

        with zipfile.ZipFile(destination, mode="w") as zf:
            for name, entry in sorted(entries.items()):
                info = zipfile.ZipInfo(name, date_time=_EPOCH)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.extra = b""
                info.create_system = 0
                zf.writestr(info, entry.read_bytes())
        return destination

    def __del__(self):
        self.close()
