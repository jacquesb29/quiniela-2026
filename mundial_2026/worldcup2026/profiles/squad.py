from __future__ import annotations


def sort_by(players, key_name: str):
    return sorted(players, key=lambda player: getattr(player, key_name), reverse=True)


def aggregate_squad(team, *, proxy_players_fn, clamp, SquadAggregateCls):
    players = proxy_players_fn(team)
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

    return SquadAggregateCls(
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
