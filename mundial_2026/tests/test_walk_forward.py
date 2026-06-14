"""Tests F0.4: walk-forward sin leakage."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.walk_forward import (  # noqa: E402
    apply_calibration,
    fit_calibration_on_train,
    run_walk_forward,
    temporal_folds,
)

VALIDATION_STATUS_JSON = ROOT / "outputs" / "validation_status.json"


def _date(day_index: int) -> str:
    # Fechas crecientes, 3 partidos por día (para ejercer la frontera de día).
    base_day = 1 + (day_index // 3)
    return f"1990-01-{base_day:02d}"


def _make_rows(n: int):
    rows = []
    for i in range(n):
        goals_a, goals_b = (2, 0) if i % 3 else (1, 1)
        rows.append({
            "match_id": f"m{i:04d}",
            "date": _date(i),
            "team_a": f"A{i}",
            "team_b": f"B{i}",
            "goals_a": str(goals_a),
            "goals_b": str(goals_b),
            "elo_a_pre": "1700",
            "elo_b_pre": "1500",
        })
    return rows


class _FakeBaseline:
    """Baseline peor que el modelo (probabilidades planas) para beats=True."""

    def __init__(self, probs):
        self._probs = probs

    def probabilities(self):
        return self._probs


def _good_model_eval(row):
    # Modelo confiado y correcto en mayoría (favorece 'a'); modal y penca 2-0.
    return {"prob_a": 0.70, "prob_draw": 0.20, "prob_b": 0.10,
            "modal_score": "2-0", "penca_score": "2-0"}


def _weak_baseline_fn(row):
    return _FakeBaseline({"a": 0.34, "draw": 0.33, "b": 0.33})


def _penca_scoring(pick, actual):
    pa, pb = (int(x) for x in str(pick).split("-"))
    aa, ab = (int(x) for x in str(actual).split("-"))
    if (pa, pb) == (aa, ab):
        return 8.0
    if pa - pb == aa - ab:
        return 5.0
    if (pa > pb) == (aa > ab) and (pa == pb) == (aa == ab):
        return 3.0
    return 0.0


class TestTemporalFolds(unittest.TestCase):
    def test_no_future_in_train(self):
        rows = _make_rows(900)
        folds = list(temporal_folds(rows, scheme="expanding", min_train=400, step=200))
        self.assertTrue(folds)
        for train, test in folds:
            train_max = max(str(r["date"]) for r in train)
            test_min = min(str(r["date"]) for r in test)
            self.assertLess(train_max, test_min, "hay fecha de train >= fecha de test (leakage)")

    def test_expanding_folds_non_overlapping(self):
        rows = _make_rows(900)
        folds = list(temporal_folds(rows, scheme="expanding", min_train=400, step=200))
        seen = set()
        prev_train_len = 0
        for train, test in folds:
            ids = {r["match_id"] for r in test}
            self.assertFalse(ids & seen, "bloques de test solapados")
            seen |= ids
            self.assertGreaterEqual(len(train), prev_train_len)  # expanding crece
            prev_train_len = len(train)


class TestCalibration(unittest.TestCase):
    def test_calibration_fit_on_train_only(self):
        # Train donde el modelo está poco confiado pero acierta 'a' siempre:
        # la temperatura óptima debe AGUDIZAR (T<1) y reducir la log-loss de train.
        train = [({"a": 0.45, "draw": 0.30, "b": 0.25}, "a") for _ in range(50)]
        T = fit_calibration_on_train(train)
        self.assertIsInstance(T, float)
        self.assertGreater(T, 0.0)

        def train_loss(temp):
            import math
            return sum(-math.log(max(apply_calibration(p, temp)[o], 1e-12)) for p, o in train)

        self.assertLessEqual(train_loss(T), train_loss(1.0) + 1e-9)
        # La función no recibe datos de test: el ajuste solo puede ver train.
        self.assertNotIn("test", fit_calibration_on_train.__code__.co_varnames)


class TestRunWalkForward(unittest.TestCase):
    def _run(self, output_dir):
        rows = _make_rows(900)
        return run_walk_forward(
            rows,
            model_eval_fn=_good_model_eval,
            baseline_pred_fns={"poisson_simple": _weak_baseline_fn, "elo_puro": _weak_baseline_fn},
            penca_scoring_fn=_penca_scoring,
            scheme="expanding", min_train=400, step=200,
            output_dir=output_dir,
        )

    def test_walk_forward_outputs_required_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp)
            with (Path(tmp) / "folds_summary.csv").open(encoding="utf-8") as handle:
                fold_rows = list(csv.DictReader(handle))
            self.assertTrue(fold_rows)
            required = {
                "train_n", "test_n", "train_end_date", "test_start_date", "test_end_date",
                "brier", "log_loss", "accuracy", "exact_score_accuracy",
                "penca_points_avg", "penca_points_total", "beats_poisson_simple", "beats_elo_puro",
            }
            self.assertTrue(required.issubset(set(fold_rows[0].keys())),
                            f"faltan columnas: {required - set(fold_rows[0].keys())}")

    def test_walk_forward_summary_beats_flags_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(tmp)
        wf = result["summary"]
        self.assertEqual(wf["beats_poisson_simple"], wf["model_logloss"] < wf["poisson_simple_logloss"])
        self.assertEqual(wf["beats_elo_puro"], wf["model_logloss"] < wf["elo_puro_logloss"])
        # El modelo confiado-correcto debe superar al baseline plano.
        self.assertTrue(wf["beats_poisson_simple"])

    def test_validation_status_uses_walk_forward(self):
        # Contrato: el veredicto se deriva de las métricas walk-forward.
        from worldcup2026.validation_label import validation_label
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(tmp)
        wf = result["summary"]
        verdict = validation_label(
            n=int(wf["total_test_n"]),
            model_logloss=wf["model_logloss"],
            baseline_logloss={"poisson_simple": wf["poisson_simple_logloss"],
                              "elo_puro": wf["elo_puro_logloss"]},
            out_of_sample=True, leakage_warning=True,
        )
        self.assertEqual(verdict.n, int(wf["total_test_n"]))
        self.assertEqual(verdict.beats_baselines,
                         wf["model_logloss"] < min(wf["poisson_simple_logloss"], wf["elo_puro_logloss"]))
        # Si el artefacto real ya incluye walk_forward, su verdict debe ser
        # coherente con él (el bloque se omite si el archivo es de una corrida
        # previa sin walk-forward, para no depender del orden de ejecución).
        if VALIDATION_STATUS_JSON.exists():
            payload = json.loads(VALIDATION_STATUS_JSON.read_text(encoding="utf-8"))
            if "walk_forward" in payload:
                self.assertEqual(payload["verdict"]["n"], payload["walk_forward"]["total_test_n"])
                self.assertEqual(
                    payload["verdict"]["beats_baselines"],
                    payload["walk_forward"]["model_logloss"] < min(
                        payload["walk_forward"]["poisson_simple_logloss"],
                        payload["walk_forward"]["elo_puro_logloss"],
                    ),
                )


if __name__ == "__main__":
    unittest.main()
