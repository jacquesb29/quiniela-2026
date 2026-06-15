"""Render de improvement_decisions.md a partir del registro revisado."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .evidence import EvidenceBundle
from .hypothesis import Hypothesis, Status

ROOT = Path(__file__).resolve().parents[2]
DECISIONS_MD = ROOT / "outputs" / "improvement" / "improvement_decisions.md"


def render(items: List[Hypothesis], ev: EvidenceBundle, gate_results: Dict,
           out_path: Path = DECISIONS_MD) -> str:
    by_status: Dict[str, List[Hypothesis]] = {}
    for h in items:
        by_status.setdefault(h.status.value, []).append(h)

    L = [
        "# Decisiones de mejora predictiva", "",
        "Capa formal para proponer/evaluar/bloquear mejoras **sin tocar producción**. "
        "Ninguna mejora que toque pesos/lambdas/Penca queda activa sin gate walk-forward aprobado. "
        "2026 live solo es tracking/operativo, nunca evidencia de entrenamiento.", "",
        "## Evidencia leída (F0–F7 + 2026 + mercado)",
        f"- F0 validación: **{ev.f0_label}**",
        f"- F3 prioridad: **{ev.f3_priority}** (vale_la_pena={ev.f3_intervene})",
        f"- F2.5 Elo staleness: **{ev.f2_staleness}**",
        f"- F4.2 colas: **{ev.f4_tail}**",
        f"- F5 atribución: **{ev.f5_attribution}** (bloquea F6 si no_clear_culprit)",
        f"- Mercado operativo: **{ev.market_operational}** · T-60 datos disponibles: **{ev.t60_data_available}**",
        f"- 2026 live: {ev.live_2026.get('finalized')} finalizados, "
        f"fuente primaria feed={ev.live_2026.get('primary_is_feed')}", "",
        "## Registro por estado", "",
    ]
    order = [Status.ACTIVE, Status.APPROVED, Status.TESTING,
             Status.DIAGNOSTIC_ONLY, Status.PROPOSED, Status.REJECTED]
    for st in order:
        group = by_status.get(st.value, [])
        if not group:
            continue
        L.append(f"### {st.value} ({len(group)})")
        for h in group:
            prod = "toca producción" if h.touches_production else "operativo/no-prod"
            L.append(f"- **{h.id}** [{h.category.value}, {prod}, gate={h.required_gate.value}, "
                     f"riesgo={h.overfit_risk.value}] — {h.decision_reason}")
        L.append("")

    L += [
        "## Reglas vigentes",
        "- F2 (`elo-staleness-shrink`): permanece **diagnostic_only** (F2.5 keep_off).",
        "- F4 (`tail-reweight`): permanece **rejected** (F4.2 keep_off).",
        "- F5 `no_clear_culprit` **bloquea F6** (`f6-component-fix` rejected).",
        "- Mercado/T-60: solo **active operativo** (overlay, no altera predicciones internas).",
        "- Ninguna hipótesis que toque producción puede estar active sin gate walk-forward aprobado.",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(L)
    out_path.write_text(text, encoding="utf-8")
    return text
