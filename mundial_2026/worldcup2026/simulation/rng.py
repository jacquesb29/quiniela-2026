from __future__ import annotations

from typing import Optional

import numpy as np
from numpy.random import Generator, PCG64


class FastRNG:
    __slots__ = ("_rng", "_poisson_buffer", "_poisson_idx", "_uniform_buffer", "_uniform_idx")

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = Generator(PCG64(seed))
        self._poisson_buffer: dict[int, np.ndarray] = {}
        self._poisson_idx: dict[int, int] = {}
        self._uniform_buffer = self._rng.random(8192)
        self._uniform_idx = 0

    def poisson(self, lmbda: float) -> int:
        if lmbda <= 0.005:
            return 0
        key = int(round(float(lmbda) * 100.0))
        idx = self._poisson_idx.get(key, 0)
        buf = self._poisson_buffer.get(key)
        if buf is None or idx >= len(buf):
            buf = self._rng.poisson(max(float(lmbda), 0.001), size=4096)
            self._poisson_buffer[key] = buf
            idx = 0
        self._poisson_idx[key] = idx + 1
        return int(buf[idx])

    def random(self) -> float:
        if self._uniform_idx >= len(self._uniform_buffer):
            self._uniform_buffer = self._rng.random(8192)
            self._uniform_idx = 0
        value = float(self._uniform_buffer[self._uniform_idx])
        self._uniform_idx += 1
        return value


_GLOBAL_RNG = FastRNG()


def seed_fast_rng(seed: Optional[int]) -> None:
    global _GLOBAL_RNG
    _GLOBAL_RNG = FastRNG(seed)


def poisson_sample_fast(lmbda: float) -> int:
    return _GLOBAL_RNG.poisson(lmbda)


def fast_random() -> float:
    return _GLOBAL_RNG.random()
