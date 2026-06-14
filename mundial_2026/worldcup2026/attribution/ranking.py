"""Ranking de culpabilidad por componente (F5). Puro."""

from __future__ import annotations

import statistics as _st
from typing import Dict, List, Mapping, Sequence

LOGLOSS_TOL = 0.002
BRIER_TOL = 0.002
DRAW_TOL = 0.01
PENCA_UNIT = 0.05
RANKING_COLUMNS = (
    "rank", "component_id", "fraction_folds_close_gap", "mean_tail5_recovery", "consistency",
    "mean_delta_logloss", "mean_delta_brier", "mean_delta_penca", "mean_delta_draw_error",
    "collateral_score", "culpability_score", "verdict",
)


def _mean(xs):
    return _st.mean(xs) if xs else 0.0


def culpability_ranking(by_fold_rows: Sequence[Mapping]) -> List[Dict[str, object]]:
    by_comp: Dict[str, list] = {}
    for r in by_fold_rows:
        by_comp.setdefault(str(r["component_id"]), []).append(r)

    entries = []
    for comp, rows in by_comp.items():
        n = len(rows)
        recoveries = [float(r["base_tail5"]) - float(r["abl_tail5"]) for r in rows]  # >0 = mejora cola
        close = sum(1 for x in recoveries if x > 0)
        fraction = close / n if n else 0.0
        mean_rec = _mean(recoveries)
        std_rec = _st.pstdev(recoveries) if n > 1 else 0.0
        consistency = max(0.0, 1.0 - std_rec / (abs(mean_rec) + 1e-6)) if mean_rec != 0 else 0.0
        consistency = min(1.0, consistency)
        mdll = _mean([float(r["delta_logloss"]) for r in rows])
        mdbr = _mean([float(r["delta_brier"]) for r in rows])
        mdpe = _mean([float(r["delta_penca"]) for r in rows])
        mddr = _mean([float(r["delta_draw_error"]) for r in rows])
        collateral = (max(0.0, mdll) / LOGLOSS_TOL + max(0.0, mdbr) / BRIER_TOL
                      + max(0.0, -mdpe) / PENCA_UNIT + max(0.0, mddr) / DRAW_TOL)
        culpability = fraction * max(0.0, mean_rec) * consistency - 0.001 * collateral
        verdict = ("culpable_probable" if (fraction >= 0.60 and mean_rec > 0 and collateral <= 4.0)
                   else "no_concluyente")
        entries.append({
            "component_id": comp,
            "fraction_folds_close_gap": round(fraction, 4),
            "mean_tail5_recovery": round(mean_rec, 6),
            "consistency": round(consistency, 4),
            "mean_delta_logloss": round(mdll, 6),
            "mean_delta_brier": round(mdbr, 6),
            "mean_delta_penca": round(mdpe, 6),
            "mean_delta_draw_error": round(mddr, 6),
            "collateral_score": round(collateral, 4),
            "culpability_score": round(culpability, 8),
            "verdict": verdict,
        })
    entries.sort(key=lambda e: (e["culpability_score"], e["component_id"]), reverse=True)
    for i, e in enumerate(entries, start=1):
        e["rank"] = i
    return entries


__all__ = ["RANKING_COLUMNS", "LOGLOSS_TOL", "BRIER_TOL", "DRAW_TOL", "culpability_ranking"]
