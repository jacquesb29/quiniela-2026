"""Métricas de atribución por componente (F5). Puro: no importa el modelo.

`compute_attribution_metrics` recibe observaciones (goles), distribuciones y picks
Penca ya elegidos, y devuelve las métricas de calibración. El pick se inyecta para
poder comparar el selector de producción vs un pick sin penalties (componente
'penca_penalties').
"""

from __future__ import annotations

import math
from typing import Dict, List, Mapping, Sequence, Tuple

OUTCOMES = ("a", "draw", "b")


def _parse(score: str) -> Tuple[int, int]:
    a, b = str(score).split("-")
    return int(a), int(b)


def realized_penca_8_5_3(pick: str, actual: str) -> float:
    pa, pb = _parse(pick)
    aa, ab = _parse(actual)
    if (pa, pb) == (aa, ab):
        return 8.0
    if pa - pb == aa - ab:
        return 5.0
    if (pa > pb) == (aa > ab) and (pa == pb) == (aa == ab):
        return 3.0
    return 0.0


def raw_expected_penca_pick(dist: Mapping[Tuple[int, int], float]) -> str:
    """Pick que maximiza puntos Penca 8/5/3 esperados SIN penalties (penalty-free)."""

    best_score, best_ev = (0, 0), -1.0
    for cand in dist:
        ca, cb = cand
        exact = dist.get(cand, 0.0)
        diff = sum(p for (a, b), p in dist.items() if (a - b) == (ca - cb))
        res_sign = 1 if ca > cb else (0 if ca == cb else -1)
        result = sum(p for (a, b), p in dist.items()
                     if (1 if a > b else (0 if a == b else -1)) == res_sign)
        ev = 8.0 * exact + 5.0 * max(0.0, diff - exact) + 3.0 * max(0.0, result - diff)
        if ev > best_ev:
            best_ev, best_score = ev, cand
    return f"{best_score[0]}-{best_score[1]}"


def _dist_1x2(dist):
    a = sum(p for (x, y), p in dist.items() if x > y)
    d = sum(p for (x, y), p in dist.items() if x == y)
    b = sum(p for (x, y), p in dist.items() if x < y)
    s = a + d + b
    return (a / s, d / s, b / s) if s > 0 else (1 / 3, 1 / 3, 1 / 3)


def _tail(dist, k):
    return sum(p for (a, b), p in dist.items() if a + b >= k)


METRIC_KEYS = ("logloss", "brier", "accuracy", "exact_top1", "penca_avg",
               "tail_err_4", "tail_err_5", "tail_err_6", "draw_error", "goal_total_bias")


def compute_attribution_metrics(
    obs: Sequence,
    dists: Sequence[Mapping[Tuple[int, int], float]],
    picks: Sequence[str],
) -> Dict[str, float]:
    n = len(obs)
    if n == 0:
        return {k: 0.0 for k in METRIC_KEYS} | {"n": 0}
    ll = br = draw_pred = exact = penca = total_pred = total_obs = 0.0
    tail_pred = {4: 0.0, 5: 0.0, 6: 0.0}
    draw_obs = sum(1 for o in obs if o.goals_a == o.goals_b) / n
    tail_obs = {k: sum(1 for o in obs if o.goals_a + o.goals_b >= k) / n for k in (4, 5, 6)}
    for o, dist, pick in zip(obs, dists, picks):
        pa, pd, pb = _dist_1x2(dist)
        probs = {"a": pa, "draw": pd, "b": pb}
        oc = "a" if o.goals_a > o.goals_b else ("draw" if o.goals_a == o.goals_b else "b")
        ll += -math.log(max(probs[oc], 1e-12))
        br += sum((probs[k] - (1.0 if k == oc else 0.0)) ** 2 for k in OUTCOMES) / 3.0
        draw_pred += pd
        if max(probs, key=probs.get) == oc:
            exact += 0  # accuracy handled below
        for k in (4, 5, 6):
            tail_pred[k] += _tail(dist, k)
        top1 = max(dist.items(), key=lambda kv: kv[1])[0] if dist else None
        if top1 == (o.goals_a, o.goals_b):
            exact += 1
        penca += realized_penca_8_5_3(pick, f"{o.goals_a}-{o.goals_b}")
        total_pred += sum((a + b) * p for (a, b), p in dist.items())
        total_obs += (o.goals_a + o.goals_b)
    # accuracy 1X2
    acc = 0
    for o, dist in zip(obs, dists):
        pa, pd, pb = _dist_1x2(dist)
        pred = max((("a", pa), ("draw", pd), ("b", pb)), key=lambda kv: kv[1])[0]
        oc = "a" if o.goals_a > o.goals_b else ("draw" if o.goals_a == o.goals_b else "b")
        acc += 1 if pred == oc else 0
    return {
        "n": n,
        "logloss": ll / n, "brier": br / n, "accuracy": acc / n,
        "exact_top1": exact / n, "penca_avg": penca / n,
        "tail_err_4": abs(tail_obs[4] - tail_pred[4] / n),
        "tail_err_5": abs(tail_obs[5] - tail_pred[5] / n),
        "tail_err_6": abs(tail_obs[6] - tail_pred[6] / n),
        "draw_error": abs(draw_obs - draw_pred / n),
        "goal_total_bias": (total_pred - total_obs) / n,
    }


__all__ = ["METRIC_KEYS", "realized_penca_8_5_3", "raw_expected_penca_pick", "compute_attribution_metrics"]
