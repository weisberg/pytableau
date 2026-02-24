"""Exception hierarchy for pytableau."""

from __future__ import annotations


class PyTableauError(Exception):
    """Base exception for all pytableau errors."""


# --- File / Package Errors ---


class FileError(PyTableauError):
    """Error related to file I/O operations."""


class InvalidWorkbookError(FileError):
    """The file is not a valid Tableau workbook (.twb or .twbx)."""


class PackageError(FileError):
    """Error extracting or creating a .twbx package."""


class AmbiguousWorkbookError(PackageError):
    """Multiple .twb files found in a TWBX archive with no unambiguous root."""

    def __init__(self, msg: str, candidates: list[str] | None = None) -> None:
        super().__init__(msg)
        self.candidates: list[str] = candidates or []


class InvalidPathError(FileError):
    """A path contains disallowed components (e.g. path traversal via `..`)."""


class CorruptWorkbookError(FileError):
    """The workbook XML is structurally corrupt or unreadable."""


# --- XML / Schema Errors ---


class XMLError(PyTableauError):
    """Error during XML parsing or manipulation."""


class SchemaValidationError(XMLError):
    """An XML mutation would produce invalid Tableau XML."""


class IncompatibleVersionError(XMLError):
    """The operation is not supported for the target Tableau version."""


# --- Semantic Model Errors ---


class FieldError(PyTableauError):
    """Error related to field operations."""


class FieldNotFoundError(FieldError, KeyError):
    """The requested field does not exist in the datasource."""


class DuplicateFieldError(FieldError):
    """A field with this name already exists."""


class FormulaError(FieldError):
    """A calculated field formula is invalid or references unknown fields."""


# --- Datasource Errors ---


class DatasourceError(PyTableauError):
    """Error related to datasource operations."""


class DatasourceNotFoundError(DatasourceError, KeyError):
    """The requested datasource does not exist in the workbook."""


class ConnectionError(DatasourceError):
    """Error related to connection manipulation."""


# --- Data Layer Errors ---


class HyperError(PyTableauError):
    """Error during .hyper file operations."""


class ExtractError(HyperError):
    """Error creating, refreshing, or attaching an extract."""


# --- Server Errors ---


class ServerError(PyTableauError):
    """Error communicating with Tableau Server/Cloud."""


class AuthenticationError(ServerError):
    """Authentication to Tableau Server/Cloud failed."""


class PublishError(ServerError):
    """Error publishing a workbook to Tableau Server/Cloud."""


class LazyNotMaterializedError(PyTableauError):
    """Raised when accessing lazy-loaded collections in streaming mode."""


# --- Template Errors ---


class TemplateError(PyTableauError):
    """Error in template processing."""


class UnmappedPlaceholderError(TemplateError):
    """A template placeholder was not mapped to a real field."""


class TemplateNotFoundError(TemplateError):
    """The specified template does not exist."""


# --- Validation ---


class ValidationIssue:
    """A single validation finding (not necessarily an error).

    Attributes:
        level: One of ``"error"``, ``"warning"``, or ``"info"``.
        message: Human-readable description of the issue.
        path: XPath or logical path to the problematic element.
    """

    __slots__ = ("level", "message", "path")

    def __init__(self, level: str, message: str, path: str = "") -> None:
        self.level = level
        self.message = message
        self.path = path

    def __repr__(self) -> str:
        return f"ValidationIssue({self.level!r}, {self.message!r}, path={self.path!r})"

    def __str__(self) -> str:
        prefix = self.level.upper()
        loc = f" at {self.path}" if self.path else ""
        return f"[{prefix}]{loc}: {self.message}"
