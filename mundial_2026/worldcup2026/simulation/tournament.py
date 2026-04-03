from __future__ import annotations


def standings_entry(teams, states, group_name, team_name, *, ensure_state):
    state = ensure_state(states, team_name)
    return {
        "team": team_name,
        "group": group_name,
        "points": state["group_points"],
        "goal_diff": state["group_goal_diff"],
        "goals_for": state["group_goals_for"],
        "fair_play": state["fair_play"],
        "elo": teams[team_name].elo,
    }


def sort_standings(entries):
    return sorted(
        entries,
        key=lambda entry: (
            entry["points"],
            entry["goal_diff"],
            entry["goals_for"],
            entry["fair_play"],
            entry["elo"],
        ),
        reverse=True,
    )


def simulate_group_stage(teams, groups, states, *, ensure_state, group_match_pairs, simulate_match_sample_fn, standings_entry_fn, sort_standings_fn):
    standings = {}
    for group_name, group_teams in groups.items():
        for team_name in group_teams:
            ensure_state(states, team_name)
        for index_a, index_b in group_match_pairs:
            team_a = group_teams[index_a]
            team_b = group_teams[index_b]
            simulate_match_sample_fn(teams, states, team_a, team_b, "group", group_name=group_name)
        entries = [standings_entry_fn(teams, states, group_name, team_name) for team_name in group_teams]
        standings[group_name] = sort_standings_fn(entries)
    return standings


def assign_third_place_slots(standings, winner_ranks, *, sort_standings_fn, r32_matches):
    third_place_entries = sort_standings_fn([table[2] for table in standings.values()])[:8]
    for rank, entry in enumerate(third_place_entries, start=1):
        entry["third_rank"] = rank

    third_slot_matches = [match for match in r32_matches if match["team_b"]["type"] == "third_place"]
    ordered_slots = sorted(
        third_slot_matches,
        key=lambda match: (
            len(match["team_b"]["allowed_groups"]),
            winner_ranks[match["team_a"]["group"]],
            match["id"],
        ),
    )

    best_assignment = {}
    best_score = -1.0

    def backtrack(index, used_groups, current, score):
        nonlocal best_assignment, best_score
        if index == len(ordered_slots):
            if score > best_score:
                best_score = score
                best_assignment = dict(current)
            return

        match = ordered_slots[index]
        winner_rank = winner_ranks[match["team_a"]["group"]]
        candidates = [
            entry for entry in third_place_entries
            if entry["group"] in match["team_b"]["allowed_groups"] and entry["group"] not in used_groups
        ]
        candidates.sort(key=lambda entry: entry["third_rank"], reverse=True)

        for candidate in candidates:
            current[match["id"]] = candidate["team"]
            used_groups.add(candidate["group"])
            candidate_score = (13 - winner_rank) * candidate["third_rank"]
            backtrack(index + 1, used_groups, current, score + candidate_score)
            used_groups.remove(candidate["group"])
            current.pop(match["id"], None)

    backtrack(0, set(), {}, 0.0)
    if len(best_assignment) != len(third_slot_matches):
        raise SystemExit("No se pudo asignar un cuadro valido para los mejores terceros.")
    return third_place_entries, best_assignment


def resolve_r32_team(slot, standings, third_assignments, match_id):
    if slot["type"] == "group_rank":
        return standings[slot["group"]][slot["rank"] - 1]["team"]
    if slot["type"] == "third_place":
        return third_assignments[match_id]
    raise SystemExit(f"Slot no soportado en {match_id}: {slot}")


def run_knockout_round(teams, states, stage, fixtures, previous_winners, *, simulate_match_sample_fn):
    winners = {}
    results = {}
    for match_id, left_id, right_id in fixtures:
        team_a = previous_winners[left_id]
        team_b = previous_winners[right_id]
        result = simulate_match_sample_fn(teams, states, team_a, team_b, stage)
        winners[match_id] = result["winner"]
        results[match_id] = result
    return winners, results


def simulate_tournament_iteration(
    teams,
    config,
    *,
    initial_payload=None,
    sample_playoff_placeholders,
    resolve_groups_for_iteration,
    initial_simulation_states,
    simulate_group_stage_fn,
    sort_standings_fn,
    assign_third_place_slots_fn,
    resolve_r32_team_fn,
    run_knockout_round_fn,
    r32_matches,
    knockout_matches,
    simulate_match_sample_fn,
):
    placeholders = sample_playoff_placeholders(teams)
    groups = resolve_groups_for_iteration(config, placeholders)
    participants = [team for members in groups.values() for team in members]
    states = initial_simulation_states(initial_payload)
    standings = simulate_group_stage_fn(teams, groups, states)

    winner_entries = sort_standings_fn([table[0] for table in standings.values()])
    winner_ranks = {entry["group"]: rank for rank, entry in enumerate(winner_entries, start=1)}
    third_entries, third_assignments = assign_third_place_slots_fn(standings, winner_ranks)

    stage_reached = {team: "group" for team in participants}
    qualified = {entry["team"] for table in standings.values() for entry in table[:2]}
    qualified.update(entry["team"] for entry in third_entries)
    bracket_matches = {}

    for team in qualified:
        stage_reached[team] = "round32"

    r32_winners = {}
    for match in r32_matches:
        team_a = resolve_r32_team_fn(match["team_a"], standings, third_assignments, match["id"])
        team_b = resolve_r32_team_fn(match["team_b"], standings, third_assignments, match["id"])
        result = simulate_match_sample_fn(teams, states, team_a, team_b, "round32")
        winner = result["winner"]
        r32_winners[match["id"]] = winner
        bracket_matches[match["id"]] = result
        stage_reached[winner] = "round16"

    round16_winners, round16_results = run_knockout_round_fn(teams, states, "round16", knockout_matches["round16"], r32_winners)
    bracket_matches.update(round16_results)
    for winner in round16_winners.values():
        stage_reached[winner] = "quarterfinal"

    quarter_winners, quarter_results = run_knockout_round_fn(teams, states, "quarterfinal", knockout_matches["quarterfinal"], round16_winners)
    bracket_matches.update(quarter_results)
    for winner in quarter_winners.values():
        stage_reached[winner] = "semifinal"

    semifinal_winners = {}
    semifinal_losers = []
    for match_id, left_id, right_id in knockout_matches["semifinal"]:
        team_a = quarter_winners[left_id]
        team_b = quarter_winners[right_id]
        result = simulate_match_sample_fn(teams, states, team_a, team_b, "semifinal")
        semifinal_winners[match_id] = result["winner"]
        semifinal_losers.append(result["loser"])
        bracket_matches[match_id] = result
    for winner in semifinal_winners.values():
        stage_reached[winner] = "final"

    third_place_result = simulate_match_sample_fn(teams, states, semifinal_losers[0], semifinal_losers[1], "third_place")
    bracket_matches["M104"] = third_place_result

    final_winners, final_results = run_knockout_round_fn(teams, states, "final", knockout_matches["final"], semifinal_winners)
    bracket_matches.update(final_results)
    champion = final_winners["M103"]
    stage_reached[champion] = "champion"

    return {
        "participants": participants,
        "standings": standings,
        "third_entries": third_entries,
        "stage_reached": stage_reached,
        "states": states,
        "champion": champion,
        "third_place": third_place_result["winner"],
        "fourth_place": third_place_result["loser"],
        "bracket_matches": bracket_matches,
    }


def simulate_tournament_batch(batch_size, seed, teams, config, initial_payload, *, seed_all_rng, empty_tournament_summary, ensure_state, simulate_tournament_iteration_fn):
    seed_all_rng(seed)
    summary = empty_tournament_summary(teams)
    for _ in range(batch_size):
        result = simulate_tournament_iteration_fn(teams, config, initial_payload=initial_payload)
        participants = set(result["participants"])
        for team_name in participants:
            stats = summary[team_name]
            state = ensure_state(result["states"], team_name)
            stats["appear"] += 1
            stats["avg_group_points"] += state["group_points"]
            stats["avg_goals_for"] += state["goals_for"]
            stats["avg_goals_against"] += state["goals_against"]

        for group_table in result["standings"].values():
            summary[group_table[0]["team"]]["group_winner"] += 1

        for team_name, stage in result["stage_reached"].items():
            stats = summary[team_name]
            if stage in {"round32", "round16", "quarterfinal", "semifinal", "final", "champion"}:
                stats["advance_group"] += 1
            if stage in {"round16", "quarterfinal", "semifinal", "final", "champion"}:
                stats["reach_round16"] += 1
            if stage in {"quarterfinal", "semifinal", "final", "champion"}:
                stats["reach_quarterfinal"] += 1
            if stage in {"semifinal", "final", "champion"}:
                stats["reach_semifinal"] += 1
            if stage in {"final", "champion"}:
                stats["reach_final"] += 1
            if stage == "champion":
                stats["champion"] += 1
        summary[result["third_place"]]["third_place"] += 1
        summary[result["fourth_place"]]["fourth_place"] += 1
    return summary


def project_bracket_batch(batch_size, seed, teams, config, initial_payload, *, seed_all_rng, empty_bracket_aggregate, bracket_match_order_fn, simulate_tournament_iteration_fn):
    seed_all_rng(seed)
    match_aggregate = empty_bracket_aggregate(bracket_match_order_fn())
    for _ in range(batch_size):
        result = simulate_tournament_iteration_fn(teams, config, initial_payload=initial_payload)
        for match_id, match_result in result["bracket_matches"].items():
            aggregate = match_aggregate[match_id]
            outcome_key = (match_result["team_a"], match_result["team_b"], match_result["winner"])
            aggregate["outcomes"][outcome_key] = aggregate["outcomes"].get(outcome_key, 0) + 1
            aggregate["winner"][match_result["winner"]] = aggregate["winner"].get(match_result["winner"], 0) + 1
            aggregate["went_extra_time"] += 1 if match_result.get("went_extra_time") else 0
            aggregate["went_penalties"] += 1 if match_result.get("went_penalties") else 0
            if match_result.get("went_penalties") and match_result.get("penalty_score_a") is not None and match_result.get("penalty_score_b") is not None:
                penalty_key = (int(match_result["penalty_score_a"]), int(match_result["penalty_score_b"]))
                aggregate["penalty_scores"][penalty_key] = aggregate["penalty_scores"].get(penalty_key, 0) + 1
    return match_aggregate


def bracket_match_order(*, r32_matches, knockout_matches):
    return [match["id"] for match in r32_matches] + [match_id for round_matches in knockout_matches.values() for match_id, _, _ in round_matches] + ["M104"]
