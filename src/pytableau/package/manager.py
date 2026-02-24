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
            except (OSError, zipfile.BadZipFile) as exc:
                self.close()
                raise InvalidWorkbookError(f"Unable to read TWBX archive: {self.source}") from exc

            twb_candidates = sorted(extracted.rglob("*.twb"))
            if not twb_candidates:
                raise PackageError(f"No .twb file found inside TWBX archive: {self.source}")

            if len(twb_candidates) == 1:
                self._twb_path = twb_candidates[0]
                self._prepared = True
                return

            # Multiple .twb files: apply resolution rules.
            root_candidates = [p for p in twb_candidates if p.parent == extracted]

            if self._twb_hint is not None:
                hint_lower = self._twb_hint.lower()
                matches = [p for p in twb_candidates if p.name.lower() == hint_lower]
                if len(matches) == 1:
                    self._twb_path = matches[0]
                    self._prepared = True
                    return
                if len(matches) > 1:
                    raise AmbiguousWorkbookError(
                        f"twb_hint '{self._twb_hint}' matched multiple files in {self.source}",
                        candidates=[str(p.relative_to(extracted)) for p in matches],
                    )
                # hint didn't match any file — fall through to standard resolution

            if len(root_candidates) == 1:
                self._twb_path = root_candidates[0]
                self._prepared = True
                return

            candidate_names = [str(p.relative_to(extracted)) for p in twb_candidates]
            raise AmbiguousWorkbookError(
                f"Multiple .twb files found in {self.source}; use twb_hint= to specify one.",
                candidates=candidate_names,
            )

        raise InvalidWorkbookError(f"Unsupported workbook path: {self.source}")

    def __enter__(self) -> PackageManager:
        self._prepare()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """Release temporary extraction state."""
        if self._working_dir is None:
            return
        shutil.rmtree(self._working_dir.name, ignore_errors=True)
        self._working_dir = None

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
        with zipfile.ZipFile(self.source) as zf:
            names = [n for n in zf.namelist() if not n.lower().endswith(".twb")]
        return sorted(names)

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

    def save_as(self, destination: str | Path) -> Path:
        """Save current package state to ``destination``.

        Args:
            destination: output workbook path (``.twb`` or ``.twbx``).

        Returns:
            Normalized output path.
        """
        destination = Path(destination).expanduser()
        if destination.suffix.lower() not in {".twb", ".twbx"}:
            raise InvalidWorkbookError("Workbook output must end with .twb or .twbx")

        self._prepare()
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.suffix.lower() == ".twb":
            if self.twb_path.resolve() != destination.resolve():
                shutil.copy2(self.twb_path, destination)
            return destination

        if self.is_twbx:
            assert self._working_dir is not None
            root = Path(self._working_dir.name)
            with zipfile.ZipFile(destination, mode="w") as zf:
                for entry in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
                    if entry.is_file():
                        arcname = entry.relative_to(root).as_posix()
                        info = zipfile.ZipInfo(arcname, date_time=_EPOCH)
                        info.compress_type = zipfile.ZIP_DEFLATED
                        info.extra = b""
                        info.create_system = 0
                        zf.writestr(info, entry.read_bytes())
            return destination

        # Source was .twb, output is .twbx.
        with zipfile.ZipFile(destination, mode="w") as zf:
            info = zipfile.ZipInfo(self.twb_path.name, date_time=_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.extra = b""
            info.create_system = 0
            zf.writestr(info, self.twb_path.read_bytes())
        return destination

    def __del__(self):
        self.close()
