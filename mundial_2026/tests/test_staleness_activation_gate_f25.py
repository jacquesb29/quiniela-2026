"""Tests F2.5: gate de validación y decisión de activación."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.config import PARAMS  # noqa: E402
from worldcup2026.ratings.activation_gate import (  # noqa: E402
    DECISION_ACTIVATE,
    DECISION_KEEP_OFF,
    build_by_bucket,
    build_gate_rows,
    decide_activation,
    staleness_match_bucket,
    write_decision_md,
    write_gate_csv,
)

BASE = {"n": 1520, "logloss": 0.995, "brier": 0.198, "accuracy": 0.53,
        "exact_score_accuracy": 0.14, "penca_points_avg": 2.50, "penca_points_total": 3800.0}


def _exp(**overrides):
    m = dict(BASE)
    m.update(overrides)
    return m


class TestActivationGateF25(unittest.TestCase):
    def test_staleness_gate_keeps_flag_off_by_default(self):
        # El default del proyecto NO cambia por correr el gate.
        self.assertFalse(PARAMS.elo_staleness_enabled)
        # Y sin diferencia de métricas (experimental == baseline) -> keep_off.
        d = decide_activation(BASE, _exp(), out_of_sample=True)
        self.assertEqual(d["decision"], DECISION_KEEP_OFF)

    def test_gate_compares_baseline_vs_experimental(self):
        rows = build_gate_rows({
            "baseline": BASE,
            "staleness_experimental": _exp(penca_points_avg=2.55),
            "poisson_simple": {"n": 1520, "logloss": 1.006, "brier": 0.199},
            "elo_puro": {"n": 1520, "logloss": 1.003, "brier": 0.200},
        })
        names = {r["model"] for r in rows}
        self.assertIn("baseline", names)
        self.assertIn("staleness_experimental", names)
        self.assertIn("poisson_simple", names)
        self.assertIn("elo_puro", names)

    def test_gate_requires_penca_improvement(self):
        # Mejora Penca clara sin empeorar log-loss -> activar.
        d_up = decide_activation(BASE, _exp(penca_points_avg=2.58, logloss=0.994), out_of_sample=True)
        self.assertEqual(d_up["decision"], DECISION_ACTIVATE)
        # Penca igual -> no activar.
        d_eq = decide_activation(BASE, _exp(penca_points_avg=2.50), out_of_sample=True)
        self.assertEqual(d_eq["decision"], DECISION_KEEP_OFF)

    def test_gate_blocks_activation_if_logloss_worse(self):
        # Penca sube pero log-loss empeora de forma relevante -> bloquear.
        d = decide_activation(BASE, _exp(penca_points_avg=2.60, logloss=0.995 + 0.02), out_of_sample=True)
        self.assertEqual(d["decision"], DECISION_KEEP_OFF)
        self.assertIn("log-loss", d["reason"].lower())

    def test_gate_reports_by_staleness_bucket(self):
        self.assertEqual(staleness_match_bucket(0.60), "alto")
        self.assertEqual(staleness_match_bucket(0.30), "medio")
        self.assertEqual(staleness_match_bucket(0.10), "bajo")
        rows = build_by_bucket({"bajo": {"n": 1520, "logloss": 0.995, "brier": 0.198, "penca_points_avg": 2.5},
                                "medio": {"n": 0}, "alto": {"n": 0}})
        buckets = {r["bucket"] for r in rows}
        self.assertEqual(buckets, {"alto", "medio", "bajo"})

    def test_activation_decision_file_exists(self):
        decision = decide_activation(BASE, _exp(), out_of_sample=True)
        model_rows = build_gate_rows({"baseline": BASE, "staleness_experimental": _exp()})
        bucket_rows = build_by_bucket({"bajo": {"n": 1520}, "medio": {"n": 0}, "alto": {"n": 0}})
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "gate.csv"
            md_path = Path(tmp) / "decision.md"
            write_gate_csv(model_rows, bucket_rows, csv_path)
            write_decision_md(decision, model_rows, bucket_rows, path=md_path, limitation_note="nota")
            self.assertTrue(csv_path.exists())
            self.assertTrue(md_path.exists())
            self.assertIn("Decisión", md_path.read_text(encoding="utf-8"))

    def test_insufficient_sample_keeps_off(self):
        d = decide_activation(BASE, _exp(n=10, penca_points_avg=3.0), out_of_sample=True)
        self.assertEqual(d["decision"], DECISION_KEEP_OFF)
        d2 = decide_activation(BASE, _exp(penca_points_avg=3.0), out_of_sample=False)
        self.assertEqual(d2["decision"], DECISION_KEEP_OFF)


if __name__ == "__main__":
    unittest.main()
