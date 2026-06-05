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
from worldcup2026.distributions import (
    build_model_stack,
    independent_score_distribution,
    ml_calibrated_score_distribution,
    overdispersed_score_distribution,
)
from worldcup2026.models.bayesian_dynamic import bayesian_dynamic_score_distribution
from worldcup2026.profiles.lineup import lineup_intelligence
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

    def test_explicit_value_style_load_and_geography_variables_move_expected_goals(self):
        teams = app.load_teams()
        opponent = teams["Saudi Arabia"]
        base = teams["Cape Verde"]
        boosted = dataclasses.replace(
            base,
            squad_market_value_eur_m=1450.0,
            top_league_minutes_share=0.95,
            gdp_ppp_usd_billion=3600.0,
            population_millions=72.0,
            league_strength_index=0.94,
            expected_threat=0.92,
            progressive_passes=0.90,
            progressive_carries=0.88,
            ppda=0.82,
            field_tilt=0.91,
            high_press_resistance=0.90,
            low_block_breaking=0.92,
            transition_defense=0.86,
            aerial_matchup_advantage=0.84,
            heat_humidity_load=0.02,
            time_zone_shift=0.0,
            venue_surface_adjustment=0.0,
            travel_cluster_difficulty=0.02,
        )
        ctx = app.MatchContext(neutral=True)

        mu_base, _ = app.expected_goals(base, opponent, ctx, state_a={}, state_b={})
        mu_boosted, _ = app.expected_goals(boosted, opponent, ctx, state_a={}, state_b={})

        self.assertGreater(mu_boosted, mu_base)

    def test_granular_penalty_variables_affect_shootout_edge(self):
        teams = app.load_teams()
        base_a = teams["Portugal"]
        base_b = teams["Netherlands"]
        stronger_penalty_side = dataclasses.replace(
            base_a,
            penalty_taker_quality=0.95,
            goalkeeper_penalty_save_rate=0.88,
            shootout_pressure_experience=0.93,
            keeper_taker_strategy_matchup=0.75,
        )
        weaker_penalty_side = dataclasses.replace(
            base_b,
            penalty_taker_quality=0.35,
            goalkeeper_penalty_save_rate=0.30,
            shootout_pressure_experience=0.38,
            keeper_taker_strategy_matchup=-0.55,
        )
        state = app.default_team_state()

        boosted_prob = app.penalties_probability(stronger_penalty_side, weaker_penalty_side, state, state)
        baseline_prob = app.penalties_probability(base_a, base_b, state, state)

        self.assertGreater(boosted_prob, baseline_prob)

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

    def test_live_score_recalculates_model_and_penca_markers(self):
        teams = app.load_teams()
        states = app.initial_team_states(teams)
        ctx = app.MatchContext(neutral=True)
        pre_match = app.predict_match(
            teams,
            "Spain",
            "Uruguay",
            ctx,
            top_scores=5,
            state_a=states["Spain"],
            state_b=states["Uruguay"],
        )
        live_match = app.predict_match_live(
            teams,
            "Spain",
            "Uruguay",
            ctx,
            0,
            1,
            "70'",
            top_scores=5,
            state_a=states["Spain"],
            state_b=states["Uruguay"],
            live_stats={
                "shots_a": 14,
                "shots_b": 6,
                "shots_on_target_a": 5,
                "shots_on_target_b": 2,
                "xg_a": 1.4,
                "xg_b": 0.7,
            },
        )

        self.assertNotEqual(app.projected_score_value(pre_match), app.projected_score_value(live_match))
        self.assertNotEqual(
            app.penca_ovacion_top_score(pre_match)["score"],
            app.penca_ovacion_top_score(live_match)["score"],
        )
        self.assertEqual(live_match.current_score_a, 0)
        self.assertEqual(live_match.current_score_b, 1)
        self.assertIsNotNone(live_match.expected_remaining_goals_a)

    def test_final_result_state_changes_future_score_probabilities(self):
        teams = app.load_teams()
        states = app.initial_team_states(teams)
        next_fixture = {"team_a": "Spain", "team_b": "Cape Verde", "stage": "group", "neutral": True, "group": "H"}
        next_ctx = app.context_from_fixture(next_fixture, teams, states)
        before = app.predict_match(
            teams,
            "Spain",
            "Cape Verde",
            next_ctx,
            top_scores=5,
            state_a=states["Spain"],
            state_b=states["Cape Verde"],
        )
        result_fixture = {
            "team_a": "Spain",
            "team_b": "Saudi Arabia",
            "stage": "group",
            "neutral": True,
            "group": "H",
            "actual_score_a": 6,
            "actual_score_b": 0,
            "actual_yellows_a": 0,
            "actual_yellows_b": 2,
            "live_xg_a": 3.4,
            "live_xg_b": 0.2,
        }
        result_ctx = app.context_from_fixture(result_fixture, teams, states)
        result_prediction = app.predict_match(
            teams,
            "Spain",
            "Saudi Arabia",
            result_ctx,
            top_scores=5,
            state_a=states["Spain"],
            state_b=states["Saudi Arabia"],
        )
        app.apply_state_updates(teams, states, result_fixture, result_ctx, result_prediction)
        after_ctx = app.context_from_fixture(next_fixture, teams, states)
        after = app.predict_match(
            teams,
            "Spain",
            "Cape Verde",
            after_ctx,
            top_scores=5,
            state_a=states["Spain"],
            state_b=states["Cape Verde"],
        )

        self.assertNotEqual(before.expected_goals_a, after.expected_goals_a)
        self.assertNotEqual(before.exact_scores[0][1], after.exact_scores[0][1])
        self.assertGreater(states["Spain"]["group_points"], 0)

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
        self.assertIn("ticket_snapshot_html", template)
        self.assertIn("Metodología", template)
        self.assertIn("Track record 2026", template)
        self.assertIn("technical-accordion", template)
        self.assertIn('id="marcadores"', template)
        self.assertIn('id="partidos"', template)
        self.assertIn("Modelo de apoyo para quiniela; no garantiza resultados.", template)
        self.assertIn("section-collapse", template)
        self.assertIn("Uso educativo y entretenimiento", template)
        self.assertIn("no garantiza ganar", template)
        self.assertIn("score_dynamics_html", template)
        self.assertIn("championship_penca_html", template)
        self.assertIn("methodology_governance_html", template)
        self.assertIn("dark_horses_html", template)
        self.assertIn("external_benchmarks_html", template)
        self.assertIn('href="#comparadores"', template)
        self.assertIn('href="#tapados"', template)
        self.assertIn("Campeonato", template)

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

    def test_external_benchmark_module_compares_published_models_without_blind_blend(self):
        bracket_payload = {
            "matches": {
                "M103": {
                    "advance_probabilities": {
                        "Spain": 0.44,
                        "France": 0.20,
                        "England": 0.16,
                        "Netherlands": 0.05,
                        "Argentina": 0.15,
                    }
                }
            }
        }
        entries = [{"projection": False, "status_state": "pre"} for _ in range(4)]
        comparison = app.external_forecast_comparison(bracket_payload, entries)
        self.assertEqual(comparison["leader"]["team"], "Spain")
        self.assertGreaterEqual(len(comparison["benchmarks"]), 7)
        self.assertGreaterEqual(comparison["agreement_count"], 3)
        html = app.build_external_forecast_benchmarks_html(bracket_payload, entries)
        self.assertIn('id="comparadores"', html)
        self.assertIn("Goldman Sachs GIR", html)
        self.assertIn("FairCast / University of Portsmouth", html)
        self.assertIn("Panmure Liberum / Joachim Klement", html)
        self.assertIn("Oddschecker / mercado público", html)
        self.assertIn("Covers / mercado de outrights", html)
        self.assertIn("No se promedian a ciegas", html)
        self.assertIn("Escenarios de estrés", html)
        self.assertIn("Bradley-Terry jerárquico dinámico", html)
        self.assertIn("Glicko/TrueSkill", html)
        self.assertIn("Skellam/ordinal", html)

    def test_dark_horse_module_derives_secondary_candidates_from_bracket_route(self):
        bracket_payload = {
            "matches": {
                "M89": {"advance_probabilities": {"Spain": 0.70, "Netherlands": 0.42, "Portugal": 0.32}},
                "M97": {"advance_probabilities": {"Spain": 0.58, "Netherlands": 0.22, "Portugal": 0.16}},
                "M101": {"advance_probabilities": {"Spain": 0.44, "Netherlands": 0.11, "Portugal": 0.08}},
                "M103": {"advance_probabilities": {"Spain": 0.36, "Netherlands": 0.07, "Portugal": 0.05}},
            }
        }
        candidates = app.dark_horse_candidates(bracket_payload, [])
        names = [candidate["team"] for candidate in candidates]
        self.assertIn("Netherlands", names)
        self.assertIn("Portugal", names)
        self.assertNotIn("Spain", names)
        netherlands = next(candidate for candidate in candidates if candidate["team"] == "Netherlands")
        self.assertGreater(netherlands["watch_index"], 0.0)
        self.assertAlmostEqual(netherlands["semifinal_prob"], 0.22)

    def test_dark_horse_html_is_transparent_about_external_signals(self):
        bracket_payload = {
            "matches": {
                "M89": {"advance_probabilities": {"Netherlands": 0.31}},
                "M97": {"advance_probabilities": {"Netherlands": 0.15}},
                "M101": {"advance_probabilities": {"Netherlands": 0.07}},
                "M103": {"advance_probabilities": {"Netherlands": 0.035}},
            }
        }
        html = app.build_dark_horses_html(bracket_payload, [])
        self.assertIn('id="tapados"', html)
        self.assertIn("Tapados con ruta realista", html)
        self.assertIn("La señal editorial solo activa vigilancia", html)
        self.assertIn("no reemplaza la llave base", html)
        self.assertIn("Netherlands", html)

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
        self.assertIn("ensemble_adjusted_points", options[0])
        self.assertIn("ensemble_score_index", options[0])
        self.assertIn("empirical_prior_index", options[0])
        self.assertIn("risk_adjusted_points", options[0])
        self.assertIn("realism_adjusted_points", options[0])
        self.assertIn("realism_index", options[0])
        self.assertIn("plausibility_index", options[0])
        self.assertIn("plausibility_note", options[0])
        self.assertIn("points_sd", options[0])
        portfolio = app.penca_score_portfolio(dist)
        self.assertIn("balanced", portfolio)
        self.assertIn("safe", portfolio)
        self.assertIn("upside", portfolio)

    def test_score_optimizer_does_not_follow_poisson_tail_blindly(self):
        dist = {
            (4, 0): 0.19,
            (2, 0): 0.17,
            (1, 0): 0.16,
            (3, 0): 0.10,
            (2, 1): 0.12,
            (1, 1): 0.12,
            (0, 0): 0.14,
        }
        options = app.penca_ovacion_score_options(dist, top_n=3)
        self.assertNotEqual(options[0]["score"], "4-0")
        self.assertEqual(options[0]["score"], "2-0")
        self.assertGreater(float(options[0].get("scoreline_calibration_index", 0.0)), 0.90)
        self.assertEqual(float(options[0].get("calibrated_promotion", 0.0)), 1.0)
        self.assertGreater(
            float(options[0]["ensemble_adjusted_points"]),
            float(app.score_expected_points_for_penca(dist, 4, 0)["ensemble_adjusted_points"]),
        )

    def test_score_optimizer_uses_match_scenario_not_only_poisson_mode(self):
        dist = {
            (2, 0): 0.23,
            (3, 0): 0.21,
            (4, 0): 0.14,
            (1, 0): 0.14,
            (5, 0): 0.05,
            (2, 1): 0.03,
            (0, 0): 0.06,
            (1, 1): 0.04,
            (3, 1): 0.03,
            (0, 1): 0.02,
            (4, 1): 0.02,
            (6, 0): 0.03,
        }
        options = app.penca_ovacion_score_options(dist, top_n=4)
        self.assertEqual(options[0]["score"], "3-0")
        self.assertEqual(options[0]["scoreline_scenario_family"], "favorito dominante")
        self.assertEqual(float(options[0].get("calibrated_promotion", 0.0)), 1.0)
        self.assertGreater(
            float(options[0]["scenario_ensemble_index"]),
            float(options[1]["scenario_ensemble_index"]),
        )
        self.assertGreater(float(options[1].get("poisson_modal_lock_penalty", 0.0)), 0.0)

    def test_score_optimizer_moves_narrow_clean_sheet_when_rival_can_score(self):
        dist = {
            (1, 0): 0.16,
            (2, 1): 0.10,
            (2, 0): 0.12,
            (1, 1): 0.12,
            (0, 0): 0.10,
            (0, 1): 0.07,
            (3, 1): 0.05,
            (3, 0): 0.04,
            (2, 2): 0.04,
            (3, 2): 0.02,
            (0, 2): 0.04,
            (1, 2): 0.05,
            (4, 2): 0.01,
            (4, 1): 0.01,
            (4, 0): 0.01,
            (2, 3): 0.02,
            (1, 3): 0.01,
            (3, 3): 0.01,
            (4, 3): 0.01,
            (5, 3): 0.01,
        }
        options = app.penca_ovacion_score_options(dist, top_n=4)
        self.assertEqual(options[0]["score"], "2-1")
        self.assertEqual(options[0]["scoreline_scenario_family"], "partido competitivo")
        self.assertEqual(float(options[0].get("calibrated_promotion", 0.0)), 1.0)
        one_nil = app.score_expected_points_for_penca(dist, 1, 0)
        self.assertGreater(float(one_nil.get("poisson_modal_lock_penalty", 0.0)), 0.0)

    def test_score_optimizer_tracks_popular_score_and_differential_value(self):
        dist = {
            (1, 0): 0.18,
            (2, 0): 0.18,
            (2, 1): 0.16,
            (3, 1): 0.13,
            (1, 1): 0.12,
            (0, 0): 0.08,
            (0, 1): 0.05,
            (1, 2): 0.04,
            (3, 0): 0.04,
            (2, 2): 0.02,
        }
        options = app.penca_ovacion_score_options(dist, top_n=5)
        self.assertIn("public_score_popularity_index", options[0])
        self.assertIn("differential_value_index", options[0])
        self.assertIn("competitive_adjusted_points", options[0])
        popular = app.score_expected_points_for_penca(dist, 2, 0)
        less_obvious = app.score_expected_points_for_penca(dist, 3, 1)
        self.assertGreater(float(popular["public_score_popularity_index"]), float(less_obvious["public_score_popularity_index"]))
        portfolio = app.penca_score_portfolio(dist)
        self.assertIn("differential", portfolio)
        self.assertIn("differential_value_index", portfolio["differential"])

    def test_tournament_scoreline_adjustment_feeds_simulation_without_rewriting_1x2(self):
        dist = {
            (1, 0): 0.16,
            (2, 1): 0.10,
            (2, 0): 0.12,
            (1, 1): 0.12,
            (0, 0): 0.10,
            (0, 1): 0.07,
            (3, 1): 0.05,
            (3, 0): 0.04,
            (2, 2): 0.04,
            (3, 2): 0.02,
            (0, 2): 0.04,
            (1, 2): 0.05,
            (4, 2): 0.01,
            (4, 1): 0.01,
            (4, 0): 0.01,
            (2, 3): 0.02,
            (1, 3): 0.01,
            (3, 3): 0.01,
            (4, 3): 0.01,
            (5, 3): 0.01,
        }
        adjusted, meta = app.apply_penca_tournament_scoreline_adjustment(
            dist,
            strength=0.25,
            outcome_drift_cap=0.012,
        )
        self.assertTrue(meta["applied"])
        self.assertGreater(adjusted[(2, 1)], dist[(2, 1)])
        self.assertLess(adjusted[(1, 0)], dist[(1, 0)])
        before = app.score_outcome_bucket_probabilities(dist)
        after = app.score_outcome_bucket_probabilities(adjusted)
        self.assertLessEqual(max(abs(after[key] - before[key]) for key in before), 0.013)

    def test_score_labels_include_team_names_for_away_style_scores(self):
        self.assertEqual(
            app.score_label_with_teams("Qatar", "Switzerland", "0-2"),
            "Qatar 0 - 2 Switzerland",
        )
        teams = app.load_teams()
        prediction = app.predict_match(teams, "Qatar", "Switzerland", app.MatchContext(neutral=True), top_scores=3)
        html = app.penca_ovacion_score_html(prediction)
        self.assertIn("Qatar", html)
        self.assertIn("Switzerland", html)
        self.assertIn("Filtro de plausibilidad", html)

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
        self.assertIn("single_exact_upper_bound", prediction.score_guidance)
        self.assertIn("coverage90_count", prediction.score_guidance)
        self.assertIn("coverage95_count", prediction.score_guidance)
        self.assertIn("score_shape_label", prediction.score_guidance)
        self.assertIn("penca_certainty_index", prediction.score_guidance)
        self.assertIn("safe_score", prediction.score_guidance)
        self.assertIn("upside_score", prediction.score_guidance)
        self.assertIn("score_portfolio", prediction.score_guidance)
        self.assertIn("recommended_public_score_popularity_index", prediction.score_guidance)
        self.assertIn("recommended_differential_value_index", prediction.score_guidance)
        self.assertIn("differential", prediction.score_guidance["score_portfolio"])

        entry = {
            "title": "Spain vs Saudi Arabia",
            "stage_label": "Grupo H",
            "prediction": prediction,
            "status_state": "pre",
        }
        profile = app.quiniela_certainty_profile(entry)
        self.assertIn("balanced_score", profile)
        self.assertIn("differential_score", profile)
        self.assertIsInstance(profile["balanced_score"], dict)

    def test_elite_knockout_match_keeps_upset_variance(self):
        teams = app.load_teams()
        prediction = app.predict_match(
            teams,
            "Spain",
            "France",
            app.MatchContext(neutral=True, knockout=True),
            include_advancement=True,
            top_scores=3,
        )
        self.assertIsNotNone(prediction.advance_a)
        self.assertLess(prediction.advance_a, 0.70)
        self.assertGreater(prediction.advance_b, 0.30)

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

    def test_team_specific_scoreline_families_distinguish_supported_goleada(self):
        teams = app.load_teams()
        profile = app.profile_for(teams["Spain"])
        history = profile.history
        supported_history = dataclasses.replace(
            history,
            scoreline_family_rates={
                **history.scoreline_family_rates,
                "clean_sheet_win_3_plus": 0.15,
                "total_4_plus": 0.34,
            },
        )
        unsupported_history = dataclasses.replace(
            history,
            scoreline_family_rates={
                **history.scoreline_family_rates,
                "clean_sheet_win_3_plus": 0.01,
                "total_4_plus": 0.14,
            },
        )
        supported = app.score_shape_team_signal(dataclasses.replace(profile, history=supported_history))
        unsupported = app.score_shape_team_signal(dataclasses.replace(profile, history=unsupported_history))

        self.assertGreater(supported["clean_sheet_win_3_plus"], unsupported["clean_sheet_win_3_plus"])
        self.assertGreater(supported["open_match"], unsupported["open_match"])

    def test_matchup_specific_history_does_not_promote_unsupported_three_nil(self):
        dist = {
            (2, 0): 0.25,
            (3, 0): 0.20,
            (1, 0): 0.15,
            (4, 0): 0.10,
            (2, 1): 0.08,
            (1, 1): 0.08,
            (0, 0): 0.06,
            (3, 1): 0.04,
            (0, 1): 0.02,
            (4, 1): 0.02,
        }
        supported_meta = {
            "favorite_is_a": True,
            "favorite_clean_sheet_win_3_plus_signal": 0.90,
            "rival_heavy_loss_signal": 0.80,
        }
        unsupported_meta = {
            "favorite_is_a": True,
            "favorite_clean_sheet_win_3_plus_signal": -0.90,
            "rival_heavy_loss_signal": -0.80,
        }

        supported = app.score_expected_points_for_penca(dist, 3, 0, supported_meta)
        unsupported = app.score_expected_points_for_penca(dist, 3, 0, unsupported_meta)
        self.assertGreater(float(supported["shape_boost"]), float(unsupported["shape_boost"]))
        self.assertGreater(
            float(supported["ensemble_adjusted_points"]),
            float(unsupported["ensemble_adjusted_points"]),
        )

    def test_matchup_family_index_uses_both_teams_for_exact_score(self):
        supported = {
            "scoreline_signal_a": {
                "clean_sheet_win_3_plus": 0.85,
                "clean_sheet_win_2": 0.40,
            },
            "scoreline_signal_b": {"heavy_loss": 0.75},
        }
        unsupported = {
            "scoreline_signal_a": {
                "clean_sheet_win_3_plus": -0.85,
                "clean_sheet_win_2": -0.40,
            },
            "scoreline_signal_b": {"heavy_loss": -0.75},
        }
        self.assertGreater(
            app.matchup_scoreline_family_index(3, 0, supported),
            app.matchup_scoreline_family_index(3, 0, unsupported),
        )
        self.assertGreater(
            app.matchup_scoreline_family_index(2, 0, supported),
            app.matchup_scoreline_family_index(2, 0, unsupported),
        )

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
        self.assertGreaterEqual(profile["coverage90"], 0.90)
        self.assertGreaterEqual(profile["coverage95"], 0.95)
        self.assertGreater(profile["coverage90_count"], 1)
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
        self.assertIn("marcador optimizado por ensamble", html)
        self.assertIn("Ensamble no solo Poisson", html)
        self.assertIn("Máximo realista exacto único", html)
        self.assertIn("Marcadores para cubrir 90%", html)
        self.assertIn("Guardrail exacto", html)
        self.assertIn("Horario del feed en EDT", html)
        self.assertIn("Qué dice cada modelo", html)
        self.assertIn("model-compare-collapse", html)
        self.assertIn("Overdispersión calibrada", html)
        self.assertIn("ML ligero regularizado", html)
        self.assertIn("Ajuste histórico del marcador", html)
        self.assertIn("Marcadores amplios o menos centrados a vigilar", html)
        self.assertIn("Modo seguro", html)
        self.assertIn("Modo diferencial", html)
        self.assertIn("Popularidad estimada del marcador", html)
        self.assertIn("Valor diferencial del marcador", html)
        self.assertIn("Qué cargar primero en Penca", html)
        self.assertIn("Modelo:", html)
        self.assertIn("Penca:", html)
        self.assertIn("Marcadores dinámicos", html)
        self.assertIn("Los marcadores cambian a medida que avanza el campeonato", html)
        self.assertIn("Modo campeonato", html)
        self.assertIn("No se promete 104/104 marcadores exactos", html)
        self.assertIn("Exactos realistas", html)
        self.assertIn("marcador que debo poner en Penca", html)
        self.assertIn('<section class="panel championship-penca-panel"', html)
        self.assertNotIn("&lt;section class=&#34;panel championship-penca-panel&#34;", html)
        self.assertIn("Escenario recomendado ahora", html)
        self.assertIn("marcador que debes poner en Penca", html)
        self.assertIn("Escenario a escoger", html)
        self.assertIn("Se recalcula cada 5 minutos", html)
        self.assertIn("Modo Penca competitivo", html)
        self.assertIn("Jugar seguro", html)
        self.assertIn("Jugar óptimo", html)
        self.assertIn("Jugar diferencial", html)
        self.assertIn('<section class="panel current-penca-panel"', html)
        self.assertNotIn("&lt;section class=&#34;panel current-penca-panel&#34;", html)
        self.assertIn('<section class="panel competitive-penca-panel">', html)
        self.assertNotIn("&lt;section class=&#34;panel competitive-penca-panel&#34;&gt;", html)
        self.assertIn("Last-pass contrast guardrail", html)
        self.assertIn(".competitive-penca-panel .summary-tile strong", html)
        self.assertIn("color: var(--accent-dark) !important", html)

    def test_championship_penca_optimizer_is_honest_and_dynamic(self):
        teams = app.load_teams()
        states = app.initial_team_states(teams)
        entries = app.dashboard_fixture_entries(
            [
                {
                    "team_a": "Spain",
                    "team_b": "Saudi Arabia",
                    "status_state": "pre",
                    "neutral": True,
                    "stage": "group",
                },
                {
                    "team_a": "Argentina",
                    "team_b": "Algeria",
                    "status_state": "in",
                    "live_score_a": 1,
                    "live_score_b": 0,
                    "status_detail": "54'",
                    "neutral": True,
                    "stage": "group",
                },
            ],
            teams,
            states,
            top_scores=3,
        )
        html = app.build_championship_penca_optimizer_html(entries)
        self.assertIn("La meta no es prometer 104/104", html)
        self.assertIn("Maximizar puntos", html)
        self.assertIn("Puntos esperados activos", html)
        self.assertIn("según el marcador que realmente se recomienda cargar ahora", html)
        self.assertIn("marcador que debo poner en Penca", html)
        self.assertIn("Los finales recalculan forma, tabla, llave y marcadores futuros", html)
        self.assertIn("in-play", html.lower())

        metrics = app.championship_penca_optimizer_metrics(entries)
        self.assertGreater(metrics["active_decision_total"], 0)
        self.assertGreater(metrics["scenario_expected_penca_points"], 0.0)
        self.assertGreater(metrics["scenario_expected_difference_scores"], 0.0)

    def test_penca_decision_switches_to_in_play_when_match_is_live(self):
        teams = app.load_teams()
        states = app.initial_team_states(teams)
        entries = app.dashboard_fixture_entries(
            [
                {
                    "team_a": "Spain",
                    "team_b": "Saudi Arabia",
                    "status_state": "in",
                    "status_detail": "45'",
                    "live_score_a": 1,
                    "live_score_b": 0,
                    "neutral": True,
                    "stage": "group",
                }
            ],
            teams,
            states,
            top_scores=3,
        )
        decision = app.penca_decision_profile(entries[0])
        self.assertEqual(decision["scenario"], "In-play real")
        self.assertIn("Spain", decision["score_to_enter_with_teams"])
        self.assertIn("Saudi Arabia", decision["score_to_enter_with_teams"])

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

    def test_live_summary_fetch_keeps_live_and_bounds_finished_matches(self):
        far_kickoff = datetime.now(timezone.utc) + timedelta(days=90)
        recent_final = datetime.now(timezone.utc) - timedelta(hours=6)
        stale_final = datetime.now(timezone.utc) - timedelta(days=7)
        self.assertTrue(sync.should_fetch_summary(far_kickoff, "live"))
        self.assertTrue(sync.should_fetch_summary(far_kickoff, "in"))
        self.assertTrue(sync.should_fetch_summary(recent_final, "final"))
        self.assertTrue(sync.should_fetch_summary(recent_final, "post"))
        self.assertFalse(sync.should_fetch_summary(stale_final, "final"))
        self.assertFalse(sync.should_fetch_summary(stale_final, "post"))

    def test_open_news_fetch_keeps_live_and_bounds_finished_matches(self):
        recent_final = datetime.now(timezone.utc) - timedelta(hours=6)
        stale_final = datetime.now(timezone.utc) - timedelta(days=7)
        self.assertTrue(sync.fixture_should_fetch_open_news({"status_state": "live"}))
        self.assertTrue(sync.fixture_should_fetch_open_news({"status_state": "in"}))
        self.assertTrue(
            sync.fixture_should_fetch_open_news(
                {"status_state": "final", "kickoff_utc": recent_final.isoformat()}
            )
        )
        self.assertFalse(
            sync.fixture_should_fetch_open_news(
                {"status_state": "post", "kickoff_utc": stale_final.isoformat()}
            )
        )

    def test_fast_refresh_preserves_previous_enrichment(self):
        fixtures = [
            {
                "id": "espn-1",
                "source": "espn_scoreboard",
                "team_a": "Mexico",
                "team_b": "South Africa",
                "market_provider": None,
                "news_headlines": [],
                "unavailable_players_a": [],
            }
        ]
        previous_by_id = {
            "espn-1": {
                "source": "espn_scoreboard+open_news",
                "market_provider": "DraftKings",
                "market_prob_a": 0.62,
                "news_headlines": ["Lineup watch: Mexico espera confirmar laterales"],
                "unavailable_players_a": ["Jugador A"],
                "open_news_provider": "gdelt",
            }
        }

        sync.preserve_previous_enrichment(fixtures, previous_by_id)

        fixture = fixtures[0]
        self.assertEqual(fixture["market_provider"], "DraftKings")
        self.assertEqual(fixture["market_prob_a"], 0.62)
        self.assertEqual(fixture["news_headlines"], ["Lineup watch: Mexico espera confirmar laterales"])
        self.assertEqual(fixture["unavailable_players_a"], ["Jugador A"])
        self.assertEqual(fixture["open_news_provider"], "gdelt")
        self.assertIn("open_news", fixture["source"])

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
        self.assertIn("Hoja de máxima firmeza", html)
        self.assertIn("Auditoría del boleto", html)
        self.assertIn("Brecha mínima contra la segunda opción", html)
        self.assertIn("Firmeza de picks base", html)
        self.assertIn("Firmeza con estrategia aplicada", html)
        self.assertIn("Firmeza si fuerzas pick único", html)
        self.assertIn("Checklist de auditoría", html)
        self.assertIn("Picks más defendibles", html)
        self.assertIn("Spain vs Uruguay", html)

    def test_model_quality_audit_html_does_not_fake_ten_out_of_ten(self):
        prediction = app.MatchPrediction(
            team_a="Spain",
            team_b="Uruguay",
            expected_goals_a=1.7,
            expected_goals_b=0.8,
            win_a=0.68,
            draw=0.20,
            win_b=0.12,
            exact_scores=[("2-0", 0.18), ("1-0", 0.15)],
            statistical_depth={"confidence_index": 0.78, "top3_coverage": 0.45, "model_agreement": 0.76},
        )
        html = app.build_model_quality_audit_html(
            [
                {
                    "title": "Spain vs Uruguay",
                    "stage_label": "Grupo H",
                    "prediction": prediction,
                    "status_state": "pre",
                }
            ],
            {"iterations": 15000},
            {"completed_matches": 0},
        )

        self.assertIn("Auditoría 10/10", html)
        self.assertIn("No se maquilla como 10/10", html)
        self.assertIn("no subimos una métrica a 90/95 o 10/10", html)
        self.assertIn("Histórico anti-fuga", html)

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
        self.assertGreater(audit["base_firmness_index"], audit["avg_certainty"])
        self.assertGreater(audit["strategy_adjusted_firmness"], audit["avg_certainty"])
        self.assertGreater(audit["base_avg_pick_prob"], 0.65)

    def test_structured_bracket_projection_uses_modal_matchup_not_exact_outcome(self):
        aggregate = {
            "outcomes": {
                ("Team A", "Team B", "Team A"): 50,
                ("Team A", "Team B", "Team B"): 35,
                ("Team C", "Team D", "Team C"): 35,
            },
            "winner": {"Team A": 50, "Team B": 35, "Team C": 35},
            "went_extra_time": 20,
            "went_penalties": 10,
            "penalty_scores": {(5, 4): 6, (4, 3): 4},
        }

        projection = app.structured_match_projection("M73", aggregate, 120)

        self.assertEqual((projection["team_a"], projection["team_b"]), ("Team A", "Team B"))
        self.assertEqual(projection["winner"], "Team A")
        self.assertAlmostEqual(projection["matchup_prob"], 85 / 120)
        self.assertAlmostEqual(projection["conditional_winner_prob"], 50 / 85)
        self.assertAlmostEqual(projection["winner_prob"], 50 / 120)

    def test_structured_bracket_projection_prefers_global_slot_winner(self):
        aggregate = {
            "outcomes": {
                ("Colombia", "Croatia", "Colombia"): 25,
                ("Colombia", "Croatia", "Croatia"): 20,
                ("Portugal", "Croatia", "Croatia"): 30,
                ("Portugal", "Japan", "Portugal"): 15,
            },
            "winner": {"Colombia": 25, "Croatia": 50, "Portugal": 15},
            "went_extra_time": 20,
            "went_penalties": 10,
            "penalty_scores": {(5, 4): 6, (4, 3): 4},
        }

        projection = app.structured_match_projection("M83", aggregate, 90)

        self.assertEqual((projection["team_a"], projection["team_b"]), ("Colombia", "Croatia"))
        self.assertEqual(projection["winner"], "Croatia")
        self.assertEqual(projection["matchup_favorite"], "Colombia")
        self.assertEqual(projection["slot_winner_mode"], "global_slot")
        self.assertAlmostEqual(projection["matchup_prob"], 45 / 90)
        self.assertAlmostEqual(projection["conditional_winner_prob"], 20 / 45)
        self.assertAlmostEqual(projection["winner_prob"], 50 / 90)

    def test_coherent_bracket_preserves_global_slot_probability(self):
        payload = {
            "matches": {
                "M81": {
                    "match_id": "M81",
                    "id": "M81",
                    "stage": "round32",
                    "team_a": "Turkey",
                    "team_b": "Iran",
                    "winner": "Turkey",
                    "winner_prob": 0.36,
                    "conditional_winner_prob": 0.92,
                },
                "M82": {
                    "match_id": "M82",
                    "id": "M82",
                    "stage": "round32",
                    "team_a": "Belgium",
                    "team_b": "Czech Republic",
                    "winner": "Belgium",
                    "winner_prob": 0.30,
                    "conditional_winner_prob": 0.79,
                },
                "M93": {
                    "match_id": "M93",
                    "id": "M93",
                    "stage": "round16",
                    "team_a": "Turkey",
                    "team_b": "Belgium",
                    "winner": "Belgium",
                    "winner_prob": 0.301,
                    "conditional_winner_prob": 0.480,
                    "advance_probabilities": {"Belgium": 0.301, "Turkey": 0.221},
                    "matchup_scenarios": [
                        {
                            "team_a": "Turkey",
                            "team_b": "Belgium",
                            "winner": "Turkey",
                            "matchup_prob": 0.186,
                            "conditional_winner_prob": 0.520,
                            "winner_prob": 0.096,
                            "conditional_winners": [
                                {"team": "Turkey", "conditional_prob": 0.520, "overall_prob": 0.096},
                                {"team": "Belgium", "conditional_prob": 0.480, "overall_prob": 0.089},
                            ],
                        }
                    ],
                },
            }
        }

        coherent = app.coherent_bracket_matches(payload)
        match = coherent["M93"]

        self.assertEqual(match["winner"], "Belgium")
        self.assertEqual(match["matchup_favorite"], "Turkey")
        self.assertEqual(match["slot_winner_mode"], "global_slot")
        self.assertAlmostEqual(match["conditional_winner_prob"], 0.480)
        self.assertAlmostEqual(match["winner_prob"], 0.301)

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

    def test_model_stack_includes_calibrated_overdispersion_layer(self):
        ctx = app.MatchContext(
            neutral=True,
            market_prob_a=0.52,
            market_prob_draw=0.25,
            market_prob_b=0.23,
        )
        dist, meta = build_model_stack(1.75, 0.95, ctx, max_goals=7, market_strength=0.30)

        self.assertIn("overdispersed", meta["weights"])
        self.assertIn("ml", meta["weights"])
        self.assertIn("bayesian", meta["weights"])
        self.assertEqual(meta["overdispersed_name"], "Overdispersión calibrada")
        self.assertEqual(meta["ml_name"], "ML ligero regularizado")
        self.assertEqual(meta["bayesian_name"], "Predictivo bayesiano dinámico")
        self.assertIn("outcome_temperature", meta)
        self.assertAlmostEqual(sum(meta["weights"].values()), 1.0, places=6)
        self.assertAlmostEqual(sum(dist.values()), 1.0, places=6)
        self.assertGreaterEqual(float(meta["outcome_temperature"]), 0.90)
        self.assertLessEqual(float(meta["outcome_temperature"]), 1.12)
        self.assertIn("ml_probs", meta)
        self.assertIn("ml_top_score", meta)
        self.assertIn("bayesian_probs", meta)
        self.assertIn("bayesian_top_score", meta)

    def test_bayesian_dynamic_distribution_is_normalized_and_not_poisson_copy(self):
        ctx = app.MatchContext(neutral=True, lineup_confirmed_a=True, lineup_coverage_a=0.9)
        bayesian = bayesian_dynamic_score_distribution(1.85, 0.88, ctx, max_goals=8)
        independent = independent_score_distribution(1.85, 0.88, max_goals=8)

        self.assertAlmostEqual(sum(bayesian.values()), 1.0, places=6)
        self.assertNotEqual(bayesian[(2, 0)], independent[(2, 0)])

    def test_lineup_intelligence_uses_conservative_fallback_without_nominal_roster(self):
        signal = lineup_intelligence(
            SimpleNamespace(players=()),
            starting_xi=["Player A", "Player B"],
            lineup_confirmed=True,
            lineup_changes=2,
            goalkeeper_change=True,
        )

        self.assertEqual(signal.mode, "XI recibido; roster nominal pendiente")
        self.assertLess(signal.overall_delta, 0.0)
        self.assertLessEqual(signal.coverage, 0.20)

    def test_lineup_intelligence_penalizes_weaker_confirmed_xi_with_nominal_roster(self):
        def player(name, position, quality):
            return SimpleNamespace(
                name=name,
                position=position,
                quality=quality,
                goalkeeping=quality if position == "GK" else 0.05,
                defense=quality,
                aerial=quality,
                creation=quality,
                attack=quality,
            )

        roster = [player("Goalkeeper One", "GK", 0.92), player("Goalkeeper Two", "GK", 0.55)]
        roster += [player(f"Defender {index}", "DF", 0.90 - index * 0.02) for index in range(1, 7)]
        roster += [player(f"Midfielder {index}", "MF", 0.91 - index * 0.02) for index in range(1, 6)]
        roster += [player(f"Forward {index}", "FW", 0.93 - index * 0.03) for index in range(1, 6)]
        weakened_xi = [
            "Goalkeeper Two",
            "Defender 1",
            "Defender 2",
            "Defender 5",
            "Defender 6",
            "Midfielder 1",
            "Midfielder 4",
            "Midfielder 5",
            "Forward 1",
            "Forward 4",
            "Forward 5",
        ]
        signal = lineup_intelligence(
            SimpleNamespace(players=tuple(roster)),
            starting_xi=weakened_xi,
            lineup_confirmed=True,
        )

        self.assertEqual(signal.mode, "XI ponderado jugador por jugador")
        self.assertGreaterEqual(signal.coverage, 0.95)
        self.assertLess(signal.overall_delta, 0.0)

    def test_ml_calibrated_distribution_is_normalized_and_visible(self):
        ctx = app.MatchContext(neutral=True, knockout=True, market_total_line=2.4)
        dist = ml_calibrated_score_distribution(1.85, 1.10, ctx, max_goals=8)
        self.assertAlmostEqual(sum(dist.values()), 1.0, places=6)
        self.assertGreater(len(dist), 0)
        self.assertGreater(max(dist.values()), 0.0)

    def test_overdispersed_distribution_keeps_more_high_goal_tail(self):
        ctx = app.MatchContext(neutral=True)
        base = independent_score_distribution(1.7, 1.2, max_goals=7)
        over = overdispersed_score_distribution(1.7, 1.2, ctx, max_goals=7)
        base_tail = sum(prob for (goals_a, goals_b), prob in base.items() if goals_a + goals_b >= 5)
        over_tail = sum(prob for (goals_a, goals_b), prob in over.items() if goals_a + goals_b >= 5)

        self.assertGreater(over_tail, base_tail)

    def test_annotate_market_moves_computes_prob_deltas(self):
        fixtures = [{"id": "10", "market_prob_a": 0.52, "market_prob_draw": 0.24, "market_prob_b": 0.24}]
        previous = {"10": {"market_prob_a": 0.48, "market_prob_draw": 0.26, "market_prob_b": 0.26}}
        sync.annotate_market_moves(fixtures, previous)
        self.assertAlmostEqual(fixtures[0]["market_move_a"], 0.04, places=4)
        self.assertAlmostEqual(fixtures[0]["market_move_draw"], -0.02, places=4)
        self.assertAlmostEqual(fixtures[0]["market_move_b"], -0.02, places=4)

    def test_summarize_market_accepts_nested_espn_draw_odds(self):
        market = sync.summarize_market(
            {
                "provider": {"name": "ESPN BET"},
                "homeTeamOdds": {"moneyLine": -110},
                "drawOdds": {"moneyLine": 240},
                "awayTeamOdds": {"moneyLine": 285},
                "overUnder": 2.5,
            }
        )

        self.assertEqual(market["market_moneyline_draw"], 240.0)
        self.assertAlmostEqual(
            market["market_prob_a"] + market["market_prob_draw"] + market["market_prob_b"],
            1.0,
            places=6,
        )

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

    def test_methodology_governance_surfaces_validation_protocols_without_fake_metrics(self):
        html = app.build_methodology_governance_html(
            entries=[],
            bracket_payload={"iterations": 15000},
            backtest={"completed_matches": 0},
        )
        self.assertIn("Auditoría metodológica profunda", html)
        self.assertIn("Backtesting serio", html)
        self.assertIn("Ablation tests", html)
        self.assertIn("Benchmarks base", html)
        self.assertIn("Stress testing", html)
        self.assertIn("Intervalos de incertidumbre", html)
        self.assertIn("Validación rolling / temporal", html)
        self.assertIn("no se está maquillando una métrica", html)


if __name__ == "__main__":
    unittest.main()
