"""Tests F2.2: reporte de discrepancia Elo/FIFA/mercado por partido."""

from __future__ import annotations

import copy
import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.ratings.market_fifa_disagreement import (  # noqa: E402
    DISAGREEMENT_COLUMNS,
    build_match_disagreement_row,
)
from worldcup2026.ratings.staleness import assess_team_staleness, compute_pool_stats  # noqa: E402

TEAMS_JSON = ROOT / "teams_2026.json"
REPORT_CSV = ROOT / "outputs" / "ratings" / "elo_market_fifa_disagreement.csv"
REQUIRED = set(DISAGREEMENT_COLUMNS)


def _load():
    payload = json.loads(TEAMS_JSON.read_text(encoding="utf-8"))
    teams = payload.get("teams", payload)
    teams = teams if isinstance(teams, list) else list(teams.values())
    qualified = [t for t in teams if isinstance(t, dict) and t.get("status") == "qualified"]
    pool = [t for t in qualified if t.get("elo") and t.get("fifa_points")]
    stats = compute_pool_stats(pool)
    by_name = {t.get("name"): t for t in qualified}
    return by_name, stats


def _assess(name, by_name, stats):
    return assess_team_staleness(by_name[name], pool_stats=stats)


class TestDisagreementF22(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by_name, cls.stats = _load()

    def test_usapy_elo_fifa_market_contradiction_strong(self):
        a = _assess("United States", self.by_name, self.stats)
        b = _assess("Paraguay", self.by_name, self.stats)
        row = build_match_disagreement_row(
            match_id="M", team_a="United States", team_b="Paraguay",
            assess_a=a, assess_b=b, market_pick="home", model_pick="away",
            market_gap_status="calculado", final_market_decision="follow_market")
        self.assertEqual(row["elo_implied_winner"], "away")    # Elo favorece Paraguay
        self.assertEqual(row["fifa_implied_winner"], "home")   # FIFA favorece USA
        self.assertTrue(row["contradicts_market"])
        self.assertEqual(row["disagreement_severity"], "strong")

    def test_australia_turkey_disagreement_reported(self):
        a = _assess("Australia", self.by_name, self.stats)
        b = _assess("Turkey", self.by_name, self.stats)
        row = build_match_disagreement_row(
            match_id="M", team_a="Australia", team_b="Turkey",
            assess_a=a, assess_b=b, market_pick=None, market_gap_status=None)
        self.assertNotEqual(row["disagreement_severity"], "low")  # discrepancia relevante
        self.assertEqual(row["source_status"], "sin_mercado")
        self.assertGreater(float(row["staleness_b"]), float(row["staleness_a"]))  # Turquía más stale

    def test_no_market_does_not_invent_market_pick(self):
        a = _assess("Brazil", self.by_name, self.stats)
        b = _assess("Morocco", self.by_name, self.stats)
        row = build_match_disagreement_row(
            match_id="M", team_a="Brazil", team_b="Morocco",
            assess_a=a, assess_b=b, market_pick=None, market_gap_status=None)
        self.assertEqual(row["market_pick"], "")
        self.assertEqual(row["elo_vs_market_gap"], "sin_mercado")
        self.assertEqual(row["fifa_vs_market_gap"], "sin_mercado")
        self.assertEqual(row["source_status"], "sin_mercado")
        self.assertFalse(row["contradicts_market"])

    def test_missing_fifa_does_not_invent_fifa_gap(self):
        a = {"elo": 1800, "fifa_implied_elo": "", "elo_staleness_score": 0.0}  # sin FIFA
        b = _assess("Brazil", self.by_name, self.stats)
        row = build_match_disagreement_row(
            match_id="M", team_a="X", team_b="Brazil",
            assess_a=a, assess_b=b, market_pick="home", market_gap_status="calculado")
        self.assertEqual(row["fifa_implied_elo_a"], "")
        self.assertEqual(row["fifa_implied_elo_diff"], "")
        self.assertEqual(row["elo_vs_fifa_gap"], "")
        self.assertIn("sin FIFA", row["warnings"])

    def test_disagreement_csv_has_required_columns(self):
        a = _assess("Spain", self.by_name, self.stats)
        b = _assess("Argentina", self.by_name, self.stats)
        row = build_match_disagreement_row(match_id="M", team_a="Spain", team_b="Argentina",
                                           assess_a=a, assess_b=b)
        self.assertEqual(set(row.keys()), REQUIRED)
        if REPORT_CSV.exists():
            with REPORT_CSV.open(encoding="utf-8") as handle:
                header = set(next(csv.reader(handle)))
            self.assertTrue(REQUIRED.issubset(header))

    def test_report_does_not_change_predictions(self):
        # Función pura: no muta los assess de entrada y es idempotente.
        a = _assess("United States", self.by_name, self.stats)
        b = _assess("Paraguay", self.by_name, self.stats)
        a_before, b_before = copy.deepcopy(a), copy.deepcopy(b)
        r1 = build_match_disagreement_row(match_id="M", team_a="United States", team_b="Paraguay",
                                          assess_a=a, assess_b=b, market_pick="home",
                                          market_gap_status="calculado")
        r2 = build_match_disagreement_row(match_id="M", team_a="United States", team_b="Paraguay",
                                          assess_a=a, assess_b=b, market_pick="home",
                                          market_gap_status="calculado")
        self.assertEqual(r1, r2)            # idempotente
        self.assertEqual(a, a_before)       # no muta entradas
        self.assertEqual(b, b_before)


if __name__ == "__main__":
    unittest.main()
