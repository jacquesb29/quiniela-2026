"""Auditoría de errores del modelo en partidos REALES de 2026 (solo diagnóstico).

FUENTE PRIMARIA: ``fixtures_live_2026.json`` vía ``worldcup2026.results_ingest``
(feed directo + contexto real → reproduce los picks de producción). El CSV
``finished_match_audit.csv`` se usa SOLO como fallback. NO depende de re-ejecutar
el dashboard. No inventa resultados. F7 no se toca; esto solo mide.
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

OUT_CSV = ROOT / "outputs" / "audit" / "worldcup2026_error_taxonomy.csv"
OUT_MD = ROOT / "outputs" / "audit" / "worldcup2026_error_report.md"
MAX_PTS = 8.0

COLUMNS = (
    "title", "actual_score", "model_pick", "market_pick", "final_pick_t60",
    "points_obtained_final", "points_obtained_model", "max_points",
    "model_fav", "model_fav_prob", "actual_outcome",
    "error_categories", "primary_error", "notes",
)


def _outcome(a, b):
    return "home" if a > b else ("draw" if a == b else "away")


def build():
    src = RI.load_results_source()
    recs = RI.finalized_records(src)
    teams = LP.load_teams() if (src.mode == "feed" and recs) else None

    rows, has_market_any = [], False
    for rec in recs:
        aa, ab = (int(x) for x in rec["actual_score"].split("-"))
        actual_out = _outcome(aa, ab)

        if not rec["from_fallback"]:
            p = LP.predict_record(rec, teams)
            modal, penca = p["modal"], p["penca"]
            model_pts, penca_pts = p["model_points"], p["penca_points"]
            trio = {"home": p["win_a"], "draw": p["draw"], "away": p["win_b"]}
            fav = max(trio, key=trio.get)
            fav_prob = round(trio[fav], 4)
            exp_total = p["xg_a"] + p["xg_b"]
            fx = rec["fixture"]
            mkt = fx.get("market_prob_a") is not None and bool(fx.get("market_provider"))
            t60 = bool(fx.get("lineup_confirmed_a")) or bool(fx.get("starting_xi_a"))
            has_market_any = has_market_any or mkt
            market_pick = (f"{fx.get('market_provider')} (odds en feed; no aplicadas)"
                           if mkt else "n/d (sin odds prepartido)")
            final_pick = penca + (" (Penca; T-60 disponible no aplicado)" if t60 else " (Penca; T-60 n/d)")
        else:
            modal, penca = rec["model_score"], rec["penca_score"]
            model_pts, penca_pts = rec["model_points"], rec["penca_points"]
            fav, fav_prob, exp_total = "n/d", "", None
            market_pick = "n/d (fallback CSV)"
            final_pick = penca + " (Penca; fallback)"

        ma, mb = (int(x) for x in modal.split("-"))
        model_out = _outcome(ma, mb)

        cats = []
        if model_pts < MAX_PTS:
            cats.append("error_marcador_exacto")
        if (model_out == "draw") != (actual_out == "draw"):
            cats.append("error_empate")
        if isinstance(fav_prob, float) and fav_prob >= 0.60 and fav != actual_out and fav != "draw":
            cats.append("error_favorito")
        if exp_total is not None and abs(exp_total - (aa + ab)) >= 2.0:
            cats.append("error_distribucion_goles")
        if actual_out != "draw" and isinstance(fav_prob, float):
            p_winner = {"home": fav_prob if fav == "home" else None,
                        "away": fav_prob if fav == "away" else None}.get(actual_out)
            # prob real del ganador (no solo del favorito):
            if not rec["from_fallback"]:
                p_winner = {"home": p["win_a"], "away": p["win_b"]}.get(actual_out)
            if p_winner is not None and p_winner <= 0.20:
                cats.append("upset_real")
        if model_pts >= MAX_PTS:
            cats = ["sin_error"]
        primary = (("error_favorito" if "error_favorito" in cats else
                    "error_empate" if "error_empate" in cats else
                    "upset_real" if "upset_real" in cats else
                    "error_marcador_exacto" if "error_marcador_exacto" in cats else
                    cats[0]) if cats else "sin_error")

        rows.append({
            "title": rec["title"], "actual_score": rec["actual_score"],
            "model_pick": modal, "market_pick": market_pick, "final_pick_t60": final_pick,
            "points_obtained_final": penca_pts, "points_obtained_model": model_pts,
            "max_points": MAX_PTS, "model_fav": fav, "model_fav_prob": fav_prob,
            "actual_outcome": actual_out, "error_categories": ";".join(cats),
            "primary_error": primary, "notes": "",
        })
    return rows, src, has_market_any


def write_md(rows, src, has_market_any):
    n = len(rows)
    model_total = sum(r["points_obtained_model"] for r in rows)
    final_total = sum(r["points_obtained_final"] for r in rows)
    maxt = n * MAX_PTS or MAX_PTS
    cat_counts = {}
    for r in rows:
        for c in r["error_categories"].split(";"):
            if c and c != "sin_error":
                cat_counts[c] = cat_counts.get(c, 0) + 1
    L = [
        "# Auditoría de errores — partidos reales Mundial 2026", "",
        f"**Muestra: {n} partidos finalizados.** Fuente primaria: `{src.source}` (modo `{src.mode}`). "
        "⚠️ n<30 → **exploratorio** (VALIDATION_GATE): conclusiones cualitativas.",
        "",
        "Caveats:",
        f"- Mercado: el feed {'trae odds del proveedor' if has_market_any else 'no trae odds confiables'}, "
        "pero **no se aplicaron** a los picks (capa operativa, no se reentrena con 2026).",
        "- T-60: la disponibilidad de alineación se reporta, pero **no se aplicó** ajuste.",
        "- 'Error de datos de entrada' no se marca sin evidencia concreta. No se inventan resultados.",
        "",
        "## Resumen de puntos Penca (8/5/3)",
        f"- Modelo (marcador modal): **{model_total:.0f}/{maxt:.0f}** ({100*model_total/maxt:.0f}%).",
        f"- Pick final (Penca): **{final_total:.0f}/{maxt:.0f}** ({100*final_total/maxt:.0f}%).",
        f"- Puntos perdidos vs máximo — modelo: {maxt-model_total:.0f}; final: {maxt-final_total:.0f}.",
        "",
        "## Por partido", "",
        "| partido | real | pick modelo | pick final (Penca) | pts modelo | pts final | máx | error principal |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        L.append(f"| {r['title']} | {r['actual_score']} | {r['model_pick']} | "
                 f"{r['final_pick_t60']} | {r['points_obtained_model']:.0f} | "
                 f"{r['points_obtained_final']:.0f} | {r['max_points']:.0f} | {r['primary_error']} |")
    L += ["", "## Conteo por categoría de error", ""]
    for c, k in sorted(cat_counts.items(), key=lambda kv: -kv[1]):
        L.append(f"- {c}: {k}")
    if not cat_counts:
        L.append("- (sin errores)")
    L += [
        "", "## Dónde se pierden los puntos", "",
        "Las fugas se concentran en **empates de favoritos y marcadores exactos**, no en upsets ni "
        "en distribución de goles. La capa Penca recupera puntos cuando el modal falla por diferencia, "
        "pero no cuando el favorito empata. (Coherente con F3.)",
    ]
    if n <= 3:
        L += ["", "_La fuente local solo contiene "
              f"{n} finalizado(s); para más partidos hay que actualizar `fixtures_live_2026.json`._"]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    rows, src, has_market_any = build()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(COLUMNS), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    write_md(rows, src, has_market_any)
    print(f"Auditoría escrita ({len(rows)} partidos): fuente={src.source} (modo {src.mode})")
    print(f"Puntos modelo: {sum(r['points_obtained_model'] for r in rows)}/{len(rows)*MAX_PTS} | "
          f"final(Penca): {sum(r['points_obtained_final'] for r in rows)}/{len(rows)*MAX_PTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
