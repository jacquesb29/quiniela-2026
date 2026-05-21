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
from worldcup2026.dashboard.html_builder import render_dashboard_html
from worldcup2026.live.adjustment import live_game_state_adjustment, live_stats_adjustment
from worldcup2026.simulation.match import sample_knockout_resolution, simulate_match_sample
from worldcup2026.types import KnockoutResolution


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class RegressionLogicTest(unittest.TestCase):
    def test_live_adjustment_becomes_more_extreme_late_when_team_leads(self):
        early_a, early_b = live_game_state_adjustment(1.20, 1.00, 1, 0, 0.20, "regulation", clamp=clamp)
        late_a, late_b = live_game_state_adjustment(1.20, 1.00, 1, 0, 0.90, "regulation", clamp=clamp)
        self.assertLess(late_a, early_a)
        self.assertGreater(late_b, early_b)

    def test_iso_timestamp_is_utc_aware_for_dashboard_consistency(self):
        self.assertTrue(app.iso_timestamp().endswith("+00:00"))

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

    def test_simulated_knockout_match_preserves_penalty_scores_for_bracket_audit(self):
        teams = {
            "Spain": SimpleNamespace(name="Spain"),
            "Portugal": SimpleNamespace(name="Portugal"),
        }
        states = {"Spain": {}, "Portugal": {}}
        result = simulate_match_sample(
            teams,
            states,
            "Spain",
            "Portugal",
            "round16",
            build_simulation_context_fn=lambda *args, **kwargs: SimpleNamespace(importance=1.0),
            ensure_state=lambda states, team: states[team],
            cached_simulation_expected_goals=lambda *args, **kwargs: (1.1, 1.0),
            simulation_state_signature=lambda state: (),
            sample_score=lambda *args, **kwargs: (1, 1),
            sample_cards_fn=lambda *args, **kwargs: (0, 0, 0, 0),
            sample_knockout_resolution_fn=lambda *args, **kwargs: {
                "winner": "Spain",
                "loser": "Portugal",
                "score_a": 1,
                "score_b": 1,
                "went_extra_time": True,
                "went_penalties": True,
                "penalty_score_a": 5,
                "penalty_score_b": 4,
            },
            update_simulation_state_fn=lambda *args, **kwargs: None,
        )

        self.assertTrue(result["went_penalties"])
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
        self.assertIn("In-play limitado", html)

    def test_provider_diagnostics_separate_prepared_from_configured(self):
        entries = [{"projection": False, "source": "espn_scoreboard", "status_state": "pre"}]
        with mock.patch.dict("os.environ", {}, clear=True):
            diagnostics = app.provider_runtime_diagnostics(entries)
            self.assertEqual(diagnostics["configured_wired"], [])
            self.assertEqual(diagnostics["deep_sources"], [])
            provider_html = app.build_provider_matrix_html(entries)
            self.assertIn("Automático sin cuentas", provider_html)
            self.assertIn("sin eventos tiro-a-tiro en este corte", provider_html)
            self.assertIn("API_FOOTBALL_KEY | credencial opcional no configurada", provider_html)
            self.assertIn("sin key | automático sin key", provider_html)
            stack = app.provider_stack_summary(entries)
            self.assertEqual(stack["configured"], [])

    def test_provider_panel_surfaces_open_news_adapter_when_used(self):
        entries = [
            {
                "projection": False,
                "source": "espn_scoreboard+open_news",
                "open_news_provider": "gdelt",
                "status_state": "pre",
            }
        ]
        provider_html = app.build_provider_matrix_html(entries)
        self.assertIn("Noticias abiertas usadas", provider_html)
        self.assertIn("gdelt", provider_html)
        self.assertIn("espn_scoreboard+open_news", provider_html)

    def test_dashboard_template_separates_ticket_mode_from_technical_manual(self):
        template = (
            PACKAGE_ROOT
            / "worldcup2026"
            / "dashboard"
            / "templates"
            / "base.html"
        ).read_text(encoding="utf-8")
        self.assertIn("Modo boleto", template)
        self.assertIn("Si vas a cargar la Penca Ovación, empieza aquí.", template)
        self.assertIn("Lectura crítica", template)
        self.assertIn("Track record 2026", template)
        self.assertIn("technical-accordion", template)
        self.assertIn('id="marcadores"', template)
        self.assertIn('id="partidos"', template)
        self.assertIn("Modelo de apoyo para quiniela; no garantiza resultados.", template)
        self.assertIn("section-collapse", template)
        self.assertIn("Uso educativo y entretenimiento", template)
        self.assertIn("no garantiza ganar", template)

    def test_pages_build_records_dashboard_timestamp_in_latest_json(self):
        script = (PACKAGE_ROOT / "build_pages_site.sh").read_text(encoding="utf-8")
        self.assertIn("dashboard_updated_at_utc", script)
        self.assertIn("timestamp_consistency_note", script)
        self.assertIn('meta name="dashboard-updated-at"', script)

    def test_dashboard_renderer_does_not_escape_inline_css(self):
        html = render_dashboard_html({"updated_at": "test"})
        self.assertIn(".technical-accordion > summary", html)
        self.assertIn('content: "Abrir"', html)
        self.assertNotIn(".technical-accordion &gt; summary", html)

    def test_consensus_guardrail_explains_external_consensus_is_defined(self):
        bracket_payload = {"matches": {"M103": {"advance_probabilities": {"Spain": 0.60, "France": 0.40}}}}
        entries = [{"projection": False, "status_state": "pre"} for _ in range(4)]
        html = app.build_consensus_guardrail_html(bracket_payload, entries)
        self.assertIn("consenso externo definido", html)
        self.assertIn("No es una caja negra", html)
        self.assertIn("Transparencia de fuentes", html)

    def test_provider_diagnostics_detect_configured_api_football_key(self):
        entries = [{"projection": False, "source": "espn_scoreboard", "status_state": "pre"}]
        with mock.patch.dict("os.environ", {"API_FOOTBALL_KEY": "dummy"}, clear=True):
            diagnostics = app.provider_runtime_diagnostics(entries)
            self.assertIn("API-Football / API-SPORTS", diagnostics["configured_wired"])
            provider_html = app.build_provider_matrix_html(entries)
            self.assertIn("API_FOOTBALL_KEY | key configurada", provider_html)
            self.assertIn("API-Football / API-SPORTS", app.provider_stack_summary(entries)["configured"])

    def test_penca_ovacion_score_optimizer_uses_expected_points_not_only_exact_prob(self):
        dist = {
            (1, 0): 0.20,
            (2, 0): 0.18,
            (3, 1): 0.18,
            (0, 0): 0.12,
            (1, 1): 0.12,
            (0, 1): 0.20,
        }
        options = app.penca_ovacion_score_options(dist, top_n=3)
        self.assertEqual(options[0]["score"], "2-0")
        self.assertGreater(options[0]["expected_points"], app.score_expected_points_for_penca(dist, 1, 0)["expected_points"])
        self.assertAlmostEqual(float(options[0]["difference_prob"]), 0.36)
        self.assertIn("risk_adjusted_points", options[0])
        self.assertIn("points_sd", options[0])
        portfolio = app.penca_score_portfolio(dist)
        self.assertIn("balanced", portfolio)
        self.assertIn("safe", portfolio)
        self.assertIn("upside", portfolio)

    def test_predict_match_exposes_penca_ovacion_recommended_score(self):
        teams = app.load_teams()
        prediction = app.predict_match(teams, "Spain", "Saudi Arabia", app.MatchContext(neutral=True), top_scores=3)
        self.assertTrue(prediction.penca_scores)
        top = app.penca_ovacion_top_score(prediction)
        self.assertIn("score", top)
        self.assertGreaterEqual(float(top["expected_points"]), 0.0)
        self.assertTrue(prediction.score_guidance)
        self.assertIn("goal_options_a", prediction.score_guidance)
        self.assertIn("top5_coverage", prediction.score_guidance)
        self.assertIn("score_shape_label", prediction.score_guidance)
        self.assertIn("penca_certainty_index", prediction.score_guidance)
        self.assertIn("safe_score", prediction.score_guidance)
        self.assertIn("upside_score", prediction.score_guidance)

    def test_historical_score_shape_adjustment_preserves_result_probabilities(self):
        teams = app.load_teams()
        team_a = teams["Spain"]
        team_b = teams["Saudi Arabia"]
        dist = {
            (1, 0): 0.18,
            (2, 0): 0.20,
            (3, 0): 0.15,
            (3, 1): 0.10,
            (1, 1): 0.16,
            (0, 0): 0.09,
            (0, 1): 0.07,
            (1, 2): 0.05,
        }
        adjusted, meta = app.apply_historical_score_shape_adjustment(
            dist,
            team_a,
            team_b,
            app.profile_for(team_a),
            app.profile_for(team_b),
            2.45,
            0.65,
            app.MatchContext(neutral=True),
            strength=0.75,
        )

        for outcome in ("a", "draw", "b"):
            before = sum(prob for score, prob in dist.items() if app.score_shape_outcome(*score) == outcome)
            after = sum(prob for score, prob in adjusted.items() if app.score_shape_outcome(*score) == outcome)
            self.assertAlmostEqual(after, before, places=8)
        self.assertAlmostEqual(sum(adjusted.values()), 1.0, places=8)
        self.assertTrue(meta["applied"])

    def test_score_shape_weight_boosts_supported_asymmetric_scores(self):
        strong_attack = {
            "attack": 0.8,
            "defense": 0.5,
            "concede": -0.4,
            "clean_sheet": 0.6,
            "scoring_rate": 0.8,
            "high_goal": 0.7,
            "strength": 0.6,
        }
        fragile_defense = {
            "attack": 0.1,
            "defense": -0.2,
            "concede": 0.5,
            "clean_sheet": -0.3,
            "scoring_rate": 0.1,
            "high_goal": 0.0,
            "strength": -0.2,
        }
        central_weight = app.score_shape_weight(1, 0, 2.55, 0.65, strong_attack, fragile_defense, app.MatchContext(neutral=True))
        asymmetric_weight = app.score_shape_weight(3, 0, 2.55, 0.65, strong_attack, fragile_defense, app.MatchContext(neutral=True))
        self.assertGreater(asymmetric_weight, central_weight)

    def test_score_precision_profile_exposes_goal_marginals_and_exact_pick(self):
        dist = {
            (1, 0): 0.20,
            (2, 0): 0.18,
            (2, 1): 0.12,
            (0, 0): 0.10,
            (1, 1): 0.15,
            (0, 1): 0.12,
            (3, 1): 0.13,
        }
        profile = app.score_precision_profile(dist, app.penca_ovacion_score_options(dist, top_n=5))
        self.assertEqual(profile["top_exact_score"], "1-0")
        self.assertGreater(profile["top5_coverage"], profile["top3_coverage"])
        self.assertEqual(profile["goal_options_a"][0]["goals"], 1)
        self.assertEqual(profile["goal_options_b"][0]["goals"], 1)
        self.assertTrue(profile["asymmetric_score_options"])

    def test_full_scorecard_lists_match_score_to_enter(self):
        teams = app.load_teams()
        prediction = app.predict_match(teams, "Spain", "Saudi Arabia", app.MatchContext(neutral=True), top_scores=3)
        html = app.build_full_scorecard_html(
            [
                {
                    "title": "Spain vs Saudi Arabia",
                    "stage_label": "Grupo H",
                    "prediction": prediction,
                    "status_state": "pre",
                }
            ]
        )
        self.assertIn("Marcadores para cargar en Penca", html)
        self.assertIn("Marcador para cargar en Penca", html)
        self.assertIn("Más probable del modelo", html)
        self.assertIn("partidos de fase de grupos auditados", html)
        self.assertIn("Spain", html)
        self.assertIn("Saudi Arabia", html)

    def test_cards_make_model_score_and_penca_score_explicit(self):
        teams = app.load_teams()
        states = app.initial_team_states(teams)
        entries = app.dashboard_fixture_entries(
            [
                {
                    "team_a": "Spain",
                    "team_b": "Saudi Arabia",
                    "status_detail": "Thu, June 11th at 3:00 PM EDT",
                    "neutral": True,
                    "stage": "group",
                }
            ],
            teams,
            states,
            top_scores=3,
        )
        html = app.build_dashboard_html(entries, "", {}, {"completed_matches": 0}, Path("state.json"), Path("fixtures.json"))
        self.assertIn("Marcador más probable del modelo", html)
        self.assertIn("Marcador recomendado Penca Ovación", html)
        self.assertIn("Horario del feed en EDT", html)
        self.assertIn("Qué dice cada modelo", html)
        self.assertIn("model-compare-collapse", html)
        self.assertIn("Ajuste histórico del marcador", html)
        self.assertIn("Marcadores amplios o menos centrados a vigilar", html)
        self.assertIn("Modo seguro", html)
        self.assertIn("Modo agresivo", html)

    def test_consensus_champion_blend_decays_with_live_and_final_results(self):
        pending = [{"projection": False, "status_state": "pre"} for _ in range(4)]
        live = [{"projection": False, "status_state": "in"} for _ in range(4)]
        final = [{"projection": False, "status_state": "post"} for _ in range(4)]
        pending_blend = app.consensus_champion_blend(pending)
        live_blend = app.consensus_champion_blend(live)
        final_blend = app.consensus_champion_blend(final)
        self.assertAlmostEqual(pending_blend, app.CONSENSUS_CHAMPION_BLEND)
        self.assertLess(live_blend, pending_blend)
        self.assertLess(final_blend, live_blend)
        self.assertGreaterEqual(final_blend, app.CONSENSUS_CHAMPION_MIN_BLEND)

    def test_consensus_adjusted_champion_table_moves_toward_model_after_results(self):
        bracket_payload = {"matches": {"M103": {"advance_probabilities": {"Spain": 0.70, "France": 0.30}}}}
        pending_entries = [{"projection": False, "status_state": "pre"} for _ in range(8)]
        final_entries = [{"projection": False, "status_state": "post"} for _ in range(8)]
        pending_rows = app.consensus_adjusted_champion_probabilities(bracket_payload, pending_entries)
        final_rows = app.consensus_adjusted_champion_probabilities(bracket_payload, final_entries)
        pending_spain = next(row for row in pending_rows if row["team"] == "Spain")
        final_spain = next(row for row in final_rows if row["team"] == "Spain")
        self.assertGreater(float(final_spain["adjusted_prob"]), float(pending_spain["adjusted_prob"]))
        self.assertGreater(float(final_spain["model_blend"]), float(pending_spain["model_blend"]))

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
        self.assertEqual(profile["tier"], "Pick base claro")
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
        self.assertIn("Auditoría del boleto", html)
        self.assertIn("Brecha mínima contra la segunda opción", html)
        self.assertIn("Checklist de auditoría", html)
        self.assertIn("Picks más defendibles", html)
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

    def test_structured_bracket_projection_uses_modal_matchup_not_exact_outcome(self):
        aggregate = {
            "outcomes": {
                ("Team A", "Team B", "Team A"): 40,
                ("Team A", "Team B", "Team B"): 35,
                ("Team C", "Team D", "Team C"): 45,
            },
            "winner": {"Team A": 40, "Team B": 35, "Team C": 45},
            "went_extra_time": 20,
            "went_penalties": 10,
            "penalty_scores": {(5, 4): 6, (4, 3): 4},
        }

        projection = app.structured_match_projection("M73", aggregate, 120)

        self.assertEqual((projection["team_a"], projection["team_b"]), ("Team A", "Team B"))
        self.assertEqual(projection["winner"], "Team A")
        self.assertAlmostEqual(projection["matchup_prob"], 75 / 120)
        self.assertAlmostEqual(projection["conditional_winner_prob"], 40 / 75)
        self.assertAlmostEqual(projection["winner_prob"], 40 / 120)

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

    def test_goal_consensus_line_accepts_serious_forecast_aliases(self):
        self.assertAlmostEqual(app.goal_consensus_total_line({"consensus_total_goals": 2.35}), 2.35)
        self.assertAlmostEqual(app.goal_consensus_total_line({"bookmaker_total_line": "2.5"}), 2.5)
        self.assertIsNone(app.goal_consensus_total_line({"market_total_line": "sin dato"}))

    def test_market_total_line_shrinks_goal_total_when_model_is_far(self):
        teams = app.load_teams()
        states = app.initial_team_states(teams)
        base_ctx = app.MatchContext(neutral=True, knockout=False, importance=1.0)
        low_total_ctx = dataclasses.replace(base_ctx, market_total_line=1.50)
        base_prediction = app.predict_match(
            teams,
            "Spain",
            "Uruguay",
            base_ctx,
            top_scores=3,
            state_a=states["Spain"],
            state_b=states["Uruguay"],
        )
        adjusted_prediction = app.predict_match(
            teams,
            "Spain",
            "Uruguay",
            low_total_ctx,
            top_scores=3,
            state_a=states["Spain"],
            state_b=states["Uruguay"],
        )
        base_total = base_prediction.expected_goals_a + base_prediction.expected_goals_b
        adjusted_total = adjusted_prediction.expected_goals_a + adjusted_prediction.expected_goals_b
        self.assertLess(adjusted_total, base_total)
        self.assertIn("aplicado", adjusted_prediction.statistical_depth["goal_consensus_status"])
        self.assertIn("Pronóstico de goles", app.goal_forecast_html({"goal_consensus_source": "mercado"}, adjusted_prediction))

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

    def test_brier_activates_with_first_final_result(self):
        teams = app.load_teams()
        backtest = app.compute_backtest_summary(
            [
                {
                    "id": "first-final",
                    "team_a": "Spain",
                    "team_b": "Uruguay",
                    "stage": "group",
                    "neutral": True,
                    "kickoff_utc": "2026-06-15T00:00:00Z",
                    "actual_score_a": 2,
                    "actual_score_b": 1,
                    "update_state": True,
                }
            ],
            teams,
            top_scores=3,
        )
        self.assertEqual(backtest["completed_matches"], 1)
        self.assertEqual(backtest["regular_time_samples"], 1)
        self.assertIsNotNone(backtest["brier_result"])
        self.assertIsNotNone(backtest["brier_reliability"])
        self.assertIsNotNone(backtest["temporal_cv_brier"])
        html = app.build_calibration_depth_html([], backtest)
        self.assertIn("Brier 2026 activo", html)
        self.assertIn("Arranca con el primer partido finalizado", html)

    def test_backtesting_empty_state_says_brier_starts_on_first_final(self):
        html = app.build_backtesting_html({"completed_matches": 0})
        self.assertIn("desde el primer partido terminado", html)
        self.assertIn("Brier", html)


if __name__ == "__main__":
    unittest.main()
