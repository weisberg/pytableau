"""Version-specific schema knowledge for Tableau XML.

Each submodule encodes what pytableau knows about the XML schema for a
particular Tableau version family.  The :class:`~pytableau.xml.engine.XMLSchemaEngine`
selects the appropriate schema module at runtime.
"""

from __future__ import annotations
