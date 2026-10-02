"""Identity, lossless native encoding, and scoped impact regression tests."""

import pytest
from lxml import etree

from pytableau import Workbook
from pytableau.build import from_spec
from pytableau.core.fields import FieldReference
from pytableau.core.references import reference_tokens


@pytest.mark.parametrize(
    "token,name,source",
    [
        ("[Sales]", "Sales", None),
        ("[Orders].[sum:Sales:qk]", "Sales", "Orders"),
        ("[Orders].[pcto:sum:Total Sales:qk:10]", "Total Sales", "Orders"),
        ("[Orders].[sum::atest Regional Orders:qk]", ":atest Regional Orders", "Orders"),
        ("[A]].B].[usr:C]]D:nk]", "C]D", "A].B"),
        (
            "[__tableau_internal_object_id__].[cnt:Object ID:qk]",
            "Object ID",
            "__tableau_internal_object_id__",
        ),
    ],
)
def test_reference_roundtrip(token, name, source):
    reference = FieldReference.parse(token)
    assert reference.name == name
    assert reference.datasource == source
    assert str(reference) == token


def test_reference_rename_retains_tablecalc_suffix():
    ref = FieldReference.parse("[Orders].[pcto:sum:Sales:qk:10]")
    assert str(ref.with_name("Revenue")) == "[Orders].[pcto:sum:Revenue:qk:10]"


def test_formula_scanner_ignores_literals_and_comments():
    formula = "[A] + '[B]' + \"[C]\" // [D]\n + [Orders].[sum:E:qk] /* [F] */"
    assert [t.reference.name for t in reference_tokens(formula, formula=True)] == ["A", "E"]


def test_rename_does_not_confuse_caption_with_another_fields_internal_name():
    wb = Workbook.new()
    xml = etree.fromstring(b"""<datasource name="Data"><columns>
      <column name="[Revenue]" caption="Sales" datatype="real"/>
      <column name="[Sales]" caption="Profit" datatype="real"/>
      <column name="[Calc]" caption="Calc"><calculation formula="[Sales] + [Revenue]"/></column>
    </columns></datasource>""")
    wb.xml_root.find("datasources").append(xml)
    wb._load_tree(wb.xml_tree)
    ds = wb.datasources[0]
    ds.rename_field("Sales", "Renamed")
    assert ds.get_field("Calc").formula == "[Sales] + [Revenue]"
    assert ds.get_field("Renamed").name == "[Revenue]"


def test_scoped_rename_and_impact_cross_datasource_calcs():
    wb = from_spec(
        {
            "datasources": [
                {"caption": "One", "columns": [{"caption": "Sales"}]},
                {"caption": "Two", "columns": [{"caption": "Sales"}]},
            ]
        }
    )
    a, b = wb.datasources
    a.add_calculated_field("Double", "[Sales] * 2")
    b.add_calculated_field("From One", f"[{a.name}].[Sales] + [Sales]")
    impact = wb.impact("Sales", a.name)
    assert len(impact) == 2
    a.rename_field("Sales", "Revenue")
    assert a.get_field("Double").formula == "[Revenue] * 2"
    assert b.get_field("From One").formula == f"[{a.name}].[Revenue] + [Sales]"


def test_native_instance_alias_and_internal_id_are_preserved_by_caption_rename():
    wb = from_spec({"datasources": [{"caption": "Data", "columns": [{"caption": "Sales"}]}]})
    ds = wb.datasources[0]
    node = etree.fromstring(
        f'''<worksheet name="Native"><table><view>
       <datasource-dependencies datasource="{ds.name}">
        <column-instance name="[pcto:sum:Sales:qk:10]" column="[Sales]" derivation="Sum"><table-calc ordering-type="Rows"/></column-instance>
       </datasource-dependencies></view><rows>[{ds.name}].[pcto:sum:Sales:qk:10]</rows>
       <panes><pane><mark class="Bar"/><encodings><color column="[{ds.name}].[sum:Sales:qk]"/></encodings></pane></panes>
       </table></worksheet>'''.encode()
    )
    wb.add_worksheet(node)
    assert wb.references().uses[0].error is None
    assert wb.worksheets[0].rows[0].name == "Sales"
    assert wb.worksheets[0].marks.color[0].datasource == ds.name
    ds.rename_field("Sales", "Revenue")
    assert wb.worksheets[0].rows[0].name == "Sales"
    assert ds.get_field("Revenue").name == "[Sales]"
    assert wb.references().uses[0].error is None


def test_parameter_reference_resolves_special_datasource():
    wb = Workbook.new()
    xml = etree.fromstring(
        b"""<datasource name="Parameters"><column name="[Parameter 3]" caption="Limit" datatype="integer" param-domain-type="all"/></datasource>"""
    )
    wb.xml_root.find("datasources").append(xml)
    wb._load_tree(wb.xml_tree)
    _, field, error = wb.references().resolve(FieldReference.parse("[Parameters].[Parameter 3]"))
    assert error is None
    assert field.caption == "Limit"


def test_impact_traverses_calculations_to_worksheets():
    wb = from_spec(
        {
            "datasources": [{"caption": "Data", "columns": [{"caption": "Sales"}]}],
            "worksheets": [{"name": "Chart", "datasource": "Data", "rows": ["Double"]}],
        }
    )
    wb.datasources[0].add_calculated_field("Double", "[Sales] * 2")
    assert {use.kind for use in wb.impact("Sales", wb.datasources[0].name)} == {
        "calculation",
        "worksheet",
    }
