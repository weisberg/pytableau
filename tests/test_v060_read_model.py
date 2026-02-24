"""v0.6.0 read model tests — #67 #68 #69 #70."""

from __future__ import annotations

from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Relation join tree (#67)
# ---------------------------------------------------------------------------


def test_relation_type_property(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(minimal_twb)
    ds = wb.datasources[0]
    # relation may be None if no explicit <relation> node
    # just verify it doesn't crash
    rel = ds.relation
    # Just verify the property access doesn't raise
    _ = rel


def test_list_custom_sql_returns_list() -> None:
    """list_custom_sql() should return a list (possibly empty)."""
    from lxml import etree

    from pytableau.core.datasource import Datasource

    xml = (
        '<datasource name="test">'
        '<relation type="text" name="Custom"><![CDATA[SELECT * FROM sales]]></relation>'
        "</datasource>"
    )
    root = etree.fromstring(xml.encode())
    ds = Datasource(root)
    sql_list = ds.list_custom_sql()
    assert isinstance(sql_list, list)


def test_relation_join_tree(tmp_path: Path) -> None:
    """Relation left/right/join_type accessors work on join nodes."""
    from lxml import etree

    from pytableau.core.datasource import Relation

    xml = """
    <relation type="join" join="inner">
      <clause type="inner"><expression op="= ([A].[id], [B].[id])" /></clause>
      <relation type="table" name="A" table="[dbo].[tableA]" />
      <relation type="table" name="B" table="[dbo].[tableB]" />
    </relation>
    """.strip()
    node = etree.fromstring(xml.encode())
    rel = Relation(node)

    assert rel.join_type == "inner"
    assert rel.left is not None
    assert rel.right is not None
    assert rel.left.table == "[dbo].[tableA]"
    assert rel.right.table == "[dbo].[tableB]"
    assert rel.on_clause is not None


# ---------------------------------------------------------------------------
# MetadataRecords (#68)
# ---------------------------------------------------------------------------


def test_metadata_records_empty_for_simple_fixture(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(minimal_twb)
    ds = wb.datasources[0]
    records = ds.metadata_records
    assert isinstance(records, list)
    # minimal fixture has no metadata-record nodes
    assert records == []


def test_metadata_record_properties() -> None:
    from lxml import etree

    from pytableau.core.datasource import MetadataRecord

    xml = """
    <metadata-record class="column">
      <remote-name>order_id</remote-name>
      <remote-type>WDT_INTEGER</remote-type>
      <local-name>[Order ID]</local-name>
      <aggregation>Sum</aggregation>
      <contains-null>true</contains-null>
    </metadata-record>
    """.strip()
    node = etree.fromstring(xml.encode())
    rec = MetadataRecord(node)

    assert rec.remote_name == "order_id"
    assert rec.remote_type == "WDT_INTEGER"
    assert rec.local_name == "[Order ID]"
    assert rec.aggregation == "Sum"
    assert rec.contains_null is True


# ---------------------------------------------------------------------------
# Hierarchies and Sets (#69)
# ---------------------------------------------------------------------------


def test_hierarchies_empty_for_simple_fixture(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(minimal_twb)
    ds = wb.datasources[0]
    assert isinstance(ds.hierarchies, list)
    assert ds.hierarchies == []


def test_hierarchies_parsed() -> None:
    from lxml import etree

    from pytableau.core.datasource import Datasource

    xml = """
    <datasource name="test">
      <drill-paths>
        <drill-path name="Location">
          <field>[Country]</field>
          <field>[State]</field>
          <field>[City]</field>
        </drill-path>
      </drill-paths>
    </datasource>
    """.strip()
    root = etree.fromstring(xml.encode())
    ds = Datasource(root)
    hierarchies = ds.hierarchies
    assert len(hierarchies) == 1
    assert hierarchies[0].name == "Location"
    assert hierarchies[0].levels == ["Country", "State", "City"]


def test_sets_parsed() -> None:
    from lxml import etree

    from pytableau.core.datasource import Datasource

    xml = """
    <datasource name="test">
      <group caption="Top Customers" class="groupfilter" field="[Customer]" name="Set_Top_Cust" />
    </datasource>
    """.strip()
    root = etree.fromstring(xml.encode())
    ds = Datasource(root)
    sets = ds.sets
    assert len(sets) == 1
    assert sets[0].caption == "Top Customers"
    assert sets[0].field_name == "Customer"


# ---------------------------------------------------------------------------
# Device layouts (#70)
# ---------------------------------------------------------------------------


def test_device_layouts_loaded(dashboard_actions_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(dashboard_actions_twb)
    assert len(wb.dashboards) == 1
    db = wb.dashboards[0]
    assert isinstance(db.device_layouts, list)
    assert len(db.device_layouts) == 2


def test_has_phone_layout(dashboard_actions_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(dashboard_actions_twb)
    db = wb.dashboards[0]
    assert db.has_phone_layout is True


def test_no_phone_layout_for_simple_fixture(minimal_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(minimal_twb)
    # minimal fixture has no dashboards
    assert len(wb.dashboards) == 0


def test_device_layout_names(dashboard_actions_twb: Path) -> None:
    from pytableau.core.workbook import Workbook

    wb = Workbook.open(dashboard_actions_twb)
    db = wb.dashboards[0]
    names = {dl.device_name for dl in db.device_layouts}
    assert "phone" in names
    assert "tablet" in names
