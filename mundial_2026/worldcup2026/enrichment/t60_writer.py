"""Escritor de data/t60_inputs.csv desde enriquecimiento confirmado.

Solo escribe filas cuando hay alineación confirmada. Preserva filas manuales
existentes (fallback). No rellena nada si no hay datos confiables.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from .models import EnrichmentRecord

ROOT = Path(__file__).resolve().parents[2]
T60_INPUT = ROOT / "data" / "t60_inputs.csv"

T60_COLUMNS = ("match_id", "captured_at_utc", "lineup_confirmed", "lineup_changes",
               "injuries_confirmed", "starting_gk", "gk_changed", "notes")


def _read_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as h:
        return {r.get("match_id"): r for r in csv.DictReader(h)}


def update_t60(records: List[EnrichmentRecord], path: Path = T60_INPUT, dry_run: bool = False):
    """Upsert de filas confirmadas. Devuelve (written_count, kept_count)."""
    existing = _read_existing(path)
    written = 0
    for rec in records:
        if not rec.lineup_confirmed:
            continue  # sin confirmación → no se toca (fallback manual)
        row = existing.get(rec.match_id, {})
        row.update({
            "match_id": rec.match_id,
            "captured_at_utc": rec.captured_at_utc,
            "lineup_confirmed": "true",
            "lineup_changes": row.get("lineup_changes", "") or "",
            "injuries_confirmed": str(rec.injuries_confirmed) if rec.injuries_confirmed else "",
            "starting_gk": rec.starting_gk or "",
            "gk_changed": "true" if rec.gk_changed else "false",
            "notes": "auto-enrichment (alineación confirmada)",
        })
        existing[rec.match_id] = row
        written += 1

    if dry_run:
        return written, len(existing) - written

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(T60_COLUMNS), lineterminator="\n")
        w.writeheader()
        for mid, row in existing.items():
            w.writerow({c: row.get(c, "") for c in T60_COLUMNS})
    tmp.replace(path)
    return written, len(existing) - written
