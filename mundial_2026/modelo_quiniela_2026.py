#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import math
import random
import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


DATA_FILE = Path(__file__).with_name("teams_2026.json")
TOURNAMENT_CONFIG_FILE = Path(__file__).with_name("tournament_2026_draw.json")
STATE_FILE = Path(__file__).with_name("tournament_state_2026.json")
FACTORIALS = [math.factorial(i) for i in range(16)]
HOST_COUNTRIES = {"Canada", "Mexico", "United States"}
GROUP_MATCH_PAIRS = [
    (0, 3),
    (1, 2),
    (0, 2),
    (3, 1),
    (0, 1),
    (2, 3),
]
STAGE_IMPORTANCE = {
    "group": 1.00,
    "round32": 1.12,
    "round16": 1.22,
    "quarterfinal": 1.30,
    "semifinal": 1.38,
    "third_place": 1.24,
    "final": 1.48,
}
STAGE_ALIASES = {
    "group": "group",
    "groups": "group",
    "fase_de_grupos": "group",
    "fasegrupos": "group",
    "round32": "round32",
    "round_of_32": "round32",
    "roundof32": "round32",
    "dieciseisavos": "round32",
    "round16": "round16",
    "round_of_16": "round16",
    "roundof16": "round16",
    "octavos": "round16",
    "round8": "quarterfinal",
    "round_of_8": "quarterfinal",
    "roundof8": "quarterfinal",
    "quarterfinal": "quarterfinal",
    "quarterfinals": "quarterfinal",
    "cuartos": "quarterfinal",
    "round4": "semifinal",
    "round_of_4": "semifinal",
    "roundof4": "semifinal",
    "semifinal": "semifinal",
    "semifinals": "semifinal",
    "semis": "semifinal",
    "third_place": "third_place",
    "thirdplace": "third_place",
    "third-place": "third_place",
    "third_and_fourth_place": "third_place",
    "thirdandfourthplace": "third_place",
    "final": "final",
}
R32_MATCHES = [
    {"id": "M73", "team_a": {"type": "group_rank", "group": "A", "rank": 2}, "team_b": {"type": "group_rank", "group": "B", "rank": 2}},
    {"id": "M74", "team_a": {"type": "group_rank", "group": "E", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["A", "B", "C", "D", "F"]}},
    {"id": "M75", "team_a": {"type": "group_rank", "group": "F", "rank": 1}, "team_b": {"type": "group_rank", "group": "C", "rank": 2}},
    {"id": "M76", "team_a": {"type": "group_rank", "group": "C", "rank": 1}, "team_b": {"type": "group_rank", "group": "F", "rank": 2}},
    {"id": "M77", "team_a": {"type": "group_rank", "group": "I", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["C", "D", "F", "G", "H"]}},
    {"id": "M78", "team_a": {"type": "group_rank", "group": "E", "rank": 2}, "team_b": {"type": "group_rank", "group": "I", "rank": 2}},
    {"id": "M79", "team_a": {"type": "group_rank", "group": "A", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["C", "E", "F", "H", "I"]}},
    {"id": "M80", "team_a": {"type": "group_rank", "group": "L", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["E", "H", "I", "J", "K"]}},
    {"id": "M81", "team_a": {"type": "group_rank", "group": "D", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["B", "E", "F", "I", "J"]}},
    {"id": "M82", "team_a": {"type": "group_rank", "group": "G", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["A", "E", "H", "I", "J"]}},
    {"id": "M83", "team_a": {"type": "group_rank", "group": "K", "rank": 2}, "team_b": {"type": "group_rank", "group": "L", "rank": 2}},
    {"id": "M84", "team_a": {"type": "group_rank", "group": "H", "rank": 1}, "team_b": {"type": "group_rank", "group": "J", "rank": 2}},
    {"id": "M85", "team_a": {"type": "group_rank", "group": "B", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["E", "F", "G", "I", "J"]}},
    {"id": "M86", "team_a": {"type": "group_rank", "group": "J", "rank": 1}, "team_b": {"type": "group_rank", "group": "H", "rank": 2}},
    {"id": "M87", "team_a": {"type": "group_rank", "group": "K", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["D", "E", "I", "J", "L"]}},
    {"id": "M88", "team_a": {"type": "group_rank", "group": "D", "rank": 2}, "team_b": {"type": "group_rank", "group": "G", "rank": 2}},
]
KNOCKOUT_MATCHES = {
    "round16": [
        ("M89", "M73", "M74"),
        ("M90", "M75", "M76"),
        ("M91", "M77", "M78"),
        ("M92", "M79", "M80"),
        ("M93", "M81", "M82"),
        ("M94", "M83", "M84"),
        ("M95", "M85", "M86"),
        ("M96", "M87", "M88"),
    ],
    "quarterfinal": [
        ("M97", "M89", "M90"),
        ("M98", "M91", "M92"),
        ("M99", "M93", "M94"),
        ("M100", "M95", "M96"),
    ],
    "semifinal": [
        ("M101", "M97", "M98"),
        ("M102", "M99", "M100"),
    ],
    "final": [
        ("M103", "M101", "M102"),
    ],
}
WINNER_NEXT_MATCH = {
    source: match_id
    for round_matches in KNOCKOUT_MATCHES.values()
    for match_id, left_source, right_source in round_matches
    for source in (left_source, right_source)
}
LOSER_NEXT_MATCH = {
    "M101": "M104",
    "M102": "M104",
}
BRACKET_FILE = Path(__file__).with_name("llave_actual_2026.md")
BRACKET_JSON_FILE = Path(__file__).with_name("llave_actual_2026.json")
DASHBOARD_HTML_FILE = Path(__file__).with_name("dashboard_actual_2026.html")
DASHBOARD_MD_FILE = Path(__file__).with_name("reporte_actual_2026.md")
BRACKET_MATCH_TITLES = {
    "M73": "Dieciseisavos 1",
    "M74": "Dieciseisavos 2",
    "M75": "Dieciseisavos 3",
    "M76": "Dieciseisavos 4",
    "M77": "Dieciseisavos 5",
    "M78": "Dieciseisavos 6",
    "M79": "Dieciseisavos 7",
    "M80": "Dieciseisavos 8",
    "M81": "Dieciseisavos 9",
    "M82": "Dieciseisavos 10",
    "M83": "Dieciseisavos 11",
    "M84": "Dieciseisavos 12",
    "M85": "Dieciseisavos 13",
    "M86": "Dieciseisavos 14",
    "M87": "Dieciseisavos 15",
    "M88": "Dieciseisavos 16",
    "M89": "Octavos 1",
    "M90": "Octavos 2",
    "M91": "Octavos 3",
    "M92": "Octavos 4",
    "M93": "Octavos 5",
    "M94": "Octavos 6",
    "M95": "Octavos 7",
    "M96": "Octavos 8",
    "M97": "Cuartos 1",
    "M98": "Cuartos 2",
    "M99": "Cuartos 3",
    "M100": "Cuartos 4",
    "M101": "Semifinal 1",
    "M102": "Semifinal 2",
    "M103": "Final",
    "M104": "Tercer puesto",
}
RIVALRIES = {
    frozenset({"Argentina", "Brazil"}): 0.16,
    frozenset({"England", "Scotland"}): 0.14,
    frozenset({"Mexico", "United States"}): 0.15,
    frozenset({"Croatia", "Serbia"}): 0.12,
    frozenset({"Japan", "South Korea"}): 0.10,
    frozenset({"Turkey", "Greece"}): 0.10,
}
TEAM_NAME_ALIASES = {
    "espana": "Spain",
    "uruguay": "Uruguay",
    "estadosunidos": "United States",
    "eeuu": "United States",
    "usa": "United States",
    "holanda": "Netherlands",
    "paisesbajos": "Netherlands",
    "brasil": "Brazil",
    "alemania": "Germany",
    "inglaterra": "England",
    "escocia": "Scotland",
    "suiza": "Switzerland",
    "coreadelsur": "South Korea",
    "corearepublica": "South Korea",
    "surcorea": "South Korea",
    "corea": "South Korea",
    "japon": "Japan",
    "arabiasaudita": "Saudi Arabia",
    "nuevazelanda": "New Zealand",
    "costademarfil": "Ivory Coast",
    "caboverde": "Cape Verde",
    "marruecos": "Morocco",
    "argelia": "Algeria",
    "egipto": "Egypt",
    "turquia": "Turkey",
    "republicacheca": "Czech Republic",
    "irlanda": "Republic of Ireland",
    "irlandadelnorte": "Northern Ireland",
    "congord": "Dem. Rep. of Congo",
    "rdcongo": "Dem. Rep. of Congo",
    "iriran": "Iran",
    "irak": "Iraq",
}
RESOURCE_BY_CONFEDERATION = {
    "UEFA": 0.70,
    "CONMEBOL": 0.60,
    "AFC": 0.57,
    "CONCACAF": 0.55,
    "CAF": 0.40,
    "OFC": 0.24,
}
HISTORICAL_BY_CONFEDERATION = {
    "UEFA": 0.25,
    "CONMEBOL": 0.26,
    "AFC": 0.08,
    "CONCACAF": 0.09,
    "CAF": 0.10,
    "OFC": 0.05,
}
DISCIPLINE_BY_CONFEDERATION = {
    "UEFA": 0.08,
    "CONMEBOL": -0.05,
    "AFC": 0.06,
    "CONCACAF": -0.02,
    "CAF": -0.04,
    "OFC": 0.04,
}
TEMPO_BY_CONFEDERATION = {
    "UEFA": 0.54,
    "CONMEBOL": 0.56,
    "AFC": 0.50,
    "CONCACAF": 0.53,
    "CAF": 0.52,
    "OFC": 0.48,
}
TRAVEL_BY_CONFEDERATION = {
    "UEFA": 0.62,
    "CONMEBOL": 0.66,
    "AFC": 0.60,
    "CONCACAF": 0.70,
    "CAF": 0.58,
    "OFC": 0.52,
}
RESOURCE_OVERRIDES = {
    "United States": 1.00,
    "Germany": 0.95,
    "England": 0.93,
    "France": 0.93,
    "Canada": 0.88,
    "Spain": 0.87,
    "Mexico": 0.84,
    "Brazil": 0.84,
    "Japan": 0.84,
    "Italy": 0.82,
    "South Korea": 0.82,
    "Australia": 0.81,
    "Netherlands": 0.81,
    "Saudi Arabia": 0.80,
    "Turkey": 0.79,
    "Belgium": 0.78,
    "Switzerland": 0.78,
    "Poland": 0.77,
    "Argentina": 0.76,
    "Denmark": 0.76,
    "Norway": 0.75,
    "Austria": 0.74,
    "Sweden": 0.74,
    "Portugal": 0.73,
    "Republic of Ireland": 0.73,
    "Czech Republic": 0.71,
    "Romania": 0.68,
    "Ukraine": 0.67,
    "Qatar": 0.67,
    "Morocco": 0.63,
    "Colombia": 0.62,
    "Iraq": 0.62,
    "Egypt": 0.60,
    "New Zealand": 0.60,
    "Algeria": 0.59,
    "Iran": 0.59,
    "South Africa": 0.59,
    "Slovakia": 0.58,
    "Tunisia": 0.56,
    "Uzbekistan": 0.54,
    "Paraguay": 0.54,
    "Jordan": 0.52,
    "Bosnia and Herzegovina": 0.52,
    "North Macedonia": 0.50,
    "Albania": 0.49,
    "Kosovo": 0.48,
    "Ghana": 0.47,
    "Bolivia": 0.46,
    "Wales": 0.46,
    "Jamaica": 0.44,
    "Senegal": 0.44,
    "Ivory Coast": 0.43,
    "Panama": 0.41,
    "Dem. Rep. of Congo": 0.40,
    "Haiti": 0.37,
    "Curacao": 0.34,
    "Cape Verde": 0.29,
    "Suriname": 0.28,
    "New Caledonia": 0.19,
}
WORLD_CUP_TITLES = {
    "Brazil": 5,
    "Germany": 4,
    "Italy": 4,
    "Argentina": 3,
    "France": 2,
    "Uruguay": 2,
    "England": 1,
    "Spain": 1,
}
TRADITION_BONUS = {
    "Argentina": 0.27,
    "Brazil": 0.30,
    "Germany": 0.29,
    "Italy": 0.29,
    "France": 0.24,
    "England": 0.20,
    "Spain": 0.20,
    "Uruguay": 0.22,
    "Netherlands": 0.20,
    "Portugal": 0.18,
    "Belgium": 0.16,
    "Croatia": 0.18,
    "Mexico": 0.15,
    "United States": 0.12,
    "Morocco": 0.10,
    "Japan": 0.12,
    "South Korea": 0.11,
    "Switzerland": 0.10,
    "Denmark": 0.10,
    "Poland": 0.10,
    "Sweden": 0.10,
    "Turkey": 0.09,
    "Czech Republic": 0.10,
    "Austria": 0.09,
    "Scotland": 0.09,
    "Wales": 0.08,
    "Norway": 0.08,
    "Senegal": 0.08,
    "Ivory Coast": 0.07,
    "Egypt": 0.07,
    "Algeria": 0.07,
    "Colombia": 0.08,
    "Paraguay": 0.08,
    "Ecuador": 0.07,
    "Australia": 0.07,
    "Iran": 0.07,
    "Saudi Arabia": 0.06,
}
COACH_OVERRIDES = {
    "Spain": 0.06,
    "Argentina": 0.06,
    "France": 0.05,
    "England": 0.05,
    "Portugal": 0.05,
    "Germany": 0.04,
    "Croatia": 0.04,
    "Japan": 0.03,
    "Morocco": 0.03,
    "Brazil": 0.03,
    "Italy": 0.03,
    "Turkey": 0.02,
    "Denmark": 0.02,
    "Mexico": 0.01,
}
DISCIPLINE_OVERRIDES = {
    "Japan": 0.08,
    "South Korea": 0.03,
    "England": 0.03,
    "Switzerland": 0.03,
    "Spain": 0.03,
    "Uruguay": -0.08,
    "Argentina": -0.05,
    "Turkey": -0.05,
    "Morocco": -0.03,
    "Mexico": -0.03,
    "Jamaica": -0.03,
    "Bolivia": -0.02,
    "Paraguay": -0.04,
}


@dataclass(frozen=True)
class Player:
    name: str
    position: str
    quality: float
    caps: float
    minutes_share: float
    attack: float
    creation: float
    defense: float
    goalkeeping: float
    aerial: float
    discipline: float
    yellow_rate: float
    red_rate: float
    availability: float


@dataclass(frozen=True)
class Team:
    name: str
    confederation: str
    status: str
    elo: float
    fifa_points: Optional[float] = None
    fifa_rank: Optional[int] = None
    host_country: Optional[str] = None
    resource_bias: float = 0.0
    heritage_bias: float = 0.0
    coach_bias: float = 0.0
    discipline_bias: float = 0.0
    chemistry_bias: float = 0.0
    attack_bias: float = 0.0
    defense_bias: float = 0.0
    players: Tuple[Player, ...] = ()

    @property
    def is_host(self) -> bool:
        return self.host_country is not None


@dataclass(frozen=True)
class SquadAggregate:
    squad_quality: float
    attack_unit: float
    midfield_unit: float
    defense_unit: float
    goalkeeper_unit: float
    bench_depth: float
    player_experience: float
    set_piece_attack: float
    set_piece_defense: float
    discipline_index: float
    yellow_rate: float
    red_rate: float
    availability: float
    finishing: float
    shot_creation: float
    pressing: float


@dataclass(frozen=True)
class TeamProfile:
    fifa_points: float
    fifa_rank: int
    fifa_strength_index: float
    resource_index: float
    heritage_index: float
    world_cup_titles: int
    trajectory_index: float
    coach_index: float
    chemistry_index: float
    morale_base: float
    tactical_flexibility: float
    travel_resilience: float
    tempo: float
    squad: SquadAggregate


@dataclass(frozen=True)
class MatchContext:
    neutral: bool = True
    home_team: Optional[str] = None
    venue_country: Optional[str] = None
    rest_days_a: int = 4
    rest_days_b: int = 4
    injuries_a: float = 0.0
    injuries_b: float = 0.0
    altitude_m: int = 0
    travel_km_a: float = 0.0
    travel_km_b: float = 0.0
    knockout: bool = False
    morale_a: float = 0.0
    morale_b: float = 0.0
    yellow_cards_a: int = 0
    yellow_cards_b: int = 0
    red_suspensions_a: int = 0
    red_suspensions_b: int = 0
    group: Optional[str] = None
    group_points_a: int = 0
    group_points_b: int = 0
    group_goal_diff_a: int = 0
    group_goal_diff_b: int = 0
    group_matches_played_a: int = 0
    group_matches_played_b: int = 0
    weather_stress: float = 0.0
    market_prob_a: Optional[float] = None
    market_prob_draw: Optional[float] = None
    market_prob_b: Optional[float] = None
    market_total_line: Optional[float] = None
    lineup_confirmed_a: bool = False
    lineup_confirmed_b: bool = False
    lineup_change_count_a: int = 0
    lineup_change_count_b: int = 0
    importance: float = 1.0


@dataclass(frozen=True)
class MatchPrediction:
    team_a: str
    team_b: str
    expected_goals_a: float
    expected_goals_b: float
    win_a: float
    draw: float
    win_b: float
    exact_scores: List[Tuple[str, float]]
    advance_a: Optional[float] = None
    advance_b: Optional[float] = None
    knockout_detail: Optional[Dict[str, float]] = None
    penalty_shootout: Optional[dict] = None
    factors: Optional[Dict[str, float]] = None
    expected_remaining_goals_a: Optional[float] = None
    expected_remaining_goals_b: Optional[float] = None
    current_score_a: Optional[int] = None
    current_score_b: Optional[int] = None
    elapsed_minutes: Optional[float] = None
    live_phase: Optional[str] = None
    statistical_depth: Optional[Dict[str, object]] = None
    live_patterns: Optional[Dict[str, object]] = None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def logistic(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def stable_seed(value: str) -> int:
    total = 0
    for index, char in enumerate(value):
        total += (index + 1) * ord(char)
    return total


def parse_elapsed_minutes(status_detail: Optional[str], knockout: bool) -> Tuple[Optional[float], str]:
    if not status_detail:
        return None, "regulation"
    text = str(status_detail).strip().lower()
    if not text:
        return None, "regulation"
    if "pen" in text or "shootout" in text:
        return 120.0 if knockout else 90.0, "penalties"
    if text in {"ht", "half time", "halftime"}:
        return 45.0, "regulation"
    if "extra" in text and "half" in text:
        return 105.0, "extra_time"

    match = re.search(r"(\d+)(?:\+(\d+))?", text)
    if match:
        elapsed = float(match.group(1))
        if match.group(2):
            elapsed += float(match.group(2))
        if knockout and elapsed > 90.0:
            return clamp(elapsed, 90.0, 120.0), "extra_time"
        return clamp(elapsed, 0.0, 90.0), "regulation"

    if knockout and ("extra time" in text or text.startswith("et")):
        return 105.0, "extra_time"
    return None, "regulation"


def live_game_state_adjustment(
    base_mu_a: float,
    base_mu_b: float,
    score_a: int,
    score_b: int,
    progress: float,
    phase: str,
) -> Tuple[float, float]:
    diff = score_a - score_b
    urgency = clamp(progress, 0.0, 1.0)
    lead_suppression = 0.08 if phase == "extra_time" else 0.12
    chase_boost = 0.12 if phase == "extra_time" else 0.18
    total_late_boost = 0.04 if phase == "extra_time" else 0.08

    mu_a = base_mu_a
    mu_b = base_mu_b
    if diff > 0:
        lead = clamp(diff, 0, 3)
        mu_a *= 1.0 - lead_suppression * urgency * lead
        mu_b *= 1.0 + chase_boost * urgency * lead
    elif diff < 0:
        lead = clamp(-diff, 0, 3)
        mu_b *= 1.0 - lead_suppression * urgency * lead
        mu_a *= 1.0 + chase_boost * urgency * lead

    if diff != 0:
        total_push = 1.0 + total_late_boost * urgency * min(abs(diff), 2)
        mu_a *= total_push
        mu_b *= total_push

    return clamp(mu_a, 0.01, 4.2), clamp(mu_b, 0.01, 4.2)


def live_stats_adjustment(
    base_total_mu: float,
    mu_a: float,
    mu_b: float,
    progress: float,
    phase: str,
    live_stats: Optional[Dict[str, float]] = None,
) -> Tuple[float, float]:
    if not live_stats:
        return mu_a, mu_b

    xg_a = float(live_stats.get("xg_a") or live_stats.get("xg_proxy_a") or 0.0)
    xg_b = float(live_stats.get("xg_b") or live_stats.get("xg_proxy_b") or 0.0)
    shots_a = float(live_stats.get("shots_a", 0.0))
    shots_b = float(live_stats.get("shots_b", 0.0))
    sot_a = float(live_stats.get("shots_on_target_a", 0.0))
    sot_b = float(live_stats.get("shots_on_target_b", 0.0))
    poss_a = float(live_stats.get("possession_a", 50.0))
    poss_b = float(live_stats.get("possession_b", 50.0))
    corners_a = float(live_stats.get("corners_a", 0.0))
    corners_b = float(live_stats.get("corners_b", 0.0))
    red_a = float(live_stats.get("red_cards_a", 0.0))
    red_b = float(live_stats.get("red_cards_b", 0.0))

    if (
        xg_a <= 0.0
        and xg_b <= 0.0
        and shots_a <= 0.0
        and shots_b <= 0.0
        and sot_a <= 0.0
        and sot_b <= 0.0
        and corners_a <= 0.0
        and corners_b <= 0.0
        and red_a <= 0.0
        and red_b <= 0.0
    ):
        return mu_a, mu_b

    scale = 0.18 if phase == "extra_time" else 0.28
    xg_diff = clamp(xg_a - xg_b, -2.0, 2.0)
    sot_diff = clamp(sot_a - sot_b, -8.0, 8.0)
    shots_diff = clamp(shots_a - shots_b, -15.0, 15.0)
    poss_diff = clamp(poss_a - poss_b, -40.0, 40.0)
    corners_diff = clamp(corners_a - corners_b, -10.0, 10.0)
    red_advantage_for_a = clamp(red_b - red_a, -2.0, 2.0)

    edge_signal = (
        0.42 * xg_diff
        + 0.06 * sot_diff
        + 0.015 * shots_diff
        + 0.004 * poss_diff
        + 0.012 * corners_diff
        + 0.48 * red_advantage_for_a
    )
    edge_signal *= 0.45 + 0.55 * clamp(progress, 0.0, 1.0)

    adjustment_a = clamp(1.0 + scale * edge_signal, 0.62, 1.55)
    adjustment_b = clamp(1.0 - scale * edge_signal, 0.62, 1.55)

    live_total_xg = xg_a + xg_b
    if live_total_xg <= 0.0:
        live_total_xg = float(live_stats.get("xg_proxy_a", 0.0)) + float(live_stats.get("xg_proxy_b", 0.0))
    expected_so_far = base_total_mu * clamp(progress, 0.15, 1.0)
    intensity_signal = clamp(live_total_xg - expected_so_far, -1.2, 1.2)
    tempo_adjustment = clamp(1.0 + (0.10 if phase == "extra_time" else 0.18) * intensity_signal, 0.72, 1.35)

    mu_a *= adjustment_a * tempo_adjustment
    mu_b *= adjustment_b * tempo_adjustment
    return clamp(mu_a, 0.01, 4.2), clamp(mu_b, 0.01, 4.2)


def stat_share(value: float, other: float, neutral: float = 0.5) -> float:
    total = value + other
    if total <= 0.0:
        return neutral
    return value / total


def format_pattern_signal(label: str, value: float, integer: bool = False, suffix: str = "") -> str:
    if integer:
        return f"{label} {int(round(value))}{suffix}"
    return f"{label} {value:.2f}{suffix}"


def derive_team_live_pattern(
    side: str,
    live_stats: Dict[str, float],
    progress: float,
    score_for: int,
    score_against: int,
) -> Dict[str, object]:
    other = "b" if side == "a" else "a"
    shots = float(live_stats.get(f"shots_{side}", 0.0))
    shots_opp = float(live_stats.get(f"shots_{other}", 0.0))
    sot = float(live_stats.get(f"shots_on_target_{side}", 0.0))
    sot_opp = float(live_stats.get(f"shots_on_target_{other}", 0.0))
    poss = float(live_stats.get(f"possession_{side}", 50.0))
    corners = float(live_stats.get(f"corners_{side}", 0.0))
    corners_opp = float(live_stats.get(f"corners_{other}", 0.0))
    fouls = float(live_stats.get(f"fouls_{side}", 0.0))
    yellows = float(live_stats.get(f"yellow_cards_{side}", 0.0))
    reds = float(live_stats.get(f"red_cards_{side}", 0.0))
    reds_opp = float(live_stats.get(f"red_cards_{other}", 0.0))
    xg = float(live_stats.get(f"xg_{side}", live_stats.get(f"xg_proxy_{side}", 0.0)))
    xg_opp = float(live_stats.get(f"xg_{other}", live_stats.get(f"xg_proxy_{other}", 0.0)))

    shot_share = stat_share(shots, shots_opp)
    sot_share = stat_share(sot, sot_opp)
    xg_share = stat_share(xg, xg_opp)
    corner_share = stat_share(corners, corners_opp)
    xg_per_shot = xg / max(shots, 1.0)
    on_target_rate = sot / max(shots, 1.0)
    score_diff = score_for - score_against

    primary = "sin patron dominante claro"
    secondary = "ritmo equilibrado"
    attack_bias = 0.0
    defense_bias = 0.0
    tempo_bias = 0.0

    if reds > reds_opp:
        primary = "inferioridad numerica"
        secondary = "resistencia y repliegue"
        attack_bias = -0.18
        defense_bias = -0.06
        tempo_bias = -0.03
    elif score_diff > 0 and poss <= 45.0 and shot_share <= 0.46:
        primary = "bloque bajo y contra"
        secondary = "protege la ventaja"
        attack_bias = -0.03
        defense_bias = 0.10
        tempo_bias = -0.08
    elif score_diff < 0 and shot_share >= 0.57 and corner_share >= 0.56:
        primary = "asedio del empate"
        secondary = "empuja la ultima linea"
        attack_bias = 0.12
        defense_bias = -0.01
        tempo_bias = 0.10
    elif poss >= 58.0 and shot_share >= 0.57 and (xg_share >= 0.56 or sot_share >= 0.56):
        if progress >= 0.30 and corner_share >= 0.55:
            primary = "dominio territorial"
            secondary = "asedio sostenido"
            attack_bias = 0.13
            defense_bias = 0.05
            tempo_bias = 0.07
        else:
            primary = "control con llegada"
            secondary = "empuja al rival"
            attack_bias = 0.09
            defense_bias = 0.03
            tempo_bias = 0.03
    elif poss >= 58.0 and xg_share <= 0.48 and sot <= max(1.0, sot_opp):
        primary = "control esteril"
        secondary = "maneja la pelota pero llega poco"
        attack_bias = -0.06
        defense_bias = 0.02
        tempo_bias = -0.05
    elif poss <= 46.0 and (xg_per_shot >= 0.12 or xg_share >= 0.50) and sot_share >= 0.45:
        primary = "transicion vertical"
        secondary = "amenaza al espacio"
        attack_bias = 0.09
        defense_bias = 0.00
        tempo_bias = 0.03
    elif xg <= 0.15 and shots <= 3.0 and progress >= 0.30:
        primary = "poca amenaza"
        secondary = "le cuesta progresar"
        attack_bias = -0.12
        defense_bias = -0.01
        tempo_bias = -0.04
    elif fouls + yellows >= 8.0 and shots <= 5.0:
        primary = "presion fisica"
        secondary = "corta el ritmo"
        attack_bias = -0.04
        defense_bias = 0.03
        tempo_bias = -0.06

    signals = []
    if abs(poss - 50.0) >= 6.0:
        signals.append(format_pattern_signal("posesion", poss, suffix="%"))
    if shots > 0.0:
        signals.append(format_pattern_signal("tiros", shots, integer=True))
    if sot > 0.0:
        signals.append(format_pattern_signal("al arco", sot, integer=True))
    if xg > 0.0:
        signals.append(format_pattern_signal("xG live", xg))
    if corners >= 3.0:
        signals.append(format_pattern_signal("corners", corners, integer=True))
    if reds > 0.0:
        signals.append(format_pattern_signal("rojas", reds, integer=True))
    if not signals:
        signals.append("sin señales en vivo suficientes")

    return {
        "primary": primary,
        "secondary": secondary,
        "summary": f"{primary} | {secondary}",
        "attack_bias": attack_bias,
        "defense_bias": defense_bias,
        "tempo_bias": tempo_bias,
        "signals": signals[:4],
    }


def detect_live_play_patterns(
    live_stats: Optional[Dict[str, float]],
    progress: float,
    phase: str,
    score_a: int,
    score_b: int,
) -> Optional[Dict[str, object]]:
    if not live_stats:
        return None
    total_signal = sum(
        float(live_stats.get(key, 0.0))
        for key in (
            "shots_a",
            "shots_b",
            "shots_on_target_a",
            "shots_on_target_b",
            "corners_a",
            "corners_b",
            "red_cards_a",
            "red_cards_b",
            "yellow_cards_a",
            "yellow_cards_b",
        )
    )
    total_xg = float(live_stats.get("xg_a", live_stats.get("xg_proxy_a", 0.0))) + float(
        live_stats.get("xg_b", live_stats.get("xg_proxy_b", 0.0))
    )
    if total_signal <= 0.0 and total_xg <= 0.0:
        return None

    side_a = derive_team_live_pattern("a", live_stats, progress, score_a, score_b)
    side_b = derive_team_live_pattern("b", live_stats, progress, score_b, score_a)

    shots_total = float(live_stats.get("shots_a", 0.0)) + float(live_stats.get("shots_b", 0.0))
    sot_total = float(live_stats.get("shots_on_target_a", 0.0)) + float(live_stats.get("shots_on_target_b", 0.0))
    fouls_total = float(live_stats.get("fouls_a", 0.0)) + float(live_stats.get("fouls_b", 0.0))
    yellows_total = float(live_stats.get("yellow_cards_a", 0.0)) + float(live_stats.get("yellow_cards_b", 0.0))
    red_total = float(live_stats.get("red_cards_a", 0.0)) + float(live_stats.get("red_cards_b", 0.0))
    poss_gap = abs(float(live_stats.get("possession_a", 50.0)) - float(live_stats.get("possession_b", 50.0)))

    if red_total > 0.0 and shots_total >= 10.0:
        tempo_label = "partido roto"
        global_tempo_bias = 0.08
    elif total_xg >= 1.6 or shots_total >= 18.0 or sot_total >= 7.0:
        tempo_label = "ida y vuelta"
        global_tempo_bias = 0.07
    elif (fouls_total >= 22.0 or yellows_total >= 5.0) and total_xg <= 1.0:
        tempo_label = "trabado y cortado"
        global_tempo_bias = -0.08
    elif poss_gap >= 14.0 and shots_total >= 8.0:
        tempo_label = "control territorial"
        global_tempo_bias = -0.01
    elif phase == "extra_time":
        tempo_label = "prorroga de desgaste"
        global_tempo_bias = -0.03
    else:
        tempo_label = "ritmo equilibrado"
        global_tempo_bias = 0.0

    return {
        "a": side_a,
        "b": side_b,
        "tempo_label": tempo_label,
        "global_tempo_bias": global_tempo_bias,
    }


def apply_live_pattern_adjustment(
    mu_a: float,
    mu_b: float,
    patterns: Optional[Dict[str, object]],
    phase: str,
) -> Tuple[float, float]:
    if not patterns:
        return mu_a, mu_b

    scale = 0.11 if phase == "extra_time" else 0.16
    side_a = patterns.get("a", {})
    side_b = patterns.get("b", {})
    tempo_bias = float(patterns.get("global_tempo_bias", 0.0))
    tempo_bias += 0.5 * (float(side_a.get("tempo_bias", 0.0)) + float(side_b.get("tempo_bias", 0.0)))

    attack_factor_a = clamp(1.0 + scale * float(side_a.get("attack_bias", 0.0)), 0.86, 1.18)
    attack_factor_b = clamp(1.0 + scale * float(side_b.get("attack_bias", 0.0)), 0.86, 1.18)
    defense_factor_a = clamp(1.0 - scale * float(side_b.get("defense_bias", 0.0)), 0.84, 1.18)
    defense_factor_b = clamp(1.0 - scale * float(side_a.get("defense_bias", 0.0)), 0.84, 1.18)
    tempo_factor = clamp(1.0 + scale * tempo_bias, 0.88, 1.14)

    mu_a *= attack_factor_a * defense_factor_a * tempo_factor
    mu_b *= attack_factor_b * defense_factor_b * tempo_factor
    return clamp(mu_a, 0.01, 4.2), clamp(mu_b, 0.01, 4.2)


def combine_current_score_distribution(
    current_score_a: int,
    current_score_b: int,
    remainder_dist: Dict[Tuple[int, int], float],
) -> Dict[Tuple[int, int], float]:
    final_dist: Dict[Tuple[int, int], float] = {}
    for (goals_a, goals_b), prob in remainder_dist.items():
        final_score = (current_score_a + goals_a, current_score_b + goals_b)
        final_dist[final_score] = final_dist.get(final_score, 0.0) + prob
    return final_dist


def compute_statistical_depth(
    final_dist: Dict[Tuple[int, int], float],
    win_a: float,
    draw: float,
    win_b: float,
    ctx: Optional[MatchContext] = None,
) -> Dict[str, object]:
    result_probs = [max(win_a, 1e-12), max(draw, 1e-12), max(win_b, 1e-12)]
    entropy = -sum(prob * math.log(prob) for prob in result_probs) / math.log(3.0)
    both_score = sum(prob for (goals_a, goals_b), prob in final_dist.items() if goals_a > 0 and goals_b > 0)
    clean_sheet_a = sum(prob for (_, goals_b), prob in final_dist.items() if goals_b == 0)
    clean_sheet_b = sum(prob for (goals_a, _), prob in final_dist.items() if goals_a == 0)
    over_2_5 = sum(prob for (goals_a, goals_b), prob in final_dist.items() if goals_a + goals_b >= 3)
    under_2_5 = 1.0 - over_2_5
    over_3_5 = sum(prob for (goals_a, goals_b), prob in final_dist.items() if goals_a + goals_b >= 4)
    under_3_5 = 1.0 - over_3_5
    top_scores = sorted(final_dist.items(), key=lambda item: item[1], reverse=True)
    top3_coverage = sum(prob for _, prob in top_scores[:3])
    sorted_results = sorted(result_probs, reverse=True)
    top_outcome_prob = sorted_results[0]
    second_outcome_prob = sorted_results[1]
    confidence = clamp(
        0.10
        + 0.60 * top_outcome_prob
        + 0.25 * (top_outcome_prob - second_outcome_prob)
        + 0.10 * top3_coverage
        + 0.10 * (1.0 - entropy),
        0.05,
        0.99,
    )
    margin_dist: Dict[int, float] = {}
    for (goals_a, goals_b), prob in final_dist.items():
        margin = goals_a - goals_b
        margin_dist[margin] = margin_dist.get(margin, 0.0) + prob
    modal_margin, modal_margin_prob = max(margin_dist.items(), key=lambda item: item[1])

    market_gap = None
    if ctx and ctx.market_prob_a is not None and ctx.market_prob_draw is not None and ctx.market_prob_b is not None:
        market_gap = (
            abs(win_a - float(ctx.market_prob_a))
            + abs(draw - float(ctx.market_prob_draw))
            + abs(win_b - float(ctx.market_prob_b))
        ) / 3.0

    return {
        "confidence_index": confidence,
        "entropy_index": entropy,
        "top_outcome_prob": top_outcome_prob,
        "second_outcome_prob": second_outcome_prob,
        "both_teams_score": both_score,
        "clean_sheet_a": clean_sheet_a,
        "clean_sheet_b": clean_sheet_b,
        "over_2_5": over_2_5,
        "under_2_5": under_2_5,
        "over_3_5": over_3_5,
        "under_3_5": under_3_5,
        "top3_coverage": top3_coverage,
        "modal_margin": modal_margin,
        "modal_margin_prob": modal_margin_prob,
        "market_gap": market_gap,
    }


def top_factor_drivers(factors: Optional[Dict[str, float]], limit: int = 3) -> List[Tuple[str, float]]:
    if not factors:
        return []
    labels = {
        "elo_diff": "Elo dinámico",
        "fifa_strength_diff": "Ranking FIFA / puntos FIFA",
        "resource_diff": "Recursos/PIB proxy",
        "heritage_diff": "Historia mundialista",
        "coach_diff": "Entrenador",
        "trajectory_diff": "Trayectoria futbolística",
        "attack_unit_diff": "Ataque",
        "midfield_diff": "Mediocampo",
        "defense_diff": "Defensa",
        "goalkeeper_diff": "Portero",
        "bench_depth_diff": "Profundidad de banco",
        "discipline_diff": "Disciplina estructural",
        "experience_diff": "Experiencia de plantilla",
        "morale_diff": "Moral",
        "home_diff": "Localía/sede",
        "travel_diff": "Viaje",
        "injury_diff": "Bajas/lesiones",
        "cards_diff": "Tarjetas y suspensiones",
        "group_pressure_diff": "Presión de grupo",
        "lineup_diff": "Alineaciones",
        "market_prob_diff": "Mercado victoria/empate/derrota",
        "recent_form_diff": "Forma reciente",
        "attack_form_diff": "Forma ofensiva",
        "defense_form_diff": "Forma defensiva",
        "tactical_attack_diff": "Firma táctica ofensiva",
        "tactical_defense_diff": "Firma táctica defensiva",
        "tactical_tempo_diff": "Ritmo táctico reciente",
        "fatigue_diff": "Fatiga",
        "availability_diff": "Disponibilidad",
        "discipline_trend_diff": "Tendencia disciplinaria",
        "rivalry": "Rivalidad",
    }
    ranked = sorted(
        ((labels.get(key, key), value) for key, value in factors.items() if key not in {"market_draw_prob", "market_total_line", "importance"}),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    return ranked[:limit]


def normalize_team_text(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return "".join(char.lower() for char in ascii_text if char.isalnum())


def normalize_stage_name(raw_stage: Optional[str]) -> Optional[str]:
    if raw_stage is None:
        return None
    if raw_stage in STAGE_IMPORTANCE:
        return raw_stage
    lowered = str(raw_stage).strip().lower()
    alias = STAGE_ALIASES.get(lowered)
    if alias:
        return alias
    compact = lowered.replace(" ", "_")
    alias = STAGE_ALIASES.get(compact)
    if alias:
        return alias
    normalized = normalize_team_text(lowered)
    alias = STAGE_ALIASES.get(normalized)
    if alias:
        return alias
    raise SystemExit(f"Stage no soportado: {raw_stage}")


def resolve_team_name(raw_name: str, teams: Dict[str, Team]) -> str:
    if raw_name in teams:
        return raw_name

    normalized = normalize_team_text(raw_name)
    if normalized in TEAM_NAME_ALIASES:
        return TEAM_NAME_ALIASES[normalized]

    for team_name in teams:
        if normalize_team_text(team_name) == normalized:
            return team_name

    raise SystemExit(
        f"Equipo no encontrado: {raw_name}. Usa list-teams para ver los nombres disponibles."
    )


def resolve_optional_team_name(raw_name: Optional[str], teams: Dict[str, Team]) -> Optional[str]:
    if raw_name is None:
        return None
    return resolve_team_name(raw_name, teams)


def resolve_venue_country(raw_name: Optional[str], teams: Dict[str, Team]) -> Optional[str]:
    if raw_name is None:
        return None

    normalized = normalize_team_text(raw_name)
    host_countries = {team.host_country for team in teams.values() if team.host_country}
    for country in host_countries:
        if country and normalize_team_text(country) == normalized:
            return country

    aliased_team = TEAM_NAME_ALIASES.get(normalized)
    if aliased_team and aliased_team in teams and teams[aliased_team].host_country:
        return teams[aliased_team].host_country

    return raw_name


def resolve_fixture_names(fixture: dict, teams: Dict[str, Team]) -> dict:
    resolved = dict(fixture)
    resolved["team_a"] = resolve_team_name(fixture["team_a"], teams)
    resolved["team_b"] = resolve_team_name(fixture["team_b"], teams)
    if fixture.get("home_team") is not None:
        resolved["home_team"] = resolve_team_name(fixture["home_team"], teams)
    if fixture.get("venue_country") is not None:
        resolved["venue_country"] = resolve_venue_country(fixture["venue_country"], teams)
    return resolved


def poisson_sample(lmbda: float) -> int:
    if lmbda <= 0:
        return 0
    threshold = math.exp(-lmbda)
    product = 1.0
    count = 0
    while product > threshold:
        count += 1
        product *= random.random()
    return count - 1


def load_players(raw_players: Sequence[dict]) -> Tuple[Player, ...]:
    players = []
    for item in raw_players:
        players.append(
            Player(
                name=item["name"],
                position=item["position"],
                quality=float(item["quality"]),
                caps=float(item.get("caps", 0.0)),
                minutes_share=float(item.get("minutes_share", 0.0)),
                attack=float(item.get("attack", 0.0)),
                creation=float(item.get("creation", 0.0)),
                defense=float(item.get("defense", 0.0)),
                goalkeeping=float(item.get("goalkeeping", 0.0)),
                aerial=float(item.get("aerial", 0.0)),
                discipline=float(item.get("discipline", 0.0)),
                yellow_rate=float(item.get("yellow_rate", 0.0)),
                red_rate=float(item.get("red_rate", 0.0)),
                availability=float(item.get("availability", 0.0)),
            )
        )
    return tuple(players)


def load_teams() -> Dict[str, Team]:
    payload = json.loads(DATA_FILE.read_text())
    teams = {}
    for item in payload["teams"]:
        teams[item["name"]] = Team(
            name=item["name"],
            confederation=item["confederation"],
            status=item["status"],
            elo=float(item["elo"]),
            fifa_points=float(item["fifa_points"]) if item.get("fifa_points") is not None else None,
            fifa_rank=int(item["fifa_rank"]) if item.get("fifa_rank") is not None else None,
            host_country=item.get("host_country"),
            resource_bias=float(item.get("resource_bias", 0.0)),
            heritage_bias=float(item.get("heritage_bias", 0.0)),
            coach_bias=float(item.get("coach_bias", 0.0)),
            discipline_bias=float(item.get("discipline_bias", 0.0)),
            chemistry_bias=float(item.get("chemistry_bias", 0.0)),
            attack_bias=float(item.get("attack_bias", 0.0)),
            defense_bias=float(item.get("defense_bias", 0.0)),
            players=load_players(item.get("players", [])),
        )
    return teams


def centered(value: float) -> float:
    return value - 0.5


FIFA_CONFEDERATION_ADJUST = {
    "UEFA": 16.0,
    "CONMEBOL": 18.0,
    "CAF": -6.0,
    "AFC": -8.0,
    "CONCACAF": -10.0,
    "OFC": -28.0,
}


@lru_cache(maxsize=None)
def estimated_fifa_points(team: Team) -> float:
    value = 1050.0 + 0.82 * (team.elo - 1200.0)
    value += 92.0 * centered(heritage_index(team))
    value += 58.0 * centered(resource_index(team))
    value += 34.0 * centered(trajectory_index(team))
    value += 26.0 * centered(coach_index(team))
    value += FIFA_CONFEDERATION_ADJUST.get(team.confederation, 0.0)
    if team.is_host:
        value += 8.0
    return clamp(value, 820.0, 2250.0)


@lru_cache(maxsize=1)
def fifa_reference_table() -> Dict[str, Tuple[float, int, bool]]:
    teams = load_teams()
    rows = []
    for team in teams.values():
        points = float(team.fifa_points) if team.fifa_points is not None else estimated_fifa_points(team)
        rows.append((team.name, points, team.fifa_rank, team.fifa_points is None))

    rows.sort(key=lambda item: (-item[1], item[0]))
    table: Dict[str, Tuple[float, int, bool]] = {}
    for derived_rank, (name, points, explicit_rank, is_proxy) in enumerate(rows, start=1):
        rank = int(explicit_rank) if explicit_rank is not None else derived_rank
        table[name] = (points, rank, is_proxy)
    return table


@lru_cache(maxsize=None)
def fifa_points_value(team: Team) -> float:
    return fifa_reference_table()[team.name][0]


@lru_cache(maxsize=None)
def fifa_rank_value(team: Team) -> int:
    return fifa_reference_table()[team.name][1]


@lru_cache(maxsize=None)
def fifa_points_are_proxy(team: Team) -> bool:
    return fifa_reference_table()[team.name][2]


@lru_cache(maxsize=1)
def fifa_points_bounds() -> Tuple[float, float]:
    values = [points for points, _, _ in fifa_reference_table().values()]
    return (min(values), max(values))


@lru_cache(maxsize=None)
def fifa_strength_index(team: Team) -> float:
    low, high = fifa_points_bounds()
    if high <= low:
        return 0.5
    return clamp((fifa_points_value(team) - low) / (high - low), 0.0, 1.0)


@lru_cache(maxsize=None)
def resource_index(team: Team) -> float:
    base = RESOURCE_OVERRIDES.get(team.name, RESOURCE_BY_CONFEDERATION[team.confederation])
    base += 0.04 * ((team.elo - 1650.0) / 400.0)
    base += team.resource_bias
    if team.is_host:
        base += 0.05
    return clamp(base, 0.18, 1.00)


@lru_cache(maxsize=None)
def heritage_index(team: Team) -> float:
    titles = WORLD_CUP_TITLES.get(team.name, 0)
    base = HISTORICAL_BY_CONFEDERATION[team.confederation]
    base += TRADITION_BONUS.get(team.name, 0.0)
    base += 0.07 * titles
    base += 0.02 if team.status == "qualified" else 0.0
    base += team.heritage_bias
    return clamp(base, 0.10, 1.00)


@lru_cache(maxsize=None)
def trajectory_index(team: Team) -> float:
    value = 0.28
    value += 0.38 * heritage_index(team)
    value += 0.18 * resource_index(team)
    value += 0.06 * clamp((team.elo - 1650.0) / 350.0, -0.2, 0.4)
    value += 0.03 if team.status == "qualified" else 0.0
    return clamp(value, 0.12, 1.00)


@lru_cache(maxsize=None)
def coach_index(team: Team) -> float:
    value = 0.32
    value += 0.26 * heritage_index(team)
    value += 0.14 * resource_index(team)
    value += 0.05 * clamp((team.elo - 1650.0) / 300.0, -0.3, 0.5)
    value += COACH_OVERRIDES.get(team.name, 0.0)
    value += team.coach_bias
    return clamp(value, 0.20, 0.98)


@lru_cache(maxsize=None)
def chemistry_index(team: Team) -> float:
    value = 0.36
    value += 0.22 * coach_index(team)
    value += 0.14 * heritage_index(team)
    value += 0.08 * resource_index(team)
    value += team.chemistry_bias
    return clamp(value, 0.20, 0.98)


@lru_cache(maxsize=None)
def discipline_proxy(team: Team) -> float:
    value = 0.56
    value += DISCIPLINE_BY_CONFEDERATION[team.confederation]
    value += DISCIPLINE_OVERRIDES.get(team.name, 0.0)
    value += team.discipline_bias
    return clamp(value, 0.18, 0.96)


@lru_cache(maxsize=None)
def tactical_flexibility(team: Team) -> float:
    value = 0.34
    value += 0.24 * coach_index(team)
    value += 0.10 * resource_index(team)
    value += 0.06 * heritage_index(team)
    return clamp(value, 0.20, 0.96)


@lru_cache(maxsize=None)
def morale_base(team: Team) -> float:
    value = 0.38
    value += 0.18 * chemistry_index(team)
    value += 0.10 * heritage_index(team)
    value += 0.06 * coach_index(team)
    return clamp(value, 0.20, 0.95)


@lru_cache(maxsize=None)
def travel_resilience(team: Team) -> float:
    value = TRAVEL_BY_CONFEDERATION[team.confederation]
    value += 0.08 * resource_index(team)
    value += 0.05 * chemistry_index(team)
    value += 0.04 if team.is_host else 0.0
    return clamp(value, 0.35, 0.98)


@lru_cache(maxsize=None)
def tempo_proxy(team: Team) -> float:
    value = TEMPO_BY_CONFEDERATION[team.confederation]
    value += 0.03 * centered(trajectory_index(team))
    value += 0.02 * centered(coach_index(team))
    return clamp(value, 0.32, 0.78)


def position_template() -> List[str]:
    return ["GK"] * 3 + ["DF"] * 8 + ["MF"] * 7 + ["FW"] * 5


def player_stat_quality(base: float, jitter: float, rng: random.Random) -> float:
    return clamp(base + rng.uniform(-jitter, jitter), 0.08, 0.98)


@lru_cache(maxsize=None)
def proxy_players(team: Team) -> Tuple[Player, ...]:
    if team.players:
        return team.players

    rng = random.Random(stable_seed(team.name))
    strength = clamp(0.50 + (team.elo - 1650.0) / 620.0, 0.12, 0.92)
    resource = resource_index(team)
    heritage = heritage_index(team)
    coach = coach_index(team)
    chemistry = chemistry_index(team)
    discipline = discipline_proxy(team)
    trajectory = trajectory_index(team)

    players = []
    for index, position in enumerate(position_template(), start=1):
        base_quality = 0.26 + 0.42 * strength + 0.12 * resource + 0.08 * heritage + 0.05 * chemistry
        quality = player_stat_quality(base_quality, 0.12, rng)
        caps = clamp(
            10.0 + 70.0 * (0.32 + 0.35 * heritage + 0.18 * chemistry + 0.10 * resource + rng.uniform(-0.15, 0.15)),
            1.0,
            160.0,
        )
        minutes_share = clamp(0.54 + 0.20 * chemistry + rng.uniform(-0.12, 0.12), 0.16, 1.00)
        availability = clamp(0.78 + 0.10 * resource + 0.06 * coach + rng.uniform(-0.10, 0.06), 0.55, 0.99)
        discipline_player = clamp(discipline + rng.uniform(-0.12, 0.12), 0.08, 0.98)

        if position == "GK":
            attack = player_stat_quality(0.10 + 0.15 * quality, 0.03, rng)
            creation = player_stat_quality(0.08 + 0.10 * quality, 0.03, rng)
            defense = player_stat_quality(0.34 + 0.25 * quality + 0.10 * coach, 0.06, rng)
            goalkeeping = player_stat_quality(0.46 + 0.30 * quality + 0.12 * coach + 0.06 * heritage, 0.08, rng)
            aerial = player_stat_quality(0.42 + 0.28 * quality, 0.07, rng)
        elif position == "DF":
            attack = player_stat_quality(0.14 + 0.18 * quality + 0.05 * resource, 0.05, rng)
            creation = player_stat_quality(0.18 + 0.20 * quality + 0.04 * coach, 0.06, rng)
            defense = player_stat_quality(0.32 + 0.34 * quality + 0.05 * heritage, 0.08, rng)
            goalkeeping = 0.0
            aerial = player_stat_quality(0.28 + 0.32 * quality + 0.06 * heritage, 0.06, rng)
        elif position == "MF":
            attack = player_stat_quality(0.22 + 0.28 * quality + 0.05 * trajectory, 0.07, rng)
            creation = player_stat_quality(0.24 + 0.34 * quality + 0.06 * coach, 0.08, rng)
            defense = player_stat_quality(0.20 + 0.22 * quality + 0.05 * chemistry, 0.06, rng)
            goalkeeping = 0.0
            aerial = player_stat_quality(0.18 + 0.18 * quality, 0.05, rng)
        else:
            attack = player_stat_quality(0.30 + 0.38 * quality + 0.06 * resource + 0.04 * coach, 0.09, rng)
            creation = player_stat_quality(0.18 + 0.24 * quality + 0.04 * chemistry, 0.08, rng)
            defense = player_stat_quality(0.10 + 0.10 * quality + 0.02 * chemistry, 0.04, rng)
            goalkeeping = 0.0
            aerial = player_stat_quality(0.20 + 0.24 * quality + 0.04 * heritage, 0.06, rng)

        yellow_rate = clamp(
            0.26 - 0.16 * discipline_player + (0.03 if position in {"DF", "MF"} else 0.0) + rng.uniform(-0.03, 0.03),
            0.03,
            0.42,
        )
        red_rate = clamp(
            0.025 - 0.014 * discipline_player + (0.008 if position == "DF" else 0.0) + rng.uniform(-0.004, 0.004),
            0.001,
            0.05,
        )

        players.append(
            Player(
                name=f"{team.name}_{position}_{index}",
                position=position,
                quality=quality,
                caps=caps,
                minutes_share=minutes_share,
                attack=attack,
                creation=creation,
                defense=defense,
                goalkeeping=goalkeeping,
                aerial=aerial,
                discipline=discipline_player,
                yellow_rate=yellow_rate,
                red_rate=red_rate,
                availability=availability,
            )
        )
    return tuple(players)


def sort_by(players: Sequence[Player], key_name: str) -> List[Player]:
    return sorted(players, key=lambda player: getattr(player, key_name), reverse=True)


@lru_cache(maxsize=None)
def aggregate_squad(team: Team) -> SquadAggregate:
    players = proxy_players(team)
    gks = [player for player in players if player.position == "GK"]
    dfs = [player for player in players if player.position == "DF"]
    mfs = [player for player in players if player.position == "MF"]
    fws = [player for player in players if player.position == "FW"]

    starting = (
        sort_by(gks, "goalkeeping")[:1]
        + sorted(dfs, key=lambda player: player.defense + 0.25 * player.aerial, reverse=True)[:4]
        + sorted(mfs, key=lambda player: player.creation + 0.15 * player.defense, reverse=True)[:3]
        + sorted(fws, key=lambda player: player.attack + 0.10 * player.creation, reverse=True)[:3]
    )
    bench = [player for player in players if player not in starting]

    squad_quality = sum(player.quality for player in starting) / len(starting)
    attack_unit = (
        0.55 * sum(player.attack for player in starting if player.position == "FW") / 3.0
        + 0.30 * sum(player.attack for player in starting if player.position == "MF") / 3.0
        + 0.15 * sum(player.attack for player in starting if player.position == "DF") / 4.0
    )
    midfield_unit = sum(
        0.55 * player.creation + 0.25 * player.quality + 0.20 * player.defense
        for player in starting
        if player.position == "MF"
    ) / 3.0
    defense_unit = (
        0.60 * sum(player.defense for player in starting if player.position == "DF") / 4.0
        + 0.20 * sum(player.defense for player in starting if player.position == "MF") / 3.0
        + 0.20 * sum(player.goalkeeping for player in starting if player.position == "GK")
    )
    goalkeeper_unit = sum(player.goalkeeping for player in starting if player.position == "GK")
    bench_depth = sum(player.quality for player in bench) / len(bench)
    player_experience = clamp(sum(player.caps for player in starting) / (len(starting) * 100.0), 0.08, 1.00)
    set_piece_attack = clamp(
        (
            sum(player.aerial for player in starting if player.position in {"DF", "FW"}) / 7.0
            + sum(player.creation for player in starting if player.position == "MF") / 6.0
        ),
        0.08,
        1.00,
    )
    set_piece_defense = clamp(
        (
            sum(player.aerial for player in starting if player.position in {"GK", "DF", "MF"}) / 8.0
            + 0.40 * goalkeeper_unit
        ),
        0.08,
        1.00,
    )
    discipline_index = clamp(sum(player.discipline for player in starting) / len(starting), 0.08, 1.00)
    yellow_rate = clamp(sum(player.yellow_rate for player in starting) / len(starting), 0.02, 0.40)
    red_rate = clamp(sum(player.red_rate for player in starting) / len(starting), 0.001, 0.05)
    availability = clamp(sum(player.availability for player in starting) / len(starting), 0.50, 1.00)
    finishing = clamp(sum(player.attack for player in starting if player.position == "FW") / 3.0, 0.08, 1.00)
    shot_creation = clamp(
        (
            sum(player.creation for player in starting if player.position == "MF") / 3.0
            + 0.45 * sum(player.creation for player in starting if player.position == "FW") / 3.0
        ),
        0.08,
        1.00,
    )
    pressing = clamp(
        (
            0.45 * sum(player.defense for player in starting if player.position == "MF") / 3.0
            + 0.35 * sum(player.defense for player in starting if player.position == "FW") / 3.0
            + 0.20 * sum(player.defense for player in starting if player.position == "DF") / 4.0
        ),
        0.08,
        1.00,
    )

    return SquadAggregate(
        squad_quality=clamp(squad_quality, 0.08, 1.00),
        attack_unit=clamp(attack_unit, 0.08, 1.00),
        midfield_unit=clamp(midfield_unit, 0.08, 1.00),
        defense_unit=clamp(defense_unit, 0.08, 1.00),
        goalkeeper_unit=clamp(goalkeeper_unit, 0.08, 1.00),
        bench_depth=clamp(bench_depth, 0.08, 1.00),
        player_experience=player_experience,
        set_piece_attack=set_piece_attack,
        set_piece_defense=set_piece_defense,
        discipline_index=discipline_index,
        yellow_rate=yellow_rate,
        red_rate=red_rate,
        availability=availability,
        finishing=finishing,
        shot_creation=shot_creation,
        pressing=pressing,
    )


@lru_cache(maxsize=None)
def profile_for(team: Team) -> TeamProfile:
    return TeamProfile(
        fifa_points=fifa_points_value(team),
        fifa_rank=fifa_rank_value(team),
        fifa_strength_index=fifa_strength_index(team),
        resource_index=resource_index(team),
        heritage_index=heritage_index(team),
        world_cup_titles=WORLD_CUP_TITLES.get(team.name, 0),
        trajectory_index=trajectory_index(team),
        coach_index=coach_index(team),
        chemistry_index=chemistry_index(team),
        morale_base=morale_base(team),
        tactical_flexibility=tactical_flexibility(team),
        travel_resilience=travel_resilience(team),
        tempo=tempo_proxy(team),
        squad=aggregate_squad(team),
    )


def rivalry_intensity(team_a: Team, team_b: Team) -> float:
    if frozenset({team_a.name, team_b.name}) in RIVALRIES:
        return RIVALRIES[frozenset({team_a.name, team_b.name})]
    if team_a.confederation == team_b.confederation:
        return 0.03
    return 0.0


def group_pressure(points: int, matches_played: int, goal_diff: int) -> float:
    if matches_played <= 0:
        return 0.0
    expected_points = 1.4 * matches_played
    gap = expected_points - points
    pressure = 0.08 * gap - 0.02 * clamp(goal_diff, -3, 3)
    return clamp(pressure, -0.18, 0.20)


def current_morale(profile: TeamProfile, explicit_morale: float) -> float:
    base = -0.02 + 0.28 * centered(profile.morale_base)
    base += 0.18 * clamp(explicit_morale, -1.0, 1.0)
    return clamp(base, -0.25, 0.25)


def market_probability(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return clamp(float(value), 0.01, 0.98)


def discipline_absence_penalty(profile: TeamProfile, yellow_cards: int, red_suspensions: int) -> float:
    penalty = 0.06 * clamp(yellow_cards, 0, 6) * (0.55 - centered(profile.squad.discipline_index))
    penalty += 0.18 * clamp(red_suspensions, 0, 4)
    return clamp(penalty, 0.0, 0.55)


def state_float(state: Optional[dict], key: str, default: float) -> float:
    if not state:
        return default
    return float(state.get(key, default))


def state_int(state: Optional[dict], key: str, default: int) -> int:
    if not state:
        return default
    return int(state.get(key, default))


def effective_elo(team: Team, state: Optional[dict] = None) -> float:
    return clamp(team.elo + state_float(state, "elo_shift", 0.0), 1200.0, 2400.0)


def recent_form_signal(state: Optional[dict]) -> float:
    return clamp(state_float(state, "recent_form", 0.0), -1.0, 1.0)


def attack_form_signal(state: Optional[dict]) -> float:
    return clamp(state_float(state, "attack_form", 0.0), -1.0, 1.0)


def defense_form_signal(state: Optional[dict]) -> float:
    return clamp(state_float(state, "defense_form", 0.0), -1.0, 1.0)


def fatigue_level(state: Optional[dict]) -> float:
    return clamp(state_float(state, "fatigue", 0.0), 0.0, 1.0)


def availability_level(state: Optional[dict]) -> float:
    return clamp(state_float(state, "availability", 1.0), 0.40, 1.0)


def discipline_trend(state: Optional[dict]) -> float:
    return clamp(state_float(state, "discipline_drift", 0.0), -1.0, 0.5)


def predictive_yellow_cards(state: Optional[dict]) -> int:
    yellow_load = state_float(state, "yellow_load", 0.0)
    accumulated = state_int(state, "yellow_cards", 0)
    return int(round(clamp(max(yellow_load, 0.35 * accumulated), 0.0, 6.0)))


def dynamic_injury_load(team: Team, state: Optional[dict]) -> float:
    profile = profile_for(team)
    baseline = 0.08 * (1.0 - profile.squad.availability)
    fatigue_pressure = 0.24 * fatigue_level(state)
    availability_pressure = 0.34 * (1.0 - availability_level(state))
    return clamp(baseline + fatigue_pressure + availability_pressure, 0.0, 0.75)


def context_components(
    team: Team,
    profile: TeamProfile,
    opponent: Team,
    ctx: MatchContext,
    side: str,
    state: Optional[dict] = None,
) -> Dict[str, float]:
    if side == "A":
        rest_days = ctx.rest_days_a
        other_rest_days = ctx.rest_days_b
        injuries = ctx.injuries_a
        travel = ctx.travel_km_a
        other_travel = ctx.travel_km_b
        morale_signal = ctx.morale_a
        yellow_cards = ctx.yellow_cards_a
        red_suspensions = ctx.red_suspensions_a
        group_points_value = ctx.group_points_a
        group_goal_diff_value = ctx.group_goal_diff_a
        group_matches_played = ctx.group_matches_played_a
        lineup_confirmed = ctx.lineup_confirmed_a
        lineup_changes = ctx.lineup_change_count_a
    else:
        rest_days = ctx.rest_days_b
        other_rest_days = ctx.rest_days_a
        injuries = ctx.injuries_b
        travel = ctx.travel_km_b
        other_travel = ctx.travel_km_a
        morale_signal = ctx.morale_b
        yellow_cards = ctx.yellow_cards_b
        red_suspensions = ctx.red_suspensions_b
        group_points_value = ctx.group_points_b
        group_goal_diff_value = ctx.group_goal_diff_b
        group_matches_played = ctx.group_matches_played_b
        lineup_confirmed = ctx.lineup_confirmed_b
        lineup_changes = ctx.lineup_change_count_b

    components = {
        "home": 0.0,
        "rest": 0.0,
        "travel": 0.0,
        "morale": current_morale(profile, morale_signal),
        "injury": -0.30 * clamp(injuries, 0.0, 1.0),
        "cards": -discipline_absence_penalty(profile, yellow_cards, red_suspensions),
        "group_pressure": 0.0,
        "weather": -0.08 * clamp(ctx.weather_stress, 0.0, 1.0),
        "altitude": 0.0,
        "rivalry": rivalry_intensity(team, opponent),
        "lineup": (0.01 if lineup_confirmed else 0.0) - 0.018 * clamp(lineup_changes, 0, 6),
        "fatigue": -0.14 * fatigue_level(state),
        "availability": -0.18 * (1.0 - availability_level(state)),
        "recent_form": 0.10 * recent_form_signal(state),
    }

    if not ctx.neutral and ctx.home_team == team.name:
        components["home"] += 0.22
    if ctx.venue_country and team.host_country == ctx.venue_country:
        components["home"] += 0.14
    elif ctx.venue_country in HOST_COUNTRIES and team.is_host:
        components["home"] += 0.06

    rest_diff = clamp(rest_days - other_rest_days, -4, 4)
    components["rest"] = 0.018 * rest_diff

    travel_diff = max(travel - other_travel, 0.0)
    components["travel"] = -0.18 * (travel_diff / 6000.0) * (1.0 - profile.travel_resilience)

    pressure = group_pressure(group_points_value, group_matches_played, group_goal_diff_value)
    components["group_pressure"] = -0.10 * pressure

    if ctx.altitude_m >= 1400 and ctx.venue_country == "Mexico" and team.name == "Mexico":
        components["altitude"] += 0.05
    if ctx.altitude_m >= 1400 and opponent.name == "Mexico" and team.name != "Mexico":
        components["altitude"] -= 0.02

    return components


def attack_metric(team: Team, profile: TeamProfile, state: Optional[dict] = None) -> float:
    strength = (effective_elo(team, state) - 1650.0) / 320.0
    value = 0.48 * strength
    value += 0.05 * centered(profile.fifa_strength_index)
    value += 0.30 * centered(profile.squad.attack_unit)
    value += 0.18 * centered(profile.squad.midfield_unit)
    value += 0.14 * centered(profile.squad.finishing)
    value += 0.10 * centered(profile.squad.set_piece_attack)
    value += 0.08 * centered(profile.coach_index)
    value += 0.06 * centered(profile.resource_index)
    value += 0.06 * centered(profile.trajectory_index)
    value += team.attack_bias
    value += 0.28 * attack_form_signal(state)
    value += 0.16 * recent_form_signal(state)
    value += 0.10 * tactical_attack_signal(state)
    value += 0.04 * tactical_tempo_signal(state)
    value -= 0.12 * fatigue_level(state)
    value -= 0.22 * (1.0 - availability_level(state))
    return value


def defense_metric(team: Team, profile: TeamProfile, state: Optional[dict] = None) -> float:
    strength = (effective_elo(team, state) - 1650.0) / 340.0
    value = 0.44 * strength
    value += 0.04 * centered(profile.fifa_strength_index)
    value += 0.28 * centered(profile.squad.defense_unit)
    value += 0.14 * centered(profile.squad.goalkeeper_unit)
    value += 0.10 * centered(profile.squad.player_experience)
    value += 0.08 * centered(profile.squad.discipline_index)
    value += 0.06 * centered(profile.coach_index)
    value += 0.05 * centered(profile.heritage_index)
    value += 0.04 * centered(profile.squad.set_piece_defense)
    value += team.defense_bias
    value += 0.30 * defense_form_signal(state)
    value += 0.14 * recent_form_signal(state)
    value += 0.08 * discipline_trend(state)
    value += 0.08 * tactical_defense_signal(state)
    value -= 0.03 * tactical_tempo_signal(state)
    value -= 0.10 * fatigue_level(state)
    value -= 0.20 * (1.0 - availability_level(state))
    return value


def expected_goals(
    team_a: Team,
    team_b: Team,
    ctx: MatchContext,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> Tuple[float, float]:
    profile_a = profile_for(team_a)
    profile_b = profile_for(team_b)
    context_a = context_components(team_a, profile_a, team_b, ctx, "A", state_a)
    context_b = context_components(team_b, profile_b, team_a, ctx, "B", state_b)
    importance_scale = clamp(ctx.importance, 0.70, 1.50)

    attack_a = attack_metric(team_a, profile_a, state_a)
    attack_b = attack_metric(team_b, profile_b, state_b)
    defense_a = defense_metric(team_a, profile_a, state_a)
    defense_b = defense_metric(team_b, profile_b, state_b)

    attack_edge_a = attack_a - defense_b
    attack_edge_b = attack_b - defense_a
    elo_diff = effective_elo(team_a, state_a) - effective_elo(team_b, state_b)
    fifa_diff = profile_a.fifa_strength_index - profile_b.fifa_strength_index
    history_weight = (0.11 if ctx.knockout else 0.06) * importance_scale

    delta_score = elo_diff / 255.0
    delta_score += 0.16 * fifa_diff
    delta_score += 0.95 * (attack_edge_a - attack_edge_b)
    delta_score += history_weight * (profile_a.heritage_index - profile_b.heritage_index)
    delta_score += 0.07 * (profile_a.resource_index - profile_b.resource_index)
    delta_score += 0.09 * (profile_a.coach_index - profile_b.coach_index)
    delta_score += 0.07 * (profile_a.squad.player_experience - profile_b.squad.player_experience)
    delta_score += 0.05 * (profile_a.chemistry_index - profile_b.chemistry_index)
    delta_score += 0.05 * (importance_scale - 1.0) * (
        (profile_a.coach_index + profile_a.squad.player_experience + profile_a.heritage_index)
        - (profile_b.coach_index + profile_b.squad.player_experience + profile_b.heritage_index)
    )
    delta_score += 0.30 * ((sum(context_a.values()) - sum(context_b.values())))
    delta_score += 0.14 * (recent_form_signal(state_a) - recent_form_signal(state_b))
    delta_score += 0.10 * (attack_form_signal(state_a) - attack_form_signal(state_b))
    delta_score += 0.08 * (defense_form_signal(state_a) - defense_form_signal(state_b))
    delta_score += 0.06 * (tactical_attack_signal(state_a) - tactical_attack_signal(state_b))
    delta_score += 0.04 * (tactical_defense_signal(state_a) - tactical_defense_signal(state_b))
    delta_score -= 0.10 * (fatigue_level(state_a) - fatigue_level(state_b))
    delta_score += 0.08 * (availability_level(state_a) - availability_level(state_b))
    if (
        ctx.market_prob_a is not None
        and ctx.market_prob_b is not None
        and ctx.market_prob_draw is not None
    ):
        market_edge = clamp(ctx.market_prob_a - ctx.market_prob_b, -0.90, 0.90)
        market_draw_suppression = clamp(ctx.market_prob_draw - 0.26, -0.18, 0.18)
        delta_score += 0.72 * market_edge
        delta_score -= 0.08 * market_draw_suppression

    share_a = logistic(delta_score)

    total_goals = 2.28
    total_goals += 0.16 * abs(elo_diff) / 400.0
    total_goals += 0.04 * abs(fifa_diff)
    total_goals += 0.18 * centered(profile_a.squad.attack_unit + profile_b.squad.attack_unit)
    total_goals += 0.12 * centered(profile_a.squad.shot_creation + profile_b.squad.shot_creation)
    total_goals -= 0.12 * centered(profile_a.squad.defense_unit + profile_b.squad.defense_unit)
    total_goals -= 0.06 * centered(profile_a.squad.goalkeeper_unit + profile_b.squad.goalkeeper_unit)
    total_goals += 0.06 * (profile_a.tempo + profile_b.tempo - 1.0)
    total_goals += 0.03 * (profile_a.squad.red_rate + profile_b.squad.red_rate - 0.02)
    total_goals += 0.04 * (
        group_pressure(ctx.group_points_a, ctx.group_matches_played_a, ctx.group_goal_diff_a)
        + group_pressure(ctx.group_points_b, ctx.group_matches_played_b, ctx.group_goal_diff_b)
    )
    total_goals -= 0.10 if ctx.knockout else 0.0
    total_goals -= 0.08 * max(importance_scale - 1.0, 0.0)
    total_goals += 0.05 * max(1.0 - importance_scale, 0.0)
    total_goals -= 0.12 * (clamp(ctx.injuries_a, 0.0, 1.0) + clamp(ctx.injuries_b, 0.0, 1.0))
    total_goals -= 0.05 * ((ctx.travel_km_a + ctx.travel_km_b) / 12000.0)
    total_goals -= 0.10 * clamp(ctx.weather_stress, 0.0, 1.0)
    total_goals += 0.08 if ctx.altitude_m >= 1400 else 0.0
    total_goals += 0.03 * rivalry_intensity(team_a, team_b)
    total_goals += 0.08 * (attack_form_signal(state_a) + attack_form_signal(state_b))
    total_goals -= 0.05 * (defense_form_signal(state_a) + defense_form_signal(state_b))
    total_goals += 0.06 * (tactical_tempo_signal(state_a) + tactical_tempo_signal(state_b))
    total_goals += 0.03 * (tactical_attack_signal(state_a) + tactical_attack_signal(state_b))
    total_goals -= 0.02 * (tactical_defense_signal(state_a) + tactical_defense_signal(state_b))
    total_goals -= 0.10 * (fatigue_level(state_a) + fatigue_level(state_b))
    total_goals -= 0.07 * ((1.0 - availability_level(state_a)) + (1.0 - availability_level(state_b)))
    if ctx.market_total_line is not None:
        total_goals = 0.84 * total_goals + 0.16 * clamp(ctx.market_total_line + 0.05, 1.5, 4.6)
    if ctx.market_prob_draw is not None:
        total_goals -= 0.12 * clamp(ctx.market_prob_draw - 0.26, -0.15, 0.22)
    total_goals = clamp(total_goals, 1.45, 4.55)

    mu_a = clamp(total_goals * share_a, 0.07, 4.95)
    mu_b = clamp(total_goals * (1.0 - share_a), 0.07, 4.95)
    return mu_a, mu_b


def factor_breakdown(
    team_a: Team,
    team_b: Team,
    ctx: MatchContext,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> Dict[str, float]:
    profile_a = profile_for(team_a)
    profile_b = profile_for(team_b)
    context_a = context_components(team_a, profile_a, team_b, ctx, "A", state_a)
    context_b = context_components(team_b, profile_b, team_a, ctx, "B", state_b)
    return {
        "elo_diff": effective_elo(team_a, state_a) - effective_elo(team_b, state_b),
        "fifa_strength_diff": profile_a.fifa_strength_index - profile_b.fifa_strength_index,
        "resource_diff": profile_a.resource_index - profile_b.resource_index,
        "heritage_diff": profile_a.heritage_index - profile_b.heritage_index,
        "coach_diff": profile_a.coach_index - profile_b.coach_index,
        "importance": clamp(ctx.importance, 0.70, 1.50),
        "trajectory_diff": profile_a.trajectory_index - profile_b.trajectory_index,
        "attack_unit_diff": profile_a.squad.attack_unit - profile_b.squad.attack_unit,
        "midfield_diff": profile_a.squad.midfield_unit - profile_b.squad.midfield_unit,
        "defense_diff": profile_a.squad.defense_unit - profile_b.squad.defense_unit,
        "goalkeeper_diff": profile_a.squad.goalkeeper_unit - profile_b.squad.goalkeeper_unit,
        "bench_depth_diff": profile_a.squad.bench_depth - profile_b.squad.bench_depth,
        "discipline_diff": profile_a.squad.discipline_index - profile_b.squad.discipline_index,
        "experience_diff": profile_a.squad.player_experience - profile_b.squad.player_experience,
        "morale_diff": context_a["morale"] - context_b["morale"],
        "home_diff": context_a["home"] - context_b["home"],
        "travel_diff": context_a["travel"] - context_b["travel"],
        "injury_diff": context_a["injury"] - context_b["injury"],
        "cards_diff": context_a["cards"] - context_b["cards"],
        "group_pressure_diff": context_a["group_pressure"] - context_b["group_pressure"],
        "lineup_diff": context_a["lineup"] - context_b["lineup"],
        "market_prob_diff": (ctx.market_prob_a or 0.0) - (ctx.market_prob_b or 0.0),
        "market_draw_prob": ctx.market_prob_draw or 0.0,
        "market_total_line": ctx.market_total_line or 0.0,
        "recent_form_diff": recent_form_signal(state_a) - recent_form_signal(state_b),
        "attack_form_diff": attack_form_signal(state_a) - attack_form_signal(state_b),
        "defense_form_diff": defense_form_signal(state_a) - defense_form_signal(state_b),
        "tactical_attack_diff": tactical_attack_signal(state_a) - tactical_attack_signal(state_b),
        "tactical_defense_diff": tactical_defense_signal(state_a) - tactical_defense_signal(state_b),
        "tactical_tempo_diff": tactical_tempo_signal(state_a) - tactical_tempo_signal(state_b),
        "fatigue_diff": fatigue_level(state_a) - fatigue_level(state_b),
        "availability_diff": availability_level(state_a) - availability_level(state_b),
        "discipline_trend_diff": discipline_trend(state_a) - discipline_trend(state_b),
        "rivalry": rivalry_intensity(team_a, team_b),
    }


def bivariate_poisson_prob(x: int, y: int, lambda1: float, lambda2: float, lambda3: float) -> float:
    limit = min(x, y)
    exp_term = math.exp(-(lambda1 + lambda2 + lambda3))
    total = 0.0
    for shared in range(limit + 1):
        total += (
            (lambda1 ** (x - shared) / FACTORIALS[x - shared])
            * (lambda2 ** (y - shared) / FACTORIALS[y - shared])
            * (lambda3 ** shared / FACTORIALS[shared])
        )
    return exp_term * total


def score_distribution(mu_a: float, mu_b: float, max_goals: int = 10) -> Dict[Tuple[int, int], float]:
    lambda3 = min(0.10, mu_a * 0.18, mu_b * 0.18)
    lambda3 = max(lambda3, 0.0)
    lambda1 = max(mu_a - lambda3, 0.001)
    lambda2 = max(mu_b - lambda3, 0.001)
    dist = {}
    total = 0.0
    for goals_a in range(max_goals + 1):
        for goals_b in range(max_goals + 1):
            prob = bivariate_poisson_prob(goals_a, goals_b, lambda1, lambda2, lambda3)
            dist[(goals_a, goals_b)] = prob
            total += prob
    if total == 0:
        return dist
    for key in list(dist):
        dist[key] /= total
    return dist


def penalties_context_state(ctx_morale: float, state: Optional[dict]) -> dict:
    penalties_state = normalize_team_state(state)
    penalties_state["morale"] = clamp(ctx_morale, -1.0, 1.0)
    return penalties_state


def extra_time_expected_goals(
    mu_a: float,
    mu_b: float,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> Tuple[float, float]:
    base_share = 0.29
    extra_fatigue_a = clamp(1.0 - 0.16 * fatigue_level(state_a) - 0.10 * (1.0 - availability_level(state_a)), 0.58, 1.05)
    extra_fatigue_b = clamp(1.0 - 0.16 * fatigue_level(state_b) - 0.10 * (1.0 - availability_level(state_b)), 0.58, 1.05)
    attacking_push_a = 1.0 + 0.08 * attack_form_signal(state_a) + 0.04 * recent_form_signal(state_a)
    attacking_push_b = 1.0 + 0.08 * attack_form_signal(state_b) + 0.04 * recent_form_signal(state_b)
    et_mu_a = clamp(mu_a * base_share * extra_fatigue_a * attacking_push_a, 0.03, 1.35)
    et_mu_b = clamp(mu_b * base_share * extra_fatigue_b * attacking_push_b, 0.03, 1.35)
    return et_mu_a, et_mu_b


def knockout_resolution_detail(
    team_a: Team,
    team_b: Team,
    ctx: MatchContext,
    mu_a: float,
    mu_b: float,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> Dict[str, float]:
    et_mu_a, et_mu_b = extra_time_expected_goals(mu_a, mu_b, state_a=state_a, state_b=state_b)
    et_dist = score_distribution(et_mu_a, et_mu_b, max_goals=5)
    et_win_a = 0.0
    et_draw = 0.0
    et_win_b = 0.0
    for (goals_a, goals_b), prob in et_dist.items():
        if goals_a > goals_b:
            et_win_a += prob
        elif goals_a < goals_b:
            et_win_b += prob
        else:
            et_draw += prob

    penalties_a = penalties_probability(
        team_a,
        team_b,
        penalties_context_state(ctx.morale_a, state_a),
        penalties_context_state(ctx.morale_b, state_b),
    )
    penalties_b = 1.0 - penalties_a
    return {
        "et_xg_a": et_mu_a,
        "et_xg_b": et_mu_b,
        "et_win_a": et_win_a,
        "et_draw": et_draw,
        "et_win_b": et_win_b,
        "penalties_a": penalties_a,
        "penalties_b": penalties_b,
        "reach_penalties": et_draw,
        "advance_a_from_draw": et_win_a + et_draw * penalties_a,
        "advance_b_from_draw": et_win_b + et_draw * penalties_b,
    }


def sample_knockout_resolution(
    team_a: Team,
    team_b: Team,
    ctx: MatchContext,
    score_a: int,
    score_b: int,
    mu_a: float,
    mu_b: float,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> dict:
    if score_a > score_b:
        return {
            "winner": team_a.name,
            "loser": team_b.name,
            "score_a": score_a,
            "score_b": score_b,
            "extra_time_score_a": 0,
            "extra_time_score_b": 0,
            "went_extra_time": False,
            "went_penalties": False,
            "penalty_score_a": None,
            "penalty_score_b": None,
        }
    if score_b > score_a:
        return {
            "winner": team_b.name,
            "loser": team_a.name,
            "score_a": score_a,
            "score_b": score_b,
            "extra_time_score_a": 0,
            "extra_time_score_b": 0,
            "went_extra_time": False,
            "went_penalties": False,
            "penalty_score_a": None,
            "penalty_score_b": None,
        }

    et_mu_a, et_mu_b = extra_time_expected_goals(mu_a, mu_b, state_a=state_a, state_b=state_b)
    et_score_a, et_score_b = sample_score(et_mu_a, et_mu_b)
    total_a = score_a + et_score_a
    total_b = score_b + et_score_b
    if et_score_a > et_score_b:
        winner = team_a.name
        loser = team_b.name
        went_penalties = False
    elif et_score_b > et_score_a:
        winner = team_b.name
        loser = team_a.name
        went_penalties = False
        penalty_score_a = None
        penalty_score_b = None
    else:
        shootout = simulate_penalty_shootout(
            team_a,
            team_b,
            ctx,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
            a_starts=random.random() < 0.5,
        )
        winner = shootout["winner"]
        loser = team_b.name if winner == team_a.name else team_a.name
        went_penalties = True
        penalty_score_a = shootout["score_a"]
        penalty_score_b = shootout["score_b"]
    if not went_penalties:
        penalty_score_a = None
        penalty_score_b = None

    return {
        "winner": winner,
        "loser": loser,
        "score_a": total_a,
        "score_b": total_b,
        "extra_time_score_a": et_score_a,
        "extra_time_score_b": et_score_b,
        "went_extra_time": True,
        "went_penalties": went_penalties,
        "penalty_score_a": penalty_score_a,
        "penalty_score_b": penalty_score_b,
    }


def predict_match(
    teams: Dict[str, Team],
    team_a_name: str,
    team_b_name: str,
    ctx: Optional[MatchContext] = None,
    top_scores: int = 6,
    include_advancement: bool = False,
    show_factors: bool = False,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> MatchPrediction:
    ctx = ctx or MatchContext()
    team_a = teams[team_a_name]
    team_b = teams[team_b_name]
    mu_a, mu_b = expected_goals(team_a, team_b, ctx, state_a=state_a, state_b=state_b)
    dist = score_distribution(mu_a, mu_b)

    win_a = 0.0
    draw = 0.0
    win_b = 0.0
    exact = []
    for (goals_a, goals_b), prob in dist.items():
        exact.append((f"{goals_a}-{goals_b}", prob))
        if goals_a > goals_b:
            win_a += prob
        elif goals_a == goals_b:
            draw += prob
        else:
            win_b += prob

    exact.sort(key=lambda item: item[1], reverse=True)
    advance_a = None
    advance_b = None
    knockout_detail = None
    penalty_shootout = None
    if include_advancement:
        knockout_detail = knockout_resolution_detail(
            team_a,
            team_b,
            ctx,
            mu_a,
            mu_b,
            state_a=state_a,
            state_b=state_b,
        )
        advance_a = win_a + draw * knockout_detail["advance_a_from_draw"]
        advance_b = win_b + draw * knockout_detail["advance_b_from_draw"]
        penalty_shootout = penalty_shootout_summary(
            team_a,
            team_b,
            ctx,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
            iterations=1600,
        )
    factors = factor_breakdown(team_a, team_b, ctx, state_a=state_a, state_b=state_b) if show_factors else None

    return MatchPrediction(
        team_a=team_a_name,
        team_b=team_b_name,
        expected_goals_a=mu_a,
        expected_goals_b=mu_b,
        win_a=win_a,
        draw=draw,
        win_b=win_b,
        exact_scores=exact[:top_scores],
        advance_a=advance_a,
        advance_b=advance_b,
        knockout_detail=knockout_detail,
        penalty_shootout=penalty_shootout,
        factors=factors,
        statistical_depth=compute_statistical_depth(dist, win_a, draw, win_b, ctx),
    )


def predict_match_live(
    teams: Dict[str, Team],
    team_a_name: str,
    team_b_name: str,
    ctx: MatchContext,
    current_score_a: int,
    current_score_b: int,
    status_detail: Optional[str],
    top_scores: int = 6,
    include_advancement: bool = False,
    show_factors: bool = False,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
    live_stats: Optional[Dict[str, float]] = None,
) -> MatchPrediction:
    team_a = teams[team_a_name]
    team_b = teams[team_b_name]
    base_mu_a, base_mu_b = expected_goals(team_a, team_b, ctx, state_a=state_a, state_b=state_b)
    elapsed_minutes, phase = parse_elapsed_minutes(status_detail, ctx.knockout)
    patterns = None

    if phase == "penalties":
        patterns = detect_live_play_patterns(
            live_stats,
            1.0,
            phase,
            current_score_a,
            current_score_b,
        )
        penalties_a = penalties_probability(
            team_a,
            team_b,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
        )
        penalties_b = 1.0 - penalties_a
        shootout = penalty_shootout_summary(
            team_a,
            team_b,
            ctx,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
            iterations=1600,
        )
        factors = factor_breakdown(team_a, team_b, ctx, state_a=state_a, state_b=state_b) if show_factors else None
        final_dist = {(current_score_a, current_score_b): 1.0}
        return MatchPrediction(
            team_a=team_a_name,
            team_b=team_b_name,
            expected_goals_a=float(current_score_a),
            expected_goals_b=float(current_score_b),
            win_a=0.0,
            draw=1.0,
            win_b=0.0,
            exact_scores=[(f"{current_score_a}-{current_score_b}", 1.0)],
            advance_a=penalties_a if include_advancement else None,
            advance_b=penalties_b if include_advancement else None,
            knockout_detail={
                "et_xg_a": 0.0,
                "et_xg_b": 0.0,
                "et_win_a": 0.0,
                "et_draw": 1.0,
                "et_win_b": 0.0,
                "penalties_a": penalties_a,
                "penalties_b": penalties_b,
                "reach_penalties": 1.0,
                "advance_a_from_draw": penalties_a,
                "advance_b_from_draw": penalties_b,
            }
            if include_advancement
            else None,
            penalty_shootout=shootout if include_advancement else None,
            factors=factors,
            expected_remaining_goals_a=0.0,
            expected_remaining_goals_b=0.0,
            current_score_a=current_score_a,
            current_score_b=current_score_b,
            elapsed_minutes=elapsed_minutes,
            live_phase=phase,
            statistical_depth=compute_statistical_depth(final_dist, 0.0, 1.0, 0.0, ctx),
            live_patterns=patterns,
        )

    if phase == "extra_time":
        base_remaining_a, base_remaining_b = extra_time_expected_goals(base_mu_a, base_mu_b, state_a=state_a, state_b=state_b)
        remaining_fraction = 1.0 if elapsed_minutes is None else clamp((120.0 - elapsed_minutes) / 30.0, 0.0, 1.0)
        progress = 1.0 if elapsed_minutes is None else clamp((elapsed_minutes - 90.0) / 30.0, 0.0, 1.0)
        rem_mu_a, rem_mu_b = live_game_state_adjustment(
            base_remaining_a * remaining_fraction,
            base_remaining_b * remaining_fraction,
            current_score_a,
            current_score_b,
            progress,
            "extra_time",
        )
        rem_mu_a, rem_mu_b = live_stats_adjustment(
            base_mu_a + base_mu_b,
            rem_mu_a,
            rem_mu_b,
            progress,
            "extra_time",
            live_stats=live_stats,
        )
        patterns = detect_live_play_patterns(
            live_stats,
            progress,
            phase,
            current_score_a,
            current_score_b,
        )
        rem_mu_a, rem_mu_b = apply_live_pattern_adjustment(rem_mu_a, rem_mu_b, patterns, "extra_time")
        remainder_dist = score_distribution(rem_mu_a, rem_mu_b, max_goals=4)
        final_dist = combine_current_score_distribution(current_score_a, current_score_b, remainder_dist)
        win_a = 0.0
        draw = 0.0
        win_b = 0.0
        exact = []
        for (goals_a, goals_b), prob in final_dist.items():
            exact.append((f"{goals_a}-{goals_b}", prob))
            if goals_a > goals_b:
                win_a += prob
            elif goals_b > goals_a:
                win_b += prob
            else:
                draw += prob
        exact.sort(key=lambda item: item[1], reverse=True)
        penalties_a = penalties_probability(
            team_a,
            team_b,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
        )
        penalties_b = 1.0 - penalties_a
        advance_a = win_a + draw * penalties_a if include_advancement else None
        advance_b = win_b + draw * penalties_b if include_advancement else None
        shootout = penalty_shootout_summary(
            team_a,
            team_b,
            ctx,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
            iterations=1600,
        ) if include_advancement else None
        factors = factor_breakdown(team_a, team_b, ctx, state_a=state_a, state_b=state_b) if show_factors else None
        return MatchPrediction(
            team_a=team_a_name,
            team_b=team_b_name,
            expected_goals_a=current_score_a + rem_mu_a,
            expected_goals_b=current_score_b + rem_mu_b,
            win_a=win_a,
            draw=draw,
            win_b=win_b,
            exact_scores=exact[:top_scores],
            advance_a=advance_a,
            advance_b=advance_b,
            knockout_detail={
                "et_xg_a": rem_mu_a,
                "et_xg_b": rem_mu_b,
                "et_win_a": win_a,
                "et_draw": draw,
                "et_win_b": win_b,
                "penalties_a": penalties_a,
                "penalties_b": penalties_b,
                "reach_penalties": draw,
                "advance_a_from_draw": penalties_a,
                "advance_b_from_draw": penalties_b,
            }
            if include_advancement
            else None,
            penalty_shootout=shootout,
            factors=factors,
            expected_remaining_goals_a=rem_mu_a,
            expected_remaining_goals_b=rem_mu_b,
            current_score_a=current_score_a,
            current_score_b=current_score_b,
            elapsed_minutes=elapsed_minutes,
            live_phase=phase,
            statistical_depth=compute_statistical_depth(final_dist, win_a, draw, win_b, ctx),
            live_patterns=patterns,
        )

    remaining_fraction = 1.0 if elapsed_minutes is None else clamp((90.0 - elapsed_minutes) / 90.0, 0.0, 1.0)
    progress = 0.0 if elapsed_minutes is None else clamp(elapsed_minutes / 90.0, 0.0, 1.0)
    rem_mu_a, rem_mu_b = live_game_state_adjustment(
        base_mu_a * remaining_fraction,
        base_mu_b * remaining_fraction,
        current_score_a,
        current_score_b,
        progress,
        "regulation",
    )
    rem_mu_a, rem_mu_b = live_stats_adjustment(
        base_mu_a + base_mu_b,
        rem_mu_a,
        rem_mu_b,
        progress,
        "regulation",
        live_stats=live_stats,
    )
    patterns = detect_live_play_patterns(
        live_stats,
        progress,
        phase,
        current_score_a,
        current_score_b,
    )
    rem_mu_a, rem_mu_b = apply_live_pattern_adjustment(rem_mu_a, rem_mu_b, patterns, "regulation")
    remainder_dist = score_distribution(rem_mu_a, rem_mu_b, max_goals=6)
    final_dist = combine_current_score_distribution(current_score_a, current_score_b, remainder_dist)

    win_a = 0.0
    draw = 0.0
    win_b = 0.0
    exact = []
    for (goals_a, goals_b), prob in final_dist.items():
        exact.append((f"{goals_a}-{goals_b}", prob))
        if goals_a > goals_b:
            win_a += prob
        elif goals_b > goals_a:
            win_b += prob
        else:
            draw += prob
    exact.sort(key=lambda item: item[1], reverse=True)

    advance_a = None
    advance_b = None
    knockout_detail = None
    penalty_shootout = None
    if include_advancement:
        knockout_detail = knockout_resolution_detail(
            team_a,
            team_b,
            ctx,
            base_mu_a,
            base_mu_b,
            state_a=state_a,
            state_b=state_b,
        )
        advance_a = win_a + draw * knockout_detail["advance_a_from_draw"]
        advance_b = win_b + draw * knockout_detail["advance_b_from_draw"]
        penalty_shootout = penalty_shootout_summary(
            team_a,
            team_b,
            ctx,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
            iterations=1600,
        )
    factors = factor_breakdown(team_a, team_b, ctx, state_a=state_a, state_b=state_b) if show_factors else None

    return MatchPrediction(
        team_a=team_a_name,
        team_b=team_b_name,
        expected_goals_a=current_score_a + rem_mu_a,
        expected_goals_b=current_score_b + rem_mu_b,
        win_a=win_a,
        draw=draw,
        win_b=win_b,
        exact_scores=exact[:top_scores],
        advance_a=advance_a,
        advance_b=advance_b,
        knockout_detail=knockout_detail,
        penalty_shootout=penalty_shootout,
        factors=factors,
        expected_remaining_goals_a=rem_mu_a,
        expected_remaining_goals_b=rem_mu_b,
        current_score_a=current_score_a,
        current_score_b=current_score_b,
        elapsed_minutes=elapsed_minutes,
        live_phase="regulation",
        statistical_depth=compute_statistical_depth(final_dist, win_a, draw, win_b, ctx),
        live_patterns=patterns,
    )


def monte_carlo_match_summary(
    teams: Dict[str, Team],
    team_a_name: str,
    team_b_name: str,
    ctx: MatchContext,
    iterations: int,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> dict:
    team_a = teams[team_a_name]
    team_b = teams[team_b_name]
    penalties_state_a = dict(state_a or {})
    penalties_state_b = dict(state_b or {})
    penalties_state_a["morale"] = ctx.morale_a
    penalties_state_b["morale"] = ctx.morale_b
    mu_a, mu_b = expected_goals(team_a, team_b, ctx, state_a=state_a, state_b=state_b)
    counts: Dict[Tuple[int, int], int] = {}
    win_a = 0
    draw = 0
    win_b = 0
    advance_a = 0
    advance_b = 0
    total_goals_a = 0
    total_goals_b = 0
    extra_time_count = 0
    penalties_count = 0

    for _ in range(iterations):
        goals_a, goals_b = sample_score(mu_a, mu_b)
        if goals_a > goals_b:
            counts[(goals_a, goals_b)] = counts.get((goals_a, goals_b), 0) + 1
            total_goals_a += goals_a
            total_goals_b += goals_b
            win_a += 1
            advance_a += 1
        elif goals_b > goals_a:
            counts[(goals_a, goals_b)] = counts.get((goals_a, goals_b), 0) + 1
            total_goals_a += goals_a
            total_goals_b += goals_b
            win_b += 1
            advance_b += 1
        else:
            draw += 1
            if ctx.knockout:
                resolution = sample_knockout_resolution(
                    team_a,
                    team_b,
                    ctx,
                    goals_a,
                    goals_b,
                    mu_a,
                    mu_b,
                    state_a=penalties_state_a,
                    state_b=penalties_state_b,
                )
                counts[(resolution["score_a"], resolution["score_b"])] = counts.get((resolution["score_a"], resolution["score_b"]), 0) + 1
                total_goals_a += resolution["score_a"]
                total_goals_b += resolution["score_b"]
                extra_time_count += 1 if resolution["went_extra_time"] else 0
                penalties_count += 1 if resolution["went_penalties"] else 0
                if resolution["winner"] == team_a_name:
                    advance_a += 1
                else:
                    advance_b += 1
            else:
                counts[(goals_a, goals_b)] = counts.get((goals_a, goals_b), 0) + 1
                total_goals_a += goals_a
                total_goals_b += goals_b

    top_scores = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:6]
    return {
        "iterations": iterations,
        "win_a": win_a / float(iterations),
        "draw": draw / float(iterations),
        "win_b": win_b / float(iterations),
        "advance_a": advance_a / float(iterations) if ctx.knockout else None,
        "advance_b": advance_b / float(iterations) if ctx.knockout else None,
        "avg_goals_a": total_goals_a / float(iterations),
        "avg_goals_b": total_goals_b / float(iterations),
        "extra_time_rate": extra_time_count / float(iterations) if ctx.knockout else None,
        "penalties_rate": penalties_count / float(iterations) if ctx.knockout else None,
        "top_scores": [(f"{score[0]}-{score[1]}", count / float(iterations)) for score, count in top_scores],
    }


def pretty_status(status: str) -> str:
    return {
        "qualified": "Clasificado",
        "uefa_playoff": "Repechaje UEFA",
        "fifa_playoff": "Repechaje FIFA",
    }[status]


def confirmed_teams(teams: Dict[str, Team]) -> List[Team]:
    return [team for team in teams.values() if team.status == "qualified"]


def average_opponent_metrics(team: Team, opponents: Sequence[Team]) -> Tuple[float, float, float]:
    xgf = 0.0
    xga = 0.0
    xpts = 0.0
    count = 0
    for opponent in opponents:
        if opponent.name == team.name:
            continue
        prediction = predict_match(
            {team.name: team, opponent.name: opponent},
            team.name,
            opponent.name,
            MatchContext(),
            top_scores=0,
        )
        xgf += prediction.expected_goals_a
        xga += prediction.expected_goals_b
        xpts += 3.0 * prediction.win_a + prediction.draw
        count += 1
    if count == 0:
        return 0.0, 0.0, 0.0
    return xgf / count, xga / count, xpts / count


def uefa_playoff_probabilities(teams: Dict[str, Team]) -> Dict[str, float]:
    probabilities = {name: 0.0 for name in teams}
    paths = [
        {
            "semi_1": ("Italy", "Northern Ireland"),
            "semi_2": ("Wales", "Bosnia and Herzegovina"),
            "final_host": "semi_2",
        },
        {
            "semi_1": ("Ukraine", "Sweden"),
            "semi_2": ("Poland", "Albania"),
            "final_host": "semi_1",
        },
        {
            "semi_1": ("Turkey", "Romania"),
            "semi_2": ("Slovakia", "Kosovo"),
            "final_host": "semi_2",
        },
        {
            "semi_1": ("Denmark", "North Macedonia"),
            "semi_2": ("Czech Republic", "Republic of Ireland"),
            "final_host": "semi_2",
        },
    ]

    for path in paths:
        semi_1 = predict_match(
            teams,
            path["semi_1"][0],
            path["semi_1"][1],
            MatchContext(neutral=False, home_team=path["semi_1"][0], knockout=True),
            include_advancement=True,
        )
        semi_2 = predict_match(
            teams,
            path["semi_2"][0],
            path["semi_2"][1],
            MatchContext(neutral=False, home_team=path["semi_2"][0], knockout=True),
            include_advancement=True,
        )

        semi_1_adv = {
            path["semi_1"][0]: semi_1.advance_a or 0.0,
            path["semi_1"][1]: semi_1.advance_b or 0.0,
        }
        semi_2_adv = {
            path["semi_2"][0]: semi_2.advance_a or 0.0,
            path["semi_2"][1]: semi_2.advance_b or 0.0,
        }

        for finalist_1, finalist_1_prob in semi_1_adv.items():
            for finalist_2, finalist_2_prob in semi_2_adv.items():
                if finalist_1_prob == 0.0 or finalist_2_prob == 0.0:
                    continue
                final_host = finalist_1 if path["final_host"] == "semi_1" else finalist_2
                ctx = MatchContext(neutral=False, home_team=final_host, knockout=True)
                final_prediction = predict_match(
                    teams,
                    finalist_1,
                    finalist_2,
                    ctx,
                    include_advancement=True,
                )
                probabilities[finalist_1] += finalist_1_prob * finalist_2_prob * (final_prediction.advance_a or 0.0)
                probabilities[finalist_2] += finalist_1_prob * finalist_2_prob * (final_prediction.advance_b or 0.0)

    return probabilities


def fifa_playoff_probabilities(teams: Dict[str, Team]) -> Dict[str, float]:
    probabilities = {name: 0.0 for name in teams}

    path_1_semi = predict_match(
        teams,
        "Jamaica",
        "New Caledonia",
        MatchContext(neutral=True, venue_country="Mexico", knockout=True),
        include_advancement=True,
    )
    path_2_semi = predict_match(
        teams,
        "Bolivia",
        "Suriname",
        MatchContext(neutral=True, venue_country="Mexico", knockout=True),
        include_advancement=True,
    )

    path_1_adv = {
        "Jamaica": path_1_semi.advance_a or 0.0,
        "New Caledonia": path_1_semi.advance_b or 0.0,
    }
    path_2_adv = {
        "Bolivia": path_2_semi.advance_a or 0.0,
        "Suriname": path_2_semi.advance_b or 0.0,
    }

    for finalist, finalist_prob in path_1_adv.items():
        final_prediction = predict_match(
            teams,
            "Dem. Rep. of Congo",
            finalist,
            MatchContext(neutral=True, venue_country="Mexico", knockout=True),
            include_advancement=True,
        )
        probabilities["Dem. Rep. of Congo"] += finalist_prob * (final_prediction.advance_a or 0.0)
        probabilities[finalist] += finalist_prob * (final_prediction.advance_b or 0.0)

    for finalist, finalist_prob in path_2_adv.items():
        final_prediction = predict_match(
            teams,
            "Iraq",
            finalist,
            MatchContext(neutral=True, venue_country="Mexico", knockout=True),
            include_advancement=True,
        )
        probabilities["Iraq"] += finalist_prob * (final_prediction.advance_a or 0.0)
        probabilities[finalist] += finalist_prob * (final_prediction.advance_b or 0.0)

    return probabilities


def qualification_probabilities(teams: Dict[str, Team]) -> Dict[str, float]:
    probabilities = {}
    uefa_probs = uefa_playoff_probabilities(teams)
    fifa_probs = fifa_playoff_probabilities(teams)
    for team in teams.values():
        if team.status == "qualified":
            probabilities[team.name] = 1.0
        elif team.status == "uefa_playoff":
            probabilities[team.name] = uefa_probs.get(team.name, 0.0)
        elif team.status == "fifa_playoff":
            probabilities[team.name] = fifa_probs.get(team.name, 0.0)
        else:
            probabilities[team.name] = 0.0
    return probabilities


def sample_score(mu_a: float, mu_b: float) -> Tuple[int, int]:
    lambda3 = min(0.08, mu_a * 0.18, mu_b * 0.18)
    shared = poisson_sample(lambda3)
    goals_a = poisson_sample(max(mu_a - lambda3, 0.001)) + shared
    goals_b = poisson_sample(max(mu_b - lambda3, 0.001)) + shared
    return goals_a, goals_b


def sample_knockout_winner(teams: Dict[str, Team], team_a: str, team_b: str, ctx: MatchContext) -> str:
    mu_a, mu_b = expected_goals(teams[team_a], teams[team_b], ctx)
    goals_a, goals_b = sample_score(mu_a, mu_b)
    return sample_knockout_resolution(
        teams[team_a],
        teams[team_b],
        ctx,
        goals_a,
        goals_b,
        mu_a,
        mu_b,
    )["winner"]


def simulate_playoffs(teams: Dict[str, Team], iterations: int) -> Dict[str, float]:
    counts = {name: 0 for name in teams}
    for _ in range(iterations):
        semi_a_1 = sample_knockout_winner(
            teams, "Italy", "Northern Ireland", MatchContext(neutral=False, home_team="Italy", knockout=True)
        )
        semi_a_2 = sample_knockout_winner(
            teams, "Wales", "Bosnia and Herzegovina", MatchContext(neutral=False, home_team="Wales", knockout=True)
        )
        counts[
            sample_knockout_winner(
                teams, semi_a_1, semi_a_2, MatchContext(neutral=False, home_team=semi_a_2, knockout=True)
            )
        ] += 1

        semi_b_1 = sample_knockout_winner(
            teams, "Ukraine", "Sweden", MatchContext(neutral=False, home_team="Ukraine", knockout=True)
        )
        semi_b_2 = sample_knockout_winner(
            teams, "Poland", "Albania", MatchContext(neutral=False, home_team="Poland", knockout=True)
        )
        counts[
            sample_knockout_winner(
                teams, semi_b_1, semi_b_2, MatchContext(neutral=False, home_team=semi_b_1, knockout=True)
            )
        ] += 1

        semi_c_1 = sample_knockout_winner(
            teams, "Turkey", "Romania", MatchContext(neutral=False, home_team="Turkey", knockout=True)
        )
        semi_c_2 = sample_knockout_winner(
            teams, "Slovakia", "Kosovo", MatchContext(neutral=False, home_team="Slovakia", knockout=True)
        )
        counts[
            sample_knockout_winner(
                teams, semi_c_1, semi_c_2, MatchContext(neutral=False, home_team=semi_c_2, knockout=True)
            )
        ] += 1

        semi_d_1 = sample_knockout_winner(
            teams, "Denmark", "North Macedonia", MatchContext(neutral=False, home_team="Denmark", knockout=True)
        )
        semi_d_2 = sample_knockout_winner(
            teams,
            "Czech Republic",
            "Republic of Ireland",
            MatchContext(neutral=False, home_team="Czech Republic", knockout=True),
        )
        counts[
            sample_knockout_winner(
                teams, semi_d_1, semi_d_2, MatchContext(neutral=False, home_team=semi_d_2, knockout=True)
            )
        ] += 1

        fifa_1 = sample_knockout_winner(
            teams, "Jamaica", "New Caledonia", MatchContext(neutral=True, venue_country="Mexico", knockout=True)
        )
        counts[
            sample_knockout_winner(
                teams,
                "Dem. Rep. of Congo",
                fifa_1,
                MatchContext(neutral=True, venue_country="Mexico", knockout=True),
            )
        ] += 1

        fifa_2 = sample_knockout_winner(
            teams, "Bolivia", "Suriname", MatchContext(neutral=True, venue_country="Mexico", knockout=True)
        )
        counts[
            sample_knockout_winner(
                teams, "Iraq", fifa_2, MatchContext(neutral=True, venue_country="Mexico", knockout=True)
            )
        ] += 1

    return {name: count / float(iterations) for name, count in counts.items()}


def load_tournament_config(path: Path) -> dict:
    return json.loads(path.read_text())


def sample_uefa_path_winner(
    teams: Dict[str, Team],
    semi_1: Tuple[str, str],
    semi_2: Tuple[str, str],
    final_host_path: str,
) -> str:
    finalist_1 = sample_knockout_winner(
        teams,
        semi_1[0],
        semi_1[1],
        MatchContext(neutral=False, home_team=semi_1[0], knockout=True, importance=1.2),
    )
    finalist_2 = sample_knockout_winner(
        teams,
        semi_2[0],
        semi_2[1],
        MatchContext(neutral=False, home_team=semi_2[0], knockout=True, importance=1.2),
    )
    final_host = finalist_1 if final_host_path == "semi_1" else finalist_2
    return sample_knockout_winner(
        teams,
        finalist_1,
        finalist_2,
        MatchContext(neutral=False, home_team=final_host, knockout=True, importance=1.25),
    )


def sample_playoff_placeholders(teams: Dict[str, Team]) -> Dict[str, str]:
    return {
        "UEFA_A": sample_uefa_path_winner(
            teams,
            ("Italy", "Northern Ireland"),
            ("Wales", "Bosnia and Herzegovina"),
            "semi_2",
        ),
        "UEFA_B": sample_uefa_path_winner(
            teams,
            ("Ukraine", "Sweden"),
            ("Poland", "Albania"),
            "semi_1",
        ),
        "UEFA_C": sample_uefa_path_winner(
            teams,
            ("Turkey", "Romania"),
            ("Slovakia", "Kosovo"),
            "semi_2",
        ),
        "UEFA_D": sample_uefa_path_winner(
            teams,
            ("Denmark", "North Macedonia"),
            ("Czech Republic", "Republic of Ireland"),
            "semi_2",
        ),
        "FIFA_1": sample_knockout_winner(
            teams,
            "Dem. Rep. of Congo",
            sample_knockout_winner(
                teams,
                "Jamaica",
                "New Caledonia",
                MatchContext(neutral=True, venue_country="Mexico", knockout=True, importance=1.2),
            ),
            MatchContext(neutral=True, venue_country="Mexico", knockout=True, importance=1.25),
        ),
        "FIFA_2": sample_knockout_winner(
            teams,
            "Iraq",
            sample_knockout_winner(
                teams,
                "Bolivia",
                "Suriname",
                MatchContext(neutral=True, venue_country="Mexico", knockout=True, importance=1.2),
            ),
            MatchContext(neutral=True, venue_country="Mexico", knockout=True, importance=1.25),
        ),
    }


def resolve_group_entry(entry: object, placeholders: Dict[str, str]) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and "placeholder" in entry:
        placeholder = entry["placeholder"]
        if placeholder not in placeholders:
            raise SystemExit(f"Placeholder no reconocido: {placeholder}")
        return placeholders[placeholder]
    raise SystemExit(f"Entrada de grupo no soportada: {entry}")


def resolve_groups_for_iteration(config: dict, placeholders: Dict[str, str]) -> Dict[str, List[str]]:
    groups = {}
    for group_name, entries in config["groups"].items():
        groups[group_name] = [resolve_group_entry(entry, placeholders) for entry in entries]
    return groups


def initial_simulation_states(payload: Optional[dict] = None) -> Dict[str, dict]:
    if not payload:
        return {}
    return copy_states(payload)


def ensure_state(states: Dict[str, dict], team_name: str) -> dict:
    if team_name not in states:
        states[team_name] = default_team_state()
    else:
        states[team_name] = normalize_team_state(states[team_name])
    return states[team_name]


def sample_cards(
    teams: Dict[str, Team],
    team_a: str,
    team_b: str,
    importance: float,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> Tuple[int, int, int, int]:
    profile_a = profile_for(teams[team_a])
    profile_b = profile_for(teams[team_b])
    rivalry = rivalry_intensity(teams[team_a], teams[team_b])

    yellow_lambda_a = clamp(
        0.75 + 7.0 * profile_a.squad.yellow_rate + 0.35 * importance + 0.60 * rivalry
        - 0.50 * profile_a.squad.discipline_index
        + 0.55 * fatigue_level(state_a)
        - 0.35 * discipline_trend(state_a),
        0.25,
        4.80,
    )
    yellow_lambda_b = clamp(
        0.75 + 7.0 * profile_b.squad.yellow_rate + 0.35 * importance + 0.60 * rivalry
        - 0.50 * profile_b.squad.discipline_index
        + 0.55 * fatigue_level(state_b)
        - 0.35 * discipline_trend(state_b),
        0.25,
        4.80,
    )
    red_prob_a = clamp(
        0.012 + 1.8 * profile_a.squad.red_rate + 0.028 * importance + 0.04 * rivalry
        - 0.02 * profile_a.squad.discipline_index
        + 0.025 * fatigue_level(state_a)
        - 0.018 * discipline_trend(state_a),
        0.003,
        0.20,
    )
    red_prob_b = clamp(
        0.012 + 1.8 * profile_b.squad.red_rate + 0.028 * importance + 0.04 * rivalry
        - 0.02 * profile_b.squad.discipline_index
        + 0.025 * fatigue_level(state_b)
        - 0.018 * discipline_trend(state_b),
        0.003,
        0.20,
    )

    yellows_a = poisson_sample(yellow_lambda_a)
    yellows_b = poisson_sample(yellow_lambda_b)
    reds_a = 1 if random.random() < red_prob_a else 0
    reds_b = 1 if random.random() < red_prob_b else 0
    return yellows_a, reds_a, yellows_b, reds_b


def penalties_probability(team_a: Team, team_b: Team, state_a: dict, state_b: dict) -> float:
    profile_a = profile_for(team_a)
    profile_b = profile_for(team_b)
    edge = 0.80 * (profile_a.squad.goalkeeper_unit - profile_b.squad.goalkeeper_unit)
    edge += 0.40 * (profile_a.coach_index - profile_b.coach_index)
    edge += 0.20 * (profile_a.heritage_index - profile_b.heritage_index)
    edge += 0.15 * (profile_a.squad.player_experience - profile_b.squad.player_experience)
    edge += 0.15 * (state_a["morale"] - state_b["morale"])
    edge += 0.12 * (recent_form_signal(state_a) - recent_form_signal(state_b))
    edge -= 0.08 * (fatigue_level(state_a) - fatigue_level(state_b))
    return logistic(edge)


def penalty_conversion_probability(
    taker: Team,
    keeper_team: Team,
    ctx: MatchContext,
    taker_state: dict,
    keeper_state: dict,
    *,
    taker_first: bool,
    sudden_death: bool,
    trailing: bool,
    round_number: int,
) -> float:
    taker_profile = profile_for(taker)
    keeper_profile = profile_for(keeper_team)
    rate = 0.74
    rate += 0.16 * centered(taker_profile.squad.finishing)
    rate += 0.05 * centered(taker_profile.squad.shot_creation)
    rate += 0.04 * centered(taker_profile.squad.player_experience)
    rate += 0.03 * centered(taker_profile.coach_index)
    rate += 0.03 * centered(taker_profile.heritage_index)
    rate += 0.05 * clamp(float(taker_state.get("morale", 0.0)), -1.0, 1.0)
    rate += 0.03 * recent_form_signal(taker_state)
    rate -= 0.06 * fatigue_level(taker_state)
    rate -= 0.06 * (1.0 - availability_level(taker_state))
    rate -= 0.10 * centered(keeper_profile.squad.goalkeeper_unit)
    rate -= 0.03 * centered(keeper_profile.coach_index)
    rate -= 0.05 * clamp(ctx.weather_stress, 0.0, 1.0)
    if taker_first:
        rate += 0.008
    if trailing:
        rate -= 0.020
    if sudden_death:
        rate -= 0.010
    if round_number >= 4:
        rate -= 0.012 * (round_number - 3)
    return clamp(rate, 0.46, 0.92)


def simulate_penalty_shootout(
    team_a: Team,
    team_b: Team,
    ctx: MatchContext,
    state_a: dict,
    state_b: dict,
    *,
    a_starts: bool,
) -> dict:
    score_a = 0
    score_b = 0
    kicks_a = 0
    kicks_b = 0
    regulation_rounds = 5

    for round_number in range(1, regulation_rounds + 1):
        order = ("A", "B") if a_starts else ("B", "A")
        for shooter in order:
            sudden_death = False
            if shooter == "A":
                trailing = score_a < score_b
                prob = penalty_conversion_probability(
                    team_a,
                    team_b,
                    ctx,
                    state_a,
                    state_b,
                    taker_first=a_starts,
                    sudden_death=sudden_death,
                    trailing=trailing,
                    round_number=round_number,
                )
                kicks_a += 1
                if random.random() < prob:
                    score_a += 1
            else:
                trailing = score_b < score_a
                prob = penalty_conversion_probability(
                    team_b,
                    team_a,
                    ctx,
                    state_b,
                    state_a,
                    taker_first=not a_starts,
                    sudden_death=sudden_death,
                    trailing=trailing,
                    round_number=round_number,
                )
                kicks_b += 1
                if random.random() < prob:
                    score_b += 1

            remaining_a = regulation_rounds - kicks_a
            remaining_b = regulation_rounds - kicks_b
            if score_a > score_b + remaining_b:
                return {"winner": team_a.name, "score_a": score_a, "score_b": score_b, "a_starts": a_starts}
            if score_b > score_a + remaining_a:
                return {"winner": team_b.name, "score_a": score_a, "score_b": score_b, "a_starts": a_starts}

    sudden_round = 0
    while score_a == score_b and sudden_round < 12:
        sudden_round += 1
        order = ("A", "B") if a_starts else ("B", "A")
        round_scored_a = False
        round_scored_b = False
        for shooter in order:
            if shooter == "A":
                prob = penalty_conversion_probability(
                    team_a,
                    team_b,
                    ctx,
                    state_a,
                    state_b,
                    taker_first=a_starts,
                    sudden_death=True,
                    trailing=score_a < score_b,
                    round_number=regulation_rounds + sudden_round,
                )
                if random.random() < prob:
                    score_a += 1
                    round_scored_a = True
            else:
                prob = penalty_conversion_probability(
                    team_b,
                    team_a,
                    ctx,
                    state_b,
                    state_a,
                    taker_first=not a_starts,
                    sudden_death=True,
                    trailing=score_b < score_a,
                    round_number=regulation_rounds + sudden_round,
                )
                if random.random() < prob:
                    score_b += 1
                    round_scored_b = True
        if round_scored_a != round_scored_b:
            break

    if score_a == score_b:
        winner = team_a.name if random.random() < penalties_probability(team_a, team_b, state_a, state_b) else team_b.name
        if winner == team_a.name:
            score_a += 1
        else:
            score_b += 1
    else:
        winner = team_a.name if score_a > score_b else team_b.name

    return {"winner": winner, "score_a": score_a, "score_b": score_b, "a_starts": a_starts}


def penalty_shootout_summary(
    team_a: Team,
    team_b: Team,
    ctx: MatchContext,
    state_a: dict,
    state_b: dict,
    iterations: int = 2400,
) -> dict:
    counts: Dict[Tuple[int, int], int] = {}
    wins_a = 0
    wins_b = 0
    total_a = 0
    total_b = 0
    starts_a = 0
    for index in range(iterations):
        a_starts = index % 2 == 0
        starts_a += 1 if a_starts else 0
        result = simulate_penalty_shootout(team_a, team_b, ctx, state_a, state_b, a_starts=a_starts)
        counts[(result["score_a"], result["score_b"])] = counts.get((result["score_a"], result["score_b"]), 0) + 1
        total_a += result["score_a"]
        total_b += result["score_b"]
        if result["winner"] == team_a.name:
            wins_a += 1
        else:
            wins_b += 1
    top_scores = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
    return {
        "iterations": iterations,
        "win_a": wins_a / float(iterations),
        "win_b": wins_b / float(iterations),
        "avg_score_a": total_a / float(iterations),
        "avg_score_b": total_b / float(iterations),
        "a_starts_rate": starts_a / float(iterations),
        "top_scores": [(f"{score[0]}-{score[1]}", count / float(iterations)) for score, count in top_scores],
    }


def build_simulation_context(
    teams: Dict[str, Team],
    states: Dict[str, dict],
    team_a: str,
    team_b: str,
    stage: str,
    group_name: Optional[str] = None,
) -> MatchContext:
    state_a = ensure_state(states, team_a)
    state_b = ensure_state(states, team_b)

    neutral = True
    home_team = None
    venue_country = None
    if stage == "group":
        if teams[team_a].is_host:
            neutral = False
            home_team = team_a
            venue_country = teams[team_a].host_country
        elif teams[team_b].is_host:
            neutral = False
            home_team = team_b
            venue_country = teams[team_b].host_country
    else:
        if teams[team_a].is_host:
            venue_country = teams[team_a].host_country
        elif teams[team_b].is_host:
            venue_country = teams[team_b].host_country

    return MatchContext(
        neutral=neutral,
        home_team=home_team,
        venue_country=venue_country,
        rest_days_a=4 if stage == "group" else 5,
        rest_days_b=4 if stage == "group" else 5,
        injuries_a=dynamic_injury_load(teams[team_a], state_a),
        injuries_b=dynamic_injury_load(teams[team_b], state_b),
        altitude_m=1500 if venue_country == "Mexico" and stage == "group" else 0,
        travel_km_a=0.0 if teams[team_a].is_host else 3500.0,
        travel_km_b=0.0 if teams[team_b].is_host else 3500.0,
        knockout=stage != "group",
        morale_a=state_a["morale"],
        morale_b=state_b["morale"],
        yellow_cards_a=predictive_yellow_cards(state_a),
        yellow_cards_b=predictive_yellow_cards(state_b),
        red_suspensions_a=int(state_a["red_suspensions"]),
        red_suspensions_b=int(state_b["red_suspensions"]),
        group=group_name,
        group_points_a=int(state_a["group_points"]),
        group_points_b=int(state_b["group_points"]),
        group_goal_diff_a=int(state_a["group_goal_diff"]),
        group_goal_diff_b=int(state_b["group_goal_diff"]),
        group_matches_played_a=int(state_a["group_matches_played"]),
        group_matches_played_b=int(state_b["group_matches_played"]),
        weather_stress=random.uniform(0.02, 0.12),
        importance=STAGE_IMPORTANCE[stage],
    )


def update_simulation_state(
    teams: Dict[str, Team],
    states: Dict[str, dict],
    team_a: str,
    team_b: str,
    ctx: MatchContext,
    expected_goals_a: float,
    expected_goals_b: float,
    score_a: int,
    score_b: int,
    yellows_a: int,
    reds_a: int,
    yellows_b: int,
    reds_b: int,
    stage: str,
    winner: Optional[str] = None,
    went_extra_time: bool = False,
    went_penalties: bool = False,
    live_stats: Optional[Dict[str, float]] = None,
) -> None:
    state_a = ensure_state(states, team_a)
    state_b = ensure_state(states, team_b)
    effective_elo_a = effective_elo(teams[team_a], state_a)
    effective_elo_b = effective_elo(teams[team_b], state_b)
    home_edge = 0.0
    if not ctx.neutral and ctx.home_team == team_a:
        home_edge = 55.0
    elif not ctx.neutral and ctx.home_team == team_b:
        home_edge = -55.0

    expected_result_a = 1.0 / (1.0 + 10.0 ** (-((effective_elo_a - effective_elo_b + home_edge) / 400.0)))
    expected_result_b = 1.0 - expected_result_a
    knockout = stage != "group"

    if score_a > score_b:
        actual_result_a = 1.0
        actual_result_b = 0.0
    elif score_b > score_a:
        actual_result_a = 0.0
        actual_result_b = 1.0
    elif knockout and winner:
        actual_result_a = 0.75 if winner == team_a else 0.25
        actual_result_b = 1.0 - actual_result_a
    else:
        actual_result_a = 0.5
        actual_result_b = 0.5

    margin_multiplier = 1.0 + 0.18 * clamp(abs(score_a - score_b), 0, 3)
    rating_k = clamp(22.0 + 12.0 * (ctx.importance - 1.0), 18.0, 34.0)
    elo_delta_a = rating_k * margin_multiplier * (actual_result_a - expected_result_a)
    elo_delta_b = -elo_delta_a
    state_a["elo_shift"] = clamp(state_a["elo_shift"] + elo_delta_a, -220.0, 220.0)
    state_b["elo_shift"] = clamp(state_b["elo_shift"] + elo_delta_b, -220.0, 220.0)

    for state, team_name, score_for, score_against, expected_for, expected_against, actual_result, expected_result, yellows, reds, rest_days, travel_km, injuries in (
        (
            state_a,
            team_a,
            score_a,
            score_b,
            expected_goals_a,
            expected_goals_b,
            actual_result_a,
            expected_result_a,
            yellows_a,
            reds_a,
            ctx.rest_days_a,
            ctx.travel_km_a,
            ctx.injuries_a,
        ),
        (
            state_b,
            team_b,
            score_b,
            score_a,
            expected_goals_b,
            expected_goals_a,
            actual_result_b,
            expected_result_b,
            yellows_b,
            reds_b,
            ctx.rest_days_b,
            ctx.travel_km_b,
            ctx.injuries_b,
        ),
    ):
        team_profile = profile_for(teams[team_name])
        attack_signal = clamp((score_for - expected_for) / 1.8, -1.0, 1.0)
        defense_signal = clamp((expected_against - score_against) / 1.8, -1.0, 1.0)
        result_signal = clamp(2.0 * (actual_result - expected_result), -1.0, 1.0)
        form_signal = clamp(0.48 * result_signal + 0.30 * attack_signal + 0.22 * defense_signal, -1.0, 1.0)

        state["recent_form"] = clamp(0.60 * state["recent_form"] + 0.40 * form_signal, -1.0, 1.0)
        state["attack_form"] = clamp(0.58 * state["attack_form"] + 0.42 * attack_signal, -1.0, 1.0)
        state["defense_form"] = clamp(0.58 * state["defense_form"] + 0.42 * defense_signal, -1.0, 1.0)
        morale_delta = clamp(0.08 * form_signal + 0.03 * (1 if actual_result > 0.5 else -1 if actual_result < 0.5 else 0), -0.18, 0.18)
        state["morale"] = clamp(0.72 * state["morale"] + morale_delta, -1.0, 1.0)

        fatigue_delta = (
            0.24
            + 0.06 * max(ctx.importance - 1.0, 0.0)
            + 0.05 * clamp(travel_km / 6000.0, 0.0, 2.0)
            + 0.05 * clamp(injuries, 0.0, 1.0)
            + 0.025 * (yellows + 2 * reds)
            + (0.18 if went_extra_time else 0.0)
            + (0.04 if went_penalties else 0.0)
            - 0.045 * clamp(rest_days, 2, 8)
        )
        state["fatigue"] = clamp(0.58 * state["fatigue"] + fatigue_delta, 0.0, 1.0)

        target_availability = (
            1.0
            - 0.50 * clamp(injuries, 0.0, 1.0)
            - 0.12 * reds
            - 0.03 * yellows
            - 0.10 * state["fatigue"]
            - (0.05 if went_extra_time else 0.0)
            - (0.02 if went_penalties else 0.0)
        )
        state["availability"] = clamp(0.74 * state["availability"] + 0.26 * target_availability, 0.40, 1.0)

        discipline_signal = clamp(
            0.10 * (team_profile.squad.discipline_index - 0.5) - 0.10 * yellows - 0.34 * reds,
            -1.0,
            0.4,
        )
        state["discipline_drift"] = clamp(0.68 * state["discipline_drift"] + 0.32 * discipline_signal, -1.0, 0.5)

    state_a["yellow_cards"] = clamp(state_a["yellow_cards"] + yellows_a, 0, 12)
    state_b["yellow_cards"] = clamp(state_b["yellow_cards"] + yellows_b, 0, 12)
    state_a["yellow_load"] = clamp(state_a["yellow_load"] * 0.55 + 0.45 * yellows_a + 0.70 * reds_a, 0.0, 6.0)
    state_b["yellow_load"] = clamp(state_b["yellow_load"] * 0.55 + 0.45 * yellows_b + 0.70 * reds_b, 0.0, 6.0)
    state_a["red_suspensions"] = clamp(reds_a, 0, 4)
    state_b["red_suspensions"] = clamp(reds_b, 0, 4)

    state_a["matches_played"] += 1
    state_b["matches_played"] += 1
    state_a["goals_for"] += score_a
    state_a["goals_against"] += score_b
    state_b["goals_for"] += score_b
    state_b["goals_against"] += score_a
    update_tactical_signature_state(state_a, live_signature_metrics("a", live_stats or {}))
    update_tactical_signature_state(state_b, live_signature_metrics("b", live_stats or {}))

    if stage == "group":
        state_a["group_matches_played"] += 1
        state_b["group_matches_played"] += 1
        state_a["group_goals_for"] += score_a
        state_b["group_goals_for"] += score_b
        state_a["group_goals_against"] += score_b
        state_b["group_goals_against"] += score_a
        state_a["group_goal_diff"] += score_a - score_b
        state_b["group_goal_diff"] += score_b - score_a
        if score_a > score_b:
            state_a["group_points"] += 3
        elif score_b > score_a:
            state_b["group_points"] += 3
        else:
            state_a["group_points"] += 1
            state_b["group_points"] += 1
        state_a["fair_play"] -= yellows_a + 3 * reds_a
        state_b["fair_play"] -= yellows_b + 3 * reds_b


def simulate_match_sample(
    teams: Dict[str, Team],
    states: Dict[str, dict],
    team_a: str,
    team_b: str,
    stage: str,
    group_name: Optional[str] = None,
) -> dict:
    ctx = build_simulation_context(teams, states, team_a, team_b, stage, group_name=group_name)
    state_a = ensure_state(states, team_a)
    state_b = ensure_state(states, team_b)
    mu_a, mu_b = expected_goals(teams[team_a], teams[team_b], ctx, state_a=state_a, state_b=state_b)
    score_a, score_b = sample_score(mu_a, mu_b)
    yellows_a, reds_a, yellows_b, reds_b = sample_cards(
        teams,
        team_a,
        team_b,
        ctx.importance,
        state_a=state_a,
        state_b=state_b,
    )

    winner = None
    loser = None
    went_extra_time = False
    went_penalties = False
    if stage != "group":
        resolution = sample_knockout_resolution(
            teams[team_a],
            teams[team_b],
            ctx,
            score_a,
            score_b,
            mu_a,
            mu_b,
            state_a=state_a,
            state_b=state_b,
        )
        winner = resolution["winner"]
        loser = resolution["loser"]
        score_a = resolution["score_a"]
        score_b = resolution["score_b"]
        went_extra_time = resolution["went_extra_time"]
        went_penalties = resolution["went_penalties"]

    update_simulation_state(
        teams,
        states,
        team_a,
        team_b,
        ctx,
        mu_a,
        mu_b,
        score_a,
        score_b,
        yellows_a,
        reds_a,
        yellows_b,
        reds_b,
        stage,
        winner=winner,
        went_extra_time=went_extra_time,
        went_penalties=went_penalties,
    )

    return {
        "team_a": team_a,
        "team_b": team_b,
        "score_a": score_a,
        "score_b": score_b,
        "winner": winner,
        "loser": loser,
        "went_extra_time": went_extra_time,
        "went_penalties": went_penalties,
    }


def standings_entry(teams: Dict[str, Team], states: Dict[str, dict], group_name: str, team_name: str) -> dict:
    state = ensure_state(states, team_name)
    return {
        "team": team_name,
        "group": group_name,
        "points": state["group_points"],
        "goal_diff": state["group_goal_diff"],
        "goals_for": state["group_goals_for"],
        "fair_play": state["fair_play"],
        "elo": teams[team_name].elo,
    }


def sort_standings(entries: Sequence[dict]) -> List[dict]:
    return sorted(
        entries,
        key=lambda entry: (
            entry["points"],
            entry["goal_diff"],
            entry["goals_for"],
            entry["fair_play"],
            entry["elo"],
        ),
        reverse=True,
    )


def simulate_group_stage(
    teams: Dict[str, Team],
    groups: Dict[str, List[str]],
    states: Dict[str, dict],
) -> Dict[str, List[dict]]:
    standings = {}
    for group_name, group_teams in groups.items():
        for team_name in group_teams:
            ensure_state(states, team_name)
        for index_a, index_b in GROUP_MATCH_PAIRS:
            team_a = group_teams[index_a]
            team_b = group_teams[index_b]
            simulate_match_sample(teams, states, team_a, team_b, "group", group_name=group_name)
        entries = [standings_entry(teams, states, group_name, team_name) for team_name in group_teams]
        standings[group_name] = sort_standings(entries)
    return standings


def assign_third_place_slots(
    standings: Dict[str, List[dict]],
    winner_ranks: Dict[str, int],
) -> Tuple[List[dict], Dict[str, str]]:
    third_place_entries = sort_standings([table[2] for table in standings.values()])[:8]
    for rank, entry in enumerate(third_place_entries, start=1):
        entry["third_rank"] = rank

    third_slot_matches = [match for match in R32_MATCHES if match["team_b"]["type"] == "third_place"]
    ordered_slots = sorted(
        third_slot_matches,
        key=lambda match: (
            len(match["team_b"]["allowed_groups"]),
            winner_ranks[match["team_a"]["group"]],
            match["id"],
        ),
    )

    best_assignment: Dict[str, str] = {}
    best_score = -1.0

    def backtrack(index: int, used_groups: set, current: Dict[str, str], score: float) -> None:
        nonlocal best_assignment, best_score
        if index == len(ordered_slots):
            if score > best_score:
                best_score = score
                best_assignment = dict(current)
            return

        match = ordered_slots[index]
        winner_rank = winner_ranks[match["team_a"]["group"]]
        candidates = [
            entry for entry in third_place_entries
            if entry["group"] in match["team_b"]["allowed_groups"] and entry["group"] not in used_groups
        ]
        candidates.sort(key=lambda entry: entry["third_rank"], reverse=True)

        for candidate in candidates:
            current[match["id"]] = candidate["team"]
            used_groups.add(candidate["group"])
            candidate_score = (13 - winner_rank) * candidate["third_rank"]
            backtrack(index + 1, used_groups, current, score + candidate_score)
            used_groups.remove(candidate["group"])
            current.pop(match["id"], None)

    backtrack(0, set(), {}, 0.0)
    if len(best_assignment) != len(third_slot_matches):
        raise SystemExit("No se pudo asignar un cuadro valido para los mejores terceros.")
    return third_place_entries, best_assignment


def resolve_r32_team(
    slot: dict,
    standings: Dict[str, List[dict]],
    third_assignments: Dict[str, str],
    match_id: str,
) -> str:
    if slot["type"] == "group_rank":
        return standings[slot["group"]][slot["rank"] - 1]["team"]
    if slot["type"] == "third_place":
        return third_assignments[match_id]
    raise SystemExit(f"Slot no soportado en {match_id}: {slot}")


def run_knockout_round(
    teams: Dict[str, Team],
    states: Dict[str, dict],
    stage: str,
    fixtures: Sequence[Tuple[str, str, str]],
    previous_winners: Dict[str, str],
) -> Tuple[Dict[str, str], Dict[str, dict]]:
    winners = {}
    results = {}
    for match_id, left_id, right_id in fixtures:
        team_a = previous_winners[left_id]
        team_b = previous_winners[right_id]
        result = simulate_match_sample(teams, states, team_a, team_b, stage)
        winners[match_id] = result["winner"]
        results[match_id] = result
    return winners, results


def simulate_tournament_iteration(
    teams: Dict[str, Team],
    config: dict,
    initial_payload: Optional[dict] = None,
) -> dict:
    placeholders = sample_playoff_placeholders(teams)
    groups = resolve_groups_for_iteration(config, placeholders)
    participants = [team for members in groups.values() for team in members]
    states = initial_simulation_states(initial_payload)
    standings = simulate_group_stage(teams, groups, states)

    winner_entries = sort_standings([table[0] for table in standings.values()])
    winner_ranks = {entry["group"]: rank for rank, entry in enumerate(winner_entries, start=1)}
    third_entries, third_assignments = assign_third_place_slots(standings, winner_ranks)

    stage_reached = {team: "group" for team in participants}
    qualified = {entry["team"] for table in standings.values() for entry in table[:2]}
    qualified.update(entry["team"] for entry in third_entries)
    bracket_matches = {}

    for team in qualified:
        stage_reached[team] = "round32"

    r32_winners = {}
    for match in R32_MATCHES:
        team_a = resolve_r32_team(match["team_a"], standings, third_assignments, match["id"])
        team_b = resolve_r32_team(match["team_b"], standings, third_assignments, match["id"])
        result = simulate_match_sample(teams, states, team_a, team_b, "round32")
        winner = result["winner"]
        r32_winners[match["id"]] = winner
        bracket_matches[match["id"]] = result
        stage_reached[winner] = "round16"

    round16_winners, round16_results = run_knockout_round(teams, states, "round16", KNOCKOUT_MATCHES["round16"], r32_winners)
    bracket_matches.update(round16_results)
    for winner in round16_winners.values():
        stage_reached[winner] = "quarterfinal"

    quarter_winners, quarter_results = run_knockout_round(teams, states, "quarterfinal", KNOCKOUT_MATCHES["quarterfinal"], round16_winners)
    bracket_matches.update(quarter_results)
    for winner in quarter_winners.values():
        stage_reached[winner] = "semifinal"

    semifinal_winners = {}
    semifinal_losers = []
    for match_id, left_id, right_id in KNOCKOUT_MATCHES["semifinal"]:
        team_a = quarter_winners[left_id]
        team_b = quarter_winners[right_id]
        result = simulate_match_sample(teams, states, team_a, team_b, "semifinal")
        semifinal_winners[match_id] = result["winner"]
        semifinal_losers.append(result["loser"])
        bracket_matches[match_id] = result
    for winner in semifinal_winners.values():
        stage_reached[winner] = "final"

    third_place_result = simulate_match_sample(
        teams,
        states,
        semifinal_losers[0],
        semifinal_losers[1],
        "third_place",
    )
    bracket_matches["M104"] = third_place_result

    final_winners, final_results = run_knockout_round(teams, states, "final", KNOCKOUT_MATCHES["final"], semifinal_winners)
    bracket_matches.update(final_results)
    champion = final_winners["M103"]
    stage_reached[champion] = "champion"

    return {
        "participants": participants,
        "standings": standings,
        "third_entries": third_entries,
        "stage_reached": stage_reached,
        "states": states,
        "champion": champion,
        "third_place": third_place_result["winner"],
        "fourth_place": third_place_result["loser"],
        "bracket_matches": bracket_matches,
    }


def command_simulate_tournament(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    if args.seed is not None:
        random.seed(args.seed)

    config = load_tournament_config(Path(args.config))
    initial_payload = None if getattr(args, "ignore_state", False) else load_persistent_payload(Path(args.state_file), teams)
    summary = {
        name: {
            "appear": 0,
            "advance_group": 0,
            "reach_round16": 0,
            "reach_quarterfinal": 0,
            "reach_semifinal": 0,
            "reach_final": 0,
            "third_place": 0,
            "fourth_place": 0,
            "champion": 0,
            "group_winner": 0,
            "avg_group_points": 0.0,
            "avg_goals_for": 0.0,
            "avg_goals_against": 0.0,
        }
        for name in teams
    }

    for iteration in range(1, args.iterations + 1):
        result = simulate_tournament_iteration(teams, config, initial_payload=initial_payload)
        participants = set(result["participants"])
        for team_name in participants:
            stats = summary[team_name]
            state = ensure_state(result["states"], team_name)
            stats["appear"] += 1
            stats["avg_group_points"] += state["group_points"]
            stats["avg_goals_for"] += state["goals_for"]
            stats["avg_goals_against"] += state["goals_against"]

        for group_table in result["standings"].values():
            summary[group_table[0]["team"]]["group_winner"] += 1

        for team_name, stage in result["stage_reached"].items():
            stats = summary[team_name]
            if stage in {"round32", "round16", "quarterfinal", "semifinal", "final", "champion"}:
                stats["advance_group"] += 1
            if stage in {"round16", "quarterfinal", "semifinal", "final", "champion"}:
                stats["reach_round16"] += 1
            if stage in {"quarterfinal", "semifinal", "final", "champion"}:
                stats["reach_quarterfinal"] += 1
            if stage in {"semifinal", "final", "champion"}:
                stats["reach_semifinal"] += 1
            if stage in {"final", "champion"}:
                stats["reach_final"] += 1
            if stage == "champion":
                stats["champion"] += 1
        summary[result["third_place"]]["third_place"] += 1
        summary[result["fourth_place"]]["fourth_place"] += 1
        if args.progress_every and iteration % args.progress_every == 0:
            print(f"Progreso: {iteration}/{args.iterations} iteraciones")

    rows = []
    for team_name, stats in summary.items():
        appear = stats["appear"] / float(args.iterations)
        if appear == 0.0 and not args.full:
            continue
        rows.append(
            (
                team_name,
                appear,
                stats["advance_group"] / float(args.iterations),
                stats["reach_round16"] / float(args.iterations),
                stats["reach_quarterfinal"] / float(args.iterations),
                stats["reach_semifinal"] / float(args.iterations),
                stats["reach_final"] / float(args.iterations),
                stats["third_place"] / float(args.iterations),
                stats["fourth_place"] / float(args.iterations),
                stats["champion"] / float(args.iterations),
                stats["group_winner"] / float(args.iterations),
                stats["avg_group_points"] / max(stats["appear"], 1),
            )
        )

    rows.sort(key=lambda row: (row[9], row[6], row[5], row[1], row[0]), reverse=True)
    if not args.full:
        rows = rows[: args.top]

    print(
        f"Simulacion Monte Carlo del torneo | iteraciones={args.iterations} | "
        f"config={Path(args.config).name}"
    )
    print("Equipo                     Mundial  Grupo  Octavos Cuartos Semis  Final   3ro    4to Campeon  1roGrp PtsGrp")
    print("-" * 118)
    for row in rows:
        name, appear, advance_group, reach_round16, reach_quarterfinal, reach_semifinal, reach_final, third_place, fourth_place, champion, group_winner, avg_points = row
        print(
            f"{name:25} {appear:7.1%} {advance_group:6.1%} {reach_round16:8.1%} "
            f"{reach_quarterfinal:7.1%} {reach_semifinal:6.1%} {reach_final:6.1%} "
            f"{third_place:6.1%} {fourth_place:6.1%} {champion:8.1%} {group_winner:7.1%} {avg_points:6.2f}"
        )


def bracket_match_order() -> List[str]:
    return [match["id"] for match in R32_MATCHES] + [match_id for round_matches in KNOCKOUT_MATCHES.values() for match_id, _, _ in round_matches] + ["M104"]


def stage_for_match_id(match_id: str) -> str:
    match_number = int(match_id[1:])
    if 73 <= match_number <= 88:
        return "round32"
    if 89 <= match_number <= 96:
        return "round16"
    if 97 <= match_number <= 100:
        return "quarterfinal"
    if 101 <= match_number <= 102:
        return "semifinal"
    if match_id == "M104":
        return "third_place"
    if match_id == "M103":
        return "final"
    raise SystemExit(f"ID de llave no reconocido: {match_id}")


def structured_match_projection(match_id: str, aggregate: dict, iterations: int) -> dict:
    modal_outcome, modal_count = max(aggregate["outcomes"].items(), key=lambda item: item[1])
    team_a, team_b, winner = modal_outcome
    appearance_counts: Dict[str, int] = {}
    opponent_counts: Dict[str, Dict[str, int]] = {}
    for outcome, count in aggregate["outcomes"].items():
        scenario_a, scenario_b, _ = outcome
        appearance_counts[scenario_a] = appearance_counts.get(scenario_a, 0) + count
        appearance_counts[scenario_b] = appearance_counts.get(scenario_b, 0) + count
        opponent_counts.setdefault(scenario_a, {})
        opponent_counts.setdefault(scenario_b, {})
        opponent_counts[scenario_a][scenario_b] = opponent_counts[scenario_a].get(scenario_b, 0) + count
        opponent_counts[scenario_b][scenario_a] = opponent_counts[scenario_b].get(scenario_a, 0) + count
    top_scenarios = []
    for outcome, count in sorted(aggregate["outcomes"].items(), key=lambda item: item[1], reverse=True)[:3]:
        scenario_a, scenario_b, scenario_winner = outcome
        top_scenarios.append(
            {
                "team_a": scenario_a,
                "team_b": scenario_b,
                "winner": scenario_winner,
                "prob": count / float(iterations),
            }
        )
    appearance_probabilities = {
        team: count / float(iterations)
        for team, count in sorted(appearance_counts.items(), key=lambda item: item[1], reverse=True)
    }
    advance_probabilities = {
        team: count / float(iterations)
        for team, count in sorted(aggregate["winner"].items(), key=lambda item: item[1], reverse=True)
    }
    opponent_map = {}
    for team, counts in opponent_counts.items():
        total = appearance_counts.get(team, 0)
        if total <= 0:
            continue
        opponent_map[team] = [
            {
                "opponent": opponent,
                "matchup_prob": count / float(iterations),
                "conditional_if_reaches": count / float(total),
            }
            for opponent, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:3]
        ]
    penalty_scores = sorted(aggregate.get("penalty_scores", {}).items(), key=lambda item: item[1], reverse=True)[:3]
    return {
        "match_id": match_id,
        "title": BRACKET_MATCH_TITLES.get(match_id, match_id),
        "stage": stage_for_match_id(match_id),
        "team_a": team_a,
        "team_b": team_b,
        "winner": winner,
        "matchup_prob": modal_count / float(iterations),
        "winner_prob": aggregate["winner"][winner] / float(iterations),
        "extra_time_prob": aggregate["went_extra_time"] / float(iterations),
        "penalties_prob": aggregate["went_penalties"] / float(iterations),
        "top_scenarios": top_scenarios,
        "appearance_probabilities": appearance_probabilities,
        "advance_probabilities": advance_probabilities,
        "opponent_map": opponent_map,
        "top_penalty_scores": [
            {"score": f"{score[0]}-{score[1]}", "prob": count / float(iterations)}
            for score, count in penalty_scores
        ],
    }


def format_match_projection(match_id: str, aggregate: dict, iterations: int) -> List[str]:
    projection = structured_match_projection(match_id, aggregate, iterations)
    team_a = projection["team_a"]
    team_b = projection["team_b"]
    winner = projection["winner"]
    outcome_prob = projection["matchup_prob"]
    winner_prob = projection["winner_prob"]
    extra_time_prob = projection["extra_time_prob"]
    penalties_prob = projection["penalties_prob"]
    lines = [
        f"### {BRACKET_MATCH_TITLES.get(match_id, match_id)}",
        f"- Cruce que aparece mas veces en la simulacion: {team_a} vs {team_b}",
        f"- Probabilidad de que este cruce ocurra: {outcome_prob:.1%}",
        f"- Equipo con mas probabilidad de salir de esta llave: {winner} ({winner_prob:.1%})",
    ]
    alternatives = [
        f"{scenario['team_a']} vs {scenario['team_b']} | gana mas probable {scenario['winner']} | este escenario aparece {scenario['prob']:.1%}"
        for scenario in projection.get("top_scenarios", [])[1:]
    ]
    if alternatives:
        lines.append(f"- Otros cruces que tambien aparecen seguido: {'; '.join(alternatives)}")
    if match_id != "M104":
        lines.append(f"- Va a proroga en {extra_time_prob:.1%} y a penales en {penalties_prob:.1%}")
        penalty_scores = projection.get("top_penalty_scores", [])
        if penalty_scores:
            lines.append(
                "- Marcadores de penales mas probables en este cruce: "
                + "; ".join(f"{item['score']} ({item['prob']:.1%})" for item in penalty_scores)
            )
    return lines


def command_project_bracket(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    if args.seed is not None:
        random.seed(args.seed)

    config = load_tournament_config(Path(args.config))
    initial_payload = None if getattr(args, "ignore_state", False) else load_persistent_payload(Path(args.state_file), teams)
    match_aggregate = {
        match_id: {
            "outcomes": {},
            "winner": {},
            "went_extra_time": 0,
            "went_penalties": 0,
            "penalty_scores": {},
        }
        for match_id in bracket_match_order()
    }

    for iteration in range(1, args.iterations + 1):
        result = simulate_tournament_iteration(teams, config, initial_payload=initial_payload)
        for match_id, match_result in result["bracket_matches"].items():
            aggregate = match_aggregate[match_id]
            outcome_key = (match_result["team_a"], match_result["team_b"], match_result["winner"])
            aggregate["outcomes"][outcome_key] = aggregate["outcomes"].get(outcome_key, 0) + 1
            aggregate["winner"][match_result["winner"]] = aggregate["winner"].get(match_result["winner"], 0) + 1
            aggregate["went_extra_time"] += 1 if match_result.get("went_extra_time") else 0
            aggregate["went_penalties"] += 1 if match_result.get("went_penalties") else 0
            if match_result.get("went_penalties") and match_result.get("penalty_score_a") is not None and match_result.get("penalty_score_b") is not None:
                penalty_key = (int(match_result["penalty_score_a"]), int(match_result["penalty_score_b"]))
                aggregate["penalty_scores"][penalty_key] = aggregate["penalty_scores"].get(penalty_key, 0) + 1
        if args.progress_every and iteration % args.progress_every == 0:
            print(f"Progreso llave: {iteration}/{args.iterations} iteraciones")

    sections = [
        f"# Llave actual proyectada | iteraciones={args.iterations}",
        "",
        "## Dieciseisavos de final",
    ]
    for match_id in [match["id"] for match in R32_MATCHES]:
        sections.extend(format_match_projection(match_id, match_aggregate[match_id], args.iterations))
        sections.append("")

    sections.append("## Octavos de final")
    for match_id, _, _ in KNOCKOUT_MATCHES["round16"]:
        sections.extend(format_match_projection(match_id, match_aggregate[match_id], args.iterations))
        sections.append("")

    sections.append("## Cuartos de final")
    for match_id, _, _ in KNOCKOUT_MATCHES["quarterfinal"]:
        sections.extend(format_match_projection(match_id, match_aggregate[match_id], args.iterations))
        sections.append("")

    sections.append("## Semifinales")
    for match_id, _, _ in KNOCKOUT_MATCHES["semifinal"]:
        sections.extend(format_match_projection(match_id, match_aggregate[match_id], args.iterations))
        sections.append("")

    sections.append("## Partido por el tercer puesto")
    sections.extend(format_match_projection("M104", match_aggregate["M104"], args.iterations))
    sections.append("")

    sections.append("## Final")
    sections.extend(format_match_projection("M103", match_aggregate["M103"], args.iterations))
    sections.append("")

    content = "\n".join(sections)
    structured = {
        "updated_at": iso_timestamp(),
        "iterations": args.iterations,
        "matches": {
            match_id: structured_match_projection(match_id, aggregate, args.iterations)
            for match_id, aggregate in match_aggregate.items()
        },
    }
    output_path = Path(args.output)
    output_json_path = Path(args.json_output)
    output_path.write_text(content)
    output_json_path.write_text(json.dumps(structured, indent=2))
    print(f"Llave proyectada guardada en {output_path}")
    print(f"Llave estructurada guardada en {output_json_path}")
    print(content)


def format_pct(value: float) -> str:
    return f"{value:.1%}"


def dashboard_stage_label(stage: str, group: Optional[str]) -> str:
    if stage == "group" and group:
        return f"Grupo {group}"
    labels = {
        "group": "Fase de grupos",
        "round32": "Dieciseisavos de final",
        "round16": "Octavos de final",
        "quarterfinal": "Cuartos de final",
        "semifinal": "Semifinal",
        "third_place": "Tercer puesto",
        "final": "Final",
    }
    return labels.get(stage, stage)


def resolved_team_name_from_penalties(
    penalties_winner: Optional[str],
    team_a: str,
    team_b: str,
) -> Optional[str]:
    if not penalties_winner:
        return None
    winner = str(penalties_winner).strip()
    if winner == "A":
        return team_a
    if winner == "B":
        return team_b
    resolved = normalize_team_name(winner)
    if resolved == team_a or winner == team_a:
        return team_a
    if resolved == team_b or winner == team_b:
        return team_b
    return None


def resolved_winner_for_entry(entry: dict, prediction: MatchPrediction) -> Optional[str]:
    score_a = entry.get("actual_score_a")
    score_b = entry.get("actual_score_b")
    if score_a is None or score_b is None:
        return None
    if int(score_a) > int(score_b):
        return prediction.team_a
    if int(score_b) > int(score_a):
        return prediction.team_b
    return resolved_team_name_from_penalties(entry.get("penalties_winner"), prediction.team_a, prediction.team_b)


def next_round_projection_note(
    entry: dict,
    prediction: MatchPrediction,
    bracket_payload: dict,
) -> Optional[str]:
    match_id = entry.get("match_id")
    if not match_id:
        return None
    winner_name = resolved_winner_for_entry(entry, prediction)
    if not winner_name:
        return None
    next_match_id = WINNER_NEXT_MATCH.get(str(match_id))
    if not next_match_id:
        return None
    next_projection = (bracket_payload.get("matches") or {}).get(next_match_id)
    if not next_projection:
        return None
    appearance_prob = float((next_projection.get("appearance_probabilities") or {}).get(winner_name, 0.0))
    advance_prob = float((next_projection.get("advance_probabilities") or {}).get(winner_name, 0.0))
    opponent_scenarios = (next_projection.get("opponent_map") or {}).get(winner_name) or []
    if opponent_scenarios:
        top = opponent_scenarios[0]
        return (
            f"Con este resultado, el siguiente cruce mas probable de {winner_name} es contra {top['opponent']}. "
            f"Ese cruce aparece en {format_pct(float(top['matchup_prob']))} de las simulaciones; "
            f"si {winner_name} llega a ese partido, su rival mas frecuente es {top['opponent']} en {format_pct(float(top['conditional_if_reaches']))}. "
            f"Probabilidad actual de que {winner_name} alcance ese cruce: {format_pct(appearance_prob)} | "
            f"probabilidad de avanzar desde esa llave: {format_pct(advance_prob)}."
        )
    return (
        f"Con este resultado, {winner_name} pasa a la siguiente llave {BRACKET_MATCH_TITLES.get(next_match_id, next_match_id)} "
        f"con probabilidad de presencia {format_pct(appearance_prob)} y probabilidad de avanzar {format_pct(advance_prob)}."
    )


def dashboard_fixture_title(fixture: dict) -> str:
    label = str(fixture.get("label", "")).strip()
    if label:
        return label
    return f"{fixture['team_a']} vs {fixture['team_b']}"


def extract_live_stats_payload(source: dict) -> Dict[str, float]:
    payload = {}
    stat_names = (
        "shots",
        "shots_on_target",
        "possession",
        "corners",
        "fouls",
        "yellow_cards",
        "red_cards",
        "xg",
        "xg_proxy",
    )
    for stat in stat_names:
        for prefix in ("a", "b"):
            key = f"live_{stat}_{prefix}"
            value = source.get(key)
            if value is None:
                continue
            payload[f"{stat}_{prefix}"] = float(value)
    return payload


def dashboard_live_stats_lines(entry: dict, team_a: str, team_b: str) -> List[str]:
    stats = extract_live_stats_payload(entry)
    if not stats:
        return []
    lines = []
    if stats.get("shots_a") is not None or stats.get("shots_b") is not None:
        lines.append(
            f"- Tiros: {team_a} {int(stats.get('shots_a', 0.0))} | {team_b} {int(stats.get('shots_b', 0.0))}"
        )
    if stats.get("shots_on_target_a") is not None or stats.get("shots_on_target_b") is not None:
        lines.append(
            f"- Tiros al arco: {team_a} {int(stats.get('shots_on_target_a', 0.0))} | {team_b} {int(stats.get('shots_on_target_b', 0.0))}"
        )
    if stats.get("possession_a") is not None or stats.get("possession_b") is not None:
        lines.append(
            f"- Posesion: {team_a} {stats.get('possession_a', 0.0):.0f}% | {team_b} {stats.get('possession_b', 0.0):.0f}%"
        )
    xg_a = stats.get("xg_a", stats.get("xg_proxy_a"))
    xg_b = stats.get("xg_b", stats.get("xg_proxy_b"))
    if xg_a is not None or xg_b is not None:
        label = "xG live" if stats.get("xg_a") is not None or stats.get("xg_b") is not None else "xG live proxy"
        lines.append(
            f"- {label}: {team_a} {float(xg_a or 0.0):.2f} | {team_b} {float(xg_b or 0.0):.2f}"
        )
    if stats.get("red_cards_a") or stats.get("red_cards_b"):
        lines.append(
            f"- Rojas en vivo: {team_a} {int(stats.get('red_cards_a', 0.0))} | {team_b} {int(stats.get('red_cards_b', 0.0))}"
        )
    return lines


def dashboard_pattern_lines(prediction: MatchPrediction) -> List[str]:
    patterns = prediction.live_patterns or {}
    side_a = patterns.get("a")
    side_b = patterns.get("b")
    if not side_a or not side_b:
        return []
    lines = [
        f"- Patron de juego {prediction.team_a}: {side_a.get('summary', 'sin patron dominante claro')}.",
        f"- Patron de juego {prediction.team_b}: {side_b.get('summary', 'sin patron dominante claro')}.",
        f"- Ritmo detectado: {patterns.get('tempo_label', 'ritmo equilibrado')}.",
    ]
    signals_a = side_a.get("signals") or []
    signals_b = side_b.get("signals") or []
    if signals_a:
        lines.append(f"- Senales {prediction.team_a}: {'; '.join(str(signal) for signal in signals_a[:3])}")
    if signals_b:
        lines.append(f"- Senales {prediction.team_b}: {'; '.join(str(signal) for signal in signals_b[:3])}")
    return lines


def dashboard_weather_summary(fixture: dict) -> Optional[str]:
    if fixture.get("weather_temperature_c") is None:
        return None
    return (
        f"{fixture.get('weather_temperature_c', 0.0):.1f} C | "
        f"HR {fixture.get('weather_humidity_pct', 0.0):.0f}% | "
        f"viento {fixture.get('weather_wind_kmh', 0.0):.0f} km/h | "
        f"estres {fixture.get('weather_stress', 0.0):.2f}"
    )


def dashboard_fixture_entries(
    fixtures: Sequence[dict],
    teams: Dict[str, Team],
    states: Dict[str, dict],
    top_scores: int,
) -> List[dict]:
    entries = []
    for fixture in fixtures:
        if fixture.get("projection_only"):
            continue
        fixture = resolve_fixture_names(dict(fixture), teams)
        team_a = fixture["team_a"]
        team_b = fixture["team_b"]
        state_a = normalize_team_state(states.get(team_a, {}))
        state_b = normalize_team_state(states.get(team_b, {}))
        ctx = context_from_fixture(fixture, teams, states)
        stage = fixture_stage_name(fixture)
        if fixture.get("status_state") == "in" and fixture.get("live_score_a") is not None and fixture.get("live_score_b") is not None:
            prediction = predict_match_live(
                teams,
                team_a,
                team_b,
                ctx,
                current_score_a=int(fixture.get("live_score_a", 0)),
                current_score_b=int(fixture.get("live_score_b", 0)),
                status_detail=fixture.get("status_detail"),
                top_scores=top_scores,
                include_advancement=stage != "group",
                show_factors=True,
                state_a=state_a,
                state_b=state_b,
                live_stats=extract_live_stats_payload(fixture),
            )
        else:
            prediction = predict_match(
                teams,
                team_a,
                team_b,
                ctx,
                top_scores=top_scores,
                include_advancement=stage != "group",
                show_factors=True,
                state_a=state_a,
                state_b=state_b,
            )
        entries.append(
            {
                "title": dashboard_fixture_title(fixture),
                "stage_label": dashboard_stage_label(stage, fixture.get("group")),
                "match_id": fixture.get("match_id"),
                "team_a": team_a,
                "team_b": team_b,
                "prediction": prediction,
                "actual_score_a": fixture.get("actual_score_a"),
                "actual_score_b": fixture.get("actual_score_b"),
                "went_extra_time": bool(fixture.get("went_extra_time", False)),
                "went_penalties": bool(fixture.get("went_penalties", False)),
                "penalties_winner": fixture.get("penalties_winner"),
                "kickoff_utc": fixture.get("kickoff_utc"),
                "venue_name": fixture.get("venue_name"),
                "venue_country": fixture.get("venue_country"),
                "status_state": fixture.get("status_state"),
                "status_detail": fixture.get("status_detail"),
                "live_score_a": fixture.get("live_score_a"),
                "live_score_b": fixture.get("live_score_b"),
                "weather_summary": dashboard_weather_summary(fixture),
                "weather_stress": fixture.get("weather_stress"),
                "referee": fixture.get("referee"),
                "lineup_status_a": fixture.get("lineup_status_a"),
                "lineup_status_b": fixture.get("lineup_status_b"),
                "lineup_change_count_a": int(fixture.get("lineup_change_count_a", 0)),
                "lineup_change_count_b": int(fixture.get("lineup_change_count_b", 0)),
                "tactical_signature_a": tactical_signature_text(state_a),
                "tactical_signature_b": tactical_signature_text(state_b),
                "tactical_sample_matches_a": int(state_a.get("tactical_sample_matches", 0)),
                "tactical_sample_matches_b": int(state_b.get("tactical_sample_matches", 0)),
                "injuries_a": fixture.get("injuries_a"),
                "injuries_b": fixture.get("injuries_b"),
                "unavailable_count_a": int(fixture.get("unavailable_count_a", 0)),
                "unavailable_count_b": int(fixture.get("unavailable_count_b", 0)),
                "questionable_count_a": int(fixture.get("questionable_count_a", 0)),
                "questionable_count_b": int(fixture.get("questionable_count_b", 0)),
                "unavailable_notes_a": fixture.get("unavailable_notes_a", []),
                "unavailable_notes_b": fixture.get("unavailable_notes_b", []),
                "news_headlines": fixture.get("news_headlines", []),
                "news_notes_a": fixture.get("news_notes_a", []),
                "news_notes_b": fixture.get("news_notes_b", []),
                "live_shots_a": fixture.get("live_shots_a"),
                "live_shots_b": fixture.get("live_shots_b"),
                "live_shots_on_target_a": fixture.get("live_shots_on_target_a"),
                "live_shots_on_target_b": fixture.get("live_shots_on_target_b"),
                "live_possession_a": fixture.get("live_possession_a"),
                "live_possession_b": fixture.get("live_possession_b"),
                "live_corners_a": fixture.get("live_corners_a"),
                "live_corners_b": fixture.get("live_corners_b"),
                "live_red_cards_a": fixture.get("live_red_cards_a"),
                "live_red_cards_b": fixture.get("live_red_cards_b"),
                "live_xg_a": fixture.get("live_xg_a"),
                "live_xg_b": fixture.get("live_xg_b"),
                "live_xg_proxy_a": fixture.get("live_xg_proxy_a"),
                "live_xg_proxy_b": fixture.get("live_xg_proxy_b"),
                "market_provider": fixture.get("market_provider"),
                "market_summary": fixture.get("market_summary"),
                "market_prob_a": fixture.get("market_prob_a"),
                "market_prob_draw": fixture.get("market_prob_draw"),
                "market_prob_b": fixture.get("market_prob_b"),
                "projection": False,
            }
        )
    return entries


def load_bracket_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def projected_bracket_entries(
    fixtures: Sequence[dict],
    bracket_payload: dict,
    teams: Dict[str, Team],
    states: Dict[str, dict],
    top_scores: int,
    seen_match_ids: Sequence[str],
) -> List[dict]:
    unresolved_fixtures = {
        str(fixture["match_id"]): fixture
        for fixture in fixtures
        if fixture.get("projection_only") and fixture.get("match_id")
    }
    entries = []
    seen = set(seen_match_ids)
    for match_id in bracket_match_order():
        if match_id in seen:
            continue
        match_projection = bracket_payload.get("matches", {}).get(match_id)
        if not match_projection:
            continue
        team_a = match_projection["team_a"]
        team_b = match_projection["team_b"]
        if team_a not in teams or team_b not in teams:
            continue
        base_fixture = dict(unresolved_fixtures.get(match_id, {}))
        base_fixture.update(
            {
                "team_a": team_a,
                "team_b": team_b,
                "stage": match_projection["stage"],
                "neutral": True,
                "match_id": match_id,
                "label": f"{match_projection['title']}: {team_a} vs {team_b}",
            }
        )
        state_a = normalize_team_state(states.get(team_a, {}))
        state_b = normalize_team_state(states.get(team_b, {}))
        ctx = context_from_fixture(base_fixture, teams, states)
        prediction = predict_match(
            teams,
            team_a,
            team_b,
            ctx,
            top_scores=top_scores,
            include_advancement=True,
            show_factors=True,
            state_a=state_a,
            state_b=state_b,
        )
        entries.append(
            {
                "title": base_fixture["label"],
                "stage_label": dashboard_stage_label(match_projection["stage"], None),
                "match_id": match_id,
                "team_a": team_a,
                "team_b": team_b,
                "prediction": prediction,
                "actual_score_a": None,
                "actual_score_b": None,
                "went_extra_time": False,
                "went_penalties": False,
                "penalties_winner": None,
                "kickoff_utc": base_fixture.get("kickoff_utc"),
                "venue_name": base_fixture.get("venue_name"),
                "venue_country": base_fixture.get("venue_country"),
                "status_state": base_fixture.get("status_state"),
                "status_detail": base_fixture.get("status_detail"),
                "live_score_a": base_fixture.get("live_score_a"),
                "live_score_b": base_fixture.get("live_score_b"),
                "weather_summary": dashboard_weather_summary(base_fixture),
                "weather_stress": base_fixture.get("weather_stress"),
                "projection": True,
                "projection_note": (
                    f"Cruce que mas aparece hoy: {team_a} vs {team_b} | "
                    f"probabilidad de que ese cruce ocurra {format_pct(match_projection['matchup_prob'])} | "
                    f"equipo con mayor probabilidad de salir de esa llave {match_projection['winner']} {format_pct(match_projection['winner_prob'])}"
                ),
                "projection_alternatives": match_projection.get("top_scenarios", [])[1:],
                "projection_penalties": match_projection.get("penalties_prob", 0.0),
                "projection_extra_time": match_projection.get("extra_time_prob", 0.0),
                "tactical_signature_a": tactical_signature_text(state_a),
                "tactical_signature_b": tactical_signature_text(state_b),
                "tactical_sample_matches_a": int(state_a.get("tactical_sample_matches", 0)),
                "tactical_sample_matches_b": int(state_b.get("tactical_sample_matches", 0)),
                "injuries_a": base_fixture.get("injuries_a"),
                "injuries_b": base_fixture.get("injuries_b"),
                "unavailable_count_a": int(base_fixture.get("unavailable_count_a", 0)),
                "unavailable_count_b": int(base_fixture.get("unavailable_count_b", 0)),
                "questionable_count_a": int(base_fixture.get("questionable_count_a", 0)),
                "questionable_count_b": int(base_fixture.get("questionable_count_b", 0)),
                "unavailable_notes_a": base_fixture.get("unavailable_notes_a", []),
                "unavailable_notes_b": base_fixture.get("unavailable_notes_b", []),
                "news_headlines": base_fixture.get("news_headlines", []),
                "news_notes_a": base_fixture.get("news_notes_a", []),
                "news_notes_b": base_fixture.get("news_notes_b", []),
            }
        )
    return entries


def dashboard_status(entry: dict) -> Tuple[str, str]:
    if entry.get("actual_score_a") is not None and entry.get("actual_score_b") is not None:
        return ("final", "Final")
    if entry.get("live_score_a") is not None and entry.get("live_score_b") is not None:
        detail = entry.get("status_detail")
        return ("live", f"En vivo{f' | {detail}' if detail else ''}")
    if entry.get("projection"):
        return ("projection", "Proyeccion")
    detail = entry.get("status_detail")
    return ("pending", detail or "Pendiente")


def dashboard_absence_lines(entry: dict, team_a: str, team_b: str) -> List[str]:
    lines = []
    count_a = int(entry.get("unavailable_count_a", 0))
    count_b = int(entry.get("unavailable_count_b", 0))
    questionable_a = int(entry.get("questionable_count_a", 0))
    questionable_b = int(entry.get("questionable_count_b", 0))
    if count_a or count_b or questionable_a or questionable_b:
        lines.append(
            f"- Bajas/dudas: {team_a} {count_a} bajas, {questionable_a} dudas | "
            f"{team_b} {count_b} bajas, {questionable_b} dudas"
        )
    notes_a = entry.get("unavailable_notes_a") or []
    notes_b = entry.get("unavailable_notes_b") or []
    if notes_a:
        lines.append(f"- Detalle {team_a}: {'; '.join(notes_a[:3])}")
    if notes_b:
        lines.append(f"- Detalle {team_b}: {'; '.join(notes_b[:3])}")
    return lines


def dashboard_news_lines(entry: dict, team_a: str, team_b: str) -> List[str]:
    lines = []
    headlines = entry.get("news_headlines") or []
    notes_a = entry.get("news_notes_a") or []
    notes_b = entry.get("news_notes_b") or []
    if headlines:
        lines.append(f"- Noticias relevantes: {'; '.join(headlines[:3])}")
    if notes_a:
        lines.append(f"- Impacto noticioso {team_a}: {'; '.join(notes_a[:2])}")
    if notes_b:
        lines.append(f"- Impacto noticioso {team_b}: {'; '.join(notes_b[:2])}")
    return lines


def dashboard_tactical_signature_lines(entry: dict, team_a: str, team_b: str) -> List[str]:
    lines = []
    signature_a = str(entry.get("tactical_signature_a") or "sin muestra suficiente")
    signature_b = str(entry.get("tactical_signature_b") or "sin muestra suficiente")
    sample_a = int(entry.get("tactical_sample_matches_a", 0))
    sample_b = int(entry.get("tactical_sample_matches_b", 0))
    if sample_a > 0 or sample_b > 0:
        lines.append(
            f"- Firma tactica reciente: {team_a} {signature_a} (muestra {sample_a}) | {team_b} {signature_b} (muestra {sample_b})"
        )
    return lines


def adjustment_reason_lines(entry: dict, prediction: MatchPrediction) -> List[str]:
    lines = []
    if int(entry.get("tactical_sample_matches_a", 0)) > 0 or int(entry.get("tactical_sample_matches_b", 0)) > 0:
        lines.append(
            f"- Ajuste por firma tactica reciente: {prediction.team_a} {entry.get('tactical_signature_a', 'sin muestra suficiente')} | "
            f"{prediction.team_b} {entry.get('tactical_signature_b', 'sin muestra suficiente')}."
        )
    if entry.get("status_state") == "in" and prediction.current_score_a is not None and prediction.current_score_b is not None:
        minute_text = f"{prediction.elapsed_minutes:.1f}" if prediction.elapsed_minutes is not None else "?"
        lines.append(
            f"- Ajuste en vivo: marcador {prediction.team_a} {prediction.current_score_a} - {prediction.current_score_b} {prediction.team_b} en el minuto {minute_text}."
        )
    if int(entry.get("unavailable_count_a", 0)) or int(entry.get("unavailable_count_b", 0)):
        lines.append(
            f"- Ajuste por bajas confirmadas: {prediction.team_a} {int(entry.get('unavailable_count_a', 0))} | {prediction.team_b} {int(entry.get('unavailable_count_b', 0))}."
        )
    if int(entry.get("questionable_count_a", 0)) or int(entry.get("questionable_count_b", 0)):
        lines.append(
            f"- Ajuste por dudas fisicas: {prediction.team_a} {int(entry.get('questionable_count_a', 0))} | {prediction.team_b} {int(entry.get('questionable_count_b', 0))}."
        )
    if entry.get("lineup_status_a") == "confirmada" or entry.get("lineup_status_b") == "confirmada":
        lines.append(
            f"- Ajuste por alineaciones: {prediction.team_a} {entry.get('lineup_status_a', 'sin confirmar')} | {prediction.team_b} {entry.get('lineup_status_b', 'sin confirmar')}."
        )
    if entry.get("lineup_change_count_a") or entry.get("lineup_change_count_b"):
        lines.append(
            f"- Ajuste por cambios en el XI: {prediction.team_a} {entry.get('lineup_change_count_a', 0)} | {prediction.team_b} {entry.get('lineup_change_count_b', 0)}."
        )
    if entry.get("weather_stress") is not None and float(entry.get("weather_stress", 0.0)) >= 0.18:
        lines.append(f"- Ajuste por clima exigente: estres climatico {float(entry.get('weather_stress', 0.0)):.2f}.")
    if entry.get("market_prob_a") is not None:
        lines.append("- Ajuste por mercado: el prior de cuotas se mezcla con la estimacion propia del modelo.")
    live_stats = extract_live_stats_payload(entry)
    if live_stats:
        shots_on_target_a = int(live_stats.get("shots_on_target_a", 0.0))
        shots_on_target_b = int(live_stats.get("shots_on_target_b", 0.0))
        xg_a = float(live_stats.get("xg_a", live_stats.get("xg_proxy_a", 0.0)))
        xg_b = float(live_stats.get("xg_b", live_stats.get("xg_proxy_b", 0.0)))
        red_a = int(live_stats.get("red_cards_a", 0.0))
        red_b = int(live_stats.get("red_cards_b", 0.0))
        if shots_on_target_a or shots_on_target_b or xg_a or xg_b:
            lines.append(
                f"- Ajuste por datos en vivo: tiros al arco {prediction.team_a} {shots_on_target_a} | {prediction.team_b} {shots_on_target_b}; "
                f"xG live {prediction.team_a} {xg_a:.2f} | {prediction.team_b} {xg_b:.2f}."
            )
        if red_a or red_b:
            lines.append(
                f"- Ajuste por expulsiones en vivo: rojas {prediction.team_a} {red_a} | {prediction.team_b} {red_b}."
            )
    patterns = prediction.live_patterns or {}
    side_a = patterns.get("a")
    side_b = patterns.get("b")
    if side_a and side_b:
        lines.append(
            f"- Ajuste por patrones de juego: {prediction.team_a} muestra {side_a.get('summary', 'sin patron claro')}; "
            f"{prediction.team_b} muestra {side_b.get('summary', 'sin patron claro')}."
        )
        if patterns.get("tempo_label"):
            lines.append(f"- Ritmo detectado del partido: {patterns['tempo_label']}.")
    if entry.get("news_headlines"):
        lines.append("- Ajuste por noticias relevantes detectadas en el feed del partido.")
    drivers = top_factor_drivers(prediction.factors, limit=2)
    if drivers:
        lines.append(
            "- Motores principales del pronostico ahora mismo: "
            + "; ".join(f"{label} {value:+.3f}" for label, value in drivers)
        )
    return lines


def goals_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Goles esperados al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Goles esperados al final de la prorroga"
    if prediction.live_phase == "penalties":
        return "Marcador actual"
    return "Goles esperados"


def projected_score_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Marcador proyectado al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Marcador proyectado al final de la prorroga"
    if prediction.live_phase == "penalties":
        return "Marcador actual"
    return "Marcador proyectado"


def projected_score_value(prediction: MatchPrediction) -> str:
    if prediction.exact_scores:
        return prediction.exact_scores[0][0]
    return f"{int(round(prediction.expected_goals_a))}-{int(round(prediction.expected_goals_b))}"


def average_goals_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Promedio estimado de goles al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Promedio estimado de goles al final de la prorroga"
    if prediction.live_phase == "penalties":
        return "Marcador actual"
    return "Promedio estimado de goles del modelo"


def result_prob_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Probabilidades de resultado al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Probabilidades de resultado al final de la prorroga"
    if prediction.live_phase == "penalties":
        return "Probabilidades de clasificar en penales"
    return "Probabilidades de resultado (90')"


def build_dashboard_markdown(
    entries: Sequence[dict],
    bracket_text: str,
    bracket_payload: dict,
    backtest: dict,
    state_path: Path,
    fixtures_path: Path,
) -> str:
    lines = [
        "# Reporte actual del Mundial 2026",
        "",
        f"Actualizado: {iso_timestamp()}",
        f"Estado usado: {state_path}",
        f"Fixtures leidos: {fixtures_path}",
        "",
        "## Lectura global del tablero",
        "",
    ]
    lines.extend(build_global_confidence_markdown(entries))
    lines.extend(["", "## Calibracion historica y backtesting", ""])
    lines.extend(build_backtesting_markdown(backtest))
    lines.extend([
        "",
        "## Llave actual",
        "",
    ])
    if bracket_text.strip():
        lines.append(bracket_text.strip())
    else:
        lines.append("_No hay llave generada todavia._")
    lines.extend(["", "## Partidos cargados", ""])

    if not entries:
        lines.append("_No hay partidos en fixtures_template.json._")
        return "\n".join(lines)

    for entry in entries:
        prediction: MatchPrediction = entry["prediction"]
        lines.append(f"### {entry['title']}")
        lines.append(f"- Etapa: {entry['stage_label']}")
        _, status_text = dashboard_status(entry)
        lines.append(f"- Estado: {status_text}")
        if prediction.elapsed_minutes is not None:
            lines.append(f"- Minuto modelado: {prediction.elapsed_minutes:.1f}")
        if entry.get("kickoff_utc"):
            venue_bits = [entry.get("venue_name"), entry.get("venue_country")]
            venue_bits = [bit for bit in venue_bits if bit]
            lines.append(f"- Sede: {' | '.join(venue_bits)}")
            lines.append(f"- Hora UTC: {entry['kickoff_utc']}")
        if entry.get("weather_summary"):
            lines.append(f"- Clima estimado: {entry['weather_summary']}")
        if entry.get("referee"):
            lines.append(f"- Arbitro: {entry['referee']}")
        if entry.get("market_summary"):
            provider = entry.get("market_provider") or "mercado"
            lines.append(f"- Odds {provider}: {entry['market_summary']}")
        if entry.get("market_prob_a") is not None:
            lines.append(
                f"- Prior de mercado (victoria/empate/derrota): {prediction.team_a} {format_pct(float(entry['market_prob_a']))} | "
                f"empate {format_pct(float(entry.get('market_prob_draw', 0.0)))} | "
                f"{prediction.team_b} {format_pct(float(entry.get('market_prob_b', 0.0)))}"
            )
        if entry.get("lineup_status_a") or entry.get("lineup_status_b"):
            lines.append(
                f"- Alineaciones: {prediction.team_a} {entry.get('lineup_status_a', 'sin confirmar')} | "
                f"{prediction.team_b} {entry.get('lineup_status_b', 'sin confirmar')}"
            )
        if entry.get("lineup_change_count_a") or entry.get("lineup_change_count_b"):
            lines.append(
                f"- Cambios de alineacion: {prediction.team_a} {entry.get('lineup_change_count_a', 0)} | "
                f"{prediction.team_b} {entry.get('lineup_change_count_b', 0)}"
            )
        lines.extend(dashboard_absence_lines(entry, prediction.team_a, prediction.team_b))
        lines.extend(dashboard_news_lines(entry, prediction.team_a, prediction.team_b))
        lines.extend(dashboard_tactical_signature_lines(entry, prediction.team_a, prediction.team_b))
        lines.extend(dashboard_live_stats_lines(entry, prediction.team_a, prediction.team_b))
        lines.extend(dashboard_pattern_lines(prediction))
        lines.extend(adjustment_reason_lines(entry, prediction))
        next_round_note = next_round_projection_note(entry, prediction, bracket_payload)
        if next_round_note:
            lines.append(f"- Siguiente cruce del ganador real: {next_round_note}")
        if entry.get("projection"):
            lines.append(f"- Proyeccion automatica: {entry.get('projection_note', '')}")
            alternatives = entry.get("projection_alternatives") or []
            if alternatives:
                lines.append(
                    "- Otras rutas probables: "
                    + "; ".join(
                        f"{scenario['team_a']} vs {scenario['team_b']} -> {scenario['winner']} {format_pct(float(scenario['prob']))}"
                        for scenario in alternatives
                    )
                )
        if entry["actual_score_a"] is not None and entry["actual_score_b"] is not None:
            result_line = f"- Resultado real: {prediction.team_a} {entry['actual_score_a']} - {entry['actual_score_b']} {prediction.team_b}"
            if entry["went_penalties"]:
                result_line += f" | penales: {entry['penalties_winner']}"
            elif entry["went_extra_time"]:
                result_line += " | con proroga"
            lines.append(result_line)
        elif entry.get("live_score_a") is not None and entry.get("live_score_b") is not None:
            lines.append(
                f"- Marcador en vivo: {prediction.team_a} {entry['live_score_a']} - {entry['live_score_b']} {prediction.team_b}"
            )
        else:
            pass
        lines.append(f"- {projected_score_label(prediction)}: {projected_score_value(prediction)}")
        if prediction.live_phase != "penalties":
            lines.append(
                f"- {average_goals_label(prediction)}: {prediction.team_a} {prediction.expected_goals_a:.2f} | "
                f"{prediction.team_b} {prediction.expected_goals_b:.2f}"
            )
        if prediction.expected_remaining_goals_a is not None and prediction.expected_remaining_goals_b is not None:
            lines.append(
                f"- Promedio estimado de goles restantes: {prediction.team_a} {prediction.expected_remaining_goals_a:.2f} | "
                f"{prediction.team_b} {prediction.expected_remaining_goals_b:.2f}"
            )
        lines.append(
            f"- {result_prob_label(prediction)}: {format_pct(prediction.win_a)} / {format_pct(prediction.draw)} / {format_pct(prediction.win_b)}"
        )
        lines.extend(statistical_depth_lines(prediction))
        if prediction.advance_a is not None and prediction.advance_b is not None:
            detail = prediction.knockout_detail or {}
            lines.append(
                f"- Clasificar: {prediction.team_a} {format_pct(prediction.advance_a)} | {prediction.team_b} {format_pct(prediction.advance_b)}"
            )
            lines.append(
                f"- Si empatan en 90': proroga {prediction.team_a} {format_pct(detail.get('et_win_a', 0.0))} | "
                f"seguir empatados {format_pct(detail.get('et_draw', 0.0))} | {prediction.team_b} {format_pct(detail.get('et_win_b', 0.0))}"
            )
            lines.append(
                f"- Penales si llegan: {prediction.team_a} {format_pct(detail.get('penalties_a', 0.0))} | "
                f"{prediction.team_b} {format_pct(detail.get('penalties_b', 0.0))}"
            )
            if prediction.penalty_shootout:
                shootout = prediction.penalty_shootout
                projected_shootout = (shootout.get("top_scores") or [("5-4", 0.0)])[0][0]
                lines.append(
                    f"- Tanda de penales proyectada: {projected_shootout}"
                )
                lines.append(
                    f"- Promedio estimado de goles en la tanda: {prediction.team_a} {shootout.get('avg_score_a', 0.0):.2f} | "
                    f"{prediction.team_b} {shootout.get('avg_score_b', 0.0):.2f}"
                )
                lines.append(
                    "- Marcadores de penales mas probables: "
                    + ", ".join(
                        f"{score} {format_pct(prob)}" for score, prob in shootout.get("top_scores", [])
                    )
                )
        score_line = ", ".join(f"{score} {format_pct(prob)}" for score, prob in prediction.exact_scores)
        lines.append(f"- Marcadores mas probables: {score_line}")
        lines.append("")

    return "\n".join(lines)


def probability_rows(prediction: MatchPrediction) -> List[Tuple[str, float, str]]:
    return [
        (f"Victoria {prediction.team_a}", prediction.win_a, "a"),
        ("Empate", prediction.draw, "draw"),
        (f"Victoria {prediction.team_b}", prediction.win_b, "b"),
    ]


def pick_summary(prediction: MatchPrediction) -> Tuple[str, float]:
    options = [
        (f"Victoria {prediction.team_a}", prediction.win_a),
        ("Empate", prediction.draw),
        (f"Victoria {prediction.team_b}", prediction.win_b),
    ]
    return max(options, key=lambda item: item[1])


def confidence_tier(confidence: float) -> str:
    if confidence >= 0.90:
        return "Pick muy fuerte"
    if confidence >= 0.75:
        return "Pick fuerte"
    if confidence >= 0.60:
        return "Pick utilizable"
    return "Pronóstico parejo: sin favorito estadístico claro"


def statistical_depth_lines(prediction: MatchPrediction) -> List[str]:
    depth = prediction.statistical_depth or {}
    lines = []
    if not depth:
        return lines
    confidence = float(depth.get("confidence_index", 0.0))
    pick_label, pick_prob = pick_summary(prediction)
    both_score = float(depth.get("both_teams_score", 0.0))
    over_2_5 = float(depth.get("over_2_5", 0.0))
    top3_coverage = float(depth.get("top3_coverage", 0.0))
    clean_sheet_a = float(depth.get("clean_sheet_a", 0.0))
    clean_sheet_b = float(depth.get("clean_sheet_b", 0.0))
    market_gap = depth.get("market_gap")
    modal_margin = int(depth.get("modal_margin", 0))
    modal_margin_prob = float(depth.get("modal_margin_prob", 0.0))

    lines.append(
        f"- Diagnóstico estadístico: {confidence_tier(confidence)} | pick actual {pick_label} {format_pct(pick_prob)} | confianza {format_pct(confidence)}"
    )
    lines.append(
        f"- Produccion ofensiva esperada: ambos marcan {format_pct(both_score)} | over 2.5 {format_pct(over_2_5)}"
    )
    lines.append(
        f"- Probabilidad de que no reciba goles: {prediction.team_a} {format_pct(clean_sheet_a)} | {prediction.team_b} {format_pct(clean_sheet_b)}"
    )
    lines.append(
        f"- Probabilidad acumulada de los 3 marcadores mas probables: {format_pct(top3_coverage)} | diferencia de goles mas probable {modal_margin:+d} ({format_pct(modal_margin_prob)})"
    )
    if market_gap is not None:
        lines.append(f"- Diferencia promedio vs mercado de victoria/empate/derrota: {format_pct(float(market_gap))}")
    drivers = top_factor_drivers(prediction.factors, limit=3)
    if drivers:
        lines.append(
            "- Factores dominantes: "
            + "; ".join(f"{label} {value:+.3f}" for label, value in drivers)
        )
    return lines


def statistical_depth_html(prediction: MatchPrediction) -> str:
    depth = prediction.statistical_depth or {}
    if not depth:
        return ""
    confidence = float(depth.get("confidence_index", 0.0))
    pick_label, pick_prob = pick_summary(prediction)
    market_gap = depth.get("market_gap")
    market_html = ""
    if market_gap is not None:
        market_html = (
            f"<div><span>Diferencia vs mercado</span><strong>{format_pct(float(market_gap))}</strong></div>"
        )
    drivers = top_factor_drivers(prediction.factors, limit=3)
    drivers_html = ""
    if drivers:
        drivers_html = (
            "<p class=\"meta\"><strong>Factores dominantes:</strong> "
            + html.escape("; ".join(f"{label} {value:+.3f}" for label, value in drivers))
            + "</p>"
        )
    return (
        "<div class=\"depth-block\">"
        "<h4>Profundidad estadística</h4>"
        f"<p class=\"meta\"><strong>{html.escape(confidence_tier(confidence))}</strong> | pick actual: {html.escape(pick_label)} {format_pct(pick_prob)}</p>"
        "<div class=\"depth-grid\">"
        f"<div><span>Confianza del pronóstico</span><strong>{format_pct(confidence)}</strong></div>"
        f"<div><span>Ambos marcan</span><strong>{format_pct(float(depth.get('both_teams_score', 0.0)))}</strong></div>"
        f"<div><span>Over 2.5 goles</span><strong>{format_pct(float(depth.get('over_2_5', 0.0)))}</strong></div>"
        f"<div><span>Probabilidad acumulada del top-3 de marcadores</span><strong>{format_pct(float(depth.get('top3_coverage', 0.0)))}</strong></div>"
        f"<div><span>Prob. de que {html.escape(prediction.team_a)} no reciba goles</span><strong>{format_pct(float(depth.get('clean_sheet_a', 0.0)))}</strong></div>"
        f"<div><span>Prob. de que {html.escape(prediction.team_b)} no reciba goles</span><strong>{format_pct(float(depth.get('clean_sheet_b', 0.0)))}</strong></div>"
        f"<div><span>Diferencia de goles mas probable</span><strong>{int(depth.get('modal_margin', 0)):+d}</strong></div>"
        f"<div><span>Probabilidad de esa diferencia</span><strong>{format_pct(float(depth.get('modal_margin_prob', 0.0)))}</strong></div>"
        f"{market_html}"
        "</div>"
        f"{drivers_html}"
        "</div>"
    )


def build_global_confidence_markdown(entries: Sequence[dict]) -> List[str]:
    if not entries:
        return ["_Sin partidos cargados para calcular la lectura global del tablero._"]

    ranked = []
    ranked_market = []
    live_matches = 0
    for entry in entries:
        prediction: MatchPrediction = entry["prediction"]
        depth = prediction.statistical_depth or {}
        confidence = float(depth.get("confidence_index", 0.0))
        top3 = float(depth.get("top3_coverage", 0.0))
        ranked.append((confidence, top3, entry))
        market_gap = depth.get("market_gap")
        if market_gap is not None:
            ranked_market.append((abs(float(market_gap)), entry))
        if entry.get("status_state") == "in":
            live_matches += 1

    avg_confidence = sum(item[0] for item in ranked) / len(ranked)
    avg_top3 = sum(item[1] for item in ranked) / len(ranked)
    strongest = sorted(ranked, key=lambda item: item[0], reverse=True)[:3]
    most_open = sorted(ranked, key=lambda item: item[0])[:3]
    market_edges = sorted(ranked_market, key=lambda item: item[0], reverse=True)[:3]

    lines = [
        "- Que significa esta seccion: resume que tan claro o incierto esta el tablero hoy. No mide si el modelo es 'bueno' o 'malo' en abstracto; mide si los picks actuales salen con ventaja clara o si hay mucha dispersion entre escenarios.",
        f"- Certeza media del pick principal: {format_pct(avg_confidence)}",
        f"- Concentracion media de los 3 marcadores mas probables: {format_pct(avg_top3)}",
        f"- Partidos en vivo ahora mismo: {live_matches}",
        "- Como validar el refresh in-play: revisa la hora de publicacion de la portada, el badge 'En vivo', el minuto modelado y el archivo latest.json del sitio.",
    ]
    if strongest:
        lines.append(
            "- Picks con ventaja mas clara: "
            + "; ".join(f"{item[2]['title']} {format_pct(item[0])}" for item in strongest)
        )
    if most_open:
        lines.append(
            "- Partidos mas parejos: "
            + "; ".join(f"{item[2]['title']} {format_pct(item[0])}" for item in most_open)
        )
    group_metrics = {}
    for confidence, _, entry in ranked:
        stage_label = str(entry.get("stage_label", ""))
        if not stage_label.startswith("Grupo "):
            continue
        prediction: MatchPrediction = entry["prediction"]
        bucket = group_metrics.setdefault(
            stage_label,
            {"matches": 0, "confidence_sum": 0.0, "draw_sum": 0.0},
        )
        bucket["matches"] += 1
        bucket["confidence_sum"] += confidence
        bucket["draw_sum"] += float(prediction.draw)
    if group_metrics:
        group_rows = []
        for group_label, stats in group_metrics.items():
            avg_conf = stats["confidence_sum"] / max(stats["matches"], 1)
            avg_draw = stats["draw_sum"] / max(stats["matches"], 1)
            balance = (1.0 - avg_conf) * 0.65 + avg_draw * 0.35
            group_rows.append((group_label, avg_conf, avg_draw, balance, int(stats["matches"])))
        balanced_groups = sorted(group_rows, key=lambda row: (row[3], row[2]), reverse=True)
        favorite_groups = sorted(group_rows, key=lambda row: (row[1], -row[2]), reverse=True)
        lines.append(
            "- Grupos mas parejos: "
            + "; ".join(
                f"{label} | equilibrio {format_pct(balance)} | empate medio {format_pct(avg_draw)} | partidos {matches}"
                for label, avg_conf, avg_draw, balance, matches in balanced_groups
            )
        )
        lines.append(
            "- Grupos con favoritos mas claros: "
            + "; ".join(
                f"{label} | certeza media {format_pct(avg_conf)} | empate medio {format_pct(avg_draw)} | partidos {matches}"
                for label, avg_conf, avg_draw, balance, matches in favorite_groups
            )
        )
    if market_edges:
        lines.append(
            "- Mayor diferencia modelo vs mercado: "
            + "; ".join(f"{item[1]['title']} {format_pct(item[0])}" for item in market_edges)
        )
    return lines


def build_global_confidence_html(entries: Sequence[dict]) -> str:
    if not entries:
        return ""

    ranked = []
    ranked_market = []
    live_matches = 0
    for entry in entries:
        prediction: MatchPrediction = entry["prediction"]
        depth = prediction.statistical_depth or {}
        confidence = float(depth.get("confidence_index", 0.0))
        top3 = float(depth.get("top3_coverage", 0.0))
        ranked.append((confidence, top3, entry))
        market_gap = depth.get("market_gap")
        if market_gap is not None:
            ranked_market.append((abs(float(market_gap)), entry))
        if entry.get("status_state") == "in":
            live_matches += 1

    avg_confidence = sum(item[0] for item in ranked) / len(ranked)
    avg_top3 = sum(item[1] for item in ranked) / len(ranked)
    strongest = sorted(ranked, key=lambda item: item[0], reverse=True)[:4]
    most_open = sorted(ranked, key=lambda item: item[0])[:4]
    market_edges = sorted(ranked_market, key=lambda item: item[0], reverse=True)[:4]
    group_metrics = {}
    for confidence, _, entry in ranked:
        stage_label = str(entry.get("stage_label", ""))
        if not stage_label.startswith("Grupo "):
            continue
        prediction: MatchPrediction = entry["prediction"]
        bucket = group_metrics.setdefault(
            stage_label,
            {"matches": 0, "confidence_sum": 0.0, "draw_sum": 0.0},
        )
        bucket["matches"] += 1
        bucket["confidence_sum"] += confidence
        bucket["draw_sum"] += float(prediction.draw)

    def bullet_list(items: Sequence[Tuple[float, float, dict]], mode: str) -> str:
        rows = []
        for confidence, _, entry in items:
            prediction: MatchPrediction = entry["prediction"]
            favorite = max(
                (
                    (prediction.win_a, f"Victoria {prediction.team_a}"),
                    (prediction.draw, "Empate"),
                    (prediction.win_b, f"Victoria {prediction.team_b}"),
                ),
                key=lambda item: item[0],
            )
            tail = (
                f"Certeza del pick {format_pct(confidence)} | resultado mas probable {favorite[1]} {format_pct(favorite[0])}"
                if mode == "firm"
                else f"Certeza del pick {format_pct(confidence)} | duelo parejo"
            )
            rows.append(
                "<li>"
                f"<strong>{html.escape(entry['title'])}</strong>"
                f"<span>{html.escape(tail)}</span>"
                "</li>"
            )
        return "".join(rows)

    def market_list(items: Sequence[Tuple[float, dict]]) -> str:
        rows = []
        for gap, entry in items:
            rows.append(
                "<li>"
                f"<strong>{html.escape(entry['title'])}</strong>"
                f"<span>Diferencia media vs mercado {format_pct(gap)}</span>"
                "</li>"
            )
        return "".join(rows)

    def group_list(items: Sequence[Tuple[str, float, float, float, int]], mode: str) -> str:
        rows = []
        for group_label, avg_conf, avg_draw, balance, matches in items:
            if mode == "balanced":
                tail = f"Equilibrio {format_pct(balance)} | empate medio {format_pct(avg_draw)} | partidos {matches}"
            else:
                tail = f"Certeza media {format_pct(avg_conf)} | empate medio {format_pct(avg_draw)} | partidos {matches}"
            rows.append(
                "<li>"
                f"<strong>{html.escape(group_label)}</strong>"
                f"<span>{html.escape(tail)}</span>"
                "</li>"
            )
        return "".join(rows)

    group_closed_html = ""
    group_open_html = ""
    if group_metrics:
        group_rows = []
        for group_label, stats in group_metrics.items():
            avg_conf = stats["confidence_sum"] / max(stats["matches"], 1)
            avg_draw = stats["draw_sum"] / max(stats["matches"], 1)
            balance = (1.0 - avg_conf) * 0.65 + avg_draw * 0.35
            group_rows.append((group_label, avg_conf, avg_draw, balance, int(stats["matches"])))
        balanced_groups = sorted(group_rows, key=lambda row: (row[3], row[2]), reverse=True)
        favorite_groups = sorted(group_rows, key=lambda row: (row[1], -row[2]), reverse=True)
        group_closed_html = (
            "<article><h3>Grupos mas parejos</h3><ul>"
            f"{group_list(balanced_groups, 'balanced')}"
            "</ul></article>"
        )
        group_open_html = (
            "<article><h3>Grupos con favoritos mas claros</h3><ul>"
            f"{group_list(favorite_groups, 'favorite')}"
            "</ul></article>"
        )

    return (
        "<section class=\"panel confidence-panel\">"
        "<div class=\"panel-head\">"
        "<div>"
        "<p class=\"eyebrow\">Lectura global</p>"
        "<h2>Lectura global del tablero</h2>"
        "<p class=\"lede-tight\">Este bloque resume que tan claros estan los picks publicados, donde los partidos se ven mas parejos y en que zonas el modelo se separa mas del mercado. No es una nota de calidad del modelo; es una lectura de certeza e incertidumbre del tablero actual.</p>"
        "</div>"
        "</div>"
        "<div class=\"confidence-tiles\">"
        f"<div class=\"summary-tile\"><span>Certeza media del pick principal</span><strong>{format_pct(avg_confidence)}</strong></div>"
        f"<div class=\"summary-tile\"><span>Concentracion media de los 3 marcadores mas probables</span><strong>{format_pct(avg_top3)}</strong></div>"
        f"<div class=\"summary-tile\"><span>Partidos en vivo detectados</span><strong>{live_matches}</strong></div>"
        "<div class=\"summary-tile\"><span>Como comprobar actualizacion</span><strong><a href=\"latest.json\">latest.json</a> + badge En vivo + minuto modelado</strong></div>"
        "</div>"
        "<div class=\"confidence-grid\">"
        "<article><h3>Picks con ventaja mas clara</h3><ul>"
        f"{bullet_list(strongest, 'firm')}"
        "</ul></article>"
        "<article><h3>Partidos mas parejos</h3><ul>"
        f"{bullet_list(most_open, 'open')}"
        "</ul></article>"
        "<article><h3>Modelo vs mercado</h3><ul>"
        f"{market_list(market_edges) if market_edges else '<li><strong>Sin odds comparables</strong><span>Aun no llegaron cuotas utilizables del feed.</span></li>'}"
        "</ul></article>"
        f"{group_closed_html}"
        f"{group_open_html}"
        "</div>"
        "</section>"
    )


def bracket_stage_sections(bracket_payload: dict) -> List[Tuple[str, str, List[dict]]]:
    matches = bracket_payload.get("matches", {})
    stage_order = [
        ("round32", "Dieciseisavos"),
        ("round16", "Octavos"),
        ("quarterfinal", "Cuartos"),
        ("semifinal", "Semifinales"),
        ("final", "Final"),
        ("third_place", "Tercer puesto"),
    ]

    def match_order(item: Tuple[str, dict]) -> Tuple[int, str]:
        match_id = item[0]
        digits = "".join(char for char in str(match_id) if char.isdigit())
        return (int(digits), str(match_id)) if digits else (10**9, str(match_id))

    sections = []
    for stage_key, label in stage_order:
        stage_matches = [
            match for _, match in sorted(matches.items(), key=match_order) if match.get("stage") == stage_key
        ]
        if stage_matches:
            sections.append((stage_key, label, stage_matches))
    return sections


def build_bracket_visual_html(bracket_payload: dict) -> str:
    iterations = bracket_payload.get("iterations")
    sections = {stage_key: (label, stage_matches) for stage_key, label, stage_matches in bracket_stage_sections(bracket_payload)}

    def split_stage(stage_key: str) -> Tuple[List[dict], List[dict]]:
        stage_matches = sections.get(stage_key, ("", []))[1]
        midpoint = len(stage_matches) // 2
        return stage_matches[:midpoint], stage_matches[midpoint:]

    def build_match_card(match: dict) -> str:
        match_cards = []
        team_a = html.escape(match.get("team_a", "?"))
        team_b = html.escape(match.get("team_b", "?"))
        winner = html.escape(match.get("winner", "?"))

        extra_parts = []
        alternatives = match.get("top_scenarios", [])[1:]
        if alternatives:
            extra_parts.append(
                "<div class=\"mini\">"
                "<strong>Otros cruces que tambien aparecen:</strong> "
                + html.escape(
                    "; ".join(
                        f"{scenario['team_a']} vs {scenario['team_b']} | favorito {scenario['winner']} | escenario {format_pct(float(scenario['prob']))}"
                        for scenario in alternatives[:2]
                    )
                )
                + "</div>"
            )
        if match.get("stage") != "third_place":
            extra_parts.append(
                "<div class=\"mini\">"
                f"<strong>Prórroga:</strong> {format_pct(float(match.get('extra_time_prob', 0.0)))} | "
                f"<strong>Penales:</strong> {format_pct(float(match.get('penalties_prob', 0.0)))}"
                "</div>"
            )
        penalty_scores = match.get("top_penalty_scores", [])
        if penalty_scores:
            extra_parts.append(
                "<p class=\"mini penalty-note\"><strong>Si se define por penales:</strong> "
                + html.escape(
                    "; ".join(
                        f"{item['score']} ({format_pct(float(item['prob']))})"
                        for item in penalty_scores[:2]
                    )
                )
                + "</p>"
            )
        detail_html = ""
        if extra_parts:
            detail_html = (
                "<details class=\"bracket-extra\">"
                "<summary>Mas detalle</summary>"
                + "".join(extra_parts)
                + "</details>"
            )

        row_a_class = "team-row favorite" if match.get("winner") == match.get("team_a") else "team-row"
        row_b_class = "team-row favorite" if match.get("winner") == match.get("team_b") else "team-row"
        row_a_badge = "<span class=\"team-badge\">Favorito</span>" if "favorite" in row_a_class else ""
        row_b_badge = "<span class=\"team-badge\">Favorito</span>" if "favorite" in row_b_class else ""
        return (
            "<article class=\"bracket-match\">"
            f"<p class=\"match-kicker\">{html.escape(str(match.get('title', '')))}</p>"
            "<div class=\"match-teams\">"
            f"<div class=\"{row_a_class}\"><span class=\"team-name\">{team_a}</span>{row_a_badge}</div>"
            "<div class=\"team-divider\"></div>"
            f"<div class=\"{row_b_class}\"><span class=\"team-name\">{team_b}</span>{row_b_badge}</div>"
            "</div>"
            "<div class=\"bracket-pills\">"
            f"<span>Cruce {format_pct(float(match.get('matchup_prob', 0.0)))}</span>"
            f"<span>Avanza {winner} {format_pct(float(match.get('winner_prob', 0.0)))}</span>"
            "</div>"
            f"{detail_html}"
            "</article>"
        )

    def build_stage_column(side_class: str, stage_key: str, label: str, stage_matches: List[dict]) -> str:
        if not stage_matches:
            return ""
        return (
            f"<section class=\"bracket-column {side_class} stage-{html.escape(stage_key)}\">"
            f"<div class=\"stage-head\"><p class=\"stage-kicker\">Ronda</p><h3>{html.escape(label)}</h3></div>"
            f"<div class=\"stage-matches\">{''.join(build_match_card(match) for match in stage_matches)}</div>"
            "</section>"
        )

    left_round32, right_round32 = split_stage("round32")
    left_round16, right_round16 = split_stage("round16")
    left_quarterfinal, right_quarterfinal = split_stage("quarterfinal")
    left_semifinal, right_semifinal = split_stage("semifinal")
    final_matches = sections.get("final", ("Final", []))[1]
    third_place_matches = sections.get("third_place", ("Tercer puesto", []))[1]

    if not any([left_round32, right_round32, left_round16, right_round16, left_quarterfinal, right_quarterfinal, left_semifinal, right_semifinal, final_matches, third_place_matches]):
        return "<p class=\"meta\">No hay llave estructurada todavía.</p>"

    sections_html = [
        build_stage_column("left left-round32", "round32", "Dieciseisavos", left_round32),
        build_stage_column("left left-round16", "round16", "Octavos", left_round16),
        build_stage_column("left left-quarterfinal", "quarterfinal", "Cuartos", left_quarterfinal),
        build_stage_column("left left-semifinal", "semifinal", "Semifinales", left_semifinal),
        (
            "<section class=\"bracket-column center-column\">"
            "<div class=\"center-stack\">"
            f"{build_stage_column('center center-final', 'final', 'Final', final_matches)}"
            f"{build_stage_column('center center-third_place', 'third_place', 'Tercer puesto', third_place_matches)}"
            "</div>"
            "</section>"
        ),
        build_stage_column("right right-semifinal", "semifinal", "Semifinales", right_semifinal),
        build_stage_column("right right-quarterfinal", "quarterfinal", "Cuartos", right_quarterfinal),
        build_stage_column("right right-round16", "round16", "Octavos", right_round16),
        build_stage_column("right right-round32", "round32", "Dieciseisavos", right_round32),
    ]

    board_width = 1908
    board_height = 1210
    column_width = 196
    column_gap = 18
    head_total = 86
    card_height = 126
    center_stack_top = 362
    center_stack_gap = 180

    def column_x(index: int) -> float:
        return float(index * (column_width + column_gap))

    def left_edge(index: int) -> float:
        return column_x(index)

    def right_edge(index: int) -> float:
        return column_x(index) + column_width

    def stage_centers(count: int, top_padding: int, gap: int, stack_offset: int = 0) -> List[float]:
        centers = []
        base = stack_offset + head_total + top_padding + (card_height / 2.0)
        for idx in range(count):
            centers.append(base + idx * (card_height + gap))
        return centers

    left_r32_y = stage_centers(len(left_round32), 0, 14)
    left_r16_y = stage_centers(len(left_round16), 56, 74)
    left_qf_y = stage_centers(len(left_quarterfinal), 158, 230)
    left_sf_y = stage_centers(len(left_semifinal), 362, 500)
    right_r32_y = stage_centers(len(right_round32), 0, 14)
    right_r16_y = stage_centers(len(right_round16), 56, 74)
    right_qf_y = stage_centers(len(right_quarterfinal), 158, 230)
    right_sf_y = stage_centers(len(right_semifinal), 362, 500)
    final_y = stage_centers(len(final_matches), 0, 20, stack_offset=center_stack_top)
    third_y = stage_centers(len(third_place_matches), 0, 20, stack_offset=center_stack_top + head_total + card_height + center_stack_gap)

    def connector_path(x1: float, y1: float, x2: float, y2: float) -> str:
        mid = (x1 + x2) / 2.0
        return f"M {x1:.1f} {y1:.1f} H {mid:.1f} V {y2:.1f} H {x2:.1f}"

    svg_paths: List[str] = []

    def link_pairs(source_centers: Sequence[float], target_centers: Sequence[float], source_x: float, target_x: float) -> None:
        for idx, target_y in enumerate(target_centers):
            source_idx = idx * 2
            if source_idx + 1 >= len(source_centers):
                break
            svg_paths.append(f"<path class=\"bracket-link\" d=\"{connector_path(source_x, source_centers[source_idx], target_x, target_y)}\" />")
            svg_paths.append(f"<path class=\"bracket-link\" d=\"{connector_path(source_x, source_centers[source_idx + 1], target_x, target_y)}\" />")

    link_pairs(left_r32_y, left_r16_y, right_edge(0), left_edge(1))
    link_pairs(left_r16_y, left_qf_y, right_edge(1), left_edge(2))
    link_pairs(left_qf_y, left_sf_y, right_edge(2), left_edge(3))
    link_pairs(right_r32_y, right_r16_y, left_edge(8), right_edge(7))
    link_pairs(right_r16_y, right_qf_y, left_edge(7), right_edge(6))
    link_pairs(right_qf_y, right_sf_y, left_edge(6), right_edge(5))

    if left_sf_y and final_y:
        svg_paths.append(f"<path class=\"bracket-link bracket-link-strong\" d=\"{connector_path(right_edge(3), left_sf_y[0], left_edge(4), final_y[0])}\" />")
    if right_sf_y and final_y:
        svg_paths.append(f"<path class=\"bracket-link bracket-link-strong\" d=\"{connector_path(left_edge(5), right_sf_y[0], right_edge(4), final_y[0])}\" />")
    if left_sf_y and third_y:
        svg_paths.append(f"<path class=\"bracket-link bracket-link-secondary\" d=\"{connector_path(right_edge(3), left_sf_y[0], left_edge(4), third_y[0])}\" />")
    if right_sf_y and third_y:
        svg_paths.append(f"<path class=\"bracket-link bracket-link-secondary\" d=\"{connector_path(left_edge(5), right_sf_y[0], right_edge(4), third_y[0])}\" />")

    bracket_svg = (
        f"<svg class=\"bracket-svg\" viewBox=\"0 0 {board_width} {board_height}\" preserveAspectRatio=\"none\" aria-hidden=\"true\">"
        "<defs>"
        "<filter id=\"bracketGlow\" x=\"-20%\" y=\"-20%\" width=\"140%\" height=\"140%\">"
        "<feDropShadow dx=\"0\" dy=\"0\" stdDeviation=\"2.5\" flood-color=\"rgba(15,109,102,0.16)\"/>"
        "</filter>"
        "</defs>"
        f"{''.join(svg_paths)}"
        "</svg>"
    )

    subtitle = ""
    if iterations:
        subtitle = (
            f"<p class=\"lede-tight\">Llave Monte Carlo dinámica con {int(iterations)} iteraciones publicadas. "
            "El cuadro se abre en dos ramas y converge hacia la final. Cada cruce muestra la combinación que más aparece hoy en esa zona; si la probabilidad del cruce es baja, esa parte de la llave sigue abierta y puede cambiar con resultados reales.</p>"
        )
    return (
        "<section class=\"panel bracket-panel\">"
        "<div class=\"panel-head\">"
        "<div>"
        "<p class=\"eyebrow\">Hoja de Ruta</p>"
        "<h2>Llave Proyectada</h2>"
        f"{subtitle}"
        "</div>"
        "</div>"
        "<div class=\"bracket-shell\">"
        "<div class=\"bracket-canvas\">"
        f"{bracket_svg}"
        "<div class=\"bracket-grid bracket-board\">"
        f"{''.join(sections_html)}"
        "</div>"
        "</div>"
        "</div>"
        "</section>"
    )


def build_backtesting_markdown(backtest: dict) -> List[str]:
    if not backtest or not backtest.get("completed_matches"):
        return ["_Sin partidos cerrados todavia para calibracion historica y backtesting._"]

    lines = [
        f"- Partidos cerrados analizados: {int(backtest.get('completed_matches', 0))}",
        f"- Muestra evaluable en tiempo reglamentario: {int(backtest.get('regular_time_samples', 0))}",
    ]
    if backtest.get("favorite_hit_rate") is not None:
        lines.append(f"- Tasa de acierto del resultado mas probable: {format_pct(float(backtest['favorite_hit_rate']))}")
    if backtest.get("top1_score_hit_rate") is not None:
        lines.append(f"- Acierto exacto del marcador mas probable: {format_pct(float(backtest['top1_score_hit_rate']))}")
    if backtest.get("top3_score_hit_rate") is not None:
        lines.append(f"- Acierto del marcador dentro del top-3: {format_pct(float(backtest['top3_score_hit_rate']))}")
    if backtest.get("logloss_result") is not None:
        lines.append(f"- Log-loss resultado: {float(backtest['logloss_result']):.3f}")
    if backtest.get("brier_result") is not None:
        lines.append(f"- Brier resultado: {float(backtest['brier_result']):.3f}")
    if backtest.get("logloss_advance") is not None:
        lines.append(f"- Log-loss clasificacion en knockout: {float(backtest['logloss_advance']):.3f}")
    if backtest.get("brier_advance") is not None:
        lines.append(f"- Brier clasificacion en knockout: {float(backtest['brier_advance']):.3f}")
    if backtest.get("market_logloss_result") is not None:
        lines.append(f"- Log-loss de mercado en esos mismos partidos: {float(backtest['market_logloss_result']):.3f}")
    buckets = backtest.get("calibration_buckets") or []
    if buckets:
        lines.append(
            "- Calibracion por buckets: "
            + "; ".join(
                f"{bucket['bucket']} -> confianza media {format_pct(float(bucket['avg_confidence']))}, acierto real {format_pct(float(bucket['hit_rate']))}, n={int(bucket['matches'])}"
                for bucket in buckets
            )
        )
    return lines


def build_backtesting_html(backtest: dict) -> str:
    if not backtest or not backtest.get("completed_matches"):
        return (
            "<section class=\"panel backtest-panel\">"
            "<div class=\"panel-head\"><div><p class=\"eyebrow\">Validacion</p><h2>Calibracion historica y backtesting</h2>"
            "<p class=\"lede-tight\">Todavia no hay partidos cerrados suficientes en el torneo para medir calibracion real. Esta seccion se llenara sola cuando existan resultados.</p>"
            "</div></div></section>"
        )

    metrics = []
    def tile(label: str, value: str) -> str:
        return f"<div class=\"summary-tile\"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>"

    metrics.append(tile("Partidos cerrados", str(int(backtest.get("completed_matches", 0)))))
    metrics.append(tile("Muestra en reglamentario", str(int(backtest.get("regular_time_samples", 0)))))
    if backtest.get("favorite_hit_rate") is not None:
        metrics.append(tile("Acierto del pick principal", format_pct(float(backtest["favorite_hit_rate"]))))
    if backtest.get("top3_score_hit_rate") is not None:
        metrics.append(tile("Marcador dentro del top-3", format_pct(float(backtest["top3_score_hit_rate"]))))

    quality_rows = []
    if backtest.get("logloss_result") is not None:
        quality_rows.append(f"<li><strong>Log-loss resultado</strong><span>{float(backtest['logloss_result']):.3f}</span></li>")
    if backtest.get("brier_result") is not None:
        quality_rows.append(f"<li><strong>Brier resultado</strong><span>{float(backtest['brier_result']):.3f}</span></li>")
    if backtest.get("logloss_advance") is not None:
        quality_rows.append(f"<li><strong>Log-loss clasificacion</strong><span>{float(backtest['logloss_advance']):.3f}</span></li>")
    if backtest.get("brier_advance") is not None:
        quality_rows.append(f"<li><strong>Brier clasificacion</strong><span>{float(backtest['brier_advance']):.3f}</span></li>")
    if backtest.get("market_logloss_result") is not None:
        quality_rows.append(f"<li><strong>Log-loss mercado</strong><span>{float(backtest['market_logloss_result']):.3f}</span></li>")

    calibration_rows = []
    for bucket in backtest.get("calibration_buckets", []):
        calibration_rows.append(
            "<li>"
            f"<strong>{html.escape(bucket['bucket'])}</strong>"
            f"<span>confianza media {format_pct(float(bucket['avg_confidence']))} | acierto real {format_pct(float(bucket['hit_rate']))} | n={int(bucket['matches'])}</span>"
            "</li>"
        )

    return (
        "<section class=\"panel backtest-panel\">"
        "<div class=\"panel-head\"><div><p class=\"eyebrow\">Validacion</p><h2>Calibracion historica y backtesting</h2>"
        "<p class=\"lede-tight\">Se reconstruye el torneo partido por partido en orden cronologico, pronosticando antes de aplicar cada resultado real. Asi se mide si el modelo estuvo bien calibrado de verdad.</p>"
        "</div></div>"
        f"<div class=\"confidence-tiles\">{''.join(metrics)}</div>"
        "<div class=\"confidence-grid\">"
        "<article><h3>Calidad predictiva</h3><ul>"
        f"{''.join(quality_rows) if quality_rows else '<li><strong>Sin muestra suficiente</strong><span>Aun no hay datos comparables.</span></li>'}"
        "</ul></article>"
        "<article><h3>Calibracion por buckets</h3><ul>"
        f"{''.join(calibration_rows) if calibration_rows else '<li><strong>Sin buckets</strong><span>Aun no hay suficientes partidos.</span></li>'}"
        "</ul></article>"
        "</div>"
        "</section>"
    )


def build_methodology_html(bracket_payload: dict, backtest: dict) -> str:
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    montecarlo_line = f"{iterations} iteraciones" if iterations else "iteraciones variables"
    return (
        "<section class=\"panel methodology\">"
        "<div class=\"panel-head\">"
        "<div>"
        "<p class=\"eyebrow\">Cómo Leer Esto</p>"
        "<h2>Profundidad Estadística</h2>"
        "<p class=\"lede-tight\">El modelo ya es robusto para quiniela. Más que agregar proxies nuevos, lo que más aporta ahora es calibración, backtesting y mejores feeds en vivo.</p>"
        "</div>"
        "</div>"
        "<div class=\"method-grid\">"
        "<article>"
        "<h3>Partido a partido</h3>"
        "<p>Usa Poisson bivariante para estimar el marcador final y probabilidades de victoria, empate y derrota.</p>"
        "</article>"
        "<article>"
        "<h3>Cuadro completo</h3>"
        f"<p>La llave publicada se construye con Monte Carlo dinámico y {html.escape(montecarlo_line)} para reducir ruido de simulación.</p>"
        "</article>"
        "<article>"
        "<h3>Estado dinámico</h3>"
        "<p>Actualiza Elo, forma, fatiga, disponibilidad, disciplina, clima, alineaciones, bajas y mercado a medida que aparecen datos nuevos. Ademas, acumula una firma tactica reciente por seleccion a partir de sus partidos previos para no arrancar cada cruce desde cero. Los puntos FIFA entran como señal estructural secundaria; si no los cargas de forma explícita, el modelo usa un proxy calibrado.</p>"
        "</article>"
        "<article>"
        "<h3>Modo in-play</h3>"
        "<p>Durante un partido, condiciona las probabilidades por minuto, marcador actual y fase del juego. Ademas, cuando el feed lo trae, suma tiros, tiros al arco, posesion, xG live o proxy, corners, disciplina y expulsiones para recalcular probabilidades, marcadores finales mas probables y patrones de juego como dominio territorial, transicion vertical o control esteril.</p>"
        "</article>"
        "<article>"
        "<h3>Noticias y bajas</h3>"
        "<p>Si el feed publica ausencias, cambios de XI o noticias relevantes del partido, esas señales entran como disponibilidad, moral o contexto adicional.</p>"
        "</article>"
        "<article>"
        "<h3>Como validar el refresh</h3>"
        "<p>La portada publica hora de actualizacion, badge En vivo, minuto modelado y un latest.json. Si esos campos cambian, el in-play se esta recalculando bien.</p>"
        "</article>"
        "</div>"
        f"<p class=\"lede-tight\">Backtesting actual: {html.escape(str(int(backtest.get('completed_matches', 0))))} partidos cerrados reconstruidos secuencialmente.</p>"
        "</section>"
    )


def build_dashboard_html(
    entries: Sequence[dict],
    bracket_text: str,
    bracket_payload: dict,
    backtest: dict,
    state_path: Path,
    fixtures_path: Path,
) -> str:
    cards = []
    for entry in entries:
        prediction: MatchPrediction = entry["prediction"]
        status_class, status_text = dashboard_status(entry)
        status_html = f"<p class=\"badge {status_class}\">{html.escape(status_text)}</p>"
        probability_rows_html = "".join(
            (
                "<div class=\"prob-row\">"
                f"<div class=\"prob-label\">{html.escape(label)}</div>"
                f"<div class=\"prob-bar\"><span class=\"prob-fill {row_class}\" style=\"width:{prob * 100:.1f}%\"></span></div>"
                f"<div class=\"prob-value\">{format_pct(prob)}</div>"
                "</div>"
            )
            for label, prob, row_class in probability_rows(prediction)
        )
        result_html = ""
        if entry["actual_score_a"] is not None and entry["actual_score_b"] is not None:
            result_text = f"Resultado real: {prediction.team_a} {entry['actual_score_a']} - {entry['actual_score_b']} {prediction.team_b}"
            if entry["went_penalties"]:
                result_text += f" | penales: {entry['penalties_winner']}"
            elif entry["went_extra_time"]:
                result_text += " | con proroga"
            result_html = f"<p class=\"meta\">{html.escape(result_text)}</p>"
        elif entry.get("live_score_a") is not None and entry.get("live_score_b") is not None:
            result_html = (
                f"<p class=\"meta\">En vivo: {html.escape(prediction.team_a)} {entry['live_score_a']} - "
                f"{entry['live_score_b']} {html.escape(prediction.team_b)}</p>"
            )
        else:
            result_html = ""

        venue_html = ""
        if entry.get("kickoff_utc") or entry.get("venue_name"):
            venue_bits = [entry.get("venue_name"), entry.get("venue_country")]
            venue_bits = [bit for bit in venue_bits if bit]
            venue_html = (
                f"<p class=\"meta\">{html.escape(' | '.join(venue_bits))}</p>"
                f"<p class=\"meta\">UTC: {html.escape(str(entry.get('kickoff_utc', '')))}</p>"
            )
        minute_html = ""
        if prediction.elapsed_minutes is not None:
            minute_html = f"<p class=\"meta\">Minuto modelado: {prediction.elapsed_minutes:.1f}</p>"

        weather_html = ""
        if entry.get("weather_summary"):
            weather_html = f"<p class=\"meta\">Clima: {html.escape(entry['weather_summary'])}</p>"

        officiating_html = ""
        if entry.get("referee"):
            officiating_html = f"<p class=\"meta\">Arbitro: {html.escape(str(entry['referee']))}</p>"

        market_html = ""
        if entry.get("market_summary"):
            market_text = entry["market_summary"]
            if entry.get("market_provider"):
                market_text = f"{entry['market_provider']}: {market_text}"
            market_html += f"<p class=\"meta\">Odds: {html.escape(market_text)}</p>"
        if entry.get("market_prob_a") is not None:
            market_html += (
                f"<p class=\"meta\">Prior de mercado (victoria/empate/derrota): {html.escape(prediction.team_a)} {format_pct(float(entry['market_prob_a']))} | "
                f"empate {format_pct(float(entry.get('market_prob_draw', 0.0)))} | "
                f"{html.escape(prediction.team_b)} {format_pct(float(entry.get('market_prob_b', 0.0)))}</p>"
            )

        lineup_html = ""
        if entry.get("lineup_status_a") or entry.get("lineup_status_b"):
            lineup_html += (
                f"<p class=\"meta\">Alineaciones: {html.escape(prediction.team_a)} {html.escape(str(entry.get('lineup_status_a', 'sin confirmar')))} | "
                f"{html.escape(prediction.team_b)} {html.escape(str(entry.get('lineup_status_b', 'sin confirmar')))}</p>"
            )
        if entry.get("lineup_change_count_a") or entry.get("lineup_change_count_b"):
            lineup_html += (
                f"<p class=\"meta\">Cambios XI: {html.escape(prediction.team_a)} {entry.get('lineup_change_count_a', 0)} | "
                f"{html.escape(prediction.team_b)} {entry.get('lineup_change_count_b', 0)}</p>"
            )

        absence_html = ""
        for line in dashboard_absence_lines(entry, prediction.team_a, prediction.team_b):
            absence_html += f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"

        news_html = ""
        for line in dashboard_news_lines(entry, prediction.team_a, prediction.team_b):
            news_html += f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"
        tactical_signature_html = ""
        for line in dashboard_tactical_signature_lines(entry, prediction.team_a, prediction.team_b):
            tactical_signature_html += f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"
        live_stats_html = ""
        for line in dashboard_live_stats_lines(entry, prediction.team_a, prediction.team_b):
            live_stats_html += f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"
        pattern_html = ""
        pattern_lines = dashboard_pattern_lines(prediction)
        if pattern_lines:
            pattern_html = (
                "<div class=\"reason-block\"><h4>Patrones de juego detectados</h4>"
                + "".join(
                    f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"
                    for line in pattern_lines
                )
                + "</div>"
            )

        reason_html = ""
        reason_lines = adjustment_reason_lines(entry, prediction)
        if reason_lines:
            reason_html = (
                "<div class=\"reason-block\"><h4>Por que cambia el pronostico</h4>"
                + "".join(
                    f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"
                    for line in reason_lines
                )
                + "</div>"
            )
        next_round_html = ""
        next_round_note = next_round_projection_note(entry, prediction, bracket_payload)
        if next_round_note:
            next_round_html = (
                "<div class=\"reason-block\"><h4>Siguiente cruce del ganador real</h4>"
                f"<p class=\"meta\">{html.escape(next_round_note)}</p>"
                "</div>"
            )

        projection_html = ""
        if entry.get("projection"):
            projection_html = f"<p class=\"meta\">{html.escape(entry.get('projection_note', ''))}</p>"
            alternatives = entry.get("projection_alternatives") or []
            if alternatives:
                projection_html += (
                    "<p class=\"meta\">Otras rutas probables: "
                    + html.escape(
                        "; ".join(
                            f"{scenario['team_a']} vs {scenario['team_b']} -> {scenario['winner']} {format_pct(float(scenario['prob']))}"
                            for scenario in alternatives
                        )
                    )
                    + "</p>"
                )
        depth_html = statistical_depth_html(prediction)

        knockout_html = ""
        if prediction.advance_a is not None and prediction.advance_b is not None:
            detail = prediction.knockout_detail or {}
            shootout_html = ""
            if prediction.penalty_shootout:
                projected_shootout = ((prediction.penalty_shootout.get("top_scores") or [("5-4", 0.0)])[0][0])
                shootout_scores = "".join(
                    f"<li><strong>{html.escape(score)}</strong><span>{format_pct(prob)}</span></li>"
                    for score, prob in prediction.penalty_shootout.get("top_scores", [])
                )
                shootout_html = (
                    f"<div><span>Tanda de penales proyectada</span><strong>{html.escape(projected_shootout)}</strong></div>"
                    f"<div><span>Promedio estimado de goles en penales</span><strong>{prediction.team_a} {prediction.penalty_shootout.get('avg_score_a', 0.0):.2f} | "
                    f"{prediction.team_b} {prediction.penalty_shootout.get('avg_score_b', 0.0):.2f}</strong></div>"
                    "<div class=\"scores\"><h4>Marcadores de penales mas probables</h4>"
                    f"<ul>{shootout_scores}</ul></div>"
                )
            knockout_html = (
                "<div class=\"subgrid\">"
                f"<div><span>Clasificar</span><strong>{html.escape(prediction.team_a)} {format_pct(prediction.advance_a)} | "
                f"{html.escape(prediction.team_b)} {format_pct(prediction.advance_b)}</strong></div>"
                f"<div><span>Proroga si empatan</span><strong>{html.escape(prediction.team_a)} {format_pct(detail.get('et_win_a', 0.0))} | "
                f"seguir empatados {format_pct(detail.get('et_draw', 0.0))} | {html.escape(prediction.team_b)} {format_pct(detail.get('et_win_b', 0.0))}</strong></div>"
                f"<div><span>Penales si llegan</span><strong>{html.escape(prediction.team_a)} {format_pct(detail.get('penalties_a', 0.0))} | "
                f"{html.escape(prediction.team_b)} {format_pct(detail.get('penalties_b', 0.0))}</strong></div>"
                f"{shootout_html}"
                "</div>"
            )

        top_scores_html = "".join(
            f"<li><strong>{html.escape(score)}</strong><span>{format_pct(prob)}</span></li>"
            for score, prob in prediction.exact_scores
        )
        remaining_goals_html = ""
        if prediction.expected_remaining_goals_a is not None and prediction.expected_remaining_goals_b is not None:
            remaining_goals_html = (
                f"<p class=\"meta\">Promedio estimado de goles restantes: {html.escape(prediction.team_a)} {prediction.expected_remaining_goals_a:.2f} | "
                f"{html.escape(prediction.team_b)} {prediction.expected_remaining_goals_b:.2f}</p>"
            )
        average_goals_html = ""
        if prediction.live_phase != "penalties":
            average_goals_html = (
                f"<p class=\"meta\">{html.escape(average_goals_label(prediction))}: "
                f"{html.escape(prediction.team_a)} {prediction.expected_goals_a:.2f} | "
                f"{html.escape(prediction.team_b)} {prediction.expected_goals_b:.2f}</p>"
            )
        cards.append(
            "<section class=\"card\">"
            f"{status_html}"
            f"<h3>{html.escape(entry['title'])}</h3>"
            f"<p class=\"meta\">{html.escape(entry['stage_label'])}</p>"
            f"{result_html}"
            f"{venue_html}"
            f"{minute_html}"
            f"{weather_html}"
            f"{officiating_html}"
            f"{market_html}"
            f"{lineup_html}"
            f"{absence_html}"
            f"{news_html}"
            f"{tactical_signature_html}"
            f"{live_stats_html}"
            f"{pattern_html}"
            f"{reason_html}"
            f"{next_round_html}"
            f"{projection_html}"
            "<div class=\"hero-metrics\">"
            f"<div class=\"metric metric-score\"><span>{html.escape(projected_score_label(prediction))}</span><strong>{html.escape(projected_score_value(prediction))}</strong></div>"
            f"<div class=\"metric metric-probs\"><span>{html.escape(result_prob_label(prediction))}</span><strong>{html.escape(prediction.team_a)} / Empate / {html.escape(prediction.team_b)}</strong></div>"
            "</div>"
            f"{average_goals_html}"
            f"<div class=\"prob-block\">{probability_rows_html}</div>"
            f"{remaining_goals_html}"
            f"{depth_html}"
            f"{knockout_html}"
            "<div class=\"scores\">"
            "<h4>Marcadores finales mas probables</h4>"
            f"<ul>{top_scores_html}</ul>"
            "</div>"
            "</section>"
        )

    if not cards:
        cards.append("<section class=\"card\"><h3>Sin partidos cargados</h3><p class=\"meta\">Agrega partidos a fixtures_template.json para ver probabilidades aqui.</p></section>")

    bracket_html = html.escape(bracket_text.strip() or "No hay llave generada todavia.")
    bracket_visual_html = build_bracket_visual_html(bracket_payload)
    methodology_html = build_methodology_html(bracket_payload, backtest)
    global_confidence_html = build_global_confidence_html(entries)
    backtesting_html = build_backtesting_html(backtest)
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dashboard Mundial 2026</title>
  <style>
    :root {{
      --bg: #f4efe2;
      --panel: rgba(255, 253, 246, 0.92);
      --panel-strong: #fffaf0;
      --ink: #182126;
      --muted: #5a676b;
      --line: rgba(184, 160, 109, 0.34);
      --accent: #0f6d66;
      --accent-dark: #0a4e49;
      --accent-soft: rgba(15, 109, 102, 0.10);
      --gold: #b5832f;
      --gold-soft: rgba(181, 131, 47, 0.12);
      --rose: #b0473c;
      --shadow: 0 20px 45px rgba(49, 40, 23, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15,109,102,0.16), transparent 24%),
        radial-gradient(circle at top right, rgba(181,131,47,0.14), transparent 22%),
        linear-gradient(180deg, #f8f3e8 0%, #eedfc4 100%);
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px 14px 56px;
    }}
    h1, h2, h3, h4 {{ margin: 0; }}
    h1 {{ font-size: clamp(2.2rem, 5vw, 3.6rem); line-height: 0.95; margin-bottom: 10px; }}
    h2 {{ font-size: clamp(1.4rem, 3vw, 2rem); }}
    h3 {{ font-size: 1.05rem; }}
    .lede {{ color: var(--muted); margin: 0; max-width: 60ch; font-size: 1.02rem; }}
    .lede-tight {{ color: var(--muted); margin: 8px 0 0; max-width: 58ch; }}
    .eyebrow {{
      margin: 0 0 10px;
      color: var(--accent-dark);
      text-transform: uppercase;
      letter-spacing: 0.16em;
      font-size: 0.75rem;
      font-weight: 700;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      backdrop-filter: blur(12px);
      border-radius: 24px;
      padding: 18px;
      box-shadow: var(--shadow);
      margin-bottom: 18px;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      background:
        linear-gradient(135deg, rgba(15, 109, 102, 0.94), rgba(10, 78, 73, 0.92)),
        linear-gradient(180deg, #0f6d66 0%, #0a4e49 100%);
      color: #f7f3ea;
      padding: 26px 22px;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -60px -70px auto;
      width: 220px;
      height: 220px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
    }}
    .hero .eyebrow,
    .hero .lede,
    .hero .meta,
    .hero .lede-tight {{
      color: rgba(247, 243, 234, 0.86);
    }}
    .hero-grid {{
      display: grid;
      gap: 18px;
      grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr);
      position: relative;
      z-index: 1;
    }}
    .summary-grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 18px;
    }}
    .summary-tile {{
      background: rgba(255,255,255,0.09);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 18px;
      padding: 14px;
    }}
    .summary-tile span {{
      color: rgba(247, 243, 234, 0.72);
      font-size: 0.72rem;
      margin-bottom: 6px;
    }}
    .summary-tile strong {{
      font-size: 1.05rem;
      color: #fffdf7;
    }}
    .hero-notes {{
      display: grid;
      gap: 12px;
    }}
    .hero-note {{
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.10);
      border-radius: 18px;
      padding: 14px;
    }}
    .hero-note h3 {{
      margin-bottom: 8px;
      font-size: 1rem;
    }}
    .hero-note p {{
      margin: 0;
      color: rgba(247, 243, 234, 0.84);
      line-height: 1.45;
      font-size: 0.95rem;
    }}
    .panel-head {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: start;
      margin-bottom: 14px;
    }}
    .meta {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.4;
    }}
    .badge {{
      display: inline-block;
      margin: 0 0 10px;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #fff;
    }}
    .badge.live {{ background: #c0392b; }}
    .badge.final {{ background: #355c3a; }}
    .badge.pending {{ background: #7d6a43; }}
    .badge.projection {{ background: #0f6d66; }}
    .bracket-panel {{
      padding-bottom: 22px;
    }}
    .bracket-shell {{
      position: relative;
      overflow-x: auto;
      padding: 8px 4px 12px;
      margin: 0 -4px;
    }}
    .bracket-canvas {{
      --bracket-col: 196px;
      --bracket-gap: 18px;
      --bracket-board-width: 1908px;
      --bracket-board-height: 1210px;
      position: relative;
      width: var(--bracket-board-width);
      min-width: var(--bracket-board-width);
      min-height: var(--bracket-board-height);
    }}
    .bracket-svg {{
      position: absolute;
      inset: 0;
      width: var(--bracket-board-width);
      height: var(--bracket-board-height);
      pointer-events: none;
      z-index: 0;
      overflow: visible;
    }}
    .bracket-link {{
      fill: none;
      stroke: rgba(15, 109, 102, 0.34);
      stroke-width: 3;
      stroke-linecap: round;
      stroke-linejoin: round;
      filter: url(#bracketGlow);
    }}
    .bracket-link-strong {{
      stroke: rgba(181, 131, 47, 0.62);
      stroke-width: 3.6;
    }}
    .bracket-link-secondary {{
      stroke: rgba(15, 109, 102, 0.20);
      stroke-dasharray: 7 8;
    }}
    .bracket-board {{
      position: relative;
      z-index: 1;
      display: grid;
      gap: 18px;
      grid-template-columns: repeat(9, var(--bracket-col));
      width: var(--bracket-board-width);
      min-width: var(--bracket-board-width);
      min-height: var(--bracket-board-height);
      align-items: start;
    }}
    .bracket-column {{
      position: relative;
      min-width: 0;
      grid-row: 1;
    }}
    .left-round32 {{ grid-column: 1; }}
    .left-round16 {{ grid-column: 2; }}
    .left-quarterfinal {{ grid-column: 3; }}
    .left-semifinal {{ grid-column: 4; }}
    .center-column {{ grid-column: 5; }}
    .right-semifinal {{ grid-column: 6; }}
    .right-quarterfinal {{ grid-column: 7; }}
    .right-round16 {{ grid-column: 8; }}
    .right-round32 {{ grid-column: 9; }}
    .stage-head {{
      margin-bottom: 14px;
      padding: 12px 14px;
      border-radius: 16px;
      background: linear-gradient(180deg, rgba(15,109,102,0.12), rgba(255,255,255,0.72));
      border: 1px solid rgba(15,109,102,0.14);
      box-shadow: 0 10px 24px rgba(12, 41, 45, 0.08);
    }}
    .stage-kicker {{
      margin: 0 0 4px;
      color: var(--accent-dark);
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
    }}
    .stage-head h3 {{
      margin: 0;
      font-size: 1.05rem;
    }}
    .stage-matches {{
      display: flex;
      flex-direction: column;
      position: relative;
    }}
    .left-round32 .stage-matches,
    .right-round32 .stage-matches {{
      gap: 14px;
    }}
    .left-round16 .stage-matches,
    .right-round16 .stage-matches {{
      gap: 74px;
      padding-top: 56px;
    }}
    .left-quarterfinal .stage-matches,
    .right-quarterfinal .stage-matches {{
      gap: 230px;
      padding-top: 158px;
    }}
    .left-semifinal .stage-matches,
    .right-semifinal .stage-matches {{
      gap: 500px;
      padding-top: 362px;
    }}
    .center-stack {{
      display: flex;
      flex-direction: column;
      gap: 232px;
      padding-top: 320px;
    }}
    .center-final .stage-matches,
    .center-third_place .stage-matches {{
      gap: 20px;
    }}
    .bracket-match {{
      min-height: 126px;
      padding: 12px 12px 14px;
      border-radius: 14px;
      background: linear-gradient(180deg, rgba(255,253,246,0.99), rgba(245,239,225,0.97));
      border: 1px solid rgba(15,109,102,0.14);
      box-shadow: 0 14px 24px rgba(12, 41, 45, 0.09);
    }}
    .match-teams {{
      display: grid;
      gap: 0;
      margin-bottom: 10px;
      border: 1px solid rgba(15,109,102,0.10);
      border-radius: 12px;
      overflow: hidden;
    }}
    .match-kicker {{
      margin: 0 0 4px;
      color: var(--accent-dark);
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
    }}
    .team-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 10px 12px;
      background: rgba(255,255,255,0.68);
    }}
    .team-row.favorite {{
      background: linear-gradient(90deg, rgba(15,109,102,0.12), rgba(255,255,255,0.90));
    }}
    .team-name {{
      display: block;
      margin: 0;
      color: var(--ink);
      font-size: 0.96rem;
      font-weight: 700;
      text-transform: none;
      letter-spacing: 0;
      line-height: 1.2;
    }}
    .team-divider {{
      height: 1px;
      background: rgba(15,109,102,0.10);
    }}
    .team-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 4px 8px;
      border-radius: 999px;
      background: rgba(15,109,102,0.12);
      color: var(--accent-dark);
      font-size: 0.70rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin: 0;
    }}
    .bracket-pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin-top: 8px;
    }}
    .bracket-pills span {{
      margin: 0;
      padding: 5px 9px;
      border-radius: 999px;
      background: rgba(15,109,102,0.08);
      border: 1px solid rgba(15,109,102,0.12);
      color: var(--accent-dark);
      font-size: 0.73rem;
      font-weight: 700;
      text-transform: none;
      letter-spacing: 0;
    }}
    .mini {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 0.80rem;
      line-height: 1.35;
    }}
    .penalty-note {{
      margin-top: 6px;
    }}
    .bracket-extra {{
      margin-top: 10px;
      border-top: 1px dashed rgba(15,109,102,0.16);
      padding-top: 6px;
    }}
    .bracket-extra summary {{
      cursor: pointer;
      color: var(--accent-dark);
      font-size: 0.76rem;
      font-weight: 700;
      list-style: none;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .bracket-extra summary::-webkit-details-marker {{
      display: none;
    }}
    .method-grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }}
    .method-grid article {{
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,0.65), rgba(15,109,102,0.05));
      border: 1px solid var(--line);
      padding: 14px;
    }}
    .method-grid p {{
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.45;
    }}
    .confidence-panel a {{
      color: var(--accent-dark);
      text-decoration: none;
      border-bottom: 1px dashed currentColor;
    }}
    .confidence-tiles {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      margin-bottom: 14px;
    }}
    .confidence-grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }}
    .confidence-grid article {{
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,0.68), rgba(181,131,47,0.05));
      border: 1px solid var(--line);
      padding: 14px;
    }}
    .confidence-grid ul {{
      list-style: none;
      padding: 0;
      margin: 12px 0 0;
      display: grid;
      gap: 10px;
    }}
    .confidence-grid li {{
      border-bottom: 1px dashed var(--line);
      padding-bottom: 8px;
    }}
    .confidence-grid li span {{
      text-transform: none;
      letter-spacing: 0;
      margin-top: 4px;
      margin-bottom: 0;
      font-size: 0.84rem;
    }}
    .confidence-panel .summary-tile {{
      background: linear-gradient(180deg, rgba(255,255,255,0.76), rgba(15,109,102,0.06));
      border: 1px solid var(--line);
    }}
    .confidence-panel .summary-tile span {{
      color: var(--muted);
    }}
    .confidence-panel .summary-tile strong {{
      color: var(--ink);
      font-size: 1rem;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
    }}
    .card {{
      background: linear-gradient(180deg, rgba(255,253,246,0.97), rgba(251,246,234,0.94));
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 18px;
      box-shadow: var(--shadow);
    }}
    .hero-metrics, .subgrid {{
      display: grid;
      gap: 12px;
      margin-top: 12px;
    }}
    .hero-metrics {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .metric, .subgrid div {{
      background: rgba(15,109,102,0.07);
      border-radius: 16px;
      padding: 12px 14px;
      border: 1px solid rgba(15,109,102,0.08);
    }}
    span {{
      display: block;
      color: var(--muted);
      font-size: 0.82rem;
      margin-bottom: 3px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    strong {{
      font-size: 1rem;
    }}
    .prob-block {{
      margin-top: 14px;
      display: grid;
      gap: 10px;
    }}
    .prob-row {{
      display: grid;
      gap: 10px;
      align-items: center;
      grid-template-columns: minmax(92px, 1fr) minmax(100px, 2.3fr) auto;
    }}
    .prob-label {{
      font-size: 0.88rem;
      color: var(--muted);
    }}
    .prob-bar {{
      height: 10px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(24, 33, 38, 0.10);
    }}
    .prob-fill {{
      display: block;
      height: 100%;
      border-radius: 999px;
    }}
    .prob-fill.a {{ background: linear-gradient(90deg, var(--accent), #14a39a); }}
    .prob-fill.draw {{ background: linear-gradient(90deg, var(--gold), #d2a54c); }}
    .prob-fill.b {{ background: linear-gradient(90deg, #34495e, #4f7091); }}
    .prob-value {{
      font-variant-numeric: tabular-nums;
      font-weight: 700;
      color: var(--ink);
    }}
    .depth-block {{
      margin-top: 14px;
      padding: 14px;
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(181,131,47,0.10), rgba(15,109,102,0.05));
      border: 1px solid rgba(181,131,47,0.18);
    }}
    .depth-block h4 {{
      margin: 0 0 10px;
      color: var(--accent-dark);
    }}
    .depth-grid {{
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .depth-grid div {{
      background: rgba(255,255,255,0.45);
      border: 1px solid rgba(15,109,102,0.08);
      border-radius: 14px;
      padding: 10px 12px;
    }}
    .reason-block {{
      margin-top: 14px;
      padding: 14px;
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(15,109,102,0.08), rgba(255,255,255,0.65));
      border: 1px solid rgba(15,109,102,0.16);
    }}
    .reason-block h4 {{
      margin: 0 0 10px;
      color: var(--accent-dark);
    }}
    .scores h4 {{
      margin: 14px 0 8px;
      color: var(--accent);
    }}
    .scores ul {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 8px;
    }}
    .scores li {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      border-bottom: 1px dashed var(--line);
      padding-bottom: 6px;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      font-size: 0.92rem;
      color: var(--ink);
      max-height: 480px;
      overflow: auto;
      padding-right: 4px;
    }}
    @media (max-width: 820px) {{
      .hero-grid {{
        grid-template-columns: 1fr;
      }}
      .hero-metrics {{
        grid-template-columns: 1fr;
      }}
      .prob-row {{
        grid-template-columns: 1fr;
      }}
      .depth-grid {{
        grid-template-columns: 1fr;
      }}
      .bracket-canvas {{
        --bracket-board-width: 1908px;
      }}
    }}
    @media (max-width: 640px) {{
      main {{
        padding: 16px 12px 42px;
      }}
      .panel, .card {{
        border-radius: 20px;
      }}
      .summary-grid,
      .confidence-tiles {{
        grid-template-columns: 1fr;
      }}
      .bracket-canvas {{
        --bracket-col: 188px;
        --bracket-gap: 14px;
        --bracket-board-width: 1804px;
      }}
      .stage-head {{
        padding: 12px 14px;
      }}
      .bracket-match {{
        min-height: 112px;
        padding: 12px;
      }}
      .center-stack {{
        gap: 180px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="panel hero">
      <div class="hero-grid">
        <div>
          <p class="eyebrow">Modelo Dinámico | Mundial 2026</p>
          <h1>Pronóstico En Vivo y Hoja de Ruta</h1>
          <p class="lede">Cada partido combina fortaleza base, Elo, puntos FIFA complementarios, forma reciente, clima, alineaciones, bajas, mercado y estado del torneo. Si un juego está en curso, las probabilidades ya se condicionan al minuto y al marcador actual.</p>
          <div class="summary-grid">
            <div class="summary-tile">
              <span>Última actualización</span>
              <strong>{html.escape(iso_timestamp())}</strong>
            </div>
            <div class="summary-tile">
              <span>Frecuencia cloud</span>
              <strong>Cada 5 minutos</strong>
            </div>
            <div class="summary-tile">
              <span>Estado del torneo</span>
              <strong>Elo + forma + fatiga + disciplina</strong>
            </div>
            <div class="summary-tile">
              <span>Origen operativo</span>
              <strong>GitHub Actions + Pages</strong>
            </div>
          </div>
        </div>
        <div class="hero-notes">
          <article class="hero-note">
            <h3>Qué significan las métricas</h3>
            <p><strong>Marcador proyectado</strong> muestra el resultado entero mas probable. <strong>Promedio estimado de goles del modelo</strong> es una media probabilistica y por eso puede llevar decimales. <strong>Probabilidades de resultado</strong> es la chance de victoria, empate o derrota en ese mismo corte. <strong>Puntos FIFA</strong> entran como señal estructural secundaria, con menos peso que Elo.</p>
          </article>
          <article class="hero-note">
            <h3>Durante un partido</h3>
            <p>El dashboard pasa a modo in-play: usa minuto, marcador actual y fase del juego para recalcular el resultado final más probable, el resto de goles esperados y los marcadores finales mas probables en cada corte de actualizacion.</p>
          </article>
          <article class="hero-note">
            <h3>Trazabilidad</h3>
            <p>Estado usado: {html.escape(str(state_path))}<br>Fixtures leídos: {html.escape(str(fixtures_path))}</p>
          </article>
          <article class="hero-note">
            <h3>Como validar el in-play</h3>
            <p>Si el partido esta en vivo, revisa la hora superior, el badge En vivo, el minuto modelado y el archivo <a href="latest.json" style="color:#fff3d7;">latest.json</a>. Todo eso se regenera en cada corrida de GitHub Actions y debe mover probabilidades y marcadores proyectados cuando cambie el estado del juego.</p>
          </article>
        </div>
      </div>
    </section>
    {methodology_html}
    {global_confidence_html}
    {backtesting_html}
    {bracket_visual_html}
    <section class="panel">
      <div class="panel-head">
        <div>
          <p class="eyebrow">Texto técnico</p>
          <h2>Resumen completo de la llave</h2>
          <p class="lede-tight">Además del bracket visual, aquí se conserva el detalle textual completo para revisar todos los cruces y porcentajes publicados.</p>
        </div>
      </div>
      <h2>Llave actual</h2>
      <pre>{bracket_html}</pre>
    </section>
    <section class="cards">
      {''.join(cards)}
    </section>
  </main>
</body>
</html>
"""


def command_project_dashboard(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    fixture_path = Path(args.fixtures)
    fixtures = read_fixtures(fixture_path)
    payload = load_persistent_payload(Path(args.state_file), teams)
    states = copy_states(payload)
    bracket_path = Path(args.bracket_file)
    bracket_json_path = Path(args.bracket_json_file)
    bracket_text = bracket_path.read_text() if bracket_path.exists() else ""
    bracket_payload = load_bracket_json(bracket_json_path)

    entries = dashboard_fixture_entries(fixtures, teams, states, args.top_scores)
    entries.extend(
        projected_bracket_entries(
            fixtures,
            bracket_payload,
            teams,
            states,
            args.top_scores,
            [entry["match_id"] for entry in entries if entry.get("match_id")],
        )
    )
    backtest = compute_backtest_summary(fixtures, teams, args.top_scores)
    markdown = build_dashboard_markdown(entries, bracket_text, bracket_payload, backtest, Path(args.state_file), fixture_path)
    html_content = build_dashboard_html(entries, bracket_text, bracket_payload, backtest, Path(args.state_file), fixture_path)

    output_md = Path(args.output_md)
    output_html = Path(args.output_html)
    output_md.write_text(markdown)
    output_html.write_text(html_content)
    print(f"Reporte Markdown guardado en {output_md}")
    print(f"Reporte HTML guardado en {output_html}")


def read_fixtures(path: Path) -> List[dict]:
    return json.loads(path.read_text())


def iso_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def default_team_state() -> dict:
    return {
        "morale": 0.0,
        "yellow_cards": 0,
        "yellow_load": 0.0,
        "red_suspensions": 0,
        "group_points": 0,
        "group_goal_diff": 0,
        "group_goals_for": 0,
        "group_goals_against": 0,
        "group_matches_played": 0,
        "fair_play": 0.0,
        "matches_played": 0,
        "goals_for": 0,
        "goals_against": 0,
        "elo_shift": 0.0,
        "recent_form": 0.0,
        "attack_form": 0.0,
        "defense_form": 0.0,
        "fatigue": 0.0,
        "availability": 1.0,
        "discipline_drift": 0.0,
        "style_possession": 0.0,
        "style_verticality": 0.0,
        "style_pressure": 0.0,
        "style_chance_quality": 0.0,
        "style_tempo": 0.0,
        "style_attack_bias": 0.0,
        "style_defense_bias": 0.0,
        "tactical_sample_matches": 0,
        "tactical_signature": "sin muestra suficiente",
        "updated_at": None,
    }


def normalize_team_state(state: Optional[dict]) -> dict:
    normalized = default_team_state()
    if state:
        legacy_state = dict(state)
        if "pending_red_suspensions" in legacy_state and "red_suspensions" not in legacy_state:
            legacy_state["red_suspensions"] = legacy_state["pending_red_suspensions"]
        normalized.update(legacy_state)
    normalized["availability"] = clamp(float(normalized["availability"]), 0.40, 1.0)
    normalized["fatigue"] = clamp(float(normalized["fatigue"]), 0.0, 1.0)
    normalized["elo_shift"] = clamp(float(normalized["elo_shift"]), -220.0, 220.0)
    normalized["recent_form"] = clamp(float(normalized["recent_form"]), -1.0, 1.0)
    normalized["attack_form"] = clamp(float(normalized["attack_form"]), -1.0, 1.0)
    normalized["defense_form"] = clamp(float(normalized["defense_form"]), -1.0, 1.0)
    normalized["discipline_drift"] = clamp(float(normalized["discipline_drift"]), -1.0, 0.5)
    normalized["style_possession"] = clamp(float(normalized["style_possession"]), -1.0, 1.0)
    normalized["style_verticality"] = clamp(float(normalized["style_verticality"]), -1.0, 1.0)
    normalized["style_pressure"] = clamp(float(normalized["style_pressure"]), -1.0, 1.0)
    normalized["style_chance_quality"] = clamp(float(normalized["style_chance_quality"]), -1.0, 1.0)
    normalized["style_tempo"] = clamp(float(normalized["style_tempo"]), -1.0, 1.0)
    normalized["style_attack_bias"] = clamp(float(normalized["style_attack_bias"]), -1.0, 1.0)
    normalized["style_defense_bias"] = clamp(float(normalized["style_defense_bias"]), -1.0, 1.0)
    normalized["tactical_sample_matches"] = max(0, int(normalized["tactical_sample_matches"]))
    normalized["yellow_load"] = clamp(float(normalized["yellow_load"]), 0.0, 6.0)
    normalized["morale"] = clamp(float(normalized["morale"]), -1.0, 1.0)
    normalized["tactical_signature"] = str(normalized.get("tactical_signature") or "sin muestra suficiente")
    return normalized


def initial_team_states(teams: Dict[str, Team]) -> Dict[str, dict]:
    return {name: default_team_state() for name in teams}


def empty_persistent_payload(teams: Dict[str, Team]) -> dict:
    return {
        "meta": {
            "version": 3,
            "updated_at": iso_timestamp(),
            "description": "Estado persistente del Mundial 2026 para actualizar automaticamente predicciones futuras.",
        },
        "applied_results": [],
        "teams": initial_team_states(teams),
    }


def normalize_persistent_payload(payload: dict, teams: Dict[str, Team]) -> dict:
    normalized = empty_persistent_payload(teams)
    normalized["meta"].update(payload.get("meta", {}))
    normalized["applied_results"] = list(payload.get("applied_results", []))

    team_payload = payload.get("teams", payload if isinstance(payload, dict) else {})
    for team_name in teams:
        normalized["teams"][team_name] = normalize_team_state(team_payload.get(team_name, {}))
    return normalized


def load_persistent_payload(path: Path, teams: Dict[str, Team]) -> dict:
    if not path.exists():
        return empty_persistent_payload(teams)
    text = path.read_text()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        payload, _ = decoder.raw_decode(text)
    return normalize_persistent_payload(payload, teams)


def save_persistent_payload(path: Path, payload: dict) -> None:
    payload["meta"]["updated_at"] = iso_timestamp()
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        dir=path.parent,
        prefix=f".{path.stem}-",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(serialized)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def copy_states(payload: dict) -> Dict[str, dict]:
    return {team_name: normalize_team_state(state) for team_name, state in payload["teams"].items()}


def print_state(state_name: str, state: dict) -> None:
    state = normalize_team_state(state)
    print(f"{state_name}")
    print(f"  Moral: {state['morale']:+.2f}")
    print(f"  Elo dinamico: {state['elo_shift']:+.1f}")
    print(f"  Forma reciente: {state['recent_form']:+.2f}")
    print(f"  Forma ataque: {state['attack_form']:+.2f}")
    print(f"  Forma defensa: {state['defense_form']:+.2f}")
    print(f"  Fatiga: {state['fatigue']:.2f}")
    print(f"  Disponibilidad: {state['availability']:.2f}")
    print(f"  Tendencia disciplinaria: {state['discipline_drift']:+.2f}")
    print(f"  Firma tactica reciente: {state['tactical_signature']}")
    print(
        f"  Rasgos tacticos: posesion {state['style_possession']:+.2f} | verticalidad {state['style_verticality']:+.2f} | "
        f"presion {state['style_pressure']:+.2f} | calidad {state['style_chance_quality']:+.2f} | ritmo {state['style_tempo']:+.2f}"
    )
    print(f"  Muestra tactica acumulada: {state['tactical_sample_matches']}")
    print(f"  Amarillas acumuladas: {state['yellow_cards']}")
    print(f"  Carga disciplinaria reciente: {state['yellow_load']:.2f}")
    print(f"  Suspensiones por roja: {state['red_suspensions']}")
    print(f"  Puntos de grupo: {state['group_points']}")
    print(f"  Diferencia de gol de grupo: {state['group_goal_diff']}")
    print(f"  Partidos de grupo: {state['group_matches_played']}")
    print(f"  Partidos totales: {state['matches_played']}")
    print(f"  Goles a favor: {state['goals_for']}")
    print(f"  Goles en contra: {state['goals_against']}")
    print(f"  Ultima actualizacion: {state['updated_at']}")


def state_has_activity(state: dict) -> bool:
    state = normalize_team_state(state)
    return any(
        [
            state["matches_played"] > 0,
            state["group_matches_played"] > 0,
            abs(state["morale"]) > 1e-9,
            abs(state["elo_shift"]) > 1e-9,
            abs(state["recent_form"]) > 1e-9,
            abs(state["attack_form"]) > 1e-9,
            abs(state["defense_form"]) > 1e-9,
            abs(state["discipline_drift"]) > 1e-9,
            abs(state["fatigue"]) > 1e-9,
            abs(state["availability"] - 1.0) > 1e-9,
            state["tactical_sample_matches"] > 0,
        ]
    )


def tactical_state_value(state: Optional[dict], key: str, default: float = 0.0) -> float:
    if not state:
        return default
    return float(normalize_team_state(state).get(key, default))


def tactical_attack_signal(state: Optional[dict]) -> float:
    return tactical_state_value(state, "style_attack_bias", 0.0)


def tactical_defense_signal(state: Optional[dict]) -> float:
    return tactical_state_value(state, "style_defense_bias", 0.0)


def tactical_tempo_signal(state: Optional[dict]) -> float:
    return tactical_state_value(state, "style_tempo", 0.0)


def tactical_signature_text(state: Optional[dict]) -> str:
    return str(normalize_team_state(state).get("tactical_signature", "sin muestra suficiente"))


def tactical_signature_from_metrics(
    style_possession: float,
    style_verticality: float,
    style_pressure: float,
    style_chance_quality: float,
    style_tempo: float,
    style_attack_bias: float,
    style_defense_bias: float,
    sample_matches: int,
) -> str:
    if sample_matches <= 0:
        return "sin muestra suficiente"
    if style_possession >= 0.22 and style_pressure >= 0.14 and style_chance_quality >= -0.02:
        return "control territorial"
    if style_possession >= 0.22 and style_chance_quality < -0.08:
        return "control esteril"
    if style_possession <= -0.12 and style_verticality >= 0.12 and style_chance_quality >= 0.0:
        return "transicion vertical"
    if style_possession <= -0.18 and style_defense_bias >= 0.08 and style_attack_bias >= -0.02:
        return "bloque bajo y contra"
    if style_tempo >= 0.18 and style_pressure >= 0.05:
        return "ritmo alto"
    if abs(style_possession) < 0.12 and abs(style_verticality) < 0.12 and abs(style_pressure) < 0.12:
        return "perfil mixto equilibrado"
    return "perfil mixto"


def live_signature_metrics(side: str, live_stats: Dict[str, float]) -> Optional[Dict[str, float]]:
    other = "b" if side == "a" else "a"
    shots = float(live_stats.get(f"shots_{side}", 0.0))
    shots_opp = float(live_stats.get(f"shots_{other}", 0.0))
    sot = float(live_stats.get(f"shots_on_target_{side}", 0.0))
    sot_opp = float(live_stats.get(f"shots_on_target_{other}", 0.0))
    poss = float(live_stats.get(f"possession_{side}", 50.0))
    corners = float(live_stats.get(f"corners_{side}", 0.0))
    corners_opp = float(live_stats.get(f"corners_{other}", 0.0))
    fouls = float(live_stats.get(f"fouls_{side}", 0.0))
    fouls_opp = float(live_stats.get(f"fouls_{other}", 0.0))
    yellows = float(live_stats.get(f"yellow_cards_{side}", 0.0))
    reds = float(live_stats.get(f"red_cards_{side}", 0.0))
    reds_opp = float(live_stats.get(f"red_cards_{other}", 0.0))
    xg = float(live_stats.get(f"xg_{side}", live_stats.get(f"xg_proxy_{side}", 0.0)))
    xg_opp = float(live_stats.get(f"xg_{other}", live_stats.get(f"xg_proxy_{other}", 0.0)))

    total_signal = shots + shots_opp + sot + sot_opp + corners + corners_opp + xg + xg_opp + fouls + fouls_opp + yellows
    if total_signal <= 0.0:
        return None

    poss_norm = clamp((poss - 50.0) / 25.0, -1.0, 1.0)
    shot_share = clamp((stat_share(shots, shots_opp) - 0.5) * 2.0, -1.0, 1.0)
    sot_share = clamp((stat_share(sot, sot_opp) - 0.5) * 2.0, -1.0, 1.0)
    corner_share = clamp((stat_share(corners, corners_opp) - 0.5) * 2.0, -1.0, 1.0)
    xg_per_shot = xg / max(shots, 1.0)
    chance_quality = clamp((xg_per_shot - 0.11) / 0.09, -1.0, 1.0)
    verticality = clamp(0.48 * (-poss_norm) + 0.32 * chance_quality + 0.20 * shot_share, -1.0, 1.0)
    pressure = clamp(0.45 * shot_share + 0.30 * corner_share + 0.25 * sot_share, -1.0, 1.0)
    match_intensity = clamp(((shots + shots_opp) + 0.8 * (corners + corners_opp) + 3.0 * (xg + xg_opp)) / 24.0 - 1.0, -1.0, 1.0)
    tempo = clamp(match_intensity + 0.20 * pressure - 0.10 * clamp((fouls + fouls_opp) / 24.0, 0.0, 1.0), -1.0, 1.0)
    attack_bias = clamp(0.40 * pressure + 0.35 * chance_quality + 0.25 * verticality, -1.0, 1.0)
    card_swing = 1.0 if reds_opp > reds else -1.0 if reds > reds_opp else 0.0
    defense_bias = clamp(0.35 * poss_norm + 0.35 * pressure - 0.18 * tempo + 0.18 * card_swing, -1.0, 1.0)
    return {
        "style_possession": poss_norm,
        "style_verticality": verticality,
        "style_pressure": pressure,
        "style_chance_quality": chance_quality,
        "style_tempo": tempo,
        "style_attack_bias": attack_bias,
        "style_defense_bias": defense_bias,
    }


def update_tactical_signature_state(state: dict, metrics: Optional[Dict[str, float]]) -> None:
    if not metrics:
        return
    alpha = 0.28
    for key, value in metrics.items():
        state[key] = clamp((1.0 - alpha) * float(state.get(key, 0.0)) + alpha * float(value), -1.0, 1.0)
    state["tactical_sample_matches"] = int(state.get("tactical_sample_matches", 0)) + 1
    state["tactical_signature"] = tactical_signature_from_metrics(
        float(state.get("style_possession", 0.0)),
        float(state.get("style_verticality", 0.0)),
        float(state.get("style_pressure", 0.0)),
        float(state.get("style_chance_quality", 0.0)),
        float(state.get("style_tempo", 0.0)),
        float(state.get("style_attack_bias", 0.0)),
        float(state.get("style_defense_bias", 0.0)),
        int(state.get("tactical_sample_matches", 0)),
    )


def fixture_stage_name(fixture: dict) -> str:
    stage = fixture.get("stage")
    if stage is not None:
        return normalize_stage_name(str(stage))
    if fixture.get("group"):
        return "group"
    if fixture.get("knockout", False):
        return "round32"
    return "group"


def resolve_fixture_winner(
    fixture: dict,
    teams: Dict[str, Team],
    team_a: str,
    team_b: str,
) -> Optional[str]:
    score_a = int(fixture["actual_score_a"])
    score_b = int(fixture["actual_score_b"])
    if score_a > score_b:
        return team_a
    if score_b > score_a:
        return team_b

    raw_winner = fixture.get("penalties_winner", fixture.get("actual_winner"))
    if raw_winner is None:
        return None
    if isinstance(raw_winner, str):
        normalized = raw_winner.strip().lower()
        if normalized in {"a", "team_a"}:
            return team_a
        if normalized in {"b", "team_b"}:
            return team_b
    return resolve_team_name(str(raw_winner), teams)


def fixture_state_ids(fixture: dict, fixture_path: Optional[Path] = None, index: Optional[int] = None) -> List[str]:
    ids = []
    if fixture.get("id"):
        ids.append(str(fixture["id"]))
    location = fixture_path.name if fixture_path else "fixture"
    label = fixture.get("label", "")
    if index is None:
        ids.append(f"{location}:{fixture['team_a']}:{fixture['team_b']}:{label}")
    else:
        ids.append(f"{location}:{index}:{fixture['team_a']}:{fixture['team_b']}:{label}")
    return ids


def apply_state_updates(
    teams: Dict[str, Team],
    states: Dict[str, dict],
    fixture: dict,
    ctx: MatchContext,
    prediction: MatchPrediction,
) -> None:
    if "actual_score_a" not in fixture or "actual_score_b" not in fixture:
        return

    team_a = fixture["team_a"]
    team_b = fixture["team_b"]
    score_a = int(fixture["actual_score_a"])
    score_b = int(fixture["actual_score_b"])
    yellows_a = int(fixture.get("actual_yellows_a", 0))
    yellows_b = int(fixture.get("actual_yellows_b", 0))
    reds_a = int(fixture.get("actual_reds_a", 0))
    reds_b = int(fixture.get("actual_reds_b", 0))
    stage = fixture_stage_name(fixture)
    winner = resolve_fixture_winner(fixture, teams, team_a, team_b)
    live_stats = extract_live_stats_payload(fixture)
    update_simulation_state(
        teams,
        states,
        team_a,
        team_b,
        ctx,
        prediction.expected_goals_a,
        prediction.expected_goals_b,
        score_a,
        score_b,
        yellows_a,
        reds_a,
        yellows_b,
        reds_b,
        stage,
        winner=winner,
        went_extra_time=bool(fixture.get("went_extra_time", False)),
        went_penalties=bool(fixture.get("went_penalties", False)),
        live_stats=live_stats,
    )
    states[team_a]["updated_at"] = iso_timestamp()
    states[team_b]["updated_at"] = iso_timestamp()


def context_from_fixture(
    fixture: dict,
    teams: Dict[str, Team],
    states: Optional[Dict[str, dict]] = None,
) -> MatchContext:
    states = states or {}
    state_a = normalize_team_state(states.get(fixture["team_a"], {}))
    state_b = normalize_team_state(states.get(fixture["team_b"], {}))
    stage = fixture_stage_name(fixture)
    knockout = stage != "group"
    default_rest_days = 4 if stage == "group" else 5

    return MatchContext(
        neutral=bool(fixture.get("neutral", fixture.get("home_team") is None)),
        home_team=fixture.get("home_team"),
        venue_country=fixture.get("venue_country"),
        rest_days_a=int(fixture.get("rest_days_a", default_rest_days)),
        rest_days_b=int(fixture.get("rest_days_b", default_rest_days)),
        injuries_a=float(fixture.get("injuries_a", dynamic_injury_load(teams[fixture["team_a"]], state_a))),
        injuries_b=float(fixture.get("injuries_b", dynamic_injury_load(teams[fixture["team_b"]], state_b))),
        altitude_m=int(fixture.get("altitude_m", 0)),
        travel_km_a=float(fixture.get("travel_km_a", 0.0)),
        travel_km_b=float(fixture.get("travel_km_b", 0.0)),
        knockout=knockout,
        morale_a=float(fixture.get("morale_a", state_a.get("morale", 0.0))),
        morale_b=float(fixture.get("morale_b", state_b.get("morale", 0.0))),
        yellow_cards_a=int(fixture.get("yellow_cards_a", predictive_yellow_cards(state_a))),
        yellow_cards_b=int(fixture.get("yellow_cards_b", predictive_yellow_cards(state_b))),
        red_suspensions_a=int(fixture.get("red_suspensions_a", state_a.get("red_suspensions", 0))),
        red_suspensions_b=int(fixture.get("red_suspensions_b", state_b.get("red_suspensions", 0))),
        group=fixture.get("group"),
        group_points_a=int(fixture.get("group_points_a", state_a.get("group_points", 0))),
        group_points_b=int(fixture.get("group_points_b", state_b.get("group_points", 0))),
        group_goal_diff_a=int(fixture.get("group_goal_diff_a", state_a.get("group_goal_diff", 0))),
        group_goal_diff_b=int(fixture.get("group_goal_diff_b", state_b.get("group_goal_diff", 0))),
        group_matches_played_a=int(
            fixture.get("group_matches_played_a", state_a.get("group_matches_played", 0))
        ),
        group_matches_played_b=int(
            fixture.get("group_matches_played_b", state_b.get("group_matches_played", 0))
        ),
        weather_stress=float(fixture.get("weather_stress", 0.0)),
        market_prob_a=market_probability(fixture.get("market_prob_a")),
        market_prob_draw=market_probability(fixture.get("market_prob_draw")),
        market_prob_b=market_probability(fixture.get("market_prob_b")),
        market_total_line=float(fixture["market_total_line"]) if fixture.get("market_total_line") is not None else None,
        lineup_confirmed_a=bool(fixture.get("lineup_confirmed_a", False)),
        lineup_confirmed_b=bool(fixture.get("lineup_confirmed_b", False)),
        lineup_change_count_a=int(fixture.get("lineup_change_count_a", 0)),
        lineup_change_count_b=int(fixture.get("lineup_change_count_b", 0)),
        importance=float(fixture.get("importance", STAGE_IMPORTANCE[stage])),
    )


def fixture_has_final_result(fixture: dict) -> bool:
    return fixture.get("actual_score_a") is not None and fixture.get("actual_score_b") is not None


def regular_time_result_available(fixture: dict) -> bool:
    return fixture_stage_name(fixture) == "group" or not bool(fixture.get("went_extra_time", False))


def actual_regular_time_outcome(fixture: dict) -> Optional[str]:
    if not fixture_has_final_result(fixture) or not regular_time_result_available(fixture):
        return None
    score_a = int(fixture["actual_score_a"])
    score_b = int(fixture["actual_score_b"])
    if score_a > score_b:
        return "a"
    if score_b > score_a:
        return "b"
    return "draw"


def actual_advancement_outcome(fixture: dict, teams: Dict[str, Team]) -> Optional[str]:
    if fixture_stage_name(fixture) == "group" or not fixture_has_final_result(fixture):
        return None
    winner = resolve_fixture_winner(fixture, teams, fixture["team_a"], fixture["team_b"])
    if winner == fixture["team_a"]:
        return "a"
    if winner == fixture["team_b"]:
        return "b"
    return None


def confidence_bucket(value: float) -> str:
    pct = value * 100.0
    if pct < 50.0:
        return "<50%"
    if pct < 60.0:
        return "50-59%"
    if pct < 70.0:
        return "60-69%"
    if pct < 80.0:
        return "70-79%"
    return "80%+"


def compute_backtest_summary(fixtures: Sequence[dict], teams: Dict[str, Team], top_scores: int) -> dict:
    completed = []
    for fixture in fixtures:
        if fixture.get("projection_only"):
            continue
        if not fixture_has_final_result(fixture):
            continue
        completed.append(dict(fixture))
    completed.sort(key=lambda item: (item.get("kickoff_utc") or "", str(item.get("id", ""))))

    if not completed:
        return {
            "completed_matches": 0,
            "regular_time_samples": 0,
            "advancement_samples": 0,
            "favorite_hit_rate": None,
            "top1_score_hit_rate": None,
            "top3_score_hit_rate": None,
            "brier_result": None,
            "logloss_result": None,
            "brier_advance": None,
            "logloss_advance": None,
            "market_logloss_result": None,
            "calibration_buckets": [],
        }

    states = copy_states(empty_persistent_payload(teams))
    result_brier = []
    result_logloss = []
    market_result_logloss = []
    advance_brier = []
    advance_logloss = []
    favorite_hits = 0
    favorite_total = 0
    top1_hits = 0
    top3_hits = 0
    regular_samples = 0
    advance_samples = 0
    calibration = {}

    for fixture in completed:
        try:
            fixture = resolve_fixture_names(fixture, teams)
        except SystemExit:
            continue
        ctx = context_from_fixture(fixture, teams, states)
        stage = fixture_stage_name(fixture)
        prediction = predict_match(
            teams,
            fixture["team_a"],
            fixture["team_b"],
            ctx,
            top_scores=top_scores,
            include_advancement=stage != "group",
            show_factors=False,
            state_a=normalize_team_state(states.get(fixture["team_a"], {})),
            state_b=normalize_team_state(states.get(fixture["team_b"], {})),
        )

        actual_outcome = actual_regular_time_outcome(fixture)
        if actual_outcome is not None:
            probs = {"a": prediction.win_a, "draw": prediction.draw, "b": prediction.win_b}
            regular_samples += 1
            favorite_total += 1
            predicted_outcome = max(probs.items(), key=lambda item: item[1])[0]
            if predicted_outcome == actual_outcome:
                favorite_hits += 1
            p_actual = max(probs[actual_outcome], 1e-12)
            result_logloss.append(-math.log(p_actual))
            result_brier.append(
                ((probs["a"] - (1.0 if actual_outcome == "a" else 0.0)) ** 2
                 + (probs["draw"] - (1.0 if actual_outcome == "draw" else 0.0)) ** 2
                 + (probs["b"] - (1.0 if actual_outcome == "b" else 0.0)) ** 2) / 3.0
            )
            if fixture.get("market_prob_a") is not None and fixture.get("market_prob_draw") is not None and fixture.get("market_prob_b") is not None:
                market_probs = {
                    "a": float(fixture["market_prob_a"]),
                    "draw": float(fixture["market_prob_draw"]),
                    "b": float(fixture["market_prob_b"]),
                }
                market_result_logloss.append(-math.log(max(market_probs[actual_outcome], 1e-12)))

            actual_score = f"{int(fixture['actual_score_a'])}-{int(fixture['actual_score_b'])}"
            predicted_scores = [score for score, _ in prediction.exact_scores]
            if predicted_scores:
                if predicted_scores[0] == actual_score:
                    top1_hits += 1
                if actual_score in predicted_scores[:3]:
                    top3_hits += 1

            bucket = confidence_bucket(float(prediction.statistical_depth.get("confidence_index", 0.0))) if prediction.statistical_depth else "<50%"
            bucket_state = calibration.setdefault(bucket, {"n": 0, "hit": 0, "avg_conf": 0.0})
            bucket_state["n"] += 1
            bucket_state["hit"] += 1 if predicted_outcome == actual_outcome else 0
            bucket_state["avg_conf"] += float(prediction.statistical_depth.get("confidence_index", 0.0)) if prediction.statistical_depth else 0.0

        actual_advance = actual_advancement_outcome(fixture, teams)
        if actual_advance is not None and prediction.advance_a is not None and prediction.advance_b is not None:
            probs = {"a": prediction.advance_a, "b": prediction.advance_b}
            advance_samples += 1
            p_actual = max(probs[actual_advance], 1e-12)
            advance_logloss.append(-math.log(p_actual))
            advance_brier.append(
                ((probs["a"] - (1.0 if actual_advance == "a" else 0.0)) ** 2
                 + (probs["b"] - (1.0 if actual_advance == "b" else 0.0)) ** 2) / 2.0
            )

        apply_state_updates(teams, states, fixture, ctx, prediction)

    calibration_buckets = []
    bucket_order = ["<50%", "50-59%", "60-69%", "70-79%", "80%+"]
    for bucket in bucket_order:
        payload = calibration.get(bucket)
        if not payload:
            continue
        n = payload["n"]
        calibration_buckets.append(
            {
                "bucket": bucket,
                "matches": n,
                "avg_confidence": payload["avg_conf"] / n,
                "hit_rate": payload["hit"] / n,
            }
        )

    def avg(values: List[float]) -> Optional[float]:
        return sum(values) / len(values) if values else None

    return {
        "completed_matches": len(completed),
        "regular_time_samples": regular_samples,
        "advancement_samples": advance_samples,
        "favorite_hit_rate": (favorite_hits / favorite_total) if favorite_total else None,
        "top1_score_hit_rate": (top1_hits / regular_samples) if regular_samples else None,
        "top3_score_hit_rate": (top3_hits / regular_samples) if regular_samples else None,
        "brier_result": avg(result_brier),
        "logloss_result": avg(result_logloss),
        "brier_advance": avg(advance_brier),
        "logloss_advance": avg(advance_logloss),
        "market_logloss_result": avg(market_result_logloss),
        "calibration_buckets": calibration_buckets,
    }


def print_prediction(prediction: MatchPrediction, show_factors: bool = False) -> None:
    print(f"{prediction.team_a} vs {prediction.team_b}")
    if prediction.elapsed_minutes is not None:
        print(f"  Minuto modelado: {prediction.elapsed_minutes:.1f}")
    if prediction.current_score_a is not None and prediction.current_score_b is not None:
        print(f"  Marcador actual: {prediction.team_a} {prediction.current_score_a} - {prediction.current_score_b} {prediction.team_b}")
    print(
        f"  {projected_score_label(prediction)}: {projected_score_value(prediction)} | "
        f"{result_prob_label(prediction)}: {prediction.win_a:.1%} / {prediction.draw:.1%} / {prediction.win_b:.1%}"
    )
    if prediction.live_phase != "penalties":
        print(
            f"  {average_goals_label(prediction)}: {prediction.team_a} {prediction.expected_goals_a:.2f} | "
            f"{prediction.team_b} {prediction.expected_goals_b:.2f}"
        )
    if prediction.expected_remaining_goals_a is not None and prediction.expected_remaining_goals_b is not None:
        print(
            f"  Promedio estimado de goles restantes: {prediction.team_a} {prediction.expected_remaining_goals_a:.2f} | "
            f"{prediction.team_b} {prediction.expected_remaining_goals_b:.2f}"
        )
    if prediction.advance_a is not None and prediction.advance_b is not None:
        detail = prediction.knockout_detail or {}
        print(
            f"  Si llegan empatados al siguiente corte: goles esperados en prorroga {detail.get('et_xg_a', 0.0):.2f} - {detail.get('et_xg_b', 0.0):.2f}"
        )
        print(
            f"    Prorroga: {prediction.team_a} {detail.get('et_win_a', 0.0):.1%} | "
            f"seguir empatados {detail.get('et_draw', 0.0):.1%} | {prediction.team_b} {detail.get('et_win_b', 0.0):.1%}"
        )
        print(
            f"    Penales si llegan: {prediction.team_a} {detail.get('penalties_a', 0.0):.1%} | "
            f"{prediction.team_b} {detail.get('penalties_b', 0.0):.1%}"
        )
        if prediction.penalty_shootout:
            shootout = prediction.penalty_shootout
            print(
                f"    Marcador esperado en penales: {prediction.team_a} {shootout.get('avg_score_a', 0.0):.2f} | "
                f"{prediction.team_b} {shootout.get('avg_score_b', 0.0):.2f}"
            )
            print("    Marcadores de penales mas probables:")
            for score, prob in shootout.get("top_scores", []):
                print(f"      {score}: {prob:.1%}")
        print(
            f"  Clasificar: {prediction.team_a} {prediction.advance_a:.1%} | "
            f"{prediction.team_b} {prediction.advance_b:.1%}"
        )
    print("  Marcadores finales mas probables:" if prediction.advance_a is not None else "  Marcadores mas probables:")
    for score, prob in prediction.exact_scores:
        print(f"    {score}: {prob:.1%}")
    if show_factors and prediction.factors:
        print("  Factores principales (A menos B):")
        for key in sorted(prediction.factors):
            print(f"    {key}: {prediction.factors[key]:+.3f}")


def print_monte_carlo_summary(team_a: str, team_b: str, summary: dict) -> None:
    print(f"  Monte Carlo ({summary['iterations']} iteraciones):")
    print(
        f"    Goles promedio: {team_a} {summary['avg_goals_a']:.2f} | "
        f"{team_b} {summary['avg_goals_b']:.2f}"
    )
    print(
        f"    Probabilidades simuladas de victoria/empate/derrota: {summary['win_a']:.1%} / {summary['draw']:.1%} / {summary['win_b']:.1%}"
    )
    if summary["advance_a"] is not None and summary["advance_b"] is not None:
        print(
            f"    Ir a proroga: {summary['extra_time_rate']:.1%} | "
            f"ir a penales: {summary['penalties_rate']:.1%}"
        )
        print(
            f"    Clasificar simulado: {team_a} {summary['advance_a']:.1%} | "
            f"{team_b} {summary['advance_b']:.1%}"
        )
    print("    Marcadores mas frecuentes:")
    for score, prob in summary["top_scores"]:
        print(f"      {score}: {prob:.1%}")


def print_team_profile(team: Team) -> None:
    profile = profile_for(team)
    squad = profile.squad
    fifa_note = " (proxy calibrado)" if fifa_points_are_proxy(team) else ""
    print(f"{team.name} ({pretty_status(team.status)})")
    print(f"  Elo: {team.elo:.0f}")
    print(f"  Puntos FIFA{fifa_note}: {profile.fifa_points:.1f}")
    print(f"  Ranking FIFA{fifa_note}: {profile.fifa_rank}")
    print(f"  PIB/recursos proxy: {profile.resource_index:.2f}")
    print(f"  Historia mundialista: {profile.heritage_index:.2f}")
    print(f"  Titulos del mundo: {profile.world_cup_titles}")
    print(f"  Trayectoria futbolistica: {profile.trajectory_index:.2f}")
    print(f"  Experiencia proxy del entrenador: {profile.coach_index:.2f}")
    print(f"  Quimica/cohesion: {profile.chemistry_index:.2f}")
    print(f"  Moral base: {profile.morale_base:.2f}")
    print(f"  Flexibilidad tactica: {profile.tactical_flexibility:.2f}")
    print(f"  Resiliencia de viaje: {profile.travel_resilience:.2f}")
    print(f"  Ritmo de juego: {profile.tempo:.2f}")
    print(f"  Calidad global de plantilla: {squad.squad_quality:.2f}")
    print(f"  Ataque de plantilla: {squad.attack_unit:.2f}")
    print(f"  Mediocampo/control: {squad.midfield_unit:.2f}")
    print(f"  Defensa de plantilla: {squad.defense_unit:.2f}")
    print(f"  Arquero: {squad.goalkeeper_unit:.2f}")
    print(f"  Profundidad de banco: {squad.bench_depth:.2f}")
    print(f"  Experiencia de jugadores: {squad.player_experience:.2f}")
    print(f"  Pelota parada ataque: {squad.set_piece_attack:.2f}")
    print(f"  Pelota parada defensa: {squad.set_piece_defense:.2f}")
    print(f"  Disciplina: {squad.discipline_index:.2f}")
    print(f"  Amarillas proxy por jugador: {squad.yellow_rate:.2f}")
    print(f"  Rojas proxy por jugador: {squad.red_rate:.3f}")
    print(f"  Disponibilidad: {squad.availability:.2f}")
    print(f"  Definicion: {squad.finishing:.2f}")
    print(f"  Generacion de ocasiones: {squad.shot_creation:.2f}")
    print(f"  Presion/recuperacion: {squad.pressing:.2f}")


def coalesce(value: Optional[float], fallback: float) -> float:
    return fallback if value is None else value


def coalesce_int(value: Optional[int], fallback: int) -> int:
    return fallback if value is None else value


def command_predict(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    team_a_name = resolve_team_name(args.team_a, teams)
    team_b_name = resolve_team_name(args.team_b, teams)
    home_team = resolve_optional_team_name(args.home_team, teams)
    venue_country = resolve_venue_country(args.venue_country, teams)
    payload = load_persistent_payload(Path(args.state_file), teams) if not args.ignore_state else empty_persistent_payload(teams)
    state_a = normalize_team_state(payload["teams"][team_a_name])
    state_b = normalize_team_state(payload["teams"][team_b_name])
    stage = normalize_stage_name(args.stage) if args.stage else ("round32" if args.knockout else "group")
    ctx = MatchContext(
        neutral=bool(args.neutral or home_team is None),
        home_team=home_team,
        venue_country=venue_country,
        rest_days_a=coalesce_int(args.rest_a, 4),
        rest_days_b=coalesce_int(args.rest_b, 4),
        injuries_a=coalesce(args.injuries_a, dynamic_injury_load(teams[team_a_name], state_a)),
        injuries_b=coalesce(args.injuries_b, dynamic_injury_load(teams[team_b_name], state_b)),
        altitude_m=coalesce_int(args.altitude, 0),
        travel_km_a=coalesce(args.travel_a, 0.0),
        travel_km_b=coalesce(args.travel_b, 0.0),
        knockout=stage != "group",
        morale_a=coalesce(args.morale_a, float(state_a["morale"])),
        morale_b=coalesce(args.morale_b, float(state_b["morale"])),
        yellow_cards_a=coalesce_int(args.yellow_cards_a, predictive_yellow_cards(state_a)),
        yellow_cards_b=coalesce_int(args.yellow_cards_b, predictive_yellow_cards(state_b)),
        red_suspensions_a=coalesce_int(args.red_suspensions_a, int(state_a["red_suspensions"])),
        red_suspensions_b=coalesce_int(args.red_suspensions_b, int(state_b["red_suspensions"])),
        group=args.group,
        group_points_a=coalesce_int(args.group_points_a, int(state_a["group_points"])),
        group_points_b=coalesce_int(args.group_points_b, int(state_b["group_points"])),
        group_goal_diff_a=coalesce_int(args.group_goal_diff_a, int(state_a["group_goal_diff"])),
        group_goal_diff_b=coalesce_int(args.group_goal_diff_b, int(state_b["group_goal_diff"])),
        group_matches_played_a=coalesce_int(args.group_matches_played_a, int(state_a["group_matches_played"])),
        group_matches_played_b=coalesce_int(args.group_matches_played_b, int(state_b["group_matches_played"])),
        weather_stress=coalesce(args.weather_stress, 0.0),
        importance=coalesce(args.importance, STAGE_IMPORTANCE[stage]),
    )
    prediction = predict_match(
        teams,
        team_a_name,
        team_b_name,
        ctx,
        top_scores=args.top_scores,
        include_advancement=stage != "group",
        show_factors=args.show_factors,
        state_a=state_a,
        state_b=state_b,
    )
    print_prediction(prediction, show_factors=args.show_factors)
    monte_carlo_iterations = getattr(args, "monte_carlo", 0)
    seed = getattr(args, "seed", None)
    if monte_carlo_iterations and monte_carlo_iterations > 0:
        if seed is not None:
            random.seed(seed)
        summary = monte_carlo_match_summary(
            teams,
            team_a_name,
            team_b_name,
            ctx,
            monte_carlo_iterations,
            state_a=state_a,
            state_b=state_b,
        )
        print_monte_carlo_summary(team_a_name, team_b_name, summary)


def command_score_prob(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    team_a_name = resolve_team_name(args.team_a, teams)
    team_b_name = resolve_team_name(args.team_b, teams)
    home_team = resolve_optional_team_name(args.home_team, teams)
    venue_country = resolve_venue_country(args.venue_country, teams)
    payload = load_persistent_payload(Path(args.state_file), teams) if not args.ignore_state else empty_persistent_payload(teams)
    state_a = normalize_team_state(payload["teams"][team_a_name])
    state_b = normalize_team_state(payload["teams"][team_b_name])
    stage = normalize_stage_name(args.stage) if args.stage else ("round32" if args.knockout else "group")
    ctx = MatchContext(
        neutral=bool(args.neutral or home_team is None),
        home_team=home_team,
        venue_country=venue_country,
        rest_days_a=4,
        rest_days_b=4,
        injuries_a=dynamic_injury_load(teams[team_a_name], state_a),
        injuries_b=dynamic_injury_load(teams[team_b_name], state_b),
        altitude_m=0,
        travel_km_a=0.0,
        travel_km_b=0.0,
        knockout=stage != "group",
        morale_a=float(state_a["morale"]),
        morale_b=float(state_b["morale"]),
        yellow_cards_a=predictive_yellow_cards(state_a),
        yellow_cards_b=predictive_yellow_cards(state_b),
        red_suspensions_a=int(state_a["red_suspensions"]),
        red_suspensions_b=int(state_b["red_suspensions"]),
        group=args.group,
        group_points_a=int(state_a["group_points"]),
        group_points_b=int(state_b["group_points"]),
        group_goal_diff_a=int(state_a["group_goal_diff"]),
        group_goal_diff_b=int(state_b["group_goal_diff"]),
        group_matches_played_a=int(state_a["group_matches_played"]),
        group_matches_played_b=int(state_b["group_matches_played"]),
        weather_stress=0.0,
        importance=STAGE_IMPORTANCE[stage],
    )
    mu_a, mu_b = expected_goals(teams[team_a_name], teams[team_b_name], ctx, state_a=state_a, state_b=state_b)
    distribution = score_distribution(mu_a, mu_b, max_goals=max(args.goals_a, args.goals_b, 10))
    probability = distribution.get((args.goals_a, args.goals_b), 0.0)
    print(f"{team_a_name} vs {team_b_name}")
    print(f"  Promedio estimado de goles del modelo: {team_a_name} {mu_a:.2f} | {team_b_name} {mu_b:.2f}")
    print(f"  Probabilidad de {args.goals_a}-{args.goals_b}: {probability:.2%}")
    if stage != "group" and args.goals_a == args.goals_b:
        detail = knockout_resolution_detail(
            teams[team_a_name],
            teams[team_b_name],
            ctx,
            mu_a,
            mu_b,
            state_a=state_a,
            state_b=state_b,
        )
        print(f"  Si acaba {args.goals_a}-{args.goals_b} en 90':")
        print(
            f"    Prorroga: {team_a_name} {detail['et_win_a']:.1%} | "
            f"seguir empatados {detail['et_draw']:.1%} | {team_b_name} {detail['et_win_b']:.1%}"
        )
        print(
            f"    Penales si llegan: {team_a_name} {detail['penalties_a']:.1%} | "
            f"{team_b_name} {detail['penalties_b']:.1%}"
        )
        shootout = penalty_shootout_summary(
            teams[team_a_name],
            teams[team_b_name],
            ctx,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
            iterations=1600,
        )
        print(
            f"    Marcador esperado en penales: {team_a_name} {shootout['avg_score_a']:.2f} | "
            f"{team_b_name} {shootout['avg_score_b']:.2f}"
        )
        print("    Marcadores de penales mas probables:")
        for score, shootout_prob in shootout["top_scores"]:
            print(f"      {score}: {shootout_prob:.1%}")


def command_power_table(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    qual_probs = qualification_probabilities(teams)
    opponent_pool = confirmed_teams(teams)
    rows = []
    for team in teams.values():
        if args.only_confirmed and team.status != "qualified":
            continue
        xgf, xga, xpts = average_opponent_metrics(team, opponent_pool)
        profile = profile_for(team)
        rows.append(
            (
                team.name,
                pretty_status(team.status),
                qual_probs[team.name],
                xgf,
                xga,
                xpts,
                profile.resource_index,
                profile.heritage_index,
                profile.coach_index,
            )
        )

    rows.sort(key=lambda item: (item[2], item[5], item[3]), reverse=True)
    print("Equipo                     Estado             Prob.Mundial  xGF   xGA   xPts  PIB   Hist  DT")
    print("-" * 92)
    for name, status, prob, xgf, xga, xpts, resource, heritage, coach in rows:
        print(
            f"{name:25} {status:17} {prob:10.1%} {xgf:5.2f} {xga:5.2f} {xpts:5.2f} "
            f"{resource:4.2f} {heritage:4.2f} {coach:4.2f}"
        )


def command_playoffs(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    exact = qualification_probabilities(teams)
    simulated = simulate_playoffs(teams, args.iterations) if args.iterations > 0 else {}
    contenders = [team for team in teams.values() if team.status != "qualified"]
    contenders.sort(key=lambda team: exact[team.name], reverse=True)
    print("Equipo                     Estado             Exacta    Simulada")
    print("-" * 62)
    for team in contenders:
        simulated_prob = simulated.get(team.name, 0.0)
        print(
            f"{team.name:25} {pretty_status(team.status):17} "
            f"{exact[team.name]:7.1%} {simulated_prob:10.1%}"
        )


def command_fixtures(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    fixture_path = Path(args.path)
    fixtures = read_fixtures(fixture_path)
    payload = empty_persistent_payload(teams) if args.reset_state else load_persistent_payload(Path(args.state_file), teams)
    states = copy_states(payload)
    applied_results = set(payload.get("applied_results", []))

    for index, fixture in enumerate(fixtures):
        if fixture.get("projection_only"):
            if fixture.get("label"):
                print(f"\n{fixture['label']}")
            print("  Cruce futuro con placeholders: se omite en la actualizacion de estado.")
            continue
        try:
            fixture = resolve_fixture_names(fixture, teams)
        except SystemExit as exc:
            label = fixture.get("label", fixture.get("id", "fixture"))
            print(f"\n{label}")
            print(f"  Fixture omitido: {exc}")
            continue
        team_a = fixture["team_a"]
        team_b = fixture["team_b"]
        if team_a not in teams or team_b not in teams:
            raise SystemExit(f"Equipo no encontrado en fixture: {team_a} vs {team_b}")
        if fixture.get("label"):
            print(f"\n{fixture['label']}")
        state_a = normalize_team_state(states.get(team_a, {}))
        state_b = normalize_team_state(states.get(team_b, {}))
        ctx = context_from_fixture(fixture, teams, states)
        prediction = predict_match(
            teams,
            team_a,
            team_b,
            ctx,
            top_scores=args.top_scores,
            include_advancement=fixture_stage_name(fixture) != "group",
            show_factors=args.show_factors,
            state_a=state_a,
            state_b=state_b,
        )
        print_prediction(prediction, show_factors=args.show_factors)
        result_ids = fixture_state_ids(fixture, fixture_path=fixture_path, index=index)
        result_id = result_ids[0]
        if fixture.get("update_state") and "actual_score_a" in fixture and "actual_score_b" in fixture:
            if not any(existing_id in applied_results for existing_id in result_ids):
                apply_state_updates(teams, states, fixture, ctx, prediction)
                applied_results.update(result_ids)
                print(f"  Estado actualizado automaticamente con resultado real [{result_id}]")
            else:
                print(f"  Resultado ya aplicado antes, se omite duplicado [{result_id}]")

    if not args.no_save_state:
        payload["teams"] = states
        payload["applied_results"] = sorted(applied_results)
        save_persistent_payload(Path(args.state_file), payload)
        print(f"\nEstado persistente guardado en {args.state_file}")


def command_state_show(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    payload = load_persistent_payload(Path(args.state_file), teams)
    if args.team:
        team_name = resolve_team_name(args.team, teams)
        print_state(team_name, payload["teams"][team_name])
        return

    print(f"Archivo de estado: {args.state_file}")
    print(f"IDs de resultados ya aplicados: {len(payload.get('applied_results', []))}")
    for team_name in sorted(payload["teams"]):
        state = payload["teams"][team_name]
        if not args.full and not state_has_activity(state):
            continue
        print_state(team_name, state)


def command_state_reset(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    payload = empty_persistent_payload(teams)
    save_persistent_payload(Path(args.state_file), payload)
    print(f"Estado reiniciado en {args.state_file}")


def command_list_teams(teams: Dict[str, Team]) -> None:
    for team in sorted(teams.values(), key=lambda item: (item.status, -item.elo, item.name)):
        print(f"{team.name:25} {pretty_status(team.status):17} Elo {team.elo:4.0f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Modelo probabilistico para quinielas del Mundial 2026."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    predict = subparsers.add_parser("predict", help="Predice un partido puntual.")
    predict.add_argument("team_a")
    predict.add_argument("team_b")
    predict.add_argument("--neutral", action="store_true", default=False)
    predict.add_argument("--home-team", default=None)
    predict.add_argument("--venue-country", default=None)
    predict.add_argument("--rest-a", type=int, default=None)
    predict.add_argument("--rest-b", type=int, default=None)
    predict.add_argument("--injuries-a", type=float, default=None)
    predict.add_argument("--injuries-b", type=float, default=None)
    predict.add_argument("--altitude", type=int, default=None)
    predict.add_argument("--travel-a", type=float, default=None)
    predict.add_argument("--travel-b", type=float, default=None)
    predict.add_argument("--knockout", action="store_true")
    predict.add_argument(
        "--stage",
        default=None,
        help="Etapa real del partido. Acepta group, round32, round16, round8, round4, semifinal, final, third_place.",
    )
    predict.add_argument("--morale-a", type=float, default=None)
    predict.add_argument("--morale-b", type=float, default=None)
    predict.add_argument("--yellow-cards-a", type=int, default=None)
    predict.add_argument("--yellow-cards-b", type=int, default=None)
    predict.add_argument("--red-suspensions-a", type=int, default=None)
    predict.add_argument("--red-suspensions-b", type=int, default=None)
    predict.add_argument("--group", default=None)
    predict.add_argument("--group-points-a", type=int, default=None)
    predict.add_argument("--group-points-b", type=int, default=None)
    predict.add_argument("--group-goal-diff-a", type=int, default=None)
    predict.add_argument("--group-goal-diff-b", type=int, default=None)
    predict.add_argument("--group-matches-played-a", type=int, default=None)
    predict.add_argument("--group-matches-played-b", type=int, default=None)
    predict.add_argument("--weather-stress", type=float, default=None)
    predict.add_argument("--importance", type=float, default=None)
    predict.add_argument("--top-scores", type=int, default=6)
    predict.add_argument("--show-factors", action="store_true")
    predict.add_argument("--monte-carlo", type=int, default=0)
    predict.add_argument("--seed", type=int, default=None)
    predict.add_argument("--state-file", default=str(STATE_FILE))
    predict.add_argument("--ignore-state", action="store_true")

    power_table = subparsers.add_parser(
        "power-table", help="Tabla base de fuerza y gol esperado vs rival promedio."
    )
    power_table.add_argument("--only-confirmed", action="store_true")

    playoffs = subparsers.add_parser(
        "playoffs", help="Probabilidades de clasificar desde repechajes."
    )
    playoffs.add_argument("--iterations", type=int, default=10000)

    fixtures = subparsers.add_parser(
        "fixtures", help="Lee un JSON de partidos y genera predicciones."
    )
    fixtures.add_argument("path")
    fixtures.add_argument("--top-scores", type=int, default=5)
    fixtures.add_argument("--show-factors", action="store_true")
    fixtures.add_argument("--state-file", default=str(STATE_FILE))
    fixtures.add_argument("--reset-state", action="store_true")
    fixtures.add_argument("--no-save-state", action="store_true")

    simulate = subparsers.add_parser(
        "simulate-tournament",
        help="Simula el Mundial completo con Monte Carlo a partir de un cuadro en JSON.",
    )
    simulate.add_argument(
        "--config",
        default=str(TOURNAMENT_CONFIG_FILE),
        help="Ruta al JSON del cuadro del torneo.",
    )
    simulate.add_argument("--iterations", type=int, default=5000)
    simulate.add_argument("--top", type=int, default=20)
    simulate.add_argument("--full", action="store_true")
    simulate.add_argument("--seed", type=int, default=None)
    simulate.add_argument("--progress-every", type=int, default=0)
    simulate.add_argument("--state-file", default=str(STATE_FILE))
    simulate.add_argument("--ignore-state", action="store_true")

    project = subparsers.add_parser(
        "project-bracket",
        help="Genera una llave proyectada actual en Markdown usando Monte Carlo.",
    )
    project.add_argument(
        "--config",
        default=str(TOURNAMENT_CONFIG_FILE),
        help="Ruta al JSON del cuadro del torneo.",
    )
    project.add_argument("--iterations", type=int, default=1000)
    project.add_argument("--seed", type=int, default=None)
    project.add_argument("--progress-every", type=int, default=0)
    project.add_argument("--output", default=str(BRACKET_FILE))
    project.add_argument("--json-output", default=str(BRACKET_JSON_FILE))
    project.add_argument("--state-file", default=str(STATE_FILE))
    project.add_argument("--ignore-state", action="store_true")

    dashboard = subparsers.add_parser(
        "project-dashboard",
        help="Genera un reporte actual con llave y probabilidades por partido.",
    )
    dashboard.add_argument("--fixtures", default=str(Path(__file__).with_name("fixtures_template.json")))
    dashboard.add_argument("--bracket-file", default=str(BRACKET_FILE))
    dashboard.add_argument("--bracket-json-file", default=str(BRACKET_JSON_FILE))
    dashboard.add_argument("--output-html", default=str(DASHBOARD_HTML_FILE))
    dashboard.add_argument("--output-md", default=str(DASHBOARD_MD_FILE))
    dashboard.add_argument("--top-scores", type=int, default=5)
    dashboard.add_argument("--state-file", default=str(STATE_FILE))

    score_prob = subparsers.add_parser(
        "score-prob",
        help="Da la probabilidad exacta de un marcador especifico.",
    )
    score_prob.add_argument("team_a")
    score_prob.add_argument("team_b")
    score_prob.add_argument("goals_a", type=int)
    score_prob.add_argument("goals_b", type=int)
    score_prob.add_argument("--neutral", action="store_true", default=False)
    score_prob.add_argument("--home-team", default=None)
    score_prob.add_argument("--venue-country", default=None)
    score_prob.add_argument("--knockout", action="store_true")
    score_prob.add_argument("--stage", default=None)
    score_prob.add_argument("--group", default=None)
    score_prob.add_argument("--state-file", default=str(STATE_FILE))
    score_prob.add_argument("--ignore-state", action="store_true")

    profile_parser = subparsers.add_parser(
        "team-profile", help="Muestra todas las variables internas de una seleccion."
    )
    profile_parser.add_argument("team")

    state_show = subparsers.add_parser(
        "state-show", help="Muestra el estado persistente que se actualiza automaticamente."
    )
    state_show.add_argument("--team", default=None)
    state_show.add_argument("--state-file", default=str(STATE_FILE))
    state_show.add_argument("--full", action="store_true")

    state_reset = subparsers.add_parser(
        "state-reset", help="Reinicia el archivo de estado persistente del torneo."
    )
    state_reset.add_argument("--state-file", default=str(STATE_FILE))

    subparsers.add_parser("list-teams", help="Lista las selecciones cargadas.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    teams = load_teams()

    if args.command == "predict":
        command_predict(args, teams)
    elif args.command == "score-prob":
        command_score_prob(args, teams)
    elif args.command == "power-table":
        command_power_table(args, teams)
    elif args.command == "playoffs":
        command_playoffs(args, teams)
    elif args.command == "fixtures":
        command_fixtures(args, teams)
    elif args.command == "simulate-tournament":
        command_simulate_tournament(args, teams)
    elif args.command == "project-bracket":
        command_project_bracket(args, teams)
    elif args.command == "project-dashboard":
        command_project_dashboard(args, teams)
    elif args.command == "state-show":
        command_state_show(args, teams)
    elif args.command == "state-reset":
        command_state_reset(args, teams)
    elif args.command == "list-teams":
        command_list_teams(teams)
    elif args.command == "team-profile":
        team_name = resolve_team_name(args.team, teams)
        print_team_profile(teams[team_name])
    else:
        parser.error("Comando no soportado.")


if __name__ == "__main__":
    main()
