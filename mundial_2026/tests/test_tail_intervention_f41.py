"""Tests F4.1: intervención post-distribución de colas (Estilo A) + gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.interventions.gate import (
    DECISION_ACTIVATE,
    decide_tail_activation,
)
from worldcup2026.interventions.tail import (
    TailParams,
    effective_tail_mass,
    tail_reweight,
)


def _dist():
    # Distribución con masa repartida y algo de cola (total hasta 6).
    raw = {}
    weights = {0: 0.10, 1: 0.20, 2: 0.25, 3: 0.20, 4: 0.13, 5: 0.08, 6: 0.04}
    # repartir cada total entre marcadores plausibles
    splits = {
        0: [(0, 0)], 1: [(1, 0), (0, 1)], 2: [(2, 0), (1, 1), (0, 2)],
        3: [(2, 1), (3, 0), (1, 2)], 4: [(3, 1), (2, 2), (4, 0)],
        5: [(3, 2), (4, 1)], 6: [(4, 2), (3, 3)],
    }
    for tot, w in weights.items():
        cells = splits[tot]
        for c in cells:
            raw[c] = raw.get(c, 0.0) + w / len(cells)
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}


HI = dict(expected_total=3.6, favorite_share=0.72)   # señal alta
LO = dict(expected_total=2.0, favorite_share=0.50)   # sin señal
WEAK = dict(expected_total=2.4, favorite_share=0.52)  # favorito débil


def _base(**ov):
    m = {"n": 1000, "logloss": 0.995, "brier": 0.198, "penca_avg": 2.50, "draw_error": 0.01,
         "tail_err_4": 0.030, "tail_err_5": 0.034, "tail_err_6": 0.022, "weak_fav_tail_overpred": 0.0}
    m.update(ov)
    return m


class TestTailReweight(unittest.TestCase):
    def test_tail_flag_off_is_identity(self):
        d = _dist()
        out = tail_reweight(d, params=TailParams(enabled=False, beta=1.0), **HI)
        self.assertEqual(out, d)

    def test_tail_intervention_increases_ge5_mass_when_signal(self):
        d = _dist()
        out = tail_reweight(d, params=TailParams(enabled=True, beta=1.0, max_mass_shift=0.10), **HI)
        self.assertGreater(effective_tail_mass(out, 5), effective_tail_mass(d, 5))

    def test_no_change_without_tail_signal(self):
        d = _dist()
        out = tail_reweight(d, params=TailParams(enabled=True, beta=1.0), **LO)
        self.assertEqual(out, d)

    def test_probabilities_sum_to_one_after_reweight(self):
        d = _dist()
        out = tail_reweight(d, params=TailParams(enabled=True, beta=1.2, max_mass_shift=0.20), **HI)
        self.assertAlmostEqual(sum(out.values()), 1.0, places=9)

    def test_weak_favorite_not_inflated(self):
        d = _dist()
        out = tail_reweight(d, params=TailParams(enabled=True, beta=1.0, weak_favorite_guard=True), **WEAK)
        self.assertEqual(out, d)  # guard impide inflar
        self.assertAlmostEqual(effective_tail_mass(out, 4), effective_tail_mass(d, 4), places=12)

    def test_mass_shift_capped(self):
        d = _dist()
        params = TailParams(enabled=True, beta=2.0, max_mass_shift=0.02)
        out = tail_reweight(d, params=params, **HI)
        added = effective_tail_mass(out, params.t0 + 1) - effective_tail_mass(d, params.t0 + 1)
        self.assertLessEqual(added, params.max_mass_shift + 1e-9)

    def test_no_2026_data_used(self):
        # Función pura/determinista; no lee archivos ni fechas 2026.
        d = _dist()
        p = TailParams(enabled=True, beta=0.8)
        self.assertEqual(tail_reweight(d, params=p, **HI), tail_reweight(d, params=p, **HI))
        self.assertNotIn("year", tail_reweight.__code__.co_varnames)


class TestTailGate(unittest.TestCase):
    def test_gate_activates_when_tail_improves_no_harm(self):
        exp = _base(tail_err_5=0.020)  # mejora tail≥5, resto igual
        d = decide_tail_activation(_base(), exp)
        self.assertEqual(d["decision"], DECISION_ACTIVATE)

    def test_gate_blocks_if_logloss_worse(self):
        exp = _base(tail_err_5=0.020, logloss=0.995 + 0.02)  # log-loss empeora
        d = decide_tail_activation(_base(), exp)
        self.assertNotEqual(d["decision"], DECISION_ACTIVATE)

    def test_gate_blocks_if_penca_worse(self):
        exp = _base(tail_err_5=0.020, penca_avg=2.40)  # Penca empeora
        d = decide_tail_activation(_base(), exp)
        self.assertNotEqual(d["decision"], DECISION_ACTIVATE)

    def test_gate_reports_by_threshold_4_5_6(self):
        d = decide_tail_activation(_base(), _base(tail_err_5=0.020))
        for k in ("tail_err_4_base", "tail_err_4_exp", "tail_err_5_base", "tail_err_5_exp",
                  "tail_err_6_base", "tail_err_6_exp"):
            self.assertIn(k, d)

    def test_gate_blocks_if_no_tail_improvement(self):
        d = decide_tail_activation(_base(), _base())  # sin mejora
        self.assertNotEqual(d["decision"], DECISION_ACTIVATE)

    def test_gate_insufficient_sample(self):
        d = decide_tail_activation(_base(), _base(n=10, tail_err_5=0.0))
        self.assertNotEqual(d["decision"], DECISION_ACTIVATE)


if __name__ == "__main__":
    unittest.main()
