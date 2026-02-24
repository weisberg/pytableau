from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

from pytableau.core.workbook import Workbook

pytest.importorskip("pandas", reason="pandas is required for extract lifecycle tests")
pytest.importorskip("pantab", reason="pantab is required for extract lifecycle tests")
pytest.importorskip(
    "tableauhyperapi", reason="tableauhyperapi is required for extract lifecycle tests"
)
pytestmark = [pytest.mark.requires_hyper]


def _write_extract_twb(path: Path) -> None:
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
        attrib={
            "name": "Sales",
            "caption": "Sales Data",
        },
    )
    etree.SubElement(datasource, "connection", attrib={"class": "sqlserver"})
    etree.SubElement(datasource, "columns")
    etree.SubElement(datasource, "metadata-records")
    Path(path).write_text(
        etree.tostring(workbook, encoding="utf-8", xml_declaration=True, pretty_print=True).decode(
            "utf-8"
        ),
        encoding="utf-8",
    )


def test_create_attach_detach_lifecycle(tmp_path: Path) -> None:
    import pandas as pd

    path = tmp_path / "sample.twb"
    _write_extract_twb(path)
    workbook = Workbook.open(path)
    sales = workbook.datasources["Sales"]

    source_df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    sales.create_extract(source_df)
    assert sales.hyper is not None
    assert sales.connections[0].class_ == "hyper"
    assert sales._hyper_path is not None
    assert sales._hyper_path.exists()
    assert len(sales.xml_node.find("metadata-records")) == len(source_df.columns)

    sales.detach_extract()
    assert sales.connections[0].class_ == "sqlserver"
    assert sales._hyper_path is None

    output = tmp_path / "with_extract.twbx"
    workbook.save_as(output)
    with ZipFile(output) as archive:
        assert any(name.endswith(".hyper") for name in archive.namelist())
