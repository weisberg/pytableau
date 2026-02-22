from __future__ import annotations

from pytableau.data.types import all_mappings, pandas_to_hyper, pandas_to_tableau_xml


def test_dataframe_type_mappings_include_expected_rows() -> None:
    mappings = all_mappings()
    assert mappings["pandas_to_hyper"]["int"] == "BIGINT"
    assert mappings["pandas_to_hyper"]["float"] == "DOUBLE"
    assert mappings["pandas_to_hyper"]["bool"] == "BOOL"
    assert mappings["hyper_to_tableau_xml"]["BIGINT"] == "integer"


def test_pandas_to_hyper_map() -> None:
    assert pandas_to_hyper("object") == "TEXT"
    assert pandas_to_hyper("int64") == "BIGINT"
    assert pandas_to_hyper("float64") == "DOUBLE"
    assert pandas_to_hyper("bool") == "BOOL"
    assert pandas_to_hyper("datetime64[ns]") == "TIMESTAMP"


def test_pandas_to_tableau_xml_map() -> None:
    assert pandas_to_tableau_xml("int64") == "integer"
    assert pandas_to_tableau_xml("float64") == "real"
    assert pandas_to_tableau_xml("bool") == "boolean"
    assert pandas_to_tableau_xml("datetime64") == "datetime"
