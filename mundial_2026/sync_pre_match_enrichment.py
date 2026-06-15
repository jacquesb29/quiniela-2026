"""Enriquecimiento automático prepartido para los próximos partidos.

Reúne (cuando hay fuente): odds (vía sync_market_odds), alineaciones y bajas
(API-Football si hay key, si no el feed local), portero titular (solo de XI
confirmado), y actualiza data/t60_inputs.csv SOLO con datos confirmados.

Seguridad: no inventa datos; todo lleva source+timestamp; nunca usa datos
post-kickoff ni live; no rompe si falta una API key (fallback a CSV local).
No toca el modelo, pesos, lambdas ni selector Penca.

Uso:
    python3 sync_pre_match_enrichment.py            # enriquece y escribe outputs + t60
    python3 sync_pre_match_enrichment.py --dry-run  # no modifica data/ (solo reportes)
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026 import results_ingest as RI
from worldcup2026.enrichment import default_source, enrich, update_t60
from worldcup2026.enrichment.models import now_utc, parse_iso

OUT_DIR = ROOT / "outputs" / "enrichment"
STATUS_CSV = OUT_DIR / "enrichment_status.csv"
STATUS_MD = OUT_DIR / "enrichment_status.md"
LINEUPS_CSV = OUT_DIR / "lineups_snapshot.csv"
INJURIES_CSV = OUT_DIR / "injuries_snapshot.csv"

STATUS_COLUMNS = ("match_id", "kickoff_utc", "team_a", "team_b", "odds_status", "fixture_status",
                  "lineup_status", "injury_status", "goalkeeper_status", "t60_status",
                  "source", "captured_at_utc", "warnings")
LINEUP_COLUMNS = ("match_id", "team", "player_name", "position", "is_starting",
                  "is_goalkeeper", "source", "captured_at_utc")
INJURY_COLUMNS = ("match_id", "team", "player_name", "status", "source", "captured_at_utc")


def upcoming_fixtures(now: datetime, horizon_h: int):
    fixtures = RI.load_fixtures() or []
    horizon = now + timedelta(hours=horizon_h)
    out = []
    for f in fixtures:
        if RI.has_final_score(f):
            continue
        ko = parse_iso(f.get("kickoff_utc"))
        if ko is not None and now <= ko <= horizon:
            out.append(f)
    out.sort(key=lambda f: f.get("kickoff_utc") or "")
    return out


def run(now=None, horizon_h: int = 24, dry_run: bool = False, source=None, write_t60: bool = True):
    now = now or now_utc()
    source = source or default_source()
    fixtures = upcoming_fixtures(now, horizon_h)
    records, players, injuries = enrich(fixtures, source, now)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_status_csv(records)
    _write_lineups_csv(players)
    _write_injuries_csv(injuries)
    _write_status_md(records, now, dry_run)

    t60_written = t60_kept = 0
    if write_t60:
        t60_written, t60_kept = update_t60(records, dry_run=dry_run)

    return {
        "now": now, "horizon_h": horizon_h, "upcoming": len(fixtures),
        "records": records, "players": players, "injuries": injuries,
        "confirmed_lineups": sum(1 for r in records if r.lineup_confirmed),
        "with_gk": sum(1 for r in records if r.goalkeeper_status == "confirmed"),
        "with_injuries": sum(1 for r in records if r.injury_status == "available"),
        "t60_written": t60_written, "t60_kept": t60_kept, "dry_run": dry_run,
    }


def _write_status_csv(records):
    with STATUS_CSV.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(STATUS_COLUMNS), lineterminator="\n")
        w.writeheader()
        for r in records:
            w.writerow({
                "match_id": r.match_id, "kickoff_utc": r.kickoff_utc, "team_a": r.team_a,
                "team_b": r.team_b, "odds_status": r.odds_status, "fixture_status": r.fixture_status,
                "lineup_status": r.lineup_status, "injury_status": r.injury_status,
                "goalkeeper_status": r.goalkeeper_status, "t60_status": r.t60_status,
                "source": r.source, "captured_at_utc": r.captured_at_utc,
                "warnings": "; ".join(r.warnings)})


def _write_lineups_csv(players):
    with LINEUPS_CSV.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(LINEUP_COLUMNS), lineterminator="\n")
        w.writeheader()
        for p in players:
            w.writerow({"match_id": p.match_id, "team": p.team, "player_name": p.player_name,
                        "position": p.position, "is_starting": p.is_starting,
                        "is_goalkeeper": p.is_goalkeeper, "source": p.source,
                        "captured_at_utc": p.captured_at})


def _write_injuries_csv(injuries):
    with INJURIES_CSV.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(INJURY_COLUMNS), lineterminator="\n")
        w.writeheader()
        for i in injuries:
            w.writerow({"match_id": i.match_id, "team": i.team, "player_name": i.player_name,
                        "status": i.status, "source": i.source, "captured_at_utc": i.captured_at})


def _write_status_md(records, now, dry_run):
    L = [
        "# Enriquecimiento prepartido — Mundial 2026", "",
        f"- Corrida: {now.isoformat()} {'(dry-run)' if dry_run else ''}",
        f"- Próximos partidos: {len(records)}",
        f"- Alineaciones confirmadas: {sum(1 for r in records if r.lineup_confirmed)}",
        f"- Con portero confirmado: {sum(1 for r in records if r.goalkeeper_status == 'confirmed')}",
        f"- Con bajas confiables: {sum(1 for r in records if r.injury_status == 'available')}",
        "",
        "_No inventa datos; todo lleva source+timestamp; no usa datos post-kickoff ni live. "
        "No modifica el modelo._", "",
        "| partido | kickoff | odds | lineup | injury | GK | T-60 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in records:
        L.append(f"| {r.team_a} vs {r.team_b} | {r.kickoff_utc} | {r.odds_status} | "
                 f"{r.lineup_status} | {r.injury_status} | {r.goalkeeper_status} | {r.t60_status} |")
    if not records:
        L.append("| (sin próximos) | | | | | | |")
    STATUS_MD.write_text("\n".join(L), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Enriquecimiento prepartido 2026")
    parser.add_argument("--dry-run", action="store_true", help="no modifica data/ (solo reportes)")
    parser.add_argument("--now", default=None, help="ISO UTC de referencia")
    parser.add_argument("--horizon-hours", type=int, default=24)
    parser.add_argument("--no-t60-write", action="store_true", help="no escribir data/t60_inputs.csv")
    args = parser.parse_args(argv)

    now = parse_iso(args.now) or now_utc()
    meta = run(now=now, horizon_h=args.horizon_hours, dry_run=args.dry_run,
               write_t60=not args.no_t60_write)
    print(f"Enriquecimiento: próximos={meta['upcoming']} | XI confirmados={meta['confirmed_lineups']} | "
          f"GK={meta['with_gk']} | bajas={meta['with_injuries']} | "
          f"t60_escritos={meta['t60_written']} (dry_run={meta['dry_run']})")
    print(f"Reportes: {STATUS_MD}, {STATUS_CSV}, {LINEUPS_CSV}, {INJURIES_CSV}")
    print("Modelo intacto: no se tocaron pesos/lambdas/Penca/flags ni predicciones.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
