"""v0.6.0 mutation tests — #76 #78 #80."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# bulk_update_fields (#80)
# ---------------------------------------------------------------------------


def test_bulk_update_fields_hidden(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(minimal_twb)
    ds = wb.datasources[0]
    count = ds.bulk_update_fields(
        where=lambda f: f.datatype == "real",
        updates={"hidden": True},
    )
    assert count >= 0  # may be 0 if no real fields
    for f in ds.all_fields:
        if f.datatype == "real":
            assert f.hidden is True


def test_bulk_rename_fields(single_datasource_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(single_datasource_twb)
    ds = wb.datasources[0]
    # Pick existing field captions
    original_captions = [f.caption for f in ds.all_fields]
    if not original_captions:
        pytest.skip("No fields in fixture")

    first = original_captions[0]
    mapping = {first: first + "_renamed"}
    count = ds.bulk_rename_fields(mapping)
    assert count == 1
    assert ds.get_field(first + "_renamed") is not None


def test_bulk_update_fields_returns_count(single_datasource_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(single_datasource_twb)
    ds = wb.datasources[0]
    count = ds.bulk_update_fields(where=lambda f: True, updates={})
    assert count == len(ds.all_fields)


def test_bulk_rename_fields_ignores_missing(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(minimal_twb)
    ds = wb.datasources[0]
    count = ds.bulk_rename_fields({"NonExistentField": "NewName"})
    assert count == 0


# ---------------------------------------------------------------------------
# auto_fix — dry run (#76)
# ---------------------------------------------------------------------------


def test_auto_fix_dry_run_no_changes(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(minimal_twb)
    # Get formula before
    formulas_before = {}
    for ds in wb.datasources:
        for calc in ds.calculated_fields:
            formulas_before[calc.caption] = calc.formula

    actions = wb.auto_fix(dry_run=True)
    assert isinstance(actions, list)

    # Formulas unchanged after dry-run
    for ds in wb.datasources:
        for calc in ds.calculated_fields:
            assert calc.formula == formulas_before[calc.caption]


def test_credential_scrubber_dry_run(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.xml.fixers import CredentialScrubber

    wb = Workbook.open(minimal_twb)
    for ds in wb.datasources:
        for conn in ds.connections:
            conn.xml_node.set("password", "hunter2")

    scrubber = CredentialScrubber()
    actions = scrubber.fix(wb, dry_run=True)
    assert len(actions) > 0
    # Password still there in dry-run
    for ds in wb.datasources:
        for conn in ds.connections:
            assert conn.xml_node.get("password") == "hunter2"


def test_credential_scrubber_applies(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.xml.fixers import CredentialScrubber

    wb = Workbook.open(minimal_twb)
    for ds in wb.datasources:
        for conn in ds.connections:
            conn.xml_node.set("password", "hunter2")

    scrubber = CredentialScrubber()
    actions = scrubber.fix(wb, dry_run=False)
    assert len(actions) > 0
    # Password removed
    for ds in wb.datasources:
        for conn in ds.connections:
            assert "password" not in conn.xml_node.attrib


def test_whitespace_normalizer() -> None:
    from lxml import etree

    from pytableau.core.datasource import Datasource
    from pytableau.xml.fixers import WhitespaceNormalizer

    xml = (
        '<datasource name="test">'
        "<columns>"
        '<column name="[C]" caption="C" datatype="real" role="measure" type="quantitative">'
        '<calculation class="tableau" formula="SUM([Sales])  /  COUNT([Orders])" />'
        "</column>"
        "</columns>"
        "</datasource>"
    )
    root = etree.fromstring(xml.encode())

    class FakeWB:
        datasources = [Datasource(root)]
        worksheets = []
        dashboards = []
        parameters = None

    fixer = WhitespaceNormalizer()
    actions = fixer.fix(FakeWB(), dry_run=False)
    assert len(actions) == 1
    assert actions[0].new_value == "SUM([Sales]) / COUNT([Orders])"


# ---------------------------------------------------------------------------
# PromotionConfig (#78)
# ---------------------------------------------------------------------------


def test_promotion_config_from_dict() -> None:
    from pytableau.package.promotion import PromotionConfig

    cfg = PromotionConfig.from_dict(
        {
            "environments": {
                "dev": {"server": "dev.db", "dbname": "sales_dev"},
                "prod": {"server": "prod.db", "dbname": "sales_prod", "port": 5432},
            }
        }
    )
    assert "dev" in cfg.environments
    assert "prod" in cfg.environments
    assert cfg.environments["prod"].server == "prod.db"
    assert cfg.environments["prod"].port == 5432


def test_promotion_config_from_yaml_requires_pyyaml(tmp_path: Path) -> None:
    """from_yaml raises ImportError (or loads if pyyaml present)."""
    from pytableau.package.promotion import PromotionConfig

    yaml_file = tmp_path / "cfg.yaml"
    yaml_file.write_text(
        "environments:\n  dev:\n    server: dev.db\n",
        encoding="utf-8",
    )
    try:
        cfg = PromotionConfig.from_yaml(str(yaml_file))
        assert "dev" in cfg.environments
    except ImportError:
        pass  # pyyaml not installed — expected


def test_promote_dry_run(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.package.promotion import PromotionConfig

    cfg = PromotionConfig.from_dict(
        {
            "environments": {
                "dev": {"server": "dev.example.com"},
                "prod": {"server": "prod.example.com"},
            }
        }
    )
    wb = Workbook.open(minimal_twb)
    changes = wb.promote("dev", "prod", cfg, dry_run=True)
    assert isinstance(changes, list)
    # Connections should still point to dev after dry run
    for ds in wb.datasources:
        for conn in ds.connections:
            assert conn.server != "prod.example.com"


def test_promote_applies(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.package.promotion import PromotionConfig

    cfg = PromotionConfig.from_dict(
        {
            "environments": {
                "dev": {"server": "dev.example.com"},
                "prod": {"server": "prod.example.com"},
            }
        }
    )
    wb = Workbook.open(minimal_twb)
    changes = wb.promote("dev", "prod", cfg, dry_run=False)
    # At least one connection updated
    assert len(changes) >= 1
    for ds in wb.datasources:
        for conn in ds.connections:
            if conn.server is not None:
                assert conn.server == "prod.example.com"


def test_promote_unknown_env_raises(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook
    from pytableau.package.promotion import PromotionConfig

    cfg = PromotionConfig.from_dict({"environments": {"dev": {"server": "dev.db"}}})
    wb = Workbook.open(minimal_twb)
    with pytest.raises(ValueError, match="Unknown environment"):
        wb.promote("dev", "staging", cfg)
