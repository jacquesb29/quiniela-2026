"""Tests F7: cierre operativo final (documentación + congelamiento)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.config import PARAMS

FINAL_REPORT = ROOT / "FINAL_MODEL_REPORT.md"
MODEL_LOCK = ROOT / "MODEL_LOCK.md"
OPERATION_GUIDE = ROOT / "QUINIELA_OPERATION_GUIDE.md"
CHANGELOG = ROOT / "CHANGELOG_FINAL.md"
FINAL_RUNNER = ROOT / "run_final_validation.py"
VARIANCE_DECISION = ROOT / "outputs" / "audit" / "variance_attribution_decision.md"

# Flags de producción que deben permanecer OFF.
PRODUCTION_FLAGS_OFF = ("elo_staleness_enabled",)


class TestF7Closure(unittest.TestCase):
    def test_final_report_exists(self):
        self.assertTrue(FINAL_REPORT.exists())
        text = FINAL_REPORT.read_text(encoding="utf-8")
        for token in ("F0", "F1", "F2", "F3", "F4", "F5", "F6"):
            self.assertIn(token, text)

    def test_model_lock_exists(self):
        self.assertTrue(MODEL_LOCK.exists())
        text = MODEL_LOCK.read_text(encoding="utf-8").lower()
        self.assertIn("congelam", text)
        self.assertIn("nuevo gate", text)

    def test_operation_guide_exists(self):
        self.assertTrue(OPERATION_GUIDE.exists())
        text = OPERATION_GUIDE.read_text(encoding="utf-8")
        for token in ("follow_market", "shade_to_market", "no_market_available", "changed", "confidence", "Confidence".lower()):
            self.assertIn(token.lower(), text.lower())

    def test_final_validation_runner_exists(self):
        self.assertTrue(FINAL_RUNNER.exists())
        # changelog también debe existir.
        self.assertTrue(CHANGELOG.exists())

    def test_no_production_flags_enabled(self):
        for flag in PRODUCTION_FLAGS_OFF:
            self.assertFalse(getattr(PARAMS, flag), f"{flag} debe estar OFF")

    def test_f6_marked_not_applicable_after_no_clear_culprit(self):
        lock = MODEL_LOCK.read_text(encoding="utf-8").lower()
        report = FINAL_REPORT.read_text(encoding="utf-8").lower()
        # F6 declarado no procede, ligado a no_clear_culprit de F5.
        self.assertIn("no_clear_culprit", lock)
        self.assertIn("no procede", lock)
        self.assertIn("no_clear_culprit", report)
        # Si el artefacto de F5 existe, debe decir no_clear_culprit.
        if VARIANCE_DECISION.exists():
            self.assertIn("no_clear_culprit", VARIANCE_DECISION.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
