"""Runner F1.4: genera outputs/market/market_decision_log.csv desde el gap modelo-mercado.

Lee `outputs/market/market_model_gap.csv` (F1.3) y aplica la regla de decisión
(`worldcup2026.market.decision.decide_pick`). SOLO decide y advierte: NO integra odds
al modelo, NO cambia la predicción interna ni picks del modelo, NO toca
pesos/lambdas/metodología/Penca.

`has_traceable_reason` se deja en False hasta T-60 (F1.5), donde se cablearán
alineaciones/bajas/portero confirmados.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup2026.market.decision import DECISION_COLUMNS, decide_pick, decision_to_row  # noqa: E402

GAP_CSV = ROOT / "outputs" / "market" / "market_model_gap.csv"
DECISION_CSV = ROOT / "outputs" / "market" / "market_decision_log.csv"


def _opt_float(value: object) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "si", "sí"}


def build_decision_rows():
    if not GAP_CSV.exists():
        print(f"[error] no existe {GAP_CSV}", file=sys.stderr)
        return []
    with GAP_CSV.open(newline="", encoding="utf-8") as handle:
        gap_rows = list(csv.DictReader(handle))
    rows = []
    for gap in gap_rows:
        verdict = decide_pick(
            match_id=gap.get("match_id", ""),
            model_pick=(gap.get("model_pick") or None),
            market_pick=(gap.get("market_pick") or None),
            contradicts_market=_as_bool(gap.get("contradicts_market")),
            contradiction_severity=(gap.get("contradiction_severity") or "none"),
            gap_1x2_total_variation=_opt_float(gap.get("gap_1x2_total_variation")),
            gap_status=(gap.get("gap_status") or "sin_muestra"),
            has_traceable_reason=False,  # T-60 (F1.5) lo cableará
        )
        rows.append(decision_to_row(verdict))
    return rows


def write_decision_csv(rows, output_path: str | Path = DECISION_CSV) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DECISION_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> int:
    rows = build_decision_rows()
    write_decision_csv(rows)
    counts = {}
    for row in rows:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    print(f"Filas escritas: {len(rows)} en {DECISION_CSV}")
    for action in ("trust_model", "keep_pick", "lower_confidence", "shade_to_market",
                   "follow_market", "no_market_available"):
        print(f"  {action}: {counts.get(action, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
