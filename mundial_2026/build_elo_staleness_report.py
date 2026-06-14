"""Runner F2.1: genera outputs/ratings/elo_staleness_report.csv.

Lee teams_2026.json (standings), calcula fifa_implied_elo y elo_staleness_score
(solo señal FIFA disponible; edad/cobertura/salto requieren state y quedan vacías),
y escribe el reporte de auditoría. NO aplica ningún ajuste, NO toca el modelo,
pesos, lambdas, metodología ni Penca. No usa mercado ni resultados posteriores.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.ratings.activity import (  # noqa: E402
    activity_level,
    compute_activity_table,
    load_match_history,
)
from worldcup2026.ratings.staleness import (  # noqa: E402
    REPORT_COLUMNS,
    assess_team_staleness,
    compute_pool_stats,
)

TEAMS_JSON = ROOT / "teams_2026.json"
RAW_RESULTS_CSV = ROOT / "data" / "international_results_raw.csv"
OUTPUT_CSV = ROOT / "outputs" / "ratings" / "elo_staleness_report.csv"

# F2.1/F2.4 NO aplican ningún ajuste ni activan shrink: solo diagnostican.
ADJUSTMENT_APPLIED = False
# Fecha de evaluación = snapshot pre-torneo (teams meta as_of). Anti-leakage: la
# actividad usa SOLO partidos anteriores -> excluye todo el Mundial 2026 (posterior).
DEFAULT_AS_OF = "2026-04-02"


def _as_of_date(payload) -> date:
    raw = (payload.get("meta", {}) or {}).get("as_of", DEFAULT_AS_OF) if isinstance(payload, dict) else DEFAULT_AS_OF
    raw = str(raw)[:10]
    try:
        y, m, d = raw.split("-")
        return date(int(y), int(m), int(d))
    except ValueError:
        y, m, d = DEFAULT_AS_OF.split("-")
        return date(int(y), int(m), int(d))


def load_payload(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def qualified_teams(payload):
    teams = payload.get("teams", payload) if isinstance(payload, dict) else payload
    teams = teams if isinstance(teams, list) else list(teams.values())
    return [t for t in teams if isinstance(t, dict) and t.get("status") == "qualified"]


def build_report_rows(teams, activity_table):
    pool = [t for t in teams if t.get("elo") and t.get("fifa_points")]
    pool_stats = compute_pool_stats(pool)
    rows = []
    for team in sorted(teams, key=lambda t: str(t.get("name", ""))):
        activity = activity_table.get(team.get("name"))
        assessed = assess_team_staleness(team, pool_stats=pool_stats, activity=activity)
        assessed["_activity_level"] = activity_level(activity)
        rows.append(assessed)
    return rows


def write_report(rows, output_path: Path = OUTPUT_CSV) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REPORT_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in REPORT_COLUMNS})


def main(argv=None) -> int:
    if not TEAMS_JSON.exists():
        print(f"ERROR: no existe {TEAMS_JSON}", file=sys.stderr)
        return 2
    payload = load_payload(TEAMS_JSON)
    teams = qualified_teams(payload)
    as_of = _as_of_date(payload)
    activity_table = {}
    if RAW_RESULTS_CSV.exists():
        activity_table = compute_activity_table(load_match_history(RAW_RESULTS_CSV), as_of_date=as_of)
    else:
        print(f"AVISO: no existe {RAW_RESULTS_CSV}; staleness sin actividad reciente", file=sys.stderr)
    rows = build_report_rows(teams, activity_table)
    write_report(rows)
    buckets = {"alto": 0, "medio": 0, "bajo": 0}
    activity_buckets = {"alta": 0, "media": 0, "baja": 0}
    for row in rows:
        buckets[row["_bucket"]] = buckets.get(row["_bucket"], 0) + 1
        activity_buckets[row["_activity_level"]] = activity_buckets.get(row["_activity_level"], 0) + 1
    print(f"Reporte escrito en {OUTPUT_CSV} ({len(rows)} equipos), as_of={as_of}")
    print(f"Staleness alto: {buckets['alto']} | medio: {buckets['medio']} | bajo: {buckets['bajo']}")
    print(f"Actividad alta: {activity_buckets['alta']} | media: {activity_buckets['media']} | baja: {activity_buckets['baja']}")
    print(f"Ajuste aplicado a predicciones: {ADJUSTMENT_APPLIED} (F2.4 es solo diagnóstico)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
