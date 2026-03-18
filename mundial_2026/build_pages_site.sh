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
payload = {
    "updated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "refresh_interval_minutes": 5,
    "in_play_enabled": True,
    "delivery": "github_actions_pages",
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
