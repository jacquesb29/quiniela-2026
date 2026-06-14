"""Re-derivación walk-forward independiente de Elo prepartido (F0.4b).

Auditoría anti-leakage: reconstruye el Elo prepartido recorriendo los partidos en
orden cronológico, guardando el Elo de ambos equipos ANTES de cada partido y
actualizándolo SOLO DESPUÉS. Nunca usa información futura. Sirve para verificar
de forma independiente los valores `elo_*_pre` almacenados en
`data/historical_matches.csv`.

No toca el modelo, ni pesos, ni lambdas, ni la capa Penca. Es solo auditoría.

Notas de modelado (documentadas):
- Equipos nuevos arrancan en `initial_elo` (neutral, por defecto 1500).
- Localía/sede: el `home_edge` es configurable y por defecto 0.0, replicando que
  el constructor original NO aplica ventaja de localía en la actualización de Elo
  (el flag `neutral` se conserva en los datos pero no entra al rating).
- `k_factor` es configurable; `k_by_tournament` permite replicar el esquema por
  torneo del constructor original para una verificación exacta.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

DEFAULT_INITIAL_ELO = 1500.0
DEFAULT_K = 24.0

# Esquema por torneo equivalente al del constructor original (para verificación).
ORIGINAL_K_BY_TOURNAMENT = {
    "FIFA World Cup": 42.0,
    "UEFA Euro": 42.0,
    "Copa América": 42.0,
}
ORIGINAL_SELECTED = {"FIFA World Cup", "UEFA Euro", "Copa América"}
ORIGINAL_START_YEAR = 1950


def _expected_score(elo_a: float, elo_b: float, home_edge: float = 0.0) -> float:
    return 1.0 / (1.0 + 10.0 ** (-((elo_a - elo_b) + home_edge) / 400.0))


def _margin_multiplier(goals_a: int, goals_b: int, elo_diff: float) -> float:
    margin = abs(goals_a - goals_b)
    if margin <= 1:
        return 1.0
    return math.log(margin + 1.0) * (2.2 / (2.2 + 0.001 * abs(elo_diff)))


def _k_for(
    tournament: str,
    *,
    k_factor: float,
    k_by_tournament: Optional[Mapping[str, float]],
    replicate_original: bool,
) -> float:
    if k_by_tournament and tournament in k_by_tournament:
        return float(k_by_tournament[tournament])
    if replicate_original:
        low = tournament.lower()
        if "qualif" in low:
            return 30.0
        if "friendly" in low:
            return 12.0
        return 22.0
    return float(k_factor)


def _match_id(date_str: str, team_a: str, team_b: str) -> str:
    return f"{date_str.replace('-', '')}_{team_a}_vs_{team_b}".replace(" ", "_")


def _parse_int(value: object) -> Optional[int]:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def rederive_walk_forward_elo(
    raw_rows: Sequence[Mapping[str, object]],
    *,
    initial_elo: float = DEFAULT_INITIAL_ELO,
    k_factor: float = DEFAULT_K,
    k_by_tournament: Optional[Mapping[str, float]] = None,
    use_margin: bool = False,
    home_edge: float = 0.0,
    replicate_original: bool = False,
    selected_tournaments: Optional[set] = None,
    start_year: Optional[int] = None,
) -> Dict[str, Tuple[float, float]]:
    """Devuelve {match_id: (elo_a_pre, elo_b_pre)} para los partidos seleccionados.

    Recorre TODOS los partidos del raw en orden de fecha y actualiza el Elo con
    cada uno (igual que el constructor original), pero solo reporta el Elo
    prepartido de los partidos seleccionados (por defecto Mundial/Euro/Copa
    América desde `start_year`). El Elo se guarda ANTES y se actualiza DESPUÉS.
    """

    ordered = sorted(raw_rows, key=lambda r: str(r.get("date", "")))
    ratings: defaultdict[str, float] = defaultdict(lambda: float(initial_elo))
    out: Dict[str, Tuple[float, float]] = {}

    for raw in ordered:
        team_a = str(raw.get("home_team", "")).strip()
        team_b = str(raw.get("away_team", "")).strip()
        if not team_a or not team_b:
            continue
        goals_a = _parse_int(raw.get("home_score"))
        goals_b = _parse_int(raw.get("away_score"))
        if goals_a is None or goals_b is None:
            continue
        date_str = str(raw.get("date", "")).strip()
        if not date_str:
            continue
        try:
            year = datetime.strptime(date_str, "%Y-%m-%d").year
        except ValueError:
            continue
        tournament = str(raw.get("tournament", "")).strip()

        elo_a_pre = ratings[team_a]
        elo_b_pre = ratings[team_b]

        is_selected = True
        if selected_tournaments is not None:
            is_selected = tournament in selected_tournaments and (
                start_year is None or year >= start_year
            )
        if is_selected:
            out[_match_id(date_str, team_a, team_b)] = (elo_a_pre, elo_b_pre)

        # Actualización SOLO después de registrar el prepartido (anti-leakage).
        expected_a = _expected_score(elo_a_pre, elo_b_pre, home_edge)
        k = _k_for(
            tournament,
            k_factor=k_factor,
            k_by_tournament=k_by_tournament,
            replicate_original=replicate_original,
        )
        mult = _margin_multiplier(goals_a, goals_b, elo_a_pre - elo_b_pre) if (use_margin or replicate_original) else 1.0
        actual_a = 1.0 if goals_a > goals_b else (0.5 if goals_a == goals_b else 0.0)
        delta = k * mult * (actual_a - expected_a)
        ratings[team_a] = elo_a_pre + delta
        ratings[team_b] = elo_b_pre - delta

    return out


def _safe_float(value: object) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_elo_comparison_rows(
    original_rows: Sequence[Mapping[str, object]],
    rederived: Mapping[str, Tuple[float, float]],
) -> List[Dict[str, object]]:
    """Une filas originales (con `elo_*_pre`) con la re-derivación por match_id."""

    rows: List[Dict[str, object]] = []
    for original in original_rows:
        mid = str(original.get("match_id") or "")
        orig_a = _safe_float(original.get("elo_a_pre"))
        orig_b = _safe_float(original.get("elo_b_pre"))
        re = rederived.get(mid)
        if re is None:
            status = "sin_rederivado"
            re_a = re_b = None
        elif orig_a is None or orig_b is None:
            status = "sin_original"
            re_a, re_b = re
        else:
            re_a, re_b = re
            status = "comparado"
        rows.append({
            "match_id": mid,
            "date": original.get("date", ""),
            "team_a": original.get("team_a", ""),
            "team_b": original.get("team_b", ""),
            "elo_a_pre_original": orig_a if orig_a is not None else "",
            "elo_b_pre_original": orig_b if orig_b is not None else "",
            "elo_a_pre_rederived": re_a if re_a is not None else "",
            "elo_b_pre_rederived": re_b if re_b is not None else "",
            "elo_delta_a": (orig_a - re_a) if (orig_a is not None and re_a is not None) else "",
            "elo_delta_b": (orig_b - re_b) if (orig_b is not None and re_b is not None) else "",
            "elo_source_status": status,
        })
    return rows


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    if sxx <= 0.0 or syy <= 0.0:
        return None
    return sxy / math.sqrt(sxx * syy)


def elo_audit_summary(
    comparison_rows: Sequence[Mapping[str, object]],
    *,
    code_audit_walk_forward: bool,
    corr_threshold: float = 0.99,
    max_abs_delta_threshold: float = 5.0,
) -> Dict[str, object]:
    """Resume la comparación y decide si persiste advertencia de leakage."""

    compared = [r for r in comparison_rows if r.get("elo_source_status") == "comparado"]
    orig_a = [float(r["elo_a_pre_original"]) for r in compared]
    re_a = [float(r["elo_a_pre_rederived"]) for r in compared]
    orig_b = [float(r["elo_b_pre_original"]) for r in compared]
    re_b = [float(r["elo_b_pre_rederived"]) for r in compared]
    deltas = [abs(float(r["elo_delta_a"])) for r in compared] + [abs(float(r["elo_delta_b"])) for r in compared]

    corr_a = pearson(orig_a, re_a)
    corr_b = pearson(orig_b, re_b)
    mean_abs_delta = (sum(deltas) / len(deltas)) if deltas else None
    max_abs_delta = max(deltas) if deltas else None

    corr_ok = corr_a is not None and corr_b is not None and corr_a >= corr_threshold and corr_b >= corr_threshold
    delta_ok = max_abs_delta is not None and max_abs_delta <= max_abs_delta_threshold
    leakage_warning = not (code_audit_walk_forward and corr_ok and delta_ok)

    return {
        "code_audit_walk_forward": code_audit_walk_forward,
        "n_compared": len(compared),
        "pearson_elo_a": corr_a,
        "pearson_elo_b": corr_b,
        "mean_abs_delta": mean_abs_delta,
        "max_abs_delta": max_abs_delta,
        "corr_threshold": corr_threshold,
        "max_abs_delta_threshold": max_abs_delta_threshold,
        "leakage_warning": leakage_warning,
    }


__all__ = [
    "ORIGINAL_K_BY_TOURNAMENT",
    "ORIGINAL_SELECTED",
    "ORIGINAL_START_YEAR",
    "rederive_walk_forward_elo",
    "build_elo_comparison_rows",
    "elo_audit_summary",
    "pearson",
]
