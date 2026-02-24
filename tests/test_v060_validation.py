"""v0.6.0 validation and complexity tests — #73 #75 #77."""

from __future__ import annotations

from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Complexity analysis (#73)
# ---------------------------------------------------------------------------


def test_complexity_report_minimal(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.inspect.complexity import analyze_complexity

    wb = Workbook.open(minimal_twb)
    report = analyze_complexity(wb)
    assert report.grade in {"A", "B", "C", "D", "F"}
    assert report.total_score >= 0
    assert isinstance(report.breakdown, dict)
    assert isinstance(report.recommendations, list)


def test_complexity_grade_a_for_minimal(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.inspect.complexity import analyze_complexity

    wb = Workbook.open(minimal_twb)
    report = analyze_complexity(wb)
    # minimal fixture has 1 live connection -> score ~3
    assert report.grade == "A"


def test_complexity_lod_heavy_scores_higher(lod_heavy_twb: Path, minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.inspect.complexity import analyze_complexity

    wb_lod = Workbook.open(lod_heavy_twb)
    wb_min = Workbook.open(minimal_twb)
    report_lod = analyze_complexity(wb_lod)
    report_min = analyze_complexity(wb_min)
    assert report_lod.total_score > report_min.total_score


def test_complexity_nested_lod_increases_score(lod_heavy_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.inspect.complexity import analyze_complexity

    wb = Workbook.open(lod_heavy_twb)
    report = analyze_complexity(wb)
    assert report.breakdown["nested_lod_expressions"] >= 1


def test_complexity_to_dict(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.inspect.complexity import analyze_complexity

    wb = Workbook.open(minimal_twb)
    report = analyze_complexity(wb)
    d = report.to_dict()
    assert "total_score" in d
    assert "grade" in d
    assert "breakdown" in d
    assert "recommendations" in d


def test_workbook_complexity_report_method(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(minimal_twb)
    report = wb.complexity_report()
    assert report is not None
    assert report.grade in {"A", "B", "C", "D", "F"}


# ---------------------------------------------------------------------------
# ValidationProfile (#75)
# ---------------------------------------------------------------------------


def test_validation_profile_strict(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.xml.rules import ValidationProfile

    wb = Workbook.open(minimal_twb)
    profile = ValidationProfile.strict()
    issues = profile.check(wb)
    assert isinstance(issues, list)


def test_validation_profile_credential_rule(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.xml.rules import CredentialExposureRule, ValidationProfile

    wb = Workbook.open(minimal_twb)
    # inject a password
    for ds in wb.datasources:
        for conn in ds.connections:
            conn.xml_node.set("password", "bad")
    profile = ValidationProfile([CredentialExposureRule()])
    issues = profile.check(wb)
    assert any(i.level == "error" for i in issues)


def test_validation_profile_empty_calc_rule() -> None:
    from lxml import etree

    from pytableau.core.datasource import Datasource
    from pytableau.xml.rules import EmptyCalcRule, ValidationProfile

    xml = """
    <datasource name="test">
      <columns>
        <column name="[Bad Calc]" caption="Bad Calc" datatype="real" role="measure" type="quantitative">
          <calculation class="tableau" formula="" />
        </column>
      </columns>
    </datasource>
    """.strip()
    root = etree.fromstring(xml.encode())

    # We need a workbook-like object; use a minimal wrapper
    class FakeWorkbook:
        datasources: list
        worksheets: list = []
        dashboards: list = []
        parameters = None
        xml_root = root

    ds = Datasource(root)

    class FakeWB:
        datasources = [ds]
        worksheets = []
        dashboards = []
        parameters = None
        xml_root = root

    profile = ValidationProfile([EmptyCalcRule()])
    issues = profile.check(FakeWB())
    assert any("empty" in i.message.lower() for i in issues)


def test_workbook_validate_with_profile(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.xml.rules import ValidationProfile

    wb = Workbook.open(minimal_twb)
    profile = ValidationProfile.default()
    issues = wb.validate(profile=profile)
    assert isinstance(issues, list)


def test_workbook_validate_no_profile_backward_compat(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(minimal_twb)
    issues = wb.validate()  # no profile — backward compat
    assert isinstance(issues, list)


# ---------------------------------------------------------------------------
# Unknown tag tolerance (#77)
# ---------------------------------------------------------------------------


def test_unknown_tag_tolerance(tmp_path: Path) -> None:
    from pytableau.xml.engine import XMLSchemaEngine

    engine = XMLSchemaEngine("2024.1")
    issues = engine.validate_element("custom-extension-tag", "datasource", {})
    # Should produce info-level, not error
    assert any(i.level == "info" for i in issues)
    assert "custom-extension-tag" in engine.unknown_elements


def test_unknown_elements_tracked(tmp_path: Path) -> None:
    from pytableau.xml.engine import XMLSchemaEngine

    engine = XMLSchemaEngine("2024.1")
    engine.validate_element("foo-tag", "workbook", {})
    engine.validate_element("bar-tag", "datasource", {})
    assert "foo-tag" in engine.unknown_elements
    assert "bar-tag" in engine.unknown_elements


def test_validate_workbook_with_unknown_tag_no_error(tmp_path: Path) -> None:
    """Unknown tags produce info-level issues, never errors."""
    from lxml import etree

    from pytableau.xml.engine import XMLSchemaEngine

    xml = (
        '<?xml version="1.0"?>'
        '<workbook source-build="20241.24.0320.0919">'
        '<datasources><datasource name="x"><my-custom-node /></datasource></datasources>'
        "</workbook>"
    )
    tree = etree.fromstring(xml.encode())
    etree_tree = tree.getroottree()
    engine = XMLSchemaEngine("2024.1")
    issues = engine.validate_workbook(etree_tree)
    assert not any(i.level == "error" for i in issues)
