#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$SCRIPT_DIR/com.jacquesbentata.quiniela2026.autoupdate.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_DST="$LAUNCH_AGENTS_DIR/com.jacquesbentata.quiniela2026.autoupdate.plist"

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$SCRIPT_DIR/logs"
cp "$PLIST_SRC" "$PLIST_DST"

launchctl bootout "gui/$(id -u)" "$PLIST_DST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/com.jacquesbentata.quiniela2026.autoupdate"
launchctl kickstart -k "gui/$(id -u)/com.jacquesbentata.quiniela2026.autoupdate"

echo "Auto-actualizacion instalada en $PLIST_DST"
echo "Se ejecuta cada 5 minutos."
