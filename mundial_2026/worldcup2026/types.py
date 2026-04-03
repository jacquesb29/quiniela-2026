from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ModelOutput:
    name: str
    dist: Dict[Tuple[int, int], float]
    probs: Dict[str, float]
    weight: float
    top_score: Tuple[str, float]


@dataclass(frozen=True)
class KnockoutResolution:
    winner: str
    loser: str
    score_a: int
    score_b: int
    extra_time_score_a: int
    extra_time_score_b: int
    went_extra_time: bool
    went_penalties: bool
    penalty_score_a: Optional[int]
    penalty_score_b: Optional[int]


@dataclass(frozen=True)
class BacktestMetrics:
    completed_matches: int
    regular_time_samples: int
    advancement_samples: int
    favorite_hit_rate: Optional[float]
    top1_score_hit_rate: Optional[float]
    top3_score_hit_rate: Optional[float]
    brier_result: Optional[float]
    logloss_result: Optional[float]
    brier_advance: Optional[float]
    logloss_advance: Optional[float]
    market_logloss_result: Optional[float]
    calibration_buckets: List[Dict[str, float]]
    brier_reliability: Optional[float] = None
    brier_resolution: Optional[float] = None
    brier_uncertainty: Optional[float] = None
    temporal_cv_logloss: Optional[float] = None
    temporal_cv_brier: Optional[float] = None
    temporal_cv_accuracy: Optional[float] = None
