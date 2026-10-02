"""Explicit extract contracts and atomic, typed schema evolution."""

from __future__ import annotations

import datetime as dt
import math
import numbers
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from decimal import Decimal, localcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from pytableau.data.bridge import HyperBridge, _hyperapi, _pandas


@dataclass(frozen=True)
class TableIdentity:
    """Schema and table are separate identifiers, including names containing dots."""

    schema: str
    name: str

    def __post_init__(self) -> None:
        if not self.schema or not self.name:
            raise ValueError("Schema and table names must be nonempty")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ContractViolation:
    column: str | None
    rule: str
    message: str


class ExtractContractError(ValueError):
    def __init__(self, violations: list[ContractViolation]) -> None:
        self.violations = violations
        super().__init__("; ".join(f"{v.column or 'table'}: {v.message}" for v in violations))


@dataclass(frozen=True)
class ColumnContract:
    name: str
    datatype: str
    nullable: bool = True
    precision: int | None = None
    scale: int | None = None
    timezone: str | None = None

    def __post_init__(self) -> None:
        if not self.name or self.datatype not in {
            "string",
            "integer",
            "real",
            "boolean",
            "date",
            "datetime",
            "decimal",
        }:
            raise ValueError("Invalid contract column name or datatype")
        if self.datatype == "decimal":
            if (
                self.precision is None
                or self.scale is None
                or not 0 <= self.scale <= self.precision <= 38
                or self.precision < 1
            ):
                raise ValueError(
                    "Decimal requires 1 <= precision <= 38 and 0 <= scale <= precision"
                )
        elif self.precision is not None or self.scale is not None:
            raise ValueError("Precision and scale apply only to decimal columns")
        if self.timezone is not None and self.datatype != "datetime":
            raise ValueError("Timezone applies only to datetime columns")

    def sql_type(self, api: Any) -> Any:
        types = {
            "string": api.SqlType.text,
            "integer": api.SqlType.big_int,
            "real": api.SqlType.double,
            "boolean": api.SqlType.bool,
            "date": api.SqlType.date,
        }
        if self.datatype == "decimal":
            return api.SqlType.numeric(self.precision, self.scale)
        if self.datatype == "datetime":
            return api.SqlType.timestamp_tz() if self.timezone else api.SqlType.timestamp()
        return types[self.datatype]()

    def accepts(self, value: Any) -> bool:
        kind = self.datatype
        if kind == "string":
            return isinstance(value, str)
        if kind == "integer":
            return (
                isinstance(value, numbers.Integral)
                and not isinstance(value, bool)
                and -(2**63) <= int(value) < 2**63
            )
        if kind == "real":
            return (
                isinstance(value, numbers.Real)
                and not isinstance(value, bool)
                and math.isfinite(value)
            )
        if kind == "boolean":
            return isinstance(value, bool) or type(value).__name__ == "bool_"
        if kind == "date":
            return isinstance(value, dt.date) and not isinstance(value, dt.datetime)
        if kind == "datetime":
            if not isinstance(value, dt.datetime) or getattr(value, "nanosecond", 0) != 0:
                return False
            timezone = value.tzinfo if value.utcoffset() is not None else None
            return timezone is None if self.timezone is None else str(timezone) == self.timezone
        if not isinstance(value, Decimal) or not value.is_finite():
            return False
        assert self.scale is not None and self.precision is not None
        if value.is_zero():
            return True
        _, digits, exponent = value.as_tuple()
        # Decimal.normalize() rounds under the caller's active decimal context.
        # Remove insignificant trailing zeros without performing arithmetic.
        assert isinstance(exponent, int)
        while len(digits) > 1 and digits[-1] == 0:
            digits = digits[:-1]
            exponent += 1
        fractional = max(0, -int(exponent))
        integer = max(0, len(digits) + int(exponent))
        return fractional <= self.scale and integer <= self.precision - self.scale


@dataclass(frozen=True)
class ExtractContract:
    columns: tuple[ColumnContract, ...]
    table: TableIdentity = field(default_factory=lambda: TableIdentity("Extract", "Extract"))
    keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        names = [c.name for c in self.columns]
        if not names or len(names) != len(set(names)) or not set(self.keys) <= set(names):
            raise ValueError("Contract requires unique columns and valid key columns")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> ExtractContract:
        return cls(
            tuple(ColumnContract(**column) for column in spec["columns"]),
            TableIdentity(**spec.get("table", {"schema": "Extract", "name": "Extract"})),
            tuple(spec.get("keys", ())),
        )

    def validate(self, df: Any) -> list[ContractViolation]:
        pandas = HyperBridge._require(_pandas, "pandas")
        if not isinstance(df, pandas.DataFrame):
            raise TypeError("Contract validation requires a pandas DataFrame")
        violations = []
        names = {c.name for c in self.columns}
        if len(df.columns) != len(set(df.columns)):
            violations.append(ContractViolation(None, "columns", "Duplicate dataframe columns"))
            return violations
        for name in names - set(df.columns):
            violations.append(ContractViolation(name, "required", "Missing column"))
        for name in set(df.columns) - names:
            violations.append(ContractViolation(str(name), "extra", "Unexpected column"))
        for column in self.columns:
            if column.name not in df:
                continue
            series = df[column.name]
            if not column.nullable and series.isna().any():
                violations.append(
                    ContractViolation(column.name, "nullable", "Null value in required column")
                )
            for index, value in series.dropna().items():
                if not column.accepts(value):
                    violations.append(
                        ContractViolation(
                            column.name,
                            "datatype",
                            f"Value at row {index!r} violates {column.datatype} contract",
                        )
                    )
                    break
        if self.keys and set(self.keys) <= set(df.columns):
            if df[list(self.keys)].isna().any().any():
                violations.append(ContractViolation(None, "keys", "Key columns contain nulls"))
            if df.duplicated(subset=list(self.keys)).any():
                violations.append(ContractViolation(None, "keys", "Duplicate key values"))
        return violations

    def require(self, df: Any) -> None:
        violations = self.validate(df)
        if violations:
            raise ExtractContractError(violations)

    def write(
        self,
        path: str | Path,
        df: Any,
        *,
        policy: str = "strict",
        mode: str = "replace",
        backfill: dict[str, Any] | None = None,
        prepare_metadata: Callable[[list[dict[str, Any]]], Callable[[], None]] | None = None,
    ) -> None:
        """Write exact values independently of the caller's Decimal context.

        New databases use format 3 for decimals above precision 18. Existing
        databases are upgraded on the staged copy when that format is needed.
        """
        with localcontext() as context:
            context.prec = max(context.prec, 76)
            self._write(
                path,
                df,
                policy=policy,
                mode=mode,
                backfill=backfill,
                prepare_metadata=prepare_metadata,
            )

    def _write(
        self,
        path: str | Path,
        df: Any,
        *,
        policy: str = "strict",
        mode: str = "replace",
        backfill: dict[str, Any] | None = None,
        prepare_metadata: Callable[[list[dict[str, Any]]], Callable[[], None]] | None = None,
    ) -> None:
        """Stage data/schema and metadata before replacing the requested table.

        ``strict`` retains the existing schema; ``additive`` permits new columns
        with explicit backfills for old rows; ``replace`` permits schema replacement.
        Append validates keys across old and new data. Other tables are preserved.
        A metadata preparer must return a no-fail commit closure after validation.
        """
        if policy not in {"strict", "additive", "replace"} or mode not in {"replace", "append"}:
            raise ValueError("Invalid schema policy or write mode")
        self.require(df)
        api = HyperBridge._require(_hyperapi, "tableauhyperapi")
        pandas = HyperBridge._require(_pandas, "pandas")
        path = Path(path)
        target = api.TableName(self.table.schema, self.table.name)
        old_df: Any = None
        if path.exists():
            bridge = HyperBridge(path)
            with bridge._connection() as conn:
                if conn.catalog.has_table(target):
                    definition = conn.catalog.get_table_definition(target)
                    actual = {
                        c.name.unescaped: (str(c.type), c.nullability) for c in definition.columns
                    }
                    expected = {
                        c.name: (
                            str(c.sql_type(api)),
                            api.Nullability.NULLABLE
                            if c.nullable
                            else api.Nullability.NOT_NULLABLE,
                        )
                        for c in self.columns
                    }
                    if policy == "strict" and actual != expected:
                        raise ExtractContractError(
                            [
                                ContractViolation(
                                    None, "schema", "Existing schema differs from strict contract"
                                )
                            ]
                        )
                    if policy == "additive" and any(
                        expected.get(k) != v for k, v in actual.items()
                    ):
                        raise ExtractContractError(
                            [
                                ContractViolation(
                                    None,
                                    "schema",
                                    "Additive policy cannot drop or change existing columns",
                                )
                            ]
                        )
                    if mode == "append":
                        with conn.execute_query(f"SELECT * FROM {target}") as rows:
                            old_df = pandas.DataFrame(
                                [
                                    [
                                        v.to_datetime()
                                        if hasattr(v, "to_datetime")
                                        else v.to_date()
                                        if hasattr(v, "to_date")
                                        else v
                                        for v in row
                                    ]
                                    for row in rows
                                ],
                                columns=list(actual),
                                dtype=object,
                            )
                        from zoneinfo import ZoneInfo

                        for column in self.columns:
                            if column.timezone and column.name in old_df:
                                old_df[column.name] = old_df[column.name].map(
                                    lambda v, zone=column.timezone: (
                                        v.astimezone(ZoneInfo(zone)) if v is not None else None
                                    )
                                )
                        for column in self.columns:
                            if column.name not in old_df:
                                if not column.nullable and column.name not in (backfill or {}):
                                    raise ExtractContractError(
                                        [
                                            ContractViolation(
                                                column.name,
                                                "backfill",
                                                "Required addition needs a backfill",
                                            )
                                        ]
                                    )
                                old_df[column.name] = (backfill or {}).get(column.name)
        combined = pandas.concat([old_df, df], ignore_index=True) if old_df is not None else df
        self.require(combined)
        path.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="pytableau-contract-", dir=path.parent) as temporary:
            staged = Path(temporary) / "staged.hyper"
            if path.exists():
                shutil.copy2(path, staged)
            wide_decimal = any(
                c.datatype == "decimal" and c.precision is not None and c.precision > 18
                for c in self.columns
            )
            with api.HyperProcess(
                telemetry=api.Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
                parameters={"default_database_version": "3" if wide_decimal else "2"},
            ) as process:
                if staged.exists() and wide_decimal:
                    with api.Connection(process.endpoint, str(staged)) as existing:
                        database_version = int(
                            existing.execute_scalar_query(
                                "SELECT database_version FROM pg_catalog.hyper_database"
                            )
                        )
                    if database_version < 3:
                        upgraded = Path(temporary) / "upgraded.hyper"
                        with api.Connection(process.endpoint) as connection:
                            connection.execute_command(
                                f"CREATE DATABASE {api.Name(str(upgraded))} WITH VERSION 3 FROM {api.Name(str(staged))}"
                            )
                        upgraded.replace(staged)
                with api.Connection(
                    endpoint=process.endpoint,
                    database=str(staged),
                    create_mode=api.CreateMode.CREATE_IF_NOT_EXISTS,
                ) as conn:
                    conn.catalog.create_schema_if_not_exists(self.table.schema)
                    conn.execute_command(f"DROP TABLE IF EXISTS {target}")
                    definition = api.TableDefinition(
                        target,
                        [
                            api.TableDefinition.Column(
                                c.name,
                                c.sql_type(api),
                                api.Nullability.NULLABLE
                                if c.nullable
                                else api.Nullability.NOT_NULLABLE,
                            )
                            for c in self.columns
                        ],
                    )
                    conn.catalog.create_table(definition)
                    with api.Inserter(conn, definition) as inserter:
                        values = combined[[c.name for c in self.columns]]
                        for row in values.itertuples(index=False, name=None):
                            inserter.add_row(
                                [
                                    None
                                    if pandas.isna(v)
                                    else v.item()
                                    if hasattr(v, "item") and not isinstance(v, Decimal)
                                    else v
                                    for v in row
                                ]
                            )
                        inserter.execute()
            schema = [
                {
                    "name": c.name,
                    "type": str(c.sql_type(api)),
                    "datatype": c.datatype,
                    "nullable": c.nullable,
                    "table": self.table.to_dict(),
                }
                for c in self.columns
            ]
            commit = prepare_metadata(schema) if prepare_metadata else None
            # XML proposal is validated before installation; commit failure restores prior file bytes.
            previous = path.read_bytes() if path.exists() else None
            staged.replace(path)
            if commit:
                try:
                    commit()
                except BaseException:
                    if previous is None:
                        path.unlink(missing_ok=True)
                    else:
                        from pytableau.fleet.journal import _atomic

                        _atomic(path, previous)
                    raise
