from __future__ import annotations

import dataclasses
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import modelo_quiniela_2026 as app
import sync_live_data_2026 as sync
from worldcup2026.live.adjustment import live_game_state_adjustment, live_stats_adjustment
from worldcup2026.simulation.match import sample_knockout_resolution
from worldcup2026.types import KnockoutResolution


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class RegressionLogicTest(unittest.TestCase):
    def test_live_adjustment_becomes_more_extreme_late_when_team_leads(self):
        early_a, early_b = live_game_state_adjustment(1.20, 1.00, 1, 0, 0.20, "regulation", clamp=clamp)
        late_a, late_b = live_game_state_adjustment(1.20, 1.00, 1, 0, 0.90, "regulation", clamp=clamp)
        self.assertLess(late_a, early_a)
        self.assertGreater(late_b, early_b)

    def test_live_stats_adjustment_rewards_team_with_stronger_live_signals(self):
        mu_a, mu_b = live_stats_adjustment(
            2.20,
            1.05,
            1.05,
            0.72,
            "regulation",
            live_stats={
                "xg_a": 1.8,
                "xg_b": 0.2,
                "shots_a": 14,
                "shots_b": 4,
                "shots_on_target_a": 7,
                "shots_on_target_b": 1,
                "possession_a": 66,
                "possession_b": 34,
                "corners_a": 6,
                "corners_b": 1,
                "red_cards_a": 0,
                "red_cards_b": 1,
            },
            clamp=clamp,
        )
        self.assertGreater(mu_a, 1.05)
        self.assertLess(mu_b, 1.05)

    def test_knockout_resolution_with_penalties_keeps_scores_consistent(self):
        team_a = SimpleNamespace(name="Spain")
        team_b = SimpleNamespace(name="Portugal")
        ctx = SimpleNamespace(morale_a=0.05, morale_b=-0.03)
        result = sample_knockout_resolution(
            team_a,
            team_b,
            ctx,
            1,
            1,
            1.10,
            0.95,
            state_a={},
            state_b={},
            asdict=dataclasses.asdict,
            KnockoutResolution=KnockoutResolution,
            extra_time_expected_goals=lambda mu_a, mu_b, state_a=None, state_b=None: (0.22, 0.18),
            sample_score=lambda mu_a, mu_b, ctx=None: (0, 0),
            simulate_penalty_shootout=lambda *args, **kwargs: {
                "winner": "Spain",
                "score_a": 5,
                "score_b": 4,
            },
            penalties_context_state=lambda morale, state: dict(state or {}, morale=morale),
            fast_random=lambda: 0.4,
        )
        self.assertTrue(result["went_extra_time"])
        self.assertTrue(result["went_penalties"])
        self.assertEqual(result["winner"], "Spain")
        self.assertEqual(result["loser"], "Portugal")
        self.assertEqual(result["penalty_score_a"], 5)
        self.assertEqual(result["penalty_score_b"], 4)

    def test_seeded_score_sampling_is_reproducible(self):
        app.seed_all_rng(77)
        sequence_one = [app.sample_score(1.35, 0.88) for _ in range(12)]
        app.seed_all_rng(77)
        sequence_two = [app.sample_score(1.35, 0.88) for _ in range(12)]
        self.assertEqual(sequence_one, sequence_two)

    def test_provider_fallback_returns_empty_index_when_deep_feed_is_disabled(self):
        with mock.patch.object(sync, "API_FOOTBALL_KEY", ""):
            self.assertFalse(sync.provider_enabled())
            self.assertEqual(sync.fetch_provider_live_index({}), {})

    def test_dashboard_live_mode_accepts_live_status_synonym(self):
        teams = app.load_teams()
        states = app.initial_team_states(teams)
        entries = app.dashboard_fixture_entries(
            [
                {
                    "team_a": "Spain",
                    "team_b": "Uruguay",
                    "status_state": "live",
                    "status_detail": "45'",
                    "live_score_a": 1,
                    "live_score_b": 0,
                    "neutral": True,
                    "stage": "group",
                }
            ],
            teams,
            states,
            top_scores=0,
        )
        prediction = entries[0]["prediction"]
        self.assertEqual(prediction.current_score_a, 1)
        self.assertEqual(prediction.current_score_b, 0)

    def test_runtime_status_counts_provider_status_variants(self):
        html = app.build_runtime_status_html(
            [
                {"projection": False, "status_state": "in"},
                {"projection": False, "status_state": "post"},
                {"projection": False, "status_state": "pre"},
            ],
            {"iterations": 15000},
        )
        self.assertIn("<strong>1</strong> en vivo", html)
        self.assertIn("<strong>1</strong> finales", html)
        self.assertIn("<strong>1</strong> pendientes", html)

    def test_live_summary_fetch_accepts_live_and_final_synonyms(self):
        far_kickoff = datetime.now(timezone.utc) + timedelta(days=90)
        self.assertTrue(sync.should_fetch_summary(far_kickoff, "live"))
        self.assertTrue(sync.should_fetch_summary(far_kickoff, "final"))
        self.assertTrue(sync.should_fetch_summary(far_kickoff, "in"))
        self.assertTrue(sync.should_fetch_summary(far_kickoff, "post"))

    def test_quiniela_certainty_profile_prefers_clear_favorite(self):
        prediction = app.MatchPrediction(
            team_a="Spain",
            team_b="Uruguay",
            expected_goals_a=1.7,
            expected_goals_b=0.8,
            win_a=0.68,
            draw=0.20,
            win_b=0.12,
            exact_scores=[("2-0", 0.18), ("1-0", 0.16), ("2-1", 0.11)],
            statistical_depth={
                "confidence_index": 0.78,
                "top3_coverage": 0.45,
                "model_agreement": 0.76,
            },
        )
        profile = app.quiniela_certainty_profile(
            {
                "title": "Spain vs Uruguay",
                "stage_label": "Grupo H",
                "prediction": prediction,
                "status_state": "pre",
            }
        )
        self.assertEqual(profile["pick_code"], "1")
        self.assertEqual(profile["tier"], "Firme")
        self.assertGreater(profile["certainty_score"], 0.65)

    def test_max_certainty_html_renders_pick_sheet(self):
        prediction = app.MatchPrediction(
            team_a="Spain",
            team_b="Uruguay",
            expected_goals_a=1.7,
            expected_goals_b=0.8,
            win_a=0.68,
            draw=0.20,
            win_b=0.12,
            exact_scores=[("2-0", 0.18), ("1-0", 0.16), ("2-1", 0.11)],
            statistical_depth={"confidence_index": 0.78, "top3_coverage": 0.45, "model_agreement": 0.76},
        )
        html = app.build_max_certainty_html(
            [
                {
                    "title": "Spain vs Uruguay",
                    "stage_label": "Grupo H",
                    "prediction": prediction,
                    "status_state": "pre",
                }
            ]
        )
        self.assertIn("Hoja de máxima certeza", html)
        self.assertIn("Auditoria del boleto", html)
        self.assertIn("Brecha minima contra la segunda opcion", html)
        self.assertIn("Checklist de auditoria", html)
        self.assertIn("Picks mas defendibles", html)
        self.assertIn("Spain vs Uruguay", html)

    def test_quiniela_audit_metrics_flags_traps_and_fragile_scores(self):
        firm_prediction = app.MatchPrediction(
            team_a="Spain",
            team_b="Uruguay",
            expected_goals_a=1.8,
            expected_goals_b=0.7,
            win_a=0.70,
            draw=0.18,
            win_b=0.12,
            exact_scores=[("2-0", 0.18), ("1-0", 0.15)],
            statistical_depth={"confidence_index": 0.80, "top3_coverage": 0.46, "model_agreement": 0.78},
        )
        trap_prediction = app.MatchPrediction(
            team_a="Turkey",
            team_b="Belgium",
            expected_goals_a=1.1,
            expected_goals_b=1.0,
            win_a=0.34,
            draw=0.33,
            win_b=0.33,
            exact_scores=[("1-1", 0.13), ("1-0", 0.10)],
            statistical_depth={"confidence_index": 0.50, "top3_coverage": 0.34, "model_agreement": 0.54},
        )
        profiles = [
            app.quiniela_certainty_profile({"title": "Spain vs Uruguay", "prediction": firm_prediction, "status_state": "pre"}),
            app.quiniela_certainty_profile({"title": "Turkey vs Belgium", "prediction": trap_prediction, "status_state": "pre"}),
        ]
        audit = app.quiniela_audit_metrics(profiles)

        self.assertEqual(audit["total"], 2)
        self.assertEqual(audit["firm_or_preferent"], 1)
        self.assertGreaterEqual(audit["traps"] + audit["high_variance"], 1)
        self.assertEqual(audit["defensible_scores"], 1)
        self.assertLess(audit["min_gap"], 0.10)

    def test_update_simulation_state_tracks_recent_xg_signals(self):
        teams = app.load_teams()
        states = app.initial_team_states(teams)
        ctx = app.MatchContext(neutral=True, knockout=False, importance=1.0)
        app.update_simulation_state(
            teams,
            states,
            "Spain",
            "Uruguay",
            ctx,
            expected_goals_a=1.35,
            expected_goals_b=0.92,
            score_a=2,
            score_b=0,
            yellows_a=1,
            reds_a=0,
            yellows_b=2,
            reds_b=0,
            stage="group",
            live_stats={"xg_a": 1.9, "xg_b": 0.35},
        )
        spain = states["Spain"]
        self.assertGreater(spain["recent_xg_for_adj"], 0.0)
        self.assertLess(spain["recent_xga_adj"], 0.0)
        self.assertNotEqual(spain["recent_opponent_strength"], 0.0)

    def test_annotate_market_moves_computes_prob_deltas(self):
        fixtures = [{"id": "10", "market_prob_a": 0.52, "market_prob_draw": 0.24, "market_prob_b": 0.24}]
        previous = {"10": {"market_prob_a": 0.48, "market_prob_draw": 0.26, "market_prob_b": 0.26}}
        sync.annotate_market_moves(fixtures, previous)
        self.assertAlmostEqual(fixtures[0]["market_move_a"], 0.04, places=4)
        self.assertAlmostEqual(fixtures[0]["market_move_draw"], -0.02, places=4)
        self.assertAlmostEqual(fixtures[0]["market_move_b"], -0.02, places=4)

    def test_annotate_referee_profiles_uses_previous_samples(self):
        previous = {
            "1": {
                "id": "1",
                "referee": "Ref A",
                "actual_yellows_a": 4,
                "actual_yellows_b": 3,
                "actual_reds_a": 1,
                "actual_reds_b": 0,
                "live_shot_log_a": [{"detail": "Penalty goal"}],
                "live_shot_log_b": [],
            },
            "2": {
                "id": "2",
                "referee": "Ref B",
                "actual_yellows_a": 1,
                "actual_yellows_b": 1,
                "actual_reds_a": 0,
                "actual_reds_b": 0,
                "live_shot_log_a": [],
                "live_shot_log_b": [],
            },
        }
        fixtures = [{"id": "3", "referee": "Ref A"}]
        sync.annotate_referee_profiles(fixtures, previous)
        self.assertEqual(fixtures[0]["referee_sample_matches"], 1)
        self.assertGreater(fixtures[0]["referee_yellow_bias"], 0.0)
        self.assertGreater(fixtures[0]["referee_red_bias"], 0.0)


if __name__ == "__main__":
    unittest.main()
