from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


def load_players(raw_players, *, PlayerCls):
    players = []
    for item in raw_players:
        players.append(
            PlayerCls(
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
                market_value_eur_m=float(item.get("market_value_eur_m", item.get("market_value", 0.0))),
                total_minutes_last_12_months=float(item.get("total_minutes_last_12_months", 0.0)),
                club_world_cup_minutes=float(item.get("club_world_cup_minutes", 0.0)),
                days_since_last_match=float(item.get("days_since_last_match", 14.0)),
                injury_proneness=float(item.get("injury_proneness", 0.0)),
                expected_threat=float(item.get("expected_threat", item.get("xt", 0.0))),
                progressive_passes=float(item.get("progressive_passes", 0.0)),
                progressive_carries=float(item.get("progressive_carries", 0.0)),
                ppda=float(item.get("ppda", 0.0)),
                field_tilt=float(item.get("field_tilt", 0.0)),
                penalty_taker_quality=float(item.get("penalty_taker_quality", 0.0)),
                goalkeeper_penalty_save_rate=float(item.get("goalkeeper_penalty_save_rate", 0.0)),
                shootout_pressure_experience=float(item.get("shootout_pressure_experience", 0.0)),
            )
        )
    return tuple(players)


@lru_cache(maxsize=8)
def load_teams(data_file: str, *, TeamCls, load_players_fn):
    payload = json.loads(Path(data_file).read_text())
    teams = {}
    for item in payload["teams"]:
        teams[item["name"]] = TeamCls(
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
            population_millions=float(item["population_millions"]) if item.get("population_millions") is not None else None,
            gdp_per_capita_usd=float(item["gdp_per_capita_usd"]) if item.get("gdp_per_capita_usd") is not None else None,
            gdp_ppp_usd_billion=float(item["gdp_ppp_usd_billion"]) if item.get("gdp_ppp_usd_billion") is not None else None,
            league_strength_index=float(item["league_strength_index"]) if item.get("league_strength_index") is not None else None,
            top_league_minutes_share=float(item["top_league_minutes_share"]) if item.get("top_league_minutes_share") is not None else None,
            avg_age=float(item["avg_age"]) if item.get("avg_age") is not None else None,
            squad_market_value_eur_m=float(item["squad_market_value_eur_m"]) if item.get("squad_market_value_eur_m") is not None else None,
            heat_humidity_load=float(item.get("heat_humidity_load", 0.0)),
            time_zone_shift=float(item.get("time_zone_shift", 0.0)),
            venue_surface_adjustment=float(item.get("venue_surface_adjustment", 0.0)),
            travel_cluster_difficulty=float(item.get("travel_cluster_difficulty", 0.0)),
            expected_threat=float(item.get("expected_threat", item.get("xt", 0.0))),
            progressive_passes=float(item.get("progressive_passes", 0.0)),
            progressive_carries=float(item.get("progressive_carries", 0.0)),
            ppda=float(item.get("ppda", 0.0)),
            field_tilt=float(item.get("field_tilt", 0.0)),
            high_press_resistance=float(item.get("high_press_resistance", 0.0)),
            low_block_breaking=float(item.get("low_block_breaking", 0.0)),
            transition_defense=float(item.get("transition_defense", 0.0)),
            aerial_matchup_advantage=float(item.get("aerial_matchup_advantage", 0.0)),
            penalty_taker_quality=float(item.get("penalty_taker_quality", 0.0)),
            goalkeeper_penalty_save_rate=float(item.get("goalkeeper_penalty_save_rate", 0.0)),
            shootout_pressure_experience=float(item.get("shootout_pressure_experience", 0.0)),
            keeper_taker_strategy_matchup=float(item.get("keeper_taker_strategy_matchup", 0.0)),
            players=load_players_fn(item.get("players", [])),
        )
    return teams


def load_tournament_config(path):
    return json.loads(Path(path).read_text())


def read_fixtures(path):
    return json.loads(Path(path).read_text())
