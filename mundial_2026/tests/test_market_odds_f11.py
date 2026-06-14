"""Tests F1.1: ingesta manual de odds + conversión sin vig."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.market.devig import (  # noqa: E402
    MARKET_IMPLIED_COLUMNS,
    devig_proportional,
    devig_1x2,
    implied_prob,
    market_lambdas,
    market_implied_to_row,
    odds_to_implied,
    overround,
    two_way_no_vig,
)
from worldcup2026.market.odds_ingest import (  # noqa: E402
    OddsSnapshot,
    is_prematch,
    is_usable_for_decision,
    to_decimal_odds,
    validate_odds_snapshot,
)


def _snapshot(**overrides) -> OddsSnapshot:
    base = dict(
        match_id="20260612_A_vs_B",
        kickoff_utc="2026-06-12T19:00:00Z",
        captured_at_utc="2026-06-12T18:00:00Z",
        snapshot_type="t60",
        source="manual:test",
        odds_format="decimal",
        odds_home="1.91", odds_draw="3.50", odds_away="4.20",
        total_line=2.5, odds_over="1.95", odds_under="1.95",
        handicap_line=-0.5, odds_hcap_home="1.98", odds_hcap_away="1.92",
    )
    base.update(overrides)
    return OddsSnapshot(**base)


class TestConversion(unittest.TestCase):
    def test_decimal_odds_valid(self):
        self.assertAlmostEqual(to_decimal_odds("1.91", "decimal"), 1.91)
        self.assertAlmostEqual(to_decimal_odds("2.50", "decimal"), 2.50)

    def test_american_odds_positive_and_negative(self):
        self.assertAlmostEqual(to_decimal_odds("150", "american"), 2.50, places=6)
        self.assertAlmostEqual(to_decimal_odds("-200", "american"), 1.50, places=6)
        self.assertAlmostEqual(to_decimal_odds("-110", "american"), 1.0 + 100.0 / 110.0, places=6)

    def test_invalid_decimal_odds_rejected(self):
        self.assertIsNone(to_decimal_odds("1.0", "decimal"))   # <= 1
        self.assertIsNone(to_decimal_odds("0.95", "decimal"))
        self.assertIsNone(to_decimal_odds("abc", "decimal"))
        self.assertIsNone(to_decimal_odds("", "decimal"))
        with self.assertRaises(ValueError):
            to_decimal_odds("1.91", "klingon")  # formato desconocido


class TestDevig(unittest.TestCase):
    def test_devig_proportional_sums_to_one(self):
        implied = [implied_prob(1.91), implied_prob(3.50), implied_prob(4.20)]
        probs = devig_proportional(implied)
        self.assertAlmostEqual(sum(probs), 1.0, places=12)
        self.assertGreater(probs[0], probs[2])  # home favorito

    def test_overround_reported(self):
        implied = [implied_prob(1.91), implied_prob(3.50), implied_prob(4.20)]
        self.assertAlmostEqual(overround(implied), 0.047369733, places=6)
        _, _, _, over = devig_1x2(1.91, 3.50, 4.20)
        self.assertAlmostEqual(over, 0.047369733, places=6)

    def test_two_way_no_vig(self):
        p_over, p_under = two_way_no_vig(1.95, 1.95)
        self.assertAlmostEqual(p_over, 0.5, places=9)
        self.assertAlmostEqual(p_under, 0.5, places=9)
        p_o, p_u = two_way_no_vig(1.83, 2.00)
        self.assertAlmostEqual(p_o + p_u, 1.0, places=12)
        self.assertGreater(p_o, p_u)  # over más probable
        with self.assertRaises(ValueError):
            two_way_no_vig(1.95, 1.95, method="shin")

    def test_market_lambdas_from_total_and_supremacy(self):
        lam_home, lam_away = market_lambdas(2.674, 0.512)
        self.assertAlmostEqual(lam_home + lam_away, 2.674, places=9)
        self.assertAlmostEqual(lam_home - lam_away, 0.512, places=9)
        self.assertGreater(lam_home, lam_away)


class TestValidationAndOrchestration(unittest.TestCase):
    def test_captured_at_required(self):
        errors = validate_odds_snapshot(_snapshot(captured_at_utc=""))
        self.assertIn("captured_at_utc obligatorio", errors)

    def test_captured_before_kickoff(self):
        late = _snapshot(captured_at_utc="2026-06-12T19:30:00Z")  # tras kickoff
        self.assertFalse(is_prematch(late))
        self.assertIn("captured_at_utc debe ser anterior a kickoff_utc", validate_odds_snapshot(late))
        # Y no se convierte como prepartido.
        self.assertIsNone(odds_to_implied(late, require_prematch=True))

    def test_closing_odds_rejected_for_pre_match_decision(self):
        closing = _snapshot(snapshot_type="closing")  # capturado antes del kickoff
        self.assertTrue(is_prematch(closing))
        self.assertFalse(is_usable_for_decision(closing))  # closing no apto para decisión
        implied = odds_to_implied(closing, require_prematch=True)
        self.assertIsNotNone(implied)  # se puede convertir (auditoría/CLV)...
        self.assertTrue(any("closing" in w for w in implied.warnings))  # ...pero queda advertido

    def test_missing_market_returns_warning(self):
        # Solo over/under, sin 1X2.
        partial = _snapshot(odds_home=None, odds_draw=None, odds_away=None,
                            handicap_line=None, odds_hcap_home=None, odds_hcap_away=None)
        implied = odds_to_implied(partial)
        self.assertIsNotNone(implied)
        self.assertIsNone(implied.p_home)
        self.assertTrue(any("1X2 ausente" in w for w in implied.warnings))
        self.assertIsNotNone(implied.market_total_goals)  # OU sí presente
        # Sin ningún mercado -> None (no se inventa).
        empty = _snapshot(odds_home=None, odds_draw=None, odds_away=None,
                          total_line=None, odds_over=None, odds_under=None,
                          handicap_line=None, odds_hcap_home=None, odds_hcap_away=None)
        self.assertIsNone(odds_to_implied(empty))

    def test_odds_to_implied_outputs_expected_columns(self):
        implied = odds_to_implied(_snapshot())
        self.assertIsNotNone(implied)
        row = market_implied_to_row(implied)
        expected = {
            "match_id", "snapshot_type", "captured_at_utc", "source", "devig_method",
            "p_home", "p_draw", "p_away", "overround_1x2",
            "market_total_goals", "market_supremacy", "supremacy_source",
            "market_lambda_home", "market_lambda_away", "market_tt_home", "market_tt_away",
            "coverage_1x2", "coverage_ou", "coverage_handicap", "coverage_tt_home", "coverage_tt_away",
            "warnings",
        }
        self.assertEqual(set(row.keys()), set(MARKET_IMPLIED_COLUMNS))
        self.assertTrue(expected.issubset(set(row.keys())))
        # Coherencia: 1X2 sin vig suma 1 y lambdas decomponen total/supremacía.
        self.assertAlmostEqual(implied.p_home + implied.p_draw + implied.p_away, 1.0, places=9)
        self.assertAlmostEqual(
            implied.market_lambda_home + implied.market_lambda_away,
            implied.market_total_goals, places=6,
        )


if __name__ == "__main__":
    unittest.main()
