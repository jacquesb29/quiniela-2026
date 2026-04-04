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


if __name__ == "__main__":
    unittest.main()
