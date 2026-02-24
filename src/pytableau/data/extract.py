"""Extract lifecycle: create, refresh, and attach .hyper files."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from pytableau.data.bridge import HyperBridge
from pytableau.data.types import pandas_to_hyper_remote_type, pandas_to_tableau_xml
from pytableau.exceptions import HyperError


class ExtractManager:
    """Utility for creating and managing extract-backed datasources."""

    def _resolve_base_dir(self, datasource) -> Path:
        if datasource._workbook is None:
            raise HyperError("Datasource is not attached to a workbook.")
        if datasource._workbook._package_manager is not None:
            return datasource._workbook._package_manager.twb_path.parent / "Data"
        if datasource._workbook._path is None:
            raise HyperError("Workbook path is unavailable for extract attachment.")
        return datasource._workbook._path.parent / "Data"

    def _metadata_name(self, datasource) -> str:
        return f"{datasource._connection_safe_name()}.hyper"

    def create(self, datasource, df, table: str = "Extract") -> None:
        """Create a new extract for ``datasource`` and attach it in XML."""
        base = self._resolve_base_dir(datasource)
        base.mkdir(parents=True, exist_ok=True)
        hyper_path = base / self._metadata_name(datasource)
        hyper = HyperBridge(hyper_path, on_write=datasource._sync_extracted_metadata)
        hyper.from_dataframe(df, table=table, mode="replace")
        self.attach(datasource, hyper_path)

    def refresh(self, datasource, df, table: str = "Extract") -> None:
        """Replace existing extract rows while preserving existing XML metadata."""
        if datasource._hyper_path is None:
            raise HyperError("No extract path is associated with this datasource.")
        HyperBridge(datasource._hyper_path).from_dataframe(df, table=table, mode="replace")

    def attach(self, datasource, hyper_path: Path | str) -> None:
        """Attach an existing ``.hyper`` file to a datasource."""
        source = Path(hyper_path)
        if not source.exists():
            raise HyperError(f"Hyper file does not exist: {source}")

        base = self._resolve_base_dir(datasource)
        base.mkdir(parents=True, exist_ok=True)
        destination = base / source.name
        if destination.suffix.lower() != ".hyper":
            destination = base / f"{source.stem}.hyper"
        if destination.resolve() != source.resolve():
            destination.write_bytes(source.read_bytes())

        datasource._set_hyper_path(destination)

        connection = datasource.connections[0] if datasource.connections else None
        if connection is None:
            from pytableau.core.datasource import Connection

            connection_node = etree.SubElement(datasource.xml_node, "connection")
            connection = Connection(connection_node)
            datasource.connections = [connection]

        connection.class_ = "hyper"
        connection.dbname = destination.name
        connection.server = None
        # Tableau expects this relative path in most TWBX packages.
        connection._node.attrib["filename"] = f"Data/{destination.name}"
        connection._node.attrib["port"] = ""
        connection._node.attrib.pop("schema", None)
        connection._node.attrib.pop("dbclass", None)
        connection._node.attrib.pop("oauth", None)

    def upsert(
        self,
        datasource,
        df: object,
        *,
        table: str = "Extract",
        key_columns: list[str] | None = None,
    ) -> int:
        """Incrementally upsert rows into an existing extract.

        Matches existing rows by *key_columns* and updates them; new rows are
        appended.  If *key_columns* is ``None`` all rows in *df* are appended
        (equivalent to an ``INSERT``-only refresh).

        Requires the ``hyper`` optional extra::

            pip install "pytableau[hyper]"

        Args:
            datasource: The :class:`~pytableau.core.datasource.Datasource` with
                an attached ``.hyper`` extract.
            df: A :class:`pandas.DataFrame` containing the updated rows.
            table: Table name inside the Hyper file.  Defaults to ``"Extract"``.
            key_columns: Column names that uniquely identify a row.  When
                provided, matching existing rows are deleted before inserting
                the new data (DELETE + INSERT pattern).
            Returns:
                Number of rows written.
        """
        if datasource._hyper_path is None:
            raise HyperError("No extract path is associated with this datasource.")

        from pytableau._compat import import_optional

        pd = import_optional("pandas", "pandas")
        tableauhyperapi = import_optional("tableauhyperapi", "hyper")
        HyperProcess = tableauhyperapi.HyperProcess
        Telemetry = tableauhyperapi.Telemetry
        Connection = tableauhyperapi.Connection
        TableName = tableauhyperapi.TableName
        pantab = import_optional("pantab", "hyper")

        hyper_path = datasource._hyper_path
        schema_name = "Extract"
        tname = TableName(schema_name, table)

        if key_columns:
            # DELETE matching rows then re-insert (DELETE+INSERT upsert pattern)
            with (
                HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp,
                Connection(hp.endpoint, str(hyper_path)) as conn,
            ):
                # Build DELETE predicate
                conditions = " AND ".join(f'"{col}" = ?' for col in key_columns)
                # Execute row-by-row deletion for matching keys
                for _, row in pd.DataFrame(df)[key_columns].drop_duplicates().iterrows():
                    values = [row[col] for col in key_columns]
                    conn.execute_command(
                        f"DELETE FROM {tname} WHERE {conditions}",
                        parameters=values,
                    )

        # Append the new/updated rows
        pantab.frame_to_hyper(
            pd.DataFrame(df),
            hyper_path,
            table=tname,
            table_mode="a",
        )
        return len(pd.DataFrame(df))

    def detach(self, datasource) -> None:
        """Convert extract-based datasource back to a live connection placeholder."""
        if not datasource.connections:
            return
        if datasource.connections[0].class_ != "hyper":
            return
        datasource.connections[0].class_ = "sqlserver"
        datasource._set_hyper_path(None)

        for key in ("filename", "dbname", "dbclass", "path", "name", "type"):
            datasource.connections[0]._node.attrib.pop(key, None)

    @staticmethod
    def contract_test(datasource) -> list[str]:
        """Verify a Hyper extract is consistent with its XML metadata.

        Checks that:
        - The datasource connection class is ``"hyper"``.
        - The ``.hyper`` file exists on disk.
        - Schema column names match ``metadata_records`` local names (if any).

        Returns:
            List of issue strings (empty = everything is consistent).
        """
        issues: list[str] = []

        if not datasource.connections:
            issues.append("Datasource has no connections.")
            return issues

        conn = datasource.connections[0]
        if getattr(conn, "class_", None) != "hyper":
            issues.append(f"Connection class is {conn.class_!r}, expected 'hyper'.")

        hyper_path = getattr(datasource, "_hyper_path", None)
        if hyper_path is None:
            issues.append("No .hyper file path associated with datasource.")
        elif not Path(hyper_path).exists():
            issues.append(f".hyper file does not exist: {hyper_path}")
        else:
            # Check schema vs metadata_records
            records = datasource.metadata_records
            if records:
                try:
                    bridge = HyperBridge(Path(hyper_path))
                    schema = bridge.schema("Extract")
                    schema_cols = {s["name"] for s in schema}
                    for record in records:
                        local = (record.local_name or "").strip("[]")
                        if local and local not in schema_cols:
                            issues.append(f"Metadata record [{local}] not found in .hyper schema.")
                except Exception as exc:
                    issues.append(f"Cannot read .hyper schema: {exc}")

        return issues

    @classmethod
    def _resolve_hyper_path(cls, datasource) -> Path:
        """Resolve the .hyper file path for a datasource."""
        hyper_path = getattr(datasource, "_hyper_path", None)
        if hyper_path is not None:
            return Path(hyper_path)
        base = cls()._resolve_base_dir(datasource)
        return base / cls()._metadata_name(datasource)

    @classmethod
    def incremental_refresh(
        cls,
        datasource,
        df,
        mode: str = "rolling",
        date_col: str | None = None,
        window_days: int = 90,
        key_cols: list[str] | None = None,
        table: str = "Extract",
    ) -> int:
        """Refresh an extract incrementally without replacing all data.

        Args:
            datasource: The :class:`~pytableau.core.datasource.Datasource`.
            df: New DataFrame with data to merge in.
            mode: ``"rolling"`` (delete old rows by date) or ``"upsert"``
                (delete-by-key then insert).
            date_col: Column name for rolling window date cutoff.
            window_days: Days to keep for rolling window (default: 90).
            key_cols: Key columns for upsert mode.
            table: Hyper table name (default: ``"Extract"``).

        Returns:
            Number of rows written.
        """
        from pytableau.data.bridge import HyperFile

        hyper_path = cls._resolve_hyper_path(datasource)
        with HyperFile(hyper_path) as hf:
            if mode == "rolling":
                if not date_col:
                    raise ValueError("date_col is required for rolling mode.")
                return hf.rolling_window_refresh(df, date_col, window_days, table=table)
            elif mode == "upsert":
                _, inserted = hf.upsert(df, key_cols or [], table=table)
                return inserted
            else:
                raise ValueError(f"Unknown incremental_refresh mode: {mode!r}")

    def sync_metadata_records(self, datasource, df) -> None:
        """Update ``<metadata-records>`` to match ``df`` schema."""
        metadata_parent = datasource.xml_node.find("metadata-records")
        if metadata_parent is None:
            metadata_parent = etree.SubElement(datasource.xml_node, "metadata-records")
        for child in list(metadata_parent):
            metadata_parent.remove(child)

        for index, field_name in enumerate(df.columns, start=1):
            record = etree.SubElement(
                metadata_parent, "metadata-record", attrib={"class": "column"}
            )
            values = (
                ("remote-name", str(field_name)),
                ("remote-type", pandas_to_hyper_remote_type(df[field_name].dtype)),
                ("local-name", f"[{field_name}]"),
                ("parent-name", "[Extract]"),
                ("remote-alias", str(field_name)),
                ("ordinal", str(index)),
                ("local-type", pandas_to_tableau_xml(df[field_name].dtype)),
                ("aggregation", "Count"),
                ("approx-count", str(len(df))),
                ("contains-null", str(any(df[field_name].isnull())).lower()),
            )
            for tag_name, value in values:
                child = etree.SubElement(record, tag_name)
                child.text = value
