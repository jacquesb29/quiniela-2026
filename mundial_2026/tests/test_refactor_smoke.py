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
        args = parser.parse_args(["project-bracket", "--iterations", "32"])
        self.assertEqual(args.command, "project-bracket")
        self.assertEqual(args.iterations, 32)

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
            ],
            {"iterations": 15000},
        )
        self.assertIn("15.000 simulaciones", html)
        self.assertIn("api_football", html)
        self.assertIn("1</strong> en vivo", html)

    def test_bracket_visual_keeps_branch_coherent(self):
        payload = {
            "iterations": 100,
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
        self.assertIn("Octavos 5", html)
        self.assertIn("Cuartos 3", html)
        self.assertIn("Turkey</span></div><div class=\"team-divider\"></div><div class=\"team-row favorite\"><span class=\"team-name\">Spain", html)
        self.assertNotIn("Belgium</span></div><div class=\"team-divider\"></div><div class=\"team-row favorite\"><span class=\"team-name\">Spain", html)


if __name__ == "__main__":
    unittest.main()
