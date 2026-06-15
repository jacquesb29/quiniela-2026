"""Evaluación de gates y decisión de estado (reglas estrictas).

Invariante central: ninguna hipótesis que toque producción puede quedar ACTIVE
sin un gate walk-forward aprobado fold-a-fold. Hoy ninguna lo cumple.
"""

from __future__ import annotations

from dataclasses import dataclass

from .evidence import EvidenceBundle
from .hypothesis import Category, Gate, Hypothesis, Status


@dataclass
class GateResult:
    gate: Gate
    passed: bool
    reason: str
    sample_ok: bool = False
    leakage_free: bool = False
    oos_fold_improvement: bool = False


def evaluate_gate(h: Hypothesis, ev: EvidenceBundle) -> GateResult:
    g = h.required_gate

    if g == Gate.DATA_FRESHNESS:
        ok = bool(ev.live_2026.get("primary_is_feed"))
        return GateResult(g, ok,
                          "feed primario y sin inventar resultados" if ok
                          else "feed no es primario", sample_ok=True, leakage_free=True)

    if g == Gate.OPERATIONAL:
        if h.category == Category.MARKET:
            ok = ev.market_operational and not h.touches_production
            return GateResult(g, ok,
                              "overlay de mercado operativo; no altera predicciones internas" if ok
                              else "pipeline de mercado no disponible", leakage_free=True)
        if h.category == Category.T60:
            ok = ev.t60_data_available and not h.touches_production
            return GateResult(g, ok,
                              "alineaciones disponibles; overlay operativo" if ok
                              else "sin alineaciones confirmadas en el feed → no activable aún")
        return GateResult(g, False, "categoría operativa no reconocida")

    if g == Gate.WALK_FORWARD_FOLD:
        # Lee veredictos out-of-sample existentes; hoy ninguno aprueba.
        if h.category == Category.ELO_FIFA:
            passed = ev.f2_staleness == "activate"
            return GateResult(g, passed, f"F2.5 = {ev.f2_staleness} (sin FIFA histórica → identidad OOS)")
        if h.id == "tail-reweight":
            passed = ev.f4_tail == "activate"
            return GateResult(g, passed, f"F4.2 fold-a-fold = {ev.f4_tail}")
        if h.id == "f6-component-fix":
            passed = ev.f5_attribution == "intervene_component"
            return GateResult(g, passed, f"F5 = {ev.f5_attribution} (bloquea F6 sin culpable causal)")
        # draws / penca_selector: sin estudio walk-forward aprobado todavía.
        return GateResult(g, False, "sin evidencia walk-forward fold-a-fold aprobada")

    return GateResult(g, False, "gate no evaluable")


def decide_status(h: Hypothesis, gr: GateResult, ev: EvidenceBundle) -> Status:
    """Determina el estado a partir del gate. Nunca ACTIVE si toca producción."""
    if h.category == Category.RESULTS_UPDATE:
        return Status.ACTIVE if gr.passed else Status.PROPOSED
    if h.category == Category.MARKET:
        return Status.ACTIVE if gr.passed else Status.PROPOSED
    if h.category == Category.T60:
        return Status.ACTIVE if gr.passed else Status.DIAGNOSTIC_ONLY
    if h.category == Category.ELO_FIFA:
        # F2 permanece diagnóstico mientras no haya evidencia OOS.
        return Status.APPROVED if gr.passed else Status.DIAGNOSTIC_ONLY
    if h.id in ("tail-reweight", "f6-component-fix"):
        return Status.APPROVED if gr.passed else Status.REJECTED
    # draws / penca_selector y cualquier otra que toque producción sin gate:
    if gr.passed:
        return Status.APPROVED
    return Status.PROPOSED


def reason_for(h: Hypothesis, gr: GateResult, status: Status) -> str:
    base = f"gate={gr.gate.value} ({'aprobado' if gr.passed else 'no aprobado'}): {gr.reason}"
    if status == Status.REJECTED:
        return "RECHAZADA — " + base
    if status == Status.DIAGNOSTIC_ONLY:
        return "DIAGNÓSTICO — " + base
    if status == Status.ACTIVE:
        return "ACTIVA (operativa, no altera predicciones internas) — " + base
    if status == Status.PROPOSED:
        return "BLOQUEADA/propuesta — " + base
    return base


def enforce_invariants(h: Hypothesis, status: Status) -> Status:
    """Guardia dura: producción + no-walk-forward-aprobado nunca queda ACTIVE."""
    if status == Status.ACTIVE and h.touches_production:
        return Status.REJECTED
    return status
