"""Runner F2.3: genera outputs/ratings/rating_adjustment_log.csv (ajuste HIPOTÉTICO).

Calcula, por (partido, equipo), qué haría el shrink de Elo hacia el FIFA-implied
SI estuviera activo, y lo registra con `applied_in_production` = estado real del
flag (False por defecto). NO aplica ningún ajuste al modelo, NO cambia
predicciones, NO toca expected_goals.py/pesos/lambdas/Penca. No usa resultados
futuros ni datos 2026 para ajustar parámetros.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date as _date

from worldcup2026.config import PARAMS  # noqa: E402
from worldcup2026.ratings.activity import (  # noqa: E402
    compute_activity_table,
    load_match_history,
)
from worldcup2026.ratings.staleness import (  # noqa: E402
    _clamp,
    assess_team_staleness,
    compute_pool_stats,
    staleness_shrunk_elo,
)

TEAMS_JSON = ROOT / "teams_2026.json"
RAW_RESULTS_CSV = ROOT / "data" / "international_results_raw.csv"
MARKET_ODDS_INPUT = ROOT / "data" / "market_odds_input.csv"
OUTPUT_CSV = ROOT / "outputs" / "ratings" / "rating_adjustment_log.csv"
DEFAULT_AS_OF = "2026-04-02"

LOG_COLUMNS = (
    "match_id", "team", "base_elo", "fifa_implied_elo", "staleness_score",
    "shrink_weight", "adjusted_elo", "shrink_target", "trigger", "reason",
    "applied_in_production", "captured_at_utc",
    "last_match_age_days", "recent_coverage_6m", "recent_coverage_12m",
    "official_matches_12m", "friendly_matches_12m", "anomalous_elo_jump", "activity_warning",
)

_ACTIVITY_KEYS = (
    "last_match_age_days", "recent_coverage_6m", "recent_coverage_12m",
    "official_matches_12m", "friendly_matches_12m", "anomalous_elo_jump", "activity_warning",
)


def parse_match_id(match_id: str) -> Optional[Tuple[str, str]]:
    rest = match_id
    if len(match_id) >= 10 and match_id[:8].isdigit() and match_id[8] == "_":
        rest = match_id[9:]
    if "_vs_" not in rest:
        return None
    home, _, away = rest.partition("_vs_")
    return home.replace("_", " ").strip(), away.replace("_", " ").strip()


def _load_qualified(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    teams = payload.get("teams", payload) if isinstance(payload, dict) else payload
    teams = teams if isinstance(teams, list) else list(teams.values())
    return [t for t in teams if isinstance(t, dict) and t.get("status") == "qualified"]


def _match_ids(path: Path):
    if not path.exists():
        return []
    seen = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            mid = (row.get("match_id") or "").strip()
            if mid and mid not in seen:
                seen.append(mid)
    return seen


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_adjustment_row(match_id: str, team_name: str, assess: dict, *, captured_at_utc: str) -> dict:
    base_elo = _num(assess.get("elo"))
    fifa_implied = _num(assess.get("fifa_implied_elo"))
    staleness = _num(assess.get("elo_staleness_score")) or 0.0
    w_fifa = PARAMS.elo_staleness_shrink_to_fifa_weight
    cap = PARAMS.elo_staleness_shrink_cap
    min_score = PARAMS.elo_staleness_min_score

    # Ajuste HIPOTÉTICO (ungated) solo para auditoría; el modelo NO lo usa.
    adjusted = base_elo
    frac = 0.0
    if base_elo is not None:
        adjusted = staleness_shrunk_elo(
            base_effective_elo=base_elo, fifa_implied_elo_value=fifa_implied,
            staleness=staleness, w_fifa=w_fifa, cap=cap, min_score=min_score, clamp=_clamp,
        )
        if fifa_implied is not None and staleness >= min_score:
            frac = _clamp(w_fifa * staleness, 0.0, cap)

    if fifa_implied is None:
        trigger, reason = "no_fifa", "sin FIFA: no se ajusta"
    elif staleness < min_score:
        trigger, reason = "elo_domina", "staleness por debajo del mínimo: Elo se mantiene"
    elif staleness >= PARAMS.elo_staleness_warning_threshold:
        trigger, reason = "staleness_shrink", f"staleness alto ({round(staleness,3)}): shrink hacia FIFA (warning fuerte)"
    else:
        trigger, reason = "staleness_shrink", f"staleness moderado ({round(staleness,3)}): shrink hacia FIFA"

    row = {
        "match_id": match_id,
        "team": team_name,
        "base_elo": base_elo if base_elo is not None else "",
        "fifa_implied_elo": round(fifa_implied, 3) if fifa_implied is not None else "",
        "staleness_score": round(staleness, 4),
        "shrink_weight": round(frac, 4),
        "adjusted_elo": round(adjusted, 3) if adjusted is not None else "",
        "shrink_target": "fifa_implied_elo",
        "trigger": trigger,
        "reason": reason,
        "applied_in_production": bool(PARAMS.elo_staleness_enabled),
        "captured_at_utc": captured_at_utc,
    }
    # Columnas de actividad (F2.4): se copian del assess si están; vacías si no.
    for key in _ACTIVITY_KEYS:
        row[key] = assess.get(key, "")
    return row


def _as_of():
    try:
        payload = json.loads(TEAMS_JSON.read_text(encoding="utf-8"))
        raw = str((payload.get("meta", {}) or {}).get("as_of", DEFAULT_AS_OF))[:10]
        y, m, d = raw.split("-")
        return _date(int(y), int(m), int(d))
    except Exception:
        y, m, d = DEFAULT_AS_OF.split("-")
        return _date(int(y), int(m), int(d))


def build_rows(captured_at_utc: Optional[str] = None):
    captured_at_utc = captured_at_utc or datetime.now(timezone.utc).isoformat()
    qualified = _load_qualified(TEAMS_JSON)
    pool = [t for t in qualified if t.get("elo") and t.get("fifa_points")]
    pool_stats = compute_pool_stats(pool)
    by_name = {t.get("name"): t for t in qualified}
    activity_table = {}
    if RAW_RESULTS_CSV.exists():
        activity_table = compute_activity_table(load_match_history(RAW_RESULTS_CSV), as_of_date=_as_of())
    cache: Dict[str, dict] = {}

    def assess(name):
        if name not in cache and name in by_name:
            cache[name] = assess_team_staleness(
                by_name[name], pool_stats=pool_stats, activity=activity_table.get(name))
        return cache.get(name)

    rows = []
    for match_id in _match_ids(MARKET_ODDS_INPUT):
        names = parse_match_id(match_id)
        if names is None:
            continue
        for team_name in names:
            a = assess(team_name)
            if a is None:
                print(f"[skip equipo no en pool] {match_id}/{team_name}", file=sys.stderr)
                continue
            rows.append(build_adjustment_row(match_id, team_name, a, captured_at_utc=captured_at_utc))
    return rows


def write_rows(rows, output_path: Path = OUTPUT_CSV):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(LOG_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in LOG_COLUMNS})


def main(argv=None) -> int:
    if not TEAMS_JSON.exists():
        print(f"ERROR: no existe {TEAMS_JSON}", file=sys.stderr)
        return 2
    rows = build_rows()
    write_rows(rows)
    print(f"Log escrito en {OUTPUT_CSV} ({len(rows)} filas equipo-partido)")
    print(f"elo_staleness_enabled (flag): {PARAMS.elo_staleness_enabled}")
    print(f"applied_in_production en todas las filas: {bool(PARAMS.elo_staleness_enabled)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
