"""Pipeline único de mercado/T-60 (cierre operativo F1).

Ejecuta en orden los pasos ya implementados (F1.1, F1.3, F1.4, F1.5, F1.6):
  1) build_market_implied      (odds manuales -> sin vig)
  2) build_market_model_gap    (modelo vs mercado)
  3) build_market_decisions    (regla de decisión)
  4) run_t60_update            (flujo T-60, si hay data/t60_inputs.csv)
  5) build_market_dashboard    (HTML de lectura)

SOLO orquesta runners de lectura/decisión. NO toca el modelo, pesos, lambdas,
metodología ni selector Penca. Falla claramente si falta el archivo crítico
(data/market_odds_input.csv) y NO se rompe si no hay mercado usable.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MARKET_INPUT = ROOT / "data" / "market_odds_input.csv"
T60_INPUT = ROOT / "data" / "t60_inputs.csv"
MARKET_DIR = ROOT / "outputs" / "market"
DASHBOARD_HTML = MARKET_DIR / "market_dashboard.html"


def _count_csv(path: Path, predicate) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for row in csv.DictReader(handle) if predicate(row))


def _is_true(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "si", "sí"}


def summarize_pipeline(market_dir: str | Path = MARKET_DIR) -> dict:
    market_dir = Path(market_dir)
    gap_csv = market_dir / "market_model_gap.csv"
    t60_csv = market_dir / "t60_decision_log.csv"
    return {
        "partidos_con_mercado": _count_csv(gap_csv, lambda r: (r.get("gap_status") or "") == "calculado"),
        "partidos_sin_mercado": _count_csv(gap_csv, lambda r: (r.get("gap_status") or "") == "sin_muestra"),
        "picks_changed": _count_csv(t60_csv, lambda r: _is_true(r.get("changed"))),
        "strong_contradictions": _count_csv(
            gap_csv, lambda r: _is_true(r.get("contradicts_market")) and (r.get("contradiction_severity") or "") == "strong"
        ),
        "dashboard_html": str(market_dir / "market_dashboard.html"),
    }


def main(argv=None, *, market_input: Path = MARKET_INPUT, t60_input: Path = T60_INPUT) -> int:
    if not Path(market_input).exists():
        print(f"ERROR: falta archivo crítico {market_input}. "
              f"Crea data/market_odds_input.csv antes de correr el pipeline.", file=sys.stderr)
        return 2

    # Importes locales para no ejecutar el modelo si falla la validación crítica.
    from worldcup2026.market import build_market_implied
    import build_market_model_gap
    import build_market_decisions
    import build_market_dashboard

    print("[1/5] build_market_implied ...")
    build_market_implied.main([])
    print("[2/5] build_market_model_gap ...")
    build_market_model_gap.main()
    print("[3/5] build_market_decisions ...")
    build_market_decisions.main()

    if Path(t60_input).exists():
        print("[4/5] run_t60_update ...")
        import run_t60_update
        run_t60_update.main()
    else:
        print(f"[4/5] run_t60_update OMITIDO: no existe {t60_input} (T-60 opcional)")

    print("[5/5] build_market_dashboard ...")
    build_market_dashboard.main()

    summary = summarize_pipeline()
    print("\n================ RESUMEN PIPELINE MERCADO/T-60 ================")
    print(f"Partidos con mercado calculable : {summary['partidos_con_mercado']}")
    print(f"Partidos sin mercado            : {summary['partidos_sin_mercado']}")
    print(f"Picks cambiados en T-60         : {summary['picks_changed']}")
    print(f"Contradicciones fuertes         : {summary['strong_contradictions']}")
    print(f"Dashboard HTML                  : {summary['dashboard_html']}")
    print("===============================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
