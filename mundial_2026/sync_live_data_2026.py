#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import subprocess
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from modelo_quiniela_2026 import BRACKET_MATCH_TITLES, load_teams, profile_for, qualification_probabilities, resolve_team_name


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = SCRIPT_DIR / "fixtures_live_2026.json"
SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
    "?dates=20260611-20260719&limit=200"
)
SUMMARY_URL_TEMPLATE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={event_id}"
SUMMARY_FETCH_WINDOW_DAYS = 10

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
    "UEFA_A": ["Italy", "Northern Ireland", "Wales", "Bosnia and Herzegovina"],
    "UEFA_B": ["Ukraine", "Sweden", "Poland", "Albania"],
    "UEFA_C": ["Turkey", "Romania", "Slovakia", "Kosovo"],
    "UEFA_D": ["Denmark", "North Macedonia", "Czech Republic", "Republic of Ireland"],
    "FIFA_1": ["Dem. Rep. of Congo", "Jamaica", "New Caledonia"],
    "FIFA_2": ["Iraq", "Bolivia", "Suriname"],
}

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


def run_curl_json(url: str) -> dict:
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "30", url],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def should_fetch_summary(kickoff: datetime, status_state: Optional[str]) -> bool:
    now = datetime.now(timezone.utc)
    if status_state in {"in", "post"}:
        return True
    return abs((kickoff - now).total_seconds()) <= SUMMARY_FETCH_WINDOW_DAYS * 86400


def american_to_implied_prob(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    odds = float(value)
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
        for obj in walk_objects(roster):
            name = obj.get("displayName") or obj.get("shortName") or obj.get("name")
            if not name:
                continue
            starter_flag = obj.get("starter")
            reserve_flag = obj.get("reserve")
            if starter_flag is True:
                lineup_confirmed = True
                starters.append(str(name))
            elif obj.get("formation"):
                lineup_confirmed = True
            elif reserve_flag is False and obj.get("position"):
                starters.append(str(name))
        unique_starters = []
        seen = set()
        for player_name in starters:
            if player_name in seen:
                continue
            seen.add(player_name)
            unique_starters.append(player_name)
        lineup_data[side] = {
            "confirmed": lineup_confirmed or len(unique_starters) >= 11,
            "starters": unique_starters[:11],
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
            else:
                soft_absences.append(label)

        load = min(0.85, 0.18 * len(hard_absences) + 0.08 * len(soft_absences))
        absences[side] = {
            "hard_count": len(hard_absences),
            "soft_count": len(soft_absences),
            "load": round(load, 3),
            "notes": (hard_absences + soft_absences)[:6],
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


def summarize_market(odds_entry: dict) -> dict:
    home_line = odds_entry.get("homeTeamOdds", {}).get("moneyLine")
    away_line = odds_entry.get("awayTeamOdds", {}).get("moneyLine")
    draw_line = odds_entry.get("drawOdds")
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

    absences = extract_absence_data(payload)
    for side, prefix in (("home", "a"), ("away", "b")):
        absence_data = absences.get(side)
        if not absence_data:
            continue
        enrichment[f"injuries_{prefix}"] = absence_data["load"]
        enrichment[f"unavailable_count_{prefix}"] = int(absence_data["hard_count"])
        enrichment[f"questionable_count_{prefix}"] = int(absence_data["soft_count"])
        enrichment[f"unavailable_notes_{prefix}"] = absence_data["notes"]

    news = extract_news_enrichment(payload, team_a, team_b)
    enrichment.update(news)
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
                continue
            current_set = set(current)
            previous_set = set(previous_lineup)
            fixture[f"lineup_change_count_{side}"] = len(current_set.symmetric_difference(previous_set)) // 2


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
    fixtures = []
    sorted_events = sorted(scoreboard_payload.get("events", []), key=lambda item: item.get("date", ""))
    for index, event in enumerate(sorted_events):
        stage, match_id = stage_and_match_id_for_index(index)
        fixture = build_fixture_from_event(event, teams, qual_probs, stage, match_id)
        if fixture is not None:
            fixtures.append(fixture)

    assign_group_letters(fixtures)
    attach_rest_and_travel(fixtures, teams)
    annotate_lineup_changes(fixtures, previous_by_id)
    return fixtures


def main() -> None:
    payload = run_curl_json(SCOREBOARD_URL)
    fixtures = build_live_fixtures(payload)
    OUTPUT_FILE.write_text(json.dumps(fixtures, indent=2, ensure_ascii=True))
    print(f"Fixtures vivos guardados en {OUTPUT_FILE}")
    print(f"Partidos sincronizados: {len(fixtures)}")
    print(f"Actualizado: {iso_now()}")


if __name__ == "__main__":
    main()
