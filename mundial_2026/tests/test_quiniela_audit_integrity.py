from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import modelo_quiniela_2026 as app


class QuinielaAuditIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.teams_payload = json.loads((PACKAGE_ROOT / "teams_2026.json").read_text())
        self.teams_by_name = {team["name"]: team for team in self.teams_payload["teams"]}
        self.draw_payload = json.loads((PACKAGE_ROOT / "tournament_2026_draw.json").read_text())

    def test_final_draw_has_48_unique_qualified_teams(self):
        groups = self.draw_payload["groups"]
        group_teams = [team for members in groups.values() for team in members]

        self.assertEqual(len(groups), 12)
        self.assertTrue(all(len(members) == 4 for members in groups.values()))
        self.assertEqual(len(group_teams), 48)
        self.assertEqual(len(set(group_teams)), 48)

        missing = [team for team in group_teams if team not in self.teams_by_name]
        not_qualified = [
            team
            for team in group_teams
            if self.teams_by_name.get(team, {}).get("status") != "qualified"
        ]
        self.assertEqual(missing, [])
        self.assertEqual(not_qualified, [])

    def test_recently_resolved_qualifiers_are_in_draw_and_old_losers_are_out(self):
        group_teams = {team for members in self.draw_payload["groups"].values() for team in members}
        for team in {"Bosnia and Herzegovina", "Dem. Rep. of Congo", "Iraq"}:
            self.assertIn(team, group_teams)
            self.assertEqual(self.teams_by_name[team]["status"], "qualified")

        for team in {"Italy", "Jamaica", "Bolivia", "Suriname", "New Caledonia"}:
            self.assertNotIn(team, group_teams)
            self.assertEqual(self.teams_by_name[team]["status"], "eliminated")

    def test_playoff_helpers_resolve_to_final_qualified_teams(self):
        teams = app.load_teams()
        self.assertEqual(
            app.resolved_fifa_path_winners(teams),
            {"FIFA_1": "Dem. Rep. of Congo", "FIFA_2": "Iraq"},
        )
        self.assertEqual(
            app.resolved_uefa_path_winners(teams),
            {
                "UEFA_A": "Bosnia and Herzegovina",
                "UEFA_B": "Sweden",
                "UEFA_C": "Turkey",
                "UEFA_D": "Czech Republic",
            },
        )

    def test_public_bracket_output_is_not_a_smoke_run(self):
        bracket = json.loads((PACKAGE_ROOT / "llave_actual_2026.json").read_text())
        self.assertGreaterEqual(int(bracket.get("iterations", 0)), 15000)
        self.assertIn("M104", bracket.get("matches", {}))
        self.assertIn("M103", bracket.get("matches", {}))

    def test_github_pages_workflow_runs_full_auto_refresh(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "quiniela-pages.yml").read_text()
        self.assertRegex(workflow, r"cron:\s*[\"']\*/5 \* \* \* \*[\"']")
        self.assertIn("--iterations 15000", workflow)
        self.assertIn("API_FOOTBALL_KEY", workflow)
        self.assertIn("cancel-in-progress: false", workflow)


if __name__ == "__main__":
    unittest.main()
