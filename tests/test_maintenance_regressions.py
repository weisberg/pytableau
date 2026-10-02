"""Regression coverage for the maintenance review's data-loss and fleet defects."""

from __future__ import annotations

import copy
import shutil
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from pytableau import Workbook
from pytableau._compat import _MissingDependency
from pytableau.build import from_spec
from pytableau.core.datasource import Datasource
from pytableau.exceptions import AmbiguousWorkbookError, InvalidWorkbookError, ValidationIssue
from pytableau.fleet import ComplianceRunner, FleetScanner, MigrationEngine, MigrationPlan
from pytableau.governance import GovernanceRuleset
from pytableau.package.manager import PackageManager


def _copy_workbook(directory: Path, minimal_twb: Path, name: str = "source.twb") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    shutil.copyfile(minimal_twb, path)
    return path


@pytest.mark.parametrize("suffix", [".twb", ".twbx"])
def test_save_as_preserves_source_and_save_targets_latest_path(tmp_path, minimal_twb, suffix):
    source = _copy_workbook(tmp_path, minimal_twb)
    original = source.read_bytes()
    output = tmp_path / f"output{suffix}"
    with Workbook.open(source) as wb:
        wb.datasources[0].swap_connection(server="first.example.com")
        wb.save_as(output)
        assert source.read_bytes() == original
        wb.datasources[0].swap_connection(server="second.example.com")
        wb.save()
    assert source.read_bytes() == original
    with Workbook.open(output) as saved:
        assert saved.datasources[0].connections[0].server == "second.example.com"


def test_new_workbook_can_save_nested_package_deterministically(tmp_path):
    wb = Workbook.new()
    first = tmp_path / "nested" / "first.twbx"
    second = tmp_path / "second.twbx"
    wb.save_as(first)
    wb.save_as(second)
    assert first.read_bytes() == second.read_bytes()
    with Workbook.open(first) as reopened:
        assert reopened.version == wb.version


def test_failed_save_preserves_existing_destination(tmp_path, minimal_twb, monkeypatch):
    source = _copy_workbook(tmp_path, minimal_twb)
    output = tmp_path / "existing.twbx"
    output.write_bytes(b"previous contents")

    def broken_save(self, destination, **kwargs):
        Path(destination).write_bytes(b"partial write")
        raise OSError("write failed")

    monkeypatch.setattr(PackageManager, "save_as", broken_save)
    with Workbook.open(source) as wb, pytest.raises(OSError, match="write failed"):
        wb.save_as(output)
    assert output.read_bytes() == b"previous contents"


def test_packaging_plain_workbook_preserves_data_assets(tmp_path, minimal_twb):
    source = _copy_workbook(tmp_path, minimal_twb)
    data = tmp_path / "Data" / "nested" / "source.hyper"
    data.parent.mkdir(parents=True)
    data.write_bytes(b"extract bytes")
    output = tmp_path / "output.twbx"
    with Workbook.open(source) as wb:
        wb.save_as(output)
    with zipfile.ZipFile(output) as archive:
        assert archive.read("Data/nested/source.hyper") == b"extract bytes"


def test_package_can_be_prepared_again_after_close(tmp_path, minimal_twb):
    archive = tmp_path / "input.twbx"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(minimal_twb, "workbook.twb")
    manager = PackageManager(archive)
    first = manager.twb_path
    manager.close()
    assert not first.exists()
    try:
        assert manager.twb_path.exists()
    finally:
        manager.close()


def test_ambiguous_package_cleans_working_directory(tmp_path, minimal_twb):
    archive = tmp_path / "ambiguous.twbx"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(minimal_twb, "first.twb")
        zf.write(minimal_twb, "second.twb")
    manager = PackageManager(archive)
    with pytest.raises(AmbiguousWorkbookError):
        _ = manager.twb_path
    assert manager._working_dir is None


def test_empty_columns_container_receives_new_fields():
    node = etree.fromstring(b'<datasource name="empty"><columns/></datasource>')
    ds = Datasource(node)
    ds.add_calculated_field("Answer", "42")
    assert node.find("columns/column") is not None
    assert node.find("column") is None


def test_missing_pantab_preserves_existing_file_and_explains_install(tmp_path, monkeypatch):
    import pytableau.data.bridge as module

    pd = pytest.importorskip("pandas")
    path = tmp_path / "existing.hyper"
    path.write_bytes(b"existing extract")
    monkeypatch.setattr(module, "_pantab", _MissingDependency("pantab", "hyper"))
    with pytest.raises(ImportError, match=r"pip install pytableau\[hyper\]"):
        module.HyperBridge(path).from_dataframe(pd.DataFrame({"a": [1]}))
    assert path.read_bytes() == b"existing extract"


def test_source_build_patch_variants_report_correct_version(minimal_twb):
    with Workbook.open(minimal_twb) as wb:
        assert wb.version == "2022.4"


def test_from_spec_does_not_mutate_caller_dict_and_retains_zero_bounds():
    spec = {
        "datasources": [{"caption": "Data", "connection": {"class": "postgres", "cls": "hyper"}}],
        "worksheets": [
            {
                "name": "Chart",
                "rows": ["Value"],
                "filters": [{"field": "Value", "minimum": 0, "maximum": 0}],
            }
        ],
    }
    original = copy.deepcopy(spec)
    first = from_spec(spec)
    second = from_spec(spec)
    assert spec == original
    assert first.datasources[0].connections[0].class_ == "postgres"
    assert second.to_xml_string() == first.to_xml_string()
    filt = first.xml_root.find("worksheets/worksheet/filters/filter")
    assert filt is not None
    assert filt.get("min") == "0"
    assert filt.get("max") == "0"


def test_long_raw_spec_is_not_treated_as_filesystem_path():
    import json

    spec = {"datasources": [{"caption": "x" * 300}]}
    wb = from_spec(json.dumps(spec))
    assert wb.datasources[0].caption == "x" * 300


def test_fleet_and_compliance_include_packages_and_ignore_non_workbooks(tmp_path, minimal_twb):
    _copy_workbook(tmp_path, minimal_twb)
    _copy_workbook(tmp_path, minimal_twb, "wrong.twx")
    (tmp_path / "directory.twb").mkdir()
    archive = tmp_path / "nested" / "packaged.twbx"
    archive.parent.mkdir()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(minimal_twb, "workbook.twb")
    scanner = FleetScanner(tmp_path).scan()
    assert scanner.summary()["total"] == 2
    assert scanner.summary()["errors"] == 0
    results = ComplianceRunner(GovernanceRuleset.default()).run(tmp_path)
    assert len(results) == 2
    assert {Path(r.workbook).suffix for r in results} == {".twb", ".twbx"}


@pytest.mark.parametrize("dry_run", [True, False])
def test_version_only_migration_applies_and_preserves_source(tmp_path, minimal_twb, dry_run):
    source = _copy_workbook(tmp_path / "input", minimal_twb)
    original = source.read_bytes()
    output = tmp_path / "output"
    plan = (
        MigrationPlan()
        .source_directory(source.parent)
        .output_directory(output)
        .target_version("2024.1")
    )
    report = MigrationEngine(plan).execute(dry_run=dry_run)
    assert report.migrated == 1
    assert source.read_bytes() == original
    if dry_run:
        assert not output.exists()
    else:
        with Workbook.open(output / source.name) as migrated:
            assert migrated.version == "2024.1"


def test_migration_preserves_subdirectories_and_excludes_its_output(tmp_path, minimal_twb):
    source_dir = tmp_path / "input"
    _copy_workbook(source_dir / "one", minimal_twb, "same.twb")
    _copy_workbook(source_dir / "two", minimal_twb, "same.twb")
    output = source_dir / "migrated"
    plan = (
        MigrationPlan()
        .source_directory(source_dir)
        .output_directory(output)
        .rename_fields({"Region": "Territory"})
    )
    report = MigrationEngine(plan).execute()
    assert report.migrated == 2
    assert (output / "one" / "same.twb").exists()
    assert (output / "two" / "same.twb").exists()
    assert MigrationEngine(plan).execute(dry_run=True).total == 2


def test_migration_matches_full_server_names(tmp_path, minimal_twb):
    source = _copy_workbook(tmp_path, minimal_twb)
    with Workbook.open(source) as wb:
        wb.datasources[0].connections[0].server = "dev.example.com.backup"
        wb.save()
    plan = (
        MigrationPlan()
        .source_directory(tmp_path)
        .swap_connections({"dev.example.com": "prod.example.com"})
    )
    assert MigrationEngine(plan).execute(dry_run=True).skipped == 1


def test_migration_output_can_be_ancestor_of_source(tmp_path, minimal_twb):
    source = _copy_workbook(tmp_path / "input", minimal_twb)
    plan = (
        MigrationPlan()
        .source_directory(source.parent)
        .output_directory(tmp_path)
        .target_version("2024.1")
    )
    assert MigrationEngine(plan).execute(dry_run=True).migrated == 1


def test_migration_validation_runs_in_dry_run(tmp_path, minimal_twb, monkeypatch):
    _copy_workbook(tmp_path, minimal_twb)
    monkeypatch.setattr(Workbook, "validate", lambda self: [ValidationIssue("error", "blocked")])
    plan = (
        MigrationPlan()
        .source_directory(tmp_path)
        .rename_fields({"Region": "Territory"})
        .validate_all()
    )
    report = MigrationEngine(plan).execute(dry_run=True)
    assert report.errors == 1
    assert "blocked" in report.results[0].error


def test_built_workbook_packages_attached_extract(tmp_path):
    wb = from_spec({"datasources": [{"caption": "Data"}]})
    wb.save_as(tmp_path / "new.twb")
    extract = tmp_path / "input.hyper"
    extract.write_bytes(b"extract")
    wb.datasources[0].attach_extract(extract)
    output = tmp_path / "new.twbx"
    wb.save_as(output)
    with zipfile.ZipFile(output) as archive:
        assert archive.read("Data/input.hyper") == b"extract"
    wb.close()


def test_copy_rebinds_extract_paths_before_further_mutations(tmp_path, minimal_twb):
    source = _copy_workbook(tmp_path, minimal_twb)
    extract = tmp_path / "input.hyper"
    extract.write_bytes(b"original extract")
    with Workbook.open(source) as wb:
        ds = wb.datasources[0]
        ds.attach_extract(extract)
        wb.save()
        source_extract = ds._hyper_path
        output = tmp_path / "copy.twbx"
        wb.save_as(output)
        assert ds._hyper_path != source_extract
        ds._hyper_path.write_bytes(b"changed extract")
        wb.save()
    assert source_extract.read_bytes() == b"original extract"
    with zipfile.ZipFile(output) as archive:
        assert archive.read("Data/input.hyper") == b"changed extract"


@pytest.mark.parametrize(
    ("active", "other"),
    [("active.twb", "other.twb"), ("workbook.twb", "Other/workbook.twb")],
)
def test_save_retains_active_workbook_hint_and_extract_in_multi_twb_package(
    tmp_path, minimal_twb, active, other
):
    source = _copy_workbook(tmp_path / "input", minimal_twb, "active.twb")
    extract = tmp_path / "input.hyper"
    extract.write_bytes(b"extract")
    with Workbook.open(source) as wb:
        wb.datasources[0].attach_extract(extract)
        wb.save()
    package = tmp_path / "input.twbx"
    with zipfile.ZipFile(package, "w") as archive:
        archive.write(source, active)
        archive.write(minimal_twb, other)
        archive.write(source.parent / "Data/input.hyper", "Data/input.hyper")
    output = tmp_path / "output.twbx"
    with Workbook.open(package, twb_hint=active) as wb:
        wb.save_as(output)
        assert wb.datasources[0]._hyper_path.read_bytes() == b"extract"
        wb.datasources[0].connections[0].server = "second.example.com"
        wb.save()
    with Workbook.open(output, twb_hint=active) as wb:
        assert wb.datasources[0].connections[0].server == "second.example.com"
    with zipfile.ZipFile(output) as archive:
        assert archive.read(other) == minimal_twb.read_bytes()


def test_plain_copy_of_nested_package_preserves_relative_extract(tmp_path, minimal_twb):
    source = _copy_workbook(tmp_path / "input", minimal_twb)
    extract = tmp_path / "input.hyper"
    extract.write_bytes(b"extract")
    with Workbook.open(source) as wb:
        wb.datasources[0].attach_extract(extract)
        wb.save()
    package = tmp_path / "input.twbx"
    with zipfile.ZipFile(package, "w") as archive:
        archive.write(source, "Book/workbook.twb")
        archive.write(source.parent / "Data/input.hyper", "Book/Data/input.hyper")
    output = tmp_path / "output" / "copy.twb"
    with Workbook.open(package) as wb:
        wb.save_as(output)
        assert wb.datasources[0]._hyper_path.read_bytes() == b"extract"
    with Workbook.open(output) as wb:
        assert wb.datasources[0]._hyper_path.read_bytes() == b"extract"


def test_plain_copy_rejects_extract_outside_active_member_directory(tmp_path, minimal_twb):
    source = _copy_workbook(tmp_path / "input", minimal_twb)
    extract = tmp_path / "input.hyper"
    extract.write_bytes(b"extract")
    with Workbook.open(source) as wb:
        wb.datasources[0].attach_extract(extract)
        wb.save()
    package = tmp_path / "input.twbx"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(
            "Book/workbook.twb",
            source.read_bytes().replace(b"Data/input.hyper", b"../Data/input.hyper"),
        )
        archive.write(source.parent / "Data/input.hyper", "Data/input.hyper")
    output = tmp_path / "output.twb"
    output.write_bytes(b"previous contents")
    with Workbook.open(package) as wb:
        assert wb.datasources[0]._hyper_path.read_bytes() == b"extract"
        with pytest.raises(InvalidWorkbookError, match="save as TWBX"):
            wb.save_as(output)
        wb.save_as(tmp_path / "output.twbx")
        assert wb.datasources[0]._hyper_path.read_bytes() == b"extract"
    assert output.read_bytes() == b"previous contents"


def test_plain_migration_copies_extract_assets(tmp_path, minimal_twb):
    source = _copy_workbook(tmp_path / "input", minimal_twb)
    extract = tmp_path / "input.hyper"
    extract.write_bytes(b"extract")
    with Workbook.open(source) as wb:
        wb.datasources[0].attach_extract(extract)
        wb.save()
    output = tmp_path / "output"
    plan = (
        MigrationPlan()
        .source_directory(source.parent)
        .output_directory(output)
        .target_version("2024.1", allow_unverified=True)
    )
    report = MigrationEngine(plan).execute()
    assert report.migrated == 1
    with Workbook.open(output / source.name) as wb:
        assert wb.datasources[0]._hyper_path.read_bytes() == b"extract"


def test_server_mappings_do_not_cascade(tmp_path, minimal_twb):
    source = _copy_workbook(tmp_path / "input", minimal_twb)
    with Workbook.open(source) as wb:
        wb.datasources[0].connections[0].server = "dev.example.com"
        wb.save()
    output = tmp_path / "output"
    plan = (
        MigrationPlan()
        .source_directory(source.parent)
        .output_directory(output)
        .swap_connections(
            {"dev.example.com": "stage.example.com", "stage.example.com": "prod.example.com"}
        )
    )
    assert MigrationEngine(plan).execute().migrated == 1
    with Workbook.open(output / source.name) as wb:
        assert wb.datasources[0].connections[0].server == "stage.example.com"


def test_field_mappings_are_applied_once_to_original_captions(tmp_path, minimal_twb):
    source = _copy_workbook(tmp_path / "input", minimal_twb)
    output = tmp_path / "output"
    plan = (
        MigrationPlan()
        .source_directory(source.parent)
        .output_directory(output)
        .rename_fields({"Region": "Territory", "Territory": "Location"})
    )
    assert MigrationEngine(plan).execute().migrated == 1
    with Workbook.open(output / source.name) as wb:
        assert wb.datasources[0].get_field("Territory") is not None
        assert wb.datasources[0].get_field("Location") is None


def test_field_mapping_cycle_preserves_field_identity(tmp_path, minimal_twb):
    source = _copy_workbook(tmp_path / "input", minimal_twb)
    with Workbook.open(source) as wb:
        ds = wb.datasources[0]
        ds.add_calculated_field("Territory", "[Region]", datatype="string")
        old_region_name = ds.get_field("Region").name
        old_territory_name = ds.get_field("Territory").name
        wb.save()
    output = tmp_path / "output"
    plan = (
        MigrationPlan()
        .source_directory(source.parent)
        .output_directory(output)
        .rename_fields({"Region": "Territory", "Territory": "Region"})
    )
    assert MigrationEngine(plan).execute().migrated == 1
    with Workbook.open(output / source.name) as wb:
        ds = wb.datasources[0]
        assert ds.get_field("Territory").name == old_region_name
        assert ds.get_field("Region").name == old_territory_name
        assert ds.get_field("Region").formula == "[Territory]"


def test_migration_rename_keeps_datasource_formulas_and_sheets_separate(tmp_path):
    wb = from_spec(
        {
            "datasources": [
                {"caption": "First", "columns": [{"caption": "Region"}]},
                {"caption": "Second", "columns": [{"caption": "Territory"}]},
            ],
            "worksheets": [
                {"name": "First Sheet", "datasource": "First", "rows": ["Region"]},
                {"name": "Second Sheet", "datasource": "Second", "rows": ["Territory"]},
            ],
        }
    )
    wb.datasources[0].add_calculated_field("Calc", "[Region]", datatype="string")
    wb.datasources[1].add_calculated_field("Calc", "[Territory]", datatype="string")
    source = tmp_path / "input" / "workbook.twb"
    wb.save_as(source)
    wb.close()
    output = tmp_path / "output"
    plan = (
        MigrationPlan()
        .source_directory(source.parent)
        .output_directory(output)
        .rename_fields({"Region": "Territory", "Territory": "Location"})
        .validate_all()
    )
    assert MigrationEngine(plan).execute().migrated == 1
    with Workbook.open(output / source.name) as wb:
        assert wb.datasources[0].get_field("Calc").formula == "[Territory]"
        assert wb.datasources[1].get_field("Calc").formula == "[Location]"
        assert wb.worksheets["First Sheet"].rows[0].name == "Territory"
        assert wb.worksheets["Second Sheet"].rows[0].name == "Location"


def test_ambiguous_unbound_sheet_rename_fails_before_mutation():
    wb = from_spec(
        {
            "datasources": [
                {"caption": "First", "columns": [{"caption": "Region"}]},
                {"caption": "Second", "columns": [{"caption": "Region"}]},
            ],
            "worksheets": [{"name": "Ambiguous", "rows": ["Region"]}],
        }
    )
    with pytest.raises(InvalidWorkbookError, match="multiple datasources"):
        wb.datasources[0].rename_field("Region", "Territory")
    assert wb.datasources[0].get_field("Region") is not None
    assert wb.worksheets[0].rows[0].name == "Region"


@pytest.mark.parametrize("dry_run", [True, False])
def test_migration_rejects_output_symlinks_to_source(tmp_path, minimal_twb, dry_run):
    source = _copy_workbook(tmp_path / "input" / "nested", minimal_twb)
    original = source.read_bytes()
    output = tmp_path / "output"
    output.mkdir()
    (output / "nested").symlink_to(source.parent, target_is_directory=True)
    plan = (
        MigrationPlan()
        .source_directory(source.parent.parent)
        .output_directory(output)
        .target_version("2024.1")
    )
    report = MigrationEngine(plan).execute(dry_run=dry_run)
    assert report.errors == 1
    assert source.read_bytes() == original
