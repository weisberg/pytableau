"""Type mapping: pandas ↔ Hyper ↔ Tableau XML data types."""

from __future__ import annotations

_NORMALIZED_PANDAS_TYPES = {
    "object": "TEXT",
    "string": "TEXT",
    "str": "TEXT",
    "str_": "TEXT",
    "int": "BIGINT",
    "int64": "BIGINT",
    "int32": "BIGINT",
    "float": "DOUBLE",
    "float64": "DOUBLE",
    "float32": "DOUBLE",
    "bool": "BOOL",
    "boolean": "BOOL",
    "datetime64": "TIMESTAMP",
    "datetime64[ns]": "TIMESTAMP",
    "datetime": "TIMESTAMP",
    "date": "DATE",
}

_HYPER_TO_TABLEAU = {
    "TEXT": "string",
    "BIGINT": "integer",
    "DOUBLE": "real",
    "BOOL": "boolean",
    "TIMESTAMP": "datetime",
    "DATE": "date",
}

_HYPER_TO_METADATA_REMOTE = {
    "TEXT": "129",
    "BIGINT": "20",
    "DOUBLE": "8",
    "BOOL": "1",
    "TIMESTAMP": "130",
    "DATE": "134",
}


def _normalise(dtype: object) -> str:
    value = str(dtype).lower().strip()
    if value.startswith("datetime64"):
        return "datetime64"
    return value


def pandas_to_hyper(dtype: object) -> str:
    """Map a pandas dtype-like object to a Hyper type."""
    normalized = _normalise(dtype)
    for pattern, hyper_type in _NORMALIZED_PANDAS_TYPES.items():
        if normalized == pattern or normalized.startswith(pattern):
            return hyper_type
    return "TEXT"


def hyper_to_tableau_xml(hyper_type: str) -> str:
    """Map a Hyper type string to Tableau XML datatype."""
    return _HYPER_TO_TABLEAU.get(str(hyper_type).upper(), "string")


def pandas_to_tableau_xml(dtype: object) -> str:
    """Map a pandas dtype-like object directly to a Tableau XML datatype."""
    return hyper_to_tableau_xml(pandas_to_hyper(dtype))


def pandas_to_hyper_remote_type(dtype: object) -> str:
    """Map pandas dtypes to a best-effort Tableau metadata ``remote-type`` id."""
    return _HYPER_TO_METADATA_REMOTE.get(pandas_to_hyper(dtype), "0")


def all_mappings() -> dict[str, dict[str, str]]:
    """Return copies of all known mapping tables for discovery/tests."""
    return {
        "pandas_to_hyper": dict(_NORMALIZED_PANDAS_TYPES),
        "hyper_to_tableau_xml": dict(_HYPER_TO_TABLEAU),
        "pandas_to_hyper_remote_type": dict(_HYPER_TO_METADATA_REMOTE),
    }

