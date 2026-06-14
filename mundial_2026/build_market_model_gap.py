"""Runner F1.3: genera outputs/market/market_model_gap.csv (modelo vs mercado).

Lee `outputs/market/market_implied_probabilities.csv` (mercado sin vig de F1.1) y la
predicción ACTUAL del modelo para cada partido, y calcula los gaps con
`worldcup2026.market.gap`.

Reglas respetadas:
- NO integra odds al modelo: la predicción del modelo se obtiene NEUTRAL (sin pasar
  ninguna señal de mercado a `MatchContext`).
- NO cambia picks ni toca pesos/lambdas/metodología/Penca.
- No inventa mercado: filas sin mercado suficiente quedan `gap_status=sin_muestra`.
- El modelo en vivo (teams_2026.json) es legítimo aquí: es predicción 2026, no el
  backtest histórico anti-leakage.

Nota: el archivo legado `market_model_gap.csv` (raíz) lo escribe el monolito; este
runner escribe en `outputs/market/market_model_gap.csv` para no pisarlo.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import modelo_quiniela_2026 as model  # noqa: E402
from worldcup2026.market.gap import GAP_COLUMNS, gap_report_to_row, model_vs_market_gap  # noqa: E402

MARKET_IMPLIED_CSV = ROOT / "outputs" / "market" / "market_implied_probabilities.csv"
GAP_OUTPUT_CSV = ROOT / "outputs" / "market" / "market_model_gap.csv"


def parse_match_id(match_id: str) -> Optional[Tuple[str, str]]:
    rest = match_id
    if len(match_id) >= 10 and match_id[:8].isdigit() and match_id[8] == "_":
        rest = match_id[9:]
    if "_vs_" not in rest:
        return None
    home, _, away = rest.partition("_vs_")
    return home.replace("_", " ").strip(), away.replace("_", " ").strip()


def model_prediction_for_match(match_id: str, teams) -> Optional[Dict[str, float]]:
    parsed = parse_match_id(match_id)
    if parsed is None:
        return None
    home_raw, away_raw = parsed
    try:
        home = model.resolve_team_name(home_raw, teams)
        away = model.resolve_team_name(away_raw, teams)
    except Exception:
        return None
    if home not in teams or away not in teams or home == away:
        return None
    # Predicción NEUTRAL, sin ninguna señal de mercado (no se integra odds al modelo).
    prediction = model.predict_match(teams, home, away, model.MatchContext(neutral=True))
    return {
        "prob_a": prediction.win_a,
        "prob_draw": prediction.draw,
        "prob_b": prediction.win_b,
        "lambda_a": prediction.expected_goals_a,
        "lambda_b": prediction.expected_goals_b,
    }


def _implied_from_row(row: Dict[str, str]) -> Dict[str, object]:
    return {
        "p_home": row.get("p_home"),
        "p_draw": row.get("p_draw"),
        "p_away": row.get("p_away"),
        "market_total_goals": row.get("market_total_goals"),
        "market_supremacy": row.get("market_supremacy"),
        "market_lambda_home": row.get("market_lambda_home"),
        "market_lambda_away": row.get("market_lambda_away"),
    }


def build_gap_rows(*, tv_mild: float = 0.08, tv_strong: float = 0.15):
    if not MARKET_IMPLIED_CSV.exists():
        print(f"[error] no existe {MARKET_IMPLIED_CSV}", file=sys.stderr)
        return []
    teams = model.load_teams()
    with MARKET_IMPLIED_CSV.open(newline="", encoding="utf-8") as handle:
        market_rows = list(csv.DictReader(handle))
    rows = []
    for market_row in market_rows:
        match_id = market_row.get("match_id", "")
        model_pred = model_prediction_for_match(match_id, teams)
        if model_pred is None:
            print(f"[skip sin modelo] {match_id}: equipos no resolubles", file=sys.stderr)
            continue
        report = model_vs_market_gap(
            model_pred, _implied_from_row(market_row),
            tv_mild=tv_mild, tv_strong=tv_strong, match_id=match_id,
        )
        rows.append(gap_report_to_row(report))
    return rows


def write_gap_csv(rows, output_path: str | Path = GAP_OUTPUT_CSV) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(GAP_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> int:
    rows = build_gap_rows()
    write_gap_csv(rows)
    calculable = sum(1 for r in rows if r["gap_status"] == "calculado")
    strong = sum(1 for r in rows if r["contradiction_severity"] == "strong")
    contradictions = sum(1 for r in rows if r["contradicts_market"])
    print(f"Filas escritas: {len(rows)} en {GAP_OUTPUT_CSV}")
    print(f"Con gap calculable (1X2): {calculable}")
    print(f"Contradicen al mercado: {contradictions} (fuertes: {strong})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
