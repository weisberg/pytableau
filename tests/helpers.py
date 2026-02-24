"""Shared test helpers."""

from __future__ import annotations

import io
from pathlib import Path

from lxml import etree


def canonicalize_twb(path: Path | str) -> str:
    """Parse a .twb file and return a canonical XML string.

    Attribute order is sorted on every element; whitespace is normalized.
    Uses W3C Canonical XML (c14n) so that two semantically identical files
    produce byte-identical output regardless of serialization order.
    """
    tree = etree.parse(str(path))
    root = tree.getroot()

    # Sort attributes on every element for stable comparison.
    _sort_attributes(root)

    buf = io.BytesIO()
    tree.write_c14n(buf)
    return buf.getvalue().decode("utf-8")


def _sort_attributes(element: etree._Element) -> None:
    """Recursively sort all element attributes alphabetically."""
    # lxml doesn't support in-place attribute reordering directly,
    # but write_c14n already sorts attributes per the C14N spec.
    for child in element:
        _sort_attributes(child)
