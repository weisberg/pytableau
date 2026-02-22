"""High-level Server workflows: publish, download, refresh, round-trip."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from pytableau.core.workbook import Workbook
from pytableau.server.client import ServerClient


def download_workbook(
    server: str,
    workbook_id: str,
    destination: str | Path,
    **auth: object,
) -> Workbook:
    """Download a workbook and return a loaded :class:`Workbook` object."""
    with ServerClient(server, **auth) as client:
        path = client.download_workbook(workbook_id, destination=destination, **auth)
        return Workbook.open(path)


def publish_workbook(
    server: str,
    workbook: str | Path,
    project_id: str,
    *,
    name: str | None = None,
    overwrite: bool = True,
    **auth: object,
) -> object:
    """Publish one workbook to a target project."""
    with ServerClient(server, **auth) as client:
        return client.publish_workbook(
            workbook,
            project_id=project_id,
            name=name,
            overwrite=overwrite,
        )


def refresh_workbook(
    server: str,
    workbook_id: str,
    modifier: Callable[[Workbook], None],
    *,
    destination: str | Path,
    project_id: str,
    name: str | None = None,
    overwrite: bool = True,
    **auth: object,
) -> Workbook:
    """Download, mutate, republish, and return the local modified workbook."""
    with ServerClient(server, **auth) as client:
        with Workbook.open(
            client.download_workbook(workbook_id, destination=destination, **auth)
        ) as workbook:
            modifier(workbook)
            workbook.save_as(destination)
            client.publish_workbook(
                destination,
                project_id=project_id,
                name=name,
                overwrite=overwrite,
            )
            return workbook
