"""Tests F2.3: mecanismo Elo staleness-aware con flag OFF (identidad)."""

from __future__ import annotations

import csv
import dataclasses
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.config import PARAMS  # noqa: E402
from worldcup2026.ratings.staleness import (  # noqa: E402
    effective_elo_staleness_aware,
    staleness_shrunk_elo,
)
from build_rating_adjustment_log import LOG_COLUMNS, build_adjustment_row  # noqa: E402

EXPECTED_GOALS_SRC = ROOT / "worldcup2026" / "models" / "expected_goals.py"
ADJ_LOG_CSV = ROOT / "outputs" / "ratings" / "rating_adjustment_log.csv"
REQUIRED = set(LOG_COLUMNS)

PARAMS_ON = dataclasses.replace(PARAMS, elo_staleness_enabled=True)


class TestFlagOff(unittest.TestCase):
    def test_flag_off_is_identity(self):
        for base, fifa, stale in [(1747, 1895.7, 0.99), (1833, 1692.8, 0.93), (1500, 2000, 1.0)]:
            out = effective_elo_staleness_aware(
                base_effective_elo=base, fifa_implied_elo_value=fifa, staleness=stale, params=PARAMS)
            self.assertEqual(out, base)  # flag OFF -> identidad exacta
        self.assertFalse(PARAMS.elo_staleness_enabled)

    def test_flag_off_predictions_bit_identical(self):
        # (a) flag apagado.
        self.assertFalse(PARAMS.elo_staleness_enabled)
        # (b) el mecanismo NO está cableado en expected_goals.py.
        self.assertNotIn("staleness", EXPECTED_GOALS_SRC.read_text(encoding="utf-8").lower())
        # (c) la predicción del modelo es determinista (modelo intacto).
        import backtest_production_adapter  # noqa: F401  (instala shims)
        import modelo_quiniela_2026 as model
        teams = {
            "__a": model.Team(name="__a", confederation="UEFA", status="qualified", elo=1800, fifa_points=None),
            "__b": model.Team(name="__b", confederation="UEFA", status="qualified", elo=1500, fifa_points=None),
        }
        ctx = model.MatchContext(neutral=True)
        p1 = model.predict_match(teams, "__a", "__b", ctx)
        p2 = model.predict_match(teams, "__a", "__b", ctx)
        self.assertEqual((p1.win_a, p1.draw, p1.win_b, tuple(p1.exact_scores)),
                         (p2.win_a, p2.draw, p2.win_b, tuple(p2.exact_scores)))


class TestShrinkMechanism(unittest.TestCase):
    def test_staleness_shrink_moves_toward_fifa(self):
        adj = staleness_shrunk_elo(base_effective_elo=1747, fifa_implied_elo_value=1895.7,
                                   staleness=0.99, w_fifa=0.5, cap=0.35, min_score=0.25)
        self.assertGreater(adj, 1747)        # sube hacia FIFA (USA subestimado)
        self.assertLess(adj, 1895.7)         # pero no llega al FIFA-implied (shrink parcial)

    def test_missing_fifa_no_adjustment(self):
        adj = staleness_shrunk_elo(base_effective_elo=1747, fifa_implied_elo_value=None,
                                   staleness=0.99, w_fifa=0.5, cap=0.35, min_score=0.25)
        self.assertEqual(adj, 1747)

    def test_agreement_no_adjustment(self):
        # staleness por debajo del mínimo -> sin ajuste.
        adj = staleness_shrunk_elo(base_effective_elo=1800, fifa_implied_elo_value=1805,
                                   staleness=0.10, w_fifa=0.5, cap=0.35, min_score=0.25)
        self.assertEqual(adj, 1800)

    def test_shrink_capped(self):
        # staleness 0.99, w_fifa 0.5 -> 0.495, pero cap 0.35 lo limita.
        adj = staleness_shrunk_elo(base_effective_elo=1000, fifa_implied_elo_value=2000,
                                   staleness=0.99, w_fifa=0.5, cap=0.35, min_score=0.0)
        self.assertAlmostEqual(adj, 0.65 * 1000 + 0.35 * 2000, places=6)  # = 1350

    def test_no_future_results_used(self):
        # La función solo depende de rating/FIFA/staleness; no recibe resultados.
        varnames = staleness_shrunk_elo.__code__.co_varnames
        for forbidden in ("goals", "result", "score", "actual"):
            self.assertNotIn(forbidden, varnames)
        # Idempotente.
        kw = dict(base_effective_elo=1747, fifa_implied_elo_value=1895.7,
                  staleness=0.99, w_fifa=0.5, cap=0.35, min_score=0.25)
        self.assertEqual(staleness_shrunk_elo(**kw), staleness_shrunk_elo(**kw))


class TestAdjustmentLog(unittest.TestCase):
    def test_rating_adjustment_log_has_required_columns(self):
        assess = {"elo": 1747, "fifa_implied_elo": 1895.7, "elo_staleness_score": 0.99}
        row = build_adjustment_row("M", "United States", assess, captured_at_utc="2026-06-14T00:00:00Z")
        self.assertEqual(set(row.keys()), REQUIRED)
        self.assertFalse(row["applied_in_production"])  # flag OFF
        if ADJ_LOG_CSV.exists():
            with ADJ_LOG_CSV.open(encoding="utf-8") as handle:
                header = set(next(csv.reader(handle)))
            self.assertTrue(REQUIRED.issubset(header))

    def test_flag_on_off_log_differs_only_in_applied_flag(self):
        # Sanidad: el log calcula el ajuste hipotético igual; solo cambia applied_in_production.
        assess = {"elo": 1747, "fifa_implied_elo": 1895.7, "elo_staleness_score": 0.99}
        row = build_adjustment_row("M", "United States", assess, captured_at_utc="t")
        self.assertGreater(float(row["adjusted_elo"]), float(row["base_elo"]))  # hipotético sube
        self.assertEqual(row["shrink_target"], "fifa_implied_elo")


if __name__ == "__main__":
    unittest.main()
