from __future__ import annotations


def resolved_uefa_path_winners(teams, *, uefa_playoff_paths):
    resolved = {}
    for placeholder, path in uefa_playoff_paths.items():
        candidates = list(path["semi_1"] + path["semi_2"])
        qualified = [name for name in candidates if name in teams and teams[name].status == "qualified"]
        pending = [name for name in candidates if name in teams and teams[name].status == "uefa_playoff"]
        if len(qualified) == 1 and not pending:
            resolved[placeholder] = qualified[0]
    return resolved


def resolved_fifa_path_winners(teams, *, fifa_playoff_paths):
    resolved = {}
    for placeholder, path in fifa_playoff_paths.items():
        candidates = [path["host"], *path["semi"]]
        qualified = [name for name in candidates if name in teams and teams[name].status == "qualified"]
        pending = [name for name in candidates if name in teams and teams[name].status == "fifa_playoff"]
        if len(qualified) == 1 and not pending:
            resolved[placeholder] = qualified[0]
    return resolved


def qualification_probabilities(
    teams,
    *,
    uefa_playoff_probabilities_fn,
    fifa_playoff_probabilities_fn,
):
    probabilities = {}
    uefa_probs = uefa_playoff_probabilities_fn(teams)
    fifa_probs = fifa_playoff_probabilities_fn(teams)
    for team in teams.values():
        if team.status == "qualified":
            probabilities[team.name] = 1.0
        elif team.status == "uefa_playoff":
            probabilities[team.name] = uefa_probs.get(team.name, 0.0)
        elif team.status == "fifa_playoff":
            probabilities[team.name] = fifa_probs.get(team.name, 0.0)
        else:
            probabilities[team.name] = 0.0
    return probabilities


def sample_uefa_path_winner(teams, semi_1, semi_2, final_host_path: str, *, sample_knockout_winner, MatchContextCls):
    finalist_1 = sample_knockout_winner(
        teams,
        semi_1[0],
        semi_1[1],
        MatchContextCls(neutral=False, home_team=semi_1[0], knockout=True, importance=1.2),
    )
    finalist_2 = sample_knockout_winner(
        teams,
        semi_2[0],
        semi_2[1],
        MatchContextCls(neutral=False, home_team=semi_2[0], knockout=True, importance=1.2),
    )
    final_host = finalist_1 if final_host_path == "semi_1" else finalist_2
    return sample_knockout_winner(
        teams,
        finalist_1,
        finalist_2,
        MatchContextCls(neutral=False, home_team=final_host, knockout=True, importance=1.25),
    )


def sample_playoff_placeholders(
    teams,
    *,
    resolved_uefa_path_winners_fn,
    resolved_fifa_path_winners_fn,
    sample_uefa_path_winner_fn,
    sample_knockout_winner,
    MatchContextCls,
):
    resolved = resolved_uefa_path_winners_fn(teams)
    resolved_fifa = resolved_fifa_path_winners_fn(teams)
    return {
        "UEFA_A": resolved.get("UEFA_A")
        or sample_uefa_path_winner_fn(
            teams,
            ("Italy", "Northern Ireland"),
            ("Wales", "Bosnia and Herzegovina"),
            "semi_2",
        ),
        "UEFA_B": resolved.get("UEFA_B")
        or sample_uefa_path_winner_fn(
            teams,
            ("Ukraine", "Sweden"),
            ("Poland", "Albania"),
            "semi_1",
        ),
        "UEFA_C": resolved.get("UEFA_C")
        or sample_uefa_path_winner_fn(
            teams,
            ("Turkey", "Romania"),
            ("Slovakia", "Kosovo"),
            "semi_2",
        ),
        "UEFA_D": resolved.get("UEFA_D")
        or sample_uefa_path_winner_fn(
            teams,
            ("Denmark", "North Macedonia"),
            ("Czech Republic", "Republic of Ireland"),
            "semi_2",
        ),
        "FIFA_1": resolved_fifa.get("FIFA_1")
        or sample_knockout_winner(
            teams,
            "Dem. Rep. of Congo",
            sample_knockout_winner(
                teams,
                "Jamaica",
                "New Caledonia",
                MatchContextCls(neutral=True, venue_country="Mexico", knockout=True, importance=1.2),
            ),
            MatchContextCls(neutral=True, venue_country="Mexico", knockout=True, importance=1.25),
        ),
        "FIFA_2": resolved_fifa.get("FIFA_2")
        or sample_knockout_winner(
            teams,
            "Iraq",
            sample_knockout_winner(
                teams,
                "Bolivia",
                "Suriname",
                MatchContextCls(neutral=True, venue_country="Mexico", knockout=True, importance=1.2),
            ),
            MatchContextCls(neutral=True, venue_country="Mexico", knockout=True, importance=1.25),
        ),
    }
