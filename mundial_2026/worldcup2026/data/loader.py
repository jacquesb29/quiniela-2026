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
            players=load_players_fn(item.get("players", [])),
        )
    return teams


def load_tournament_config(path):
    return json.loads(Path(path).read_text())


def read_fixtures(path):
    return json.loads(Path(path).read_text())
