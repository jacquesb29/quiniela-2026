#!/usr/bin/env bash
# Scheduler OPCIONAL para la operación diaria de la quiniela 2026.
#
# NO se activa solo. Por defecto solo MUESTRA las instrucciones (modo dry-run).
# Para instalar el cron hay que pasar --install EXPLÍCITAMENTE y confirmar.
#
# Corre run_daily_quiniela_ops.py cada 30 min (útil en días de partido).
# El runner es operativo: NO cambia el modelo, pesos, lambdas, Penca ni flags.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$(command -v python3 || echo /usr/bin/python3)"
CMD="cd ${REPO_DIR} && ${PYTHON_BIN} run_daily_quiniela_ops.py >> ${REPO_DIR}/outputs/ops/cron.log 2>&1"
# Cada 30 minutos, todos los días (filtra días de partido con tu propio criterio si quieres).
CRON_LINE="*/30 * * * * ${CMD}"
CRON_TAG="# quiniela-2026-daily-ops"

echo "=== Operación diaria de la quiniela 2026 — scheduler ==="
echo "Repo:    ${REPO_DIR}"
echo "Python:  ${PYTHON_BIN}"
echo "Comando: ${CMD}"
echo
echo "Línea de cron propuesta (cada 30 minutos):"
echo "  ${CRON_LINE}  ${CRON_TAG}"
echo

if [[ "${1:-}" == "--install" ]]; then
  read -r -p "¿Instalar esta línea en tu crontab? [y/N] " ans
  if [[ "${ans:-N}" == "y" || "${ans:-N}" == "Y" ]]; then
    mkdir -p "${REPO_DIR}/outputs/ops"
    ( crontab -l 2>/dev/null | grep -v -F "${CRON_TAG}" ; echo "${CRON_LINE}  ${CRON_TAG}" ) | crontab -
    echo "Instalado. Revisa con: crontab -l"
  else
    echo "Cancelado. No se modificó el crontab."
  fi
else
  echo "Modo solo-instrucciones (no se tocó el crontab)."
  echo "Para instalar: scripts/setup_quiniela_cron.sh --install"
  echo "Para correr una vez ahora: cd ${REPO_DIR} && ${PYTHON_BIN} run_daily_quiniela_ops.py"
  echo "Para quitar el cron: crontab -l | grep -v '${CRON_TAG}' | crontab -"
fi
