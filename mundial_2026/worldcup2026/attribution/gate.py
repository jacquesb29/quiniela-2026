"""Gate de intervención por componente (F5). Identifica; no corrige ni activa."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Sequence


@dataclass(frozen=True)
class F5GateThresholds:
    min_close_gap_fraction: float = 0.60
    logloss_tol: float = 0.002
    brier_tol: float = 0.002
    penca_tol: float = 0.0
    draw_tol: float = 0.01
    min_culpability_margin: float = 0.05
    min_folds: int = 4


def decide_component_intervention(
    ranking: Sequence[Mapping],
    *,
    n_folds: int,
    thresholds: F5GateThresholds = F5GateThresholds(),
) -> Dict[str, object]:
    t = thresholds
    if not ranking:
        return {"decision": "no_clear_culprit", "reason": "sin ranking", "target_component": None}
    if n_folds < t.min_folds:
        return {"decision": "no_clear_culprit", "reason": f"folds insuficientes (n={n_folds})",
                "target_component": None}

    top = ranking[0]
    second_score = float(ranking[1]["culpability_score"]) if len(ranking) > 1 else float("-inf")
    margin = float(top["culpability_score"]) - second_score

    majority = float(top["fraction_folds_close_gap"]) >= t.min_close_gap_fraction
    logloss_ok = float(top["mean_delta_logloss"]) <= t.logloss_tol
    brier_ok = float(top["mean_delta_brier"]) <= t.brier_tol
    penca_ok = float(top["mean_delta_penca"]) >= -t.penca_tol
    draw_ok = float(top["mean_delta_draw_error"]) <= t.draw_tol
    distinguishable = margin >= t.min_culpability_margin
    recovers = float(top["mean_tail5_recovery"]) > 0.0

    if majority and recovers and logloss_ok and brier_ok and penca_ok and draw_ok and distinguishable:
        return {
            "decision": f"intervene_component:{top['component_id']}",
            "target_component": top["component_id"],
            "reason": "componente con causa distinguible que cierra el gap de cola sin daño colateral",
            "culpability_margin": round(margin, 8),
        }

    fails = []
    if not majority:
        fails.append("no mejora en mayoría de folds")
    if not recovers:
        fails.append("no recupera masa de cola")
    if not (logloss_ok and brier_ok):
        fails.append("daño en log-loss/Brier")
    if not penca_ok:
        fails.append("empeora Penca")
    if not draw_ok:
        fails.append("empeora empates")
    if not distinguishable:
        fails.append(f"culpable no distinguible del 2º (margen {margin:.4f} < {t.min_culpability_margin})")
    return {
        "decision": "no_clear_culprit",
        "target_component": None,
        "reason": "; ".join(fails),
        "culpability_margin": round(margin, 8),
    }


__all__ = ["F5GateThresholds", "decide_component_intervention"]
