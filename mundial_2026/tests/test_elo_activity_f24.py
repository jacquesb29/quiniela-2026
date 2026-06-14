"""Tests F2.4: enriquecimiento de staleness con actividad reciente."""

from __future__ import annotations

import csv
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.config import PARAMS  # noqa: E402
from worldcup2026.ratings.activity import (  # noqa: E402
    RecentActivity,
    compute_activity_table,
    is_official,
)
from worldcup2026.ratings.staleness import (  # noqa: E402
    REPORT_COLUMNS,
    PoolStats,
    assess_team_staleness,
    elo_staleness_score,
)
from build_rating_adjustment_log import LOG_COLUMNS, build_adjustment_row, build_rows  # noqa: E402

REPORT_CSV = ROOT / "outputs" / "ratings" / "elo_staleness_report.csv"
EXPECTED_GOALS_SRC = ROOT / "worldcup2026" / "models" / "expected_goals.py"
_POOL = PoolStats(mean_elo=1800.0, std_elo=100.0, mean_fifa=1500.0, std_fifa=100.0)
ACTIVITY_COLS = {"last_match_age_days", "recent_coverage_6m", "recent_coverage_12m",
                 "official_matches_12m", "friendly_matches_12m", "anomalous_elo_jump", "activity_warning"}


def _m(d, home, away, gh, ga, tournament="FIFA World Cup qualification"):
    return {"date": d, "home_team": home, "away_team": away,
            "home_score": str(gh), "away_score": str(ga), "tournament": tournament}


class TestActivity(unittest.TestCase):
    def test_recent_activity_uses_only_past_matches(self):
        raw = [
            _m("2025-12-01", "Z", "Y", 1, 0),                 # antes de as_of -> cuenta
            _m("2026-05-01", "Z", "Y", 3, 0),                 # DESPUÉS de as_of -> se ignora
        ]
        table = compute_activity_table(raw, as_of_date=date(2026, 4, 2))
        self.assertEqual(table["Z"].recent_coverage_12m, 1)   # solo el partido pasado
        self.assertEqual(table["Z"].last_match_age_days, (date(2026, 4, 2) - date(2025, 12, 1)).days)
        # Cambiar el partido futuro no altera la actividad pasada.
        raw2 = [_m("2025-12-01", "Z", "Y", 1, 0), _m("2026-05-01", "Z", "Y", 9, 0)]
        self.assertEqual(compute_activity_table(raw2, as_of_date=date(2026, 4, 2))["Z"].recent_coverage_12m, 1)

    def test_team_without_recent_matches_gets_higher_staleness(self):
        inactive = elo_staleness_score({"elo": 1800}, fifa_implied_elo_value=1800,
                                       last_match_age_days=600, recent_coverage=None, anomalous_jump=None,
                                       official_matches_12m=0, friendly_matches_12m=0)
        active = elo_staleness_score({"elo": 1800}, fifa_implied_elo_value=1800,
                                     last_match_age_days=5, recent_coverage=None, anomalous_jump=None,
                                     official_matches_12m=12, friendly_matches_12m=0)
        self.assertGreater(inactive, active)

    def test_team_with_recent_official_coverage_gets_lower_staleness(self):
        with_cov = elo_staleness_score({"elo": 1800}, fifa_implied_elo_value=1850,
                                       last_match_age_days=20, recent_coverage=None, anomalous_jump=None,
                                       official_matches_12m=12, friendly_matches_12m=0)
        without_cov = elo_staleness_score({"elo": 1800}, fifa_implied_elo_value=1850,
                                          last_match_age_days=20, recent_coverage=None, anomalous_jump=None,
                                          official_matches_12m=0, friendly_matches_12m=0)
        self.assertLessEqual(with_cov, without_cov)

    def test_friendlies_weight_less_than_officials(self):
        officials = elo_staleness_score({"elo": 1800}, fifa_implied_elo_value=1800,
                                        last_match_age_days=30, recent_coverage=None, anomalous_jump=None,
                                        official_matches_12m=10, friendly_matches_12m=0)
        friendlies = elo_staleness_score({"elo": 1800}, fifa_implied_elo_value=1800,
                                         last_match_age_days=30, recent_coverage=None, anomalous_jump=None,
                                         official_matches_12m=0, friendly_matches_12m=10)
        self.assertGreater(friendlies, officials)  # amistosos pesan menos -> más staleness
        self.assertTrue(is_official("FIFA World Cup qualification"))
        self.assertFalse(is_official("Friendly"))

    def test_anomalous_elo_jump_detected(self):
        # (a) en datos reales el proxy de salto se computa (no None).
        raw = [_m("2025-06-01", "Z", "Y", 2, 0), _m("2025-09-01", "Y", "Z", 0, 1),
               _m("2025-11-01", "Z", "W", 3, 0)]
        table = compute_activity_table(raw, as_of_date=date(2026, 4, 2))
        self.assertIsNotNone(table["Z"].anomalous_elo_jump)
        self.assertGreater(table["Z"].anomalous_elo_jump, 0.0)
        # (b) un salto alto dispara warning en assess (sin forzar ajuste).
        big_jump = RecentActivity(last_match_age_days=10, recent_coverage_6m=3, recent_coverage_12m=6,
                                  official_matches_12m=4, friendly_matches_12m=2, anomalous_elo_jump=60.0,
                                  activity_warning="")
        row = assess_team_staleness({"name": "X", "elo": 1800, "fifa_points": 1500},
                                    pool_stats=_POOL, activity=big_jump)
        self.assertIn("salto de Elo reciente", row["warnings"])

    def test_missing_history_warns_without_inventing(self):
        row = assess_team_staleness({"name": "X", "elo": 1800, "fifa_points": 1500},
                                    pool_stats=_POOL, activity=None)
        self.assertIn("sin actividad reciente", row["warnings"])
        self.assertEqual(row["recent_coverage_12m"], "")     # no inventa
        self.assertEqual(row["anomalous_elo_jump"], "")

    def test_predictions_bit_identical_with_flag_off(self):
        self.assertFalse(PARAMS.elo_staleness_enabled)
        self.assertNotIn("staleness", EXPECTED_GOALS_SRC.read_text(encoding="utf-8").lower())
        import backtest_production_adapter  # noqa: F401
        import modelo_quiniela_2026 as model
        teams = {
            "__a": model.Team(name="__a", confederation="UEFA", status="qualified", elo=1800, fifa_points=None),
            "__b": model.Team(name="__b", confederation="UEFA", status="qualified", elo=1500, fifa_points=None),
        }
        ctx = model.MatchContext(neutral=True)
        p1 = model.predict_match(teams, "__a", "__b", ctx)
        p2 = model.predict_match(teams, "__a", "__b", ctx)
        self.assertEqual((p1.win_a, p1.draw, p1.win_b), (p2.win_a, p2.draw, p2.win_b))

    def test_staleness_report_has_activity_columns(self):
        self.assertTrue(ACTIVITY_COLS.issubset(set(REPORT_COLUMNS)))
        if REPORT_CSV.exists():
            with REPORT_CSV.open(encoding="utf-8") as handle:
                header = set(next(csv.reader(handle)))
            self.assertTrue(ACTIVITY_COLS.issubset(header))

    def test_rating_adjustment_log_has_activity_columns(self):
        self.assertTrue(ACTIVITY_COLS.issubset(set(LOG_COLUMNS)))
        # build_rows produce filas con las columnas de actividad pobladas (datos reales).
        rows = build_rows(captured_at_utc="2026-06-14T00:00:00Z")
        self.assertTrue(rows)
        self.assertTrue(ACTIVITY_COLS.issubset(set(rows[0].keys())))
        # Una fila con assess mínimo (sin actividad) sigue teniendo las columnas (vacías).
        minimal = build_adjustment_row("M", "X", {"elo": 1800, "fifa_implied_elo": 1850,
                                                  "elo_staleness_score": 0.5}, captured_at_utc="t")
        self.assertEqual(set(minimal.keys()), set(LOG_COLUMNS))


if __name__ == "__main__":
    unittest.main()
