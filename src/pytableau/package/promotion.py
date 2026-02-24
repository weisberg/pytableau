"""Workbook promotion between environments — #78."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    pass


@dataclass
class EnvironmentSpec:
    name: str
    server: str | None = None
    dbname: str | None = None
    username: str | None = None
    port: int | None = None
    connection_class: str | None = None


@dataclass
class PromotionConfig:
    environments: dict[str, EnvironmentSpec] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> PromotionConfig:
        """Build a :class:`PromotionConfig` from a plain dictionary.

        Expected format::

            {
                "environments": {
                    "dev": {"server": "dev.example.com", "dbname": "sales_dev"},
                    "prod": {"server": "prod.example.com", "dbname": "sales_prod"},
                }
            }
        """
        envs: dict[str, EnvironmentSpec] = {}
        for name, spec in d.get("environments", {}).items():
            envs[name] = EnvironmentSpec(
                name=name,
                server=spec.get("server"),
                dbname=spec.get("dbname"),
                username=spec.get("username"),
                port=int(spec["port"]) if spec.get("port") is not None else None,
                connection_class=spec.get("connection_class"),
            )
        return cls(environments=envs)

    @classmethod
    def from_yaml(cls, path: str) -> PromotionConfig:
        """Load a :class:`PromotionConfig` from a YAML file.

        Requires ``pyyaml``: ``pip install pyyaml``.
        """
        try:
            import yaml  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required to load promotion configs from YAML. "
                "Install it with: pip install pyyaml"
            ) from exc

        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return cls.from_dict(data or {})


class PromotionChange(NamedTuple):
    datasource: str
    connection: int
    attribute: str
    old_value: str | None
    new_value: str | None
