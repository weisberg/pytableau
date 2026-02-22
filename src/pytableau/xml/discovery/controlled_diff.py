"""Controlled differ for schema-building experiments."""

from __future__ import annotations

from pathlib import Path
from lxml import etree
from dataclasses import dataclass
from difflib import ndiff


@dataclass
class ControlledDiffer:
    """Compare two workbooks and return line-oriented schema-level diffs."""

    before: str | Path
    after: str | Path

    def _read_lines(self, file: str | Path) -> list[str]:
        return Path(file).read_text(encoding="utf-8").splitlines()

    def diff(self) -> list[str]:
        before_lines = self._read_lines(self.before)
        after_lines = self._read_lines(self.after)
        return [line for line in ndiff(before_lines, after_lines) if line and line[0] in {"+", "-"}]

    def xml_nodes(self) -> dict[str, int]:
        before_tree = etree.parse(str(self.before))
        after_tree = etree.parse(str(self.after))
        before_tags = {node.tag for node in before_tree.getroot().iter()}
        after_tags = {node.tag for node in after_tree.getroot().iter()}
        return {
            "added_tags": len(after_tags - before_tags),
            "removed_tags": len(before_tags - after_tags),
            "shared_tags": len(before_tags & after_tags),
        }

    def summary(self) -> str:
        data = self.xml_nodes()
        return (
            f"Added tags: {data['added_tags']}, Removed tags: {data['removed_tags']}, "
            f"Shared tags: {data['shared_tags']}"
        )
