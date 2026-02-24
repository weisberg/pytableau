"""Round-trip tests for golden fixture workbooks — #59 #60."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import canonicalize_twb

FIXTURE_NAMES = [
    "minimal_v2022_4.twb",
    "single_datasource_v2023_1.twb",
    "multi_datasource_v2024_1.twb",
    "parameters_v2024_1.twb",
    "lod_heavy_v2024_1.twb",
    "dashboard_actions_v2024_1.twb",
]

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_roundtrip(name: str, tmp_path: Path) -> None:
    """Open a fixture, save it without modification, and verify canonical equality."""
    from pytableau.core.workbook import Workbook

    source = FIXTURE_DIR / name
    wb = Workbook.open(source)
    dest = tmp_path / name
    wb.save_as(dest, scrub_credentials=False)

    assert canonicalize_twb(source) == canonicalize_twb(dest), (
        f"Round-trip produced different canonical XML for {name}"
    )


def test_canonicalize_helper(minimal_twb: Path) -> None:
    """canonicalize_twb is deterministic across two calls."""
    c1 = canonicalize_twb(minimal_twb)
    c2 = canonicalize_twb(minimal_twb)
    assert c1 == c2
    assert "<workbook" in c1
