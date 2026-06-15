"""Tests de la capa worldcup2026/improvement/.

Obligatorios:
  - test_registry_exists
  - test_no_improvement_active_without_gate
  - test_f2_remains_keep_off
  - test_f4_remains_keep_off
  - test_f5_no_clear_culprit_blocks_f6
  - test_market_t60_active_operational
  - test_predictions_unchanged
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_improvement_review
from worldcup2026.improvement import collect_evidence, load_registry
from worldcup2026.improvement.registry import COLUMNS, REGISTRY_CSV
from worldcup2026.improvement.hypothesis import Gate, Status, validate


def setUpModule():
    run_improvement_review.main([])  # genera registry + decisions


def _by_id():
    return {h.id: h for h in load_registry()}


class TestImprovement(unittest.TestCase):
    def test_registry_exists(self):
        self.assertTrue(REGISTRY_CSV.exists())
        reg = load_registry()
        ids = {h.id for h in reg}
        for required in ("results-update-feed-primary", "market-overlay-refine",
                         "t60-lineup-adjust", "elo-staleness-shrink", "draws-favorito-uplift",
                         "tail-reweight", "penca-selector-tune", "f6-component-fix"):
            self.assertIn(required, ids)
        # cabecera completa
        import csv
        header = next(csv.reader(REGISTRY_CSV.open(encoding="utf-8")))
        self.assertEqual(tuple(header), COLUMNS)

    def test_no_improvement_active_without_gate(self):
        for h in load_registry():
            if h.status == Status.ACTIVE:
                # ACTIVE solo permitido para gates operativos/frescura y sin tocar producción.
                self.assertFalse(h.touches_production, f"{h.id} ACTIVE y toca producción")
                self.assertIn(h.required_gate, (Gate.OPERATIONAL, Gate.DATA_FRESHNESS))
                self.assertEqual(validate(h), [])

    def test_f2_remains_keep_off(self):
        h = _by_id()["elo-staleness-shrink"]
        self.assertEqual(h.status, Status.DIAGNOSTIC_ONLY)

    def test_f4_remains_keep_off(self):
        h = _by_id()["tail-reweight"]
        self.assertEqual(h.status, Status.REJECTED)

    def test_f5_no_clear_culprit_blocks_f6(self):
        ev = collect_evidence(ROOT)
        self.assertEqual(ev.f5_attribution, "no_clear_culprit")
        h = _by_id()["f6-component-fix"]
        self.assertEqual(h.status, Status.REJECTED)

    def test_market_t60_active_operational(self):
        market = _by_id()["market-overlay-refine"]
        self.assertEqual(market.status, Status.ACTIVE)
        self.assertFalse(market.touches_production)
        self.assertEqual(market.required_gate, Gate.OPERATIONAL)
        # T-60: overlay; active solo si hay alineaciones, si no diagnostic_only (nunca toca prod).
        t60 = _by_id()["t60-lineup-adjust"]
        self.assertIn(t60.status, (Status.ACTIVE, Status.DIAGNOSTIC_ONLY))
        self.assertFalse(t60.touches_production)

    def test_predictions_unchanged(self):
        import modelo_quiniela_2026 as M
        teams = M.load_teams()
        pairs = [("Mexico", "South Africa"), ("Canada", "Bosnia and Herzegovina"),
                 ("Brazil", "Morocco")]

        def snapshot():
            out = {}
            for a, b in pairs:
                p = M.predict_match(teams, a, b)
                out[(a, b)] = (round(p.win_a, 9), round(p.draw, 9), round(p.win_b, 9),
                               round(p.expected_goals_a, 9), round(p.expected_goals_b, 9),
                               p.exact_scores[0][0])
            return out

        before = snapshot()
        run_improvement_review.main([])  # vuelve a correr la revisión
        after = snapshot()
        self.assertEqual(before, after, "La revisión de mejoras NO debe cambiar predicciones")


if __name__ == "__main__":
    unittest.main()
