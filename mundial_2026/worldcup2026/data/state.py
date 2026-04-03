from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Mapping, Optional

from ..modeling import clamp


@dataclass
class TeamState:
    morale: float = 0.0
    yellow_cards: int = 0
    yellow_load: float = 0.0
    red_suspensions: int = 0
    group_points: int = 0
    group_goal_diff: int = 0
    group_goals_for: int = 0
    group_goals_against: int = 0
    group_matches_played: int = 0
    fair_play: float = 0.0
    matches_played: int = 0
    goals_for: int = 0
    goals_against: int = 0
    elo_shift: float = 0.0
    recent_form: float = 0.0
    attack_form: float = 0.0
    defense_form: float = 0.0
    fatigue: float = 0.0
    availability: float = 1.0
    discipline_drift: float = 0.0
    style_possession: float = 0.0
    style_verticality: float = 0.0
    style_pressure: float = 0.0
    style_chance_quality: float = 0.0
    style_tempo: float = 0.0
    style_attack_bias: float = 0.0
    style_defense_bias: float = 0.0
    tactical_sample_matches: int = 0
    tactical_signature: str = "sin muestra suficiente"
    updated_at: Optional[str] = None

    @classmethod
    def from_mapping(cls, payload: Optional[Mapping[str, Any]]) -> "TeamState":
        if not payload:
            state = cls()
            state.clamp_all()
            return state
        raw = dict(payload)
        if "pending_red_suspensions" in raw and "red_suspensions" not in raw:
            raw["red_suspensions"] = raw["pending_red_suspensions"]
        allowed = {field.name for field in fields(cls)}
        normalized = {key: value for key, value in raw.items() if key in allowed}
        state = cls(**normalized)
        state.clamp_all()
        return state

    def clamp_all(self) -> None:
        self.morale = clamp(float(self.morale), -1.0, 1.0)
        self.elo_shift = clamp(float(self.elo_shift), -220.0, 220.0)
        self.recent_form = clamp(float(self.recent_form), -1.0, 1.0)
        self.attack_form = clamp(float(self.attack_form), -1.0, 1.0)
        self.defense_form = clamp(float(self.defense_form), -1.0, 1.0)
        self.fatigue = clamp(float(self.fatigue), 0.0, 1.0)
        self.availability = clamp(float(self.availability), 0.40, 1.0)
        self.discipline_drift = clamp(float(self.discipline_drift), -1.0, 0.5)
        self.yellow_load = clamp(float(self.yellow_load), 0.0, 6.0)
        self.style_possession = clamp(float(self.style_possession), -1.0, 1.0)
        self.style_verticality = clamp(float(self.style_verticality), -1.0, 1.0)
        self.style_pressure = clamp(float(self.style_pressure), -1.0, 1.0)
        self.style_chance_quality = clamp(float(self.style_chance_quality), -1.0, 1.0)
        self.style_tempo = clamp(float(self.style_tempo), -1.0, 1.0)
        self.style_attack_bias = clamp(float(self.style_attack_bias), -1.0, 1.0)
        self.style_defense_bias = clamp(float(self.style_defense_bias), -1.0, 1.0)
        self.yellow_cards = max(0, int(self.yellow_cards))
        self.red_suspensions = max(0, int(self.red_suspensions))
        self.group_points = int(self.group_points)
        self.group_goal_diff = int(self.group_goal_diff)
        self.group_goals_for = max(0, int(self.group_goals_for))
        self.group_goals_against = max(0, int(self.group_goals_against))
        self.group_matches_played = max(0, int(self.group_matches_played))
        self.matches_played = max(0, int(self.matches_played))
        self.goals_for = max(0, int(self.goals_for))
        self.goals_against = max(0, int(self.goals_against))
        self.tactical_sample_matches = max(0, int(self.tactical_sample_matches))
        self.tactical_signature = str(self.tactical_signature or "sin muestra suficiente")
        self.updated_at = None if self.updated_at is None else str(self.updated_at)

    def simulation_signature(self) -> tuple[float, ...]:
        return (
            round(self.elo_shift, 1),
            round(self.recent_form, 1),
            round(self.attack_form, 1),
            round(self.defense_form, 1),
            round(self.fatigue, 1),
            round(self.availability, 1),
            round(self.discipline_drift, 1),
            round(self.style_attack_bias, 1),
            round(self.style_defense_bias, 1),
            round(self.style_tempo, 1),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_team_state() -> Dict[str, Any]:
    return TeamState().to_dict()


def coerce_team_state(state: Optional[Mapping[str, Any]]) -> TeamState:
    return TeamState.from_mapping(state)


def normalize_team_state(state: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    return TeamState.from_mapping(state).to_dict()


def initial_team_states(teams: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {name: default_team_state() for name in teams}


def copy_states(payload: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    source = payload.get("teams", payload) if isinstance(payload, Mapping) else {}
    return {
        team_name: normalize_team_state(state)
        for team_name, state in dict(source).items()
    }


def state_has_activity(state: Optional[Mapping[str, Any]]) -> bool:
    normalized = TeamState.from_mapping(state)
    return any(
        [
            normalized.matches_played > 0,
            normalized.group_matches_played > 0,
            abs(normalized.morale) > 1e-9,
            abs(normalized.elo_shift) > 1e-9,
            abs(normalized.recent_form) > 1e-9,
            abs(normalized.attack_form) > 1e-9,
            abs(normalized.defense_form) > 1e-9,
            abs(normalized.discipline_drift) > 1e-9,
            abs(normalized.fatigue) > 1e-9,
            abs(normalized.availability - 1.0) > 1e-9,
            normalized.tactical_sample_matches > 0,
        ]
    )
