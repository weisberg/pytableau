"""Optional CLI interface for pytableau.

Provides the ``pytableau`` command-line tool.

Usage::

    pytableau inspect workbook.twbx
    pytableau diff before.twb after.twb
    pytableau swap workbook.twb --server prod-db.corp.com --db analytics_prod

.. note::
    Full implementation is tracked in Phase 1 of the development plan.
"""

from __future__ import annotations
