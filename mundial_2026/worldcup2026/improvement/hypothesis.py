"""Hipótesis de mejora predictiva: dataclass + enums + validación de invariantes.

Esta capa NO toca producción: solo describe, clasifica y valida propuestas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple


class Status(str, Enum):
    PROPOSED = "proposed"
    TESTING = "testing"
    REJECTED = "rejected"
    DIAGNOSTIC_ONLY = "diagnostic_only"
    APPROVED = "approved"
    ACTIVE = "active"


class Category(str, Enum):
    MARKET = "market"
    T60 = "t60"
    ELO_FIFA = "elo_fifa"
    DRAWS = "draws"
    TAILS = "tails"
    PENCA_SELECTOR = "penca_selector"
    LINEUP_DATA = "lineup_data"
    RESULTS_UPDATE = "results_update"


class OverfitRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Gate(str, Enum):
    WALK_FORWARD_FOLD = "walk_forward_fold"
    OPERATIONAL = "operational"
    DATA_FRESHNESS = "data_freshness"
    NONE_POSSIBLE = "none_possible"


@dataclass(frozen=True)
class Hypothesis:
    id: str
    category: Category
    description: str
    affected_files: Tuple[str, ...]
    touches_production: bool
    target_metric: str
    overfit_risk: OverfitRisk
    required_gate: Gate
    status: Status
    evidence_refs: Tuple[str, ...] = ()
    decision_reason: str = ""
    source_phase: str = ""

    def with_decision(self, status: Status, reason: str,
                      evidence_refs: Tuple[str, ...] = None) -> "Hypothesis":
        from dataclasses import replace
        return replace(self, status=status, decision_reason=reason,
                       evidence_refs=evidence_refs if evidence_refs is not None else self.evidence_refs)


def validate(h: Hypothesis) -> List[str]:
    """Devuelve la lista de violaciones de invariantes (vacía = válida)."""
    problems: List[str] = []
    if not h.id:
        problems.append("id vacío")
    if h.touches_production and h.required_gate != Gate.WALK_FORWARD_FOLD:
        problems.append(f"{h.id}: toca producción pero su gate no es walk_forward_fold")
    if h.status == Status.ACTIVE:
        if not h.evidence_refs:
            problems.append(f"{h.id}: ACTIVE sin evidence_refs")
        if h.touches_production:
            problems.append(f"{h.id}: ACTIVE y toca producción (prohibido sin gate WF aprobado)")
    return problems
