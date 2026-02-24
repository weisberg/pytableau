"""Template engine for parameterized workbook generation."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from lxml import etree

from pytableau.exceptions import UnmappedPlaceholderError
from pytableau.templates.mapping import (
    FieldMapping,
    find_placeholders,
    is_placeholder,
)


class TemplateEngine:
    """Operate on a workbook XML tree and replace placeholder tokens."""

    def __init__(self, tree: etree._ElementTree | etree._Element | Path | str) -> None:
        if isinstance(tree, str | Path):
            self._tree = etree.parse(str(tree))
        elif isinstance(tree, etree._ElementTree):
            self._tree = tree
        else:
            self._tree = etree.ElementTree(tree)

    @property
    def tree(self) -> etree._ElementTree:
        return self._tree

    def discover_placeholders(self) -> set[str]:
        """Scan the template for unresolved placeholders."""
        tokens: set[str] = set()
        for node in self._tree.iter():
            if node.tag is etree.Comment:
                continue
            tokens.update(find_placeholders(node.tag))
            if node.text:
                tokens.update(find_placeholders(node.text))
            if node.tail:
                tokens.update(find_placeholders(node.tail))
            for value in node.attrib.values():
                tokens.update(find_placeholders(value))
        return tokens

    def map_fields(self, mapping: dict[str, str], *, strict: bool = True) -> TemplateEngine:
        """Replace placeholders with concrete field names.\n\n        Example: ``{\"__MEASURE__\": \"Sales\"}``.\n"""
        if any(not is_placeholder(key) for key in mapping):
            bad = [key for key in mapping if not is_placeholder(key)]
            raise ValueError(f"Invalid placeholder keys: {bad}")

        field_mapping = FieldMapping(dict(mapping))
        self._apply_mapping(field_mapping)
        unresolved = self.discover_placeholders()
        if strict and unresolved:
            raise UnmappedPlaceholderError(
                "Template still contains unmapped placeholders: " + ", ".join(sorted(unresolved))
            )
        return self

    def replace_datasource_placeholders(
        self, mapping: dict[str, str], *, strict: bool = True
    ) -> TemplateEngine:
        """Replace datasource placeholders in names/ids as part of template wiring."""
        if any(not is_placeholder(key) for key in mapping):
            bad = [key for key in mapping if not is_placeholder(key)]
            raise ValueError(f"Invalid placeholder keys: {bad}")

        self._apply_mapping(FieldMapping(dict(mapping)))
        unresolved = self.discover_placeholders()
        if strict and unresolved:
            raise UnmappedPlaceholderError(
                "Template still contains unmapped datasource placeholders: "
                + ", ".join(sorted(unresolved))
            )
        return self

    def _apply_mapping(self, mapping: FieldMapping) -> None:
        for node in self._tree.iter():
            if node.tag is etree.Comment:
                continue
            if node.tag:
                node.tag = mapping.apply(str(node.tag))
            node_text = node.text or ""
            node_tail = node.tail or ""
            if node_text:
                node.text = mapping.apply(node_text)
            if node_tail:
                node.tail = mapping.apply(node_tail)

            for key, value in list(node.attrib.items()):
                replaced_key = mapping.apply(key)
                replaced_value = mapping.apply(value)
                if replaced_key == key and replaced_value == value:
                    continue
                node.attrib.pop(key)
                node.attrib[replaced_key] = replaced_value

    def _iter_fields(self) -> Iterable[str]:
        for node in self._tree.iter():
            if node.tag is etree.Comment:
                continue
            if node.tag in {"field", "column", "connection", "datasource"}:
                for key in ("name", "caption", "dbname", "path", "filename"):
                    value = node.get(key)
                    if value:
                        yield value

    def map_datasource(self, mapping: dict[str, str], *, strict: bool = True) -> TemplateEngine:
        """Backward-compatible alias for datasource placeholder replacement."""
        if not mapping:
            return self

        self._apply_mapping(FieldMapping(dict(mapping)))
        unresolved = self.discover_placeholders()
        if strict and unresolved:
            unresolved_ds = [token for token in unresolved if any(ch.isupper() for ch in token)]
            if unresolved_ds:
                raise UnmappedPlaceholderError(
                    "Template still contains unresolved datasource placeholders: "
                    + ", ".join(sorted(unresolved_ds))
                )
        return self

    def validate_all_mapped(self) -> None:
        """Raise if any ``__PLACEHOLDER__`` token remains in template XML."""
        unresolved = self.discover_placeholders()
        if unresolved:
            raise UnmappedPlaceholderError(
                "Template placeholders remain unresolved: " + ", ".join(sorted(unresolved))
            )

    def replace_datasource(self, old_name: str, new_node: etree._Element) -> None:
        """Replace a datasource element in the template by its ``name`` attribute.

        Args:
            old_name: The ``name`` attribute of the datasource to replace.
            new_node: The replacement lxml :class:`~lxml.etree._Element`.

        Raises:
            KeyError: If no datasource with *old_name* is found.
        """
        root = self._tree.getroot()
        for ds in root.findall(".//datasources/datasource"):
            if ds.get("name") == old_name:
                parent = ds.getparent()
                if parent is None:
                    raise KeyError(f"Datasource {old_name!r} has no parent element.")
                idx = list(parent).index(ds)
                parent.remove(ds)
                parent.insert(idx, new_node)
                return
        raise KeyError(f"Datasource {old_name!r} not found in template.")
