"""Tests de reproducibilidad del fix de caché mutable (worldcup2026/distributions.py).

Garantizan que `predict_match` es determinista para la misma entrada, que el
orden de partidos no contamina una predicción, que limpiar o no el caché da el
mismo resultado, que ninguna función cacheada expone un mutable compartido, y
que el backtest ya no necesita forzar caché frío.
"""

from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Importar el adaptador instala los shims neutrales y NO limpia caché (el
# workaround se eliminó tras el fix). Sirve para el test del backtest.
import backtest_production_adapter as adapter  # noqa: E402
import modelo_quiniela_2026 as model  # noqa: E402
import worldcup2026.distributions as D  # noqa: E402

HISTORICAL_CSV = ROOT / "data" / "historical_matches.csv"


def _teams_ctx(elo_a: float, elo_b: float):
    name_a, name_b = "__rt_a__X", "__rt_b__Y"
    team_a = model.Team(name=name_a, confederation="UEFA", status="qualified", elo=elo_a, fifa_points=None)
    team_b = model.Team(name=name_b, confederation="UEFA", status="qualified", elo=elo_b, fifa_points=None)
    return {name_a: team_a, name_b: team_b}, name_a, name_b, model.MatchContext(neutral=True)


def _triple(prediction):
    return (
        round(prediction.win_a, 12),
        round(prediction.draw, 12),
        round(prediction.win_b, 12),
        tuple((s, round(p, 12)) for s, p in prediction.exact_scores),
    )


def _clear_distribution_caches():
    for name in dir(D):
        obj = getattr(D, name)
        cache_clear = getattr(obj, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


class TestCacheReproducibility(unittest.TestCase):
    def test_predict_match_same_input_five_times_identical(self):
        teams, na, nb, ctx = _teams_ctx(1800, 1500)
        results = [_triple(model.predict_match(teams, na, nb, ctx)) for _ in range(5)]
        self.assertEqual(len(set(results)), 1, f"predict_match no determinista: {set(results)}")

    def test_match_order_does_not_change_prediction(self):
        teams, na, nb, ctx = _teams_ctx(1800, 1500)
        first = _triple(model.predict_match(teams, na, nb, ctx))
        # Predecir otros partidos (distintos mu) entre medias no debe alterar X.
        for elo_a, elo_b in [(1200, 2000), (1500, 1500), (2100, 1300), (1700, 1650)]:
            t2, a2, b2, c2 = _teams_ctx(elo_a, elo_b)
            model.predict_match(t2, a2, b2, c2)
        again = _triple(model.predict_match(teams, na, nb, ctx))
        self.assertEqual(first, again)

    def test_clear_and_no_clear_same_result(self):
        teams, na, nb, ctx = _teams_ctx(1850, 1480)
        r_no_clear = _triple(model.predict_match(teams, na, nb, ctx))
        _clear_distribution_caches()
        r_clear = _triple(model.predict_match(teams, na, nb, ctx))
        self.assertEqual(r_no_clear, r_clear)

    def test_no_cached_function_returns_shared_mutable(self):
        builders = [
            ("score_distribution", lambda: D.score_distribution(1.7, 1.1, max_goals=7)),
            ("independent_score_distribution", lambda: D.independent_score_distribution(1.7, 1.1, max_goals=7)),
            ("overdispersed_score_distribution", lambda: D.overdispersed_score_distribution(1.7, 1.1, None, max_goals=7)),
            ("low_score_adjusted_distribution", lambda: D.low_score_adjusted_distribution(1.7, 1.1, None, max_goals=7)),
            ("cached_low_score_distribution", lambda: D.cached_low_score_distribution(34, 22, -3, 7)),
        ]
        for label, build in builders:
            first = build()
            second = build()
            self.assertIsNot(first, second, f"{label} devuelve el MISMO objeto (mutable compartido)")
            key = next(iter(first))
            sentinel = 987654.0
            first[key] = sentinel  # mutación del caller
            third = build()
            self.assertNotEqual(third.get(key), sentinel, f"{label}: la mutación del caller contaminó el caché")

    def test_backtest_reproducible_without_cache_clear(self):
        with HISTORICAL_CSV.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        target = rows[10]
        first = _triple(adapter.production_prediction_fn(target))
        # Intercalar otros partidos SIN limpiar caché (el adaptador ya no lo hace).
        for other in rows[20:26]:
            adapter.production_prediction_fn(other)
        again = _triple(adapter.production_prediction_fn(target))
        self.assertEqual(first, again)


if __name__ == "__main__":
    unittest.main()
