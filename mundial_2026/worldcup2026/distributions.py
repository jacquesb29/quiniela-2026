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
from .models.bayesian_dynamic import bayesian_dynamic_score_distribution

FACTORIALS = [math.factorial(i) for i in range(16)]


def poisson_prob(goals: int, mu: float) -> float:
    if goals < 0:
        return 0.0
    mu = max(mu, 0.001)
    factorial = FACTORIALS[goals] if goals < len(FACTORIALS) else math.factorial(goals)
    return math.exp(-mu) * (mu ** goals) / factorial


def negative_binomial_prob(goals: int, mu: float, alpha: float) -> float:
    """Negative-binomial PMF for football score overdispersion.

    alpha close to 0 behaves like Poisson; higher alpha gives fatter tails.
    """

    if goals < 0:
        return 0.0
    mu = max(mu, 0.001)
    alpha = max(alpha, 1e-6)
    r = 1.0 / alpha
    p = r / (r + mu)
    log_prob = (
        math.lgamma(goals + r)
        - math.lgamma(goals + 1)
        - math.lgamma(r)
        + r * math.log(max(p, 1e-12))
        + goals * math.log(max(1.0 - p, 1e-12))
    )
    return math.exp(log_prob)


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
    # Copia defensiva: el objeto cacheado nunca se expone a mutación in-place de
    # un caller (reproducibilidad). Claves (tuplas) y valores (float) son
    # inmutables, así que una copia superficial es segura y completa.
    return dict(cached_primary_score_distribution(
        quantize_for_cache(mu_a),
        quantize_for_cache(mu_b),
        knockout_key,
        importance_key,
        draw_key,
        max_goals,
    ))


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
    # Copia defensiva: este resultado lo mutan in-place algunos consumidores
    # (Dixon-Coles de baja anotación). Devolver una copia impide que esa mutación
    # contamine el dict cacheado y rompa el determinismo.
    return dict(cached_independent_score_distribution(
        quantize_for_cache(mu_a),
        quantize_for_cache(mu_b),
        max_goals,
    ))


@lru_cache(maxsize=32768)
def cached_overdispersed_score_distribution(
    mu_a_key: int,
    mu_b_key: int,
    alpha_key: int,
    max_goals: int,
) -> Dict[Tuple[int, int], float]:
    mu_a = mu_a_key / PARAMS.cache_goal_precision
    mu_b = mu_b_key / PARAMS.cache_goal_precision
    alpha = alpha_key / 1000.0
    dist: Dict[Tuple[int, int], float] = {}
    total = 0.0
    for goals_a in range(max_goals + 1):
        prob_a = negative_binomial_prob(goals_a, mu_a, alpha)
        for goals_b in range(max_goals + 1):
            prob = prob_a * negative_binomial_prob(goals_b, mu_b, alpha)
            dist[(goals_a, goals_b)] = prob
            total += prob
    if total <= 0.0:
        return dist
    for key in list(dist):
        dist[key] /= total
    return dist


def overdispersion_alpha(mu_a: float, mu_b: float, ctx: object | None = None) -> float:
    total_goals = mu_a + mu_b
    closeness = clamp(1.0 - abs(mu_a - mu_b) / max(total_goals, 1.0), 0.0, 1.0)
    alpha = (
        PARAMS.negative_binomial_alpha_base
        + PARAMS.negative_binomial_alpha_total_weight * clamp((total_goals - 2.25) / 1.4, 0.0, 1.0)
        + PARAMS.negative_binomial_alpha_closeness_weight * closeness
    )
    if ctx and getattr(ctx, "knockout", False):
        alpha -= PARAMS.negative_binomial_alpha_knockout_penalty
    return clamp(alpha, 0.04, 0.24)


def overdispersed_score_distribution(
    mu_a: float,
    mu_b: float,
    ctx: object | None = None,
    max_goals: int = 10,
) -> Dict[Tuple[int, int], float]:
    alpha = overdispersion_alpha(mu_a, mu_b, ctx)
    # Copia defensiva del dict cacheado (reproducibilidad).
    return dict(cached_overdispersed_score_distribution(
        quantize_for_cache(mu_a),
        quantize_for_cache(mu_b),
        int(round(alpha * 1000.0)),
        max_goals,
    ))


def _safe_sigmoid(value: float) -> float:
    value = clamp(value, -8.0, 8.0)
    return 1.0 / (1.0 + math.exp(-value))


def ml_adjusted_goal_means(mu_a: float, mu_b: float, ctx: object | None = None) -> Tuple[float, float]:
    """Regularized ML-style goal correction.

    This is a lightweight, auditable model member: nonlinear features adjust
    goal total and favorite share, but the movement is intentionally capped so
    it cannot overpower the calibrated football models before live backtesting.
    """

    base_total = max(mu_a + mu_b, 0.20)
    edge = mu_a - mu_b
    closeness = clamp(1.0 - abs(edge) / max(base_total, 1.0), 0.0, 1.0)
    knockout = bool(ctx and getattr(ctx, "knockout", False))
    importance = float(getattr(ctx, "importance", 1.0)) if ctx else 1.0
    draw_signal = 0.0
    if ctx and getattr(ctx, "market_prob_draw", None) is not None:
        draw_signal = clamp(
            float(getattr(ctx, "market_prob_draw")) - PARAMS.low_score_draw_threshold,
            PARAMS.low_score_draw_negative_cap,
            PARAMS.low_score_draw_positive_cap,
        )

    total_target = base_total
    total_target *= 1.0 - PARAMS.ml_knockout_total_guard * closeness * (1.0 if knockout else 0.0)
    total_target *= 1.0 + PARAMS.ml_high_total_boost * clamp((base_total - 2.55) / 1.20, 0.0, 1.0)
    total_target *= 1.0 - 0.04 * max(draw_signal, 0.0)
    total_target *= 1.0 + 0.015 * max(importance - 1.0, 0.0)

    if ctx and getattr(ctx, "market_total_line", None) is not None:
        try:
            market_total = float(getattr(ctx, "market_total_line"))
            total_target = (
                (1.0 - PARAMS.ml_total_market_blend) * total_target
                + PARAMS.ml_total_market_blend * market_total
            )
        except (TypeError, ValueError):
            pass

    total_target = clamp(total_target, max(0.85, base_total - 0.38), min(4.35, base_total + 0.38))

    share_a = clamp(mu_a / base_total, 0.06, 0.94)
    logit_share = math.log(share_a / (1.0 - share_a))
    logit_share += PARAMS.ml_favorite_share_weight * clamp(edge, -1.60, 1.60)
    if ctx and getattr(ctx, "market_prob_a", None) is not None and getattr(ctx, "market_prob_b", None) is not None:
        try:
            market_edge = float(getattr(ctx, "market_prob_a")) - float(getattr(ctx, "market_prob_b"))
            logit_share += PARAMS.ml_market_edge_weight * clamp(market_edge, -0.70, 0.70)
        except (TypeError, ValueError):
            pass
    if knockout and closeness > 0.55:
        logit_share *= 1.0 - 0.05 * closeness

    adjusted_share_a = clamp(_safe_sigmoid(logit_share), 0.07, 0.93)
    return (
        clamp(total_target * adjusted_share_a, 0.05, 4.10),
        clamp(total_target * (1.0 - adjusted_share_a), 0.05, 4.10),
    )


def ml_score_shape_weight(
    goals_a: int,
    goals_b: int,
    mu_a: float,
    mu_b: float,
    ctx: object | None = None,
) -> float:
    total_mu = max(mu_a + mu_b, 0.20)
    total_goals = goals_a + goals_b
    edge = mu_a - mu_b
    margin = abs(goals_a - goals_b)
    favorite_is_a = edge >= 0.0
    favorite_wins = goals_a > goals_b if favorite_is_a else goals_b > goals_a
    closeness = clamp(1.0 - abs(edge) / max(total_mu, 1.0), 0.0, 1.0)
    knockout = bool(ctx and getattr(ctx, "knockout", False))
    high_total_signal = clamp((total_mu - 2.45) / 1.25, 0.0, 1.0)
    low_total_signal = clamp((2.10 - total_mu) / 0.90, 0.0, 1.0)
    weight = 1.0

    if total_goals >= 4:
        weight *= 1.0 + PARAMS.ml_score_shape_strength * high_total_signal
    if total_goals <= 1:
        weight *= 1.0 + 0.45 * PARAMS.ml_score_shape_strength * low_total_signal
    if margin >= 3 and closeness > 0.55:
        weight *= 1.0 - 0.70 * PARAMS.ml_score_shape_strength * closeness
    if margin >= 2 and favorite_wins and abs(edge) > 0.55:
        weight *= 1.0 + 0.50 * PARAMS.ml_score_shape_strength * clamp(abs(edge), 0.0, 1.6)
    if goals_a == goals_b and knockout:
        weight *= 1.0 + 0.35 * PARAMS.ml_score_shape_strength * closeness
    return clamp(weight, 0.78, 1.28)


def ml_calibrated_score_distribution(
    mu_a: float,
    mu_b: float,
    ctx: object | None = None,
    max_goals: int = 10,
) -> Dict[Tuple[int, int], float]:
    adj_mu_a, adj_mu_b = ml_adjusted_goal_means(mu_a, mu_b, ctx)
    alpha = clamp(overdispersion_alpha(adj_mu_a, adj_mu_b, ctx) + 0.025, 0.06, 0.26)
    dist = cached_overdispersed_score_distribution(
        quantize_for_cache(adj_mu_a),
        quantize_for_cache(adj_mu_b),
        int(round(alpha * 1000.0)),
        max_goals,
    )
    adjusted: Dict[Tuple[int, int], float] = {}
    total = 0.0
    for (goals_a, goals_b), prob in dist.items():
        weighted = prob * ml_score_shape_weight(goals_a, goals_b, adj_mu_a, adj_mu_b, ctx)
        adjusted[(goals_a, goals_b)] = weighted
        total += weighted
    if total <= 0.0:
        return dict(dist)
    for key in list(adjusted):
        adjusted[key] /= total
    return adjusted


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


def apply_outcome_temperature(
    dist: Dict[Tuple[int, int], float],
    temperature: float,
    strength: float,
) -> Dict[Tuple[int, int], float]:
    """Lightly sharpen or flatten 1X2 probabilities without changing score shape."""

    temperature = clamp(temperature, PARAMS.outcome_temperature_min, PARAMS.outcome_temperature_max)
    strength = clamp(strength, 0.0, 1.0)
    if abs(temperature - 1.0) < 1e-6 or strength <= 0.0:
        return dict(dist)
    current = outcome_probabilities_from_distribution(dist)
    powered = {key: max(value, 1e-9) ** (1.0 / temperature) for key, value in current.items()}
    total = sum(powered.values()) or 1.0
    target = {key: value / total for key, value in powered.items()}
    return apply_outcome_target_shrink(
        dist,
        target["a"],
        target["draw"],
        target["b"],
        strength=strength,
    )


def outcome_temperature(
    probs: Dict[str, float],
    agreement: float,
    market_probs: Optional[Dict[str, float]] = None,
) -> float:
    sorted_probs = sorted((float(probs.get(key, 0.0)) for key in ("a", "draw", "b")), reverse=True)
    top_prob = sorted_probs[0] if sorted_probs else 0.0
    gap = (sorted_probs[0] - sorted_probs[1]) if len(sorted_probs) >= 2 else 0.0
    temperature = 1.0
    if agreement >= 0.84 and gap >= 0.16 and top_prob >= 0.48:
        temperature -= PARAMS.outcome_temperature_sharpen * clamp((agreement - 0.84) / 0.16, 0.0, 1.0)
    if agreement <= 0.72 or gap <= 0.07:
        temperature += PARAMS.outcome_temperature_flatten * max(
            clamp((0.72 - agreement) / 0.22, 0.0, 1.0),
            clamp((0.07 - gap) / 0.07, 0.0, 1.0),
        )
    if market_probs:
        market_distance = 0.5 * sum(
            abs(float(probs.get(key, 0.0)) - float(market_probs.get(key, 0.0)))
            for key in ("a", "draw", "b")
        )
        temperature += 0.04 * clamp(market_distance / 0.18, 0.0, 1.0)
    return clamp(temperature, PARAMS.outcome_temperature_min, PARAMS.outcome_temperature_max)


def effective_market_shrink_strength(
    ensemble_probs: Dict[str, float],
    market_probs: Dict[str, float],
    agreement: float,
    requested_strength: float,
) -> float:
    if requested_strength <= 0.0:
        return 0.0
    market_distance = 0.5 * sum(
        abs(float(ensemble_probs.get(key, 0.0)) - float(market_probs.get(key, 0.0)))
        for key in ("a", "draw", "b")
    )
    multiplier = (
        0.70
        + PARAMS.market_shrink_gap_boost * clamp(market_distance / 0.20, 0.0, 1.0)
        + PARAMS.market_shrink_disagreement_boost * clamp((1.0 - agreement) / 0.35, 0.0, 1.0)
    )
    return clamp(requested_strength * multiplier, 0.0, PARAMS.market_shrink_cap)


def model_blend_weights(mu_a: float, mu_b: float, ctx: object | None = None) -> Dict[str, float]:
    closeness = clamp(1.0 - abs(mu_a - mu_b) / max(mu_a + mu_b, 1.0), 0.0, 1.0)
    total_goals = mu_a + mu_b
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
    overdispersed = clamp(
        PARAMS.model_overdispersed_base
        + PARAMS.model_overdispersed_total_weight * clamp((total_goals - 2.40) / 1.25, 0.0, 1.0)
        - PARAMS.model_overdispersed_draw_penalty * max(draw_signal, 0.0),
        0.04,
        PARAMS.model_overdispersed_max,
    )
    ml = clamp(
        PARAMS.model_ml_base
        + PARAMS.model_ml_total_weight * clamp((total_goals - 2.20) / 1.60, 0.0, 1.0)
        + PARAMS.model_ml_closeness_weight * closeness
        + PARAMS.model_ml_market_weight * (1.0 if ctx and getattr(ctx, "market_total_line", None) is not None else 0.0)
        + (PARAMS.model_ml_knockout_bonus if ctx and getattr(ctx, "knockout", False) else 0.0),
        0.06,
        PARAMS.model_ml_max,
    )
    lineup_coverage = 0.0
    if ctx:
        lineup_coverage = 0.5 * (
            float(getattr(ctx, "lineup_coverage_a", 0.0) or 0.0)
            + float(getattr(ctx, "lineup_coverage_b", 0.0) or 0.0)
        )
    bayesian = clamp(
        PARAMS.model_bayesian_base
        + PARAMS.model_bayesian_uncertainty_weight * closeness
        + PARAMS.model_bayesian_lineup_weight * lineup_coverage,
        0.08,
        PARAMS.model_bayesian_max,
    )
    primary = max(PARAMS.model_primary_min, 1.0 - contrast - low_score - overdispersed - ml - bayesian)
    total = primary + contrast + low_score + overdispersed + ml + bayesian
    return {
        "primary": primary / total,
        "contrast": contrast / total,
        "low_score": low_score / total,
        "overdispersed": overdispersed / total,
        "ml": ml / total,
        "bayesian": bayesian / total,
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
    overdispersed = overdispersed_score_distribution(mu_a, mu_b, ctx, max_goals=max_goals)
    ml_calibrated = ml_calibrated_score_distribution(mu_a, mu_b, ctx, max_goals=max_goals)
    bayesian_dynamic = bayesian_dynamic_score_distribution(mu_a, mu_b, ctx, max_goals=max_goals)
    primary_probs = outcome_probabilities_from_distribution(primary)
    contrast_probs = outcome_probabilities_from_distribution(contrast)
    low_score_probs = outcome_probabilities_from_distribution(low_score)
    overdispersed_probs = outcome_probabilities_from_distribution(overdispersed)
    ml_probs = outcome_probabilities_from_distribution(ml_calibrated)
    bayesian_probs = outcome_probabilities_from_distribution(bayesian_dynamic)
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
        ModelOutput("Ajuste de baja anotación", low_score, low_score_probs, base_weights["low_score"], top_score_from_distribution(low_score)),
        ModelOutput("Overdispersión calibrada", overdispersed, overdispersed_probs, base_weights["overdispersed"], top_score_from_distribution(overdispersed)),
        ModelOutput("ML ligero regularizado", ml_calibrated, ml_probs, base_weights["ml"], top_score_from_distribution(ml_calibrated)),
        ModelOutput("Predictivo bayesiano dinámico", bayesian_dynamic, bayesian_probs, base_weights["bayesian"], top_score_from_distribution(bayesian_dynamic)),
    ]
    adaptive_weights = adaptive_ensemble_weights(models, market_probs=market_probs)
    ensemble = blend_distributions([(weight, model.dist) for weight, model in zip(adaptive_weights, models)])
    agreement = pairwise_model_agreement([model.probs for model in models])
    market_used = False
    applied_market_strength = 0.0
    if market_probs:
        pre_market_probs = outcome_probabilities_from_distribution(ensemble)
        applied_market_strength = effective_market_shrink_strength(
            pre_market_probs,
            market_probs,
            agreement,
            market_strength,
        )
        ensemble = apply_outcome_target_shrink(
            ensemble,
            market_probs["a"],
            market_probs["draw"],
            market_probs["b"],
            strength=applied_market_strength,
        )
        market_used = applied_market_strength > 0.0

    ensemble_probs = outcome_probabilities_from_distribution(ensemble)
    temperature = outcome_temperature(ensemble_probs, agreement, market_probs)
    ensemble = apply_outcome_temperature(
        ensemble,
        temperature,
        PARAMS.outcome_temperature_strength,
    )
    ensemble_probs = outcome_probabilities_from_distribution(ensemble)
    meta = {
        "primary_name": models[0].name,
        "contrast_name": models[1].name,
        "low_score_name": models[2].name,
        "overdispersed_name": models[3].name,
        "ml_name": models[4].name,
        "bayesian_name": models[5].name,
        "final_name": "Ensamble ligero",
        "weights": {
            "primary": adaptive_weights[0],
            "contrast": adaptive_weights[1],
            "low_score": adaptive_weights[2],
            "overdispersed": adaptive_weights[3],
            "ml": adaptive_weights[4],
            "bayesian": adaptive_weights[5],
        },
        "base_weights": base_weights,
        "agreement": agreement,
        "market_shrink": applied_market_strength if market_used else 0.0,
        "outcome_temperature": temperature,
        "primary_probs": primary_probs,
        "contrast_probs": contrast_probs,
        "low_score_probs": low_score_probs,
        "overdispersed_probs": overdispersed_probs,
        "ml_probs": ml_probs,
        "bayesian_probs": bayesian_probs,
        "ensemble_probs": ensemble_probs,
        "primary_top_score": models[0].top_score,
        "contrast_top_score": models[1].top_score,
        "low_score_top_score": models[2].top_score,
        "overdispersed_top_score": models[3].top_score,
        "ml_top_score": models[4].top_score,
        "bayesian_top_score": models[5].top_score,
        "ensemble_top_score": top_score_from_distribution(ensemble),
        "ml_note": "Calibrador ML ligero con features no lineales de total de goles, favoritismo, mercado, knockout y forma del marcador.",
        "bayesian_note": "Predictivo Bayes empírico con pooling parcial y sobredispersión variable: reduce dependencia de un modo Poisson aislado.",
    }
    return ensemble, meta


@lru_cache(maxsize=4096)
def _cached_low_score_distribution_inner(
    mu_a_key: int,
    mu_b_key: int,
    rho_key: int,
    max_goals: int,
) -> Dict[Tuple[int, int], float]:
    mu_a = mu_a_key / 20.0
    mu_b = mu_b_key / 20.0
    rho = rho_key / 100.0
    # `independent_score_distribution` ya devuelve una copia privada, así que
    # mutar `base` aquí no afecta a ningún caché compartido.
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


def cached_low_score_distribution(
    mu_a_key: int,
    mu_b_key: int,
    rho_key: int,
    max_goals: int,
) -> Dict[Tuple[int, int], float]:
    # Wrapper externo: copia defensiva para no exponer el dict cacheado interno a
    # mutación in-place de un caller. Mantiene el nombre público estable.
    return dict(_cached_low_score_distribution_inner(mu_a_key, mu_b_key, rho_key, max_goals))
