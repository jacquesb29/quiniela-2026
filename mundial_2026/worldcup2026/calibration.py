from __future__ import annotations

import dataclasses
import math
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

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
