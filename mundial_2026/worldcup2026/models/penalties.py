from __future__ import annotations


def penalties_probability(
    team_a,
    team_b,
    state_a,
    state_b,
    *,
    profile_for,
    logistic,
    recent_form_signal,
    fatigue_level,
):
    profile_a = profile_for(team_a)
    profile_b = profile_for(team_b)
    edge = 0.80 * (profile_a.squad.goalkeeper_unit - profile_b.squad.goalkeeper_unit)
    edge += 0.40 * (profile_a.coach_index - profile_b.coach_index)
    edge += 0.20 * (profile_a.heritage_index - profile_b.heritage_index)
    edge += 0.14 * (profile_a.history.shootout_index - profile_b.history.shootout_index)
    edge += 0.15 * (profile_a.squad.player_experience - profile_b.squad.player_experience)
    edge += 0.15 * (state_a["morale"] - state_b["morale"])
    edge += 0.12 * (recent_form_signal(state_a) - recent_form_signal(state_b))
    edge -= 0.08 * (fatigue_level(state_a) - fatigue_level(state_b))
    return logistic(edge)


def penalty_conversion_probability(
    taker,
    keeper_team,
    ctx,
    taker_state,
    keeper_state,
    *,
    taker_first,
    sudden_death,
    trailing,
    round_number,
    profile_for,
    centered,
    recent_form_signal,
    fatigue_level,
    availability_level,
    clamp,
):
    taker_profile = profile_for(taker)
    keeper_profile = profile_for(keeper_team)
    rate = 0.74
    rate += 0.16 * centered(taker_profile.squad.finishing)
    rate += 0.05 * centered(taker_profile.squad.shot_creation)
    rate += 0.04 * centered(taker_profile.squad.player_experience)
    rate += 0.03 * centered(taker_profile.coach_index)
    rate += 0.03 * centered(taker_profile.heritage_index)
    rate += 0.02 * centered(taker_profile.history.shootout_index)
    rate += 0.05 * clamp(float(taker_state.get("morale", 0.0)), -1.0, 1.0)
    rate += 0.03 * recent_form_signal(taker_state)
    rate -= 0.06 * fatigue_level(taker_state)
    rate -= 0.06 * (1.0 - availability_level(taker_state))
    rate -= 0.10 * centered(keeper_profile.squad.goalkeeper_unit)
    rate -= 0.03 * centered(keeper_profile.coach_index)
    rate -= 0.02 * centered(keeper_profile.history.shootout_index)
    rate -= 0.05 * clamp(ctx.weather_stress, 0.0, 1.0)
    if taker_first:
        rate += 0.008
    if trailing:
        rate -= 0.020
    if sudden_death:
        rate -= 0.010
    if round_number >= 4:
        rate -= 0.012 * (round_number - 3)
    return clamp(rate, 0.46, 0.92)


def simulate_penalty_shootout(
    team_a,
    team_b,
    ctx,
    state_a,
    state_b,
    *,
    a_starts,
    penalty_conversion_probability_fn,
    penalties_probability_fn,
    fast_random,
):
    score_a = 0
    score_b = 0
    kicks_a = 0
    kicks_b = 0
    regulation_rounds = 5

    for round_number in range(1, regulation_rounds + 1):
        order = ("A", "B") if a_starts else ("B", "A")
        for shooter in order:
            sudden_death = False
            if shooter == "A":
                trailing = score_a < score_b
                prob = penalty_conversion_probability_fn(
                    team_a,
                    team_b,
                    ctx,
                    state_a,
                    state_b,
                    taker_first=a_starts,
                    sudden_death=sudden_death,
                    trailing=trailing,
                    round_number=round_number,
                )
                kicks_a += 1
                if fast_random() < prob:
                    score_a += 1
            else:
                trailing = score_b < score_a
                prob = penalty_conversion_probability_fn(
                    team_b,
                    team_a,
                    ctx,
                    state_b,
                    state_a,
                    taker_first=not a_starts,
                    sudden_death=sudden_death,
                    trailing=trailing,
                    round_number=round_number,
                )
                kicks_b += 1
                if fast_random() < prob:
                    score_b += 1

            remaining_a = regulation_rounds - kicks_a
            remaining_b = regulation_rounds - kicks_b
            if score_a > score_b + remaining_b:
                return {"winner": team_a.name, "score_a": score_a, "score_b": score_b, "a_starts": a_starts}
            if score_b > score_a + remaining_a:
                return {"winner": team_b.name, "score_a": score_a, "score_b": score_b, "a_starts": a_starts}

    sudden_round = 0
    while score_a == score_b and sudden_round < 12:
        sudden_round += 1
        order = ("A", "B") if a_starts else ("B", "A")
        round_scored_a = False
        round_scored_b = False
        for shooter in order:
            if shooter == "A":
                prob = penalty_conversion_probability_fn(
                    team_a,
                    team_b,
                    ctx,
                    state_a,
                    state_b,
                    taker_first=a_starts,
                    sudden_death=True,
                    trailing=score_a < score_b,
                    round_number=regulation_rounds + sudden_round,
                )
                if fast_random() < prob:
                    score_a += 1
                    round_scored_a = True
            else:
                prob = penalty_conversion_probability_fn(
                    team_b,
                    team_a,
                    ctx,
                    state_b,
                    state_a,
                    taker_first=not a_starts,
                    sudden_death=True,
                    trailing=score_b < score_a,
                    round_number=regulation_rounds + sudden_round,
                )
                if fast_random() < prob:
                    score_b += 1
                    round_scored_b = True
        if round_scored_a != round_scored_b:
            break

    if score_a == score_b:
        winner = team_a.name if fast_random() < penalties_probability_fn(team_a, team_b, state_a, state_b) else team_b.name
        if winner == team_a.name:
            score_a += 1
        else:
            score_b += 1
    else:
        winner = team_a.name if score_a > score_b else team_b.name

    return {"winner": winner, "score_a": score_a, "score_b": score_b, "a_starts": a_starts}
