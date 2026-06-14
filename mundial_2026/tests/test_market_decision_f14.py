"""Tests F1.4: regla de decisión modelo vs mercado."""

from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.market.decision import (  # noqa: E402
    CONF_ALTA,
    DECISION_COLUMNS,
    decide_pick,
    decision_to_row,
)

DECISION_CSV = ROOT / "outputs" / "market" / "market_decision_log.csv"

REQUIRED_COLUMNS = {
    "match_id", "model_pick", "market_pick", "final_pick", "action",
    "confidence_label", "contradiction_severity", "gap_1x2_total_variation",
    "contradicts_market", "reason", "source_status",
}


class TestDecisionF14(unittest.TestCase):
    def test_no_market_available_caps_confidence(self):
        v = decide_pick(model_pick="home", market_pick=None, contradicts_market=False,
                        contradiction_severity="none", gap_1x2_total_variation=None,
                        gap_status="sin_muestra")
        self.assertEqual(v.action, "no_market_available")
        self.assertEqual(v.final_pick, "home")
        self.assertNotEqual(v.confidence_label, CONF_ALTA)

    def test_low_gap_trusts_model(self):
        v = decide_pick(model_pick="home", market_pick="home", contradicts_market=False,
                        contradiction_severity="none", gap_1x2_total_variation=0.03,
                        gap_status="calculado")
        self.assertEqual(v.action, "trust_model")
        self.assertEqual(v.final_pick, "home")
        self.assertEqual(v.confidence_label, CONF_ALTA)

    def test_mild_gap_keeps_pick_medium_confidence(self):
        v = decide_pick(model_pick="home", market_pick="home", contradicts_market=False,
                        contradiction_severity="mild", gap_1x2_total_variation=0.10,
                        gap_status="calculado")
        self.assertEqual(v.action, "keep_pick")
        self.assertEqual(v.final_pick, "home")
        self.assertEqual(v.confidence_label, "Media")

    def test_strong_gap_lowers_confidence(self):
        v = decide_pick(model_pick="home", market_pick="home", contradicts_market=False,
                        contradiction_severity="strong", gap_1x2_total_variation=0.20,
                        gap_status="calculado")
        self.assertIn(v.action, {"lower_confidence", "shade_to_market"})
        self.assertEqual(v.final_pick, "home")  # final sigue siendo el del modelo
        self.assertEqual(v.confidence_label, "Baja")

    def test_contradicting_winner_follows_market(self):
        v = decide_pick(model_pick="away", market_pick="home", contradicts_market=True,
                        contradiction_severity="strong", gap_1x2_total_variation=0.26,
                        gap_status="calculado")
        self.assertEqual(v.action, "follow_market")
        self.assertEqual(v.final_pick, "home")
        self.assertEqual(v.confidence_label, "Baja")
        self.assertTrue("contradic" in v.reason.lower() or "ganador" in v.reason.lower())

    def test_strong_gap_without_reason_never_high_confidence(self):
        v = decide_pick(model_pick="home", market_pick="home", contradicts_market=False,
                        contradiction_severity="strong", gap_1x2_total_variation=0.22,
                        gap_status="calculado", has_traceable_reason=False)
        self.assertNotEqual(v.confidence_label, CONF_ALTA)
        # Con razón trazable tampoco sube a Alta (gap fuerte).
        v2 = decide_pick(model_pick="home", market_pick="home", contradicts_market=False,
                         contradiction_severity="strong", gap_1x2_total_variation=0.22,
                         gap_status="calculado", has_traceable_reason=True)
        self.assertNotEqual(v2.confidence_label, CONF_ALTA)
        self.assertEqual(v2.action, "lower_confidence")

    def test_market_decision_log_has_required_columns(self):
        row = decision_to_row(decide_pick(
            model_pick="home", market_pick="home", contradicts_market=False,
            contradiction_severity="none", gap_1x2_total_variation=0.02, gap_status="calculado"))
        self.assertEqual(set(row.keys()), set(DECISION_COLUMNS))
        self.assertTrue(REQUIRED_COLUMNS.issubset(set(row.keys())))
        if DECISION_CSV.exists():
            with DECISION_CSV.open(encoding="utf-8") as handle:
                header = set(next(csv.reader(handle)))
            self.assertTrue(REQUIRED_COLUMNS.issubset(header))


if __name__ == "__main__":
    unittest.main()
