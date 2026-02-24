"""Constants and enumerations for pytableau.

All Tableau-level concepts (mark types, data types, roles, etc.) are
represented as ``str`` enums so that values compare equal to the raw
XML attribute strings used by Tableau.
"""

from __future__ import annotations

from enum import Enum


class MarkType(str, Enum):
    """Viz mark types as they appear in Tableau XML."""

    AUTOMATIC = "automatic"
    BAR = "bar"
    LINE = "line"
    AREA = "area"
    CIRCLE = "circle"
    SQUARE = "square"
    SHAPE = "shape"  # custom shapes palette
    TEXT = "text"
    MAP = "map"
    PIE = "pie"
    GANTT = "gantt_rounded"
    GANTT_BAR = "gantt_rounded"  # alias — same XML value
    POLYGON = "polygon"
    DENSITY = "density"


class DataType(str, Enum):
    """Field data types as they appear in Tableau XML."""

    STRING = "string"
    INTEGER = "integer"
    REAL = "real"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"


class Role(str, Enum):
    """Semantic role of a field."""

    DIMENSION = "dimension"
    MEASURE = "measure"


class AggregationType(str, Enum):
    """Default aggregation types for measure fields."""

    SUM = "Sum"
    AVG = "Avg"
    COUNT = "Count"
    COUNTD = "CountD"
    MIN = "Min"
    MAX = "Max"
    MEDIAN = "Median"
    ATTR = "Attr"
    STDEV = "Stdev"
    VAR = "Var"
    YEAR = "Year"
    QUARTER = "Quarter"
    MONTH = "Month"
    WEEK = "Week"
    DAY = "Day"
    NONE = "None"


class FilterType(str, Enum):
    """Filter types as they appear in Tableau XML."""

    CATEGORICAL = "categorical"
    QUANTITATIVE = "quantitative"
    RELATIVE_DATE = "relative-date"
    RANGE = "range"
    TOP = "top"
    WILDCARD = "wildcard"
    ALL = "all"


class SortOrder(str, Enum):
    """Sort direction options."""

    ASCENDING = "asc"
    DESCENDING = "desc"
    NONE = "none"


class SortType(str, Enum):
    """Sort method options."""

    ALPHABETIC = "alphabetic"
    DATA_SOURCE = "data-source-order"
    FIELD = "field"
    MANUAL = "manual"
    NONE = "none"


class ConnectionType(str, Enum):
    """Common Tableau connection class names (``class`` XML attribute)."""

    HYPER = "hyper"
    TEXTSCAN = "textscan"  # CSV / text files
    EXCEL = "excel-direct"
    SQLSERVER = "sqlserver"
    MSSQL = "sqlserver"  # alias — same XML class value as SQLSERVER
    POSTGRES = "postgres"
    MYSQL = "mysql"
    ORACLE = "oracle"
    REDSHIFT = "redshift"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    DATABRICKS = "spark"
    ATHENA = "athena"
    TABLEAU_SERVER = "tableau-server"  # published data source on Tableau Server/Cloud


class DashboardSizeType(str, Enum):
    """Dashboard size constraint modes."""

    FIXED = "fixed"
    AUTOMATIC = "automatic"
    RANGE = "range"


class ZoneType(str, Enum):
    """Dashboard zone layout types."""

    LAYOUT_BASIC = "layout-basic"
    LAYOUT_FLOW = "layout-flow"
    WORKSHEET = "worksheet"
    TEXT = "text"
    IMAGE = "image"
    WEB = "web"
    BLANK = "blank"
    TITLE = "title"
    LEGEND = "legend"
    FILTER = "filter"
    PARAMETER = "parameter"
    EXTENSION = "extension"


class ShelfType(str, Enum):
    """Worksheet shelf identifiers."""

    ROWS = "rows"
    COLUMNS = "columns"
    COLOR = "color"
    SIZE = "size"
    LABEL = "label"
    DETAIL = "detail"
    TOOLTIP = "tooltip"
    PATH = "path"
    SHAPE = "shape"
    ANGLE = "angle"


class ActionType(str, Enum):
    """Dashboard action types."""

    FILTER = "filter"
    HIGHLIGHT = "highlight"
    URL = "url"
    GOTO_SHEET = "goto-sheet"
    CHANGE_PARAMETER = "change-parameter"
    CHANGE_SET_VALUES = "change-set-values"


class ParameterDomainType(str, Enum):
    """Parameter allowable values type."""

    ALL = "all"
    ANY = "any"
    LIST = "list"
    RANGE = "range"


class ValidationLevel(str, Enum):
    """Severity levels for validation issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# ---------------------------------------------------------------------------
# Tableau version mapping: version string → XML source-build attribute value
# ---------------------------------------------------------------------------

#: Maps human-readable Tableau version strings to the ``source-build``
#: attribute value written in workbook XML headers.
TABLEAU_VERSION_MAP: dict[str, str] = {
    "2022.1": "20221.22.0418.1333",
    "2022.2": "20222.22.0719.1543",
    "2022.3": "20223.22.1007.0912",
    "2022.4": "20224.23.0112.0803",
    "2023.1": "20231.23.0309.0931",
    "2023.2": "20232.23.0609.0906",
    "2023.3": "20233.23.0921.0921",
    "2023.4": "20234.24.0111.0824",
    "2024.1": "20241.24.0312.0830",
    "2024.2": "20242.24.0613.0835",
    "2024.3": "20243.24.0912.0921",
    "2025.1": "20251.25.0314.0930",
}

#: The minimum Tableau version supported by pytableau.
MINIMUM_TABLEAU_VERSION = "2022.1"

#: The default Tableau version used when creating new workbooks.
DEFAULT_TABLEAU_VERSION = "2024.1"
