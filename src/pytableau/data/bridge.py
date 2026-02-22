"""HyperBridge: unified pantab + tableauhyperapi wrapper."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

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
            raise HyperError(
                f"Missing function '{name}' in optional dependency for hyper support."
            )
        return target

    def from_dataframe(self, df: Any, table: str = "Extract", mode: str = "replace") -> None:
        if mode not in {"replace", "append"}:
            raise ValueError("mode must be 'replace' or 'append'")

        pandas_module = self._require(_pandas, "pandas")
        if not isinstance(df, pandas_module.DataFrame):
            raise TypeError("from_dataframe() expects a pandas DataFrame.")

        if mode == "replace" and self.path.exists():
            self.path.unlink()

        pantab = self._require(_pantab, "pantab")
        writer = self._as_callable(pantab, "frame_to_hyper")
        if self.path.parent:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        writer(df, str(self.path), table=table, mode=mode)

        if self._on_write is not None:
            self._on_write(df, table)

    def to_dataframe(self, table: str = "Extract"):
        self._require(_pandas, "pandas")
        pantab = self._require(_pantab, "pantab")
        reader = self._as_callable(pantab, "hyper_to_frame")
        output = reader(str(self.path), table=table)
        if isinstance(output, list):
            pandas_module = self._require(_pandas, "pandas")
            return pandas_module.DataFrame(output)
        return output

    def append_dataframe(self, df: Any, table: str = "Extract") -> None:
        self.from_dataframe(df, table=table, mode="append")

    def execute(self, sql: str) -> None:
        hyperapi = self._require(_hyperapi, "tableauhyperapi")
        self._run_command(sql, hyperapi=hyperapi)

    def query(self, sql: str):
        self._require(_pandas, "pandas")
        hyperapi = self._require(_hyperapi, "tableauhyperapi")
        return self._run_query(sql, hyperapi=hyperapi)

    def _run_command(self, sql: str, *, hyperapi: Any) -> None:
        endpoint = getattr(hyperapi, "HyperProcess", None)
        connection_ctor = getattr(hyperapi, "Connection", None)
        if endpoint is None or connection_ctor is None:
            raise HyperError("Unsupported tableauhyperapi API: expected HyperProcess and Connection.")

        with endpoint() as process:
            with connection_ctor(
                endpoint=process.endpoint,
                database=str(self.path),
                create_if_missing=False,
            ) as connection:
                if not hasattr(connection, "execute_command"):
                    raise HyperError("Unsupported tableauhyperapi Connection API.")
                connection.execute_command(sql)

    def _run_query(self, sql: str, *, hyperapi: Any):
        endpoint = getattr(hyperapi, "HyperProcess", None)
        connection_ctor = getattr(hyperapi, "Connection", None)
        if endpoint is None or connection_ctor is None:
            raise HyperError("Unsupported tableauhyperapi API: expected HyperProcess and Connection.")

        with endpoint() as process:
            with connection_ctor(
                endpoint=process.endpoint,
                database=str(self.path),
                create_if_missing=False,
            ) as connection:
                if hasattr(connection, "execute_query"):
                    result = connection.execute_query(sql)
                    rows = list(result.fetchall()) if hasattr(result, "fetchall") else list(result)
                    descriptions = getattr(result, "description", None)
                    columns = []
                    if descriptions:
                        for column in descriptions:
                            columns.append(str(getattr(column, "name", "")) or "")
                elif hasattr(connection, "execute_list_query"):
                    rows = connection.execute_list_query(sql)
                    columns = [f"column_{idx}" for idx in range(len(rows[0]))] if rows else []
                else:
                    raise HyperError("Unsupported tableauhyperapi Connection API.")
                return self._rows_to_dataframe(rows, columns)

    def _rows_to_dataframe(self, rows: list[tuple[Any, ...]], columns: list[str]):
        pandas_module = self._require(_pandas, "pandas")
        if not rows and columns:
            return pandas_module.DataFrame(columns=columns)
        return pandas_module.DataFrame.from_records(rows, columns=columns if columns else None)

    def tables(self) -> list[str]:
        try:
            rows = self.query("SELECT table_name FROM information_schema.tables")
        except Exception as exc:
            raise HyperError(f"Unable to enumerate tables from '{self.path}'.") from exc
        return [str(row[0]) for row in rows.itertuples(index=False, name=None)]

    def schema(self, table: str) -> list[dict[str, str]]:
        rows = self.query(
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_name = '{table}'"
        )
        return [
            {
                "name": str(row[0]),
                "type": str(row[1]),
            }
            for row in rows.itertuples(index=False, name=None)
        ]

    def row_count(self, table: str) -> int:
        rows = self.query(f"SELECT COUNT(*) AS __count FROM [{table}]")
        if len(rows) == 0:
            return 0
        return int(rows.iloc[0, 0])
