"""Shared modules for the World Cup 2026 model.

This package is introduced in phases so the existing CLI and Pages build
continue to work while the monolith is progressively decomposed.
"""

from .config import ModelHyperparameters, PARAMS
from .distributions import (
    apply_outcome_target_shrink,
    blend_distributions,
    build_model_stack,
    cached_low_score_distribution,
    dixon_coles_tau,
    independent_score_distribution,
    low_score_adjusted_distribution,
    low_score_rho,
    model_blend_weights,
    outcome_probabilities_from_distribution,
    poisson_prob,
    score_distribution,
)
from .metrics import avg_or_none, brier_decomposition, summarize_temporal_windows
from .modeling import (
    adaptive_ensemble_weights,
    dynamic_correlation,
    quantize_for_cache,
    top_score_from_distribution,
)
from .parallel import (
    default_parallel_workers,
    empty_bracket_aggregate,
    empty_tournament_summary,
    merge_bracket_aggregate,
    merge_tournament_summary,
    run_parallel_batches,
)
from .types import BacktestMetrics, KnockoutResolution, ModelOutput

__all__ = [
    "BacktestMetrics",
    "KnockoutResolution",
    "ModelHyperparameters",
    "ModelOutput",
    "PARAMS",
    "adaptive_ensemble_weights",
    "apply_outcome_target_shrink",
    "avg_or_none",
    "blend_distributions",
    "brier_decomposition",
    "build_model_stack",
    "cached_low_score_distribution",
    "default_parallel_workers",
    "dixon_coles_tau",
    "dynamic_correlation",
    "empty_bracket_aggregate",
    "empty_tournament_summary",
    "independent_score_distribution",
    "low_score_adjusted_distribution",
    "low_score_rho",
    "merge_bracket_aggregate",
    "merge_tournament_summary",
    "model_blend_weights",
    "outcome_probabilities_from_distribution",
    "poisson_prob",
    "quantize_for_cache",
    "run_parallel_batches",
    "score_distribution",
    "summarize_temporal_windows",
    "top_score_from_distribution",
]
