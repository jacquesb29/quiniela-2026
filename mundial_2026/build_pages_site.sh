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
bracket_path = script_dir / "llave_actual_2026.json"
fixtures_payload = []
teams_payload = {}
history_payload = {}
bracket_payload = {}
dashboard_updated_at = None
if fixtures_path.exists():
    fixtures_payload = json.loads(fixtures_path.read_text())
if teams_path.exists():
    teams_payload = json.loads(teams_path.read_text())
if history_path.exists():
    history_payload = json.loads(history_path.read_text())
if bracket_path.exists():
    bracket_payload = json.loads(bracket_path.read_text())
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
    "live_refresh_interval_minutes": 5,
    "scoreline_refresh_interval_minutes": 5,
    "fast_dashboard_refresh_interval_minutes": 5,
    "deep_bracket_refresh_interval_minutes": 480,
    "deep_bracket_minimum_iterations": 100000,
    "full_100k_bracket_refresh_interval_minutes": 480,
    "full_100k_bracket_workflow": "quiniela-100k.yml",
    "full_100k_bracket_update_policy": "La llave 100k no corre cada 5 minutos: se publica cada 8 horas, se puede lanzar manualmente despues de cambios grandes, tambien corre tras push relevante de modelo/datos, y el tablero live de 5 minutos sigue usando la ultima llave profunda publicada.",
    "update_policy_summary": "Marcadores, picks y lectura in-play: cada 5 minutos. La llave profunda publicada usa 100k como referencia estable y se refresca cada 8 horas, manualmente o por push relevante.",
    "in_play_enabled": True,
    "delivery": "github_actions_pages",
    "monte_carlo_iterations": bracket_payload.get("iterations"),
    "scoreline_engine": bracket_payload.get("scoreline_engine"),
    "explicit_variable_blocks": [
        "squad_market_value",
        "top_5_players_value_share",
        "value_depth_ratio",
        "population_gdp_league_strength",
        "pre_world_cup_physical_load",
        "advanced_style_xT_progression_PPDA_field_tilt",
        "tactical_matchup_compatibility",
        "geography_2026_travel_heat_surface_timezone",
        "granular_penalties_taker_keeper_pressure_matchup",
    ],
    "bracket_recalculated_from_scoreline_ensemble": bracket_payload.get("bracket_recalculated_from_scoreline_ensemble"),
    "bracket_recalculation_policy": bracket_payload.get("recalculation_policy"),
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
