"""Orquestación del enriquecimiento prepartido (sin I/O de escritura).

Construye, por partido próximo, el estado de odds/fixture/lineup/injury/GK/T-60
y los snapshots de alineaciones y lesiones. No escribe archivos (eso vive en
sync_pre_match_enrichment.py / t60_writer.py). No inventa datos.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Optional

from . import injuries as inj
from . import lineups as lu
from .models import (EnrichmentRecord, GK_CONFIRMED, GK_NONE, INJURY_AVAILABLE, INJURY_NONE,
                     LINEUP_CONFIRMED, LINEUP_NONE, LINEUP_UNCONFIRMED, ODDS_LOCAL, ODDS_NONE,
                     T60_FALLBACK, T60_SKIPPED, T60_WRITTEN, iso)

ROOT = Path(__file__).resolve().parents[2]
MARKET_INPUT = ROOT / "data" / "market_odds_input.csv"
T60_INPUT = ROOT / "data" / "t60_inputs.csv"


def _pair_key_from_match_id(match_id: str) -> str:
    parts = (match_id or "").split("_", 1)
    rest = parts[1] if len(parts) == 2 and parts[0].isdigit() else (match_id or "")
    return rest.strip().lower()


def _pair_key(team_a: str, team_b: str) -> str:
    return f"{team_a}_vs_{team_b}".strip().lower().replace(" ", "_")


def _present_keys(path: Path) -> set:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as h:
        return {_pair_key_from_match_id(r.get("match_id", "")) for r in csv.DictReader(h)}


def enrich(fixtures: List[dict], source, now, fixture_status_map: Optional[dict] = None):
    """Devuelve (records, lineup_players, injury_records)."""
    from worldcup2026.odds_provider.provider import build_match_id

    odds_keys = _present_keys(MARKET_INPUT)
    t60_keys = _present_keys(T60_INPUT)
    fixture_status_map = fixture_status_map or {}

    records: List[EnrichmentRecord] = []
    all_players = []
    all_injuries = []

    for fx in fixtures:
        team_a, team_b = fx.get("team_a"), fx.get("team_b")
        mid = build_match_id(team_a, team_b, fx.get("kickoff_utc", ""))
        pkey = _pair_key(team_a, team_b)
        warnings: List[str] = []

        players, confirmed = lu.confirmed_lineup(fx, source, now)
        injuries = inj.trusted_injuries(fx, source, now)
        gk = lu.starting_goalkeeper(players, confirmed)

        # estados
        odds_status = ODDS_LOCAL if pkey in odds_keys else ODDS_NONE
        lineup_status = (LINEUP_CONFIRMED if confirmed else
                         (LINEUP_UNCONFIRMED if players else LINEUP_NONE))
        injury_status = INJURY_AVAILABLE if injuries else INJURY_NONE
        gk_status = GK_CONFIRMED if gk else GK_NONE

        if confirmed:
            t60_status = T60_WRITTEN
        elif pkey in t60_keys:
            t60_status = T60_FALLBACK
        else:
            t60_status = T60_SKIPPED

        if lineup_status == LINEUP_NONE:
            warnings.append("sin alineación disponible (no se inventa)")
        elif lineup_status == LINEUP_UNCONFIRMED:
            warnings.append("alineación no confirmada; no se escribe T-60")
        if injury_status == INJURY_NONE:
            warnings.append("sin bajas confiables")
        if gk_status == GK_NONE and confirmed:
            warnings.append("XI confirmado sin marca de portero")

        src_names = sorted({p.source for p in players} | {i.source for i in injuries})
        rec = EnrichmentRecord(
            match_id=mid, kickoff_utc=fx.get("kickoff_utc", ""), team_a=team_a, team_b=team_b,
            odds_status=odds_status, fixture_status=fixture_status_map.get(mid, "feed"),
            lineup_status=lineup_status, injury_status=injury_status,
            goalkeeper_status=gk_status, t60_status=t60_status,
            source=";".join(src_names), captured_at_utc=iso(now), warnings=warnings,
            lineup_confirmed=confirmed, starting_gk=gk, injuries_confirmed=len(injuries),
            gk_changed=False)
        records.append(rec)
        all_players.extend(players)
        all_injuries.extend(injuries)

    return records, all_players, all_injuries
