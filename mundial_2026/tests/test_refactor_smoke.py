from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from worldcup2026.cli import build_parser
from worldcup2026.live.adjustment import live_game_state_adjustment
from worldcup2026.live.patterns import detect_live_play_patterns
from worldcup2026.data.loader import load_tournament_config, read_fixtures
from worldcup2026.dashboard.comparison import compare_entry_predictions as compare_dashboard_entry_predictions
from worldcup2026.dashboard.html_builder import render_dashboard_html
import modelo_quiniela_2026 as app


class RefactorSmokeTest(unittest.TestCase):
    def test_cli_parser_accepts_project_bracket(self):
        parser = build_parser(
            state_file="state.json",
            tournament_config_file="config.json",
            bracket_file="bracket.md",
            bracket_json_file="bracket.json",
            dashboard_html_file="dashboard.html",
            dashboard_md_file="dashboard.md",
            fixtures_template_file="fixtures.json",
        )
        args = parser.parse_args(["project-bracket"])
        self.assertEqual(args.command, "project-bracket")
        self.assertEqual(args.iterations, app.MIN_MONTE_CARLO_ITERATIONS)

    def test_cli_parser_defaults_all_tournament_monte_carlo_to_15000(self):
        parser = build_parser(
            state_file="state.json",
            tournament_config_file="config.json",
            bracket_file="bracket.md",
            bracket_json_file="bracket.json",
            dashboard_html_file="dashboard.html",
            dashboard_md_file="dashboard.md",
            fixtures_template_file="fixtures.json",
        )
        for command in ("project-bracket", "simulate-tournament", "playoffs"):
            args = parser.parse_args([command])
            self.assertEqual(args.iterations, 15000)

    def test_monte_carlo_guard_rejects_less_than_15000(self):
        with self.assertRaises(SystemExit):
            app.ensure_minimum_monte_carlo_iterations(14999, label="test")
        app.ensure_minimum_monte_carlo_iterations(15000, label="test")

    def test_cli_parser_accepts_audit_quiniela(self):
        parser = build_parser(
            state_file="state.json",
            tournament_config_file="config.json",
            bracket_file="bracket.md",
            bracket_json_file="bracket.json",
            dashboard_html_file="dashboard.html",
            dashboard_md_file="dashboard.md",
            fixtures_template_file="fixtures.json",
        )
        args = parser.parse_args(["audit-quiniela", "--min-iterations", "15000"])
        self.assertEqual(args.command, "audit-quiniela")
        self.assertEqual(args.min_iterations, 15000)

    def test_live_adjustment_boosts_trailing_team_late(self):
        mu_a, mu_b = live_game_state_adjustment(1.0, 1.0, 1, 0, 0.9, "regulation", clamp=lambda v, lo, hi: max(lo, min(hi, v)))
        self.assertLess(mu_a, 1.0)
        self.assertGreater(mu_b, 1.0)

    def test_live_patterns_detect_signal(self):
        patterns = detect_live_play_patterns(
            {
                "shots_a": 12,
                "shots_b": 3,
                "shots_on_target_a": 6,
                "shots_on_target_b": 1,
                "possession_a": 64,
                "possession_b": 36,
                "corners_a": 6,
                "corners_b": 1,
                "xg_a": 1.4,
                "xg_b": 0.2,
            },
            0.6,
            "regulation",
            1,
            0,
            clamp=lambda v, lo, hi: max(lo, min(hi, v)),
        )
        self.assertIsNotNone(patterns)
        self.assertIn("tempo_label", patterns)
        self.assertIn("summary", patterns["a"])

    def test_loader_roundtrip_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            fixtures_path = Path(tmpdir) / "fixtures.json"
            config_path.write_text('{"groups": {"A": ["Spain", "Uruguay"]}}')
            fixtures_path.write_text('[{"team_a": "Spain", "team_b": "Uruguay"}]')
            self.assertIn("groups", load_tournament_config(config_path))
            self.assertEqual(read_fixtures(fixtures_path)[0]["team_a"], "Spain")

    def test_methodology_mentions_15000_iterations(self):
        html = app.build_methodology_html({"iterations": 15000}, {"completed_matches": 0})
        self.assertIn("15.000 iteraciones", html)
        self.assertIn("Semáforo metodológico", html)
        self.assertIn("Control de calidad del pronóstico", html)
        self.assertIn("15.000 simulaciones", html)

    def test_runtime_status_panel_mentions_provider_and_simulations(self):
        html = app.build_runtime_status_html(
            [
                {
                    "projection": False,
                    "status_state": "live",
                    "live_feed_provider": "api_football",
                    "source": "espn_scoreboard",
                },
                {
                    "projection": False,
                    "status_state": "final",
                    "live_feed_provider": None,
                    "source": "espn_scoreboard",
                },
                {
                    "projection": True,
                    "status_state": "pre",
                    "live_feed_provider": None,
                    "source": "bracket_projection",
                },
            ],
            {"iterations": 15000},
        )
        self.assertIn("15.000 simulaciones", html)
        self.assertIn("api_football", html)
        self.assertIn("1</strong> en vivo", html)
        self.assertIn("3</strong> partidos del Mundial modelados", html)
        self.assertIn("2</strong> con fixture/live directo", html)
        self.assertIn("1</strong> cruces eliminatorios proyectados", html)

    def test_landing_proof_explains_operational_robustness(self):
        html = app.build_landing_proof_html(
            [
                {"projection": False, "status_state": "pre", "market_total_line": 2.5},
                {"projection": True, "status_state": "pre"},
            ],
            {
                "iterations": 15000,
                "matches": {
                    "final": {
                        "winner": "Spain",
                        "winner_prob": 0.3,
                    }
                },
            },
            {"completed_matches": 0},
        )
        self.assertIn("Prueba operacional", html)
        self.assertIn("15.000 simulaciones", html)
        self.assertIn("No fuerza una falsa certeza", html)
        self.assertIn("Modela 2 partidos: 1 fixtures directos y 1 cruces de llave proyectados", html)

    def test_dashboard_renderer_keeps_max_certainty_html_unescaped(self):
        html = render_dashboard_html(
            {
                "updated_at": "2026-05-15T00:00:00",
                "state_path": "state.json",
                "fixtures_path": "fixtures.json",
                "landing_proof_html": "<section class=\"landing-proof\"><h2>Prueba operacional</h2></section>",
                "runtime_status_html": "",
                "methodology_html": "",
                "calibration_depth_html": "<section class=\"calibration-panel\"><h2>Cómo evitamos que el modelo se sobreconfíe</h2></section>",
                "prediction_power_html": "<section class=\"power-panel\"><h2>Probabilidad pura vs convicción</h2></section>",
                "agentic_learning_html": "<section class=\"agentic-panel\"><h2>Agentes de aprendizaje</h2><p>Noticias multi-fuente</p></section>",
                "provider_matrix_html": "<section class=\"provider-panel\"><h2>No depender solo de ESPN</h2><p>Sportmonks</p></section>",
                "global_confidence_html": "",
                "max_certainty_html": "<section class=\"certainty-panel\"><h2>Hoja de máxima certeza</h2></section>",
                "strategy_html": "<section class=\"strategy-panel\"><h2>Estrategia para ganar la quiniela</h2><p>Ventaja vs boleto popular</p><p>Diferenciales positivos</p><p>Cobertura recomendada</p><p>Marcador exacto principal</p></section>",
                "full_scorecard_html": "<section class=\"scorecard-panel\"><h2>Marcadores para cargar en Penca</h2></section>",
                "recent_changes_html": "",
                "backtesting_html": "",
                "bracket_visual_html": "",
                "bracket_html": "",
                "cards_html": "",
            }
        )
        self.assertIn("Quiniela Intelligence 2026", html)
        self.assertIn("Una sala de decisión", html)
        self.assertIn("De datos a boleto", html)
        self.assertIn("Primero decide como una mesa profesional", html)
        self.assertIn("Monte Carlo vigente", html)
        self.assertIn("15.000 simulaciones por corrida", html)
        self.assertIn("Partidos totales del Mundial 2026", html)
        self.assertIn("El formato completo tiene 104 partidos", html)
        self.assertIn("No son 72 en total: 72 es solo la fase de grupos.", html)
        self.assertNotIn("Partidos modelados: 72 de fase de grupos", html)
        self.assertIn('<section class="landing-proof">', html)
        self.assertIn('<section class="calibration-panel">', html)
        self.assertIn('<section class="power-panel">', html)
        self.assertIn('<section class="agentic-panel">', html)
        self.assertIn('<section class="provider-panel">', html)
        self.assertIn('<section class="certainty-panel">', html)
        self.assertIn('<section class="strategy-panel">', html)
        self.assertIn("Estrategia para ganar la quiniela", html)
        self.assertNotIn("&lt;section class=&quot;certainty-panel&quot;&gt;", html)

    def test_recent_change_comparison_does_not_mix_changed_matchups_as_pick_moves(self):
        previous_entries = [
            {
                "match_id": "M96",
                "title": "Dieciseisavos 16: Turkey vs Iran",
                "team_a": "Turkey",
                "team_b": "Iran",
                "prediction": {"label": "Victoria Turkey", "prob": 0.615, "score": "2-0"},
            }
        ]
        current_entries = [
            {
                "match_id": "M96",
                "title": "Dieciseisavos 16: Paraguay vs Iran",
                "team_a": "Paraguay",
                "team_b": "Iran",
                "prediction": {"label": "Victoria Paraguay", "prob": 0.459, "score": "1-1"},
            }
        ]
        changes = compare_dashboard_entry_predictions(
            current_entries,
            previous_entries,
            dashboard_entry_key=lambda entry: entry["match_id"],
            pick_summary=lambda prediction: (prediction["label"], prediction["prob"]),
            projected_score_value=lambda prediction: prediction["score"],
        )
        self.assertEqual(changes["movers"], [])
        self.assertEqual(changes["score_changes"], [])
        self.assertEqual(changes["label_changes"], [])
        self.assertEqual(changes["matchup_changes"][0]["previous_matchup"], "Turkey vs Iran")
        self.assertEqual(changes["matchup_changes"][0]["current_matchup"], "Paraguay vs Iran")

    def test_bracket_visual_keeps_branch_coherent(self):
        payload = {
            "iterations": 15000,
            "updated_at": "2026-05-17T15:43:15",
            "matches": {
                "M81": {
                    "match_id": "M81",
                    "title": "Dieciseisavos 9",
                    "stage": "round32",
                    "team_a": "Turkey",
                    "team_b": "Bosnia and Herzegovina",
                    "winner": "Turkey",
                    "matchup_prob": 0.14,
                    "winner_prob": 0.43,
                    "top_scenarios": [],
                    "matchup_scenarios": [],
                },
                "M82": {
                    "match_id": "M82",
                    "title": "Dieciseisavos 10",
                    "stage": "round32",
                    "team_a": "Belgium",
                    "team_b": "Czech Republic",
                    "winner": "Belgium",
                    "matchup_prob": 0.15,
                    "winner_prob": 0.58,
                    "top_scenarios": [],
                    "matchup_scenarios": [],
                },
                "M83": {
                    "match_id": "M83",
                    "title": "Dieciseisavos 11",
                    "stage": "round32",
                    "team_a": "Croatia",
                    "team_b": "Colombia",
                    "winner": "Croatia",
                    "matchup_prob": 0.16,
                    "winner_prob": 0.52,
                    "top_scenarios": [],
                    "matchup_scenarios": [],
                },
                "M84": {
                    "match_id": "M84",
                    "title": "Dieciseisavos 12",
                    "stage": "round32",
                    "team_a": "Spain",
                    "team_b": "Austria",
                    "winner": "Spain",
                    "matchup_prob": 0.48,
                    "winner_prob": 0.73,
                    "top_scenarios": [],
                    "matchup_scenarios": [],
                },
                "M93": {
                    "match_id": "M93",
                    "title": "Octavos 5",
                    "stage": "round16",
                    "team_a": "Turkey",
                    "team_b": "Belgium",
                    "winner": "Belgium",
                    "matchup_prob": 0.12,
                    "winner_prob": 0.50,
                    "top_scenarios": [],
                    "matchup_scenarios": [
                        {
                            "team_a": "Turkey",
                            "team_b": "Belgium",
                            "winner": "Turkey",
                            "matchup_prob": 0.28,
                            "conditional_winner_prob": 0.58,
                            "winner_prob": 0.16,
                            "conditional_winners": [
                                {"team": "Turkey", "conditional_prob": 0.58, "overall_prob": 0.16},
                                {"team": "Belgium", "conditional_prob": 0.42, "overall_prob": 0.12},
                            ],
                        },
                    ],
                },
                "M94": {
                    "match_id": "M94",
                    "title": "Octavos 6",
                    "stage": "round16",
                    "team_a": "Croatia",
                    "team_b": "Spain",
                    "winner": "Spain",
                    "matchup_prob": 0.22,
                    "winner_prob": 0.73,
                    "top_scenarios": [],
                    "matchup_scenarios": [
                        {
                            "team_a": "Croatia",
                            "team_b": "Spain",
                            "winner": "Spain",
                            "matchup_prob": 0.22,
                            "conditional_winner_prob": 0.83,
                            "winner_prob": 0.18,
                            "conditional_winners": [
                                {"team": "Spain", "conditional_prob": 0.83, "overall_prob": 0.18},
                                {"team": "Croatia", "conditional_prob": 0.17, "overall_prob": 0.04},
                            ],
                        },
                    ],
                },
                "M99": {
                    "match_id": "M99",
                    "title": "Cuartos 3",
                    "stage": "quarterfinal",
                    "team_a": "Belgium",
                    "team_b": "Spain",
                    "winner": "Spain",
                    "matchup_prob": 0.24,
                    "winner_prob": 0.69,
                    "top_scenarios": [],
                    "matchup_scenarios": [
                        {
                            "team_a": "Belgium",
                            "team_b": "Spain",
                            "winner": "Spain",
                            "matchup_prob": 0.24,
                            "conditional_winner_prob": 0.89,
                            "winner_prob": 0.22,
                            "conditional_winners": [
                                {"team": "Spain", "conditional_prob": 0.89, "overall_prob": 0.22},
                                {"team": "Belgium", "conditional_prob": 0.11, "overall_prob": 0.03},
                            ],
                        },
                        {
                            "team_a": "Turkey",
                            "team_b": "Spain",
                            "winner": "Spain",
                            "matchup_prob": 0.16,
                            "conditional_winner_prob": 0.98,
                            "winner_prob": 0.15,
                            "conditional_winners": [
                                {"team": "Spain", "conditional_prob": 0.98, "overall_prob": 0.15},
                                {"team": "Turkey", "conditional_prob": 0.02, "overall_prob": 0.01},
                            ],
                        },
                    ],
                },
            },
        }
        html = app.build_bracket_visual_html(payload)
        self.assertIn("Llave actualizada", html)
        self.assertIn("2026-05-17T15:43:15", html)
        self.assertIn("15.000 simulaciones", html)
        self.assertIn("Octavos 5", html)
        self.assertIn("Cuartos 3", html)
        self.assertIn("Turkey</span></div><div class=\"team-divider\"></div><div class=\"team-row favorite\"><span class=\"team-name\">Spain", html)
        self.assertNotIn("Belgium</span></div><div class=\"team-divider\"></div><div class=\"team-row favorite\"><span class=\"team-name\">Spain", html)


if __name__ == "__main__":
    unittest.main()
