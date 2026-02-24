"""Tests for v0.8.0 — Template Engine Extensions (M8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from pytableau.core.workbook import Workbook
from pytableau.templates.engine import TemplateEngine

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# replace_datasource
# ---------------------------------------------------------------------------


def _make_engine_with_two_ds() -> TemplateEngine:
    xml = b"""\
<?xml version='1.0' encoding='UTF-8'?>
<workbook>
  <datasources>
    <datasource name="old_ds" caption="Old">
      <connection class="sqlserver" server="old.example.com"/>
    </datasource>
    <datasource name="other_ds" caption="Other"/>
  </datasources>
  <worksheets/>
</workbook>"""
    tree = etree.ElementTree(etree.fromstring(xml))
    return TemplateEngine(tree)


def test_replace_datasource_replaces_node():
    engine = _make_engine_with_two_ds()
    new_ds = etree.fromstring(
        b'<datasource name="old_ds" caption="New"><connection class="postgres" server="new.example.com"/></datasource>'
    )
    engine.replace_datasource("old_ds", new_ds)
    root = engine.tree.getroot()
    ds_nodes = root.findall(".//datasources/datasource")
    names = [n.get("name") for n in ds_nodes]
    assert "old_ds" in names
    # Verify the new node was inserted (caption changed)
    new_node = next(n for n in ds_nodes if n.get("name") == "old_ds")
    assert new_node.get("caption") == "New"


def test_replace_datasource_raises_key_error_for_unknown():
    engine = _make_engine_with_two_ds()
    new_ds = etree.fromstring(b'<datasource name="nonexistent"/>')
    with pytest.raises(KeyError, match="nonexistent"):
        engine.replace_datasource("nonexistent", new_ds)


def test_replace_datasource_preserves_other_datasources():
    engine = _make_engine_with_two_ds()
    new_ds = etree.fromstring(b'<datasource name="old_ds" caption="Replaced"/>')
    engine.replace_datasource("old_ds", new_ds)
    root = engine.tree.getroot()
    ds_nodes = root.findall(".//datasources/datasource")
    names = [n.get("name") for n in ds_nodes]
    assert "other_ds" in names


def test_replace_datasource_maintains_position():
    engine = _make_engine_with_two_ds()
    root = engine.tree.getroot()
    container = root.find(".//datasources")
    assert container is not None
    old_idx = list(container).index(container.find("datasource[@name='old_ds']"))

    new_ds = etree.fromstring(b'<datasource name="old_ds" caption="Replacement"/>')
    engine.replace_datasource("old_ds", new_ds)

    new_idx = list(container).index(container.find("datasource[@name='old_ds']"))
    assert new_idx == old_idx


# ---------------------------------------------------------------------------
# save_as_template
# ---------------------------------------------------------------------------


def test_save_as_template_returns_mapping(tmp_path):
    wb = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    dest = tmp_path / "template.twb"
    mapping = wb.save_as_template(dest)
    assert isinstance(mapping, dict)
    assert len(mapping) > 0


def test_save_as_template_creates_file(tmp_path):
    wb = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    dest = tmp_path / "template.twb"
    wb.save_as_template(dest)
    assert dest.exists()


def test_save_as_template_file_contains_placeholders(tmp_path):
    wb = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    dest = tmp_path / "template.twb"
    wb.save_as_template(dest)
    content = dest.read_text()
    assert "__FIELD" in content


def test_save_as_template_does_not_modify_live_workbook():
    wb = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    original_fields = [f.caption for f in wb.datasources[0].fields]

    import os
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".twb", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        wb.save_as_template(tmp_path)
        # Live workbook captions unchanged
        after_fields = [f.caption for f in wb.datasources[0].fields]
        assert original_fields == after_fields
    finally:
        os.unlink(tmp_path)


def test_save_as_template_roundtrip(tmp_path):
    """save_as_template → Workbook.open → captions are __FIELDN__ tokens."""
    wb = Workbook.open(FIXTURE_DIR / "single_datasource_v2023_1.twb")
    dest = tmp_path / "template.twb"
    mapping = wb.save_as_template(dest)

    template_wb = Workbook.open(dest)
    captions = [f.caption for f in template_wb.datasources[0].fields]
    # At least some captions should be placeholder tokens
    placeholders = [c for c in captions if c is not None and c.startswith("__FIELD")]
    assert len(placeholders) > 0

    # The mapping values should contain the original captions
    originals = set(mapping.values())
    assert len(originals) > 0


def test_save_as_template_uses_custom_prefix(tmp_path):
    wb = Workbook.open(FIXTURE_DIR / "minimal_v2022_4.twb")
    dest = tmp_path / "template.twb"
    mapping = wb.save_as_template(dest, field_placeholder_prefix="DIM")
    assert any("__DIM" in k for k in mapping)
    content = dest.read_text()
    assert "__DIM" in content


def test_save_as_template_mapping_values_are_original_captions():
    wb = Workbook.open(FIXTURE_DIR / "single_datasource_v2023_1.twb")
    import os
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".twb", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        original_captions = {f.caption for f in wb.datasources[0].fields if f.caption}
        mapping = wb.save_as_template(tmp_path)
        mapped_values = set(mapping.values())
        # Intersection: at least some original captions appear in the mapping
        assert len(original_captions & mapped_values) > 0
    finally:
        os.unlink(tmp_path)
