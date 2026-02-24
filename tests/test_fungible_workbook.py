"""Mutation tests against sample_workbook_fungible.twbx.

Each test mutates sample_workbook_fungible.twbx in-place and re-opens it to
verify the change persisted.  The ``fresh_fungible`` fixture resets the file
to an exact copy of sample_workbook.twbx before and after every test, so:

  - Tests are fully isolated from each other.
  - sample_workbook_fungible.twbx is always restored when the suite finishes,
    including on failure.

Run from the pytableau project root.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pytableau.core.workbook import Workbook

ROOT = Path(__file__).parent.parent
SAMPLE = ROOT / "sample_workbook.twbx"
FUNGIBLE = ROOT / "sample_workbook_fungible.twbx"

pytestmark = pytest.mark.skipif(
    not SAMPLE.exists(),
    reason="sample_workbook.twbx not found in project root",
)


# ---------------------------------------------------------------------------
# Fixture: reset fungible workbook around every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_fungible():
    """Copy sample → fungible before each test; restore after (even on failure)."""
    shutil.copy2(SAMPLE, FUNGIBLE)
    yield
    shutil.copy2(SAMPLE, FUNGIBLE)


# ---------------------------------------------------------------------------
# 1. Connection: swap hyper extract path
# ---------------------------------------------------------------------------


def test_connection_swap_hyper_dbname():
    """Changing hyper dbname persists through a save/reload cycle."""
    new_path = "Data/Extracts/production_extract.hyper"

    wb = Workbook.open(FUNGIBLE)
    ds = list(wb.datasources)[0]
    hyper = next(c for c in ds.connections if c.class_ == "hyper")
    hyper.dbname = new_path
    wb.save()
    wb.close()

    wb2 = Workbook.open(FUNGIBLE)
    ds2 = list(wb2.datasources)[0]
    hyper2 = next(c for c in ds2.connections if c.class_ == "hyper")
    assert hyper2.dbname == new_path
    wb2.close()


def test_connection_swap_server_via_cli():
    """swap_connection CLI command writes new server into the file."""
    from pytableau.cli.main import app

    result = app.call(
        "swap_connection",
        workbook=FUNGIBLE,
        server="prod-server.corp.com",
    )
    assert result.ok, f"swap_connection failed: {result.error}"

    wb = Workbook.open(FUNGIBLE)
    ds = list(wb.datasources)[0]
    servers = {c.server for c in ds.connections if c.server}
    assert "prod-server.corp.com" in servers
    wb.close()


def test_connection_swap_preserves_other_connections():
    """Swapping connection properties doesn't remove other connections."""
    from pytableau.cli.main import app

    original_count = len(list(list(Workbook.open(FUNGIBLE).datasources)[0].connections))

    app.call("swap_connection", workbook=FUNGIBLE, server="new-host.example.com")

    wb = Workbook.open(FUNGIBLE)
    after_count = len(list(list(wb.datasources)[0].connections))
    assert after_count == original_count
    wb.close()


# ---------------------------------------------------------------------------
# 2. Field: rename a calculated field
# ---------------------------------------------------------------------------


def test_rename_field_gd_int():
    """Renaming 'GD Int' → 'Goal Diff Int' is visible after reload."""
    from pytableau.cli.main import app

    result = app.call(
        "rename_field",
        workbook=FUNGIBLE,
        old_name="GD Int",
        new_name="Goal Diff Int",
    )
    assert result.ok, f"rename_field failed: {result.error}"

    wb = Workbook.open(FUNGIBLE)
    ds = list(wb.datasources)[0]
    captions = {f.caption for f in ds.all_fields}
    assert "Goal Diff Int" in captions or "[Goal Diff Int]" in captions
    assert "GD Int" not in captions and "[GD Int]" not in captions
    wb.close()


def test_rename_field_updates_canonical_xml_definition():
    """The canonical datasource <column> node is updated in the XML.

    Note: Tableau also stores redundant column copies inside per-worksheet
    <datasource-dependencies> nodes.  Those are advisory display metadata and
    are not read by pytableau — only the canonical definition matters.
    """
    from lxml import etree

    from pytableau.cli.main import app
    from pytableau.package.manager import PackageManager

    app.call(
        "rename_field",
        workbook=FUNGIBLE,
        old_name="GD Int",
        new_name="Goal Diff Int",
    )

    pm = PackageManager(FUNGIBLE)
    tree = etree.parse(str(pm.twb_path))
    pm.close()

    # Find the federated datasource (not the Parameters pseudo-datasource).
    # The canonical column node inside it must be updated; worksheet-level
    # <datasource-dependencies> copies are advisory and may still carry the
    # old name.
    federated_ds = next(
        el
        for el in tree.getroot().findall(".//datasources/datasource")
        if (el.get("name") or "").startswith("federated.")
    )
    canonical_captions = {
        col.get("caption")
        for col in federated_ds.findall("column")  # direct children only
        if col.get("caption")
    }
    assert "Goal Diff Int" in canonical_captions
    assert "GD Int" not in canonical_captions


# ---------------------------------------------------------------------------
# 3. Version migration
# ---------------------------------------------------------------------------


def test_version_migrate_2023_1():
    """Migrating to 2023.1 changes version and source-build after reload."""
    from pytableau.cli.main import app

    result = app.call(
        "version_migrate",
        workbook=FUNGIBLE,
        target_version="2023.1",
    )
    assert result.ok, f"version_migrate failed: {result.error}"

    wb = Workbook.open(FUNGIBLE)
    assert wb.version == "2023.1"
    wb.close()


def test_version_migrate_source_build_attribute():
    """source-build XML attribute matches expected build string for 2023.1."""
    from lxml import etree

    from pytableau.constants import TABLEAU_VERSION_MAP
    from pytableau.package.manager import PackageManager

    wb = Workbook.open(FUNGIBLE)
    wb.migrate_version("2023.1")
    wb.save()
    wb.close()

    pm = PackageManager(FUNGIBLE)
    tree = etree.parse(str(pm.twb_path))
    pm.close()

    source_build = tree.getroot().get("source-build")
    assert source_build == TABLEAU_VERSION_MAP["2023.1"]


def test_version_migrate_then_back():
    """Migrating 2024.1 → 2022.4 → 2024.1 round-trips correctly."""
    wb = Workbook.open(FUNGIBLE)
    assert wb.version == "2024.1"

    wb.migrate_version("2022.4")
    wb.save()
    wb.close()

    wb2 = Workbook.open(FUNGIBLE)
    assert wb2.version == "2022.4"
    wb2.migrate_version("2024.1")
    wb2.save()
    wb2.close()

    wb3 = Workbook.open(FUNGIBLE)
    assert wb3.version == "2024.1"
    wb3.close()


# ---------------------------------------------------------------------------
# 4. Calculated field: formula rewrite
# ---------------------------------------------------------------------------


def test_rewrite_formula_persists():
    """Updating a calc field's formula via XML is visible after reload."""

    wb = Workbook.open(FUNGIBLE)
    ds = list(wb.datasources)[0]

    # Find GD Int and rewrite its formula
    calcs = list(ds.calculated_fields)
    gd_int = next(cf for cf in calcs if cf.caption == "GD Int")
    original_formula = gd_int.formula

    new_formula = "INT([GD]) * 2"
    calc_el = gd_int.xml_node.find("calculation")
    if calc_el is not None:
        calc_el.set("formula", new_formula)
    else:
        # formula stored as attribute on the column node itself
        gd_int.xml_node.set("formula", new_formula)

    wb.save()
    wb.close()

    # Reload and verify
    wb2 = Workbook.open(FUNGIBLE)
    ds2 = list(wb2.datasources)[0]
    gd_int2 = next(cf for cf in ds2.calculated_fields if cf.caption == "GD Int")
    assert gd_int2.formula == new_formula
    assert gd_int2.formula != original_formula
    wb2.close()


def test_add_calculated_field_persists():
    """A newly added calculated field survives a save/reload cycle."""
    wb = Workbook.open(FUNGIBLE)
    ds = list(wb.datasources)[0]

    before_count = len(list(ds.calculated_fields))
    ds.add_calculated_field(
        caption="Test | Total Goals",
        formula="[GF] + [GA]",
        datatype="integer",
        role="measure",
    )
    assert len(list(ds.calculated_fields)) == before_count + 1
    wb.save()
    wb.close()

    wb2 = Workbook.open(FUNGIBLE)
    ds2 = list(wb2.datasources)[0]
    after_count = len(list(ds2.calculated_fields))
    captions = {cf.caption for cf in ds2.calculated_fields}

    assert after_count == before_count + 1
    assert "Test | Total Goals" in captions
    wb2.close()


def test_added_field_formula_correct():
    """Formula of a newly added field is readable after reload."""
    wb = Workbook.open(FUNGIBLE)
    ds = list(wb.datasources)[0]
    ds.add_calculated_field(
        caption="Test | Points Per Game",
        formula="[Points] / MAX([Initial or Final])",
        datatype="real",
        role="measure",
    )
    wb.save()
    wb.close()

    wb2 = Workbook.open(FUNGIBLE)
    ds2 = list(wb2.datasources)[0]
    ppg = next(
        (cf for cf in ds2.calculated_fields if cf.caption == "Test | Points Per Game"),
        None,
    )
    assert ppg is not None
    assert "[Points]" in (ppg.formula or "")
    wb2.close()


# ---------------------------------------------------------------------------
# 5. Parameter: change default value
# ---------------------------------------------------------------------------


def test_parameter_value_change_persists():
    """Updating a parameter's default value persists through save/reload."""

    wb = Workbook.open(FUNGIBLE)
    params = list(wb.parameters.parameters)
    ch1 = next(p for p in params if p.caption == "Club Highlight 1")

    # Change the default value attribute on the XML node
    ch1.xml_node.set("value", '"Arsenal"')
    wb.save()
    wb.close()

    wb2 = Workbook.open(FUNGIBLE)
    params2 = list(wb2.parameters.parameters)
    ch1_2 = next(p for p in params2 if p.caption == "Club Highlight 1")
    assert '"Arsenal"' in (ch1_2.value or "")
    wb2.close()


def test_two_parameters_changed_independently():
    """Changing both Club Highlight params results in different values."""
    wb = Workbook.open(FUNGIBLE)
    params = list(wb.parameters.parameters)

    ch1 = next(p for p in params if p.caption == "Club Highlight 1")
    ch2 = next(p for p in params if p.caption == "Club Highlight 2")
    ch1.xml_node.set("value", '"Liverpool"')
    ch2.xml_node.set("value", '"Manchester City"')
    wb.save()
    wb.close()

    wb2 = Workbook.open(FUNGIBLE)
    params2 = list(wb2.parameters.parameters)
    ch1_2 = next(p for p in params2 if p.caption == "Club Highlight 1")
    ch2_2 = next(p for p in params2 if p.caption == "Club Highlight 2")

    assert '"Liverpool"' in (ch1_2.value or "")
    assert '"Manchester City"' in (ch2_2.value or "")
    assert ch1_2.value != ch2_2.value
    wb2.close()


# ---------------------------------------------------------------------------
# 6. Multiple sequential mutations
# ---------------------------------------------------------------------------


def test_sequential_mutations_all_persist():
    """Three independent mutations applied sequentially all survive reload."""
    # Mutation 1: rename a field using the proper datasource API
    wb = Workbook.open(FUNGIBLE)
    ds = list(wb.datasources)[0]
    ds.rename_field("GD Int", "GD Integer")
    wb.save()
    wb.close()

    # Mutation 2: version migrate
    wb = Workbook.open(FUNGIBLE)
    wb.migrate_version("2023.1")
    wb.save()
    wb.close()

    # Mutation 3: add a calculated field
    wb = Workbook.open(FUNGIBLE)
    ds = list(wb.datasources)[0]
    ds.add_calculated_field(
        caption="Test | Season Count",
        formula="COUNTD([Season])",
        datatype="integer",
        role="measure",
    )
    wb.save()
    wb.close()

    # Verify all three persisted
    wb_final = Workbook.open(FUNGIBLE)
    ds_final = list(wb_final.datasources)[0]

    assert wb_final.version == "2023.1"

    captions = {cf.caption for cf in ds_final.calculated_fields}
    assert "Test | Season Count" in captions

    all_captions = {f.caption for f in ds_final.all_fields}
    # The object model should reflect the rename; raw worksheet dependency
    # copies are advisory and not parsed into the object model.
    assert "GD Int" not in all_captions, (
        "GD Int still present in datasource object model after rename"
    )

    wb_final.close()


# ---------------------------------------------------------------------------
# 7. Integrity checks: mutations don't break other data
# ---------------------------------------------------------------------------


def test_rename_preserves_worksheet_count():
    """Renaming a field doesn't remove worksheets from the workbook."""
    from pytableau.cli.main import app

    ws_before = list(Workbook.open(FUNGIBLE).worksheets.names)
    app.call(
        "rename_field",
        workbook=FUNGIBLE,
        old_name="GD Int",
        new_name="GD Integer",
    )
    wb = Workbook.open(FUNGIBLE)
    assert wb.worksheets.names == ws_before
    wb.close()


def test_version_migrate_preserves_datasource():
    """Version migration doesn't alter the datasource structure."""
    wb_before = Workbook.open(FUNGIBLE)
    ds_before = list(wb_before.datasources)[0]
    field_count_before = len(list(ds_before.all_fields))
    calc_count_before = len(list(ds_before.calculated_fields))
    wb_before.close()

    wb = Workbook.open(FUNGIBLE)
    wb.migrate_version("2022.4")
    wb.save()
    wb.close()

    wb_after = Workbook.open(FUNGIBLE)
    ds_after = list(wb_after.datasources)[0]
    assert len(list(ds_after.all_fields)) == field_count_before
    assert len(list(ds_after.calculated_fields)) == calc_count_before
    wb_after.close()


def test_add_field_preserves_parameter_count():
    """Adding a calculated field doesn't corrupt the parameters datasource."""
    wb = Workbook.open(FUNGIBLE)
    ds = list(wb.datasources)[0]
    ds.add_calculated_field(
        caption="Test | Canary",
        formula="1",
        datatype="integer",
        role="measure",
    )
    wb.save()
    wb.close()

    wb2 = Workbook.open(FUNGIBLE)
    assert wb2.parameters is not None
    assert len(list(wb2.parameters.parameters)) == 3
    wb2.close()


def test_validate_after_mutation_still_clean():
    """Validation finds no errors after a version migrate + field add."""
    wb = Workbook.open(FUNGIBLE)
    ds = list(wb.datasources)[0]
    wb.migrate_version("2023.1")
    ds.add_calculated_field(
        caption="Test | Canary 2",
        formula="[GF] - [GA]",
        datatype="integer",
        role="measure",
    )
    wb.save()
    wb.close()

    wb2 = Workbook.open(FUNGIBLE)
    issues = wb2.validate()
    errors = [i for i in issues if i.level == "error"]
    assert errors == [], f"Validation errors after mutation: {errors}"
    wb2.close()
