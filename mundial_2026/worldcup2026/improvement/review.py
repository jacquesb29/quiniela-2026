"""Orquestación: hipótesis sembradas + revisión por gates.

Propone candidatas, evalúa gates, bloquea las que no tienen evidencia y marca
diagnostic_only las no activables. NO modifica producción ni corre el modelo.
"""

from __future__ import annotations

from typing import List

from .evidence import EvidenceBundle, collect_evidence
from .gates import GateResult, decide_status, enforce_invariants, evaluate_gate, reason_for
from .hypothesis import Category, Gate, Hypothesis, OverfitRisk, Status, validate

# --------------------------------------------------------------------------- #
# Hipótesis iniciales obligatorias (8)
# --------------------------------------------------------------------------- #
DEFAULT_HYPOTHESES: List[Hypothesis] = [
    Hypothesis(
        id="results-update-feed-primary",
        category=Category.RESULTS_UPDATE,
        description="Ingesta de resultados 2026 con feed primario y CSV de fallback.",
        affected_files=("worldcup2026/results_ingest.py", "run_worldcup2026_live_tracker.py"),
        touches_production=False,
        target_metric="cobertura_y_frescura_de_resultados",
        overfit_risk=OverfitRisk.LOW,
        required_gate=Gate.DATA_FRESHNESS,
        status=Status.PROPOSED,
        evidence_refs=("outputs/audit/worldcup2026_source_consistency.csv",
                       "outputs/audit/worldcup2026_data_inventory.md"),
        source_phase="2026-live",
    ),
    Hypothesis(
        id="market-overlay-refine",
        category=Category.MARKET,
        description="Refinar el overlay de mercado/de-vig como capa de recomendación.",
        affected_files=("worldcup2026/market/", "run_market_t60_pipeline.py"),
        touches_production=False,
        target_metric="calidad_recomendacion_operativa",
        overfit_risk=OverfitRisk.LOW,
        required_gate=Gate.OPERATIONAL,
        status=Status.PROPOSED,
        evidence_refs=("outputs/market/market_decision_log.csv",),
        source_phase="F1",
    ),
    Hypothesis(
        id="t60-lineup-adjust",
        category=Category.T60,
        description="Ajuste T-60 por alineaciones confirmadas (overlay operativo).",
        affected_files=("worldcup2026/market/t60.py", "run_t60_update.py"),
        touches_production=False,
        target_metric="acierto_post_alineacion",
        overfit_risk=OverfitRisk.MEDIUM,
        required_gate=Gate.OPERATIONAL,
        status=Status.PROPOSED,
        evidence_refs=("outputs/market/t60_decision_log.csv",),
        source_phase="F1",
    ),
    Hypothesis(
        id="elo-staleness-shrink",
        category=Category.ELO_FIFA,
        description="Shrink Elo→FIFA staleness-aware para ratings desactualizados.",
        affected_files=("worldcup2026/ratings/", "worldcup2026/config.py"),
        touches_production=True,
        target_metric="logloss_oos",
        overfit_risk=OverfitRisk.HIGH,
        required_gate=Gate.WALK_FORWARD_FOLD,
        status=Status.PROPOSED,
        evidence_refs=("outputs/ratings/staleness_activation_decision.md",),
        source_phase="F2",
    ),
    Hypothesis(
        id="draws-favorito-uplift",
        category=Category.DRAWS,
        description="Subir prob. de empate cuando el favorito es fuerte (sesgo F3).",
        affected_files=("modelo_quiniela_2026.py",),
        touches_production=True,
        target_metric="draw_calibration_oos",
        overfit_risk=OverfitRisk.HIGH,
        required_gate=Gate.WALK_FORWARD_FOLD,
        status=Status.PROPOSED,
        evidence_refs=("outputs/audit/draw_audit.csv",),
        source_phase="F3",
    ),
    Hypothesis(
        id="tail-reweight",
        category=Category.TAILS,
        description="Re-pesar colas (≥4 goles) subestimadas por el ensamble.",
        affected_files=("worldcup2026/interventions/", "modelo_quiniela_2026.py"),
        touches_production=True,
        target_metric="tail_calibration_oos",
        overfit_risk=OverfitRisk.HIGH,
        required_gate=Gate.WALK_FORWARD_FOLD,
        status=Status.PROPOSED,
        evidence_refs=("outputs/audit/tail_walkforward_decision.md",),
        source_phase="F4",
    ),
    Hypothesis(
        id="penca-selector-tune",
        category=Category.PENCA_SELECTOR,
        description="Ajustar el selector Penca 8/5/3 (valor esperado vs modal).",
        affected_files=("modelo_quiniela_2026.py",),
        touches_production=True,
        target_metric="penca_avg_oos",
        overfit_risk=OverfitRisk.HIGH,
        required_gate=Gate.WALK_FORWARD_FOLD,
        status=Status.PROPOSED,
        evidence_refs=("outputs/audit/penca_score_audit.csv",),
        source_phase="F3",
    ),
    Hypothesis(
        id="f6-component-fix",
        category=Category.TAILS,
        description="Corregir el componente causal del gap de cola (F6).",
        affected_files=("worldcup2026/attribution/", "modelo_quiniela_2026.py"),
        touches_production=True,
        target_metric="variance_attribution_oos",
        overfit_risk=OverfitRisk.HIGH,
        required_gate=Gate.WALK_FORWARD_FOLD,
        status=Status.PROPOSED,
        evidence_refs=("outputs/audit/variance_attribution_decision.md",),
        source_phase="F5/F6",
    ),
]


def propose_candidates(ev: EvidenceBundle) -> List[Hypothesis]:
    """Por ahora las candidatas son el set obligatorio sembrado."""
    return list(DEFAULT_HYPOTHESES)


def review(registry: List[Hypothesis], ev: EvidenceBundle):
    """Devuelve (hipótesis_revisadas, gate_results_por_id)."""
    reviewed: List[Hypothesis] = []
    gate_results = {}
    for h in registry:
        gr = evaluate_gate(h, ev)
        status = decide_status(h, gr, ev)
        status = enforce_invariants(h, status)
        reviewed.append(h.with_decision(status, reason_for(h, gr, status)))
        gate_results[h.id] = gr

    # Validación dura de invariantes: ninguna ACTIVE viola las reglas.
    violations = []
    for h in reviewed:
        violations.extend(validate(h))
    if violations:  # pragma: no cover - nunca debería ocurrir con las reglas actuales
        raise AssertionError("Invariantes violadas: " + "; ".join(violations))
    return reviewed, gate_results
