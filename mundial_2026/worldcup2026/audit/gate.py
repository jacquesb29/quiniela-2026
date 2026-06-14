"""Gate de decisión de F3 (sección J). Responde preguntas objetivas; NO interviene."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class F3Thresholds:
    draw_gap: float = 0.02            # subestimación de empate relevante (pp)
    fav_overconf: float = 0.03        # sobreestimación de victoria del favorito
    total_goals_bias: float = 0.20    # sesgo de goles totales relevante
    score_tv: float = 0.06            # distancia de variación total de marcadores
    tail_gap: float = 0.02            # subestimación de colas relevante
    penca_gap: float = 0.15           # optimismo Penca relevante
    min_n: int = 500


def f3_decision(
    *,
    n: int,
    draw_error_global: float,            # observed - predicted (positivo => subestima)
    fav_pred_rate: float,
    fav_obs_rate: float,
    total_goals_bias: float,             # predicted - observed
    score_tv_distance: float,
    max_tail_underprediction: float,     # max(observed - predicted) sobre colas
    penca_gap_global: float,             # expected - realized (positivo => optimismo)
    thresholds: F3Thresholds = F3Thresholds(),
) -> Dict[str, object]:
    t = thresholds
    subestima_empates = draw_error_global > t.draw_gap
    sobreestima_favoritos = (fav_pred_rate - fav_obs_rate) > t.fav_overconf
    goles_mal_calibrados = abs(total_goals_bias) > t.total_goals_bias or score_tv_distance > t.score_tv
    subestima_colas = max_tail_underprediction > t.tail_gap
    optimismo_penca = penca_gap_global > t.penca_gap

    sample_ok = n >= t.min_n
    any_flag = any([subestima_empates, sobreestima_favoritos, goles_mal_calibrados,
                    subestima_colas, optimismo_penca])
    vale_la_pena = bool(any_flag and sample_ok)

    # Prioridad sugerida: el eje accionable con mayor exceso sobre su umbral.
    candidates = []
    if subestima_empates:
        candidates.append(("empates", draw_error_global - t.draw_gap))
    if goles_mal_calibrados:
        candidates.append(("goles_totales", max(abs(total_goals_bias) - t.total_goals_bias,
                                                 score_tv_distance - t.score_tv)))
    if subestima_colas:
        candidates.append(("colas", max_tail_underprediction - t.tail_gap))
    if sobreestima_favoritos:
        candidates.append(("favoritos", (fav_pred_rate - fav_obs_rate) - t.fav_overconf))
    if optimismo_penca:
        candidates.append(("penca", penca_gap_global - t.penca_gap))
    suggested_priority = max(candidates, key=lambda c: c[1])[0] if candidates else "ninguna"

    return {
        "n": n,
        "sample_ok": sample_ok,
        "subestima_empates": subestima_empates,
        "sobreestima_favoritos": sobreestima_favoritos,
        "goles_mal_calibrados": goles_mal_calibrados,
        "subestima_colas": subestima_colas,
        "optimismo_penca": optimismo_penca,
        "vale_la_pena_intervenir": vale_la_pena,
        "suggested_priority": suggested_priority,
        "draw_error_global": round(draw_error_global, 6),
        "fav_overconfidence": round(fav_pred_rate - fav_obs_rate, 6),
        "total_goals_bias": round(total_goals_bias, 6),
        "score_tv_distance": round(score_tv_distance, 6),
        "max_tail_underprediction": round(max_tail_underprediction, 6),
        "penca_gap_global": round(penca_gap_global, 6),
    }


__all__ = ["F3Thresholds", "f3_decision"]
