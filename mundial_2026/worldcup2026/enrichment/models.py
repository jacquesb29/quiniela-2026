"""Modelos y validación del enriquecimiento prepartido.

Reglas duras:
- Todo dato lleva ``source`` y ``captured_at`` (timestamp UTC).
- Nunca se usan datos capturados DESPUÉS del kickoff para decisiones prepartido.
- Nunca se inventan alineaciones, lesiones ni portero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

# Estados (vocabulario estable para los reportes).
ODDS_API = "api"
ODDS_LOCAL = "local_csv"
ODDS_NONE = "none"

FIXTURE_FEED = "feed"
FIXTURE_LOCAL = "local_fallback"

LINEUP_CONFIRMED = "confirmed"
LINEUP_UNCONFIRMED = "unconfirmed"
LINEUP_NONE = "none"

INJURY_AVAILABLE = "available"
INJURY_NONE = "none"

GK_CONFIRMED = "confirmed"
GK_NONE = "none"

T60_WRITTEN = "written"
T60_FALLBACK = "fallback_manual"
T60_SKIPPED = "skipped"


@dataclass(frozen=True)
class LineupPlayer:
    match_id: str
    team: str
    player_name: str
    position: str
    is_starting: bool
    is_goalkeeper: bool
    source: str
    captured_at: str


@dataclass(frozen=True)
class InjuryRecord:
    match_id: str
    team: str
    player_name: str
    status: str
    source: str
    captured_at: str


@dataclass
class EnrichmentRecord:
    match_id: str
    kickoff_utc: str
    team_a: str
    team_b: str
    odds_status: str = ODDS_NONE
    fixture_status: str = FIXTURE_FEED
    lineup_status: str = LINEUP_NONE
    injury_status: str = INJURY_NONE
    goalkeeper_status: str = GK_NONE
    t60_status: str = T60_SKIPPED
    source: str = ""
    captured_at_utc: str = ""
    warnings: List[str] = field(default_factory=list)
    # Datos derivados para escribir t60_inputs (solo si confirmados).
    lineup_confirmed: bool = False
    starting_gk: Optional[str] = None
    injuries_confirmed: int = 0
    gk_changed: bool = False


def parse_iso(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def is_pre_kickoff(captured_at: str, kickoff_utc: str) -> bool:
    """True solo si el dato fue capturado en o antes del kickoff (ambos parseables)."""
    cap = parse_iso(captured_at)
    ko = parse_iso(kickoff_utc)
    if cap is None or ko is None:
        return False
    return cap <= ko


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
