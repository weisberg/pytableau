"""CLI entry point: ``pytableau inspect``, ``pytableau diff``, ``pytableau swap``.

The CLI is built with `click <https://click.palletsprojects.com/>`_.

.. note::
    Full implementation is tracked in Phase 1 of the development plan.
    Phase 0 ships a minimal skeleton so that the ``pytableau`` console
    script entry point is importable.
"""

from __future__ import annotations

try:
    import click
except ImportError as exc:
    raise ImportError(
        "The pytableau CLI requires 'click'. "
        "Install it with: pip install click"
    ) from exc


@click.group()
@click.version_option(package_name="pytableau")
def app() -> None:
    """pytableau — The unified Python SDK for Tableau workbook engineering."""


@app.command()
@click.argument("workbook", type=click.Path(exists=True))
@click.option("--format", "fmt", default="table", type=click.Choice(["table", "json"]))
def inspect(workbook: str, fmt: str) -> None:
    """Inspect a Tableau workbook and print its contents."""
    raise NotImplementedError("pytableau inspect is implemented in Phase 1")


@app.command()
@click.argument("before", type=click.Path(exists=True))
@click.argument("after", type=click.Path(exists=True))
def diff(before: str, after: str) -> None:
    """Show semantic differences between two Tableau workbooks."""
    raise NotImplementedError("pytableau diff is implemented in Phase 2")


@app.command()
@click.argument("workbook", type=click.Path(exists=True))
@click.option("--server", required=True, help="New database server hostname")
@click.option("--db", required=False, help="New database name")
@click.option("--username", required=False, help="New database username")
@click.option("--output", "-o", required=False, help="Output path (default: overwrite)")
def swap(workbook: str, server: str, db: str | None, username: str | None, output: str | None) -> None:
    """Swap connection properties in a Tableau workbook."""
    raise NotImplementedError("pytableau swap is implemented in Phase 2")
