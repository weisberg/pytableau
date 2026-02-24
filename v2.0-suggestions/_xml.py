"""Internal XML-generation helpers for the build module."""

from __future__ import annotations

import re
import time

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(caption: str) -> str:
    """Turn a human caption into a safe XML name slug.

    >>> slugify("Sales Data")
    'sales_data'
    """
    return _SLUG_RE.sub("_", caption.strip().lower()).strip("_")


def encode_shelf_field(field: str) -> str:
    """Wrap a field reference in brackets if not already wrapped.

    >>> encode_shelf_field("Region")
    '[Region]'
    >>> encode_shelf_field("[SUM(Sales)]")
    '[SUM(Sales)]'
    >>> encode_shelf_field("SUM(Sales)")
    '[SUM(Sales)]'
    """
    field = field.strip()
    if field.startswith("[") and field.endswith("]"):
        return field
    return f"[{field}]"


def encode_shelf_list(fields: list[str]) -> str:
    """Encode a list of field references as a comma-separated shelf string."""
    return ", ".join(encode_shelf_field(f) for f in fields)


def make_column_type(role: str) -> str:
    """Return the Tableau ``type`` attribute for a role.

    Dimensions are ``nominal``, measures are ``quantitative``.
    """
    return "quantitative" if role == "measure" else "nominal"


def unique_calc_name(existing: set[str]) -> str:
    """Generate a unique ``[Calculation_...]`` internal name."""
    counter = 0
    while True:
        name = f"[Calculation_{int(time.time())}_{counter}]"
        if name not in existing:
            return name
        counter += 1


def ds_internal_name(connection_class: str, caption: str) -> str:
    """Build the dotted internal datasource name.

    >>> ds_internal_name("hyper", "Sales Data")
    'hyper.sales_data'
    """
    return f"{connection_class}.{slugify(caption)}"
