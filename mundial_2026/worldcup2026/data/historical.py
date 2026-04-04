from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

FIFA_CONFEDERATION_ADJUST = {
    "UEFA": 16.0,
    "CONMEBOL": 18.0,
    "CAF": -6.0,
    "AFC": -8.0,
    "CONCACAF": -10.0,
    "OFC": -28.0,
}

HISTORICAL_TEAM_NAME_ALIASES = {
    "Curacao": "Curaçao",
    "Dem. Rep. of Congo": "DR Congo",
}


def estimated_fifa_points(
    team,
    *,
    heritage_index,
    resource_index,
    trajectory_index,
    coach_index,
    centered,
    clamp,
):
    value = 1050.0 + 0.82 * (team.elo - 1200.0)
    value += 92.0 * centered(heritage_index(team))
    value += 58.0 * centered(resource_index(team))
    value += 34.0 * centered(trajectory_index(team))
    value += 26.0 * centered(coach_index(team))
    value += FIFA_CONFEDERATION_ADJUST.get(team.confederation, 0.0)
    if team.is_host:
        value += 8.0
    return clamp(value, 820.0, 2250.0)


@lru_cache(maxsize=8)
def fifa_reference_table(*, load_teams_fn, estimated_fifa_points_fn):
    teams = load_teams_fn()
    rows = []
    for team in teams.values():
        points = float(team.fifa_points) if team.fifa_points is not None else estimated_fifa_points_fn(team)
        rows.append((team.name, points, team.fifa_rank, team.fifa_points is None))

    rows.sort(key=lambda item: (-item[1], item[0]))
    table = {}
    for derived_rank, (name, points, explicit_rank, is_proxy) in enumerate(rows, start=1):
        rank = int(explicit_rank) if explicit_rank is not None else derived_rank
        table[name] = (points, rank, is_proxy)
    return table


def fifa_points_value(team, *, reference_table_fn):
    return reference_table_fn()[team.name][0]


def fifa_rank_value(team, *, reference_table_fn):
    return reference_table_fn()[team.name][1]


def fifa_points_are_proxy(team, *, reference_table_fn):
    return reference_table_fn()[team.name][2]


def fifa_points_bounds(*, reference_table_fn):
    values = [points for points, _, _ in reference_table_fn().values()]
    return (min(values), max(values))


def fifa_strength_index(team, *, points_bounds_fn, points_value_fn, clamp):
    low, high = points_bounds_fn()
    if high <= low:
        return 0.5
    return clamp((points_value_fn(team) - low) / (high - low), 0.0, 1.0)


@lru_cache(maxsize=8)
def historical_features_payload(historical_features_file: str):
    path = Path(historical_features_file)
    if not path.exists():
        return {"meta": {"missing": True}, "teams": {}}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"meta": {"invalid": True}, "teams": {}}


def proxy_historical_snapshot(
    team,
    *,
    HistoricalSnapshotCls,
    clamp,
    world_cup_titles,
    coach_overrides,
    team_name_aliases=None,
):
    team_name_aliases = team_name_aliases or HISTORICAL_TEAM_NAME_ALIASES
    strength = clamp(0.50 + (team.elo - 1650.0) / 600.0, 0.08, 0.95)
    attack = clamp(strength + 0.10 * team.attack_bias, 0.05, 0.98)
    defense = clamp(strength + 0.10 * team.defense_bias, 0.05, 0.98)
    competitive = clamp(0.42 + (team.elo - 1650.0) / 720.0, 0.08, 0.95)
    world_cup = clamp(0.26 + 0.10 * world_cup_titles.get(team.name, 0), 0.05, 0.98)
    shootout = clamp(0.46 + 0.06 * coach_overrides.get(team.name, 0.0), 0.05, 0.95)
    return HistoricalSnapshotCls(
        source_names=(team_name_aliases.get(team.name, team.name),),
        matches_since_1990=0,
        weighted_matches_since_1990=0.0,
        points_per_match=1.25,
        weighted_points_per_match=1.25,
        goals_for_per_match=1.2,
        goals_against_per_match=1.2,
        goal_diff_per_match=0.0,
        weighted_goals_for_per_match=1.2,
        weighted_goals_against_per_match=1.2,
        weighted_goal_diff_per_match=0.0,
        scoring_rate=0.62,
        clean_sheet_rate=0.26,
        competitive_matches_since_1990=0,
        competitive_points_per_match=1.25,
        competitive_goal_diff_per_match=0.0,
        world_cup_matches_since_1990=0,
        world_cup_points_per_match=0.0,
        world_cup_goal_diff_per_match=0.0,
        shootout_matches_since_1990=0,
        shootout_win_rate=0.5,
        strength_index=strength,
        attack_index=attack,
        defense_index=defense,
        competitive_index=competitive,
        world_cup_index=world_cup,
        shootout_index=shootout,
    )


def historical_snapshot(
    team,
    *,
    payload_fn,
    proxy_snapshot_fn,
    HistoricalSnapshotCls,
    empirical_bayes_shrinkage,
    clamp,
    team_name_aliases=None,
):
    team_name_aliases = team_name_aliases or HISTORICAL_TEAM_NAME_ALIASES
    payload = payload_fn()
    row = payload.get("teams", {}).get(team.name)
    if not row:
        return proxy_snapshot_fn(team)
    proxy = proxy_snapshot_fn(team)
    weighted_matches = float(row.get("weighted_matches_since_1990", 0.0))
    matches_since_1990 = int(row.get("matches_since_1990", 0))
    competitive_matches = int(row.get("competitive_matches_since_1990", 0))
    world_cup_matches = int(row.get("world_cup_matches_since_1990", 0))
    shootout_matches = int(row.get("shootout_matches_since_1990", 0))

    strength_index = clamp(
        empirical_bayes_shrinkage(float(row.get("strength_index", proxy.strength_index)), weighted_matches or matches_since_1990, proxy.strength_index, 18.0),
        0.0,
        1.0,
    )
    attack_index = clamp(
        empirical_bayes_shrinkage(float(row.get("attack_index", proxy.attack_index)), weighted_matches or matches_since_1990, proxy.attack_index, 18.0),
        0.0,
        1.0,
    )
    defense_index = clamp(
        empirical_bayes_shrinkage(float(row.get("defense_index", proxy.defense_index)), weighted_matches or matches_since_1990, proxy.defense_index, 18.0),
        0.0,
        1.0,
    )
    competitive_index = clamp(
        empirical_bayes_shrinkage(float(row.get("competitive_index", proxy.competitive_index)), competitive_matches, proxy.competitive_index, 12.0),
        0.0,
        1.0,
    )
    world_cup_index = clamp(
        empirical_bayes_shrinkage(float(row.get("world_cup_index", proxy.world_cup_index)), world_cup_matches, proxy.world_cup_index, 6.0),
        0.0,
        1.0,
    )
    shootout_index = clamp(
        empirical_bayes_shrinkage(float(row.get("shootout_index", proxy.shootout_index)), shootout_matches, proxy.shootout_index, 5.0),
        0.0,
        1.0,
    )
    return HistoricalSnapshotCls(
        source_names=tuple(row.get("source_names") or [team_name_aliases.get(team.name, team.name)]),
        matches_since_1990=matches_since_1990,
        weighted_matches_since_1990=weighted_matches,
        points_per_match=float(row.get("points_per_match", proxy.points_per_match)),
        weighted_points_per_match=float(row.get("weighted_points_per_match", proxy.weighted_points_per_match)),
        goals_for_per_match=float(row.get("goals_for_per_match", 1.2)),
        goals_against_per_match=float(row.get("goals_against_per_match", 1.2)),
        goal_diff_per_match=float(row.get("goal_diff_per_match", 0.0)),
        weighted_goals_for_per_match=float(row.get("weighted_goals_for_per_match", 1.2)),
        weighted_goals_against_per_match=float(row.get("weighted_goals_against_per_match", 1.2)),
        weighted_goal_diff_per_match=float(row.get("weighted_goal_diff_per_match", 0.0)),
        scoring_rate=float(row.get("scoring_rate", 0.62)),
        clean_sheet_rate=float(row.get("clean_sheet_rate", 0.26)),
        competitive_matches_since_1990=competitive_matches,
        competitive_points_per_match=float(row.get("competitive_points_per_match", proxy.competitive_points_per_match)),
        competitive_goal_diff_per_match=float(row.get("competitive_goal_diff_per_match", 0.0)),
        world_cup_matches_since_1990=world_cup_matches,
        world_cup_points_per_match=float(row.get("world_cup_points_per_match", proxy.world_cup_points_per_match)),
        world_cup_goal_diff_per_match=float(row.get("world_cup_goal_diff_per_match", 0.0)),
        shootout_matches_since_1990=shootout_matches,
        shootout_win_rate=float(row.get("shootout_win_rate", proxy.shootout_win_rate)),
        strength_index=strength_index,
        attack_index=attack_index,
        defense_index=defense_index,
        competitive_index=competitive_index,
        world_cup_index=world_cup_index,
        shootout_index=shootout_index,
    )
