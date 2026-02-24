from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from pytableau.core.workbook import Workbook
from pytableau.package.manager import PackageManager


def _write_minimal_twb(path: Path) -> None:
    workbook = etree.Element(
        "workbook",
        attrib={
            "source-build": "20241.24.0312.0830",
            "source-platform": "test",
        },
    )
    datasources = etree.SubElement(workbook, "datasources")
    etree.SubElement(datasources, "datasource", name="Sales")
    worksheets = etree.SubElement(workbook, "worksheets")
    etree.SubElement(worksheets, "worksheet", name="Overview")
    dashboards = etree.SubElement(workbook, "dashboards")
    etree.SubElement(dashboards, "dashboard", name="Exec")
    Path(path).write_text(
        etree.tostring(workbook, encoding="utf-8", xml_declaration=True, pretty_print=True).decode(
            "utf-8"
        ),
        encoding="utf-8",
    )


def test_package_manager_preserves_twb_contents(tmp_path: Path) -> None:
    twb_path = tmp_path / "workbook.twb"
    _write_minimal_twb(twb_path)

    pm = PackageManager(twb_path)
    assert not pm.is_twbx
    assert pm.twb_path == twb_path

    with pm:
        output = tmp_path / "copied.twb"
        pm.save_as(output)
        assert output.exists()
        parsed = etree.parse(str(output))
        assert parsed.getroot().tag == "workbook"


def test_package_manager_round_trip_twbx(tmp_path: Path) -> None:
    source_twb = tmp_path / "source.twb"
    source_data = tmp_path / "Data" / "example.txt"
    source_data.parent.mkdir(parents=True)
    _write_minimal_twb(source_twb)
    source_data.write_text("ok")

    twbx_path = tmp_path / "source.twbx"
    with zipfile.ZipFile(twbx_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(source_twb, "source.twb")
        zf.write(source_data, "Data/example.txt")

    output_twbx = tmp_path / "roundtrip.twbx"
    with PackageManager(twbx_path) as pm:
        assert pm.is_twbx
        assert pm.twb_path.name == "source.twb"
        pm.save_as(output_twbx)

    with zipfile.ZipFile(output_twbx) as zf:
        names = set(zf.namelist())
    assert "source.twb" in names
    assert "Data/example.txt" in names


def test_workbook_open_and_save_twb(tmp_path: Path) -> None:
    source_twb = tmp_path / "source.twb"
    _write_minimal_twb(source_twb)

    workbook = Workbook.open(source_twb)
    assert workbook.version == "2024.1"
    assert list(workbook.datasources.names) == ["Sales"]
    assert list(workbook.worksheets.names) == ["Overview"]

    output = tmp_path / "out.twb"
    workbook.save_as(output)
    parsed = etree.parse(str(output))
    assert parsed.xpath("count(/workbook/datasources/datasource) = 1")
