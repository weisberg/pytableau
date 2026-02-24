"""Programmatic viz authoring — build Tableau workbooks from code.

The ``build`` module provides fluent builder APIs for constructing valid
Tableau XML without starting from a pre-existing ``.twb`` file.

Builders
--------

.. autosummary::

    DatasourceBuilder
    WorksheetBuilder
    DashboardBuilder

Spec loader
-----------

.. autosummary::

    from_spec

Shortcuts
---------

.. autosummary::

    quick_chart
    quick_dashboard

Example
-------
::

    from pytableau import Workbook
    from pytableau.build import (
        DatasourceBuilder,
        WorksheetBuilder,
        DashboardBuilder,
        from_spec,
        quick_chart,
    )

    # Builder pattern
    wb = Workbook.new()
    ds = DatasourceBuilder("Sales") \\
        .connection("hyper", dbname="sales.hyper") \\
        .column("Region", "string", "dimension") \\
        .column("Sales", "real", "measure") \\
        .build()
    ws = WorksheetBuilder("Revenue by Region") \\
        .datasource("hyper.sales") \\
        .mark_type("bar") \\
        .rows("Region") \\
        .columns("SUM(Sales)") \\
        .build()

    # One-liner
    wb = quick_chart(dimension="Region", measure="Sales", chart_type="bar")

    # YAML spec
    wb = from_spec("workbook_spec.yml")
"""

from pytableau.build.dashboard import DashboardBuilder
from pytableau.build.datasource import DatasourceBuilder
from pytableau.build.shortcuts import quick_chart, quick_dashboard
from pytableau.build.spec import from_spec
from pytableau.build.worksheet import WorksheetBuilder

__all__ = [
    "DatasourceBuilder",
    "WorksheetBuilder",
    "DashboardBuilder",
    "from_spec",
    "quick_chart",
    "quick_dashboard",
]
