"""Catálogo de componentes a ablacionar (F5). Solo describe; no construye dists."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .ensemble_recompose import RecomposeOverrides

# Priors de las palancas μ (NO ajustados a resultados; aproximaciones documentadas).
MU_TOTAL_SCALE = 1.05    # 'mu_total': μ ligeramente más alto (sondea el sesgo -0.187)
MU_CLAMP_SCALE = 1.12    # 'mu_clamp': sondea la cota superior (aproximación; clamp es aguas arriba)


@dataclass(frozen=True)
class ComponentAblation:
    id: str
    layer: str
    kind: str          # "mu_scale" | "recompose" | "no_reshape" | "penca_relax"
    description: str
    mu_scale: float = 1.0
    overrides: RecomposeOverrides = RecomposeOverrides()


COMPONENTS: Tuple[ComponentAblation, ...] = (
    ComponentAblation("mu_total", "mu", "mu_scale",
                      "μ total más alto (sondea sesgo de goles -0.187)", mu_scale=MU_TOTAL_SCALE),
    ComponentAblation("mu_clamp", "mu", "mu_scale",
                      "relaja la cota superior de μ (aprox.; clamp es aguas arriba)", mu_scale=MU_CLAMP_SCALE),
    ComponentAblation("dixon_coles", "ensemble", "recompose",
                      "elimina el miembro Dixon-Coles de baja anotación",
                      overrides=RecomposeOverrides(drop_member="low_score")),
    ComponentAblation("bivariate", "ensemble", "recompose",
                      "primario sin correlación bivariante (Poisson independiente)",
                      overrides=RecomposeOverrides(use_independent_primary=True)),
    ComponentAblation("overdispersed", "ensemble", "recompose",
                      "amplifica el miembro sobredisperso (peso ×2)",
                      overrides=RecomposeOverrides(member_weight_scale={"overdispersed": 2.0})),
    ComponentAblation("reshape", "shape", "no_reshape",
                      "desactiva el reshape histórico (boost a marcadores centrales)"),
    ComponentAblation("penca_penalties", "selector", "penca_relax",
                      "pick Penca sin penalties anti-goleada (misma distribución)"),
)

__all__ = ["ComponentAblation", "COMPONENTS", "MU_TOTAL_SCALE", "MU_CLAMP_SCALE"]
