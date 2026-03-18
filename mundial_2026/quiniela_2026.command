#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MODEL="$SCRIPT_DIR/modelo_quiniela_2026.py"
FIXTURES="$SCRIPT_DIR/fixtures_template.json"
LIVE_FIXTURES="$SCRIPT_DIR/fixtures_live_2026.json"
DRAW="$SCRIPT_DIR/tournament_2026_draw.json"
LIVE_SYNC="$SCRIPT_DIR/sync_live_data_2026.py"

usage() {
  cat <<'EOF'
Uso:
  ./mundial_2026/quiniela_2026.command help
  ./mundial_2026/quiniela_2026.command predict "España" Uruguay
  ./mundial_2026/quiniela_2026.command score "España" Uruguay 2 1
  ./mundial_2026/quiniela_2026.command score "España" Uruguay 1 1 round16
  ./mundial_2026/quiniela_2026.command knockout "España" Uruguay round16
  ./mundial_2026/quiniela_2026.command live-sync
  ./mundial_2026/quiniela_2026.command update
  ./mundial_2026/quiniela_2026.command simulate 1000
  ./mundial_2026/quiniela_2026.command bracket 1000
  ./mundial_2026/quiniela_2026.command dashboard
  ./mundial_2026/quiniela_2026.command state "España"
  ./mundial_2026/quiniela_2026.command reset

Comandos:
  predict   Predice un partido normal de fase de grupos o amistoso.
  score     Devuelve la probabilidad exacta de un marcador A-B.
            Opcional: agrega una etapa knockout al final.
  knockout  Predice un partido eliminatorio. Etapas validas:
            round32 round16 round8 round4 semifinal third_place final
  live-sync Sincroniza el fixture oficial y resultados reales desde el feed publico.
  update    Sincroniza feed publico, actualiza estado, llave y dashboard.
  simulate  Simula el torneo completo con Monte Carlo.
  bracket   Genera la llave proyectada actual y la guarda en llave_actual_2026.md.
  dashboard Genera un reporte actual con llave y probabilidades por partido.
  state     Muestra el estado dinamico guardado de una seleccion.
  reset     Reinicia tournament_state_2026.json.
EOF
}

cd "$ROOT_DIR"

if [[ $# -eq 0 ]]; then
  usage
  exit 0
fi

command_name="$1"
shift

case "$command_name" in
  help|-h|--help)
    usage
    ;;
  predict)
    if [[ $# -lt 2 ]]; then
      echo 'Faltan equipos. Ejemplo: ./mundial_2026/quiniela_2026.command predict "España" Uruguay' >&2
      exit 1
    fi
    "$PYTHON_BIN" "$MODEL" predict "$1" "$2" --monte-carlo 5000 --seed 7 --show-factors
    ;;
  score)
    if [[ $# -lt 4 ]]; then
      echo 'Faltan datos. Ejemplo: ./mundial_2026/quiniela_2026.command score "España" Uruguay 2 1' >&2
      exit 1
    fi
    if [[ $# -ge 5 ]]; then
      "$PYTHON_BIN" "$MODEL" score-prob "$1" "$2" "$3" "$4" --stage "$5"
    else
      "$PYTHON_BIN" "$MODEL" score-prob "$1" "$2" "$3" "$4"
    fi
    ;;
  knockout)
    if [[ $# -lt 3 ]]; then
      echo 'Faltan datos. Ejemplo: ./mundial_2026/quiniela_2026.command knockout "España" Uruguay round16' >&2
      exit 1
    fi
    "$PYTHON_BIN" "$MODEL" predict "$1" "$2" --stage "$3" --monte-carlo 5000 --seed 7 --show-factors
    ;;
  live-sync)
    "$PYTHON_BIN" "$LIVE_SYNC"
    ;;
  update)
    "$PYTHON_BIN" "$LIVE_SYNC"
    "$PYTHON_BIN" "$MODEL" state-reset
    "$PYTHON_BIN" "$MODEL" fixtures "$LIVE_FIXTURES"
    "$PYTHON_BIN" "$MODEL" project-bracket --config "$DRAW" --iterations 1200 --seed 7 --progress-every 300
    "$PYTHON_BIN" "$MODEL" project-dashboard --fixtures "$LIVE_FIXTURES"
    ;;
  simulate)
    iterations="${1:-1000}"
    "$PYTHON_BIN" "$MODEL" simulate-tournament --config "$DRAW" --iterations "$iterations" --top 48 --seed 7 --progress-every 250
    ;;
  bracket)
    iterations="${1:-1000}"
    "$PYTHON_BIN" "$MODEL" project-bracket --config "$DRAW" --iterations "$iterations" --seed 7 --progress-every 250
    ;;
  dashboard)
    if [[ -f "$LIVE_FIXTURES" ]]; then
      "$PYTHON_BIN" "$MODEL" project-dashboard --fixtures "$LIVE_FIXTURES"
    else
      "$PYTHON_BIN" "$MODEL" project-dashboard
    fi
    ;;
  state)
    if [[ $# -lt 1 ]]; then
      echo 'Falta el equipo. Ejemplo: ./mundial_2026/quiniela_2026.command state "España"' >&2
      exit 1
    fi
    "$PYTHON_BIN" "$MODEL" state-show --team "$1"
    ;;
  reset)
    "$PYTHON_BIN" "$MODEL" state-reset
    ;;
  *)
    echo "Comando no reconocido: $command_name" >&2
    usage
    exit 1
    ;;
esac
