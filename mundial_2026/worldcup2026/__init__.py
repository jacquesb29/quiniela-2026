"""Shared modules for the World Cup 2026 model.

This package is introduced in phases so the existing CLI and Pages build
continue to work while the monolith is progressively decomposed.
"""

from .calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
    empirical_bayes_shrinkage,
    prediction_confidence_interval,
    shrink_probability,
    walk_forward_validation,
)
from .config import ModelHyperparameters, PARAMS
from .data import (
    TeamState,
    coerce_team_state,
    copy_states,
    default_team_state,
    initial_team_states,
    normalize_team_state,
    state_has_activity,
)
from .dashboard import render_dashboard_html
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
from .logging_utils import log, setup_logger
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
from .simulation import FastRNG, fast_random, poisson_sample_fast, seed_fast_rng
from .types import BacktestMetrics, KnockoutResolution, ModelOutput

__all__ = [
    "BacktestMetrics",
    "FastRNG",
    "IsotonicCalibrator",
    "KnockoutResolution",
    "ModelHyperparameters",
    "ModelOutput",
    "PARAMS",
    "PlattCalibrator",
    "TeamState",
    "adaptive_ensemble_weights",
    "apply_outcome_target_shrink",
    "avg_or_none",
    "blend_distributions",
    "brier_decomposition",
    "build_model_stack",
    "cached_low_score_distribution",
    "coerce_team_state",
    "default_parallel_workers",
    "default_team_state",
    "dixon_coles_tau",
    "dynamic_correlation",
    "empirical_bayes_shrinkage",
    "empty_bracket_aggregate",
    "empty_tournament_summary",
    "fast_random",
    "independent_score_distribution",
    "initial_team_states",
    "low_score_adjusted_distribution",
    "low_score_rho",
    "log",
    "merge_bracket_aggregate",
    "merge_tournament_summary",
    "model_blend_weights",
    "normalize_team_state",
    "outcome_probabilities_from_distribution",
    "poisson_prob",
    "poisson_sample_fast",
    "prediction_confidence_interval",
    "quantize_for_cache",
    "render_dashboard_html",
    "run_parallel_batches",
    "score_distribution",
    "seed_fast_rng",
    "setup_logger",
    "shrink_probability",
    "state_has_activity",
    "summarize_temporal_windows",
    "top_score_from_distribution",
    "walk_forward_validation",
]
