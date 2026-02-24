"""Phase 0 smoke tests: verify the package imports cleanly.

These tests constitute the Phase 0 acceptance criterion:
  "pip install pytableau works, imports cleanly, does nothing yet."
"""

from __future__ import annotations

import importlib


def test_pytableau_imports() -> None:
    """The top-level package must import without error."""
    import pytableau  # noqa: F401


def test_version_is_defined() -> None:
    """__version__ must be a non-empty string."""
    from pytableau import __version__

    assert isinstance(__version__, str)
    assert __version__


def test_constants_import() -> None:
    """All enums in constants.py must be importable."""
    from pytableau.constants import (
        AggregationType,
        ConnectionType,
        DataType,
        FilterType,
        MarkType,
        ParameterDomainType,
        Role,
        SortOrder,
        SortType,
        ValidationLevel,
        ZoneType,
    )

    assert MarkType.BAR == "bar"
    assert MarkType.SHAPE == "shape"
    assert MarkType.GANTT == "gantt_rounded"
    assert MarkType.GANTT_BAR == "gantt_rounded"  # alias
    assert DataType.STRING == "string"
    assert Role.DIMENSION == "dimension"
    assert FilterType.CATEGORICAL == "categorical"
    assert FilterType.WILDCARD == "wildcard"
    assert FilterType.ALL == "all"
    assert AggregationType.SUM == "Sum"
    assert AggregationType.STDEV == "Stdev"
    assert AggregationType.VAR == "Var"
    assert SortOrder.DESCENDING == "desc"
    assert SortOrder.NONE == "none"
    assert ConnectionType.HYPER == "hyper"
    assert ConnectionType.SQLSERVER == "sqlserver"
    assert ConnectionType.MSSQL == "sqlserver"  # alias
    assert ConnectionType.TABLEAU_SERVER == "tableau-server"
    assert ValidationLevel.ERROR == "error"
    assert SortType.ALPHABETIC == "alphabetic"
    assert ZoneType.WORKSHEET == "worksheet"
    assert ZoneType.LEGEND == "legend"
    assert ZoneType.FILTER == "filter"
    assert ZoneType.PARAMETER == "parameter"
    assert ZoneType.EXTENSION == "extension"
    assert ParameterDomainType.ALL == "all"


def test_exceptions_import() -> None:
    """All exception classes must be importable from the top-level package."""
    from pytableau import (
        DatasourceError,
        DatasourceNotFoundError,
        FieldError,
        FieldNotFoundError,
        FileError,
        InvalidWorkbookError,
        PyTableauError,
        SchemaValidationError,
        XMLError,
    )

    # Verify inheritance
    assert issubclass(InvalidWorkbookError, FileError)
    assert issubclass(FileError, PyTableauError)
    assert issubclass(SchemaValidationError, XMLError)
    assert issubclass(FieldNotFoundError, FieldError)
    assert issubclass(FieldNotFoundError, KeyError)
    assert issubclass(DatasourceNotFoundError, DatasourceError)
    assert issubclass(DatasourceNotFoundError, KeyError)


def test_validation_issue() -> None:
    """ValidationIssue must format correctly."""
    from pytableau import ValidationIssue

    issue = ValidationIssue("error", "missing required element", "/workbook/datasource")
    assert str(issue) == "[ERROR] at /workbook/datasource: missing required element"

    issue_no_path = ValidationIssue("warning", "unusual structure")
    assert str(issue_no_path) == "[WARNING]: unusual structure"


def test_compat_import() -> None:
    """_compat.import_optional must return a stub for a missing module."""
    from pytableau._compat import _MissingDependency, import_optional

    stub = import_optional("_nonexistent_module_xyz", "hyper")
    assert isinstance(stub, _MissingDependency)

    try:
        _ = stub.some_attr
        raise AssertionError("Should have raised ImportError")
    except ImportError as exc:
        assert "pytableau[hyper]" in str(exc)


def test_submodules_importable() -> None:
    """Every subpackage __init__ must be importable."""
    submodules = [
        "pytableau.core",
        "pytableau.xml",
        "pytableau.xml.schemas",
        "pytableau.xml.discovery",
        "pytableau.data",
        "pytableau.package",
        "pytableau.templates",
        "pytableau.templates.library",
        "pytableau.server",
        "pytableau.inspect",
    ]
    for name in submodules:
        mod = importlib.import_module(name)
        assert mod is not None, f"{name} failed to import"


def test_template_library_builtin_names() -> None:
    """BUILTIN_TEMPLATES must list the expected template names."""
    from pytableau.templates.library import BUILTIN_TEMPLATES

    expected = {
        "bar_chart",
        "line_chart",
        "scatter_plot",
        "heatmap",
        "treemap",
        "map",
        "kpi_dashboard",
        "stacked_bar",
        "dual_axis",
        "area_chart",
    }
    assert set(BUILTIN_TEMPLATES) == expected


def test_template_not_found_error() -> None:
    """get_template_path must raise TemplateNotFoundError for unknown names."""
    from pytableau.exceptions import TemplateNotFoundError
    from pytableau.templates.library import get_template_path

    try:
        get_template_path("nonexistent_template")
        raise AssertionError("Should have raised TemplateNotFoundError")
    except TemplateNotFoundError:
        pass


def test_package_manager_helpers() -> None:
    """is_twb / is_twbx helpers must classify paths correctly."""
    from pathlib import Path

    from pytableau.package.manager import is_twb, is_twbx

    assert is_twb(Path("my_workbook.twb"))
    assert not is_twb(Path("my_workbook.twbx"))
    assert not is_twbx(Path("my_workbook.twb"))
    # is_twbx also checks zipfile.is_zipfile, so a plain .twbx path that
    # doesn't exist is False (not a valid zip).
    assert not is_twbx(Path("my_workbook.twbx"))


def test_xml_node_proxy() -> None:
    """XMLNodeProxy must store and expose the lxml element."""
    from lxml import etree

    from pytableau.xml.proxy import XMLNodeProxy

    node = etree.Element("workbook")
    proxy = XMLNodeProxy(node)
    assert proxy.xml_node is node


def test_placeholder_pattern() -> None:
    """PLACEHOLDER_PATTERN must match valid template placeholder names."""
    import re

    from pytableau.templates.mapping import PLACEHOLDER_PATTERN

    assert re.fullmatch(PLACEHOLDER_PATTERN, "__DIMENSION__")
    assert re.fullmatch(PLACEHOLDER_PATTERN, "__PARAM_TITLE__")
    assert not re.fullmatch(PLACEHOLDER_PATTERN, "no_underscores")
    assert not re.fullmatch(PLACEHOLDER_PATTERN, "__lowercase__")
