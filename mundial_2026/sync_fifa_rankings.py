#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_FILE = SCRIPT_DIR / "teams_2026.json"
FIFA_BY_COUNTRY_ENDPOINT = "https://inside.fifa.com/api/rankings/by-country"


def fetch_country_ranking(country_code: str) -> Tuple[float, int, str]:
    query = urlencode(
        {
            "gender": 1,
            "footballType": "football",
            "locale": "en",
            "countryCode": country_code,
        }
    )
    request = Request(
        f"{FIFA_BY_COUNTRY_ENDPOINT}?{query}",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    latest = (((payload.get("Data") or {}).get("Latest") or [{}]) or [{}])[0]
    rank = int(latest["Rank"])
    points = float(latest["Points"])
    pub_date = latest.get("PubDate") or ""
    return points, rank, pub_date


def main() -> int:
    payload = json.loads(DATA_FILE.read_text())
    teams = payload.get("teams", [])
    ranking_as_of = None

    for team in teams:
        country_code = team.get("fifa_country_code")
        if not country_code:
            print(f"Saltando {team.get('name')}: falta fifa_country_code", file=sys.stderr)
            continue
        try:
            points, rank, pub_date = fetch_country_ranking(str(country_code))
        except (HTTPError, URLError, KeyError, ValueError, TimeoutError) as exc:
            print(f"Error al sincronizar {team.get('name')} ({country_code}): {exc}", file=sys.stderr)
            return 1
        team["fifa_points"] = round(points, 2)
        team["fifa_rank"] = rank
        ranking_as_of = pub_date or ranking_as_of

    meta = payload.setdefault("meta", {})
    if ranking_as_of:
        meta["fifa_rankings_as_of"] = ranking_as_of
    meta["fifa_rankings_source"] = FIFA_BY_COUNTRY_ENDPOINT
    meta["fifa_rankings_synced_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    DATA_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
    print(f"Ranking FIFA sincronizado en {DATA_FILE}")
    if ranking_as_of:
        print(f"Fecha oficial FIFA: {ranking_as_of}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
