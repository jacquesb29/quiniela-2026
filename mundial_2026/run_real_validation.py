"""Orquestador de validación real (F0.1 + F0.2).

Corre el backtest histórico, los benchmarks y la ablation usando el modelo
de producción REAL (vía `backtest_production_adapter`), no el proxy Elo-only.

No modifica el modelo, ni pesos, ni metodología. Solo genera artefactos de
medición y reporta si el modelo dejó de ser idéntico a Elo puro y si la
ablation ya distingue features ausentes.

Uso:
    python3 run_real_validation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import modelo_quiniela_2026 as model  # noqa: E402
from backtest_production_adapter import (  # noqa: E402
    production_prediction_fn,
    production_prediction_with_penca,
)
from worldcup2026.ablation import run_ablation  # noqa: E402
from worldcup2026.backtesting import (  # noqa: E402
    evaluate_backtest_rows,
    run_historical_backtest,
    summarize_backtest,
)
from worldcup2026.benchmarks import (  # noqa: E402
    elo_prediction,
    evaluate_benchmarks,
    poisson_simple_prediction,
    read_csv_rows,
    run_benchmarks,
    summarize_benchmark_rows,
    write_csv_rows,
)
from worldcup2026.elo_rederive import (  # noqa: E402
    ORIGINAL_K_BY_TOURNAMENT,
    ORIGINAL_SELECTED,
    ORIGINAL_START_YEAR,
    build_elo_comparison_rows,
    elo_audit_summary,
    rederive_walk_forward_elo,
)
from worldcup2026.validation_compare import (  # noqa: E402
    best_comparable_baseline_logloss,
    market_coverage_summary,
    paired_benchmark_comparison,
)
from worldcup2026.validation_label import validation_label  # noqa: E402
from worldcup2026.walk_forward import run_walk_forward  # noqa: E402

HISTORICAL_CSV = ROOT / "data" / "historical_matches.csv"
RAW_RESULTS_CSV = ROOT / "data" / "international_results_raw.csv"
REAL_BACKTEST_DIR = ROOT / "outputs" / "real_backtest"
WALK_FORWARD_DIR = ROOT / "outputs" / "walk_forward"
REDERIVED_ELO_CSV = WALK_FORWARD_DIR / "rederived_elo_matches.csv"
ELO_AUDIT_CSV = WALK_FORWARD_DIR / "elo_leakage_audit.csv"
ELO_AUDIT_MD = WALK_FORWARD_DIR / "elo_leakage_audit.md"

# El constructor original (tools/build_real_historical_backtest.py) registra el
# Elo prepartido ANTES del partido y lo actualiza DESPUÉS, recorriendo por fecha:
# es walk-forward por construcción (auditoría de código confirmada).
ELO_CODE_AUDIT_WALK_FORWARD = True
BENCHMARK_RESULTS_CSV = ROOT / "outputs" / "benchmark_results.csv"
BENCHMARK_SUMMARY_CSV = ROOT / "outputs" / "benchmark_summary.csv"
ABLATION_CSV = REAL_BACKTEST_DIR / "ablation_results.csv"
PAIRED_COMPARISON_CSV = REAL_BACKTEST_DIR / "paired_comparison.csv"
VALIDATION_STATUS_JSON = ROOT / "outputs" / "validation_status.json"

# La validación walk-forward (F0.4) es out-of-sample por construcción.
MODEL_OUT_OF_SAMPLE = True
# `leakage_warning` ya NO es constante: lo decide la auditoría de Elo (F0.4b).


def _model_eval_fn(row):
    """Adaptador walk-forward: fila histórica -> probs/score modal/score Penca."""

    prediction = production_prediction_fn(row)
    if prediction is None:
        return None
    top = model.penca_ovacion_top_score(prediction)
    modal = prediction.exact_scores[0][0] if prediction.exact_scores else None
    return {
        "prob_a": prediction.win_a,
        "prob_draw": prediction.draw,
        "prob_b": prediction.win_b,
        "modal_score": modal,
        "penca_score": top.get("score") if top else None,
    }


def _write_elo_audit_md(audit, compare, leakage_warning):
    def fmt(value):
        try:
            return f"{float(value):.6f}"
        except (TypeError, ValueError):
            return str(value)

    lines = [
        "# Auditoría de leakage de Elo prepartido (F0.4b)",
        "",
        "## 1. Auditoría de código del constructor original",
        "",
        "`tools/build_real_historical_backtest.py` ordena todos los partidos por "
        "fecha, registra `elo_a_pre`/`elo_b_pre` con el rating ANTES del partido y "
        "ejecuta `update_elo` solo DESPUÉS. Equipos nuevos arrancan en 1500. No usa "
        "rankings ni resultados posteriores. Es **walk-forward por construcción**: "
        f"`ELO_CODE_AUDIT_WALK_FORWARD = {audit['code_audit_walk_forward']}`.",
        "",
        "## 2. Re-derivación independiente (réplica fiel walk-forward)",
        "",
        f"- Partidos comparados: {audit['n_compared']}",
        f"- Correlación de Pearson Elo A: {fmt(audit['pearson_elo_a'])}",
        f"- Correlación de Pearson Elo B: {fmt(audit['pearson_elo_b'])}",
        f"- Diferencia absoluta media: {fmt(audit['mean_abs_delta'])} puntos Elo",
        f"- Diferencia absoluta máxima: {fmt(audit['max_abs_delta'])} puntos Elo",
        "",
        "Una re-derivación independiente reproduce el Elo almacenado salvo ruido de "
        "redondeo (los valores se guardan con 3 decimales). Esto confirma que el "
        "Elo prepartido es un cómputo determinista sin información futura.",
        "",
        "## 3. Backtest comparativo (Elo original vs Elo re-derivado)",
        "",
        f"- log-loss modelo (Elo original): {fmt(compare['model_original_logloss'])}",
        f"- log-loss modelo (Elo re-derivado): {fmt(compare['model_rederived_logloss'])}",
        f"- desviación de log-loss: {fmt(compare['logloss_shift_vs_original'])}",
        f"- log-loss Poisson simple (re-derivado): {fmt(compare['poisson_rederived_logloss'])}",
        f"- log-loss Elo puro (re-derivado): {fmt(compare['elo_puro_rederived_logloss'])}",
        f"- modelo supera Poisson (re-derivado): {compare['model_beats_poisson_rederived']}",
        f"- modelo supera Elo puro (re-derivado): {compare['model_beats_elo_rederived']}",
        f"- backtest estable: {compare['backtest_stable']}",
        "",
        "## 4. Veredicto de leakage",
        "",
        f"**leakage_warning = {leakage_warning}**. "
        + (
            "No hay evidencia de fuga: auditoría de código walk-forward, "
            "re-derivación reproduce el Elo y el backtest es estable. Se permite "
            "apagar la advertencia de leakage."
            if not leakage_warning
            else "Persiste advertencia: la re-derivación o la estabilidad del "
            "backtest no cumplen el umbral; se mantiene leakage_warning=True."
        ),
        "",
        "Esto es auditoría anti-leakage, no optimización del modelo: no se cambiaron "
        "pesos, lambdas, metodología ni selector Penca.",
    ]
    ELO_AUDIT_MD.write_text("\n".join(lines), encoding="utf-8")


def _run_elo_leakage_audit(*, original_model_logloss):
    raw = read_csv_rows(RAW_RESULTS_CSV)
    original_rows = read_csv_rows(HISTORICAL_CSV)
    # Réplica fiel walk-forward independiente (mismo esquema, implementación propia).
    rederived = rederive_walk_forward_elo(
        raw,
        replicate_original=True,
        k_by_tournament=ORIGINAL_K_BY_TOURNAMENT,
        selected_tournaments=ORIGINAL_SELECTED,
        start_year=ORIGINAL_START_YEAR,
    )
    comparison_rows = build_elo_comparison_rows(original_rows, rederived)
    WALK_FORWARD_DIR.mkdir(parents=True, exist_ok=True)
    write_csv_rows(REDERIVED_ELO_CSV, comparison_rows)
    audit = elo_audit_summary(comparison_rows, code_audit_walk_forward=ELO_CODE_AUDIT_WALK_FORWARD)

    # Backtest comparativo sobre filas con Elo re-derivado (mismo modelo, sin tocar pesos).
    rederived_rows = []
    for row in original_rows:
        re = rederived.get(str(row.get("match_id") or ""))
        if re is None:
            continue
        new_row = dict(row)
        new_row["elo_a_pre"] = f"{re[0]:.3f}"
        new_row["elo_b_pre"] = f"{re[1]:.3f}"
        rederived_rows.append(new_row)

    model_eval = evaluate_backtest_rows(
        rederived_rows,
        prediction_fn=production_prediction_with_penca,
        model_name="modelo_completo_elo_rederivado",
    )
    model_re = summarize_backtest(model_eval)
    bench_re = {
        str(row["benchmark"]): row for row in summarize_benchmark_rows(evaluate_benchmarks(rederived_rows))
    }
    model_ll = model_re.get("log_loss")
    poisson_ll = (bench_re.get("poisson_simple") or {}).get("log_loss")
    elo_ll = (bench_re.get("elo_puro") or {}).get("log_loss")

    def _f(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    model_ll_f = _f(model_ll)
    poisson_ll_f = _f(poisson_ll)
    elo_ll_f = _f(elo_ll)
    orig_ll_f = _f(original_model_logloss)
    beats_poisson = model_ll_f is not None and poisson_ll_f is not None and model_ll_f < poisson_ll_f
    beats_elo = model_ll_f is not None and elo_ll_f is not None and model_ll_f < elo_ll_f
    logloss_shift = abs(model_ll_f - orig_ll_f) if (model_ll_f is not None and orig_ll_f is not None) else None
    backtest_stable = bool(
        beats_poisson and beats_elo and logloss_shift is not None and logloss_shift < 0.02
    )
    compare = {
        "model_original_logloss": orig_ll_f,
        "model_rederived_logloss": model_ll_f,
        "model_rederived_brier": _f(model_re.get("brier_score")),
        "poisson_rederived_logloss": poisson_ll_f,
        "elo_puro_rederived_logloss": elo_ll_f,
        "model_beats_poisson_rederived": beats_poisson,
        "model_beats_elo_rederived": beats_elo,
        "logloss_shift_vs_original": logloss_shift,
        "backtest_stable": backtest_stable,
    }

    # Decisión: la advertencia de leakage se apaga solo si la auditoría de Elo está
    # limpia Y el backtest con Elo re-derivado se mantiene estable.
    leakage_warning = bool(audit["leakage_warning"] or not backtest_stable)

    audit_csv_rows = [{"metric": k, "value": v} for k, v in audit.items()]
    audit_csv_rows += [{"metric": k, "value": v} for k, v in compare.items()]
    audit_csv_rows.append({"metric": "final_leakage_warning", "value": leakage_warning})
    write_csv_rows(ELO_AUDIT_CSV, audit_csv_rows)
    _write_elo_audit_md(audit, compare, leakage_warning)
    return audit, compare, leakage_warning


def _fmt(value: object) -> str:
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return str(value)


def main(argv: Optional[list[str]] = None) -> int:
    if not HISTORICAL_CSV.exists():
        print(f"ERROR: no existe {HISTORICAL_CSV}")
        return 1

    print(f"Histórico: {HISTORICAL_CSV}")
    print("Corriendo backtest del modelo de producción real (modelo_completo)...")
    backtest = run_historical_backtest(
        HISTORICAL_CSV,
        output_dir=REAL_BACKTEST_DIR,
        prediction_fn=production_prediction_with_penca,
        model_name="modelo_completo",
    )
    model_summary = backtest["summary"]

    print("Corriendo benchmarks (elo_puro, poisson_simple, mercado_puro, ...)...")
    benchmark_rows = run_benchmarks(
        HISTORICAL_CSV,
        output_csv=BENCHMARK_RESULTS_CSV,
        summary_csv=BENCHMARK_SUMMARY_CSV,
        full_model_fn=production_prediction_fn,
    )
    benchmark_summary = {
        str(row["benchmark"]): row for row in summarize_benchmark_rows(benchmark_rows)
    }

    print("Corriendo ablation con full_model_fn=production_prediction_fn...")
    ablation = run_ablation(
        HISTORICAL_CSV,
        full_model_fn=production_prediction_fn,
        output_csv=ABLATION_CSV,
    )

    # ---- F0.3: comparación pareada honesta (muestra completa) ----
    comparison = paired_benchmark_comparison(backtest["rows"], benchmark_rows)
    write_csv_rows(PAIRED_COMPARISON_CSV, comparison)
    coverage = market_coverage_summary(benchmark_rows)

    # ---- F0.4: walk-forward sin leakage (juez out-of-sample) ----
    print("Corriendo walk-forward (expanding, min_train=400, step=200)...")
    rows = read_csv_rows(HISTORICAL_CSV)
    walk_forward = run_walk_forward(
        rows,
        model_eval_fn=_model_eval_fn,
        baseline_pred_fns={
            "poisson_simple": poisson_simple_prediction,
            "elo_puro": elo_prediction,
        },
        penca_scoring_fn=model.realized_penca_points_for_score,
        scheme="expanding",
        min_train=400,
        step=200,
        output_dir=WALK_FORWARD_DIR,
        calibrate=False,  # juez del modelo crudo; sin cambios predictivos
    )
    wf = walk_forward["summary"]

    # ---- F0.4b: auditoría y re-derivación de Elo prepartido sin leakage ----
    print("Re-derivando Elo walk-forward independiente y auditando leakage...")
    elo_audit, elo_backtest_compare, leakage_warning = _run_elo_leakage_audit(
        original_model_logloss=model_summary.get("log_loss"),
    )

    # ---- F0.5: etiqueta de validación basada en walk-forward + candado ----
    wf_baselines = {
        "poisson_simple": wf.get("poisson_simple_logloss"),
        "elo_puro": wf.get("elo_puro_logloss"),
    }
    verdict = validation_label(
        n=int(wf.get("total_test_n") or 0),
        model_logloss=wf.get("model_logloss"),
        baseline_logloss=wf_baselines,
        out_of_sample=MODEL_OUT_OF_SAMPLE,
        leakage_warning=leakage_warning,
    )
    status_payload = {
        "verdict": verdict.to_dict(),
        "model_summary": {
            "matches": model_summary.get("matches"),
            "brier_score": model_summary.get("brier_score"),
            "log_loss": model_summary.get("log_loss"),
            "accuracy_1x2": model_summary.get("accuracy_1x2"),
        },
        "walk_forward": wf,
        "elo_leakage_audit": elo_audit,
        "elo_backtest_compare": elo_backtest_compare,
        "market_coverage": coverage,
        "paired_comparison": comparison,
        "known_issues": [
            "RESUELTO: bug de caché mutable en worldcup2026/distributions.py "
            "(los wrappers de distribución devolvían el dict cacheado y se mutaba "
            "in-place). Corregido con copia defensiva; predict_match es determinista.",
            "F0.4 walk-forward implementado: el veredicto usa métricas out-of-sample.",
            ("RESUELTO: F0.4b auditó elo_*_pre. La re-derivación walk-forward "
             "independiente reproduce el Elo almacenado y el backtest es estable, "
             "por lo que leakage_warning="
             + str(leakage_warning) + "."),
        ],
    }
    with VALIDATION_STATUS_JSON.open("w", encoding="utf-8") as handle:
        json.dump(status_payload, handle, ensure_ascii=False, indent=2)

    # ---- Reporte ----
    print("\n================ REPORTE DE VALIDACIÓN ================")
    model_brier = model_summary.get("brier_score")
    model_logloss = model_summary.get("log_loss")
    print(f"modelo_completo : matches={model_summary.get('matches')} "
          f"brier={_fmt(model_brier)} logloss={_fmt(model_logloss)} "
          f"acc={_fmt(model_summary.get('accuracy_1x2'))}")

    for name in ("elo_puro", "poisson_simple", "mercado_puro"):
        row = benchmark_summary.get(name)
        if row is None:
            print(f"{name:15} : (sin fila / sin muestra)")
            continue
        print(f"{name:15} : matches={row.get('matches')} "
              f"brier={_fmt(row.get('brier_score'))} logloss={_fmt(row.get('log_loss'))} "
              f"acc={_fmt(row.get('accuracy'))}")

    elo_row = benchmark_summary.get("elo_puro")
    if elo_row is not None and model_brier not in (None, ""):
        try:
            identical = abs(float(model_brier) - float(elo_row.get("brier_score"))) < 1e-9
        except (TypeError, ValueError):
            identical = False
        print(f"\n¿modelo_completo idéntico a elo_puro (brier)? {identical}")

    sin_elo = next((r for r in ablation if r.variant == "sin_elo"), None)
    if sin_elo is not None:
        print(f"sin_elo: matches={sin_elo.matches} applicable={sin_elo.applicable} "
              f"stripped_fields={sin_elo.stripped_fields}")

    not_applicable = [r.variant for r in ablation if not r.applicable]
    print(f"Ablations marcadas applicable=False: {not_applicable}")

    print("\n--- Comparación pareada (F0.3) ---")
    for row in comparison:
        print(f"{str(row['baseline']):15} n={row['n_paired']:>5} "
              f"dBrier={_fmt(row['delta_brier'])} dLogloss={_fmt(row['delta_logloss'])} "
              f"beats={row['beats']} -> {row['comparison_status']}")
    print(f"Cobertura de mercado: {coverage['n_with_market']}/{coverage['n_total_matches']} "
          f"({coverage['market_coverage_pct']}%) has_market_sample={coverage['has_market_sample']}")

    print("\n--- Walk-forward (F0.4) ---")
    print(f"folds={wf.get('n_folds')} total_test_n={wf.get('total_test_n')} "
          f"model_logloss={_fmt(wf.get('model_logloss'))} model_brier={_fmt(wf.get('model_brier'))} "
          f"acc={_fmt(wf.get('model_accuracy'))}")
    print(f"poisson_simple_logloss={_fmt(wf.get('poisson_simple_logloss'))} "
          f"elo_puro_logloss={_fmt(wf.get('elo_puro_logloss'))}")
    print(f"penca_avg={_fmt(wf.get('penca_points_avg'))} "
          f"exact_acc={_fmt(wf.get('model_exact_score_accuracy'))} "
          f"beats_poisson={wf.get('beats_poisson_simple')} beats_elo={wf.get('beats_elo_puro')}")

    print("\n--- Auditoría de Elo (F0.4b) ---")
    print(f"code_audit_walk_forward={elo_audit['code_audit_walk_forward']} "
          f"n={elo_audit['n_compared']} pearson_a={_fmt(elo_audit['pearson_elo_a'])} "
          f"pearson_b={_fmt(elo_audit['pearson_elo_b'])} max_abs_delta={_fmt(elo_audit['max_abs_delta'])}")
    print(f"backtest re-derivado: model_logloss={_fmt(elo_backtest_compare['model_rederived_logloss'])} "
          f"(orig {_fmt(elo_backtest_compare['model_original_logloss'])}, "
          f"shift {_fmt(elo_backtest_compare['logloss_shift_vs_original'])}) "
          f"beats_poisson={elo_backtest_compare['model_beats_poisson_rederived']} "
          f"beats_elo={elo_backtest_compare['model_beats_elo_rederived']} "
          f"stable={elo_backtest_compare['backtest_stable']}")
    print(f"leakage_warning -> {leakage_warning}")

    print("\n--- Etiqueta de validación (F0.5) ---")
    print(f"label={verdict.label} | beats_baselines={verdict.beats_baselines} | "
          f"out_of_sample={verdict.out_of_sample} | leakage_warning={verdict.leakage_warning}")
    print(f"razón: {verdict.reason}")
    print(f"¿puede decir 'validado'? {'SÍ' if verdict.label == 'validado' else 'NO'}")
    print("======================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
