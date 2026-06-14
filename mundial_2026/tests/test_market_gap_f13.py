"""Tests F1.3: comparación modelo vs mercado."""

from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.market.gap import (  # noqa: E402
    GAP_COLUMNS,
    gap_report_to_row,
    model_vs_market_gap,
    total_variation_distance,
)

GAP_CSV = ROOT / "outputs" / "market" / "market_model_gap.csv"

REQUIRED_COLUMNS = {
    "match_id", "model_pick", "market_pick",
    "model_prob_a", "model_prob_draw", "model_prob_b",
    "market_prob_a", "market_prob_draw", "market_prob_b",
    "gap_1x2_home", "gap_1x2_draw", "gap_1x2_away", "gap_1x2_total_variation",
    "model_total_goals", "market_total_goals", "gap_total_goals",
    "model_supremacy", "market_supremacy", "gap_supremacy",
    "model_lambda_a", "model_lambda_b", "market_lambda_home", "market_lambda_away",
    "gap_lambda_home", "gap_lambda_away",
    "contradicts_market", "contradiction_severity", "gap_status", "warnings",
}


def _model(pa, pd, pb, la=1.6, lb=1.0):
    return {"prob_a": pa, "prob_draw": pd, "prob_b": pb, "lambda_a": la, "lambda_b": lb}


def _market(ph, pdr, pa_, total=2.6, sup=0.6, lh=1.6, la=1.0):
    return {"p_home": ph, "p_draw": pdr, "p_away": pa_,
            "market_total_goals": total, "market_supremacy": sup,
            "market_lambda_home": lh, "market_lambda_away": la}


class TestGapF13(unittest.TestCase):
    def test_gap_none_without_market(self):
        report = model_vs_market_gap(_model(0.5, 0.3, 0.2), None)
        self.assertIsNone(report.gap_1x2_total_variation)
        self.assertEqual(report.gap_status, "sin_muestra")
        self.assertFalse(report.contradicts_market)
        self.assertEqual(report.contradiction_severity, "none")

    def test_total_variation_distance(self):
        tv = total_variation_distance(
            {"home": 0.5, "draw": 0.3, "away": 0.2},
            {"home": 0.4, "draw": 0.3, "away": 0.3},
        )
        self.assertAlmostEqual(tv, 0.1, places=12)

    def test_winner_contradiction_detected(self):
        report = model_vs_market_gap(_model(0.5, 0.3, 0.2), _market(0.2, 0.3, 0.5))
        self.assertEqual(report.model_pick, "home")
        self.assertEqual(report.market_pick, "away")
        self.assertTrue(report.contradicts_market)

    def test_gap_severity_mild_and_strong(self):
        mild = model_vs_market_gap(_model(0.50, 0.30, 0.20), _market(0.42, 0.30, 0.28))
        self.assertAlmostEqual(mild.gap_1x2_total_variation, 0.08, places=9)
        self.assertEqual(mild.contradiction_severity, "mild")
        strong = model_vs_market_gap(_model(0.60, 0.25, 0.15), _market(0.40, 0.25, 0.35))
        self.assertAlmostEqual(strong.gap_1x2_total_variation, 0.20, places=9)
        self.assertEqual(strong.contradiction_severity, "strong")

    def test_missing_total_keeps_lambda_gap_empty(self):
        implied = {"p_home": 0.5, "p_draw": 0.3, "p_away": 0.2,
                   "market_total_goals": None, "market_supremacy": None,
                   "market_lambda_home": None, "market_lambda_away": None}
        report = model_vs_market_gap(_model(0.5, 0.3, 0.2), implied)
        self.assertEqual(report.gap_status, "calculado")          # 1X2 sí presente
        self.assertIsNone(report.gap_total_goals)
        self.assertIsNone(report.gap_lambda_home)
        self.assertIsNone(report.gap_lambda_away)
        self.assertTrue(any("gap_lambda vac" in w for w in report.warnings))

    def test_market_model_gap_csv_has_required_columns(self):
        # Columnas de la fila serializada cubren las requeridas.
        row = gap_report_to_row(model_vs_market_gap(_model(0.5, 0.3, 0.2), _market(0.45, 0.30, 0.25)))
        self.assertEqual(set(row.keys()), set(GAP_COLUMNS))
        self.assertTrue(REQUIRED_COLUMNS.issubset(set(row.keys())))
        # Si el artefacto real existe, su cabecera también debe cubrirlas.
        if GAP_CSV.exists():
            with GAP_CSV.open(encoding="utf-8") as handle:
                header = set(next(csv.reader(handle)))
            self.assertTrue(REQUIRED_COLUMNS.issubset(header))


if __name__ == "__main__":
    unittest.main()
