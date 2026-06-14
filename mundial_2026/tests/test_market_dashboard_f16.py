"""Tests F1.6: dashboard de mercado/T-60 (lectura de outputs)."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.market.dashboard import (  # noqa: E402
    build_match_market_view,
    load_market_outputs,
    render_market_dashboard_html,
    validation_scope_text,
)

REAL_MARKET_DIR = ROOT / "outputs" / "market"
REAL_VALIDATION = ROOT / "outputs" / "validation_status.json"


def _write_csv(path: Path, rows, cols):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _make_market_dir(tmp: Path, *, gap=None, decision=None, t60=None, implied=None, last_hour=None):
    if gap is not None:
        _write_csv(tmp / "market_model_gap.csv", gap, list(gap[0].keys()))
    if decision is not None:
        _write_csv(tmp / "market_decision_log.csv", decision, list(decision[0].keys()))
    if t60 is not None:
        _write_csv(tmp / "t60_decision_log.csv", t60, list(t60[0].keys()))
    if implied is not None:
        _write_csv(tmp / "market_implied_probabilities.csv", implied, list(implied[0].keys()))
    if last_hour is not None:
        _write_csv(tmp / "last_hour_update.csv", last_hour, list(last_hour[0].keys()))


class TestMarketDashboardF16(unittest.TestCase):
    def test_dashboard_reads_market_outputs(self):
        if not (REAL_MARKET_DIR / "market_model_gap.csv").exists():
            self.skipTest("outputs de mercado reales no presentes")
        data = load_market_outputs(REAL_MARKET_DIR, REAL_VALIDATION)
        self.assertTrue(data["available"])
        self.assertTrue(data["match_ids"])
        view = build_match_market_view(data["match_ids"][0], data)
        self.assertIn("final_pick", view)

    def test_dashboard_handles_missing_market_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = load_market_outputs(tmp, Path(tmp) / "no_validation.json")
            self.assertFalse(data["available"])
            html = render_market_dashboard_html(data)
            self.assertIn("pendiente", html.lower())  # no rompe la web

    def test_dashboard_shows_final_pick(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _make_market_dir(tmp,
                gap=[{"match_id": "M", "gap_status": "calculado", "model_pick": "home",
                      "market_pick": "home", "contradicts_market": "False",
                      "contradiction_severity": "mild", "gap_1x2_total_variation": "0.1"}],
                decision=[{"match_id": "M", "final_pick": "home", "action": "keep_pick",
                           "confidence_label": "Media", "model_pick": "home", "market_pick": "home"}])
            data = load_market_outputs(tmp, tmp / "v.json")
            view = build_match_market_view("M", data)
            self.assertEqual(view["final_pick"], "home")
            self.assertIn("Pick final recomendado", render_market_dashboard_html(data))

    def test_dashboard_shows_t60_before_after_when_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _make_market_dir(tmp,
                t60=[{"match_id": "M", "pick_before": "away", "pick_after": "home",
                      "changed": "True", "confidence_before": "Media", "confidence_after": "Baja",
                      "trigger": "market_contradiction", "reason": "contradicción de ganador",
                      "captured_at_utc": "2026-06-14T18:40:00Z", "lineup_confirmed": "True",
                      "injuries_confirmed": "", "starting_gk": "Turner", "gk_changed": "False"}])
            data = load_market_outputs(tmp, tmp / "v.json")
            html = render_market_dashboard_html(data)
            self.assertIn("away → home", html)
            self.assertIn("contradicción de ganador", html)

    def test_dashboard_does_not_show_high_confidence_when_decision_low(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _make_market_dir(tmp,
                gap=[{"match_id": "M", "gap_status": "calculado", "model_pick": "home",
                      "market_pick": "away", "contradicts_market": "True",
                      "contradiction_severity": "strong", "gap_1x2_total_variation": "0.26"}],
                decision=[{"match_id": "M", "final_pick": "away", "action": "follow_market",
                           "confidence_label": "Baja", "model_pick": "home", "market_pick": "away"}])
            data = load_market_outputs(tmp, tmp / "v.json")
            html = render_market_dashboard_html(data)
            self.assertIn("Confianza: <b>Baja", html)
            self.assertNotIn("Confianza: <b>Alta", html)

    def test_dashboard_hides_market_when_gap_sin_muestra(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _make_market_dir(tmp,
                gap=[{"match_id": "M", "gap_status": "sin_muestra", "model_pick": "home",
                      "market_pick": "", "contradicts_market": "False",
                      "contradiction_severity": "none", "gap_1x2_total_variation": ""}],
                decision=[{"match_id": "M", "final_pick": "home", "action": "no_market_available",
                           "confidence_label": "Media", "model_pick": "home", "market_pick": ""}])
            data = load_market_outputs(tmp, tmp / "v.json")
            view = build_match_market_view("M", data)
            self.assertFalse(view["show_market"])
            html = render_market_dashboard_html(data)
            self.assertIn("sin muestra suficiente", html)
            self.assertNotIn("Pick mercado:", html)  # no se muestra pick de mercado

    def test_dashboard_validation_scope_text_present(self):
        validado = {"verdict": {"label": "validado", "reason": "supera benchmarks"}}
        text = validation_scope_text(validado)
        self.assertIn("vs Poisson", text)
        self.assertIn("Track 2026", text)
        # En el HTML renderizado también aparece el alcance.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "v.json").write_text('{"verdict": {"label": "validado", "reason": "x"}}', encoding="utf-8")
            _make_market_dir(tmp, gap=[{"match_id": "M", "gap_status": "calculado",
                                        "model_pick": "home", "market_pick": "home",
                                        "contradicts_market": "False", "contradiction_severity": "none",
                                        "gap_1x2_total_variation": "0.02"}])
            data = load_market_outputs(tmp, tmp / "v.json")
            html = render_market_dashboard_html(data)
            self.assertIn("validado", html.lower())
            self.assertIn("vs Poisson", html)


if __name__ == "__main__":
    unittest.main()
