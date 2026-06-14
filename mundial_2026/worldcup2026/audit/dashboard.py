"""Dashboard F3 (sección H): SOLO lectura de los CSV de auditoría. No corrige."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Dict, List, Optional

AUDIT_FILES = {
    "score": "score_distribution_audit.csv",
    "draw": "draw_audit.csv",
    "goals": "goal_calibration.csv",
    "tail": "tail_events_audit.csv",
    "exact": "exact_score_audit.csv",
    "penca": "penca_score_audit.csv",
}
SECTION_TITLES = {
    "score": "Score calibration", "draw": "Draw calibration", "goals": "Goal calibration",
    "tail": "Tail calibration", "exact": "Exact score performance", "penca": "Penca performance",
}


def _read_rows(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_audit_outputs(audit_dir: str | Path, gate_path: Optional[str | Path] = None) -> dict:
    audit_dir = Path(audit_dir)
    tables = {key: _read_rows(audit_dir / fname) for key, fname in AUDIT_FILES.items()}
    gate = None
    if gate_path is not None and Path(gate_path).exists():
        try:
            gate = json.loads(Path(gate_path).read_text(encoding="utf-8"))
        except (ValueError, OSError):
            gate = None
    return {"tables": tables, "gate": gate, "available": any(tables.values())}


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def _render_table(rows: List[dict]) -> str:
    if not rows:
        return "<p>(sin datos)</p>"
    cols = list(rows[0].keys())
    out = ["<table border='1' cellspacing='0' cellpadding='3'><tr>"]
    out += [f"<th>{_esc(c)}</th>" for c in cols]
    out.append("</tr>")
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{_esc(r.get(c))}</td>" for c in cols) + "</tr>")
    out.append("</table>")
    return "".join(out)


def render_f3_dashboard_html(data: dict) -> str:
    header = '<section class="f3-audit"><h3>Auditoría estructural F3 (histórico, no validación 2026)</h3>'
    if not data.get("available"):
        return header + "<p>auditoría F3 pendiente: no hay outputs de auditoría todavía.</p></section>"
    parts = [header]
    gate = data.get("gate")
    if gate:
        parts.append("<h4>Veredicto del gate</h4><ul>")
        for key in ("subestima_empates", "sobreestima_favoritos", "goles_mal_calibrados",
                    "subestima_colas", "optimismo_penca", "vale_la_pena_intervenir", "suggested_priority"):
            parts.append(f"<li>{_esc(key)}: <b>{_esc(gate.get(key))}</b></li>")
        parts.append("</ul>")
    for key, title in SECTION_TITLES.items():
        parts.append(f"<h4>{_esc(title)}</h4>")
        parts.append(_render_table(data["tables"].get(key, [])))
    parts.append("</section>")
    return "\n".join(parts)


__all__ = ["AUDIT_FILES", "load_audit_outputs", "render_f3_dashboard_html"]
