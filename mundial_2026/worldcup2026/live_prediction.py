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


def predict_fixture(fx: dict, teams=None) -> Optional[dict]:
    """Predice un partido del feed (próximo o finalizado) reconstruyendo su
    contexto real. Devuelve None si algún equipo no está en el roster (p. ej.
    placeholders de eliminatorias). No requiere marcador real."""
    if fx is None:
        return None
    import modelo_quiniela_2026 as M
    teams = teams or M.load_teams()
    if fx.get("team_a") not in teams or fx.get("team_b") not in teams:
        return None
    ctx = M.context_from_fixture(fx, teams)
    pred = M.predict_match(teams, fx["team_a"], fx["team_b"], ctx=ctx)
    sg = pred.score_guidance or {}
    modal = pred.exact_scores[0][0]
    penca = str(M.penca_ovacion_top_score(pred)["score"])
    return {
        "prediction": pred,
        "modal": modal,
        "penca": penca,
        "recommended_score": sg.get("recommended_score", penca),
        "confidence_label": sg.get("penca_certainty_label") or sg.get("precision_label") or "n/d",
        "win_a": pred.win_a, "draw": pred.draw, "win_b": pred.win_b,
        "xg_a": pred.expected_goals_a, "xg_b": pred.expected_goals_b,
    }


def predict_record(record: dict, teams=None) -> Optional[dict]:
    """``record`` proviene de results_ingest.finalized_records (modo feed)."""
    fx = record.get("fixture")
    base = predict_fixture(fx, teams)
    if base is None:
        return None
    import modelo_quiniela_2026 as M
    actual = record["actual_score"]
    base["model_points"] = M.realized_penca_points_for_score(base["modal"], actual)
    base["penca_points"] = M.realized_penca_points_for_score(base["penca"], actual)
    return base
