"""Tableau function registry: 100+ built-in functions with metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FunctionInfo:
    """Metadata for a single Tableau built-in function."""

    name: str
    category: str  # aggregate | string | number | date | type_conv | logical | table_calc | user | spatial
    min_args: int
    max_args: int | None  # None = variadic
    return_type: str | None
    deprecated: bool = False
    deprecation_note: str = ""


def _f(
    name: str,
    cat: str,
    mn: int,
    mx: int | None,
    ret: str | None,
    dep: bool = False,
    note: str = "",
) -> tuple[str, FunctionInfo]:
    return name.upper(), FunctionInfo(name.upper(), cat, mn, mx, ret, dep, note)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

FUNCTION_REGISTRY: dict[str, FunctionInfo] = dict(
    [
        # ---- Aggregate (14) ----
        _f("SUM", "aggregate", 1, 1, "real"),
        _f("AVG", "aggregate", 1, 1, "real"),
        _f("COUNT", "aggregate", 1, 1, "integer"),
        _f("COUNTD", "aggregate", 1, 1, "integer"),
        _f("MAX", "aggregate", 1, None, None),  # also string/date
        _f("MIN", "aggregate", 1, None, None),
        _f("MEDIAN", "aggregate", 1, 1, "real"),
        _f("PERCENTILE", "aggregate", 2, 2, "real"),
        _f("STDEV", "aggregate", 1, 1, "real"),
        _f("STDEVP", "aggregate", 1, 1, "real"),
        _f("VAR", "aggregate", 1, 1, "real"),
        _f("VARP", "aggregate", 1, 1, "real"),
        _f("ATTR", "aggregate", 1, 1, None),
        _f("COLLECT", "aggregate", 1, 1, "geometry"),
        # ---- String (20) ----
        _f("ASCII", "string", 1, 1, "integer"),
        _f("CHAR", "string", 1, 1, "string"),
        _f("CONTAINS", "string", 2, 2, "boolean"),
        _f("ENDSWITH", "string", 2, 2, "boolean"),
        _f("FIND", "string", 2, 3, "integer"),
        _f("FINDNTH", "string", 3, 3, "integer"),
        _f("LEFT", "string", 2, 2, "string"),
        _f("LEN", "string", 1, 1, "integer"),
        _f("LOWER", "string", 1, 1, "string"),
        _f("LTRIM", "string", 1, 1, "string"),
        _f("MID", "string", 2, 3, "string"),
        _f("REPLACE", "string", 3, 3, "string"),
        _f("RIGHT", "string", 2, 2, "string"),
        _f("RTRIM", "string", 1, 1, "string"),
        _f("SPACE", "string", 1, 1, "string"),
        _f("SPLIT", "string", 3, 3, "string"),
        _f("STARTSWITH", "string", 2, 2, "boolean"),
        _f("TRIM", "string", 1, 1, "string"),
        _f("UPPER", "string", 1, 1, "string"),
        _f("REGEXP_EXTRACT", "string", 2, 2, "string"),
        _f("REGEXP_EXTRACT_NTH", "string", 3, 3, "string"),
        _f("REGEXP_MATCH", "string", 2, 2, "boolean"),
        _f("REGEXP_REPLACE", "string", 3, 3, "string"),
        # ---- Number (26) ----
        _f("ABS", "number", 1, 1, "real"),
        _f("ACOS", "number", 1, 1, "real"),
        _f("ASIN", "number", 1, 1, "real"),
        _f("ATAN", "number", 1, 1, "real"),
        _f("ATAN2", "number", 2, 2, "real"),
        _f("CEILING", "number", 1, 1, "integer"),
        _f("COS", "number", 1, 1, "real"),
        _f("COT", "number", 1, 1, "real"),
        _f("DEGREES", "number", 1, 1, "real"),
        _f("DIV", "number", 2, 2, "integer"),
        _f("EXP", "number", 1, 1, "real"),
        _f("FLOOR", "number", 1, 1, "integer"),
        _f("HEXBINX", "number", 2, 2, "real"),
        _f("HEXBINY", "number", 2, 2, "real"),
        _f("LN", "number", 1, 1, "real"),
        _f("LOG", "number", 1, 2, "real"),
        _f("PI", "number", 0, 0, "real"),
        _f("POWER", "number", 2, 2, "real"),
        _f("RADIANS", "number", 1, 1, "real"),
        _f("ROUND", "number", 1, 2, "real"),
        _f("SIGN", "number", 1, 1, "integer"),
        _f("SIN", "number", 1, 1, "real"),
        _f("SQRT", "number", 1, 1, "real"),
        _f("SQUARE", "number", 1, 1, "real"),
        _f("TAN", "number", 1, 1, "real"),
        _f("ZN", "number", 1, 1, "real"),
        # ---- Date (17) ----
        _f("DATEADD", "date", 3, 3, "datetime"),
        _f("DATEDIFF", "date", 3, 4, "integer"),
        _f("DATENAME", "date", 2, 3, "string"),
        _f("DATEPARSE", "date", 2, 2, "datetime"),
        _f("DATEPART", "date", 2, 3, "integer"),
        _f("DATETRUNC", "date", 2, 3, "datetime"),
        _f("DAY", "date", 1, 1, "integer"),
        _f("ISDATE", "date", 1, 1, "boolean"),
        _f("MAKEDATE", "date", 3, 3, "date"),
        _f("MAKEDATETIME", "date", 2, 2, "datetime"),
        _f("MAKETIME", "date", 3, 3, "time"),
        _f("MONTH", "date", 1, 1, "integer"),
        _f("NOW", "date", 0, 0, "datetime"),
        _f("QUARTER", "date", 1, 1, "integer"),
        _f("TODAY", "date", 0, 0, "date"),
        _f("WEEK", "date", 1, 1, "integer"),
        _f("YEAR", "date", 1, 1, "integer"),
        # ---- Type conversion (6) ----
        _f("DATE", "type_conv", 1, 1, "date"),
        _f("DATETIME", "type_conv", 1, 1, "datetime"),
        _f("FLOAT", "type_conv", 1, 1, "real"),
        _f("INT", "type_conv", 1, 1, "integer"),
        _f("STR", "type_conv", 1, 1, "string"),
        _f("BOOL", "type_conv", 1, 1, "boolean"),
        # ---- Logical (6) ----
        _f("IF", "logical", 2, None, None),
        _f("IIF", "logical", 3, 3, None),
        _f("IFNULL", "logical", 2, 2, None),
        _f("ISNULL", "logical", 1, 1, "boolean"),
        _f("CASE", "logical", 2, None, None),
        _f("COALESCE", "logical", 2, None, None),
        # ---- Table calculations (28) ----
        _f("FIRST", "table_calc", 0, 0, "integer"),
        _f("LAST", "table_calc", 0, 0, "integer"),
        _f("INDEX", "table_calc", 0, 0, "integer"),
        _f("LOOKUP", "table_calc", 1, 2, None),
        _f("PREVIOUS_VALUE", "table_calc", 1, 1, None),
        _f("RANK", "table_calc", 1, 2, "integer"),
        _f("RANK_DENSE", "table_calc", 1, 2, "integer"),
        _f("RANK_MODIFIED", "table_calc", 1, 2, "integer"),
        _f("RANK_PERCENTILE", "table_calc", 1, 2, "real"),
        _f("RANK_UNIQUE", "table_calc", 1, 2, "integer"),
        _f("RUNNING_AVG", "table_calc", 1, 1, "real"),
        _f("RUNNING_COUNT", "table_calc", 1, 1, "integer"),
        _f("RUNNING_MAX", "table_calc", 1, 1, None),
        _f("RUNNING_MIN", "table_calc", 1, 1, None),
        _f("RUNNING_SUM", "table_calc", 1, 1, "real"),
        _f("SIZE", "table_calc", 0, 0, "integer"),
        _f("TOTAL", "table_calc", 1, 1, None),
        _f("WINDOW_AVG", "table_calc", 1, 3, "real"),
        _f("WINDOW_COUNT", "table_calc", 1, 3, "integer"),
        _f("WINDOW_MAX", "table_calc", 1, 3, None),
        _f("WINDOW_MEDIAN", "table_calc", 1, 3, "real"),
        _f("WINDOW_MIN", "table_calc", 1, 3, None),
        _f("WINDOW_PERCENTILE", "table_calc", 2, 4, "real"),
        _f("WINDOW_STDEV", "table_calc", 1, 3, "real"),
        _f("WINDOW_STDEVP", "table_calc", 1, 3, "real"),
        _f("WINDOW_SUM", "table_calc", 1, 3, "real"),
        _f("WINDOW_VAR", "table_calc", 1, 3, "real"),
        _f("WINDOW_VARP", "table_calc", 1, 3, "real"),
        # ---- User (3) ----
        _f("FULLNAME", "user", 0, 0, "string"),
        _f("ISMEMBEROF", "user", 1, 1, "boolean"),
        _f("USERNAME", "user", 0, 0, "string"),
        # ---- Spatial / Geo (8) ----
        _f("AREA", "spatial", 1, 2, "real"),
        _f("BUFFER", "spatial", 2, 3, "geometry"),
        _f("DISTANCE", "spatial", 3, 3, "real"),
        _f("INTERSECTS", "spatial", 2, 2, "boolean"),
        _f("ISVALID", "spatial", 1, 1, "boolean"),
        _f("MAKELINE", "spatial", 2, 2, "geometry"),
        _f("MAKEPOINT", "spatial", 2, 3, "geometry"),
        _f("SPATIAL_INTERSECTS", "spatial", 2, 2, "boolean"),
        # ---- Deprecated (5) ----
        _f(
            "SCRIPT_REAL",
            "deprecated",
            1,
            None,
            "real",
            dep=True,
            note="Use Python/R extensions or TabPy (archived Dec 2025).",
        ),
        _f(
            "SCRIPT_STR",
            "deprecated",
            1,
            None,
            "string",
            dep=True,
            note="Use Python/R extensions or TabPy (archived Dec 2025).",
        ),
        _f(
            "SCRIPT_INT",
            "deprecated",
            1,
            None,
            "integer",
            dep=True,
            note="Use Python/R extensions or TabPy (archived Dec 2025).",
        ),
        _f(
            "SCRIPT_BOOL",
            "deprecated",
            1,
            None,
            "boolean",
            dep=True,
            note="Use Python/R extensions or TabPy (archived Dec 2025).",
        ),
        _f(
            "RAWSQL_REAL",
            "deprecated",
            1,
            None,
            "real",
            dep=True,
            note="Use native Tableau functions or calculated fields.",
        ),
        _f(
            "RAWSQL_STR",
            "deprecated",
            1,
            None,
            "string",
            dep=True,
            note="Use native Tableau functions or calculated fields.",
        ),
        _f(
            "RAWSQL_INT",
            "deprecated",
            1,
            None,
            "integer",
            dep=True,
            note="Use native Tableau functions or calculated fields.",
        ),
        _f(
            "RAWSQL_BOOL",
            "deprecated",
            1,
            None,
            "boolean",
            dep=True,
            note="Use native Tableau functions or calculated fields.",
        ),
    ]
)

#: Set of deprecated function names for quick lookup
DEPRECATED_FUNCTIONS: frozenset[str] = frozenset(
    name for name, info in FUNCTION_REGISTRY.items() if info.deprecated
)
