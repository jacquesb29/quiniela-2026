"""Tests F0.1 + F0.2: adaptador de backtest real y ablation no degenerada.

Cubren los 7 tests obligatorios de la fase:
  1. test_adapter_uses_row_elo_not_teams_json
  2. test_production_fn_returns_valid_distribution
  3. test_modelo_completo_differs_from_elo_puro
  4. test_no_teams_json_import_in_adapter
  5. test_sin_fifa_marked_not_applicable_when_empty
  6. test_strip_counts_match
  7. test_no_identical_deltas_for_applicable_blocks
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backtest_production_adapter as adapter  # noqa: E402
import modelo_quiniela_2026 as model  # noqa: E402
from worldcup2026.ablation import (  # noqa: E402
    NOT_APPLICABLE_RECOMMENDATION,
    evaluate_ablation,
    strip_block_fields,
)
from worldcup2026.benchmarks import elo_prediction  # noqa: E402


def _row(team_a="Alpha", team_b="Beta", elo_a="1800", elo_b="1500", goals_a="2", goals_b="0", **extra):
    row = {
        "match_id": f"{team_a}_{team_b}",
        "date": "1990-06-01",
        "competition": "FIFA World Cup",
        "phase": "unknown_stage_from_source",
        "team_a": team_a,
        "team_b": team_b,
        "goals_a": goals_a,
        "goals_b": goals_b,
        "neutral": "1",
        "knockout": "",
        "elo_a_pre": elo_a,
        "elo_b_pre": elo_b,
        "fifa_rank_a_pre": "",
        "fifa_rank_b_pre": "",
        "market_prob_a_pre": "",
        "market_prob_draw_pre": "",
        "market_prob_b_pre": "",
        "squad_quality_a_pre": "",
        "squad_quality_b_pre": "",
        "historical_strength_a_pre": "0.62",
        "historical_strength_b_pre": "0.30",
    }
    row.update(extra)
    return row


class TestAdapterF01(unittest.TestCase):
    def test_adapter_uses_row_elo_not_teams_json(self):
        row = _row(elo_a="1234.5", elo_b="1999.0")
        team_a = adapter.team_from_historical_row(row, "a")
        team_b = adapter.team_from_historical_row(row, "b")
        self.assertEqual(team_a.elo, 1234.5)
        self.assertEqual(team_b.elo, 1999.0)
        # No FIFA real (queda neutral); el nombre es sintético (no del JSON 2026).
        self.assertIsNone(team_a.fifa_points)
        self.assertTrue(team_a.name.startswith("__bt__"))

    def test_production_fn_returns_valid_distribution(self):
        pred = adapter.production_prediction_fn(_row())
        self.assertIsNotNone(pred)
        total = pred.win_a + pred.draw + pred.win_b
        self.assertAlmostEqual(total, 1.0, places=6)
        for p in (pred.win_a, pred.draw, pred.win_b):
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)
        self.assertTrue(pred.exact_scores)
        # El favorito por Elo (A) debe tener mayor probabilidad que el débil (B).
        self.assertGreater(pred.win_a, pred.win_b)

    def test_modelo_completo_differs_from_elo_puro(self):
        row = _row(elo_a="1850", elo_b="1480")
        prod = adapter.production_prediction_fn(row)
        elo = elo_prediction(row)
        self.assertIsNotNone(elo)
        # Las probabilidades del modelo real NO deben coincidir con el benchmark
        # elo_puro: son motores distintos (ensamble vs logística simple).
        diffs = [
            abs(prod.win_a - elo.prob_a),
            abs(prod.draw - elo.prob_draw),
            abs(prod.win_b - elo.prob_b),
        ]
        self.assertTrue(max(diffs) > 1e-6, f"modelo idéntico a elo_puro: {diffs}")

    def test_no_teams_json_import_in_adapter(self):
        # Si el adaptador intentara resolver vía teams_2026.json, llamaría a
        # model.load_teams(); lo forzamos a fallar y la predicción debe seguir.
        original = model.load_teams

        def _boom():
            raise RuntimeError("teams_2026.json no debe leerse en el backtest")

        model.load_teams = _boom
        try:
            pred = adapter.production_prediction_fn(_row())
            self.assertIsNotNone(pred)
            self.assertAlmostEqual(pred.win_a + pred.draw + pred.win_b, 1.0, places=6)
        finally:
            model.load_teams = original


class TestAblationF02(unittest.TestCase):
    def _rows(self, n=24):
        rows = []
        for i in range(n):
            elo_a = 1500 + (i * 17) % 400
            elo_b = 1500 + (i * 29) % 400
            ga, gb = (2, 0) if elo_a >= elo_b else (0, 1)
            rows.append(_row(team_a=f"A{i}", team_b=f"B{i}", elo_a=str(elo_a), elo_b=str(elo_b),
                             goals_a=str(ga), goals_b=str(gb)))
        return rows

    def test_sin_fifa_marked_not_applicable_when_empty(self):
        results = evaluate_ablation(self._rows(), full_model_fn=adapter.production_prediction_fn)
        sin_fifa = next(r for r in results if r.variant == "sin_fifa")
        self.assertFalse(sin_fifa.applicable)
        self.assertEqual(sin_fifa.stripped_fields, 0)
        self.assertEqual(sin_fifa.recommendation, NOT_APPLICABLE_RECOMMENDATION)

    def test_strip_counts_match(self):
        row = _row()
        # elo_a_pre y elo_b_pre presentes con valor -> 2 eliminadas.
        _, count_elo = strip_block_fields(row, "sin_elo")
        self.assertEqual(count_elo, 2)
        # fifa_*_pre presentes pero vacías -> 0 eliminadas (no cuentan).
        _, count_fifa = strip_block_fields(row, "sin_fifa")
        self.assertEqual(count_fifa, 0)

    def test_no_identical_deltas_for_applicable_blocks(self):
        results = evaluate_ablation(self._rows(), full_model_fn=adapter.production_prediction_fn)
        # sin_elo es aplicable Y consumido por el modelo: debe mover métricas.
        sin_elo = next(r for r in results if r.variant == "sin_elo")
        self.assertTrue(sin_elo.applicable)
        self.assertGreater(sin_elo.matches, 0)
        # Regresión del síntoma viejo: NO todos los deltas aplicables son cero.
        applicable_deltas = [
            r.delta_log_loss_vs_full
            for r in results
            if r.applicable and r.variant != "modelo_completo" and r.delta_log_loss_vs_full is not None
        ]
        self.assertTrue(applicable_deltas)
        self.assertFalse(
            all(abs(d) < 1e-12 for d in applicable_deltas),
            "todos los deltas aplicables son cero (ablation degenerada)",
        )


if __name__ == "__main__":
    unittest.main()
