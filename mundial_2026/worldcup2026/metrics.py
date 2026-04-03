from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .config import PARAMS


def avg_or_none(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def brier_decomposition(
    predictions: Sequence[Tuple[float, float, float]],
    outcomes: Sequence[str],
) -> Dict[str, float]:
    if not predictions or not outcomes or len(predictions) != len(outcomes):
        return {"brier": 0.0, "reliability": 0.0, "resolution": 0.0, "uncertainty": 0.0}

    n = len(predictions)
    bar_a = sum(1.0 for outcome in outcomes if outcome == "a") / n
    bar_d = sum(1.0 for outcome in outcomes if outcome == "draw") / n
    bar_b = sum(1.0 for outcome in outcomes if outcome == "b") / n
    uncertainty = (bar_a * (1.0 - bar_a) + bar_d * (1.0 - bar_d) + bar_b * (1.0 - bar_b)) / 3.0

    total_brier = 0.0
    buckets: Dict[float, List[Tuple[Tuple[float, float, float], str]]] = {}
    for triple, outcome in zip(predictions, outcomes):
        pa, pd, pb = triple
        obs_a = 1.0 if outcome == "a" else 0.0
        obs_d = 1.0 if outcome == "draw" else 0.0
        obs_b = 1.0 if outcome == "b" else 0.0
        total_brier += ((pa - obs_a) ** 2 + (pd - obs_d) ** 2 + (pb - obs_b) ** 2) / 3.0
        bucket_key = round(max(pa, pd, pb) * 10.0) / 10.0
        buckets.setdefault(bucket_key, []).append((triple, outcome))

    reliability = 0.0
    resolution = 0.0
    for items in buckets.values():
        nk = len(items)
        avg_pa = sum(item[0][0] for item in items) / nk
        avg_pd = sum(item[0][1] for item in items) / nk
        avg_pb = sum(item[0][2] for item in items) / nk
        obs_a = sum(1.0 for _, outcome in items if outcome == "a") / nk
        obs_d = sum(1.0 for _, outcome in items if outcome == "draw") / nk
        obs_b = sum(1.0 for _, outcome in items if outcome == "b") / nk
        reliability += (nk / n) * (((avg_pa - obs_a) ** 2 + (avg_pd - obs_d) ** 2 + (avg_pb - obs_b) ** 2) / 3.0)
        resolution += (nk / n) * (((obs_a - bar_a) ** 2 + (obs_d - bar_d) ** 2 + (obs_b - bar_b) ** 2) / 3.0)

    return {
        "brier": total_brier / n,
        "reliability": reliability,
        "resolution": resolution,
        "uncertainty": uncertainty,
    }


def summarize_temporal_windows(
    result_logloss: Sequence[float],
    result_brier: Sequence[float],
    result_hits: Sequence[int],
    *,
    fold_size: int = PARAMS.temporal_cv_fold_size,
) -> Dict[str, Optional[float]]:
    if not result_logloss:
        return {"logloss": None, "brier": None, "accuracy": None}
    fold_size = max(1, int(fold_size))
    logloss_windows: List[float] = []
    brier_windows: List[float] = []
    accuracy_windows: List[float] = []
    for start in range(0, len(result_logloss), fold_size):
        end = start + fold_size
        logloss_windows.append(sum(result_logloss[start:end]) / len(result_logloss[start:end]))
        brier_windows.append(sum(result_brier[start:end]) / len(result_brier[start:end]))
        accuracy_windows.append(sum(result_hits[start:end]) / len(result_hits[start:end]))
    return {
        "logloss": avg_or_none(logloss_windows),
        "brier": avg_or_none(brier_windows),
        "accuracy": avg_or_none(accuracy_windows),
    }
