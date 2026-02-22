from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from pytableau.core.workbook import Workbook

pytest.importorskip("pandas", reason="pandas is optional for metadata sync tests")
pytestmark = [pytest.mark.requires_hyper]


def _write_extract_dataset_twb(path: Path) -> None:
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
    Path(path).write_text(
        etree.tostring(workbook, encoding="utf-8", xml_declaration=True, pretty_print=True).decode(
            "utf-8"
        ),
        encoding="utf-8",
    )


def test_metadata_records_are_rebuilt_for_dataframe_schema(tmp_path: Path) -> None:
    import pandas as pd

    path = tmp_path / "sample.twb"
    _write_extract_dataset_twb(path)
    workbook = Workbook.open(path)
    sales = workbook.datasources["Sales"]

    df = pd.DataFrame(
        {
            "Product Category": ["A", "B", "C"],
            "Revenue": [10.5, 20.0, 15.25],
        }
    )
    sales._sync_extracted_metadata(df)

    metadata = sales.xml_node.find("metadata-records")
    assert metadata is not None
    records = metadata.findall("metadata-record")
    assert len(records) == 2
    assert records[0].findtext("remote-name") == "Product Category"
    assert records[0].findtext("local-name") == "[Product Category]"
    assert records[1].findtext("remote-name") == "Revenue"
