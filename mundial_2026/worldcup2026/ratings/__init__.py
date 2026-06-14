"""Subpaquete de auditoría de ratings (F2.1): detección de Elo stale/inconsistente.

No toca el modelo, pesos, lambdas, metodología ni Penca. No aplica ningún ajuste.
"""

from __future__ import annotations

from .activity import (
    RecentActivity,
    activity_level,
    compute_activity_table,
    is_official,
    load_match_history,
)
from .staleness import (
    ACTION_DOMINATE,
    ACTION_SHRINK_FIFA,
    DEFAULT_WEIGHTS,
    REPORT_COLUMNS,
    PoolStats,
    assess_team_staleness,
    compute_pool_stats,
    effective_elo_staleness_aware,
    elo_staleness_score,
    elo_vs_fifa_gap,
    fifa_implied_elo,
    recommended_action,
    staleness_bucket,
    staleness_shrunk_elo,
)

__all__ = [
    "ACTION_DOMINATE",
    "ACTION_SHRINK_FIFA",
    "DEFAULT_WEIGHTS",
    "REPORT_COLUMNS",
    "PoolStats",
    "assess_team_staleness",
    "compute_pool_stats",
    "elo_staleness_score",
    "elo_vs_fifa_gap",
    "fifa_implied_elo",
    "recommended_action",
    "staleness_bucket",
    "staleness_shrunk_elo",
    "effective_elo_staleness_aware",
    "RecentActivity",
    "activity_level",
    "compute_activity_table",
    "is_official",
    "load_match_history",
]
