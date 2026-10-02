"""HyperBridge: unified pantab + tableauhyperapi wrapper."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from pytableau._compat import _MissingDependency, import_optional
from pytableau.exceptions import HyperError

_pantab = import_optional("pantab", "hyper")
_hyperapi = import_optional("tableauhyperapi", "hyper")
_pandas = import_optional("pandas", "pandas")


class HyperBridge:
    """Thin wrapper around .hyper I/O helpers."""

    def __init__(
        self,
        path: str | Path,
        *,
        on_write: Callable[[Any, str], None] | None = None,
    ) -> None:
        self.path = Path(path)
        self._on_write = on_write

    @staticmethod
    def _require(module: Any, feature: str) -> Any:
        if isinstance(module, _MissingDependency):
            raise ImportError(str(module))
        return module

    @staticmethod
    def _as_callable(module: Any, name: str) -> Callable[..., Any]:
        target = getattr(module, name, None)
        if target is None:
            raise HyperError(f"Missing function '{name}' in optional dependency for hyper support.")
        return target

    def from_dataframe(self, df: Any, table: str = "Extract", mode: str = "replace") -> None:
        if mode not in {"replace", "append"}:
            raise ValueError("mode must be 'replace' or 'append'")

        pandas_module = self._require(_pandas, "pandas")
        if not isinstance(df, pandas_module.DataFrame):
            raise TypeError("from_dataframe() expects a pandas DataFrame.")

        pantab = self._require(_pantab, "pantab")
        writer = self._as_callable(pantab, "frame_to_hyper")
        if self.path.parent:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "replace" and self.path.exists():
            # pantab's write mode replaces the entire database. Replace just the
            # requested table in a copy, then install it after a successful write.
            hyperapi = self._require(_hyperapi, "tableauhyperapi")
            with TemporaryDirectory(prefix="pytableau-write-", dir=self.path.parent) as temp_dir:
                staged = Path(temp_dir) / "staged.hyper"
                shutil.copy2(self.path, staged)
                HyperBridge(staged).execute(f"DROP TABLE IF EXISTS {hyperapi.TableName(table)}")
                writer(df, str(staged), table=table, table_mode="a")
                staged.replace(self.path)
        else:
            writer(df, str(self.path), table=table, table_mode="w" if mode == "replace" else "a")

        if self._on_write is not None:
            self._on_write(df, table)

    def to_dataframe(self, table: str = "Extract"):
        self._require(_pandas, "pandas")
        pantab = self._require(_pantab, "pantab")
        reader = self._as_callable(pantab, "frame_from_hyper")
        output = reader(str(self.path), table=table)
        if isinstance(output, list):
            pandas_module = self._require(_pandas, "pandas")
            return pandas_module.DataFrame(output)
        return output

    def append_dataframe(self, df: Any, table: str = "Extract") -> None:
        self.from_dataframe(df, table=table, mode="append")

    def execute(self, sql: str) -> int | None:
        with self._connection() as connection:
            return connection.execute_command(sql)

    def query(self, sql: str):
        self._require(_pandas, "pandas")
        with self._connection() as connection, connection.execute_query(sql) as result:
            rows = list(result)
            columns = [column.name.unescaped for column in result.schema.columns]
        return self._rows_to_dataframe(rows, columns)

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        hyperapi = self._require(_hyperapi, "tableauhyperapi")
        with (
            hyperapi.HyperProcess(
                telemetry=hyperapi.Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU
            ) as process,
            hyperapi.Connection(
                endpoint=process.endpoint,
                database=str(self.path),
                create_mode=hyperapi.CreateMode.NONE,
            ) as connection,
        ):
            yield connection

    def _rows_to_dataframe(self, rows: list[tuple[Any, ...]], columns: list[str]):
        pandas_module = self._require(_pandas, "pandas")
        if not rows and columns:
            return pandas_module.DataFrame(columns=columns)
        return pandas_module.DataFrame.from_records(rows, columns=columns if columns else None)

    def tables(self) -> list[str]:
        with self._connection() as connection:
            return [
                table.name.unescaped
                for schema in connection.catalog.get_schema_names()
                for table in connection.catalog.get_table_names(schema)
            ]

    def schema(self, table: str) -> list[dict[str, str]]:
        hyperapi = self._require(_hyperapi, "tableauhyperapi")
        with self._connection() as connection:
            definition = connection.catalog.get_table_definition(hyperapi.TableName(table))
            return [
                {"name": column.name.unescaped, "type": str(column.type)}
                for column in definition.columns
            ]

    def row_count(self, table: str) -> int:
        hyperapi = self._require(_hyperapi, "tableauhyperapi")
        rows = self.query(f"SELECT COUNT(*) AS __count FROM {hyperapi.TableName(table)}")
        if len(rows) == 0:
            return 0
        return int(rows.iloc[0, 0])


# ---------------------------------------------------------------------------
# HyperFile — context-managed wrapper (v0.8.0)
# ---------------------------------------------------------------------------


class HyperFile:
    """Context-managed wrapper for ``.hyper`` file operations.

    Provides ergonomic access to common patterns: bulk insert, rolling
    window refresh, upsert, and introspection — all via a single
    ``with HyperFile(path) as hf:`` block.

    Example::

        with HyperFile("data/sales.hyper") as hf:
            hf.bulk_insert(df)
            print(hf.row_count())
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._bridge: HyperBridge | None = None

    def __enter__(self) -> HyperFile:
        self._bridge = HyperBridge(self._path)
        return self

    def __exit__(self, *exc: Any) -> None:
        self._bridge = None

    @property
    def _b(self) -> HyperBridge:
        if self._bridge is None:
            raise RuntimeError("HyperFile must be used as a context manager.")
        return self._bridge

    def list_tables(self) -> list[str]:
        """Return all table names in the .hyper file."""
        return self._b.tables()

    def schema(self, table: str = "Extract") -> list[dict[str, str]]:
        """Return column schema for *table* as list of ``{name, type}`` dicts."""
        return self._b.schema(table)

    def row_count(self, table: str = "Extract") -> int:
        """Return the number of rows in *table*."""
        return self._b.row_count(table)

    def query(self, sql: str) -> Any:
        """Execute *sql* and return a DataFrame."""
        return self._b.query(sql)

    def bulk_insert(self, df: Any, table: str = "Extract", *, batch_size: int = 10_000) -> int:
        """Insert *df* in batches. Returns total rows inserted.

        Uses ``mode="replace"`` for the first batch to reset the table,
        then ``mode="append"`` for subsequent batches.
        """
        total = 0
        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        if len(df) == 0:
            self._b.from_dataframe(df, table=table, mode="replace")
            return 0
        _ = self._b  # Enforce context-manager use before creating any output.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="pytableau-bulk-", dir=self._path.parent) as temp_dir:
            staged_path = Path(temp_dir) / "staged.hyper"
            if self._path.exists():
                shutil.copy2(self._path, staged_path)
            bridge = HyperBridge(staged_path)
            for i in range(0, len(df), batch_size):
                chunk = df.iloc[i : i + batch_size]
                mode = "replace" if i == 0 else "append"
                bridge.from_dataframe(chunk, table=table, mode=mode)
                total += len(chunk)
            staged_path.replace(self._path)
        return total

    def rolling_window_refresh(
        self, df: Any, date_col: str, window_days: int, table: str = "Extract"
    ) -> int:
        """Delete rows older than *window_days* days and append *df*.

        Args:
            df: DataFrame with new data to append.
            date_col: Column name containing date values for windowing.
            window_days: Rows with dates older than this many days are deleted.
            table: Target Hyper table name.

        Returns:
            Number of rows written.
        """
        import datetime

        if window_days < 0:
            raise ValueError("window_days must not be negative.")
        if date_col not in df.columns:
            raise ValueError(f"Date column not found: {date_col!r}")
        hyperapi = self._b._require(_hyperapi, "tableauhyperapi")
        cutoff = datetime.date.today() - datetime.timedelta(days=window_days)
        if self._path.exists():
            with TemporaryDirectory(prefix="pytableau-rolling-", dir=self._path.parent) as temp_dir:
                staged_path = Path(temp_dir) / "staged.hyper"
                shutil.copy2(self._path, staged_path)
                bridge = HyperBridge(staged_path)
                bridge.execute(
                    f"DELETE FROM {hyperapi.TableName(table)} "
                    f"WHERE {hyperapi.Name(date_col)} < DATE '{cutoff}'"
                )
                bridge.append_dataframe(df, table=table)
                staged_path.replace(self._path)
        else:
            self._b.append_dataframe(df, table=table)
        return len(df)

    def upsert(self, df: Any, key_cols: list[str], table: str = "Extract") -> tuple[int, int]:
        """Atomically replace rows matching all key columns, then insert.

        Composite keys and null keys are supported. Work is staged in a copy
        of the extract; failures leave the original file untouched.

        Args:
            df: DataFrame with new/updated rows.
            key_cols: Column names that form the unique key.
            table: Target Hyper table name.

        Returns:
            Tuple of ``(deleted, inserted)`` row counts.
        """
        if not key_cols:
            raise ValueError("key_cols must not be empty for upsert.")
        pandas_module = self._b._require(_pandas, "pandas")
        hyperapi = self._b._require(_hyperapi, "tableauhyperapi")
        if not isinstance(df, pandas_module.DataFrame):
            raise TypeError("upsert() expects a pandas DataFrame.")
        missing = [col for col in key_cols if col not in df.columns]
        if missing:
            raise ValueError(f"Key columns not found: {missing}")
        if df.empty:
            return 0, 0
        if not self._path.exists():
            self._b.from_dataframe(df, table=table)
            return 0, len(df)
        with self._b._connection() as connection:
            has_table = connection.catalog.has_table(hyperapi.TableName(table))
        if not has_table:
            self._b.append_dataframe(df, table=table)
            return 0, len(df)

        with TemporaryDirectory(prefix="pytableau-upsert-", dir=self._path.parent) as temp_dir:
            staged_path = Path(temp_dir) / "staged.hyper"
            shutil.copy2(self._path, staged_path)
            stage_name = f"__pytableau_upsert_{uuid4().hex}"
            HyperBridge(staged_path).from_dataframe(df, table=stage_name)
            target = hyperapi.TableName(table)
            stage = hyperapi.TableName(stage_name)
            predicates = " AND ".join(
                f"target.{hyperapi.Name(col)} IS NOT DISTINCT FROM incoming.{hyperapi.Name(col)}"
                for col in key_cols
            )
            columns = ", ".join(str(hyperapi.Name(str(col))) for col in df.columns)
            with (
                hyperapi.HyperProcess(
                    telemetry=hyperapi.Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU
                ) as process,
                hyperapi.Connection(endpoint=process.endpoint, database=str(staged_path)) as conn,
            ):
                conn.execute_command("BEGIN")
                deleted = conn.execute_command(
                    f"DELETE FROM {target} AS target WHERE EXISTS "
                    f"(SELECT 1 FROM {stage} AS incoming WHERE {predicates})"
                )
                conn.execute_command(
                    f"INSERT INTO {target} ({columns}) SELECT {columns} FROM {stage}"
                )
                conn.execute_command("COMMIT")
                conn.execute_command(f"DROP TABLE {stage}")
            staged_path.replace(self._path)
        return deleted or 0, len(df)
