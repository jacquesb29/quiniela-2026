"""Tests F2.1: fifa_implied_elo, elo_staleness_score y reporte de staleness."""

from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.ratings.staleness import (  # noqa: E402
    REPORT_COLUMNS,
    T_HIGH,
    T_LOW,
    PoolStats,
    assess_team_staleness,
    compute_pool_stats,
    elo_staleness_score,
    fifa_implied_elo,
)

TEAMS_JSON = ROOT / "teams_2026.json"
REPORT_CSV = ROOT / "outputs" / "ratings" / "elo_staleness_report.csv"

REQUIRED = {
    "team", "elo", "fifa_points", "fifa_rank", "fifa_implied_elo", "elo_vs_fifa_gap",
    "last_match_age_days", "recent_coverage", "anomalous_jump", "elo_staleness_score",
    "recommended_action", "warnings",
}

_POOL = PoolStats(mean_elo=1800.0, std_elo=100.0, mean_fifa=1500.0, std_fifa=100.0)


def _load_real_pool():
    payload = json.loads(TEAMS_JSON.read_text(encoding="utf-8"))
    teams = payload.get("teams", payload)
    teams = teams if isinstance(teams, list) else list(teams.values())
    qualified = [t for t in teams if isinstance(t, dict) and t.get("status") == "qualified"]
    pool = [t for t in qualified if t.get("elo") and t.get("fifa_points")]
    return qualified, compute_pool_stats(pool)


def _team(name, qualified):
    return next(t for t in qualified if t.get("name") == name)


class TestFifaImpliedElo(unittest.TestCase):
    def test_fifa_implied_elo_monotonic(self):
        low = fifa_implied_elo({"fifa_points": 1400}, pool_stats=_POOL)
        mid = fifa_implied_elo({"fifa_points": 1500}, pool_stats=_POOL)
        high = fifa_implied_elo({"fifa_points": 1700}, pool_stats=_POOL)
        self.assertLess(low, mid)
        self.assertLess(mid, high)
        self.assertAlmostEqual(mid, 1800.0, places=6)  # fifa = media -> elo medio


class TestStalenessScore(unittest.TestCase):
    def test_staleness_score_in_range(self):
        for fp in (1300, 1500, 1700, 1900, 2100):
            fie = fifa_implied_elo({"fifa_points": fp}, pool_stats=_POOL)
            s = elo_staleness_score({"elo": 1800}, fifa_implied_elo_value=fie,
                                    last_match_age_days=None, recent_coverage=None, anomalous_jump=None)
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)

    def test_agreement_low_staleness(self):
        # elo == fifa_implied (fifa = media) -> gap 0 -> score bajo.
        fie = fifa_implied_elo({"fifa_points": 1500}, pool_stats=_POOL)
        s = elo_staleness_score({"elo": 1800}, fifa_implied_elo_value=fie,
                                last_match_age_days=None, recent_coverage=None, anomalous_jump=None)
        self.assertLess(s, T_LOW)

    def test_disagreement_high_staleness(self):
        # elo bajo pero FIFA muy alta -> gap grande -> score alto.
        fie = fifa_implied_elo({"fifa_points": 1900}, pool_stats=_POOL)  # implied ~2200
        s = elo_staleness_score({"elo": 1800}, fifa_implied_elo_value=fie,
                                last_match_age_days=None, recent_coverage=None, anomalous_jump=None)
        self.assertGreaterEqual(s, T_HIGH)

    def test_missing_fifa_warns_and_does_not_invent(self):
        row = assess_team_staleness({"name": "X", "elo": 1800, "fifa_points": None}, pool_stats=_POOL)
        self.assertEqual(row["fifa_implied_elo"], "")     # no se inventa
        self.assertEqual(row["fifa_points"], "")
        self.assertEqual(row["elo_staleness_score"], 0.0)  # sin señal -> 0
        self.assertIn("sin fifa", row["warnings"])
        self.assertEqual(row["recommended_action"], "elo_domina")


class TestRealCases(unittest.TestCase):
    def test_usa_paraguay_inconsistency_detected(self):
        qualified, pool = _load_real_pool()
        usa = assess_team_staleness(_team("United States", qualified), pool_stats=pool)
        par = assess_team_staleness(_team("Paraguay", qualified), pool_stats=pool)
        self.assertGreaterEqual(usa["elo_staleness_score"], T_HIGH)
        self.assertGreaterEqual(par["elo_staleness_score"], T_HIGH)
        # Gaps de signo opuesto: USA Elo subestima (gap<0), Paraguay sobrevalora (gap>0).
        self.assertLess(float(usa["elo_vs_fifa_gap"]), 0.0)
        self.assertGreater(float(par["elo_vs_fifa_gap"]), 0.0)
        self.assertEqual(usa["recommended_action"], "shrink_fifa")
        self.assertEqual(par["recommended_action"], "shrink_fifa")

    def test_australia_turkey_possible_staleness_detected(self):
        qualified, pool = _load_real_pool()
        aus = assess_team_staleness(_team("Australia", qualified), pool_stats=pool)
        tur = assess_team_staleness(_team("Turkey", qualified), pool_stats=pool)
        self.assertGreater(tur["elo_staleness_score"], aus["elo_staleness_score"])
        self.assertLess(aus["elo_staleness_score"], T_LOW)   # Australia consistente
        self.assertGreater(tur["elo_staleness_score"], 0.0)  # Turquía con señal


class TestReport(unittest.TestCase):
    def test_report_has_required_columns(self):
        row = assess_team_staleness({"name": "X", "elo": 1800, "fifa_points": 1600}, pool_stats=_POOL)
        self.assertTrue(REQUIRED.issubset(set(row.keys())))
        if REPORT_CSV.exists():
            with REPORT_CSV.open(encoding="utf-8") as handle:
                header = set(next(csv.reader(handle)))
            self.assertTrue(REQUIRED.issubset(header))


if __name__ == "__main__":
    unittest.main()
