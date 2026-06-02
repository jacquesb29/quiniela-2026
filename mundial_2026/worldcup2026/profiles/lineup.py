from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Sequence


@dataclass(frozen=True)
class LineupIntelligence:
    """Bounded lineup signal.

    Nominal rosters activate player-level comparison. If a provider supplies
    an XI before the local roster has real player names, the fallback remains
    deliberately small instead of inventing player quality.
    """

    overall_delta: float = 0.0
    attack_delta: float = 0.0
    defense_delta: float = 0.0
    goalkeeper_delta: float = 0.0
    coverage: float = 0.0
    matched_players: int = 0
    supplied_players: int = 0
    mode: str = "sin XI nominal"
    note: str = "Sin alineación confirmada; no se aplica ajuste individual."

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_player_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _sort_by(players: Sequence[object], key_name: str) -> list[object]:
    return sorted(players, key=lambda player: float(getattr(player, key_name, 0.0)), reverse=True)


def _projected_starters(players: Sequence[object]) -> list[object]:
    gks = [player for player in players if getattr(player, "position", "") == "GK"]
    dfs = [player for player in players if getattr(player, "position", "") == "DF"]
    mfs = [player for player in players if getattr(player, "position", "") == "MF"]
    fws = [player for player in players if getattr(player, "position", "") == "FW"]
    return (
        _sort_by(gks, "goalkeeping")[:1]
        + sorted(dfs, key=lambda player: float(getattr(player, "defense", 0.0)) + 0.25 * float(getattr(player, "aerial", 0.0)), reverse=True)[:4]
        + sorted(mfs, key=lambda player: float(getattr(player, "creation", 0.0)) + 0.15 * float(getattr(player, "defense", 0.0)), reverse=True)[:3]
        + sorted(fws, key=lambda player: float(getattr(player, "attack", 0.0)) + 0.10 * float(getattr(player, "creation", 0.0)), reverse=True)[:3]
    )


def _mean(players: Sequence[object], field: str) -> float:
    if not players:
        return 0.0
    return sum(float(getattr(player, field, 0.0)) for player in players) / len(players)


def _player_index(players: Sequence[object]) -> dict[str, object]:
    index: dict[str, object] = {}
    surname_candidates: dict[str, list[object]] = {}
    for player in players:
        key = normalize_player_name(getattr(player, "name", ""))
        if not key:
            continue
        index[key] = player
        surname_candidates.setdefault(key.split()[-1], []).append(player)
    for surname, candidates in surname_candidates.items():
        if len(candidates) == 1:
            index.setdefault(surname, candidates[0])
    return index


def _matched_players(players: Sequence[object], names: Sequence[str]) -> list[object]:
    index = _player_index(players)
    matched: list[object] = []
    seen = set()
    for name in names:
        key = normalize_player_name(name)
        player = index.get(key) or index.get(key.split()[-1] if key else "")
        if player is None or id(player) in seen:
            continue
        seen.add(id(player))
        matched.append(player)
    return matched


def lineup_intelligence(
    team: object,
    *,
    starting_xi: Sequence[str] = (),
    unavailable_players: Sequence[str] = (),
    lineup_confirmed: bool = False,
    lineup_changes: int = 0,
    goalkeeper_change: bool = False,
) -> LineupIntelligence:
    xi = tuple(str(name).strip() for name in starting_xi if str(name).strip())
    players = tuple(getattr(team, "players", ()) or ())
    if not xi:
        return LineupIntelligence()

    supplied = len(xi)
    change_penalty = 0.018 * _clamp(float(lineup_changes), 0.0, 6.0)
    goalkeeper_penalty = 0.035 if goalkeeper_change else 0.0
    if not players:
        return LineupIntelligence(
            overall_delta=-_clamp(change_penalty + goalkeeper_penalty, 0.0, 0.15),
            defense_delta=-goalkeeper_penalty,
            goalkeeper_delta=-goalkeeper_penalty,
            coverage=0.20 if lineup_confirmed else 0.08,
            matched_players=0,
            supplied_players=supplied,
            mode="XI recibido; roster nominal pendiente",
            note="El proveedor entregó el XI, pero faltan nombres locales para ponderar jugador por jugador. Se usa solo un ajuste conservador.",
        )

    actual = _matched_players(players, xi)
    projected = _projected_starters(players)
    coverage = _clamp(len(actual) / max(supplied, 1), 0.0, 1.0)
    if coverage < 0.45 or len(projected) < 7:
        return LineupIntelligence(
            overall_delta=-_clamp(change_penalty + goalkeeper_penalty, 0.0, 0.15),
            defense_delta=-goalkeeper_penalty,
            goalkeeper_delta=-goalkeeper_penalty,
            coverage=coverage,
            matched_players=len(actual),
            supplied_players=supplied,
            mode="XI parcial; señal acotada",
            note="La cobertura nominal del XI es insuficiente para elevar el peso individual. Se conserva un ajuste pequeño.",
        )

    projected_quality = _mean(projected, "quality")
    projected_attack = _mean(projected, "attack")
    projected_defense = _mean(projected, "defense")
    actual_quality = _mean(actual, "quality")
    actual_attack = _mean(actual, "attack")
    actual_defense = _mean(actual, "defense")
    actual_gks = [player for player in actual if getattr(player, "position", "") == "GK"]
    projected_gks = [player for player in projected if getattr(player, "position", "") == "GK"]
    goalkeeper_delta = _mean(actual_gks, "goalkeeping") - _mean(projected_gks, "goalkeeping")
    absent_expected = _matched_players(projected, unavailable_players)
    absence_penalty = 0.025 * len(absent_expected)
    scale = 0.75 * coverage
    return LineupIntelligence(
        overall_delta=_clamp(scale * (actual_quality - projected_quality) - change_penalty - absence_penalty, -0.24, 0.18),
        attack_delta=_clamp(scale * (actual_attack - projected_attack) - 0.55 * absence_penalty, -0.22, 0.18),
        defense_delta=_clamp(scale * (actual_defense - projected_defense) - 0.45 * absence_penalty - goalkeeper_penalty, -0.22, 0.18),
        goalkeeper_delta=_clamp(scale * goalkeeper_delta - goalkeeper_penalty, -0.22, 0.18),
        coverage=coverage,
        matched_players=len(actual),
        supplied_players=supplied,
        mode="XI ponderado jugador por jugador",
        note="El XI se comparó con la alineación estructural esperada usando los nombres disponibles del roster.",
    )
