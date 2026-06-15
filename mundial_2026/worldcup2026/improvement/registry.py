"""Persistencia del registro de hipótesis: improvement_registry.csv."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from .hypothesis import Category, Gate, Hypothesis, OverfitRisk, Status

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_CSV = ROOT / "outputs" / "improvement" / "improvement_registry.csv"

COLUMNS = (
    "id", "category", "description", "affected_files", "touches_production",
    "target_metric", "overfit_risk", "required_gate", "status",
    "evidence_refs", "decision_reason", "source_phase", "last_reviewed",
)

_SEP = ";"


def to_row(h: Hypothesis, last_reviewed: str = "") -> dict:
    return {
        "id": h.id,
        "category": h.category.value,
        "description": h.description,
        "affected_files": _SEP.join(h.affected_files),
        "touches_production": "true" if h.touches_production else "false",
        "target_metric": h.target_metric,
        "overfit_risk": h.overfit_risk.value,
        "required_gate": h.required_gate.value,
        "status": h.status.value,
        "evidence_refs": _SEP.join(h.evidence_refs),
        "decision_reason": h.decision_reason,
        "source_phase": h.source_phase,
        "last_reviewed": last_reviewed,
    }


def from_row(row: dict) -> Hypothesis:
    def _tuple(value: str):
        return tuple(x for x in (value or "").split(_SEP) if x)
    return Hypothesis(
        id=row["id"],
        category=Category(row["category"]),
        description=row["description"],
        affected_files=_tuple(row.get("affected_files")),
        touches_production=str(row.get("touches_production")).strip().lower() == "true",
        target_metric=row.get("target_metric", ""),
        overfit_risk=OverfitRisk(row.get("overfit_risk", "high")),
        required_gate=Gate(row.get("required_gate", "walk_forward_fold")),
        status=Status(row.get("status", "proposed")),
        evidence_refs=_tuple(row.get("evidence_refs")),
        decision_reason=row.get("decision_reason", ""),
        source_phase=row.get("source_phase", ""),
    )


def load_registry(path: Path = REGISTRY_CSV) -> List[Hypothesis]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as h:
        return [from_row(r) for r in csv.DictReader(h)]


def save_registry(items: List[Hypothesis], path: Path = REGISTRY_CSV,
                  last_reviewed: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(COLUMNS), lineterminator="\n")
        w.writeheader()
        for it in items:
            w.writerow(to_row(it, last_reviewed=last_reviewed))


def upsert(items: List[Hypothesis], new: Hypothesis) -> List[Hypothesis]:
    out = [it for it in items if it.id != new.id]
    out.append(new)
    return out
