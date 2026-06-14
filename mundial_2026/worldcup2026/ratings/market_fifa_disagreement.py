"""Discrepancia Elo / FIFA-implied / mercado por partido (F2.2).

Combina, por partido, el Elo base, el FIFA-implied Elo, el staleness por equipo
(F2.1) y el mercado (F1, si existe) para señalar partidos donde el rating base es
riesgoso. SOLO diagnostica: NO cambia picks ni predicciones, NO toca el modelo,
pesos, lambdas, metodología ni Penca, NO aplica ningún ajuste.

Reglas: sin mercado no se inventa market_pick; sin FIFA no se inventa
fifa_implied; si Elo contradice FIFA y mercado a la vez ⇒ severidad fuerte.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional

from .staleness import T_HIGH

WINNER_EVEN_ELO = 25.0   # |elo_diff| <= 25 -> "even" (sin favorito claro)

SEVERITY_STRONG = "strong"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ACTION_DOMINATE = "elo_domina"
ACTION_SHRINK_FIFA = "shrink_fifa"
ACTION_SHRINK_FIFA_MARKET = "shrink_fifa_market"


def _num(row: Mapping, key: str) -> Optional[float]:
    value = row.get(key) if isinstance(row, Mapping) else getattr(row, key, None)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def winner_from_diff(diff: Optional[float], *, even_elo: float = WINNER_EVEN_ELO) -> str:
    if diff is None:
        return ""
    if diff > even_elo:
        return "home"
    if diff < -even_elo:
        return "away"
    return "even"


def build_match_disagreement_row(
    *,
    match_id: str,
    team_a: str,
    team_b: str,
    assess_a: Mapping,
    assess_b: Mapping,
    market_pick: Optional[str] = None,
    model_pick: Optional[str] = None,
    market_gap_status: Optional[str] = None,
    final_market_decision: Optional[str] = None,
    t_high: float = T_HIGH,
    even_elo: float = WINNER_EVEN_ELO,
) -> Dict[str, object]:
    elo_a = _num(assess_a, "elo")
    elo_b = _num(assess_b, "elo")
    fifa_imp_a = _num(assess_a, "fifa_implied_elo")
    fifa_imp_b = _num(assess_b, "fifa_implied_elo")
    stale_a = _num(assess_a, "elo_staleness_score") or 0.0
    stale_b = _num(assess_b, "elo_staleness_score") or 0.0

    elo_diff = (elo_a - elo_b) if (elo_a is not None and elo_b is not None) else None
    fifa_diff = (fifa_imp_a - fifa_imp_b) if (fifa_imp_a is not None and fifa_imp_b is not None) else None

    elo_winner = winner_from_diff(elo_diff, even_elo=even_elo)
    fifa_winner = winner_from_diff(fifa_diff, even_elo=even_elo)

    market_pick = (market_pick or "").strip() or None
    has_market = (market_gap_status == "calculado") and market_pick is not None

    # elo_vs_fifa_gap numérico (escala Elo); categóricos para mercado.
    elo_vs_fifa_gap = (elo_diff - fifa_diff) if (elo_diff is not None and fifa_diff is not None) else None

    def _cat_vs_market(winner: str) -> str:
        if not has_market:
            return "sin_mercado"
        if winner in ("home", "away") and winner != market_pick:
            return "contradice"
        return "alineado"

    elo_vs_market = _cat_vs_market(elo_winner)
    fifa_vs_market = _cat_vs_market(fifa_winner)

    elo_fifa_disagree = elo_winner in ("home", "away") and fifa_winner in ("home", "away") and elo_winner != fifa_winner
    elo_market_contradict = has_market and elo_winner in ("home", "away") and elo_winner != market_pick
    fifa_market_contradict = has_market and fifa_winner in ("home", "away") and fifa_winner != market_pick
    max_staleness = max(stale_a, stale_b)
    high_staleness = max_staleness >= t_high

    if elo_fifa_disagree and elo_market_contradict:
        severity = SEVERITY_STRONG
    elif elo_fifa_disagree and high_staleness:
        severity = SEVERITY_STRONG
    elif elo_fifa_disagree or elo_market_contradict or high_staleness:
        severity = SEVERITY_MEDIUM
    else:
        severity = SEVERITY_LOW

    if severity == SEVERITY_STRONG:
        action = ACTION_SHRINK_FIFA_MARKET if has_market else ACTION_SHRINK_FIFA
    elif severity == SEVERITY_MEDIUM:
        action = ACTION_SHRINK_FIFA
    else:
        action = ACTION_DOMINATE

    warnings: List[str] = []
    if fifa_imp_a is None or fifa_imp_b is None:
        warnings.append("sin FIFA en uno o ambos equipos: gap FIFA parcial")
    if not has_market:
        warnings.append("sin mercado: no se compara contra mercado")
    if elo_fifa_disagree:
        warnings.append("Elo contradice FIFA en el ganador")
    if elo_market_contradict:
        warnings.append("Elo contradice mercado en el ganador")
    if fifa_market_contradict:
        warnings.append("FIFA contradice mercado en el ganador")
    if high_staleness:
        warnings.append(f"staleness alto (max={round(max_staleness, 3)})")

    return {
        "match_id": match_id,
        "team_a": team_a,
        "team_b": team_b,
        "elo_a": elo_a if elo_a is not None else "",
        "elo_b": elo_b if elo_b is not None else "",
        "elo_diff": round(elo_diff, 3) if elo_diff is not None else "",
        "fifa_implied_elo_a": round(fifa_imp_a, 3) if fifa_imp_a is not None else "",
        "fifa_implied_elo_b": round(fifa_imp_b, 3) if fifa_imp_b is not None else "",
        "fifa_implied_elo_diff": round(fifa_diff, 3) if fifa_diff is not None else "",
        "staleness_a": round(stale_a, 4),
        "staleness_b": round(stale_b, 4),
        "elo_implied_winner": elo_winner,
        "fifa_implied_winner": fifa_winner,
        "market_pick": market_pick if has_market else "",
        "model_pick": (model_pick or "") if has_market else "",
        "final_market_decision": (final_market_decision or "") if has_market else "",
        "elo_vs_fifa_gap": round(elo_vs_fifa_gap, 3) if elo_vs_fifa_gap is not None else "",
        "elo_vs_market_gap": elo_vs_market,
        "fifa_vs_market_gap": fifa_vs_market,
        "contradicts_market": bool(elo_market_contradict),
        "disagreement_severity": severity,
        "recommended_action": action,
        "source_status": "mercado_disponible" if has_market else "sin_mercado",
        "warnings": ";".join(warnings),
    }


DISAGREEMENT_COLUMNS = (
    "match_id", "team_a", "team_b", "elo_a", "elo_b", "elo_diff",
    "fifa_implied_elo_a", "fifa_implied_elo_b", "fifa_implied_elo_diff",
    "staleness_a", "staleness_b", "elo_implied_winner", "fifa_implied_winner",
    "market_pick", "model_pick", "final_market_decision",
    "elo_vs_fifa_gap", "elo_vs_market_gap", "fifa_vs_market_gap",
    "contradicts_market", "disagreement_severity", "recommended_action",
    "source_status", "warnings",
)


__all__ = [
    "WINNER_EVEN_ELO",
    "SEVERITY_STRONG", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "DISAGREEMENT_COLUMNS",
    "winner_from_diff",
    "build_match_disagreement_row",
]
