"""Auditoría de marcadores y empates (F3, sección A/B). Solo mide; no corrige.

Módulo puro: no importa el monolito ni modifica predicciones. Recibe
`MatchObservation` (observado + distribución predicha por el modelo) y produce
tablas observado-vs-predicho. El observado son resultados históricos pasados; la
predicción es leakage-safe (la arma el runner con el adaptador). No usa 2026.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import List, Mapping, Sequence, Tuple

TRACKED_SCORES: List[Tuple[int, int]] = [
    (0, 0), (1, 0), (0, 1), (1, 1), (2, 1), (1, 2), (2, 0), (0, 2),
    (2, 2), (3, 1), (1, 3), (3, 0), (0, 3),
]

DRAW_EPS = 0.02  # tolerancia para el veredicto de empates


@dataclass(frozen=True)
class MatchObservation:
    match_id: str
    goals_a: int
    goals_b: int
    elo_diff: float
    model_dist: Mapping[Tuple[int, int], float]
    win_a: float
    draw: float
    win_b: float
    eg_a: float
    eg_b: float
    penca_score: str
    penca_expected_points: float


def _actual(o: MatchObservation) -> Tuple[int, int]:
    return (o.goals_a, o.goals_b)


def _fmt_score(s: Tuple[int, int]) -> str:
    return f"{s[0]}-{s[1]}"


def score_distribution_audit(obs: Sequence[MatchObservation], tracked=TRACKED_SCORES) -> List[dict]:
    n = len(obs)
    if n == 0:
        return []
    tracked_set = set(tracked)
    counts = Counter(_actual(o) for o in obs)
    rows: List[dict] = []
    for s in tracked:
        observed_count = counts.get(s, 0)
        observed_freq = observed_count / n
        predicted_freq = sum(o.model_dist.get(s, 0.0) for o in obs) / n
        abs_error = abs(observed_freq - predicted_freq)
        rel_error = round(abs_error / observed_freq, 4) if observed_freq > 0 else ""
        rows.append({
            "scoreline": _fmt_score(s),
            "observed_count": observed_count,
            "observed_freq": round(observed_freq, 6),
            "predicted_freq": round(predicted_freq, 6),
            "abs_error": round(abs_error, 6),
            "rel_error": rel_error,
        })
    # "resto": todo lo no listado.
    resto_count = sum(c for s, c in counts.items() if s not in tracked_set)
    resto_obs = resto_count / n
    resto_pred = sum(sum(o.model_dist.values()) - sum(o.model_dist.get(s, 0.0) for s in tracked) for o in obs) / n
    abs_error = abs(resto_obs - resto_pred)
    rows.append({
        "scoreline": "resto",
        "observed_count": resto_count,
        "observed_freq": round(resto_obs, 6),
        "predicted_freq": round(resto_pred, 6),
        "abs_error": round(abs_error, 6),
        "rel_error": round(abs_error / resto_obs, 4) if resto_obs > 0 else "",
    })
    return rows


def score_total_variation(score_rows: Sequence[Mapping]) -> float:
    return 0.5 * sum(abs(float(r["observed_freq"]) - float(r["predicted_freq"])) for r in score_rows)


def favorite_bucket(elo_diff: float) -> str:
    gap = abs(float(elo_diff))
    if gap < 50:
        return "parejo"
    if gap < 120:
        return "favorito_leve"
    if gap < 220:
        return "favorito_medio"
    return "favorito_fuerte"


def _draw_verdict(observed: float, predicted: float, eps: float = DRAW_EPS) -> str:
    if predicted < observed - eps:
        return "subestima_empates"
    if predicted > observed + eps:
        return "sobreestima_empates"
    return "calibrado"


def draw_audit(obs: Sequence[MatchObservation], eps: float = DRAW_EPS) -> List[dict]:
    if not obs:
        return []
    order = ["global", "parejo", "favorito_leve", "favorito_medio", "favorito_fuerte"]
    groups = {b: [] for b in order}
    groups["global"] = list(obs)
    for o in obs:
        groups[favorite_bucket(o.elo_diff)].append(o)

    rows: List[dict] = []
    for bucket in order:
        subset = groups[bucket]
        nb = len(subset)
        if nb == 0:
            rows.append({"bucket": bucket, "n": 0, "observed_draw_rate": "", "predicted_draw_rate": "",
                         "error": "", "reliability_gap": "", "verdict": "sin_muestra"})
            continue
        observed = sum(1 for o in subset if o.goals_a == o.goals_b) / nb
        predicted = sum(o.draw for o in subset) / nb
        error = predicted - observed
        rows.append({
            "bucket": bucket,
            "n": nb,
            "observed_draw_rate": round(observed, 6),
            "predicted_draw_rate": round(predicted, 6),
            "error": round(error, 6),
            "reliability_gap": round(abs(error), 6),
            "verdict": _draw_verdict(observed, predicted, eps),
        })
    return rows


SCORE_COLUMNS = ("scoreline", "observed_count", "observed_freq", "predicted_freq", "abs_error", "rel_error")
DRAW_COLUMNS = ("bucket", "n", "observed_draw_rate", "predicted_draw_rate", "error", "reliability_gap", "verdict")

__all__ = [
    "TRACKED_SCORES", "DRAW_EPS", "SCORE_COLUMNS", "DRAW_COLUMNS",
    "MatchObservation", "score_distribution_audit", "score_total_variation",
    "favorite_bucket", "draw_audit",
]
