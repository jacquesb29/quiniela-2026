"""Genera data/market_odds_input.csv automáticamente desde una API oficial de cuotas.

Primaria: The Odds API (THE_ODDS_API_KEY). Descarga 1X2 pre-match, valida integridad,
elimina duplicados, consensúa entre casas y escribe el CSV en el formato de F1.

Seguridad operativa:
- NUNCA odds live ni closing para pre-match (se descartan en el provider/modelos).
- Registra bookmaker y timestamp.
- Caché + reintentos + manejo de rate-limit (en el provider).
- FALLBACK: si no hay API key, o la API falla, o no hay cuotas válidas, NO sobreescribe;
  conserva el CSV existente y deja un warning. No inventa odds. No hace scraping.

Uso:
    python3 sync_market_odds.py            # genera/actualiza el CSV (con backup .bak)
    python3 sync_market_odds.py --dry-run  # no escribe; solo informa
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.odds_provider import (F1_COLUMNS, OddsProviderError, TheOddsApiProvider,
                                        best_quote_per_match, build_f1_rows, collect_quotes,
                                        dedup_quotes, reject_invalid)
from worldcup2026.odds_provider.sync_odds import now_utc

MARKET_INPUT = ROOT / "data" / "market_odds_input.csv"


def generate_rows(provider: TheOddsApiProvider, now=None):
    """Devuelve (rows, stats). Lanza OddsProviderError si la API falla."""
    now = now or now_utc()
    quotes = collect_quotes(provider, now=now)
    quotes = dedup_quotes(quotes)
    good, bad = reject_invalid(quotes)
    by_match = best_quote_per_match(good)
    rows = build_f1_rows(by_match)
    stats = {"raw": len(quotes), "valid": len(good), "rejected": len(bad), "matches": len(rows)}
    return rows, stats


def write_csv(rows, path: Path = MARKET_INPUT):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(F1_COLUMNS), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in F1_COLUMNS})
    tmp.replace(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sync de cuotas pre-match → data/market_odds_input.csv")
    parser.add_argument("--dry-run", action="store_true", help="no escribe; solo informa")
    parser.add_argument("--api-key", default=None, help="override de THE_ODDS_API_KEY")
    args = parser.parse_args(argv)

    provider = TheOddsApiProvider(api_key=args.api_key or "")

    if not provider.has_key:
        print("[fallback] THE_ODDS_API_KEY no configurada → se conserva el CSV existente. "
              "No se inventan odds. Exporta THE_ODDS_API_KEY para activar el sync.", file=sys.stderr)
        print(f"CSV intacto: {MARKET_INPUT} (existe={MARKET_INPUT.exists()})")
        return 0

    try:
        rows, stats = generate_rows(provider)
    except OddsProviderError as exc:
        print(f"[fallback] API falló ({exc}) → se conserva el CSV existente; no se sobreescribe.",
              file=sys.stderr)
        return 0

    if not rows:
        print("[fallback] la API no devolvió cuotas pre-match válidas → CSV existente intacto.",
              file=sys.stderr)
        return 0

    print(f"Cuotas: brutas={stats['raw']} válidas={stats['valid']} "
          f"rechazadas={stats['rejected']} partidos={stats['matches']}")
    if args.dry_run:
        print("[dry-run] no se escribió el CSV.")
        for r in rows[:10]:
            print(f"  {r['match_id']}: {r['odds_home']}/{r['odds_draw']}/{r['odds_away']} "
                  f"({r['source']}, {r['snapshot_type']})")
        return 0

    write_csv(rows)
    print(f"Escrito {MARKET_INPUT} ({stats['matches']} partidos). Backup: {MARKET_INPUT.name}.bak")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
