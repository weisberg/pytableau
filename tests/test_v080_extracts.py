"""Tests for v0.8.0 — Hyper Extract Management (M7).

All tests in this file require optional hyper/pandas dependencies and
are skipped if those are not installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# All tests require hyper + pandas
pytestmark = pytest.mark.requires_hyper


@pytest.fixture()
def sample_df():
    """Small DataFrame for testing."""
    pandas = pytest.importorskip("pandas")
    return pandas.DataFrame(
        {
            "Date": pandas.date_range("2024-01-01", periods=10, freq="D"),
            "Sales": range(10, 110, 10),
            "Region": ["East"] * 5 + ["West"] * 5,
        }
    )


@pytest.fixture()
def hyper_path(tmp_path, sample_df):
    """Create a pre-populated .hyper file for testing."""
    from pytableau.data.bridge import HyperBridge

    path = tmp_path / "test.hyper"
    bridge = HyperBridge(path)
    bridge.from_dataframe(sample_df, table="Extract", mode="replace")
    return path


# ---------------------------------------------------------------------------
# HyperFile context manager
# ---------------------------------------------------------------------------


def test_hyper_file_context_manager(hyper_path):
    from pytableau.data.bridge import HyperFile

    with HyperFile(hyper_path) as hf:
        assert hf._bridge is not None
    assert hf._bridge is None


def test_hyper_file_not_entered_raises():
    from pytableau.data.bridge import HyperFile

    hf = HyperFile(Path("/nonexistent/file.hyper"))
    with pytest.raises(RuntimeError, match="context manager"):
        _ = hf._b


def test_hyper_file_list_tables(hyper_path):
    from pytableau.data.bridge import HyperFile

    with HyperFile(hyper_path) as hf:
        tables = hf.list_tables()
    assert isinstance(tables, list)


def test_hyper_file_schema(hyper_path):
    from pytableau.data.bridge import HyperFile

    with HyperFile(hyper_path) as hf:
        schema = hf.schema("Extract")
    assert isinstance(schema, list)
    assert len(schema) > 0
    assert "name" in schema[0]


def test_hyper_file_row_count(hyper_path, sample_df):
    from pytableau.data.bridge import HyperFile

    with HyperFile(hyper_path) as hf:
        count = hf.row_count("Extract")
    assert count == len(sample_df)


# ---------------------------------------------------------------------------
# bulk_insert
# ---------------------------------------------------------------------------


def test_bulk_insert_all_rows(tmp_path, sample_df):
    from pytableau.data.bridge import HyperFile

    path = tmp_path / "bulk.hyper"
    with HyperFile(path) as hf:
        written = hf.bulk_insert(sample_df, batch_size=3)
    assert written == len(sample_df)


def test_bulk_insert_correct_row_count_in_file(tmp_path, sample_df):
    from pytableau.data.bridge import HyperFile

    path = tmp_path / "bulk2.hyper"
    with HyperFile(path) as hf:
        hf.bulk_insert(sample_df)
        count = hf.row_count("Extract")
    assert count == len(sample_df)


# ---------------------------------------------------------------------------
# contract_test
# ---------------------------------------------------------------------------


def test_contract_test_no_hyper_path():
    from pytableau.core.workbook import Workbook
    from pytableau.data.extract import ExtractManager

    fixture_dir = Path(__file__).parent / "fixtures"
    wb = Workbook.open(fixture_dir / "minimal_v2022_4.twb")
    ds = wb.datasources[0]
    issues = ExtractManager.contract_test(ds)
    # No hyper connection → issues list should be non-empty
    assert isinstance(issues, list)
    assert len(issues) > 0


def test_contract_test_returns_list():
    from pytableau.core.workbook import Workbook
    from pytableau.data.extract import ExtractManager

    fixture_dir = Path(__file__).parent / "fixtures"
    wb = Workbook.open(fixture_dir / "minimal_v2022_4.twb")
    ds = wb.datasources[0]
    result = ExtractManager.contract_test(ds)
    assert isinstance(result, list)
