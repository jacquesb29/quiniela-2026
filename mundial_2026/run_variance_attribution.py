"""Runner F5: atribución causal de la compresión de varianza (fold-a-fold).

Identifica QUÉ componente causa la subestimación de colas de F3, ablando uno por
vez y validando con los folds de F0.4. NO corrige, NO activa, NO modifica
producción, NO usa Mundial 2026. Requisito bloqueante: la re-composición debe
reproducir la distribución de producción bit-idéntico; si no, se detiene.
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
import backtest_production_adapter as adapter  # noqa: E402
from worldcup2026.benchmarks import read_csv_rows, safe_float  # noqa: E402
from worldcup2026.distributions import build_model_stack  # noqa: E402
from worldcup2026.attribution.components import COMPONENTS  # noqa: E402
from worldcup2026.attribution.ensemble_recompose import recompose_ensemble  # noqa: E402
from worldcup2026.attribution.gate import decide_component_intervention  # noqa: E402
from worldcup2026.attribution.metrics import (  # noqa: E402
    METRIC_KEYS,
    compute_attribution_metrics,
    raw_expected_penca_pick,
)
from worldcup2026.attribution.ranking import RANKING_COLUMNS, culpability_ranking  # noqa: E402
from worldcup2026.attribution.walkforward import BY_FOLD_COLUMNS, run_component_walkforward  # noqa: E402
from run_f3_audit import collect_match_observations  # noqa: E402

HISTORICAL_CSV = ROOT / "data" / "historical_matches.csv"
AUDIT_DIR = ROOT / "outputs" / "audit"
BY_FOLD_CSV = AUDIT_DIR / "variance_attribution_by_fold.csv"
BY_COMPONENT_CSV = AUDIT_DIR / "variance_attribution_by_component.csv"
RANKING_CSV = AUDIT_DIR / "variance_culpability_ranking.csv"
DECISION_MD = AUDIT_DIR / "variance_attribution_decision.md"
RESHAPE_STRENGTH = 0.46


def _reshape(dist, ta, tb, ctx, mu_a, mu_b):
    out, _ = model.apply_historical_score_shape_adjustment(
        dist, ta, tb, model.profile_for(ta), model.profile_for(tb),
        mu_a, mu_b, ctx, state_a=None, state_b=None, strength=RESHAPE_STRENGTH)
    return dict(out)


def production_distribution(ta, tb, ctx, mu_a, mu_b):
    dist, _ = build_model_stack(mu_a, mu_b, ctx, max_goals=10, market_strength=0.30)
    return _reshape(dist, ta, tb, ctx, mu_a, mu_b)


def _selector_pick(dist):
    opts = model.penca_ovacion_score_options(dist, 6)
    return opts[0]["score"] if opts else "0-0"


def _write(path, rows, columns=None):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    cols = list(columns) if columns else list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def main(argv=None) -> int:
    if not HISTORICAL_CSV.exists():
        print(f"ERROR: no existe {HISTORICAL_CSV}", file=sys.stderr)
        return 2
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_csv_rows(HISTORICAL_CSV)
    rows_by_id = {str(r.get("match_id")): r for r in rows}
    print("Recolectando observaciones (leakage-safe)...")
    obs = collect_match_observations(rows)
    obs_by_id = {o.match_id: o for o in obs}

    # Contexto/equipos/μ por partido (reconstrucción de producción).
    ctx_by_id, team_by_id = {}, {}
    for o in obs:
        row = rows_by_id.get(o.match_id)
        if row is None:
            continue
        ctx_by_id[o.match_id] = adapter.context_from_historical_row(row)
        team_by_id[o.match_id] = (adapter.team_from_historical_row(row, "a"),
                                  adapter.team_from_historical_row(row, "b"))

    # ---- Requisito bloqueante: reproducir producción bit-idéntico ----
    sample = obs[:25]
    for o in sample:
        ta, tb = team_by_id[o.match_id]
        recon = production_distribution(ta, tb, ctx_by_id[o.match_id], o.eg_a, o.eg_b)
        if recon != dict(o.model_dist):
            maxdiff = max(abs(recon.get(k, 0) - o.model_dist.get(k, 0)) for k in set(recon) | set(o.model_dist))
            print(f"[BLOQUEANTE] recompose NO reproduce producción ({o.match_id}, maxdiff={maxdiff:.2e}). "
                  "Atribución NO válida; F5 detenido.", file=sys.stderr)
            DECISION_MD.write_text("# F5 detenido\n\nLa re-composición no reproduce la distribución de "
                                   "producción bit-idéntico. La atribución no es válida.\n", encoding="utf-8")
            return 3
    print(f"Bloqueante OK: recompose reproduce producción en {len(sample)} muestras.")

    # ---- Pre-cómputo baseline ----
    base_dist = {o.match_id: dict(o.model_dist) for o in obs}
    print("Pre-computando picks baseline (selector de producción)...")
    base_pick = {o.match_id: _selector_pick(base_dist[o.match_id]) for o in obs}

    def baseline_metrics(test_obs):
        return compute_attribution_metrics(test_obs, [base_dist[o.match_id] for o in test_obs],
                                           [base_pick[o.match_id] for o in test_obs])

    all_fold_rows, by_component_rows = [], []
    for comp in COMPONENTS:
        print(f"Ablacionando componente: {comp.id} ...")
        abl_dist, abl_pick = {}, {}
        for o in obs:
            ta, tb = team_by_id[o.match_id]
            ctx = ctx_by_id[o.match_id]
            if comp.kind == "mu_scale":
                s = comp.mu_scale
                d, _ = build_model_stack(o.eg_a * s, o.eg_b * s, ctx, max_goals=10, market_strength=0.30)
                abl_dist[o.match_id] = _reshape(d, ta, tb, ctx, o.eg_a * s, o.eg_b * s)
                abl_pick[o.match_id] = _selector_pick(abl_dist[o.match_id])
            elif comp.kind == "recompose":
                ens = recompose_ensemble(o.eg_a, o.eg_b, ctx, overrides=comp.overrides)
                abl_dist[o.match_id] = _reshape(ens, ta, tb, ctx, o.eg_a, o.eg_b)
                abl_pick[o.match_id] = _selector_pick(abl_dist[o.match_id])
            elif comp.kind == "no_reshape":
                d, _ = build_model_stack(o.eg_a, o.eg_b, ctx, max_goals=10, market_strength=0.30)
                abl_dist[o.match_id] = dict(d)
                abl_pick[o.match_id] = _selector_pick(abl_dist[o.match_id])
            else:  # penca_relax: misma distribución, pick sin penalties
                abl_dist[o.match_id] = base_dist[o.match_id]
                abl_pick[o.match_id] = raw_expected_penca_pick(base_dist[o.match_id])

        def ablated_metrics(test_obs, _ad=abl_dist, _ap=abl_pick):
            return compute_attribution_metrics(test_obs, [_ad[o.match_id] for o in test_obs],
                                               [_ap[o.match_id] for o in test_obs])

        fold_rows = run_component_walkforward(
            rows, component_id=comp.id, obs_by_id=obs_by_id,
            baseline_metrics_fn=baseline_metrics, ablated_metrics_fn=ablated_metrics)
        all_fold_rows.extend(fold_rows)
        # agregado por componente
        if fold_rows:
            import statistics as st
            by_component_rows.append({
                "component_id": comp.id, "layer": comp.layer, "n_folds": len(fold_rows),
                "mean_delta_tail4": round(st.mean(f["delta_tail4"] for f in fold_rows), 6),
                "mean_delta_tail5": round(st.mean(f["delta_tail5"] for f in fold_rows), 6),
                "mean_delta_tail6": round(st.mean(f["delta_tail6"] for f in fold_rows), 6),
                "mean_delta_logloss": round(st.mean(f["delta_logloss"] for f in fold_rows), 6),
                "mean_delta_penca": round(st.mean(f["delta_penca"] for f in fold_rows), 6),
                "mean_delta_draw_error": round(st.mean(f["delta_draw_error"] for f in fold_rows), 6),
                "mean_delta_goal_bias": round(st.mean(f["delta_goal_total_bias"] for f in fold_rows), 6),
            })

    ranking = culpability_ranking(all_fold_rows)
    n_folds = max((f["fold_id"] for f in all_fold_rows), default=0)
    decision = decide_component_intervention(ranking, n_folds=n_folds)

    _write(BY_FOLD_CSV, all_fold_rows, BY_FOLD_COLUMNS)
    _write(BY_COMPONENT_CSV, by_component_rows)
    _write(RANKING_CSV, ranking, RANKING_COLUMNS)
    _write_decision_md(ranking, decision, n_folds)

    print("\n================ F5 ATRIBUCIÓN DE VARIANZA ================")
    print("Ranking de culpabilidad (tail≥5):")
    for e in ranking:
        print(f"  #{e['rank']} {e['component_id']:14} close_gap={e['fraction_folds_close_gap']} "
              f"recovery={e['mean_tail5_recovery']:+.4f} culp={e['culpability_score']:.5f} -> {e['verdict']}")
    print(f"\nDECISIÓN: {decision['decision']} — {decision['reason']}")
    print("==========================================================")
    return 0


def _write_decision_md(ranking, decision, n_folds):
    lines = ["# Atribución causal de la compresión de varianza (F5)", "",
             f"Folds (F0.4): {n_folds}. Ablación de un componente por vez, walk-forward leakage-safe. "
             "F5 identifica; no corrige ni activa.", "",
             "## Ranking de culpabilidad", "",
             "| rank | componente | %folds_cierra_gap | recovery_tail5 | consistencia | Δlogloss | Δpenca | culpabilidad | veredicto |",
             "|---|---|---|---|---|---|---|---|---|"]
    for e in ranking:
        lines.append(f"| {e['rank']} | {e['component_id']} | {e['fraction_folds_close_gap']} | "
                     f"{e['mean_tail5_recovery']:+.4f} | {e['consistency']} | {e['mean_delta_logloss']:+.5f} | "
                     f"{e['mean_delta_penca']:+.4f} | {e['culpability_score']:.5f} | {e['verdict']} |")
    top = ranking[0] if ranking else {}
    lines += ["", "## Componente #1 (fold-a-fold)", "",
              f"- {top.get('component_id')}: cierra el gap de cola en {top.get('fraction_folds_close_gap')} de los folds; "
              f"recovery medio tail≥5 = {top.get('mean_tail5_recovery')}; Δlog-loss medio = {top.get('mean_delta_logloss')}.",
              "", "## Preguntas", "",
              f"- ¿hay culpable claro? {'sí: ' + str(decision.get('target_component')) if decision['decision'].startswith('intervene') else 'no (no_clear_culprit)'}",
              f"- margen sobre el 2º: {decision.get('culpability_margin')}",
              "", f"## Decisión del gate: **{decision['decision']}**", "", decision["reason"],
              "", "F5 no corrige ni activa. Cualquier intervención sería una fase posterior, gated."]
    DECISION_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
