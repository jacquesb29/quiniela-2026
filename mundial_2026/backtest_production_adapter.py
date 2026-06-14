"""Adaptador de backtest: fila histórica -> modelo de producción real.

Este módulo NO modifica el modelo predictivo. Solo traduce una fila
pre-partido de `data/historical_matches.csv` a las entradas que espera
`modelo_quiniela_2026.predict_match` y devuelve una predicción comparable
con el resto del harness de `worldcup2026`.

Reglas de diseño (F0.1):

- No se lee `teams_2026.json` en el backtest histórico. Se logra construyendo
  cada `Team` con `fifa_points=None`: bajo `STRICT_REAL_INPUTS_ONLY=True` el
  modelo cortocircuita `fifa_strength_index` a neutral y nunca llega a
  `fifa_reference_table()`, que es la única ruta que abriría `teams_2026.json`.
- Solo se usan columnas pre-partido de la fila (`elo_*_pre`, `neutral`, `phase`).
  El marcador (`goals_a`, `goals_b`) jamás entra a la predicción.
- Cualquier variable histórica ausente o vacía queda neutral. En particular,
  los nombres de equipo se sufijan con un prefijo sintético para que NUNCA
  coincidan con `historical_features_1950.json`; así `historical_snapshot`
  cae a su rama proxy neutral y se evita el leakage de agregados históricos
  que incluyen partidos posteriores a la fecha de la fila.
- No se usan datos del Mundial 2026 ni se recalibra nada aquí.

Limitaciones documentadas (no se inventan datos para taparlas):

- El histórico solo trae `elo_*_pre` e `historical_strength_*_pre` con valores;
  `fifa_rank_*_pre`, `market_prob_*_pre` y `squad_quality_*_pre` están vacíos.
  Por tanto el modelo, en este backtest, corre sobre Elo pre-partido + capas
  neutrales. Esto valida las capas Elo / distribución / Penca, NO las capas
  squad / mercado / contexto (sin dato histórico disponible).
- No se aplica ventaja de localía: atribuir local exigiría un mapa
  equipo->país que solo vive en `teams_2026.json` (prohibido aquí). El partido
  se trata como neutral.
"""

from __future__ import annotations

from typing import Optional

import modelo_quiniela_2026 as model
from worldcup2026.benchmarks import safe_float
from worldcup2026.backtesting import phase_from_row

# Rank FIFA neutral (medio) usado solo como valor inerte; no entra a las lambdas.
_NEUTRAL_FIFA_RANK = 50


def _install_neutral_data_shims() -> None:
    """Neutraliza las búsquedas FIFA acopladas a `teams_2026.json`.

    Hallazgo arquitectónico: `profile_for` (worldcup2026/profiles/team.py) llama
    a `fifa_points_value(team)` y `fifa_rank_value(team)` de forma incondicional
    (sin respetar `STRICT_REAL_INPUTS_ONLY`). Ambas resuelven contra
    `fifa_reference_table()`, que ejecuta `load_teams()` -> lee `teams_2026.json`
    y, para un nombre histórico ausente, lanzaría KeyError.

    Para cumplir las reglas del backtest (no leer `teams_2026.json`, no usar
    datos 2026, dejar neutral lo ausente) sin editar el modelo, el adaptador
    sustituye esas DOS funciones de acceso a datos por constantes neutrales.

    Importante sobre qué NO se toca:
    - No se altera ningún peso, lambda, distribución de marcador ni la capa Penca.
    - `fifa_strength_index` ya devuelve neutral porque cada `Team` se construye
      con `fifa_points=None`; los valores neutralizados aquí (`fifa_points`,
      `fifa_rank` crudos) no alimentan `expected_goals` ni el ensamble, así que
      la neutralización es inerte para la predicción y solo evita el acoplamiento
      a `teams_2026.json` y el KeyError.
    """

    model.fifa_points_value = lambda team: 1500.0
    model.fifa_rank_value = lambda team: _NEUTRAL_FIFA_RANK


_install_neutral_data_shims()

# Elo neutral usado solo cuando la columna `elo_*_pre` está ausente o vacía
# (p.ej. en la ablation `sin_elo`). Es el mismo punto neutro que usa el resto
# del modelo, no un dato inventado de un partido concreto.
NEUTRAL_ELO = 1500.0

# Prefijo que garantiza que el nombre no exista en teams_2026.json ni en
# historical_features_1950.json -> fuerza snapshot histórico neutral.
_SYNTHETIC_PREFIX = "__bt__"

# Confederación neutral, idéntica para ambos lados: cualquier término derivado
# de confederación se cancela en el diferencial A-B y es simétrico en los
# términos absolutos. Bajo modo estricto, además, casi todo se neutraliza.
_NEUTRAL_CONFEDERATION = "UEFA"


def _synthetic_name(row, side: str) -> str:
    real = str(row.get(f"team_{side}") or f"side_{side}").strip()
    return f"{_SYNTHETIC_PREFIX}{side}__{real}"


def team_from_historical_row(row, side: str) -> "model.Team":
    """Construye un `Team` SOLO con columnas pre-partido de la fila.

    `fifa_points=None` mantiene neutral toda la capa FIFA y evita leer
    `teams_2026.json`. El Elo proviene de `elo_{side}_pre`; si falta, se usa
    el Elo neutral.
    """

    elo = safe_float(row.get(f"elo_{side}_pre"))
    if elo is None:
        elo = NEUTRAL_ELO
    return model.Team(
        name=_synthetic_name(row, side),
        confederation=_NEUTRAL_CONFEDERATION,
        status="qualified",
        elo=float(elo),
        fifa_points=None,
        fifa_rank=None,
        host_country=None,
    )


def context_from_historical_row(row) -> "model.MatchContext":
    """MatchContext neutral derivado solo de campos pre-partido.

    `knockout` se infiere de la fase si está disponible; el resto queda en los
    valores por defecto neutrales del modelo. No se aplica localía (ver módulo).
    """

    knockout = phase_from_row(row) == "knockout"
    return model.MatchContext(
        neutral=True,
        knockout=knockout,
    )


def production_prediction_fn(row, *, top_scores: int = 6) -> Optional["model.MatchPrediction"]:
    """Predicción del modelo de producción real para una fila histórica.

    Devuelve un `MatchPrediction` (compatible con `coerce_prediction`). No usa
    el marcador real. Cualquier fila irrecuperable devuelve None.
    """

    name_a = _synthetic_name(row, "a")
    name_b = _synthetic_name(row, "b")
    if name_a == name_b:
        return None
    team_a = team_from_historical_row(row, "a")
    team_b = team_from_historical_row(row, "b")
    teams = {name_a: team_a, name_b: team_b}
    ctx = context_from_historical_row(row)
    # Reproducibilidad: el bug de caché mutable que rompía el determinismo de
    # `predict_match` ya está corregido en worldcup2026/distributions.py, por lo
    # que YA NO se fuerza caché frío. Se mantiene únicamente una siembra estable
    # del RNG (derivada de campos de identidad del partido que ninguna ablation
    # elimina) como defensa por si algún camino tocara RNG; el camino analítico de
    # `predict_match` es determinista sin ella.
    seed_key = "|".join(
        str(row.get(field) or "")
        for field in ("match_id", "team_a", "team_b", "date")
    )
    model.seed_all_rng(model.stable_seed(seed_key))
    return model.predict_match(
        teams,
        name_a,
        name_b,
        ctx,
        top_scores=top_scores,
        include_advancement=False,
        show_factors=False,
        state_a=None,
        state_b=None,
    )


def production_prediction_with_penca(row, *, top_scores: int = 6) -> Optional[dict]:
    """Igual que `production_prediction_fn` pero como dict con puntos Penca.

    Añade `expected_penca_points` del marcador recomendado por la capa Penca,
    para que `evaluate_backtest_rows` lo registre en `backtest_predictions.csv`.
    """

    prediction = production_prediction_fn(row, top_scores=top_scores)
    if prediction is None:
        return None
    top_penca = model.penca_ovacion_top_score(prediction)
    expected_penca_points = safe_float(top_penca.get("expected_points")) if top_penca else None
    most_likely_score = prediction.exact_scores[0][0] if prediction.exact_scores else None
    return {
        "prob_a": float(prediction.win_a),
        "prob_draw": float(prediction.draw),
        "prob_b": float(prediction.win_b),
        "expected_goals_a": float(prediction.expected_goals_a),
        "expected_goals_b": float(prediction.expected_goals_b),
        "most_likely_score": most_likely_score,
        "penca_score": top_penca.get("score") if top_penca else None,
        "expected_penca_points": expected_penca_points if expected_penca_points is not None else "",
    }


__all__ = [
    "NEUTRAL_ELO",
    "team_from_historical_row",
    "context_from_historical_row",
    "production_prediction_fn",
    "production_prediction_with_penca",
]
