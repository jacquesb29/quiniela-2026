"""Operación diaria automática de la quiniela (solo operativo, NO mejora el modelo).

Orquesta, en orden y a prueba de fallos:
  1. actualizar/validar fixtures_live_2026.json (sync seguro con fallback al feed local);
  2. auditar partidos finalizados;
  3. identificar próximos partidos dentro de las próximas 24 h;
  4. validar odds en data/market_odds_input.csv (rechaza closing prepartido);
  5. validar T-60 en data/t60_inputs.csv;
  6. correr run_market_t60_pipeline.py;
  7. correr run_improvement_review.py;
  8. generar resumen operativo + CSV de picks.

NO cambia el modelo, pesos, lambdas, metodología, selector Penca ni flags.
NO inventa resultados ni odds. NO usa closing odds para decisiones prepartido.
Si el sync falla, usa el último feed local y deja un warning.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026 import results_ingest as RI
from worldcup2026 import live_prediction as LP

SYNC_SCRIPT = ROOT / "sync_live_data_2026.py"
MARKET_INPUT = ROOT / "data" / "market_odds_input.csv"
T60_INPUT = ROOT / "data" / "t60_inputs.csv"
MARKET_DECISION_LOG = ROOT / "outputs" / "market" / "market_decision_log.csv"
T60_DECISION_LOG = ROOT / "outputs" / "market" / "t60_decision_log.csv"

OPS_DIR = ROOT / "outputs" / "ops"
SUMMARY_MD = OPS_DIR / "daily_quiniela_summary.md"
PICKS_CSV = OPS_DIR / "daily_quiniela_picks.csv"

PICKS_COLUMNS = (
    "match_id", "kickoff_utc", "team_a", "team_b", "model_pick", "market_pick",
    "final_pick", "final_score_recommendation", "confidence_label", "action",
    "reason", "odds_available", "t60_available", "warnings",
)

# Vocabulario de acciones operativas requerido.
ACTIONS = ("trust_model", "follow_market", "shade_to_market", "no_market_available")
_ACTION_MAP = {"keep_pick": "trust_model", "": "no_market_available"}
CLOSING_SNAPSHOTS = {"closing", "close", "cierre"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _pair_key(team_a: str, team_b: str) -> str:
    return f"{team_a}_vs_{team_b}".strip().lower().replace(" ", "_")


def _pair_key_from_market_id(match_id: str) -> str:
    """'20260612_Mexico_vs_South_Africa' -> 'mexico_vs_south_africa'."""
    parts = (match_id or "").split("_", 1)
    rest = parts[1] if len(parts) == 2 and parts[0].isdigit() else (match_id or "")
    return rest.strip().lower()


def _1x2_side(win_a: float, draw: float, win_b: float) -> str:
    return "home" if win_a >= max(draw, win_b) else ("draw" if draw >= win_b else "away")


def _parse_iso(value: str):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Paso 0: sync de odds (opcional, a prueba de fallos)
# --------------------------------------------------------------------------- #
def run_odds_sync(enabled: bool, dry_run: bool = False):
    """Actualiza data/market_odds_input.csv desde la API antes de F1/T-60.

    Devuelve (odds_source, msg):
      odds_source ∈ {"api", "local_csv"}.
    Nunca rompe: sin key / API caída / sin cuotas → conserva el CSV local y avisa.
    No inventa odds.
    """
    if not enabled:
        return ("local_csv", "sync de odds desactivado (--no-odds-sync); se usa el CSV local existente")
    try:
        import sync_market_odds
        from worldcup2026.odds_provider import TheOddsApiProvider, OddsProviderError
        provider = TheOddsApiProvider()
        if not provider.has_key:
            return ("local_csv", "sin THE_ODDS_API_KEY: se usa el CSV local existente (no se inventan odds)")
        try:
            rows, stats = sync_market_odds.generate_rows(provider)
        except OddsProviderError as exc:
            return ("local_csv", f"API de odds falló ({type(exc).__name__}); se usa el CSV local existente")
        if not rows:
            return ("local_csv", "la API no devolvió cuotas pre-match válidas; se usa el CSV local existente")
        if dry_run:
            return ("api", f"[dry-run] API OK con {stats['matches']} partidos; CSV NO modificado")
        sync_market_odds.write_csv(rows)
        return ("api", f"odds actualizadas desde API ({stats['matches']} partidos, "
                       f"{stats['valid']} cuotas válidas)")
    except Exception as exc:  # nunca romper la operación diaria
        return ("local_csv", f"sync de odds no disponible ({type(exc).__name__}); se usa el CSV local")


# --------------------------------------------------------------------------- #
# Paso 1: sync seguro (feed)
# --------------------------------------------------------------------------- #
def run_sync(enabled: bool, script: Path = SYNC_SCRIPT, timeout: int = 150):
    if not enabled:
        return ("skipped", "sync omitido (--no-sync); se usa el feed local existente")
    if not script.exists():
        return ("failed", f"sync no disponible ({script.name} no encontrado); se usa el último feed local")
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return ("failed", f"sync falló ({type(exc).__name__}); se usa el último feed local")
    if proc.returncode != 0:
        return ("failed", "sync devolvió error; se usa el último feed local (sin romper)")
    return ("ok", "feed actualizado por sync_live_data_2026.py")


# --------------------------------------------------------------------------- #
# Pasos 4-5: odds y T-60 disponibles
# --------------------------------------------------------------------------- #
def load_odds_index(path: Path = MARKET_INPUT) -> dict:
    idx: dict = {}
    if not path.exists():
        return idx
    for r in csv.DictReader(path.open(encoding="utf-8")):
        key = _pair_key_from_market_id(r.get("match_id", ""))
        idx.setdefault(key, []).append(r)
    return idx


def odds_status_for(key: str, odds_idx: dict):
    """Devuelve (odds_available, closing_only, note)."""
    rows = odds_idx.get(key)
    if not rows:
        return (False, False, "sin odds en data/market_odds_input.csv")
    usable = [r for r in rows if str(r.get("snapshot_type", "")).strip().lower() not in CLOSING_SNAPSHOTS]
    if not usable:
        return (False, True, "odds tipo closing rechazadas para decisión prepartido")
    return (True, False, "")


def load_t60_index(path: Path = T60_INPUT) -> dict:
    idx: dict = {}
    if not path.exists():
        return idx
    for r in csv.DictReader(path.open(encoding="utf-8")):
        idx[_pair_key_from_market_id(r.get("match_id", ""))] = r
    return idx


def t60_status_for(key: str, t60_idx: dict):
    r = t60_idx.get(key)
    if not r:
        return (False, "sin T-60 en data/t60_inputs.csv")
    confirmed = str(r.get("lineup_confirmed", "")).strip().lower() in ("true", "1", "si", "yes")
    return (confirmed, "" if confirmed else "T-60 presente pero alineación sin confirmar")


# --------------------------------------------------------------------------- #
# Paso 6-7: pipelines (a prueba de fallos)
# --------------------------------------------------------------------------- #
def _run_module_main(module_name: str, argv=None):
    try:
        mod = __import__(module_name)
        rc = mod.main(argv) if argv is not None else mod.main()
        return (int(rc or 0), "")
    except SystemExit as exc:
        return (int(exc.code or 0), "")
    except Exception as exc:  # no romper la operación diaria
        return (1, f"{module_name} falló: {type(exc).__name__}: {exc}")


def load_decision_log(path: Path, key_field: str = "match_id") -> dict:
    idx: dict = {}
    if not path.exists():
        return idx
    for r in csv.DictReader(path.open(encoding="utf-8")):
        idx[_pair_key_from_market_id(r.get(key_field, ""))] = r
    return idx


# --------------------------------------------------------------------------- #
# Construcción de picks
# --------------------------------------------------------------------------- #
def build_picks(now: datetime, horizon_h: int, sync_state, sync_msg,
                market_rc_msg, improvement_rc_msg, odds_source="local_csv", odds_msg=""):
    src = RI.load_results_source()
    fixtures = RI.load_fixtures() or []
    finalized = RI.finalized_fixtures(fixtures)

    horizon = now + timedelta(hours=horizon_h)
    upcoming = []
    for f in fixtures:
        if RI.has_final_score(f):
            continue
        ko = _parse_iso(f.get("kickoff_utc"))
        if ko is None:
            continue
        if now <= ko <= horizon:
            upcoming.append((ko, f))
    upcoming.sort(key=lambda t: t[0])

    odds_idx = load_odds_index()
    t60_idx = load_t60_index()
    market_dec = load_decision_log(MARKET_DECISION_LOG)
    t60_dec = load_decision_log(T60_DECISION_LOG)
    teams = LP.load_teams() if upcoming else None

    rows = []
    for ko, fx in upcoming:
        key = _pair_key(fx["team_a"], fx["team_b"])
        warnings = []
        if sync_state == "failed":
            warnings.append(sync_msg)

        odds_available, closing_only, odds_note = odds_status_for(key, odds_idx)
        if closing_only:
            warnings.append(odds_note)
        t60_available, t60_note = t60_status_for(key, t60_idx)
        if t60_note:
            warnings.append(t60_note)

        pred = LP.predict_fixture(fx, teams)
        if pred is None:
            rows.append({
                "match_id": fx.get("id", key), "kickoff_utc": fx.get("kickoff_utc", ""),
                "team_a": fx["team_a"], "team_b": fx["team_b"],
                "model_pick": "n/d", "market_pick": "", "final_pick": "n/d",
                "final_score_recommendation": "n/d", "confidence_label": "n/d",
                "action": "no_market_available", "reason": "equipo placeholder o fuera de roster; sin pick",
                "odds_available": odds_available, "t60_available": t60_available,
                "warnings": "; ".join(warnings + ["sin predicción de modelo"]),
            })
            continue

        model_side = _1x2_side(pred["win_a"], pred["draw"], pred["win_b"])
        model_pick = model_side
        market_pick = ""
        final_pick = model_side
        action = "no_market_available"
        reason = "sin odds usables: se confía en el modelo (trust_model por defecto)"
        confidence = pred["confidence_label"]
        score_reco = pred["recommended_score"]

        if odds_available and key in market_dec:
            md = market_dec[key]
            model_pick = md.get("model_pick") or model_side
            market_pick = md.get("market_pick") or ""
            final_pick = md.get("final_pick") or model_side
            action = _ACTION_MAP.get(md.get("action", ""), md.get("action") or "no_market_available")
            reason = md.get("reason") or reason
            if md.get("confidence_label"):
                confidence = md["confidence_label"]
            # T-60 puede mover el pick si hay alineación
            if t60_available and key in t60_dec:
                td = t60_dec[key]
                if str(td.get("changed", "")).strip().lower() in ("true", "1", "si", "yes"):
                    final_pick = td.get("pick_after") or final_pick
                    reason = f"T-60 ({td.get('trigger', 'ajuste')}): {td.get('reason', '')}".strip()
            if final_pick and final_pick != model_side:
                warnings.append(f"acción {action}: pick final ({final_pick}) difiere del modelo "
                                f"({model_side}); el marcador sugerido es del modelo, valida el resultado")
        elif odds_available:
            action = "trust_model"
            reason = "odds presentes pero sin decisión calculable; se mantiene el modelo"

        rows.append({
            "match_id": fx.get("id", key), "kickoff_utc": fx.get("kickoff_utc", ""),
            "team_a": fx["team_a"], "team_b": fx["team_b"],
            "model_pick": model_pick, "market_pick": market_pick, "final_pick": final_pick,
            "final_score_recommendation": score_reco, "confidence_label": confidence,
            "action": action, "reason": reason,
            "odds_available": odds_available, "t60_available": t60_available,
            "warnings": "; ".join(warnings),
        })

    meta = {
        "now": now, "horizon_h": horizon_h, "source": src.source, "mode": src.mode,
        "total_fixtures": len(fixtures), "finalized": len(finalized),
        "upcoming": len(upcoming),
        "with_odds": sum(1 for r in rows if r["odds_available"]),
        "with_t60": sum(1 for r in rows if r["t60_available"]),
        "sync_state": sync_state, "sync_msg": sync_msg,
        "market_msg": market_rc_msg, "improvement_msg": improvement_rc_msg,
        "odds_source": odds_source, "odds_msg": odds_msg,
        "finalized_list": finalized,
    }
    return rows, meta


# --------------------------------------------------------------------------- #
# Salidas
# --------------------------------------------------------------------------- #
def write_csv(rows):
    OPS_DIR.mkdir(parents=True, exist_ok=True)
    with PICKS_CSV.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(PICKS_COLUMNS), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in PICKS_COLUMNS})


def write_summary(rows, meta):
    action_counts = {a: 0 for a in ACTIONS}
    for r in rows:
        action_counts[r["action"]] = action_counts.get(r["action"], 0) + 1

    L = [
        "# Resumen operativo diario — Quiniela Mundial 2026", "",
        f"- **Corrida:** {meta['now'].isoformat()} (ventana próximas {meta['horizon_h']} h)",
        f"- **Fuente:** `{meta['source']}` (modo `{meta['mode']}`) — sync feed: **{meta['sync_state']}** ({meta['sync_msg']})",
        f"- **Odds:** origen **{meta['odds_source']}** ({meta['odds_msg']})",
        f"- **Fixtures totales:** {meta['total_fixtures']} · **finalizados:** {meta['finalized']} · "
        f"**próximos (24 h):** {meta['upcoming']}",
        f"- **Próximos con odds:** {meta['with_odds']} · **con T-60:** {meta['with_t60']}",
        f"- Pipeline mercado/T-60: {meta['market_msg'] or 'OK'} · "
        f"Revisión de mejoras: {meta['improvement_msg'] or 'OK'}",
        "",
        "_Operativo: NO cambia el modelo, pesos, lambdas, Penca ni flags. No inventa resultados ni odds._",
        "",
        "## Acciones (conteo)",
    ]
    for a in ACTIONS:
        L.append(f"- {a}: {action_counts.get(a, 0)}")

    L += ["", "## Próximos partidos — qué marcador cargar", ""]
    if rows:
        L.append("| kickoff (UTC) | partido | **marcador a cargar** | 1X2 final | conf. | acción | odds | T-60 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in rows:
            L.append(f"| {r['kickoff_utc']} | {r['team_a']} vs {r['team_b']} | "
                     f"**{r['final_score_recommendation']}** | {r['final_pick']} | "
                     f"{r['confidence_label']} | {r['action']} | "
                     f"{'sí' if r['odds_available'] else 'no'} | {'sí' if r['t60_available'] else 'no'} |")
    else:
        L.append("_No hay partidos en las próximas 24 h según el feed local._")

    # Detalle por partido (picks, razones, advertencias)
    L += ["", "## Detalle por partido", ""]
    for r in rows:
        L.append(f"### {r['team_a']} vs {r['team_b']} ({r['kickoff_utc']})")
        L.append(f"- Modelo: **{r['model_pick']}** · Mercado: {r['market_pick'] or 'n/d'} · "
                 f"Final 1X2: **{r['final_pick']}** · Acción: **{r['action']}**")
        L.append(f"- **Marcador a cargar en la quiniela: {r['final_score_recommendation']}** "
                 f"(confianza {r['confidence_label']})")
        L.append(f"- Razón: {r['reason']}")
        if r["warnings"]:
            L.append(f"- ⚠️ Advertencias: {r['warnings']}")
        L.append("")

    L += ["## Partidos finalizados detectados", ""]
    if meta["finalized_list"]:
        for f in meta["finalized_list"]:
            L.append(f"- {f['team_a']} {f['actual_score_a']}-{f['actual_score_b']} {f['team_b']}")
    else:
        L.append("- (ninguno)")
    L += ["", "_Para más resultados, actualizar `fixtures_live_2026.json` (sync). No se inventan marcadores._"]

    OPS_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_MD.write_text("\n".join(L), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Operación diaria de la quiniela 2026")
    parser.add_argument("--no-sync", action="store_true", help="no intentar actualizar el feed (usa el local)")
    parser.add_argument("--no-odds-sync", action="store_true", help="no actualizar odds desde la API (usa el CSV local)")
    parser.add_argument("--dry-run", action="store_true", help="no modifica datos de entrada (odds/feed); solo preview")
    parser.add_argument("--now", default=None, help="ISO UTC de referencia (default: ahora)")
    parser.add_argument("--horizon-hours", type=int, default=24)
    parser.add_argument("--sync-script", default=str(SYNC_SCRIPT), help="ruta al script de sync")
    parser.add_argument("--skip-pipelines", action="store_true", help="no correr market/improvement (tests)")
    args = parser.parse_args(argv)

    now = _parse_iso(args.now) or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # 0) sync de ODDS primero (a prueba de fallos: sin key / API caída → CSV local)
    odds_source, odds_msg = run_odds_sync(not args.no_odds_sync, dry_run=args.dry_run)

    # 1) sync del feed (no toca la red en dry-run)
    sync_state, sync_msg = run_sync(not args.no_sync and not args.dry_run, script=Path(args.sync_script))

    # 6-7) pipelines (no rompen la operación) — consumen el CSV ya actualizado
    market_msg = improvement_msg = ""
    if not args.skip_pipelines:
        _, market_msg = _run_module_main("run_market_t60_pipeline", argv=[])
        _, improvement_msg = _run_module_main("run_improvement_review", argv=[])

    rows, meta = build_picks(now, args.horizon_hours, sync_state, sync_msg, market_msg,
                             improvement_msg, odds_source=odds_source, odds_msg=odds_msg)
    write_csv(rows)
    write_summary(rows, meta)

    print(f"Operación diaria: {meta['now'].isoformat()} | fuente={meta['source']} sync={meta['sync_state']} "
          f"| odds={meta['odds_source']} ({meta['odds_msg']})")
    print(f"Finalizados={meta['finalized']} | próximos(24h)={meta['upcoming']} | "
          f"con_odds={meta['with_odds']} | con_t60={meta['with_t60']} | picks={len(rows)}")
    print(f"Resumen: {SUMMARY_MD}")
    print(f"Picks:   {PICKS_CSV}")
    print("Modelo intacto: no se tocaron pesos/lambdas/Penca/flags ni predicciones.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
