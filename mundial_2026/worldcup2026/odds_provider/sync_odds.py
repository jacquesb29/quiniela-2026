"""Orquestación de bajo nivel: recolectar, deduplicar, consensuar y mapear a F1.

No hace I/O de archivos de salida (eso vive en sync_market_odds.py). Aquí solo
transformaciones puras + recolección vía el provider inyectado.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from .models import OddsQuote, is_valid
from .provider import TheOddsApiProvider, consensus_quote

# Cabecera EXACTA esperada por F1 (data/market_odds_input.csv).
F1_COLUMNS = (
    "match_id", "kickoff_utc", "captured_at_utc", "snapshot_type", "source", "odds_format",
    "odds_home", "odds_draw", "odds_away", "total_line", "odds_over", "odds_under",
    "handicap_line", "odds_hcap_home", "odds_hcap_away", "tt_home_line", "odds_tt_home_over",
    "odds_tt_home_under", "tt_away_line", "odds_tt_away_over", "odds_tt_away_under", "note",
)


def collect_quotes(provider: TheOddsApiProvider, now: Optional[datetime] = None) -> List[OddsQuote]:
    return provider.fetch_quotes(now=now)


def dedup_quotes(quotes: List[OddsQuote]) -> List[OddsQuote]:
    """Elimina duplicados por (match_id, bookmaker, snapshot_type); conserva el primero."""
    seen = set()
    out: List[OddsQuote] = []
    for q in quotes:
        key = q.dedup_key()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def reject_invalid(quotes: List[OddsQuote]):
    """Devuelve (válidas, descartadas)."""
    good, bad = [], []
    for q in quotes:
        (good if is_valid(q) else bad).append(q)
    return good, bad


def best_quote_per_match(quotes: List[OddsQuote]) -> Dict[str, OddsQuote]:
    by_match: Dict[str, List[OddsQuote]] = {}
    for q in quotes:
        by_match.setdefault(q.match_id, []).append(q)
    return {mid: consensus_quote(qs) for mid, qs in by_match.items()}


def quote_to_f1_row(q: OddsQuote) -> dict:
    row = {col: "" for col in F1_COLUMNS}
    row.update({
        "match_id": q.match_id,
        "kickoff_utc": q.kickoff_utc,
        "captured_at_utc": q.captured_at,
        "snapshot_type": q.snapshot_type,
        "source": f"{q.source}:{q.bookmaker}",
        "odds_format": "decimal",
        "odds_home": q.home_odds,
        "odds_draw": q.draw_odds,
        "odds_away": q.away_odds,
        "note": "auto: The Odds API (consenso multi-casa)",
    })
    return row


def build_f1_rows(by_match: Dict[str, OddsQuote]) -> List[dict]:
    rows = [quote_to_f1_row(q) for q in by_match.values()]
    rows.sort(key=lambda r: (r["kickoff_utc"], r["match_id"]))
    return rows


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
