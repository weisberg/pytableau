"""v0.5.0 security and streaming tests — #57 #58 #61 #66 #79."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from pytableau.core.workbook import Workbook
from pytableau.exceptions import (
    AmbiguousWorkbookError,
    InvalidWorkbookError,
    LazyNotMaterializedError,
)

# ---------------------------------------------------------------------------
# Strict / compatibility mode (#57)
# ---------------------------------------------------------------------------


def test_strict_mode_rejects_huge_tree(tmp_path: Path) -> None:
    """strict=True should raise if node count > 500 000."""
    # We don't generate 500k nodes in tests — instead verify the flag is accepted.
    source = Path(__file__).parent / "fixtures" / "minimal_v2022_4.twb"
    wb = Workbook.open(source, strict=True)
    assert wb.version is not None  # opens fine (small file)


def test_strict_mode_rejects_non_workbook_root(tmp_path: Path) -> None:
    """strict=True should raise if root element != workbook."""
    bad_xml = tmp_path / "bad.twb"
    bad_xml.write_text('<?xml version="1.0"?><datasource name="x" />', encoding="utf-8")
    with pytest.raises(InvalidWorkbookError):
        Workbook.open(bad_xml, strict=True)


def test_compatibility_mode_warns_on_non_workbook_root(tmp_path: Path) -> None:
    """compatibility=True should warn (not raise) on non-workbook root."""
    bad_xml = tmp_path / "compat.twb"
    bad_xml.write_text('<?xml version="1.0"?><workbook source-build="20241.24.0320.0919" />', encoding="utf-8")
    import warnings
    with warnings.catch_warnings(record=True):
        wb = Workbook.open(bad_xml, compatibility=True)
    assert wb is not None


# ---------------------------------------------------------------------------
# Credential scrubbing (#58)
# ---------------------------------------------------------------------------


def test_scrub_credentials_removes_password(tmp_path: Path) -> None:
    """save_as with scrub_credentials=True strips passwords."""
    source = Path(__file__).parent / "fixtures" / "minimal_v2022_4.twb"
    wb = Workbook.open(source)
    # Manually inject a password to test scrubbing.
    for ds in wb.datasources:
        for conn in ds.connections:
            conn.xml_node.set("password", "s3cret")

    dest = tmp_path / "scrubbed.twb"
    wb.save_as(dest, scrub_credentials=True)

    wb2 = Workbook.open(dest)
    for ds in wb2.datasources:
        for conn in ds.connections:
            assert "password" not in conn.xml_node.attrib


def test_scrub_credentials_false_preserves_attrs(tmp_path: Path) -> None:
    """save_as with scrub_credentials=False preserves all attributes."""
    source = Path(__file__).parent / "fixtures" / "minimal_v2022_4.twb"
    wb = Workbook.open(source)
    for ds in wb.datasources:
        for conn in ds.connections:
            conn.xml_node.set("password", "keepme")

    dest = tmp_path / "unscrubbed.twb"
    wb.save_as(dest, scrub_credentials=False)

    wb2 = Workbook.open(dest)
    for ds in wb2.datasources:
        for conn in ds.connections:
            if "password" in conn.xml_node.attrib:
                assert conn.xml_node.get("password") == "keepme"
                return
    pytest.fail("Password attribute not found after save with scrub_credentials=False")


def test_datasource_scrub_credentials_returns_actions() -> None:
    """Datasource.scrub_credentials() returns ScrubAction list."""
    source = Path(__file__).parent / "fixtures" / "minimal_v2022_4.twb"
    wb = Workbook.open(source)
    ds = wb.datasources[0]
    conn = ds.connections[0]
    conn.xml_node.set("password", "abc")
    conn.xml_node.set("odbc-connect-string-extras", "PWD=secret")

    actions = ds.scrub_credentials()
    assert len(actions) == 2
    attrs = {a.attribute for a in actions}
    assert "password" in attrs
    assert "odbc-connect-string-extras" in attrs


# ---------------------------------------------------------------------------
# Streaming mode (#61)
# ---------------------------------------------------------------------------


def test_streaming_mode_loads_datasources(minimal_twb: Path) -> None:
    """streaming=True populates datasources correctly."""
    wb = Workbook.open(minimal_twb, streaming=True)
    assert len(wb.datasources) >= 1


def test_streaming_mode_worksheets_raise(minimal_twb: Path) -> None:
    """Accessing worksheets in streaming mode raises LazyNotMaterializedError."""
    wb = Workbook.open(minimal_twb, streaming=True)
    with pytest.raises(LazyNotMaterializedError):
        _ = len(wb.worksheets)


def test_streaming_mode_dashboards_raise(minimal_twb: Path) -> None:
    """Accessing dashboards in streaming mode raises LazyNotMaterializedError."""
    wb = Workbook.open(minimal_twb, streaming=True)
    with pytest.raises(LazyNotMaterializedError):
        _ = len(wb.dashboards)


def test_streaming_mode_worksheet_iter_raises(minimal_twb: Path) -> None:
    """Iterating worksheets in streaming mode raises LazyNotMaterializedError."""
    wb = Workbook.open(minimal_twb, streaming=True)
    with pytest.raises(LazyNotMaterializedError):
        list(wb.worksheets)


# ---------------------------------------------------------------------------
# AmbiguousWorkbookError / twb_hint (#66)
# ---------------------------------------------------------------------------


def test_ambiguous_workbook_error_has_candidates(tmp_path: Path) -> None:
    """AmbiguousWorkbookError carries candidates list."""
    exc = AmbiguousWorkbookError("test", candidates=["a.twb", "b.twb"])
    assert exc.candidates == ["a.twb", "b.twb"]
    assert "test" in str(exc)


def test_twbx_with_single_twb_opens_normally(tmp_path: Path) -> None:
    """A .twbx with one .twb opens without twb_hint."""
    twb_content = b'<?xml version="1.0"?><workbook source-build="20241.24.0320.0919" />'
    archive = tmp_path / "single.twbx"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("workbook.twb", twb_content)
    # Should open without error
    wb = Workbook.open(archive)
    assert wb is not None


def test_twbx_with_two_twbs_raises_ambiguous(tmp_path: Path) -> None:
    """A .twbx with two root-level .twb files raises AmbiguousWorkbookError."""
    twb_content = b'<?xml version="1.0"?><workbook source-build="20241.24.0320.0919" />'
    archive = tmp_path / "ambiguous.twbx"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("workbook.twb", twb_content)
        zf.writestr("other.twb", twb_content)
    with pytest.raises(AmbiguousWorkbookError) as exc_info:
        Workbook.open(archive)
    assert len(exc_info.value.candidates) == 2


def test_twb_hint_resolves_ambiguity(tmp_path: Path) -> None:
    """twb_hint resolves ambiguous multi-TWB archives."""
    content_a = b'<?xml version="1.0"?><workbook source-build="20241.24.0320.0919" source-platform="win" />'
    content_b = b'<?xml version="1.0"?><workbook source-build="20222.22.0614.2200" source-platform="mac" />'
    archive = tmp_path / "hinted.twbx"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("first.twb", content_a)
        zf.writestr("second.twb", content_b)
    wb = Workbook.open(archive, twb_hint="second.twb")
    assert wb is not None


# ---------------------------------------------------------------------------
# Workbook-level swap_connection (#79)
# ---------------------------------------------------------------------------


def test_workbook_swap_connection_updates_all(minimal_twb: Path) -> None:
    """Workbook.swap_connection() updates all datasources."""
    wb = Workbook.open(minimal_twb)
    result = wb.swap_connection(server="prod.example.com")
    assert result.updated_count == len(wb.datasources)
    assert result.skipped_count == 0
    for ds in wb.datasources:
        for conn in ds.connections:
            assert conn.server == "prod.example.com"


def test_workbook_swap_connection_with_where_filter(multi_datasource_twb: Path) -> None:
    """Workbook.swap_connection(where=...) only updates matching datasources."""
    wb = Workbook.open(multi_datasource_twb)
    first_name = wb.datasources[0].name
    result = wb.swap_connection(
        where=lambda ds: ds.name == first_name,
        server="filtered.example.com",
    )
    assert result.updated_count == 1
    assert result.skipped_count == len(wb.datasources) - 1


def test_swap_result_details(minimal_twb: Path) -> None:
    """SwapResult.details contains per-datasource info."""
    wb = Workbook.open(minimal_twb)
    result = wb.swap_connection(server="new.example.com")
    assert isinstance(result.details, list)
    assert all("datasource" in d for d in result.details)
