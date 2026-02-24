"""v0.5.0 packaging and datasource tests — #62 #63 #64 #65."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from pytableau.exceptions import InvalidPathError
from pytableau.package.manager import PackageManager

# ---------------------------------------------------------------------------
# list_assets / glob / find / data_dir (#62)
# ---------------------------------------------------------------------------


def _make_twbx(tmp_path: Path, files: dict[str, bytes]) -> Path:
    """Helper: create a .twbx with the given member files."""
    archive = tmp_path / "test.twbx"
    twb = b'<?xml version="1.0"?><workbook source-build="20241.24.0320.0919" />'
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("workbook.twb", twb)
        for name, content in files.items():
            zf.writestr(name, content)
    return archive


def test_list_assets_excludes_twb(tmp_path: Path) -> None:
    archive = _make_twbx(
        tmp_path,
        {
            "Data/Extract.hyper": b"hyper",
            "Data/Notes.txt": b"notes",
        },
    )
    pm = PackageManager(archive)
    assets = pm.list_assets()
    assert all(not a.endswith(".twb") for a in assets)
    assert "Data/Extract.hyper" in assets
    assert "Data/Notes.txt" in assets


def test_list_assets_sorted(tmp_path: Path) -> None:
    archive = _make_twbx(
        tmp_path,
        {
            "z_last.csv": b"z",
            "a_first.csv": b"a",
        },
    )
    pm = PackageManager(archive)
    assets = pm.list_assets()
    assert assets == sorted(assets)


def test_list_assets_empty_for_twb(tmp_path: Path) -> None:
    twb = tmp_path / "workbook.twb"
    twb.write_text(
        '<?xml version="1.0"?><workbook source-build="20241.24.0320.0919" />', encoding="utf-8"
    )
    pm = PackageManager(twb)
    assert pm.list_assets() == []


def test_glob_pattern_match(tmp_path: Path) -> None:
    archive = _make_twbx(
        tmp_path,
        {
            "Data/sales.hyper": b"h",
            "Data/orders.hyper": b"h",
            "readme.txt": b"r",
        },
    )
    pm = PackageManager(archive)
    # fnmatch '*' matches '/' so *.hyper matches full paths like Data/sales.hyper
    hypers = pm.glob("*.hyper")
    assert len(hypers) == 2
    # More specific pattern also works
    hypers_data = pm.glob("Data/*.hyper")
    assert len(hypers_data) == 2
    # txt files not included
    txt = pm.glob("*.txt")
    assert len(txt) == 1


def test_find_case_insensitive(tmp_path: Path) -> None:
    archive = _make_twbx(tmp_path, {"Data/MyExtract.Hyper": b"h"})
    pm = PackageManager(archive)
    result = pm.find("myextract.hyper")
    assert result == "Data/MyExtract.Hyper"


def test_find_returns_none_for_missing(tmp_path: Path) -> None:
    archive = _make_twbx(tmp_path, {"readme.txt": b"r"})
    pm = PackageManager(archive)
    assert pm.find("nothere.hyper") is None


def test_data_dir_returns_parent_of_hyper(tmp_path: Path) -> None:
    archive = _make_twbx(tmp_path, {"Data/Datasources/sales.hyper": b"h"})
    pm = PackageManager(archive)
    assert pm.data_dir == "Data/Datasources"


def test_data_dir_returns_none_when_no_hyper(tmp_path: Path) -> None:
    archive = _make_twbx(tmp_path, {"readme.txt": b"r"})
    pm = PackageManager(archive)
    assert pm.data_dir is None


# ---------------------------------------------------------------------------
# Deterministic ZIP (#63)
# ---------------------------------------------------------------------------


def test_save_as_deterministic(tmp_path: Path) -> None:
    """Two saves of the same workbook produce byte-identical .twbx."""
    from pytableau.core.workbook import Workbook

    source = Path(__file__).parent / "fixtures" / "minimal_v2022_4.twb"
    wb = Workbook.open(source)

    out1 = tmp_path / "out1.twbx"
    out2 = tmp_path / "out2.twbx"
    wb.save_as(out1, scrub_credentials=False)
    wb.save_as(out2, scrub_credentials=False)

    assert out1.read_bytes() == out2.read_bytes()


# ---------------------------------------------------------------------------
# resolve() path traversal guard (#64)
# ---------------------------------------------------------------------------


def test_resolve_clean_path(tmp_path: Path) -> None:
    twb = tmp_path / "wb.twb"
    twb.write_text(
        '<?xml version="1.0"?><workbook source-build="20241.24.0320.0919" />', encoding="utf-8"
    )
    pm = PackageManager(twb)
    assert pm.resolve("Data/sales.hyper") == "Data/sales.hyper"
    assert pm.resolve("/Data/sales.hyper") == "Data/sales.hyper"


def test_resolve_rejects_parent_traversal(tmp_path: Path) -> None:
    twb = tmp_path / "wb.twb"
    twb.write_text(
        '<?xml version="1.0"?><workbook source-build="20241.24.0320.0919" />', encoding="utf-8"
    )
    pm = PackageManager(twb)
    with pytest.raises(InvalidPathError):
        pm.resolve("../etc/passwd")


def test_resolve_rejects_windows_drive(tmp_path: Path) -> None:
    twb = tmp_path / "wb.twb"
    twb.write_text(
        '<?xml version="1.0"?><workbook source-build="20241.24.0320.0919" />', encoding="utf-8"
    )
    pm = PackageManager(twb)
    with pytest.raises(InvalidPathError):
        pm.resolve("C:/Users/secret.txt")


# ---------------------------------------------------------------------------
# Datasource.open / save_as (.tds / .tdsx) (#65)
# ---------------------------------------------------------------------------


def _make_tds(tmp_path: Path, name: str = "Sales") -> Path:
    path = tmp_path / "Sales.tds"
    path.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<datasource name="{name}" caption="{name}">'
        f'<connection class="sqlserver" server="dev.example.com" dbname="sales" />'
        f"<columns>"
        f'<column name="[Revenue]" caption="Revenue" datatype="real" role="measure" type="quantitative" />'
        f"</columns>"
        f"</datasource>",
        encoding="utf-8",
    )
    return path


def test_datasource_open_tds(tmp_path: Path) -> None:
    from pytableau.core.datasource import Datasource

    tds = _make_tds(tmp_path)
    ds = Datasource.open(tds)
    assert ds.name == "Sales"
    assert any(f.caption == "Revenue" for f in ds.all_fields)


def test_datasource_save_as_tds(tmp_path: Path) -> None:
    from pytableau.core.datasource import Datasource

    tds = _make_tds(tmp_path)
    ds = Datasource.open(tds)
    out = tmp_path / "Sales_copy.tds"
    ds.save_as(out)
    assert out.exists()
    ds2 = Datasource.open(out)
    assert ds2.name == ds.name


def test_datasource_open_tdsx(tmp_path: Path) -> None:
    from pytableau.core.datasource import Datasource

    tds_content = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<datasource name="Orders" caption="Orders">'
        b'<connection class="postgres" server="db.example.com" dbname="orders" />'
        b"</datasource>"
    )
    tdsx = tmp_path / "Orders.tdsx"
    with zipfile.ZipFile(tdsx, "w") as zf:
        zf.writestr("Orders.tds", tds_content)
    ds = Datasource.open(tdsx)
    assert ds.name == "Orders"


def test_datasource_save_as_tdsx(tmp_path: Path) -> None:
    from pytableau.core.datasource import Datasource

    tds = _make_tds(tmp_path)
    ds = Datasource.open(tds)
    out = tmp_path / "Sales.tdsx"
    ds.save_as(out)
    assert out.exists()
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert any(n.endswith(".tds") for n in names)
