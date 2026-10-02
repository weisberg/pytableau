"""Image, shape, and asset handling within .twbx packages."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from lxml import etree

from pytableau.exceptions import InvalidPathError

IMAGE_EXTS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp"})


@dataclass(frozen=True)
class WorkbookAsset:
    """Metadata for a single asset stored inside a ``.twbx`` package.

    Attributes:
        name: Path of the asset inside the ZIP archive (e.g. ``"Image/logo.png"``).
        size: Compressed size in bytes.
        is_image: ``True`` if the file extension is a recognised image format.
    """

    name: str
    size: int
    is_image: bool


def list_assets(twbx_path: str | Path) -> list[WorkbookAsset]:
    """Return all non-workbook assets stored inside a ``.twbx`` file.

    Args:
        twbx_path: Path to the ``.twbx`` package.

    Returns:
        List of :class:`WorkbookAsset` objects (excludes the ``.twb`` entry).
    """
    assets: list[WorkbookAsset] = []
    with zipfile.ZipFile(str(twbx_path), "r") as zf:
        for info in zf.infolist():
            if info.filename.endswith(".twb"):
                continue
            suffix = Path(info.filename).suffix.lower()
            assets.append(
                WorkbookAsset(
                    name=info.filename,
                    size=info.compress_size,
                    is_image=suffix in IMAGE_EXTS,
                )
            )
    return assets


def extract_asset(
    twbx_path: str | Path,
    asset_name: str,
    output_dir: str | Path,
) -> Path:
    """Extract a single asset from a ``.twbx`` archive.

    Args:
        twbx_path: Path to the ``.twbx`` package.
        asset_name: Internal archive path of the asset to extract.
        output_dir: Directory where the asset will be written.

    Returns:
        Absolute :class:`~pathlib.Path` of the extracted file.
    """
    with zipfile.ZipFile(str(twbx_path), "r") as zf:
        extracted = zf.extract(asset_name, str(output_dir))
    return Path(extracted)


def add_asset(
    twbx_path: str | Path,
    asset_path: str | Path,
    *,
    dest_name: str | None = None,
) -> None:
    """Add a file to an existing ``.twbx`` archive.

    The operation round-trips through a temporary file to avoid in-place
    ``ZipFile`` limitations.

    Args:
        twbx_path: Path to the ``.twbx`` package to modify.
        asset_path: Path to the local file to add.
        dest_name: Internal archive name for the asset.  Defaults to
            ``"Image/<filename>"``.
    """
    twbx_path = Path(twbx_path)
    asset_path = Path(asset_path)
    archive_name = dest_name or f"Image/{asset_path.name}"

    with tempfile.NamedTemporaryFile(suffix=".twbx", delete=False, dir=twbx_path.parent) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with (
            zipfile.ZipFile(str(twbx_path), "r") as src_zf,
            zipfile.ZipFile(str(tmp_path), "w", compression=zipfile.ZIP_DEFLATED) as dst_zf,
        ):
            for item in src_zf.infolist():
                dst_zf.writestr(item, src_zf.read(item.filename))
            dst_zf.write(str(asset_path), archive_name)

        shutil.move(str(tmp_path), str(twbx_path))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def owned_assets(
    root: Path, tree: etree._ElementTree, *, reject_external: bool = False
) -> dict[str, Path]:
    paths = set((root / "Data").rglob("*")) if (root / "Data").exists() else set()
    for node in tree.getroot().iter():
        for attribute in ("filename", "path"):
            value = node.get(attribute)
            if not value:
                continue
            member = PurePosixPath(value)
            candidate = root / value
            portable = (
                not member.is_absolute()
                and ".." not in member.parts
                and "\\" not in value
                and ":" not in value
            )
            if not portable or not candidate.resolve().is_relative_to(root.resolve()):
                if reject_external and candidate.is_file():
                    raise InvalidPathError(
                        f"Packaged output requires an owned relative asset reference: {value}"
                    )
                continue
            if candidate.is_file():
                paths.add(candidate)
    result = {}
    for path in paths:
        if not path.is_file():
            continue
        if not path.resolve().is_relative_to(root.resolve()):
            raise InvalidPathError(f"Asset symlink escapes workbook directory: {path}")
        result[path.relative_to(root).as_posix()] = path
    return result


def plain_asset_name(member: str, asset: str) -> str:
    """Map a ZIP member to the layout of a standalone active workbook."""
    path = PurePosixPath(asset)
    parent = PurePosixPath(member).parent
    return (path.relative_to(parent) if path.is_relative_to(parent) else path).as_posix()
