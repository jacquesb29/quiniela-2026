from __future__ import annotations

import math
from typing import Dict, Tuple

from worldcup2026.config import PARAMS


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _negative_binomial_prob(goals: int, mu: float, alpha: float) -> float:
    mu = max(mu, 0.001)
    alpha = max(alpha, 1e-6)
    r = 1.0 / alpha
    p = r / (r + mu)
    return math.exp(
        math.lgamma(goals + r)
        - math.lgamma(goals + 1)
        - math.lgamma(r)
        + r * math.log(max(p, 1e-12))
        + goals * math.log(max(1.0 - p, 1e-12))
    )


def _side_evidence(ctx: object | None, side: str) -> float:
    if ctx is None:
        return PARAMS.bayesian_base_evidence
    coverage = float(getattr(ctx, f"lineup_coverage_{side}", 0.0) or 0.0)
    confirmed = bool(getattr(ctx, f"lineup_confirmed_{side}", False))
    injuries = float(getattr(ctx, f"injuries_{side}", 0.0) or 0.0)
    evidence = PARAMS.bayesian_base_evidence
    evidence += PARAMS.bayesian_lineup_evidence * coverage
    evidence += 1.2 if confirmed else 0.0
    evidence -= PARAMS.bayesian_injury_uncertainty * _clamp(injuries, 0.0, 1.0)
    return _clamp(evidence, 3.0, 18.0)


def _posterior_mean(mu: float, evidence: float) -> float:
    return (
        evidence * max(mu, 0.001)
        + PARAMS.bayesian_prior_strength * PARAMS.bayesian_prior_mean_goals
    ) / (evidence + PARAMS.bayesian_prior_strength)


def bayesian_dynamic_score_distribution(
    mu_a: float,
    mu_b: float,
    ctx: object | None = None,
    max_goals: int = 10,
) -> Dict[Tuple[int, int], float]:
    """Empirical-Bayes posterior predictive distribution.

    This member is intentionally not a Poisson copy. It partially pools the
    expected goals toward an international-football prior and uses a
    negative-binomial posterior predictive distribution whose uncertainty
    contracts when confirmed lineup evidence improves.
    """

    evidence_a = _side_evidence(ctx, "a")
    evidence_b = _side_evidence(ctx, "b")
    posterior_a = _posterior_mean(mu_a, evidence_a)
    posterior_b = _posterior_mean(mu_b, evidence_b)
    raw_total = max(posterior_a + posterior_b, 0.2)
    target_total = 0.82 * max(mu_a + mu_b, 0.2) + 0.18 * raw_total
    posterior_a *= target_total / raw_total
    posterior_b *= target_total / raw_total
    alpha_a = _clamp(
        PARAMS.bayesian_overdispersion_floor + 1.0 / (evidence_a + PARAMS.bayesian_prior_strength),
        PARAMS.bayesian_overdispersion_floor,
        PARAMS.bayesian_overdispersion_cap,
    )
    alpha_b = _clamp(
        PARAMS.bayesian_overdispersion_floor + 1.0 / (evidence_b + PARAMS.bayesian_prior_strength),
        PARAMS.bayesian_overdispersion_floor,
        PARAMS.bayesian_overdispersion_cap,
    )
    edge = posterior_a - posterior_b
    closeness = _clamp(1.0 - abs(edge) / max(target_total, 1.0), 0.0, 1.0)
    knockout = bool(ctx and getattr(ctx, "knockout", False))

    dist: Dict[Tuple[int, int], float] = {}
    total = 0.0
    for goals_a in range(max_goals + 1):
        prob_a = _negative_binomial_prob(goals_a, posterior_a, alpha_a)
        for goals_b in range(max_goals + 1):
            prob = prob_a * _negative_binomial_prob(goals_b, posterior_b, alpha_b)
            margin = abs(goals_a - goals_b)
            if goals_a == goals_b:
                prob *= 1.0 + 0.07 * closeness + (0.025 if knockout else 0.0)
            if margin >= 2 and ((edge > 0.45 and goals_a > goals_b) or (edge < -0.45 and goals_b > goals_a)):
                prob *= 1.0 + 0.08 * _clamp(abs(edge), 0.0, 1.5)
            if margin >= 4 and closeness > 0.55:
                prob *= 0.90
            dist[(goals_a, goals_b)] = prob
            total += prob
    if total <= 0.0:
        return dist
    return {score: prob / total for score, prob in dist.items()}
