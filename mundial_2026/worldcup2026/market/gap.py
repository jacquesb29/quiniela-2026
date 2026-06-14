"""Comparación modelo vs mercado (F1.3).

Lógica pura y determinista: calcula gaps entre la predicción del modelo (probabilidades
1X2 y lambdas) y el mercado ya convertido sin vig (`MarketImplied`/fila CSV). NO integra
odds al modelo, NO cambia picks, NO toca pesos/lambdas/metodología/Penca.

Convención de alineación: `model_pred.prob_a/lambda_a` = lado HOME del mercado
(`p_home/market_lambda_home`), y `prob_b/lambda_b` = lado AWAY. El runner garantiza que
el primer equipo del `match_id` sea el lado home del mercado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

OUTCOMES: Tuple[str, str, str] = ("home", "draw", "away")

SEVERITY_NONE = "none"
SEVERITY_MILD = "mild"
SEVERITY_STRONG = "strong"

STATUS_CALCULADO = "calculado"
STATUS_SIN_MUESTRA = "sin_muestra"


@dataclass(frozen=True)
class GapReport:
    match_id: str
    model_pick: Optional[str]
    market_pick: Optional[str]
    model_prob_a: Optional[float]
    model_prob_draw: Optional[float]
    model_prob_b: Optional[float]
    market_prob_a: Optional[float]
    market_prob_draw: Optional[float]
    market_prob_b: Optional[float]
    gap_1x2_home: Optional[float]
    gap_1x2_draw: Optional[float]
    gap_1x2_away: Optional[float]
    gap_1x2_total_variation: Optional[float]
    model_total_goals: Optional[float]
    market_total_goals: Optional[float]
    gap_total_goals: Optional[float]
    model_supremacy: Optional[float]
    market_supremacy: Optional[float]
    gap_supremacy: Optional[float]
    model_lambda_a: Optional[float]
    model_lambda_b: Optional[float]
    market_lambda_home: Optional[float]
    market_lambda_away: Optional[float]
    gap_lambda_home: Optional[float]
    gap_lambda_away: Optional[float]
    contradicts_market: bool
    contradiction_severity: str
    gap_status: str
    warnings: Tuple[str, ...]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def total_variation_distance(p: Mapping[str, float], q: Mapping[str, float]) -> float:
    return 0.5 * sum(abs(float(p[k]) - float(q[k])) for k in OUTCOMES)


def argmax_outcome(prob_home: float, prob_draw: float, prob_away: float) -> str:
    probs = {"home": prob_home, "draw": prob_draw, "away": prob_away}
    return max(OUTCOMES, key=lambda k: probs[k])


def classify_severity(tv: Optional[float], tv_mild: float, tv_strong: float) -> str:
    if tv is None:
        return SEVERITY_NONE
    if tv >= tv_strong:
        return SEVERITY_STRONG
    if tv >= tv_mild:
        return SEVERITY_MILD
    return SEVERITY_NONE


def _f(value: object) -> Optional[float]:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return (a - b) if (a is not None and b is not None) else None


# --------------------------------------------------------------------------- #
# Núcleo
# --------------------------------------------------------------------------- #
def model_vs_market_gap(
    model_pred: Mapping[str, object],
    implied: Optional[Mapping[str, object]],
    *,
    tv_mild: float = 0.08,
    tv_strong: float = 0.15,
    match_id: str = "",
) -> GapReport:
    warnings: List[str] = []

    # ---- modelo ----
    m_a = _f(model_pred.get("prob_a"))
    m_d = _f(model_pred.get("prob_draw"))
    m_b = _f(model_pred.get("prob_b"))
    model_lambda_a = _f(model_pred.get("lambda_a"))
    model_lambda_b = _f(model_pred.get("lambda_b"))
    model_pick = argmax_outcome(m_a, m_d, m_b) if None not in (m_a, m_d, m_b) else None
    model_total = (model_lambda_a + model_lambda_b) if (model_lambda_a is not None and model_lambda_b is not None) else None
    model_supremacy = _diff(model_lambda_a, model_lambda_b)

    # ---- mercado ausente del todo ----
    if implied is None:
        warnings.append("sin fila de mercado: comparación no calculable")
        return GapReport(
            match_id=match_id, model_pick=model_pick, market_pick=None,
            model_prob_a=m_a, model_prob_draw=m_d, model_prob_b=m_b,
            market_prob_a=None, market_prob_draw=None, market_prob_b=None,
            gap_1x2_home=None, gap_1x2_draw=None, gap_1x2_away=None, gap_1x2_total_variation=None,
            model_total_goals=model_total, market_total_goals=None, gap_total_goals=None,
            model_supremacy=model_supremacy, market_supremacy=None, gap_supremacy=None,
            model_lambda_a=model_lambda_a, model_lambda_b=model_lambda_b,
            market_lambda_home=None, market_lambda_away=None,
            gap_lambda_home=None, gap_lambda_away=None,
            contradicts_market=False, contradiction_severity=SEVERITY_NONE,
            gap_status=STATUS_SIN_MUESTRA, warnings=tuple(warnings),
        )

    # ---- mercado ----
    k_a = _f(implied.get("p_home"))
    k_d = _f(implied.get("p_draw"))
    k_b = _f(implied.get("p_away"))
    market_total = _f(implied.get("market_total_goals"))
    market_supremacy = _f(implied.get("market_supremacy"))
    market_lambda_home = _f(implied.get("market_lambda_home"))
    market_lambda_away = _f(implied.get("market_lambda_away"))

    has_market_1x2 = None not in (k_a, k_d, k_b)
    market_pick = argmax_outcome(k_a, k_d, k_b) if has_market_1x2 else None

    # 1X2 gaps + TV (solo si hay 1X2 de mercado)
    if has_market_1x2 and model_pick is not None:
        gap_home = m_a - k_a
        gap_draw = m_d - k_d
        gap_away = m_b - k_b
        tv = total_variation_distance(
            {"home": m_a, "draw": m_d, "away": m_b},
            {"home": k_a, "draw": k_d, "away": k_b},
        )
        contradicts = model_pick != market_pick
        severity = classify_severity(tv, tv_mild, tv_strong)
        gap_status = STATUS_CALCULADO
    else:
        gap_home = gap_draw = gap_away = tv = None
        contradicts = False
        severity = SEVERITY_NONE
        gap_status = STATUS_SIN_MUESTRA
        warnings.append("mercado 1X2 ausente/insuficiente: gap 1X2 no calculable")

    # total / supremacía / lambdas (independientes del 1X2; vacíos + warning si faltan)
    gap_total = _diff(model_total, market_total)
    if market_total is None:
        warnings.append("mercado sin total: gap_total_goals vacío")
    gap_supremacy = _diff(model_supremacy, market_supremacy)
    if market_supremacy is None:
        warnings.append("mercado sin supremacía: gap_supremacy vacío")
    gap_lambda_home = _diff(model_lambda_a, market_lambda_home)
    gap_lambda_away = _diff(model_lambda_b, market_lambda_away)
    if market_lambda_home is None or market_lambda_away is None:
        warnings.append("mercado sin total/handicap: gap_lambda vacío")

    return GapReport(
        match_id=match_id, model_pick=model_pick, market_pick=market_pick,
        model_prob_a=m_a, model_prob_draw=m_d, model_prob_b=m_b,
        market_prob_a=k_a, market_prob_draw=k_d, market_prob_b=k_b,
        gap_1x2_home=gap_home, gap_1x2_draw=gap_draw, gap_1x2_away=gap_away,
        gap_1x2_total_variation=tv,
        model_total_goals=model_total, market_total_goals=market_total, gap_total_goals=gap_total,
        model_supremacy=model_supremacy, market_supremacy=market_supremacy, gap_supremacy=gap_supremacy,
        model_lambda_a=model_lambda_a, model_lambda_b=model_lambda_b,
        market_lambda_home=market_lambda_home, market_lambda_away=market_lambda_away,
        gap_lambda_home=gap_lambda_home, gap_lambda_away=gap_lambda_away,
        contradicts_market=contradicts, contradiction_severity=severity,
        gap_status=gap_status, warnings=tuple(warnings),
    )


def gap_report_to_row(report: GapReport) -> Dict[str, object]:
    def fmt(value):
        return "" if value is None else value

    return {
        "match_id": report.match_id,
        "model_pick": fmt(report.model_pick),
        "market_pick": fmt(report.market_pick),
        "model_prob_a": fmt(report.model_prob_a),
        "model_prob_draw": fmt(report.model_prob_draw),
        "model_prob_b": fmt(report.model_prob_b),
        "market_prob_a": fmt(report.market_prob_a),
        "market_prob_draw": fmt(report.market_prob_draw),
        "market_prob_b": fmt(report.market_prob_b),
        "gap_1x2_home": fmt(report.gap_1x2_home),
        "gap_1x2_draw": fmt(report.gap_1x2_draw),
        "gap_1x2_away": fmt(report.gap_1x2_away),
        "gap_1x2_total_variation": fmt(report.gap_1x2_total_variation),
        "model_total_goals": fmt(report.model_total_goals),
        "market_total_goals": fmt(report.market_total_goals),
        "gap_total_goals": fmt(report.gap_total_goals),
        "model_supremacy": fmt(report.model_supremacy),
        "market_supremacy": fmt(report.market_supremacy),
        "gap_supremacy": fmt(report.gap_supremacy),
        "model_lambda_a": fmt(report.model_lambda_a),
        "model_lambda_b": fmt(report.model_lambda_b),
        "market_lambda_home": fmt(report.market_lambda_home),
        "market_lambda_away": fmt(report.market_lambda_away),
        "gap_lambda_home": fmt(report.gap_lambda_home),
        "gap_lambda_away": fmt(report.gap_lambda_away),
        "contradicts_market": report.contradicts_market,
        "contradiction_severity": report.contradiction_severity,
        "gap_status": report.gap_status,
        "warnings": ";".join(report.warnings),
    }


GAP_COLUMNS = tuple(gap_report_to_row(GapReport(
    match_id="", model_pick=None, market_pick=None,
    model_prob_a=None, model_prob_draw=None, model_prob_b=None,
    market_prob_a=None, market_prob_draw=None, market_prob_b=None,
    gap_1x2_home=None, gap_1x2_draw=None, gap_1x2_away=None, gap_1x2_total_variation=None,
    model_total_goals=None, market_total_goals=None, gap_total_goals=None,
    model_supremacy=None, market_supremacy=None, gap_supremacy=None,
    model_lambda_a=None, model_lambda_b=None, market_lambda_home=None, market_lambda_away=None,
    gap_lambda_home=None, gap_lambda_away=None,
    contradicts_market=False, contradiction_severity=SEVERITY_NONE,
    gap_status=STATUS_SIN_MUESTRA, warnings=(),
)).keys())


__all__ = [
    "OUTCOMES",
    "SEVERITY_NONE", "SEVERITY_MILD", "SEVERITY_STRONG",
    "STATUS_CALCULADO", "STATUS_SIN_MUESTRA",
    "GAP_COLUMNS",
    "GapReport",
    "total_variation_distance",
    "argmax_outcome",
    "classify_severity",
    "model_vs_market_gap",
    "gap_report_to_row",
]
