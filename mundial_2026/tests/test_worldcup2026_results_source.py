"""Tests: fuente de resultados 2026 (feed primario, CSV de fallback).

Cubre los tests obligatorios solicitados:
  - test_tracker_uses_fixtures_live_as_primary_source
  - test_finished_match_audit_used_only_as_fallback
  - test_source_consistency_report_exists
  - test_data_inventory_lists_finalized_matches
  - test_status_values_are_audited
  - test_no_results_are_invented
"""

from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026 import results_ingest as RI

DATA_INVENTORY = RI.DATA_INVENTORY_MD
SOURCE_CONSISTENCY = RI.SOURCE_CONSISTENCY_CSV


def setUpModule():
    # Reportes puros (sin modelo); garantiza existencia sin re-ejecutar el dashboard.
    RI.generate_reports()


class TestResultsSource(unittest.TestCase):
    def test_tracker_uses_fixtures_live_as_primary_source(self):
        src = RI.load_results_source()
        self.assertTrue(src.feed_available)
        self.assertEqual(src.mode, "feed")
        self.assertEqual(src.source, "fixtures_live_2026.json")

    def test_finished_match_audit_used_only_as_fallback(self):
        # Con el feed presente, el CSV NO es primario.
        primary = RI.load_results_source()
        self.assertNotEqual(primary.mode, "fallback_csv")
        self.assertNotEqual(primary.source, "finished_match_audit.csv")
        # Si el feed falta, recién entonces se usa el CSV.
        missing = ROOT / "__no_such_feed__.json"
        fallback = RI.load_results_source(fixtures_path=missing, audit_path=RI.AUDIT_CSV_PATH)
        self.assertEqual(fallback.mode, "fallback_csv")
        self.assertEqual(fallback.source, "finished_match_audit.csv")
        self.assertGreaterEqual(fallback.finalized_matches, 1)

    def test_source_consistency_report_exists(self):
        self.assertTrue(SOURCE_CONSISTENCY.exists())
        rows = list(csv.DictReader(SOURCE_CONSISTENCY.open(encoding="utf-8")))
        self.assertEqual(set(rows[0].keys()),
                         {"source", "total_matches", "finalized_matches", "latest_date", "notes"})
        sources = {r["source"] for r in rows}
        self.assertIn("fixtures_live_2026.json", sources)
        self.assertIn("finished_match_audit.csv", sources)

    def test_data_inventory_lists_finalized_matches(self):
        self.assertTrue(DATA_INVENTORY.exists())
        text = DATA_INVENTORY.read_text(encoding="utf-8")
        self.assertIn("Fuente principal", text)
        # Cada partido finalizado del feed aparece con su marcador.
        src = RI.load_results_source()
        for rec in RI.finalized_records(src):
            self.assertIn(rec["title"], text)
            self.assertIn(rec["actual_score"], text)

    def test_status_values_are_audited(self):
        fixtures = RI.load_fixtures()
        buckets, _ = RI.status_value_audit(fixtures)
        for k in ("pre", "live", "post", "final", "finished", "ft", "other"):
            self.assertIn(k, buckets)
        text = DATA_INVENTORY.read_text(encoding="utf-8")
        self.assertIn("Auditoría de valores de status", text)
        for k in ("pre", "post", "ft"):
            self.assertIn(k, text)

    def test_no_results_are_invented(self):
        fixtures = RI.load_fixtures()
        feed_finalized = [f for f in fixtures if RI.has_final_score(f)]
        src = RI.load_results_source()
        # El nº de finalizados coincide exactamente con los del feed con marcador real.
        self.assertEqual(src.finalized_matches, len(feed_finalized))
        # Cada registro finalizado corresponde a un marcador real con formato válido.
        for rec in RI.finalized_records(src):
            self.assertRegex(rec["actual_score"], r"^\d+-\d+$")
            self.assertIsNotNone(rec["fixture"].get("actual_score_a"))


if __name__ == "__main__":
    unittest.main()
