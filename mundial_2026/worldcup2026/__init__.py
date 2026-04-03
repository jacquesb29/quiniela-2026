"""Shared modules for the World Cup 2026 model.

This package is introduced in phases so the existing CLI and Pages build
continue to work while the monolith is progressively decomposed.
"""

from .config import ModelHyperparameters, PARAMS
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
    "avg_or_none",
    "brier_decomposition",
    "default_parallel_workers",
    "dynamic_correlation",
    "empty_bracket_aggregate",
    "empty_tournament_summary",
    "merge_bracket_aggregate",
    "merge_tournament_summary",
    "quantize_for_cache",
    "run_parallel_batches",
    "summarize_temporal_windows",
    "top_score_from_distribution",
]
