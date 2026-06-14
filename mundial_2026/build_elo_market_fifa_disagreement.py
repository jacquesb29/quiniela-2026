"""Runner F2.2: genera outputs/ratings/elo_market_fifa_disagreement.csv.

Combina Elo + FIFA-implied + staleness (F2.1) + mercado (F1) por partido. SOLO
diagnostica: NO cambia picks ni predicciones, NO toca el modelo, pesos, lambdas,
metodología ni Penca, NO aplica ajuste. La lista de partidos sale de
data/market_odds_input.csv; el mercado se enlaza desde outputs/market.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.ratings.market_fifa_disagreement import (  # noqa: E402
    DISAGREEMENT_COLUMNS,
    build_match_disagreement_row,
)
from worldcup2026.ratings.staleness import assess_team_staleness, compute_pool_stats  # noqa: E402

TEAMS_JSON = ROOT / "teams_2026.json"
MARKET_ODDS_INPUT = ROOT / "data" / "market_odds_input.csv"
MARKET_GAP_CSV = ROOT / "outputs" / "market" / "market_model_gap.csv"
MARKET_DECISION_CSV = ROOT / "outputs" / "market" / "market_decision_log.csv"
OUTPUT_CSV = ROOT / "outputs" / "ratings" / "elo_market_fifa_disagreement.csv"

ADJUSTMENT_APPLIED = False  # F2.2 no aplica ningún ajuste


def parse_match_id(match_id: str) -> Optional[Tuple[str, str]]:
    rest = match_id
    if len(match_id) >= 10 and match_id[:8].isdigit() and match_id[8] == "_":
        rest = match_id[9:]
    if "_vs_" not in rest:
        return None
    home, _, away = rest.partition("_vs_")
    return home.replace("_", " ").strip(), away.replace("_", " ").strip()


def _read_csv_map(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {(r.get("match_id") or "").strip(): r for r in csv.DictReader(handle)}


def _load_qualified(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    teams = payload.get("teams", payload) if isinstance(payload, dict) else payload
    teams = teams if isinstance(teams, list) else list(teams.values())
    return [t for t in teams if isinstance(t, dict) and t.get("status") == "qualified"]


def _match_ids_from_input(path: Path):
    if not path.exists():
        return []
    seen = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            mid = (row.get("match_id") or "").strip()
            if mid and mid not in seen:
                seen.append(mid)
    return seen


def build_rows():
    qualified = _load_qualified(TEAMS_JSON)
    pool = [t for t in qualified if t.get("elo") and t.get("fifa_points")]
    pool_stats = compute_pool_stats(pool)
    by_name = {t.get("name"): t for t in qualified}
    assess_cache: Dict[str, dict] = {}

    def assess(name):
        if name not in assess_cache:
            team = by_name.get(name)
            assess_cache[name] = assess_team_staleness(team, pool_stats=pool_stats) if team else None
        return assess_cache[name]

    gap_map = _read_csv_map(MARKET_GAP_CSV)
    decision_map = _read_csv_map(MARKET_DECISION_CSV)

    rows = []
    for match_id in _match_ids_from_input(MARKET_ODDS_INPUT):
        names = parse_match_id(match_id)
        if names is None:
            print(f"[skip match_id no parseable] {match_id}", file=sys.stderr)
            continue
        team_a, team_b = names
        assess_a, assess_b = assess(team_a), assess(team_b)
        if assess_a is None or assess_b is None:
            print(f"[skip equipos no en pool] {match_id}", file=sys.stderr)
            continue
        gap = gap_map.get(match_id, {})
        decision = decision_map.get(match_id, {})
        rows.append(build_match_disagreement_row(
            match_id=match_id, team_a=team_a, team_b=team_b,
            assess_a=assess_a, assess_b=assess_b,
            market_pick=gap.get("market_pick"),
            model_pick=gap.get("model_pick"),
            market_gap_status=gap.get("gap_status"),
            final_market_decision=decision.get("action"),
        ))
    return rows


def write_rows(rows, output_path: Path = OUTPUT_CSV):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DISAGREEMENT_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in DISAGREEMENT_COLUMNS})


def main(argv=None) -> int:
    if not TEAMS_JSON.exists():
        print(f"ERROR: no existe {TEAMS_JSON}", file=sys.stderr)
        return 2
    rows = build_rows()
    write_rows(rows)
    sev = {"strong": 0, "medium": 0, "low": 0}
    for r in rows:
        sev[r["disagreement_severity"]] = sev.get(r["disagreement_severity"], 0) + 1
    print(f"Reporte escrito en {OUTPUT_CSV} ({len(rows)} partidos)")
    print(f"Severidad fuerte: {sev['strong']} | media: {sev['medium']} | baja: {sev['low']}")
    print(f"Ajuste aplicado a predicciones: {ADJUSTMENT_APPLIED} (F2.2 es solo diagnóstico)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
