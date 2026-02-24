"""XMLNodeProxy: safe mutation base class for XML-backed objects.

Every pytableau object that wraps an XML element (Datasource, Worksheet,
Dashboard, etc.) inherits from :class:`XMLNodeProxy`.  The proxy ensures
that mutations go through the validation layer and that raw ``lxml``
access is always available as an escape hatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lxml import etree


class XMLNodeProxy:
    """Base class for all objects backed by a Tableau XML element.

    Subclasses must call ``super().__init__(node)`` with the underlying
    ``lxml`` element.  This class stores a reference to the element and
    exposes it through the :attr:`xml_node` property.

    Args:
        node: The ``lxml`` element this object wraps.
    """

    def __init__(self, node: etree._Element) -> None:
        self._node: etree._Element = node

    @property
    def xml_node(self) -> etree._Element:
        """The underlying ``lxml`` XML element (raw escape hatch)."""
        return self._node
