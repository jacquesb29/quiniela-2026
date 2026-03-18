#!/bin/zsh
set -euo pipefail

PLIST_DST="$HOME/Library/LaunchAgents/com.jacquesbentata.quiniela2026.autoupdate.plist"

launchctl bootout "gui/$(id -u)" "$PLIST_DST" >/dev/null 2>&1 || true
rm -f "$PLIST_DST"

echo "Auto-actualizacion desinstalada de $PLIST_DST"
