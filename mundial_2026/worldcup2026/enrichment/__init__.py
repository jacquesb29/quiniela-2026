"""Enriquecimiento automático prepartido: odds, fixtures, alineaciones, bajas, portero.

Mejora la INFORMACIÓN DE ENTRADA del overlay operativo (F1/T-60). NO modifica el
modelo, pesos, lambdas, metodología ni selector Penca. No inventa datos. No usa
datos post-kickoff ni live para decisiones prepartido. No guarda API keys.
"""

from __future__ import annotations

from .models import (EnrichmentRecord, InjuryRecord, LineupPlayer, is_pre_kickoff, now_utc)
from .sources import (ApiFootballSource, CompositeSource, FeedSource, default_source)
from .lineups import confirmed_lineup, starting_goalkeeper
from .injuries import trusted_injuries
from .sync_enrichment import enrich
from .t60_writer import T60_COLUMNS, T60_INPUT, update_t60

__all__ = [
    "EnrichmentRecord", "InjuryRecord", "LineupPlayer", "is_pre_kickoff", "now_utc",
    "ApiFootballSource", "CompositeSource", "FeedSource", "default_source",
    "confirmed_lineup", "starting_goalkeeper", "trusted_injuries", "enrich",
    "T60_COLUMNS", "T60_INPUT", "update_t60",
]
