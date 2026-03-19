#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$SCRIPT_DIR/site"
export SCRIPT_DIR

mkdir -p "$SITE_DIR"

cp "$SCRIPT_DIR/dashboard_actual_2026.html" "$SITE_DIR/index.html"
cp "$SCRIPT_DIR/dashboard_actual_2026.html" "$SITE_DIR/dashboard_actual_2026.html"
cp "$SCRIPT_DIR/reporte_actual_2026.md" "$SITE_DIR/reporte_actual_2026.md"
cp "$SCRIPT_DIR/llave_actual_2026.md" "$SITE_DIR/llave_actual_2026.md"
cp "$SCRIPT_DIR/llave_actual_2026.json" "$SITE_DIR/llave_actual_2026.json"
cp "$SCRIPT_DIR/fixtures_live_2026.json" "$SITE_DIR/fixtures_live_2026.json"

python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

script_dir = Path(os.environ["SCRIPT_DIR"])
site_dir = script_dir / "site"
fixtures_path = script_dir / "fixtures_live_2026.json"
teams_path = script_dir / "teams_2026.json"
fixtures_payload = []
teams_payload = {}
if fixtures_path.exists():
    fixtures_payload = json.loads(fixtures_path.read_text())
if teams_path.exists():
    teams_payload = json.loads(teams_path.read_text())
live_sources = sorted({item.get("source") for item in fixtures_payload if item.get("source")})
live_providers = sorted({item.get("live_feed_provider") for item in fixtures_payload if item.get("live_feed_provider")})
payload = {
    "updated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "refresh_interval_minutes": 5,
    "in_play_enabled": True,
    "delivery": "github_actions_pages",
    "live_feed_stack": live_sources or ["espn_scoreboard"],
    "live_feed_providers": live_providers,
    "official_fifa_rankings_as_of": (teams_payload.get("meta") or {}).get("fifa_rankings_as_of"),
    "files": {
        "dashboard": "dashboard_actual_2026.html",
        "report": "reporte_actual_2026.md",
        "bracket_markdown": "llave_actual_2026.md",
        "bracket_json": "llave_actual_2026.json",
        "fixtures_live": "fixtures_live_2026.json",
    },
}
(site_dir / "latest.json").write_text(json.dumps(payload, indent=2))
PY
