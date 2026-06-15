"""Proveedor de cuotas: The Odds API (primaria) con HTTP inyectable.

- ``http_fetch`` se inyecta para tests offline (sin red, sin API key real).
- Reintentos con backoff y manejo de rate-limit (429).
- Parser de la respuesta v4 (`/sports/{sport}/odds?markets=h2h`).
- ``fetch_pre_match_odds(match_id)`` con caché y fallback.

Reglas: nunca live ni closing para pre-match; se descartan eventos ya comenzados.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable, List, Optional
from urllib.parse import urlencode

from .cache import OddsCache
from .models import (OddsQuote, SNAPSHOT_OPEN, SNAPSHOT_T60, is_valid, validate_odds)

DEFAULT_BASE_URL = os.environ.get("THE_ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4").rstrip("/")
DEFAULT_SPORT = os.environ.get("THE_ODDS_API_SPORTS", "soccer_fifa_world_cup").split(",")[0].strip()
DEFAULT_REGIONS = os.environ.get("THE_ODDS_API_REGIONS", "us,eu,uk").strip()
T60_WINDOW_MINUTES = int(os.environ.get("ODDS_T60_WINDOW_MIN", "90") or "90")


class OddsProviderError(Exception):
    pass


class RateLimitError(OddsProviderError):
    pass


def urllib_fetch(url: str, timeout: int = 20) -> str:
    """Fetch HTTP real (stdlib). Lanza RateLimitError en 429, OddsProviderError en otros."""
    req = urllib.request.Request(url, headers={"User-Agent": "quiniela-2026-odds/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RateLimitError(f"rate limit (429): {exc}") from exc
        raise OddsProviderError(f"HTTP {exc.code}: {exc}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise OddsProviderError(f"red/URL: {exc}") from exc


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def build_match_id(home: str, away: str, commence_time: str) -> str:
    dt = _parse_iso(commence_time)
    date_token = dt.strftime("%Y%m%d") if dt else "00000000"
    return f"{date_token}_{home}_vs_{away}".replace(" ", "_")


def classify_snapshot(commence_time: str, now: datetime) -> Optional[str]:
    """open / t60 para pre-match; None si el partido ya comenzó (live → se descarta)."""
    ko = _parse_iso(commence_time)
    if ko is None:
        return SNAPSHOT_OPEN
    if ko <= now:
        return None  # ya comenzó → nunca usar live como pre-match
    minutes_to_ko = (ko - now).total_seconds() / 60.0
    return SNAPSHOT_T60 if minutes_to_ko <= T60_WINDOW_MINUTES else SNAPSHOT_OPEN


class TheOddsApiProvider:
    def __init__(self, api_key: str = "", base_url: str = DEFAULT_BASE_URL,
                 sport: str = DEFAULT_SPORT, regions: str = DEFAULT_REGIONS,
                 http_fetch: Callable[[str, int], str] = urllib_fetch,
                 max_retries: int = 3, backoff_seconds: float = 1.0,
                 timeout: int = 20, sleep_fn: Callable[[float], None] = time.sleep,
                 now_fn: Callable[[], datetime] = _utc_now):
        self.api_key = api_key or os.environ.get("THE_ODDS_API_KEY", "").strip()
        self.base_url = base_url.rstrip("/")
        self.sport = sport
        self.regions = regions
        self._fetch = http_fetch
        self.max_retries = max_retries
        self.backoff = backoff_seconds
        self.timeout = timeout
        self._sleep = sleep_fn
        self._now = now_fn

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)

    def build_url(self) -> str:
        params = {"apiKey": self.api_key, "regions": self.regions,
                  "markets": "h2h", "oddsFormat": "decimal", "dateFormat": "iso"}
        return f"{self.base_url}/sports/{self.sport}/odds?{urlencode(params)}"

    def fetch_raw_events(self) -> List[dict]:
        if not self.has_key:
            raise OddsProviderError("THE_ODDS_API_KEY no configurada")
        url = self.build_url()
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                body = self._fetch(url, self.timeout)
                data = json.loads(body)
                if not isinstance(data, list):
                    raise OddsProviderError("respuesta inesperada (no es lista)")
                return data
            except RateLimitError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    self._sleep(self.backoff * attempt)  # backoff lineal ante 429
            except (OddsProviderError, ValueError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    self._sleep(self.backoff * attempt)
        raise OddsProviderError(f"fallo tras {self.max_retries} intentos: {last_exc}")

    def parse_events(self, raw_events: List[dict], now: Optional[datetime] = None) -> List[OddsQuote]:
        now = now or self._now()
        quotes: List[OddsQuote] = []
        for ev in raw_events or []:
            home = ev.get("home_team")
            away = ev.get("away_team")
            commence = ev.get("commence_time")
            if not (home and away and commence):
                continue
            snapshot = classify_snapshot(commence, now)
            if snapshot is None:
                continue  # evento ya comenzado → descartar (no pre-match)
            match_id = build_match_id(home, away, commence)
            captured = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            for bk in ev.get("bookmakers", []) or []:
                bk_key = bk.get("key") or bk.get("title") or "unknown"
                h2h = next((m for m in bk.get("markets", []) or [] if m.get("key") == "h2h"), None)
                if not h2h:
                    continue
                prices = {}
                for oc in h2h.get("outcomes", []) or []:
                    name = oc.get("name")
                    price = oc.get("price")
                    if name == home:
                        prices["home"] = price
                    elif name == away:
                        prices["away"] = price
                    elif str(name).strip().lower() == "draw":
                        prices["draw"] = price
                if {"home", "draw", "away"} <= set(prices):
                    quotes.append(OddsQuote(
                        match_id=match_id, kickoff_utc=str(commence).replace("+00:00", "Z"),
                        home_team=home, away_team=away,
                        home_odds=float(prices["home"]), draw_odds=float(prices["draw"]),
                        away_odds=float(prices["away"]), bookmaker=str(bk_key),
                        captured_at=captured, snapshot_type=snapshot,
                        source="the_odds_api"))
        return quotes

    def fetch_quotes(self, now: Optional[datetime] = None) -> List[OddsQuote]:
        return self.parse_events(self.fetch_raw_events(), now=now)


def fetch_pre_match_odds(match_id: str, provider: Optional[TheOddsApiProvider] = None,
                         cache: Optional[OddsCache] = None,
                         now: Optional[datetime] = None) -> Optional[dict]:
    """Devuelve dict con home_odds, draw_odds, away_odds, bookmaker, captured_at,
    snapshot_type para ``match_id``; o None si no hay dato (fallback a caché stale)."""
    provider = provider or TheOddsApiProvider()
    cache = cache or OddsCache()
    now = now or _utc_now()
    cache_key = f"odds_events:{provider.sport}:{provider.regions}"

    cached = cache.get(cache_key)
    quotes_dicts = None
    if cached is not None:
        quotes_dicts = cached  # cache HIT
    else:
        try:
            quotes = provider.fetch_quotes(now=now)  # cache MISS → red
            quotes_dicts = [q.as_dict() for q in quotes]
            cache.set(cache_key, quotes_dicts)
        except OddsProviderError:
            stale = cache.get_stale(cache_key)  # fallback API failure
            if stale is None:
                return None
            quotes_dicts = stale

    matches = [OddsQuote(**q) for q in quotes_dicts if q.get("match_id") == match_id]
    matches = [q for q in matches if is_valid(q)]
    if not matches:
        return None
    best = consensus_quote(matches)
    return {
        "home_odds": best.home_odds, "draw_odds": best.draw_odds, "away_odds": best.away_odds,
        "bookmaker": best.bookmaker, "captured_at": best.captured_at,
        "snapshot_type": best.snapshot_type,
    }


def consensus_quote(quotes: List[OddsQuote]) -> OddsQuote:
    """Consenso por mediana de cuotas entre casas (snapshot más cercano al kickoff)."""
    def _median(values):
        s = sorted(values)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0

    # prioriza t60 sobre open si ambos existen
    t60 = [q for q in quotes if q.snapshot_type == SNAPSHOT_T60]
    pool = t60 or quotes
    ref = pool[0]
    return OddsQuote(
        match_id=ref.match_id, kickoff_utc=ref.kickoff_utc,
        home_team=ref.home_team, away_team=ref.away_team,
        home_odds=round(_median([q.home_odds for q in pool]), 4),
        draw_odds=round(_median([q.draw_odds for q in pool]), 4),
        away_odds=round(_median([q.away_odds for q in pool]), 4),
        bookmaker=f"consensus({len(pool)})", captured_at=ref.captured_at,
        snapshot_type=ref.snapshot_type, source="the_odds_api")
