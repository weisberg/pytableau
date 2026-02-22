"""PackageManager: transparent ``.twbx`` ↔ temp directory management.

A ``.twbx`` file is a ZIP archive containing a ``.twb`` XML file and
optional data files (e.g. ``.hyper`` extract).  :class:`PackageManager`
handles extraction, mutation, and re-packaging transparently.

.. note::
    Full implementation is tracked in Phase 1 of the development plan.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from pytableau.exceptions import InvalidWorkbookError, PackageError


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

    def __init__(self, source: str | Path) -> None:
        self.source = Path(source).expanduser()
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

            # Prefer a top-level .twb when available; otherwise use first match.
            root_twb = next((path for path in twb_candidates if path.parent == extracted), None)
            self._twb_path = root_twb or twb_candidates[0]
            self._prepared = True
            return

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
            with zipfile.ZipFile(destination, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                assert self._working_dir is not None
                root = Path(self._working_dir.name)
                for entry in sorted(root.rglob("*")):
                    if entry.is_file():
                        zf.write(entry, entry.relative_to(root).as_posix())
            return destination

        # Source was .twb, output is .twbx.
        with zipfile.ZipFile(destination, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(self.twb_path, self.twb_path.name)
        return destination

    def __del__(self):
        self.close()
