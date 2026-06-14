"""Runner F1.6: genera outputs/market/market_dashboard.html (lectura de outputs).

SOLO lee los CSV de mercado/T-60 (F1.1/F1.3/F1.4/F1.5) y validation_status.json y
renderiza un fragmento HTML por partido. NO recalcula lógica de mercado, NO toca el
modelo, pesos, lambdas, metodología ni selector Penca. Si faltan archivos, escribe
una sección "mercado/T-60 pendiente" sin romper.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.market.dashboard import load_market_outputs, render_market_dashboard_html  # noqa: E402

MARKET_DIR = ROOT / "outputs" / "market"
VALIDATION_STATUS_JSON = ROOT / "outputs" / "validation_status.json"
OUTPUT_HTML = MARKET_DIR / "market_dashboard.html"

_PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Mercado y T-60 — Mundial 2026</title></head>
<body>
{fragment}
</body></html>
"""


def main(argv=None) -> int:
    data = load_market_outputs(MARKET_DIR, VALIDATION_STATUS_JSON)
    fragment = render_market_dashboard_html(data)
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(_PAGE.format(fragment=fragment), encoding="utf-8")
    print(f"Dashboard de mercado escrito en {OUTPUT_HTML}")
    print(f"Partidos mostrados: {len(data['match_ids'])} | archivos disponibles: {data['available']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
