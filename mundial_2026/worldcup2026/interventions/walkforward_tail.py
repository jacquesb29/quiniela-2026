"""Validación walk-forward fold-a-fold de la intervención de colas (F4.2).

Reutiliza EXACTAMENTE los folds de F0.4 (`worldcup2026.walk_forward.temporal_folds`
con el mismo esquema/min_train/step). Compara baseline vs el candidato `fuerte`
de F4.1 por fold. Es validación: NO activa nada, NO toca el modelo ni el flag.

Las funciones de métricas se inyectan (el runner las arma con el modelo); este
módulo solo itera folds, agrega y decide (gate walk-forward).
"""

from __future__ import annotations

import statistics as _st
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Sequence

from worldcup2026.walk_forward import temporal_folds

# Mismos folds que F0.4 (no se crean folds nuevos).
FOLD_SCHEME = "expanding"
FOLD_MIN_TRAIN = 400
FOLD_STEP = 200

FOLD_COLUMNS = (
    "fold_id", "n_train", "n_test",
    "baseline_logloss", "experimental_logloss", "delta_logloss",
    "baseline_brier", "experimental_brier", "delta_brier",
    "baseline_penca", "experimental_penca", "delta_penca",
    "baseline_tail4", "experimental_tail4", "delta_tail4",
    "baseline_tail5", "experimental_tail5", "delta_tail5",
    "baseline_tail6", "experimental_tail6", "delta_tail6",
    "baseline_draw_error", "experimental_draw_error", "delta_draw_error",
)


@dataclass(frozen=True)
class WFTailGateThresholds:
    min_improve_fraction: float = 0.60   # >=60% de folds deben mejorar tail>=5
    not_worse_fraction: float = 0.50     # mayoría de folds: tail>=4 y >=6 no peor
    logloss_tol: float = 0.002
    brier_tol: float = 0.002
    penca_tol: float = 0.0
    draw_tol: float = 0.01
    min_folds: int = 4


def run_tail_walkforward(
    rows: Sequence[Mapping],
    *,
    obs_by_id: Mapping[str, object],
    baseline_metrics_fn: Callable[[List[object]], dict],
    experimental_metrics_fn: Callable[[List[object]], dict],
    scheme: str = FOLD_SCHEME,
    min_train: int = FOLD_MIN_TRAIN,
    step: int = FOLD_STEP,
) -> List[Dict[str, object]]:
    fold_rows: List[Dict[str, object]] = []
    for idx, (train, test) in enumerate(
        temporal_folds(rows, scheme=scheme, min_train=min_train, step=step), start=1
    ):
        test_obs = [obs_by_id[str(r.get("match_id"))] for r in test if str(r.get("match_id")) in obs_by_id]
        if not test_obs:
            continue
        base = baseline_metrics_fn(test_obs)
        exp = experimental_metrics_fn(test_obs)

        def d(metric):  # delta experimental - baseline
            return round(exp[metric] - base[metric], 6)

        fold_rows.append({
            "fold_id": idx, "n_train": len(train), "n_test": len(test_obs),
            "baseline_logloss": round(base["logloss"], 6), "experimental_logloss": round(exp["logloss"], 6),
            "delta_logloss": d("logloss"),
            "baseline_brier": round(base["brier"], 6), "experimental_brier": round(exp["brier"], 6),
            "delta_brier": d("brier"),
            "baseline_penca": round(base["penca_avg"], 6), "experimental_penca": round(exp["penca_avg"], 6),
            "delta_penca": d("penca_avg"),
            "baseline_tail4": round(base["tail_err_4"], 6), "experimental_tail4": round(exp["tail_err_4"], 6),
            "delta_tail4": d("tail_err_4"),
            "baseline_tail5": round(base["tail_err_5"], 6), "experimental_tail5": round(exp["tail_err_5"], 6),
            "delta_tail5": d("tail_err_5"),
            "baseline_tail6": round(base["tail_err_6"], 6), "experimental_tail6": round(exp["tail_err_6"], 6),
            "delta_tail6": d("tail_err_6"),
            "baseline_draw_error": round(base["draw_error"], 6),
            "experimental_draw_error": round(exp["draw_error"], 6),
            "delta_draw_error": d("draw_error"),
        })
    return fold_rows


def _stats(values: Sequence[float]) -> dict:
    if not values:
        return {"mean": "", "median": "", "std": ""}
    return {
        "mean": round(_st.mean(values), 6),
        "median": round(_st.median(values), 6),
        "std": round(_st.pstdev(values), 6),
    }


def summarize_walkforward(fold_rows: Sequence[Mapping]) -> List[dict]:
    n = len(fold_rows)
    # Para errores/logloss/brier: mejora = delta < 0. Para Penca: mejora = delta > 0.
    specs = [
        ("logloss", "delta_logloss", "lower"), ("brier", "delta_brier", "lower"),
        ("penca", "delta_penca", "higher"),
        ("tail4", "delta_tail4", "lower"), ("tail5", "delta_tail5", "lower"),
        ("tail6", "delta_tail6", "lower"), ("draw_error", "delta_draw_error", "lower"),
    ]
    rows = []
    for name, key, direction in specs:
        deltas = [float(f[key]) for f in fold_rows]
        if direction == "lower":
            won = sum(1 for x in deltas if x < 0)
        else:
            won = sum(1 for x in deltas if x > 0)
        lost = n - won
        s = _stats(deltas)
        rows.append({
            "metric": name, "mean": s["mean"], "median": s["median"], "std": s["std"],
            "folds_won": won, "folds_lost": lost,
            "pct_improvement": round(won / n, 4) if n else "",
        })
    return rows


def decide_tail_walkforward(fold_rows: Sequence[Mapping], *,
                            thresholds: WFTailGateThresholds = WFTailGateThresholds()) -> dict:
    n = len(fold_rows)
    t = thresholds
    if n < t.min_folds:
        return {"decision": "keep_off", "reason": f"folds insuficientes (n={n} < {t.min_folds})",
                "n_folds": n, "tail5_improved_fraction": "", }

    improved5 = sum(1 for f in fold_rows if float(f["experimental_tail5"]) < float(f["baseline_tail5"]))
    not_worse4 = sum(1 for f in fold_rows if float(f["experimental_tail4"]) <= float(f["baseline_tail4"]) + 1e-9)
    not_worse6 = sum(1 for f in fold_rows if float(f["experimental_tail6"]) <= float(f["baseline_tail6"]) + 1e-9)
    mean_dll = _st.mean(float(f["delta_logloss"]) for f in fold_rows)
    mean_dbr = _st.mean(float(f["delta_brier"]) for f in fold_rows)
    mean_dpe = _st.mean(float(f["delta_penca"]) for f in fold_rows)
    mean_ddr = _st.mean(float(f["delta_draw_error"]) for f in fold_rows)

    frac5 = improved5 / n
    frac4_ok = (not_worse4 / n) >= t.not_worse_fraction
    frac6_ok = (not_worse6 / n) >= t.not_worse_fraction
    majority5 = frac5 >= t.min_improve_fraction
    logloss_ok = mean_dll <= t.logloss_tol
    brier_ok = mean_dbr <= t.brier_tol
    penca_ok = mean_dpe >= -t.penca_tol
    draw_ok = mean_ddr <= t.draw_tol

    activate = majority5 and frac4_ok and frac6_ok and logloss_ok and brier_ok and penca_ok and draw_ok
    if activate:
        decision, reason = "activate", "mejora tail>=5 en mayoría de folds sin daño en tail>=4/>=6, log-loss, Brier, Penca ni empates"
    else:
        fails = []
        if not majority5:
            fails.append(f"solo {frac5:.0%} de folds mejoran tail>=5 (<{t.min_improve_fraction:.0%})")
        if not frac4_ok:
            fails.append("tail>=4 empeora en demasiados folds")
        if not frac6_ok:
            fails.append("tail>=6 empeora en demasiados folds")
        if not logloss_ok:
            fails.append("log-loss medio empeora")
        if not brier_ok:
            fails.append("Brier medio empeora")
        if not penca_ok:
            fails.append("Penca media empeora")
        if not draw_ok:
            fails.append("empates empeoran")
        decision, reason = "keep_off", "; ".join(fails)
    return {
        "decision": decision, "reason": reason, "n_folds": n,
        "tail5_improved_fraction": round(frac5, 4),
        "tail4_not_worse_fraction": round(not_worse4 / n, 4),
        "tail6_not_worse_fraction": round(not_worse6 / n, 4),
        "mean_delta_logloss": round(mean_dll, 6), "mean_delta_brier": round(mean_dbr, 6),
        "mean_delta_penca": round(mean_dpe, 6), "mean_delta_draw_error": round(mean_ddr, 6),
    }


__all__ = [
    "FOLD_SCHEME", "FOLD_MIN_TRAIN", "FOLD_STEP", "FOLD_COLUMNS",
    "WFTailGateThresholds", "run_tail_walkforward", "summarize_walkforward", "decide_tail_walkforward",
]
