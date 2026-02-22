"""Field-mapping helpers used by the template engine."""

from __future__ import annotations

import re
from dataclasses import dataclass


_PLACEHOLDER_RE = re.compile(r"__[A-Z][A-Z0-9_]*__")

#: Regex pattern that matches template placeholder names.
PLACEHOLDER_PATTERN = r"__[A-Z][A-Z0-9_]*__"


@dataclass(frozen=True)
class FieldMapping:
    """A collection of user-provided placeholder mappings.

    The mapping keys are placeholder tokens (for example ``__DIMENSION__``)
    and the values are replacement strings.
    """

    values: dict[str, str]

    def __post_init__(self) -> None:
        self._validate_inputs()

    def _validate_inputs(self) -> None:
        for key in self.values:
            if not is_placeholder(key):
                raise ValueError(
                    f"Invalid placeholder {key!r}; expected pattern {PLACEHOLDER_PATTERN!r}"
                )

    def keys(self) -> list[str]:
        return list(self.values.keys())

    def items(self) -> list[tuple[str, str]]:
        return list(self.values.items())

    def unresolved(self, values: list[str] | set[str]) -> set[str]:
        """Return placeholder tokens that are used but not mapped."""
        unresolved: set[str] = set()
        for value in values:
            for token in find_placeholders(value):
                if token not in self.values:
                    unresolved.add(token)
        return unresolved

    def apply(self, value: str) -> str:
        """Apply all mappings to one value."""
        out = value
        for placeholder, replacement in self.values.items():
            if placeholder in out:
                out = out.replace(placeholder, replacement)
        return out


def is_placeholder(value: str) -> bool:
    """Return True when *value* is a template placeholder token."""
    return bool(re.fullmatch(PLACEHOLDER_PATTERN, value))


def find_placeholders(value: str) -> set[str]:
    """Extract placeholder tokens from a string."""
    return set(_PLACEHOLDER_RE.findall(value))
