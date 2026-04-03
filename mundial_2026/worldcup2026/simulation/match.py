from __future__ import annotations


def sample_cards(
    teams,
    team_a,
    team_b,
    importance,
    *,
    state_a=None,
    state_b=None,
    profile_for,
    rivalry_intensity,
    fatigue_level,
    discipline_trend,
    poisson_sample,
    fast_random,
    clamp,
):
    profile_a = profile_for(teams[team_a])
    profile_b = profile_for(teams[team_b])
    rivalry = rivalry_intensity(teams[team_a], teams[team_b])

    yellow_lambda_a = clamp(
        0.75 + 7.0 * profile_a.squad.yellow_rate + 0.35 * importance + 0.60 * rivalry
        - 0.50 * profile_a.squad.discipline_index
        + 0.55 * fatigue_level(state_a)
        - 0.35 * discipline_trend(state_a),
        0.25,
        4.80,
    )
    yellow_lambda_b = clamp(
        0.75 + 7.0 * profile_b.squad.yellow_rate + 0.35 * importance + 0.60 * rivalry
        - 0.50 * profile_b.squad.discipline_index
        + 0.55 * fatigue_level(state_b)
        - 0.35 * discipline_trend(state_b),
        0.25,
        4.80,
    )
    red_prob_a = clamp(
        0.012 + 1.8 * profile_a.squad.red_rate + 0.028 * importance + 0.04 * rivalry
        - 0.02 * profile_a.squad.discipline_index
        + 0.025 * fatigue_level(state_a)
        - 0.018 * discipline_trend(state_a),
        0.003,
        0.20,
    )
    red_prob_b = clamp(
        0.012 + 1.8 * profile_b.squad.red_rate + 0.028 * importance + 0.04 * rivalry
        - 0.02 * profile_b.squad.discipline_index
        + 0.025 * fatigue_level(state_b)
        - 0.018 * discipline_trend(state_b),
        0.003,
        0.20,
    )

    yellows_a = poisson_sample(yellow_lambda_a)
    yellows_b = poisson_sample(yellow_lambda_b)
    reds_a = 1 if fast_random() < red_prob_a else 0
    reds_b = 1 if fast_random() < red_prob_b else 0
    return yellows_a, reds_a, yellows_b, reds_b


def penalty_shootout_summary(team_a, team_b, ctx, state_a, state_b, *, iterations=2400, simulate_penalty_shootout_fn):
    counts = {}
    wins_a = 0
    wins_b = 0
    total_a = 0
    total_b = 0
    starts_a = 0
    for index in range(iterations):
        a_starts = index % 2 == 0
        starts_a += 1 if a_starts else 0
        result = simulate_penalty_shootout_fn(team_a, team_b, ctx, state_a, state_b, a_starts=a_starts)
        counts[(result["score_a"], result["score_b"])] = counts.get((result["score_a"], result["score_b"]), 0) + 1
        total_a += result["score_a"]
        total_b += result["score_b"]
        if result["winner"] == team_a.name:
            wins_a += 1
        else:
            wins_b += 1
    top_scores = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
    return {
        "iterations": iterations,
        "win_a": wins_a / float(iterations),
        "win_b": wins_b / float(iterations),
        "avg_score_a": total_a / float(iterations),
        "avg_score_b": total_b / float(iterations),
        "a_starts_rate": starts_a / float(iterations),
        "top_scores": [(f"{score[0]}-{score[1]}", count / float(iterations)) for score, count in top_scores],
    }


def build_simulation_context(
    teams,
    states,
    team_a,
    team_b,
    stage,
    *,
    group_name=None,
    ensure_state,
    dynamic_injury_load,
    predictive_yellow_cards,
    stage_importance,
    random_choice,
    MatchContext,
):
    state_a = ensure_state(states, team_a)
    state_b = ensure_state(states, team_b)

    neutral = True
    home_team = None
    venue_country = None
    if stage == "group":
        if teams[team_a].is_host:
            neutral = False
            home_team = team_a
            venue_country = teams[team_a].host_country
        elif teams[team_b].is_host:
            neutral = False
            home_team = team_b
            venue_country = teams[team_b].host_country
    else:
        if teams[team_a].is_host:
            venue_country = teams[team_a].host_country
        elif teams[team_b].is_host:
            venue_country = teams[team_b].host_country

    weather_bucket = random_choice((0.03, 0.06, 0.09, 0.12))

    return MatchContext(
        neutral=neutral,
        home_team=home_team,
        venue_country=venue_country,
        rest_days_a=4 if stage == "group" else 5,
        rest_days_b=4 if stage == "group" else 5,
        injuries_a=dynamic_injury_load(teams[team_a], state_a),
        injuries_b=dynamic_injury_load(teams[team_b], state_b),
        altitude_m=1500 if venue_country == "Mexico" and stage == "group" else 0,
        travel_km_a=0.0 if teams[team_a].is_host else 3500.0,
        travel_km_b=0.0 if teams[team_b].is_host else 3500.0,
        knockout=stage != "group",
        morale_a=state_a["morale"],
        morale_b=state_b["morale"],
        yellow_cards_a=predictive_yellow_cards(state_a),
        yellow_cards_b=predictive_yellow_cards(state_b),
        red_suspensions_a=int(state_a["red_suspensions"]),
        red_suspensions_b=int(state_b["red_suspensions"]),
        group=group_name,
        group_points_a=int(state_a["group_points"]),
        group_points_b=int(state_b["group_points"]),
        group_goal_diff_a=int(state_a["group_goal_diff"]),
        group_goal_diff_b=int(state_b["group_goal_diff"]),
        group_matches_played_a=int(state_a["group_matches_played"]),
        group_matches_played_b=int(state_b["group_matches_played"]),
        weather_stress=weather_bucket,
        importance=stage_importance[stage],
    )


def sample_knockout_resolution(
    team_a,
    team_b,
    ctx,
    score_a,
    score_b,
    mu_a,
    mu_b,
    *,
    state_a=None,
    state_b=None,
    asdict,
    KnockoutResolution,
    extra_time_expected_goals,
    sample_score,
    simulate_penalty_shootout,
    penalties_context_state,
    fast_random,
):
    if score_a > score_b:
        return asdict(
            KnockoutResolution(
                winner=team_a.name,
                loser=team_b.name,
                score_a=score_a,
                score_b=score_b,
                extra_time_score_a=0,
                extra_time_score_b=0,
                went_extra_time=False,
                went_penalties=False,
                penalty_score_a=None,
                penalty_score_b=None,
            )
        )
    if score_b > score_a:
        return asdict(
            KnockoutResolution(
                winner=team_b.name,
                loser=team_a.name,
                score_a=score_a,
                score_b=score_b,
                extra_time_score_a=0,
                extra_time_score_b=0,
                went_extra_time=False,
                went_penalties=False,
                penalty_score_a=None,
                penalty_score_b=None,
            )
        )

    et_mu_a, et_mu_b = extra_time_expected_goals(mu_a, mu_b, state_a=state_a, state_b=state_b)
    et_score_a, et_score_b = sample_score(et_mu_a, et_mu_b, ctx)
    total_a = score_a + et_score_a
    total_b = score_b + et_score_b
    penalty_score_a = None
    penalty_score_b = None
    if et_score_a > et_score_b:
        winner = team_a.name
        loser = team_b.name
        went_penalties = False
    elif et_score_b > et_score_a:
        winner = team_b.name
        loser = team_a.name
        went_penalties = False
    else:
        shootout = simulate_penalty_shootout(
            team_a,
            team_b,
            ctx,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
            a_starts=fast_random() < 0.5,
        )
        winner = shootout["winner"]
        loser = team_b.name if winner == team_a.name else team_a.name
        went_penalties = True
        penalty_score_a = shootout["score_a"]
        penalty_score_b = shootout["score_b"]
    return asdict(
        KnockoutResolution(
            winner=winner,
            loser=loser,
            score_a=total_a,
            score_b=total_b,
            extra_time_score_a=et_score_a,
            extra_time_score_b=et_score_b,
            went_extra_time=True,
            went_penalties=went_penalties,
            penalty_score_a=penalty_score_a,
            penalty_score_b=penalty_score_b,
        )
    )


def update_simulation_state(
    teams,
    states,
    team_a,
    team_b,
    ctx,
    expected_goals_a,
    expected_goals_b,
    score_a,
    score_b,
    yellows_a,
    reds_a,
    yellows_b,
    reds_b,
    stage,
    *,
    winner=None,
    went_extra_time=False,
    went_penalties=False,
    live_stats=None,
    ensure_state,
    effective_elo,
    elo_delta_for_match,
    profile_for,
    live_signature_metrics,
    update_tactical_signature_state,
    clamp,
):
    state_a = ensure_state(states, team_a)
    state_b = ensure_state(states, team_b)
    effective_elo_a = effective_elo(teams[team_a], state_a)
    effective_elo_b = effective_elo(teams[team_b], state_b)
    home_edge = 0.0
    if not ctx.neutral and ctx.home_team == team_a:
        home_edge = 55.0
    elif not ctx.neutral and ctx.home_team == team_b:
        home_edge = -55.0

    knockout = stage != "group"
    if score_a > score_b:
        actual_result_a = 1.0
        actual_result_b = 0.0
    elif score_b > score_a:
        actual_result_a = 0.0
        actual_result_b = 1.0
    elif knockout and winner:
        actual_result_a = 0.75 if winner == team_a else 0.25
        actual_result_b = 1.0 - actual_result_a
    else:
        actual_result_a = 0.5
        actual_result_b = 0.5

    elo_delta_a, expected_result_a = elo_delta_for_match(
        elo_a=effective_elo_a,
        elo_b=effective_elo_b,
        actual_result_a=actual_result_a,
        importance=ctx.importance,
        goal_diff=score_a - score_b,
        home_edge=home_edge,
        clamp=clamp,
    )
    expected_result_b = 1.0 - expected_result_a
    elo_delta_b = -elo_delta_a
    state_a["elo_shift"] = clamp(state_a["elo_shift"] + elo_delta_a, -220.0, 220.0)
    state_b["elo_shift"] = clamp(state_b["elo_shift"] + elo_delta_b, -220.0, 220.0)

    for state, team_name, score_for, score_against, expected_for, expected_against, actual_result, expected_result, yellows, reds, rest_days, travel_km, injuries in (
        (state_a, team_a, score_a, score_b, expected_goals_a, expected_goals_b, actual_result_a, expected_result_a, yellows_a, reds_a, ctx.rest_days_a, ctx.travel_km_a, ctx.injuries_a),
        (state_b, team_b, score_b, score_a, expected_goals_b, expected_goals_a, actual_result_b, expected_result_b, yellows_b, reds_b, ctx.rest_days_b, ctx.travel_km_b, ctx.injuries_b),
    ):
        team_profile = profile_for(teams[team_name])
        attack_signal = clamp((score_for - expected_for) / 1.8, -1.0, 1.0)
        defense_signal = clamp((expected_against - score_against) / 1.8, -1.0, 1.0)
        result_signal = clamp(2.0 * (actual_result - expected_result), -1.0, 1.0)
        form_signal = clamp(0.48 * result_signal + 0.30 * attack_signal + 0.22 * defense_signal, -1.0, 1.0)

        state["recent_form"] = clamp(0.60 * state["recent_form"] + 0.40 * form_signal, -1.0, 1.0)
        state["attack_form"] = clamp(0.58 * state["attack_form"] + 0.42 * attack_signal, -1.0, 1.0)
        state["defense_form"] = clamp(0.58 * state["defense_form"] + 0.42 * defense_signal, -1.0, 1.0)
        morale_delta = clamp(0.08 * form_signal + 0.03 * (1 if actual_result > 0.5 else -1 if actual_result < 0.5 else 0), -0.18, 0.18)
        state["morale"] = clamp(0.72 * state["morale"] + morale_delta, -1.0, 1.0)

        fatigue_delta = (
            0.24
            + 0.06 * max(ctx.importance - 1.0, 0.0)
            + 0.05 * clamp(travel_km / 6000.0, 0.0, 2.0)
            + 0.05 * clamp(injuries, 0.0, 1.0)
            + 0.025 * (yellows + 2 * reds)
            + (0.18 if went_extra_time else 0.0)
            + (0.04 if went_penalties else 0.0)
            - 0.045 * clamp(rest_days, 2, 8)
        )
        state["fatigue"] = clamp(0.58 * state["fatigue"] + fatigue_delta, 0.0, 1.0)

        target_availability = (
            1.0
            - 0.50 * clamp(injuries, 0.0, 1.0)
            - 0.12 * reds
            - 0.03 * yellows
            - 0.10 * state["fatigue"]
            - (0.05 if went_extra_time else 0.0)
            - (0.02 if went_penalties else 0.0)
        )
        state["availability"] = clamp(0.74 * state["availability"] + 0.26 * target_availability, 0.40, 1.0)

        discipline_signal = clamp(
            0.10 * (team_profile.squad.discipline_index - 0.5) - 0.10 * yellows - 0.34 * reds,
            -1.0,
            0.4,
        )
        state["discipline_drift"] = clamp(0.68 * state["discipline_drift"] + 0.32 * discipline_signal, -1.0, 0.5)

    state_a["yellow_cards"] = clamp(state_a["yellow_cards"] + yellows_a, 0, 12)
    state_b["yellow_cards"] = clamp(state_b["yellow_cards"] + yellows_b, 0, 12)
    state_a["yellow_load"] = clamp(state_a["yellow_load"] * 0.55 + 0.45 * yellows_a + 0.70 * reds_a, 0.0, 6.0)
    state_b["yellow_load"] = clamp(state_b["yellow_load"] * 0.55 + 0.45 * yellows_b + 0.70 * reds_b, 0.0, 6.0)
    state_a["red_suspensions"] = clamp(reds_a, 0, 4)
    state_b["red_suspensions"] = clamp(reds_b, 0, 4)

    state_a["matches_played"] += 1
    state_b["matches_played"] += 1
    state_a["goals_for"] += score_a
    state_a["goals_against"] += score_b
    state_b["goals_for"] += score_b
    state_b["goals_against"] += score_a
    update_tactical_signature_state(state_a, live_signature_metrics("a", live_stats or {}))
    update_tactical_signature_state(state_b, live_signature_metrics("b", live_stats or {}))

    if stage == "group":
        state_a["group_matches_played"] += 1
        state_b["group_matches_played"] += 1
        state_a["group_goals_for"] += score_a
        state_b["group_goals_for"] += score_b
        state_a["group_goals_against"] += score_b
        state_b["group_goals_against"] += score_a
        state_a["group_goal_diff"] += score_a - score_b
        state_b["group_goal_diff"] += score_b - score_a
        if score_a > score_b:
            state_a["group_points"] += 3
        elif score_b > score_a:
            state_b["group_points"] += 3
        else:
            state_a["group_points"] += 1
            state_b["group_points"] += 1
        state_a["fair_play"] -= yellows_a + 3 * reds_a
        state_b["fair_play"] -= yellows_b + 3 * reds_b


def simulate_match_sample(
    teams,
    states,
    team_a,
    team_b,
    stage,
    *,
    group_name=None,
    build_simulation_context_fn,
    ensure_state,
    cached_simulation_expected_goals,
    simulation_state_signature,
    sample_score,
    sample_cards_fn,
    sample_knockout_resolution_fn,
    update_simulation_state_fn,
):
    ctx = build_simulation_context_fn(teams, states, team_a, team_b, stage, group_name=group_name)
    state_a = ensure_state(states, team_a)
    state_b = ensure_state(states, team_b)
    mu_a, mu_b = cached_simulation_expected_goals(
        team_a,
        team_b,
        ctx,
        simulation_state_signature(state_a),
        simulation_state_signature(state_b),
    )
    score_a, score_b = sample_score(mu_a, mu_b, ctx)
    yellows_a, reds_a, yellows_b, reds_b = sample_cards_fn(
        teams,
        team_a,
        team_b,
        ctx.importance,
        state_a=state_a,
        state_b=state_b,
    )

    winner = None
    loser = None
    went_extra_time = False
    went_penalties = False
    if stage != "group":
        resolution = sample_knockout_resolution_fn(
            teams[team_a],
            teams[team_b],
            ctx,
            score_a,
            score_b,
            mu_a,
            mu_b,
            state_a=state_a,
            state_b=state_b,
        )
        winner = resolution["winner"]
        loser = resolution["loser"]
        score_a = resolution["score_a"]
        score_b = resolution["score_b"]
        went_extra_time = resolution["went_extra_time"]
        went_penalties = resolution["went_penalties"]

    update_simulation_state_fn(
        teams,
        states,
        team_a,
        team_b,
        ctx,
        mu_a,
        mu_b,
        score_a,
        score_b,
        yellows_a,
        reds_a,
        yellows_b,
        reds_b,
        stage,
        winner=winner,
        went_extra_time=went_extra_time,
        went_penalties=went_penalties,
    )

    return {
        "team_a": team_a,
        "team_b": team_b,
        "score_a": score_a,
        "score_b": score_b,
        "winner": winner,
        "loser": loser,
        "went_extra_time": went_extra_time,
        "went_penalties": went_penalties,
    }
