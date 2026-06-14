from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


Outcome = str
Score = Tuple[int, int]
HistoricalRow = Mapping[str, object]
PredictionFn = Callable[[HistoricalRow], Optional["BenchmarkPrediction"]]


OUTCOMES: Tuple[Outcome, Outcome, Outcome] = ("a", "draw", "b")
BENCHMARK_NAMES: Tuple[str, ...] = (
    "fifa_ranking_puro",
    "elo_puro",
    "mercado_puro",
    "poisson_simple",
    "favorito_historico",
    "modelo_sin_mercado",
)


@dataclass(frozen=True)
class BenchmarkPrediction:
    benchmark: str
    prob_a: float
    prob_draw: float
    prob_b: float
    expected_goals_a: Optional[float] = None
    expected_goals_b: Optional[float] = None
    most_likely_score: Optional[str] = None
    notes: str = ""

    def probabilities(self) -> Dict[Outcome, float]:
        return {"a": self.prob_a, "draw": self.prob_draw, "b": self.prob_b}


def safe_float(value: object, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return parsed


def safe_int(value: object, default: Optional[int] = None) -> Optional[int]:
    parsed = safe_float(value)
    if parsed is None:
        return default
    return int(parsed)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_probabilities(
    prob_a: float,
    prob_draw: float,
    prob_b: float,
) -> Tuple[float, float, float]:
    values = [max(0.0, float(prob_a)), max(0.0, float(prob_draw)), max(0.0, float(prob_b))]
    total = sum(values)
    if total <= 0.0:
        return (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)
    return (values[0] / total, values[1] / total, values[2] / total)


def actual_outcome(row: HistoricalRow) -> Optional[Outcome]:
    goals_a = safe_int(row.get("goals_a"))
    goals_b = safe_int(row.get("goals_b"))
    if goals_a is None or goals_b is None:
        return None
    if goals_a > goals_b:
        return "a"
    if goals_b > goals_a:
        return "b"
    return "draw"


def actual_score(row: HistoricalRow) -> Optional[str]:
    goals_a = safe_int(row.get("goals_a"))
    goals_b = safe_int(row.get("goals_b"))
    if goals_a is None or goals_b is None:
        return None
    return f"{goals_a}-{goals_b}"


def predicted_outcome(prediction: BenchmarkPrediction) -> Outcome:
    return max(prediction.probabilities().items(), key=lambda item: item[1])[0]


def brier_score(prediction: BenchmarkPrediction, outcome: Outcome) -> float:
    probs = prediction.probabilities()
    return sum((probs[key] - (1.0 if outcome == key else 0.0)) ** 2 for key in OUTCOMES) / 3.0


def log_loss(prediction: BenchmarkPrediction, outcome: Outcome) -> float:
    return -math.log(max(prediction.probabilities().get(outcome, 0.0), 1e-12))


def ranked_probability_score(prediction: BenchmarkPrediction, outcome: Outcome) -> float:
    probs = [prediction.prob_a, prediction.prob_draw, prediction.prob_b]
    observed = [1.0 if outcome == key else 0.0 for key in OUTCOMES]
    cumulative_pred = 0.0
    cumulative_obs = 0.0
    total = 0.0
    for index in range(len(OUTCOMES) - 1):
        cumulative_pred += probs[index]
        cumulative_obs += observed[index]
        total += (cumulative_pred - cumulative_obs) ** 2
    return total / (len(OUTCOMES) - 1)


def poisson_prob(goals: int, mean: float) -> float:
    mean = max(float(mean), 1e-9)
    return math.exp(goals * math.log(mean) - mean - math.lgamma(goals + 1))


def most_likely_score_from_xg(mu_a: float, mu_b: float, max_goals: int = 7) -> Tuple[str, float]:
    best_score = (0, 0)
    best_prob = -1.0
    for goals_a in range(max_goals + 1):
        prob_a = poisson_prob(goals_a, mu_a)
        for goals_b in range(max_goals + 1):
            prob = prob_a * poisson_prob(goals_b, mu_b)
            if prob > best_prob:
                best_score = (goals_a, goals_b)
                best_prob = prob
    return (f"{best_score[0]}-{best_score[1]}", best_prob)


def probabilities_from_strength(strength_a_minus_b: float, *, draw_base: float = 0.25) -> Tuple[float, float, float]:
    strength = clamp(float(strength_a_minus_b), -4.0, 4.0)
    closeness = clamp(1.0 - abs(strength) / 4.0, 0.0, 1.0)
    draw = clamp(draw_base + 0.08 * closeness, 0.16, 0.34)
    non_draw_a = 1.0 / (1.0 + math.exp(-strength))
    return normalize_probabilities((1.0 - draw) * non_draw_a, draw, (1.0 - draw) * (1.0 - non_draw_a))


def xg_from_probabilities(prob_a: float, prob_draw: float, prob_b: float, *, total_goals: float = 2.55) -> Tuple[float, float]:
    edge = clamp(prob_a - prob_b, -0.70, 0.70)
    draw_drag = clamp(prob_draw - 0.25, -0.10, 0.12)
    total = clamp(total_goals - 0.85 * draw_drag, 1.75, 3.25)
    mu_a = clamp(total * (0.50 + 0.38 * edge), 0.25, 3.60)
    mu_b = clamp(total - mu_a, 0.25, 3.60)
    return mu_a, mu_b


def fifa_ranking_prediction(row: HistoricalRow) -> Optional[BenchmarkPrediction]:
    rank_a = safe_float(row.get("fifa_rank_a_pre"))
    rank_b = safe_float(row.get("fifa_rank_b_pre"))
    if rank_a is None or rank_b is None:
        return None
    strength = clamp((rank_b - rank_a) / 22.0, -3.0, 3.0)
    prob_a, prob_draw, prob_b = probabilities_from_strength(strength, draw_base=0.25)
    mu_a, mu_b = xg_from_probabilities(prob_a, prob_draw, prob_b)
    score, _ = most_likely_score_from_xg(mu_a, mu_b)
    return BenchmarkPrediction("fifa_ranking_puro", prob_a, prob_draw, prob_b, mu_a, mu_b, score)


def elo_prediction(row: HistoricalRow) -> Optional[BenchmarkPrediction]:
    elo_a = safe_float(row.get("elo_a_pre"))
    elo_b = safe_float(row.get("elo_b_pre"))
    if elo_a is None or elo_b is None:
        return None
    expected_a = 1.0 / (1.0 + 10.0 ** (-(elo_a - elo_b) / 400.0))
    strength = math.log(max(expected_a, 1e-9) / max(1.0 - expected_a, 1e-9))
    prob_a, prob_draw, prob_b = probabilities_from_strength(strength, draw_base=0.24)
    mu_a, mu_b = xg_from_probabilities(prob_a, prob_draw, prob_b)
    score, _ = most_likely_score_from_xg(mu_a, mu_b)
    return BenchmarkPrediction("elo_puro", prob_a, prob_draw, prob_b, mu_a, mu_b, score)


def market_prediction(row: HistoricalRow) -> Optional[BenchmarkPrediction]:
    prob_a = safe_float(row.get("market_prob_a_pre"), safe_float(row.get("market_prob_a")))
    prob_draw = safe_float(row.get("market_prob_draw_pre"), safe_float(row.get("market_prob_draw")))
    prob_b = safe_float(row.get("market_prob_b_pre"), safe_float(row.get("market_prob_b")))
    if prob_a is None or prob_draw is None or prob_b is None:
        return None
    prob_a, prob_draw, prob_b = normalize_probabilities(prob_a, prob_draw, prob_b)
    mu_a, mu_b = xg_from_probabilities(prob_a, prob_draw, prob_b)
    score, _ = most_likely_score_from_xg(mu_a, mu_b)
    return BenchmarkPrediction("mercado_puro", prob_a, prob_draw, prob_b, mu_a, mu_b, score)


def poisson_simple_prediction(row: HistoricalRow) -> Optional[BenchmarkPrediction]:
    mu_a = safe_float(row.get("expected_goals_a_pre"), safe_float(row.get("xg_a_pre")))
    mu_b = safe_float(row.get("expected_goals_b_pre"), safe_float(row.get("xg_b_pre")))
    if mu_a is None or mu_b is None:
        base = market_prediction(row) or elo_prediction(row) or fifa_ranking_prediction(row)
        if base is None or base.expected_goals_a is None or base.expected_goals_b is None:
            return None
        mu_a = base.expected_goals_a
        mu_b = base.expected_goals_b
    dist: Dict[Score, float] = {}
    total = 0.0
    for goals_a in range(8):
        prob_a = poisson_prob(goals_a, mu_a)
        for goals_b in range(8):
            prob = prob_a * poisson_prob(goals_b, mu_b)
            dist[(goals_a, goals_b)] = prob
            total += prob
    if total <= 0.0:
        return None
    win_a = sum(prob for (goals_a, goals_b), prob in dist.items() if goals_a > goals_b) / total
    draw = sum(prob for (goals_a, goals_b), prob in dist.items() if goals_a == goals_b) / total
    win_b = sum(prob for (goals_a, goals_b), prob in dist.items() if goals_b > goals_a) / total
    score, _ = most_likely_score_from_xg(mu_a, mu_b)
    return BenchmarkPrediction("poisson_simple", win_a, draw, win_b, mu_a, mu_b, score)


def historical_favorite_prediction(row: HistoricalRow) -> Optional[BenchmarkPrediction]:
    value_a = (
        safe_float(row.get("historical_strength_a_pre"))
        or safe_float(row.get("history_a_pre"))
        or safe_float(row.get("world_cup_index_a_pre"))
    )
    value_b = (
        safe_float(row.get("historical_strength_b_pre"))
        or safe_float(row.get("history_b_pre"))
        or safe_float(row.get("world_cup_index_b_pre"))
    )
    if value_a is None or value_b is None:
        base = fifa_ranking_prediction(row) or elo_prediction(row)
        if base is None:
            return None
        return BenchmarkPrediction(
            "favorito_historico",
            base.prob_a,
            base.prob_draw,
            base.prob_b,
            base.expected_goals_a,
            base.expected_goals_b,
            base.most_likely_score,
            "fallback_fifa_or_elo",
        )
    strength = clamp((value_a - value_b) * 2.3, -3.0, 3.0)
    prob_a, prob_draw, prob_b = probabilities_from_strength(strength, draw_base=0.26)
    mu_a, mu_b = xg_from_probabilities(prob_a, prob_draw, prob_b)
    score, _ = most_likely_score_from_xg(mu_a, mu_b)
    return BenchmarkPrediction("favorito_historico", prob_a, prob_draw, prob_b, mu_a, mu_b, score)


def no_market_proxy_prediction(row: HistoricalRow) -> Optional[BenchmarkPrediction]:
    """Benchmark no-market scaffold.

    When a full-model adapter is available, benchmark_predictions_for_row()
    uses that adapter with market fields stripped. Until then, this proxy
    averages the available non-market benchmarks so the comparison table
    still has a no-market reference row without altering the real model.
    """

    stripped = strip_market_fields(row)
    candidates = [
        prediction
        for prediction in (
            elo_prediction(stripped),
            fifa_ranking_prediction(stripped),
            historical_favorite_prediction(stripped),
        )
        if prediction is not None
    ]
    if not candidates:
        return None
    prob_a, prob_draw, prob_b = normalize_probabilities(
        sum(prediction.prob_a for prediction in candidates) / len(candidates),
        sum(prediction.prob_draw for prediction in candidates) / len(candidates),
        sum(prediction.prob_b for prediction in candidates) / len(candidates),
    )
    mu_a, mu_b = xg_from_probabilities(prob_a, prob_draw, prob_b)
    score, _ = most_likely_score_from_xg(mu_a, mu_b)
    return BenchmarkPrediction(
        "modelo_sin_mercado",
        prob_a,
        prob_draw,
        prob_b,
        mu_a,
        mu_b,
        score,
        "proxy_sin_mercado; reemplazable por full_model_fn con mercado removido",
    )


def strip_market_fields(row: HistoricalRow) -> Dict[str, object]:
    stripped = dict(row)
    for key in (
        "market_prob_a",
        "market_prob_draw",
        "market_prob_b",
        "market_prob_a_pre",
        "market_prob_draw_pre",
        "market_prob_b_pre",
        "market_total_line",
        "market_total_line_pre",
    ):
        stripped.pop(key, None)
    return stripped


def coerce_prediction(name: str, prediction: object) -> Optional[BenchmarkPrediction]:
    if prediction is None:
        return None
    if isinstance(prediction, BenchmarkPrediction):
        if prediction.benchmark == name:
            return prediction
        return BenchmarkPrediction(
            name,
            prediction.prob_a,
            prediction.prob_draw,
            prediction.prob_b,
            prediction.expected_goals_a,
            prediction.expected_goals_b,
            prediction.most_likely_score,
            prediction.notes,
        )
    if isinstance(prediction, Mapping):
        prob_a = safe_float(prediction.get("prob_a"), safe_float(prediction.get("win_a")))
        prob_draw = safe_float(prediction.get("prob_draw"), safe_float(prediction.get("draw")))
        prob_b = safe_float(prediction.get("prob_b"), safe_float(prediction.get("win_b")))
        mu_a = safe_float(prediction.get("expected_goals_a"))
        mu_b = safe_float(prediction.get("expected_goals_b"))
        score = prediction.get("most_likely_score") or prediction.get("top_score")
    else:
        prob_a = safe_float(getattr(prediction, "prob_a", None), safe_float(getattr(prediction, "win_a", None)))
        prob_draw = safe_float(getattr(prediction, "prob_draw", None), safe_float(getattr(prediction, "draw", None)))
        prob_b = safe_float(getattr(prediction, "prob_b", None), safe_float(getattr(prediction, "win_b", None)))
        mu_a = safe_float(getattr(prediction, "expected_goals_a", None))
        mu_b = safe_float(getattr(prediction, "expected_goals_b", None))
        exact_scores = getattr(prediction, "exact_scores", None)
        score = exact_scores[0][0] if exact_scores else getattr(prediction, "most_likely_score", None)
    if prob_a is None or prob_draw is None or prob_b is None:
        return None
    prob_a, prob_draw, prob_b = normalize_probabilities(prob_a, prob_draw, prob_b)
    if score is None and mu_a is not None and mu_b is not None:
        score, _ = most_likely_score_from_xg(mu_a, mu_b)
    return BenchmarkPrediction(name, prob_a, prob_draw, prob_b, mu_a, mu_b, str(score) if score else None)


def benchmark_predictions_for_row(
    row: HistoricalRow,
    *,
    full_model_fn: Optional[PredictionFn] = None,
    no_market_model_fn: Optional[PredictionFn] = None,
) -> List[BenchmarkPrediction]:
    predictions: List[BenchmarkPrediction] = []
    for candidate in (
        fifa_ranking_prediction(row),
        elo_prediction(row),
        market_prediction(row),
        poisson_simple_prediction(row),
        historical_favorite_prediction(row),
    ):
        if candidate is not None:
            predictions.append(candidate)
    if no_market_model_fn is not None:
        no_market = coerce_prediction("modelo_sin_mercado", no_market_model_fn(strip_market_fields(row)))
        if no_market is not None:
            predictions.append(no_market)
    elif full_model_fn is not None:
        no_market = coerce_prediction("modelo_sin_mercado", full_model_fn(strip_market_fields(row)))
        if no_market is not None:
            predictions.append(no_market)
    else:
        no_market = no_market_proxy_prediction(row)
        if no_market is not None:
            predictions.append(no_market)
    return predictions


def evaluate_benchmarks(
    rows: Sequence[HistoricalRow],
    *,
    full_model_fn: Optional[PredictionFn] = None,
    no_market_model_fn: Optional[PredictionFn] = None,
) -> List[Dict[str, object]]:
    output: List[Dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        outcome = actual_outcome(row)
        score = actual_score(row)
        match_id = row.get("match_id") or row.get("id") or index
        for prediction in benchmark_predictions_for_row(
            row,
            full_model_fn=full_model_fn,
            no_market_model_fn=no_market_model_fn,
        ):
            predicted = predicted_outcome(prediction)
            output.append(
                {
                    "match_id": match_id,
                    "date": row.get("date", ""),
                    "competition": row.get("competition", ""),
                    "team_a": row.get("team_a", ""),
                    "team_b": row.get("team_b", ""),
                    "benchmark": prediction.benchmark,
                    "prob_a": prediction.prob_a,
                    "prob_draw": prediction.prob_draw,
                    "prob_b": prediction.prob_b,
                    "expected_goals_a": prediction.expected_goals_a,
                    "expected_goals_b": prediction.expected_goals_b,
                    "most_likely_score": prediction.most_likely_score,
                    "predicted_outcome": predicted,
                    "actual_outcome": outcome or "",
                    "actual_score": score or "",
                    "brier_score": brier_score(prediction, outcome) if outcome else "",
                    "log_loss": log_loss(prediction, outcome) if outcome else "",
                    "accuracy": 1 if outcome and predicted == outcome else (0 if outcome else ""),
                    "ranked_probability_score": ranked_probability_score(prediction, outcome) if outcome else "",
                    "notes": prediction.notes,
                }
            )
    return output


def summarize_benchmark_rows(rows: Sequence[Mapping[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[str, Dict[str, object]] = {}
    for row in rows:
        benchmark = str(row.get("benchmark", ""))
        if not benchmark:
            continue
        bucket = grouped.setdefault(
            benchmark,
            {"benchmark": benchmark, "matches": 0, "brier_score": 0.0, "log_loss": 0.0, "accuracy": 0.0, "ranked_probability_score": 0.0},
        )
        if row.get("actual_outcome") == "":
            continue
        bucket["matches"] = int(bucket["matches"]) + 1
        for metric in ("brier_score", "log_loss", "accuracy", "ranked_probability_score"):
            bucket[metric] = float(bucket[metric]) + float(row.get(metric) or 0.0)
    summaries = []
    for bucket in grouped.values():
        matches = int(bucket["matches"])
        row = dict(bucket)
        if matches:
            for metric in ("brier_score", "log_loss", "accuracy", "ranked_probability_score"):
                row[metric] = float(row[metric]) / matches
        else:
            for metric in ("brier_score", "log_loss", "accuracy", "ranked_probability_score"):
                row[metric] = ""
        summaries.append(row)
    return sorted(summaries, key=lambda item: str(item["benchmark"]))


def read_csv_rows(path: str | Path) -> List[Dict[str, object]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: str | Path, rows: Sequence[Mapping[str, object]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_benchmarks(
    historical_matches_csv: str | Path,
    *,
    output_csv: str | Path = "benchmark_results.csv",
    summary_csv: Optional[str | Path] = None,
    full_model_fn: Optional[PredictionFn] = None,
    no_market_model_fn: Optional[PredictionFn] = None,
) -> List[Dict[str, object]]:
    rows = read_csv_rows(historical_matches_csv)
    results = evaluate_benchmarks(
        rows,
        full_model_fn=full_model_fn,
        no_market_model_fn=no_market_model_fn,
    )
    write_csv_rows(output_csv, results)
    if summary_csv is not None:
        write_csv_rows(summary_csv, summarize_benchmark_rows(results))
    return results


def run_benchmarks_cli(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Genera benchmark_results.csv desde historical_matches.csv.")
    parser.add_argument("historical_matches_csv", help="CSV historico con columnas pre-partido.")
    parser.add_argument("--output-csv", default="benchmark_results.csv", help="Archivo CSV detallado por partido/benchmark.")
    parser.add_argument("--summary-csv", default="benchmark_summary.csv", help="Archivo CSV agregado por benchmark.")
    args = parser.parse_args(argv)
    run_benchmarks(
        args.historical_matches_csv,
        output_csv=args.output_csv,
        summary_csv=args.summary_csv,
    )
    return 0


__all__ = [
    "BENCHMARK_NAMES",
    "BenchmarkPrediction",
    "benchmark_predictions_for_row",
    "brier_score",
    "coerce_prediction",
    "evaluate_benchmarks",
    "log_loss",
    "market_prediction",
    "most_likely_score_from_xg",
    "no_market_proxy_prediction",
    "normalize_probabilities",
    "ranked_probability_score",
    "read_csv_rows",
    "run_benchmarks",
    "run_benchmarks_cli",
    "summarize_benchmark_rows",
    "write_csv_rows",
]


if __name__ == "__main__":
    raise SystemExit(run_benchmarks_cli())
