"""Adaptador de materialización de mercado a MatchContext (F1.5).

`apply_market_to_context` rellena ÚNICAMENTE los campos de mercado de un
`MatchContext` (que el modelo ya sabe consumir mediante su blend fijo existente) a
partir del mercado sin vig. NO muta el contexto original (devuelve uno nuevo), NO
cambia pesos/lambdas/metodología/Penca y NO reentrena nada: solo provee entradas.
"""

from __future__ import annotations

import dataclasses
from typing import Mapping, Optional

import modelo_quiniela_2026 as model


def _get(implied, attr: str):
    if implied is None:
        return None
    if isinstance(implied, Mapping):
        return implied.get(attr)
    return getattr(implied, attr, None)


def _f(value) -> Optional[float]:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_market_to_context(ctx: "model.MatchContext", implied, prev_implied=None) -> "model.MatchContext":
    """Devuelve un MatchContext nuevo con SOLO los campos de mercado poblados.

    `implied`/`prev_implied`: MarketImplied o mapping con p_home/p_draw/p_away y
    market_total_goals. El movimiento (market_move_*) sale de la diferencia con
    `prev_implied` si se provee; si no, queda 0.0.
    """

    p_home = _f(_get(implied, "p_home"))
    p_draw = _f(_get(implied, "p_draw"))
    p_away = _f(_get(implied, "p_away"))
    total = _f(_get(implied, "market_total_goals"))

    move_a = move_draw = move_b = 0.0
    if prev_implied is not None:
        prev_home = _f(_get(prev_implied, "p_home"))
        prev_draw = _f(_get(prev_implied, "p_draw"))
        prev_away = _f(_get(prev_implied, "p_away"))
        if p_home is not None and prev_home is not None:
            move_a = p_home - prev_home
        if p_draw is not None and prev_draw is not None:
            move_draw = p_draw - prev_draw
        if p_away is not None and prev_away is not None:
            move_b = p_away - prev_away

    return dataclasses.replace(
        ctx,
        market_prob_a=p_home,
        market_prob_draw=p_draw,
        market_prob_b=p_away,
        market_total_line=total,
        market_move_a=move_a,
        market_move_draw=move_draw,
        market_move_b=move_b,
    )


__all__ = ["apply_market_to_context"]
