"""Runner F3: auditoría estructural de distribución de marcadores.

Usa data/historical_matches.csv (observado, pasado) y la predicción leakage-safe
del modelo (backtest_production_adapter.production_prediction_fn) para medir
empates, goles totales, colas, exact scores y Penca. F3 MIDE; F3 NO CORRIGE: no
cambia pesos, lambdas, metodología, selector Penca ni ninguna predicción, y no usa
Mundial 2026 para ajustar.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import modelo_quiniela_2026 as model  # noqa: E402
from backtest_production_adapter import production_prediction_fn  # noqa: E402
from worldcup2026.benchmarks import read_csv_rows, safe_float  # noqa: E402
from worldcup2026.audit.dashboard import load_audit_outputs, render_f3_dashboard_html  # noqa: E402
from worldcup2026.audit.exact_score import EXACT_COLUMNS, exact_score_audit  # noqa: E402
from worldcup2026.audit.gate import f3_decision  # noqa: E402
from worldcup2026.audit.goals import GOAL_COLUMNS, TAIL_COLUMNS, goal_calibration, tail_audit  # noqa: E402
from worldcup2026.audit.penca import PENCA_COLUMNS, penca_audit  # noqa: E402
from worldcup2026.audit.scoreline import (  # noqa: E402
    DRAW_COLUMNS,
    SCORE_COLUMNS,
    MatchObservation,
    draw_audit,
    score_distribution_audit,
    score_total_variation,
)

HISTORICAL_CSV = ROOT / "data" / "historical_matches.csv"
AUDIT_DIR = ROOT / "outputs" / "audit"
GATE_JSON = AUDIT_DIR / "f3_gate.json"
SUMMARY_MD = AUDIT_DIR / "f3_summary.md"
DASHBOARD_HTML = AUDIT_DIR / "f3_dashboard.html"


def collect_match_observations(rows):
    obs = []
    for row in rows:
        ga = safe_float(row.get("goals_a"))
        gb = safe_float(row.get("goals_b"))
        if ga is None or gb is None:
            continue
        pred = production_prediction_fn(row)
        if pred is None or not pred.score_distribution:
            continue
        top = model.penca_ovacion_top_score(pred)
        elo_a = safe_float(row.get("elo_a_pre")) or 0.0
        elo_b = safe_float(row.get("elo_b_pre")) or 0.0
        obs.append(MatchObservation(
            match_id=str(row.get("match_id") or ""),
            goals_a=int(ga), goals_b=int(gb),
            elo_diff=elo_a - elo_b,
            model_dist=dict(pred.score_distribution),
            win_a=float(pred.win_a), draw=float(pred.draw), win_b=float(pred.win_b),
            eg_a=float(pred.expected_goals_a), eg_b=float(pred.expected_goals_b),
            penca_score=str(top.get("score")) if top else "",
            penca_expected_points=float(top.get("expected_points") or 0.0) if top else 0.0,
        ))
    return obs


def _write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c, "") for c in columns})


def _fav_rates(obs):
    if not obs:
        return 0.0, 0.0
    pred = sum(max(o.win_a, o.win_b) for o in obs) / len(obs)
    obs_rate = 0.0
    for o in obs:
        if o.goals_a == o.goals_b:
            continue
        actual = "home" if o.goals_a > o.goals_b else "away"
        fav = "home" if o.win_a >= o.win_b else "away"
        if actual == fav:
            obs_rate += 1
    return pred, obs_rate / len(obs)


def main(argv=None) -> int:
    if not HISTORICAL_CSV.exists():
        print(f"ERROR: no existe {HISTORICAL_CSV}", file=sys.stderr)
        return 2
    print("Recolectando observaciones (predicción leakage-safe)...")
    obs = collect_match_observations(read_csv_rows(HISTORICAL_CSV))
    n = len(obs)
    print(f"Partidos auditados: {n}")

    score_rows = score_distribution_audit(obs)
    draw_rows = draw_audit(obs)
    goal_rows = goal_calibration(obs)
    tail_rows = tail_audit(obs)
    exact_rows = exact_score_audit(obs)
    penca_rows = penca_audit(obs, model.realized_penca_points_for_score)

    _write_csv(AUDIT_DIR / "score_distribution_audit.csv", SCORE_COLUMNS, score_rows)
    _write_csv(AUDIT_DIR / "draw_audit.csv", DRAW_COLUMNS, draw_rows)
    _write_csv(AUDIT_DIR / "goal_calibration.csv", GOAL_COLUMNS, goal_rows)
    _write_csv(AUDIT_DIR / "tail_events_audit.csv", TAIL_COLUMNS, tail_rows)
    _write_csv(AUDIT_DIR / "exact_score_audit.csv", EXACT_COLUMNS, exact_rows)
    _write_csv(AUDIT_DIR / "penca_score_audit.csv", PENCA_COLUMNS, penca_rows)

    # ---- Escalares para el gate ----
    draw_global = next((r for r in draw_rows if r["bucket"] == "global"), {})
    draw_error_global = (float(draw_global.get("observed_draw_rate") or 0.0)
                         - float(draw_global.get("predicted_draw_rate") or 0.0))
    total_row = next((r for r in goal_rows if r["dimension"] == "total_goals"), {})
    total_goals_bias = float(total_row.get("bias") or 0.0)
    score_tv = score_total_variation(score_rows)
    max_tail_under = max((float(r["observed_rate"]) - float(r["predicted_rate"]) for r in tail_rows), default=0.0)
    penca_global = next((r for r in penca_rows if r["bucket"] == "global"), {})
    penca_gap_global = float(penca_global.get("gap") or 0.0)
    fav_pred, fav_obs = _fav_rates(obs)

    gate = f3_decision(
        n=n, draw_error_global=draw_error_global, fav_pred_rate=fav_pred, fav_obs_rate=fav_obs,
        total_goals_bias=total_goals_bias, score_tv_distance=score_tv,
        max_tail_underprediction=max_tail_under, penca_gap_global=penca_gap_global,
    )
    GATE_JSON.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")

    _write_summary(score_rows, draw_rows, goal_rows, tail_rows, exact_rows, penca_rows, gate, n)
    data = load_audit_outputs(AUDIT_DIR, GATE_JSON)
    DASHBOARD_HTML.write_text(
        "<!doctype html><meta charset='utf-8'><title>Auditoría F3</title>\n" + render_f3_dashboard_html(data),
        encoding="utf-8",
    )

    print("\n================ GATE F3 ================")
    for k in ("subestima_empates", "sobreestima_favoritos", "goles_mal_calibrados",
              "subestima_colas", "optimismo_penca", "vale_la_pena_intervenir", "suggested_priority"):
        print(f"  {k}: {gate[k]}")
    print("=========================================")
    return 0


def _write_summary(score_rows, draw_rows, goal_rows, tail_rows, exact_rows, penca_rows, gate, n):
    lines = [
        "# Auditoría estructural F3 (histórico)", "",
        f"Partidos: {n}. Observado = histórico pasado; predicho = modelo leakage-safe (solo Elo prepartido). "
        "No es validación de 2026. **F3 mide; no corrige.**", "",
        "## Empates (por bucket de favorito)", "",
        "| bucket | n | observado | predicho | error | veredicto |", "|---|---|---|---|---|---|",
    ]
    for r in draw_rows:
        lines.append(f"| {r['bucket']} | {r['n']} | {r['observed_draw_rate']} | {r['predicted_draw_rate']} | "
                     f"{r['error']} | {r['verdict']} |")
    total_row = next((r for r in goal_rows if r["dimension"] == "total_goals"), {})
    lines += ["", "## Goles totales", "",
              f"- media observada={total_row.get('mean_observed')}, predicha={total_row.get('mean_predicted')}, "
              f"bias={total_row.get('bias')}, mae={total_row.get('mae')}", ""]
    lines += ["## Colas", "", "| umbral | observado | predicho | abs_error |", "|---|---|---|---|"]
    for r in tail_rows:
        lines.append(f"| {r['threshold']} | {r['observed_rate']} | {r['predicted_rate']} | {r['abs_error']} |")
    lines += ["", "## Exact score", "", "| top_n | hit_rate | cobertura |", "|---|---|---|"]
    for r in exact_rows:
        lines.append(f"| {r['top_n']} | {r['exact_hit_rate']} | {r['mean_probability_coverage']} |")
    lines += ["", "## Penca (8/5/3)", "", "| bucket | n | realized | expected | gap |", "|---|---|---|---|---|"]
    for r in penca_rows:
        lines.append(f"| {r['bucket']} | {r['n']} | {r['mean_realized_penca']} | "
                     f"{r['mean_expected_penca']} | {r['gap']} |")
    lines += ["", "## Veredicto del gate", ""]
    for k in ("subestima_empates", "sobreestima_favoritos", "goles_mal_calibrados",
              "subestima_colas", "optimismo_penca", "vale_la_pena_intervenir", "suggested_priority"):
        lines.append(f"- {k}: **{gate[k]}**")
    lines += ["", "F3 no cambió ninguna predicción ni peso del modelo."]
    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
