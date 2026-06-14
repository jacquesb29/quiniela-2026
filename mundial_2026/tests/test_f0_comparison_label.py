"""Tests F0.3 (comparación pareada) y F0.5 (candado de etiqueta de validación)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.validation_compare import (  # noqa: E402
    market_coverage_summary,
    paired_benchmark_comparison,
)
from worldcup2026.validation_label import (  # noqa: E402
    LABEL_NO_SUPERADO,
    LABEL_PENDIENTE,
    LABEL_PROVISIONAL,
    LABEL_UTILIZABLE,
    LABEL_VALIDADO,
    ValidationVerdict,
    assert_no_unbacked_validado,
    validation_label,
)


def _model_row(mid, brier, logloss):
    return {"match_id": mid, "brier_score": brier, "log_loss": logloss}


def _bench_row(mid, benchmark, brier, logloss):
    return {"match_id": mid, "benchmark": benchmark, "brier_score": brier,
            "log_loss": logloss, "actual_outcome": "a"}


class TestPairedComparisonF03(unittest.TestCase):
    def test_market_paired_only_where_market_exists(self):
        model = [_model_row(i, 0.2, 1.0) for i in range(1, 6)]
        # mercado_puro solo en 2 partidos; elo_puro en los 5.
        bench = [_bench_row(i, "elo_puro", 0.21, 1.05) for i in range(1, 6)]
        bench += [_bench_row(i, "mercado_puro", 0.19, 0.95) for i in (2, 4)]
        rows = paired_benchmark_comparison(model, bench, baselines=("elo_puro", "mercado_puro"))
        by = {r["baseline"]: r for r in rows}
        self.assertEqual(by["elo_puro"]["n_paired"], 5)
        self.assertEqual(by["mercado_puro"]["n_paired"], 2)  # solo donde hay mercado

    def test_beats_flag_consistency(self):
        model = [_model_row(i, 0.20, 0.90) for i in range(1, 40)]
        bench = [_bench_row(i, "elo_puro", 0.21, 1.00) for i in range(1, 40)]
        rows = paired_benchmark_comparison(model, bench, baselines=("elo_puro",))
        row = rows[0]
        self.assertEqual(row["beats"], row["delta_logloss"] < 0.0)
        self.assertTrue(row["beats"])  # 0.90 < 1.00
        # Caso inverso: modelo peor.
        model_bad = [_model_row(i, 0.30, 1.20) for i in range(1, 40)]
        rows_bad = paired_benchmark_comparison(model_bad, bench, baselines=("elo_puro",))
        self.assertFalse(rows_bad[0]["beats"])
        self.assertEqual(rows_bad[0]["beats"], rows_bad[0]["delta_logloss"] < 0.0)

    def test_no_cross_population_comparison(self):
        # Modelo en {1,2,3}; baseline en {2,3,4}. Pareo debe ser {2,3}.
        model = [_model_row(1, 0.10, 0.50), _model_row(2, 0.20, 1.00), _model_row(3, 0.20, 1.00)]
        bench = [_bench_row(2, "elo_puro", 0.30, 1.40), _bench_row(3, "elo_puro", 0.30, 1.40),
                 _bench_row(4, "elo_puro", 0.99, 9.9)]
        rows = paired_benchmark_comparison(model, bench, baselines=("elo_puro",))
        row = rows[0]
        self.assertEqual(row["n_paired"], 2)
        # Las medias se calculan SOLO sobre {2,3}, no sobre toda la población.
        self.assertAlmostEqual(row["model_logloss"], 1.00, places=9)
        self.assertAlmostEqual(row["baseline_logloss"], 1.40, places=9)

    def test_market_zero_coverage_marked_sin_muestra(self):
        model = [_model_row(i, 0.2, 1.0) for i in range(1, 6)]
        bench = [_bench_row(i, "elo_puro", 0.21, 1.05) for i in range(1, 6)]  # sin mercado
        cov = market_coverage_summary(bench)
        self.assertEqual(cov["n_with_market"], 0)
        self.assertFalse(cov["has_market_sample"])
        rows = paired_benchmark_comparison(model, bench, baselines=("mercado_puro",))
        self.assertEqual(rows[0]["comparison_status"], "sin_muestra")
        self.assertNotEqual(rows[0]["comparison_status"], "medido_no_superado")


class TestValidationLabelF05(unittest.TestCase):
    def test_no_validado_when_below_baseline(self):
        verdict = validation_label(
            n=1930, model_logloss=1.10,
            baseline_logloss={"poisson_simple": 1.00, "elo_puro": 1.01},
            out_of_sample=True, leakage_warning=False,
        )
        self.assertEqual(verdict.label, LABEL_NO_SUPERADO)
        self.assertNotEqual(verdict.label, LABEL_VALIDADO)

    def test_no_validado_low_n(self):
        verdict = validation_label(
            n=10, model_logloss=0.50,
            baseline_logloss={"poisson_simple": 1.00},
            out_of_sample=True, leakage_warning=False,
        )
        self.assertEqual(verdict.label, LABEL_PENDIENTE)

    def test_validado_only_when_all_conditions_met(self):
        base = dict(n=1930, model_logloss=0.99,
                    baseline_logloss={"poisson_simple": 1.00}, out_of_sample=True,
                    leakage_warning=False)
        self.assertEqual(validation_label(**base).label, LABEL_VALIDADO)
        # Romper cada condición -> deja de ser validado.
        self.assertEqual(validation_label(**{**base, "leakage_warning": True}).label, LABEL_UTILIZABLE)
        self.assertEqual(validation_label(**{**base, "n": 300}).label, LABEL_UTILIZABLE)
        self.assertEqual(validation_label(**{**base, "out_of_sample": False}).label, LABEL_PROVISIONAL)
        self.assertEqual(
            validation_label(**{**base, "model_logloss": 1.20}).label, LABEL_NO_SUPERADO
        )

    def test_dashboard_html_has_no_unbacked_validado(self):
        non_validado = ValidationVerdict(
            label=LABEL_UTILIZABLE, reason="test", n=1930,
            beats_baselines=True, out_of_sample=True, leakage_warning=True,
        )
        # HTML que afirma fuerte sin respaldo -> debe fallar.
        with self.assertRaises(AssertionError):
            assert_no_unbacked_validado("<p>El modelo validado supera todo</p>", non_validado)
        # HTML neutral -> no falla.
        assert_no_unbacked_validado("<p>Medido, no superado; lectura provisional.</p>", non_validado)
        # Si la etiqueta ES validado, la frase está permitida.
        validado = ValidationVerdict(
            label=LABEL_VALIDADO, reason="ok", n=1930,
            beats_baselines=True, out_of_sample=True, leakage_warning=False,
        )
        assert_no_unbacked_validado("<p>modelo validado fuera de muestra</p>", validado)
        # Dashboard real publicado: con el veredicto actual no debe afirmar 'validado'.
        dashboard = ROOT / "dashboard_actual_2026.html"
        if dashboard.exists():
            assert_no_unbacked_validado(dashboard.read_text(encoding="utf-8"), non_validado)

    def test_label_matches_metrics(self):
        # beats_baselines refleja model_logloss < mejor baseline comparable.
        v_beats = validation_label(
            n=600, model_logloss=0.90, baseline_logloss={"x": 1.0},
            out_of_sample=True, leakage_warning=True,
        )
        self.assertTrue(v_beats.beats_baselines)
        v_lose = validation_label(
            n=600, model_logloss=1.10, baseline_logloss={"x": 1.0},
            out_of_sample=True, leakage_warning=True,
        )
        self.assertFalse(v_lose.beats_baselines)
        # n y flags se propagan al veredicto.
        self.assertEqual(v_beats.n, 600)
        self.assertTrue(v_beats.out_of_sample)


if __name__ == "__main__":
    unittest.main()
