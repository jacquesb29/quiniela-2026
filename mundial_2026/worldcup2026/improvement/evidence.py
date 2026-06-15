"""Lectura de evidencia de F0–F7 + auditoría 2026 + mercado/T-60.

Solo LEE artefactos existentes. No corre el modelo, no entrena, no usa 2026
como evidencia de activación (solo como tracking/operativo).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

VALIDATION_STATUS = ROOT / "outputs" / "validation_status.json"
F3_GATE = ROOT / "outputs" / "audit" / "f3_gate.json"
STALENESS_DECISION = ROOT / "outputs" / "ratings" / "staleness_activation_decision.md"
TAIL_WF_DECISION = ROOT / "outputs" / "audit" / "tail_walkforward_decision.md"
VARIANCE_DECISION = ROOT / "outputs" / "audit" / "variance_attribution_decision.md"
MARKET_DECISION = ROOT / "outputs" / "market" / "market_decision_log.csv"
LIVE_TRACKING = ROOT / "outputs" / "audit" / "worldcup2026_live_tracking.csv"


def _grep_token(path: Path, tokens) -> str:
    if not path.exists():
        return "n/d"
    text = path.read_text(encoding="utf-8").lower()
    for tok in tokens:
        if tok.lower() in text:
            return tok
    return "desconocido"


@dataclass
class EvidenceBundle:
    f0_label: str = "n/d"
    f3_priority: str = "n/d"
    f3_intervene: str = "n/d"
    f2_staleness: str = "n/d"        # keep_off / activate / diagnostic_only
    f4_tail: str = "n/d"             # keep_off / activate
    f5_attribution: str = "n/d"      # no_clear_culprit / intervene_component
    market_operational: bool = False
    t60_data_available: bool = False
    live_2026: dict = field(default_factory=dict)


def collect_evidence(root: Path = ROOT) -> EvidenceBundle:
    ev = EvidenceBundle()

    if VALIDATION_STATUS.exists():
        try:
            ev.f0_label = json.loads(VALIDATION_STATUS.read_text(encoding="utf-8")) \
                .get("verdict", {}).get("label", "n/d")
        except (ValueError, OSError):
            pass

    if F3_GATE.exists():
        try:
            g = json.loads(F3_GATE.read_text(encoding="utf-8"))
            ev.f3_priority = g.get("suggested_priority", "n/d")
            ev.f3_intervene = str(g.get("vale_la_pena_intervenir", "n/d"))
        except (ValueError, OSError):
            pass

    ev.f2_staleness = _grep_token(STALENESS_DECISION, ["keep_off", "activate", "diagnostic_only"])
    ev.f4_tail = _grep_token(TAIL_WF_DECISION, ["keep_off", "activate"])
    ev.f5_attribution = _grep_token(VARIANCE_DECISION, ["no_clear_culprit", "intervene_component"])
    ev.market_operational = MARKET_DECISION.exists()

    # 2026 live: SOLO tracking/operativo (nunca evidencia de entrenamiento).
    live = {"finalized": 0, "primary_is_feed": False, "t60_any": False}
    try:
        from worldcup2026 import results_ingest as RI
        src = RI.load_results_source()
        live["finalized"] = src.finalized_matches
        live["primary_is_feed"] = src.mode == "feed"
        live["source"] = src.source
    except Exception:  # pragma: no cover - defensivo
        live["source"] = "n/d"
    if LIVE_TRACKING.exists():
        try:
            rows = list(csv.DictReader(LIVE_TRACKING.open(encoding="utf-8")))
            live["t60_any"] = any(r.get("t60_disponible") == "si" for r in rows)
        except OSError:
            pass
    ev.t60_data_available = bool(live.get("t60_any"))
    ev.live_2026 = live
    return ev
