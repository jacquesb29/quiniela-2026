"""Tests F1.5: flujo T-60 y materialización (apply_market_to_context)."""

from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import modelo_quiniela_2026 as model  # noqa: E402
from market_context_adapter import apply_market_to_context  # noqa: E402
from worldcup2026.market.odds_ingest import OddsSnapshot  # noqa: E402
from worldcup2026.market.t60 import (  # noqa: E402
    T60_DECISION_COLUMNS,
    T60Inputs,
    run_t60_for_match,
    t60_change_to_row,
)

T60_CSV = ROOT / "outputs" / "market" / "t60_decision_log.csv"

REQUIRED_COLUMNS = {
    "match_id", "pick_before", "pick_after", "changed", "confidence_before",
    "confidence_after", "trigger", "reason", "captured_at_utc", "odds_snapshot_type",
    "lineup_confirmed", "lineup_changes", "injuries_confirmed", "starting_gk", "gk_changed",
}


def _odds(snapshot_type="t60", home="1.50", draw="4.00", away="7.00", complete_1x2=True):
    return OddsSnapshot(
        match_id="M", kickoff_utc="2026-06-12T19:00:00Z",
        captured_at_utc="2026-06-12T18:00:00Z", snapshot_type=snapshot_type,
        source="test", odds_format="decimal",
        odds_home=home if complete_1x2 else None,
        odds_draw=draw if complete_1x2 else None,
        odds_away=away if complete_1x2 else None,
        total_line=2.5, odds_over="1.95", odds_under="1.95",
        handicap_line=-0.5, odds_hcap_home="1.95", odds_hcap_away="1.95",
    )


def _inputs(odds, *, lineup_changes=0, injuries=(), gk_changed=False):
    return T60Inputs(
        match_id="M", captured_at_utc="2026-06-12T18:05:00Z", odds=odds,
        lineup_confirmed=True, lineup_changes=lineup_changes, injuries_confirmed=injuries,
        starting_gk="GK", gk_changed=gk_changed, notes="",
    )


def _model(pa, pd, pb):
    return {"prob_a": pa, "prob_draw": pd, "prob_b": pb, "lambda_a": 1.6, "lambda_b": 1.0}


class TestT60(unittest.TestCase):
    def test_t60_no_valid_odds_keeps_pick(self):
        change = run_t60_for_match(
            match_id="M", model_pred=_model(0.6, 0.25, 0.15),
            t60_inputs=_inputs(None), prior_pick="home", prior_confidence="Media")
        self.assertFalse(change.changed)
        self.assertEqual(change.pick_after, "home")
        self.assertIn("sin odds", change.reason.lower())

    def test_t60_rejects_closing_odds_for_decision(self):
        change = run_t60_for_match(
            match_id="M", model_pred=_model(0.6, 0.25, 0.15),
            t60_inputs=_inputs(_odds(snapshot_type="closing")),
            prior_pick="home", prior_confidence="Media")
        self.assertFalse(change.changed)
        self.assertEqual(change.pick_after, "home")  # closing no decide

    def test_t60_does_not_change_without_material_reason(self):
        # Modelo y mercado favorecen home (gap bajo), pero el prior era 'away':
        # el pick cambiaría a home, pero sin razón material -> se suprime.
        change = run_t60_for_match(
            match_id="M", model_pred=_model(0.62, 0.24, 0.14),
            t60_inputs=_inputs(_odds(home="1.50", draw="4.00", away="7.00")),
            prior_pick="away", prior_confidence="Media")
        self.assertFalse(change.changed)
        self.assertEqual(change.pick_after, "away")
        self.assertIn("material", change.reason.lower())

    def test_t60_changes_when_market_contradiction_strong(self):
        # Modelo favorece home; mercado favorece away -> contradicción -> follow_market.
        change = run_t60_for_match(
            match_id="M", model_pred=_model(0.60, 0.25, 0.15),
            t60_inputs=_inputs(_odds(home="4.00", draw="3.60", away="1.70")),
            prior_pick="home", prior_confidence="Media")
        self.assertTrue(change.changed)
        self.assertEqual(change.pick_after, "away")
        self.assertEqual(change.confidence_after, "Baja")
        self.assertEqual(change.trigger, "market_contradiction")

    def test_t60_logs_before_after(self):
        change = run_t60_for_match(
            match_id="M", model_pred=_model(0.60, 0.25, 0.15),
            t60_inputs=_inputs(_odds(home="4.00", draw="3.60", away="1.70")),
            prior_pick="home", prior_confidence="Media")
        self.assertEqual(change.pick_before, "home")
        self.assertEqual(change.pick_after, "away")
        self.assertNotEqual(change.pick_before, change.pick_after)

    def test_t60_reason_required_when_changed(self):
        change = run_t60_for_match(
            match_id="M", model_pred=_model(0.60, 0.25, 0.15),
            t60_inputs=_inputs(_odds(home="4.00", draw="3.60", away="1.70")),
            prior_pick="home", prior_confidence="Media")
        self.assertTrue(change.changed)
        self.assertTrue(change.reason.strip())

    def test_t60_decision_log_has_required_columns(self):
        change = run_t60_for_match(
            match_id="M", model_pred=_model(0.6, 0.25, 0.15),
            t60_inputs=_inputs(_odds()), prior_pick="home", prior_confidence="Media")
        row = t60_change_to_row(change)
        self.assertEqual(set(row.keys()), set(T60_DECISION_COLUMNS))
        self.assertTrue(REQUIRED_COLUMNS.issubset(set(row.keys())))
        if T60_CSV.exists():
            with T60_CSV.open(encoding="utf-8") as handle:
                header = set(next(csv.reader(handle)))
            self.assertTrue(REQUIRED_COLUMNS.issubset(header))


class TestApplyMarketToContext(unittest.TestCase):
    def test_apply_market_to_context_fills_only_market_fields(self):
        ctx = model.MatchContext(neutral=False, rest_days_a=6, knockout=True)
        implied = {"p_home": 0.5, "p_draw": 0.3, "p_away": 0.2, "market_total_goals": 2.6}
        new_ctx = apply_market_to_context(ctx, implied)
        # Campos de mercado poblados.
        self.assertAlmostEqual(new_ctx.market_prob_a, 0.5)
        self.assertAlmostEqual(new_ctx.market_prob_draw, 0.3)
        self.assertAlmostEqual(new_ctx.market_prob_b, 0.2)
        self.assertAlmostEqual(new_ctx.market_total_line, 2.6)
        # Campos no-mercado intactos.
        self.assertFalse(new_ctx.neutral)
        self.assertEqual(new_ctx.rest_days_a, 6)
        self.assertTrue(new_ctx.knockout)

    def test_apply_market_to_context_does_not_mutate_original_context(self):
        ctx = model.MatchContext(neutral=True)
        self.assertIsNone(ctx.market_prob_a)
        implied = {"p_home": 0.5, "p_draw": 0.3, "p_away": 0.2, "market_total_goals": 2.6}
        new_ctx = apply_market_to_context(ctx, implied)
        # El contexto original no se muta (dataclass frozen + replace).
        self.assertIsNone(ctx.market_prob_a)
        self.assertIsNotNone(new_ctx.market_prob_a)
        self.assertIsNot(ctx, new_ctx)


if __name__ == "__main__":
    unittest.main()
