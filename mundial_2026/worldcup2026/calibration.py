from __future__ import annotations

import csv
import dataclasses
import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .benchmarks import read_csv_rows, safe_float, write_csv_rows

try:
    from sklearn.isotonic import IsotonicRegression
except Exception:  # pragma: no cover - optional dependency fallback
    IsotonicRegression = None


def empirical_bayes_shrinkage(
    observed_rate: float,
    sample_size: float,
    prior_mean: float,
    prior_strength: float,
) -> float:
    sample_size = max(float(sample_size), 0.0)
    prior_strength = max(float(prior_strength), 0.0)
    if sample_size + prior_strength <= 0.0:
        return float(prior_mean)
    return (
        float(observed_rate) * sample_size + float(prior_mean) * prior_strength
    ) / (sample_size + prior_strength)


def shrink_probability(
    observed_value: float,
    sample_size: float,
    prior_mean: float,
    prior_strength: float,
    *,
    low: float = 0.0,
    high: float = 1.0,
) -> float:
    value = empirical_bayes_shrinkage(
        observed_value,
        sample_size,
        prior_mean,
        prior_strength,
    )
    return max(low, min(high, float(value)))


class PlattCalibrator:
    def __init__(self) -> None:
        self.a: float = 1.0
        self.b: float = 0.0

    def fit(
        self,
        predicted_probs: Sequence[float],
        actual_outcomes: Sequence[int],
        *,
        lr: float = 0.01,
        epochs: int = 500,
    ) -> "PlattCalibrator":
        if not predicted_probs or len(predicted_probs) != len(actual_outcomes):
            return self
        a, b = self.a, self.b
        n = len(predicted_probs)
        for _ in range(max(50, int(epochs))):
            grad_a = 0.0
            grad_b = 0.0
            for prob, outcome in zip(predicted_probs, actual_outcomes):
                p = min(max(float(prob), 1e-10), 1.0 - 1e-10)
                logit = math.log(p / (1.0 - p))
                q = 1.0 / (1.0 + math.exp(-(a * logit + b)))
                error = q - float(outcome)
                grad_a += error * logit
                grad_b += error
            a -= lr * grad_a / n
            b -= lr * grad_b / n
        self.a = a
        self.b = b
        return self

    def calibrate(self, prob: float) -> float:
        p = min(max(float(prob), 1e-10), 1.0 - 1e-10)
        logit = math.log(p / (1.0 - p))
        return 1.0 / (1.0 + math.exp(-(self.a * logit + self.b)))


class IsotonicCalibrator:
    def __init__(self) -> None:
        self._fitted = False
        self._model = IsotonicRegression(out_of_bounds="clip") if IsotonicRegression is not None else None

    def fit(self, predicted_probs: Sequence[float], actual_outcomes: Sequence[int]) -> "IsotonicCalibrator":
        if self._model is None or not predicted_probs or len(predicted_probs) != len(actual_outcomes):
            return self
        self._model.fit(list(predicted_probs), list(actual_outcomes))
        self._fitted = True
        return self

    def calibrate(self, prob: float) -> float:
        if not self._fitted or self._model is None:
            return float(prob)
        return float(self._model.predict([float(prob)])[0])


def prediction_confidence_interval(
    predictor: Callable[[Any], Any],
    ctx: Any,
    *,
    n_bootstrap: int = 120,
    alpha: float = 0.10,
    rng_seed: Optional[int] = None,
) -> Dict[str, Any]:
    rng = np.random.default_rng(rng_seed)
    win_a_samples: List[float] = []
    draw_samples: List[float] = []
    win_b_samples: List[float] = []
    mu_a_samples: List[float] = []
    mu_b_samples: List[float] = []

    for _ in range(max(12, int(n_bootstrap))):
        perturbed_ctx = dataclasses.replace(
            ctx,
            injuries_a=max(0.0, min(1.0, float(getattr(ctx, "injuries_a", 0.0)) + float(rng.normal(0.0, 0.05)))),
            injuries_b=max(0.0, min(1.0, float(getattr(ctx, "injuries_b", 0.0)) + float(rng.normal(0.0, 0.05)))),
            weather_stress=max(0.0, min(1.0, float(getattr(ctx, "weather_stress", 0.0)) + float(rng.normal(0.0, 0.02)))),
        )
        prediction = predictor(perturbed_ctx)
        win_a_samples.append(float(getattr(prediction, "win_a", 0.0)))
        draw_samples.append(float(getattr(prediction, "draw", 0.0)))
        win_b_samples.append(float(getattr(prediction, "win_b", 0.0)))
        mu_a_samples.append(float(getattr(prediction, "expected_goals_a", 0.0)))
        mu_b_samples.append(float(getattr(prediction, "expected_goals_b", 0.0)))

    lo = alpha / 2.0
    hi = 1.0 - lo
    return {
        "win_a_ci": (float(np.quantile(win_a_samples, lo)), float(np.quantile(win_a_samples, hi))),
        "draw_ci": (float(np.quantile(draw_samples, lo)), float(np.quantile(draw_samples, hi))),
        "win_b_ci": (float(np.quantile(win_b_samples, lo)), float(np.quantile(win_b_samples, hi))),
        "mu_a_ci": (float(np.quantile(mu_a_samples, lo)), float(np.quantile(mu_a_samples, hi))),
        "mu_b_ci": (float(np.quantile(mu_b_samples, lo)), float(np.quantile(mu_b_samples, hi))),
        "sensitivity": float(np.std(win_a_samples)),
    }


def walk_forward_validation(
    fixtures: Sequence[dict],
    *,
    predict_fn: Callable[[dict], Optional[dict]],
    update_fn: Callable[[dict], None],
    min_train: int = 5,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    trained = 0
    for fixture in fixtures:
        if trained >= min_train:
            row = predict_fn(fixture)
            if row:
                results.append(row)
        update_fn(fixture)
        trained += 1
    return results


CALIBRATION_OUTCOMES = ("a", "draw", "b")


def normalize_triple(prob_a: float, prob_draw: float, prob_b: float) -> Tuple[float, float, float]:
    values = [max(0.0, float(prob_a)), max(0.0, float(prob_draw)), max(0.0, float(prob_b))]
    total = sum(values)
    if total <= 0.0:
        return (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)
    return (values[0] / total, values[1] / total, values[2] / total)


def row_probabilities(row: Mapping[str, object]) -> Optional[Tuple[float, float, float]]:
    prob_a = safe_float(row.get("prob_a"), safe_float(row.get("win_a")))
    prob_draw = safe_float(row.get("prob_draw"), safe_float(row.get("draw")))
    prob_b = safe_float(row.get("prob_b"), safe_float(row.get("win_b")))
    if prob_a is None or prob_draw is None or prob_b is None:
        return None
    return normalize_triple(prob_a, prob_draw, prob_b)


def row_outcome(row: Mapping[str, object]) -> Optional[str]:
    outcome = str(row.get("actual_outcome") or row.get("outcome") or "").strip().lower()
    if outcome in {"a", "home", "team_a", "1"}:
        return "a"
    if outcome in {"draw", "empate", "x"}:
        return "draw"
    if outcome in {"b", "away", "team_b", "2"}:
        return "b"
    return None


def multiclass_brier(rows: Sequence[Mapping[str, object]], *, prefix: str = "") -> Optional[float]:
    values: List[float] = []
    for row in rows:
        outcome = row_outcome(row)
        probs = row_probabilities_with_prefix(row, prefix)
        if outcome is None or probs is None:
            continue
        values.append(
            sum(
                (prob - (1.0 if outcome == key else 0.0)) ** 2
                for prob, key in zip(probs, CALIBRATION_OUTCOMES)
            )
            / 3.0
        )
    return sum(values) / len(values) if values else None


def multiclass_log_loss(rows: Sequence[Mapping[str, object]], *, prefix: str = "") -> Optional[float]:
    values: List[float] = []
    for row in rows:
        outcome = row_outcome(row)
        probs = row_probabilities_with_prefix(row, prefix)
        if outcome is None or probs is None:
            continue
        prob_map = dict(zip(CALIBRATION_OUTCOMES, probs))
        values.append(-math.log(max(prob_map[outcome], 1e-12)))
    return sum(values) / len(values) if values else None


def multiclass_accuracy(rows: Sequence[Mapping[str, object]], *, prefix: str = "") -> Optional[float]:
    values: List[int] = []
    for row in rows:
        outcome = row_outcome(row)
        probs = row_probabilities_with_prefix(row, prefix)
        if outcome is None or probs is None:
            continue
        predicted = CALIBRATION_OUTCOMES[int(np.argmax(probs))]
        values.append(1 if predicted == outcome else 0)
    return sum(values) / len(values) if values else None


def row_probabilities_with_prefix(row: Mapping[str, object], prefix: str = "") -> Optional[Tuple[float, float, float]]:
    if not prefix:
        return row_probabilities(row)
    prob_a = safe_float(row.get(f"{prefix}prob_a"))
    prob_draw = safe_float(row.get(f"{prefix}prob_draw"))
    prob_b = safe_float(row.get(f"{prefix}prob_b"))
    if prob_a is None or prob_draw is None or prob_b is None:
        return None
    return normalize_triple(prob_a, prob_draw, prob_b)


def apply_temperature_to_probs(probs: Tuple[float, float, float], temperature: float) -> Tuple[float, float, float]:
    temperature = max(0.05, float(temperature))
    adjusted = [max(prob, 1e-12) ** (1.0 / temperature) for prob in probs]
    return normalize_triple(adjusted[0], adjusted[1], adjusted[2])


def empirical_base_rates(rows: Sequence[Mapping[str, object]]) -> Tuple[float, float, float]:
    counts = {"a": 0, "draw": 0, "b": 0}
    total = 0
    for row in rows:
        outcome = row_outcome(row)
        if outcome not in counts:
            continue
        counts[outcome] += 1
        total += 1
    if total <= 0:
        return (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)
    return (counts["a"] / total, counts["draw"] / total, counts["b"] / total)


def shrink_probs_to_base_rates(
    probs: Tuple[float, float, float],
    base_rates: Tuple[float, float, float],
    strength: float,
) -> Tuple[float, float, float]:
    strength = max(0.0, min(1.0, float(strength)))
    return normalize_triple(
        (1.0 - strength) * probs[0] + strength * base_rates[0],
        (1.0 - strength) * probs[1] + strength * base_rates[1],
        (1.0 - strength) * probs[2] + strength * base_rates[2],
    )


def fit_temperature(
    rows: Sequence[Mapping[str, object]],
    *,
    candidates: Optional[Sequence[float]] = None,
) -> float:
    candidates = candidates or [0.50 + index * 0.05 for index in range(51)]
    best_temperature = 1.0
    best_loss = math.inf
    for temperature in candidates:
        calibrated_rows = []
        for row in rows:
            probs = row_probabilities(row)
            if probs is None:
                continue
            calibrated = apply_temperature_to_probs(probs, temperature)
            next_row = dict(row)
            next_row["cal_prob_a"] = calibrated[0]
            next_row["cal_prob_draw"] = calibrated[1]
            next_row["cal_prob_b"] = calibrated[2]
            calibrated_rows.append(next_row)
        loss = multiclass_log_loss(calibrated_rows, prefix="cal_")
        if loss is not None and loss < best_loss:
            best_loss = loss
            best_temperature = float(temperature)
    return best_temperature


def calibrate_prediction_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    temperature: Optional[float] = None,
    shrinkage_strength: float = 0.06,
) -> List[Dict[str, object]]:
    fitted_temperature = temperature if temperature is not None else fit_temperature(rows)
    base_rates = empirical_base_rates(rows)
    calibrated_rows: List[Dict[str, object]] = []
    for row in rows:
        probs = row_probabilities(row)
        if probs is None:
            continue
        temp_probs = apply_temperature_to_probs(probs, fitted_temperature)
        final_probs = shrink_probs_to_base_rates(temp_probs, base_rates, shrinkage_strength)
        next_row = dict(row)
        next_row["temperature"] = fitted_temperature
        next_row["shrinkage_strength"] = shrinkage_strength
        next_row["cal_prob_a"] = final_probs[0]
        next_row["cal_prob_draw"] = final_probs[1]
        next_row["cal_prob_b"] = final_probs[2]
        next_row["cal_predicted_outcome"] = CALIBRATION_OUTCOMES[int(np.argmax(final_probs))]
        calibrated_rows.append(next_row)
    return calibrated_rows


def reliability_curve_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    prefix: str = "",
    bins: int = 10,
) -> List[Dict[str, object]]:
    buckets: Dict[str, Dict[str, float]] = {}
    bins = max(2, int(bins))
    for row in rows:
        outcome = row_outcome(row)
        probs = row_probabilities_with_prefix(row, prefix)
        if outcome is None or probs is None:
            continue
        confidence = max(probs)
        predicted = CALIBRATION_OUTCOMES[int(np.argmax(probs))]
        lower = int(min(bins - 1, max(0, confidence * bins))) / bins
        upper = lower + 1.0 / bins
        bucket = f"{lower:.1f}-{upper:.1f}"
        state = buckets.setdefault(bucket, {"matches": 0.0, "confidence_sum": 0.0, "hits": 0.0})
        state["matches"] += 1.0
        state["confidence_sum"] += confidence
        state["hits"] += 1.0 if predicted == outcome else 0.0
    output = []
    for bucket, state in sorted(buckets.items()):
        matches = max(1.0, state["matches"])
        output.append(
            {
                "version": "calibrada" if prefix else "original",
                "bucket": bucket,
                "matches": int(state["matches"]),
                "avg_predicted_confidence": state["confidence_sum"] / matches,
                "observed_hit_rate": state["hits"] / matches,
                "calibration_gap": (state["confidence_sum"] / matches) - (state["hits"] / matches),
            }
        )
    return output


def calibration_report_rows(
    original_rows: Sequence[Mapping[str, object]],
    calibrated_rows: Sequence[Mapping[str, object]],
) -> List[Dict[str, object]]:
    return [
        {
            "version": "original",
            "matches": len(original_rows),
            "brier_score": multiclass_brier(original_rows),
            "log_loss": multiclass_log_loss(original_rows),
            "accuracy": multiclass_accuracy(original_rows),
            "temperature": "",
            "shrinkage_strength": "",
        },
        {
            "version": "calibrada",
            "matches": len(calibrated_rows),
            "brier_score": multiclass_brier(calibrated_rows, prefix="cal_"),
            "log_loss": multiclass_log_loss(calibrated_rows, prefix="cal_"),
            "accuracy": multiclass_accuracy(calibrated_rows, prefix="cal_"),
            "temperature": calibrated_rows[0].get("temperature", "") if calibrated_rows else "",
            "shrinkage_strength": calibrated_rows[0].get("shrinkage_strength", "") if calibrated_rows else "",
        },
    ]


def run_calibration_report(
    predictions_csv: str | Path,
    *,
    output_dir: str | Path = ".",
    temperature: Optional[float] = None,
    shrinkage_strength: float = 0.06,
    bins: int = 10,
) -> Dict[str, object]:
    rows = read_csv_rows(predictions_csv)
    calibrated = calibrate_prediction_rows(
        rows,
        temperature=temperature,
        shrinkage_strength=shrinkage_strength,
    )
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report = calibration_report_rows(rows, calibrated)
    bin_rows = reliability_curve_rows(rows, bins=bins) + reliability_curve_rows(calibrated, prefix="cal_", bins=bins)
    write_csv_rows(output_path / "calibrated_predictions.csv", calibrated)
    write_csv_rows(output_path / "calibration_report.csv", report)
    write_csv_rows(output_path / "calibration_bins.csv", bin_rows)
    return {"report": report, "calibrated_predictions": calibrated, "calibration_bins": bin_rows}


def run_calibration_report_cli(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Genera calibrated_predictions.csv, calibration_report.csv y calibration_bins.csv.")
    parser.add_argument("predictions_csv", help="CSV con prob_a/prob_draw/prob_b y actual_outcome.")
    parser.add_argument("--output-dir", default=".", help="Directorio de salida.")
    parser.add_argument("--temperature", type=float, default=None, help="Temperatura fija; si se omite, se ajusta por grid search.")
    parser.add_argument("--shrinkage-strength", type=float, default=0.06, help="Shrinkage contra tasas base historicas.")
    parser.add_argument("--bins", type=int, default=10, help="Numero de bins de reliability curve.")
    args = parser.parse_args(argv)
    run_calibration_report(
        args.predictions_csv,
        output_dir=args.output_dir,
        temperature=args.temperature,
        shrinkage_strength=args.shrinkage_strength,
        bins=args.bins,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run_calibration_report_cli())
