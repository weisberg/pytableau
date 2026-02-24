"""Tests for v1.0.0 — stub implementation verification."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# core.formatting — Color
# ---------------------------------------------------------------------------


def test_color_from_hex():
    """Color.from_hex('#FF5733') → r=255, g=87, b=51."""
    from pytableau.core.formatting import Color

    c = Color.from_hex("#FF5733")
    assert c.r == 255
    assert c.g == 87
    assert c.b == 51


def test_color_to_hex():
    """Color.to_hex() returns '#FF5733'."""
    from pytableau.core.formatting import Color

    c = Color(255, 87, 51)
    assert c.to_hex() == "#FF5733"


def test_color_palette_to_dict():
    """ColorPalette.to_dict() returns dict with name and colors list."""
    from pytableau.core.formatting import Color, ColorPalette

    palette = ColorPalette(
        name="TestPalette",
        colors=[Color(255, 0, 0), Color(0, 255, 0), Color(0, 0, 255)],
    )
    d = palette.to_dict()
    assert d["name"] == "TestPalette"
    assert isinstance(d["colors"], list)
    assert len(d["colors"]) == 3
    assert d["colors"][0] == "#FF0000"


def test_font_defaults():
    """Font default values are correct."""
    from pytableau.core.formatting import Font

    f = Font()
    assert f.family == "Tableau Book"
    assert f.size == 10
    assert f.bold is False
    assert f.italic is False
    assert f.underline is False


def test_format_spec_to_dict_json_serializable():
    """FormatSpec.to_dict() is JSON-serializable."""
    from pytableau.core.formatting import Color, Font, FormatSpec

    spec = FormatSpec(
        font=Font(family="Arial", size=12, bold=True),
        text_color=Color(0, 0, 0),
        background_color=Color(255, 255, 255),
    )
    d = spec.to_dict()
    # Should not raise
    serialized = json.dumps(d)
    loaded = json.loads(serialized)
    assert loaded["font"]["family"] == "Arial"
    assert loaded["text_color"] == "#000000"


# ---------------------------------------------------------------------------
# xml.writer
# ---------------------------------------------------------------------------


def test_writer_to_string_returns_xml():
    """xml.writer.to_string() returns valid XML string."""
    from lxml import etree

    from pytableau.xml.writer import to_string

    root = etree.Element("root")
    child = etree.SubElement(root, "child")
    child.text = "hello"

    result = to_string(root)
    assert isinstance(result, str)
    assert "<root>" in result
    assert "<child>hello</child>" in result


def test_writer_write_creates_file(tmp_path):
    """xml.writer.write() creates a file on disk."""
    from lxml import etree

    from pytableau.xml.writer import write

    root = etree.Element("workbook")
    out = tmp_path / "test.xml"
    write(root, out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "workbook" in content


def test_writer_indent_no_raise():
    """xml.writer.indent() doesn't raise on element."""
    from lxml import etree

    from pytableau.xml.writer import indent

    root = etree.Element("root")
    etree.SubElement(root, "a")
    etree.SubElement(root, "b")
    indent(root)  # should not raise
