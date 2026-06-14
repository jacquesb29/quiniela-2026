"""Runner F1.5: flujo T-60 y materialización de la recomendación prepartido.

Combina odds t60 (F1.1), gap modelo-mercado (F1.3), decisión (F1.4) y datos
manuales de alineación/bajas/portero (data/t60_inputs.csv) para refrescar la
recomendación con before/after. Demuestra la materialización alimentando las odds
a un MatchContext (blend fijo del modelo) sin reentrenar ni cambiar internals.

NO cambia pesos/lambdas/metodología/Penca, NO usa closing para decidir, NO inventa
odds, NO hace scraping. La predicción interna del modelo no se modifica: el T-60
produce recomendación operativa.

Salidas:
- outputs/market/last_hour_update.csv
- outputs/market/t60_decision_log.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import modelo_quiniela_2026 as model  # noqa: E402
from build_market_model_gap import model_prediction_for_match  # noqa: E402
from market_context_adapter import apply_market_to_context  # noqa: E402
from worldcup2026.market.devig import odds_to_implied  # noqa: E402
from worldcup2026.market.gap import argmax_outcome  # noqa: E402
from worldcup2026.market.odds_ingest import is_usable_for_decision, load_odds_input  # noqa: E402
from worldcup2026.market.t60 import (  # noqa: E402
    T60_DECISION_COLUMNS,
    load_t60_inputs,
    run_t60_for_match,
    t60_change_to_row,
)

ODDS_INPUT_CSV = ROOT / "data" / "market_odds_input.csv"
T60_INPUT_CSV = ROOT / "data" / "t60_inputs.csv"
LAST_HOUR_CSV = ROOT / "outputs" / "market" / "last_hour_update.csv"
T60_DECISION_CSV = ROOT / "outputs" / "market" / "t60_decision_log.csv"

LAST_HOUR_COLUMNS = (
    "match_id", "captured_at_utc", "odds_updated", "odds_snapshot_type",
    "lineup_confirmed", "lineup_changes", "injuries_confirmed", "starting_gk",
    "gk_changed", "relevant_changes", "recompute_done",
)


def _write_csv(path, columns, rows):
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> int:
    odds_snapshots = load_odds_input(ODDS_INPUT_CSV) if ODDS_INPUT_CSV.exists() else []
    t60_inputs = load_t60_inputs(T60_INPUT_CSV, odds_snapshots)
    teams = model.load_teams()

    t60_rows = []
    last_hour_rows = []
    changed_count = 0

    for inputs in t60_inputs:
        model_pred = model_prediction_for_match(inputs.match_id, teams)
        if model_pred is None:
            print(f"[skip sin modelo] {inputs.match_id}", file=sys.stderr)
            continue

        # "before" = pick del modelo solo (neutral), confianza base Media.
        prior_pick = argmax_outcome(model_pred["prob_a"], model_pred["prob_draw"], model_pred["prob_b"])
        prior_confidence = "Media"

        change = run_t60_for_match(
            match_id=inputs.match_id,
            model_pred=model_pred,
            t60_inputs=inputs,
            prior_pick=prior_pick,
            prior_confidence=prior_confidence,
            prev_implied=None,
        )
        t60_rows.append(t60_change_to_row(change))
        if change.changed:
            changed_count += 1

        # Materialización: alimentar odds t60 a un MatchContext (blend fijo del modelo).
        valid_odds = inputs.odds is not None and is_usable_for_decision(inputs.odds)
        recompute_done = False
        if valid_odds:
            implied = odds_to_implied(inputs.odds, require_prematch=True)
            if implied is not None:
                parsed = model_prediction_for_match  # ya validado arriba
                # Reconstruir nombres de equipo para predecir con contexto de mercado.
                from build_market_model_gap import parse_match_id
                names = parse_match_id(inputs.match_id)
                if names is not None:
                    try:
                        home = model.resolve_team_name(names[0], teams)
                        away = model.resolve_team_name(names[1], teams)
                        market_ctx = apply_market_to_context(model.MatchContext(neutral=True), implied)
                        # Predicción informada por mercado mediante el blend EXISTENTE del modelo.
                        model.predict_match(teams, home, away, market_ctx)
                        recompute_done = True
                    except Exception:
                        recompute_done = False

        last_hour_rows.append({
            "match_id": inputs.match_id,
            "captured_at_utc": inputs.captured_at_utc,
            "odds_updated": valid_odds,
            "odds_snapshot_type": (inputs.odds.snapshot_type if inputs.odds is not None else ""),
            "lineup_confirmed": inputs.lineup_confirmed,
            "lineup_changes": inputs.lineup_changes,
            "injuries_confirmed": ";".join(inputs.injuries_confirmed),
            "starting_gk": inputs.starting_gk or "",
            "gk_changed": inputs.gk_changed,
            "relevant_changes": change.trigger,
            "recompute_done": recompute_done,
        })

    _write_csv(T60_DECISION_CSV, T60_DECISION_COLUMNS, t60_rows)
    _write_csv(LAST_HOUR_CSV, LAST_HOUR_COLUMNS, last_hour_rows)

    kept = len(t60_rows) - changed_count
    print(f"Partidos procesados: {len(t60_rows)}")
    print(f"Picks cambiados: {changed_count}")
    print(f"Picks mantenidos: {kept}")
    for row in t60_rows:
        if row["changed"]:
            print(f"  CAMBIO {row['match_id']}: {row['pick_before']} -> {row['pick_after']} "
                  f"(trigger={row['trigger']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
