"""Caché en disco para respuestas de odds (TTL configurable).

JSON simple por clave. ``now_fn`` inyectable para tests deterministas.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = ROOT / "outputs" / "odds_cache"


class OddsCache:
    def __init__(self, directory: Path = DEFAULT_CACHE_DIR, ttl_seconds: int = 600,
                 now_fn: Callable[[], float] = time.time):
        self.directory = Path(directory)
        self.ttl_seconds = ttl_seconds
        self._now = now_fn

    def _path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return self.directory / f"{digest}.json"

    def get(self, key: str):
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        stored_at = float(payload.get("stored_at", 0))
        if self._now() - stored_at > self.ttl_seconds:
            return None  # caduco
        return payload.get("value")

    def get_stale(self, key: str):
        """Devuelve el valor aunque esté caduco (para fallback)."""
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("value")
        except (ValueError, OSError):
            return None

    def set(self, key: str, value) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {"stored_at": self._now(), "key": key, "value": value}
        self._path(key).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def clear(self) -> None:
        if self.directory.exists():
            for p in self.directory.glob("*.json"):
                p.unlink()
