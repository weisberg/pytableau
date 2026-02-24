"""Tests for v0.7.0 — Semantic Diff & Patch (M6)."""

from __future__ import annotations

import json
from pathlib import Path

from pytableau.core.workbook import Workbook
from pytableau.inspect.diff import (
    Patch,
    PatchAction,
    PatchOp,
    apply_patch,
    diff_workbooks,
)
from pytableau.xml.canonical import canonicalize, git_clean, to_json
from pytableau.xml.differ import xml_diff

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def minimal_wb():
    return Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")


def modified_wb():
    return Workbook.open(FIXTURE_DIR / "modified_v2024_1.twb")


# ---------------------------------------------------------------------------
# git_clean
# ---------------------------------------------------------------------------


def test_git_clean_returns_string(tmp_path):
    src = FIXTURE_DIR / "minimal_v2022_4.twb"
    dst = tmp_path / "minimal.twb"
    import shutil
    shutil.copy(src, dst)
    result = git_clean(dst, in_place=False)
    assert isinstance(result, str)
    assert "<workbook" in result


def test_git_clean_strips_thumbnails(tmp_path):
    """git_clean should remove <thumbnails> elements."""
    twb_content = """\
<?xml version='1.0' encoding='UTF-8'?>
<workbook source-build="20241.24.0320.0919" source-platform="win" version="18.1">
  <datasources/>
  <worksheets/>
  <dashboards/>
  <thumbnails>
    <thumbnail name="Sheet1">base64data==</thumbnail>
  </thumbnails>
</workbook>
"""
    p = tmp_path / "test.twb"
    p.write_text(twb_content, encoding="utf-8")
    result = git_clean(p, in_place=False)
    assert "thumbnails" not in result
    assert "base64data" not in result


def test_git_clean_in_place_false_does_not_write(tmp_path):
    src = FIXTURE_DIR / "minimal_v2022_4.twb"
    original = src.read_text()
    git_clean(src, in_place=False)
    assert src.read_text() == original  # unchanged


def test_git_clean_in_place_true_writes(tmp_path):
    import shutil
    dst = tmp_path / "workbook.twb"
    shutil.copy(FIXTURE_DIR / "minimal_v2022_4.twb", dst)
    import time
    time.sleep(0.01)
    git_clean(dst, in_place=True)
    assert dst.exists()


# ---------------------------------------------------------------------------
# to_json / canonicalize
# ---------------------------------------------------------------------------


def test_to_json_returns_valid_json():
    wb = minimal_wb()
    j = to_json(wb)
    d = json.loads(j)
    assert "version" in d
    assert "datasources" in d


def test_to_json_stable_across_calls():
    wb = minimal_wb()
    assert to_json(wb) == to_json(wb)


def test_to_json_has_worksheets_dashboards():
    wb = minimal_wb()
    d = json.loads(to_json(wb))
    assert "worksheets" in d
    assert "dashboards" in d


def test_canonicalize_sorted_keys():
    wb = minimal_wb()
    d = canonicalize(wb)
    keys = list(d.keys())
    assert keys == sorted(keys)


def test_workbook_to_json_method():
    wb = minimal_wb()
    j = wb.to_json()
    assert json.loads(j)["version"] == wb.version


# ---------------------------------------------------------------------------
# diff_workbooks
# ---------------------------------------------------------------------------


def test_diff_identical_workbooks_is_empty():
    wb = minimal_wb()
    d = diff_workbooks(wb, wb)
    assert d.is_empty()


def test_diff_detects_field_added():
    before = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    after = Workbook.open(FIXTURE_DIR / "modified_v2024_1.twb")
    d = diff_workbooks(before, after)
    # modified has "Territory" and "Profit Ratio" instead of "Region" + new calc
    assert not d.is_empty()


def test_diff_detects_datasource_level_field_changes():
    before = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    diff_workbooks(before, Workbook.open(FIXTURE_DIR / "modified_v2024_1.twb"))
    ds_names = list(before.datasources.names)
    assert len(ds_names) > 0


def test_diff_workbook_diff_to_text():
    before = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    after = Workbook.open(FIXTURE_DIR / "modified_v2024_1.twb")
    d = diff_workbooks(before, after)
    text = d.to_text()
    assert isinstance(text, str)


def test_diff_workbook_diff_to_dict_serializable():
    before = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    after = Workbook.open(FIXTURE_DIR / "modified_v2024_1.twb")
    d = diff_workbooks(before, after)
    data = d.to_dict()
    # Must be JSON-serializable
    json.dumps(data)


def test_diff_workbook_diff_to_html():
    before = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    after = Workbook.open(FIXTURE_DIR / "modified_v2024_1.twb")
    d = diff_workbooks(before, after)
    html = d.to_html()
    assert isinstance(html, str)


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------


def test_patch_from_diff_creates_ops():
    before = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    after = Workbook.open(FIXTURE_DIR / "modified_v2024_1.twb")
    d = diff_workbooks(before, after)
    p = Patch.from_diff(d)
    assert isinstance(p.ops, list)


def test_patch_to_dict_roundtrip():
    ops = [
        PatchOp(action=PatchAction.MODIFY_CONNECTION, target="datasource:foo/connection:0",
                attribute="server", old_value="dev", new_value="prod")
    ]
    p = Patch(ops=ops)
    d = p.to_dict()
    p2 = Patch.from_dict(d)
    assert len(p2.ops) == 1
    assert p2.ops[0].attribute == "server"
    assert p2.ops[0].new_value == "prod"


def test_patch_to_json():
    p = Patch(ops=[])
    j = p.to_json()
    assert json.loads(j)["ops"] == []


def test_apply_patch_modify_connection():
    wb = minimal_wb()
    ds_name = list(wb.datasources.names)[0]
    orig_server = wb.datasources[ds_name].connections[0].server

    ops = [
        PatchOp(
            action=PatchAction.MODIFY_CONNECTION,
            target=f"datasource:{ds_name}/connection:0",
            attribute="server",
            old_value=orig_server,
            new_value="patched.example.com",
        )
    ]
    p = Patch(ops=ops)
    applied = apply_patch(wb, p, validate=False)
    assert applied == 1
    assert wb.datasources[ds_name].connections[0].server == "patched.example.com"


def test_apply_patch_skips_missing_target():
    wb = minimal_wb()
    ops = [
        PatchOp(
            action=PatchAction.MODIFY_CONNECTION,
            target="datasource:nonexistent/connection:0",
            attribute="server",
            old_value=None,
            new_value="new",
        )
    ]
    p = Patch(ops=ops)
    import warnings
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        applied = apply_patch(wb, p, validate=False)
    assert applied == 0


# ---------------------------------------------------------------------------
# xml_diff
# ---------------------------------------------------------------------------


def test_xml_diff_identical_files_empty():
    src = FIXTURE_DIR / "minimal_v2022_4.twb"
    lines = xml_diff(src, src)
    # Diffing a file against itself should yield no +/- lines
    changed = [ln for ln in lines if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
    assert len(changed) == 0


def test_xml_diff_different_files_has_output():
    before = FIXTURE_DIR / "minimal_v2022_4.twb"
    after = FIXTURE_DIR / "modified_v2024_1.twb"
    lines = xml_diff(before, after)
    assert len(lines) > 0


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def test_cli_diff_command():
    from pytableau.cli.main import app
    result = app.call(
        "diff",
        before=str(FIXTURE_DIR / "minimal_v2022_4.twb"),
        after=str(FIXTURE_DIR / "modified_v2024_1.twb"),
    )
    assert result.ok


def test_cli_git_clean_dry_run(tmp_path):
    import shutil

    from pytableau.cli.main import app
    dst = tmp_path / "workbook.twb"
    shutil.copy(FIXTURE_DIR / "minimal_v2022_4.twb", dst)
    result = app.call("git_clean", workbook=str(dst), dry_run=True)
    assert result.ok


def test_cli_to_json_command():
    from pytableau.cli.main import app
    result = app.call("to_json", workbook=str(FIXTURE_DIR / "minimal_v2022_4.twb"))
    assert result.ok
    assert "canonical" in result.result
