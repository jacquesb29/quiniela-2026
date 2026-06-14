"""Runner F4.1: evalúa la intervención post-distribución de colas (Estilo A).

Compara, en walk-forward histórico, el baseline (distribución actual del modelo)
vs candidatos con `tail_reweight` (flag ON SOLO dentro de este runner). NO toca el
modelo, pesos, lambdas, metodología ni el selector Penca de producción; no activa
nada; no usa Mundial 2026. Reusa el colector leakage-safe de F3.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import modelo_quiniela_2026 as model  # noqa: E402
from worldcup2026.benchmarks import read_csv_rows  # noqa: E402
from worldcup2026.interventions.gate import decide_tail_activation  # noqa: E402
from worldcup2026.interventions.tail import FAV_STRONG, TOTAL_HIGH, TailParams, effective_tail_mass, tail_reweight  # noqa: E402
from worldcup2026.interventions.walkforward_tail import (  # noqa: E402
    FOLD_COLUMNS,
    decide_tail_walkforward,
    run_tail_walkforward,
    summarize_walkforward,
)
from run_f3_audit import collect_match_observations  # noqa: E402

HISTORICAL_CSV = ROOT / "data" / "historical_matches.csv"
AUDIT_DIR = ROOT / "outputs" / "audit"
CANDIDATES_CSV = AUDIT_DIR / "tail_intervention_candidates.csv"
GATE_CSV = AUDIT_DIR / "tail_intervention_gate.csv"
DECISION_MD = AUDIT_DIR / "tail_intervention_decision.md"
WF_BY_FOLD_CSV = AUDIT_DIR / "tail_walkforward_by_fold.csv"
WF_SUMMARY_CSV = AUDIT_DIR / "tail_walkforward_summary.csv"
WF_DECISION_MD = AUDIT_DIR / "tail_walkforward_decision.md"

OUTCOMES = ("a", "draw", "b")

# Candidatos: priors conservadores (NO ajustados a resultados 2026).
CANDIDATES = {
    "moderado": TailParams(enabled=True, beta=0.55, t0=3, max_mass_shift=0.04, min_signal=0.35, weak_favorite_guard=True),
    "fuerte":   TailParams(enabled=True, beta=1.00, t0=3, max_mass_shift=0.07, min_signal=0.30, weak_favorite_guard=True),
}


def _fav_share(o):
    tot = o.eg_a + o.eg_b
    return (max(o.eg_a, o.eg_b) / tot) if tot > 0 else 0.5


def _outcome(o):
    if o.goals_a > o.goals_b:
        return "a"
    return "draw" if o.goals_a == o.goals_b else "b"


def _dist_1x2(dist):
    a = sum(p for (x, y), p in dist.items() if x > y)
    d = sum(p for (x, y), p in dist.items() if x == y)
    b = sum(p for (x, y), p in dist.items() if x < y)
    s = a + d + b
    return (a / s, d / s, b / s) if s > 0 else (1 / 3, 1 / 3, 1 / 3)


def compute_metrics(obs, dists):
    n = len(obs)
    ll = br = draw_pred = 0.0
    tail_pred = {4: 0.0, 5: 0.0, 6: 0.0}
    draw_obs = sum(1 for o in obs if o.goals_a == o.goals_b) / n
    tail_obs = {k: sum(1 for o in obs if o.goals_a + o.goals_b >= k) / n for k in (4, 5, 6)}
    penca_real = 0.0
    exact_hits = 0
    weak_num = weak_pred = weak_obs = 0
    for o, dist in zip(obs, dists):
        pa, pd, pb = _dist_1x2(dist)
        probs = {"a": pa, "draw": pd, "b": pb}
        oc = _outcome(o)
        ll += -math.log(max(probs[oc], 1e-12))
        br += sum((probs[k] - (1.0 if k == oc else 0.0)) ** 2 for k in OUTCOMES) / 3.0
        draw_pred += pd
        for k in (4, 5, 6):
            tail_pred[k] += effective_tail_mass(dist, k)
        # Penca con el MISMO selector existente, sobre esta distribución.
        opts = model.penca_ovacion_score_options(dist, 6)
        pick = opts[0]["score"] if opts else None
        if pick is not None:
            penca_real += model.realized_penca_points_for_score(pick, f"{o.goals_a}-{o.goals_b}")
        top1 = max(dist.items(), key=lambda kv: kv[1])[0] if dist else None
        if top1 == (o.goals_a, o.goals_b):
            exact_hits += 1
        # Favoritos débiles: guard objetivo del gate.
        if _fav_share(o) < FAV_STRONG and (o.eg_a + o.eg_b) < TOTAL_HIGH:
            weak_num += 1
            weak_pred += effective_tail_mass(dist, 4)
            weak_obs += 1 if (o.goals_a + o.goals_b) >= 4 else 0
    weak_overpred = ((weak_pred - weak_obs) / weak_num) if weak_num else 0.0
    return {
        "n": n,
        "logloss": ll / n, "brier": br / n,
        "penca_avg": penca_real / n,
        "exact_top1": exact_hits / n,
        "draw_error": abs(draw_obs - draw_pred / n),
        "tail_err_4": abs(tail_obs[4] - tail_pred[4] / n),
        "tail_err_5": abs(tail_obs[5] - tail_pred[5] / n),
        "tail_err_6": abs(tail_obs[6] - tail_pred[6] / n),
        "pred_ge4": tail_pred[4] / n, "pred_ge5": tail_pred[5] / n, "pred_ge6": tail_pred[6] / n,
        "obs_ge4": tail_obs[4], "obs_ge5": tail_obs[5], "obs_ge6": tail_obs[6],
        "weak_fav_tail_overpred": weak_overpred,
    }


def main(argv=None) -> int:
    if not HISTORICAL_CSV.exists():
        print(f"ERROR: no existe {HISTORICAL_CSV}", file=sys.stderr)
        return 2
    print("Recolectando observaciones (leakage-safe)...")
    obs = collect_match_observations(read_csv_rows(HISTORICAL_CSV))
    print(f"Partidos: {len(obs)}")

    baseline_dists = [dict(o.model_dist) for o in obs]
    base_m = compute_metrics(obs, baseline_dists)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    cand_rows, gate_rows, decisions = [], [], {}
    for cid, params in CANDIDATES.items():
        exp_dists = [tail_reweight(o.model_dist, params=params, expected_total=o.eg_a + o.eg_b,
                                   favorite_share=_fav_share(o)) for o in obs]
        exp_m = compute_metrics(obs, exp_dists)
        decision = decide_tail_activation(base_m, exp_m)
        decisions[cid] = decision
        cand_rows.append({
            "candidate_id": cid, "params": json.dumps(params.__dict__),
            "pred_ge4": round(exp_m["pred_ge4"], 6), "pred_ge5": round(exp_m["pred_ge5"], 6),
            "pred_ge6": round(exp_m["pred_ge6"], 6),
            "obs_ge4": round(exp_m["obs_ge4"], 6), "obs_ge5": round(exp_m["obs_ge5"], 6),
            "obs_ge6": round(exp_m["obs_ge6"], 6),
            "tail_err_4": round(exp_m["tail_err_4"], 6), "tail_err_5": round(exp_m["tail_err_5"], 6),
            "tail_err_6": round(exp_m["tail_err_6"], 6),
            "flag_default": "OFF",
        })
        gate_rows.append({
            "candidate_id": cid, "n": exp_m["n"],
            "base_logloss": round(base_m["logloss"], 6), "exp_logloss": round(exp_m["logloss"], 6),
            "base_brier": round(base_m["brier"], 6), "exp_brier": round(exp_m["brier"], 6),
            "base_penca": round(base_m["penca_avg"], 6), "exp_penca": round(exp_m["penca_avg"], 6),
            "base_draw_err": round(base_m["draw_error"], 6), "exp_draw_err": round(exp_m["draw_error"], 6),
            "tail_err_4_base": round(base_m["tail_err_4"], 6), "tail_err_4_exp": round(exp_m["tail_err_4"], 6),
            "tail_err_5_base": round(base_m["tail_err_5"], 6), "tail_err_5_exp": round(exp_m["tail_err_5"], 6),
            "tail_err_6_base": round(base_m["tail_err_6"], 6), "tail_err_6_exp": round(exp_m["tail_err_6"], 6),
            "weak_fav_tail_overpred": round(exp_m["weak_fav_tail_overpred"], 6),
            "decision": decision["decision"], "reason": decision["reason"],
        })

    _write(CANDIDATES_CSV, cand_rows)
    _write(GATE_CSV, gate_rows)
    _write_decision_md(base_m, gate_rows, decisions)

    # ---- F4.2: validación walk-forward fold-a-fold del candidato 'fuerte' ----
    rows_hist = read_csv_rows(HISTORICAL_CSV)
    obs_by_id = {o.match_id: o for o in obs}
    strong = CANDIDATES["fuerte"]

    def _baseline_metrics(test_obs):
        return compute_metrics(test_obs, [dict(o.model_dist) for o in test_obs])

    def _experimental_metrics(test_obs):
        dists = [tail_reweight(o.model_dist, params=strong, expected_total=o.eg_a + o.eg_b,
                               favorite_share=_fav_share(o)) for o in test_obs]
        return compute_metrics(test_obs, dists)

    fold_rows = run_tail_walkforward(
        rows_hist, obs_by_id=obs_by_id,
        baseline_metrics_fn=_baseline_metrics, experimental_metrics_fn=_experimental_metrics)
    wf_summary = summarize_walkforward(fold_rows)
    wf_decision = decide_tail_walkforward(fold_rows)
    _write(WF_BY_FOLD_CSV, [{c: f.get(c, "") for c in FOLD_COLUMNS} for f in fold_rows])
    _write(WF_SUMMARY_CSV, wf_summary)
    _write_wf_decision_md(fold_rows, wf_summary, wf_decision)

    print("\n================ GATE F4.1 (intervención de colas) ================")
    print(f"baseline: tail_err 4/5/6 = {base_m['tail_err_4']:.4f}/{base_m['tail_err_5']:.4f}/{base_m['tail_err_6']:.4f} "
          f"logloss={base_m['logloss']:.5f} penca={base_m['penca_avg']:.4f}")
    for r in gate_rows:
        print(f"  [{r['candidate_id']}] tail_err5 {r['tail_err_5_base']:.4f}->{r['tail_err_5_exp']:.4f} "
              f"Δlogloss={r['exp_logloss']-r['base_logloss']:+.5f} Δpenca={r['exp_penca']-r['base_penca']:+.4f} "
              f"-> {r['decision']}")
    print("\n--- F4.2 walk-forward fold-a-fold (candidato 'fuerte') ---")
    print(f"folds={wf_decision['n_folds']} tail5_mejora_fraccion={wf_decision.get('tail5_improved_fraction')} "
          f"mean_dlogloss={wf_decision.get('mean_delta_logloss')} mean_dpenca={wf_decision.get('mean_delta_penca')}")
    print(f"DECISIÓN walk-forward: {wf_decision['decision']} — {wf_decision['reason']}")
    print("===================================================================")
    return 0


def _write_wf_decision_md(fold_rows, summary, decision):
    n = len(fold_rows)
    won5 = sum(1 for f in fold_rows if float(f["experimental_tail5"]) < float(f["baseline_tail5"]))
    lost5 = n - won5
    lines = ["# Validación walk-forward F4.2 — candidato 'fuerte' (fold-a-fold)", "",
             "Reusa exactamente los folds de F0.4 (expanding, min_train=400, step=200). Es validación: "
             "NO activa nada; el flag de producción sigue OFF.", "",
             f"- Folds: {n}",
             f"- Folds que MEJORAN tail≥5: **{won5}**; que empeoran: **{lost5}** "
             f"(fracción de mejora = {decision.get('tail5_improved_fraction')})",
             f"- ¿Mejora concentrada en pocos folds? {'posible' if won5 and won5 < max(1, int(0.6*n)) else 'no evidente'}",
             f"- Estabilidad (media Δlog-loss / Δtail5):", ]
    by = {r["metric"]: r for r in summary}
    lines += [
        f"  - Δlog-loss media={by['logloss']['mean']} (std {by['logloss']['std']})",
        f"  - Δtail5 media={by['tail5']['mean']} (std {by['tail5']['std']})",
        f"  - Δpenca media={by['penca']['mean']}",
        f"  - Δempates media={by['draw_error']['mean']}",
        "", "## Por fold", "",
        "| fold | n_test | tail5 base→exp | Δlogloss | Δpenca |", "|---|---|---|---|---|"]
    for f in fold_rows:
        lines.append(f"| {f['fold_id']} | {f['n_test']} | {f['baseline_tail5']}→{f['experimental_tail5']} | "
                     f"{f['delta_logloss']:+.5f} | {f['delta_penca']:+.4f} |")
    lines += ["", "## Preguntas", "",
              f"- ¿cuántos folds mejoran? {won5}/{n}",
              f"- ¿cuántos empeoran? {lost5}/{n}",
              f"- ¿hay evidencia de sobreajuste? {'revisar (mejora no mayoritaria)' if won5 < int(0.6*n)+ (1 if 0.6*n%1 else 0) else 'baja (mejora consistente)'}",
              f"- ¿la mejora es consistente? {'sí' if decision['decision']=='activate' else 'no concluyente'}",
              "", f"## Decisión walk-forward: **{decision['decision']}**", "", decision["reason"],
              "", "Flag de producción: permanece **OFF** (F4.2 es validación; no activa)."]
    WF_DECISION_MD.write_text("\n".join(lines), encoding="utf-8")


def _write(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_decision_md(base_m, gate_rows, decisions):
    lines = ["# Decisión — Intervención de colas (F4.1, experimental gated)", "",
             "F4.1 es experimental y post-distribución. Flag OFF por defecto; el modelo de "
             "producción NO se modifica. No usa Mundial 2026.", "",
             f"Baseline: total≥4/5/6 obs {base_m['obs_ge4']:.3f}/{base_m['obs_ge5']:.3f}/{base_m['obs_ge6']:.3f} "
             f"vs pred {base_m['pred_ge4']:.3f}/{base_m['pred_ge5']:.3f}/{base_m['pred_ge6']:.3f}; "
             f"logloss={base_m['logloss']:.5f}, penca={base_m['penca_avg']:.4f}.", "",
             "| candidato | tail_err5 base→exp | Δlogloss | Δbrier | Δpenca | Δdraw_err | weak_fav | decisión |",
             "|---|---|---|---|---|---|---|---|"]
    for r in gate_rows:
        lines.append(f"| {r['candidate_id']} | {r['tail_err_5_base']:.4f}→{r['tail_err_5_exp']:.4f} | "
                     f"{r['exp_logloss']-r['base_logloss']:+.5f} | {r['exp_brier']-r['base_brier']:+.5f} | "
                     f"{r['exp_penca']-r['base_penca']:+.4f} | {r['exp_draw_err']-r['base_draw_err']:+.4f} | "
                     f"{r['weak_fav_tail_overpred']:.4f} | **{r['decision']}** |")
    any_activate = any(d["decision"] == "activate" for d in decisions.values())
    lines += ["", "## Resultado",
              ("Algún candidato pasa el gate → considerar activación (con doble revisión)."
               if any_activate else
               "Ningún candidato pasa el gate como `activate`. **Se mantiene el flag OFF.**"),
              "", "Flag de producción: `tail_intervention` permanece **OFF** (experimental)."]
    DECISION_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
