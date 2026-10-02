"""End-to-end, conflict, recovery and native XML authoring acceptance tests."""

import copy
import json
import zipfile

import pytest
from lxml import etree

from pytableau import Workbook
from pytableau.build import (
    DatasourceBuilder,
    LogicalTable,
    Pane,
    RelationBuilder,
    Relationship,
    TableCalculation,
    WorksheetBuilder,
    from_spec,
)
from pytableau.core.formatting import Color, Font, FormatSpec
from pytableau.core.state import fingerprint, snapshot
from pytableau.exceptions import SchemaValidationError
from pytableau.fleet import MigrationEngine, MigrationManifest, MigrationPlan
from pytableau.inspect.diff import Patch, PatchOp
from pytableau.xml.semantic import Capability


def workbook():
    return from_spec(
        {
            "datasources": [
                {
                    "caption": "Data",
                    "columns": [
                        {"caption": "Region"},
                        {"caption": "Sales", "datatype": "real", "role": "measure"},
                        {"caption": "Profit", "datatype": "real", "role": "measure"},
                    ],
                }
            ],
            "worksheets": [
                {"name": "Chart", "datasource": "Data", "rows": ["Region"], "columns": ["Sales"]}
            ],
            "dashboards": [{"name": "Dash", "zones": [{"worksheet": "Chart"}]}],
        }
    )


def test_complete_patch_changes_and_unknown_document_nodes(tmp_path):
    left = workbook()
    left.xml_root.addprevious(etree.Comment("build comment"))
    left.xml_root.addnext(etree.ProcessingInstruction("keep", "trailing"))
    left.save_as(tmp_path / "left.twb")
    with Workbook.open(tmp_path / "left.twb") as right:
        right.worksheets[0].rows = ["Profit"]
        right.dashboards[0].xml_node.set("custom", "changed")
        right.xml_root.set("future-attribute", "keep")
        right.xml_root.append(etree.Element("unknown-extension", payload="x"))
        right.datasources[0].get_field("Sales").datatype = "integer"
        diff = left.diff(right)
        assert "worksheet" in diff.components_modified
        assert "dashboard" in diff.components_modified
        assert "unknown-extension" in diff.after_state["xml"]
        assert "worksheet" in diff.to_html()
        patch = Patch.from_dict(json.loads(Patch.from_diff(diff).to_json()))
        assert left.apply(patch) == 1
        assert left.diff(right).is_empty()
        assert fingerprint(snapshot(left)) == fingerprint(snapshot(right))
        assert "build comment" in left.to_xml_string()
        assert "trailing" in left.to_xml_string()


def test_package_asset_only_patch_uses_working_bytes_and_conflicts(tmp_path):
    archive = tmp_path / "before.twbx"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("nested/main.twb", workbook().to_xml_string())
        z.writestr("Images/logo.png", b"old")
        z.writestr("Data/old.csv", b"remove")
    with Workbook.open(archive) as left, Workbook.open(archive) as right:
        root = right._package_manager.twb_path.parent.parent
        (root / "Images/logo.png").write_bytes(b"new")
        (root / "Data/old.csv").unlink()
        (root / "Images/new.png").write_bytes(b"added")
        assert "Images/new.png" in right._package_manager.list_assets()
        diff = left.diff(right)
        assert diff.assets_modified == ["Data/old.csv", "Images/logo.png", "Images/new.png"]
        patch = Patch.from_diff(diff)
        left.apply(patch)
        assert left.diff(right).is_empty()
        left.save_as(tmp_path / "patched.twbx")
        with zipfile.ZipFile(tmp_path / "patched.twbx") as z:
            assert z.read("Images/logo.png") == b"new"
            assert "Data/old.csv" not in z.namelist()
        prior = fingerprint(snapshot(left))
        with pytest.raises(ValueError, match="conflict"):
            left.apply(patch)
        assert fingerprint(snapshot(left)) == prior


def test_patch_failure_rolls_back_prior_operations():
    wb = workbook()
    original = fingerprint(snapshot(wb))
    ds = wb.datasources[0].name
    patch = Patch(
        [
            PatchOp("modify_field", f"datasource:{ds}/field:Sales", "role", None, "dimension"),
            PatchOp("add_worksheet", "worksheet:Missing", None, None, "Missing"),
        ]
    )
    with pytest.raises(ValueError, match="XML payload"):
        wb.apply(patch)
    assert fingerprint(snapshot(wb)) == original


def test_transaction_restores_document_and_asset_changes(tmp_path):
    archive = tmp_path / "input.twbx"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("main.twb", "<!--preamble-->" + workbook().to_xml_string().split("?>", 1)[1])
        z.writestr("Data/data.csv", "original")
    with Workbook.open(archive) as wb:
        before = fingerprint(snapshot(wb))
        with pytest.raises(RuntimeError), wb.transaction():
            wb.xml_root.set("changed", "true")
            (wb._package_manager.twb_path.parent / "Data/data.csv").write_text("changed")
            raise RuntimeError("rollback")
        assert fingerprint(snapshot(wb)) == before


def test_semantic_errors_and_calc_cycle():
    wb = workbook()
    ds = wb.datasources[0]
    ds.add_calculated_field("A", "[B]")
    ds.add_calculated_field("B", "[A] + [Missing]")
    messages = [i.message for i in wb.validate() if i.level == "error"]
    assert any("Missing" in m for m in messages)
    assert any("cycle" in m for m in messages)
    assert not any("cycle" in i.message for i in wb.validate(semantic=False))


def test_version_normalization_and_capability_rejection():
    wb = workbook()
    wb.xml_root.set("source-build", "2025.3.1 (20253.26.0112.0000)")
    wb._load_tree(wb.xml_tree)
    assert wb.version == "2025.3"
    manifest = etree.SubElement(wb.xml_root, "document-format-change-manifest")
    etree.SubElement(manifest, "document-format-change", name="MultiFactRelationships")
    before = wb.to_xml_string()
    report = wb.compatibility("2024.1")
    assert report.status == "unsupported"
    with pytest.raises(SchemaValidationError):
        wb.migrate_version("2024.1", allow_unverified=True)
    assert wb.to_xml_string() == before
    assert wb.compatibility("2025.3").compatible


def test_unknown_downgrade_needs_explicit_unverified_override():
    wb = Workbook.new(version="2025.3")
    etree.SubElement(
        etree.SubElement(wb.xml_root, "document-format-change-manifest"),
        "document-format-change",
        name="UnverifiedFeature",
    )
    report = wb.compatibility("2024.3")
    assert report.status == "unverified"
    registry = (
        Capability("custom", "2025.2", ".//document-format-change[@name='UnverifiedFeature']"),
    )
    assert wb.compatibility("2024.3", capabilities=registry).status == "unsupported"
    with pytest.raises(SchemaValidationError):
        wb.migrate_version("2024.3")
    wb.migrate_version("2024.3", allow_unverified=True)
    assert wb.version == "2024.3"


def plan_fixture(tmp_path, *, inplace=False):
    source, output, journal = tmp_path / "source", tmp_path / "output", tmp_path / "journal"
    source.mkdir()
    for name in ("a", "b"):
        wb = workbook()
        wb.save_as(source / f"{name}.twb")
    plan = MigrationPlan().source_directory(source).rename_fields({"Sales": "Revenue"})
    if not inplace:
        plan.output_directory(output)
    return source, source if inplace else output, journal, MigrationEngine(plan)


@pytest.mark.parametrize("inplace", [False, True])
def test_durable_migration_apply_resume_and_rollback(tmp_path, inplace):
    source, output, journal, engine = plan_fixture(tmp_path, inplace=inplace)
    originals = {p.name: p.read_bytes() for p in source.glob("*.twb")}
    output.mkdir(exist_ok=True)
    if not inplace:
        (output / "a.twb").write_bytes(b"pre-existing destination")
    old_output = {p.name: p.read_bytes() for p in output.glob("*.twb")}
    manifest = engine.prepare(journal)
    assert manifest.status == "prepared"
    assert {p.name: p.read_bytes() for p in source.glob("*.twb")} == originals
    manifest.apply()
    MigrationManifest(manifest.path).resume()
    with Workbook.open(output / "a.twb") as wb:
        assert wb.datasources[0].get_field("Revenue")
    manifest.rollback()
    assert manifest.status == "rolled_back"
    assert {p.name: p.read_bytes() for p in output.glob("*.twb")} == old_output
    assert {p.name: p.read_bytes() for p in source.glob("*.twb")} == originals


def test_resume_after_replace_before_status_recorded(tmp_path, monkeypatch):
    _, output, journal, engine = plan_fixture(tmp_path)
    manifest = engine.prepare(journal)
    original_save = manifest._save

    def crash():
        if any(r["status"] == "written" for r in manifest.data["files"]):
            raise RuntimeError("process died after replacement")
        original_save()

    monkeypatch.setattr(manifest, "_save", crash)
    with pytest.raises(RuntimeError):
        manifest.apply()
    assert (output / "a.twb").exists()
    recovered = MigrationManifest(manifest.path)
    recovered.resume()
    assert recovered.status == "applied"
    recovered.rollback()
    assert not list(output.glob("*.twb"))


def test_migration_conflict_preflights_all_before_any_write(tmp_path):
    source, output, journal, engine = plan_fixture(tmp_path)
    manifest = engine.prepare(journal)
    (source / "b.twb").write_text("external edit")
    with pytest.raises(ValueError, match="source conflict"):
        manifest.apply()
    assert not output.exists()


def test_rollback_conflict_leaves_all_outputs_untouched(tmp_path):
    _, output, journal, engine = plan_fixture(tmp_path)
    manifest = engine.prepare(journal)
    manifest.apply()
    (output / "b.twb").write_bytes(b"external edit")
    prior = (output / "a.twb").read_bytes()
    with pytest.raises(ValueError, match="Rollback conflict"):
        manifest.rollback()
    assert (output / "a.twb").read_bytes() == prior


def test_native_join_tree_and_logical_relationship_authoring():
    orders = RelationBuilder.table("[public].[orders]", alias="Orders")
    customers = RelationBuilder.custom_sql("SELECT id FROM customers", alias="Customers")
    join = orders.join(
        customers, keys=(("[Orders].[customer_id]", "[Customers].[id]"),), how="left"
    )
    node = join.build()
    assert node.get("join") == "left"
    assert node.find("clause/expression/expression").get("op") == "[Orders].[customer_id]"
    assert len(node.findall("relation")) == 2
    ds = (
        DatasourceBuilder("Data")
        .logical_model(
            [
                LogicalTable("orders", "Orders", join),
                LogicalTable("customers", "Customers", customers),
            ],
            [Relationship("orders", "customers", (("[customer_id]", "[id]"),))],
        )
        .build()
    )
    assert ds.find("connection/relation").get("type") == "collection"
    assert ds.find("connection/named-connections/named-connection") is not None
    assert (
        ds.find("object-graph/relationships/relationship/first-end-point").get("object-id")
        == "orders"
    )
    with pytest.raises(ValueError, match="alias"):
        orders.join(customers, keys=(("[Missing].[id]", "[Customers].[id]"),))


def test_native_axes_tablecalc_and_format_roundtrip(tmp_path):
    wb = workbook()
    ws = (
        WorksheetBuilder("Native")
        .datasource(wb.datasources[0].name)
        .columns("Region")
        .dual_axis("SUM(Sales)", "SUM(Profit)")
        .panes(Pane("Bar", "SUM(Sales)"), Pane("Line", "SUM(Profit)"))
        .format(FormatSpec(Font(size=14, bold=True), Color.from_hex("#336699")))
        .build()
    )
    wb.add_worksheet(ws)
    encodings = ws.findall("table/style/style-rule[@element='axis']/encoding")
    assert len(encodings) == 2 and all(e.get("synchronized") == "true" for e in encodings)
    assert ws.find("table/panes/pane").get("y-axis-name").endswith("[sum:Sales:qk]")
    assert FormatSpec.read(ws).font.size == 14
    FormatSpec(background_color=Color.from_hex("#FFFFFF")).apply(ws)
    assert FormatSpec.read(ws).font.bold
    calc = TableCalculation("SUM(Sales)", addressing=("Region",), partitioning=("Profit",))
    native = (
        WorksheetBuilder("Calc")
        .datasource(wb.datasources[0].name)
        .rows("Region")
        .columns("SUM(Sales)")
        .table_calculation(calc)
        .build()
    )
    wb.add_worksheet(native)
    assert "pcto:sum:Sales:qk" in native.findtext("table/cols")
    assert native.find(".//table-calc/order").get("field").endswith("[none:Region:nk]")
    assert not native.findall(".//partitioning")
    assert not [u for u in wb.references().uses if u.error]
    wb.save_as(tmp_path / "native.twb")
    with Workbook.open(tmp_path / "native.twb") as saved:
        assert fingerprint(snapshot(saved)) == fingerprint(snapshot(wb))


def test_spec_supports_native_advanced_features():
    spec = {
        "datasources": [
            {
                "caption": "Data",
                "columns": [{"caption": "Sales"}, {"caption": "Profit"}],
                "relation": {
                    "type": "join",
                    "how": "inner",
                    "left": {"table": "[orders]", "alias": "Orders"},
                    "right": {"table": "[customers]", "alias": "Customers"},
                    "keys": [["[Orders].[id]", "[Customers].[id]"]],
                },
            }
        ],
        "worksheets": [
            {
                "name": "Chart",
                "datasource": "Data",
                "dual_axis": {"primary": "SUM(Sales)", "secondary": "SUM(Profit)"},
                "format": {"text_color": "#112233"},
            }
        ],
    }
    wb = from_spec(copy.deepcopy(spec))
    assert wb.datasources[0].xml_node.find("connection/relation").get("join") == "inner"
    assert wb.worksheets[0].xml_node.find("table/panes") is not None


def test_manual_remove_field_retains_datasource_and_formula_noops_fail():
    wb = workbook()
    ds = wb.datasources[0].name
    assert (
        wb.apply(
            Patch([PatchOp("remove_field", f"datasource:{ds}/field:Profit", None, None, None)])
        )
        == 1
    )
    assert len(wb.datasources) == 1
    assert wb.datasources[0].get_field("Profit") is None
    with pytest.raises(ValueError, match="calculated"):
        wb.apply(
            Patch([PatchOp("modify_field", f"datasource:{ds}/field:Sales", "formula", None, "1")])
        )
    with pytest.raises(ValueError, match="conflict"):
        wb.apply(
            Patch(
                [
                    PatchOp(
                        "modify_field",
                        f"datasource:{ds}/field:Sales",
                        "caption",
                        "sales",
                        "Revenue",
                    )
                ]
            )
        )


def test_semantically_invalid_snapshot_patch_rolls_back():
    left, right = workbook(), workbook()
    right.datasources[0].add_calculated_field("Broken", "[Unknown]")
    prior = fingerprint(snapshot(left))
    with pytest.raises(SchemaValidationError, match="Unknown"):
        left.apply(Patch.from_diff(left.diff(right)))
    assert fingerprint(snapshot(left)) == prior


def test_plain_asset_deletion_survives_save_and_reopen(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    workbook().save_as(a / "w.twb")
    workbook().save_as(b / "w.twb")
    (a / "Data").mkdir()
    (a / "Data/deleted.csv").write_bytes(b"owned asset")
    with Workbook.open(a / "w.twb") as left, Workbook.open(b / "w.twb") as right:
        left.apply(Patch.from_diff(left.diff(right)))
        left.save()
        assert not (a / "Data/deleted.csv").exists()
        with Workbook.open(a / "w.twb") as reopened:
            assert reopened.diff(right).is_empty()


def test_package_member_layout_changes_are_patchable(tmp_path):
    for name, member in (("a", "nested/main.twb"), ("b", "main.twb")):
        with zipfile.ZipFile(tmp_path / f"{name}.twbx", "w") as z:
            z.writestr(member, workbook().to_xml_string())
    with Workbook.open(tmp_path / "a.twbx") as a, Workbook.open(tmp_path / "b.twbx") as b:
        diff = a.diff(b)
        assert not diff.is_empty()
        a.apply(Patch.from_diff(diff))
        assert a.diff(b).is_empty()
        assert a._package_manager.twb_member_name == "main.twb"


def test_corrupt_backup_and_ancestor_output_are_not_false_success(tmp_path):
    _, output, journal, engine = plan_fixture(tmp_path)
    output.mkdir()
    (output / "a.twb").write_bytes(b"original")
    manifest = engine.prepare(journal)
    manifest.data["files"][0]["backup"] = None
    manifest._save()
    with pytest.raises(ValueError, match="backup"):
        manifest.rollback()
    assert (output / "a.twb").read_bytes() == b"original"
    source = tmp_path / "ancestor" / "nested"
    source.mkdir(parents=True)
    workbook().save_as(source / "c.twb")
    plan = (
        MigrationPlan()
        .source_directory(source)
        .output_directory(source.parent)
        .rename_fields({"Sales": "Revenue"})
    )
    second = MigrationEngine(plan).prepare(tmp_path / "journal2")
    assert second.data["files"]
    second.apply()
    assert (source.parent / "c.twb").is_file()


def test_native_dual_axis_uses_requested_calculation_and_valid_encodings():
    ds = workbook().datasources[0].name
    node = (
        WorksheetBuilder("Native")
        .datasource(ds)
        .columns("Region")
        .dual_axis("SUM(Sales)", "SUM(Profit)")
        .table_calculation(TableCalculation("SUM(Sales)"))
        .build()
    )
    assert "pcto:sum:Sales:qk" in node.findtext("table/rows")
    assert "pcto:sum:Sales:qk" in node.find("table/panes/pane").get("y-axis-name")
    assert all(n.get("type") == "space" for n in node.findall("table/style/style-rule/encoding"))
    assert all(
        n.get("type") in {"nominal", "quantitative", "ordinal"}
        for n in node.findall(".//column-instance")
    )
    assert [n.tag for n in node.find("table")] == ["view", "style", "panes", "rows", "cols"]


@pytest.mark.parametrize(
    "aggregate,code,derivation",
    [
        ("COUNT", "cnt", "Count"),
        ("COUNTD", "ctd", "CountD"),
        ("ATTR", "attr", "Attribute"),
        ("YEAR", "yr", "Year"),
    ],
)
def test_native_aggregate_enums(aggregate, code, derivation):
    node = (
        WorksheetBuilder("Native")
        .datasource("D")
        .columns(f"{aggregate}(Sales)")
        .panes(Pane())
        .build()
    )
    instance = node.find(".//column-instance")
    assert instance.get("name").startswith(f"[{code}:")
    assert instance.get("derivation") == derivation


def test_native_spec_resolves_calculated_caption_to_internal_identity():
    wb = from_spec(
        {
            "datasources": [
                {
                    "caption": "Data",
                    "columns": [
                        {"caption": "Sales", "datatype": "real", "role": "measure"},
                        {"caption": "Region"},
                    ],
                    "calculated_fields": [{"caption": "Margin", "formula": "[Sales]*0.2"}],
                }
            ],
            "worksheets": [
                {
                    "name": "Chart",
                    "datasource": "Data",
                    "rows": ["Region"],
                    "columns": ["SUM(Margin)"],
                    "table_calculations": [
                        {
                            "field": "SUM(Margin)",
                            "function": "running_total",
                            "addressing": ["Region"],
                        }
                    ],
                }
            ],
        }
    )
    field = wb.datasources[0].get_field("Margin")
    node = wb.worksheets[0].xml_node
    assert field.name[1:-1] in node.findtext("table/cols")
    dependency = node.find(f".//datasource-dependencies/column[@name='{field.name}']")
    assert dependency.find("calculation").get("formula") == "[Sales]*0.2"
    assert node.find(".//table-calc").get("type") == "CumTotal"
    assert not [i for i in wb.validate() if i.level == "error"]


def test_qualified_shelf_edits_do_not_modify_another_datasource():
    wb = workbook()
    ws = wb.worksheets[0]
    ws.rows = ["[left].[sum:Sales:qk]", "[right].[sum:Sales:qk]"]
    with pytest.raises(ValueError, match="Ambiguous"):
        ws.remove_from_shelf("rows", "Sales")
    ws.move_within_shelf("rows", "[right].[sum:Sales:qk]", 0)
    assert ws.rows[0].datasource == "right"
    assert ws.remove_from_shelf("rows", "[left].[sum:Sales:qk]") == 1
    assert len(ws.rows) == 1 and ws.rows[0].datasource == "right"


def test_plain_save_failure_restores_xml_assets_and_deletions(tmp_path, monkeypatch):
    from pathlib import Path

    path = tmp_path / "w.twb"
    wb = workbook()
    wb.save_as(path)
    data = tmp_path / "Data"
    data.mkdir()
    (data / "a.csv").write_bytes(b"old-a")
    (data / "b.csv").write_bytes(b"old-b")
    with Workbook.open(path) as wb:
        original = path.read_bytes()
        with wb.transaction():
            wb.xml_root.set("modified", "true")
            root = wb._package_manager.twb_path.parent
            (root / "Data/a.csv").write_bytes(b"new-a")
            (root / "Data/b.csv").write_bytes(b"new-b")
        replace = Path.replace

        def fail_xml(source, target):
            if Path(target) == path:
                raise OSError("injected XML replacement failure")
            return replace(source, target)

        monkeypatch.setattr(Path, "replace", fail_xml)
        with pytest.raises(OSError, match="injected"):
            wb.save()
        assert path.read_bytes() == original
        assert (data / "a.csv").read_bytes() == b"old-a"
        assert (data / "b.csv").read_bytes() == b"old-b"


def test_native_format_manifest_cannot_bypass_known_capabilities():
    wb = Workbook.new(version="2025.3")
    manifest = etree.SubElement(wb.xml_root, "document-format-change-manifest")
    etree.SubElement(manifest, "MultiFactRelationships")
    etree.SubElement(manifest, "UnregisteredFutureCapability")
    report = wb.compatibility("2024.1")
    assert report.status == "unsupported"
    assert "multi_fact_relationships" in report.detected_features
    assert any(i.feature == "UnregisteredFutureCapability" for i in report.issues)
    with pytest.raises(SchemaValidationError, match="2024.2"):
        wb.migrate_version("2024.1", allow_unverified=True)


@pytest.mark.parametrize("extension", [".twb", ".twbx"])
def test_plain_save_preserves_referenced_images_without_transaction(tmp_path, extension):
    source = tmp_path / "source"
    source.mkdir()
    image = source / "Images/logo.png"
    image.parent.mkdir()
    image.write_bytes(b"image")
    wb = workbook()
    etree.SubElement(wb.xml_root, "background-image", filename="Images/logo.png")
    path = source / "source.twb"
    path.write_text(wb.to_xml_string())
    output = tmp_path / "output" / ("copy" + extension)
    with Workbook.open(path) as opened:
        opened.save_as(output)
    with Workbook.open(output) as copied:
        assert snapshot(copied)["assets"]["Images/logo.png"] == "aW1hZ2U="


def test_native_dependency_copy_cannot_invent_a_physical_field():
    wb = from_spec(
        {
            "datasources": [
                {
                    "caption": "Data",
                    "columns": [{"caption": "Sales", "datatype": "real", "role": "measure"}],
                }
            ],
            "worksheets": [
                {
                    "name": "Bad",
                    "datasource": "Data",
                    "columns": ["SUM(Missing)"],
                    "panes": [{"mark_type": "Bar"}],
                }
            ],
        }
    )
    assert any("Missing" in i.message for i in wb.validate() if i.level == "error")


def test_manual_structural_patch_enforces_old_xml_and_payload_identity():
    wb = workbook()
    ds = wb.datasources[0]
    sales = ds.get_field("Sales")
    old = etree.tostring(sales.xml_node, encoding="unicode", with_tail=False)
    sales.datatype = "integer"
    target = f"datasource:{ds.name}/field:Sales"
    with pytest.raises(ValueError, match="conflict"):
        wb.apply(Patch([PatchOp("remove_field", target, None, old, None)]))
    assert wb.datasources[0].get_field("Sales").datatype == "integer"
    with pytest.raises(ValueError, match="identity"):
        wb.apply(
            Patch(
                [
                    PatchOp(
                        "add_field",
                        f"datasource:{ds.name}/field:Expected",
                        None,
                        None,
                        '<column name="[Different]" caption="Different" datatype="string"/>',
                    )
                ]
            )
        )
    assert wb.datasources[0].get_field("Different") is None


def test_rollback_retains_pending_asset_deletion_baseline(tmp_path):
    source = tmp_path / "source.twb"
    workbook().save_as(source)
    data = tmp_path / "Data/a.csv"
    data.parent.mkdir()
    data.write_bytes(b"old")
    with Workbook.open(source) as left, Workbook.open(source) as right:
        with right.transaction():
            (right._package_manager.twb_path.parent / "Data/a.csv").unlink()
        left.apply(Patch.from_diff(left.diff(right)))
        pending = dict(left._asset_tombstones)
        with pytest.raises(RuntimeError), left.transaction():
            restored = left._package_manager.twb_path.parent / "Data/a.csv"
            restored.parent.mkdir()
            restored.write_bytes(b"new")
            raise RuntimeError("rollback")
        assert left._asset_tombstones == pending
        # A failing patch may first restore the asset and clear its tombstone.
        target = snapshot(left)
        target["assets"]["Data/a.csv"] = "bmV3"
        patch = Patch(
            [
                PatchOp("replace_snapshot", "workbook", None, fingerprint(snapshot(left)), target),
                PatchOp("unknown", "workbook", None, None, None),
            ]
        )
        with pytest.raises(ValueError):
            left.apply(patch)
        assert left._asset_tombstones == pending
        left.save()
        assert not data.exists()


def test_nested_package_asset_deletion_maps_to_plain_layout(tmp_path):
    archive = tmp_path / "nested.twbx"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("nested/main.twb", workbook().to_xml_string())
        z.writestr("nested/Data/a.csv", b"old")
    output = tmp_path / "output/w.twb"
    with Workbook.open(archive) as baseline:
        baseline.save_as(output)
    assert (output.parent / "Data/a.csv").exists()
    with Workbook.open(archive) as left, Workbook.open(archive) as right:
        with right.transaction():
            (right._package_manager.twb_path.parent / "Data/a.csv").unlink()
        left.apply(Patch.from_diff(left.diff(right)))
        left.save_as(output)
    assert not (output.parent / "Data/a.csv").exists()
    with Workbook.open(output) as saved:
        assert not snapshot(saved)["assets"]


def test_migration_rejects_duplicate_symlink_destinations_before_install(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    for name in ("a", "b"):
        wb = workbook()
        wb.xml_root.set("marker", name)
        wb.save_as(source / f"{name}.twb")
    shared = output / "shared.twb"
    shared.write_bytes(b"original")
    (output / "a.twb").symlink_to(shared)
    (output / "b.twb").symlink_to(shared)
    plan = (
        MigrationPlan()
        .source_directory(source)
        .output_directory(output)
        .rename_fields({"Sales": "Revenue"})
    )
    with pytest.raises(ValueError, match="Duplicate"):
        MigrationEngine(plan).prepare(tmp_path / "journal")
    assert shared.read_bytes() == b"original"


def test_pane_axis_requires_an_actual_shelf_binding():
    builder = (
        WorksheetBuilder("Missing axis")
        .datasource("Data")
        .columns("SUM(Sales)")
        .panes(Pane("Bar", "SUM(Profit)"))
    )
    with pytest.raises(ValueError, match="shelf binding"):
        builder.build()
    valid = (
        WorksheetBuilder("X axis")
        .datasource("Data")
        .columns("SUM(Sales)")
        .panes(Pane("Bar", "SUM(Sales)"))
        .build()
    )
    assert valid.find("table/panes/pane").get("x-axis-name").endswith("[sum:Sales:qk]")
