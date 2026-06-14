"""Intervenciones experimentales gated (F4). OFF por defecto; no tocan el modelo."""

from __future__ import annotations

from .gate import (
    DECISION_ACTIVATE,
    DECISION_DIAGNOSTIC,
    DECISION_KEEP_OFF,
    TailGateThresholds,
    decide_tail_activation,
)
from .tail import TailParams, effective_tail_mass, tail_reweight, tail_signal

__all__ = [
    "TailParams", "tail_signal", "tail_reweight", "effective_tail_mass",
    "TailGateThresholds", "decide_tail_activation",
    "DECISION_ACTIVATE", "DECISION_KEEP_OFF", "DECISION_DIAGNOSTIC",
]
