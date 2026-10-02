"""Real Hyper contract integration: precise values, schema identity and rollback."""

import datetime as dt
from decimal import Decimal

import pytest

from pytableau.build import from_spec
from pytableau.data import (
    ColumnContract,
    ExtractContract,
    ExtractContractError,
    HyperBridge,
    TableIdentity,
)

pd = pytest.importorskip("pandas")
pytest.importorskip("tableauhyperapi")
pytestmark = pytest.mark.requires_hyper


def contract(*extra, table=None):
    return ExtractContract(
        (
            ColumnContract("id", "integer", False),
            ColumnContract("amount", "decimal", False, 12, 2),
            *extra,
        ),
        table or TableIdentity("Extract", "Orders"),
        ("id",),
    )


def frame(ids=(1, 2)):
    return pd.DataFrame(
        {"id": pd.Series(ids, dtype="Int64"), "amount": [Decimal("12.34") for _ in ids]}
    )


def test_real_typed_contract_preserves_decimal_and_qualified_tables(tmp_path):
    path = tmp_path / "typed.hyper"
    c = contract()
    c.write(path, frame())
    other = contract(table=TableIdentity("public", "Orders"))
    other.write(path, frame((9,)))
    bridge = HyperBridge(path)
    assert set(bridge.table_identities()) == {c.table, other.table}
    assert bridge.row_count(c.table) == 2
    assert bridge.row_count(other.table) == 1
    assert bridge.schema(c.table)[1]["type"].lower() == "numeric(12, 2)"
    with bridge._connection() as conn:
        assert conn.execute_scalar_query(
            'SELECT "amount" FROM "Extract"."Orders" LIMIT 1'
        ) == Decimal("12.34")
    c.write(path, frame((3,)))
    assert bridge.row_count(other.table) == 1
    assert bridge.row_count(c.table) == 1


def test_contract_rejects_null_type_precision_and_duplicate_keys_before_write(tmp_path):
    path = tmp_path / "data.hyper"
    c = contract()
    c.write(path, frame())
    original = path.read_bytes()
    invalid = [
        frame((1, 1)),
        pd.DataFrame({"id": [None], "amount": [Decimal("1.00")]}),
        pd.DataFrame({"id": [3], "amount": [Decimal("1.234")]}),
        pd.DataFrame({"id": ["3"], "amount": [Decimal("1.00")]}),
        pd.DataFrame({"id": [3], "amount": [Decimal("12345678901.00")]}),
    ]
    for df in invalid:
        with pytest.raises(ExtractContractError):
            c.write(path, df)
        assert path.read_bytes() == original


def test_append_checks_combined_keys_and_additive_backfill(tmp_path):
    path = tmp_path / "data.hyper"
    c = contract()
    c.write(path, frame())
    with pytest.raises(ExtractContractError, match="Duplicate"):
        c.write(path, frame((1,)), mode="append")
    evolved = contract(ColumnContract("status", "string", False))
    new = frame((3,))
    new["status"] = "new"
    original = path.read_bytes()
    with pytest.raises(ExtractContractError, match="strict"):
        evolved.write(path, new)
    with pytest.raises(ExtractContractError, match="backfill"):
        evolved.write(path, new, policy="additive", mode="append")
    assert path.read_bytes() == original
    evolved.write(path, new, policy="additive", mode="append", backfill={"status": "old"})
    bridge = HyperBridge(path)
    assert bridge.row_count(c.table) == 3
    assert bridge.query('SELECT "status" FROM "Extract"."Orders" ORDER BY "id"')[
        "status"
    ].tolist() == ["old", "old", "new"]
    changed = ExtractContract(
        (
            ColumnContract("id", "string", False),
            ColumnContract("amount", "decimal", False, 12, 2),
            ColumnContract("status", "string", False),
        ),
        c.table,
    )
    with pytest.raises(ExtractContractError, match="Additive"):
        changed.write(
            path,
            pd.DataFrame({"id": ["x"], "amount": [Decimal("1.00")], "status": ["x"]}),
            policy="additive",
        )


def test_nullable_dates_timezone_and_empty_schema(tmp_path):
    c = ExtractContract(
        (
            ColumnContract("id", "integer"),
            ColumnContract("day", "date"),
            ColumnContract("at", "datetime", timezone="UTC"),
        )
    )
    path = tmp_path / "dates.hyper"
    df = pd.DataFrame(
        {
            "id": pd.Series([1, None], dtype="Int64"),
            "day": [dt.date(2026, 1, 1), None],
            "at": [dt.datetime(2026, 1, 1, tzinfo=dt.UTC), None],
        }
    )
    c.write(path, df)
    assert HyperBridge(path).row_count(c.table) == 2
    c.write(path, df.iloc[:0])
    assert HyperBridge(path).row_count(c.table) == 0
    df["at"] = [dt.datetime(2026, 1, 1), None]
    with pytest.raises(ExtractContractError):
        c.write(path, df)


def test_metadata_preparation_and_commit_failure_restore_extract(tmp_path):
    path = tmp_path / "data.hyper"
    c = contract()
    c.write(path, frame())
    original = path.read_bytes()

    def bad_preparer(schema):
        raise RuntimeError("Invalid proposed XML")

    with pytest.raises(RuntimeError):
        c.write(path, frame((3,)), prepare_metadata=bad_preparer)
    assert path.read_bytes() == original

    def preparer(schema):
        def fail_commit():
            raise RuntimeError("Commit failure")

        return fail_commit

    with pytest.raises(RuntimeError):
        c.write(path, frame((3,)), prepare_metadata=preparer)
    assert path.read_bytes() == original


def test_datasource_contract_write_syncs_xml_before_save(tmp_path):
    wb = from_spec({"datasources": [{"caption": "Data", "connection": {"class": "hyper"}}]})
    wb.save_as(tmp_path / "data.twb")
    ds = wb.datasources[0]
    ds.write_extract(frame(), contract())
    assert {r.local_name for r in ds.metadata_records} == {"[id]", "[amount]"}
    assert {r.parent_name for r in ds.metadata_records} == {"[Extract].[Orders]"}
    assert ds._hyper_path.is_file()
    assert not [i for i in wb.validate() if i.level == "error"]
    wb.save_as(tmp_path / "data.twbx")


def test_nullable_integer_and_named_timezone_can_append(tmp_path):
    from zoneinfo import ZoneInfo

    c = ExtractContract(
        (
            ColumnContract("id", "integer"),
            ColumnContract("at", "datetime", timezone="America/New_York"),
        )
    )
    path = tmp_path / "nullable.hyper"
    zone = ZoneInfo("America/New_York")
    df = pd.DataFrame(
        {
            "id": pd.Series([1, None], dtype="Int64"),
            "at": [dt.datetime(2026, 1, 1, tzinfo=zone), None],
        }
    )
    c.write(path, df)
    c.write(
        path,
        pd.DataFrame(
            {"id": pd.Series([2], dtype="Int64"), "at": [dt.datetime(2026, 2, 1, tzinfo=zone)]}
        ),
        mode="append",
    )
    assert HyperBridge(path).row_count(c.table) == 3


def test_decimal_zero_and_trailing_zero_representability(tmp_path):
    zero = ColumnContract("v", "decimal", precision=2, scale=2)
    assert zero.accepts(Decimal("0"))
    column = ColumnContract("v", "decimal", precision=4, scale=2)
    assert column.accepts(Decimal("1.2300"))
    c = ExtractContract((column,))
    c.write(tmp_path / "decimal.hyper", pd.DataFrame({"v": [Decimal("1.2300")]}))


def test_transaction_hyper_writes_are_isolated_until_save(tmp_path):
    from pytableau import Workbook

    wb = from_spec({"datasources": [{"caption": "Data", "connection": {"class": "hyper"}}]})
    wb.save_as(tmp_path / "w.twb")
    ds = wb.datasources[0]
    ds.write_extract(frame(), contract())
    wb.save()
    path = ds._hyper_path
    original = path.read_bytes()
    cached_bridge = ds.hyper
    with pytest.raises(RuntimeError), wb.transaction():
        cached_bridge.execute('UPDATE "Extract"."Orders" SET "amount"=88')
        # The handle obtained before entering the transaction is rebound too.
        ds.hyper.execute('UPDATE "Extract"."Orders" SET "amount"=99')
        raise RuntimeError("rollback")
    assert path.read_bytes() == original
    with wb.transaction():
        cached_bridge.execute('UPDATE "Extract"."Orders" SET "amount"=99')
    assert path.read_bytes() == original
    wb.save()
    with Workbook.open(tmp_path / "w.twb") as saved:
        assert saved.datasources[0].hyper.query('SELECT "amount" FROM "Extract"."Orders"')[
            "amount"
        ].iloc[0] == Decimal("99.00")


def test_contract_preserves_nested_package_extract_path(tmp_path):
    import zipfile

    from pytableau import Workbook

    c = contract()
    hyper = tmp_path / "nested.hyper"
    c.write(hyper, frame())
    wb = from_spec(
        {
            "datasources": [
                {
                    "caption": "Data",
                    "connection": {
                        "class": "hyper",
                        "filename": "Data/nested/t.hyper",
                        "dbname": "Data/nested/t.hyper",
                    },
                }
            ]
        }
    )
    package = tmp_path / "nested.twbx"
    with zipfile.ZipFile(package, "w") as z:
        z.writestr("main.twb", wb.to_xml_string())
        z.writestr("Data/nested/t.hyper", hyper.read_bytes())
    with Workbook.open(package) as actual:
        ds = actual.datasources[0]
        ds.write_extract(frame((3,)), c)
        assert ds.connections[0].xml_node.get("filename") == "Data/nested/t.hyper"
        assert not [i for i in actual.validate() if i.level == "error"]
        actual.save_as(tmp_path / "saved.twbx")
    with Workbook.open(tmp_path / "saved.twbx") as saved:
        assert saved.datasources[0]._hyper_path.is_file()
        assert saved.datasources[0].hyper.row_count(c.table) == 1


def test_external_extract_transaction_rejects_uncaptured_writes(tmp_path):
    from pytableau import Workbook
    from pytableau.exceptions import InvalidPathError

    hyper = tmp_path / "external.hyper"
    contract().write(hyper, frame())
    source = tmp_path / "source"
    source.mkdir()
    wb = from_spec(
        {
            "datasources": [
                {
                    "caption": "Data",
                    "connection": {"class": "hyper", "filename": str(hyper), "dbname": str(hyper)},
                }
            ]
        }
    )
    wb.save_as(source / "w.twb")
    with (
        Workbook.open(source / "w.twb") as opened,
        pytest.raises(InvalidPathError, match="outside"),
        opened.transaction(),
    ):
        pass


def test_decimal_validation_does_not_round_under_callers_context(tmp_path):
    from decimal import localcontext

    column = ColumnContract("v", "decimal", precision=38, scale=0)
    value = Decimal("12345678901234567890123456789012345678")
    fractional = Decimal("1234567890123456789012345678.000000001")
    with localcontext() as context:
        context.prec = 8
        assert column.accepts(value)
        assert not column.accepts(fractional)
        c = ExtractContract((column,))
        path = tmp_path / "exact.hyper"
        contract().write(path, frame())
        c.write(path, pd.DataFrame({"v": [value]}))
    with HyperBridge(path)._connection() as conn:
        assert conn.execute_scalar_query('SELECT "v" FROM "Extract"."Extract"') == value
        assert conn.execute_scalar_query('SELECT COUNT(*) FROM "Extract"."Orders"') == 2
        assert (
            int(conn.execute_scalar_query("SELECT database_version FROM pg_catalog.hyper_database"))
            == 3
        )


def test_schema_replacement_drops_xml_fields_and_rejects_dependent_calcs(tmp_path):
    from pytableau.exceptions import SchemaValidationError

    wb = from_spec(
        {
            "datasources": [
                {
                    "caption": "Data",
                    "columns": [
                        {"caption": "id", "datatype": "integer"},
                        {"caption": "amount", "datatype": "real", "role": "measure"},
                    ],
                }
            ]
        }
    )
    wb.save_as(tmp_path / "w.twb")
    ds = wb.datasources[0]
    ds.write_extract(frame(), contract())
    ds.add_calculated_field("Double", "[amount]*2")
    prior = ds._hyper_path.read_bytes()
    smaller = ExtractContract((ColumnContract("id", "integer", False),), contract().table)
    with pytest.raises(SchemaValidationError, match="amount"):
        ds.write_extract(frame()[["id"]], smaller, policy="replace")
    assert ds._hyper_path.read_bytes() == prior
    ds.remove_field("Double")
    ds.write_extract(frame()[["id"]], smaller, policy="replace")
    assert ds.get_field("amount") is None
    assert not [i for i in wb.validate() if i.level == "error"]


@pytest.mark.parametrize("timezone", [None, "UTC"])
def test_exact_datetime_rejects_submicrosecond_values(tmp_path, timezone):
    c = ExtractContract((ColumnContract("at", "datetime", False, timezone=timezone),))
    path = tmp_path / "time.hyper"
    c.write(path, pd.DataFrame({"at": [pd.Timestamp("2026-01-01", tz=timezone)]}))
    before = path.read_bytes()
    invalid = pd.DataFrame({"at": [pd.Timestamp("2026-01-01 12:34:56.123456789", tz=timezone)]})
    with pytest.raises(ExtractContractError, match="datetime"):
        c.write(path, invalid)
    assert path.read_bytes() == before


def test_native_contract_write_preserves_live_model_and_updates_extract(tmp_path):
    import copy

    from lxml import etree

    from pytableau import Workbook
    from pytableau.build import DatasourceBuilder, LogicalTable, RelationBuilder

    wb = Workbook.new()
    node = (
        DatasourceBuilder("Native")
        .connection("sqlserver", server="live")
        .column("id", "integer")
        .logical_model(
            [LogicalTable("orders", "Orders", RelationBuilder.table("[Orders]", alias="Orders"))],
            [],
        )
        .build()
    )
    wb.xml_root.find("datasources").append(node)
    extract = etree.SubElement(node, "extract")
    connection = etree.SubElement(
        extract,
        "connection",
        attrib={"class": "hyper", "filename": "Data/shared.hyper", "dbname": "Data/shared.hyper"},
    )
    etree.SubElement(
        connection, "relation", type="table", table="[Extract].[Orders]", name="Orders"
    )
    c = ExtractContract(
        (ColumnContract("id", "integer", False),), TableIdentity("Extract", "Orders")
    )
    hyper = tmp_path / "Data/shared.hyper"
    c.write(hyper, pd.DataFrame({"id": [1]}))
    path = tmp_path / "native.twb"
    path.write_text(wb.to_xml_string())
    with Workbook.open(path) as actual:
        ds = actual.datasources[0]
        live = etree.tostring(copy.deepcopy(ds.xml_node.find("connection")))
        graph = etree.tostring(copy.deepcopy(ds.xml_node.find("object-graph")))
        ds.write_extract(pd.DataFrame({"id": [2]}), c)
        assert etree.tostring(ds.xml_node.find("connection")) == live
        assert etree.tostring(ds.xml_node.find("object-graph")) == graph
        assert ds.xml_node.find("extract/connection").get("class") == "hyper"
        assert ds.hyper.row_count(c.table) == 1
        assert not [i for i in actual.validate() if i.level == "error"]
