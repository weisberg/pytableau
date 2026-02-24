"""Build datasource XML elements programmatically.

Example::

    from pytableau.build import DatasourceBuilder
    from pytableau.constants import DataType, Role

    ds = (
        DatasourceBuilder("Sales Data")
        .connection("hyper", dbname="Data/sales.hyper")
        .column("Region", DataType.STRING, Role.DIMENSION)
        .column("Sales", DataType.REAL, Role.MEASURE)
        .calculated_field("Margin", "SUM([Sales]) - SUM([Cost])")
        .build()
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree

from pytableau.constants import DataType, Role
from pytableau.exceptions import DuplicateFieldError

from ._xml import ds_internal_name, make_column_type, slugify, unique_calc_name

if TYPE_CHECKING:
    pass


@dataclass
class _ColumnSpec:
    caption: str
    datatype: str
    role: str
    hidden: bool = False


@dataclass
class _CalcFieldSpec:
    caption: str
    formula: str
    datatype: str = DataType.REAL.value
    role: str = Role.MEASURE.value


class DatasourceBuilder:
    """Fluent builder for ``<datasource>`` XML elements.

    Parameters:
        caption: The human-readable datasource name (becomes the ``caption`` attribute).
    """

    def __init__(self, caption: str) -> None:
        self._caption = caption
        self._connection_class: str = "hyper"
        self._connection_attrs: dict[str, str] = {}
        self._columns: list[_ColumnSpec] = []
        self._calc_fields: list[_CalcFieldSpec] = []
        self._seen_captions: set[str] = set()

    # -- Connection ----------------------------------------------------------

    def connection(self, cls: str, **attrs: str) -> DatasourceBuilder:
        """Set the connection class and attributes.

        Args:
            cls: Connection class (e.g. ``"hyper"``, ``"sqlserver"``,
                ``"postgres"``, ``"snowflake"``).
            **attrs: Additional connection attributes passed directly to the
                XML element (e.g. ``server="prod.corp.com"``,
                ``dbname="analytics"``).
        """
        self._connection_class = cls
        self._connection_attrs = dict(attrs)
        return self

    # -- Columns -------------------------------------------------------------

    def column(
        self,
        caption: str,
        datatype: DataType | str = DataType.STRING,
        role: Role | str = Role.DIMENSION,
        *,
        hidden: bool = False,
    ) -> DatasourceBuilder:
        """Add a data column.

        Args:
            caption: Field display name.
            datatype: Tableau data type.
            role: Semantic role (dimension or measure).
            hidden: Whether the field is hidden from the viz pane.
        """
        key = caption.strip().lower()
        if key in self._seen_captions:
            raise DuplicateFieldError(f"Column '{caption}' already defined.")
        self._seen_captions.add(key)

        dt = datatype.value if isinstance(datatype, DataType) else str(datatype)
        r = role.value if isinstance(role, Role) else str(role)
        self._columns.append(_ColumnSpec(caption=caption, datatype=dt, role=r, hidden=hidden))
        return self

    def calculated_field(
        self,
        caption: str,
        formula: str,
        datatype: DataType | str = DataType.REAL,
        role: Role | str = Role.MEASURE,
    ) -> DatasourceBuilder:
        """Add a calculated field.

        Args:
            caption: Field display name.
            formula: Tableau calculation formula.
            datatype: Result data type.
            role: Semantic role.
        """
        key = caption.strip().lower()
        if key in self._seen_captions:
            raise DuplicateFieldError(f"Calculated field '{caption}' already defined.")
        self._seen_captions.add(key)

        dt = datatype.value if isinstance(datatype, DataType) else str(datatype)
        r = role.value if isinstance(role, Role) else str(role)
        self._calc_fields.append(
            _CalcFieldSpec(caption=caption, formula=formula, datatype=dt, role=r)
        )
        return self

    # -- Classmethods --------------------------------------------------------

    @classmethod
    def from_dataframe(cls, df: object, caption: str = "Data") -> DatasourceBuilder:
        """Infer columns from a pandas DataFrame's dtypes.

        Args:
            df: A ``pandas.DataFrame``.
            caption: Name for the datasource.

        Raises:
            ImportError: If pandas is not installed.
            TypeError: If *df* is not a DataFrame.
        """
        try:
            import pandas as pd  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "pandas is required for DatasourceBuilder.from_dataframe(). "
                "Install it with: pip install 'pytableau[pandas]'"
            ) from exc

        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pandas DataFrame, got {type(df).__name__}")

        # Heuristic column names that should be dimensions even when numeric
        _DIMENSION_HINTS = {
            "id",
            "key",
            "code",
            "name",
            "category",
            "type",
            "region",
            "state",
            "country",
            "city",
            "zip",
            "postal",
            "status",
            "group",
            "segment",
            "class",
            "tier",
            "level",
            "flag",
        }

        builder = cls(caption)
        builder.connection("hyper", dbname=f"Data/{slugify(caption)}.hyper")

        for col_name in df.columns:
            dtype = df[col_name].dtype
            name_lower = str(col_name).lower().strip()

            # Infer datatype and role from pandas dtype
            if pd.api.types.is_bool_dtype(dtype):
                dt, role = DataType.BOOLEAN, Role.DIMENSION
            elif pd.api.types.is_integer_dtype(dtype):
                dt, role = DataType.INTEGER, Role.MEASURE
            elif pd.api.types.is_float_dtype(dtype):
                dt, role = DataType.REAL, Role.MEASURE
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                dt, role = DataType.DATETIME, Role.DIMENSION
            else:
                dt, role = DataType.STRING, Role.DIMENSION

            # Override to dimension for heuristic column names
            if any(hint in name_lower for hint in _DIMENSION_HINTS):
                role = Role.DIMENSION

            builder.column(str(col_name), dt, role)

        return builder

    @classmethod
    def from_hyper(cls, hyper_path: str | Path, caption: str | None = None) -> DatasourceBuilder:
        """Infer columns from a ``.hyper`` file's schema.

        Requires the ``tableauhyperapi`` package.

        Args:
            hyper_path: Path to the ``.hyper`` file.
            caption: Datasource name (defaults to the filename stem).

        Raises:
            ImportError: If tableauhyperapi is not installed.
        """
        try:
            from tableauhyperapi import Connection, HyperProcess, Telemetry
        except ImportError as exc:
            raise ImportError(
                "tableauhyperapi is required for DatasourceBuilder.from_hyper(). "
                "Install it with: pip install 'pytableau[hyper]'"
            ) from exc

        path = Path(hyper_path)
        name = caption or path.stem

        builder = cls(name)
        builder.connection("hyper", dbname=str(path))

        _HYPER_TYPE_MAP = {
            "BOOL": (DataType.BOOLEAN, Role.DIMENSION),
            "SMALL_INT": (DataType.INTEGER, Role.MEASURE),
            "INT": (DataType.INTEGER, Role.MEASURE),
            "BIG_INT": (DataType.INTEGER, Role.MEASURE),
            "DOUBLE": (DataType.REAL, Role.MEASURE),
            "OID": (DataType.INTEGER, Role.DIMENSION),
            "TEXT": (DataType.STRING, Role.DIMENSION),
            "VARCHAR": (DataType.STRING, Role.DIMENSION),
            "CHAR": (DataType.STRING, Role.DIMENSION),
            "DATE": (DataType.DATE, Role.DIMENSION),
            "TIMESTAMP": (DataType.DATETIME, Role.DIMENSION),
            "TIMESTAMP_TZ": (DataType.DATETIME, Role.DIMENSION),
            "GEOGRAPHY": (DataType.STRING, Role.DIMENSION),
            "INTERVAL": (DataType.STRING, Role.DIMENSION),
            "NUMERIC": (DataType.REAL, Role.MEASURE),
        }

        with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp, Connection(
            hp.endpoint, str(path)
        ) as conn:
                for schema in conn.catalog.get_schema_names():
                    for table in conn.catalog.get_table_names(schema):
                        defn = conn.catalog.get_table_definition(table)
                        for col in defn.columns:
                            type_tag = str(col.type).split("(")[0].upper()
                            dt, role = _HYPER_TYPE_MAP.get(
                                type_tag,
                                (DataType.STRING, Role.DIMENSION),
                            )
                            builder.column(col.name.unescaped, dt, role)

        return builder

    # -- Build ---------------------------------------------------------------

    @property
    def name(self) -> str:
        """The internal datasource name that will appear in the XML."""
        return ds_internal_name(self._connection_class, self._caption)

    def build(self) -> etree._Element:
        """Generate the ``<datasource>`` XML element.

        Returns:
            An ``lxml.etree._Element`` ready to append to a workbook.
        """
        internal_name = self.name

        ds = etree.Element("datasource", name=internal_name, caption=self._caption)

        # Connection
        conn_attrs = {"class": self._connection_class, **self._connection_attrs}
        etree.SubElement(ds, "connection", attrib=conn_attrs)

        # Columns container
        columns = etree.SubElement(ds, "columns")

        # Data columns
        for spec in self._columns:
            attrs: dict[str, str] = {
                "name": f"[{spec.caption}]",
                "caption": spec.caption,
                "datatype": spec.datatype,
                "role": spec.role,
                "type": make_column_type(spec.role),
            }
            if spec.hidden:
                attrs["hidden"] = "true"
            etree.SubElement(columns, "column", attrib=attrs)

        # Calculated fields
        existing_names: set[str] = {f"[{c.caption}]" for c in self._columns}
        for calc in self._calc_fields:
            internal = unique_calc_name(existing_names)
            existing_names.add(internal)
            attrs = {
                "name": internal,
                "caption": calc.caption,
                "datatype": calc.datatype,
                "role": calc.role,
                "type": make_column_type(calc.role),
            }
            col = etree.SubElement(columns, "column", attrib=attrs)
            etree.SubElement(
                col, "calculation", attrib={"class": "tableau", "formula": calc.formula}
            )

        return ds

    def raw(self) -> etree._Element:
        """Return the built element (alias for :meth:`build` when you want the escape hatch)."""
        return self.build()
