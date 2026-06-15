"""Lógica de alineaciones: confirmación, filtro pre-kickoff y portero titular."""

from __future__ import annotations

from typing import List, Optional, Tuple

from .models import LineupPlayer, is_pre_kickoff


def confirmed_lineup(fixture: dict, source, now) -> Tuple[List[LineupPlayer], bool]:
    """Devuelve (jugadores_pre_kickoff, confirmado).

    Descarta cualquier jugador cuyo captured_at sea posterior al kickoff
    (no se usan datos post-kickoff para decisiones prepartido)."""
    kickoff = fixture.get("kickoff_utc", "")
    players, confirmed = source.lineup_for(fixture, now)
    valid = [p for p in players if is_pre_kickoff(p.captured_at, kickoff)]
    if len(valid) != len(players):
        confirmed = confirmed and bool(valid)  # si se cayó algo post-kickoff, no afirmar de más
    # confirmado solo si la fuente lo marcó Y quedan jugadores válidos
    return valid, bool(confirmed and valid)


def starting_goalkeeper(players: List[LineupPlayer], confirmed: bool) -> Optional[str]:
    """Portero titular SOLO desde alineación confirmada con marca de GK."""
    if not confirmed:
        return None
    for p in players:
        if p.is_starting and p.is_goalkeeper and p.player_name:
            return p.player_name
    return None
