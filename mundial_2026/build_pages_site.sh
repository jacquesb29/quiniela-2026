#!/usr/bin/env bash
set -euo pipefail

SCRIPT_HOME="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_DIR="${WORLDCUP_PUBLISH_ROOT:-$SCRIPT_HOME}"
SITE_DIR="${WORLDCUP_PUBLISH_SITE_DIR:-$SCRIPT_DIR/site}"
export SCRIPT_DIR

mkdir -p "$SITE_DIR"

cp "$SCRIPT_DIR/dashboard_actual_2026.html" "$SITE_DIR/index.html"
cp "$SCRIPT_DIR/dashboard_actual_2026.html" "$SITE_DIR/dashboard_actual_2026.html"
cp "$SCRIPT_DIR/reporte_actual_2026.md" "$SITE_DIR/reporte_actual_2026.md"
cp "$SCRIPT_DIR/llave_actual_2026.md" "$SITE_DIR/llave_actual_2026.md"
cp "$SCRIPT_DIR/llave_actual_2026.json" "$SITE_DIR/llave_actual_2026.json"
cp "$SCRIPT_DIR/fixtures_live_2026.json" "$SITE_DIR/fixtures_live_2026.json"
cp "$SCRIPT_DIR/historical_features_1950.json" "$SITE_DIR/historical_features_1950.json"

python3 - <<'PY'
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

script_dir = Path(os.environ["SCRIPT_DIR"])
site_dir = script_dir / "site"
fixtures_path = script_dir / "fixtures_live_2026.json"
teams_path = script_dir / "teams_2026.json"
history_path = script_dir / "historical_features_1950.json"
dashboard_path = script_dir / "dashboard_actual_2026.html"
fixtures_payload = []
teams_payload = {}
history_payload = {}
dashboard_updated_at = None
if fixtures_path.exists():
    fixtures_payload = json.loads(fixtures_path.read_text())
if teams_path.exists():
    teams_payload = json.loads(teams_path.read_text())
if history_path.exists():
    history_payload = json.loads(history_path.read_text())
if dashboard_path.exists():
    match = re.search(r'<meta name="dashboard-updated-at" content="([^"]+)"', dashboard_path.read_text())
    if match:
        dashboard_updated_at = match.group(1)
live_sources = sorted({item.get("source") for item in fixtures_payload if item.get("source")})
live_providers = sorted({item.get("live_feed_provider") for item in fixtures_payload if item.get("live_feed_provider")})
published_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
payload = {
    "updated_at_utc": published_at,
    "publication_updated_at_utc": published_at,
    "dashboard_updated_at_utc": dashboard_updated_at,
    "timestamp_consistency_note": "latest.json se escribe despues de copiar el HTML; compara dashboard_updated_at_utc contra publication_updated_at_utc para detectar desfases reales de publicacion o cache.",
    "refresh_interval_minutes": 5,
    "in_play_enabled": True,
    "delivery": "github_actions_pages",
    "live_feed_stack": live_sources or ["espn_scoreboard"],
    "live_feed_providers": live_providers,
    "official_fifa_rankings_as_of": (teams_payload.get("meta") or {}).get("fifa_rankings_as_of"),
    "historical_base": {
        "from_date": (history_payload.get("meta") or {}).get("from_date"),
        "official_matches": (history_payload.get("meta") or {}).get("official_matches_since_start"),
        "minimum_official_matches_required": (history_payload.get("meta") or {}).get("minimum_official_matches_required"),
        "definition": (history_payload.get("meta") or {}).get("official_match_definition"),
    },
    "files": {
        "dashboard": "dashboard_actual_2026.html",
        "report": "reporte_actual_2026.md",
        "bracket_markdown": "llave_actual_2026.md",
        "bracket_json": "llave_actual_2026.json",
        "fixtures_live": "fixtures_live_2026.json",
        "historical_features": "historical_features_1950.json",
    },
}
(site_dir / "latest.json").write_text(json.dumps(payload, indent=2))
PY
