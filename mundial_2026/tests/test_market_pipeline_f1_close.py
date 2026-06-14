"""Tests cierre operativo F1: pipeline único de mercado/T-60 + runbook."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_market_t60_pipeline as pipeline  # noqa: E402

RUNBOOK = ROOT / "MARKET_T60_RUNBOOK.md"
DASHBOARD_HTML = ROOT / "outputs" / "market" / "market_dashboard.html"


class TestMarketT60Pipeline(unittest.TestCase):
    def test_market_t60_pipeline_runs_end_to_end(self):
        code = pipeline.main([])
        self.assertEqual(code, 0)
        self.assertTrue(DASHBOARD_HTML.exists())

    def test_market_t60_pipeline_handles_missing_market(self):
        missing = ROOT / "data" / "__no_existe_market_input__.csv"
        self.assertFalse(missing.exists())
        # Debe fallar CLARAMENTE (código != 0) sin lanzar excepción.
        code = pipeline.main([], market_input=missing)
        self.assertEqual(code, 2)

    def test_runbook_exists_and_mentions_required_files(self):
        self.assertTrue(RUNBOOK.exists())
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("market_odds_input.csv", text)
        self.assertIn("t60_inputs.csv", text)
        # Menciona cómo evitar closing/post-kickoff.
        self.assertIn("closing", text.lower())
        self.assertIn("kickoff", text.lower())

    def test_pipeline_summary_contains_changed_picks(self):
        pipeline.main([])  # asegura outputs frescos
        summary = pipeline.summarize_pipeline()
        for key in ("partidos_con_mercado", "partidos_sin_mercado", "picks_changed",
                    "strong_contradictions", "dashboard_html"):
            self.assertIn(key, summary)
        self.assertIsInstance(summary["picks_changed"], int)
        self.assertGreaterEqual(summary["picks_changed"], 0)


if __name__ == "__main__":
    unittest.main()
