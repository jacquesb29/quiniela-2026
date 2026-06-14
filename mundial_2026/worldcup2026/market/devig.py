"""Conversión de odds a probabilidades sin vig y señales de mercado (F1.1).

Funciones puras y deterministas: implícitas, overround, de-vig proporcional,
de-vig de dos vías, total esperado desde over/under, margen (supremacía) desde
handicap o 1X2, y lambdas de mercado. NO consume ni modifica el modelo, ni
pesos, ni lambdas del modelo, ni la capa Penca.

Reglas: si falta un mercado, el campo correspondiente queda None (no se inventa).
`snapshot_type=closing` se puede convertir (auditoría/CLV), pero NO es apto para
decisión prepartido (eso lo decide odds_ingest.is_usable_for_decision).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .odds_ingest import (
    OddsSnapshot,
    coverage_flags,
    is_prematch,
    to_decimal_odds,
)

# Clamps de lambdas de MERCADO (independientes de los del modelo, documentados).
MARKET_LAMBDA_FLOOR = 0.05
MARKET_LAMBDA_CAP = 4.95
_GRID = 16  # goles máximos por lado en sumas de Poisson


@dataclass(frozen=True)
class MarketImplied:
    match_id: str
    snapshot_type: str
    captured_at_utc: str
    source: str
    devig_method: str
    p_home: Optional[float]
    p_draw: Optional[float]
    p_away: Optional[float]
    overround_1x2: Optional[float]
    market_total_goals: Optional[float]
    market_supremacy: Optional[float]
    supremacy_source: Optional[str]
    market_lambda_home: Optional[float]
    market_lambda_away: Optional[float]
    market_tt_home: Optional[float]
    market_tt_away: Optional[float]
    coverage: Dict[str, bool]
    warnings: Tuple[str, ...]


# --------------------------------------------------------------------------- #
# De-vig básico
# --------------------------------------------------------------------------- #
def implied_prob(decimal_odds: float) -> float:
    return 1.0 / float(decimal_odds)


def booksum(implied: Sequence[float]) -> float:
    return sum(implied)


def overround(implied: Sequence[float]) -> float:
    return booksum(implied) - 1.0


def devig_proportional(implied: Sequence[float]) -> List[float]:
    total = booksum(implied)
    if total <= 0.0:
        raise ValueError("booksum <= 0")
    return [value / total for value in implied]


def two_way_no_vig(odds_a: float, odds_b: float, method: str = "proportional") -> Tuple[float, float]:
    if method != "proportional":
        raise ValueError(f"método de-vig no soportado en F1.1: {method!r}")
    q_a = implied_prob(odds_a)
    q_b = implied_prob(odds_b)
    p_a, p_b = devig_proportional([q_a, q_b])
    return p_a, p_b


def devig_1x2(
    odds_home: float, odds_draw: float, odds_away: float, method: str = "proportional"
) -> Tuple[float, float, float, float]:
    """Devuelve (p_home, p_draw, p_away, overround)."""

    if method != "proportional":
        raise ValueError(f"método de-vig no soportado en F1.1: {method!r}")
    implied = [implied_prob(odds_home), implied_prob(odds_draw), implied_prob(odds_away)]
    over = overround(implied)
    p_home, p_draw, p_away = devig_proportional(implied)
    return p_home, p_draw, p_away, over


# --------------------------------------------------------------------------- #
# Poisson / Skellam (rejilla, sin dependencias externas)
# --------------------------------------------------------------------------- #
def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0.0:
        return 1.0 if k == 0 else 0.0
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))


def _poisson_cdf(k: int, lam: float) -> float:
    return sum(_poisson_pmf(i, lam) for i in range(0, k + 1))


def _bisect(func, target: float, lo: float, hi: float, *, tol: float = 1e-7, max_iter: int = 200) -> float:
    f_lo = func(lo) - target
    f_hi = func(hi) - target
    # Si el objetivo está fuera del rango alcanzable, devolver el extremo más cercano.
    if f_lo > 0 and f_hi > 0:
        return lo
    if f_lo < 0 and f_hi < 0:
        return hi
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = func(mid) - target
        if abs(f_mid) < tol:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
    return 0.5 * (lo + hi)


def _total_over_prob(lam_total: float, line: float) -> float:
    """P(total > line) consistente con un mercado de dos vías sin vig.

    Línea media (.5): sin empuje -> P(N >= ceil(line)).
    Línea entera: empuje en N==line -> over/(over+under) (excluye empuje).
    Cuarto de línea (.25/.75): promedio de las dos líneas vecinas.
    """

    if abs((line * 2) - round(line * 2)) > 1e-9:  # cuarto de línea
        return 0.5 * (_total_over_prob(lam_total, line - 0.25) + _total_over_prob(lam_total, line + 0.25))
    if abs((line * 2) % 2 - 1) < 1e-9:  # media línea -> *2 impar
        floor_line = int(math.floor(line))
        return 1.0 - _poisson_cdf(floor_line, lam_total)
    # Línea entera con empuje.
    over = 1.0 - _poisson_cdf(int(line), lam_total)
    under = _poisson_cdf(int(line) - 1, lam_total)
    denom = over + under
    return over / denom if denom > 0 else 0.0


def market_expected_total(total_line: float, p_over_no_vig: float) -> Optional[float]:
    if total_line is None or p_over_no_vig is None:
        return None
    return _bisect(lambda lam: _total_over_prob(lam, total_line), p_over_no_vig, 0.05, 8.0)


def _lambdas_from(total: float, supremacy: float) -> Tuple[float, float]:
    return (total + supremacy) / 2.0, (total - supremacy) / 2.0


def _outcome_probs(lam_home: float, lam_away: float) -> Tuple[float, float, float]:
    p_home = p_draw = p_away = 0.0
    home_pmf = [_poisson_pmf(i, lam_home) for i in range(_GRID + 1)]
    away_pmf = [_poisson_pmf(j, lam_away) for j in range(_GRID + 1)]
    for i in range(_GRID + 1):
        for j in range(_GRID + 1):
            prob = home_pmf[i] * away_pmf[j]
            if i > j:
                p_home += prob
            elif i == j:
                p_draw += prob
            else:
                p_away += prob
    return p_home, p_draw, p_away


def _handicap_home_cover(lam_home: float, lam_away: float, handicap_line: float) -> float:
    """Prob. de dos vías (sin empuje) de que el home cubra el handicap_line."""

    threshold = -handicap_line  # home cubre si margen D > threshold
    home_pmf = [_poisson_pmf(i, lam_home) for i in range(_GRID + 1)]
    away_pmf = [_poisson_pmf(j, lam_away) for j in range(_GRID + 1)]
    cover = against = 0.0
    for i in range(_GRID + 1):
        for j in range(_GRID + 1):
            prob = home_pmf[i] * away_pmf[j]
            margin = i - j
            if margin > threshold + 1e-12:
                cover += prob
            elif margin < threshold - 1e-12:
                against += prob
            # margin == threshold (entero) -> empuje, excluido
    denom = cover + against
    return cover / denom if denom > 0 else 0.0


def market_supremacy_from_1x2(
    p_home: float, p_draw: float, p_away: float, total_goals: float
) -> Optional[float]:
    if total_goals is None or p_home is None:
        return None
    eps = 1e-3
    return _bisect(
        lambda s: _outcome_probs(*_lambdas_from(total_goals, s))[0],
        p_home,
        -total_goals + eps,
        total_goals - eps,
    )


def market_supremacy_from_handicap(
    handicap_line: float, p_hcap_home_no_vig: float, total_goals: float
) -> Optional[float]:
    if handicap_line is None or p_hcap_home_no_vig is None or total_goals is None:
        return None
    eps = 1e-3
    return _bisect(
        lambda s: _handicap_home_cover(*_lambdas_from(total_goals, s), handicap_line),
        p_hcap_home_no_vig,
        -total_goals + eps,
        total_goals - eps,
    )


def market_lambdas(
    total_goals: float, supremacy: float, *, floor: float = MARKET_LAMBDA_FLOOR, cap: float = MARKET_LAMBDA_CAP
) -> Tuple[float, float]:
    lam_home, lam_away = _lambdas_from(total_goals, supremacy)
    clamp = lambda v: max(floor, min(cap, v))
    return clamp(lam_home), clamp(lam_away)


def _team_total(line: float, p_over_no_vig: float) -> Optional[float]:
    if line is None or p_over_no_vig is None:
        return None
    return _bisect(lambda lam: _total_over_prob(lam, line), p_over_no_vig, 0.02, 6.0)


# --------------------------------------------------------------------------- #
# Orquestador
# --------------------------------------------------------------------------- #
def odds_to_implied(
    snapshot: OddsSnapshot, method: str = "proportional", *, require_prematch: bool = True
) -> Optional[MarketImplied]:
    fmt = snapshot.odds_format
    warnings: List[str] = []

    if require_prematch and not is_prematch(snapshot):
        # No se usan odds posteriores al kickoff (anti-leakage).
        return None
    if snapshot.snapshot_type == "closing":
        warnings.append("snapshot_type=closing: no apto para decisión prepartido (solo CLV/auditoría)")

    cov = coverage_flags(snapshot)

    # ---- 1X2 ----
    p_home = p_draw = p_away = over_1x2 = None
    if cov["1x2"]:
        dh = to_decimal_odds(snapshot.odds_home, fmt)
        dd = to_decimal_odds(snapshot.odds_draw, fmt)
        da = to_decimal_odds(snapshot.odds_away, fmt)
        p_home, p_draw, p_away, over_1x2 = devig_1x2(dh, dd, da, method=method)
    else:
        warnings.append("1X2 ausente o incompleto: probabilidades 1X2 = None")

    # ---- total desde over/under ----
    market_total = None
    if cov["ou"]:
        d_over = to_decimal_odds(snapshot.odds_over, fmt)
        d_under = to_decimal_odds(snapshot.odds_under, fmt)
        p_over, _ = two_way_no_vig(d_over, d_under, method=method)
        market_total = market_expected_total(snapshot.total_line, p_over)
    else:
        warnings.append("over/under ausente: market_total_goals = None")

    # ---- supremacía (handicap preferido, 1X2 fallback) ----
    supremacy = None
    supremacy_source = None
    if market_total is not None and cov["handicap"]:
        d_h = to_decimal_odds(snapshot.odds_hcap_home, fmt)
        d_a = to_decimal_odds(snapshot.odds_hcap_away, fmt)
        p_hcap_home, _ = two_way_no_vig(d_h, d_a, method=method)
        supremacy = market_supremacy_from_handicap(snapshot.handicap_line, p_hcap_home, market_total)
        supremacy_source = "handicap"
    elif market_total is not None and p_home is not None:
        supremacy = market_supremacy_from_1x2(p_home, p_draw, p_away, market_total)
        supremacy_source = "1x2"
    else:
        warnings.append("sin total y/o mercado para despejar supremacía: market_supremacy = None")

    # ---- lambdas mercado ----
    lam_home = lam_away = None
    if market_total is not None and supremacy is not None:
        lam_home, lam_away = market_lambdas(market_total, supremacy)

    # ---- team totals ----
    tt_home = tt_away = None
    if cov["tt_home"]:
        d_o = to_decimal_odds(snapshot.odds_tt_home_over, fmt)
        d_u = to_decimal_odds(snapshot.odds_tt_home_under, fmt)
        p_o, _ = two_way_no_vig(d_o, d_u, method=method)
        tt_home = _team_total(snapshot.tt_home_line, p_o)
    if cov["tt_away"]:
        d_o = to_decimal_odds(snapshot.odds_tt_away_over, fmt)
        d_u = to_decimal_odds(snapshot.odds_tt_away_under, fmt)
        p_o, _ = two_way_no_vig(d_o, d_u, method=method)
        tt_away = _team_total(snapshot.tt_away_line, p_o)

    # Nada convertible -> None (no se inventa un MarketImplied vacío).
    if not cov["1x2"] and not cov["ou"]:
        return None

    return MarketImplied(
        match_id=snapshot.match_id,
        snapshot_type=snapshot.snapshot_type,
        captured_at_utc=snapshot.captured_at_utc,
        source=snapshot.source,
        devig_method=method,
        p_home=p_home, p_draw=p_draw, p_away=p_away, overround_1x2=over_1x2,
        market_total_goals=market_total,
        market_supremacy=supremacy, supremacy_source=supremacy_source,
        market_lambda_home=lam_home, market_lambda_away=lam_away,
        market_tt_home=tt_home, market_tt_away=tt_away,
        coverage=cov,
        warnings=tuple(warnings),
    )


def market_implied_to_row(mi: MarketImplied) -> Dict[str, object]:
    def fmt(value):
        return "" if value is None else value

    return {
        "match_id": mi.match_id,
        "snapshot_type": mi.snapshot_type,
        "captured_at_utc": mi.captured_at_utc,
        "source": mi.source,
        "devig_method": mi.devig_method,
        "p_home": fmt(mi.p_home), "p_draw": fmt(mi.p_draw), "p_away": fmt(mi.p_away),
        "overround_1x2": fmt(mi.overround_1x2),
        "market_total_goals": fmt(mi.market_total_goals),
        "market_supremacy": fmt(mi.market_supremacy),
        "supremacy_source": fmt(mi.supremacy_source),
        "market_lambda_home": fmt(mi.market_lambda_home),
        "market_lambda_away": fmt(mi.market_lambda_away),
        "market_tt_home": fmt(mi.market_tt_home),
        "market_tt_away": fmt(mi.market_tt_away),
        "coverage_1x2": mi.coverage.get("1x2", False),
        "coverage_ou": mi.coverage.get("ou", False),
        "coverage_handicap": mi.coverage.get("handicap", False),
        "coverage_tt_home": mi.coverage.get("tt_home", False),
        "coverage_tt_away": mi.coverage.get("tt_away", False),
        "warnings": ";".join(mi.warnings),
    }


MARKET_IMPLIED_COLUMNS = tuple(market_implied_to_row(MarketImplied(
    match_id="", snapshot_type="", captured_at_utc="", source="", devig_method="",
    p_home=None, p_draw=None, p_away=None, overround_1x2=None,
    market_total_goals=None, market_supremacy=None, supremacy_source=None,
    market_lambda_home=None, market_lambda_away=None, market_tt_home=None, market_tt_away=None,
    coverage={}, warnings=(),
)).keys())


__all__ = [
    "MARKET_LAMBDA_FLOOR",
    "MARKET_LAMBDA_CAP",
    "MARKET_IMPLIED_COLUMNS",
    "MarketImplied",
    "implied_prob",
    "booksum",
    "overround",
    "devig_proportional",
    "two_way_no_vig",
    "devig_1x2",
    "market_expected_total",
    "market_supremacy_from_1x2",
    "market_supremacy_from_handicap",
    "market_lambdas",
    "odds_to_implied",
    "market_implied_to_row",
]
