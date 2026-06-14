"""Intervención post-distribución de colas/varianza (F4.1, Estilo A).

Reescala MASA hacia totales altos en la distribución de marcador YA producida por
el modelo, sin tocar el modelo, pesos, lambdas, metodología ni el selector Penca.
Función pura y experimental: con `enabled=False` es identidad exacta. No usa datos
del Mundial 2026; los parámetros son priors conservadores, no ajustados a 2026.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Mapping, Tuple

# Priors de la señal de scoring (NO ajustados a 2026).
TOTAL_NORM_LO, TOTAL_NORM_HI = 2.4, 4.0     # normaliza expected_total -> [0,1]
ASYM_LO, ASYM_HI = 0.50, 0.80               # asimetría de favorito -> [0,1]
W_TOTAL, W_ASYM = 0.6, 0.4
FAV_STRONG = 0.62                           # share de favorito "fuerte"
TOTAL_HIGH = 2.9                            # total esperado "alto"


@dataclass(frozen=True)
class TailParams:
    enabled: bool = False           # OFF por defecto -> identidad
    beta: float = 0.0               # intensidad del tilt hacia totales altos
    t0: int = 3                     # solo reescala total > t0 (boost a total>=t0+1)
    max_mass_shift: float = 0.06    # tope de masa trasladada a total>=t0+1
    min_signal: float = 0.35        # no intervenir si la señal es baja
    weak_favorite_guard: bool = True  # no inflar goleadas sin favorito fuerte ni total alto


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def tail_signal(*, expected_total: float, favorite_share: float) -> float:
    """Señal de scoring en [0,1]: alta con total esperado alto y/o favorito marcado."""

    norm_total = _clamp((expected_total - TOTAL_NORM_LO) / (TOTAL_NORM_HI - TOTAL_NORM_LO), 0.0, 1.0)
    asym = _clamp((favorite_share - ASYM_LO) / (ASYM_HI - ASYM_LO), 0.0, 1.0)
    return _clamp(W_TOTAL * norm_total + W_ASYM * asym, 0.0, 1.0)


def effective_tail_mass(dist: Mapping[Tuple[int, int], float], k: int) -> float:
    return sum(p for (a, b), p in dist.items() if a + b >= k)


def tail_reweight(
    dist: Mapping[Tuple[int, int], float],
    *,
    params: TailParams,
    expected_total: float,
    favorite_share: float,
) -> Dict[Tuple[int, int], float]:
    """Devuelve una distribución reescalada (o idéntica). Suma 1; cap por max_mass_shift."""

    base = dict(dist)
    if not params.enabled:
        return base  # identidad exacta con flag OFF

    # Guard: sin favorito fuerte ni total esperado alto -> no inflar goleadas.
    if params.weak_favorite_guard and favorite_share < FAV_STRONG and expected_total < TOTAL_HIGH:
        return base

    signal = tail_signal(expected_total=expected_total, favorite_share=favorite_share)
    if signal < params.min_signal:
        return base

    tilted: Dict[Tuple[int, int], float] = {}
    for (a, b), p in base.items():
        extra = max(0, (a + b) - params.t0)
        tilted[(a, b)] = p * math.exp(params.beta * signal * extra)
    total = sum(tilted.values())
    if total <= 0.0:
        return base
    tilted = {k: v / total for k, v in tilted.items()}

    # Cap conservador sobre el incremento de masa en total>=t0+1.
    k_tail = params.t0 + 1
    base_tail = effective_tail_mass(base, k_tail)
    new_tail = effective_tail_mass(tilted, k_tail)
    delta = new_tail - base_tail
    if delta > params.max_mass_shift and delta > 0:
        # Mezcla lineal: la masa de cola es lineal en lambda -> caps exactos.
        lam = params.max_mass_shift / delta
        keys = set(tilted) | set(base)
        return {k: lam * tilted.get(k, 0.0) + (1.0 - lam) * base.get(k, 0.0) for k in keys}
    return tilted


__all__ = [
    "TailParams", "tail_signal", "tail_reweight", "effective_tail_mass",
    "FAV_STRONG", "TOTAL_HIGH",
]
