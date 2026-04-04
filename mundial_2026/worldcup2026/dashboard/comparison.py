from __future__ import annotations


def compare_entry_predictions(current_entries, previous_entries, *, dashboard_entry_key, pick_summary, projected_score_value):
    previous_map = {dashboard_entry_key(entry): entry for entry in previous_entries}
    movers = []
    score_changes = []
    label_changes = []
    for current in current_entries:
        previous = previous_map.get(dashboard_entry_key(current))
        if not previous:
            continue
        current_prediction = current["prediction"]
        previous_prediction = previous["prediction"]
        current_label, current_prob = pick_summary(current_prediction)
        previous_label, previous_prob = pick_summary(previous_prediction)
        delta = float(current_prob) - float(previous_prob)
        title = str(current.get("title", "Partido"))
        abs_delta = abs(delta)
        if abs_delta >= 0.005 or previous_label != current_label:
            movers.append(
                {
                    "title": title,
                    "previous_label": previous_label,
                    "previous_prob": float(previous_prob),
                    "current_label": current_label,
                    "current_prob": float(current_prob),
                    "delta": delta,
                    "abs_delta": abs_delta,
                }
            )
        previous_score = projected_score_value(previous_prediction)
        current_score = projected_score_value(current_prediction)
        if previous_score != current_score:
            score_changes.append(
                {
                    "title": title,
                    "previous_score": previous_score,
                    "current_score": current_score,
                }
            )
        if previous_label != current_label:
            label_changes.append(
                {
                    "title": title,
                    "previous_label": previous_label,
                    "current_label": current_label,
                }
            )
    movers.sort(key=lambda item: item["abs_delta"], reverse=True)
    return {
        "movers": movers[:6],
        "score_changes": score_changes[:6],
        "label_changes": label_changes[:6],
    }


def compare_bracket_payloads(current_bracket, previous_bracket):
    current_matches = current_bracket.get("matches", {}) if current_bracket else {}
    previous_matches = previous_bracket.get("matches", {}) if previous_bracket else {}
    stage_order = {"round32": 0, "round16": 1, "quarterfinal": 2, "semifinal": 3, "final": 4, "third_place": 5}

    def matchup_text(match):
        return f"{match.get('team_a', '?')} vs {match.get('team_b', '?')}"

    matchup_changes = []
    favorite_flips = []
    current_teams = set()
    previous_teams = set()

    for match_id, current in current_matches.items():
        current_teams.update(team for team in [current.get("team_a"), current.get("team_b")] if team)
        previous = previous_matches.get(match_id)
        if not previous:
            continue
        previous_teams.update(team for team in [previous.get("team_a"), previous.get("team_b")] if team)
        if current.get("team_a") != previous.get("team_a") or current.get("team_b") != previous.get("team_b"):
            matchup_changes.append(
                {
                    "match_id": match_id,
                    "title": current.get("title", match_id),
                    "stage": current.get("stage"),
                    "previous_matchup": matchup_text(previous),
                    "current_matchup": matchup_text(current),
                    "current_prob": float(current.get("matchup_prob", 0.0)),
                }
            )
        elif current.get("winner") != previous.get("winner"):
            favorite_flips.append(
                {
                    "match_id": match_id,
                    "title": current.get("title", match_id),
                    "stage": current.get("stage"),
                    "matchup": matchup_text(current),
                    "previous_winner": previous.get("winner"),
                    "current_winner": current.get("winner"),
                    "current_prob": float(current.get("winner_prob", 0.0)),
                }
            )

    for previous in previous_matches.values():
        previous_teams.update(team for team in [previous.get("team_a"), previous.get("team_b")] if team)

    matchup_changes.sort(
        key=lambda item: (stage_order.get(str(item.get("stage")), 99), -item["current_prob"], str(item["title"]))
    )
    favorite_flips.sort(
        key=lambda item: (stage_order.get(str(item.get("stage")), 99), -item["current_prob"], str(item["title"]))
    )

    return {
        "matchup_changes": matchup_changes[:8],
        "favorite_flips": favorite_flips[:6],
        "new_teams": sorted(current_teams - previous_teams),
        "dropped_teams": sorted(previous_teams - current_teams),
    }
