"""Genera outputs/market/market_implied_probabilities.csv desde el CSV manual (F1.1).

No consume ni modifica el modelo. Convierte cada snapshot prepartido válido a
probabilidades sin vig y señales de mercado. Las filas posteriores al kickoff se
excluyen (anti-leakage). Las filas inválidas se omiten con log a stderr.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .devig import MARKET_IMPLIED_COLUMNS, market_implied_to_row, odds_to_implied
from .odds_ingest import load_odds_input, validate_odds_snapshot


def build_market_implied_rows(input_path: str | Path, *, method: str = "proportional") -> List[dict]:
    rows: List[dict] = []
    for snap in load_odds_input(input_path):
        errors = validate_odds_snapshot(snap)
        if errors:
            print(f"[skip inválido] {snap.match_id}/{snap.snapshot_type}: {'; '.join(errors)}", file=sys.stderr)
            continue
        implied = odds_to_implied(snap, method=method, require_prematch=True)
        if implied is None:
            print(f"[skip no-prematch/sin-mercado] {snap.match_id}/{snap.snapshot_type}", file=sys.stderr)
            continue
        rows.append(market_implied_to_row(implied))
    return rows


def write_market_implied_csv(rows: Sequence[dict], output_path: str | Path) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MARKET_IMPLIED_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="F1.1: odds manuales -> probabilidades sin vig.")
    parser.add_argument("--input", default="data/market_odds_input.csv")
    parser.add_argument("--output", default="outputs/market/market_implied_probabilities.csv")
    parser.add_argument("--method", default="proportional")
    args = parser.parse_args(argv)
    rows = build_market_implied_rows(args.input, method=args.method)
    write_market_implied_csv(rows, args.output)
    print(f"Escritas {len(rows)} filas en {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
