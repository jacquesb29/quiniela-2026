"""Re-composición fiel del ensamble (F5), con palancas de ablación.

Clona EXACTAMENTE el cuerpo de `worldcup2026.distributions.build_model_stack`
llamando a sus funciones públicas, para poder ablacionar UN componente sin tocar
el código de producción. Con `RecomposeOverrides()` por defecto debe reproducir
`build_model_stack(...)[0]` bit-idéntico (requisito bloqueante de F5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Tuple

from worldcup2026.config import PARAMS
from worldcup2026.distributions import (
    apply_outcome_target_shrink,
    apply_outcome_temperature,
    bayesian_dynamic_score_distribution,
    blend_distributions,
    effective_market_shrink_strength,
    independent_score_distribution,
    low_score_adjusted_distribution,
    ml_calibrated_score_distribution,
    model_blend_weights,
    outcome_probabilities_from_distribution,
    outcome_temperature,
    overdispersed_score_distribution,
    pairwise_model_agreement,
    score_distribution,
)
from worldcup2026.modeling import adaptive_ensemble_weights, top_score_from_distribution
from worldcup2026.types import ModelOutput


@dataclass(frozen=True)
class RecomposeOverrides:
    use_independent_primary: bool = False                 # ablación 'bivariate' (λ3=0)
    drop_member: Optional[str] = None                     # ablación 'dixon_coles' -> drop "low_score"
    member_weight_scale: Mapping[str, float] = field(default_factory=dict)  # 'overdispersed' boost


def recompose_ensemble(
    mu_a: float,
    mu_b: float,
    ctx: object | None = None,
    *,
    overrides: RecomposeOverrides = RecomposeOverrides(),
    max_goals: int = 10,
    market_strength: float = 0.30,
) -> Dict[Tuple[int, int], float]:
    primary = score_distribution(mu_a, mu_b, max_goals=max_goals, ctx=ctx)
    contrast = independent_score_distribution(mu_a, mu_b, max_goals=max_goals)
    low_score = low_score_adjusted_distribution(mu_a, mu_b, ctx, max_goals=max_goals)
    overdispersed = overdispersed_score_distribution(mu_a, mu_b, ctx, max_goals=max_goals)
    ml_calibrated = ml_calibrated_score_distribution(mu_a, mu_b, ctx, max_goals=max_goals)
    bayesian_dynamic = bayesian_dynamic_score_distribution(mu_a, mu_b, ctx, max_goals=max_goals)

    # Ablación 'bivariate': el primario usa Poisson independiente (sin correlación λ3).
    primary_used = contrast if overrides.use_independent_primary else primary

    base_weights = dict(model_blend_weights(mu_a, mu_b, ctx))
    for member, scale in overrides.member_weight_scale.items():
        if member in base_weights:
            base_weights[member] = base_weights[member] * float(scale)
    if overrides.drop_member and overrides.drop_member in base_weights:
        base_weights[overrides.drop_member] = 0.0

    market_probs = None
    if ctx and getattr(ctx, "market_prob_a", None) is not None and \
            getattr(ctx, "market_prob_draw", None) is not None and \
            getattr(ctx, "market_prob_b", None) is not None:
        market_probs = {
            "a": float(getattr(ctx, "market_prob_a")),
            "draw": float(getattr(ctx, "market_prob_draw")),
            "b": float(getattr(ctx, "market_prob_b")),
        }

    models = [
        ModelOutput("Bivariante Poisson", primary_used, outcome_probabilities_from_distribution(primary_used),
                    base_weights["primary"], top_score_from_distribution(primary_used)),
        ModelOutput("Poisson independiente", contrast, outcome_probabilities_from_distribution(contrast),
                    base_weights["contrast"], top_score_from_distribution(contrast)),
        ModelOutput("Ajuste de baja anotación", low_score, outcome_probabilities_from_distribution(low_score),
                    base_weights["low_score"], top_score_from_distribution(low_score)),
        ModelOutput("Overdispersión calibrada", overdispersed, outcome_probabilities_from_distribution(overdispersed),
                    base_weights["overdispersed"], top_score_from_distribution(overdispersed)),
        ModelOutput("ML ligero regularizado", ml_calibrated, outcome_probabilities_from_distribution(ml_calibrated),
                    base_weights["ml"], top_score_from_distribution(ml_calibrated)),
        ModelOutput("Predictivo bayesiano dinámico", bayesian_dynamic, outcome_probabilities_from_distribution(bayesian_dynamic),
                    base_weights["bayesian"], top_score_from_distribution(bayesian_dynamic)),
    ]
    adaptive_weights = adaptive_ensemble_weights(models, market_probs=market_probs)
    ensemble = blend_distributions([(w, m.dist) for w, m in zip(adaptive_weights, models)])
    agreement = pairwise_model_agreement([m.probs for m in models])

    if market_probs:
        pre_market_probs = outcome_probabilities_from_distribution(ensemble)
        applied = effective_market_shrink_strength(pre_market_probs, market_probs, agreement, market_strength)
        ensemble = apply_outcome_target_shrink(ensemble, market_probs["a"], market_probs["draw"],
                                               market_probs["b"], strength=applied)

    ensemble_probs = outcome_probabilities_from_distribution(ensemble)
    temperature = outcome_temperature(ensemble_probs, agreement, market_probs)
    ensemble = apply_outcome_temperature(ensemble, temperature, PARAMS.outcome_temperature_strength)
    return ensemble


__all__ = ["RecomposeOverrides", "recompose_ensemble"]
