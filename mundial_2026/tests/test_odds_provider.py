"""Tests del proveedor de cuotas (offline, sin red ni API key real).

Obligatorios:
  - API response parsing
  - CSV generation
  - duplicate removal
  - cache hit
  - cache miss
  - API failure fallback
  - invalid odds rejection
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.odds_provider import (F1_COLUMNS, OddsCache, OddsProviderError, OddsQuote,
                                        SNAPSHOT_CLOSING, TheOddsApiProvider, best_quote_per_match,
                                        build_f1_rows, dedup_quotes, fetch_pre_match_odds, is_valid,
                                        reject_invalid, validate_odds)
import sync_market_odds

NOW = datetime(2026, 6, 19, 0, 0, 0, tzinfo=timezone.utc)
FIXED_CLOCK = lambda: 1000.0  # noqa: E731

SAMPLE = json.dumps([
    {"id": "e1", "sport_key": "soccer_fifa_world_cup", "commence_time": "2026-06-20T19:00:00Z",
     "home_team": "Brazil", "away_team": "Haiti", "bookmakers": [
         {"key": "pinnacle", "title": "Pinnacle", "markets": [{"key": "h2h", "outcomes": [
             {"name": "Brazil", "price": 1.30}, {"name": "Haiti", "price": 9.0}, {"name": "Draw", "price": 5.5}]}]},
         {"key": "betfair", "title": "Betfair", "markets": [{"key": "h2h", "outcomes": [
             {"name": "Brazil", "price": 1.33}, {"name": "Haiti", "price": 8.5}, {"name": "Draw", "price": 5.2}]}]},
     ]},
    {"id": "e2", "sport_key": "soccer_fifa_world_cup", "commence_time": "2026-06-20T22:00:00Z",
     "home_team": "Spain", "away_team": "Cape Verde", "bookmakers": [
         {"key": "williamhill", "title": "WilliamHill", "markets": [{"key": "h2h", "outcomes": [
             {"name": "Spain", "price": 1.25}, {"name": "Cape Verde", "price": 11.0}, {"name": "Draw", "price": 6.0}]}]},
     ]},
])


def make_fetch(body=SAMPLE, fail=False):
    state = {"calls": 0}

    def _fetch(url, timeout=20):
        state["calls"] += 1
        if fail:
            raise OddsProviderError("simulado: API caída")
        return body
    return _fetch, state


def make_provider(fail=False, **kw):
    fetch, state = make_fetch(fail=fail)
    p = TheOddsApiProvider(api_key="TEST", sport="soccer_fifa_world_cup", regions="eu",
                           http_fetch=fetch, max_retries=2, backoff_seconds=0.0,
                           sleep_fn=lambda s: None, now_fn=lambda: NOW, **kw)
    return p, state


class TestOddsProvider(unittest.TestCase):
    def test_api_response_parsing(self):
        p, _ = make_provider()
        quotes = p.parse_events(json.loads(SAMPLE), now=NOW)
        self.assertEqual(len(quotes), 3)  # 2 casas (e1) + 1 casa (e2)
        brazil = [q for q in quotes if q.match_id == "20260620_Brazil_vs_Haiti"]
        self.assertEqual(len(brazil), 2)
        q = brazil[0]
        self.assertEqual(q.home_team, "Brazil")
        self.assertAlmostEqual(q.home_odds, 1.30)
        self.assertEqual(q.snapshot_type, "open")  # >90 min al kickoff
        self.assertTrue(q.bookmaker and q.captured_at)

    def test_csv_generation(self):
        p, _ = make_provider()
        quotes = p.parse_events(json.loads(SAMPLE), now=NOW)
        rows = build_f1_rows(best_quote_per_match(quotes))
        self.assertEqual(len(rows), 2)  # 2 partidos
        self.assertEqual(set(rows[0].keys()), set(F1_COLUMNS))
        for r in rows:
            self.assertTrue(r["odds_home"] and r["odds_draw"] and r["odds_away"])
            self.assertEqual(r["odds_format"], "decimal")
            self.assertIn(r["snapshot_type"], ("open", "t60"))
            self.assertTrue(str(r["source"]).startswith("the_odds_api"))

    def test_duplicate_removal(self):
        p, _ = make_provider()
        quotes = p.parse_events(json.loads(SAMPLE), now=NOW)
        doubled = quotes + [quotes[0]]  # introduce un duplicado exacto
        self.assertEqual(len(dedup_quotes(doubled)), len(quotes))

    def test_cache_hit(self):
        with tempfile.TemporaryDirectory() as d:
            cache = OddsCache(Path(d), ttl_seconds=10_000, now_fn=FIXED_CLOCK)
            # pre-poblamos la caché con eventos válidos
            p_ok, _ = make_provider()
            quotes = p_ok.fetch_quotes(now=NOW)
            cache.set("odds_events:soccer_fifa_world_cup:eu", [q.as_dict() for q in quotes])
            # provider que FALLA si se le llama → si devuelve dato, fue por cache hit
            p_fail, state = make_provider(fail=True)
            out = fetch_pre_match_odds("20260620_Brazil_vs_Haiti", provider=p_fail, cache=cache, now=NOW)
            self.assertIsNotNone(out)
            self.assertEqual(state["calls"], 0)  # no tocó la red
            self.assertIn("home_odds", out)
            self.assertIn("bookmaker", out)

    def test_cache_miss(self):
        with tempfile.TemporaryDirectory() as d:
            cache = OddsCache(Path(d), ttl_seconds=10_000, now_fn=FIXED_CLOCK)
            self.assertIsNone(cache.get("inexistente"))
            p, state = make_provider()
            out = fetch_pre_match_odds("20260620_Spain_vs_Cape_Verde", provider=p, cache=cache, now=NOW)
            self.assertIsNotNone(out)
            self.assertGreaterEqual(state["calls"], 1)  # hubo fetch real (miss)
            # ahora ya quedó cacheado
            self.assertIsNotNone(cache.get("odds_events:soccer_fifa_world_cup:eu"))

    def test_api_failure_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            cache = OddsCache(Path(d), ttl_seconds=10_000, now_fn=FIXED_CLOCK)
            p_fail, _ = make_provider(fail=True)
            # sin caché previa → devuelve None sin romper
            out = fetch_pre_match_odds("20260620_Brazil_vs_Haiti", provider=p_fail, cache=cache, now=NOW)
            self.assertIsNone(out)
        # sync_market_odds sin API key → conserva CSV, retorna 0 (no rompe, no inventa)
        existing = sync_market_odds.MARKET_INPUT
        before = existing.read_text(encoding="utf-8") if existing.exists() else None
        os.environ.pop("THE_ODDS_API_KEY", None)
        rc = sync_market_odds.main([])
        self.assertEqual(rc, 0)
        after = existing.read_text(encoding="utf-8") if existing.exists() else None
        self.assertEqual(before, after)  # CSV intacto

    def test_invalid_odds_rejection(self):
        bad = OddsQuote(match_id="x", kickoff_utc="2026-06-20T19:00:00Z", home_team="A", away_team="B",
                        home_odds=0.5, draw_odds=3.0, away_odds=4.0, bookmaker="b",
                        captured_at="2026-06-19T00:00:00Z", snapshot_type="open")
        self.assertFalse(is_valid(bad))
        self.assertTrue(validate_odds(bad))
        closing = OddsQuote(match_id="y", kickoff_utc="2026-06-20T19:00:00Z", home_team="A", away_team="B",
                            home_odds=2.0, draw_odds=3.3, away_odds=3.6, bookmaker="b",
                            captured_at="2026-06-19T00:00:00Z", snapshot_type=SNAPSHOT_CLOSING)
        self.assertFalse(is_valid(closing))  # closing prohibido para pre-match
        good = OddsQuote(match_id="z", kickoff_utc="2026-06-20T19:00:00Z", home_team="A", away_team="B",
                         home_odds=2.0, draw_odds=3.3, away_odds=3.6, bookmaker="b",
                         captured_at="2026-06-19T00:00:00Z", snapshot_type="open")
        keep, drop = reject_invalid([good, bad, closing])
        self.assertEqual(len(keep), 1)
        self.assertEqual(len(drop), 2)


if __name__ == "__main__":
    unittest.main()
