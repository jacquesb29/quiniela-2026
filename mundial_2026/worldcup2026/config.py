from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelHyperparameters:
    bivariate_correlation_base: float = 0.08
    bivariate_correlation_cap: float = 0.10
    bivariate_shared_goal_share: float = 0.18
    bivariate_closeness_bonus: float = 0.04
    bivariate_knockout_bonus: float = 0.03
    bivariate_importance_bonus: float = 0.02
    low_score_draw_threshold: float = 0.27
    low_score_draw_positive_cap: float = 0.12
    low_score_draw_negative_cap: float = -0.08
    low_score_rho_base: float = -0.16
    low_score_rho_positive_draw: float = -0.55
    low_score_rho_negative_draw: float = 0.20
    low_score_knockout_shift: float = -0.02
    low_score_floor: float = 0.05
    model_contrast_weight: float = 0.18
    model_low_score_base: float = 0.12
    model_low_score_closeness_weight: float = 0.08
    model_low_score_draw_weight: float = 0.45
    model_low_score_knockout_bonus: float = 0.03
    model_low_score_min: float = 0.12
    model_low_score_max: float = 0.28
    model_primary_min: float = 0.40
    model_market_bonus_strength: float = 0.30
    model_consensus_strength: float = 1.0
    confidence_base: float = 0.10
    confidence_top_outcome_weight: float = 0.60
    confidence_gap_weight: float = 0.25
    confidence_top3_weight: float = 0.10
    confidence_entropy_weight: float = 0.10
    confidence_agreement_weight: float = 0.12
    confidence_floor: float = 0.05
    confidence_cap: float = 0.99
    extra_time_share: float = 0.29
    extra_time_fatigue_weight: float = 0.16
    extra_time_availability_weight: float = 0.10
    extra_time_attack_form_weight: float = 0.08
    extra_time_recent_form_weight: float = 0.04
    cache_goal_precision: float = 50.0
    cache_rho_precision: float = 100.0
    temporal_cv_fold_size: int = 8
    auto_parallel_min_iterations: int = 4000
    auto_parallel_max_workers_floor: int = 1


PARAMS = ModelHyperparameters()
