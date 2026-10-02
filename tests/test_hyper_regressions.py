"""Exercise real Hyper I/O, preservation, and composite-key mutations."""

from __future__ import annotations

import datetime
import shutil

import pytest

from pytableau.data.bridge import HyperBridge, HyperFile

pd = pytest.importorskip("pandas")
pytest.importorskip("pantab")
hyperapi = pytest.importorskip("tableauhyperapi")
pytestmark = pytest.mark.requires_hyper


def test_replacing_one_table_preserves_other_tables(tmp_path):
    bridge = HyperBridge(tmp_path / "multi.hyper")
    bridge.from_dataframe(pd.DataFrame({"a": [1]}), table="Other")
    bridge.from_dataframe(pd.DataFrame({"b": [2]}))
    assert bridge.to_dataframe(table="Other")["a"].tolist() == [1]
    assert bridge.to_dataframe()["b"].tolist() == [2]


def test_query_retains_names_for_empty_results(tmp_path):
    bridge = HyperBridge(tmp_path / "empty.hyper")
    bridge.from_dataframe(pd.DataFrame({"a": [1]}))
    result = bridge.query('SELECT "a" AS "Empty Result" FROM "Extract" WHERE FALSE')
    assert result.empty
    assert result.columns.tolist() == ["Empty Result"]


def test_bulk_insert_empty_dataframe_clears_old_rows(tmp_path):
    with HyperFile(tmp_path / "empty.hyper") as hf:
        df = pd.DataFrame({"a": [1]})
        hf.bulk_insert(df)
        assert hf.bulk_insert(df.iloc[:0]) == 0
        assert hf.row_count() == 0


@pytest.mark.parametrize("batch_size", [0, -1])
def test_bulk_insert_rejects_invalid_batch_size(tmp_path, batch_size):
    with HyperFile(tmp_path / "invalid.hyper") as hf, pytest.raises(ValueError, match="positive"):
        hf.bulk_insert(pd.DataFrame({"a": [1]}), batch_size=batch_size)


def test_upsert_matches_composite_keys_and_escaped_values(tmp_path):
    path = tmp_path / "upsert.hyper"
    original = pd.DataFrame(
        {"key": ["O'Brien", "O'Brien", "Other"], "part": [1, 2, 1], "value": [10, 20, 30]}
    )
    incoming = pd.DataFrame({"key": ["O'Brien", "New"], "part": [1, 3], "value": [11, 40]})
    with HyperFile(path) as hf:
        hf.bulk_insert(original)
        assert hf.upsert(incoming, ["key", "part"]) == (1, 2)
    result = HyperBridge(path).to_dataframe().sort_values(["key", "part"])
    assert result["value"].tolist() == [40, 11, 20, 30]


def test_upsert_matches_null_keys(tmp_path):
    path = tmp_path / "null.hyper"
    with HyperFile(path) as hf:
        hf.bulk_insert(
            pd.DataFrame({"key": pd.Series([1, None], dtype="Int64"), "value": [10, 20]})
        )
        assert hf.upsert(
            pd.DataFrame({"key": pd.Series([None], dtype="Int64"), "value": [21]}), ["key"]
        ) == (1, 1)
        assert hf.row_count() == 2


def test_failed_upsert_preserves_original_extract(tmp_path):
    path = tmp_path / "preserve.hyper"
    with HyperFile(path) as hf:
        hf.bulk_insert(pd.DataFrame({"key": [1], "value": [10]}))
        before = path.read_bytes()
        with pytest.raises(hyperapi.HyperException):
            hf.upsert(pd.DataFrame({"key": [1], "value": ["not an integer"]}), ["key"])
        assert path.read_bytes() == before
        assert hf.row_count() == 1
    assert HyperBridge(path).to_dataframe()["value"].tolist() == [10]


def test_rolling_refresh_removes_old_rows(tmp_path):
    today = datetime.date.today()
    path = tmp_path / "rolling.hyper"
    original = pd.DataFrame(
        {"date": pd.to_datetime([today - datetime.timedelta(days=20), today]), "value": [1, 2]}
    )
    incoming = pd.DataFrame({"date": pd.to_datetime([today]), "value": [3]})
    with HyperFile(path) as hf:
        hf.bulk_insert(original)
        assert hf.rolling_window_refresh(incoming, "date", 10) == 1
        assert hf.row_count() == 2
    assert sorted(HyperBridge(path).to_dataframe()["value"].tolist()) == [2, 3]


def test_rolling_refresh_surfaces_delete_failures(tmp_path):
    path = tmp_path / "failed_rolling.hyper"
    with HyperFile(path) as hf:
        df = pd.DataFrame({"value": [1]})
        hf.bulk_insert(df)
        before = path.read_bytes()
        with pytest.raises(hyperapi.HyperException):
            hf.rolling_window_refresh(pd.DataFrame({"missing_date": ["today"]}), "missing_date", 10)
        assert path.read_bytes() == before


def test_datasource_upsert_delegates_to_working_extract_api(tmp_path, minimal_twb):
    from pytableau import Workbook

    source = tmp_path / "source.twb"
    shutil.copyfile(minimal_twb, source)
    with Workbook.open(source) as wb:
        ds = wb.datasources[0]
        ds.create_extract(pd.DataFrame({"key": [1, 2], "value": [10, 20]}))
        assert (
            ds.upsert_extract(pd.DataFrame({"key": [1], "value": [11]}), key_columns=["key"]) == 1
        )
        assert sorted(ds.hyper.to_dataframe()["value"].tolist()) == [11, 20]


def test_failed_bulk_batch_preserves_original_database(tmp_path):
    path = tmp_path / "batches.hyper"
    with HyperFile(path) as hf:
        hf.bulk_insert(pd.DataFrame({"a": [99]}))
        original = path.read_bytes()
        with pytest.raises(ValueError, match="type mismatch"):
            hf.bulk_insert(pd.DataFrame({"a": [1, "not an integer"]}), batch_size=1)
        assert path.read_bytes() == original
    assert HyperBridge(path).to_dataframe()["a"].tolist() == [99]


def test_upsert_creates_missing_table_and_preserves_other_tables(tmp_path):
    path = tmp_path / "new_table.hyper"
    bridge = HyperBridge(path)
    bridge.from_dataframe(pd.DataFrame({"value": [99]}), table="Other")
    with HyperFile(path) as hf:
        assert hf.upsert(pd.DataFrame({"id": [1]}), ["id"]) == (0, 1)
    assert bridge.to_dataframe(table="Other")["value"].tolist() == [99]
    assert bridge.to_dataframe()["id"].tolist() == [1]
