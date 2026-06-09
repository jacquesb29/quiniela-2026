#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def fetch_bytes(url: str, timeout: int) -> bytes:
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.read()
    except Exception as first_error:
        result = subprocess.run(
            ["curl", "-fsSL", "--max-time", str(timeout), "--location", url],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            return result.stdout
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or str(first_error)) from first_error


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch the public bracket only when it is at least as deep as the local snapshot."
    )
    parser.add_argument("--json-url", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--md-url", required=True)
    parser.add_argument("--md-output", required=True)
    parser.add_argument("--min-iterations", type=int, default=100000)
    parser.add_argument("--timeout", type=int, default=8)
    args = parser.parse_args()

    json_output = Path(args.json_output)
    md_output = Path(args.md_output)

    try:
        json_bytes = fetch_bytes(args.json_url, args.timeout)
        payload = json.loads(json_bytes.decode("utf-8"))
    except (OSError, URLError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"No se pudo leer llave publica; se conserva local: {exc}")
        return

    iterations = int(payload.get("iterations") or 0)
    if iterations < args.min_iterations:
        print(
            "Llave publica ignorada: "
            f"{iterations} iteraciones < minimo {args.min_iterations}. Se conserva local."
        )
        return

    json_output.write_bytes(json_bytes)
    try:
        md_output.write_bytes(fetch_bytes(args.md_url, args.timeout))
    except (OSError, URLError, RuntimeError) as exc:
        print(f"Markdown publico no disponible; JSON profundo actualizado igualmente: {exc}")
    print(f"Llave publica aceptada: {iterations} iteraciones.")


if __name__ == "__main__":
    main()
