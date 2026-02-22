from __future__ import annotations

import pytest

from pytableau.data.bridge import HyperBridge

pytest.importorskip("pandas", reason="pandas is required for HyperBridge DataFrame tests")
pytest.importorskip("pantab", reason="pantab is required for HyperBridge integration tests")
pytest.importorskip("tableauhyperapi", reason="tableauhyperapi is required for HyperBridge integration tests")
pytestmark = [pytest.mark.requires_hyper]


def _sample_df():
    import pandas as pd

    return pd.DataFrame(
        {
            "Product": ["A", "B", "C", "D"],
            "Revenue": [100.0, 200.5, 300.25, 400.75],
        }
    )


def test_hyper_bridge_roundtrip_dataframe(tmp_path):
    import pandas as pd

    df = _sample_df()
    bridge = HyperBridge(tmp_path / "sample.hyper")
    bridge.from_dataframe(df)
    back = bridge.to_dataframe()

    assert isinstance(back, pd.DataFrame)
    assert list(back.columns) == ["Product", "Revenue"]
    assert len(back) == len(df)


def test_hyper_bridge_query_row_count(tmp_path):
    import pandas as pd

    df = _sample_df()
    bridge = HyperBridge(tmp_path / "sample_query.hyper")
    bridge.from_dataframe(df)

    result = bridge.query("SELECT COUNT(*) AS row_count FROM [Extract]")
    assert isinstance(result, pd.DataFrame)
    assert result.iloc[0, 0] == len(df)
