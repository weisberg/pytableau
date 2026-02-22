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

    def sync_metadata_records(self, datasource, df) -> None:
        """Update ``<metadata-records>`` to match ``df`` schema."""
        metadata_parent = datasource.xml_node.find("metadata-records")
        if metadata_parent is None:
            metadata_parent = etree.SubElement(datasource.xml_node, "metadata-records")
        for child in list(metadata_parent):
            metadata_parent.remove(child)

        for index, field_name in enumerate(df.columns, start=1):
            record = etree.SubElement(metadata_parent, "metadata-record", attrib={"class": "column"})
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
