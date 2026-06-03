from __future__ import annotations


def sort_by(players, key_name: str):
    return sorted(players, key=lambda player: getattr(player, key_name), reverse=True)


def normalized_ppda_intensity(value: float, *, clamp) -> float:
    """Lower raw PPDA means stronger pressing; normalized inputs are accepted too."""

    if value <= 0:
        return 0.0
    if value <= 1.0:
        return clamp(value, 0.0, 1.0)
    return clamp((18.0 - value) / 10.0, 0.0, 1.0)


def market_value_index(value_eur_m: float, *, clamp) -> float:
    if value_eur_m <= 0:
        return 0.50
    import math

    return clamp(math.log1p(value_eur_m) / math.log1p(1600.0), 0.10, 1.0)


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
    recent_minutes_load = clamp(sum(player.minutes_share for player in starting) / len(starting), 0.16, 1.00)
    goalkeeper_minutes_load = clamp(
        sum(player.minutes_share for player in starting if player.position == "GK"),
        0.16,
        1.00,
    )
    bench_impact = clamp(
        sum(
            0.45 * player.quality
            + 0.20 * player.attack
            + 0.15 * player.creation
            + 0.10 * player.defense
            + 0.10 * player.availability
            for player in bench[:5]
        )
        / max(len(bench[:5]), 1),
        0.08,
        1.00,
    )
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
    values = [max(float(getattr(player, "market_value_eur_m", 0.0)), 0.0) for player in players]
    explicit_squad_market_value = getattr(team, "squad_market_value_eur_m", None)
    squad_market_value = (
        float(explicit_squad_market_value)
        if explicit_squad_market_value is not None and explicit_squad_market_value > 0
        else sum(values)
    )
    top_values = sorted(values, reverse=True)[:5]
    top_5_players_value_share = clamp(sum(top_values) / max(squad_market_value, 1e-9), 0.0, 0.92)
    starting_values = [max(float(getattr(player, "market_value_eur_m", 0.0)), 0.0) for player in starting]
    bench_values = [max(float(getattr(player, "market_value_eur_m", 0.0)), 0.0) for player in bench]
    starting_value_mean = sum(starting_values) / max(len(starting_values), 1)
    bench_value_mean = sum(bench_values) / max(len(bench_values), 1)
    value_depth_ratio = clamp(bench_value_mean / max(starting_value_mean, 1e-9), 0.05, 1.25)
    talent_market_index = clamp(
        0.54 * market_value_index(squad_market_value, clamp=clamp)
        + 0.22 * clamp(value_depth_ratio, 0.0, 1.0)
        + 0.14 * (1.0 - top_5_players_value_share)
        + 0.10 * clamp(float(getattr(team, "top_league_minutes_share", 0.0) or 0.0), 0.0, 1.0),
        0.08,
        1.0,
    )
    total_minutes_last_12_months = sum(
        float(getattr(player, "total_minutes_last_12_months", 0.0) or 0.0) for player in starting
    )
    if total_minutes_last_12_months <= 0:
        total_minutes_last_12_months = 3300.0 * sum(float(getattr(player, "minutes_share", 0.0)) for player in starting)
    club_world_cup_minutes = sum(
        float(getattr(player, "club_world_cup_minutes", 0.0) or 0.0) for player in starting
    )
    days_since_last_match = clamp(
        sum(float(getattr(player, "days_since_last_match", 14.0) or 14.0) for player in starting) / len(starting),
        1.0,
        45.0,
    )
    injury_proneness = clamp(
        sum(float(getattr(player, "injury_proneness", 0.0) or 0.0) for player in starting) / len(starting),
        0.0,
        1.0,
    )
    minutes_load_component = clamp((total_minutes_last_12_months / max(len(starting), 1) - 2100.0) / 1800.0, 0.0, 1.0)
    club_world_cup_component = clamp(club_world_cup_minutes / 3600.0, 0.0, 1.0)
    recency_component = clamp((8.0 - days_since_last_match) / 8.0, 0.0, 1.0)
    physical_load_index = clamp(
        0.46 * minutes_load_component
        + 0.20 * club_world_cup_component
        + 0.18 * recency_component
        + 0.16 * injury_proneness,
        0.0,
        1.0,
    )
    expected_threat = clamp(
        (
            sum(float(getattr(player, "expected_threat", 0.0) or 0.0) for player in starting)
            / len(starting)
            + float(getattr(team, "expected_threat", 0.0) or 0.0)
        )
        / (2.0 if getattr(team, "expected_threat", 0.0) else 1.0),
        0.0,
        1.0,
    )
    progressive_passes = clamp(
        (
            sum(float(getattr(player, "progressive_passes", 0.0) or 0.0) for player in starting)
            / len(starting)
            + float(getattr(team, "progressive_passes", 0.0) or 0.0)
        )
        / (2.0 if getattr(team, "progressive_passes", 0.0) else 1.0),
        0.0,
        1.0,
    )
    progressive_carries = clamp(
        (
            sum(float(getattr(player, "progressive_carries", 0.0) or 0.0) for player in starting)
            / len(starting)
            + float(getattr(team, "progressive_carries", 0.0) or 0.0)
        )
        / (2.0 if getattr(team, "progressive_carries", 0.0) else 1.0),
        0.0,
        1.0,
    )
    raw_ppda_values = [float(getattr(player, "ppda", 0.0) or 0.0) for player in starting]
    ppda = clamp(
        (
            sum(normalized_ppda_intensity(value, clamp=clamp) for value in raw_ppda_values) / len(starting)
            + normalized_ppda_intensity(float(getattr(team, "ppda", 0.0) or 0.0), clamp=clamp)
        )
        / (2.0 if getattr(team, "ppda", 0.0) else 1.0),
        0.0,
        1.0,
    )
    field_tilt = clamp(
        (
            sum(float(getattr(player, "field_tilt", 0.0) or 0.0) for player in starting)
            / len(starting)
            + float(getattr(team, "field_tilt", 0.0) or 0.0)
        )
        / (2.0 if getattr(team, "field_tilt", 0.0) else 1.0),
        0.0,
        1.0,
    )
    advanced_style_index = clamp(
        0.28 * expected_threat
        + 0.20 * progressive_passes
        + 0.18 * progressive_carries
        + 0.16 * ppda
        + 0.18 * field_tilt,
        0.0,
        1.0,
    )
    high_press_resistance = clamp(
        float(getattr(team, "high_press_resistance", 0.0) or 0.0)
        or (0.42 * midfield_unit + 0.28 * shot_creation + 0.18 * player_experience + 0.12 * progressive_carries),
        0.0,
        1.0,
    )
    low_block_breaking = clamp(
        float(getattr(team, "low_block_breaking", 0.0) or 0.0)
        or (0.32 * shot_creation + 0.25 * finishing + 0.18 * set_piece_attack + 0.15 * expected_threat + 0.10 * progressive_passes),
        0.0,
        1.0,
    )
    transition_defense = clamp(
        float(getattr(team, "transition_defense", 0.0) or 0.0)
        or (0.36 * defense_unit + 0.22 * midfield_unit + 0.18 * pressing + 0.14 * discipline_index + 0.10 * goalkeeper_unit),
        0.0,
        1.0,
    )
    aerial_matchup_advantage = clamp(
        float(getattr(team, "aerial_matchup_advantage", 0.0) or 0.0)
        or (0.52 * set_piece_attack + 0.30 * set_piece_defense + 0.18 * goalkeeper_unit),
        0.0,
        1.0,
    )
    tactical_matchup_index = clamp(
        0.28 * high_press_resistance
        + 0.26 * low_block_breaking
        + 0.25 * transition_defense
        + 0.21 * aerial_matchup_advantage,
        0.0,
        1.0,
    )
    penalty_taker_quality = clamp(
        float(getattr(team, "penalty_taker_quality", 0.0) or 0.0)
        or (
            sum(float(getattr(player, "penalty_taker_quality", 0.0) or 0.0) for player in sort_by(players, "attack")[:5])
            / 5.0
        ),
        0.0,
        1.0,
    )
    goalkeeper_penalty_save_rate = clamp(
        float(getattr(team, "goalkeeper_penalty_save_rate", 0.0) or 0.0)
        or (
            sum(float(getattr(player, "goalkeeper_penalty_save_rate", 0.0) or 0.0) for player in gks[:1])
            if gks
            else 0.0
        ),
        0.0,
        1.0,
    )
    shootout_pressure_experience = clamp(
        float(getattr(team, "shootout_pressure_experience", 0.0) or 0.0)
        or (
            sum(float(getattr(player, "shootout_pressure_experience", 0.0) or 0.0) for player in starting)
            / len(starting)
        ),
        0.0,
        1.0,
    )
    keeper_taker_strategy_matchup = clamp(float(getattr(team, "keeper_taker_strategy_matchup", 0.0) or 0.0), -1.0, 1.0)
    penalty_granular_index = clamp(
        0.38 * penalty_taker_quality
        + 0.26 * goalkeeper_penalty_save_rate
        + 0.24 * shootout_pressure_experience
        + 0.12 * (0.5 + 0.5 * keeper_taker_strategy_matchup),
        0.0,
        1.0,
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
        recent_minutes_load=recent_minutes_load,
        goalkeeper_minutes_load=goalkeeper_minutes_load,
        bench_impact=bench_impact,
        squad_market_value=squad_market_value,
        top_5_players_value_share=top_5_players_value_share,
        value_depth_ratio=value_depth_ratio,
        talent_market_index=talent_market_index,
        total_minutes_last_12_months=total_minutes_last_12_months,
        club_world_cup_minutes=club_world_cup_minutes,
        days_since_last_match=days_since_last_match,
        injury_proneness=injury_proneness,
        physical_load_index=physical_load_index,
        expected_threat=expected_threat,
        progressive_passes=progressive_passes,
        progressive_carries=progressive_carries,
        ppda=ppda,
        field_tilt=field_tilt,
        advanced_style_index=advanced_style_index,
        high_press_resistance=high_press_resistance,
        low_block_breaking=low_block_breaking,
        transition_defense=transition_defense,
        aerial_matchup_advantage=aerial_matchup_advantage,
        tactical_matchup_index=tactical_matchup_index,
        penalty_taker_quality=penalty_taker_quality,
        goalkeeper_penalty_save_rate=goalkeeper_penalty_save_rate,
        shootout_pressure_experience=shootout_pressure_experience,
        keeper_taker_strategy_matchup=keeper_taker_strategy_matchup,
        penalty_granular_index=penalty_granular_index,
    )
