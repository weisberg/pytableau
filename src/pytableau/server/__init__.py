"""Tableau Server / Cloud integration.

Wraps ``tableauserverclient`` with pytableau conventions, providing
one-call publish, download, and round-trip workflows.

Requires the ``[server]`` extra::

    pip install "pytableau[server]"

.. note::
    Full implementation is tracked in Phase 5 of the development plan.
"""

from __future__ import annotations
