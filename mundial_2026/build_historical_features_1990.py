#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_TEAMS_FILE = ROOT / "teams_2026.json"
DEFAULT_OUTPUT_FILE = ROOT / "historical_features_1990.json"
DEFAULT_START_DATE = "1990-01-01"
TODAY = date(2026, 4, 3)
TEAM_DATASET_ALIASES = {
    "Curacao": "Curaçao",
    "Dem. Rep. of Congo": "DR Congo",
}
COMPETITIVE_TOURNAMENT_EXCLUDE = {"Friendly", "Unofficial Friendly"}
DATASET_SOURCE_RESULTS = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
DATASET_SOURCE_SHOOTOUTS = "https://raw.githubusercontent.com/martj42/international_results/master/shootouts.csv"
DATASET_SOURCE_FORMER_NAMES = "https://raw.githubusercontent.com/martj42/international_results/master/former_names.csv"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_map(raw_by_team: dict[str, float]) -> dict[str, float]:
    values = list(raw_by_team.values())
    if not values:
        return {}
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        return {team: 0.5 for team in raw_by_team}
    return {team: clamp((value - low) / (high - low), 0.0, 1.0) for team, value in raw_by_team.items()}


def metric_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator <= 0.0:
        return default
    return numerator / denominator


def recency_weight(match_date: date) -> float:
    years_old = max(0.0, (TODAY - match_date).days / 365.25)
    return 0.5 ** (years_old / 8.0)


def load_teams(path: Path) -> list[dict]:
    return json.loads(path.read_text())["teams"]


def build_team_name_map(teams: list[dict], former_names_path: Path, start_date: str) -> dict[str, list[str]]:
    team_names: dict[str, list[str]] = {}
    former_rows: list[dict] = []
    with former_names_path.open(newline="") as handle:
        former_rows.extend(csv.DictReader(handle))

    for team in teams:
        local_name = team["name"]
        dataset_name = TEAM_DATASET_ALIASES.get(local_name, local_name)
        aliases = [dataset_name]
        for row in former_rows:
            if row["current"] != dataset_name:
                continue
            if row["end_date"] < start_date:
                continue
            aliases.append(row["former"])
        team_names[local_name] = sorted(set(aliases))
    return team_names


def team_stat_bucket() -> dict[str, float]:
    return {
        "matches": 0.0,
        "points": 0.0,
        "wins": 0.0,
        "draws": 0.0,
        "losses": 0.0,
        "gf": 0.0,
        "ga": 0.0,
        "scored_matches": 0.0,
        "clean_sheet_matches": 0.0,
        "weighted_matches": 0.0,
        "weighted_points": 0.0,
        "weighted_gf": 0.0,
        "weighted_ga": 0.0,
        "competitive_matches": 0.0,
        "competitive_points": 0.0,
        "competitive_gf": 0.0,
        "competitive_ga": 0.0,
        "competitive_clean_sheet_matches": 0.0,
        "competitive_scored_matches": 0.0,
        "world_cup_matches": 0.0,
        "world_cup_points": 0.0,
        "world_cup_gf": 0.0,
        "world_cup_ga": 0.0,
        "world_cup_scored_matches": 0.0,
        "world_cup_clean_sheet_matches": 0.0,
    }


def update_bucket(bucket: dict[str, float], goals_for: int, goals_against: int, tournament: str, weight: float) -> None:
    bucket["matches"] += 1.0
    bucket["gf"] += goals_for
    bucket["ga"] += goals_against
    bucket["weighted_matches"] += weight
    bucket["weighted_gf"] += weight * goals_for
    bucket["weighted_ga"] += weight * goals_against
    if goals_for > 0:
        bucket["scored_matches"] += 1.0
    if goals_against == 0:
        bucket["clean_sheet_matches"] += 1.0

    if goals_for > goals_against:
        points = 3.0
        bucket["wins"] += 1.0
    elif goals_for == goals_against:
        points = 1.0
        bucket["draws"] += 1.0
    else:
        points = 0.0
        bucket["losses"] += 1.0
    bucket["points"] += points
    bucket["weighted_points"] += weight * points

    competitive = tournament not in COMPETITIVE_TOURNAMENT_EXCLUDE
    if competitive:
        bucket["competitive_matches"] += 1.0
        bucket["competitive_points"] += points
        bucket["competitive_gf"] += goals_for
        bucket["competitive_ga"] += goals_against
        if goals_for > 0:
            bucket["competitive_scored_matches"] += 1.0
        if goals_against == 0:
            bucket["competitive_clean_sheet_matches"] += 1.0

    if tournament == "FIFA World Cup":
        bucket["world_cup_matches"] += 1.0
        bucket["world_cup_points"] += points
        bucket["world_cup_gf"] += goals_for
        bucket["world_cup_ga"] += goals_against
        if goals_for > 0:
            bucket["world_cup_scored_matches"] += 1.0
        if goals_against == 0:
            bucket["world_cup_clean_sheet_matches"] += 1.0


def build_output_record(team: str, aliases: list[str], bucket: dict[str, float], shootouts: dict[str, float]) -> dict[str, object]:
    matches = bucket["matches"]
    weighted_matches = bucket["weighted_matches"]
    competitive_matches = bucket["competitive_matches"]
    world_cup_matches = bucket["world_cup_matches"]
    shootout_matches = shootouts["matches"]

    points_per_match = metric_div(bucket["points"], matches)
    weighted_points_per_match = metric_div(bucket["weighted_points"], weighted_matches, points_per_match)
    goals_for_per_match = metric_div(bucket["gf"], matches)
    goals_against_per_match = metric_div(bucket["ga"], matches)
    goal_diff_per_match = metric_div(bucket["gf"] - bucket["ga"], matches)
    weighted_goals_for_per_match = metric_div(bucket["weighted_gf"], weighted_matches, goals_for_per_match)
    weighted_goals_against_per_match = metric_div(bucket["weighted_ga"], weighted_matches, goals_against_per_match)
    weighted_goal_diff_per_match = weighted_goals_for_per_match - weighted_goals_against_per_match
    scoring_rate = metric_div(bucket["scored_matches"], matches)
    clean_sheet_rate = metric_div(bucket["clean_sheet_matches"], matches)

    competitive_points_per_match = metric_div(bucket["competitive_points"], competitive_matches, 1.15)
    competitive_goal_diff_per_match = metric_div(
        bucket["competitive_gf"] - bucket["competitive_ga"], competitive_matches, 0.0
    )
    competitive_scoring_rate = metric_div(bucket["competitive_scored_matches"], competitive_matches, scoring_rate)
    competitive_clean_sheet_rate = metric_div(
        bucket["competitive_clean_sheet_matches"], competitive_matches, clean_sheet_rate
    )

    world_cup_points_per_match = metric_div(bucket["world_cup_points"], world_cup_matches, 0.0)
    world_cup_goal_diff_per_match = metric_div(
        bucket["world_cup_gf"] - bucket["world_cup_ga"], world_cup_matches, 0.0
    )
    world_cup_scoring_rate = metric_div(bucket["world_cup_scored_matches"], world_cup_matches, 0.0)
    world_cup_clean_sheet_rate = metric_div(bucket["world_cup_clean_sheet_matches"], world_cup_matches, 0.0)

    world_cup_ppm_shrunk = metric_div(bucket["world_cup_points"] + 5.0, world_cup_matches + 4.0, 1.25)
    world_cup_gdpm_shrunk = metric_div(
        bucket["world_cup_gf"] - bucket["world_cup_ga"], world_cup_matches + 4.0, 0.0
    )
    world_cup_gfpm_shrunk = metric_div(bucket["world_cup_gf"] + 4.8, world_cup_matches + 4.0, 1.20)
    world_cup_gapm_shrunk = metric_div(bucket["world_cup_ga"] + 4.4, world_cup_matches + 4.0, 1.10)

    competitive_ppm_shrunk = metric_div(bucket["competitive_points"] + 10.0, competitive_matches + 8.0, 1.25)
    competitive_gdpm_shrunk = metric_div(
        bucket["competitive_gf"] - bucket["competitive_ga"], competitive_matches + 8.0, 0.0
    )
    competitive_gfpm_shrunk = metric_div(bucket["competitive_gf"] + 10.4, competitive_matches + 8.0, 1.30)
    competitive_gapm_shrunk = metric_div(bucket["competitive_ga"] + 8.8, competitive_matches + 8.0, 1.10)

    shootout_win_rate = metric_div(shootouts["wins"], shootout_matches, 0.0)
    shootout_win_rate_shrunk = metric_div(shootouts["wins"] + 1.5, shootout_matches + 3.0, 0.5)

    return {
        "source_names": aliases,
        "matches_since_1990": int(matches),
        "weighted_matches_since_1990": round(weighted_matches, 3),
        "points_per_match": round(points_per_match, 4),
        "weighted_points_per_match": round(weighted_points_per_match, 4),
        "goals_for_per_match": round(goals_for_per_match, 4),
        "goals_against_per_match": round(goals_against_per_match, 4),
        "goal_diff_per_match": round(goal_diff_per_match, 4),
        "weighted_goals_for_per_match": round(weighted_goals_for_per_match, 4),
        "weighted_goals_against_per_match": round(weighted_goals_against_per_match, 4),
        "weighted_goal_diff_per_match": round(weighted_goal_diff_per_match, 4),
        "scoring_rate": round(scoring_rate, 4),
        "clean_sheet_rate": round(clean_sheet_rate, 4),
        "competitive_matches_since_1990": int(competitive_matches),
        "competitive_points_per_match": round(competitive_points_per_match, 4),
        "competitive_goal_diff_per_match": round(competitive_goal_diff_per_match, 4),
        "competitive_scoring_rate": round(competitive_scoring_rate, 4),
        "competitive_clean_sheet_rate": round(competitive_clean_sheet_rate, 4),
        "world_cup_matches_since_1990": int(world_cup_matches),
        "world_cup_points_per_match": round(world_cup_points_per_match, 4),
        "world_cup_goal_diff_per_match": round(world_cup_goal_diff_per_match, 4),
        "world_cup_scoring_rate": round(world_cup_scoring_rate, 4),
        "world_cup_clean_sheet_rate": round(world_cup_clean_sheet_rate, 4),
        "world_cup_points_per_match_shrunk": round(world_cup_ppm_shrunk, 4),
        "world_cup_goal_diff_per_match_shrunk": round(world_cup_gdpm_shrunk, 4),
        "world_cup_goals_for_per_match_shrunk": round(world_cup_gfpm_shrunk, 4),
        "world_cup_goals_against_per_match_shrunk": round(world_cup_gapm_shrunk, 4),
        "competitive_points_per_match_shrunk": round(competitive_ppm_shrunk, 4),
        "competitive_goal_diff_per_match_shrunk": round(competitive_gdpm_shrunk, 4),
        "competitive_goals_for_per_match_shrunk": round(competitive_gfpm_shrunk, 4),
        "competitive_goals_against_per_match_shrunk": round(competitive_gapm_shrunk, 4),
        "shootout_matches_since_1990": int(shootout_matches),
        "shootout_win_rate": round(shootout_win_rate, 4),
        "shootout_win_rate_shrunk": round(shootout_win_rate_shrunk, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye features historicos de selecciones desde 1990.")
    parser.add_argument("--teams", default=str(DEFAULT_TEAMS_FILE))
    parser.add_argument("--results", required=True)
    parser.add_argument("--shootouts", required=True)
    parser.add_argument("--former-names", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_FILE))
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    args = parser.parse_args()

    teams = load_teams(Path(args.teams))
    team_aliases = build_team_name_map(teams, Path(args.former_names), args.start_date)
    dataset_name_to_team: dict[str, str] = {}
    for local_name, aliases in team_aliases.items():
        for alias in aliases:
            dataset_name_to_team[alias] = local_name

    stats = defaultdict(team_stat_bucket)
    with Path(args.results).open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["date"] < args.start_date:
                continue
            home_team = dataset_name_to_team.get(row["home_team"])
            away_team = dataset_name_to_team.get(row["away_team"])
            if not home_team and not away_team:
                continue
            match_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
            weight = recency_weight(match_date)
            home_score = int(row["home_score"])
            away_score = int(row["away_score"])
            tournament = row["tournament"]
            if home_team:
                update_bucket(stats[home_team], home_score, away_score, tournament, weight)
            if away_team:
                update_bucket(stats[away_team], away_score, home_score, tournament, weight)

    shootouts = defaultdict(lambda: {"matches": 0.0, "wins": 0.0})
    with Path(args.shootouts).open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["date"] < args.start_date:
                continue
            participants = [
                dataset_name_to_team.get(row["home_team"]),
                dataset_name_to_team.get(row["away_team"]),
            ]
            winner = dataset_name_to_team.get(row["winner"])
            for team in participants:
                if team:
                    shootouts[team]["matches"] += 1.0
            if winner:
                shootouts[winner]["wins"] += 1.0

    team_rows: dict[str, dict[str, object]] = {}
    strength_raw: dict[str, float] = {}
    attack_raw: dict[str, float] = {}
    defense_raw: dict[str, float] = {}
    competitive_raw: dict[str, float] = {}
    world_cup_raw: dict[str, float] = {}
    shootout_raw: dict[str, float] = {}

    for team in [entry["name"] for entry in teams]:
        row = build_output_record(team, team_aliases[team], stats[team], shootouts[team])
        team_rows[team] = row
        world_cup_experience = min(float(row["world_cup_matches_since_1990"]) / 20.0, 1.0)
        shootout_experience = min(float(row["shootout_matches_since_1990"]) / 12.0, 1.0)
        strength_raw[team] = (
            0.32 * float(row["weighted_points_per_match"])
            + 0.18 * float(row["points_per_match"])
            + 0.18 * float(row["competitive_points_per_match_shrunk"])
            + 0.12 * float(row["weighted_goal_diff_per_match"])
            + 0.10 * float(row["world_cup_points_per_match_shrunk"])
            + 0.05 * float(row["scoring_rate"])
            + 0.05 * float(row["clean_sheet_rate"])
        )
        attack_raw[team] = (
            0.42 * float(row["weighted_goals_for_per_match"])
            + 0.20 * float(row["goals_for_per_match"])
            + 0.15 * float(row["competitive_goals_for_per_match_shrunk"])
            + 0.10 * float(row["world_cup_goals_for_per_match_shrunk"])
            + 0.08 * float(row["scoring_rate"])
            + 0.05 * max(float(row["weighted_goal_diff_per_match"]), 0.0)
        )
        defense_raw[team] = (
            -0.42 * float(row["weighted_goals_against_per_match"])
            - 0.18 * float(row["goals_against_per_match"])
            - 0.15 * float(row["competitive_goals_against_per_match_shrunk"])
            - 0.10 * float(row["world_cup_goals_against_per_match_shrunk"])
            + 0.10 * float(row["clean_sheet_rate"])
            + 0.05 * float(row["competitive_clean_sheet_rate"])
        )
        competitive_raw[team] = (
            0.55 * float(row["competitive_points_per_match_shrunk"])
            + 0.25 * float(row["competitive_goal_diff_per_match_shrunk"])
            + 0.10 * float(row["world_cup_points_per_match_shrunk"])
            + 0.10 * float(row["competitive_clean_sheet_rate"])
        )
        world_cup_raw[team] = (
            0.55 * float(row["world_cup_points_per_match_shrunk"])
            + 0.20 * float(row["world_cup_goal_diff_per_match_shrunk"])
            + 0.15 * world_cup_experience
            + 0.10 * float(row["world_cup_scoring_rate"])
        )
        shootout_raw[team] = (
            0.70 * float(row["shootout_win_rate_shrunk"])
            + 0.30 * shootout_experience
        )

    strength_idx = normalize_map(strength_raw)
    attack_idx = normalize_map(attack_raw)
    defense_idx = normalize_map(defense_raw)
    competitive_idx = normalize_map(competitive_raw)
    world_cup_idx = normalize_map(world_cup_raw)
    shootout_idx = normalize_map(shootout_raw)

    for team, row in team_rows.items():
        row["strength_index"] = round(strength_idx[team], 4)
        row["attack_index"] = round(attack_idx[team], 4)
        row["defense_index"] = round(defense_idx[team], 4)
        row["competitive_index"] = round(competitive_idx[team], 4)
        row["world_cup_index"] = round(world_cup_idx[team], 4)
        row["shootout_index"] = round(shootout_idx[team], 4)

    output = {
        "meta": {
            "as_of": TODAY.isoformat(),
            "from_date": args.start_date,
            "description": "Indicadores historicos de selecciones nacionales desde 1990, con mezcla de rendimiento total, competitivo, mundialista y penales.",
            "source_results": DATASET_SOURCE_RESULTS,
            "source_shootouts": DATASET_SOURCE_SHOOTOUTS,
            "source_former_names": DATASET_SOURCE_FORMER_NAMES,
            "decay_half_life_years": 8,
            "competitive_exclusions": sorted(COMPETITIVE_TOURNAMENT_EXCLUDE),
        },
        "teams": team_rows,
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True))
    print(f"Escrito: {output_path}")


if __name__ == "__main__":
    main()
