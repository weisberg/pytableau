"""Durable prepare/apply/resume/rollback with a journal for each installed file."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from pytableau.core.state import snapshot
from pytableau.core.workbook import Workbook
from pytableau.exceptions import InvalidPathError
from pytableau.fleet._paths import workbook_paths


def _hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, prefix=".pytableau-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    # Advisory OS locks are released on process death, permitting safe crash recovery.
    with path.with_suffix(path.suffix + ".lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt as windows_lock

            msvcrt: Any = windows_lock

            stream.write(b"\0")
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class MigrationManifest:
    """A persisted plan containing exact outputs, source hashes and destination backups.

    Only one writer may apply/rollback a manifest. Edits to any source or output
    conflict before installation starts. Resume recognizes a crash between file
    replacement and recording completion. Rollback restores pre-existing outputs.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.data: dict[str, Any] = json.loads(self.path.read_text())
        if self.data.get("format") != 1:
            raise ValueError("Unsupported migration manifest format")
        destination = Path(self.data["output_root"]).resolve()
        destinations = set()
        for record in self.data["files"]:
            identity = Path(record["destination"]).resolve()
            if identity in destinations:
                raise ValueError("Duplicate migration destination identity")
            destinations.add(identity)
            if not Path(record["destination"]).resolve().is_relative_to(destination):
                raise InvalidPathError("Manifest destination escapes output root")
            if not Path(record["prepared"]).resolve().is_relative_to(self.path.parent / "prepared"):
                raise InvalidPathError("Manifest prepared path escapes journal directory")

    @property
    def status(self) -> str:
        return str(self.data["status"])

    def _save(self) -> None:
        _atomic(self.path, json.dumps(self.data, indent=2, sort_keys=True).encode())

    def apply(self) -> None:
        """Install or resume all prepared files, rejecting conflicts first."""
        with _lock(self.path):
            self.data = MigrationManifest(self.path).data
            if self.status in {"rolling_back", "rolled_back"}:
                raise ValueError("Rolled-back manifests cannot be reapplied; prepare a new plan")
            files = self.data["files"]
            accepted = {f["destination"]: {f["old_hash"], f["new_hash"]} for f in files}
            for name, digest in self.data["sources"].items():
                allowed = accepted.get(name, {digest}) if self.status != "prepared" else {digest}
                if _hash(Path(name)) not in allowed:
                    raise ValueError(f"Migration source conflict: {name}")
            for record in files:
                current = _hash(Path(record["destination"]))
                allowed = (
                    {record["new_hash"]} if record["status"] == "written" else {record["old_hash"]}
                )
                if self.status != "prepared":
                    allowed.add(record["new_hash"])
                if current not in allowed:
                    raise ValueError(f"Migration destination conflict: {record['destination']}")
                if _hash(Path(record["prepared"])) != record["new_hash"]:
                    raise ValueError(f"Prepared output changed: {record['prepared']}")
            self.data["status"] = "applying"
            self._save()
            for record in files:
                destination = Path(record["destination"])
                if _hash(destination) != record["new_hash"]:
                    _atomic(destination, Path(record["prepared"]).read_bytes())
                record["status"] = "written"
                self._save()
            self.data["status"] = "applied"
            self._save()

    resume = apply

    def rollback(self) -> None:
        """Restore all previous output bytes after preflighting the entire fleet."""
        with _lock(self.path):
            self.data = MigrationManifest(self.path).data
            for record in self.data["files"]:
                if _hash(Path(record["destination"])) not in {
                    record["old_hash"],
                    record["new_hash"],
                }:
                    raise ValueError(f"Rollback conflict: {record['destination']}")
            for record in self.data["files"]:
                if (record["backup"] is None) != (record["old_hash"] is None):
                    raise ValueError("Corrupt destination backup")
                if record["backup"] is not None:
                    data = base64.b64decode(record["backup"], validate=True)
                    if hashlib.sha256(data).hexdigest() != record["old_hash"]:
                        raise ValueError("Corrupt destination backup")
            if self.status == "prepared":
                self.data["status"] = "rolled_back"
                self._save()
                return
            self.data["status"] = "rolling_back"
            self._save()
            for record in reversed(self.data["files"]):
                destination = Path(record["destination"])
                backup = record["backup"]
                if backup is None:
                    destination.unlink(missing_ok=True)
                else:
                    data = base64.b64decode(backup, validate=True)
                    if hashlib.sha256(data).hexdigest() != record["old_hash"]:
                        raise ValueError("Corrupt destination backup")
                    _atomic(destination, data)
                record["status"] = "restored"
                self._save()
            self.data["status"] = "rolled_back"
            self._save()


def prepare(engine: Any, directory: str | Path) -> MigrationManifest:
    """Prepare exact migration outputs in a new journal directory; leave sources intact."""
    plan = engine._plan
    if plan._source is None:
        raise ValueError("MigrationPlan.source_directory() is required")
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    if manifest_path.exists() or (directory / "prepared").exists():
        raise FileExistsError("Use a fresh journal directory")
    source_root = plan._source.resolve()
    output_root = (plan._output or plan._source).resolve()
    if directory.is_relative_to(source_root) or directory.is_relative_to(output_root):
        raise InvalidPathError("Journal directory must be outside source and output trees")
    staged_plan = copy.copy(plan)
    staged_plan._output = directory / "prepared"
    staged_engine = type(engine)(staged_plan)
    sources: dict[str, str | None] = {}
    results = []
    for path in workbook_paths(plan._source, plan._pattern):
        if (
            output_root != source_root
            and output_root.is_relative_to(source_root)
            and path.resolve().is_relative_to(output_root)
        ):
            continue
        with Workbook.open(path) as wb:
            state = snapshot(wb)
        sources[str(path.resolve())] = _hash(path)
        if path.suffix.lower() == ".twb":
            for asset in state["assets"]:
                asset_path = path.parent / asset
                sources[str(asset_path.resolve())] = _hash(asset_path)
        result = staged_engine._migrate_one(path, dry_run=False)
        if result.status == "error":
            raise ValueError(f"Preparation failed for {path}: {result.error}")
        results.append(result.to_dict())
    records = []
    prepared = directory / "prepared"
    if prepared.exists():
        for path in sorted(prepared.rglob("*")):
            if not path.is_file():
                continue
            destination = (output_root / path.relative_to(prepared)).resolve()
            if not destination.is_relative_to(output_root):
                raise InvalidPathError("Destination escapes migration output")
            old = destination.read_bytes() if destination.is_file() else None
            records.append(
                {
                    "destination": str(destination),
                    "prepared": str(path),
                    "old_hash": _hash(destination),
                    "new_hash": _hash(path),
                    "backup": base64.b64encode(old).decode() if old is not None else None,
                    "status": "pending",
                }
            )
    identities = [record["destination"] for record in records]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate migration destination identity")
    # No output may overwrite a different input workbook/asset incidentally.
    for record in records:
        name = record["destination"]
        if name in sources and output_root != source_root:
            raise ValueError(f"Output overlaps a migration source: {name}")
    data = {
        "format": 1,
        "status": "prepared",
        "source_root": str(source_root),
        "output_root": str(output_root),
        "sources": sources,
        "files": records,
        "results": results,
    }
    _atomic(manifest_path, json.dumps(data, indent=2, sort_keys=True).encode())
    return MigrationManifest(manifest_path)
