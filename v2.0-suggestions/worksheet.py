"""Build worksheet XML elements programmatically.

Example::

    from pytableau.build import WorksheetBuilder

    ws = (
        WorksheetBuilder("Revenue by Region")
        .datasource("hyper.sales_data")
        .mark_type("bar")
        .rows("Region")
        .columns("SUM(Sales)")
        .color("Product Category")
        .sort("SUM(Sales)", descending=True)
        .filter("Year", values=[2024, 2025])
        .build()
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from lxml import etree

from pytableau.constants import FilterType, MarkType
from pytableau.exceptions import InvalidWorkbookError

from ._xml import encode_shelf_field, encode_shelf_list


@dataclass
class _FilterSpec:
    """Internal filter specification."""

    field: str
    filter_type: str
    values: list[str] | None = None
    minimum: float | int | str | None = None
    maximum: float | int | str | None = None
    include_min: bool = True
    include_max: bool = True

    def to_xml(self, parent: etree._Element) -> etree._Element:
        """Append a ``<filter>`` element to *parent*."""
        field_ref = encode_shelf_field(self.field)
        attrs: dict[str, str] = {"class": self.filter_type, "field": field_ref}

        if self.filter_type == FilterType.RANGE.value:
            if self.minimum is not None:
                attrs["min"] = str(self.minimum)
                attrs["include-min"] = "true" if self.include_min else "false"
            if self.maximum is not None:
                attrs["max"] = str(self.maximum)
                attrs["include-max"] = "true" if self.include_max else "false"

        node = etree.SubElement(parent, "filter", attrib=attrs)

        if self.filter_type == FilterType.CATEGORICAL.value and self.values:
            values_el = etree.SubElement(node, "values")
            for v in self.values:
                etree.SubElement(values_el, "value").text = str(v)

        return node


@dataclass
class _SortSpec:
    """Internal sort specification."""

    field: str
    descending: bool = False
    by: str | None = None


class WorksheetBuilder:
    """Fluent builder for ``<worksheet>`` XML elements.

    Parameters:
        name: The worksheet tab name.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._datasource_name: str | None = None
        self._mark_type: str = MarkType.AUTOMATIC.value
        self._rows: list[str] = []
        self._cols: list[str] = []
        self._color: list[str] = []
        self._size: list[str] = []
        self._detail: list[str] = []
        self._tooltip: list[str] = []
        self._label: list[str] = []
        self._filters: list[_FilterSpec] = []
        self._sorts: list[_SortSpec] = []
        self._title: str | None = None

    # -- Datasource binding --------------------------------------------------

    def datasource(self, name: str) -> WorksheetBuilder:
        """Bind this worksheet to a datasource by its internal name.

        The name should match the ``name`` attribute on a ``<datasource>``
        element — for example ``"hyper.sales_data"``.
        """
        self._datasource_name = name
        return self

    # -- Mark type -----------------------------------------------------------

    def mark_type(self, mt: MarkType | str) -> WorksheetBuilder:
        """Set the visualization mark type.

        Accepts a :class:`~pytableau.constants.MarkType` enum or any raw
        string value (``"bar"``, ``"line"``, ``"circle"``, etc.).
        """
        self._mark_type = mt.value if isinstance(mt, MarkType) else str(mt)
        return self

    # -- Shelf methods -------------------------------------------------------

    def rows(self, *fields: str) -> WorksheetBuilder:
        """Append fields to the **Rows** shelf (vertical axis / row grouping).

        Each argument is a field name or aggregated expression::

            .rows("Region")
            .rows("SUM(Sales)", "SUM(Profit)")
        """
        self._rows.extend(fields)
        return self

    def columns(self, *fields: str) -> WorksheetBuilder:
        """Append fields to the **Columns** shelf (horizontal axis).

        Works identically to :meth:`rows`::

            .columns("MONTH(Order Date)")
        """
        self._cols.extend(fields)
        return self

    def color(self, *fields: str) -> WorksheetBuilder:
        """Encode on the **Color** mark channel."""
        self._color.extend(fields)
        return self

    def size(self, *fields: str) -> WorksheetBuilder:
        """Encode on the **Size** mark channel."""
        self._size.extend(fields)
        return self

    def detail(self, *fields: str) -> WorksheetBuilder:
        """Encode on the **Detail** mark channel."""
        self._detail.extend(fields)
        return self

    def tooltip(self, *fields: str) -> WorksheetBuilder:
        """Encode on the **Tooltip** mark channel."""
        self._tooltip.extend(fields)
        return self

    def label(self, *fields: str) -> WorksheetBuilder:
        """Encode on the **Label** mark channel."""
        self._label.extend(fields)
        return self

    # -- Filters -------------------------------------------------------------

    def filter(
        self,
        field: str,
        *,
        values: list[str | int | float] | None = None,
        minimum: float | int | str | None = None,
        maximum: float | int | str | None = None,
        filter_type: FilterType | str | None = None,
    ) -> WorksheetBuilder:
        """Add a filter to the worksheet.

        The filter type is inferred from the arguments if not provided:

        - *values* present → ``categorical``
        - *minimum* / *maximum* present → ``range``

        Args:
            field: Field name to filter.
            values: Explicit values for a categorical filter.
            minimum: Lower bound for a range filter.
            maximum: Upper bound for a range filter.
            filter_type: Override the inferred type.
        """
        if filter_type is not None:
            ft = filter_type.value if isinstance(filter_type, FilterType) else str(filter_type)
        elif values is not None:
            ft = FilterType.CATEGORICAL.value
        elif minimum is not None or maximum is not None:
            ft = FilterType.RANGE.value
        else:
            ft = FilterType.CATEGORICAL.value

        str_values = [str(v) for v in values] if values else None

        self._filters.append(
            _FilterSpec(
                field=field,
                filter_type=ft,
                values=str_values,
                minimum=minimum,
                maximum=maximum,
            )
        )
        return self

    # -- Sort ----------------------------------------------------------------

    def sort(
        self,
        field: str,
        *,
        descending: bool = False,
        by: str | None = None,
    ) -> WorksheetBuilder:
        """Add a sort specification.

        Args:
            field: The field to sort.
            descending: Sort descending (default ascending).
            by: Optional secondary field to sort by.
        """
        self._sorts.append(_SortSpec(field=field, descending=descending, by=by))
        return self

    # -- Title ---------------------------------------------------------------

    def title(self, text: str) -> WorksheetBuilder:
        """Set the worksheet title text."""
        self._title = text
        return self

    # -- Build ---------------------------------------------------------------

    def build(self) -> etree._Element:
        """Generate the ``<worksheet>`` XML element.

        Returns:
            An ``lxml.etree._Element`` ready to append to a workbook.

        Raises:
            InvalidWorkbookError: If the worksheet has no shelf fields.
        """
        if not self._rows and not self._cols:
            raise InvalidWorkbookError(
                f"Worksheet '{self._name}' has no rows or columns defined. "
                "Call .rows() and/or .columns() before .build()."
            )

        ws = etree.Element("worksheet", name=self._name)

        # Mark type (stored as a style attribute)
        if self._mark_type and self._mark_type != MarkType.AUTOMATIC.value:
            style = etree.SubElement(ws, "style", mark=self._mark_type)

        # Rows and Columns shelves
        rows_el = etree.SubElement(ws, "rows")
        rows_el.text = encode_shelf_list(self._rows) if self._rows else ""

        cols_el = etree.SubElement(ws, "cols")
        cols_el.text = encode_shelf_list(self._cols) if self._cols else ""

        # Marks card channels
        marks_el = etree.SubElement(ws, "marks")
        for channel_name, channel_fields in [
            ("color", self._color),
            ("size", self._size),
            ("detail", self._detail),
            ("tooltip", self._tooltip),
            ("label", self._label),
        ]:
            if channel_fields:
                ch = etree.SubElement(marks_el, channel_name)
                ch.text = encode_shelf_list(channel_fields)

        # Filters
        if self._filters:
            filters_el = etree.SubElement(ws, "filters")
            for spec in self._filters:
                spec.to_xml(filters_el)

        # Sorts
        if self._sorts:
            sorts_el = etree.SubElement(ws, "sorts")
            for spec in self._sorts:
                sort_attrs: dict[str, str] = {
                    "field": encode_shelf_field(spec.field),
                    "direction": "DESC" if spec.descending else "ASC",
                }
                if spec.by:
                    sort_attrs["using"] = encode_shelf_field(spec.by)
                etree.SubElement(sorts_el, "sort", attrib=sort_attrs)

        # Datasource dependencies
        if self._datasource_name:
            deps = etree.SubElement(ws, "datasource-dependencies")
            etree.SubElement(deps, "datasource", name=self._datasource_name)

        # Title
        if self._title:
            title_el = etree.SubElement(ws, "title")
            title_el.text = self._title

        return ws

    def raw(self) -> etree._Element:
        """Return the built element (alias for :meth:`build`)."""
        return self.build()
