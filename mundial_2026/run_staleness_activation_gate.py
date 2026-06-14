"""Runner F2.5: gate de validación y decisión de activación del Elo staleness-aware.

Compara, en walk-forward histórico, el modelo baseline vs un modelo EXPERIMENTAL
con el shrink staleness-aware activado SOLO dentro de este runner (flag ON local
vía un PARAMS copiado; NO cambia el default `elo_staleness_enabled=False`).

Salidas: outputs/ratings/staleness_activation_gate.csv y staleness_activation_decision.md.

NO toca el modelo, pesos, lambdas, metodología ni Penca. NO usa resultados futuros
ni datos del Mundial 2026 para ajustar parámetros ni para activar.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import modelo_quiniela_2026 as model  # noqa: E402
import backtest_production_adapter as adapter  # noqa: E402  (instala shims)
from worldcup2026.config import PARAMS  # noqa: E402
from worldcup2026.benchmarks import elo_prediction, poisson_simple_prediction, read_csv_rows  # noqa: E402
from worldcup2026.ratings.activation_gate import (  # noqa: E402
    build_by_bucket,
    build_gate_rows,
    decide_activation,
    staleness_match_bucket,
    write_decision_md,
    write_gate_csv,
)
from worldcup2026.ratings.staleness import effective_elo_staleness_aware
from worldcup2026.walk_forward import run_walk_forward  # noqa: E402

HISTORICAL_CSV = ROOT / "data" / "historical_matches.csv"
GATE_CSV = ROOT / "outputs" / "ratings" / "staleness_activation_gate.csv"
DECISION_MD = ROOT / "outputs" / "ratings" / "staleness_activation_decision.md"

# Flag ON SOLO local (no se cambia el default del proyecto).
PARAMS_ON = dataclasses.replace(PARAMS, elo_staleness_enabled=True)

LIMITATION = (
    "El histórico `historical_matches.csv` no tiene FIFA prepartido "
    "(`fifa_rank_*_pre`/`fifa_points` vacíos) ⇒ `fifa_implied_elo=None` ⇒ el shrink "
    "staleness-aware es IDENTIDAD en walk-forward y el experimental coincide con el "
    "baseline. Por tanto no hay evidencia histórica para activar. El mecanismo solo "
    "puede usarse con FIFA/mercado ACTUALES (2026) como diagnóstico/guardrail, y esos "
    "datos NO deben usarse para activar (leakage/overfit). Decisión: mantener OFF."
)


def _pred_to_eval(prediction):
    if prediction is None:
        return None
    top = model.penca_ovacion_top_score(prediction)
    modal = prediction.exact_scores[0][0] if prediction.exact_scores else None
    return {
        "prob_a": prediction.win_a, "prob_draw": prediction.draw, "prob_b": prediction.win_b,
        "modal_score": modal, "penca_score": top.get("score") if top else None,
    }


def baseline_eval(row):
    return _pred_to_eval(adapter.production_prediction_fn(row))


def experimental_eval(row):
    # Mismo pipeline, pero el Elo de cada equipo pasa por el wrapper gated con flag ON.
    team_a = adapter.team_from_historical_row(row, "a")
    team_b = adapter.team_from_historical_row(row, "b")
    # Sin FIFA histórico -> fifa_implied None -> shrink identidad (experimental == baseline).
    elo_a = effective_elo_staleness_aware(base_effective_elo=team_a.elo, fifa_implied_elo_value=None,
                                          staleness=0.0, params=PARAMS_ON)
    elo_b = effective_elo_staleness_aware(base_effective_elo=team_b.elo, fifa_implied_elo_value=None,
                                          staleness=0.0, params=PARAMS_ON)
    team_a = dataclasses.replace(team_a, elo=elo_a)
    team_b = dataclasses.replace(team_b, elo=elo_b)
    if team_a.name == team_b.name:
        return None
    ctx = adapter.context_from_historical_row(row)
    seed_key = "|".join(str(row.get(f) or "") for f in ("match_id", "team_a", "team_b", "date"))
    model.seed_all_rng(model.stable_seed(seed_key))
    pred = model.predict_match({team_a.name: team_a, team_b.name: team_b}, team_a.name, team_b.name, ctx)
    return _pred_to_eval(pred)


def _metrics_from_wf(summary):
    return {
        "n": summary.get("total_test_n"),
        "logloss": summary.get("model_logloss"),
        "brier": summary.get("model_brier"),
        "accuracy": summary.get("model_accuracy"),
        "exact_score_accuracy": summary.get("model_exact_score_accuracy"),
        "penca_points_avg": summary.get("penca_points_avg"),
        "penca_points_total": summary.get("penca_points_total"),
    }


def main(argv=None) -> int:
    rows = read_csv_rows(HISTORICAL_CSV)
    baselines = {"poisson_simple": poisson_simple_prediction, "elo_puro": elo_prediction}
    penca_fn = model.realized_penca_points_for_score

    print("Walk-forward baseline ...")
    wf_base = run_walk_forward(rows, model_eval_fn=baseline_eval, baseline_pred_fns=baselines,
                               penca_scoring_fn=penca_fn, scheme="expanding", min_train=400, step=200)["summary"]
    print("Walk-forward experimental (staleness-aware, flag ON local) ...")
    wf_exp = run_walk_forward(rows, model_eval_fn=experimental_eval, baseline_pred_fns=baselines,
                              penca_scoring_fn=penca_fn, scheme="expanding", min_train=400, step=200)["summary"]

    base_m = _metrics_from_wf(wf_base)
    exp_m = _metrics_from_wf(wf_exp)
    model_metrics = {
        "baseline": base_m,
        "staleness_experimental": exp_m,
        "poisson_simple": {"n": wf_base.get("total_test_n"), "logloss": wf_base.get("poisson_simple_logloss"),
                           "brier": wf_base.get("poisson_simple_brier")},
        "elo_puro": {"n": wf_base.get("total_test_n"), "logloss": wf_base.get("elo_puro_logloss"),
                     "brier": wf_base.get("elo_puro_brier")},
    }

    # Buckets de staleness sobre el histórico: sin FIFA -> todos "bajo".
    bucket_counts = {"alto": 0, "medio": 0, "bajo": 0}
    for _ in rows:
        bucket_counts[staleness_match_bucket(0.0)] += 1
    bucket_metrics = {
        "bajo": {"n": bucket_counts["bajo"], "logloss": base_m["logloss"], "brier": base_m["brier"],
                 "penca_points_avg": base_m["penca_points_avg"],
                 "note": "histórico sin FIFA: todos los partidos caen en 'bajo'"},
        "medio": {"n": 0}, "alto": {"n": 0},
    }

    decision = decide_activation(base_m, exp_m, out_of_sample=True)
    model_rows = build_gate_rows(model_metrics)
    bucket_rows = build_by_bucket(bucket_metrics)
    write_gate_csv(model_rows, bucket_rows, GATE_CSV)
    write_decision_md(decision, model_rows, bucket_rows, path=DECISION_MD, limitation_note=LIMITATION)

    print("\n================ GATE DE ACTIVACIÓN (F2.5) ================")
    print(f"baseline     : logloss={base_m['logloss']} penca_avg={base_m['penca_points_avg']}")
    print(f"experimental : logloss={exp_m['logloss']} penca_avg={exp_m['penca_points_avg']}")
    print(f"DECISIÓN: {decision['decision']} ({decision['operational_status']}) — {decision['reason']}")
    print(f"flag elo_staleness_enabled (default del proyecto): {PARAMS.elo_staleness_enabled}")
    print("===========================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
