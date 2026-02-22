"""Optional dependency import helpers.

Provides clear error messages when optional extras are not installed.
"""

from __future__ import annotations

import importlib
from typing import Any


class _MissingDependency:
    """Placeholder that raises ImportError on any attribute access."""

    def __init__(self, name: str, extra: str) -> None:
        self._name = name
        self._extra = extra

    def __getattr__(self, attr: str) -> Any:
        raise ImportError(
            f"{self._name} is required for this feature. "
            f"Install it with: pip install pytableau[{self._extra}]"
        )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise ImportError(
            f"{self._name} is required for this feature. "
            f"Install it with: pip install pytableau[{self._extra}]"
        )


def import_optional(module_name: str, extra: str) -> Any:
    """Import an optional dependency, returning a stub if unavailable.

    Args:
        module_name: Fully qualified module name (e.g. ``"tableauhyperapi"``).
        extra: The pip extra that provides this dependency (e.g. ``"hyper"``).

    Returns:
        The imported module, or a :class:`_MissingDependency` stub that raises
        a helpful :class:`ImportError` on first use.
    """
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return _MissingDependency(module_name, extra)
