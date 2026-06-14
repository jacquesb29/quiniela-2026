"""Paquete de auditoría estructural F3 (solo medición; no corrige, no toca el modelo)."""

from __future__ import annotations

from .exact_score import EXACT_COLUMNS, exact_score_audit
from .gate import F3Thresholds, f3_decision
from .goals import GOAL_COLUMNS, TAIL_COLUMNS, goal_calibration, tail_audit
from .penca import PENCA_COLUMNS, outcome_bucket, penca_audit
from .scoreline import (
    DRAW_COLUMNS,
    SCORE_COLUMNS,
    TRACKED_SCORES,
    MatchObservation,
    draw_audit,
    favorite_bucket,
    score_distribution_audit,
    score_total_variation,
)

__all__ = [
    "MatchObservation", "TRACKED_SCORES",
    "SCORE_COLUMNS", "DRAW_COLUMNS", "GOAL_COLUMNS", "TAIL_COLUMNS", "EXACT_COLUMNS", "PENCA_COLUMNS",
    "score_distribution_audit", "score_total_variation", "favorite_bucket", "draw_audit",
    "goal_calibration", "tail_audit", "exact_score_audit", "outcome_bucket", "penca_audit",
    "F3Thresholds", "f3_decision",
]
