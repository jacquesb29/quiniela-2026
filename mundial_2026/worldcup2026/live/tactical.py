from __future__ import annotations


def tactical_signature_from_metrics(
    style_possession: float,
    style_verticality: float,
    style_pressure: float,
    style_chance_quality: float,
    style_tempo: float,
    style_attack_bias: float,
    style_defense_bias: float,
    sample_matches: int,
):
    if sample_matches <= 0:
        return "sin muestra suficiente"
    if style_possession >= 0.22 and style_pressure >= 0.14 and style_chance_quality >= -0.02:
        return "control territorial"
    if style_possession >= 0.22 and style_chance_quality < -0.08:
        return "control esteril"
    if style_possession <= -0.12 and style_verticality >= 0.12 and style_chance_quality >= 0.0:
        return "transicion vertical"
    if style_possession <= -0.18 and style_defense_bias >= 0.08 and style_attack_bias >= -0.02:
        return "bloque bajo y contra"
    if style_tempo >= 0.18 and style_pressure >= 0.05:
        return "ritmo alto"
    if abs(style_possession) < 0.12 and abs(style_verticality) < 0.12 and abs(style_pressure) < 0.12:
        return "perfil mixto equilibrado"
    return "perfil mixto"


def _stat_share(value: float, other: float, neutral: float = 0.5) -> float:
    total = value + other
    if total <= 0.0:
        return neutral
    return value / total


def live_signature_metrics(side: str, live_stats: dict, *, clamp):
    other = "b" if side == "a" else "a"
    shots = float(live_stats.get(f"shots_{side}", 0.0))
    shots_opp = float(live_stats.get(f"shots_{other}", 0.0))
    sot = float(live_stats.get(f"shots_on_target_{side}", 0.0))
    sot_opp = float(live_stats.get(f"shots_on_target_{other}", 0.0))
    poss = float(live_stats.get(f"possession_{side}", 50.0))
    corners = float(live_stats.get(f"corners_{side}", 0.0))
    corners_opp = float(live_stats.get(f"corners_{other}", 0.0))
    fouls = float(live_stats.get(f"fouls_{side}", 0.0))
    fouls_opp = float(live_stats.get(f"fouls_{other}", 0.0))
    yellows = float(live_stats.get(f"yellow_cards_{side}", 0.0))
    reds = float(live_stats.get(f"red_cards_{side}", 0.0))
    reds_opp = float(live_stats.get(f"red_cards_{other}", 0.0))
    xg = float(live_stats.get(f"xg_{side}", live_stats.get(f"xg_proxy_{side}", 0.0)))
    xg_opp = float(live_stats.get(f"xg_{other}", live_stats.get(f"xg_proxy_{other}", 0.0)))

    total_signal = shots + shots_opp + sot + sot_opp + corners + corners_opp + xg + xg_opp + fouls + fouls_opp + yellows
    if total_signal <= 0.0:
        return None

    poss_norm = clamp((poss - 50.0) / 25.0, -1.0, 1.0)
    shot_share = clamp((_stat_share(shots, shots_opp) - 0.5) * 2.0, -1.0, 1.0)
    sot_share = clamp((_stat_share(sot, sot_opp) - 0.5) * 2.0, -1.0, 1.0)
    corner_share = clamp((_stat_share(corners, corners_opp) - 0.5) * 2.0, -1.0, 1.0)
    xg_per_shot = xg / max(shots, 1.0)
    chance_quality = clamp((xg_per_shot - 0.11) / 0.09, -1.0, 1.0)
    verticality = clamp(0.48 * (-poss_norm) + 0.32 * chance_quality + 0.20 * shot_share, -1.0, 1.0)
    pressure = clamp(0.45 * shot_share + 0.30 * corner_share + 0.25 * sot_share, -1.0, 1.0)
    match_intensity = clamp(((shots + shots_opp) + 0.8 * (corners + corners_opp) + 3.0 * (xg + xg_opp)) / 24.0 - 1.0, -1.0, 1.0)
    tempo = clamp(match_intensity + 0.20 * pressure - 0.10 * clamp((fouls + fouls_opp) / 24.0, 0.0, 1.0), -1.0, 1.0)
    attack_bias = clamp(0.40 * pressure + 0.35 * chance_quality + 0.25 * verticality, -1.0, 1.0)
    card_swing = 1.0 if reds_opp > reds else -1.0 if reds > reds_opp else 0.0
    defense_bias = clamp(0.35 * poss_norm + 0.35 * pressure - 0.18 * tempo + 0.18 * card_swing, -1.0, 1.0)
    return {
        "style_possession": poss_norm,
        "style_verticality": verticality,
        "style_pressure": pressure,
        "style_chance_quality": chance_quality,
        "style_tempo": tempo,
        "style_attack_bias": attack_bias,
        "style_defense_bias": defense_bias,
    }


def update_tactical_signature_state(state: dict, metrics, *, clamp):
    if not metrics:
        return
    alpha = 0.28
    for key, value in metrics.items():
        state[key] = clamp((1.0 - alpha) * float(state.get(key, 0.0)) + alpha * float(value), -1.0, 1.0)
    state["tactical_sample_matches"] = int(state.get("tactical_sample_matches", 0)) + 1
    state["tactical_signature"] = tactical_signature_from_metrics(
        float(state.get("style_possession", 0.0)),
        float(state.get("style_verticality", 0.0)),
        float(state.get("style_pressure", 0.0)),
        float(state.get("style_chance_quality", 0.0)),
        float(state.get("style_tempo", 0.0)),
        float(state.get("style_attack_bias", 0.0)),
        float(state.get("style_defense_bias", 0.0)),
        int(state.get("tactical_sample_matches", 0)),
    )
