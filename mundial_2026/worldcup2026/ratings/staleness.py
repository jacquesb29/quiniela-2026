"""Detección pura de Elo stale/inconsistente (F2.1).

Calcula `fifa_implied_elo` (FIFA anclado a la escala Elo por estadística
transversal del pool) y `elo_staleness_score` (señales pre-partido), y recomienda
una acción. NO toca el modelo, ni pesos, ni lambdas, ni metodología, ni Penca, ni
aplica ningún ajuste. Es solo diagnóstico/auditoría.

Reglas:
- Si falta FIFA, no se inventa: el score usa solo las señales disponibles + warning.
- Score siempre en [0,1].
- No usa mercado ni resultados posteriores al partido.
- Los parámetros son priors conservadores documentados, NO ajustados a datos 2026.
"""

from __future__ import annotations

import statistics as _st
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# --- Priors conservadores (NO ajustados a resultados 2026; ilustrativos/validables) ---
GAP_SCALE = 150.0          # puntos Elo de discrepancia para saturar la señal
AGE_MIN, AGE_MAX = 120.0, 540.0       # días sin jugar: 4–18 meses
COV_MIN = 8.0              # partidos oficiales en ventana reciente
JUMP_MIN, JUMP_MAX = 40.0, 120.0      # salto de rating anómalo (puntos Elo)
T_LOW, T_HIGH = 0.25, 0.55            # umbrales de acción

DEFAULT_WEIGHTS: Dict[str, float] = {
    "fifa_gap": 0.60,
    "age": 0.20,
    "coverage": 0.15,
    "jump": 0.05,
}

# Los amistosos pesan menos que los oficiales en la cobertura reciente (F2.4).
FRIENDLY_WEIGHT = 0.40

ELO_CLAMP_LOW, ELO_CLAMP_HIGH = 1200.0, 2400.0

ACTION_DOMINATE = "elo_domina"
ACTION_SHRINK_FIFA = "shrink_fifa"


@dataclass(frozen=True)
class PoolStats:
    mean_elo: float
    std_elo: float
    mean_fifa: float
    std_fifa: float


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _num(team, key: str) -> Optional[float]:
    if team is None:
        return None
    value = team.get(key) if isinstance(team, Mapping) else getattr(team, key, None)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_pool_stats(teams: Sequence) -> PoolStats:
    elos = [v for v in (_num(t, "elo") for t in teams) if v is not None]
    fifas = [v for v in (_num(t, "fifa_points") for t in teams) if v is not None]
    if len(elos) < 2 or len(fifas) < 2:
        raise ValueError("pool insuficiente para estadística transversal")
    return PoolStats(
        mean_elo=_st.mean(elos), std_elo=_st.pstdev(elos),
        mean_fifa=_st.mean(fifas), std_fifa=_st.pstdev(fifas),
    )


def fifa_implied_elo(team, *, pool_stats: PoolStats, clamp=_clamp) -> Optional[float]:
    """Ancla FIFA a la escala Elo (leakage-safe). None si falta FIFA."""

    fifa_points = _num(team, "fifa_points")
    if fifa_points is None or pool_stats.std_fifa <= 0:
        return None
    z_fifa = (fifa_points - pool_stats.mean_fifa) / pool_stats.std_fifa
    return clamp(pool_stats.mean_elo + pool_stats.std_elo * z_fifa, ELO_CLAMP_LOW, ELO_CLAMP_HIGH)


# --- Normalización de señales a [0,1] ---
def f_gap(gap: float, *, gap_scale: float = GAP_SCALE) -> float:
    return _clamp(abs(gap) / gap_scale, 0.0, 1.0)


def f_age(age_days: float, *, age_min: float = AGE_MIN, age_max: float = AGE_MAX) -> float:
    return _clamp((age_days - age_min) / (age_max - age_min), 0.0, 1.0)


def f_coverage(n_recent: float, *, cov_min: float = COV_MIN) -> float:
    return _clamp((cov_min - n_recent) / cov_min, 0.0, 1.0)


def f_jump(jump_elo: float, *, jump_min: float = JUMP_MIN, jump_max: float = JUMP_MAX) -> float:
    return _clamp((abs(jump_elo) - jump_min) / (jump_max - jump_min), 0.0, 1.0)


def elo_vs_fifa_gap(elo: Optional[float], fifa_implied: Optional[float]) -> Optional[float]:
    if elo is None or fifa_implied is None:
        return None
    return elo - fifa_implied


def elo_staleness_score(
    team,
    *,
    fifa_implied_elo_value: Optional[float],
    last_match_age_days: Optional[float],
    recent_coverage: Optional[float],
    anomalous_jump: Optional[float],
    recent_coverage_6m: Optional[float] = None,
    recent_coverage_12m: Optional[float] = None,
    official_matches_12m: Optional[float] = None,
    friendly_matches_12m: Optional[float] = None,
    weights: Mapping[str, float] = DEFAULT_WEIGHTS,
    clamp=_clamp,
) -> float:
    """Score en [0,1]. Usa solo las señales disponibles (re-normaliza pesos).

    Compat F2.1/F2.3: si solo se pasa `fifa_implied_elo_value`, el comportamiento
    es idéntico (score = f_gap). F2.4 añade cobertura oficial/amistoso ponderada:
    los amistosos pesan menos (FRIENDLY_WEIGHT).
    """

    elo = _num(team, "elo")
    components: Dict[str, float] = {}
    if elo is not None and fifa_implied_elo_value is not None:
        components["fifa_gap"] = f_gap(elo - fifa_implied_elo_value)
    if last_match_age_days is not None:
        components["age"] = f_age(float(last_match_age_days))

    # Cobertura: prioriza la separación oficial/amistoso (F2.4); si no, legacy.
    effective_coverage: Optional[float] = None
    if official_matches_12m is not None or friendly_matches_12m is not None:
        effective_coverage = (official_matches_12m or 0.0) + FRIENDLY_WEIGHT * (friendly_matches_12m or 0.0)
    elif recent_coverage is not None:
        effective_coverage = float(recent_coverage)
    elif recent_coverage_12m is not None:
        effective_coverage = float(recent_coverage_12m)
    if effective_coverage is not None:
        components["coverage"] = f_coverage(effective_coverage)

    if anomalous_jump is not None:
        components["jump"] = f_jump(float(anomalous_jump))
    if not components:
        return 0.0
    numerator = sum(weights.get(k, 0.0) * v for k, v in components.items())
    denominator = sum(weights.get(k, 0.0) for k in components)
    if denominator <= 0.0:
        return 0.0
    return clamp(numerator / denominator, 0.0, 1.0)


def recommended_action(
    score: float, gap: Optional[float], *, fifa_available: bool
) -> Tuple[str, List[str]]:
    if not fifa_available and gap is None:
        return ACTION_DOMINATE, ["sin referencia FIFA: no se puede recomendar shrink"]
    if score < T_LOW:
        return ACTION_DOMINATE, []
    if score < T_HIGH:
        return ACTION_SHRINK_FIFA, ["discrepancia moderada Elo vs FIFA"]
    return ACTION_SHRINK_FIFA, ["discrepancia fuerte Elo vs FIFA (warning fuerte)"]


def staleness_bucket(score: float) -> str:
    if score >= T_HIGH:
        return "alto"
    if score >= T_LOW:
        return "medio"
    return "bajo"


def assess_team_staleness(
    team,
    *,
    pool_stats: PoolStats,
    activity=None,
    last_match_age_days: Optional[float] = None,
    recent_coverage: Optional[float] = None,
    anomalous_jump: Optional[float] = None,
    weights: Mapping[str, float] = DEFAULT_WEIGHTS,
    clamp=_clamp,
) -> Dict[str, object]:
    """Fila de auditoría para un equipo (sin aplicar ningún ajuste).

    `activity` (F2.4, opcional): un RecentActivity con señales recientes. Si es
    None, el comportamiento es idéntico a F2.1 (solo señal FIFA).
    """

    # Señales recientes desde `activity` (F2.4) o desde args legacy (compat).
    rec6m = rec12m = off12m = fri12m = None
    activity_warning = ""
    if activity is not None:
        last_match_age_days = activity.last_match_age_days
        rec6m = activity.recent_coverage_6m
        rec12m = activity.recent_coverage_12m
        off12m = activity.official_matches_12m
        fri12m = activity.friendly_matches_12m
        anomalous_jump = activity.anomalous_elo_jump
        activity_warning = activity.activity_warning

    elo = _num(team, "elo")
    fifa_points = _num(team, "fifa_points")
    fifa_rank = team.get("fifa_rank") if isinstance(team, Mapping) else getattr(team, "fifa_rank", None)
    fie = fifa_implied_elo(team, pool_stats=pool_stats, clamp=clamp)
    gap = elo_vs_fifa_gap(elo, fie)
    score = elo_staleness_score(
        team,
        fifa_implied_elo_value=fie,
        last_match_age_days=last_match_age_days,
        recent_coverage=recent_coverage,
        anomalous_jump=anomalous_jump,
        recent_coverage_6m=rec6m,
        recent_coverage_12m=rec12m,
        official_matches_12m=off12m,
        friendly_matches_12m=fri12m,
        weights=weights,
        clamp=clamp,
    )
    warnings: List[str] = []
    if fifa_points is None:
        warnings.append("sin fifa: score sin señal FIFA")
    if activity is None and last_match_age_days is None:
        warnings.append("sin actividad reciente (no se cargó historial)")
    if activity_warning:
        warnings.append(activity_warning)
    if anomalous_jump is not None and anomalous_jump >= JUMP_MIN:
        warnings.append(f"salto de Elo reciente ({anomalous_jump})")
    action, action_warnings = recommended_action(score, gap, fifa_available=fifa_points is not None)
    warnings.extend(action_warnings)

    name = team.get("name") if isinstance(team, Mapping) else getattr(team, "name", "")
    legacy_coverage = recent_coverage if recent_coverage is not None else (rec12m if rec12m is not None else "")
    return {
        "team": name,
        "elo": elo if elo is not None else "",
        "fifa_points": fifa_points if fifa_points is not None else "",
        "fifa_rank": fifa_rank if fifa_rank is not None else "",
        "fifa_implied_elo": round(fie, 3) if fie is not None else "",
        "elo_vs_fifa_gap": round(gap, 3) if gap is not None else "",
        "last_match_age_days": last_match_age_days if last_match_age_days is not None else "",
        "recent_coverage": legacy_coverage,
        "recent_coverage_6m": rec6m if rec6m is not None else "",
        "recent_coverage_12m": rec12m if rec12m is not None else "",
        "official_matches_12m": off12m if off12m is not None else "",
        "friendly_matches_12m": fri12m if fri12m is not None else "",
        "anomalous_jump": anomalous_jump if anomalous_jump is not None else "",
        "anomalous_elo_jump": anomalous_jump if anomalous_jump is not None else "",
        "activity_warning": activity_warning,
        "elo_staleness_score": round(score, 4),
        "recommended_action": action,
        "warnings": ";".join(warnings),
        "_bucket": staleness_bucket(score),
    }


REPORT_COLUMNS = (
    "team", "elo", "fifa_points", "fifa_rank", "fifa_implied_elo", "elo_vs_fifa_gap",
    "last_match_age_days", "recent_coverage", "recent_coverage_6m", "recent_coverage_12m",
    "official_matches_12m", "friendly_matches_12m", "anomalous_jump", "anomalous_elo_jump",
    "activity_warning", "elo_staleness_score", "recommended_action", "warnings",
)


# --------------------------------------------------------------------------- #
# F2.3 — Mecanismo de Elo staleness-aware (APAGADO por defecto)
# --------------------------------------------------------------------------- #
# IMPORTANTE: este mecanismo NO está cableado en el modelo (expected_goals.py no
# lo invoca). `effective_elo_staleness_aware` con el flag OFF devuelve EXACTAMENTE
# el Elo efectivo base (identidad). Solo se activaría tras el gate de validación.

def staleness_shrunk_elo(
    *,
    base_effective_elo: float,
    fifa_implied_elo_value: Optional[float],
    staleness: float,
    w_fifa: float,
    cap: float,
    min_score: float = 0.0,
    clamp=_clamp,
) -> float:
    """Elo encogido hacia el FIFA-implied (no hacia resultados).

    - Si falta FIFA (None) -> devuelve base (no ajusta).
    - Si staleness < min_score -> devuelve base (Elo y FIFA suficientemente de acuerdo).
    - Fracción de shrink = clamp(w_fifa * staleness, 0, cap) (cap conservador).
    - adjusted = (1 - frac)*base + frac*fifa_implied.
    """

    if fifa_implied_elo_value is None:
        return base_effective_elo
    if staleness < min_score:
        return base_effective_elo
    frac = clamp(w_fifa * staleness, 0.0, cap)
    return (1.0 - frac) * base_effective_elo + frac * fifa_implied_elo_value


def effective_elo_staleness_aware(
    *,
    base_effective_elo: float,
    fifa_implied_elo_value: Optional[float],
    staleness: float,
    params,
    clamp=_clamp,
) -> float:
    """Punto de conexión gated. Con `params.elo_staleness_enabled=False` es identidad.

    `params` es PARAMS (worldcup2026.config). Integración futura en
    expected_goals.py: reemplazar `effective_elo(team, state)` por esta función
    SOLO tras superar el gate de validación; hoy permanece desconectada.
    """

    if not getattr(params, "elo_staleness_enabled", False):
        return base_effective_elo
    return staleness_shrunk_elo(
        base_effective_elo=base_effective_elo,
        fifa_implied_elo_value=fifa_implied_elo_value,
        staleness=staleness,
        w_fifa=getattr(params, "elo_staleness_shrink_to_fifa_weight", 0.50),
        cap=getattr(params, "elo_staleness_shrink_cap", 0.35),
        min_score=getattr(params, "elo_staleness_min_score", 0.25),
        clamp=clamp,
    )


__all__ = [
    "GAP_SCALE", "T_LOW", "T_HIGH", "DEFAULT_WEIGHTS", "REPORT_COLUMNS",
    "ACTION_DOMINATE", "ACTION_SHRINK_FIFA",
    "PoolStats", "compute_pool_stats", "fifa_implied_elo",
    "f_gap", "f_age", "f_coverage", "f_jump", "elo_vs_fifa_gap",
    "elo_staleness_score", "recommended_action", "staleness_bucket",
    "assess_team_staleness",
    "staleness_shrunk_elo", "effective_elo_staleness_aware",
]
