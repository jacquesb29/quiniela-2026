"""Validación walk-forward sin leakage (F0.4).

Es un JUEZ de validación temporal: mide si el modelo de producción realmente
mejora fuera de muestra. No ajusta el modelo, ni pesos, ni lambdas, ni la capa
Penca. El modelo y los baselines se inyectan como funciones (igual que en el
resto del harness) para no acoplar este módulo al monolito ni provocar ciclos
de import.

Garantías anti-leakage:
- Las filas se ordenan por fecha.
- Ningún partido del futuro entra en train: `max(train.date) < min(test.date)`
  de forma estricta (los partidos del día-frontera se absorben en train, nunca
  en test).
- Los bloques de test no se solapan.
- La calibración (opcional, apagada por defecto) se ajusta SOLO con train y se
  aplica en test; jamás usa etiquetas de test para fijar la temperatura.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from .benchmarks import actual_outcome, actual_score, safe_float, write_csv_rows

OUTCOMES: Tuple[str, str, str] = ("a", "draw", "b")
ModelEval = Mapping[str, object]
ModelEvalFn = Callable[[Mapping[str, object]], Optional[ModelEval]]
BaselinePredFn = Callable[[Mapping[str, object]], object]


def _date_key(row: Mapping[str, object]) -> str:
    return str(row.get("date") or "")


def temporal_folds(
    rows: Sequence[Mapping[str, object]],
    *,
    scheme: str = "expanding",
    min_train: int = 400,
    step: int = 200,
) -> Iterator[Tuple[List[Mapping[str, object]], List[Mapping[str, object]]]]:
    """Genera folds temporales (train, test) sin fuga de futuro.

    `expanding`: train crece desde el inicio; `rolling`: train es una ventana de
    tamaño `min_train`. En ambos casos el test es el siguiente bloque de hasta
    `step` filas con fecha ESTRICTAMENTE posterior al último día de train.
    """

    ordered = sorted(rows, key=lambda r: (_date_key(r), str(r.get("match_id") or "")))
    n = len(ordered)
    boundary = min_train
    while boundary < n:
        if scheme == "rolling":
            train = ordered[max(0, boundary - min_train):boundary]
        else:
            train = ordered[:boundary]
        if not train:
            boundary += step
            continue
        train_max_date = _date_key(train[-1])
        raw_test = ordered[boundary:boundary + step]
        # Anti-leak estricto: descartar del test las filas del mismo día que el
        # final de train (se absorberán en el train del siguiente fold).
        test = [r for r in raw_test if _date_key(r) > train_max_date]
        if test:
            yield train, test
        boundary += step


def _model_probs(eval_row: ModelEval) -> Dict[str, float]:
    return {
        "a": float(eval_row["prob_a"]),
        "draw": float(eval_row["prob_draw"]),
        "b": float(eval_row["prob_b"]),
    }


def _baseline_probs(prediction: object) -> Optional[Dict[str, float]]:
    if prediction is None:
        return None
    probs = getattr(prediction, "probabilities", None)
    if callable(probs):
        values = probs()
        return {"a": float(values["a"]), "draw": float(values["draw"]), "b": float(values["b"])}
    return None


def _brier(probs: Mapping[str, float], outcome: str) -> float:
    return sum((probs[key] - (1.0 if key == outcome else 0.0)) ** 2 for key in OUTCOMES) / 3.0


def _logloss(probs: Mapping[str, float], outcome: str) -> float:
    return -math.log(max(probs.get(outcome, 0.0), 1e-12))


def _argmax_outcome(probs: Mapping[str, float]) -> str:
    return max(OUTCOMES, key=lambda key: probs[key])


def _mean(values: Sequence[float]) -> Optional[float]:
    return (sum(values) / len(values)) if values else None


def apply_calibration(probs: Mapping[str, float], temperature: float) -> Dict[str, float]:
    """Temperature scaling sobre 1X2 (T>0). T=1 deja las probabilidades igual."""

    t = max(float(temperature), 1e-6)
    scaled = {key: max(float(probs.get(key, 0.0)), 1e-12) ** (1.0 / t) for key in OUTCOMES}
    total = sum(scaled.values())
    if total <= 0.0:
        return {key: 1.0 / 3.0 for key in OUTCOMES}
    return {key: value / total for key, value in scaled.items()}


def fit_calibration_on_train(
    train_evals: Sequence[Tuple[Mapping[str, float], str]],
    *,
    grid: Optional[Sequence[float]] = None,
) -> float:
    """Ajusta la temperatura SOLO con datos de train (minimiza log-loss en train).

    `train_evals`: lista de (probs, outcome) del propio train. No recibe ni mira
    datos de test: estructuralmente no puede haber leakage de calibración.
    """

    if not train_evals:
        return 1.0
    candidates = list(grid) if grid is not None else [round(0.5 + 0.05 * i, 2) for i in range(0, 31)]
    best_t = 1.0
    best_loss = float("inf")
    for t in candidates:
        loss = 0.0
        for probs, outcome in train_evals:
            loss += _logloss(apply_calibration(probs, t), outcome)
        if loss < best_loss:
            best_loss = loss
            best_t = t
    return best_t


def _evaluate_fold(
    test: Sequence[Mapping[str, object]],
    *,
    model_eval_fn: ModelEvalFn,
    baseline_pred_fns: Mapping[str, BaselinePredFn],
    penca_scoring_fn: Optional[Callable[[object, object], float]],
    temperature: float,
) -> Dict[str, object]:
    model_brier: List[float] = []
    model_logloss: List[float] = []
    model_hits: List[float] = []
    exact_hits: List[float] = []
    penca_points: List[float] = []
    baseline_acc: Dict[str, Dict[str, List[float]]] = {
        name: {"brier": [], "logloss": [], "hits": []} for name in baseline_pred_fns
    }

    for row in test:
        outcome = actual_outcome(row)
        if outcome is None:
            continue
        eval_row = model_eval_fn(row)
        if eval_row is None:
            continue
        probs = _model_probs(eval_row)
        if temperature != 1.0:
            probs = apply_calibration(probs, temperature)
        model_brier.append(_brier(probs, outcome))
        model_logloss.append(_logloss(probs, outcome))
        model_hits.append(1.0 if _argmax_outcome(probs) == outcome else 0.0)

        asc = actual_score(row)
        modal = eval_row.get("modal_score")
        if modal is not None and asc is not None:
            exact_hits.append(1.0 if str(modal) == str(asc) else 0.0)
        penca_score = eval_row.get("penca_score")
        if penca_scoring_fn is not None and penca_score is not None and asc is not None:
            penca_points.append(float(penca_scoring_fn(penca_score, asc)))

        for name, fn in baseline_pred_fns.items():
            bprobs = _baseline_probs(fn(row))
            if bprobs is None:
                continue
            baseline_acc[name]["brier"].append(_brier(bprobs, outcome))
            baseline_acc[name]["logloss"].append(_logloss(bprobs, outcome))
            baseline_acc[name]["hits"].append(1.0 if _argmax_outcome(bprobs) == outcome else 0.0)

    summary: Dict[str, object] = {
        "test_n_scored": len(model_logloss),
        "brier": _mean(model_brier),
        "log_loss": _mean(model_logloss),
        "accuracy": _mean(model_hits),
        "exact_score_accuracy": _mean(exact_hits),
        "penca_points_avg": _mean(penca_points),
        "penca_points_total": sum(penca_points) if penca_points else 0.0,
    }
    model_ll = summary["log_loss"]
    for name in baseline_pred_fns:
        b_ll = _mean(baseline_acc[name]["logloss"])
        summary[f"{name}_brier"] = _mean(baseline_acc[name]["brier"])
        summary[f"{name}_logloss"] = b_ll
        summary[f"beats_{name}"] = (
            bool(model_ll is not None and b_ll is not None and model_ll < b_ll)
        )
    return summary


def run_walk_forward(
    rows: Sequence[Mapping[str, object]],
    *,
    model_eval_fn: ModelEvalFn,
    baseline_pred_fns: Mapping[str, BaselinePredFn],
    penca_scoring_fn: Optional[Callable[[object, object], float]] = None,
    scheme: str = "expanding",
    min_train: int = 400,
    step: int = 200,
    output_dir: Optional[str | Path] = None,
    calibrate: bool = False,
) -> Dict[str, object]:
    """Corre walk-forward y devuelve {folds, summary}; opcionalmente escribe CSVs."""

    folds = list(temporal_folds(rows, scheme=scheme, min_train=min_train, step=step))
    fold_rows: List[Dict[str, object]] = []
    # Acumuladores agregados (pool de TODOS los test, sin solape entre folds).
    pooled_model_logloss: List[float] = []
    pooled_model_brier: List[float] = []
    pooled_model_hits: List[float] = []
    pooled_exact: List[float] = []
    pooled_penca: List[float] = []
    pooled_baseline: Dict[str, Dict[str, List[float]]] = {
        name: {"brier": [], "logloss": []} for name in baseline_pred_fns
    }

    for idx, (train, test) in enumerate(folds, start=1):
        temperature = 1.0
        if calibrate:
            train_evals: List[Tuple[Dict[str, float], str]] = []
            for row in train:
                outcome = actual_outcome(row)
                if outcome is None:
                    continue
                eval_row = model_eval_fn(row)
                if eval_row is None:
                    continue
                train_evals.append((_model_probs(eval_row), outcome))
            temperature = fit_calibration_on_train(train_evals)

        fold_summary = _evaluate_fold(
            test,
            model_eval_fn=model_eval_fn,
            baseline_pred_fns=baseline_pred_fns,
            penca_scoring_fn=penca_scoring_fn,
            temperature=temperature,
        )
        fold_dates = sorted(_date_key(r) for r in test)
        train_dates = sorted(_date_key(r) for r in train)
        fold_row: Dict[str, object] = {
            "fold": idx,
            "train_n": len(train),
            "test_n": len(test),
            "train_end_date": train_dates[-1] if train_dates else "",
            "test_start_date": fold_dates[0] if fold_dates else "",
            "test_end_date": fold_dates[-1] if fold_dates else "",
            "temperature": temperature,
        }
        fold_row.update(fold_summary)
        fold_rows.append(fold_row)

        # Pool agregado: re-evaluar test para acumular por partido (mismas reglas).
        for row in test:
            outcome = actual_outcome(row)
            if outcome is None:
                continue
            eval_row = model_eval_fn(row)
            if eval_row is None:
                continue
            probs = _model_probs(eval_row)
            if temperature != 1.0:
                probs = apply_calibration(probs, temperature)
            pooled_model_brier.append(_brier(probs, outcome))
            pooled_model_logloss.append(_logloss(probs, outcome))
            pooled_model_hits.append(1.0 if _argmax_outcome(probs) == outcome else 0.0)
            asc = actual_score(row)
            modal = eval_row.get("modal_score")
            if modal is not None and asc is not None:
                pooled_exact.append(1.0 if str(modal) == str(asc) else 0.0)
            penca_score = eval_row.get("penca_score")
            if penca_scoring_fn is not None and penca_score is not None and asc is not None:
                pooled_penca.append(float(penca_scoring_fn(penca_score, asc)))
            for name, fn in baseline_pred_fns.items():
                bprobs = _baseline_probs(fn(row))
                if bprobs is None:
                    continue
                pooled_baseline[name]["brier"].append(_brier(bprobs, outcome))
                pooled_baseline[name]["logloss"].append(_logloss(bprobs, outcome))

    model_logloss = _mean(pooled_model_logloss)
    summary: Dict[str, object] = {
        "n_folds": len(fold_rows),
        "total_test_n": len(pooled_model_logloss),
        "scheme": scheme,
        "min_train": min_train,
        "step": step,
        "calibrated": calibrate,
        "model_brier": _mean(pooled_model_brier),
        "model_logloss": model_logloss,
        "model_accuracy": _mean(pooled_model_hits),
        "model_exact_score_accuracy": _mean(pooled_exact),
        "penca_points_avg": _mean(pooled_penca),
        "penca_points_total": sum(pooled_penca) if pooled_penca else 0.0,
    }
    for name in baseline_pred_fns:
        b_ll = _mean(pooled_baseline[name]["logloss"])
        summary[f"{name}_brier"] = _mean(pooled_baseline[name]["brier"])
        summary[f"{name}_logloss"] = b_ll
        summary[f"beats_{name}"] = bool(
            model_logloss is not None and b_ll is not None and model_logloss < b_ll
        )

    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        write_csv_rows(out / "folds_summary.csv", fold_rows)
        write_csv_rows(out / "walk_forward_summary.csv", [summary])

    return {"folds": fold_rows, "summary": summary}


__all__ = [
    "temporal_folds",
    "run_walk_forward",
    "fit_calibration_on_train",
    "apply_calibration",
]
