"""Actividad reciente prepartido por equipo (F2.4), leakage-safe.

Calcula señales de actividad usando SOLO partidos anteriores a una fecha de
evaluación (`as_of_date`): edad del último partido, cobertura 6m/12m, oficiales
vs amistosos en 12m, y un salto de Elo reciente (proxy walk-forward simple).

No usa resultados posteriores a `as_of_date` (excluye el Mundial 2026, que es
posterior al snapshot). No ajusta parámetros con datos 2026. No toca el modelo.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

ACTIVITY_ELO_K = 24.0      # K simple para el proxy de salto (no es el Elo del modelo)
ACTIVITY_INITIAL_ELO = 1500.0
FRIENDLY_TOURNAMENTS = {"friendly", "unofficial friendly"}
WINDOW_6M_DAYS = 182
WINDOW_12M_DAYS = 365


@dataclass(frozen=True)
class RecentActivity:
    last_match_age_days: Optional[int]
    recent_coverage_6m: int
    recent_coverage_12m: int
    official_matches_12m: int
    friendly_matches_12m: int
    anomalous_elo_jump: Optional[float]
    activity_warning: str


def is_official(tournament: str) -> bool:
    return str(tournament or "").strip().lower() not in FRIENDLY_TOURNAMENTS


def _parse_date(value: str) -> Optional[date]:
    try:
        year, month, day = str(value).split("-")
        return date(int(year), int(month), int(day))
    except (ValueError, AttributeError):
        return None


def _parse_int(value) -> Optional[int]:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def load_match_history(path: str | Path) -> List[dict]:
    import csv as _csv
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(_csv.DictReader(handle))


def compute_activity_table(
    raw_rows: Sequence[Mapping],
    *,
    as_of_date: date,
    k: float = ACTIVITY_ELO_K,
    initial_elo: float = ACTIVITY_INITIAL_ELO,
) -> Dict[str, RecentActivity]:
    """Devuelve {team_name: RecentActivity} usando solo partidos < as_of_date."""

    ordered = sorted(
        (r for r in raw_rows if _parse_date(r.get("date")) is not None),
        key=lambda r: r["date"],
    )
    ratings: defaultdict[str, float] = defaultdict(lambda: float(initial_elo))
    matches: defaultdict[str, List[tuple]] = defaultdict(list)   # (date, official)
    jumps: defaultdict[str, List[float]] = defaultdict(list)     # |delta| en 12m

    for row in ordered:
        match_date = _parse_date(row.get("date"))
        if match_date is None or not (match_date < as_of_date):
            continue  # anti-leakage: solo pasado respecto a la evaluación
        home = str(row.get("home_team", "")).strip()
        away = str(row.get("away_team", "")).strip()
        gh = _parse_int(row.get("home_score"))
        ga = _parse_int(row.get("away_score"))
        if not home or not away or gh is None or ga is None:
            continue
        official = is_official(row.get("tournament"))
        matches[home].append((match_date, official))
        matches[away].append((match_date, official))

        # Proxy de salto de Elo (simple, solo señal de actividad).
        ra, rb = ratings[home], ratings[away]
        expected_home = 1.0 / (1.0 + 10.0 ** (-((ra - rb) / 400.0)))
        actual_home = 1.0 if gh > ga else (0.5 if gh == ga else 0.0)
        delta = k * (actual_home - expected_home)
        ratings[home] = ra + delta
        ratings[away] = rb - delta
        if (as_of_date - match_date).days <= WINDOW_12M_DAYS:
            jumps[home].append(abs(delta))
            jumps[away].append(abs(delta))

    table: Dict[str, RecentActivity] = {}
    for team, team_matches in matches.items():
        dates = [m[0] for m in team_matches]
        last = max(dates)
        age = (as_of_date - last).days
        in_12m = [m for m in team_matches if (as_of_date - m[0]).days <= WINDOW_12M_DAYS]
        in_6m = [m for m in team_matches if (as_of_date - m[0]).days <= WINDOW_6M_DAYS]
        official_12m = sum(1 for m in in_12m if m[1])
        friendly_12m = sum(1 for m in in_12m if not m[1])
        team_jumps = jumps.get(team, [])
        anomalous = max(team_jumps) if team_jumps else None

        warning = ""
        if len(in_12m) == 0:
            warning = "sin partidos en 12m"
        elif age is not None and age > WINDOW_12M_DAYS:
            warning = "último partido hace más de 12m"
        table[team] = RecentActivity(
            last_match_age_days=age,
            recent_coverage_6m=len(in_6m),
            recent_coverage_12m=len(in_12m),
            official_matches_12m=official_12m,
            friendly_matches_12m=friendly_12m,
            anomalous_elo_jump=round(anomalous, 3) if anomalous is not None else None,
            activity_warning=warning,
        )
    return table


def activity_level(activity: Optional[RecentActivity]) -> str:
    """Nivel de actividad (no de staleness) por cobertura oficial efectiva en 12m."""

    if activity is None or activity.recent_coverage_12m == 0:
        return "baja"
    effective = activity.official_matches_12m + 0.4 * activity.friendly_matches_12m
    if effective >= 10:
        return "alta"
    if effective >= 5:
        return "media"
    return "baja"


__all__ = [
    "ACTIVITY_ELO_K",
    "FRIENDLY_TOURNAMENTS",
    "RecentActivity",
    "is_official",
    "load_match_history",
    "compute_activity_table",
    "activity_level",
]
