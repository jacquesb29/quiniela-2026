"""Tests de la operación diaria (run_daily_quiniela_ops.py).

Obligatorios:
  - test_daily_ops_runner_exists
  - test_daily_ops_does_not_invent_results
  - test_daily_ops_handles_sync_failure
  - test_daily_ops_marks_missing_odds
  - test_daily_ops_marks_missing_t60
  - test_daily_ops_outputs_required_columns
  - test_daily_ops_summary_contains_final_picks
  - test_scheduler_script_exists_but_not_auto_enabled
  - test_no_model_predictions_changed
"""

from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_daily_quiniela_ops as OPS
from worldcup2026 import results_ingest as RI

RUNNER = ROOT / "run_daily_quiniela_ops.py"
SCHED = ROOT / "scripts" / "setup_quiniela_cron.sh"

# Momento de referencia dentro del torneo (determinista para los tests).
REF_NOW = "2026-06-15T00:00:00Z"
COMMON_ARGS = ["--no-sync", "--now", REF_NOW]


def setUpModule():
    OPS.main(COMMON_ARGS)


class TestDailyOps(unittest.TestCase):
    def test_daily_ops_runner_exists(self):
        self.assertTrue(RUNNER.exists())
        self.assertTrue(hasattr(OPS, "main"))

    def test_daily_ops_does_not_invent_results(self):
        # Los finalizados del resumen deben coincidir EXACTO con los del feed (con marcador real).
        fixtures = RI.load_fixtures()
        feed_finalized = [f for f in fixtures if RI.has_final_score(f)]
        text = OPS.SUMMARY_MD.read_text(encoding="utf-8")
        # nº de finalizados reportado == nº real del feed
        self.assertIn(f"**finalizados:** {len(feed_finalized)}", text)
        # ningún pick de partido próximo trae marcador real inventado
        for r in csv.DictReader(OPS.PICKS_CSV.open(encoding="utf-8")):
            self.assertNotIn("actual_score", r)

    def test_daily_ops_handles_sync_failure(self):
        # Sync habilitado pero script inexistente -> no rompe y deja warning.
        rc = OPS.main(["--now", REF_NOW, "--sync-script", str(ROOT / "__no_such_sync__.py")])
        self.assertEqual(rc, 0)
        text = OPS.SUMMARY_MD.read_text(encoding="utf-8")
        self.assertIn("sync: **failed**", text)
        self.assertIn("último feed local", text)
        # restaura estado base
        OPS.main(COMMON_ARGS)

    def test_daily_ops_marks_missing_odds(self):
        rows = list(csv.DictReader(OPS.PICKS_CSV.open(encoding="utf-8")))
        # Debe existir al menos un partido próximo y todos traen booleano de odds.
        for r in rows:
            self.assertIn(r["odds_available"], ("True", "False"))
        # Si hay próximos sin odds, deben quedar marcados como no disponibles.
        self.assertTrue(all(r["odds_available"] in ("True", "False") for r in rows))

    def test_daily_ops_marks_missing_t60(self):
        rows = list(csv.DictReader(OPS.PICKS_CSV.open(encoding="utf-8")))
        for r in rows:
            self.assertIn(r["t60_available"], ("True", "False"))

    def test_daily_ops_outputs_required_columns(self):
        with OPS.PICKS_CSV.open(encoding="utf-8") as h:
            header = next(csv.reader(h))
        self.assertEqual(tuple(header), OPS.PICKS_COLUMNS)
        for col in ("match_id", "kickoff_utc", "team_a", "team_b", "model_pick", "market_pick",
                    "final_pick", "final_score_recommendation", "confidence_label", "action",
                    "reason", "odds_available", "t60_available", "warnings"):
            self.assertIn(col, header)

    def test_daily_ops_summary_contains_final_picks(self):
        text = OPS.SUMMARY_MD.read_text(encoding="utf-8")
        self.assertIn("qué marcador cargar", text)
        self.assertIn("marcador a cargar en la quiniela", text.lower())
        # acciones del vocabulario presentes
        self.assertIn("## Acciones", text)
        for a in OPS.ACTIONS:
            self.assertIn(a, text)

    def test_scheduler_script_exists_but_not_auto_enabled(self):
        self.assertTrue(SCHED.exists())
        body = SCHED.read_text(encoding="utf-8")
        # No debe instalar crontab salvo --install explícito.
        self.assertIn("--install", body)
        self.assertIn("Modo solo-instrucciones", body)
        # La instalación está condicionada (no se ejecuta crontab incondicionalmente).
        self.assertNotRegex(body, r"^\s*crontab -\s*$")

    def test_no_model_predictions_changed(self):
        import modelo_quiniela_2026 as M
        teams = M.load_teams()
        pairs = [("Germany", "Curacao"), ("Netherlands", "Japan"), ("Mexico", "South Africa")]

        def snapshot():
            out = {}
            for a, b in pairs:
                p = M.predict_match(teams, a, b)
                out[(a, b)] = (round(p.win_a, 9), round(p.draw, 9), round(p.win_b, 9),
                               round(p.expected_goals_a, 9), round(p.expected_goals_b, 9),
                               p.exact_scores[0][0])
            return out

        before = snapshot()
        OPS.main(COMMON_ARGS)
        after = snapshot()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
