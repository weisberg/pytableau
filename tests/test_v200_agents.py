"""M2 Agent Ergonomics — 22 tests covering agents/discovery, agents/transactions,
agents/receipts, and enhanced exceptions with suggestion field."""

from __future__ import annotations

import pytest

from pytableau import Workbook
from pytableau.agents.receipts import OperationReceipt
from pytableau.agents.transactions import WorkbookTransaction
from pytableau.exceptions import (
    DuplicateFieldError,
    FieldNotFoundError,
    PyTableauError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_TWB = "tests/fixtures/minimal_v2022_4.twb"
DS_NAME = "sqlserver.sales"


@pytest.fixture
def wb():
    return Workbook.open(MINIMAL_TWB)


@pytest.fixture
def ds(wb):
    return wb.datasources[DS_NAME]


# ---------------------------------------------------------------------------
# 1. OperationReceipt — receipts.py
# ---------------------------------------------------------------------------


class TestOperationReceipt:
    def test_ok_status_created(self):
        r = OperationReceipt(status="created", field_name="Revenue")
        assert r.ok is True

    def test_ok_status_updated(self):
        r = OperationReceipt(status="updated", field_name="Revenue")
        assert r.ok is True

    def test_ok_status_removed(self):
        r = OperationReceipt(status="removed")
        assert r.ok is True

    def test_not_ok_already_exists(self):
        r = OperationReceipt(status="already_exists", field_name="Revenue")
        assert r.ok is False

    def test_not_ok_skipped(self):
        r = OperationReceipt(status="skipped")
        assert r.ok is False

    def test_str_includes_status(self):
        r = OperationReceipt(status="created", field_name="Profit")
        s = str(r)
        assert "[created]" in s
        assert "Profit" in s

    def test_str_includes_suggestion(self):
        r = OperationReceipt(status="skipped", suggestion="Did you mean 'Revenue'?")
        assert "Revenue" in str(r)

    def test_str_includes_datasource(self):
        r = OperationReceipt(status="created", datasource="Sales")
        assert "Sales" in str(r)

    def test_default_suggestion_is_none(self):
        r = OperationReceipt(status="created")
        assert r.suggestion is None


# ---------------------------------------------------------------------------
# 2. PyTableauError.suggestion — exceptions.py
# ---------------------------------------------------------------------------


class TestEnhancedExceptions:
    def test_base_exception_has_suggestion_default(self):
        err = PyTableauError("something went wrong")
        assert err.suggestion == ""

    def test_base_exception_accepts_suggestion_kwarg(self):
        err = PyTableauError("something went wrong", suggestion="Try this instead.")
        assert err.suggestion == "Try this instead."

    def test_field_not_found_inherits_suggestion(self):
        err = FieldNotFoundError("no such field", suggestion="Did you mean 'Region'?")
        assert "Region" in err.suggestion

    def test_duplicate_field_error_has_suggestion_default(self):
        err = DuplicateFieldError("already exists")
        assert err.suggestion == ""


# ---------------------------------------------------------------------------
# 3. Datasource.available_fields — discovery.py
# ---------------------------------------------------------------------------


class TestAvailableFields:
    def test_returns_list(self, ds):
        result = ds.available_fields()
        assert isinstance(result, list)

    def test_each_entry_has_required_keys(self, ds):
        for entry in ds.available_fields():
            assert "name" in entry
            assert "caption" in entry
            assert "datatype" in entry
            assert "is_calculated" in entry

    def test_calculated_field_has_formula(self, wb, ds):
        ds.add_calculated_field("CalcTest", "[Region]")
        fields = ds.available_fields()
        calc = next(f for f in fields if f["caption"] == "CalcTest")
        assert calc["is_calculated"] is True
        assert "formula" in calc

    def test_regular_field_has_no_formula(self, ds):
        regular = next(f for f in ds.available_fields() if not f["is_calculated"])
        assert "formula" not in regular

    def test_suggestion_on_field_not_found(self, ds):
        with pytest.raises(FieldNotFoundError) as exc_info:
            ds.rename_field("NonExistentField", "New")
        assert exc_info.value.suggestion != ""


# ---------------------------------------------------------------------------
# 4. Workbook.describe — discovery.py
# ---------------------------------------------------------------------------


class TestWorkbookDescribe:
    def test_returns_dict_with_required_keys(self, wb):
        schema = wb.describe()
        assert "version" in schema
        assert "datasources" in schema
        assert "worksheets" in schema
        assert "dashboards" in schema
        assert "parameters" in schema

    def test_datasources_list_non_empty(self, wb):
        schema = wb.describe()
        assert len(schema["datasources"]) >= 1

    def test_datasource_entry_has_fields(self, wb):
        ds_entry = wb.describe()["datasources"][0]
        assert "name" in ds_entry
        assert "fields" in ds_entry
        assert isinstance(ds_entry["fields"], list)

    def test_worksheets_listed(self, wb):
        schema = wb.describe()
        assert len(schema["worksheets"]) >= 1
        assert "name" in schema["worksheets"][0]

    def test_is_json_serialisable(self, wb):
        import json

        schema = wb.describe()
        serialised = json.dumps(schema)  # must not raise
        assert len(serialised) > 0


# ---------------------------------------------------------------------------
# 5. Workbook.capabilities — discovery.py
# ---------------------------------------------------------------------------


class TestWorkbookCapabilities:
    def test_returns_dict_with_required_keys(self, wb):
        caps = wb.capabilities()
        assert "has_extract" in caps
        assert "datasource_count" in caps
        assert "worksheet_count" in caps
        assert "dashboard_count" in caps
        assert "parameter_count" in caps
        assert "extras" in caps

    def test_extras_contains_expected_keys(self, wb):
        extras = wb.capabilities()["extras"]
        for key in ("hyper", "pandas", "server", "governance"):
            assert key in extras
            assert isinstance(extras[key], bool)

    def test_datasource_count_correct(self, wb):
        caps = wb.capabilities()
        non_param = sum(1 for ds in wb.datasources if not ds.is_parameters)
        assert caps["datasource_count"] == non_param


# ---------------------------------------------------------------------------
# 6. WorkbookTransaction — transactions.py
# ---------------------------------------------------------------------------


class TestWorkbookTransaction:
    def test_transaction_is_context_manager(self, wb):
        with wb.transaction() as tx:
            assert isinstance(tx, WorkbookTransaction)

    def test_successful_mutation_is_retained(self, wb):
        before = len(wb.datasources[DS_NAME].available_fields())
        with wb.transaction() as tx:
            tx.add_calculated_field(DS_NAME, "TxField", "[Region]")
        after = len(wb.datasources[DS_NAME].available_fields())
        assert after == before + 1

    def test_rollback_on_exception(self, wb):
        before = len(wb.datasources[DS_NAME].available_fields())
        try:
            with wb.transaction() as tx:
                tx.add_calculated_field(DS_NAME, "RollbackField", "[Region]")
                raise RuntimeError("deliberate failure")
        except RuntimeError:
            pass
        after = len(wb.datasources[DS_NAME].available_fields())
        assert after == before  # restored to pre-transaction state

    def test_rollback_does_not_suppress_exception(self, wb):
        with pytest.raises(RuntimeError, match="deliberate"), wb.transaction():
            raise RuntimeError("deliberate")

    def test_rename_field_via_transaction(self, wb, ds):
        ds.add_calculated_field("TxRename", "[Region]")
        with wb.transaction() as tx:
            tx.rename_field(DS_NAME, "TxRename", "TxRenamed")
        names = [f["caption"] for f in wb.datasources[DS_NAME].available_fields()]
        assert "TxRenamed" in names
        assert "TxRename" not in names

    def test_remove_field_via_transaction(self, wb, ds):
        ds.add_calculated_field("TxRemove", "[Region]")
        before = len(wb.datasources[DS_NAME].available_fields())
        with wb.transaction() as tx:
            tx.remove_field(DS_NAME, "TxRemove")
        after = len(wb.datasources[DS_NAME].available_fields())
        assert after == before - 1

    def test_transaction_method_returns_transaction(self, wb):
        tx = wb.transaction()
        assert isinstance(tx, WorkbookTransaction)
