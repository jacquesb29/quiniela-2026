from __future__ import annotations


def stat_share(value: float, other: float, neutral: float = 0.5) -> float:
    total = value + other
    if total <= 0.0:
        return neutral
    return value / total


def format_pattern_signal(label: str, value: float, integer: bool = False, suffix: str = "") -> str:
    if integer:
        return f"{label} {int(round(value))}{suffix}"
    return f"{label} {value:.2f}{suffix}"


def derive_team_live_pattern(side: str, live_stats: dict, progress: float, score_for: int, score_against: int, *, clamp):
    other = "b" if side == "a" else "a"
    shots = float(live_stats.get(f"shots_{side}", 0.0))
    shots_opp = float(live_stats.get(f"shots_{other}", 0.0))
    sot = float(live_stats.get(f"shots_on_target_{side}", 0.0))
    sot_opp = float(live_stats.get(f"shots_on_target_{other}", 0.0))
    poss = float(live_stats.get(f"possession_{side}", 50.0))
    corners = float(live_stats.get(f"corners_{side}", 0.0))
    corners_opp = float(live_stats.get(f"corners_{other}", 0.0))
    fouls = float(live_stats.get(f"fouls_{side}", 0.0))
    yellows = float(live_stats.get(f"yellow_cards_{side}", 0.0))
    reds = float(live_stats.get(f"red_cards_{side}", 0.0))
    reds_opp = float(live_stats.get(f"red_cards_{other}", 0.0))
    xg = float(live_stats.get(f"xg_{side}", live_stats.get(f"xg_proxy_{side}", 0.0)))
    xg_opp = float(live_stats.get(f"xg_{other}", live_stats.get(f"xg_proxy_{other}", 0.0)))

    shot_share = stat_share(shots, shots_opp)
    sot_share = stat_share(sot, sot_opp)
    xg_share = stat_share(xg, xg_opp)
    corner_share = stat_share(corners, corners_opp)
    xg_per_shot = xg / max(shots, 1.0)
    score_diff = score_for - score_against

    primary = "sin patron dominante claro"
    secondary = "ritmo equilibrado"
    attack_bias = 0.0
    defense_bias = 0.0
    tempo_bias = 0.0

    if reds > reds_opp:
        primary = "inferioridad numerica"
        secondary = "resistencia y repliegue"
        attack_bias = -0.18
        defense_bias = -0.06
        tempo_bias = -0.03
    elif score_diff > 0 and poss <= 45.0 and shot_share <= 0.46:
        primary = "bloque bajo y contra"
        secondary = "protege la ventaja"
        attack_bias = -0.03
        defense_bias = 0.10
        tempo_bias = -0.08
    elif score_diff < 0 and shot_share >= 0.57 and corner_share >= 0.56:
        primary = "asedio del empate"
        secondary = "empuja la ultima linea"
        attack_bias = 0.12
        defense_bias = -0.01
        tempo_bias = 0.10
    elif poss >= 58.0 and shot_share >= 0.57 and (xg_share >= 0.56 or sot_share >= 0.56):
        if progress >= 0.30 and corner_share >= 0.55:
            primary = "dominio territorial"
            secondary = "asedio sostenido"
            attack_bias = 0.13
            defense_bias = 0.05
            tempo_bias = 0.07
        else:
            primary = "control con llegada"
            secondary = "empuja al rival"
            attack_bias = 0.09
            defense_bias = 0.03
            tempo_bias = 0.03
    elif poss >= 58.0 and xg_share <= 0.48 and sot <= max(1.0, sot_opp):
        primary = "control esteril"
        secondary = "maneja la pelota pero llega poco"
        attack_bias = -0.06
        defense_bias = 0.02
        tempo_bias = -0.05
    elif poss <= 46.0 and (xg_per_shot >= 0.12 or xg_share >= 0.50) and sot_share >= 0.45:
        primary = "transicion vertical"
        secondary = "amenaza al espacio"
        attack_bias = 0.09
        defense_bias = 0.00
        tempo_bias = 0.03
    elif xg <= 0.15 and shots <= 3.0 and progress >= 0.30:
        primary = "poca amenaza"
        secondary = "le cuesta progresar"
        attack_bias = -0.12
        defense_bias = -0.01
        tempo_bias = -0.04
    elif fouls + yellows >= 8.0 and shots <= 5.0:
        primary = "presion fisica"
        secondary = "corta el ritmo"
        attack_bias = -0.04
        defense_bias = 0.03
        tempo_bias = -0.06

    signals = []
    if abs(poss - 50.0) >= 6.0:
        signals.append(format_pattern_signal("posesion", poss, suffix="%"))
    if shots > 0.0:
        signals.append(format_pattern_signal("tiros", shots, integer=True))
    if sot > 0.0:
        signals.append(format_pattern_signal("al arco", sot, integer=True))
    if xg > 0.0:
        signals.append(format_pattern_signal("xG live", xg))
    if corners >= 3.0:
        signals.append(format_pattern_signal("corners", corners, integer=True))
    if reds > 0.0:
        signals.append(format_pattern_signal("rojas", reds, integer=True))
    if not signals:
        signals.append("sin señales en vivo suficientes")

    return {
        "primary": primary,
        "secondary": secondary,
        "summary": f"{primary} | {secondary}",
        "attack_bias": attack_bias,
        "defense_bias": defense_bias,
        "tempo_bias": tempo_bias,
        "signals": signals[:4],
    }


def detect_live_play_patterns(live_stats, progress: float, phase: str, score_a: int, score_b: int, *, clamp):
    if not live_stats:
        return None
    total_signal = sum(
        float(live_stats.get(key, 0.0))
        for key in (
            "shots_a",
            "shots_b",
            "shots_on_target_a",
            "shots_on_target_b",
            "corners_a",
            "corners_b",
            "red_cards_a",
            "red_cards_b",
            "yellow_cards_a",
            "yellow_cards_b",
        )
    )
    total_xg = float(live_stats.get("xg_a", live_stats.get("xg_proxy_a", 0.0))) + float(
        live_stats.get("xg_b", live_stats.get("xg_proxy_b", 0.0))
    )
    if total_signal <= 0.0 and total_xg <= 0.0:
        return None

    side_a = derive_team_live_pattern("a", live_stats, progress, score_a, score_b, clamp=clamp)
    side_b = derive_team_live_pattern("b", live_stats, progress, score_b, score_a, clamp=clamp)

    shots_total = float(live_stats.get("shots_a", 0.0)) + float(live_stats.get("shots_b", 0.0))
    sot_total = float(live_stats.get("shots_on_target_a", 0.0)) + float(live_stats.get("shots_on_target_b", 0.0))
    fouls_total = float(live_stats.get("fouls_a", 0.0)) + float(live_stats.get("fouls_b", 0.0))
    yellows_total = float(live_stats.get("yellow_cards_a", 0.0)) + float(live_stats.get("yellow_cards_b", 0.0))
    red_total = float(live_stats.get("red_cards_a", 0.0)) + float(live_stats.get("red_cards_b", 0.0))
    poss_gap = abs(float(live_stats.get("possession_a", 50.0)) - float(live_stats.get("possession_b", 50.0)))

    if red_total > 0.0 and shots_total >= 10.0:
        tempo_label = "partido roto"
        global_tempo_bias = 0.08
    elif total_xg >= 1.6 or shots_total >= 18.0 or sot_total >= 7.0:
        tempo_label = "ida y vuelta"
        global_tempo_bias = 0.07
    elif (fouls_total >= 22.0 or yellows_total >= 5.0) and total_xg <= 1.0:
        tempo_label = "trabado y cortado"
        global_tempo_bias = -0.08
    elif poss_gap >= 14.0 and shots_total >= 8.0:
        tempo_label = "control territorial"
        global_tempo_bias = -0.01
    elif phase == "extra_time":
        tempo_label = "prorroga de desgaste"
        global_tempo_bias = -0.03
    else:
        tempo_label = "ritmo equilibrado"
        global_tempo_bias = 0.0

    return {
        "a": side_a,
        "b": side_b,
        "tempo_label": tempo_label,
        "global_tempo_bias": global_tempo_bias,
    }
