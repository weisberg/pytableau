"""Package layer: transparent ``.twbx`` ZIP handling.

Provides :class:`~pytableau.package.manager.PackageManager` which
manages the extraction and re-packaging of ``.twbx`` files into
temporary directories, so the rest of the codebase can work with
plain files.

.. note::
    Full implementation is tracked in Phase 1 of the development plan.
"""

from __future__ import annotations
