"""Capa de mejora predictiva: proponer, evaluar y bloquear mejoras sin tocar
producción hasta que pasen gates. No modifica pesos/lambdas/Penca/flags, no
entrena con 2026, no inventa resultados ni cambia predicciones."""

from __future__ import annotations

from .evidence import EvidenceBundle, collect_evidence
from .gates import GateResult, decide_status, evaluate_gate
from .hypothesis import Category, Gate, Hypothesis, OverfitRisk, Status, validate
from .registry import COLUMNS, REGISTRY_CSV, load_registry, save_registry
from .review import DEFAULT_HYPOTHESES, propose_candidates, review

__all__ = [
    "EvidenceBundle", "collect_evidence", "GateResult", "decide_status", "evaluate_gate",
    "Category", "Gate", "Hypothesis", "OverfitRisk", "Status", "validate",
    "COLUMNS", "REGISTRY_CSV", "load_registry", "save_registry",
    "DEFAULT_HYPOTHESES", "propose_candidates", "review",
]
