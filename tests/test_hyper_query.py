from __future__ import annotations

import pytest

from pytableau.data.bridge import HyperBridge

pytest.importorskip("pandas", reason="pandas is required for HyperBridge SQL tests")
pytest.importorskip("pantab", reason="pantab is required for HyperBridge SQL tests")
pytest.importorskip(
    "tableauhyperapi", reason="tableauhyperapi is required for HyperBridge SQL tests"
)
pytestmark = [pytest.mark.requires_hyper]


def _sample_df():
    import pandas as pd

    return pd.DataFrame({"A": [1, 2, 3], "B": [10, 20, 30]})


def test_query_returns_filtered_rows(tmp_path):
    df = _sample_df()
    bridge = HyperBridge(tmp_path / "query.hyper")
    bridge.from_dataframe(df)

    result = bridge.query("SELECT A FROM [Extract] WHERE A > 1")
    assert list(result["A"]) == [2, 3]
