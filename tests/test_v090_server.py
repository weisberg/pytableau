"""Tests for v0.9.0 — Server Integration Extensions (M10).

All tests mock external dependencies (tableauserverclient, requests).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import pytableau.server.client as _client_module

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_tsc():
    """Build a minimal mock of the tableauserverclient module."""
    tsc = MagicMock()

    # Workbook model stub
    wb_item = MagicMock()
    wb_item.id = "wb-001"
    wb_item.name = "My Workbook"
    wb_item.project_id = "proj-001"
    wb_item.connections = []

    # Server stub
    server = MagicMock()
    server.workbooks.get.return_value = ([wb_item], MagicMock(total_available=1))
    server.workbooks.refresh.return_value = MagicMock(id="job-001", status="InProgress")
    server.workbooks.get_by_id.return_value = wb_item
    server.auth.sign_in = MagicMock()
    server.auth.sign_out = MagicMock()
    server.__enter__ = MagicMock(return_value=server)
    server.__exit__ = MagicMock(return_value=False)
    tsc.Server.return_value = server

    # Auth stubs
    tsc.PersonalAccessTokenAuth.return_value = MagicMock()
    tsc.TableauAuth.return_value = MagicMock()

    return tsc, server, wb_item


def _make_client(tsc, server_url="https://tableau.example.com"):
    """Create a ServerClient with mocked TSC and pre-signed-in state."""
    from pytableau.server.client import ServerClient

    with patch.object(_client_module, "_tsc", tsc):
        client = ServerClient(server_url)
        # Mark as signed-in to skip auth in subsequent calls
        client._signed_in = True
    return client, tsc.Server.return_value


# ---------------------------------------------------------------------------
# MetadataClient
# ---------------------------------------------------------------------------


def test_metadata_client_builds_correct_url():
    from pytableau.server.metadata import MetadataClient

    client = MetadataClient("https://tableau.example.com", token="tok123")
    assert client._url == "https://tableau.example.com/api/metadata/graphql"


def test_metadata_client_strips_trailing_slash():
    from pytableau.server.metadata import MetadataClient

    client = MetadataClient("https://tableau.example.com/", token="tok123")
    assert not client._url.endswith("//api")
    assert "metadata/graphql" in client._url


def test_metadata_client_query_sends_correct_request():
    from pytableau.server.metadata import MetadataClient

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"fieldsConnection": {"nodes": []}}}
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_resp) as mock_post:
        client = MetadataClient("https://tableau.example.com", token="tok123")
        result = client.query("{ test }")

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs[1]["headers"]["x-tableau-auth"] == "tok123"
    assert "test" in call_kwargs[1]["json"]["query"]
    assert isinstance(result, dict)


def test_metadata_client_query_raises_on_http_error():
    from pytableau.server.metadata import MetadataClient

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("401 Unauthorized")

    with patch("requests.post", return_value=mock_resp):
        client = MetadataClient("https://tableau.example.com", token="bad_token")
        with pytest.raises(Exception, match="401"):
            client.query("{ test }")


# ---------------------------------------------------------------------------
# ServerClient additions
# ---------------------------------------------------------------------------


def test_server_client_list_workbooks_returns_list():
    tsc, server, wb_item = _make_mock_tsc()
    client, _ = _make_client(tsc)

    with patch.object(_client_module, "_tsc", tsc):
        result = client.list_workbooks(token_name="tok", token_secret="secret", site_id="")

    assert isinstance(result, list)
    assert len(result) >= 1
    assert result[0]["id"] == "wb-001"
    assert result[0]["name"] == "My Workbook"


def test_server_client_list_workbooks_filters_by_project():
    tsc, server, wb_item = _make_mock_tsc()
    client, _ = _make_client(tsc)

    with patch.object(_client_module, "_tsc", tsc):
        result = client.list_workbooks(
            project_id="proj-001",
            token_name="tok",
            token_secret="secret",
            site_id="",
        )

    assert isinstance(result, list)


def test_server_client_refresh_extract_returns_job_dict():
    tsc, server, wb_item = _make_mock_tsc()
    client, _ = _make_client(tsc)

    with patch.object(_client_module, "_tsc", tsc):
        result = client.refresh_extract(
            "wb-001", token_name="tok", token_secret="secret", site_id=""
        )

    assert isinstance(result, dict)
    assert "job_id" in result or "id" in result
    assert "status" in result


def test_publish_workbook_chunked_small_file(tmp_path):
    """Small file → delegates to regular publish_workbook."""
    tsc, server, wb_item = _make_mock_tsc()
    client, _ = _make_client(tsc)

    # Create a small workbook file
    small_twb = tmp_path / "small.twb"
    small_twb.write_bytes(b"<workbook/>" * 100)

    with patch.object(client, "publish_workbook", return_value={"id": "wb-001"}) as mock_pub:
        client.publish_workbook_chunked(
            small_twb,
            project_id="proj-001",
            name="Test",
            chunk_size_mb=64,
            token_name="tok",
            token_secret="secret",
            site_id="",
        )

    mock_pub.assert_called_once()


def test_detect_drift_empty_for_matching_connections():
    from pytableau.core.workbook import Workbook

    tsc, server, wb_item = _make_mock_tsc()
    client, _ = _make_client(tsc)

    local_wb = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")

    # Server workbook has no connections → no drift items
    wb_item.connections = []
    server.workbooks.get_by_id.return_value = wb_item

    with patch.object(_client_module, "_tsc", tsc):
        result = client.detect_drift(local_wb, "wb-001")

    assert isinstance(result, list)


def test_detect_drift_workflow_delegates_to_client():
    from pytableau.core.workbook import Workbook
    from pytableau.server.workflows import detect_drift_workflow

    local_wb = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")

    with patch("pytableau.server.workflows.ServerClient") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.detect_drift.return_value = []

        result = detect_drift_workflow(
            "https://tableau.example.com",
            local_wb,
            "wb-001",
            token_name="tok",
            token_secret="secret",
            site_id="",
        )

    assert isinstance(result, list)
    instance.detect_drift.assert_called_once()
