"""XML generation helpers: to_string, write, and indent."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lxml import etree as _etree


def to_string(
    element: _etree._Element,
    *,
    pretty: bool = True,
    xml_declaration: bool = False,
    encoding: str = "utf-8",
) -> str:
    """Serialise *element* to an XML string.

    Args:
        element: The lxml element to serialise.
        pretty: Whether to pretty-print with indentation.
        xml_declaration: Whether to prepend ``<?xml …?>`` declaration.
        encoding: Encoding label used in the declaration (only relevant when
            *xml_declaration* is ``True``).

    Returns:
        UTF-8 decoded XML string.
    """
    from lxml import etree

    if xml_declaration:
        raw = etree.tostring(
            element,
            pretty_print=pretty,
            xml_declaration=True,
            encoding=encoding,
        )
        if isinstance(raw, bytes):
            return raw.decode(encoding)
        return raw
    return etree.tostring(element, pretty_print=pretty, encoding="unicode")


def write(
    element: _etree._Element,
    path: str | Path,
    *,
    pretty: bool = True,
    xml_declaration: bool = True,
    encoding: str = "utf-8",
) -> None:
    """Write *element* as an XML file to *path*.

    Args:
        element: The lxml element (or ElementTree root) to write.
        path: Destination file path.
        pretty: Whether to pretty-print with indentation.
        xml_declaration: Whether to write the ``<?xml …?>`` declaration.
        encoding: File encoding.
    """
    from lxml import etree

    tree = etree.ElementTree(element)
    tree.write(
        str(path),
        pretty_print=pretty,
        xml_declaration=xml_declaration,
        encoding=encoding,
    )


def indent(element: _etree._Element, space: str = "  ", level: int = 0) -> None:
    """In-place pretty-print *element* by adding whitespace text nodes.

    Requires lxml ≥ 4.5.

    Args:
        element: Root element to indent.
        space: Indentation string per level.
        level: Starting indentation level (default 0).
    """
    from lxml import etree

    etree.indent(element, space=space, level=level)
