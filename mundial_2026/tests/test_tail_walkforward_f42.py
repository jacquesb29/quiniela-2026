"""Tests F4.2: validación walk-forward fold-a-fold del candidato de colas."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.walk_forward import temporal_folds
from worldcup2026.interventions.walkforward_tail import (
    FOLD_COLUMNS,
    FOLD_MIN_TRAIN,
    FOLD_SCHEME,
    FOLD_STEP,
    WFTailGateThresholds,
    decide_tail_walkforward,
    run_tail_walkforward,
)
EXPECTED_GOALS_SRC = ROOT / "worldcup2026" / "models" / "expected_goals.py"  # chequeo no-wiring


def _row(i):
    base_day = 1 + (i // 3)
    return {"match_id": f"m{i:04d}", "date": f"1990-01-{base_day:02d}",
            "team_a": f"A{i}", "team_b": f"B{i}", "goals_a": "1", "goals_b": "0",
            "elo_a_pre": "1700", "elo_b_pre": "1500"}


def _rows(n=900):
    return [_row(i) for i in range(n)]


def _fold(fid, **ov):
    base = {
        "fold_id": fid, "n_train": 400, "n_test": 200,
        "baseline_logloss": 0.995, "experimental_logloss": 0.996, "delta_logloss": 0.001,
        "baseline_brier": 0.198, "experimental_brier": 0.198, "delta_brier": 0.0,
        "baseline_penca": 2.50, "experimental_penca": 2.50, "delta_penca": 0.0,
        "baseline_tail4": 0.030, "experimental_tail4": 0.030, "delta_tail4": 0.0,
        "baseline_tail5": 0.034, "experimental_tail5": 0.020, "delta_tail5": -0.014,
        "baseline_tail6": 0.022, "experimental_tail6": 0.022, "delta_tail6": 0.0,
        "baseline_draw_error": 0.01, "experimental_draw_error": 0.01, "delta_draw_error": 0.0,
    }
    base.update(ov)
    return base


def _improving_folds(n=8):
    return [_fold(i + 1) for i in range(n)]


class TestFoldsAndOutputs(unittest.TestCase):
    def test_same_folds_as_f04(self):
        # Mismos parámetros que F0.4 y mismos splits sobre las mismas filas.
        self.assertEqual((FOLD_SCHEME, FOLD_MIN_TRAIN, FOLD_STEP), ("expanding", 400, 200))
        rows = _rows(900)
        f_ref = list(temporal_folds(rows, scheme="expanding", min_train=400, step=200))
        f_used = list(temporal_folds(rows, scheme=FOLD_SCHEME, min_train=FOLD_MIN_TRAIN, step=FOLD_STEP))
        self.assertEqual([(len(tr), len(te)) for tr, te in f_ref],
                         [(len(tr), len(te)) for tr, te in f_used])
        self.assertEqual([[r["match_id"] for r in te] for _, te in f_ref],
                         [[r["match_id"] for r in te] for _, te in f_used])

    def test_fold_outputs_have_required_columns(self):
        rows = _rows(900)
        obs_by_id = {r["match_id"]: r for r in rows}

        def metrics(test_obs):
            return {"logloss": 1.0, "brier": 0.2, "penca_avg": 2.5, "tail_err_4": 0.03,
                    "tail_err_5": 0.03, "tail_err_6": 0.02, "draw_error": 0.01}

        fold_rows = run_tail_walkforward(rows, obs_by_id=obs_by_id,
                                         baseline_metrics_fn=metrics, experimental_metrics_fn=metrics)
        self.assertTrue(fold_rows)
        self.assertEqual(set(fold_rows[0].keys()), set(FOLD_COLUMNS))

    def test_tail_metrics_present_per_fold(self):
        f = _fold(1)
        for k in ("baseline_tail4", "experimental_tail4", "delta_tail4",
                  "baseline_tail5", "experimental_tail5", "delta_tail5",
                  "baseline_tail6", "experimental_tail6", "delta_tail6"):
            self.assertIn(k, f)


class TestWalkforwardGate(unittest.TestCase):
    def test_gate_requires_majority_fold_improvement(self):
        # 7/8 mejoran -> activate.
        folds = _improving_folds(8)
        self.assertEqual(decide_tail_walkforward(folds)["decision"], "activate")
        # Solo 2/8 mejoran -> keep_off.
        few = [_fold(i + 1, experimental_tail5=0.040, delta_tail5=0.006) for i in range(6)] + \
              [_fold(7), _fold(8)]
        self.assertEqual(decide_tail_walkforward(few)["decision"], "keep_off")

    def test_gate_blocks_if_logloss_worse(self):
        folds = [_fold(i + 1, experimental_logloss=0.995 + 0.02, delta_logloss=0.02) for i in range(8)]
        self.assertEqual(decide_tail_walkforward(folds)["decision"], "keep_off")

    def test_gate_blocks_if_penca_worse(self):
        folds = [_fold(i + 1, experimental_penca=2.40, delta_penca=-0.10) for i in range(8)]
        self.assertEqual(decide_tail_walkforward(folds)["decision"], "keep_off")

    def test_no_2026_data_used(self):
        # El splitting solo usa las filas provistas (orden por fecha); función pura.
        rows = _rows(900)
        f1 = list(temporal_folds(rows, scheme="expanding", min_train=400, step=200))
        f2 = list(temporal_folds(rows, scheme="expanding", min_train=400, step=200))
        self.assertEqual([[r["match_id"] for r in te] for _, te in f1],
                         [[r["match_id"] for r in te] for _, te in f2])
        self.assertNotIn("year", decide_tail_walkforward.__code__.co_varnames)

    def test_production_flag_remains_off(self):
        # La intervención NO está cableada en el motor de goles de producción.
        src = EXPECTED_GOALS_SRC.read_text(encoding="utf-8").lower()
        self.assertNotIn("tail_reweight", src)
        self.assertNotIn("interventions", src)


if __name__ == "__main__":
    unittest.main()
