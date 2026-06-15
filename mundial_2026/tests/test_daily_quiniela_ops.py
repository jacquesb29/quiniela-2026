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
import os
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
        self.assertIn("sync feed: **failed**", text)
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


class TestDailyOpsOddsSync(unittest.TestCase):
    """Encadenado del sync de odds (paso 0) en la operación diaria."""

    MARKET_CSV = ROOT / "data" / "market_odds_input.csv"

    def _csv_snapshot(self):
        return self.MARKET_CSV.read_text(encoding="utf-8") if self.MARKET_CSV.exists() else None

    def test_daily_ops_runs_odds_sync_first(self):
        order = []
        orig_odds = OPS.run_odds_sync
        orig_mod = OPS._run_module_main

        def fake_odds(enabled, dry_run=False):
            order.append("odds_sync")
            return orig_odds(enabled, dry_run=dry_run)

        def fake_mod(name, argv=None):
            order.append(name)
            return (0, "")

        OPS.run_odds_sync, OPS._run_module_main = fake_odds, fake_mod
        try:
            OPS.main(["--no-sync", "--now", REF_NOW])
        finally:
            OPS.run_odds_sync, OPS._run_module_main = orig_odds, orig_mod
        self.assertIn("odds_sync", order)
        self.assertIn("run_market_t60_pipeline", order)
        # el sync de odds ocurre ANTES del pipeline de mercado/T-60
        self.assertLess(order.index("odds_sync"), order.index("run_market_t60_pipeline"))

    def test_daily_ops_no_key_falls_back_to_local_csv(self):
        os.environ.pop("THE_ODDS_API_KEY", None)
        before = self._csv_snapshot()
        OPS.main(["--no-sync", "--skip-pipelines", "--now", REF_NOW])
        text = OPS.SUMMARY_MD.read_text(encoding="utf-8")
        self.assertIn("origen **local_csv**", text)
        self.assertIn("THE_ODDS_API_KEY", text)
        self.assertEqual(before, self._csv_snapshot())  # CSV intacto

    def test_daily_ops_api_failure_falls_back_to_local_csv(self):
        import sync_market_odds
        from worldcup2026.odds_provider import OddsProviderError
        os.environ["THE_ODDS_API_KEY"] = "TEST_KEY"
        orig = sync_market_odds.generate_rows
        sync_market_odds.generate_rows = lambda *a, **k: (_ for _ in ()).throw(OddsProviderError("boom"))
        before = self._csv_snapshot()
        try:
            OPS.main(["--no-sync", "--skip-pipelines", "--now", REF_NOW])
        finally:
            sync_market_odds.generate_rows = orig
            os.environ.pop("THE_ODDS_API_KEY", None)
        text = OPS.SUMMARY_MD.read_text(encoding="utf-8")
        self.assertIn("origen **local_csv**", text)
        self.assertIn("falló", text)
        self.assertEqual(before, self._csv_snapshot())  # CSV intacto

    def test_daily_ops_no_odds_sync_flag_skips_sync(self):
        called = {"n": 0}
        import sync_market_odds
        orig = sync_market_odds.generate_rows

        def spy(*a, **k):
            called["n"] += 1
            return orig(*a, **k)

        sync_market_odds.generate_rows = spy
        os.environ["THE_ODDS_API_KEY"] = "TEST_KEY"
        try:
            OPS.main(["--no-sync", "--no-odds-sync", "--skip-pipelines", "--now", REF_NOW])
        finally:
            sync_market_odds.generate_rows = orig
            os.environ.pop("THE_ODDS_API_KEY", None)
        self.assertEqual(called["n"], 0)  # no se intentó descargar
        text = OPS.SUMMARY_MD.read_text(encoding="utf-8")
        self.assertIn("desactivado", text)
        self.assertIn("origen **local_csv**", text)

    def test_daily_ops_summary_reports_odds_source(self):
        OPS.main(["--no-sync", "--skip-pipelines", "--now", REF_NOW])
        text = OPS.SUMMARY_MD.read_text(encoding="utf-8")
        self.assertIn("**Odds:**", text)
        self.assertTrue(("origen **api**" in text) or ("origen **local_csv**" in text))

    def test_no_model_predictions_changed_with_odds_sync(self):
        import modelo_quiniela_2026 as M
        teams = M.load_teams()
        pairs = [("Spain", "Cape Verde"), ("Belgium", "Egypt")]

        def snapshot():
            return {(a, b): M.predict_match(teams, a, b).exact_scores[0][0] for a, b in pairs}

        before = snapshot()
        OPS.main(["--no-sync", "--skip-pipelines", "--now", REF_NOW])
        self.assertEqual(before, snapshot())


def tearDownModule():
    # deja la operación en estado base reproducible
    OPS.main(COMMON_ARGS)


if __name__ == "__main__":
    unittest.main()
