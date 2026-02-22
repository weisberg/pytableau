"""PackageManager: transparent ``.twbx`` ↔ temp directory management.

A ``.twbx`` file is a ZIP archive containing a ``.twb`` XML file and
optional data files (e.g. ``.hyper`` extract).  :class:`PackageManager`
handles extraction, mutation, and re-packaging transparently.

.. note::
    Full implementation is tracked in Phase 1 of the development plan.
"""

from __future__ import annotations

import zipfile
from pathlib import Path


def is_twbx(path: Path) -> bool:
    """Return ``True`` if *path* is a valid ``.twbx`` ZIP archive."""
    return path.suffix.lower() == ".twbx" and zipfile.is_zipfile(path)


def is_twb(path: Path) -> bool:
    """Return ``True`` if *path* is a ``.twb`` XML file."""
    return path.suffix.lower() == ".twb"
