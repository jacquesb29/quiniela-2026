from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence

from .benchmarks import (
    BenchmarkPrediction,
    HistoricalRow,
    PredictionFn,
    actual_outcome,
    brier_score,
    coerce_prediction,
    elo_prediction,
    log_loss,
    market_prediction,
    ranked_probability_score,
    read_csv_rows,
    safe_float,
    safe_int,
    write_csv_rows,
)


REQUIRED_HISTORICAL_COLUMNS = (
    "date",
    "competition",
    "team_a",
    "team_b",
    "goals_a",
    "goals_b",
    "neutral",
    "knockout",
    "elo_a_pre",
    "elo_b_pre",
    "fifa_rank_a_pre",
    "fifa_rank_b_pre",
    "market_prob_a_pre",
    "market_prob_draw_pre",
    "market_prob_b_pre",
    "squad_quality_a_pre",
    "squad_quality_b_pre",
)


def validate_historical_rows(rows: Sequence[HistoricalRow]) -> List[str]:
    if not rows:
        return ["historical_matches.csv no tiene filas."]
    available = set(rows[0].keys())
    missing = [column for column in REQUIRED_HISTORICAL_COLUMNS if column not in available]
    if missing:
        return [f"Faltan columnas requeridas: {', '.join(missing)}."]
    return []


def phase_from_row(row: HistoricalRow) -> str:
    value = str(row.get("phase") or row.get("stage") or "").strip().lower()
    if value:
        if "group" in value or "grupo" in value:
            return "group"
        if "knockout" in value or "elimin" in value or "round" in value:
            return "knockout"
        return value
    knockout = str(row.get("knockout", "")).strip().lower()
    return "knockout" if knockout in {"1", "true", "yes", "y", "si", "sí"} else "group"


def default_backtest_prediction(row: HistoricalRow) -> Optional[BenchmarkPrediction]:
    """Fallback audit baseline when no full-model adapter is injected.

    This is deliberately simple: market if available, otherwise Elo.
    It does not replace the project model; it only lets the backtest scaffold
    produce metrics before a full-model prediction adapter is wired in.
    """

    prediction = market_prediction(row) or elo_prediction(row)
    return coerce_prediction("baseline_disponible", prediction)


def predicted_outcome_from_prediction(prediction: BenchmarkPrediction) -> str:
    probabilities = prediction.probabilities()
    return max(probabilities.items(), key=lambda item: item[1])[0]


def prediction_confidence(prediction: BenchmarkPrediction) -> float:
    return max(prediction.prob_a, prediction.prob_draw, prediction.prob_b)


def prediction_optional_float(raw_prediction: object, key: str) -> object:
    if isinstance(raw_prediction, Mapping):
        value = raw_prediction.get(key)
    else:
        value = getattr(raw_prediction, key, None)
    parsed = safe_float(value)
    return parsed if parsed is not None else ""


def calibration_bucket(confidence: float, bins: int = 10) -> str:
    bins = max(2, int(bins))
    lower = int(min(bins - 1, max(0, confidence * bins))) / bins
    upper = lower + 1.0 / bins
    return f"{lower:.1f}-{upper:.1f}"


def evaluate_backtest_rows(
    rows: Sequence[HistoricalRow],
    *,
    prediction_fn: Optional[PredictionFn] = None,
    model_name: str = "modelo",
    calibration_bins: int = 10,
) -> List[Dict[str, object]]:
    predictor: PredictionFn = prediction_fn or default_backtest_prediction
    evaluated: List[Dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        outcome = actual_outcome(row)
        if outcome is None:
            continue
        raw_prediction = predictor(row)
        prediction = coerce_prediction(model_name, raw_prediction)
        if prediction is None:
            continue
        predicted = predicted_outcome_from_prediction(prediction)
        goals_a = safe_int(row.get("goals_a"))
        goals_b = safe_int(row.get("goals_b"))
        xg_mae_a = ""
        xg_mae_b = ""
        xg_mae_total = ""
        if prediction.expected_goals_a is not None and goals_a is not None:
            xg_mae_a = abs(prediction.expected_goals_a - goals_a)
        if prediction.expected_goals_b is not None and goals_b is not None:
            xg_mae_b = abs(prediction.expected_goals_b - goals_b)
        if xg_mae_a != "" and xg_mae_b != "":
            xg_mae_total = float(xg_mae_a) + float(xg_mae_b)
        confidence = prediction_confidence(prediction)
        hit = 1 if predicted == outcome else 0
        evaluated.append(
            {
                "match_id": row.get("match_id") or row.get("id") or index,
                "date": row.get("date", ""),
                "competition": row.get("competition", ""),
                "phase": phase_from_row(row),
                "team_a": row.get("team_a", ""),
                "team_b": row.get("team_b", ""),
                "model": prediction.benchmark,
                "prob_a": prediction.prob_a,
                "prob_draw": prediction.prob_draw,
                "prob_b": prediction.prob_b,
                "expected_goals_a": prediction.expected_goals_a,
                "expected_goals_b": prediction.expected_goals_b,
                "most_likely_score": prediction.most_likely_score,
                "actual_outcome": outcome,
                "predicted_outcome": predicted,
                "accuracy": hit,
                "brier_score": brier_score(prediction, outcome),
                "log_loss": log_loss(prediction, outcome),
                "ranked_probability_score": ranked_probability_score(prediction, outcome),
                "mae_goals_a": xg_mae_a,
                "mae_goals_b": xg_mae_b,
                "mae_total_goals": xg_mae_total,
                "expected_penca_points": prediction_optional_float(raw_prediction, "expected_penca_points"),
                "confidence": confidence,
                "calibration_bucket": calibration_bucket(confidence, calibration_bins),
            }
        )
    return evaluated


def _mean(values: Sequence[object]) -> Optional[float]:
    parsed = [safe_float(value) for value in values]
    clean = [value for value in parsed if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def summarize_backtest(evaluated_rows: Sequence[Mapping[str, object]]) -> Dict[str, object]:
    if not evaluated_rows:
        return {
            "matches": 0,
            "accuracy_1x2": "",
            "brier_score": "",
            "log_loss": "",
            "ranked_probability_score": "",
            "mae_goals_a": "",
            "mae_goals_b": "",
            "mae_total_goals": "",
        }
    return {
        "matches": len(evaluated_rows),
        "accuracy_1x2": _mean([row.get("accuracy") for row in evaluated_rows]),
        "brier_score": _mean([row.get("brier_score") for row in evaluated_rows]),
        "log_loss": _mean([row.get("log_loss") for row in evaluated_rows]),
        "ranked_probability_score": _mean([row.get("ranked_probability_score") for row in evaluated_rows]),
        "mae_goals_a": _mean([row.get("mae_goals_a") for row in evaluated_rows]),
        "mae_goals_b": _mean([row.get("mae_goals_b") for row in evaluated_rows]),
        "mae_total_goals": _mean([row.get("mae_total_goals") for row in evaluated_rows]),
    }


def summarize_by_key(
    evaluated_rows: Sequence[Mapping[str, object]],
    key: str,
) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Mapping[str, object]]] = defaultdict(list)
    for row in evaluated_rows:
        grouped[str(row.get(key) or "sin_clasificar")].append(row)
    output = []
    for value, items in sorted(grouped.items()):
        summary = summarize_backtest(items)
        summary[key] = value
        output.append(summary)
    return output


def calibration_bin_rows(evaluated_rows: Sequence[Mapping[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Mapping[str, object]]] = defaultdict(list)
    for row in evaluated_rows:
        grouped[str(row.get("calibration_bucket") or "sin_bucket")].append(row)
    output = []
    for bucket, items in sorted(grouped.items()):
        output.append(
            {
                "bucket": bucket,
                "matches": len(items),
                "avg_predicted_confidence": _mean([row.get("confidence") for row in items]),
                "observed_hit_rate": _mean([row.get("accuracy") for row in items]),
                "avg_brier_score": _mean([row.get("brier_score") for row in items]),
                "avg_log_loss": _mean([row.get("log_loss") for row in items]),
            }
        )
    return output


def write_summary_csv(path: str | Path, summary: Mapping[str, object]) -> None:
    rows = [{"metric": key, "value": value} for key, value in summary.items()]
    write_csv_rows(path, rows)


def run_historical_backtest(
    historical_matches_csv: str | Path,
    *,
    output_dir: str | Path = ".",
    prediction_fn: Optional[PredictionFn] = None,
    model_name: str = "modelo",
    calibration_bins_count: int = 10,
    write_predictions: bool = True,
) -> Dict[str, object]:
    rows = read_csv_rows(historical_matches_csv)
    validation_errors = validate_historical_rows(rows)
    if validation_errors:
        raise ValueError(" ".join(validation_errors))

    evaluated = evaluate_backtest_rows(
        rows,
        prediction_fn=prediction_fn,
        model_name=model_name,
        calibration_bins=calibration_bins_count,
    )
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    summary = summarize_backtest(evaluated)

    write_summary_csv(output_path / "backtest_summary.csv", summary)
    write_csv_rows(output_path / "backtest_by_competition.csv", summarize_by_key(evaluated, "competition"))
    write_csv_rows(output_path / "backtest_by_phase.csv", summarize_by_key(evaluated, "phase"))
    write_csv_rows(output_path / "calibration_bins.csv", calibration_bin_rows(evaluated))
    if write_predictions:
        write_csv_rows(output_path / "backtest_predictions.csv", evaluated)
    return {
        "summary": summary,
        "rows": evaluated,
        "by_competition": summarize_by_key(evaluated, "competition"),
        "by_phase": summarize_by_key(evaluated, "phase"),
        "calibration_bins": calibration_bin_rows(evaluated),
    }


def run_historical_backtest_cli(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Evalua un historical_matches.csv contra un adaptador predictivo o baseline disponible.")
    parser.add_argument("historical_matches_csv", help="CSV historico con columnas pre-partido.")
    parser.add_argument("--output-dir", default=".", help="Directorio donde guardar backtest_summary.csv y reportes.")
    parser.add_argument("--model-name", default="baseline_disponible", help="Nombre del modelo reportado si no hay adaptador externo.")
    args = parser.parse_args(argv)
    run_historical_backtest(args.historical_matches_csv, output_dir=args.output_dir, model_name=args.model_name)
    return 0


__all__ = [
    "REQUIRED_HISTORICAL_COLUMNS",
    "calibration_bin_rows",
    "default_backtest_prediction",
    "evaluate_backtest_rows",
    "run_historical_backtest",
    "run_historical_backtest_cli",
    "summarize_backtest",
    "summarize_by_key",
    "validate_historical_rows",
]


if __name__ == "__main__":
    raise SystemExit(run_historical_backtest_cli())
