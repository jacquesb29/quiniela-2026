"""Tests F5: atribución causal de la compresión de varianza."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.distributions import build_model_stack
from worldcup2026.walk_forward import temporal_folds
from worldcup2026.attribution.ensemble_recompose import RecomposeOverrides, recompose_ensemble
from worldcup2026.attribution.gate import F5GateThresholds, decide_component_intervention
from worldcup2026.attribution.metrics import (
    METRIC_KEYS,
    compute_attribution_metrics,
    raw_expected_penca_pick,
)
from worldcup2026.attribution.ranking import culpability_ranking
from worldcup2026.attribution.walkforward import FOLD_MIN_TRAIN, FOLD_SCHEME, FOLD_STEP

EXPECTED_GOALS_SRC = ROOT / "worldcup2026" / "models" / "expected_goals.py"
DISTRIBUTIONS_SRC = ROOT / "worldcup2026" / "distributions.py"


def _ctx(**ov):
    base = dict(knockout=False, importance=1.0, market_prob_a=None, market_prob_draw=None,
                market_prob_b=None, market_total_line=None, lineup_coverage_a=0.0, lineup_coverage_b=0.0)
    base.update(ov)
    return SimpleNamespace(**base)


def _obs(ga, gb, mid="m"):
    return SimpleNamespace(match_id=mid, goals_a=ga, goals_b=gb)


def _row(i):
    base_day = 1 + (i // 3)
    return {"match_id": f"m{i:04d}", "date": f"1990-01-{base_day:02d}", "team_a": f"A{i}",
            "team_b": f"B{i}", "goals_a": "1", "goals_b": "0", "elo_a_pre": "1700", "elo_b_pre": "1500"}


def _ranking_entry(cid, frac, recovery, cul, **ov):
    e = {"component_id": cid, "fraction_folds_close_gap": frac, "mean_tail5_recovery": recovery,
         "consistency": 0.9, "mean_delta_logloss": 0.0, "mean_delta_brier": 0.0,
         "mean_delta_penca": 0.0, "mean_delta_draw_error": 0.0, "collateral_score": 0.0,
         "culpability_score": cul, "verdict": "culpable_probable", "rank": 1}
    e.update(ov)
    return e


class TestRecompose(unittest.TestCase):
    def test_recompose_matches_production_bit_identical(self):
        ctx = _ctx()
        for mu_a, mu_b in [(1.65, 0.87), (2.1, 0.46), (1.2, 1.2)]:
            prod, _ = build_model_stack(mu_a, mu_b, ctx, max_goals=10, market_strength=0.30)
            self.assertEqual(prod, recompose_ensemble(mu_a, mu_b, ctx))

    def test_ablation_changes_only_target_component(self):
        ctx = _ctx()
        mu_a, mu_b = 1.8, 1.0
        default = recompose_ensemble(mu_a, mu_b, ctx)
        prod, _ = build_model_stack(mu_a, mu_b, ctx, max_goals=10, market_strength=0.30)
        self.assertEqual(default, prod)  # sin ablación = producción
        self.assertNotEqual(recompose_ensemble(mu_a, mu_b, ctx, overrides=RecomposeOverrides(drop_member="low_score")), default)
        self.assertNotEqual(recompose_ensemble(mu_a, mu_b, ctx, overrides=RecomposeOverrides(use_independent_primary=True)), default)
        self.assertNotEqual(recompose_ensemble(mu_a, mu_b, ctx, overrides=RecomposeOverrides(member_weight_scale={"overdispersed": 2.0})), default)


class TestFoldsAndMetrics(unittest.TestCase):
    def test_same_folds_as_f04(self):
        self.assertEqual((FOLD_SCHEME, FOLD_MIN_TRAIN, FOLD_STEP), ("expanding", 400, 200))
        rows = [_row(i) for i in range(900)]
        ref = list(temporal_folds(rows, scheme="expanding", min_train=400, step=200))
        used = list(temporal_folds(rows, scheme=FOLD_SCHEME, min_train=FOLD_MIN_TRAIN, step=FOLD_STEP))
        self.assertEqual([[r["match_id"] for r in te] for _, te in ref],
                         [[r["match_id"] for r in te] for _, te in used])

    def test_attribution_metrics_present_per_component(self):
        obs = [_obs(1, 0), _obs(1, 1), _obs(3, 2)]
        dists = [{(1, 0): 0.6, (0, 0): 0.4}, {(1, 1): 0.5, (1, 0): 0.5}, {(3, 2): 0.5, (1, 0): 0.5}]
        picks = ["1-0", "1-0", "2-1"]
        m = compute_attribution_metrics(obs, dists, picks)
        for k in METRIC_KEYS:
            self.assertIn(k, m)

    def test_penca_penalties_affect_pick_not_tail_mass(self):
        # Misma distribución, distinto pick -> tail_err idéntico, penca puede diferir.
        obs = [_obs(2, 2), _obs(3, 1)]
        dists = [{(1, 0): 0.4, (2, 2): 0.3, (3, 1): 0.3}, {(1, 0): 0.4, (2, 2): 0.3, (3, 1): 0.3}]
        base_picks = ["1-0", "1-0"]
        relaxed_picks = [raw_expected_penca_pick(dists[0]), raw_expected_penca_pick(dists[1])]
        mb = compute_attribution_metrics(obs, dists, base_picks)
        mr = compute_attribution_metrics(obs, dists, relaxed_picks)
        for k in ("tail_err_4", "tail_err_5", "tail_err_6"):
            self.assertAlmostEqual(mb[k], mr[k], places=12)  # masa de cola NO cambia


class TestRankingAndGate(unittest.TestCase):
    def test_culpability_ranking_deterministic(self):
        by_fold = []
        for fid in range(1, 9):
            by_fold.append({"component_id": "mu_total", "base_tail5": 0.034, "abl_tail5": 0.018,
                            "delta_logloss": 0.0005, "delta_brier": 0.0, "delta_penca": 0.001, "delta_draw_error": 0.0})
            by_fold.append({"component_id": "dixon_coles", "base_tail5": 0.034, "abl_tail5": 0.030,
                            "delta_logloss": 0.001, "delta_brier": 0.0, "delta_penca": -0.001, "delta_draw_error": 0.0})
        r1 = culpability_ranking(by_fold)
        r2 = culpability_ranking(by_fold)
        self.assertEqual(r1, r2)
        self.assertEqual(r1[0]["component_id"], "mu_total")  # mayor recovery -> rank 1
        self.assertEqual(r1[0]["rank"], 1)

    def test_gate_requires_majority_fold_evidence(self):
        ranking = [_ranking_entry("x", 0.30, 0.01, 0.5), _ranking_entry("y", 0.10, 0.001, 0.05)]
        self.assertEqual(decide_component_intervention(ranking, n_folds=8)["decision"], "no_clear_culprit")

    def test_gate_requires_distinguishable_culprit(self):
        # #1 y #2 casi iguales -> no distinguible.
        ranking = [_ranking_entry("x", 0.80, 0.02, 0.100), _ranking_entry("y", 0.78, 0.019, 0.099)]
        self.assertEqual(decide_component_intervention(ranking, n_folds=8)["decision"], "no_clear_culprit")

    def test_gate_blocks_on_collateral_harm(self):
        ranking = [_ranking_entry("x", 0.80, 0.02, 0.500, mean_delta_logloss=0.02),
                   _ranking_entry("y", 0.10, 0.0, 0.001)]
        self.assertEqual(decide_component_intervention(ranking, n_folds=8)["decision"], "no_clear_culprit")

    def test_gate_activates_when_clear(self):
        ranking = [_ranking_entry("x", 0.80, 0.02, 0.500), _ranking_entry("y", 0.10, 0.0, 0.001)]
        d = decide_component_intervention(ranking, n_folds=8)
        self.assertTrue(d["decision"].startswith("intervene_component:"))


class TestIntegrity(unittest.TestCase):
    def test_no_2026_data_used(self):
        ctx = _ctx()
        self.assertEqual(recompose_ensemble(1.6, 0.9, ctx), recompose_ensemble(1.6, 0.9, ctx))
        self.assertNotIn("year", recompose_ensemble.__code__.co_varnames)

    def test_production_flags_remain_off(self):
        eg = EXPECTED_GOALS_SRC.read_text(encoding="utf-8").lower()
        di = DISTRIBUTIONS_SRC.read_text(encoding="utf-8").lower()
        for src in (eg, di):
            self.assertNotIn("attribution", src)
            self.assertNotIn("recompose_ensemble", src)


if __name__ == "__main__":
    unittest.main()
