"""Version-specific schema knowledge for Tableau XML.

Each submodule encodes what pytableau knows about the XML schema for a
particular Tableau version family.  The :class:`~pytableau.xml.engine.XMLSchemaEngine`
selects the appropriate schema module at runtime.

.. note::
    Full implementation is tracked in Phase 1 of the development plan.
"""

from __future__ import annotations
