"""Tests for phase 4–6 features: template, dashboard/worksheet mutation, discovery, server."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from lxml import etree
import pytest

from pytableau.core.fields import FieldReference
from pytableau.core.workbook import Workbook
from pytableau.exceptions import UnmappedPlaceholderError
from pytableau.server.client import AuthenticationError
from pytableau.templates.engine import TemplateEngine
from pytableau.templates.library import get_template_path
from pytableau.xml.discovery import CorpusAnalyzer, ControlledDiffer


def _write_base_twb(path: Path) -> None:
    workbook = etree.Element(
        "workbook",
        attrib={
            "source-build": "20241.24.0312.0830",
            "source-platform": "test",
        },
    )

    datasources = etree.SubElement(workbook, "datasources")
    datasource = etree.SubElement(
        datasources,
        "datasource",
        attrib={"name": "Sales", "caption": "Sales"},
    )
    etree.SubElement(datasource, "connection", attrib={"class": "sqlserver"})
    columns = etree.SubElement(datasource, "columns")
    etree.SubElement(
        columns,
        "column",
        attrib={"name": "region", "caption": "Region", "datatype": "string", "role": "dimension"},
    )
    etree.SubElement(
        columns,
        "column",
        attrib={"name": "sales", "caption": "Sales", "datatype": "real", "role": "measure"},
    )

    worksheets = etree.SubElement(workbook, "worksheets")
    worksheet = etree.SubElement(
        worksheets,
        "worksheet",
        attrib={"name": "Overview"},
    )
    etree.SubElement(worksheet, "rows").text = "[Region]"
    etree.SubElement(worksheet, "cols").text = "[Sales]"
    marks = etree.SubElement(worksheet, "marks")
    etree.SubElement(marks, "color").text = "[Region]"
    etree.SubElement(worksheet, "datasource-dependencies").append(
        etree.Element("datasource", name="Sales")
    )

    dashboards = etree.SubElement(workbook, "dashboards")
    dashboard = etree.SubElement(dashboards, "dashboard", attrib={"name": "Dashboard"})
    etree.SubElement(
        dashboard,
        "size",
        attrib={"type": "automatic", "width": "1200", "height": "800"},
    )
    etree.SubElement(
        dashboard,
        "zone",
        attrib={"name": "root", "type": "layout-basic", "x": "0", "y": "0", "w": "100", "h": "100"},
    )

    path.write_text(
        etree.tostring(workbook, encoding="utf-8", xml_declaration=True, pretty_print=True).decode(
            "utf-8"
        ),
        encoding="utf-8",
    )


def _write_versioned_twb(path: Path, *, extra_tag: str | None = None) -> None:
    root = etree.Element("workbook", source-build="20241.24.0312.0830", source-platform="test")
    if extra_tag:
        etree.SubElement(root, extra_tag)
    path.write_text(
        etree.tostring(root, encoding="utf-8", xml_declaration=True, pretty_print=True).decode("utf-8"),
        encoding="utf-8",
    )


def _install_fake_tableau_serverclient(monkeypatch) -> dict[str, Any]:
    state: dict[str, Any] = {"signed_in": None, "published": [], "downloaded": []}

    class FakeAuthManager:
        def sign_in(self, auth: object) -> None:
            state["signed_in"] = auth

        def sign_out(self) -> None:
            state["signed_in"] = None

    class FakeWorkbookItem:
        def __init__(self, name: str, project_id: str) -> None:
            self.name = name
            self.project_id = project_id

    class FakeWorkbooks:
        def publish(self, item: FakeWorkbookItem, path: str, mode: str | object | None = None) -> None:
            state["published"].append((item.name, item.project_id, path, str(mode)))
            return {"name": item.name, "project": item.project_id, "path": path, "mode": str(mode)}

        def download(self, workbook_id: str, filepath: str | Path | None = None, **kwargs: Any) -> None:
            state["downloaded"].append((workbook_id, str(filepath)))
            target = Path(filepath) if filepath is not None else Path(f"{workbook_id}.twb")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("<workbook source-build='20241.24.0312.0830'></workbook>")

    class FakeServer:
        def __init__(self, _url: str, use_server_version: bool = True) -> None:
            self.url = _url
            self.auth = FakeAuthManager()
            self.workbooks = FakeWorkbooks()

    class FakePublishMode:
        Overwrite = "Overwrite"
        CreateNew = "CreateNew"

    class FakePersonalAccessTokenAuth:
        def __init__(self, token_name: str, token_secret: str, site_id: str | None = None) -> None:
            self.token_name = token_name
            self.token_secret = token_secret
            self.site_id = site_id

        def __repr__(self) -> str:
            return f"token:{self.token_name}@{self.site_id}"

    class FakeTableauAuth:
        def __init__(self, username: str, password: str, site_id: str | None = None) -> None:
            self.username = username
            self.password = password
            self.site_id = site_id

        def __repr__(self) -> str:
            return f"user:{self.username}@{self.site_id}"

    fake_tsc = SimpleNamespace(
        Server=FakeServer,
        PublishMode=FakePublishMode,
        WorkbookItem=FakeWorkbookItem,
        models=SimpleNamespace(WorkbookItem=FakeWorkbookItem),
        PersonalAccessTokenAuth=FakePersonalAccessTokenAuth,
        TableauAuth=FakeTableauAuth,
    )
    monkeypatch.setattr("pytableau.server.client._tsc", fake_tsc)
    return state


def test_template_engine_from_template_and_strict_behavior() -> None:
    engine = TemplateEngine(get_template_path("bar_chart"))
    assert "__DIMENSION__" in engine.discover_placeholders()
    with pytest.raises(UnmappedPlaceholderError):
        engine.map_fields({}, strict=True)

    wb = Workbook.from_template(
        "bar_chart",
        **{
            "__WORKSHEET__": "Overview",
            "__PLACEHOLDER_DS__": "Sales",
            "__DIMENSION__": "Region",
            "__MEASURE__": "Sales",
        },
    )
    assert wb.worksheets["Overview"].name == "Overview"
    assert wb.template.discover_placeholders() == {"__DASHBOARD__"}
    wb.template.map_fields({"__DASHBOARD__": "Dashboard"}, strict=True)
    assert not wb.template.discover_placeholders()


def test_worksheet_shelf_mutation_helpers(tmp_path: Path) -> None:
    path = tmp_path / "sample.twb"
    _write_base_twb(path)

    workbook = Workbook.open(path)
    worksheet = workbook.worksheets["Overview"]

    worksheet.add_to_shelf("rows", "Segment")
    assert worksheet.rows == [
        FieldReference("Region"),
        FieldReference("Segment"),
    ]
    worksheet.move_within_shelf("rows", "Segment", 0)
    assert worksheet.rows[0].name == "Segment"

    removed = worksheet.remove_from_shelf("rows", "Segment")
    assert removed == 1
    assert all(row.name != "Segment" for row in worksheet.rows)

    worksheet.add_to_shelf("color", "State")
    worksheet.move_within_shelf("color", "State", 0)
    assert [f.name for f in worksheet.marks.color] == ["State"]
    assert worksheet.remove_from_shelf("color", "State") == 1


def test_dashboard_action_and_zone_mutation(tmp_path: Path) -> None:
    path = tmp_path / "sample.twb"
    _write_base_twb(path)
    workbook = Workbook.open(path)
    dashboard = workbook.dashboards["Dashboard"]

    action = dashboard.add_filter_action("FilterByRegion", field="Region", source_sheet="Overview")
    assert action.name == "FilterByRegion"
    assert action.fields == ["Region"]
    assert dashboard.add_highlight_action("HighlightByRegion", field="Region").name == "HighlightByRegion"
    assert dashboard.add_url_action("OpenWeb", "https://example.com").name == "OpenWeb"
    assert len(dashboard.actions) == 3
    assert dashboard.remove_action("OpenWeb") == 1
    assert len(dashboard.actions) == 2

    zone = dashboard.add_zone("worksheet", "new", x=10, y=20, w=30, h=40, parent_name="root")
    assert zone.name == "new"
    assert dashboard.move_zone("new", x=99, y=88) == 1
    assert dashboard.remove_zone("new") == 1


def test_discovery_tools(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write_versioned_twb(corpus_dir / "one.twb")
    _write_versioned_twb(corpus_dir / "two.twb", extra_tag="dashboard")

    analyzer = CorpusAnalyzer(corpus_dir)
    summary = analyzer.analyze()
    assert summary["files"] == 2
    assert "workbook" in summary["tag_counts"]
    assert "workbook" == analyzer.top_tags(1)[0]

    before = tmp_path / "before.twb"
    after = tmp_path / "after.twb"
    _write_versioned_twb(before)
    _write_versioned_twb(after, extra_tag="sheet")
    differ = ControlledDiffer(before, after)
    delta = differ.xml_nodes()
    assert delta["added_tags"] == 1
    assert any(line.startswith("+ ") for line in differ.diff())


def _run_with_fake_server(monkeypatch, callback: Callable[[dict[str, Any]], None]) -> None:
    state = _install_fake_tableau_serverclient(monkeypatch)
    callback(state)
    assert state["signed_in"] is None
    assert state["published"]


def test_server_workflow_with_fake_client(monkeypatch, tmp_path: Path) -> None:
    from pytableau.server.client import ServerClient
    from pytableau.server.workflows import publish_workbook as workflow_publish_workbook
    from pytableau.server.workflows import download_workbook as workflow_download_workbook
    from pytableau.server.workflows import refresh_workbook as workflow_refresh_workbook

    workbook_path = tmp_path / "report.twbx"
    _write_versioned_twb(workbook_path, extra_tag="worksheet")

    def _exercise(state: dict[str, Any]) -> None:
        with ServerClient("https://server", site_id="site") as client:
            client.publish_workbook(workbook_path, project_id="proj", name="report", token_name="token", token_secret="secret")
            assert state["published"][0][0] == "report"

        workflow_publish_workbook(
            "https://server",
            workbook_path,
            project_id="proj",
            name="workflow-report",
            token_name="token",
            token_secret="secret",
        )
        assert state["published"][-1][0] == "workflow-report"

        client = ServerClient("https://server", site_id="site")
        with pytest.raises(AuthenticationError):
            client.publish_workbook(workbook_path, project_id="proj")

        downloaded = workflow_download_workbook(
            "https://server",
            "my-workbook-id",
            destination=tmp_path / "workflow.twb",
            token_name="token",
            token_secret="secret",
        )
        assert downloaded.version == "2024.1"

        workbook_out = workflow_refresh_workbook(
            "https://server",
            "my-workbook-id",
            lambda _wb: None,
            destination=tmp_path / "refreshed.twb",
            project_id="proj",
            token_name="token",
            token_secret="secret",
        )
        assert workbook_out.version == "2024.1"

    _run_with_fake_server(monkeypatch, _exercise)
