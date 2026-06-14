"""Auditoría de goles y colas (F3, secciones C/D). Solo mide; no corrige."""

from __future__ import annotations

from typing import List, Sequence

from .scoreline import MatchObservation


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _pred_total_eq(o: MatchObservation, k: int) -> float:
    return sum(p for (x, y), p in o.model_dist.items() if x + y == k)


def _pred_total_ge(o: MatchObservation, k: int) -> float:
    return sum(p for (x, y), p in o.model_dist.items() if x + y >= k)


def goal_calibration(obs: Sequence[MatchObservation]) -> List[dict]:
    if not obs:
        return []
    n = len(obs)
    rows: List[dict] = []

    def dim(name, observed, predicted):
        mo, mp = _mean(observed), _mean(predicted)
        return {
            "dimension": name,
            "mean_observed": round(mo, 6),
            "mean_predicted": round(mp, 6),
            "bias": round(mp - mo, 6),
            "mae": round(_mean([abs(p - o_) for p, o_ in zip(predicted, observed)]), 6),
        }

    rows.append(dim("total_goals", [o.goals_a + o.goals_b for o in obs], [o.eg_a + o.eg_b for o in obs]))
    rows.append(dim("goals_a", [o.goals_a for o in obs], [o.eg_a for o in obs]))
    rows.append(dim("goals_b", [o.goals_b for o in obs], [o.eg_b for o in obs]))

    # Buckets de total de goles: 0..5 y 6+ (freq observada vs predicha).
    for k in range(6):
        obs_freq = sum(1 for o in obs if o.goals_a + o.goals_b == k) / n
        pred_freq = _mean([_pred_total_eq(o, k) for o in obs])
        rows.append({
            "dimension": f"total_eq_{k}",
            "mean_observed": round(obs_freq, 6),
            "mean_predicted": round(pred_freq, 6),
            "bias": round(pred_freq - obs_freq, 6),
            "mae": round(abs(pred_freq - obs_freq), 6),
        })
    obs_freq = sum(1 for o in obs if o.goals_a + o.goals_b >= 6) / n
    pred_freq = _mean([_pred_total_ge(o, 6) for o in obs])
    rows.append({
        "dimension": "total_ge_6",
        "mean_observed": round(obs_freq, 6),
        "mean_predicted": round(pred_freq, 6),
        "bias": round(pred_freq - obs_freq, 6),
        "mae": round(abs(pred_freq - obs_freq), 6),
    })
    return rows


def tail_audit(obs: Sequence[MatchObservation], thresholds=(4, 5, 6)) -> List[dict]:
    if not obs:
        return []
    n = len(obs)
    rows: List[dict] = []
    for k in thresholds:
        observed_rate = sum(1 for o in obs if o.goals_a + o.goals_b >= k) / n
        predicted_rate = _mean([_pred_total_ge(o, k) for o in obs])
        abs_error = abs(observed_rate - predicted_rate)
        rows.append({
            "threshold": f"total>={k}",
            "observed_rate": round(observed_rate, 6),
            "predicted_rate": round(predicted_rate, 6),
            "abs_error": round(abs_error, 6),
            "rel_error": round(abs_error / observed_rate, 4) if observed_rate > 0 else "",
        })
    return rows


GOAL_COLUMNS = ("dimension", "mean_observed", "mean_predicted", "bias", "mae")
TAIL_COLUMNS = ("threshold", "observed_rate", "predicted_rate", "abs_error", "rel_error")

__all__ = ["GOAL_COLUMNS", "TAIL_COLUMNS", "goal_calibration", "tail_audit"]
