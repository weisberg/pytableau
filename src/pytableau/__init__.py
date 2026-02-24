"""pytableau — The unified Python SDK for Tableau workbook engineering.

Quickstart::

    from pytableau import Workbook

    wb = Workbook.open("sales_dashboard.twbx")
    print(wb.version)
    wb.save_as("modified.twbx")
"""

from __future__ import annotations

from pytableau._version import __version__
from pytableau.build import (
    DashboardBuilder,
    DatasourceBuilder,
    WorksheetBuilder,
    from_spec,
    quick_chart,
    quick_dashboard,
)
from pytableau.build.theme import Theme
from pytableau.calculations import LintIssue
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
from pytableau.core.formatting import Color, ColorPalette, Font, FormatSpec
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
    TableauConnectionError,
    TemplateError,
    TemplateNotFoundError,
    UnmappedPlaceholderError,
    ValidationIssue,
    XMLError,
)
from pytableau.governance import (
    GovernanceLintIssue,
    GovernanceRuleset,
    WorkbookIndex,
    lint_with_ruleset,
)
from pytableau.inspect.diff import Patch, WorkbookDiff
from pytableau.package.assets import WorkbookAsset, add_asset, extract_asset, list_assets

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
    "TableauConnectionError",
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
    # Diff & Patch
    "WorkbookDiff",
    "Patch",
    # Formula linter
    "LintIssue",
    # Formatting
    "Color",
    "Font",
    "ColorPalette",
    "FormatSpec",
    # Package assets
    "WorkbookAsset",
    "list_assets",
    "extract_asset",
    "add_asset",
    # Build
    "DatasourceBuilder",
    "WorksheetBuilder",
    "DashboardBuilder",
    "from_spec",
    "quick_chart",
    "quick_dashboard",
    "Theme",
    # Governance
    "WorkbookIndex",
    "GovernanceLintIssue",
    "GovernanceRuleset",
    "lint_with_ruleset",
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
