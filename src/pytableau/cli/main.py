"""CLI entry point: ``pytableau inspect``, ``pytableau diff``, ``pytableau swap``.

The CLI is built with `click <https://click.palletsprojects.com/>`_.

.. note::
    Full implementation is tracked in Phase 1 of the development plan.
    Phase 0 ships a minimal skeleton so that the ``pytableau`` console
    script entry point is importable.
"""

from __future__ import annotations

import json

try:
    import click
except ImportError as exc:
    raise ImportError(
        "The pytableau CLI requires 'click'. "
        "Install it with: pip install click"
    ) from exc

from pytableau.core.workbook import Workbook


@click.group()
@click.version_option(package_name="pytableau")
def app() -> None:
    """pytableau — The unified Python SDK for Tableau workbook engineering."""


@app.command()
@click.argument("workbook", type=click.Path(exists=True))
@click.option("--format", "fmt", default="table", type=click.Choice(["table", "json"]))
def inspect(workbook: str, fmt: str) -> None:
    """Inspect a Tableau workbook and print its contents."""
    wb = Workbook.open(workbook)
    payload = {
        "path": str(workbook),
        "version": wb.version,
        "source_platform": wb.source_platform,
        "datasource_count": len(wb.datasources),
        "datasources": wb.datasources.names,
        "worksheet_count": len(wb.worksheets),
        "worksheets": wb.worksheets.names,
        "dashboard_count": len(wb.dashboards),
        "dashboards": wb.dashboards.names,
    }

    if fmt == "json":
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    click.echo(f"Workbook: {workbook}")
    click.echo(f"Version: {wb.version}")
    if wb.source_platform:
        click.echo(f"Source platform: {wb.source_platform}")
    click.echo(f"Datasources ({payload['datasource_count']}):")
    for name in payload["datasources"]:
        click.echo(f"  - {name}")
    click.echo(f"Worksheets ({payload['worksheet_count']}):")
    for name in payload["worksheets"]:
        click.echo(f"  - {name}")
    click.echo(f"Dashboards ({payload['dashboard_count']}):")
    for name in payload["dashboards"]:
        click.echo(f"  - {name}")


@app.command()
@click.argument("before", type=click.Path(exists=True))
@click.argument("after", type=click.Path(exists=True))
def diff(before: str, after: str) -> None:
    """Show semantic differences between two Tableau workbooks."""
    before_wb = Workbook.open(before)
    after_wb = Workbook.open(after)

    before_xml = before_wb.to_xml_string().splitlines()
    after_xml = after_wb.to_xml_string().splitlines()

    if before_xml == after_xml:
        click.echo("No differences detected.")
        return

    before_set = {line for line in before_xml}
    after_set = {line for line in after_xml}
    added = sorted(after_set - before_set)
    removed = sorted(before_set - after_set)

    click.echo(f"Added lines: {len(added)}")
    for item in added[:40]:
        click.echo(f"  + {item}")
    if len(added) > 40:
        click.echo(f"  ... ({len(added) - 40} more)")

    click.echo(f"Removed lines: {len(removed)}")
    for item in removed[:40]:
        click.echo(f"  - {item}")
    if len(removed) > 40:
        click.echo(f"  ... ({len(removed) - 40} more)")


@app.command()
@click.argument("workbook", type=click.Path(exists=True))
@click.option("--server", required=True, help="New database server hostname")
@click.option("--db", required=False, help="New database name")
@click.option("--username", required=False, help="New database username")
@click.option("--output", "-o", required=False, help="Output path (default: overwrite)")
def swap(
    workbook: str,
    server: str,
    db: str | None,
    username: str | None,
    output: str | None,
) -> None:
    """Swap connection properties in a Tableau workbook."""
    wb = Workbook.open(workbook)
    updated = 0

    for conn in wb.xml_tree.findall(".//connection"):
        if server:
            conn.set("server", server)
            updated += 1
        if db:
            if "dbname" in conn.attrib:
                conn.set("dbname", db)
            elif "dbName" in conn.attrib:
                conn.set("dbName", db)
            else:
                conn.set("dbname", db)
            updated += 1
        if username:
            conn.set("username", username)
            updated += 1

    destination = output or workbook
    wb.save_as(destination)
    click.echo(f"Updated {updated} connection attributes.")
