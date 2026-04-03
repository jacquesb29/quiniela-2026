R32_MATCHES = [
    {"id": "M73", "team_a": {"type": "group_rank", "group": "A", "rank": 2}, "team_b": {"type": "group_rank", "group": "B", "rank": 2}},
    {"id": "M74", "team_a": {"type": "group_rank", "group": "E", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["A", "B", "C", "D", "F"]}},
    {"id": "M75", "team_a": {"type": "group_rank", "group": "F", "rank": 1}, "team_b": {"type": "group_rank", "group": "C", "rank": 2}},
    {"id": "M76", "team_a": {"type": "group_rank", "group": "C", "rank": 1}, "team_b": {"type": "group_rank", "group": "F", "rank": 2}},
    {"id": "M77", "team_a": {"type": "group_rank", "group": "I", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["C", "D", "F", "G", "H"]}},
    {"id": "M78", "team_a": {"type": "group_rank", "group": "E", "rank": 2}, "team_b": {"type": "group_rank", "group": "I", "rank": 2}},
    {"id": "M79", "team_a": {"type": "group_rank", "group": "A", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["C", "E", "F", "H", "I"]}},
    {"id": "M80", "team_a": {"type": "group_rank", "group": "L", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["E", "H", "I", "J", "K"]}},
    {"id": "M81", "team_a": {"type": "group_rank", "group": "D", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["B", "E", "F", "I", "J"]}},
    {"id": "M82", "team_a": {"type": "group_rank", "group": "G", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["A", "E", "H", "I", "J"]}},
    {"id": "M83", "team_a": {"type": "group_rank", "group": "K", "rank": 2}, "team_b": {"type": "group_rank", "group": "L", "rank": 2}},
    {"id": "M84", "team_a": {"type": "group_rank", "group": "H", "rank": 1}, "team_b": {"type": "group_rank", "group": "J", "rank": 2}},
    {"id": "M85", "team_a": {"type": "group_rank", "group": "B", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["E", "F", "G", "I", "J"]}},
    {"id": "M86", "team_a": {"type": "group_rank", "group": "J", "rank": 1}, "team_b": {"type": "group_rank", "group": "H", "rank": 2}},
    {"id": "M87", "team_a": {"type": "group_rank", "group": "K", "rank": 1}, "team_b": {"type": "third_place", "allowed_groups": ["D", "E", "I", "J", "L"]}},
    {"id": "M88", "team_a": {"type": "group_rank", "group": "D", "rank": 2}, "team_b": {"type": "group_rank", "group": "G", "rank": 2}},
]

KNOCKOUT_MATCHES = {
    "round16": [
        ("M89", "M73", "M74"),
        ("M90", "M75", "M76"),
        ("M91", "M77", "M78"),
        ("M92", "M79", "M80"),
        ("M93", "M81", "M82"),
        ("M94", "M83", "M84"),
        ("M95", "M85", "M86"),
        ("M96", "M87", "M88"),
    ],
    "quarterfinal": [
        ("M97", "M89", "M90"),
        ("M98", "M91", "M92"),
        ("M99", "M93", "M94"),
        ("M100", "M95", "M96"),
    ],
    "semifinal": [
        ("M101", "M97", "M98"),
        ("M102", "M99", "M100"),
    ],
    "final": [
        ("M103", "M101", "M102"),
    ],
}

WINNER_NEXT_MATCH = {
    source: match_id
    for round_matches in KNOCKOUT_MATCHES.values()
    for match_id, left_source, right_source in round_matches
    for source in (left_source, right_source)
}

LOSER_NEXT_MATCH = {
    "M101": "M104",
    "M102": "M104",
}

BRACKET_MATCH_TITLES = {
    "M73": "Dieciseisavos 1",
    "M74": "Dieciseisavos 2",
    "M75": "Dieciseisavos 3",
    "M76": "Dieciseisavos 4",
    "M77": "Dieciseisavos 5",
    "M78": "Dieciseisavos 6",
    "M79": "Dieciseisavos 7",
    "M80": "Dieciseisavos 8",
    "M81": "Dieciseisavos 9",
    "M82": "Dieciseisavos 10",
    "M83": "Dieciseisavos 11",
    "M84": "Dieciseisavos 12",
    "M85": "Dieciseisavos 13",
    "M86": "Dieciseisavos 14",
    "M87": "Dieciseisavos 15",
    "M88": "Dieciseisavos 16",
    "M89": "Octavos 1",
    "M90": "Octavos 2",
    "M91": "Octavos 3",
    "M92": "Octavos 4",
    "M93": "Octavos 5",
    "M94": "Octavos 6",
    "M95": "Octavos 7",
    "M96": "Octavos 8",
    "M97": "Cuartos 1",
    "M98": "Cuartos 2",
    "M99": "Cuartos 3",
    "M100": "Cuartos 4",
    "M101": "Semifinal 1",
    "M102": "Semifinal 2",
    "M103": "Final",
    "M104": "Tercer puesto",
}
