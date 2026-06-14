"""Gate de activación del Elo staleness-aware (F2.5).

Decide si el mecanismo (F2.3/F2.4) debe ACTIVARSE en producción o quedarse como
diagnóstico. Es lógica pura de decisión + escritura de artefactos; NO cambia el
flag por defecto, NO toca el modelo, pesos, lambdas, metodología ni Penca.

Regla central: activar solo si mejora puntos Penca fuera de muestra SIN empeorar
log-loss/Brier de forma relevante. Sin evidencia (o evidencia solo en 2026) ⇒ NO
activar; a lo sumo, diagnóstico/guardrail operativo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

from .staleness import T_HIGH, T_LOW

DECISION_ACTIVATE = "activate"
DECISION_KEEP_OFF = "keep_off"

GATE_COLUMNS = (
    "model", "n", "logloss", "brier", "accuracy", "exact_score_accuracy",
    "penca_points_avg", "penca_points_total",
)
BUCKET_COLUMNS = ("bucket", "n", "logloss", "brier", "penca_points_avg", "note")


@dataclass(frozen=True)
class ActivationThresholds:
    min_n: int = 500
    penca_eps: float = 0.01        # mejora mínima de Penca promedio para considerar
    logloss_tol: float = 0.002     # empeoramiento de log-loss tolerable
    brier_tol: float = 0.002       # empeoramiento de Brier tolerable


def _f(metrics: Mapping, key: str) -> Optional[float]:
    value = metrics.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def decide_activation(
    baseline: Mapping[str, object],
    experimental: Mapping[str, object],
    *,
    out_of_sample: bool,
    thresholds: ActivationThresholds = ActivationThresholds(),
) -> Dict[str, object]:
    """Decide activar / mantener OFF a partir de métricas baseline vs experimental."""

    n = int(experimental.get("n") or baseline.get("n") or 0)
    base_ll, exp_ll = _f(baseline, "logloss"), _f(experimental, "logloss")
    base_br, exp_br = _f(baseline, "brier"), _f(experimental, "brier")
    base_pe, exp_pe = _f(baseline, "penca_points_avg"), _f(experimental, "penca_points_avg")

    def result(decision, reason, operational_status="diagnostic_only"):
        return {
            "decision": decision,
            "reason": reason,
            "operational_status": operational_status,
            "n": n,
            "delta_penca_avg": (exp_pe - base_pe) if (exp_pe is not None and base_pe is not None) else None,
            "delta_logloss": (exp_ll - base_ll) if (exp_ll is not None and base_ll is not None) else None,
            "delta_brier": (exp_br - base_br) if (exp_br is not None and base_br is not None) else None,
        }

    if not out_of_sample:
        return result(DECISION_KEEP_OFF, "comparación no es fuera de muestra")
    if n < thresholds.min_n:
        return result(DECISION_KEEP_OFF, f"muestra insuficiente (n={n} < {thresholds.min_n})")
    if None in (base_ll, exp_ll, base_pe, exp_pe):
        return result(DECISION_KEEP_OFF, "métricas incompletas para decidir")

    d_penca = exp_pe - base_pe
    d_ll = exp_ll - base_ll
    d_br = (exp_br - base_br) if (exp_br is not None and base_br is not None) else 0.0

    if abs(d_penca) <= thresholds.penca_eps and abs(d_ll) <= thresholds.logloss_tol:
        return result(DECISION_KEEP_OFF, "sin diferencia relevante (sin evidencia de mejora)")
    if d_penca > thresholds.penca_eps and d_ll <= thresholds.logloss_tol and d_br <= thresholds.brier_tol:
        return result(DECISION_ACTIVATE, "mejora puntos Penca sin empeorar log-loss/Brier", "production_candidate")
    if d_penca > thresholds.penca_eps and (d_ll > thresholds.logloss_tol or d_br > thresholds.brier_tol):
        return result(DECISION_KEEP_OFF, "mejora Penca pero empeora log-loss/Brier de forma relevante")
    return result(DECISION_KEEP_OFF, "no mejora puntos Penca")


def staleness_match_bucket(max_staleness: float, *, t_low: float = T_LOW, t_high: float = T_HIGH) -> str:
    if max_staleness >= t_high:
        return "alto"
    if max_staleness >= t_low:
        return "medio"
    return "bajo"


def build_gate_rows(model_metrics: Mapping[str, Mapping[str, object]]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for name, m in model_metrics.items():
        rows.append({
            "model": name,
            "n": m.get("n", ""),
            "logloss": m.get("logloss", ""),
            "brier": m.get("brier", ""),
            "accuracy": m.get("accuracy", ""),
            "exact_score_accuracy": m.get("exact_score_accuracy", ""),
            "penca_points_avg": m.get("penca_points_avg", ""),
            "penca_points_total": m.get("penca_points_total", ""),
        })
    return rows


def build_by_bucket(bucket_metrics: Mapping[str, Mapping[str, object]]) -> List[Dict[str, object]]:
    rows = []
    for bucket in ("alto", "medio", "bajo"):
        m = bucket_metrics.get(bucket, {"n": 0})
        rows.append({
            "bucket": bucket,
            "n": m.get("n", 0),
            "logloss": m.get("logloss", ""),
            "brier": m.get("brier", ""),
            "penca_points_avg": m.get("penca_points_avg", ""),
            "note": m.get("note", "" if m.get("n") else "sin partidos en este bucket (histórico)"),
        })
    return rows


def write_gate_csv(model_rows: Sequence[Dict[str, object]], bucket_rows: Sequence[Dict[str, object]], path) -> None:
    import csv as _csv
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = _csv.writer(handle, lineterminator="\n")
        writer.writerow(["section"] + list(GATE_COLUMNS))
        for row in model_rows:
            writer.writerow(["model"] + [row.get(c, "") for c in GATE_COLUMNS])
        writer.writerow([])
        writer.writerow(["section"] + list(BUCKET_COLUMNS))
        for row in bucket_rows:
            writer.writerow(["bucket"] + [row.get(c, "") for c in BUCKET_COLUMNS])


def write_decision_md(decision: Mapping[str, object], model_rows, bucket_rows, *, path,
                      limitation_note: str = "") -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Decisión de activación — Elo staleness-aware (F2.5)",
        "",
        f"**Decisión: {decision.get('decision')}** "
        f"(estado operativo: {decision.get('operational_status')})",
        "",
        f"- Razón: {decision.get('reason')}",
        f"- n (out-of-sample): {decision.get('n')}",
        f"- Δ puntos Penca prom.: {decision.get('delta_penca_avg')}",
        f"- Δ log-loss: {decision.get('delta_logloss')}",
        f"- Δ Brier: {decision.get('delta_brier')}",
        "",
        "## Modelos comparados (walk-forward)",
        "",
        "| modelo | n | logloss | brier | acc | exact_acc | penca_avg |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in model_rows:
        lines.append(f"| {r['model']} | {r['n']} | {r['logloss']} | {r['brier']} | "
                     f"{r['accuracy']} | {r['exact_score_accuracy']} | {r['penca_points_avg']} |")
    lines += ["", "## Rendimiento por bucket de staleness", "",
              "| bucket | n | logloss | brier | penca_avg | nota |", "|---|---|---|---|---|---|"]
    for r in bucket_rows:
        lines.append(f"| {r['bucket']} | {r['n']} | {r['logloss']} | {r['brier']} | "
                     f"{r['penca_points_avg']} | {r['note']} |")
    if limitation_note:
        lines += ["", "## Limitación", "", limitation_note]
    lines += ["", "## Estado del flag",
              "`elo_staleness_enabled` permanece **False** salvo que esta decisión sea `activate`.",
              "Esto es validación, no se ajustó el modelo ni se usaron resultados futuros/2026."]
    out.write_text("\n".join(lines), encoding="utf-8")


__all__ = [
    "DECISION_ACTIVATE", "DECISION_KEEP_OFF", "GATE_COLUMNS", "BUCKET_COLUMNS",
    "ActivationThresholds", "decide_activation", "staleness_match_bucket",
    "build_gate_rows", "build_by_bucket", "write_gate_csv", "write_decision_md",
]
