from __future__ import annotations

import json
import sys
import tempfile
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
        self.assertIn("python3 -m unittest discover -s mundial_2026/tests", workflow)
        self.assertIn("audit-quiniela", workflow)
        self.assertIn("API_FOOTBALL_KEY", workflow)
        self.assertIn("cancel-in-progress: false", workflow)

    def test_audit_workflow_text_requires_publish_gate(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "quiniela-pages.yml").read_text()
        self.assertEqual(app.audit_workflow_text(workflow, 15000), [])

    def test_dashboard_audit_requires_ticket_audit_block(self):
        html = (
            "<html><section class=\"certainty-panel\"><h2>Hoja de máxima certeza</h2>"
            "<p>Picks mas defendibles</p><p>Marcadores exactos mas defendibles</p><p>15000</p></section></html>"
        )
        errors = app.audit_dashboard_html(html)
        self.assertTrue(any("Auditoria del boleto" in error for error in errors))

    def build_valid_bracket_matches(self):
        team_pool = [team for members in self.draw_payload["groups"].values() for team in members]
        bracket_matches = {}
        previous_winners = {}
        previous_losers = {}

        def match_record(match_id, stage, team_a, team_b, winner):
            loser = team_b if winner == team_a else team_a
            return {
                "match_id": match_id,
                "stage": stage,
                "team_a": team_a,
                "team_b": team_b,
                "winner": winner,
                "matchup_prob": 0.2,
                "conditional_winner_prob": 0.6,
                "winner_prob": 0.6,
                "penalties_prob": 0.12,
                "top_penalty_scores": [{"score": "5-4", "prob": 0.08}],
                "matchup_scenarios": [
                    {
                        "team_a": team_a,
                        "team_b": team_b,
                        "winner": winner,
                        "matchup_prob": 0.2,
                        "conditional_winner_prob": 0.6,
                        "winner_prob": 0.12,
                        "conditional_winners": [
                            {"team": winner, "conditional_prob": 0.6, "overall_prob": 0.12},
                            {"team": loser, "conditional_prob": 0.4, "overall_prob": 0.08},
                        ],
                    }
                ],
            }

        for index, match in enumerate(app.R32_MATCHES):
            team_a = team_pool[(index * 2) % len(team_pool)]
            team_b = team_pool[(index * 2 + 1) % len(team_pool)]
            winner = team_a
            bracket_matches[match["id"]] = match_record(match["id"], "round32", team_a, team_b, winner)
            previous_winners[match["id"]] = winner
            previous_losers[match["id"]] = team_b

        for stage, matches in app.KNOCKOUT_MATCHES.items():
            for match_id, left_source, right_source in matches:
                team_a = previous_winners[left_source]
                team_b = previous_winners[right_source]
                winner = team_a
                bracket_matches[match_id] = match_record(match_id, stage, team_a, team_b, winner)
                previous_winners[match_id] = winner
                previous_losers[match_id] = team_b

        bracket_matches["M104"] = match_record(
            "M104",
            "third_place",
            previous_losers["M101"],
            previous_losers["M102"],
            previous_losers["M101"],
        )
        return bracket_matches

    def test_bracket_audit_requires_third_place_semifinal_losers(self):
        teams = app.load_teams()
        bracket_matches = self.build_valid_bracket_matches()
        self.assertEqual(app.audit_bracket_payload({"iterations": 15000, "matches": bracket_matches}, teams, 15000), [])

        bad_matches = json.loads(json.dumps(bracket_matches))
        bad_matches["M104"]["team_a"] = bad_matches["M101"]["winner"]
        bad_matches["M104"]["team_b"] = bad_matches["M102"]["winner"]
        bad_matches["M104"]["winner"] = bad_matches["M101"]["winner"]
        errors = app.audit_bracket_payload({"iterations": 15000, "matches": bad_matches}, teams, 15000)
        self.assertTrue(any("M104" in error and "rama proyectada" in error for error in errors))

    def test_bracket_audit_requires_penalty_score_options_when_penalties_are_possible(self):
        teams = app.load_teams()
        bracket_matches = self.build_valid_bracket_matches()
        bracket_matches["M73"]["top_penalty_scores"] = []

        errors = app.audit_bracket_payload({"iterations": 15000, "matches": bracket_matches}, teams, 15000)

        self.assertTrue(any("M73" in error and "marcadores probables de tanda" in error for error in errors))

    def test_bracket_audit_rejects_exact_scenario_probability_as_matchup_probability(self):
        teams = app.load_teams()
        bracket_matches = self.build_valid_bracket_matches()
        bracket_matches["M73"]["matchup_prob"] = 0.12

        errors = app.audit_bracket_payload({"iterations": 15000, "matches": bracket_matches}, teams, 15000)

        self.assertTrue(any("M73" in error and "probabilidad del escenario" in error for error in errors))

    def test_coherent_bracket_matches_rewrites_raw_modal_branch_for_publish(self):
        bracket_matches = self.build_valid_bracket_matches()
        raw_matches = json.loads(json.dumps(bracket_matches))
        raw_matches["M104"]["team_a"] = raw_matches["M101"]["winner"]
        raw_matches["M104"]["team_b"] = raw_matches["M102"]["winner"]
        raw_matches["M104"]["winner"] = raw_matches["M101"]["winner"]

        coherent = app.coherent_bracket_matches({"matches": raw_matches})

        self.assertEqual(coherent["M104"]["team_a"], bracket_matches["M104"]["team_a"])
        self.assertEqual(coherent["M104"]["team_b"], bracket_matches["M104"]["team_b"])
        self.assertEqual(coherent["M104"]["winner"], bracket_matches["M104"]["winner"])

    def test_run_quiniela_audit_passes_with_minimal_valid_generated_artifacts(self):
        teams = app.load_teams()
        draw = self.draw_payload
        first_group = draw["groups"]["A"]
        bracket_matches = self.build_valid_bracket_matches()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_path = tmp / "draw.json"
            fixtures_path = tmp / "fixtures.json"
            bracket_path = tmp / "bracket.json"
            dashboard_path = tmp / "index.html"
            workflow_path = tmp / "workflow.yml"
            config_path.write_text(json.dumps(draw))
            fixtures_path.write_text(json.dumps([{"id": "1", "team_a": first_group[0], "team_b": first_group[1], "status_state": "pre"}]))
            bracket_path.write_text(json.dumps({"iterations": 15000, "matches": bracket_matches}))
            dashboard_path.write_text(
                "<html><section class=\"certainty-panel\"><h2>Hoja de máxima certeza</h2>"
                "<p>Auditoria del boleto</p>"
                "<p>Picks firmes o preferentes</p>"
                "<p>Partidos trampa o alta varianza</p>"
                "<p>Marcadores exactos defendibles</p>"
                "<p>Brecha minima contra la segunda opcion</p>"
                "<p>Checklist de auditoria</p>"
                "<p>Picks mas defendibles</p><p>Marcadores exactos mas defendibles</p><p>15000</p></section></html>"
            )
            workflow_path.write_text(
                'cron: "*/5 * * * *"\n'
                "python3 -m unittest discover -s mundial_2026/tests\n"
                "python3 mundial_2026/modelo_quiniela_2026.py project-bracket --iterations 15000\n"
                "python3 mundial_2026/modelo_quiniela_2026.py audit-quiniela\n"
                "API_FOOTBALL_KEY\n"
                "cancel-in-progress: false\n"
            )
            self.assertEqual(
                app.run_quiniela_audit(
                    teams,
                    config_path=config_path,
                    bracket_json_path=bracket_path,
                    dashboard_html_path=dashboard_path,
                    fixtures_path=fixtures_path,
                    workflow_path=workflow_path,
                    min_iterations=15000,
                ),
                [],
            )


if __name__ == "__main__":
    unittest.main()
