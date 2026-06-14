"""Flujo T-60: materialización de la recomendación prepartido (F1.5).

Refresca la recomendación operativa hasta 60' antes del partido usando odds t60,
gap modelo-mercado (F1.3), la regla de decisión (F1.4) y datos manuales de
alineación/bajas/portero. SOLO produce recomendación operativa con before/after:
NO reentrena, NO cambia la predicción interna del modelo, NO toca
pesos/lambdas/metodología/Penca.

Reglas: sin odds t60 válidas no se fuerza cambio; closing no es apto para decisión;
sin razón material no se cambia el pick; todo cambio lleva before/after y reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

from .decision import decide_pick
from .devig import MarketImplied, odds_to_implied
from .gap import model_vs_market_gap
from .odds_ingest import OddsSnapshot, is_usable_for_decision

DEFAULT_ODDS_MOVE_THRESHOLD = 0.06
DEFAULT_LINEUP_CHANGE_THRESHOLD = 3


@dataclass(frozen=True)
class T60Inputs:
    match_id: str
    captured_at_utc: str
    odds: Optional[OddsSnapshot]
    lineup_confirmed: bool
    lineup_changes: int
    injuries_confirmed: Tuple[str, ...]
    starting_gk: Optional[str]
    gk_changed: bool
    notes: str = ""


@dataclass(frozen=True)
class T60Change:
    match_id: str
    pick_before: Optional[str]
    pick_after: Optional[str]
    changed: bool
    confidence_before: str
    confidence_after: str
    trigger: str
    reason: str
    captured_at_utc: str
    odds_snapshot_type: str
    lineup_confirmed: bool
    lineup_changes: int
    injuries_confirmed: str
    starting_gk: str
    gk_changed: bool


def implied_to_mapping(implied: Optional[MarketImplied]) -> Optional[Dict[str, object]]:
    if implied is None:
        return None
    return {
        "p_home": implied.p_home, "p_draw": implied.p_draw, "p_away": implied.p_away,
        "market_total_goals": implied.market_total_goals,
        "market_supremacy": implied.market_supremacy,
        "market_lambda_home": implied.market_lambda_home,
        "market_lambda_away": implied.market_lambda_away,
    }


def has_traceable_reason(inputs: T60Inputs, *, lineup_change_threshold: int = DEFAULT_LINEUP_CHANGE_THRESHOLD) -> bool:
    return bool(inputs.injuries_confirmed) or inputs.gk_changed or inputs.lineup_changes >= lineup_change_threshold


def run_t60_for_match(
    *,
    match_id: str,
    model_pred: Mapping[str, object],
    t60_inputs: T60Inputs,
    prior_pick: Optional[str],
    prior_confidence: str,
    prev_implied: Optional[MarketImplied] = None,
    tv_mild: float = 0.08,
    tv_strong: float = 0.15,
    odds_move_threshold: float = DEFAULT_ODDS_MOVE_THRESHOLD,
    lineup_change_threshold: int = DEFAULT_LINEUP_CHANGE_THRESHOLD,
) -> T60Change:
    odds = t60_inputs.odds
    # Odds válidas para decisión: prematch, no closing, 1X2 completo.
    valid_odds = odds is not None and is_usable_for_decision(odds)
    implied = odds_to_implied(odds, require_prematch=True) if valid_odds else None
    implied_map = implied_to_mapping(implied)

    gap = model_vs_market_gap(model_pred, implied_map, tv_mild=tv_mild, tv_strong=tv_strong, match_id=match_id)
    traceable = has_traceable_reason(t60_inputs, lineup_change_threshold=lineup_change_threshold)
    decision = decide_pick(
        match_id=match_id,
        model_pick=gap.model_pick,
        market_pick=gap.market_pick,
        contradicts_market=gap.contradicts_market,
        contradiction_severity=gap.contradiction_severity,
        gap_1x2_total_variation=gap.gap_1x2_total_variation,
        gap_status=gap.gap_status,
        has_traceable_reason=traceable,
    )

    # Razones materiales (cualquiera habilita un cambio de pick).
    triggers: List[str] = []
    if gap.contradicts_market:
        triggers.append("market_contradiction")
    if prev_implied is not None and implied is not None and prev_implied.p_home is not None and implied.p_home is not None:
        if abs(float(implied.p_home) - float(prev_implied.p_home)) >= odds_move_threshold:
            triggers.append("odds_move")
    if t60_inputs.lineup_changes >= lineup_change_threshold:
        triggers.append("lineup")
    if t60_inputs.injuries_confirmed:
        triggers.append("injury")
    if t60_inputs.gk_changed:
        triggers.append("gk")
    if gap.contradiction_severity == "strong" and not traceable:
        triggers.append("gap_strong")

    candidate_pick = decision.final_pick
    confidence_after = decision.confidence_label

    if not valid_odds:
        # Sin odds t60 válidas (o closing): no se fuerza cambio.
        return T60Change(
            match_id=match_id, pick_before=prior_pick, pick_after=prior_pick, changed=False,
            confidence_before=prior_confidence, confidence_after=prior_confidence,
            trigger="none",
            reason="sin odds t60 válidas (ausentes/closing/post-kickoff): se mantiene el pick previo",
            captured_at_utc=t60_inputs.captured_at_utc,
            odds_snapshot_type=(odds.snapshot_type if odds is not None else ""),
            lineup_confirmed=t60_inputs.lineup_confirmed, lineup_changes=t60_inputs.lineup_changes,
            injuries_confirmed=";".join(t60_inputs.injuries_confirmed),
            starting_gk=t60_inputs.starting_gk or "", gk_changed=t60_inputs.gk_changed,
        )

    # Guard: si el pick cambiaría pero no hay razón material -> se suprime el cambio.
    if candidate_pick != prior_pick and not triggers:
        return T60Change(
            match_id=match_id, pick_before=prior_pick, pick_after=prior_pick, changed=False,
            confidence_before=prior_confidence, confidence_after=confidence_after,
            trigger="none",
            reason="cambio suprimido: sin razón material; se mantiene el pick previo",
            captured_at_utc=t60_inputs.captured_at_utc,
            odds_snapshot_type=odds.snapshot_type,
            lineup_confirmed=t60_inputs.lineup_confirmed, lineup_changes=t60_inputs.lineup_changes,
            injuries_confirmed=";".join(t60_inputs.injuries_confirmed),
            starting_gk=t60_inputs.starting_gk or "", gk_changed=t60_inputs.gk_changed,
        )

    changed = candidate_pick != prior_pick
    trigger = triggers[0] if triggers else "none"
    if changed:
        reason = f"{trigger}: {decision.reason}"
    elif triggers:
        reason = f"sin cambio de pick; señales materiales presentes ({', '.join(triggers)}); {decision.reason}"
    else:
        reason = f"sin cambios: pick mantenido; {decision.reason}"

    return T60Change(
        match_id=match_id, pick_before=prior_pick, pick_after=candidate_pick, changed=changed,
        confidence_before=prior_confidence, confidence_after=confidence_after,
        trigger=trigger, reason=reason,
        captured_at_utc=t60_inputs.captured_at_utc,
        odds_snapshot_type=odds.snapshot_type,
        lineup_confirmed=t60_inputs.lineup_confirmed, lineup_changes=t60_inputs.lineup_changes,
        injuries_confirmed=";".join(t60_inputs.injuries_confirmed),
        starting_gk=t60_inputs.starting_gk or "", gk_changed=t60_inputs.gk_changed,
    )


def t60_change_to_row(change: T60Change) -> Dict[str, object]:
    def fmt(value):
        return "" if value is None else value

    return {
        "match_id": change.match_id,
        "pick_before": fmt(change.pick_before),
        "pick_after": fmt(change.pick_after),
        "changed": change.changed,
        "confidence_before": change.confidence_before,
        "confidence_after": change.confidence_after,
        "trigger": change.trigger,
        "reason": change.reason,
        "captured_at_utc": change.captured_at_utc,
        "odds_snapshot_type": change.odds_snapshot_type,
        "lineup_confirmed": change.lineup_confirmed,
        "lineup_changes": change.lineup_changes,
        "injuries_confirmed": change.injuries_confirmed,
        "starting_gk": change.starting_gk,
        "gk_changed": change.gk_changed,
    }


T60_DECISION_COLUMNS = tuple(t60_change_to_row(T60Change(
    match_id="", pick_before=None, pick_after=None, changed=False,
    confidence_before="", confidence_after="", trigger="", reason="",
    captured_at_utc="", odds_snapshot_type="", lineup_confirmed=False, lineup_changes=0,
    injuries_confirmed="", starting_gk="", gk_changed=False,
)).keys())


def _parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "si", "sí"}


def _parse_int(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def load_t60_inputs(path, odds_snapshots: Optional[List[OddsSnapshot]] = None) -> List[T60Inputs]:
    """Lee data/t60_inputs.csv y enlaza odds (t60 preferido sobre opening) por match_id."""

    import csv as _csv
    from pathlib import Path as _Path

    odds_by_match: Dict[str, OddsSnapshot] = {}
    for snap in (odds_snapshots or []):
        if snap.snapshot_type not in ("opening", "t60"):
            continue
        current = odds_by_match.get(snap.match_id)
        # Preferir t60 sobre opening.
        if current is None or (snap.snapshot_type == "t60" and current.snapshot_type != "t60"):
            odds_by_match[snap.match_id] = snap

    inputs: List[T60Inputs] = []
    with _Path(path).open(newline="", encoding="utf-8") as handle:
        for raw in _csv.DictReader(handle):
            match_id = (raw.get("match_id") or "").strip()
            injuries_raw = (raw.get("injuries_confirmed") or "").strip()
            injuries = tuple(x.strip() for x in injuries_raw.replace(",", ";").split(";") if x.strip())
            inputs.append(T60Inputs(
                match_id=match_id,
                captured_at_utc=(raw.get("captured_at_utc") or "").strip(),
                odds=odds_by_match.get(match_id),
                lineup_confirmed=_parse_bool(raw.get("lineup_confirmed")),
                lineup_changes=_parse_int(raw.get("lineup_changes")),
                injuries_confirmed=injuries,
                starting_gk=((raw.get("starting_gk") or "").strip() or None),
                gk_changed=_parse_bool(raw.get("gk_changed")),
                notes=(raw.get("notes") or "").strip(),
            ))
    return inputs


__all__ = [
    "DEFAULT_ODDS_MOVE_THRESHOLD",
    "DEFAULT_LINEUP_CHANGE_THRESHOLD",
    "T60_DECISION_COLUMNS",
    "T60Inputs",
    "T60Change",
    "implied_to_mapping",
    "has_traceable_reason",
    "run_t60_for_match",
    "t60_change_to_row",
    "load_t60_inputs",
]
