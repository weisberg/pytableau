"""Canonical serialization for Tableau workbooks.

Provides deterministic JSON serialization and VCS-friendly git_clean()
that strips volatile elements (thumbnails, session IDs) to make workbook
diffs human-readable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook


# Attributes that change every save/open but carry no semantic value
_VOLATILE_ATTRS: frozenset[str] = frozenset(
    {"zoom-level", "default-view-tab", "object-id", "saved-by-version"}
)


# ---------------------------------------------------------------------------
# Canonical dict serialization
# ---------------------------------------------------------------------------


def _canon_field(f: Any) -> dict[str, Any]:
    return {
        "datatype": str(f.datatype),
        "role": str(f.role),
        "hidden": f.hidden,
    }


def _canon_conn(c: Any) -> dict[str, Any]:
    return {
        "class": c.class_,
        "server": c.server,
        "dbname": c.dbname,
        "username": c.username,
    }


def _canon_ds(ds: Any) -> dict[str, Any]:
    return {
        "caption": ds.caption,
        "connections": [_canon_conn(c) for c in ds.connections],
        "fields": {
            f.caption: _canon_field(f) for f in sorted(ds.fields, key=lambda x: x.caption or "")
        },
        "calculated_fields": {
            f.caption: (f.formula or "")
            for f in sorted(ds.calculated_fields, key=lambda x: x.caption or "")
        },
    }


def canonicalize(workbook: Workbook) -> dict[str, Any]:
    """Serialize workbook to a stable, deterministic canonical dict.

    Omits volatile IDs and sorts all keys. Suitable for diffing and
    storing alongside the workbook in version control.
    """
    raw = {
        "version": workbook.version,
        "datasources": {
            ds.name: _canon_ds(ds)
            for ds in sorted(workbook.datasources, key=lambda d: d.name or "")
        },
        "worksheets": sorted(ws.name for ws in workbook.worksheets),
        "dashboards": sorted(d.name for d in workbook.dashboards),
    }
    return dict(sorted(raw.items()))


def to_json(workbook: Workbook, indent: int = 2) -> str:
    """Serialize workbook to a canonical, deterministic JSON string."""
    return json.dumps(canonicalize(workbook), sort_keys=True, indent=indent)


# ---------------------------------------------------------------------------
# git_clean: strip thumbnails + volatile attrs for VCS-friendly diffs
# ---------------------------------------------------------------------------


def git_clean(path: Path | str, *, in_place: bool = True) -> str:
    """Strip thumbnails and volatile attributes for VCS-friendly diffs.

    Args:
        path: Path to ``.twb`` file to clean.
        in_place: If ``True`` (default), overwrite the file. If ``False``,
            return the cleaned XML string without writing.

    Returns:
        Cleaned XML as a string.
    """
    _parser = etree.XMLParser(resolve_entities=False, no_network=True)
    tree = etree.parse(str(path), _parser)
    root = tree.getroot()

    # Remove <thumbnails> elements (base64 blobs that change every save)
    for elem in root.xpath("//thumbnails"):
        parent = elem.getparent()
        if parent is not None:
            parent.remove(elem)

    # Remove <style> blocks with volatile layout coordinates
    for elem in root.xpath("//style"):
        parent = elem.getparent()
        if parent is not None:
            parent.remove(elem)

    # Strip volatile per-session attributes
    for elem in root.iter():
        for attr in _VOLATILE_ATTRS:
            elem.attrib.pop(attr, None)

    xml_bytes = etree.tostring(
        root,
        encoding="unicode",
        pretty_print=True,
        xml_declaration=False,
    )
    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    cleaned = header + xml_bytes

    if in_place:
        Path(path).write_text(cleaned, encoding="utf-8")

    return xml_bytes  # return without XML declaration for diffing
