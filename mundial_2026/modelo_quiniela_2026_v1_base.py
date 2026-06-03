"""Baseline checkpoint for the Quiniela 2026 model.

This file deliberately does not import and run the current model, because that
would drift every time `modelo_quiniela_2026.py` changes. The frozen baseline is
the exact model file at commit 0370dfd with the SHA-256 recorded below.

Use this checkpoint as the fixed comparison target for future ablation tests,
backtesting, learned weights and Penca optimization.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

BASELINE_VERSION = "v1_base"
BASELINE_COMMIT = "0370dfd"
BASELINE_MODEL_PATH = "mundial_2026/modelo_quiniela_2026.py"
BASELINE_SHA256 = "e49da3c5dc296d85c6de46529686bde9e2f1e3fa965dba843cb10d2fa0b05ad0"
BASELINE_COMPONENTS = (
    "Elo internacional",
    "FIFA ranking / points",
    "plantilla y valor estructural",
    "historia oficial desde 1950",
    "entrenador, quimica, disciplina, defensa y ataque",
    "mercado/consenso externo como guardrail",
    "Poisson, Dixon-Coles, overdispersion, bivariante y ensamble",
    "Monte Carlo de 15.000 simulaciones",
    "estado dinamico",
    "optimizacion Penca Ovacion",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def current_model_path() -> Path:
    return repo_root() / BASELINE_MODEL_PATH


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root()), "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def baseline_matches_current() -> bool:
    path = current_model_path()
    return path.exists() and sha256_file(path) == BASELINE_SHA256


def baseline_status() -> dict[str, str | bool | tuple[str, ...]]:
    path = current_model_path()
    current_sha = sha256_file(path) if path.exists() else "missing"
    return {
        "baseline_version": BASELINE_VERSION,
        "baseline_commit": BASELINE_COMMIT,
        "current_commit": current_commit(),
        "model_path": BASELINE_MODEL_PATH,
        "baseline_sha256": BASELINE_SHA256,
        "current_sha256": current_sha,
        "matches_current_file": current_sha == BASELINE_SHA256,
        "components": BASELINE_COMPONENTS,
    }


def restore_hint() -> str:
    return (
        f"Para correr exactamente el baseline, usa `git checkout {BASELINE_COMMIT} -- "
        f"{BASELINE_MODEL_PATH}` o compara contra ese commit en el backtesting. "
        "No uses el modelo actual como baseline si el SHA ya cambio."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the frozen v1 baseline checkpoint.")
    parser.add_argument("--verify", action="store_true", help="Exit with non-zero status if the current model no longer matches v1.")
    args = parser.parse_args(argv)
    status = baseline_status()
    print(f"Baseline {status['baseline_version']} | commit {status['baseline_commit']}")
    print(f"Modelo: {status['model_path']}")
    print(f"SHA baseline: {status['baseline_sha256']}")
    print(f"SHA actual:    {status['current_sha256']}")
    print(f"Coincide con archivo actual: {status['matches_current_file']}")
    print("Componentes congelados:")
    for component in BASELINE_COMPONENTS:
        print(f"- {component}")
    if not status["matches_current_file"]:
        print(restore_hint())
    return 1 if args.verify and not status["matches_current_file"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
