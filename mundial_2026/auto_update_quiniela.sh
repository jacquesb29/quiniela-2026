#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNNER="$SCRIPT_DIR/quiniela_2026.command"
MODEL="$SCRIPT_DIR/modelo_quiniela_2026.py"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LIVE_SYNC="$SCRIPT_DIR/sync_live_data_2026.py"
LIVE_FIXTURES="$SCRIPT_DIR/fixtures_live_2026.json"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/auto_update.log"
ITERATIONS="${BRACKET_ITERATIONS:-300}"
ICLOUD_SYNC="${ICLOUD_SYNC:-1}"
ICLOUD_ROOT="$HOME/Library/Mobile Documents/com~apple~CloudDocs"
ICLOUD_DIR="$ICLOUD_ROOT/quiniela_2026"

mkdir -p "$LOG_DIR"

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Inicio auto-update"
  cd "$ROOT_DIR"
  "$PYTHON_BIN" "$LIVE_SYNC"
  "$PYTHON_BIN" "$MODEL" state-reset
  "$PYTHON_BIN" "$MODEL" fixtures "$LIVE_FIXTURES"
  "$RUNNER" bracket "$ITERATIONS"
  "$PYTHON_BIN" "$MODEL" project-dashboard --fixtures "$LIVE_FIXTURES"
  if [[ "$ICLOUD_SYNC" != "0" && -d "$ICLOUD_ROOT" ]]; then
    mkdir -p "$ICLOUD_DIR"
    cp "$LIVE_FIXTURES" "$ICLOUD_DIR/"
    cp "$SCRIPT_DIR/llave_actual_2026.md" "$ICLOUD_DIR/"
    cp "$SCRIPT_DIR/llave_actual_2026.json" "$ICLOUD_DIR/"
    cp "$SCRIPT_DIR/reporte_actual_2026.md" "$ICLOUD_DIR/"
    cp "$SCRIPT_DIR/dashboard_actual_2026.html" "$ICLOUD_DIR/"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sync iCloud -> $ICLOUD_DIR"
  fi
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Fin auto-update"
} >>"$LOG_FILE" 2>&1
