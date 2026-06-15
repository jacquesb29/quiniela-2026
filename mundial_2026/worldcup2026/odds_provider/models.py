"""Modelos y validación de cuotas pre-match (1X2).

Reglas duras:
- Solo se aceptan snapshots PRE-MATCH (`open`, `t60`).
- Se rechazan `live` y `closing` para decisiones previas al partido.
- Cada cuota registra bookmaker y timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List

# Tipos de snapshot.
SNAPSHOT_OPEN = "open"      # pre-match, lejos del kickoff
SNAPSHOT_T60 = "t60"        # pre-match, cerca del kickoff (~<=90 min)
SNAPSHOT_LIVE = "live"      # partido en juego — PROHIBIDO para pre-match
SNAPSHOT_CLOSING = "closing"  # cierre — PROHIBIDO para decisiones previas

ACCEPTED_PREMATCH = frozenset({SNAPSHOT_OPEN, SNAPSHOT_T60, "prematch", "pre_match"})
REJECTED_FOR_PREMATCH = frozenset({SNAPSHOT_LIVE, SNAPSHOT_CLOSING})

# Cordura de cuotas decimales.
MIN_DECIMAL_ODDS = 1.01
MAX_DECIMAL_ODDS = 1000.0
MIN_OVERROUND = 1.00   # suma de probabilidades implícitas (1/odds); <1 sería arbitraje imposible
MAX_OVERROUND = 1.60   # margen de casa razonable para 1X2


@dataclass(frozen=True)
class OddsQuote:
    match_id: str
    kickoff_utc: str
    home_team: str
    away_team: str
    home_odds: float
    draw_odds: float
    away_odds: float
    bookmaker: str
    captured_at: str
    snapshot_type: str
    source: str = "the_odds_api"

    def as_dict(self) -> dict:
        return asdict(self)

    def dedup_key(self):
        return (self.match_id, self.bookmaker, self.snapshot_type)


def implied_overround(quote: OddsQuote) -> float:
    return (1.0 / quote.home_odds) + (1.0 / quote.draw_odds) + (1.0 / quote.away_odds)


def is_prematch_snapshot(snapshot_type: str) -> bool:
    return str(snapshot_type or "").strip().lower() in ACCEPTED_PREMATCH


def validate_odds(quote: OddsQuote) -> List[str]:
    """Devuelve la lista de problemas (vacía = válida)."""
    problems: List[str] = []
    for name, val in (("home", quote.home_odds), ("draw", quote.draw_odds), ("away", quote.away_odds)):
        if val is None or not isinstance(val, (int, float)):
            problems.append(f"{name}_odds no numérica")
        elif not (MIN_DECIMAL_ODDS <= float(val) <= MAX_DECIMAL_ODDS):
            problems.append(f"{name}_odds fuera de rango ({val})")
    snap = str(quote.snapshot_type or "").strip().lower()
    if snap in REJECTED_FOR_PREMATCH:
        problems.append(f"snapshot {snap} no permitido para pre-match")
    elif not is_prematch_snapshot(snap):
        problems.append(f"snapshot {snap!r} no reconocido como pre-match")
    if not quote.bookmaker:
        problems.append("bookmaker vacío")
    if not quote.captured_at:
        problems.append("captured_at vacío")
    if not problems:
        ovr = implied_overround(quote)
        if not (MIN_OVERROUND <= ovr <= MAX_OVERROUND):
            problems.append(f"overround implausible ({ovr:.3f})")
    return problems


def is_valid(quote: OddsQuote) -> bool:
    return not validate_odds(quote)
