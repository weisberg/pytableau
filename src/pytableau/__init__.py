"""pytableau — The unified Python SDK for Tableau workbook engineering.

Quickstart::

    from pytableau import Workbook

    wb = Workbook.open("sales_dashboard.twbx")
    print(wb.version)
    wb.save_as("modified.twbx")
"""

from __future__ import annotations

from pytableau._version import __version__
from pytableau.constants import (
    AggregationType,
    ConnectionType,
    DataType,
    FilterType,
    MarkType,
    ParameterDomainType,
    Role,
    SortOrder,
    ValidationLevel,
)
from pytableau.core.workbook import Workbook
from pytableau.exceptions import (
    AmbiguousWorkbookError,
    AuthenticationError,
    ConnectionError,
    CorruptWorkbookError,
    DatasourceError,
    DatasourceNotFoundError,
    DuplicateFieldError,
    ExtractError,
    FieldError,
    FieldNotFoundError,
    FileError,
    FormulaError,
    HyperError,
    IncompatibleVersionError,
    InvalidPathError,
    InvalidWorkbookError,
    LazyNotMaterializedError,
    PackageError,
    PublishError,
    PyTableauError,
    SchemaValidationError,
    ServerError,
    TemplateError,
    TemplateNotFoundError,
    UnmappedPlaceholderError,
    ValidationIssue,
    XMLError,
)

__all__ = [
    # Version
    "__version__",
    # Top-level exceptions
    "PyTableauError",
    "FileError",
    "InvalidWorkbookError",
    "PackageError",
    "AmbiguousWorkbookError",
    "InvalidPathError",
    "LazyNotMaterializedError",
    "CorruptWorkbookError",
    "XMLError",
    "SchemaValidationError",
    "IncompatibleVersionError",
    "FieldError",
    "FieldNotFoundError",
    "DuplicateFieldError",
    "FormulaError",
    "DatasourceError",
    "DatasourceNotFoundError",
    "ConnectionError",
    "HyperError",
    "ExtractError",
    "ServerError",
    "AuthenticationError",
    "PublishError",
    "TemplateError",
    "UnmappedPlaceholderError",
    "TemplateNotFoundError",
    "ValidationIssue",
    "Workbook",
    # Enums
    "MarkType",
    "DataType",
    "Role",
    "AggregationType",
    "FilterType",
    "SortOrder",
    "ConnectionType",
    "ParameterDomainType",
    "ValidationLevel",
]
