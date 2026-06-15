"""Lógica de lesiones/bajas: solo de fuente trazable, filtradas pre-kickoff."""

from __future__ import annotations

from typing import List

from .models import InjuryRecord, is_pre_kickoff


def trusted_injuries(fixture: dict, source, now) -> List[InjuryRecord]:
    """Devuelve bajas con source+timestamp, capturadas en o antes del kickoff.

    Descarta cualquier registro sin source o capturado post-kickoff. No inventa."""
    kickoff = fixture.get("kickoff_utc", "")
    out: List[InjuryRecord] = []
    for rec in source.injuries_for(fixture, now):
        if not rec.source or not rec.captured_at:
            continue
        if not is_pre_kickoff(rec.captured_at, kickoff):
            continue
        if not rec.player_name:
            continue
        out.append(rec)
    return out
