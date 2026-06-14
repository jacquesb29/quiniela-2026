"""Tests F3: auditoría estructural de distribución de marcadores."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.audit.exact_score import EXACT_COLUMNS, exact_score_audit
from worldcup2026.audit.gate import f3_decision
from worldcup2026.audit.goals import GOAL_COLUMNS, TAIL_COLUMNS, goal_calibration, tail_audit
from worldcup2026.audit.penca import PENCA_COLUMNS, penca_audit
from worldcup2026.audit.scoreline import (
    DRAW_COLUMNS,
    SCORE_COLUMNS,
    MatchObservation,
    draw_audit,
    favorite_bucket,
    score_distribution_audit,
)


def _dist(*pairs):
    # pairs: ((a,b),p) ... normalizada para sumar 1.
    d = {k: p for k, p in pairs}
    s = sum(d.values())
    return {k: v / s for k, v in d.items()} if s else d


def _obs(match_id, ga, gb, elo_diff, dist, win_a=0.5, draw=0.27, win_b=0.23,
         eg_a=1.5, eg_b=1.1, penca="1-0", penca_exp=2.5):
    return MatchObservation(match_id=match_id, goals_a=ga, goals_b=gb, elo_diff=elo_diff,
                            model_dist=dist, win_a=win_a, draw=draw, win_b=win_b,
                            eg_a=eg_a, eg_b=eg_b, penca_score=penca, penca_expected_points=penca_exp)


def _penca_8_5_3(pick, actual):
    pa, pb = (int(x) for x in str(pick).split("-"))
    aa, ab = (int(x) for x in str(actual).split("-"))
    if (pa, pb) == (aa, ab):
        return 8.0
    if pa - pb == aa - ab:
        return 5.0
    if (pa > pb) == (aa > ab) and (pa == pb) == (aa == ab):
        return 3.0
    return 0.0


def _sample():
    d = _dist(((1, 0), 0.30), ((0, 0), 0.20), ((1, 1), 0.20), ((2, 1), 0.15), ((2, 0), 0.15))
    return [
        _obs("m1", 1, 0, 200, d),
        _obs("m2", 1, 1, 30, d),
        _obs("m3", 0, 0, 100, d),
        _obs("m4", 2, 1, 150, d),
    ]


class TestScoreAndDraw(unittest.TestCase):
    def test_observed_and_predicted_frequencies_sum_to_one(self):
        rows = score_distribution_audit(_sample())
        self.assertAlmostEqual(sum(float(r["observed_freq"]) for r in rows), 1.0, places=6)
        self.assertAlmostEqual(sum(float(r["predicted_freq"]) for r in rows), 1.0, places=6)
        self.assertEqual(set(SCORE_COLUMNS), set(rows[0].keys()))

    def test_favorite_bucket_classification(self):
        self.assertEqual(favorite_bucket(10), "parejo")
        self.assertEqual(favorite_bucket(80), "favorito_leve")
        self.assertEqual(favorite_bucket(150), "favorito_medio")
        self.assertEqual(favorite_bucket(300), "favorito_fuerte")

    def test_draw_subestimation_detected(self):
        # 50% empates reales, pero el modelo predice draw=0.27 -> subestima.
        d = _dist(((1, 0), 0.5), ((1, 1), 0.5))
        obs = [_obs("a", 1, 1, 20, d, draw=0.27), _obs("b", 0, 0, 20, d, draw=0.27),
               _obs("c", 1, 0, 20, d, draw=0.27), _obs("d", 2, 1, 20, d, draw=0.27)]
        rows = {r["bucket"]: r for r in draw_audit(obs)}
        self.assertEqual(rows["global"]["verdict"], "subestima_empates")
        self.assertEqual(set(DRAW_COLUMNS), set(rows["global"].keys()))


class TestGoalsAndTails(unittest.TestCase):
    def test_tail_audit_matches_distribution(self):
        d = _dist(((3, 2), 0.5), ((1, 0), 0.5))  # 50% de masa en total>=4 (3-2)
        obs = [_obs("a", 3, 2, 0, d), _obs("b", 1, 0, 0, d)]
        rows = {r["threshold"]: r for r in tail_audit(obs)}
        self.assertAlmostEqual(float(rows["total>=4"]["predicted_rate"]), 0.5, places=6)
        self.assertAlmostEqual(float(rows["total>=4"]["observed_rate"]), 0.5, places=6)
        self.assertEqual(set(TAIL_COLUMNS), set(rows["total>=4"].keys()))
        # goal_calibration columnas
        grow = goal_calibration(obs)[0]
        self.assertEqual(set(GOAL_COLUMNS), set(grow.keys()))


class TestExactAndPenca(unittest.TestCase):
    def test_exact_score_hit_rate_and_coverage(self):
        rows = exact_score_audit(_sample(), ns=(1, 3, 5))
        by = {r["top_n"]: r for r in rows}
        # cobertura crece con N y está en [0,1]; hit_rate en [0,1].
        self.assertLessEqual(by[1]["mean_probability_coverage"], by[5]["mean_probability_coverage"])
        for r in rows:
            self.assertGreaterEqual(r["exact_hit_rate"], 0.0)
            self.assertLessEqual(r["exact_hit_rate"], 1.0)
        self.assertEqual(set(EXACT_COLUMNS), set(rows[0].keys()))

    def test_penca_audit_uses_8_5_3(self):
        d = _dist(((1, 0), 1.0))
        obs = [_obs("a", 1, 0, 100, d, penca="1-0", penca_exp=2.5)]  # exacto -> 8
        rows = {r["bucket"]: r for r in penca_audit(obs, _penca_8_5_3)}
        self.assertEqual(rows["global"]["mean_realized_penca"], 8.0)
        self.assertEqual(set(PENCA_COLUMNS), set(rows["global"].keys()))


class TestGateAndIntegrity(unittest.TestCase):
    def test_f3_gate_thresholds(self):
        g = f3_decision(n=1000, draw_error_global=0.05, fav_pred_rate=0.60, fav_obs_rate=0.50,
                        total_goals_bias=-0.30, score_tv_distance=0.10,
                        max_tail_underprediction=0.05, penca_gap_global=0.20)
        self.assertTrue(g["subestima_empates"])
        self.assertTrue(g["sobreestima_favoritos"])
        self.assertTrue(g["goles_mal_calibrados"])
        self.assertTrue(g["subestima_colas"])
        self.assertTrue(g["optimismo_penca"])
        self.assertTrue(g["vale_la_pena_intervenir"])
        # Todo calibrado -> nada que intervenir.
        clean = f3_decision(n=1000, draw_error_global=0.0, fav_pred_rate=0.5, fav_obs_rate=0.5,
                            total_goals_bias=0.0, score_tv_distance=0.0,
                            max_tail_underprediction=0.0, penca_gap_global=0.0)
        self.assertFalse(clean["vale_la_pena_intervenir"])
        self.assertEqual(clean["suggested_priority"], "ninguna")
        # Muestra insuficiente -> no intervenir aunque haya señal.
        small = f3_decision(n=10, draw_error_global=0.10, fav_pred_rate=0.6, fav_obs_rate=0.5,
                            total_goals_bias=0.0, score_tv_distance=0.0,
                            max_tail_underprediction=0.0, penca_gap_global=0.0)
        self.assertFalse(small["vale_la_pena_intervenir"])

    def test_no_future_results_used(self):
        # Cambiar el resultado observado NO altera la frecuencia PREDICHA (la predicción
        # no depende de los goles reales del partido).
        base = _sample()
        pred_before = [r["predicted_freq"] for r in score_distribution_audit(base)]
        mutated = [copy.replace(o, goals_a=5, goals_b=5) if hasattr(copy, "replace")
                   else o for o in base]
        # Fallback para Python sin copy.replace: reconstruir con goles distintos.
        import dataclasses
        mutated = [dataclasses.replace(o, goals_a=5, goals_b=5) for o in base]
        pred_after = [r["predicted_freq"] for r in score_distribution_audit(mutated)]
        self.assertEqual(pred_before, pred_after)

    def test_audit_csvs_have_required_columns(self):
        sample = _sample()
        self.assertEqual(set(SCORE_COLUMNS), set(score_distribution_audit(sample)[0].keys()))
        self.assertEqual(set(DRAW_COLUMNS), set(draw_audit(sample)[0].keys()))
        self.assertEqual(set(GOAL_COLUMNS), set(goal_calibration(sample)[0].keys()))
        self.assertEqual(set(TAIL_COLUMNS), set(tail_audit(sample)[0].keys()))
        self.assertEqual(set(EXACT_COLUMNS), set(exact_score_audit(sample)[0].keys()))
        self.assertEqual(set(PENCA_COLUMNS), set(penca_audit(sample, _penca_8_5_3)[0].keys()))

    def test_audit_is_read_only(self):
        sample = _sample()
        before = copy.deepcopy([(o.match_id, o.goals_a, o.goals_b, dict(o.model_dist)) for o in sample])
        score_distribution_audit(sample)
        draw_audit(sample)
        goal_calibration(sample)
        tail_audit(sample)
        exact_score_audit(sample)
        penca_audit(sample, _penca_8_5_3)
        after = [(o.match_id, o.goals_a, o.goals_b, dict(o.model_dist)) for o in sample]
        self.assertEqual(before, after)  # no muta las observaciones


if __name__ == "__main__":
    unittest.main()
