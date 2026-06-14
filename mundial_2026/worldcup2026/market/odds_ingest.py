"""Ingesta manual de odds prepartido (F1.1).

Carga `data/market_odds_input.csv` (manual-first, sin scraping), preserva los
tokens de cuota tal cual se cargaron (auditable) y ofrece conversión a decimal y
validaciones anti-leakage. NO consume el modelo ni lo modifica.

Reglas:
- No inventa ni autocompleta odds faltantes (celdas vacías -> None).
- `captured_at_utc`, `kickoff_utc`, `source`, `odds_format` son obligatorios.
- `captured_at_utc` debe ser anterior a `kickoff_utc`.
- `snapshot_type=closing` no es utilizable para decisiones prepartido.
- Cuotas decimales <= 1.0 son inválidas.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

VALID_SNAPSHOT_TYPES = ("opening", "t60", "closing")
VALID_ODDS_FORMATS = ("decimal", "american", "fractional")
PREMATCH_DECISION_TYPES = ("opening", "t60")

# Columnas de entrada en orden fijo.
INPUT_COLUMNS = (
    "match_id", "kickoff_utc", "captured_at_utc", "snapshot_type", "source", "odds_format",
    "odds_home", "odds_draw", "odds_away",
    "total_line", "odds_over", "odds_under",
    "handicap_line", "odds_hcap_home", "odds_hcap_away",
    "tt_home_line", "odds_tt_home_over", "odds_tt_home_under",
    "tt_away_line", "odds_tt_away_over", "odds_tt_away_under",
    "note",
)


@dataclass(frozen=True)
class OddsSnapshot:
    match_id: str
    kickoff_utc: str
    captured_at_utc: str
    snapshot_type: str
    source: str
    odds_format: str
    # Cuotas como TOKEN crudo (str) para preservar el formato original auditable.
    odds_home: Optional[str] = None
    odds_draw: Optional[str] = None
    odds_away: Optional[str] = None
    total_line: Optional[float] = None
    odds_over: Optional[str] = None
    odds_under: Optional[str] = None
    handicap_line: Optional[float] = None
    odds_hcap_home: Optional[str] = None
    odds_hcap_away: Optional[str] = None
    tt_home_line: Optional[float] = None
    odds_tt_home_over: Optional[str] = None
    odds_tt_home_under: Optional[str] = None
    tt_away_line: Optional[float] = None
    odds_tt_away_over: Optional[str] = None
    odds_tt_away_under: Optional[str] = None
    note: str = ""


def _clean(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_line(value: object) -> Optional[float]:
    text = _clean(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_decimal_odds(value: object, fmt: str) -> Optional[float]:
    """Convierte una cuota a decimal. None si vacía/ inválida.

    - decimal: float directo; <= 1.0 es inválido (None).
    - american: +M -> 1 + M/100 ; -M -> 1 + 100/|M|.
    - fractional: 'a/b' -> 1 + a/b.
    Formato desconocido -> ValueError claro.
    """

    token = _clean(value)
    if token is None:
        return None
    if fmt == "decimal":
        try:
            decimal = float(token)
        except ValueError:
            return None
        return decimal if decimal > 1.0 else None
    if fmt == "american":
        try:
            american = float(token)
        except ValueError:
            return None
        if american == 0:
            return None
        decimal = 1.0 + (american / 100.0 if american > 0 else 100.0 / abs(american))
        return decimal if decimal > 1.0 else None
    if fmt == "fractional":
        if "/" not in token:
            return None
        num, _, den = token.partition("/")
        try:
            a = float(num)
            b = float(den)
        except ValueError:
            return None
        if b == 0:
            return None
        decimal = 1.0 + a / b
        return decimal if decimal > 1.0 else None
    raise ValueError(f"odds_format no soportado: {fmt!r}")


def _parse_dt(value: str) -> Optional[datetime]:
    text = _clean(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_odds_input(path: str | Path) -> List[OddsSnapshot]:
    """Lee el CSV manual y deduplica por (match_id, snapshot_type) con captured_at máximo."""

    rows: List[OddsSnapshot] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            rows.append(
                OddsSnapshot(
                    match_id=_clean(raw.get("match_id")) or "",
                    kickoff_utc=_clean(raw.get("kickoff_utc")) or "",
                    captured_at_utc=_clean(raw.get("captured_at_utc")) or "",
                    snapshot_type=(_clean(raw.get("snapshot_type")) or "").lower(),
                    source=_clean(raw.get("source")) or "",
                    odds_format=(_clean(raw.get("odds_format")) or "").lower(),
                    odds_home=_clean(raw.get("odds_home")),
                    odds_draw=_clean(raw.get("odds_draw")),
                    odds_away=_clean(raw.get("odds_away")),
                    total_line=_safe_line(raw.get("total_line")),
                    odds_over=_clean(raw.get("odds_over")),
                    odds_under=_clean(raw.get("odds_under")),
                    handicap_line=_safe_line(raw.get("handicap_line")),
                    odds_hcap_home=_clean(raw.get("odds_hcap_home")),
                    odds_hcap_away=_clean(raw.get("odds_hcap_away")),
                    tt_home_line=_safe_line(raw.get("tt_home_line")),
                    odds_tt_home_over=_clean(raw.get("odds_tt_home_over")),
                    odds_tt_home_under=_clean(raw.get("odds_tt_home_under")),
                    tt_away_line=_safe_line(raw.get("tt_away_line")),
                    odds_tt_away_over=_clean(raw.get("odds_tt_away_over")),
                    odds_tt_away_under=_clean(raw.get("odds_tt_away_under")),
                    note=_clean(raw.get("note")) or "",
                )
            )
    # Deduplicar por (match_id, snapshot_type) -> captured_at_utc más reciente.
    best: Dict[tuple, OddsSnapshot] = {}
    for snap in rows:
        key = (snap.match_id, snap.snapshot_type)
        current = best.get(key)
        if current is None or (snap.captured_at_utc or "") > (current.captured_at_utc or ""):
            best[key] = snap
    return list(best.values())


def is_prematch(snapshot: OddsSnapshot) -> bool:
    captured = _parse_dt(snapshot.captured_at_utc)
    kickoff = _parse_dt(snapshot.kickoff_utc)
    if captured is None or kickoff is None:
        return False
    return captured < kickoff


def has_minimum_market(snapshot: OddsSnapshot) -> bool:
    """Mercado mínimo utilizable = 1X2 completo y convertible a decimal."""

    fmt = snapshot.odds_format
    if fmt not in VALID_ODDS_FORMATS:
        return False
    try:
        trio = [
            to_decimal_odds(snapshot.odds_home, fmt),
            to_decimal_odds(snapshot.odds_draw, fmt),
            to_decimal_odds(snapshot.odds_away, fmt),
        ]
    except ValueError:
        return False
    return all(value is not None for value in trio)


def is_usable_for_decision(snapshot: OddsSnapshot) -> bool:
    """Apto para decisión prepartido: prematch, no closing y con 1X2 completo."""

    return (
        not validate_odds_snapshot(snapshot)
        and is_prematch(snapshot)
        and snapshot.snapshot_type in PREMATCH_DECISION_TYPES
        and has_minimum_market(snapshot)
    )


def coverage_flags(snapshot: OddsSnapshot) -> Dict[str, bool]:
    fmt = snapshot.odds_format if snapshot.odds_format in VALID_ODDS_FORMATS else "decimal"

    def both(a, b) -> bool:
        try:
            return to_decimal_odds(a, fmt) is not None and to_decimal_odds(b, fmt) is not None
        except ValueError:
            return False

    return {
        "1x2": has_minimum_market(snapshot),
        "ou": snapshot.total_line is not None and both(snapshot.odds_over, snapshot.odds_under),
        "handicap": snapshot.handicap_line is not None and both(snapshot.odds_hcap_home, snapshot.odds_hcap_away),
        "tt_home": snapshot.tt_home_line is not None and both(snapshot.odds_tt_home_over, snapshot.odds_tt_home_under),
        "tt_away": snapshot.tt_away_line is not None and both(snapshot.odds_tt_away_over, snapshot.odds_tt_away_under),
    }


def validate_odds_snapshot(snapshot: OddsSnapshot) -> List[str]:
    """Devuelve lista de errores (vacía = válido). No lanza."""

    errors: List[str] = []
    if not snapshot.match_id:
        errors.append("match_id obligatorio")
    if not snapshot.source:
        errors.append("source obligatorio")
    if not snapshot.kickoff_utc:
        errors.append("kickoff_utc obligatorio")
    if not snapshot.captured_at_utc:
        errors.append("captured_at_utc obligatorio")
    if snapshot.snapshot_type not in VALID_SNAPSHOT_TYPES:
        errors.append(f"snapshot_type inválido: {snapshot.snapshot_type!r}")
    if snapshot.odds_format not in VALID_ODDS_FORMATS:
        errors.append(f"odds_format obligatorio/ inválido: {snapshot.odds_format!r}")
        return errors  # sin formato no se pueden validar cuotas

    captured = _parse_dt(snapshot.captured_at_utc)
    kickoff = _parse_dt(snapshot.kickoff_utc)
    if snapshot.captured_at_utc and captured is None:
        errors.append("captured_at_utc no es fecha ISO válida")
    if snapshot.kickoff_utc and kickoff is None:
        errors.append("kickoff_utc no es fecha ISO válida")
    if captured is not None and kickoff is not None and not captured < kickoff:
        errors.append("captured_at_utc debe ser anterior a kickoff_utc")

    fmt = snapshot.odds_format
    odds_fields = [
        ("odds_home", snapshot.odds_home), ("odds_draw", snapshot.odds_draw), ("odds_away", snapshot.odds_away),
        ("odds_over", snapshot.odds_over), ("odds_under", snapshot.odds_under),
        ("odds_hcap_home", snapshot.odds_hcap_home), ("odds_hcap_away", snapshot.odds_hcap_away),
        ("odds_tt_home_over", snapshot.odds_tt_home_over), ("odds_tt_home_under", snapshot.odds_tt_home_under),
        ("odds_tt_away_over", snapshot.odds_tt_away_over), ("odds_tt_away_under", snapshot.odds_tt_away_under),
    ]
    for name, token in odds_fields:
        if token is not None and to_decimal_odds(token, fmt) is None:
            errors.append(f"cuota inválida en {name}: {token!r} (formato {fmt})")

    # Coherencia de mercados de dos vías (no autocompletar el lado faltante).
    pairs = [
        ("over/under", snapshot.odds_over, snapshot.odds_under),
        ("handicap", snapshot.odds_hcap_home, snapshot.odds_hcap_away),
        ("team_total_home", snapshot.odds_tt_home_over, snapshot.odds_tt_home_under),
        ("team_total_away", snapshot.odds_tt_away_over, snapshot.odds_tt_away_under),
    ]
    for label, a, b in pairs:
        if (a is None) != (b is None):
            errors.append(f"mercado {label} incompleto (un lado presente, el otro vacío)")

    if snapshot.total_line is not None and snapshot.total_line <= 0:
        errors.append("total_line debe ser > 0")
    return errors


__all__ = [
    "VALID_SNAPSHOT_TYPES",
    "VALID_ODDS_FORMATS",
    "INPUT_COLUMNS",
    "OddsSnapshot",
    "to_decimal_odds",
    "load_odds_input",
    "validate_odds_snapshot",
    "has_minimum_market",
    "is_prematch",
    "is_usable_for_decision",
    "coverage_flags",
]
