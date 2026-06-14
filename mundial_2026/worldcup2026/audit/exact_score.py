"""Auditoría de exact score top-N (F3, sección E). Solo mide; no corrige."""

from __future__ import annotations

from typing import List, Sequence

from .scoreline import MatchObservation


def exact_score_audit(obs: Sequence[MatchObservation], ns=(1, 3, 5, 10)) -> List[dict]:
    if not obs:
        return []
    n = len(obs)
    rows: List[dict] = []
    for top_n in ns:
        hits = 0
        coverage_sum = 0.0
        for o in obs:
            ranked = sorted(o.model_dist.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
            top_scores = {score for score, _ in ranked}
            if (o.goals_a, o.goals_b) in top_scores:
                hits += 1
            coverage_sum += sum(p for _, p in ranked)
        rows.append({
            "top_n": top_n,
            "exact_hit_rate": round(hits / n, 6),
            "mean_probability_coverage": round(coverage_sum / n, 6),
        })
    return rows


EXACT_COLUMNS = ("top_n", "exact_hit_rate", "mean_probability_coverage")

__all__ = ["EXACT_COLUMNS", "exact_score_audit"]
