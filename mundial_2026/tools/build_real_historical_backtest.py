#!/usr/bin/env python3
from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
RAW_RESULTS = ROOT / "data" / "international_results_raw.csv"
OUTPUT_MATCHES = ROOT / "data" / "historical_matches.csv"
OUTPUT_COVERAGE = ROOT / "data" / "real_data_coverage_report.csv"
SOURCE_URL = "https://github.com/martj42/international_results"
SOURCE_RAW_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
SELECTED_TOURNAMENTS = {"FIFA World Cup", "UEFA Euro", "Copa América"}
START_YEAR = 1950


def parse_int(value: object) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def expected_score(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-(elo_a - elo_b) / 400.0))


def match_result_points(goals_a: int, goals_b: int) -> float:
    if goals_a > goals_b:
        return 1.0
    if goals_b > goals_a:
        return 0.0
    return 0.5


def elo_k_factor(tournament: str) -> float:
    if tournament in SELECTED_TOURNAMENTS:
        return 42.0
    if "qualif" in tournament.lower():
        return 30.0
    if "friendly" in tournament.lower():
        return 12.0
    return 22.0


def elo_margin_multiplier(goals_a: int, goals_b: int, elo_diff: float) -> float:
    margin = abs(goals_a - goals_b)
    if margin <= 1:
        return 1.0
    return math.log(margin + 1.0) * (2.2 / (2.2 + 0.001 * abs(elo_diff)))


def update_elo(
    ratings: MutableMapping[str, float],
    team_a: str,
    team_b: str,
    goals_a: int,
    goals_b: int,
    tournament: str,
) -> None:
    elo_a = ratings[team_a]
    elo_b = ratings[team_b]
    actual_a = match_result_points(goals_a, goals_b)
    expected_a = expected_score(elo_a, elo_b)
    k = elo_k_factor(tournament)
    margin_mult = elo_margin_multiplier(goals_a, goals_b, elo_a - elo_b)
    delta = k * margin_mult * (actual_a - expected_a)
    ratings[team_a] = elo_a + delta
    ratings[team_b] = elo_b - delta


def update_history(
    history: MutableMapping[str, Dict[str, float]],
    team_a: str,
    team_b: str,
    goals_a: int,
    goals_b: int,
) -> None:
    points_a = 3.0 if goals_a > goals_b else (1.0 if goals_a == goals_b else 0.0)
    points_b = 3.0 if goals_b > goals_a else (1.0 if goals_a == goals_b else 0.0)
    for team, points, goals_for, goals_against in (
        (team_a, points_a, goals_a, goals_b),
        (team_b, points_b, goals_b, goals_a),
    ):
        bucket = history[team]
        bucket["matches"] += 1.0
        bucket["points"] += points
        bucket["goals_for"] += goals_for
        bucket["goals_against"] += goals_against


def historical_strength(history: Mapping[str, Mapping[str, float]], team: str) -> str:
    bucket = history.get(team)
    if not bucket or bucket.get("matches", 0.0) <= 0:
        return ""
    matches = float(bucket["matches"])
    points_per_match = float(bucket["points"]) / matches
    goal_diff_per_match = (float(bucket["goals_for"]) - float(bucket["goals_against"])) / matches
    # Normalized to roughly 0-1, using only matches already played before this row.
    value = max(0.0, min(1.0, (points_per_match / 3.0) * 0.82 + ((goal_diff_per_match + 2.0) / 4.0) * 0.18))
    return f"{value:.6f}"


def read_raw_results(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return sorted(csv.DictReader(handle), key=lambda row: row.get("date", ""))


def build_historical_rows(raw_rows: Iterable[Mapping[str, str]]) -> Tuple[List[Dict[str, object]], Counter]:
    ratings: defaultdict[str, float] = defaultdict(lambda: 1500.0)
    history: defaultdict[str, Dict[str, float]] = defaultdict(
        lambda: {"matches": 0.0, "points": 0.0, "goals_for": 0.0, "goals_against": 0.0}
    )
    selected_rows: List[Dict[str, object]] = []
    competition_counts: Counter = Counter()
    match_counter = 0
    for raw in raw_rows:
        team_a = str(raw.get("home_team", "")).strip()
        team_b = str(raw.get("away_team", "")).strip()
        tournament = str(raw.get("tournament", "")).strip()
        if not team_a or not team_b:
            continue
        goals_a = parse_int(raw.get("home_score"))
        goals_b = parse_int(raw.get("away_score"))
        if goals_a is None or goals_b is None:
            continue
        date_text = str(raw.get("date", "")).strip()
        if not date_text:
            continue
        date = parse_date(date_text)
        is_selected = tournament in SELECTED_TOURNAMENTS and date.year >= START_YEAR
        if is_selected:
            match_counter += 1
            competition_counts[tournament] += 1
            neutral = str(raw.get("neutral", "")).strip().lower()
            selected_rows.append(
                {
                    "match_id": f"{date.strftime('%Y%m%d')}_{team_a}_vs_{team_b}".replace(" ", "_"),
                    "date": date.strftime("%Y-%m-%d"),
                    "competition": tournament,
                    "phase": "unknown_stage_from_source",
                    "team_a": team_a,
                    "team_b": team_b,
                    "goals_a": goals_a,
                    "goals_b": goals_b,
                    "neutral": "1" if neutral in {"true", "1", "yes"} else "0",
                    "knockout": "",
                    "elo_a_pre": f"{ratings[team_a]:.3f}",
                    "elo_b_pre": f"{ratings[team_b]:.3f}",
                    "fifa_rank_a_pre": "",
                    "fifa_rank_b_pre": "",
                    "market_prob_a_pre": "",
                    "market_prob_draw_pre": "",
                    "market_prob_b_pre": "",
                    "squad_quality_a_pre": "",
                    "squad_quality_b_pre": "",
                    "historical_strength_a_pre": historical_strength(history, team_a),
                    "historical_strength_b_pre": historical_strength(history, team_b),
                    "city": raw.get("city", ""),
                    "venue_country": raw.get("country", ""),
                    "source_dataset": "martj42/international_results",
                    "source_url": SOURCE_URL,
                    "data_quality_note": (
                        "Resultados oficiales publicos; Elo e historial usan solo partidos previos. "
                        "Ranking FIFA, mercado, plantilla y fase exacta quedan vacios si no hay fuente real conectada."
                    ),
                }
            )
        update_elo(ratings, team_a, team_b, goals_a, goals_b, tournament)
        if tournament in SELECTED_TOURNAMENTS:
            update_history(history, team_a, team_b, goals_a, goals_b)
    return selected_rows, competition_counts


def write_csv(path: Path, rows: List[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def coverage_rows(raw_count: int, selected_count: int, counts: Counter) -> List[Dict[str, object]]:
    now = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, object]] = [
        {"metric": "generated_at_utc", "value": now, "note": "Reporte de cobertura de datos reales."},
        {"metric": "source_url", "value": SOURCE_URL, "note": "Dataset publico usado para resultados historicos."},
        {"metric": "source_raw_url", "value": SOURCE_RAW_URL, "note": "CSV descargado a data/international_results_raw.csv."},
        {"metric": "source_rows", "value": raw_count, "note": "Total de partidos en el dataset fuente."},
        {
            "metric": "selected_rows",
            "value": selected_count,
            "note": "Mundiales, Euro y Copa America desde 1950 incluidos en historical_matches.csv.",
        },
        {
            "metric": "real_pre_match_fields_available",
            "value": "date,teams,score,neutral,city,country,elo_pre,historical_strength_pre",
            "note": "Elo/historial son features calculadas solo con resultados previos; no usan futuro.",
        },
        {
            "metric": "real_pre_match_fields_missing",
            "value": "fifa_rank_pre,market_prob_pre,squad_quality_pre,exact_stage_or_knockout",
            "note": "Se dejan vacios para no usar proxies ni datos inventados.",
        },
    ]
    for competition, count in sorted(counts.items()):
        rows.append({"metric": f"competition_rows:{competition}", "value": count, "note": "Filas incluidas para backtesting real."})
    return rows


def main() -> int:
    raw_rows = read_raw_results(RAW_RESULTS)
    selected_rows, counts = build_historical_rows(raw_rows)
    write_csv(OUTPUT_MATCHES, selected_rows)
    write_csv(OUTPUT_COVERAGE, coverage_rows(len(raw_rows), len(selected_rows), counts))
    print(f"Wrote {OUTPUT_MATCHES} ({len(selected_rows)} rows)")
    print(f"Wrote {OUTPUT_COVERAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
