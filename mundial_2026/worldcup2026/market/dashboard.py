"""Dashboard de mercado/T-60 (F1.6): SOLO lectura de outputs ya generados.

Lee los CSV de F1.1/F1.3/F1.4/F1.5 y `validation_status.json` y arma una vista por
partido + un fragmento HTML. NO recalcula lógica de mercado, NO toca el modelo,
pesos, lambdas, metodología ni selector Penca. Si faltan archivos, muestra una
sección "mercado/T-60 pendiente" sin romper la web.

Reglas de presentación:
- No maquillar: se muestra la confianza tal cual la decidió F1.4 (nunca "Alta" si
  el log dice "Baja").
- No mostrar mercado si gap_status=sin_muestra.
- Si T-60 cambia el pick, mostrar before/after + reason; si lo mantiene, indicarlo.
- Si la etiqueta es "validado", aclarar que es histórico vs Poisson/Elo, no vs mercado.
"""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Dict, List, Optional

MARKET_FILES = {
    "implied": "market_implied_probabilities.csv",
    "gap": "market_model_gap.csv",
    "decision": "market_decision_log.csv",
    "last_hour": "last_hour_update.csv",
    "t60": "t60_decision_log.csv",
}


def _read_csv_map(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    out: Dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            mid = (row.get("match_id") or "").strip()
            if mid:
                out[mid] = row
    return out


def _is_true(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "si", "sí"}


def load_market_outputs(market_dir: str | Path, validation_status_path: str | Path) -> dict:
    market_dir = Path(market_dir)
    tables = {key: _read_csv_map(market_dir / fname) for key, fname in MARKET_FILES.items()}
    validation = None
    vpath = Path(validation_status_path)
    if vpath.exists():
        try:
            validation = json.loads(vpath.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            validation = None
    match_ids = sorted(
        {mid for table in tables.values() for mid in table.keys()}
    )
    available = any(tables[k] for k in ("gap", "decision", "implied", "t60", "last_hour"))
    return {
        "tables": tables,
        "validation": validation,
        "match_ids": match_ids,
        "available": available,
    }


def validation_scope_text(validation: Optional[dict]) -> str:
    if not validation or "verdict" not in validation:
        return "Validación: estado no disponible."
    verdict = validation["verdict"]
    label = verdict.get("label", "desconocida")
    reason = verdict.get("reason", "")
    text = f"Etiqueta de validación: {label}. {reason}".strip()
    if label == "validado":
        text += (
            " Nota: validado FUERA DE MUESTRA vs Poisson/Elo en histórico "
            "(Mundial/Euro/Copa América); NO validado contra mercado (sin odds históricas)."
        )
    text += " Track 2026 de mercado: exploratorio (n<30)."
    return text


def build_match_market_view(match_id: str, data: dict) -> dict:
    tables = data["tables"]
    gap = tables["gap"].get(match_id, {})
    dec = tables["decision"].get(match_id, {})
    t60 = tables["t60"].get(match_id, {})
    imp = tables["implied"].get(match_id, {})
    lh = tables["last_hour"].get(match_id, {})

    gap_status = (gap.get("gap_status") or "sin_muestra").strip()
    show_market = gap_status == "calculado"

    severity = (gap.get("contradiction_severity") or "none").strip()
    contradicts = _is_true(gap.get("contradicts_market"))

    warnings: List[str] = []
    if not show_market:
        warnings.append("sin mercado suficiente")
    if imp and not _is_true(imp.get("coverage_1x2")) and _is_true(imp.get("coverage_ou")):
        warnings.append("solo over/under")
    if lh and not _is_true(lh.get("odds_updated")) and (lh.get("odds_snapshot_type") or "").strip() == "closing":
        warnings.append("closing rechazado")
    if severity == "strong":
        warnings.append("gap fuerte")
    if contradicts:
        warnings.append("mercado contradice modelo")
    warnings.append("track 2026 exploratorio")

    return {
        "match_id": match_id,
        "show_market": show_market,
        "gap_status": gap_status,
        "model_pick": dec.get("model_pick") or gap.get("model_pick") or "",
        "market_pick": (dec.get("market_pick") or gap.get("market_pick") or "") if show_market else "",
        "final_pick": dec.get("final_pick") or gap.get("model_pick") or "",
        "action": dec.get("action") or ("no_market_available" if not show_market else ""),
        "confidence": dec.get("confidence_label") or "",
        "gap_1x2_total_variation": gap.get("gap_1x2_total_variation", "") if show_market else "",
        "gap_total_goals": gap.get("gap_total_goals", ""),
        "gap_supremacy": gap.get("gap_supremacy", ""),
        "contradicts_market": contradicts,
        "contradiction_severity": severity,
        # T-60
        "t60_present": bool(t60),
        "pick_before": t60.get("pick_before", ""),
        "pick_after": t60.get("pick_after", ""),
        "changed": _is_true(t60.get("changed")),
        "trigger": t60.get("trigger", ""),
        "reason": t60.get("reason", ""),
        "captured_at_utc": t60.get("captured_at_utc", ""),
        "lineup_confirmed": t60.get("lineup_confirmed", lh.get("lineup_confirmed", "")),
        "injuries_confirmed": t60.get("injuries_confirmed", lh.get("injuries_confirmed", "")),
        "starting_gk": t60.get("starting_gk", lh.get("starting_gk", "")),
        "gk_changed": t60.get("gk_changed", lh.get("gk_changed", "")),
        "warnings": warnings,
    }


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def _render_match_block(view: dict) -> str:
    lines = [f'<div class="market-match" data-match-id="{_esc(view["match_id"])}">']
    lines.append(f'  <h4>{_esc(view["match_id"])}</h4>')
    lines.append(f'  <p>Pick modelo: <b>{_esc(view["model_pick"] or "—")}</b></p>')
    if view["show_market"]:
        lines.append(f'  <p>Pick mercado: <b>{_esc(view["market_pick"] or "—")}</b></p>')
        lines.append(
            '  <p>Gap modelo-mercado: '
            f'TV1X2={_esc(view["gap_1x2_total_variation"] or "—")}, '
            f'gap_total={_esc(view["gap_total_goals"] or "—")}, '
            f'gap_supremacy={_esc(view["gap_supremacy"] or "—")}, '
            f'contradice={_esc("sí" if view["contradicts_market"] else "no")}, '
            f'severidad={_esc(view["contradiction_severity"])}</p>'
        )
    else:
        lines.append('  <p>Mercado: <b>sin muestra suficiente</b> (no se muestra pick de mercado)</p>')
    lines.append(f'  <p>Pick final recomendado: <b>{_esc(view["final_pick"] or "—")}</b> '
                 f'(acción: {_esc(view["action"] or "—")})</p>')
    lines.append(f'  <p>Confianza: <b>{_esc(view["confidence"] or "—")}</b></p>')
    if view["t60_present"]:
        if view["changed"]:
            lines.append(
                f'  <p>T-60: <b>cambió</b> {_esc(view["pick_before"])} → {_esc(view["pick_after"])} '
                f'(trigger: {_esc(view["trigger"])})</p>'
            )
        else:
            lines.append(f'  <p>T-60: <b>pick mantenido</b> ({_esc(view["pick_after"] or view["pick_before"])})</p>')
        lines.append(f'  <p>T-60 razón: {_esc(view["reason"] or "—")}</p>')
        lines.append(
            f'  <p>T-60 captura: {_esc(view["captured_at_utc"] or "—")} | '
            f'alineación confirmada: {_esc(view["lineup_confirmed"] or "—")} | '
            f'bajas: {_esc(view["injuries_confirmed"] or "—")} | '
            f'portero: {_esc(view["starting_gk"] or "—")} | '
            f'cambio portero: {_esc(view["gk_changed"] or "—")}</p>'
        )
    else:
        lines.append('  <p>T-60: pendiente (sin entrada T-60 para este partido)</p>')
    if view["warnings"]:
        lines.append('  <p>Advertencias: ' + ", ".join(_esc(w) for w in view["warnings"]) + "</p>")
    lines.append("</div>")
    return "\n".join(lines)


def render_market_dashboard_html(data: dict) -> str:
    header = '<section class="market-t60-dashboard">\n  <h3>Mercado y T-60</h3>'
    scope = f'  <p class="validation-scope">{_esc(validation_scope_text(data.get("validation")))}</p>'
    if not data.get("available"):
        body = ('  <div class="market-pending"><p>mercado/T-60 pendiente: no hay archivos de '
                'mercado disponibles todavía.</p></div>')
        return f"{header}\n{scope}\n{body}\n</section>"
    blocks = [_render_match_block(build_match_market_view(mid, data)) for mid in data["match_ids"]]
    return f"{header}\n{scope}\n" + "\n".join(blocks) + "\n</section>"


__all__ = [
    "MARKET_FILES",
    "load_market_outputs",
    "validation_scope_text",
    "build_match_market_view",
    "render_market_dashboard_html",
]
