from __future__ import annotations

import math
from functools import lru_cache
from typing import Dict, Optional, Sequence, Tuple

from .config import PARAMS
from .modeling import (
    adaptive_ensemble_weights,
    clamp,
    dynamic_correlation,
    quantize_for_cache,
    top_score_from_distribution,
)
from .types import ModelOutput

FACTORIALS = [math.factorial(i) for i in range(16)]


def poisson_prob(goals: int, mu: float) -> float:
    if goals < 0:
        return 0.0
    mu = max(mu, 0.001)
    factorial = FACTORIALS[goals] if goals < len(FACTORIALS) else math.factorial(goals)
    return math.exp(-mu) * (mu ** goals) / factorial


@lru_cache(maxsize=65536)
def cached_primary_score_distribution(
    mu_a_key: int,
    mu_b_key: int,
    knockout_key: int,
    importance_key: int,
    draw_key: int,
    max_goals: int,
) -> Dict[Tuple[int, int], float]:
    mu_a = mu_a_key / PARAMS.cache_goal_precision
    mu_b = mu_b_key / PARAMS.cache_goal_precision
    ctx = None
    if knockout_key or importance_key or draw_key:
        from types import SimpleNamespace

        ctx = SimpleNamespace(
            knockout=bool(knockout_key),
            importance=float(importance_key) / 100.0,
            market_prob_draw=PARAMS.low_score_draw_threshold + draw_key / PARAMS.cache_rho_precision,
        )
    lambda3 = dynamic_correlation(mu_a, mu_b, ctx)
    dist: Dict[Tuple[int, int], float] = {}
    total = 0.0
    for goals_a in range(max_goals + 1):
        for goals_b in range(max_goals + 1):
            subtotal = 0.0
            limit = min(goals_a, goals_b)
            for shared_goals in range(limit + 1):
                subtotal += (
                    poisson_prob(goals_a - shared_goals, max(mu_a - lambda3, 0.001))
                    * poisson_prob(goals_b - shared_goals, max(mu_b - lambda3, 0.001))
                    * poisson_prob(shared_goals, max(lambda3, 0.0001))
                )
            dist[(goals_a, goals_b)] = subtotal
            total += subtotal
    if total == 0.0:
        return dist
    for key in list(dist):
        dist[key] /= total
    return dist


def score_distribution(
    mu_a: float,
    mu_b: float,
    max_goals: int = 10,
    ctx: object | None = None,
) -> Dict[Tuple[int, int], float]:
    knockout_key = 1 if ctx and getattr(ctx, "knockout", False) else 0
    importance_key = int(round(float(getattr(ctx, "importance", 1.0)) * 100.0)) if ctx else 100
    draw_key = 0
    if ctx and getattr(ctx, "market_prob_draw", None) is not None:
        draw_signal = clamp(
            float(getattr(ctx, "market_prob_draw")) - PARAMS.low_score_draw_threshold,
            PARAMS.low_score_draw_negative_cap,
            PARAMS.low_score_draw_positive_cap,
        )
        draw_key = int(round(draw_signal * PARAMS.cache_rho_precision))
    return cached_primary_score_distribution(
        quantize_for_cache(mu_a),
        quantize_for_cache(mu_b),
        knockout_key,
        importance_key,
        draw_key,
        max_goals,
    )


@lru_cache(maxsize=65536)
def cached_independent_score_distribution(
    mu_a_key: int,
    mu_b_key: int,
    max_goals: int,
) -> Dict[Tuple[int, int], float]:
    mu_a = mu_a_key / PARAMS.cache_goal_precision
    mu_b = mu_b_key / PARAMS.cache_goal_precision
    dist: Dict[Tuple[int, int], float] = {}
    total = 0.0
    for goals_a in range(max_goals + 1):
        prob_a = poisson_prob(goals_a, mu_a)
        for goals_b in range(max_goals + 1):
            prob = prob_a * poisson_prob(goals_b, mu_b)
            dist[(goals_a, goals_b)] = prob
            total += prob
    if total == 0.0:
        return dist
    for key in list(dist):
        dist[key] /= total
    return dist


def independent_score_distribution(mu_a: float, mu_b: float, max_goals: int = 10) -> Dict[Tuple[int, int], float]:
    return cached_independent_score_distribution(
        quantize_for_cache(mu_a),
        quantize_for_cache(mu_b),
        max_goals,
    )


def low_score_rho(mu_a: float, mu_b: float, ctx: object | None = None) -> float:
    closeness = clamp(1.0 - abs(mu_a - mu_b) / max(mu_a + mu_b, 1.0), 0.0, 1.0)
    draw_signal = 0.0
    if ctx and getattr(ctx, "market_prob_draw", None) is not None:
        draw_signal = clamp(
            float(getattr(ctx, "market_prob_draw")) - PARAMS.low_score_draw_threshold,
            PARAMS.low_score_draw_negative_cap,
            PARAMS.low_score_draw_positive_cap,
        )
    rho = (
        PARAMS.low_score_rho_base * closeness
        + PARAMS.low_score_rho_positive_draw * max(draw_signal, 0.0)
        + PARAMS.low_score_rho_negative_draw * min(draw_signal, 0.0)
    )
    if ctx and getattr(ctx, "knockout", False):
        rho += PARAMS.low_score_knockout_shift
    return clamp(rho, -0.22, 0.08)


def dixon_coles_tau(x: int, y: int, mu_a: float, mu_b: float, rho: float) -> float:
    if x == 0 and y == 0:
        return max(PARAMS.low_score_floor, 1.0 - mu_a * mu_b * rho)
    if x == 0 and y == 1:
        return max(PARAMS.low_score_floor, 1.0 + mu_a * rho)
    if x == 1 and y == 0:
        return max(PARAMS.low_score_floor, 1.0 + mu_b * rho)
    if x == 1 and y == 1:
        return max(PARAMS.low_score_floor, 1.0 - rho)
    return 1.0


def low_score_adjusted_distribution(
    mu_a: float,
    mu_b: float,
    ctx: object | None = None,
    max_goals: int = 10,
) -> Dict[Tuple[int, int], float]:
    rho = low_score_rho(mu_a, mu_b, ctx)
    base = independent_score_distribution(mu_a, mu_b, max_goals=max_goals)
    total = 0.0
    for (goals_a, goals_b), prob in list(base.items()):
        adjusted = prob * dixon_coles_tau(goals_a, goals_b, mu_a, mu_b, rho)
        base[(goals_a, goals_b)] = max(adjusted, 0.0)
        total += base[(goals_a, goals_b)]
    if total == 0.0:
        return base
    for key in list(base):
        base[key] /= total
    return base


def outcome_probabilities_from_distribution(dist: Dict[Tuple[int, int], float]) -> Dict[str, float]:
    win_a = 0.0
    draw = 0.0
    win_b = 0.0
    for (goals_a, goals_b), prob in dist.items():
        if goals_a > goals_b:
            win_a += prob
        elif goals_a == goals_b:
            draw += prob
        else:
            win_b += prob
    return {"a": win_a, "draw": draw, "b": win_b}


def blend_distributions(
    weighted_distributions: Sequence[Tuple[float, Dict[Tuple[int, int], float]]]
) -> Dict[Tuple[int, int], float]:
    dist: Dict[Tuple[int, int], float] = {}
    total_weight = 0.0
    for weight, current in weighted_distributions:
        if weight <= 0.0:
            continue
        total_weight += weight
        for score, prob in current.items():
            dist[score] = dist.get(score, 0.0) + weight * prob
    if total_weight <= 0.0:
        return {}
    for key in list(dist):
        dist[key] /= total_weight
    total = sum(dist.values())
    if total > 0.0:
        for key in list(dist):
            dist[key] /= total
    return dist


def apply_outcome_target_shrink(
    dist: Dict[Tuple[int, int], float],
    target_a: float,
    target_draw: float,
    target_b: float,
    strength: float,
) -> Dict[Tuple[int, int], float]:
    strength = clamp(strength, 0.0, 1.0)
    if strength <= 0.0:
        return dict(dist)
    current = outcome_probabilities_from_distribution(dist)
    targets = {"a": max(target_a, 1e-6), "draw": max(target_draw, 1e-6), "b": max(target_b, 1e-6)}
    scales = {
        key: (targets[key] / max(current.get(key, 1e-6), 1e-6)) ** strength
        for key in ("a", "draw", "b")
    }
    adjusted: Dict[Tuple[int, int], float] = {}
    total = 0.0
    for (goals_a, goals_b), prob in dist.items():
        outcome = "a" if goals_a > goals_b else ("draw" if goals_a == goals_b else "b")
        scaled = prob * scales[outcome]
        adjusted[(goals_a, goals_b)] = scaled
        total += scaled
    if total <= 0.0:
        return dict(dist)
    for key in list(adjusted):
        adjusted[key] /= total
    return adjusted


def model_blend_weights(mu_a: float, mu_b: float, ctx: object | None = None) -> Dict[str, float]:
    closeness = clamp(1.0 - abs(mu_a - mu_b) / max(mu_a + mu_b, 1.0), 0.0, 1.0)
    draw_signal = 0.0
    if ctx and getattr(ctx, "market_prob_draw", None) is not None:
        draw_signal = clamp(
            float(getattr(ctx, "market_prob_draw")) - PARAMS.low_score_draw_threshold,
            PARAMS.low_score_draw_negative_cap,
            PARAMS.low_score_draw_positive_cap,
        )
    contrast = PARAMS.model_contrast_weight
    low_score = clamp(
        PARAMS.model_low_score_base
        + PARAMS.model_low_score_closeness_weight * closeness
        + PARAMS.model_low_score_draw_weight * max(draw_signal, 0.0)
        + (PARAMS.model_low_score_knockout_bonus if ctx and getattr(ctx, "knockout", False) else 0.0),
        PARAMS.model_low_score_min,
        PARAMS.model_low_score_max,
    )
    primary = max(PARAMS.model_primary_min, 1.0 - contrast - low_score)
    total = primary + contrast + low_score
    return {
        "primary": primary / total,
        "contrast": contrast / total,
        "low_score": low_score / total,
    }


def pairwise_model_agreement(prob_sets: Sequence[Dict[str, float]]) -> float:
    if len(prob_sets) < 2:
        return 1.0
    distances = []
    for index in range(len(prob_sets)):
        for other in range(index + 1, len(prob_sets)):
            distance = 0.5 * sum(
                abs(float(prob_sets[index].get(key, 0.0)) - float(prob_sets[other].get(key, 0.0)))
                for key in ("a", "draw", "b")
            )
            distances.append(distance)
    if not distances:
        return 1.0
    return clamp(1.0 - (sum(distances) / len(distances)), 0.0, 1.0)


def build_model_stack(
    mu_a: float,
    mu_b: float,
    ctx: object | None = None,
    *,
    max_goals: int = 10,
    market_strength: float = 0.28,
) -> Tuple[Dict[Tuple[int, int], float], Dict[str, object]]:
    primary = score_distribution(mu_a, mu_b, max_goals=max_goals, ctx=ctx)
    contrast = independent_score_distribution(mu_a, mu_b, max_goals=max_goals)
    low_score = low_score_adjusted_distribution(mu_a, mu_b, ctx, max_goals=max_goals)
    primary_probs = outcome_probabilities_from_distribution(primary)
    contrast_probs = outcome_probabilities_from_distribution(contrast)
    low_score_probs = outcome_probabilities_from_distribution(low_score)
    base_weights = model_blend_weights(mu_a, mu_b, ctx)
    market_probs = None
    if ctx and getattr(ctx, "market_prob_a", None) is not None and getattr(ctx, "market_prob_draw", None) is not None and getattr(ctx, "market_prob_b", None) is not None:
        market_probs = {
            "a": float(getattr(ctx, "market_prob_a")),
            "draw": float(getattr(ctx, "market_prob_draw")),
            "b": float(getattr(ctx, "market_prob_b")),
        }
    models = [
        ModelOutput("Bivariante Poisson", primary, primary_probs, base_weights["primary"], top_score_from_distribution(primary)),
        ModelOutput("Poisson independiente", contrast, contrast_probs, base_weights["contrast"], top_score_from_distribution(contrast)),
        ModelOutput("Ajuste de baja anotacion", low_score, low_score_probs, base_weights["low_score"], top_score_from_distribution(low_score)),
    ]
    adaptive_weights = adaptive_ensemble_weights(models, market_probs=market_probs)
    ensemble = blend_distributions([(weight, model.dist) for weight, model in zip(adaptive_weights, models)])
    market_used = False
    if market_probs:
        ensemble = apply_outcome_target_shrink(
            ensemble,
            market_probs["a"],
            market_probs["draw"],
            market_probs["b"],
            strength=market_strength,
        )
        market_used = market_strength > 0.0

    ensemble_probs = outcome_probabilities_from_distribution(ensemble)
    agreement = pairwise_model_agreement([model.probs for model in models])
    meta = {
        "primary_name": models[0].name,
        "contrast_name": models[1].name,
        "low_score_name": models[2].name,
        "final_name": "Ensamble ligero",
        "weights": {
            "primary": adaptive_weights[0],
            "contrast": adaptive_weights[1],
            "low_score": adaptive_weights[2],
        },
        "base_weights": base_weights,
        "agreement": agreement,
        "market_shrink": clamp(market_strength, 0.0, 1.0) if market_used else 0.0,
        "primary_probs": primary_probs,
        "contrast_probs": contrast_probs,
        "low_score_probs": low_score_probs,
        "ensemble_probs": ensemble_probs,
        "primary_top_score": models[0].top_score,
        "contrast_top_score": models[1].top_score,
        "low_score_top_score": models[2].top_score,
        "ensemble_top_score": top_score_from_distribution(ensemble),
    }
    return ensemble, meta


@lru_cache(maxsize=4096)
def cached_low_score_distribution(
    mu_a_key: int,
    mu_b_key: int,
    rho_key: int,
    max_goals: int,
) -> Dict[Tuple[int, int], float]:
    mu_a = mu_a_key / 20.0
    mu_b = mu_b_key / 20.0
    rho = rho_key / 100.0
    base = independent_score_distribution(mu_a, mu_b, max_goals=max_goals)
    total = 0.0
    for (goals_a, goals_b), prob in list(base.items()):
        adjusted = prob * dixon_coles_tau(goals_a, goals_b, mu_a, mu_b, rho)
        base[(goals_a, goals_b)] = max(adjusted, 0.0)
        total += base[(goals_a, goals_b)]
    if total > 0.0:
        for key in list(base):
            base[key] /= total
    return base
