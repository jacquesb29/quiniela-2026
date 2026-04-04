from __future__ import annotations


def live_game_state_adjustment(base_mu_a: float, base_mu_b: float, score_a: int, score_b: int, progress: float, phase: str, *, clamp):
    diff = score_a - score_b
    urgency = clamp(progress, 0.0, 1.0)
    lead_suppression = 0.08 if phase == "extra_time" else 0.12
    chase_boost = 0.12 if phase == "extra_time" else 0.18
    total_late_boost = 0.04 if phase == "extra_time" else 0.08

    mu_a = base_mu_a
    mu_b = base_mu_b
    if diff > 0:
        lead = clamp(diff, 0, 3)
        mu_a *= 1.0 - lead_suppression * urgency * lead
        mu_b *= 1.0 + chase_boost * urgency * lead
    elif diff < 0:
        lead = clamp(-diff, 0, 3)
        mu_b *= 1.0 - lead_suppression * urgency * lead
        mu_a *= 1.0 + chase_boost * urgency * lead

    if diff != 0:
        total_push = 1.0 + total_late_boost * urgency * min(abs(diff), 2)
        mu_a *= total_push
        mu_b *= total_push

    return clamp(mu_a, 0.01, 4.2), clamp(mu_b, 0.01, 4.2)


def live_stats_adjustment(base_total_mu: float, mu_a: float, mu_b: float, progress: float, phase: str, live_stats=None, *, clamp):
    if not live_stats:
        return mu_a, mu_b

    xg_a = float(live_stats.get("xg_a") or live_stats.get("xg_proxy_a") or 0.0)
    xg_b = float(live_stats.get("xg_b") or live_stats.get("xg_proxy_b") or 0.0)
    shots_a = float(live_stats.get("shots_a", 0.0))
    shots_b = float(live_stats.get("shots_b", 0.0))
    sot_a = float(live_stats.get("shots_on_target_a", 0.0))
    sot_b = float(live_stats.get("shots_on_target_b", 0.0))
    poss_a = float(live_stats.get("possession_a", 50.0))
    poss_b = float(live_stats.get("possession_b", 50.0))
    corners_a = float(live_stats.get("corners_a", 0.0))
    corners_b = float(live_stats.get("corners_b", 0.0))
    red_a = float(live_stats.get("red_cards_a", 0.0))
    red_b = float(live_stats.get("red_cards_b", 0.0))

    if (
        xg_a <= 0.0
        and xg_b <= 0.0
        and shots_a <= 0.0
        and shots_b <= 0.0
        and sot_a <= 0.0
        and sot_b <= 0.0
        and corners_a <= 0.0
        and corners_b <= 0.0
        and red_a <= 0.0
        and red_b <= 0.0
    ):
        return mu_a, mu_b

    scale = 0.18 if phase == "extra_time" else 0.28
    xg_diff = clamp(xg_a - xg_b, -2.0, 2.0)
    sot_diff = clamp(sot_a - sot_b, -8.0, 8.0)
    shots_diff = clamp(shots_a - shots_b, -15.0, 15.0)
    poss_diff = clamp(poss_a - poss_b, -40.0, 40.0)
    corners_diff = clamp(corners_a - corners_b, -10.0, 10.0)
    red_advantage_for_a = clamp(red_b - red_a, -2.0, 2.0)

    edge_signal = (
        0.42 * xg_diff
        + 0.06 * sot_diff
        + 0.015 * shots_diff
        + 0.004 * poss_diff
        + 0.012 * corners_diff
        + 0.48 * red_advantage_for_a
    )
    edge_signal *= 0.45 + 0.55 * clamp(progress, 0.0, 1.0)

    adjustment_a = clamp(1.0 + scale * edge_signal, 0.62, 1.55)
    adjustment_b = clamp(1.0 - scale * edge_signal, 0.62, 1.55)

    live_total_xg = xg_a + xg_b
    if live_total_xg <= 0.0:
        live_total_xg = float(live_stats.get("xg_proxy_a", 0.0)) + float(live_stats.get("xg_proxy_b", 0.0))
    expected_so_far = base_total_mu * clamp(progress, 0.15, 1.0)
    intensity_signal = clamp(live_total_xg - expected_so_far, -1.2, 1.2)
    tempo_adjustment = clamp(1.0 + (0.10 if phase == "extra_time" else 0.18) * intensity_signal, 0.72, 1.35)

    mu_a *= adjustment_a * tempo_adjustment
    mu_b *= adjustment_b * tempo_adjustment
    return clamp(mu_a, 0.01, 4.2), clamp(mu_b, 0.01, 4.2)


def apply_live_pattern_adjustment(mu_a: float, mu_b: float, patterns, phase: str, *, clamp):
    if not patterns:
        return mu_a, mu_b

    scale = 0.11 if phase == "extra_time" else 0.16
    side_a = patterns.get("a", {})
    side_b = patterns.get("b", {})
    tempo_bias = float(patterns.get("global_tempo_bias", 0.0))
    tempo_bias += 0.5 * (float(side_a.get("tempo_bias", 0.0)) + float(side_b.get("tempo_bias", 0.0)))

    attack_factor_a = clamp(1.0 + scale * float(side_a.get("attack_bias", 0.0)), 0.86, 1.18)
    attack_factor_b = clamp(1.0 + scale * float(side_b.get("attack_bias", 0.0)), 0.86, 1.18)
    defense_factor_a = clamp(1.0 - scale * float(side_b.get("defense_bias", 0.0)), 0.84, 1.18)
    defense_factor_b = clamp(1.0 - scale * float(side_a.get("defense_bias", 0.0)), 0.84, 1.18)
    tempo_factor = clamp(1.0 + scale * tempo_bias, 0.88, 1.14)

    mu_a *= attack_factor_a * defense_factor_a * tempo_factor
    mu_b *= attack_factor_b * defense_factor_b * tempo_factor
    return clamp(mu_a, 0.01, 4.2), clamp(mu_b, 0.01, 4.2)
