from __future__ import annotations

import multiprocessing as mp
import random
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Sequence

from .config import PARAMS


def default_parallel_workers(iterations: int) -> int:
    if iterations < PARAMS.auto_parallel_min_iterations:
        return 1
    return max(PARAMS.auto_parallel_max_workers_floor, mp.cpu_count() - 1)


def empty_tournament_summary(teams: Dict[str, Any]) -> Dict[str, dict]:
    return {
        name: {
            "appear": 0,
            "advance_group": 0,
            "reach_round16": 0,
            "reach_quarterfinal": 0,
            "reach_semifinal": 0,
            "reach_final": 0,
            "third_place": 0,
            "fourth_place": 0,
            "champion": 0,
            "group_winner": 0,
            "avg_group_points": 0.0,
            "avg_goals_for": 0.0,
            "avg_goals_against": 0.0,
        }
        for name in teams
    }


def empty_bracket_aggregate(match_ids: Sequence[str]) -> Dict[str, dict]:
    return {
        match_id: {
            "outcomes": {},
            "winner": {},
            "went_extra_time": 0,
            "went_penalties": 0,
            "penalty_scores": {},
        }
        for match_id in match_ids
    }


def merge_tournament_summary(target: Dict[str, dict], batch_summary: Dict[str, dict]) -> None:
    for team_name, stats in batch_summary.items():
        current = target[team_name]
        for key, value in stats.items():
            current[key] += value


def merge_bracket_aggregate(target: Dict[str, dict], batch_aggregate: Dict[str, dict]) -> None:
    for match_id, aggregate in batch_aggregate.items():
        current = target[match_id]
        current["went_extra_time"] += aggregate.get("went_extra_time", 0)
        current["went_penalties"] += aggregate.get("went_penalties", 0)
        for outcome_key, count in aggregate.get("outcomes", {}).items():
            current["outcomes"][outcome_key] = current["outcomes"].get(outcome_key, 0) + count
        for winner, count in aggregate.get("winner", {}).items():
            current["winner"][winner] = current["winner"].get(winner, 0) + count
        for score_key, count in aggregate.get("penalty_scores", {}).items():
            current["penalty_scores"][score_key] = current["penalty_scores"].get(score_key, 0) + count


def run_parallel_batches(
    *,
    iterations: int,
    workers: int,
    seed: Optional[int],
    worker_fn: Callable[[int, int, Dict[str, Any], dict, Optional[dict]], dict],
    teams: Dict[str, Any],
    config: dict,
    initial_payload: Optional[dict],
    progress_every: int = 0,
) -> List[dict]:
    workers = max(1, workers)
    if workers == 1:
        return [worker_fn(iterations, seed or 0, teams, config, initial_payload)]

    base_seed = seed if seed is not None else random.randrange(1, 10_000_000)
    batch_size = iterations // workers
    remainder = iterations % workers
    completed_iterations = 0
    results: List[dict] = []
    try:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for batch_index in range(workers):
                size = batch_size + (1 if batch_index < remainder else 0)
                if size <= 0:
                    continue
                future = executor.submit(
                    worker_fn,
                    size,
                    base_seed + batch_index,
                    teams,
                    config,
                    initial_payload,
                )
                futures[future] = size
            for future in as_completed(futures):
                results.append(future.result())
                if progress_every:
                    completed_iterations += futures[future]
                    print(f"Progreso: {min(completed_iterations, iterations)}/{iterations} iteraciones")
        return results
    except (PermissionError, OSError):
        return [worker_fn(iterations, base_seed, teams, config, initial_payload)]
