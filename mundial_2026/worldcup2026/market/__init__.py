"""Subpaquete de mercado (F1.1): ingesta manual de odds y conversión sin vig.

No consume ni modifica el modelo predictivo (pesos, lambdas, metodología, Penca).
"""

from __future__ import annotations

from .devig import (
    MARKET_IMPLIED_COLUMNS,
    MarketImplied,
    booksum,
    devig_1x2,
    devig_proportional,
    implied_prob,
    market_expected_total,
    market_implied_to_row,
    market_lambdas,
    market_supremacy_from_1x2,
    market_supremacy_from_handicap,
    odds_to_implied,
    overround,
    two_way_no_vig,
)
from .decision import (
    DECISION_COLUMNS,
    DecisionVerdict,
    decide_pick,
    decision_to_row,
)
from .gap import (
    GAP_COLUMNS,
    GapReport,
    classify_severity,
    gap_report_to_row,
    model_vs_market_gap,
    total_variation_distance,
)
from .odds_ingest import (
    INPUT_COLUMNS,
    OddsSnapshot,
    coverage_flags,
    has_minimum_market,
    is_prematch,
    is_usable_for_decision,
    load_odds_input,
    to_decimal_odds,
    validate_odds_snapshot,
)

__all__ = [
    "INPUT_COLUMNS",
    "MARKET_IMPLIED_COLUMNS",
    "OddsSnapshot",
    "MarketImplied",
    "load_odds_input",
    "validate_odds_snapshot",
    "to_decimal_odds",
    "has_minimum_market",
    "is_prematch",
    "is_usable_for_decision",
    "coverage_flags",
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
    "GAP_COLUMNS",
    "GapReport",
    "model_vs_market_gap",
    "gap_report_to_row",
    "total_variation_distance",
    "classify_severity",
    "DECISION_COLUMNS",
    "DecisionVerdict",
    "decide_pick",
    "decision_to_row",
]
