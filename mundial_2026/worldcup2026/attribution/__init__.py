"""Atribución causal de la compresión de varianza (F5). Solo identifica; no corrige."""

from __future__ import annotations

from .components import COMPONENTS, ComponentAblation
from .ensemble_recompose import RecomposeOverrides, recompose_ensemble
from .gate import F5GateThresholds, decide_component_intervention
from .metrics import (
    METRIC_KEYS,
    compute_attribution_metrics,
    raw_expected_penca_pick,
    realized_penca_8_5_3,
)
from .ranking import RANKING_COLUMNS, culpability_ranking
from .walkforward import BY_FOLD_COLUMNS, run_component_walkforward

__all__ = [
    "COMPONENTS", "ComponentAblation", "RecomposeOverrides", "recompose_ensemble",
    "F5GateThresholds", "decide_component_intervention",
    "METRIC_KEYS", "compute_attribution_metrics", "raw_expected_penca_pick", "realized_penca_8_5_3",
    "RANKING_COLUMNS", "culpability_ranking", "BY_FOLD_COLUMNS", "run_component_walkforward",
]
