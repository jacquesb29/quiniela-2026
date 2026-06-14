"""Atribución walk-forward fold-a-fold por componente (F5). Reusa folds de F0.4."""

from __future__ import annotations

from typing import Callable, Dict, List, Mapping, Sequence

from worldcup2026.walk_forward import temporal_folds

FOLD_SCHEME = "expanding"
FOLD_MIN_TRAIN = 400
FOLD_STEP = 200

BY_FOLD_COLUMNS = (
    "component_id", "fold_id", "n_test",
    "base_tail4", "abl_tail4", "delta_tail4",
    "base_tail5", "abl_tail5", "delta_tail5",
    "base_tail6", "abl_tail6", "delta_tail6",
    "delta_goal_total_bias", "delta_exact_top1", "delta_penca",
    "delta_logloss", "delta_brier", "delta_draw_error",
)


def run_component_walkforward(
    rows: Sequence[Mapping],
    *,
    component_id: str,
    obs_by_id: Mapping[str, object],
    baseline_metrics_fn: Callable[[List[object]], dict],
    ablated_metrics_fn: Callable[[List[object]], dict],
    scheme: str = FOLD_SCHEME,
    min_train: int = FOLD_MIN_TRAIN,
    step: int = FOLD_STEP,
) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for idx, (_, test) in enumerate(
        temporal_folds(rows, scheme=scheme, min_train=min_train, step=step), start=1
    ):
        test_obs = [obs_by_id[str(r.get("match_id"))] for r in test if str(r.get("match_id")) in obs_by_id]
        if not test_obs:
            continue
        b = baseline_metrics_fn(test_obs)
        a = ablated_metrics_fn(test_obs)
        out.append({
            "component_id": component_id, "fold_id": idx, "n_test": len(test_obs),
            "base_tail4": round(b["tail_err_4"], 6), "abl_tail4": round(a["tail_err_4"], 6),
            "delta_tail4": round(a["tail_err_4"] - b["tail_err_4"], 6),
            "base_tail5": round(b["tail_err_5"], 6), "abl_tail5": round(a["tail_err_5"], 6),
            "delta_tail5": round(a["tail_err_5"] - b["tail_err_5"], 6),
            "base_tail6": round(b["tail_err_6"], 6), "abl_tail6": round(a["tail_err_6"], 6),
            "delta_tail6": round(a["tail_err_6"] - b["tail_err_6"], 6),
            "delta_goal_total_bias": round(a["goal_total_bias"] - b["goal_total_bias"], 6),
            "delta_exact_top1": round(a["exact_top1"] - b["exact_top1"], 6),
            "delta_penca": round(a["penca_avg"] - b["penca_avg"], 6),
            "delta_logloss": round(a["logloss"] - b["logloss"], 6),
            "delta_brier": round(a["brier"] - b["brier"], 6),
            "delta_draw_error": round(a["draw_error"] - b["draw_error"], 6),
        })
    return out


__all__ = ["FOLD_SCHEME", "FOLD_MIN_TRAIN", "FOLD_STEP", "BY_FOLD_COLUMNS", "run_component_walkforward"]
