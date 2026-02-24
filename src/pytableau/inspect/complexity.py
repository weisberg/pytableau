"""Workbook complexity analysis — #73."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytableau.core.workbook import Workbook

_LOD_RE = re.compile(r"\b(FIXED|INCLUDE|EXCLUDE)\b", re.IGNORECASE)
_NESTED_LOD_RE = re.compile(
    r"\b(FIXED|INCLUDE|EXCLUDE)\b.*\b(FIXED|INCLUDE|EXCLUDE)\b", re.IGNORECASE | re.DOTALL
)


@dataclass
class ComplexityConfig:
    lod_score: int = 5
    nested_lod_bonus: int = 10
    calc_score: int = 2
    live_connection_score: int = 3
    parameter_score: int = 1
    action_score: int = 1


@dataclass
class ComplexityReport:
    total_score: int
    breakdown: dict
    recommendations: list[str]
    grade: str

    def to_dict(self) -> dict:
        return {
            "total_score": self.total_score,
            "grade": self.grade,
            "breakdown": self.breakdown,
            "recommendations": self.recommendations,
        }


def _grade(score: int) -> str:
    if score < 20:
        return "A"
    if score < 50:
        return "B"
    if score < 100:
        return "C"
    if score < 200:
        return "D"
    return "F"


def analyze_complexity(
    workbook: Workbook, config: ComplexityConfig | None = None
) -> ComplexityReport:
    """Analyze the complexity of *workbook* and return a :class:`ComplexityReport`."""
    cfg = config or ComplexityConfig()

    lod_count = 0
    nested_lod_count = 0
    calc_count = 0
    live_connections = 0
    parameter_count = 0
    action_count = 0

    for ds in workbook.datasources:
        for calc in ds.calculated_fields:
            calc_count += 1
            formula = calc.formula or ""
            lods = _LOD_RE.findall(formula)
            lod_count += len(lods)
            if _NESTED_LOD_RE.search(formula):
                nested_lod_count += 1

        for conn in ds.connections:
            cls = conn.class_ or ""
            if cls.lower() not in {"hyper", "excel-direct", "textscan", "csv"}:
                live_connections += 1

    if workbook.parameters is not None:
        parameter_count = len(workbook.parameters.parameters)

    for dashboard in workbook.dashboards:
        action_count += len(dashboard.actions)

    total = (
        lod_count * cfg.lod_score
        + nested_lod_count * cfg.nested_lod_bonus
        + calc_count * cfg.calc_score
        + live_connections * cfg.live_connection_score
        + parameter_count * cfg.parameter_score
        + action_count * cfg.action_score
    )

    breakdown = {
        "lod_expressions": lod_count,
        "nested_lod_expressions": nested_lod_count,
        "calculated_fields": calc_count,
        "live_connections": live_connections,
        "parameters": parameter_count,
        "dashboard_actions": action_count,
    }

    recommendations: list[str] = []
    if nested_lod_count > 0:
        recommendations.append(
            f"Found {nested_lod_count} nested LOD expression(s); consider simplifying."
        )
    if lod_count > 10:
        recommendations.append(
            f"High LOD expression count ({lod_count}); consider extracts for performance."
        )
    if live_connections > 3:
        recommendations.append(
            f"{live_connections} live connections detected; consider consolidating."
        )

    return ComplexityReport(
        total_score=total,
        breakdown=breakdown,
        recommendations=recommendations,
        grade=_grade(total),
    )
