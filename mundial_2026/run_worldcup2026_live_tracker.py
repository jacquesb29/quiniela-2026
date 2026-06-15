"""Tracker acumulativo del Mundial 2026 (solo seguimiento, sin cambios al modelo).

FUENTE PRIMARIA: ``fixtures_live_2026.json`` vía ``worldcup2026.results_ingest``
(feed directo, contexto real con ``context_from_fixture``). ``finished_match_audit.csv``
se usa SOLO como fallback si el feed falta. NO depende de re-ejecutar el dashboard.
NO toca pesos, lambdas, metodología, selector Penca ni flags: es medición.

Genera:
  outputs/audit/worldcup2026_live_tracking.csv   (una fila por partido finalizado)
  outputs/audit/worldcup2026_live_tracking.md    (tabla + métricas acumuladas)
  outputs/audit/worldcup2026_data_inventory.md       (inventario de datos)
  outputs/audit/worldcup2026_source_consistency.csv  (comparación de fuentes)
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026 import results_ingest as RI
from worldcup2026 import live_prediction as LP

OUT_CSV = ROOT / "outputs" / "audit" / "worldcup2026_live_tracking.csv"
OUT_MD = ROOT / "outputs" / "audit" / "worldcup2026_live_tracking.md"
MAX_PTS = 8.0

COLUMNS = (
    "fecha", "partido", "marcador_real", "pick_modelo", "pick_penca",
    "puntos_modelo", "puntos_penca", "resultado_correcto", "empate",
    "favorito_gano", "mercado_disponible", "t60_disponible",
)


def _outcome(a, b):
    return "home" if a > b else ("draw" if a == b else "away")


def _yn(flag):
    return "n/d" if flag is None else ("si" if flag else "no")


def _has_market(fx):
    return fx.get("market_prob_a") is not None and bool(fx.get("market_provider"))


def _has_t60(fx):
    return (bool(fx.get("lineup_confirmed_a")) or bool(fx.get("lineup_confirmed_b"))
            or bool(fx.get("starting_xi_a")) or bool(fx.get("starting_xi_b")))


def _categories(model_pts, model_out, actual_out, fav_side, fav_prob,
                exp_total, actual_total, win_prob_winner):
    if model_pts >= MAX_PTS:
        return ["sin_error"]
    cats = ["error_marcador_exacto"]
    if (model_out == "draw") != (actual_out == "draw"):
        cats.append("error_empate")
    if fav_prob is not None and fav_prob >= 0.60 and fav_side != actual_out:
        cats.append("error_favorito")
    if exp_total is not None and abs(exp_total - actual_total) >= 2.0:
        cats.append("error_distribucion_goles")
    if (actual_out != "draw" and win_prob_winner is not None and win_prob_winner <= 0.20):
        cats.append("upset_real")
    return cats


def build_rows():
    src = RI.load_results_source()
    recs = RI.finalized_records(src)
    teams = LP.load_teams() if (src.mode == "feed" and recs) else None

    rows, enriched = [], []
    for rec in recs:
        aa, ab = (int(x) for x in rec["actual_score"].split("-"))
        actual_out = _outcome(aa, ab)

        if not rec["from_fallback"]:
            p = LP.predict_record(rec, teams)
            modal, penca = p["modal"], p["penca"]
            model_pts, penca_pts = p["model_points"], p["penca_points"]
            ma, mb = (int(x) for x in modal.split("-"))
            model_out = _outcome(ma, mb)
            fav_side = "home" if p["win_a"] >= p["win_b"] else "away"
            fav_prob = max(p["win_a"], p["win_b"])
            favorito_gano = (fav_side == "home" and actual_out == "home") or \
                            (fav_side == "away" and actual_out == "away")
            win_prob_winner = (p["win_a"] if actual_out == "home"
                               else p["win_b"] if actual_out == "away" else None)
            exp_total, draw_prob = p["xg_a"] + p["xg_b"], p["draw"]
            argmax_out = ("home" if p["win_a"] >= max(p["draw"], p["win_b"])
                          else "draw" if p["draw"] >= p["win_b"] else "away")
            fx = rec["fixture"]
            mercado, t60 = _has_market(fx), _has_t60(fx)
        else:
            modal, penca = rec["model_score"], rec["penca_score"]
            model_pts, penca_pts = rec["model_points"], rec["penca_points"]
            ma, mb = (int(x) for x in modal.split("-"))
            model_out = _outcome(ma, mb)
            fav_side = fav_prob = exp_total = draw_prob = argmax_out = win_prob_winner = None
            favorito_gano = mercado = t60 = None

        model_exact = modal == rec["actual_score"]
        rows.append({
            "fecha": rec.get("date", "n/d"),
            "partido": rec["title"],
            "marcador_real": rec["actual_score"],
            "pick_modelo": modal,
            "pick_penca": penca,
            "puntos_modelo": model_pts,
            "puntos_penca": penca_pts,
            "resultado_correcto": _yn(model_out == actual_out),
            "empate": _yn(actual_out == "draw"),
            "favorito_gano": _yn(favorito_gano),
            "mercado_disponible": _yn(mercado),
            "t60_disponible": _yn(t60),
        })
        enriched.append({
            "model_pts": model_pts, "penca_pts": penca_pts,
            "model_out": model_out, "actual_out": actual_out, "argmax_out": argmax_out,
            "model_exact": model_exact, "actual_draw": actual_out == "draw",
            "exp_draw_prob": draw_prob, "exp_total": exp_total, "actual_total": aa + ab,
            "favorito_gano": favorito_gano,
            "categories": _categories(model_pts, model_out, actual_out, fav_side,
                                      fav_prob, exp_total, aa + ab, win_prob_winner),
        })
    return rows, enriched, src


def accumulate(enriched):
    n = len(enriched) or 1
    model_e = [e for e in enriched if e["exp_total"] is not None]
    cat_counts = {}
    for e in enriched:
        for c in e["categories"]:
            if c != "sin_error":
                cat_counts[c] = cat_counts.get(c, 0) + 1
    fav_win = [e for e in model_e if e["favorito_gano"]]
    fav_lose = [e for e in model_e if e["favorito_gano"] is False]

    def _sub(sample):
        if not sample:
            return {"n": 0, "model_avg": 0.0, "penca_avg": 0.0, "exact_rate": 0.0}
        k = len(sample)
        return {"n": k,
                "model_avg": sum(e["model_pts"] for e in sample) / k,
                "penca_avg": sum(e["penca_pts"] for e in sample) / k,
                "exact_rate": sum(e["model_exact"] for e in sample) / k}

    argmax_e = [e for e in enriched if e["argmax_out"] is not None]
    return {
        "n": len(enriched),
        "acc_1x2_pick_modal": sum(e["model_out"] == e["actual_out"] for e in enriched) / n,
        "acc_1x2_argmax": (sum(e["argmax_out"] == e["actual_out"] for e in argmax_e) / len(argmax_e)
                           if argmax_e else 0.0),
        "exact_hit_rate": sum(e["model_exact"] for e in enriched) / n,
        "penca_avg_model": sum(e["model_pts"] for e in enriched) / n,
        "penca_avg_penca": sum(e["penca_pts"] for e in enriched) / n,
        "cat_counts": cat_counts,
        "draws_obs": sum(e["actual_draw"] for e in model_e),
        "draws_exp": sum(e["exp_draw_prob"] for e in model_e),
        "goals_obs": sum(e["actual_total"] for e in model_e),
        "goals_exp": sum(e["exp_total"] for e in model_e),
        "n_model": len(model_e),
        "fav_win": _sub(fav_win), "fav_lose": _sub(fav_lose),
    }


def write_md(rows, acc, src):
    n = acc["n"]
    L = [
        "# Tracker acumulativo — Mundial 2026", "",
        f"**Partidos finalizados registrados: {n}.** Fuente primaria: `{src.source}` "
        f"(modo `{src.mode}`). Se auto-actualiza desde el feed con contexto real; los picks "
        "reproducen los de producción y los puntos usan la regla 8/5/3.",
        "⚠️ Con n<30 las métricas son **exploratorias** (VALIDATION_GATE): seguimiento, no inferencia.",
        "Sin cambios al modelo: solo medición.", "",
        "## Partidos", "",
        "| fecha | partido | real | pick modelo | pick Penca | pts modelo | pts Penca | result. correcto | empate | favorito ganó | mercado | T-60 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        L.append("| " + " | ".join(str(r[c]) for c in COLUMNS) + " |")

    fw, fl = acc["fav_win"], acc["fav_lose"]
    L += [
        "", "## Métricas acumuladas", "",
        f"- **Accuracy 1X2 (pick modal):** {acc['acc_1x2_pick_modal']*100:.0f}% "
        f"({int(round(acc['acc_1x2_pick_modal']*n))}/{n}) — resultado implícito del marcador elegido.",
        f"- **Accuracy 1X2 (argmax probabilístico):** {acc['acc_1x2_argmax']*100:.0f}% "
        f"— capacidad discriminante del modelo (ML).",
        f"- **Exact score hit rate (modal):** {acc['exact_hit_rate']*100:.0f}% "
        f"({int(round(acc['exact_hit_rate']*n))}/{n}).",
        f"- **Puntos Penca promedio:** modelo {acc['penca_avg_model']:.2f} · "
        f"pick Penca {acc['penca_avg_penca']:.2f} (máx {MAX_PTS:.0f}).",
        "", "### Errores por categoría",
    ]
    if acc["cat_counts"]:
        for c, k in sorted(acc["cat_counts"].items(), key=lambda kv: -kv[1]):
            L.append(f"- {c}: {k}")
    else:
        L.append("- (sin errores)")
    L += [
        "", "### Empates: observados vs esperados",
        f"- Observados: **{acc['draws_obs']}** · Esperados (Σ prob. empate del modelo): "
        f"**{acc['draws_exp']:.2f}** → desvío {acc['draws_obs']-acc['draws_exp']:+.2f}.",
        "", "### Goles: observados vs esperados",
        f"- Total observado: **{acc['goals_obs']}** · esperado: **{acc['goals_exp']:.2f}** "
        f"(desvío {acc['goals_obs']-acc['goals_exp']:+.2f}).",
        f"- Promedio por partido: observado **{acc['goals_obs']/(acc['n_model'] or 1):.2f}** · "
        f"esperado **{acc['goals_exp']/(acc['n_model'] or 1):.2f}**.",
        "", "### Rendimiento según el favorito",
        f"- **Favorito ganó** (n={fw['n']}): pts modelo {fw['model_avg']:.2f} · "
        f"pts Penca {fw['penca_avg']:.2f} · exact {fw['exact_rate']*100:.0f}%.",
        f"- **Favorito NO ganó** (n={fl['n']}): pts modelo {fl['model_avg']:.2f} · "
        f"pts Penca {fl['penca_avg']:.2f} · exact {fl['exact_rate']*100:.0f}%.",
        "", "_'mercado disponible' = el feed trae odds del proveedor; 'T-60 disponible' = "
        "hay alineación confirmada. Indica disponibilidad de señal, no que se haya aplicado un ajuste._",
    ]
    if n <= 3:
        L += ["", "_La fuente local solo contiene "
              f"{n} finalizado(s); para más partidos hay que actualizar `fixtures_live_2026.json`. "
              "No se inventaron resultados._"]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    rows, enriched, src = build_rows()
    acc = accumulate(enriched)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(COLUMNS), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    write_md(rows, acc, src)
    RI.generate_reports()  # inventario + consistencia de fuentes

    print(f"Tracker actualizado: fuente={src.source} (modo {src.mode}); {acc['n']} partidos finalizados")
    print(f"Acc1X2(modal)={acc['acc_1x2_pick_modal']*100:.0f}% Acc1X2(argmax)={acc['acc_1x2_argmax']*100:.0f}% "
          f"Exact={acc['exact_hit_rate']*100:.0f}% PencaProm(modelo/penca)={acc['penca_avg_model']:.2f}/{acc['penca_avg_penca']:.2f}")
    print(f"Empates obs/esp={acc['draws_obs']}/{acc['draws_exp']:.2f} Goles obs/esp={acc['goals_obs']}/{acc['goals_exp']:.2f}")
    if acc["n"] <= 3:
        print("Aviso: la fuente local solo contiene 3 finalizados; actualizar fixtures_live_2026.json para más.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
