from __future__ import annotations


def effective_elo(team, state=None, *, clamp, state_float):
    return clamp(team.elo + state_float(state, "elo_shift", 0.0), 1200.0, 2400.0)


def elo_expected_result(elo_a: float, elo_b: float, *, home_edge: float = 0.0) -> float:
    return 1.0 / (1.0 + 10.0 ** (-((elo_a - elo_b + home_edge) / 400.0)))


def elo_margin_multiplier(goal_diff: int, *, clamp) -> float:
    return 1.0 + 0.18 * clamp(abs(goal_diff), 0, 3)


def elo_rating_k(importance: float, *, clamp) -> float:
    return clamp(22.0 + 12.0 * (importance - 1.0), 18.0, 34.0)


def elo_delta_for_match(
    *,
    elo_a: float,
    elo_b: float,
    actual_result_a: float,
    importance: float,
    goal_diff: int,
    home_edge: float,
    clamp,
):
    expected_result_a = elo_expected_result(elo_a, elo_b, home_edge=home_edge)
    margin_multiplier = elo_margin_multiplier(goal_diff, clamp=clamp)
    rating_k = elo_rating_k(importance, clamp=clamp)
    delta_a = rating_k * margin_multiplier * (actual_result_a - expected_result_a)
    return delta_a, expected_result_a
