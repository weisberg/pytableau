"""Agent-ready CLI interface for pytableau — powered by tooli.

Provides the ``pytableau`` command-line tool with automatic JSON output,
MCP tool exposure, dry-run planning, and structured error recovery.

Install the CLI extra to use::

    pip install "pytableau[cli]"

Usage::

    pytableau inspect workbook.twbx
    pytableau diff before.twb after.twb
    pytableau swap-connection workbook.twb --server prod-db.corp.com
    pytableau inspect workbook.twbx --json
    pytableau --help-agent
    pytableau mcp serve --transport stdio
"""

from __future__ import annotations
