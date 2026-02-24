"""Structural XML diff between two Tableau workbook files.

Provides line-level unified diffs on canonicalized (thumbnail-stripped,
volatile-attribute-removed) XML for use in CLI output and git hooks.

For semantic object-model diffs, use :mod:`pytableau.inspect.diff`.
"""

from __future__ import annotations

import difflib
from pathlib import Path


def xml_diff(before_path: Path | str, after_path: Path | str) -> list[str]:
    """Return unified diff lines of canonicalized XML.

    Strips thumbnails and volatile attributes before diffing so that only
    semantically meaningful changes appear.

    Args:
        before_path: Path to the base ``.twb`` file.
        after_path: Path to the modified ``.twb`` file.

    Returns:
        List of unified diff lines (with ``+``/``-``/``@@`` prefixes).
    """
    from pytableau.xml.canonical import git_clean

    a_xml = git_clean(before_path, in_place=False)
    b_xml = git_clean(after_path, in_place=False)
    a_lines = a_xml.splitlines(keepends=True)
    b_lines = b_xml.splitlines(keepends=True)
    return list(
        difflib.unified_diff(
            a_lines,
            b_lines,
            fromfile=str(before_path),
            tofile=str(after_path),
        )
    )
