from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence

from .backtesting import evaluate_backtest_rows, summarize_backtest
from .benchmarks import BenchmarkPrediction, HistoricalRow, PredictionFn, coerce_prediction, read_csv_rows, safe_float, write_csv_rows


AblationPredictionFn = Callable[[HistoricalRow], Optional[BenchmarkPrediction]]


ABLATION_BLOCKS: tuple[str, ...] = (
    "sin_mercado",
    "sin_elo",
    "sin_fifa",
    "sin_historia",
    "sin_plantilla",
    "sin_contexto",
    "sin_coach_bias",
    "sin_chemistry_bias",
    "sin_discipline_bias",
    "sin_resource_index",
    "sin_consensus_priors",
    "sin_tactical_bias",
    "sin_state_dynamic",
)


@dataclass(frozen=True)
class AblationResult:
    variant: str
    matches: int
    brier_score: Optional[float]
    log_loss: Optional[float]
    accuracy: Optional[float]
    mae_total_goals: Optional[float]
    expected_penca_points: Optional[float]
    delta_brier_vs_full: Optional[float]
    delta_log_loss_vs_full: Optional[float]
    delta_accuracy_vs_full: Optional[float]
    recommendation: str
    stripped_fields: int = 0
    applicable: bool = True


BLOCK_PREFIXES: Dict[str, tuple[str, ...]] = {
    "sin_mercado": ("market_", "consensus_", "external_"),
    "sin_elo": ("elo_",),
    "sin_fifa": ("fifa_",),
    "sin_historia": ("historical_", "history_", "heritage_", "world_cup_"),
    "sin_plantilla": ("squad_", "player_", "club_quality_", "bench_", "top_5_", "median_player_"),
    "sin_contexto": ("neutral", "home_", "venue_", "travel_", "rest_", "weather_", "altitude_", "heat_"),
    "sin_coach_bias": ("coach_",),
    "sin_chemistry_bias": ("chemistry_", "cohesion_", "shared_"),
    "sin_discipline_bias": ("discipline_", "yellow_", "red_", "card_", "foul_", "referee_"),
    "sin_resource_index": ("resource_", "gdp_", "population_", "macro_"),
    "sin_consensus_priors": ("consensus_", "external_", "goldman_", "opta_", "forecast_"),
    "sin_tactical_bias": ("tactical_", "press", "transition_", "aerial_", "set_piece_", "midfield_", "counterattack_"),
    "sin_state_dynamic": ("state_", "morale_", "recent_", "fatigue_", "availability_", "live_"),
}

NOT_APPLICABLE_RECOMMENDATION = "no_aplicable: feature ausente en histórico"


def _field_has_value(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def strip_block_fields(row: HistoricalRow, block: str) -> tuple[Dict[str, object], int]:
    """Elimina las columnas del bloque y devuelve (fila_sin_bloque, n_eliminadas).

    `n_eliminadas` cuenta solo columnas que existían y tenían valor no vacío;
    así una columna presente pero vacía no cuenta como "ablacionada" y la
    ablation no puede reportar evidencia falsa sobre una feature ausente.
    """

    stripped = dict(row)
    stripped_count = 0
    for prefix in BLOCK_PREFIXES.get(block, ()):
        for key in list(stripped):
            if str(key).startswith(prefix):
                had_value = _field_has_value(stripped.get(key))
                stripped.pop(key, None)
                if had_value:
                    stripped_count += 1
    return stripped, stripped_count


def block_applicable(row: HistoricalRow, block: str) -> bool:
    """True si el bloque tiene al menos una columna presente y no vacía."""

    for prefix in BLOCK_PREFIXES.get(block, ()):
        for key in row:
            if str(key).startswith(prefix) and _field_has_value(row.get(key)):
                return True
    return False


def block_stripped_field_count(rows: Sequence[HistoricalRow], block: str) -> int:
    """Número de columnas distintas que el bloque elimina con valor en algún row."""

    columns: set[str] = set()
    for row in rows:
        for prefix in BLOCK_PREFIXES.get(block, ()):
            for key in row:
                if str(key).startswith(prefix) and _field_has_value(row.get(key)):
                    columns.add(str(key))
    return len(columns)


def _summary_metric(summary: Mapping[str, object], key: str) -> Optional[float]:
    return safe_float(summary.get(key))


def _mean_expected_penca_points(rows: Sequence[Mapping[str, object]]) -> Optional[float]:
    values = [
        safe_float(row.get("expected_penca_points"))
        for row in rows
        if safe_float(row.get("expected_penca_points")) is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _recommendation(
    *,
    variant: str,
    full_log_loss: Optional[float],
    variant_log_loss: Optional[float],
    full_brier: Optional[float],
    variant_brier: Optional[float],
) -> str:
    if variant_log_loss is None or full_log_loss is None:
        return "sin_datos_suficientes"
    log_delta = variant_log_loss - full_log_loss
    brier_delta = (variant_brier - full_brier) if variant_brier is not None and full_brier is not None else 0.0
    if log_delta > 0.01 or brier_delta > 0.004:
        return f"conservar_o_reforzar_bloque; quitar {variant} empeora metricas"
    if log_delta < -0.01 or brier_delta < -0.004:
        return f"reducir_bloque; quitar {variant} mejora metricas"
    return "impacto_neutro; mantener_con_peso_suave"


def evaluate_ablation(
    rows: Sequence[HistoricalRow],
    *,
    full_model_fn: PredictionFn,
    variant_fns: Optional[Mapping[str, PredictionFn]] = None,
) -> List[AblationResult]:
    variant_fns = dict(variant_fns or {})
    full_rows = evaluate_backtest_rows(rows, prediction_fn=full_model_fn, model_name="modelo_completo")
    full_summary = summarize_backtest(full_rows)
    full_brier = _summary_metric(full_summary, "brier_score")
    full_log_loss = _summary_metric(full_summary, "log_loss")
    full_accuracy = _summary_metric(full_summary, "accuracy_1x2")
    full_mae = _summary_metric(full_summary, "mae_total_goals")
    full_penca = _mean_expected_penca_points(full_rows)

    results = [
        AblationResult(
            variant="modelo_completo",
            matches=int(full_summary.get("matches") or 0),
            brier_score=full_brier,
            log_loss=full_log_loss,
            accuracy=full_accuracy,
            mae_total_goals=full_mae,
            expected_penca_points=full_penca,
            delta_brier_vs_full=0.0 if full_brier is not None else None,
            delta_log_loss_vs_full=0.0 if full_log_loss is not None else None,
            delta_accuracy_vs_full=0.0 if full_accuracy is not None else None,
            recommendation="referencia",
        )
    ]

    for block in ABLATION_BLOCKS:
        applicable = any(block_applicable(row, block) for row in rows)
        stripped_fields = block_stripped_field_count(rows, block)
        prediction_fn = variant_fns.get(block)
        if prediction_fn is None:
            prediction_fn = lambda row, block=block: full_model_fn(strip_block_fields(row, block)[0])
        evaluated = evaluate_backtest_rows(rows, prediction_fn=prediction_fn, model_name=block)
        summary = summarize_backtest(evaluated)
        brier = _summary_metric(summary, "brier_score")
        logloss = _summary_metric(summary, "log_loss")
        accuracy = _summary_metric(summary, "accuracy_1x2")
        mae = _summary_metric(summary, "mae_total_goals")
        penca = _mean_expected_penca_points(evaluated)
        if not applicable:
            recommendation = NOT_APPLICABLE_RECOMMENDATION
        else:
            recommendation = _recommendation(
                variant=block,
                full_log_loss=full_log_loss,
                variant_log_loss=logloss,
                full_brier=full_brier,
                variant_brier=brier,
            )
        results.append(
            AblationResult(
                variant=block,
                matches=int(summary.get("matches") or 0),
                brier_score=brier,
                log_loss=logloss,
                accuracy=accuracy,
                mae_total_goals=mae,
                expected_penca_points=penca,
                delta_brier_vs_full=(brier - full_brier) if brier is not None and full_brier is not None else None,
                delta_log_loss_vs_full=(logloss - full_log_loss) if logloss is not None and full_log_loss is not None else None,
                delta_accuracy_vs_full=(accuracy - full_accuracy) if accuracy is not None and full_accuracy is not None else None,
                recommendation=recommendation,
                stripped_fields=stripped_fields,
                applicable=applicable,
            )
        )
    return results


def ablation_results_to_rows(results: Sequence[AblationResult]) -> List[Dict[str, object]]:
    return [
        {
            "variant": result.variant,
            "matches": result.matches,
            "brier_score": result.brier_score,
            "log_loss": result.log_loss,
            "accuracy": result.accuracy,
            "mae_total_goals": result.mae_total_goals,
            "expected_penca_points": result.expected_penca_points,
            "delta_brier_vs_full": result.delta_brier_vs_full,
            "delta_log_loss_vs_full": result.delta_log_loss_vs_full,
            "delta_accuracy_vs_full": result.delta_accuracy_vs_full,
            "stripped_fields": result.stripped_fields,
            "applicable": result.applicable,
            "recommendation": result.recommendation,
        }
        for result in results
    ]


def run_ablation(
    historical_matches_csv: str | Path,
    *,
    full_model_fn: PredictionFn,
    output_csv: str | Path = "ablation_results.csv",
    variant_fns: Optional[Mapping[str, PredictionFn]] = None,
) -> List[AblationResult]:
    rows = read_csv_rows(historical_matches_csv)
    results = evaluate_ablation(rows, full_model_fn=full_model_fn, variant_fns=variant_fns)
    write_csv_rows(output_csv, ablation_results_to_rows(results))
    return results


def unavailable_full_model_adapter(row: HistoricalRow) -> Optional[BenchmarkPrediction]:
    raise RuntimeError(
        "Ablation requiere un full_model_fn que llame al modelo completo actual. "
        "Este modulo no modifica ni importa el monolito por defecto."
    )


def run_ablation_cli(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Estructura de ablation; requiere adaptador del modelo completo para ejecutarse.")
    parser.add_argument("historical_matches_csv", help="CSV historico con columnas pre-partido.")
    parser.add_argument("--output-csv", default="ablation_results.csv", help="Salida CSV.")
    args = parser.parse_args(argv)
    run_ablation(args.historical_matches_csv, full_model_fn=unavailable_full_model_adapter, output_csv=args.output_csv)
    return 0


__all__ = [
    "ABLATION_BLOCKS",
    "BLOCK_PREFIXES",
    "NOT_APPLICABLE_RECOMMENDATION",
    "AblationResult",
    "ablation_results_to_rows",
    "block_applicable",
    "block_stripped_field_count",
    "evaluate_ablation",
    "run_ablation",
    "strip_block_fields",
]


if __name__ == "__main__":
    raise SystemExit(run_ablation_cli())
