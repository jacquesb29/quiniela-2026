"""Auditoría Penca 8/5/3 (F3, sección F). Solo mide; no corrige.

`scoring_fn(pick_score, actual_score) -> float` se inyecta (el runner pasa
`modelo_quiniela_2026.realized_penca_points_for_score`). En tests se pasa una
función local 8/5/3 equivalente.
"""

from __future__ import annotations

from typing import Callable, List, Sequence

from .scoreline import MatchObservation


def outcome_bucket(o: MatchObservation) -> str:
    if o.goals_a == o.goals_b:
        return "empate"
    actual_winner = "home" if o.goals_a > o.goals_b else "away"
    model_fav = "home" if o.win_a >= o.win_b else "away"
    return "favorito_gana" if actual_winner == model_fav else "underdog_gana"


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def penca_audit(
    obs: Sequence[MatchObservation],
    scoring_fn: Callable[[object, object], float],
) -> List[dict]:
    if not obs:
        return []
    order = ["global", "favorito_gana", "underdog_gana", "empate"]
    groups = {b: [] for b in order}
    groups["global"] = list(obs)
    for o in obs:
        groups[outcome_bucket(o)].append(o)

    rows: List[dict] = []
    for bucket in order:
        subset = groups[bucket]
        nb = len(subset)
        if nb == 0:
            rows.append({"bucket": bucket, "n": 0, "mean_realized_penca": "",
                         "mean_expected_penca": "", "gap": ""})
            continue
        realized = _mean([scoring_fn(o.penca_score, f"{o.goals_a}-{o.goals_b}") for o in subset])
        expected = _mean([o.penca_expected_points for o in subset])
        rows.append({
            "bucket": bucket,
            "n": nb,
            "mean_realized_penca": round(realized, 6),
            "mean_expected_penca": round(expected, 6),
            "gap": round(expected - realized, 6),
        })
    return rows


PENCA_COLUMNS = ("bucket", "n", "mean_realized_penca", "mean_expected_penca", "gap")

__all__ = ["PENCA_COLUMNS", "outcome_bucket", "penca_audit"]
