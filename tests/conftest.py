"""Shared pytest fixtures for pytableau tests."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"

_FIXTURE_NAMES = [
    "minimal_v2022_4.twb",
    "single_datasource_v2023_1.twb",
    "multi_datasource_v2024_1.twb",
    "parameters_v2024_1.twb",
    "lod_heavy_v2024_1.twb",
    "dashboard_actions_v2024_1.twb",
]


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    return FIXTURE_DIR


@pytest.fixture(scope="session")
def minimal_twb() -> Path:
    return FIXTURE_DIR / "minimal_v2022_4.twb"


@pytest.fixture(scope="session")
def single_datasource_twb() -> Path:
    return FIXTURE_DIR / "single_datasource_v2023_1.twb"


@pytest.fixture(scope="session")
def multi_datasource_twb() -> Path:
    return FIXTURE_DIR / "multi_datasource_v2024_1.twb"


@pytest.fixture(scope="session")
def parameters_twb() -> Path:
    return FIXTURE_DIR / "parameters_v2024_1.twb"


@pytest.fixture(scope="session")
def lod_heavy_twb() -> Path:
    return FIXTURE_DIR / "lod_heavy_v2024_1.twb"


@pytest.fixture(scope="session")
def dashboard_actions_twb() -> Path:
    return FIXTURE_DIR / "dashboard_actions_v2024_1.twb"


@pytest.fixture(scope="session", params=_FIXTURE_NAMES)
def any_fixture_path(request) -> Path:
    return FIXTURE_DIR / request.param
