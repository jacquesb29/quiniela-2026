"""Integración de cuotas pre-match (1X2) vía API oficial — The Odds API (primaria),
API-Football (respaldo). Alimenta F1/F7 sin intervención manual.

No hace scraping. Solo APIs documentadas. No usa odds live ni closing para
decisiones pre-match. No toca el modelo, pesos, lambdas ni selector Penca.
"""

from __future__ import annotations

from .cache import DEFAULT_CACHE_DIR, OddsCache
from .models import (OddsQuote, SNAPSHOT_OPEN, SNAPSHOT_T60, SNAPSHOT_LIVE, SNAPSHOT_CLOSING,
                     implied_overround, is_prematch_snapshot, is_valid, validate_odds)
from .provider import (OddsProviderError, RateLimitError, TheOddsApiProvider,
                       build_match_id, classify_snapshot, consensus_quote, fetch_pre_match_odds,
                       urllib_fetch)
from .sync_odds import (F1_COLUMNS, best_quote_per_match, build_f1_rows, collect_quotes,
                        dedup_quotes, quote_to_f1_row, reject_invalid)

__all__ = [
    "OddsCache", "DEFAULT_CACHE_DIR",
    "OddsQuote", "SNAPSHOT_OPEN", "SNAPSHOT_T60", "SNAPSHOT_LIVE", "SNAPSHOT_CLOSING",
    "implied_overround", "is_prematch_snapshot", "is_valid", "validate_odds",
    "OddsProviderError", "RateLimitError", "TheOddsApiProvider", "build_match_id",
    "classify_snapshot", "consensus_quote", "fetch_pre_match_odds", "urllib_fetch",
    "F1_COLUMNS", "best_quote_per_match", "build_f1_rows", "collect_quotes",
    "dedup_quotes", "quote_to_f1_row", "reject_invalid",
]
