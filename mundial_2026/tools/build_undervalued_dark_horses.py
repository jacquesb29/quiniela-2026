#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Mapping


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "pre_tournament_100k_dark_horses.csv"
OUTPUT = ROOT / "outputs" / "undervalued_dark_horses.csv"
SITE_OUTPUT = ROOT / "site" / "undervalued_dark_horses.csv"


def safe_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def label_for(row: Mapping[str, object], value_score: float, gap: float, path_index: float) -> str:
    if gap >= 0.01 and path_index >= 0.16 and value_score >= 70:
        return "Tapado infravalorado fuerte"
    if gap >= 0.004 and path_index >= 0.10 and value_score >= 50:
        return "Tapado infravalorado jugable"
    if path_index >= 0.15:
        return "Tapado por camino favorable"
    return "Alerta secundaria"


def action_for(label: str) -> str:
    if "fuerte" in label:
        return "Considerar como diferencial de llave si necesitas separarte del consenso."
    if "jugable" in label:
        return "Vigilar antes de octavos/cuartos; usar solo si su ruta se confirma."
    if "camino" in label:
        return "No subirlo por talento puro; subirlo solo si el cuadro queda abierto."
    return "Mantener en watchlist, no mover la llave base sin nueva evidencia."


def build_rows(rows: List[Mapping[str, str]]) -> List[Dict[str, object]]:
    output: List[Dict[str, object]] = []
    for raw in rows:
        model_prob = safe_float(raw.get("model_prob"))
        consensus_prob = safe_float(raw.get("consensus_prob"))
        adjusted_prob = safe_float(raw.get("adjusted_prob"))
        quarterfinal_prob = safe_float(raw.get("quarterfinal_prob"))
        semifinal_prob = safe_float(raw.get("semifinal_prob"))
        final_prob = safe_float(raw.get("final_prob"))
        watch_index = safe_float(raw.get("watch_index"))
        gap = model_prob - consensus_prob
        adjusted_gap = adjusted_prob - consensus_prob
        path_index = 0.50 * quarterfinal_prob + 0.32 * semifinal_prob + 0.18 * final_prob
        ceiling_index = 0.55 * semifinal_prob + 0.45 * final_prob
        value_score = 100.0 * max(
            0.0,
            min(
                1.0,
                0.36 * min(max(gap, adjusted_gap, 0.0) / 0.025, 1.0)
                + 0.28 * min(path_index / 0.24, 1.0)
                + 0.20 * min(ceiling_index / 0.16, 1.0)
                + 0.16 * min(watch_index / 100.0, 1.0),
            ),
        )
        label = label_for(raw, value_score, max(gap, adjusted_gap), path_index)
        output.append(
            {
                "team": raw.get("team", ""),
                "undervalued_label": label,
                "undervalued_value_score": round(value_score, 2),
                "model_minus_consensus": round(gap, 6),
                "adjusted_minus_consensus": round(adjusted_gap, 6),
                "path_index": round(path_index, 6),
                "ceiling_index": round(ceiling_index, 6),
                "model_prob": model_prob,
                "consensus_prob": consensus_prob,
                "adjusted_prob": adjusted_prob,
                "quarterfinal_prob": quarterfinal_prob,
                "semifinal_prob": semifinal_prob,
                "final_prob": final_prob,
                "watch_index": watch_index,
                "tier": raw.get("tier", ""),
                "action": action_for(label),
                "data_note": "Brecha calculada contra consenso externo disponible en el modelo; no reemplaza odds live reales.",
            }
        )
    return sorted(output, key=lambda row: (float(row["undervalued_value_score"]), float(row["path_index"])), reverse=True)


def write_rows(path: Path, rows: List[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rows = build_rows(read_rows(INPUT))
    write_rows(OUTPUT, rows)
    write_rows(SITE_OUTPUT, rows)
    print(f"Wrote {OUTPUT} ({len(rows)} rows)")
    print(f"Wrote {SITE_OUTPUT} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
