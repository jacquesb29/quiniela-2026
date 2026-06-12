#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import subprocess
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlencode, urlparse

from modelo_quiniela_2026 import BRACKET_MATCH_TITLES, load_teams, profile_for, qualification_probabilities, resolve_team_name


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = SCRIPT_DIR / "fixtures_live_2026.json"
LIVE_SYNC_STATUS_FILE = SCRIPT_DIR / "live_sync_status.json"
SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
    "?dates=20260611-20260719&limit=200"
)
SUMMARY_URL_TEMPLATE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={event_id}"
SUMMARY_FETCH_WINDOW_DAYS = int(os.environ.get("SUMMARY_FETCH_WINDOW_DAYS", "10") or "10")
SUMMARY_POST_LOOKBACK_DAYS = int(os.environ.get("SUMMARY_POST_LOOKBACK_DAYS", "3") or "3")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
API_FOOTBALL_BASE_URL = (os.environ.get("API_FOOTBALL_BASE_URL") or "https://v3.football.api-sports.io").rstrip("/")
API_FOOTBALL_HOST = os.environ.get("API_FOOTBALL_HOST", "v3.football.api-sports.io").strip()
SPORTMONKS_TOKEN = os.environ.get("SPORTMONKS_TOKEN", "").strip()
SPORTMONKS_BASE_URL = (os.environ.get("SPORTMONKS_BASE_URL") or "https://api.sportmonks.com/v3").rstrip("/")
SPORTMONKS_LIVESCORES_PATH = os.environ.get("SPORTMONKS_LIVESCORES_PATH", "/football/livescores/inplay").strip()
SPORTMONKS_INCLUDES = os.environ.get(
    "SPORTMONKS_INCLUDES",
    "scores;events.type;participants;statistics.type;lineups.details.type;sidelined;venue;referees",
).strip()
FOOTBALL_DATA_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
FOOTBALL_DATA_BASE_URL = (os.environ.get("FOOTBALL_DATA_BASE_URL") or "https://api.football-data.org/v4").rstrip("/")
FOOTBALL_DATA_COMPETITION = os.environ.get("FOOTBALL_DATA_COMPETITION", "WC").strip()
FOOTBALL_DATA_SEASON = os.environ.get("FOOTBALL_DATA_SEASON", "2026").strip()
THESPORTSDB_KEY = os.environ.get("THESPORTSDB_KEY", "").strip()
THESPORTSDB_BASE_URL = (os.environ.get("THESPORTSDB_BASE_URL") or "https://www.thesportsdb.com/api/v1/json").rstrip("/")
THESPORTSDB_LIVESCORE_QUERY = os.environ.get("THESPORTSDB_LIVESCORE_QUERY", "s=Soccer").strip()
THE_ODDS_API_KEY = os.environ.get("THE_ODDS_API_KEY", "").strip()
THE_ODDS_API_BASE_URL = (os.environ.get("THE_ODDS_API_BASE_URL") or "https://api.the-odds-api.com/v4").rstrip("/")
THE_ODDS_API_SPORTS = [
    item.strip()
    for item in os.environ.get("THE_ODDS_API_SPORTS", "soccer_fifa_world_cup").split(",")
    if item.strip()
]
THE_ODDS_API_REGIONS = os.environ.get("THE_ODDS_API_REGIONS", "us,eu,uk").strip()
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "").strip()
NEWSAPI_BASE_URL = (os.environ.get("NEWSAPI_BASE_URL") or "https://newsapi.org/v2/everything").strip()
GDELT_DOC_API = (os.environ.get("GDELT_DOC_API") or "https://api.gdeltproject.org/api/v2/doc/doc").strip()
NEWS_LOOKAHEAD_DAYS = int(os.environ.get("NEWS_LOOKAHEAD_DAYS", "30") or "30")
NEWS_MAX_FIXTURES = int(os.environ.get("NEWS_MAX_FIXTURES", "8") or "8")
NEWS_POST_LOOKBACK_DAYS = int(os.environ.get("NEWS_POST_LOOKBACK_DAYS", "2") or "2")
CURL_MAX_TIME_SECONDS = int(os.environ.get("CURL_MAX_TIME_SECONDS", "30") or "30")

PRIMARY_DEEP_LIVE_PROVIDER = {
    "name": "API-Football / API-SPORTS",
    "provider_id": "api_football",
    "env": "API_FOOTBALL_KEY",
    "reason": (
        "Proveedor live profundo elegido para automatizar el in-play: ya esta cableado "
        "y puede aportar fixtures live, eventos, lineups y estadisticas cuando la key existe."
    ),
    "auto_update": "GitHub Actions lo intenta en cada corrida de 5 minutos si API_FOOTBALL_KEY esta configurada.",
    "fallback": "Si no hay key o el feed no devuelve el partido, el pipeline sigue con ESPN scoreboard + GDELT + Open-Meteo.",
}

COUNTRY_MAP = {
    "USA": "United States",
    "United States of America": "United States",
    "Mexico": "Mexico",
    "Canada": "Canada",
}

CONFED_TRAVEL_BASELINE_KM = {
    "UEFA": 6400.0,
    "CONMEBOL": 5200.0,
    "AFC": 10800.0,
    "CAF": 8600.0,
    "CONCACAF": 1200.0,
    "OFC": 12200.0,
}

PLACEHOLDER_PATHS = {
    "UEFA_A": ["Bosnia and Herzegovina"],
    "UEFA_B": ["Sweden"],
    "UEFA_C": ["Turkey"],
    "UEFA_D": ["Czech Republic"],
    "FIFA_1": ["Dem. Rep. of Congo"],
    "FIFA_2": ["Iraq"],
}

API_FOOTBALL_STAT_MAP = {
    "ball possession": "possession",
    "shots on goal": "shots_on_target",
    "shots off goal": "shots_off_target",
    "total shots": "shots",
    "blocked shots": "blocked_shots",
    "shots insidebox": "shots_inside_box",
    "shots outsidebox": "shots_outside_box",
    "corner kicks": "corners",
    "fouls": "fouls",
    "yellow cards": "yellow_cards",
    "red cards": "red_cards",
    "expected goals": "xg",
}

SHOT_EVENT_POSITIVE_TOKENS = (
    "goal",
    "shot on goal",
    "shot off goal",
    "blocked shot",
    "missed penalty",
    "penalty",
)

TOURNAMENT_STAGE_ORDER = (
    [("group", None)] * 72
    + [("round32", f"M{match_number}") for match_number in range(73, 89)]
    + [("round16", f"M{match_number}") for match_number in range(89, 97)]
    + [("quarterfinal", f"M{match_number}") for match_number in range(97, 101)]
    + [("semifinal", "M101"), ("semifinal", "M102")]
    + [("third_place", "M104"), ("final", "M103")]
)

# Approximate venue-level climate baselines for June/July, used until forecast data is available.
VENUE_DATA = {
    "AT&T Stadium": {
        "lat": 32.7473,
        "lon": -97.0945,
        "altitude_m": 163,
        "country": "United States",
        "temp_c": 32.0,
        "humidity": 55.0,
        "precip": 24.0,
        "wind_kmh": 15.0,
        "wet_bulb_c": 23.0,
    },
    "BC Place": {
        "lat": 49.2778,
        "lon": -123.1119,
        "altitude_m": 14,
        "country": "Canada",
        "temp_c": 21.0,
        "humidity": 71.0,
        "precip": 35.0,
        "wind_kmh": 10.0,
        "wet_bulb_c": 16.0,
    },
    "BMO Field": {
        "lat": 43.6332,
        "lon": -79.4186,
        "altitude_m": 76,
        "country": "Canada",
        "temp_c": 25.0,
        "humidity": 63.0,
        "precip": 28.0,
        "wind_kmh": 14.0,
        "wet_bulb_c": 18.0,
    },
    "Estadio Akron": {
        "lat": 20.6829,
        "lon": -103.4623,
        "altitude_m": 1566,
        "country": "Mexico",
        "temp_c": 25.0,
        "humidity": 55.0,
        "precip": 35.0,
        "wind_kmh": 11.0,
        "wet_bulb_c": 17.0,
    },
    "Estadio BBVA": {
        "lat": 25.6690,
        "lon": -100.2440,
        "altitude_m": 534,
        "country": "Mexico",
        "temp_c": 31.0,
        "humidity": 57.0,
        "precip": 30.0,
        "wind_kmh": 13.0,
        "wet_bulb_c": 23.0,
    },
    "Estadio Banorte": {
        "lat": 19.3029,
        "lon": -99.1505,
        "altitude_m": 2240,
        "country": "Mexico",
        "temp_c": 22.0,
        "humidity": 56.0,
        "precip": 40.0,
        "wind_kmh": 12.0,
        "wet_bulb_c": 16.0,
    },
    "GEHA Field at Arrowhead Stadium": {
        "lat": 39.0489,
        "lon": -94.4839,
        "altitude_m": 265,
        "country": "United States",
        "temp_c": 30.0,
        "humidity": 63.0,
        "precip": 32.0,
        "wind_kmh": 14.0,
        "wet_bulb_c": 22.0,
    },
    "Gillette Stadium": {
        "lat": 42.0909,
        "lon": -71.2643,
        "altitude_m": 95,
        "country": "United States",
        "temp_c": 26.0,
        "humidity": 67.0,
        "precip": 30.0,
        "wind_kmh": 12.0,
        "wet_bulb_c": 19.0,
    },
    "Hard Rock Stadium": {
        "lat": 25.9580,
        "lon": -80.2389,
        "altitude_m": 4,
        "country": "United States",
        "temp_c": 31.0,
        "humidity": 74.0,
        "precip": 48.0,
        "wind_kmh": 15.0,
        "wet_bulb_c": 26.0,
    },
    "Levi's Stadium": {
        "lat": 37.4030,
        "lon": -121.9700,
        "altitude_m": 18,
        "country": "United States",
        "temp_c": 24.0,
        "humidity": 60.0,
        "precip": 8.0,
        "wind_kmh": 12.0,
        "wet_bulb_c": 17.0,
    },
    "Lincoln Financial Field": {
        "lat": 39.9008,
        "lon": -75.1675,
        "altitude_m": 12,
        "country": "United States",
        "temp_c": 29.0,
        "humidity": 66.0,
        "precip": 32.0,
        "wind_kmh": 12.0,
        "wet_bulb_c": 22.0,
    },
    "Lumen Field": {
        "lat": 47.5952,
        "lon": -122.3316,
        "altitude_m": 5,
        "country": "United States",
        "temp_c": 23.0,
        "humidity": 65.0,
        "precip": 22.0,
        "wind_kmh": 10.0,
        "wet_bulb_c": 17.0,
    },
    "Mercedes-Benz Stadium": {
        "lat": 33.7554,
        "lon": -84.4008,
        "altitude_m": 320,
        "country": "United States",
        "temp_c": 30.0,
        "humidity": 70.0,
        "precip": 38.0,
        "wind_kmh": 11.0,
        "wet_bulb_c": 24.0,
    },
    "MetLife Stadium": {
        "lat": 40.8135,
        "lon": -74.0745,
        "altitude_m": 9,
        "country": "United States",
        "temp_c": 29.0,
        "humidity": 68.0,
        "precip": 34.0,
        "wind_kmh": 13.0,
        "wet_bulb_c": 22.0,
    },
    "NRG Stadium": {
        "lat": 29.6847,
        "lon": -95.4107,
        "altitude_m": 12,
        "country": "United States",
        "temp_c": 33.0,
        "humidity": 73.0,
        "precip": 40.0,
        "wind_kmh": 12.0,
        "wet_bulb_c": 27.0,
    },
    "SoFi Stadium": {
        "lat": 33.9535,
        "lon": -118.3392,
        "altitude_m": 43,
        "country": "United States",
        "temp_c": 26.0,
        "humidity": 70.0,
        "precip": 6.0,
        "wind_kmh": 11.0,
        "wet_bulb_c": 20.0,
    },
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_previous_fixtures() -> Dict[str, dict]:
    if not OUTPUT_FILE.exists():
        return {}
    try:
        payload = json.loads(OUTPUT_FILE.read_text())
    except Exception:
        return {}
    return {str(item.get("id")): item for item in payload if item.get("id")}


PERSISTABLE_ENRICHMENT_KEYS = (
    "market_provider",
    "market_summary",
    "market_prob_a",
    "market_prob_draw",
    "market_prob_b",
    "market_total_line",
    "market_moneyline_a",
    "market_moneyline_draw",
    "market_moneyline_b",
    "starting_xi_a",
    "starting_xi_b",
    "starting_goalkeeper_a",
    "starting_goalkeeper_b",
    "lineup_status_a",
    "lineup_status_b",
    "lineup_confirmed_a",
    "lineup_confirmed_b",
    "lineup_change_count_a",
    "lineup_change_count_b",
    "injuries_a",
    "injuries_b",
    "unavailable_count_a",
    "unavailable_count_b",
    "questionable_count_a",
    "questionable_count_b",
    "unavailable_notes_a",
    "unavailable_notes_b",
    "unavailable_players_a",
    "unavailable_players_b",
    "news_headlines",
    "news_notes_a",
    "news_notes_b",
    "open_news_provider",
    "open_news_sources",
    "morale_a",
    "morale_b",
)


def empty_enrichment_value(value: object) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, (list, dict, tuple, set)) and not value:
        return True
    return False


def preserve_previous_enrichment(fixtures: List[dict], previous_by_id: Dict[str, dict]) -> None:
    """Keep the latest enriched signal when the fast refresh does not re-query it.

    The five-minute workflow intentionally limits expensive news/summary calls.
    Without this merge, a fast refresh can accidentally erase market odds, open
    news, injuries, or lineup fields that were gathered by a deeper run.
    """
    for fixture in fixtures:
        previous = previous_by_id.get(str(fixture.get("id"))) or {}
        if not previous:
            continue
        for key in PERSISTABLE_ENRICHMENT_KEYS:
            if key not in previous:
                continue
            if empty_enrichment_value(fixture.get(key)) and not empty_enrichment_value(previous.get(key)):
                fixture[key] = previous[key]

        previous_source = str(previous.get("source") or "")
        current_source = str(fixture.get("source") or "espn_scoreboard")
        if "open_news" in previous_source and "open_news" not in current_source:
            fixture["source"] = f"{current_source}+open_news"


def run_curl_json(url: str, headers: Optional[Dict[str, str]] = None) -> dict:
    command = ["curl", "-sL", "--max-time", str(CURL_MAX_TIME_SECONDS)]
    for key, value in (headers or {}).items():
        command.extend(["-H", f"{key}: {value}"])
    command.append(url)
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def provider_enabled() -> bool:
    return bool(API_FOOTBALL_KEY or SPORTMONKS_TOKEN)


def configured_provider_names() -> List[str]:
    providers = []
    if API_FOOTBALL_KEY:
        providers.append("api_football")
    if SPORTMONKS_TOKEN:
        providers.append("sportmonks")
    if FOOTBALL_DATA_TOKEN:
        providers.append("football_data")
    if THESPORTSDB_KEY:
        providers.append("thesportsdb")
    if NEWSAPI_KEY:
        providers.append("newsapi")
    if GDELT_DOC_API:
        providers.append("gdelt")
    if THE_ODDS_API_KEY:
        providers.append("the_odds_api")
    return providers


def api_football_headers() -> Dict[str, str]:
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    if API_FOOTBALL_HOST:
        headers["x-rapidapi-host"] = API_FOOTBALL_HOST
    return headers


def api_football_url(path: str, **params: object) -> str:
    query = {key: value for key, value in params.items() if value not in (None, "", [])}
    return f"{API_FOOTBALL_BASE_URL}{path}?{urlencode(query, doseq=True)}"


def api_football_enabled() -> bool:
    return bool(API_FOOTBALL_KEY)


def sportmonks_enabled() -> bool:
    return bool(SPORTMONKS_TOKEN)


def sportmonks_url(path: str, **params: object) -> str:
    query = {key: value for key, value in params.items() if value not in (None, "", [])}
    query["api_token"] = SPORTMONKS_TOKEN
    path_value = path if path.startswith("/") else f"/{path}"
    return f"{SPORTMONKS_BASE_URL}{path_value}?{urlencode(query, doseq=True)}"


def football_data_enabled() -> bool:
    return bool(FOOTBALL_DATA_TOKEN)


def football_data_headers() -> Dict[str, str]:
    return {"X-Auth-Token": FOOTBALL_DATA_TOKEN}


def football_data_url() -> str:
    query = {"season": FOOTBALL_DATA_SEASON} if FOOTBALL_DATA_SEASON else {}
    suffix = f"?{urlencode(query)}" if query else ""
    return f"{FOOTBALL_DATA_BASE_URL}/competitions/{FOOTBALL_DATA_COMPETITION}/matches{suffix}"


def thesportsdb_enabled() -> bool:
    return bool(THESPORTSDB_KEY)


def thesportsdb_url() -> str:
    query = THESPORTSDB_LIVESCORE_QUERY or "s=Soccer"
    return f"{THESPORTSDB_BASE_URL}/{THESPORTSDB_KEY}/livescore.php?{query}"


def odds_api_enabled() -> bool:
    return bool(THE_ODDS_API_KEY)


def odds_api_url(sport_key: str, **params: object) -> str:
    query = {key: value for key, value in params.items() if value not in (None, "", [])}
    query["apiKey"] = THE_ODDS_API_KEY
    return f"{THE_ODDS_API_BASE_URL}/sports/{sport_key}/odds?{urlencode(query, doseq=True)}"


def newsapi_enabled() -> bool:
    return bool(NEWSAPI_KEY)


def newsapi_url(query: str) -> str:
    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 12,
        "apiKey": NEWSAPI_KEY,
    }
    return f"{NEWSAPI_BASE_URL}?{urlencode(params)}"


def gdelt_enabled() -> bool:
    return bool(GDELT_DOC_API)


def gdelt_url(query: str) -> str:
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": 12,
        "sort": "hybridrel",
    }
    return f"{GDELT_DOC_API}?{urlencode(params)}"


def normalize_key(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())


def provider_team_name(raw_name: str, teams: Dict[str, object]) -> str:
    try:
        return resolve_team_name(raw_name, teams)
    except SystemExit:
        return raw_name


def match_lookup_key(team_a: str, team_b: str) -> Tuple[str, str]:
    normalized = sorted((normalize_key(team_a), normalize_key(team_b)))
    return normalized[0], normalized[1]


def should_fetch_summary(kickoff: datetime, status_state: Optional[str]) -> bool:
    now = datetime.now(timezone.utc)
    status = str(status_state or "").strip().lower()
    if status in {
        "in",
        "live",
        "in_progress",
    }:
        return True
    if status in {"post", "final", "finished"}:
        return 0 <= (now - kickoff).total_seconds() <= SUMMARY_POST_LOOKBACK_DAYS * 86400
    return abs((kickoff - now).total_seconds()) <= SUMMARY_FETCH_WINDOW_DAYS * 86400


def american_odds_value(value) -> Optional[float]:
    """Accept ESPN's scalar or nested American-odds payloads."""
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("moneyLine", "american", "value", "odds"):
            if key in value:
                return american_odds_value(value[key])
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def american_to_implied_prob(value) -> Optional[float]:
    if value is None:
        return None
    odds = american_odds_value(value)
    if odds is None:
        return None
    if odds == 0:
        return None
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def normalize_probabilities(*values: Optional[float]) -> Tuple[Optional[float], ...]:
    present = [float(value) for value in values if value is not None and value > 0]
    if not present:
        return tuple(None for _ in values)
    total = sum(present)
    normalized = []
    for value in values:
        if value is None or value <= 0:
            normalized.append(None)
        else:
            normalized.append(float(value) / total)
    return tuple(normalized)


def walk_objects(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_objects(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_objects(item)


def extract_referee(summary_payload: dict) -> Optional[str]:
    for obj in walk_objects(summary_payload):
        for key in ("officials", "official", "referees", "referee"):
            if key not in obj:
                continue
            value = obj[key]
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        name = item.get("displayName") or item.get("fullName") or item.get("name")
                        if name:
                            return str(name)
                    elif isinstance(item, str):
                        return item
            elif isinstance(value, dict):
                name = value.get("displayName") or value.get("fullName") or value.get("name")
                if name:
                    return str(name)
            elif isinstance(value, str):
                return value
    return None


def extract_lineup_data(summary_payload: dict) -> Dict[str, dict]:
    rosters = summary_payload.get("rosters", [])
    lineup_data: Dict[str, dict] = {}
    for roster in rosters:
        side = roster.get("homeAway")
        if side not in {"home", "away"}:
            continue
        starters = []
        lineup_confirmed = False
        goalkeeper_name = None
        for obj in walk_objects(roster):
            name = obj.get("displayName") or obj.get("shortName") or obj.get("name")
            if not name:
                continue
            position_blob = nested_text(obj.get("position") or obj.get("athlete", {}).get("position") or "").lower()
            starter_flag = obj.get("starter")
            reserve_flag = obj.get("reserve")
            if starter_flag is True:
                lineup_confirmed = True
                starters.append(str(name))
                if goalkeeper_name is None and any(token in position_blob for token in ("gk", "goalkeeper", "keeper")):
                    goalkeeper_name = str(name)
            elif obj.get("formation"):
                lineup_confirmed = True
            elif reserve_flag is False and obj.get("position"):
                starters.append(str(name))
                if goalkeeper_name is None and any(token in position_blob for token in ("gk", "goalkeeper", "keeper")):
                    goalkeeper_name = str(name)
        unique_starters = []
        seen = set()
        for player_name in starters:
            if player_name in seen:
                continue
            seen.add(player_name)
            unique_starters.append(player_name)
        if goalkeeper_name is None and unique_starters:
            goalkeeper_name = unique_starters[0]
        lineup_data[side] = {
            "confirmed": lineup_confirmed or len(unique_starters) >= 11,
            "starters": unique_starters[:11],
            "goalkeeper": goalkeeper_name,
        }
    return lineup_data


ABSENCE_HARD_TOKENS = (
    "out",
    "injured",
    "injury",
    "suspended",
    "illness",
    "inactive",
    "ruled out",
    "will miss",
)

ABSENCE_SOFT_TOKENS = (
    "questionable",
    "doubtful",
    "probable",
    "fitness test",
    "late decision",
    "day-to-day",
)

NEWS_NEGATIVE_TOKENS = (
    "injury",
    "injured",
    "out",
    "ruled out",
    "will miss",
    "misses",
    "suspended",
    "ban",
    "illness",
    "doubtful",
)

NEWS_POSITIVE_TOKENS = (
    "returns",
    "return",
    "back",
    "available",
    "fit",
    "cleared",
    "ready",
    "boost",
)

NEWS_LINEUP_TOKENS = (
    "lineup",
    "starting xi",
    "starts",
    "starting",
    "bench",
    "rotation",
)


def nested_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(piece for piece in (nested_text(item) for item in value.values()) if piece)
    if isinstance(value, list):
        return " ".join(piece for piece in (nested_text(item) for item in value) if piece)
    return str(value)


def classify_absence(player_obj: dict) -> Optional[Tuple[str, float, str]]:
    if not isinstance(player_obj, dict):
        return None
    if not any(key in player_obj for key in ("displayName", "shortName", "name")):
        return None

    status_blob = " ".join(
        piece
        for piece in (
            nested_text(player_obj.get("status")),
            nested_text(player_obj.get("availability")),
            nested_text(player_obj.get("injury")),
            nested_text(player_obj.get("injuryStatus")),
            nested_text(player_obj.get("injuryNote")),
            nested_text(player_obj.get("note")),
            nested_text(player_obj.get("detail")),
            nested_text(player_obj.get("description")),
            nested_text(player_obj.get("type")),
        )
        if piece
    ).lower()
    if not status_blob:
        return None

    severity = 0.0
    if any(token in status_blob for token in ABSENCE_HARD_TOKENS):
        severity = 1.0
    elif any(token in status_blob for token in ABSENCE_SOFT_TOKENS):
        severity = 0.5
    if severity <= 0.0:
        return None

    player_name = player_obj.get("displayName") or player_obj.get("shortName") or player_obj.get("name")
    if not player_name:
        return None

    note = (
        nested_text(player_obj.get("injuryNote"))
        or nested_text(player_obj.get("detail"))
        or nested_text(player_obj.get("description"))
        or nested_text(player_obj.get("status"))
        or nested_text(player_obj.get("availability"))
    )
    return str(player_name), severity, note.strip()


def extract_absence_data(summary_payload: dict) -> Dict[str, dict]:
    absences: Dict[str, dict] = {}
    for roster in summary_payload.get("rosters", []):
        side = roster.get("homeAway")
        if side not in {"home", "away"}:
            continue
        hard_absences: List[str] = []
        soft_absences: List[str] = []
        hard_names: List[str] = []
        soft_names: List[str] = []
        seen = set()
        for obj in walk_objects(roster):
            classified = classify_absence(obj)
            if not classified:
                continue
            player_name, severity, note = classified
            key = (player_name, note)
            if key in seen:
                continue
            seen.add(key)
            label = f"{player_name}: {note}" if note else player_name
            if severity >= 1.0:
                hard_absences.append(label)
                hard_names.append(str(player_name))
            else:
                soft_absences.append(label)
                soft_names.append(str(player_name))

        load = min(0.85, 0.18 * len(hard_absences) + 0.08 * len(soft_absences))
        absences[side] = {
            "hard_count": len(hard_absences),
            "soft_count": len(soft_absences),
            "load": round(load, 3),
            "notes": (hard_absences + soft_absences)[:6],
            "players": (hard_names + soft_names)[:12],
        }
    return absences


def team_aliases(team_name: str) -> List[str]:
    aliases = {team_name.lower()}
    alias_map = {
        "United States": {"usa", "usmnt", "united states"},
        "Mexico": {"mexico", "el tri"},
        "England": {"england", "three lions"},
        "Argentina": {"argentina", "albiceleste"},
        "Brazil": {"brazil", "brasil", "selecao"},
    }
    aliases.update(alias_map.get(team_name, set()))
    return sorted(alias for alias in aliases if alias)


def extract_news_enrichment(summary_payload: dict, team_a: str, team_b: str) -> dict:
    aliases = {
        "a": team_aliases(team_a),
        "b": team_aliases(team_b),
    }
    seen = set()
    headlines: List[str] = []
    notes = {"a": [], "b": []}
    morale = {"a": 0.0, "b": 0.0}
    injury_bump = {"a": 0.0, "b": 0.0}

    for obj in walk_objects(summary_payload):
        if not isinstance(obj, dict):
            continue
        headline = obj.get("headline") or obj.get("shortHeadline") or obj.get("title")
        if not headline:
            continue
        detail = obj.get("description") or obj.get("summary") or ""
        text = str(headline).strip()
        if not text:
            continue
        if detail:
            combined = f"{text}: {str(detail).strip()}"
        else:
            combined = text
        if combined in seen:
            continue
        seen.add(combined)
        lowered = combined.lower()

        relevant_sides = [
            side
            for side, side_aliases in aliases.items()
            if any(alias in lowered for alias in side_aliases)
        ]
        has_signal = any(token in lowered for token in NEWS_NEGATIVE_TOKENS + NEWS_POSITIVE_TOKENS + NEWS_LINEUP_TOKENS)
        if not relevant_sides and not has_signal:
            continue

        headlines.append(combined)
        for side in relevant_sides:
            if any(token in lowered for token in NEWS_NEGATIVE_TOKENS):
                morale[side] -= 0.05
                injury_bump[side] += 0.06
                notes[side].append(text)
            elif any(token in lowered for token in NEWS_POSITIVE_TOKENS):
                morale[side] += 0.03
                notes[side].append(text)
            elif any(token in lowered for token in NEWS_LINEUP_TOKENS):
                morale[side] += 0.01
                notes[side].append(text)
        if len(headlines) >= 6:
            break

    payload = {}
    if headlines:
        payload["news_headlines"] = headlines[:5]
    for side, prefix in (("a", "a"), ("b", "b")):
        if notes[side]:
            payload[f"news_notes_{prefix}"] = notes[side][:4]
        if abs(morale[side]) > 1e-9:
            payload[f"morale_{prefix}"] = max(-0.18, min(0.18, round(morale[side], 3)))
        if injury_bump[side] > 0.0:
            payload[f"news_injury_bump_{prefix}"] = round(min(0.18, injury_bump[side]), 3)
    return payload


def article_source_name(article: dict) -> str:
    source = article.get("source")
    if isinstance(source, dict):
        name = source.get("name")
        if name:
            return str(name)
    for key in ("sourceCommonName", "domain", "url"):
        value = article.get(key)
        if not value:
            continue
        if key == "url":
            parsed = urlparse(str(value))
            return parsed.netloc or str(value)
        return str(value)
    return "fuente abierta"


def article_title_text(article: dict) -> str:
    return str(
        article.get("title")
        or article.get("headline")
        or article.get("seendate")
        or ""
    ).strip()


def article_body_text(article: dict) -> str:
    return " ".join(
        str(piece).strip()
        for piece in (
            article_title_text(article),
            article.get("description"),
            article.get("summary"),
            article.get("sourceCommonName"),
        )
        if piece
    )


def classify_open_news_articles(articles: Sequence[dict], team_a: str, team_b: str, provider: str) -> dict:
    aliases = {
        "a": team_aliases(team_a),
        "b": team_aliases(team_b),
    }
    headlines: List[str] = []
    notes = {"a": [], "b": []}
    morale = {"a": 0.0, "b": 0.0}
    injury_bump = {"a": 0.0, "b": 0.0}
    seen = set()
    source_names = []

    for article in articles:
        if not isinstance(article, dict):
            continue
        text = article_body_text(article)
        title = article_title_text(article)
        if not text or not title:
            continue
        lowered = text.lower()
        relevant_sides = [
            side
            for side, side_aliases in aliases.items()
            if any(alias in lowered for alias in side_aliases)
        ]
        has_signal = any(token in lowered for token in NEWS_NEGATIVE_TOKENS + NEWS_POSITIVE_TOKENS + NEWS_LINEUP_TOKENS)
        if not relevant_sides or not has_signal:
            continue

        source_name = article_source_name(article)
        headline = f"{source_name}: {title}"
        if headline in seen:
            continue
        seen.add(headline)
        source_names.append(source_name)
        headlines.append(headline)
        for side in relevant_sides:
            if any(token in lowered for token in NEWS_NEGATIVE_TOKENS):
                morale[side] -= 0.04
                injury_bump[side] += 0.05
                notes[side].append(headline)
            elif any(token in lowered for token in NEWS_POSITIVE_TOKENS):
                morale[side] += 0.025
                notes[side].append(headline)
            elif any(token in lowered for token in NEWS_LINEUP_TOKENS):
                morale[side] += 0.008
                notes[side].append(headline)
        if len(headlines) >= 5:
            break

    if not headlines:
        return {}

    payload: Dict[str, object] = {
        "open_news_provider": provider,
        "open_news_sources": sorted(set(source_names))[:6],
        "news_headlines": headlines[:5],
    }
    for side, prefix in (("a", "a"), ("b", "b")):
        if notes[side]:
            payload[f"news_notes_{prefix}"] = notes[side][:4]
        if abs(morale[side]) > 1e-9:
            payload[f"morale_{prefix}"] = max(-0.14, min(0.14, round(morale[side], 3)))
        if injury_bump[side] > 0.0:
            payload[f"news_injury_bump_{prefix}"] = round(min(0.16, injury_bump[side]), 3)
    return payload


def open_news_query(team_a: str, team_b: str) -> str:
    team_terms = f'"{team_a}" OR "{team_b}"'
    signal_terms = "injury OR injured OR suspended OR doubtful OR lineup OR squad OR return OR ruled out"
    return f"({team_terms}) (World Cup OR FIFA OR soccer OR football) ({signal_terms})"


def fetch_gdelt_news_for_fixture(team_a: str, team_b: str) -> dict:
    if not gdelt_enabled():
        return {}
    try:
        payload = run_curl_json(gdelt_url(open_news_query(team_a, team_b)))
    except Exception:
        return {}
    return classify_open_news_articles(payload.get("articles") or [], team_a, team_b, "gdelt")


def fetch_newsapi_news_for_fixture(team_a: str, team_b: str) -> dict:
    if not newsapi_enabled():
        return {}
    try:
        payload = run_curl_json(newsapi_url(open_news_query(team_a, team_b)))
    except Exception:
        return {}
    return classify_open_news_articles(payload.get("articles") or [], team_a, team_b, "newsapi")


def merge_news_payload(base: dict, extra: dict) -> dict:
    if not extra:
        return base
    merged = dict(base)
    for key, value in extra.items():
        if key in {"news_headlines", "open_news_sources", "news_notes_a", "news_notes_b"}:
            current = list(merged.get(key, []) or [])
            for item in value or []:
                if item not in current:
                    current.append(item)
            merged[key] = current[:8]
        elif key in {"morale_a", "morale_b", "news_injury_bump_a", "news_injury_bump_b"}:
            merged[key] = round(float(merged.get(key, 0.0) or 0.0) + float(value or 0.0), 3)
        elif key == "open_news_provider" and merged.get(key):
            providers = [str(item) for item in (merged[key], value) if item]
            merged[key] = "+".join(dict.fromkeys(providers))
        else:
            merged[key] = value
    return merged


def fixture_should_fetch_open_news(fixture: dict) -> bool:
    status = str(fixture.get("status_state") or "").lower()
    if status in {"in", "live", "in_progress"}:
        return True
    kickoff_text = fixture.get("kickoff_utc")
    if not kickoff_text:
        return False
    try:
        kickoff = parse_iso_utc(str(kickoff_text))
    except Exception:
        return False
    now = datetime.now(timezone.utc)
    if status in {"post", "final", "finished"}:
        return 0 <= (now - kickoff).total_seconds() <= NEWS_POST_LOOKBACK_DAYS * 86400
    return -2 <= (kickoff - now).days <= NEWS_LOOKAHEAD_DAYS


def annotate_open_news(fixtures: List[dict]) -> None:
    fetched = 0
    for fixture in fixtures:
        if fetched >= NEWS_MAX_FIXTURES:
            break
        if fixture.get("projection_only") or not fixture_should_fetch_open_news(fixture):
            continue
        team_a = str(fixture.get("team_a") or "")
        team_b = str(fixture.get("team_b") or "")
        if not team_a or not team_b:
            continue
        news_payload = {}
        news_payload = merge_news_payload(news_payload, fetch_gdelt_news_for_fixture(team_a, team_b))
        news_payload = merge_news_payload(news_payload, fetch_newsapi_news_for_fixture(team_a, team_b))
        if not news_payload:
            continue
        for prefix in ("a", "b"):
            injury_bump = float(news_payload.pop(f"news_injury_bump_{prefix}", 0.0) or 0.0)
            if injury_bump > 0.0:
                news_payload[f"injuries_{prefix}"] = round(
                    min(0.9, float(fixture.get(f"injuries_{prefix}", 0.0) or 0.0) + injury_bump),
                    3,
                )
        fixture.update(merge_news_payload(fixture, news_payload))
        existing_source = str(fixture.get("source") or "espn_scoreboard")
        if "open_news" not in existing_source:
            fixture["source"] = f"{existing_source}+open_news"
        fetched += 1


def summarize_market(odds_entry: dict) -> dict:
    home_line = american_odds_value(odds_entry.get("homeTeamOdds", {}).get("moneyLine"))
    away_line = american_odds_value(odds_entry.get("awayTeamOdds", {}).get("moneyLine"))
    draw_line = american_odds_value(odds_entry.get("drawOdds"))
    prob_a, prob_draw, prob_b = normalize_probabilities(
        american_to_implied_prob(home_line),
        american_to_implied_prob(draw_line),
        american_to_implied_prob(away_line),
    )
    details = []
    if home_line is not None:
        details.append(f"1 {home_line}")
    if draw_line is not None:
        details.append(f"X {draw_line}")
    if away_line is not None:
        details.append(f"2 {away_line}")
    if odds_entry.get("overUnder") is not None:
        details.append(f"O/U {odds_entry['overUnder']}")
    return {
        "market_provider": odds_entry.get("provider", {}).get("name"),
        "market_summary": " | ".join(details) if details else None,
        "market_prob_a": prob_a,
        "market_prob_draw": prob_draw,
        "market_prob_b": prob_b,
        "market_total_line": odds_entry.get("overUnder"),
        "market_moneyline_a": home_line,
        "market_moneyline_draw": draw_line,
        "market_moneyline_b": away_line,
    }


def parse_numeric_stat(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_stat_label(value: str) -> str:
    return "".join(char for char in str(value).lower() if char.isalnum() or char.isspace()).strip()


def stat_key_from_label(label: str) -> Optional[str]:
    normalized = normalize_stat_label(label)
    if any(token in normalized for token in ("expected goals", "expectedgoal", "xg")):
        return "xg"
    if "shots on target" in normalized or "shots on goal" in normalized:
        return "shots_on_target"
    if normalized in {"shots", "total shots"} or ("shots" in normalized and "target" not in normalized and "goal" not in normalized):
        return "shots"
    if "possession" in normalized:
        return "possession"
    if "corner" in normalized:
        return "corners"
    if "foul" in normalized:
        return "fouls"
    if "yellow" in normalized:
        return "yellow_cards"
    if "red" in normalized:
        return "red_cards"
    return None


def live_xg_proxy(stats: Dict[str, float]) -> Optional[float]:
    shots = float(stats.get("shots", 0.0))
    shots_on_target = float(stats.get("shots_on_target", 0.0))
    corners = float(stats.get("corners", 0.0))
    if shots <= 0.0 and shots_on_target <= 0.0 and corners <= 0.0:
        return None
    non_target = max(shots - shots_on_target, 0.0)
    return round(0.11 * shots_on_target + 0.03 * non_target + 0.02 * corners, 3)


def extract_live_statistics(summary_payload: dict) -> dict:
    by_side: Dict[str, Dict[str, float]] = {"home": {}, "away": {}}
    for obj in walk_objects(summary_payload):
        if not isinstance(obj, dict):
            continue
        side = obj.get("homeAway")
        stats = obj.get("statistics")
        if side not in {"home", "away"} or not isinstance(stats, list):
            continue
        for stat in stats:
            if not isinstance(stat, dict):
                continue
            label = (
                stat.get("displayName")
                or stat.get("name")
                or stat.get("shortDisplayName")
                or stat.get("abbreviation")
            )
            key = stat_key_from_label(str(label or ""))
            if not key:
                continue
            value = (
                stat.get("displayValue")
                if stat.get("displayValue") is not None
                else stat.get("value")
            )
            parsed = parse_numeric_stat(value)
            if parsed is None:
                continue
            by_side[side][key] = parsed

    enrichment = {}
    for side, prefix in (("home", "a"), ("away", "b")):
        stats = by_side.get(side, {})
        for stat_key, value in stats.items():
            enrichment[f"live_{stat_key}_{prefix}"] = value
        proxy = live_xg_proxy(stats)
        if proxy is not None and f"live_xg_{prefix}" not in enrichment:
            enrichment[f"live_xg_proxy_{prefix}"] = proxy
        elif proxy is not None:
            enrichment[f"live_xg_proxy_{prefix}"] = proxy
    return enrichment


def api_football_stat_key(label: str) -> Optional[str]:
    normalized = normalize_stat_label(label)
    return API_FOOTBALL_STAT_MAP.get(normalized)


def api_football_side(home_first: bool, index: int) -> str:
    return "a" if (index == 0 and home_first) or (index == 1 and not home_first) else "b"


def parse_api_football_statistics(payload: dict, home_name: str, away_name: str, team_a: str, team_b: str) -> dict:
    enrichment: Dict[str, object] = {}
    stats_rows = payload.get("response") or []
    home_first = normalize_key(team_a) == normalize_key(home_name)
    by_side: Dict[str, Dict[str, float]] = {"a": {}, "b": {}}

    for index, row in enumerate(stats_rows[:2]):
        side = api_football_side(home_first, index)
        for stat in row.get("statistics", []):
            key = api_football_stat_key(str(stat.get("type") or ""))
            if not key:
                continue
            parsed = parse_numeric_stat(stat.get("value"))
            if parsed is None:
                continue
            by_side[side][key] = parsed

    for side in ("a", "b"):
        stats = by_side[side]
        for stat_key, value in stats.items():
            enrichment[f"live_{stat_key}_{side}"] = value

        xg = stats.get("xg")
        if xg is not None:
            enrichment[f"live_xg_{side}"] = round(float(xg), 3)

        shots = float(stats.get("shots", 0.0))
        shots_on_target = float(stats.get("shots_on_target", 0.0))
        shots_off_target = float(stats.get("shots_off_target", max(shots - shots_on_target, 0.0)))
        blocked = float(stats.get("blocked_shots", 0.0))
        inside_box = float(stats.get("shots_inside_box", 0.0))
        outside_box = float(stats.get("shots_outside_box", 0.0))
        if enrichment.get(f"live_xg_{side}") is None:
            deeper_proxy = (
                0.14 * shots_on_target
                + 0.05 * shots_off_target
                + 0.04 * blocked
                + 0.05 * inside_box
                + 0.015 * outside_box
            )
            if deeper_proxy > 0.0:
                enrichment[f"live_xg_proxy_{side}"] = round(deeper_proxy, 3)

    return enrichment


def is_shot_event(event_type: str, detail: str) -> bool:
    normalized = f"{event_type} {detail}".lower()
    return any(token in normalized for token in SHOT_EVENT_POSITIVE_TOKENS)


def infer_shot_xg(detail: str) -> float:
    normalized = detail.lower()
    if "missed penalty" in normalized or normalized == "penalty":
        return 0.76
    if "goal" in normalized:
        return 0.30
    if "blocked" in normalized:
        return 0.06
    if "on goal" in normalized:
        return 0.12
    if "off goal" in normalized:
        return 0.05
    return 0.07


def parse_api_football_events(payload: dict, home_name: str, away_name: str, team_a: str, team_b: str) -> dict:
    enrichment: Dict[str, object] = {}
    shot_logs = {"a": [], "b": []}
    shot_counts = {"a": 0, "b": 0}
    shot_xg = {"a": 0.0, "b": 0.0}
    big_chances = {"a": 0, "b": 0}
    red_cards = {"a": 0, "b": 0}
    yellow_cards = {"a": 0, "b": 0}
    substitutions = {"a": 0, "b": 0}
    substitution_logs = {"a": [], "b": []}

    for event in payload.get("response") or []:
        raw_team = (event.get("team") or {}).get("name")
        if not raw_team:
            continue
        canonical = provider_team_name(str(raw_team), {team_a: None, team_b: None})
        if normalize_key(canonical) == normalize_key(team_a):
            side = "a"
        elif normalize_key(canonical) == normalize_key(team_b):
            side = "b"
        else:
            continue

        event_type = str(event.get("type") or "")
        detail = str(event.get("detail") or "")
        minute = int((event.get("time") or {}).get("elapsed") or 0)
        player_name = ((event.get("player") or {}).get("name") or "").strip()
        comments = (event.get("comments") or "").strip()

        if event_type.lower() == "card":
            normalized = detail.lower()
            if "yellow" in normalized:
                yellow_cards[side] += 1
            if "red" in normalized:
                red_cards[side] += 1

        normalized_event = f"{event_type} {detail}".lower()
        if "subst" in normalized_event or "substitution" in normalized_event:
            substitutions[side] += 1
            substitution_logs[side].append(
                {
                    "minute": minute,
                    "player": player_name or None,
                    "detail": detail or None,
                    "comments": comments or None,
                }
            )

        if not is_shot_event(event_type, detail):
            continue

        shot_counts[side] += 1
        xg_value = infer_shot_xg(detail)
        shot_xg[side] += xg_value
        if "penalty" in detail.lower() or "goal" in detail.lower():
            big_chances[side] += 1
        shot_logs[side].append(
            {
                "minute": minute,
                "player": player_name or None,
                "type": event_type,
                "detail": detail,
                "comments": comments or None,
                "xg_proxy": round(xg_value, 3),
            }
        )

    for side in ("a", "b"):
        if shot_counts[side] > 0:
            enrichment[f"live_shot_events_{side}"] = shot_counts[side]
            enrichment[f"live_big_chances_{side}"] = big_chances[side]
            enrichment[f"live_shot_log_{side}"] = shot_logs[side][-12:]
            if enrichment.get(f"live_xg_{side}") is None:
                enrichment[f"live_xg_proxy_{side}"] = round(shot_xg[side], 3)
        if yellow_cards[side] > 0 and enrichment.get(f"live_yellow_cards_{side}") is None:
            enrichment[f"live_yellow_cards_{side}"] = yellow_cards[side]
        if red_cards[side] > 0 and enrichment.get(f"live_red_cards_{side}") is None:
            enrichment[f"live_red_cards_{side}"] = red_cards[side]
        if substitutions[side] > 0:
            enrichment[f"live_substitutions_{side}"] = substitutions[side]
            enrichment[f"live_substitution_log_{side}"] = substitution_logs[side][-8:]
    return enrichment


def extract_api_football_lineups(payload: dict, home_name: str, away_name: str, team_a: str, team_b: str) -> dict:
    enrichment: Dict[str, object] = {}
    for row in payload.get("response") or []:
        raw_team = (row.get("team") or {}).get("name") or ""
        canonical = provider_team_name(str(raw_team), {team_a: None, team_b: None})
        if normalize_key(canonical) == normalize_key(team_a):
            side = "a"
        elif normalize_key(canonical) == normalize_key(team_b):
            side = "b"
        else:
            continue

        starters = []
        goalkeeper_name = None
        for player in row.get("startXI") or []:
            player_payload = player.get("player") or {}
            name = (player_payload.get("name") or "").strip()
            if name:
                starters.append(name)
                position_blob = str(
                    player_payload.get("pos")
                    or player_payload.get("position")
                    or player.get("position")
                    or ""
                ).lower()
                if goalkeeper_name is None and any(token in position_blob for token in ("gk", "goalkeeper", "keeper")):
                    goalkeeper_name = name

        if starters:
            enrichment[f"lineup_confirmed_{side}"] = True
            enrichment[f"starting_xi_{side}"] = starters[:11]
            enrichment[f"lineup_status_{side}"] = "confirmada"
            enrichment[f"starting_goalkeeper_{side}"] = goalkeeper_name or starters[0]
            enrichment[f"goalkeeper_confirmed_{side}"] = True
    return enrichment


def fetch_api_football_fixture_details(fixture_id: int, home_name: str, away_name: str, team_a: str, team_b: str) -> dict:
    enrichment: Dict[str, object] = {
        "live_feed_provider": "api_football",
        "live_feed_depth": "eventos_y_estadisticas",
    }
    headers = api_football_headers()
    detail_calls = (
        ("/fixtures/statistics", parse_api_football_statistics),
        ("/fixtures/events", parse_api_football_events),
        ("/fixtures/lineups", extract_api_football_lineups),
    )
    for path, parser in detail_calls:
        try:
            payload = run_curl_json(api_football_url(path, fixture=fixture_id), headers=headers)
        except Exception:
            continue
        enrichment.update(parser(payload, home_name, away_name, team_a, team_b))
    return enrichment


def fetch_api_football_live_index(teams: Dict[str, object]) -> Dict[Tuple[str, str], dict]:
    if not api_football_enabled():
        return {}
    try:
        payload = run_curl_json(api_football_url("/fixtures", live="all"), headers=api_football_headers())
    except Exception:
        return {}

    index: Dict[Tuple[str, str], dict] = {}
    for row in payload.get("response") or []:
        home_raw = (((row.get("teams") or {}).get("home") or {}).get("name") or "").strip()
        away_raw = (((row.get("teams") or {}).get("away") or {}).get("name") or "").strip()
        if not home_raw or not away_raw:
            continue
        team_a = provider_team_name(home_raw, teams)
        team_b = provider_team_name(away_raw, teams)
        match_key = match_lookup_key(team_a, team_b)
        fixture_id = int(((row.get("fixture") or {}).get("id")) or 0)
        if fixture_id <= 0:
            continue

        enrichment = {
            "live_feed_provider": "api_football",
            "live_feed_depth": "eventos_y_estadisticas",
            "live_elapsed_minutes": ((row.get("fixture") or {}).get("status") or {}).get("elapsed"),
            "provider_fixture_id": fixture_id,
        }
        enrichment.update(fetch_api_football_fixture_details(fixture_id, home_raw, away_raw, team_a, team_b))
        index[match_key] = enrichment
    return index


def sportmonks_participant_side(row: dict, team_a: str, team_b: str) -> Tuple[Dict[int, str], Dict[str, str]]:
    id_to_side: Dict[int, str] = {}
    side_to_name: Dict[str, str] = {}
    participants = row.get("participants") or row.get("teams") or []
    if not isinstance(participants, list):
        return id_to_side, side_to_name

    for participant in participants:
        if not isinstance(participant, dict):
            continue
        raw_name = str(participant.get("name") or participant.get("display_name") or participant.get("short_code") or "").strip()
        participant_id = int(participant.get("id") or participant.get("team_id") or 0)
        location = str((participant.get("meta") or {}).get("location") or participant.get("location") or "").lower()
        canonical = provider_team_name(raw_name, {team_a: None, team_b: None}) if raw_name else ""
        side = None
        if canonical and normalize_key(canonical) == normalize_key(team_a):
            side = "a"
        elif canonical and normalize_key(canonical) == normalize_key(team_b):
            side = "b"
        elif location in {"home", "localteam"}:
            side = "a"
        elif location in {"away", "visitorteam"}:
            side = "b"
        if side:
            if participant_id:
                id_to_side[participant_id] = side
            side_to_name[side] = canonical or raw_name
    return id_to_side, side_to_name


def sportmonks_side_from_payload(obj: dict, id_to_side: Dict[int, str], team_a: str, team_b: str) -> Optional[str]:
    for key in ("participant_id", "team_id", "teamId"):
        try:
            raw_id = int(obj.get(key) or 0)
        except (TypeError, ValueError):
            raw_id = 0
        if raw_id in id_to_side:
            return id_to_side[raw_id]

    for key in ("participant", "team"):
        nested = obj.get(key)
        if not isinstance(nested, dict):
            continue
        nested_id = int(nested.get("id") or nested.get("team_id") or 0)
        if nested_id in id_to_side:
            return id_to_side[nested_id]
        raw_name = str(nested.get("name") or nested.get("display_name") or "").strip()
        if raw_name:
            canonical = provider_team_name(raw_name, {team_a: None, team_b: None})
            if normalize_key(canonical) == normalize_key(team_a):
                return "a"
            if normalize_key(canonical) == normalize_key(team_b):
                return "b"
    return None


def parse_sportmonks_statistics(row: dict, id_to_side: Dict[int, str], team_a: str, team_b: str) -> dict:
    enrichment: Dict[str, object] = {}
    by_side: Dict[str, Dict[str, float]] = {"a": {}, "b": {}}
    statistics = row.get("statistics") or []
    if not isinstance(statistics, list):
        return enrichment

    for stat in statistics:
        if not isinstance(stat, dict):
            continue
        side = sportmonks_side_from_payload(stat, id_to_side, team_a, team_b)
        if side not in {"a", "b"}:
            continue
        label = (
            nested_text(stat.get("type"))
            or str(stat.get("type_name") or "")
            or str(stat.get("name") or "")
            or str(stat.get("code") or "")
        )
        key = stat_key_from_label(label)
        if not key:
            continue
        value = (
            stat.get("value")
            if stat.get("value") is not None
            else (stat.get("data") or {}).get("value")
            if isinstance(stat.get("data"), dict)
            else None
        )
        parsed = parse_numeric_stat(value)
        if parsed is None:
            continue
        by_side[side][key] = parsed

    for side, stats in by_side.items():
        for stat_key, value in stats.items():
            enrichment[f"live_{stat_key}_{side}"] = value
        proxy = live_xg_proxy(stats)
        if proxy is not None and f"live_xg_{side}" not in enrichment:
            enrichment[f"live_xg_proxy_{side}"] = proxy
    return enrichment


def parse_sportmonks_events(row: dict, id_to_side: Dict[int, str], team_a: str, team_b: str) -> dict:
    enrichment: Dict[str, object] = {}
    events = row.get("events") or []
    if not isinstance(events, list):
        return enrichment

    shot_logs = {"a": [], "b": []}
    shot_counts = {"a": 0, "b": 0}
    shot_xg = {"a": 0.0, "b": 0.0}
    big_chances = {"a": 0, "b": 0}
    yellow_cards = {"a": 0, "b": 0}
    red_cards = {"a": 0, "b": 0}
    substitutions = {"a": 0, "b": 0}
    max_minute = 0

    for event in events:
        if not isinstance(event, dict):
            continue
        side = sportmonks_side_from_payload(event, id_to_side, team_a, team_b)
        if side not in {"a", "b"}:
            continue
        minute = int(event.get("minute") or event.get("sort_order") or 0)
        max_minute = max(max_minute, minute)
        label = " ".join(
            text
            for text in (
                nested_text(event.get("type")),
                str(event.get("type_name") or ""),
                str(event.get("result") or ""),
                str(event.get("info") or ""),
                str(event.get("addition") or ""),
            )
            if text
        )
        normalized = label.lower()
        if "yellow" in normalized:
            yellow_cards[side] += 1
        if "red" in normalized:
            red_cards[side] += 1
        if "substitution" in normalized or "substitution" in str(event.get("type") or "").lower():
            substitutions[side] += 1
        if not is_shot_event(normalized, normalized) and "attempt" not in normalized:
            continue
        shot_counts[side] += 1
        xg_value = infer_shot_xg(normalized)
        shot_xg[side] += xg_value
        if "penalty" in normalized or "goal" in normalized:
            big_chances[side] += 1
        player = event.get("player") or event.get("player_name") or {}
        player_name = nested_text(player) if not isinstance(player, str) else player
        shot_logs[side].append(
            {
                "minute": minute,
                "player": player_name or None,
                "type": label or "event",
                "detail": label or None,
                "xg_proxy": round(xg_value, 3),
            }
        )

    if max_minute:
        enrichment["live_elapsed_minutes"] = max_minute
    for side in ("a", "b"):
        if shot_counts[side] > 0:
            enrichment[f"live_shot_events_{side}"] = shot_counts[side]
            enrichment[f"live_big_chances_{side}"] = big_chances[side]
            enrichment[f"live_shot_log_{side}"] = shot_logs[side][-12:]
            if enrichment.get(f"live_xg_{side}") is None:
                enrichment[f"live_xg_proxy_{side}"] = round(shot_xg[side], 3)
        if yellow_cards[side]:
            enrichment[f"live_yellow_cards_{side}"] = yellow_cards[side]
        if red_cards[side]:
            enrichment[f"live_red_cards_{side}"] = red_cards[side]
        if substitutions[side]:
            enrichment[f"live_substitutions_{side}"] = substitutions[side]
    return enrichment


def parse_sportmonks_lineups(row: dict, id_to_side: Dict[int, str], team_a: str, team_b: str) -> dict:
    enrichment: Dict[str, object] = {}
    lineups = row.get("lineups") or []
    if not isinstance(lineups, list):
        return enrichment
    starters = {"a": [], "b": []}
    goalkeepers = {"a": None, "b": None}
    for item in lineups:
        if not isinstance(item, dict):
            continue
        side = sportmonks_side_from_payload(item, id_to_side, team_a, team_b)
        if side not in {"a", "b"}:
            continue
        line_type = nested_text(item.get("type") or item.get("details") or item).lower()
        if "bench" in line_type or "substitute" in line_type:
            continue
        player_payload = item.get("player") or item.get("participant") or {}
        player_name = (
            str(player_payload.get("display_name") or player_payload.get("name") or "").strip()
            if isinstance(player_payload, dict)
            else str(player_payload).strip()
        )
        if not player_name:
            continue
        starters[side].append(player_name)
        position_blob = nested_text(item.get("position") or item.get("formation_position") or item.get("details")).lower()
        if goalkeepers[side] is None and any(token in position_blob for token in ("gk", "goalkeeper", "keeper")):
            goalkeepers[side] = player_name

    for side in ("a", "b"):
        if starters[side]:
            enrichment[f"lineup_confirmed_{side}"] = len(starters[side]) >= 11
            enrichment[f"starting_xi_{side}"] = starters[side][:11]
            enrichment[f"lineup_status_{side}"] = "confirmada" if len(starters[side]) >= 11 else "parcial"
            enrichment[f"starting_goalkeeper_{side}"] = goalkeepers[side] or starters[side][0]
            enrichment[f"goalkeeper_confirmed_{side}"] = bool(goalkeepers[side])
    return enrichment


def parse_sportmonks_fixture(row: dict, team_a: str, team_b: str) -> dict:
    id_to_side, _side_names = sportmonks_participant_side(row, team_a, team_b)
    enrichment: Dict[str, object] = {
        "live_feed_provider": "sportmonks",
        "live_feed_depth": "eventos_estadisticas_lineups",
        "provider_fixture_id": row.get("id"),
    }
    status_blob = nested_text(row.get("state") or row.get("status") or "").lower()
    if status_blob:
        enrichment["provider_status_detail"] = status_blob[:120]
    enrichment.update(parse_sportmonks_statistics(row, id_to_side, team_a, team_b))
    enrichment.update(parse_sportmonks_events(row, id_to_side, team_a, team_b))
    enrichment.update(parse_sportmonks_lineups(row, id_to_side, team_a, team_b))
    return enrichment


def fetch_sportmonks_live_index(teams: Dict[str, object]) -> Dict[Tuple[str, str], dict]:
    if not sportmonks_enabled():
        return {}
    try:
        payload = run_curl_json(sportmonks_url(SPORTMONKS_LIVESCORES_PATH, include=SPORTMONKS_INCLUDES))
    except Exception:
        return {}

    index: Dict[Tuple[str, str], dict] = {}
    for row in payload.get("data") or payload.get("response") or []:
        if not isinstance(row, dict):
            continue
        _id_to_side, side_names = sportmonks_participant_side(row, "", "")
        raw_a = side_names.get("a", "")
        raw_b = side_names.get("b", "")
        if not raw_a or not raw_b:
            participants = row.get("participants") or []
            names = [str(item.get("name") or "").strip() for item in participants if isinstance(item, dict) and item.get("name")]
            if len(names) >= 2:
                raw_a, raw_b = names[0], names[1]
        if not raw_a or not raw_b:
            continue
        team_a = provider_team_name(raw_a, teams)
        team_b = provider_team_name(raw_b, teams)
        index[match_lookup_key(team_a, team_b)] = parse_sportmonks_fixture(row, team_a, team_b)
    return index


def score_to_int(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("goals", "score", "display", "current", "regularTime"):
            parsed = score_to_int(value.get(key))
            if parsed is not None:
                return parsed
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def football_data_match_score(score_payload: dict) -> Tuple[Optional[int], Optional[int]]:
    if not isinstance(score_payload, dict):
        return None, None
    for key in ("fullTime", "regularTime", "halfTime"):
        row = score_payload.get(key)
        if not isinstance(row, dict):
            continue
        home = score_to_int(row.get("home"))
        away = score_to_int(row.get("away"))
        if home is not None and away is not None:
            return home, away
    return None, None


def fetch_football_data_live_index(teams: Dict[str, object]) -> Dict[Tuple[str, str], dict]:
    if not football_data_enabled():
        return {}
    try:
        payload = run_curl_json(football_data_url(), headers=football_data_headers())
    except Exception:
        return {}

    index: Dict[Tuple[str, str], dict] = {}
    for row in payload.get("matches") or []:
        if not isinstance(row, dict):
            continue
        raw_home = str((row.get("homeTeam") or {}).get("name") or "").strip()
        raw_away = str((row.get("awayTeam") or {}).get("name") or "").strip()
        if not raw_home or not raw_away:
            continue
        team_a = provider_team_name(raw_home, teams)
        team_b = provider_team_name(raw_away, teams)
        score_a, score_b = football_data_match_score(row.get("score") or {})
        status = str(row.get("status") or "").strip().upper()
        enrichment: Dict[str, object] = {
            "live_feed_provider": "football_data",
            "live_feed_depth": "estado_y_marcador",
            "provider_fixture_id": row.get("id"),
            "provider_status_detail": status.lower(),
        }
        if status in {"LIVE", "IN_PLAY", "PAUSED"} and score_a is not None and score_b is not None:
            enrichment["live_score_a"] = score_a
            enrichment["live_score_b"] = score_b
        if status in {"FINISHED", "AWARDED"} and score_a is not None and score_b is not None:
            enrichment["actual_score_a"] = score_a
            enrichment["actual_score_b"] = score_b
            enrichment["update_state"] = True
        if status:
            enrichment["provider_match_status"] = status
        index[match_lookup_key(team_a, team_b)] = enrichment
    return index


def fetch_thesportsdb_live_index(teams: Dict[str, object]) -> Dict[Tuple[str, str], dict]:
    if not thesportsdb_enabled():
        return {}
    try:
        payload = run_curl_json(thesportsdb_url())
    except Exception:
        return {}

    rows = payload.get("events") or payload.get("event") or payload.get("livescores") or []
    if isinstance(rows, dict):
        rows = [rows]
    index: Dict[Tuple[str, str], dict] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        raw_home = str(row.get("strHomeTeam") or row.get("strHome") or row.get("homeTeam") or "").strip()
        raw_away = str(row.get("strAwayTeam") or row.get("strAway") or row.get("awayTeam") or "").strip()
        if not raw_home or not raw_away:
            continue
        team_a = provider_team_name(raw_home, teams)
        team_b = provider_team_name(raw_away, teams)
        score_a = score_to_int(row.get("intHomeScore") or row.get("intHomeGoals") or row.get("homeScore"))
        score_b = score_to_int(row.get("intAwayScore") or row.get("intAwayGoals") or row.get("awayScore"))
        progress = str(row.get("strProgress") or row.get("strStatus") or row.get("status") or "").strip()
        enrichment: Dict[str, object] = {
            "live_feed_provider": "thesportsdb",
            "live_feed_depth": "estado_y_marcador_publico",
            "provider_fixture_id": row.get("idEvent") or row.get("id"),
            "provider_status_detail": progress[:120],
        }
        if score_a is not None and score_b is not None:
            enrichment["live_score_a"] = score_a
            enrichment["live_score_b"] = score_b
        minute = score_to_int(row.get("intMinute") or row.get("strMinute") or row.get("minute"))
        if minute is not None:
            enrichment["live_elapsed_minutes"] = minute
        index[match_lookup_key(team_a, team_b)] = enrichment
    return index


def merge_provider_indexes(*indexes: Dict[Tuple[str, str], dict]) -> Dict[Tuple[str, str], dict]:
    merged: Dict[Tuple[str, str], dict] = {}
    for index in indexes:
        for key, payload in index.items():
            if not payload:
                continue
            if key not in merged:
                merged[key] = dict(payload)
                continue
            previous_provider = str(merged[key].get("live_feed_provider") or "")
            merged[key].update(payload)
            current_provider = str(payload.get("live_feed_provider") or "")
            providers = [item for item in (previous_provider, current_provider) if item]
            if providers:
                merged[key]["live_feed_provider"] = "+".join(dict.fromkeys(providers))
    return merged


def fetch_provider_live_index(teams: Dict[str, object]) -> Dict[Tuple[str, str], dict]:
    return merge_provider_indexes(
        fetch_api_football_live_index(teams),
        fetch_sportmonks_live_index(teams),
        fetch_football_data_live_index(teams),
        fetch_thesportsdb_live_index(teams),
    )


def summary_enrichment(event_id: str, kickoff: datetime, status_state: Optional[str], team_a: str, team_b: str) -> dict:
    if not should_fetch_summary(kickoff, status_state):
        return {}
    try:
        payload = run_curl_json(SUMMARY_URL_TEMPLATE.format(event_id=event_id))
    except Exception:
        return {}

    enrichment = {}
    odds = payload.get("odds") or payload.get("pickcenter") or []
    if odds:
        enrichment.update(summarize_market(odds[0]))

    referee = extract_referee(payload)
    if referee:
        enrichment["referee"] = referee

    lineups = extract_lineup_data(payload)
    for side, prefix in (("home", "a"), ("away", "b")):
        lineup = lineups.get(side)
        if not lineup:
            continue
        enrichment[f"lineup_confirmed_{prefix}"] = bool(lineup["confirmed"])
        enrichment[f"starting_xi_{prefix}"] = lineup["starters"]
        enrichment[f"lineup_status_{prefix}"] = "confirmada" if lineup["confirmed"] else "sin confirmar"
        if lineup.get("goalkeeper"):
            enrichment[f"starting_goalkeeper_{prefix}"] = lineup["goalkeeper"]
            enrichment[f"goalkeeper_confirmed_{prefix}"] = bool(lineup["confirmed"])

    absences = extract_absence_data(payload)
    for side, prefix in (("home", "a"), ("away", "b")):
        absence_data = absences.get(side)
        if not absence_data:
            continue
        enrichment[f"injuries_{prefix}"] = absence_data["load"]
        enrichment[f"unavailable_count_{prefix}"] = int(absence_data["hard_count"])
        enrichment[f"questionable_count_{prefix}"] = int(absence_data["soft_count"])
        enrichment[f"unavailable_notes_{prefix}"] = absence_data["notes"]
        enrichment[f"unavailable_players_{prefix}"] = absence_data["players"]

    news = extract_news_enrichment(payload, team_a, team_b)
    enrichment.update(news)
    enrichment.update(extract_live_statistics(payload))
    for prefix in ("a", "b"):
        injury_bump = float(enrichment.pop(f"news_injury_bump_{prefix}", 0.0) or 0.0)
        if injury_bump > 0.0:
            enrichment[f"injuries_{prefix}"] = round(
                min(0.9, float(enrichment.get(f"injuries_{prefix}", 0.0)) + injury_bump),
                3,
            )
    return enrichment


def annotate_lineup_changes(fixtures: List[dict], previous_by_id: Dict[str, dict]) -> None:
    for fixture in fixtures:
        previous = previous_by_id.get(str(fixture.get("id")))
        for side in ("a", "b"):
            current = fixture.get(f"starting_xi_{side}", [])
            previous_lineup = (previous or {}).get(f"starting_xi_{side}", [])
            if not current or not previous_lineup:
                fixture[f"lineup_change_count_{side}"] = 0
            else:
                current_set = set(current)
                previous_set = set(previous_lineup)
                fixture[f"lineup_change_count_{side}"] = len(current_set.symmetric_difference(previous_set)) // 2
            current_goalkeeper = str(fixture.get(f"starting_goalkeeper_{side}") or "").strip()
            previous_goalkeeper = str((previous or {}).get(f"starting_goalkeeper_{side}") or "").strip()
            fixture[f"goalkeeper_change_{side}"] = bool(
                current_goalkeeper and previous_goalkeeper and normalize_key(current_goalkeeper) != normalize_key(previous_goalkeeper)
            )


def annotate_market_moves(fixtures: List[dict], previous_by_id: Dict[str, dict]) -> None:
    for fixture in fixtures:
        previous = previous_by_id.get(str(fixture.get("id"))) or {}
        for key in ("a", "draw", "b"):
            current_value = fixture.get(f"market_prob_{key}")
            previous_value = previous.get(f"market_prob_{key}")
            if current_value is None or previous_value is None:
                fixture[f"market_move_{key}"] = 0.0
                continue
            fixture[f"market_move_{key}"] = round(float(current_value) - float(previous_value), 4)


def build_referee_profiles(previous_by_id: Dict[str, dict]) -> Dict[str, dict]:
    rows = []
    for fixture in previous_by_id.values():
        referee = str(fixture.get("referee") or "").strip()
        if not referee:
            continue
        yellow_total = int(fixture.get("actual_yellows_a", fixture.get("live_yellow_cards_a", 0)) or 0) + int(
            fixture.get("actual_yellows_b", fixture.get("live_yellow_cards_b", 0)) or 0
        )
        red_total = int(fixture.get("actual_reds_a", fixture.get("live_red_cards_a", 0)) or 0) + int(
            fixture.get("actual_reds_b", fixture.get("live_red_cards_b", 0)) or 0
        )
        penalty_events = 0
        for side in ("a", "b"):
            for shot in fixture.get(f"live_shot_log_{side}", []) or []:
                detail = str((shot or {}).get("detail") or "").lower()
                if "penalty" in detail:
                    penalty_events += 1
        rows.append(
            {
                "referee": referee,
                "yellow_total": yellow_total,
                "red_total": red_total,
                "penalty_events": penalty_events,
            }
        )

    if not rows:
        return {}

    global_yellow = sum(row["yellow_total"] for row in rows) / max(len(rows), 1)
    global_red = sum(row["red_total"] for row in rows) / max(len(rows), 1)
    global_penalties = sum(row["penalty_events"] for row in rows) / max(len(rows), 1)

    grouped: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["referee"]].append(row)

    profiles: Dict[str, dict] = {}
    for referee, samples in grouped.items():
        yellow_avg = sum(item["yellow_total"] for item in samples) / len(samples)
        red_avg = sum(item["red_total"] for item in samples) / len(samples)
        penalty_avg = sum(item["penalty_events"] for item in samples) / len(samples)
        profiles[referee] = {
            "referee_sample_matches": len(samples),
            "referee_yellow_bias": max(-1.0, min((yellow_avg - global_yellow) / 3.0, 1.0)),
            "referee_red_bias": max(-1.0, min((red_avg - global_red) / 1.5, 1.0)),
            "referee_penalty_bias": max(-1.0, min((penalty_avg - global_penalties) / 1.0, 1.0)),
        }
    return profiles


def annotate_referee_profiles(fixtures: List[dict], previous_by_id: Dict[str, dict]) -> None:
    profiles = build_referee_profiles(previous_by_id)
    for fixture in fixtures:
        referee = str(fixture.get("referee") or "").strip()
        profile = profiles.get(referee)
        if not profile:
            fixture["referee_sample_matches"] = 0
            fixture["referee_yellow_bias"] = 0.0
            fixture["referee_red_bias"] = 0.0
            fixture["referee_penalty_bias"] = 0.0
            continue
        fixture.update(profile)


def parse_iso_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def canonical_country(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    return COUNTRY_MAP.get(raw, raw)


def stage_label_to_key(label: str) -> Optional[str]:
    normalized = label.strip().lower()
    if "group" in normalized:
        return "group"
    if "32" in normalized:
        return "round32"
    if "16" in normalized:
        return "round16"
    if "quarter" in normalized:
        return "quarterfinal"
    if "semi" in normalized:
        return "semifinal"
    if "third" in normalized:
        return "third_place"
    if "final" in normalized:
        return "final"
    return None


def stage_and_match_id_for_index(index: int) -> Tuple[str, Optional[str]]:
    if index >= len(TOURNAMENT_STAGE_ORDER):
        raise SystemExit(f"Se esperaban {len(TOURNAMENT_STAGE_ORDER)} partidos y llegaron mas.")
    return TOURNAMENT_STAGE_ORDER[index]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2.0) ** 2
    return radius * (2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)))


def weather_stress_from_metrics(temp_c: float, humidity: float, precip: float, wind_kmh: float, wet_bulb_c: float) -> float:
    stress = 0.02
    if temp_c >= 30.0:
        stress += 0.08 + 0.015 * (temp_c - 30.0)
    elif temp_c <= 5.0:
        stress += 0.03 + 0.010 * (5.0 - temp_c)
    if humidity >= 70.0 and temp_c >= 24.0:
        stress += 0.04 + 0.002 * (humidity - 70.0)
    if precip >= 50.0:
        stress += 0.02 + 0.0015 * (precip - 50.0)
    if wind_kmh >= 25.0:
        stress += 0.02 + 0.001 * (wind_kmh - 25.0)
    if wet_bulb_c >= 22.0:
        stress += 0.06 + 0.015 * (wet_bulb_c - 22.0)
    return max(0.02, min(stress, 0.45))


def forecast_weather(venue_name: str, kickoff: datetime) -> dict:
    venue = VENUE_DATA.get(venue_name)
    if venue is None:
        return {
            "mode": "fallback",
            "temperature_c": 25.0,
            "humidity": 60.0,
            "precip": 20.0,
            "wind_kmh": 10.0,
            "wet_bulb_c": 18.0,
            "weather_stress": 0.10,
        }

    now = datetime.now(timezone.utc)
    if kickoff > now + timedelta(days=14) or kickoff < now - timedelta(days=2):
        temp_c = venue["temp_c"]
        humidity = venue["humidity"]
        precip = venue["precip"]
        wind_kmh = venue["wind_kmh"]
        wet_bulb_c = venue["wet_bulb_c"]
        return {
            "mode": "baseline",
            "temperature_c": temp_c,
            "humidity": humidity,
            "precip": precip,
            "wind_kmh": wind_kmh,
            "wet_bulb_c": wet_bulb_c,
            "weather_stress": weather_stress_from_metrics(temp_c, humidity, precip, wind_kmh, wet_bulb_c),
        }

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={venue['lat']}&longitude={venue['lon']}"
        "&hourly=temperature_2m,relative_humidity_2m,precipitation_probability,wind_speed_10m,wet_bulb_temperature_2m"
        "&forecast_days=16&timezone=GMT"
    )
    try:
        payload = run_curl_json(url)
        hourly = payload["hourly"]
        target = kickoff.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00")
        time_values = hourly["time"]
        if target not in time_values:
            raise KeyError(target)
        index = time_values.index(target)
        temp_c = float(hourly["temperature_2m"][index])
        humidity = float(hourly["relative_humidity_2m"][index])
        precip = float(hourly["precipitation_probability"][index])
        wind_kmh = float(hourly["wind_speed_10m"][index])
        wet_bulb_c = float(hourly["wet_bulb_temperature_2m"][index])
        return {
            "mode": "forecast",
            "temperature_c": temp_c,
            "humidity": humidity,
            "precip": precip,
            "wind_kmh": wind_kmh,
            "wet_bulb_c": wet_bulb_c,
            "weather_stress": weather_stress_from_metrics(temp_c, humidity, precip, wind_kmh, wet_bulb_c),
        }
    except Exception:
        temp_c = venue["temp_c"]
        humidity = venue["humidity"]
        precip = venue["precip"]
        wind_kmh = venue["wind_kmh"]
        wet_bulb_c = venue["wet_bulb_c"]
        return {
            "mode": "baseline-fallback",
            "temperature_c": temp_c,
            "humidity": humidity,
            "precip": precip,
            "wind_kmh": wind_kmh,
            "wet_bulb_c": wet_bulb_c,
            "weather_stress": weather_stress_from_metrics(temp_c, humidity, precip, wind_kmh, wet_bulb_c),
        }


def resolve_placeholder_name(raw_name: str, qual_probs: Dict[str, float]) -> Tuple[str, Optional[str]]:
    label = raw_name.strip()
    mapping = {
        "Winner Playoff Path A": "UEFA_A",
        "Winner Playoff Path B": "UEFA_B",
        "Winner Playoff Path C": "UEFA_C",
        "Winner Playoff Path D": "UEFA_D",
        "Intercontinental Playoff Path 1": "FIFA_1",
        "Intercontinental Playoff Path 2": "FIFA_2",
        "Winner Playoff Tournament 1": "FIFA_1",
        "Winner Playoff Tournament 2": "FIFA_2",
        "Playoff Tournament Winner 1": "FIFA_1",
        "Playoff Tournament Winner 2": "FIFA_2",
    }
    placeholder = mapping.get(label)
    if placeholder is None:
        return raw_name, None
    candidates = PLACEHOLDER_PATHS[placeholder]
    best_team = max(candidates, key=lambda team_name: qual_probs.get(team_name, 0.0))
    return best_team, placeholder


def canonical_team_name(raw_name: str, teams: Dict[str, object], qual_probs: Dict[str, float]) -> Tuple[str, Optional[str]]:
    try:
        return resolve_team_name(raw_name, teams), None
    except SystemExit:
        return resolve_placeholder_name(raw_name, qual_probs)


def is_unresolved_placeholder(team_name: str, teams: Dict[str, object]) -> bool:
    if team_name in teams:
        return False
    normalized = team_name.lower()
    if normalized.startswith("group "):
        return True
    if normalized.startswith("round of 32 "):
        return True
    if normalized.startswith("round of 16 "):
        return True
    if normalized.startswith("quarterfinal "):
        return True
    if normalized.startswith("semifinal "):
        return True
    if normalized.startswith("third place group "):
        return True
    if normalized.endswith(" winner") or normalized.endswith(" loser"):
        return True
    return False


def estimate_cards(team, stage: str, weather_stress: float) -> Tuple[int, int]:
    profile = profile_for(team)
    knockout_boost = 0.45 if stage != "group" else 0.0
    yellow_raw = 1.1 + 1.8 * (1.0 - profile.squad.discipline_index) + knockout_boost + 1.3 * weather_stress
    yellow_est = max(0, min(int(round(yellow_raw)), 6))
    red_score = 0.01 + 0.08 * profile.squad.red_rate + 0.04 * weather_stress + (0.015 if stage != "group" else 0.0)
    red_est = 1 if red_score >= 0.08 else 0
    return yellow_est, red_est


def infer_groups(fixtures: List[dict]) -> Dict[frozenset, str]:
    graph: Dict[str, set] = defaultdict(set)
    first_seen: Dict[str, datetime] = {}
    for fixture in fixtures:
        if fixture["stage"] != "group":
            continue
        team_a = fixture["team_a"]
        team_b = fixture["team_b"]
        graph[team_a].add(team_b)
        graph[team_b].add(team_a)
        kickoff = parse_iso_utc(fixture["kickoff_utc"])
        first_seen[team_a] = min(first_seen.get(team_a, kickoff), kickoff)
        first_seen[team_b] = min(first_seen.get(team_b, kickoff), kickoff)

    components: List[Tuple[datetime, frozenset]] = []
    seen = set()
    for team_name in graph:
        if team_name in seen:
            continue
        queue = deque([team_name])
        component = set()
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            component.add(current)
            for neighbor in graph[current]:
                if neighbor not in seen:
                    queue.append(neighbor)
        earliest = min(first_seen[name] for name in component)
        components.append((earliest, frozenset(component)))

    components.sort(key=lambda item: item[0])
    letters = [chr(ord("A") + idx) for idx in range(len(components))]
    return {component: letters[index] for index, (_, component) in enumerate(components)}


def assign_group_letters(fixtures: List[dict]) -> None:
    component_to_group = infer_groups(fixtures)
    by_team_component = {}
    for component, group in component_to_group.items():
        for team_name in component:
            by_team_component[team_name] = group
    for fixture in fixtures:
        if fixture["stage"] == "group":
            fixture["group"] = by_team_component.get(fixture["team_a"])


def attach_rest_and_travel(fixtures: List[dict], teams: Dict[str, object]) -> None:
    previous: Dict[str, Tuple[datetime, dict]] = {}
    for fixture in fixtures:
        kickoff = parse_iso_utc(fixture["kickoff_utc"])
        venue = VENUE_DATA.get(fixture["venue_name"])
        if fixture.get("projection_only"):
            default_rest = 4 if fixture["stage"] == "group" else 5
            fixture["rest_days_a"] = default_rest
            fixture["rest_days_b"] = default_rest
            fixture["travel_km_a"] = 0.0
            fixture["travel_km_b"] = 0.0
            continue
        for side in ("a", "b"):
            team_name = fixture[f"team_{side}"]
            team = teams.get(team_name)
            prev = previous.get(team_name)
            if prev is None:
                rest_days = 5
                if team and getattr(team, "is_host", False) and fixture["venue_country"] == getattr(team, "host_country", None):
                    travel_km = 0.0
                else:
                    confed = getattr(team, "confederation", "UEFA") if team else "UEFA"
                    travel_km = CONFED_TRAVEL_BASELINE_KM.get(confed, 5000.0)
            else:
                prev_kickoff, prev_venue = prev
                rest_days = max(2, int((kickoff - prev_kickoff).total_seconds() // 86400))
                if venue and prev_venue:
                    travel_km = haversine_km(prev_venue["lat"], prev_venue["lon"], venue["lat"], venue["lon"])
                else:
                    travel_km = 1500.0
            fixture[f"rest_days_{side}"] = rest_days
            fixture[f"travel_km_{side}"] = round(travel_km, 1)
            if venue:
                previous[team_name] = (kickoff, venue)


def build_fixture_from_event(
    event: dict,
    teams: Dict[str, object],
    qual_probs: Dict[str, float],
    stage: str,
    match_id: Optional[str],
    provider_live_index: Dict[Tuple[str, str], dict],
) -> Optional[dict]:
    competition = event.get("competitions", [{}])[0]
    competitors = competition.get("competitors", [])
    if len(competitors) != 2:
        return None

    home = next((item for item in competitors if item.get("homeAway") == "home"), competitors[0])
    away = next((item for item in competitors if item.get("homeAway") == "away"), competitors[-1])

    raw_team_a = home.get("team", {}).get("displayName", "")
    raw_team_b = away.get("team", {}).get("displayName", "")
    team_a, placeholder_a = canonical_team_name(raw_team_a, teams, qual_probs)
    team_b, placeholder_b = canonical_team_name(raw_team_b, teams, qual_probs)

    kickoff = parse_iso_utc(event["date"])
    venue = competition.get("venue", {}) or {}
    venue_name = venue.get("fullName", "Unknown venue")
    venue_country = canonical_country((venue.get("address") or {}).get("country")) or VENUE_DATA.get(venue_name, {}).get("country", "United States")
    weather = forecast_weather(venue_name, kickoff)
    unresolved = is_unresolved_placeholder(team_a, teams) or is_unresolved_placeholder(team_b, teams)
    enrichment = summary_enrichment(
        str(event["id"]),
        kickoff,
        event.get("status", {}).get("type", {}).get("state"),
        team_a,
        team_b,
    )
    provider_enrichment = provider_live_index.get(match_lookup_key(team_a, team_b), {})

    fixture = {
        "id": f"espn-{event['id']}",
        "label": f"{team_a} vs {team_b}" if not match_id else f"{BRACKET_MATCH_TITLES.get(match_id, team_a + ' vs ' + team_b)}",
        "team_a": team_a,
        "team_b": team_b,
        "stage": stage,
        "match_id": match_id,
        "group": None,
        "neutral": True,
        "venue_name": venue_name,
        "venue_city": (venue.get("address") or {}).get("city"),
        "venue_country": venue_country,
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
        "status_state": event.get("status", {}).get("type", {}).get("state"),
        "status_detail": event.get("status", {}).get("type", {}).get("detail"),
        "altitude_m": int(VENUE_DATA.get(venue_name, {}).get("altitude_m", 0)),
        "weather_stress": round(float(weather["weather_stress"]), 4),
        "weather_mode": weather["mode"],
        "weather_temperature_c": round(float(weather["temperature_c"]), 1),
        "weather_humidity_pct": round(float(weather["humidity"]), 1),
        "weather_precipitation_pct": round(float(weather["precip"]), 1),
        "weather_wind_kmh": round(float(weather["wind_kmh"]), 1),
        "weather_wet_bulb_c": round(float(weather["wet_bulb_c"]), 1),
        "source": "espn_scoreboard",
        "source_event_name": event.get("name"),
        "raw_team_a": raw_team_a if placeholder_a else None,
        "raw_team_b": raw_team_b if placeholder_b else None,
        "placeholder_a": placeholder_a,
        "placeholder_b": placeholder_b,
        "lineup_confirmed_a": False,
        "lineup_confirmed_b": False,
        "lineup_change_count_a": 0,
        "lineup_change_count_b": 0,
    }
    fixture.update(enrichment)
    if provider_enrichment:
        fixture.update(provider_enrichment)
        fixture["source"] = f"espn_scoreboard+{provider_enrichment.get('live_feed_provider', 'deep_live')}"
    if unresolved:
        fixture["projection_only"] = True
        fixture["slot_team_a"] = raw_team_a
        fixture["slot_team_b"] = raw_team_b

    status = event.get("status", {}).get("type", {})
    state = status.get("state")
    completed = bool(status.get("completed")) or state == "post"
    live = state == "in"
    score_a = int(float(home.get("score", 0) or 0))
    score_b = int(float(away.get("score", 0) or 0))

    if live:
        fixture["live_score_a"] = score_a
        fixture["live_score_b"] = score_b

    if completed and not unresolved:
        shootout_a = home.get("shootoutScore")
        shootout_b = away.get("shootoutScore")
        shootout_present = shootout_a is not None and shootout_b is not None
        went_extra_time = False
        if shootout_present:
            went_extra_time = True
            fixture["went_penalties"] = True
            fixture["actual_penalties_a"] = int(shootout_a)
            fixture["actual_penalties_b"] = int(shootout_b)
            if int(shootout_a) > int(shootout_b):
                fixture["penalties_winner"] = team_a
            elif int(shootout_b) > int(shootout_a):
                fixture["penalties_winner"] = team_b
        else:
            raw_blob = json.dumps(event).lower()
            if "after extra time" in raw_blob or "aet" in raw_blob:
                went_extra_time = True

        team_obj_a = teams.get(team_a)
        team_obj_b = teams.get(team_b)
        yellows_a, reds_a = estimate_cards(team_obj_a, stage, fixture["weather_stress"]) if team_obj_a else (1, 0)
        yellows_b, reds_b = estimate_cards(team_obj_b, stage, fixture["weather_stress"]) if team_obj_b else (1, 0)
        if fixture.get("live_yellow_cards_a") is not None:
            yellows_a = int(round(float(fixture.get("live_yellow_cards_a", yellows_a))))
        if fixture.get("live_yellow_cards_b") is not None:
            yellows_b = int(round(float(fixture.get("live_yellow_cards_b", yellows_b))))
        if fixture.get("live_red_cards_a") is not None:
            reds_a = int(round(float(fixture.get("live_red_cards_a", reds_a))))
        if fixture.get("live_red_cards_b") is not None:
            reds_b = int(round(float(fixture.get("live_red_cards_b", reds_b))))

        fixture.update(
            {
                "actual_score_a": score_a,
                "actual_score_b": score_b,
                "actual_yellows_a": yellows_a,
                "actual_yellows_b": yellows_b,
                "actual_reds_a": reds_a,
                "actual_reds_b": reds_b,
                "went_extra_time": went_extra_time,
                "update_state": True,
            }
        )

    return fixture


def build_live_fixtures(scoreboard_payload: dict) -> List[dict]:
    teams = load_teams()
    qual_probs = qualification_probabilities(teams)
    previous_by_id = load_previous_fixtures()
    provider_live_index = fetch_provider_live_index(teams)
    fixtures = []
    sorted_events = sorted(scoreboard_payload.get("events", []), key=lambda item: item.get("date", ""))
    for index, event in enumerate(sorted_events):
        stage, match_id = stage_and_match_id_for_index(index)
        fixture = build_fixture_from_event(event, teams, qual_probs, stage, match_id, provider_live_index)
        if fixture is not None:
            fixtures.append(fixture)

    assign_group_letters(fixtures)
    attach_rest_and_travel(fixtures, teams)
    preserve_previous_enrichment(fixtures, previous_by_id)
    annotate_open_news(fixtures)
    annotate_lineup_changes(fixtures, previous_by_id)
    annotate_market_moves(fixtures, previous_by_id)
    annotate_referee_profiles(fixtures, previous_by_id)
    return fixtures


def fixture_is_live_status(fixture: dict) -> bool:
    status = str(fixture.get("status_state") or fixture.get("provider_match_status") or "").strip().lower()
    return status in {"in", "live", "in_progress", "in_play", "paused"} or fixture.get("live_elapsed_minutes") is not None


def fixture_is_final_status(fixture: dict) -> bool:
    status = str(fixture.get("status_state") or fixture.get("provider_match_status") or "").strip().lower()
    return status in {"post", "final", "full_time", "finished", "complete", "completed", "finished", "awarded"}


def fixture_should_be_live_by_clock(fixture: dict, now: datetime) -> bool:
    kickoff_text = fixture.get("kickoff_utc")
    if not kickoff_text or fixture_is_final_status(fixture):
        return False
    try:
        kickoff = parse_iso_utc(str(kickoff_text))
    except Exception:
        return False
    return kickoff <= now <= kickoff + timedelta(minutes=150)


def live_provider_names_from_fixtures(fixtures: Sequence[dict]) -> List[str]:
    providers = []
    for fixture in fixtures:
        provider_blob = str(fixture.get("live_feed_provider") or "").strip()
        if not provider_blob:
            continue
        providers.extend(part.strip() for part in provider_blob.split("+") if part.strip())
    return sorted(dict.fromkeys(providers))


def live_source_names_from_fixtures(fixtures: Sequence[dict]) -> List[str]:
    sources = []
    for fixture in fixtures:
        source_blob = str(fixture.get("source") or "").strip()
        if not source_blob:
            continue
        sources.extend(part.strip() for part in source_blob.split("+") if part.strip())
    return sorted(dict.fromkeys(sources))


def write_live_sync_status(fixtures: Sequence[dict], *, scoreboard_available: bool, used_fallback: bool, fallback_reason: str = "") -> dict:
    now = datetime.now(timezone.utc)
    live_count = sum(1 for fixture in fixtures if fixture_is_live_status(fixture))
    final_count = sum(1 for fixture in fixtures if fixture_is_final_status(fixture))
    should_be_live = [
        {
            "id": fixture.get("id"),
            "label": fixture.get("label"),
            "kickoff_utc": fixture.get("kickoff_utc"),
            "status_state": fixture.get("status_state"),
            "live_score_a": fixture.get("live_score_a"),
            "live_score_b": fixture.get("live_score_b"),
            "live_elapsed_minutes": fixture.get("live_elapsed_minutes"),
        }
        for fixture in fixtures
        if fixture_should_be_live_by_clock(fixture, now)
    ]
    missing_live_payload = [
        item
        for item in should_be_live
        if item.get("live_score_a") is None and item.get("live_score_b") is None and item.get("live_elapsed_minutes") is None
    ]
    providers_used = live_provider_names_from_fixtures(fixtures)
    sources_used = live_source_names_from_fixtures(fixtures) or ["espn_scoreboard"]
    primary_configured = api_football_enabled()
    primary_used = PRIMARY_DEEP_LIVE_PROVIDER["provider_id"] in providers_used
    status = {
        "updated_at_utc": iso_now(),
        "scoreboard_available": bool(scoreboard_available),
        "used_fallback": bool(used_fallback),
        "fallback_reason": fallback_reason[:500],
        "configured_providers": configured_provider_names(),
        "sources_used": sources_used,
        "providers_used": providers_used,
        "deep_live_provider_used": bool(providers_used),
        "selected_deep_live_provider": PRIMARY_DEEP_LIVE_PROVIDER,
        "automatic_live_update": {
            "enabled": True,
            "interval_minutes": 5,
            "workflow": "quiniela-pages.yml",
            "primary_provider_configured": bool(primary_configured),
            "primary_provider_used": bool(primary_used),
            "mode": (
                "live_profundo_automatico"
                if primary_used
                else "proveedor_profundo_configurado_sin_match"
                if primary_configured
                else "fallback_publico_automatico"
            ),
            "explanation": (
                "API-Football se usa solo cuando la key existe y devuelve el partido vivo. "
                "Sin eso, el sistema igual se actualiza solo cada 5 minutos con fuentes publicas/base."
            ),
        },
        "fixtures_total": len(fixtures),
        "live_count": live_count,
        "final_count": final_count,
        "should_be_live_by_clock_count": len(should_be_live),
        "missing_live_payload_count": len(missing_live_payload),
        "stale_live_warning": bool(missing_live_payload and (used_fallback or not scoreboard_available or live_count == 0)),
        "stale_live_fixtures": missing_live_payload[:6],
        "action_if_warning": (
            "No cargar como in-play profundo: revisar GitHub Actions, ESPN/API base o activar proveedor profundo. "
            "Si ya hay marcador/estado live, el modelo queda en in-play base limitado; si falta marcador/minuto, usa fallback hasta recibir datos reales."
        ),
    }
    LIVE_SYNC_STATUS_FILE.write_text(json.dumps(status, indent=2, ensure_ascii=True))
    return status


def main() -> None:
    used_fallback = False
    scoreboard_available = False
    fallback_reason = ""
    try:
        payload = run_curl_json(SCOREBOARD_URL)
        scoreboard_available = True
        fixtures = build_live_fixtures(payload)
        OUTPUT_FILE.write_text(json.dumps(fixtures, indent=2, ensure_ascii=True))
    except Exception as exc:
        if not OUTPUT_FILE.exists():
            raise
        used_fallback = True
        fallback_reason = str(exc)
        fixtures = json.loads(OUTPUT_FILE.read_text())
        print(f"Advertencia: ESPN scoreboard no disponible ({exc}); se reutiliza {OUTPUT_FILE}")

    sync_status = write_live_sync_status(
        fixtures,
        scoreboard_available=scoreboard_available,
        used_fallback=used_fallback,
        fallback_reason=fallback_reason,
    )
    print(f"Fixtures vivos guardados en {OUTPUT_FILE}")
    print(f"Estado live guardado en {LIVE_SYNC_STATUS_FILE}")
    print(f"Partidos sincronizados: {len(fixtures)}")
    print(f"Fallback por feed base: {'si' if used_fallback else 'no'}")
    print(f"Proveedores configurados: {', '.join(sync_status['configured_providers']) or 'ninguno'}")
    print(f"Proveedores usados en fixtures: {', '.join(sync_status['providers_used']) or 'ninguno'}")
    print(f"Alerta stale live: {'si' if sync_status['stale_live_warning'] else 'no'}")
    print(f"Actualizado: {iso_now()}")


if __name__ == "__main__":
    main()
