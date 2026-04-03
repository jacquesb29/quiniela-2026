from __future__ import annotations

import logging
import sys


def setup_logger(name: str = "worldcup2026", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


log = setup_logger()
