"""Fuentes de enriquecimiento: feed local y API-Football (documentada).

Contrato de fuente:
  lineup_for(fixture, now)  -> (List[LineupPlayer], confirmed: bool)
  injuries_for(fixture, now) -> List[InjuryRecord]

- ``http_fetch`` inyectable (tests offline; sin red ni API key real).
- Si no hay key/fixture id resoluble, la fuente API devuelve vacío SIN romper.
- No inventa datos: si no hay XI, devuelve lista vacía.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Callable, List, Optional, Tuple

from .models import InjuryRecord, LineupPlayer, iso

API_FOOTBALL_BASE_URL = (os.environ.get("API_FOOTBALL_BASE_URL") or "https://v3.football.api-sports.io").rstrip("/")


def _http_fetch(url: str, headers: dict, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _match_id(fixture: dict) -> str:
    from worldcup2026.odds_provider.provider import build_match_id
    return build_match_id(fixture.get("team_a", ""), fixture.get("team_b", ""),
                          fixture.get("kickoff_utc", ""))


class FeedSource:
    """Lee alineaciones/bajas del propio feed (fixtures_live_2026.json) si están.

    El feed trae nombres de XI y flags de confirmación, pero no posiciones ni
    portero fiables → no deriva GK (eso queda para la API)."""

    name = "feed:fixtures_live_2026.json"

    def lineup_for(self, fx: dict, now) -> Tuple[List[LineupPlayer], bool]:
        captured = iso(now)
        mid = _match_id(fx)
        players: List[LineupPlayer] = []
        confirmed_any = False
        for side, team in (("a", fx.get("team_a")), ("b", fx.get("team_b"))):
            xi = fx.get(f"starting_xi_{side}") or []
            conf = bool(fx.get(f"lineup_confirmed_{side}"))
            if xi and conf:
                confirmed_any = True
            for name in xi:
                players.append(LineupPlayer(
                    match_id=mid, team=team, player_name=str(name), position="",
                    is_starting=True, is_goalkeeper=False, source=self.name, captured_at=captured))
        return players, confirmed_any

    def injuries_for(self, fx: dict, now) -> List[InjuryRecord]:
        captured = iso(now)
        mid = _match_id(fx)
        out: List[InjuryRecord] = []
        for side, team in (("a", fx.get("team_a")), ("b", fx.get("team_b"))):
            for name in (fx.get(f"unavailable_players_{side}") or []):
                out.append(InjuryRecord(match_id=mid, team=team, player_name=str(name),
                                        status="unavailable", source=self.name, captured_at=captured))
        return out


class ApiFootballSource:
    """API-Football: /fixtures/lineups y /injuries (documentadas).

    Resuelve el fixture id desde ``fixture['api_football_fixture_id']`` si existe;
    sin key o sin id resoluble, devuelve vacío (no rompe, no inventa)."""

    name = "api_football"

    def __init__(self, api_key: str = "", base_url: str = API_FOOTBALL_BASE_URL,
                 http_fetch: Callable[..., str] = None, timeout: int = 20):
        self.api_key = api_key or os.environ.get("API_FOOTBALL_KEY", "").strip()
        self.base_url = base_url.rstrip("/")
        self._fetch = http_fetch
        self.timeout = timeout

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"x-apisports-key": self.api_key, "Accept": "application/json"}

    def _get(self, path: str, params: dict):
        if not self.has_key:
            return None
        from urllib.parse import urlencode
        url = f"{self.base_url}{path}?{urlencode(params)}"
        fetch = self._fetch or (lambda u, t=self.timeout: _http_fetch(u, self._headers(), t))
        try:
            body = fetch(url, self.timeout) if self._fetch else fetch(url)
            return json.loads(body)
        except (urllib.error.URLError, OSError, ValueError):
            return None

    @staticmethod
    def _fixture_id(fx: dict) -> Optional[str]:
        fid = fx.get("api_football_fixture_id")
        return str(fid) if fid else None

    def lineup_for(self, fx: dict, now) -> Tuple[List[LineupPlayer], bool]:
        fid = self._fixture_id(fx)
        if not (self.has_key and fid):
            return [], False
        data = self._get("/fixtures/lineups", {"fixture": fid})
        return self.parse_lineups(data, fx, now)

    def parse_lineups(self, data, fx: dict, now) -> Tuple[List[LineupPlayer], bool]:
        captured = iso(now)
        mid = _match_id(fx)
        players: List[LineupPlayer] = []
        if not data or not isinstance(data.get("response"), list):
            return [], False
        for team_block in data["response"]:
            team = (team_block.get("team") or {}).get("name") or ""
            for entry in team_block.get("startXI", []) or []:
                p = entry.get("player") or {}
                pos = str(p.get("pos") or "")
                players.append(LineupPlayer(
                    match_id=mid, team=team, player_name=str(p.get("name") or ""),
                    position=pos, is_starting=True, is_goalkeeper=(pos.upper() == "G"),
                    source=self.name, captured_at=captured))
        confirmed = len(players) > 0  # API publica el XI solo cuando está anunciado
        return players, confirmed

    def injuries_for(self, fx: dict, now) -> List[InjuryRecord]:
        fid = self._fixture_id(fx)
        if not (self.has_key and fid):
            return []
        data = self._get("/injuries", {"fixture": fid})
        return self.parse_injuries(data, fx, now)

    def parse_injuries(self, data, fx: dict, now) -> List[InjuryRecord]:
        captured = iso(now)
        mid = _match_id(fx)
        out: List[InjuryRecord] = []
        if not data or not isinstance(data.get("response"), list):
            return []
        for item in data["response"]:
            p = item.get("player") or {}
            team = (item.get("team") or {}).get("name") or ""
            out.append(InjuryRecord(match_id=mid, team=team, player_name=str(p.get("name") or ""),
                                    status=str(p.get("type") or p.get("reason") or "out"),
                                    source=self.name, captured_at=captured))
        return out


class CompositeSource:
    """Intenta varias fuentes en orden; la primera con XI confirmado gana."""

    name = "composite"

    def __init__(self, sources):
        self.sources = list(sources)

    def lineup_for(self, fx, now):
        fallback = ([], False)
        for s in self.sources:
            players, confirmed = s.lineup_for(fx, now)
            if confirmed and players:
                return players, True
            if players and not fallback[0]:
                fallback = (players, False)
        return fallback

    def injuries_for(self, fx, now):
        for s in self.sources:
            recs = s.injuries_for(fx, now)
            if recs:
                return recs
        return []


def default_source() -> CompositeSource:
    """API-Football (si hay key+id) y luego el feed local."""
    return CompositeSource([ApiFootballSource(), FeedSource()])
