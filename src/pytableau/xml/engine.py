"""XMLSchemaEngine: validation and version-aware schema rules.

The schema engine is the gatekeeper for all XML mutations in pytableau.
Every change to a workbook's XML tree passes through here before the file
is written, ensuring we never produce a corrupt ``.twb``.

.. note::
    Full implementation is tracked in Phase 1 of the development plan.
    Phase 0 ships the class skeleton and interface contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pytableau.exceptions import ValidationIssue

if TYPE_CHECKING:
    from lxml import etree


class XMLSchemaEngine:
    """Validates XML mutations against known Tableau schema rules.

    The engine operates in a version-aware mode: rules that apply to
    Tableau 2024.x may differ from those for 2022.x.  The ``version``
    parameter controls which rule set is active.

    Args:
        version: Tableau version string (e.g. ``"2024.1"``).  Must be one
            of the versions listed in
            :data:`~pytableau.constants.TABLEAU_VERSION_MAP`.
    """

    def __init__(self, version: str = "2024.1") -> None:
        self.version = version

    def validate_element(
        self,
        tag: str,
        parent_tag: str,
        attributes: dict[str, str],
        version: str | None = None,
    ) -> list[ValidationIssue]:
        """Validate a single XML element in context.

        Args:
            tag: The element tag name (e.g. ``"column"``).
            parent_tag: The tag name of the parent element.
            attributes: Dictionary of attribute name → value pairs.
            version: Override the engine version for this check.

        Returns:
            A (possibly empty) list of :class:`~pytableau.exceptions.ValidationIssue`.
        """
        raise NotImplementedError

    def validate_workbook(self, tree: etree.ElementTree) -> list[ValidationIssue]:
        """Validate a complete workbook XML tree.

        Args:
            tree: The lxml ElementTree representing the full workbook.

        Returns:
            All validation issues found, across every level of severity.
        """
        raise NotImplementedError

    def is_compatible(self, tree: etree.ElementTree, target_version: str) -> bool:
        """Check whether a workbook XML tree is compatible with a given version.

        Args:
            tree: The workbook XML tree to check.
            target_version: The Tableau version to check compatibility against.

        Returns:
            ``True`` if no ERROR-level compatibility issues are found.
        """
        raise NotImplementedError
