from __future__ import annotations

from worldcup2026.config import PARAMS


def context_components(
    team,
    profile,
    opponent,
    ctx,
    side,
    *,
    state=None,
    current_morale,
    discipline_absence_penalty,
    group_pressure,
    rivalry_intensity,
    fatigue_level,
    availability_level,
    recent_form_signal,
    clamp,
    host_countries,
):
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
        lineup_strength = float(getattr(ctx, "lineup_strength_delta_a", 0.0) or 0.0)
        lineup_attack = float(getattr(ctx, "lineup_attack_delta_a", 0.0) or 0.0)
        lineup_defense = float(getattr(ctx, "lineup_defense_delta_a", 0.0) or 0.0)
        lineup_goalkeeper = float(getattr(ctx, "lineup_goalkeeper_delta_a", 0.0) or 0.0)
        lineup_coverage = float(getattr(ctx, "lineup_coverage_a", 0.0) or 0.0)
        market_move = ctx.market_move_a
        goalkeeper_confirmed = ctx.goalkeeper_confirmed_a
        goalkeeper_change = ctx.goalkeeper_change_a
        live_substitutions = ctx.live_substitutions_a
        live_substitutions_other = ctx.live_substitutions_b
        substitution_impact = ctx.substitution_impact_a
        substitution_impact_other = ctx.substitution_impact_b
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
        lineup_strength = float(getattr(ctx, "lineup_strength_delta_b", 0.0) or 0.0)
        lineup_attack = float(getattr(ctx, "lineup_attack_delta_b", 0.0) or 0.0)
        lineup_defense = float(getattr(ctx, "lineup_defense_delta_b", 0.0) or 0.0)
        lineup_goalkeeper = float(getattr(ctx, "lineup_goalkeeper_delta_b", 0.0) or 0.0)
        lineup_coverage = float(getattr(ctx, "lineup_coverage_b", 0.0) or 0.0)
        market_move = ctx.market_move_b
        goalkeeper_confirmed = ctx.goalkeeper_confirmed_b
        goalkeeper_change = ctx.goalkeeper_change_b
        live_substitutions = ctx.live_substitutions_b
        live_substitutions_other = ctx.live_substitutions_a
        substitution_impact = ctx.substitution_impact_b
        substitution_impact_other = ctx.substitution_impact_a

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
        "lineup_strength": 0.20 * clamp(lineup_strength, -0.24, 0.18) * (0.45 + 0.55 * clamp(lineup_coverage, 0.0, 1.0)),
        "lineup_attack": 0.12 * clamp(lineup_attack, -0.22, 0.18) * (0.45 + 0.55 * clamp(lineup_coverage, 0.0, 1.0)),
        "lineup_defense": 0.10 * clamp(lineup_defense, -0.22, 0.18) * (0.45 + 0.55 * clamp(lineup_coverage, 0.0, 1.0)),
        "lineup_goalkeeper": 0.12 * clamp(lineup_goalkeeper, -0.22, 0.18) * (0.45 + 0.55 * clamp(lineup_coverage, 0.0, 1.0)),
        "goalkeeper_context": (0.014 if goalkeeper_confirmed else 0.0) - (0.045 if goalkeeper_change else 0.0),
        "substitutions": (
            0.035 * clamp(substitution_impact - substitution_impact_other, -1.0, 1.0)
            + 0.012 * clamp(live_substitutions - live_substitutions_other, -5, 5)
        ),
        "market_move": 0.22 * clamp(market_move, -0.18, 0.18),
        "referee": (
            0.012 * clamp(ctx.referee_penalty_bias, -1.0, 1.0)
            + 0.010 * clamp(ctx.referee_red_bias, -1.0, 1.0) * (0.5 - profile.squad.discipline_index)
            - 0.008 * clamp(ctx.referee_yellow_bias, -1.0, 1.0) * (0.55 - profile.squad.discipline_index)
        ),
        "fatigue": -0.14 * fatigue_level(state),
        "availability": -0.18 * (1.0 - availability_level(state)),
        "recent_form": 0.10 * recent_form_signal(state),
    }

    if not ctx.neutral and ctx.home_team == team.name:
        components["home"] += 0.22
    if ctx.venue_country and team.host_country == ctx.venue_country:
        components["home"] += 0.14
    elif ctx.venue_country in host_countries and team.is_host:
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


def attack_metric(team, profile, *, state=None, effective_elo, centered, attack_form_signal, recent_form_signal, tactical_attack_signal, tactical_tempo_signal, fatigue_level, availability_level):
    strength = (effective_elo(team, state) - 1650.0) / 320.0
    value = 0.48 * strength
    value += 0.05 * centered(profile.fifa_strength_index)
    value += 0.12 * centered(profile.history.attack_index)
    value += 0.05 * centered(profile.history.competitive_index)
    value += 0.30 * centered(profile.squad.attack_unit)
    value += 0.18 * centered(profile.squad.midfield_unit)
    value += 0.14 * centered(profile.squad.finishing)
    value += 0.10 * centered(profile.squad.set_piece_attack)
    value += 0.06 * centered(profile.squad.recent_minutes_load)
    value += 0.06 * centered(profile.squad.bench_impact)
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


def defense_metric(team, profile, *, state=None, effective_elo, centered, defense_form_signal, recent_form_signal, discipline_trend, tactical_defense_signal, tactical_tempo_signal, fatigue_level, availability_level):
    strength = (effective_elo(team, state) - 1650.0) / 340.0
    value = 0.44 * strength
    value += 0.04 * centered(profile.fifa_strength_index)
    value += 0.12 * centered(profile.history.defense_index)
    value += 0.04 * centered(profile.history.world_cup_index)
    value += 0.28 * centered(profile.squad.defense_unit)
    value += 0.14 * centered(profile.squad.goalkeeper_unit)
    value += 0.10 * centered(profile.squad.player_experience)
    value += 0.08 * centered(profile.squad.discipline_index)
    value += 0.06 * centered(profile.coach_index)
    value += 0.05 * centered(profile.heritage_index)
    value += 0.04 * centered(profile.squad.set_piece_defense)
    value += 0.04 * centered(profile.squad.recent_minutes_load)
    value += 0.05 * centered(profile.squad.goalkeeper_minutes_load)
    value += 0.05 * centered(profile.squad.bench_impact)
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
    team_a,
    team_b,
    ctx,
    *,
    state_a=None,
    state_b=None,
    profile_for,
    context_components_fn,
    attack_metric_fn,
    defense_metric_fn,
    effective_elo,
    logistic,
    centered,
    rivalry_intensity,
    attack_form_signal,
    defense_form_signal,
    recent_form_signal,
    tactical_attack_signal,
    tactical_defense_signal,
    tactical_tempo_signal,
    fatigue_level,
    availability_level,
    recent_xg_for_signal,
    recent_xga_signal,
    recent_opponent_strength_signal,
    group_pressure,
    clamp,
):
    profile_a = profile_for(team_a)
    profile_b = profile_for(team_b)
    context_a = context_components_fn(team_a, profile_a, team_b, ctx, "A", state=state_a)
    context_b = context_components_fn(team_b, profile_b, team_a, ctx, "B", state=state_b)
    importance_scale = clamp(ctx.importance, 0.70, 1.50)

    attack_a = attack_metric_fn(team_a, profile_a, state=state_a)
    attack_b = attack_metric_fn(team_b, profile_b, state=state_b)
    defense_a = defense_metric_fn(team_a, profile_a, state=state_a)
    defense_b = defense_metric_fn(team_b, profile_b, state=state_b)

    attack_edge_a = attack_a - defense_b
    attack_edge_b = attack_b - defense_a
    elo_diff = effective_elo(team_a, state_a) - effective_elo(team_b, state_b)
    fifa_diff = profile_a.fifa_strength_index - profile_b.fifa_strength_index
    history_weight = (0.11 if ctx.knockout else 0.06) * importance_scale

    # Elo/FIFA already influence attack_metric and defense_metric. Keep the
    # direct layer as a guardrail, not a second full-strength vote.
    delta_score = elo_diff / PARAMS.expected_goal_elo_divisor
    delta_score += PARAMS.expected_goal_fifa_weight * fifa_diff
    delta_score += PARAMS.expected_goal_history_strength_weight * (
        profile_a.history.strength_index - profile_b.history.strength_index
    )
    delta_score += PARAMS.expected_goal_attack_edge_weight * (attack_edge_a - attack_edge_b)
    delta_score += history_weight * (profile_a.heritage_index - profile_b.heritage_index)
    delta_score += 0.05 * (profile_a.history.world_cup_index - profile_b.history.world_cup_index)
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
    delta_score += 0.12 * (recent_xg_for_signal(state_a) - recent_xg_for_signal(state_b))
    delta_score -= 0.10 * (recent_xga_signal(state_a) - recent_xga_signal(state_b))
    delta_score += 0.04 * (recent_opponent_strength_signal(state_a) - recent_opponent_strength_signal(state_b))
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
    if ctx.knockout:
        share_a = 0.5 + (share_a - 0.5) * (1.0 - PARAMS.knockout_favorite_share_shrink)

    total_goals = 2.28
    total_goals += 0.16 * abs(elo_diff) / 400.0
    total_goals += 0.04 * abs(fifa_diff)
    total_goals += 0.18 * centered(profile_a.squad.attack_unit + profile_b.squad.attack_unit)
    total_goals += 0.08 * centered(profile_a.history.attack_index + profile_b.history.attack_index)
    total_goals += 0.12 * centered(profile_a.squad.shot_creation + profile_b.squad.shot_creation)
    total_goals -= 0.12 * centered(profile_a.squad.defense_unit + profile_b.squad.defense_unit)
    total_goals -= 0.08 * centered(profile_a.history.defense_index + profile_b.history.defense_index)
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
    total_goals += 0.08 * (recent_xg_for_signal(state_a) + recent_xg_for_signal(state_b))
    total_goals += 0.06 * (recent_xga_signal(state_a) + recent_xga_signal(state_b))
    total_goals += 0.06 * (tactical_tempo_signal(state_a) + tactical_tempo_signal(state_b))
    total_goals += 0.03 * (tactical_attack_signal(state_a) + tactical_attack_signal(state_b))
    total_goals -= 0.02 * (tactical_defense_signal(state_a) + tactical_defense_signal(state_b))
    total_goals -= 0.10 * (fatigue_level(state_a) + fatigue_level(state_b))
    total_goals -= 0.07 * ((1.0 - availability_level(state_a)) + (1.0 - availability_level(state_b)))
    if ctx.market_total_line is not None:
        consensus_total = clamp(ctx.market_total_line + PARAMS.goal_consensus_total_offset, 1.5, 4.6)
        gap = abs(total_goals - consensus_total)
        if gap >= PARAMS.goal_consensus_extreme_gap:
            consensus_weight = PARAMS.goal_consensus_extreme_gap_weight
        elif gap >= PARAMS.goal_consensus_high_gap:
            consensus_weight = PARAMS.goal_consensus_high_gap_weight
        else:
            consensus_weight = PARAMS.goal_consensus_base_weight
        total_goals = (1.0 - consensus_weight) * total_goals + consensus_weight * consensus_total
    if ctx.market_prob_draw is not None:
        total_goals -= 0.12 * clamp(ctx.market_prob_draw - 0.26, -0.15, 0.22)
    total_goals -= 0.40 * clamp(ctx.market_move_draw, -0.08, 0.08)
    total_goals = clamp(total_goals, 1.45, 4.55)

    mu_a = clamp(total_goals * share_a, 0.07, 4.95)
    mu_b = clamp(total_goals * (1.0 - share_a), 0.07, 4.95)
    return mu_a, mu_b


def factor_breakdown(
    team_a,
    team_b,
    ctx,
    *,
    state_a=None,
    state_b=None,
    profile_for,
    context_components_fn,
    effective_elo,
    attack_form_signal,
    defense_form_signal,
    fatigue_level,
    availability_level,
    discipline_trend,
    tactical_attack_signal,
    tactical_defense_signal,
    tactical_tempo_signal,
    recent_xg_for_signal,
    recent_xga_signal,
    recent_opponent_strength_signal,
):
    profile_a = profile_for(team_a)
    profile_b = profile_for(team_b)
    context_a = context_components_fn(team_a, profile_a, team_b, ctx, "A", state=state_a)
    context_b = context_components_fn(team_b, profile_b, team_a, ctx, "B", state=state_b)
    return {
        "elo_diff": effective_elo(team_a, state_a) - effective_elo(team_b, state_b),
        "fifa_strength_diff": profile_a.fifa_strength_index - profile_b.fifa_strength_index,
        "resource_diff": profile_a.resource_index - profile_b.resource_index,
        "heritage_diff": profile_a.heritage_index - profile_b.heritage_index,
        "historical_strength_diff": profile_a.history.strength_index - profile_b.history.strength_index,
        "historical_attack_diff": profile_a.history.attack_index - profile_b.history.attack_index,
        "historical_defense_diff": profile_a.history.defense_index - profile_b.history.defense_index,
        "competitive_history_diff": profile_a.history.competitive_index - profile_b.history.competitive_index,
        "world_cup_history_diff": profile_a.history.world_cup_index - profile_b.history.world_cup_index,
        "coach_diff": profile_a.coach_index - profile_b.coach_index,
        "importance": ctx.importance,
        "trajectory_diff": profile_a.trajectory_index - profile_b.trajectory_index,
        "attack_unit_diff": profile_a.squad.attack_unit - profile_b.squad.attack_unit,
        "midfield_diff": profile_a.squad.midfield_unit - profile_b.squad.midfield_unit,
        "defense_diff": profile_a.squad.defense_unit - profile_b.squad.defense_unit,
        "goalkeeper_diff": profile_a.squad.goalkeeper_unit - profile_b.squad.goalkeeper_unit,
        "bench_depth_diff": profile_a.squad.bench_depth - profile_b.squad.bench_depth,
        "recent_minutes_load_diff": profile_a.squad.recent_minutes_load - profile_b.squad.recent_minutes_load,
        "goalkeeper_minutes_load_diff": profile_a.squad.goalkeeper_minutes_load - profile_b.squad.goalkeeper_minutes_load,
        "bench_impact_diff": profile_a.squad.bench_impact - profile_b.squad.bench_impact,
        "experience_diff": profile_a.squad.player_experience - profile_b.squad.player_experience,
        "discipline_diff": profile_a.squad.discipline_index - profile_b.squad.discipline_index,
        "home_diff": context_a["home"] - context_b["home"],
        "injury_diff": context_a["injury"] - context_b["injury"],
        "travel_diff": context_a["travel"] - context_b["travel"],
        "morale_diff": context_a["morale"] - context_b["morale"],
        "cards_diff": context_a["cards"] - context_b["cards"],
        "group_pressure_diff": context_a["group_pressure"] - context_b["group_pressure"],
        "recent_form_diff": context_a["recent_form"] - context_b["recent_form"],
        "goalkeeper_context_diff": context_a["goalkeeper_context"] - context_b["goalkeeper_context"],
        "substitution_diff": context_a["substitutions"] - context_b["substitutions"],
        "market_move_diff": context_a["market_move"] - context_b["market_move"],
        "referee_profile_diff": context_a["referee"] - context_b["referee"],
        "market_prob_diff": (ctx.market_prob_a or 0.0) - (ctx.market_prob_b or 0.0),
        "market_draw_prob": ctx.market_prob_draw or 0.0,
        "market_total_line": ctx.market_total_line or 0.0,
        "attack_form_diff": attack_form_signal(state_a) - attack_form_signal(state_b),
        "defense_form_diff": defense_form_signal(state_a) - defense_form_signal(state_b),
        "recent_xg_for_adj_diff": recent_xg_for_signal(state_a) - recent_xg_for_signal(state_b),
        "recent_xga_adj_diff": recent_xga_signal(state_a) - recent_xga_signal(state_b),
        "recent_opponent_strength_diff": recent_opponent_strength_signal(state_a) - recent_opponent_strength_signal(state_b),
        "fatigue_diff": fatigue_level(state_a) - fatigue_level(state_b),
        "availability_diff": availability_level(state_a) - availability_level(state_b),
        "discipline_trend_diff": discipline_trend(state_a) - discipline_trend(state_b),
        "lineup_diff": context_a["lineup"] - context_b["lineup"],
        "lineup_strength_diff": context_a["lineup_strength"] - context_b["lineup_strength"],
        "lineup_attack_diff": context_a["lineup_attack"] - context_b["lineup_attack"],
        "lineup_defense_diff": context_a["lineup_defense"] - context_b["lineup_defense"],
        "lineup_goalkeeper_diff": context_a["lineup_goalkeeper"] - context_b["lineup_goalkeeper"],
        "tactical_attack_diff": tactical_attack_signal(state_a) - tactical_attack_signal(state_b),
        "tactical_defense_diff": tactical_defense_signal(state_a) - tactical_defense_signal(state_b),
        "tactical_tempo_diff": tactical_tempo_signal(state_a) - tactical_tempo_signal(state_b),
        "rivalry": context_a["rivalry"],
    }
