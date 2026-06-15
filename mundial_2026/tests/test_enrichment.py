"""Tests del enriquecimiento prepartido (offline, fuente inyectada).

Obligatorios:
  - test_enrichment_package_exists
  - test_enrichment_does_not_invent_lineups
  - test_enrichment_fallback_to_manual_t60
  - test_confirmed_lineup_writes_t60_inputs
  - test_goalkeeper_written_only_from_confirmed_lineup
  - test_injuries_written_only_from_trusted_source
  - test_no_post_kickoff_data_used_for_prematch
  - test_daily_ops_runs_enrichment_before_t60
  - test_daily_ops_no_enrichment_flag_skips_sync
  - test_no_model_predictions_changed
"""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026 import enrichment as ENR
from worldcup2026.enrichment.models import InjuryRecord, LineupPlayer, iso
from worldcup2026.enrichment import lineups as LU, injuries as INJ
from worldcup2026.enrichment.t60_writer import T60_COLUMNS
from worldcup2026.odds_provider.provider import build_match_id
import run_daily_quiniela_ops as OPS

KO = "2026-06-20T19:00:00Z"
NOW = datetime(2026, 6, 20, 18, 0, 0, tzinfo=timezone.utc)  # 1 h antes del kickoff
FX = {"team_a": "Spain", "team_b": "Cape Verde", "kickoff_utc": KO,
      "starting_xi_a": [], "starting_xi_b": []}
MID = build_match_id("Spain", "Cape Verde", KO)


class FakeSource:
    """Fuente inyectable: alineación confirmada/no, GK opcional, captured_at configurable."""

    def __init__(self, confirmed=True, gk="Keeper Uno", injuries=("Lesionado Uno",),
                 captured_at=None, injury_source="fake_api"):
        self.confirmed = confirmed
        self.gk = gk
        self.injuries = injuries
        self.captured_at = captured_at or iso(NOW)  # pre-kickoff por defecto
        self.injury_source = injury_source

    def lineup_for(self, fx, now):
        cap = self.captured_at
        players = [
            LineupPlayer(MID, fx["team_a"], "Delantero A", "F", True, False, "fake_api", cap),
            LineupPlayer(MID, fx["team_a"], self.gk or "GK A", "G", True, bool(self.gk), "fake_api", cap),
        ]
        return players, self.confirmed

    def injuries_for(self, fx, now):
        return [InjuryRecord(MID, fx["team_a"], n, "out", self.injury_source, self.captured_at)
                for n in self.injuries]


class TestEnrichment(unittest.TestCase):
    def test_enrichment_package_exists(self):
        for name in ("models", "sources", "sync_enrichment", "lineups", "injuries", "t60_writer"):
            self.assertTrue((ROOT / "worldcup2026" / "enrichment" / f"{name}.py").exists())
        self.assertTrue((ROOT / "sync_pre_match_enrichment.py").exists())
        for fn in ("enrich", "update_t60", "confirmed_lineup", "starting_goalkeeper", "trusted_injuries"):
            self.assertTrue(hasattr(ENR, fn))

    def test_enrichment_does_not_invent_lineups(self):
        # Sin alineación (fuente vacía) → no se crean jugadores ni se confirma.
        class Empty:
            def lineup_for(self, fx, now): return [], False
            def injuries_for(self, fx, now): return []
        records, players, injuries = ENR.enrich([FX], Empty(), NOW)
        self.assertEqual(players, [])
        self.assertEqual(records[0].lineup_status, "none")
        self.assertFalse(records[0].lineup_confirmed)

    def test_enrichment_fallback_to_manual_t60(self):
        # Alineación NO confirmada → no se escribe t60; fila manual se conserva.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t60_inputs.csv"
            path.write_text("match_id,captured_at_utc,lineup_confirmed,lineup_changes,"
                            "injuries_confirmed,starting_gk,gk_changed,notes\n"
                            f"{MID},2026-06-19T00:00:00Z,true,0,,Manual GK,false,manual\n",
                            encoding="utf-8")
            records, _, _ = ENR.enrich([FX], FakeSource(confirmed=False), NOW)
            written, kept = ENR.update_t60(records, path=path)
            self.assertEqual(written, 0)  # no se sobreescribió con datos no confirmados
            rows = list(csv.DictReader(path.open(encoding="utf-8")))
            self.assertEqual(rows[0]["starting_gk"], "Manual GK")  # fila manual intacta

    def test_confirmed_lineup_writes_t60_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t60_inputs.csv"
            records, _, _ = ENR.enrich([FX], FakeSource(confirmed=True), NOW)
            written, _ = ENR.update_t60(records, path=path)
            self.assertEqual(written, 1)
            rows = {r["match_id"]: r for r in csv.DictReader(path.open(encoding="utf-8"))}
            self.assertIn(MID, rows)
            self.assertEqual(rows[MID]["lineup_confirmed"], "true")
            self.assertEqual(set(rows[MID].keys()), set(T60_COLUMNS))

    def test_goalkeeper_written_only_from_confirmed_lineup(self):
        # confirmado con GK → se escribe el portero
        rec_conf, _, _ = ENR.enrich([FX], FakeSource(confirmed=True, gk="Keeper Uno"), NOW)
        self.assertEqual(rec_conf[0].goalkeeper_status, "confirmed")
        self.assertEqual(rec_conf[0].starting_gk, "Keeper Uno")
        # NO confirmado (aunque haya un jugador GK) → sin portero
        rec_unc, _, _ = ENR.enrich([FX], FakeSource(confirmed=False, gk="Keeper Uno"), NOW)
        self.assertEqual(rec_unc[0].goalkeeper_status, "none")
        self.assertIsNone(rec_unc[0].starting_gk)
        # comprobación directa del helper
        players, _ = FakeSource(gk="Keeper Uno").lineup_for(FX, NOW)
        self.assertIsNone(LU.starting_goalkeeper(players, confirmed=False))

    def test_injuries_written_only_from_trusted_source(self):
        # Registro sin source → descartado por trusted_injuries.
        class MixedInjuries:
            def lineup_for(self, fx, now): return [], False
            def injuries_for(self, fx, now):
                return [InjuryRecord(MID, "Spain", "Con Fuente", "out", "fake_api", iso(NOW)),
                        InjuryRecord(MID, "Spain", "Sin Fuente", "out", "", iso(NOW))]
        trusted = INJ.trusted_injuries(FX, MixedInjuries(), NOW)
        self.assertEqual(len(trusted), 1)
        self.assertEqual(trusted[0].player_name, "Con Fuente")
        self.assertTrue(trusted[0].source and trusted[0].captured_at)

    def test_no_post_kickoff_data_used_for_prematch(self):
        # captured_at DESPUÉS del kickoff → se descarta; no confirma, no GK, no t60.
        post = iso(NOW + timedelta(hours=4))  # > kickoff
        src = FakeSource(confirmed=True, gk="Keeper Uno", captured_at=post)
        records, players, injuries = ENR.enrich([FX], src, NOW)
        self.assertEqual(players, [])         # jugadores post-kickoff filtrados
        self.assertEqual(injuries, [])        # bajas post-kickoff filtradas
        self.assertFalse(records[0].lineup_confirmed)
        self.assertEqual(records[0].goalkeeper_status, "none")
        self.assertNotEqual(records[0].t60_status, "written")


class TestEnrichmentDailyOpsIntegration(unittest.TestCase):
    ARGS = ["--no-sync", "--no-odds-sync", "--skip-pipelines",
            "--enrichment-dry-run", "--now", "2026-06-15T00:00:00Z"]

    def test_daily_ops_runs_enrichment_before_t60(self):
        order = []
        orig_enr, orig_mod = OPS.run_enrichment_sync, OPS._run_module_main

        def fake_enr(enabled, now, dry_run=False):
            order.append("enrichment")
            return (None, "enrichment (fake)")

        def fake_mod(name, argv=None):
            order.append(name)
            return (0, "")

        OPS.run_enrichment_sync, OPS._run_module_main = fake_enr, fake_mod
        try:
            OPS.main(["--no-sync", "--no-odds-sync", "--now", "2026-06-15T00:00:00Z"])
        finally:
            OPS.run_enrichment_sync, OPS._run_module_main = orig_enr, orig_mod
        self.assertIn("enrichment", order)
        self.assertIn("run_market_t60_pipeline", order)
        self.assertLess(order.index("enrichment"), order.index("run_market_t60_pipeline"))

    def test_daily_ops_no_enrichment_flag_skips_sync(self):
        called = {"n": 0}
        import sync_pre_match_enrichment as ENRMOD
        orig = ENRMOD.run

        def spy(*a, **k):
            called["n"] += 1
            return orig(*a, **k)

        ENRMOD.run = spy
        try:
            OPS.main(self.ARGS + ["--no-enrichment-sync"])
        finally:
            ENRMOD.run = orig
        self.assertEqual(called["n"], 0)
        text = OPS.SUMMARY_MD.read_text(encoding="utf-8")
        self.assertIn("desactivado", text)

    def test_no_model_predictions_changed(self):
        import modelo_quiniela_2026 as M
        teams = M.load_teams()
        pairs = [("Spain", "Cape Verde"), ("Belgium", "Egypt")]

        def snap():
            return {(a, b): M.predict_match(teams, a, b).exact_scores[0][0] for a, b in pairs}

        before = snap()
        OPS.main(self.ARGS + ["--no-enrichment-sync"])
        self.assertEqual(before, snap())


if __name__ == "__main__":
    unittest.main()
