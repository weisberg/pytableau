"""CorpusAnalyzer: infer schema rules from a corpus of .twb files.

.. note::
    Full implementation is tracked in Phase 6 of the development plan.
"""

from __future__ import annotations

from pathlib import Path
from collections import Counter
from lxml import etree


class CorpusAnalyzer:
    """Analyze a folder of .twb files to infer shared XML structure."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"Corpus path does not exist: {self.path}")

    def _iter_twb_files(self) -> list[Path]:
        if self.path.is_file():
            return [self.path]
        return list(self.path.glob("**/*.twb"))

    def analyze(self) -> dict[str, object]:
        tag_counter: Counter[str] = Counter()
        attr_counter: Counter[str] = Counter()
        files_parsed = 0
        for file in self._iter_twb_files():
            try:
                root = etree.parse(str(file)).getroot()
            except (OSError, etree.XMLSyntaxError):
                continue
            files_parsed += 1
            for node in root.iter():
                tag_counter[node.tag] += 1
                for attr_name in node.attrib:
                    attr_counter[attr_name] += 1

        return {
            "files": files_parsed,
            "tag_counts": dict(tag_counter),
            "attribute_counts": dict(attr_counter),
            "top_tags": [tag for tag, _ in tag_counter.most_common(20)],
        }

    def top_tags(self, limit: int = 20) -> list[str]:
        data = self.analyze()["tag_counts"]
        tags = sorted(data, key=lambda item: data[item], reverse=True)
        return tags[:limit]
