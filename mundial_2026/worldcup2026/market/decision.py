"""Regla de decisión modelo vs mercado (F1.4).

Usa el gap modelo-mercado (F1.3) para decidir si confiar en el modelo, bajar
confianza o recomendar seguir al mercado. SOLO decide y advierte: NO integra odds
al modelo, NO cambia la predicción interna, NO toca pesos/lambdas/metodología/Penca.

`has_traceable_reason` (baja confirmada, alineación, portero…) llegará con T-60
(F1.5); aquí su valor por defecto es False, así que un gap fuerte con mismo ganador
recomienda acercarse al mercado en vez de justificar quedarse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

CONF_ALTA = "Alta"
CONF_MEDIA = "Media"
CONF_BAJA = "Baja"

ACTION_TRUST_MODEL = "trust_model"
ACTION_KEEP_PICK = "keep_pick"
ACTION_LOWER_CONFIDENCE = "lower_confidence"
ACTION_SHADE_TO_MARKET = "shade_to_market"
ACTION_FOLLOW_MARKET = "follow_market"
ACTION_NO_MARKET = "no_market_available"

SEVERITY_NONE = "none"
SEVERITY_MILD = "mild"
SEVERITY_STRONG = "strong"

SOURCE_WITH_MARKET = "mercado_disponible"
SOURCE_NO_MARKET = "sin_mercado"


@dataclass(frozen=True)
class DecisionVerdict:
    match_id: str
    model_pick: Optional[str]
    market_pick: Optional[str]
    final_pick: Optional[str]
    action: str
    confidence_label: str
    contradiction_severity: str
    gap_1x2_total_variation: Optional[float]
    contradicts_market: bool
    reason: str
    source_status: str


def _has_market(gap_status: str, market_pick: Optional[str]) -> bool:
    return gap_status == "calculado" and bool(market_pick)


def decide_pick(
    *,
    match_id: str = "",
    model_pick: Optional[str],
    market_pick: Optional[str],
    contradicts_market: bool,
    contradiction_severity: str,
    gap_1x2_total_variation: Optional[float],
    gap_status: str,
    has_traceable_reason: bool = False,
) -> DecisionVerdict:
    market_pick = market_pick or None

    def verdict(action, final_pick, confidence, reason, contradicts=contradicts_market):
        return DecisionVerdict(
            match_id=match_id,
            model_pick=model_pick,
            market_pick=market_pick,
            final_pick=final_pick,
            action=action,
            confidence_label=confidence,
            contradiction_severity=contradiction_severity,
            gap_1x2_total_variation=gap_1x2_total_variation,
            contradicts_market=contradicts,
            reason=reason,
            source_status=SOURCE_WITH_MARKET if _has_market(gap_status, market_pick) else SOURCE_NO_MARKET,
        )

    # 1) Sin mercado suficiente: nunca confianza Alta; se mantiene el pick del modelo.
    if not _has_market(gap_status, market_pick):
        return verdict(
            ACTION_NO_MARKET, model_pick, CONF_MEDIA if model_pick else CONF_BAJA,
            "sin mercado suficiente: se mantiene el pick del modelo; confianza acotada (no Alta)",
            contradicts=False,
        )

    # 2) Contradicción de ganador: seguir mercado, confianza Baja.
    if contradicts_market or (model_pick is not None and market_pick is not None and model_pick != market_pick):
        return verdict(
            ACTION_FOLLOW_MARKET, market_pick, CONF_BAJA,
            f"contradicción de ganador: modelo={model_pick} vs mercado={market_pick} "
            f"(severidad {contradiction_severity}); se recomienda seguir al mercado",
            contradicts=True,
        )

    # 3) Mismo ganador: la acción depende de la severidad del gap.
    if contradiction_severity == SEVERITY_STRONG:
        if has_traceable_reason:
            return verdict(
                ACTION_LOWER_CONFIDENCE, model_pick, CONF_BAJA,
                "gap fuerte con mismo ganador y razón trazable: se mantiene pick del modelo "
                "con confianza Baja",
            )
        return verdict(
            ACTION_SHADE_TO_MARKET, model_pick, CONF_BAJA,
            "gap fuerte con mismo ganador y sin razón trazable: acercarse al mercado; "
            "final_pick sigue siendo el del modelo por ahora, confianza Baja",
        )
    if contradiction_severity == SEVERITY_MILD:
        return verdict(
            ACTION_KEEP_PICK, model_pick, CONF_MEDIA,
            "gap moderado con mismo ganador: se conserva el pick del modelo, confianza máxima Media",
        )
    # severidad none -> modelo y mercado concuerdan de cerca.
    return verdict(
        ACTION_TRUST_MODEL, model_pick, CONF_ALTA,
        "modelo y mercado coinciden en ganador con gap bajo: se confía en el modelo",
    )


def decision_to_row(verdict: DecisionVerdict) -> Dict[str, object]:
    def fmt(value):
        return "" if value is None else value

    return {
        "match_id": verdict.match_id,
        "model_pick": fmt(verdict.model_pick),
        "market_pick": fmt(verdict.market_pick),
        "final_pick": fmt(verdict.final_pick),
        "action": verdict.action,
        "confidence_label": verdict.confidence_label,
        "contradiction_severity": verdict.contradiction_severity,
        "gap_1x2_total_variation": fmt(verdict.gap_1x2_total_variation),
        "contradicts_market": verdict.contradicts_market,
        "reason": verdict.reason,
        "source_status": verdict.source_status,
    }


DECISION_COLUMNS = tuple(decision_to_row(DecisionVerdict(
    match_id="", model_pick=None, market_pick=None, final_pick=None,
    action="", confidence_label="", contradiction_severity="",
    gap_1x2_total_variation=None, contradicts_market=False, reason="", source_status="",
)).keys())


__all__ = [
    "CONF_ALTA", "CONF_MEDIA", "CONF_BAJA",
    "ACTION_TRUST_MODEL", "ACTION_KEEP_PICK", "ACTION_LOWER_CONFIDENCE",
    "ACTION_SHADE_TO_MARKET", "ACTION_FOLLOW_MARKET", "ACTION_NO_MARKET",
    "SOURCE_WITH_MARKET", "SOURCE_NO_MARKET",
    "DECISION_COLUMNS",
    "DecisionVerdict",
    "decide_pick",
    "decision_to_row",
]
