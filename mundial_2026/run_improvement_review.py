"""Runner de revisión de mejoras predictivas.

Lee resultados de F0–F7, la auditoría 2026 live y mercado/T-60; propone las
hipótesis candidatas; bloquea automáticamente las que no tienen evidencia; y
marca diagnostic_only las no activables. Genera el registro y las decisiones.

NO modifica producción, NO activa flags, NO toca pesos/lambdas/Penca, NO usa
2026 para entrenar, NO inventa resultados, NO cambia predicciones.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.improvement import collect_evidence, load_registry, save_registry
from worldcup2026.improvement.decisions import render
from worldcup2026.improvement.registry import REGISTRY_CSV
from worldcup2026.improvement.review import DEFAULT_HYPOTHESES, propose_candidates, review
from worldcup2026.improvement.hypothesis import Status


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    reviewed_at = argv[0] if argv else date.today().isoformat()

    ev = collect_evidence(ROOT)

    # Mantiene hipótesis previas si existen; siempre garantiza las obligatorias.
    existing = {h.id for h in load_registry()}
    registry = list(load_registry()) if existing else []
    for h in propose_candidates(ev):
        if h.id not in existing:
            registry.append(h)
    if not registry:
        registry = list(DEFAULT_HYPOTHESES)

    reviewed, gate_results = review(registry, ev)
    save_registry(reviewed, last_reviewed=reviewed_at)
    render(reviewed, ev, gate_results)

    buckets = {}
    for h in reviewed:
        buckets.setdefault(h.status.value, []).append(h.id)

    print(f"Revisión de mejoras: {len(reviewed)} hipótesis | registro={REGISTRY_CSV.name}")
    for st in (Status.ACTIVE, Status.APPROVED, Status.TESTING,
               Status.DIAGNOSTIC_ONLY, Status.PROPOSED, Status.REJECTED):
        ids = buckets.get(st.value, [])
        if ids:
            print(f"  {st.value}: {', '.join(ids)}")
    print("Producción intacta: no se tocaron pesos/lambdas/Penca/flags ni predicciones.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
