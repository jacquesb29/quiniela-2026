from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

from .config import PARAMS
from .types import ModelOutput


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def quantize_for_cache(value: float, precision: Optional[float] = None) -> int:
    scale = precision if precision is not None else PARAMS.cache_goal_precision
    return int(round(float(value) * scale))


def dynamic_correlation(mu_a: float, mu_b: float, ctx: object | None = None) -> float:
    closeness = clamp(1.0 - abs(mu_a - mu_b) / max(mu_a + mu_b, 1.0), 0.0, 1.0)
    draw_signal = 0.0
    importance = 1.0
    knockout = False
    if ctx:
        knockout = bool(getattr(ctx, "knockout", False))
        importance = float(getattr(ctx, "importance", 1.0))
        market_prob_draw = getattr(ctx, "market_prob_draw", None)
        if market_prob_draw is not None:
            draw_signal = clamp(
                float(market_prob_draw) - PARAMS.low_score_draw_threshold,
                PARAMS.low_score_draw_negative_cap,
                PARAMS.low_score_draw_positive_cap,
            )
    base = PARAMS.bivariate_correlation_base
    base += PARAMS.bivariate_closeness_bonus * closeness
    base += PARAMS.bivariate_importance_bonus * max(importance - 1.0, 0.0)
    base += 0.04 * max(draw_signal, 0.0)
    if knockout:
        base += PARAMS.bivariate_knockout_bonus
    return clamp(
        base,
        0.0,
        min(
            PARAMS.bivariate_correlation_cap,
            mu_a * 0.25,
            mu_b * 0.25,
        ),
    )


def top_score_from_distribution(dist: Dict[Tuple[int, int], float]) -> Tuple[str, float]:
    if not dist:
        return ("0-0", 0.0)
    (goals_a, goals_b), prob = max(dist.items(), key=lambda item: item[1])
    return (f"{goals_a}-{goals_b}", float(prob))


def adaptive_ensemble_weights(
    models: Sequence[ModelOutput],
    market_probs: Optional[Dict[str, float]] = None,
) -> list[float]:
    if not models:
        return []
    if len(models) == 1:
        return [1.0]

    base_weights = [model.weight for model in models]
    total_base = sum(base_weights) or 1.0
    consensus = {
        key: sum(model.probs.get(key, 0.0) * weight for model, weight in zip(models, base_weights)) / total_base
        for key in ("a", "draw", "b")
    }
    adjusted_weights = []
    for model in models:
        distance = 0.5 * sum(
            abs(float(model.probs.get(key, 0.0)) - float(consensus[key]))
            for key in ("a", "draw", "b")
        )
        agreement_multiplier = clamp(1.0 - distance * PARAMS.model_consensus_strength, 0.55, 1.25)
        market_multiplier = 1.0
        if market_probs:
            market_distance = 0.5 * sum(
                abs(float(model.probs.get(key, 0.0)) - float(market_probs.get(key, 0.0)))
                for key in ("a", "draw", "b")
            )
            market_multiplier = clamp(1.0 - market_distance * PARAMS.model_market_bonus_strength, 0.70, 1.10)
        adjusted_weights.append(model.weight * agreement_multiplier * market_multiplier)
    total = sum(adjusted_weights)
    if total <= 0.0:
        return [weight / total_base for weight in base_weights]
    return [weight / total for weight in adjusted_weights]
