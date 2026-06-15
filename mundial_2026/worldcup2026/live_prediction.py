"""Reproduce la predicción de producción para un partido finalizado del feed.

Importa el monolito de forma PEREZOSA (dentro de la función) para que importar
este módulo no arrastre el modelo completo. Reconstruye el contexto REAL del
partido (``context_from_fixture``) y devuelve modal + Penca + probabilidades +
goles esperados, reproduciendo exactamente los picks de producción. No altera
nada: solo lee.
"""

from __future__ import annotations

from typing import Optional


def load_teams():
    import modelo_quiniela_2026 as M
    return M.load_teams()


def predict_record(record: dict, teams=None) -> Optional[dict]:
    """``record`` proviene de results_ingest.finalized_records (modo feed)."""
    fx = record.get("fixture")
    if fx is None:
        return None
    import modelo_quiniela_2026 as M
    teams = teams or M.load_teams()
    ctx = M.context_from_fixture(fx, teams)
    pred = M.predict_match(teams, fx["team_a"], fx["team_b"], ctx=ctx)
    modal = pred.exact_scores[0][0]
    penca = str(M.penca_ovacion_top_score(pred)["score"])
    actual = record["actual_score"]
    return {
        "prediction": pred,
        "modal": modal,
        "penca": penca,
        "win_a": pred.win_a, "draw": pred.draw, "win_b": pred.win_b,
        "xg_a": pred.expected_goals_a, "xg_b": pred.expected_goals_b,
        "model_points": M.realized_penca_points_for_score(modal, actual),
        "penca_points": M.realized_penca_points_for_score(penca, actual),
    }
