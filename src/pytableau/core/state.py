"""Portable workbook snapshots, including working package assets."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any

from lxml import etree

from pytableau.exceptions import InvalidPathError
from pytableau.package.manager import PackageManager

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


def safe_member(name: str) -> str:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise InvalidPathError(f"Unsafe snapshot asset path: {name!r}")
    return str(path)


def xml_identity(xml: str | bytes) -> bytes:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=True)
    tree = etree.parse(io.BytesIO(xml.encode() if isinstance(xml, str) else xml), parser)
    return etree.tostring(tree, method="c14n", with_comments=True)


def snapshot(workbook: Workbook) -> dict[str, Any]:
    """Capture the complete XML document and current assets, never the stale ZIP."""
    pm = workbook._package_manager
    member = pm.twb_member_name if pm is not None else None
    packaged = bool(pm and pm.is_twbx and not pm._snapshot_plain)
    member = (member or "workbook.twb") if packaged else "workbook.twb"
    files: dict[str, bytes] = {}
    if pm is not None and pm.is_twbx:
        root = pm.twb_path
        for _ in PurePosixPath(pm.twb_member_name).parts:
            root = root.parent
        for path in root.rglob("*"):
            if path.is_file() and path != pm.twb_path:
                files[path.relative_to(root).as_posix()] = path.read_bytes()
    elif workbook._path is not None:
        root = workbook._path.parent
        from pytableau.package.assets import owned_assets

        files = {
            name: path.read_bytes() for name, path in owned_assets(root, workbook.xml_tree).items()
        }
    return {
        "packaged": packaged,
        "xml": etree.tostring(workbook.xml_tree, encoding="unicode"),
        "member": safe_member(member),
        "assets": {safe_member(k): base64.b64encode(v).decode() for k, v in sorted(files.items())},
        "tombstones": dict(workbook._asset_tombstones),
    }


def fingerprint(state: dict[str, Any]) -> str:
    content = {
        "member": state["member"],
        "packaged": state.get("packaged", False),
        "xml": xml_identity(state["xml"]).decode(),
        "assets": {
            k: hashlib.sha256(base64.b64decode(v, validate=True)).hexdigest()
            for k, v in sorted(state["assets"].items())
        },
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def install(workbook: Workbook, state: dict[str, Any], *, restore_tombstones: bool = False) -> None:
    """Install a validated snapshot into isolated working storage."""
    member = safe_member(state["member"])
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    tree = etree.parse(io.BytesIO(state["xml"].encode()), parser)
    if tree.getroot().tag != "workbook":
        raise ValueError("Snapshot root must be a workbook")
    assets = {
        safe_member(k): base64.b64decode(v, validate=True) for k, v in state["assets"].items()
    }
    if member in assets:
        raise ValueError("Snapshot assets overlap the active workbook")
    original = snapshot(workbook)
    tombstones = dict(workbook._asset_tombstones)
    from pytableau.package.assets import plain_asset_name

    for name in original["assets"].keys() - state["assets"].keys():
        destination_name = plain_asset_name(original["member"], name)
        tombstones.setdefault(
            destination_name, hashlib.sha256(base64.b64decode(original["assets"][name])).hexdigest()
        )
    present = {plain_asset_name(member, name) for name in state["assets"]}
    tombstones = {k: v for k, v in tombstones.items() if k not in present}
    old = workbook._package_manager
    storage = TemporaryDirectory(prefix="pytableau-snapshot-")
    archive = Path(storage.name) / "state.twbx"
    try:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(member, state["xml"])
            for name, data in assets.items():
                zf.writestr(name, data)
        pm = PackageManager(archive, twb_hint=member)
        pm._source_storage = storage
        pm._snapshot_plain = not state.get("packaged", False)
        pm._prepare()
    except BaseException:
        storage.cleanup()
        raise
    workbook._package_manager = pm
    try:
        workbook._load_tree(tree)
    except BaseException:
        workbook._package_manager = old
        pm.close()
        raise
    workbook._asset_tombstones = (
        dict(state.get("tombstones", {})) if restore_tombstones else tombstones
    )
    if old is not None:
        old.close()
