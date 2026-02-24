"""Agent ergonomics for pytableau — discovery, transactions, and structured receipts.

This package makes pytableau easier for AI agents and automation pipelines to use:

- :mod:`pytableau.agents.discovery` — introspect workbooks and datasources as plain dicts
- :mod:`pytableau.agents.transactions` — atomic multi-step mutations with XML rollback
- :mod:`pytableau.agents.receipts` — structured results from mutation operations
"""

from __future__ import annotations

from pytableau.agents.receipts import OperationReceipt
from pytableau.agents.transactions import WorkbookTransaction

__all__ = [
    "OperationReceipt",
    "WorkbookTransaction",
]
