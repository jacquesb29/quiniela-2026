"""Comparación honesta pareada modelo vs benchmarks (F0.3).

Compara el modelo de producción contra cada baseline SOLO en los partidos donde
ambos tienen predicción válida (mismo `match_id`). Nunca mezcla poblaciones
distintas y nunca declara "no superado" un baseline sin muestra (p.ej. mercado
sin odds históricas): ese caso se marca `sin_muestra`.

No toca el modelo, ni pesos, ni lambdas, ni la capa Penca. Solo agrega métricas
ya calculadas por el harness de backtest/benchmarks.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence

# Umbrales de muestra (coherentes con VALIDATION_GATE.md).
MIN_EXPLORATORY = 30   # n < 30 -> exploratorio/provisional
DEFAULT_BASELINES = ("poisson_simple", "elo_puro", "mercado_puro")
MARKET_BENCHMARK = "mercado_puro"

# Estados de comparación.
STATUS_SIN_MUESTRA = "sin_muestra"
STATUS_PROVISIONAL = "provisional"
STATUS_SUPERADO = "medido_superado"
STATUS_NO_SUPERADO = "medido_no_superado"


def _to_float(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _match_key(row: Mapping[str, object]) -> Optional[str]:
    key = row.get("match_id")
    if key is None or str(key).strip() == "":
        return None
    return str(key)


def _valid_metric_index(rows: Sequence[Mapping[str, object]]) -> Dict[str, Dict[str, float]]:
    """Indexa por match_id las filas con brier/logloss numéricos (predicción válida)."""

    index: Dict[str, Dict[str, float]] = {}
    for row in rows:
        key = _match_key(row)
        if key is None:
            continue
        brier = _to_float(row.get("brier_score"))
        logloss = _to_float(row.get("log_loss"))
        if brier is None or logloss is None:
            continue
        # Última gana si hubiera duplicados del mismo benchmark/modelo.
        index[key] = {"brier": brier, "log_loss": logloss}
    return index


def market_coverage_summary(
    benchmark_rows: Sequence[Mapping[str, object]],
    *,
    market_benchmark: str = MARKET_BENCHMARK,
) -> Dict[str, object]:
    """Cobertura de mercado: cuántos partidos distintos tienen odds históricas usables."""

    all_matches = set()
    market_matches = set()
    for row in benchmark_rows:
        key = _match_key(row)
        if key is None:
            continue
        all_matches.add(key)
        if str(row.get("benchmark")) == market_benchmark and _to_float(row.get("brier_score")) is not None:
            market_matches.add(key)
    n_total = len(all_matches)
    n_with_market = len(market_matches)
    coverage = (n_with_market / n_total) if n_total else 0.0
    return {
        "n_total_matches": n_total,
        "n_with_market": n_with_market,
        "market_coverage_pct": round(100.0 * coverage, 4),
        "has_market_sample": n_with_market > 0,
    }


def _comparison_status(n_paired: int, beats: Optional[bool]) -> str:
    if n_paired == 0:
        return STATUS_SIN_MUESTRA
    if n_paired < MIN_EXPLORATORY:
        return STATUS_PROVISIONAL
    return STATUS_SUPERADO if beats else STATUS_NO_SUPERADO


def paired_benchmark_comparison(
    model_rows: Sequence[Mapping[str, object]],
    benchmark_rows: Sequence[Mapping[str, object]],
    *,
    model_name: str = "modelo_completo",
    baselines: Sequence[str] = DEFAULT_BASELINES,
) -> List[Dict[str, object]]:
    """Compara el modelo vs cada baseline solo en partidos pareados.

    `model_rows`: filas por partido del modelo (backtest_predictions).
    `benchmark_rows`: filas por partido/benchmark (benchmark_results).
    Devuelve una fila por baseline con n pareado, deltas, beats y estado.
    """

    model_index = _valid_metric_index(model_rows)

    benchmark_by_name: Dict[str, List[Mapping[str, object]]] = {}
    for row in benchmark_rows:
        benchmark_by_name.setdefault(str(row.get("benchmark")), []).append(row)

    results: List[Dict[str, object]] = []
    for baseline in baselines:
        baseline_index = _valid_metric_index(benchmark_by_name.get(baseline, []))
        paired_keys = sorted(set(model_index) & set(baseline_index))
        n_paired = len(paired_keys)

        if n_paired == 0:
            results.append({
                "baseline": baseline,
                "n_paired": 0,
                "model_brier": "",
                "baseline_brier": "",
                "delta_brier": "",
                "model_logloss": "",
                "baseline_logloss": "",
                "delta_logloss": "",
                "beats": "",
                "comparison_status": STATUS_SIN_MUESTRA,
            })
            continue

        model_brier = sum(model_index[k]["brier"] for k in paired_keys) / n_paired
        model_logloss = sum(model_index[k]["log_loss"] for k in paired_keys) / n_paired
        base_brier = sum(baseline_index[k]["brier"] for k in paired_keys) / n_paired
        base_logloss = sum(baseline_index[k]["log_loss"] for k in paired_keys) / n_paired
        delta_brier = model_brier - base_brier
        delta_logloss = model_logloss - base_logloss
        # "beats" = el modelo mejora (menor) log-loss respecto al baseline en la
        # misma población pareada. Menor log-loss es mejor.
        beats = delta_logloss < 0.0
        results.append({
            "baseline": baseline,
            "n_paired": n_paired,
            "model_brier": model_brier,
            "baseline_brier": base_brier,
            "delta_brier": delta_brier,
            "model_logloss": model_logloss,
            "baseline_logloss": base_logloss,
            "delta_logloss": delta_logloss,
            "beats": beats,
            "comparison_status": _comparison_status(n_paired, beats),
        })
    return results


def best_comparable_baseline_logloss(
    comparison_rows: Sequence[Mapping[str, object]],
) -> Dict[str, Optional[float]]:
    """Devuelve {baseline: logloss} solo de baselines con muestra pareada (>0)."""

    out: Dict[str, Optional[float]] = {}
    for row in comparison_rows:
        if int(row.get("n_paired") or 0) <= 0:
            continue
        logloss = _to_float(row.get("baseline_logloss"))
        if logloss is not None:
            out[str(row.get("baseline"))] = logloss
    return out


__all__ = [
    "MIN_EXPLORATORY",
    "DEFAULT_BASELINES",
    "MARKET_BENCHMARK",
    "STATUS_SIN_MUESTRA",
    "STATUS_PROVISIONAL",
    "STATUS_SUPERADO",
    "STATUS_NO_SUPERADO",
    "market_coverage_summary",
    "paired_benchmark_comparison",
    "best_comparable_baseline_logloss",
]
