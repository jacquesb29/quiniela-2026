#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import math
import random
import re
import shutil
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from worldcup2026.calibration import empirical_bayes_shrinkage
from worldcup2026.config import PARAMS
from worldcup2026.constants import (
    BRACKET_MATCH_TITLES,
    COACH_OVERRIDES,
    DISCIPLINE_BY_CONFEDERATION,
    DISCIPLINE_OVERRIDES,
    GROUP_MATCH_PAIRS,
    HISTORICAL_BY_CONFEDERATION,
    KNOCKOUT_MATCHES,
    LOSER_NEXT_MATCH,
    R32_MATCHES,
    RESOURCE_BY_CONFEDERATION,
    RESOURCE_OVERRIDES,
    RIVALRIES,
    STAGE_ALIASES,
    STAGE_IMPORTANCE,
    TEAM_NAME_ALIASES,
    TEMPO_BY_CONFEDERATION,
    TRADITION_BONUS,
    TRAVEL_BY_CONFEDERATION,
    WINNER_NEXT_MATCH,
    WORLD_CUP_TITLES,
)
from worldcup2026.dashboard.backtesting import (
    compute_backtest_summary as calculate_compute_backtest_summary,
)
from worldcup2026.dashboard.charts import (
    render_chart_grid,
    render_dual_bar_chart,
    render_rank_chart,
)
from worldcup2026.dashboard.comparison import (
    compare_bracket_payloads as calculate_compare_bracket_payloads,
    compare_entry_predictions as calculate_compare_entry_predictions,
)
from worldcup2026.dashboard.html_builder import render_dashboard_html
from worldcup2026.data.historical import (
    estimated_fifa_points as calculate_estimated_fifa_points,
    fifa_points_are_proxy as calculate_fifa_points_are_proxy,
    fifa_points_bounds as calculate_fifa_points_bounds,
    fifa_points_value as calculate_fifa_points_value,
    fifa_rank_value as calculate_fifa_rank_value,
    fifa_reference_table as calculate_fifa_reference_table,
    fifa_strength_index as calculate_fifa_strength_index,
    historical_features_payload as calculate_historical_features_payload,
    historical_snapshot as calculate_historical_snapshot,
    proxy_historical_snapshot as calculate_proxy_historical_snapshot,
)
from worldcup2026.data.loader import (
    load_players as calculate_load_players,
    load_teams as calculate_load_teams,
    load_tournament_config as calculate_load_tournament_config,
    read_fixtures as calculate_read_fixtures,
)
from worldcup2026.data.state import (
    coerce_team_state as package_coerce_team_state,
    copy_states as package_copy_states,
    default_team_state as package_default_team_state,
    initial_team_states as package_initial_team_states,
    normalize_team_state as package_normalize_team_state,
    state_has_activity as package_state_has_activity,
)
from worldcup2026.distributions import (
    build_model_stack,
    cached_low_score_distribution,
    low_score_rho,
    model_blend_weights,
)
from worldcup2026.logging_utils import log
from worldcup2026.metrics import avg_or_none, brier_decomposition, summarize_temporal_windows
from worldcup2026.live.adjustment import (
    apply_live_pattern_adjustment as calculate_apply_live_pattern_adjustment,
    live_game_state_adjustment as calculate_live_game_state_adjustment,
    live_stats_adjustment as calculate_live_stats_adjustment,
)
from worldcup2026.live.patterns import (
    derive_team_live_pattern as calculate_derive_team_live_pattern,
    detect_live_play_patterns as calculate_detect_live_play_patterns,
    format_pattern_signal as calculate_format_pattern_signal,
    stat_share as calculate_stat_share,
)
from worldcup2026.live.tactical import (
    live_signature_metrics as calculate_live_signature_metrics,
    tactical_signature_from_metrics as calculate_tactical_signature_from_metrics,
    update_tactical_signature_state as calculate_update_tactical_signature_state,
)
from worldcup2026.models.penalties import (
    penalties_probability as calculate_penalties_probability,
    penalty_conversion_probability as calculate_penalty_conversion_probability,
    simulate_penalty_shootout as run_penalty_shootout,
)
from worldcup2026.models.elo import (
    effective_elo as calculate_effective_elo,
    elo_delta_for_match as calculate_elo_delta_for_match,
)
from worldcup2026.models.expected_goals import (
    attack_metric as calculate_attack_metric,
    context_components as calculate_context_components,
    defense_metric as calculate_defense_metric,
    expected_goals as calculate_expected_goals,
    factor_breakdown as calculate_factor_breakdown,
)
from worldcup2026.modeling import (
    dynamic_correlation,
)
from worldcup2026.parallel import (
    default_parallel_workers,
    empty_bracket_aggregate,
    empty_tournament_summary,
    merge_bracket_aggregate,
    merge_tournament_summary,
    run_parallel_batches,
)
from worldcup2026.simulation.rng import fast_random, poisson_sample_fast, seed_fast_rng
from worldcup2026.simulation.match import (
    build_simulation_context as calculate_build_simulation_context,
    penalty_shootout_summary as calculate_penalty_shootout_summary,
    sample_cards as calculate_sample_cards,
    sample_knockout_resolution as calculate_sample_knockout_resolution,
    simulate_match_sample as calculate_simulate_match_sample,
    update_simulation_state as calculate_update_simulation_state,
)
from worldcup2026.simulation.tournament import (
    assign_third_place_slots as calculate_assign_third_place_slots,
    bracket_match_order as calculate_bracket_match_order,
    project_bracket_batch as calculate_project_bracket_batch,
    resolve_r32_team as calculate_resolve_r32_team,
    run_knockout_round as calculate_run_knockout_round,
    simulate_group_stage as calculate_simulate_group_stage,
    simulate_tournament_batch as calculate_simulate_tournament_batch,
    simulate_tournament_iteration as calculate_simulate_tournament_iteration,
    sort_standings as calculate_sort_standings,
    standings_entry as calculate_standings_entry,
)
from worldcup2026.simulation.playoffs import (
    qualification_probabilities as calculate_qualification_probabilities,
    resolved_fifa_path_winners as calculate_resolved_fifa_path_winners,
    resolved_uefa_path_winners as calculate_resolved_uefa_path_winners,
    sample_playoff_placeholders as calculate_sample_playoff_placeholders,
    sample_uefa_path_winner as calculate_sample_uefa_path_winner,
)
from worldcup2026.cli import (
    build_parser as package_build_parser,
    dispatch_command as package_dispatch_command,
)
from worldcup2026.profiles.indices import (
    chemistry_index as calculate_chemistry_index,
    coach_index as calculate_coach_index,
    discipline_proxy as calculate_discipline_proxy,
    heritage_index as calculate_heritage_index,
    morale_base as calculate_morale_base,
    resource_index as calculate_resource_index,
    tactical_flexibility as calculate_tactical_flexibility,
    tempo_proxy as calculate_tempo_proxy,
    trajectory_index as calculate_trajectory_index,
    travel_resilience as calculate_travel_resilience,
)
from worldcup2026.profiles.squad import aggregate_squad as calculate_aggregate_squad
from worldcup2026.profiles.team import profile_for as calculate_profile_for
from worldcup2026.types import BacktestMetrics, KnockoutResolution
from worldcup2026.utils.naming import (
    normalize_stage_name as package_normalize_stage_name,
    normalize_team_name as package_normalize_team_name,
    normalize_team_text as package_normalize_team_text,
    resolve_optional_team_name as package_resolve_optional_team_name,
    resolve_team_name as package_resolve_team_name,
    resolve_venue_country as package_resolve_venue_country,
    resolved_team_name_from_penalties as package_resolved_team_name_from_penalties,
)


DATA_FILE = Path(__file__).with_name("teams_2026.json")
HISTORICAL_FEATURES_FILE = Path(__file__).with_name("historical_features_1990.json")
TOURNAMENT_CONFIG_FILE = Path(__file__).with_name("tournament_2026_draw.json")
STATE_FILE = Path(__file__).with_name("tournament_state_2026.json")
FACTORIALS = [math.factorial(i) for i in range(16)]
HOST_COUNTRIES = {"Canada", "Mexico", "United States"}
BRACKET_FILE = Path(__file__).with_name("llave_actual_2026.md")
BRACKET_JSON_FILE = Path(__file__).with_name("llave_actual_2026.json")
DASHBOARD_HTML_FILE = Path(__file__).with_name("dashboard_actual_2026.html")
DASHBOARD_MD_FILE = Path(__file__).with_name("reporte_actual_2026.md")


@dataclass(frozen=True)
class Player:
    name: str
    position: str
    quality: float
    caps: float
    minutes_share: float
    attack: float
    creation: float
    defense: float
    goalkeeping: float
    aerial: float
    discipline: float
    yellow_rate: float
    red_rate: float
    availability: float


@dataclass(frozen=True)
class Team:
    name: str
    confederation: str
    status: str
    elo: float
    fifa_points: Optional[float] = None
    fifa_rank: Optional[int] = None
    host_country: Optional[str] = None
    resource_bias: float = 0.0
    heritage_bias: float = 0.0
    coach_bias: float = 0.0
    discipline_bias: float = 0.0
    chemistry_bias: float = 0.0
    attack_bias: float = 0.0
    defense_bias: float = 0.0
    players: Tuple[Player, ...] = ()

    @property
    def is_host(self) -> bool:
        return self.host_country is not None


@dataclass(frozen=True)
class SquadAggregate:
    squad_quality: float
    attack_unit: float
    midfield_unit: float
    defense_unit: float
    goalkeeper_unit: float
    bench_depth: float
    player_experience: float
    set_piece_attack: float
    set_piece_defense: float
    discipline_index: float
    yellow_rate: float
    red_rate: float
    availability: float
    finishing: float
    shot_creation: float
    pressing: float


@dataclass(frozen=True)
class HistoricalSnapshot:
    source_names: Tuple[str, ...]
    matches_since_1990: int
    weighted_matches_since_1990: float
    points_per_match: float
    weighted_points_per_match: float
    goals_for_per_match: float
    goals_against_per_match: float
    goal_diff_per_match: float
    weighted_goals_for_per_match: float
    weighted_goals_against_per_match: float
    weighted_goal_diff_per_match: float
    scoring_rate: float
    clean_sheet_rate: float
    competitive_matches_since_1990: int
    competitive_points_per_match: float
    competitive_goal_diff_per_match: float
    world_cup_matches_since_1990: int
    world_cup_points_per_match: float
    world_cup_goal_diff_per_match: float
    shootout_matches_since_1990: int
    shootout_win_rate: float
    strength_index: float
    attack_index: float
    defense_index: float
    competitive_index: float
    world_cup_index: float
    shootout_index: float


@dataclass(frozen=True)
class TeamProfile:
    fifa_points: float
    fifa_rank: int
    fifa_strength_index: float
    resource_index: float
    heritage_index: float
    world_cup_titles: int
    trajectory_index: float
    coach_index: float
    chemistry_index: float
    morale_base: float
    tactical_flexibility: float
    travel_resilience: float
    tempo: float
    squad: SquadAggregate
    history: HistoricalSnapshot


@dataclass(frozen=True)
class MatchContext:
    neutral: bool = True
    home_team: Optional[str] = None
    venue_country: Optional[str] = None
    rest_days_a: int = 4
    rest_days_b: int = 4
    injuries_a: float = 0.0
    injuries_b: float = 0.0
    altitude_m: int = 0
    travel_km_a: float = 0.0
    travel_km_b: float = 0.0
    knockout: bool = False
    morale_a: float = 0.0
    morale_b: float = 0.0
    yellow_cards_a: int = 0
    yellow_cards_b: int = 0
    red_suspensions_a: int = 0
    red_suspensions_b: int = 0
    group: Optional[str] = None
    group_points_a: int = 0
    group_points_b: int = 0
    group_goal_diff_a: int = 0
    group_goal_diff_b: int = 0
    group_matches_played_a: int = 0
    group_matches_played_b: int = 0
    weather_stress: float = 0.0
    market_prob_a: Optional[float] = None
    market_prob_draw: Optional[float] = None
    market_prob_b: Optional[float] = None
    market_total_line: Optional[float] = None
    lineup_confirmed_a: bool = False
    lineup_confirmed_b: bool = False
    lineup_change_count_a: int = 0
    lineup_change_count_b: int = 0
    importance: float = 1.0


@dataclass(frozen=True)
class MatchPrediction:
    team_a: str
    team_b: str
    expected_goals_a: float
    expected_goals_b: float
    win_a: float
    draw: float
    win_b: float
    exact_scores: List[Tuple[str, float]]
    advance_a: Optional[float] = None
    advance_b: Optional[float] = None
    knockout_detail: Optional[Dict[str, float]] = None
    penalty_shootout: Optional[dict] = None
    factors: Optional[Dict[str, float]] = None
    expected_remaining_goals_a: Optional[float] = None
    expected_remaining_goals_b: Optional[float] = None
    current_score_a: Optional[int] = None
    current_score_b: Optional[int] = None
    elapsed_minutes: Optional[float] = None
    live_phase: Optional[str] = None
    statistical_depth: Optional[Dict[str, object]] = None
    live_patterns: Optional[Dict[str, object]] = None
    model_stack: Optional[Dict[str, object]] = None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def logistic(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def stable_seed(value: str) -> int:
    total = 0
    for index, char in enumerate(value):
        total += (index + 1) * ord(char)
    return total


def seed_all_rng(seed: Optional[int]) -> None:
    random.seed(seed)
    seed_fast_rng(seed)


def parse_elapsed_minutes(status_detail: Optional[str], knockout: bool) -> Tuple[Optional[float], str]:
    if not status_detail:
        return None, "regulation"
    text = str(status_detail).strip().lower()
    if not text:
        return None, "regulation"
    if "pen" in text or "shootout" in text:
        return 120.0 if knockout else 90.0, "penalties"
    if text in {"ht", "half time", "halftime"}:
        return 45.0, "regulation"
    if "extra" in text and "half" in text:
        return 105.0, "extra_time"

    match = re.search(r"(\d+)(?:\+(\d+))?", text)
    if match:
        elapsed = float(match.group(1))
        if match.group(2):
            elapsed += float(match.group(2))
        if knockout and elapsed > 90.0:
            return clamp(elapsed, 90.0, 120.0), "extra_time"
        return clamp(elapsed, 0.0, 90.0), "regulation"

    if knockout and ("extra time" in text or text.startswith("et")):
        return 105.0, "extra_time"
    return None, "regulation"


def live_game_state_adjustment(
    base_mu_a: float,
    base_mu_b: float,
    score_a: int,
    score_b: int,
    progress: float,
    phase: str,
) -> Tuple[float, float]:
    return calculate_live_game_state_adjustment(
        base_mu_a,
        base_mu_b,
        score_a,
        score_b,
        progress,
        phase,
        clamp=clamp,
    )


def live_stats_adjustment(
    base_total_mu: float,
    mu_a: float,
    mu_b: float,
    progress: float,
    phase: str,
    live_stats: Optional[Dict[str, float]] = None,
) -> Tuple[float, float]:
    return calculate_live_stats_adjustment(
        base_total_mu,
        mu_a,
        mu_b,
        progress,
        phase,
        live_stats,
        clamp=clamp,
    )


def stat_share(value: float, other: float, neutral: float = 0.5) -> float:
    return calculate_stat_share(value, other, neutral)


def format_pattern_signal(label: str, value: float, integer: bool = False, suffix: str = "") -> str:
    return calculate_format_pattern_signal(label, value, integer, suffix)


def derive_team_live_pattern(
    side: str,
    live_stats: Dict[str, float],
    progress: float,
    score_for: int,
    score_against: int,
) -> Dict[str, object]:
    return calculate_derive_team_live_pattern(
        side,
        live_stats,
        progress,
        score_for,
        score_against,
        clamp=clamp,
    )


def detect_live_play_patterns(
    live_stats: Optional[Dict[str, float]],
    progress: float,
    phase: str,
    score_a: int,
    score_b: int,
) -> Optional[Dict[str, object]]:
    return calculate_detect_live_play_patterns(
        live_stats,
        progress,
        phase,
        score_a,
        score_b,
        clamp=clamp,
    )


def apply_live_pattern_adjustment(
    mu_a: float,
    mu_b: float,
    patterns: Optional[Dict[str, object]],
    phase: str,
) -> Tuple[float, float]:
    return calculate_apply_live_pattern_adjustment(mu_a, mu_b, patterns, phase, clamp=clamp)


def combine_current_score_distribution(
    current_score_a: int,
    current_score_b: int,
    remainder_dist: Dict[Tuple[int, int], float],
) -> Dict[Tuple[int, int], float]:
    final_dist: Dict[Tuple[int, int], float] = {}
    for (goals_a, goals_b), prob in remainder_dist.items():
        final_score = (current_score_a + goals_a, current_score_b + goals_b)
        final_dist[final_score] = final_dist.get(final_score, 0.0) + prob
    return final_dist


def compute_statistical_depth(
    final_dist: Dict[Tuple[int, int], float],
    win_a: float,
    draw: float,
    win_b: float,
    ctx: Optional[MatchContext] = None,
    model_stack: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    result_probs = [max(win_a, 1e-12), max(draw, 1e-12), max(win_b, 1e-12)]
    entropy = -sum(prob * math.log(prob) for prob in result_probs) / math.log(3.0)
    both_score = sum(prob for (goals_a, goals_b), prob in final_dist.items() if goals_a > 0 and goals_b > 0)
    clean_sheet_a = sum(prob for (_, goals_b), prob in final_dist.items() if goals_b == 0)
    clean_sheet_b = sum(prob for (goals_a, _), prob in final_dist.items() if goals_a == 0)
    over_2_5 = sum(prob for (goals_a, goals_b), prob in final_dist.items() if goals_a + goals_b >= 3)
    under_2_5 = 1.0 - over_2_5
    over_3_5 = sum(prob for (goals_a, goals_b), prob in final_dist.items() if goals_a + goals_b >= 4)
    under_3_5 = 1.0 - over_3_5
    top_scores = sorted(final_dist.items(), key=lambda item: item[1], reverse=True)
    top3_coverage = sum(prob for _, prob in top_scores[:3])
    sorted_results = sorted(result_probs, reverse=True)
    top_outcome_prob = sorted_results[0]
    second_outcome_prob = sorted_results[1]
    model_agreement = float((model_stack or {}).get("agreement", 0.0)) if model_stack else None
    confidence = clamp(
        PARAMS.confidence_base
        + PARAMS.confidence_top_outcome_weight * top_outcome_prob
        + PARAMS.confidence_gap_weight * (top_outcome_prob - second_outcome_prob)
        + PARAMS.confidence_top3_weight * top3_coverage
        + PARAMS.confidence_entropy_weight * (1.0 - entropy),
        PARAMS.confidence_floor,
        PARAMS.confidence_cap,
    )
    if model_agreement is not None:
        confidence = clamp(
            confidence + PARAMS.confidence_agreement_weight * (model_agreement - 0.5),
            PARAMS.confidence_floor,
            PARAMS.confidence_cap,
        )
    margin_dist: Dict[int, float] = {}
    for (goals_a, goals_b), prob in final_dist.items():
        margin = goals_a - goals_b
        margin_dist[margin] = margin_dist.get(margin, 0.0) + prob
    modal_margin, modal_margin_prob = max(margin_dist.items(), key=lambda item: item[1])

    market_gap = None
    if ctx and ctx.market_prob_a is not None and ctx.market_prob_draw is not None and ctx.market_prob_b is not None:
        market_gap = (
            abs(win_a - float(ctx.market_prob_a))
            + abs(draw - float(ctx.market_prob_draw))
            + abs(win_b - float(ctx.market_prob_b))
        ) / 3.0

    return {
        "confidence_index": confidence,
        "entropy_index": entropy,
        "top_outcome_prob": top_outcome_prob,
        "second_outcome_prob": second_outcome_prob,
        "both_teams_score": both_score,
        "clean_sheet_a": clean_sheet_a,
        "clean_sheet_b": clean_sheet_b,
        "over_2_5": over_2_5,
        "under_2_5": under_2_5,
        "over_3_5": over_3_5,
        "under_3_5": under_3_5,
        "top3_coverage": top3_coverage,
        "modal_margin": modal_margin,
        "modal_margin_prob": modal_margin_prob,
        "market_gap": market_gap,
        "model_agreement": model_agreement,
        "model_stack_names": (
            [
                str((model_stack or {}).get("primary_name", "")),
                str((model_stack or {}).get("contrast_name", "")),
                str((model_stack or {}).get("low_score_name", "")),
                str((model_stack or {}).get("final_name", "")),
            ]
            if model_stack
            else []
        ),
        "model_stack_weights": dict((model_stack or {}).get("weights", {})) if model_stack else {},
        "market_shrink": float((model_stack or {}).get("market_shrink", 0.0)) if model_stack else 0.0,
    }


def top_factor_drivers(factors: Optional[Dict[str, float]], limit: int = 3) -> List[Tuple[str, float]]:
    if not factors:
        return []
    labels = {
        "elo_diff": "Elo dinámico",
        "fifa_strength_diff": "Ranking FIFA / puntos FIFA",
        "resource_diff": "Recursos/PIB proxy",
        "heritage_diff": "Historia mundialista",
        "historical_strength_diff": "Historia competitiva desde 1990",
        "historical_attack_diff": "Ataque historico desde 1990",
        "historical_defense_diff": "Defensa historica desde 1990",
        "competitive_history_diff": "Rendimiento competitivo desde 1990",
        "world_cup_history_diff": "Rendimiento en Mundiales desde 1990",
        "coach_diff": "Entrenador",
        "trajectory_diff": "Trayectoria futbolística",
        "attack_unit_diff": "Ataque",
        "midfield_diff": "Mediocampo",
        "defense_diff": "Defensa",
        "goalkeeper_diff": "Portero",
        "bench_depth_diff": "Profundidad de banco",
        "discipline_diff": "Disciplina estructural",
        "experience_diff": "Experiencia de plantilla",
        "morale_diff": "Moral",
        "home_diff": "Localía/sede",
        "travel_diff": "Viaje",
        "injury_diff": "Bajas/lesiones",
        "cards_diff": "Tarjetas y suspensiones",
        "group_pressure_diff": "Presión de grupo",
        "lineup_diff": "Alineaciones",
        "market_prob_diff": "Mercado victoria/empate/derrota",
        "recent_form_diff": "Forma reciente",
        "attack_form_diff": "Forma ofensiva",
        "defense_form_diff": "Forma defensiva",
        "tactical_attack_diff": "Firma táctica ofensiva",
        "tactical_defense_diff": "Firma táctica defensiva",
        "tactical_tempo_diff": "Ritmo táctico reciente",
        "fatigue_diff": "Fatiga",
        "availability_diff": "Disponibilidad",
        "discipline_trend_diff": "Tendencia disciplinaria",
        "rivalry": "Rivalidad",
    }
    ranked = sorted(
        ((labels.get(key, key), value) for key, value in factors.items() if key not in {"market_draw_prob", "market_total_line", "importance"}),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    return ranked[:limit]


def normalize_team_text(value: str) -> str:
    return package_normalize_team_text(value)


def normalize_team_name(value: str) -> str:
    return package_normalize_team_name(value, aliases=TEAM_NAME_ALIASES)


def normalize_stage_name(raw_stage: Optional[str]) -> Optional[str]:
    return package_normalize_stage_name(
        raw_stage,
        stage_importance=STAGE_IMPORTANCE,
        stage_aliases=STAGE_ALIASES,
    )


def resolve_team_name(raw_name: str, teams: Dict[str, Team]) -> str:
    return package_resolve_team_name(raw_name, teams, aliases=TEAM_NAME_ALIASES)


def resolve_optional_team_name(raw_name: Optional[str], teams: Dict[str, Team]) -> Optional[str]:
    return package_resolve_optional_team_name(raw_name, teams, aliases=TEAM_NAME_ALIASES)


def resolve_venue_country(raw_name: Optional[str], teams: Dict[str, Team]) -> Optional[str]:
    return package_resolve_venue_country(raw_name, teams, aliases=TEAM_NAME_ALIASES)


def resolve_fixture_names(fixture: dict, teams: Dict[str, Team]) -> dict:
    resolved = dict(fixture)
    resolved["team_a"] = resolve_team_name(fixture["team_a"], teams)
    resolved["team_b"] = resolve_team_name(fixture["team_b"], teams)
    if fixture.get("home_team") is not None:
        resolved["home_team"] = resolve_team_name(fixture["home_team"], teams)
    if fixture.get("venue_country") is not None:
        resolved["venue_country"] = resolve_venue_country(fixture["venue_country"], teams)
    return resolved


def poisson_sample(lmbda: float) -> int:
    return poisson_sample_fast(lmbda)


def load_players(raw_players: Sequence[dict]) -> Tuple[Player, ...]:
    return calculate_load_players(raw_players, PlayerCls=Player)


@lru_cache(maxsize=1)
def load_teams() -> Dict[str, Team]:
    return calculate_load_teams(
        str(DATA_FILE),
        TeamCls=Team,
        load_players_fn=load_players,
    )


def centered(value: float) -> float:
    return value - 0.5


@lru_cache(maxsize=None)
def estimated_fifa_points(team: Team) -> float:
    return calculate_estimated_fifa_points(
        team,
        heritage_index=heritage_index,
        resource_index=resource_index,
        trajectory_index=trajectory_index,
        coach_index=coach_index,
        centered=centered,
        clamp=clamp,
    )


@lru_cache(maxsize=1)
def fifa_reference_table() -> Dict[str, Tuple[float, int, bool]]:
    return calculate_fifa_reference_table(
        load_teams_fn=load_teams,
        estimated_fifa_points_fn=estimated_fifa_points,
    )


@lru_cache(maxsize=None)
def fifa_points_value(team: Team) -> float:
    return calculate_fifa_points_value(team, reference_table_fn=fifa_reference_table)


@lru_cache(maxsize=None)
def fifa_rank_value(team: Team) -> int:
    return calculate_fifa_rank_value(team, reference_table_fn=fifa_reference_table)


@lru_cache(maxsize=None)
def fifa_points_are_proxy(team: Team) -> bool:
    return calculate_fifa_points_are_proxy(team, reference_table_fn=fifa_reference_table)


@lru_cache(maxsize=1)
def fifa_points_bounds() -> Tuple[float, float]:
    return calculate_fifa_points_bounds(reference_table_fn=fifa_reference_table)


@lru_cache(maxsize=None)
def fifa_strength_index(team: Team) -> float:
    return calculate_fifa_strength_index(
        team,
        points_bounds_fn=fifa_points_bounds,
        points_value_fn=fifa_points_value,
        clamp=clamp,
    )


@lru_cache(maxsize=1)
def historical_features_payload() -> dict:
    return calculate_historical_features_payload(str(HISTORICAL_FEATURES_FILE))


def proxy_historical_snapshot(team: Team) -> HistoricalSnapshot:
    return calculate_proxy_historical_snapshot(
        team,
        HistoricalSnapshotCls=HistoricalSnapshot,
        clamp=clamp,
        world_cup_titles=WORLD_CUP_TITLES,
        coach_overrides=COACH_OVERRIDES,
    )


@lru_cache(maxsize=None)
def historical_snapshot(team: Team) -> HistoricalSnapshot:
    return calculate_historical_snapshot(
        team,
        payload_fn=historical_features_payload,
        proxy_snapshot_fn=proxy_historical_snapshot,
        HistoricalSnapshotCls=HistoricalSnapshot,
        empirical_bayes_shrinkage=empirical_bayes_shrinkage,
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def resource_index(team: Team) -> float:
    return calculate_resource_index(team, clamp=clamp)


@lru_cache(maxsize=None)
def heritage_index(team: Team) -> float:
    return calculate_heritage_index(
        team,
        historical_snapshot=historical_snapshot,
        clamp=clamp,
        centered=centered,
    )


@lru_cache(maxsize=None)
def trajectory_index(team: Team) -> float:
    return calculate_trajectory_index(
        team,
        historical_snapshot=historical_snapshot,
        heritage_index_value=heritage_index(team),
        resource_index_value=resource_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def coach_index(team: Team) -> float:
    return calculate_coach_index(
        team,
        historical_snapshot=historical_snapshot,
        heritage_index_value=heritage_index(team),
        resource_index_value=resource_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def chemistry_index(team: Team) -> float:
    return calculate_chemistry_index(
        team,
        coach_index_value=coach_index(team),
        heritage_index_value=heritage_index(team),
        resource_index_value=resource_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def discipline_proxy(team: Team) -> float:
    return calculate_discipline_proxy(team, clamp=clamp)


@lru_cache(maxsize=None)
def tactical_flexibility(team: Team) -> float:
    return calculate_tactical_flexibility(
        coach_index_value=coach_index(team),
        resource_index_value=resource_index(team),
        heritage_index_value=heritage_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def morale_base(team: Team) -> float:
    return calculate_morale_base(
        chemistry_index_value=chemistry_index(team),
        heritage_index_value=heritage_index(team),
        coach_index_value=coach_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def travel_resilience(team: Team) -> float:
    return calculate_travel_resilience(
        team,
        resource_index_value=resource_index(team),
        chemistry_index_value=chemistry_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def tempo_proxy(team: Team) -> float:
    return calculate_tempo_proxy(
        team,
        trajectory_index_value=trajectory_index(team),
        coach_index_value=coach_index(team),
        clamp=clamp,
        centered=centered,
    )


def position_template() -> List[str]:
    return ["GK"] * 3 + ["DF"] * 8 + ["MF"] * 7 + ["FW"] * 5


def player_stat_quality(base: float, jitter: float, rng: random.Random) -> float:
    return clamp(base + rng.uniform(-jitter, jitter), 0.08, 0.98)


@lru_cache(maxsize=None)
def proxy_players(team: Team) -> Tuple[Player, ...]:
    if team.players:
        return team.players

    rng = random.Random(stable_seed(team.name))
    strength = clamp(0.50 + (team.elo - 1650.0) / 620.0, 0.12, 0.92)
    resource = resource_index(team)
    heritage = heritage_index(team)
    coach = coach_index(team)
    chemistry = chemistry_index(team)
    discipline = discipline_proxy(team)
    trajectory = trajectory_index(team)

    players = []
    for index, position in enumerate(position_template(), start=1):
        base_quality = 0.26 + 0.42 * strength + 0.12 * resource + 0.08 * heritage + 0.05 * chemistry
        quality = player_stat_quality(base_quality, 0.12, rng)
        caps = clamp(
            10.0 + 70.0 * (0.32 + 0.35 * heritage + 0.18 * chemistry + 0.10 * resource + rng.uniform(-0.15, 0.15)),
            1.0,
            160.0,
        )
        minutes_share = clamp(0.54 + 0.20 * chemistry + rng.uniform(-0.12, 0.12), 0.16, 1.00)
        availability = clamp(0.78 + 0.10 * resource + 0.06 * coach + rng.uniform(-0.10, 0.06), 0.55, 0.99)
        discipline_player = clamp(discipline + rng.uniform(-0.12, 0.12), 0.08, 0.98)

        if position == "GK":
            attack = player_stat_quality(0.10 + 0.15 * quality, 0.03, rng)
            creation = player_stat_quality(0.08 + 0.10 * quality, 0.03, rng)
            defense = player_stat_quality(0.34 + 0.25 * quality + 0.10 * coach, 0.06, rng)
            goalkeeping = player_stat_quality(0.46 + 0.30 * quality + 0.12 * coach + 0.06 * heritage, 0.08, rng)
            aerial = player_stat_quality(0.42 + 0.28 * quality, 0.07, rng)
        elif position == "DF":
            attack = player_stat_quality(0.14 + 0.18 * quality + 0.05 * resource, 0.05, rng)
            creation = player_stat_quality(0.18 + 0.20 * quality + 0.04 * coach, 0.06, rng)
            defense = player_stat_quality(0.32 + 0.34 * quality + 0.05 * heritage, 0.08, rng)
            goalkeeping = 0.0
            aerial = player_stat_quality(0.28 + 0.32 * quality + 0.06 * heritage, 0.06, rng)
        elif position == "MF":
            attack = player_stat_quality(0.22 + 0.28 * quality + 0.05 * trajectory, 0.07, rng)
            creation = player_stat_quality(0.24 + 0.34 * quality + 0.06 * coach, 0.08, rng)
            defense = player_stat_quality(0.20 + 0.22 * quality + 0.05 * chemistry, 0.06, rng)
            goalkeeping = 0.0
            aerial = player_stat_quality(0.18 + 0.18 * quality, 0.05, rng)
        else:
            attack = player_stat_quality(0.30 + 0.38 * quality + 0.06 * resource + 0.04 * coach, 0.09, rng)
            creation = player_stat_quality(0.18 + 0.24 * quality + 0.04 * chemistry, 0.08, rng)
            defense = player_stat_quality(0.10 + 0.10 * quality + 0.02 * chemistry, 0.04, rng)
            goalkeeping = 0.0
            aerial = player_stat_quality(0.20 + 0.24 * quality + 0.04 * heritage, 0.06, rng)

        yellow_rate = clamp(
            0.26 - 0.16 * discipline_player + (0.03 if position in {"DF", "MF"} else 0.0) + rng.uniform(-0.03, 0.03),
            0.03,
            0.42,
        )
        red_rate = clamp(
            0.025 - 0.014 * discipline_player + (0.008 if position == "DF" else 0.0) + rng.uniform(-0.004, 0.004),
            0.001,
            0.05,
        )

        players.append(
            Player(
                name=f"{team.name}_{position}_{index}",
                position=position,
                quality=quality,
                caps=caps,
                minutes_share=minutes_share,
                attack=attack,
                creation=creation,
                defense=defense,
                goalkeeping=goalkeeping,
                aerial=aerial,
                discipline=discipline_player,
                yellow_rate=yellow_rate,
                red_rate=red_rate,
                availability=availability,
            )
        )
    return tuple(players)


def sort_by(players: Sequence[Player], key_name: str) -> List[Player]:
    return sorted(players, key=lambda player: getattr(player, key_name), reverse=True)


@lru_cache(maxsize=None)
def aggregate_squad(team: Team) -> SquadAggregate:
    return calculate_aggregate_squad(
        team,
        proxy_players_fn=proxy_players,
        clamp=clamp,
        SquadAggregateCls=SquadAggregate,
    )


@lru_cache(maxsize=None)
def profile_for(team: Team) -> TeamProfile:
    return calculate_profile_for(
        team,
        TeamProfileCls=TeamProfile,
        fifa_points_value_fn=fifa_points_value,
        fifa_rank_value_fn=fifa_rank_value,
        fifa_strength_index_fn=fifa_strength_index,
        resource_index_fn=resource_index,
        heritage_index_fn=heritage_index,
        world_cup_titles=WORLD_CUP_TITLES,
        trajectory_index_fn=trajectory_index,
        coach_index_fn=coach_index,
        chemistry_index_fn=chemistry_index,
        morale_base_fn=morale_base,
        tactical_flexibility_fn=tactical_flexibility,
        travel_resilience_fn=travel_resilience,
        tempo_proxy_fn=tempo_proxy,
        aggregate_squad_fn=aggregate_squad,
        historical_snapshot_fn=historical_snapshot,
    )


def rivalry_intensity(team_a: Team, team_b: Team) -> float:
    if frozenset({team_a.name, team_b.name}) in RIVALRIES:
        return RIVALRIES[frozenset({team_a.name, team_b.name})]
    if team_a.confederation == team_b.confederation:
        return 0.03
    return 0.0


def group_pressure(points: int, matches_played: int, goal_diff: int) -> float:
    if matches_played <= 0:
        return 0.0
    expected_points = 1.4 * matches_played
    gap = expected_points - points
    pressure = 0.08 * gap - 0.02 * clamp(goal_diff, -3, 3)
    return clamp(pressure, -0.18, 0.20)


def current_morale(profile: TeamProfile, explicit_morale: float) -> float:
    base = -0.02 + 0.28 * centered(profile.morale_base)
    base += 0.18 * clamp(explicit_morale, -1.0, 1.0)
    return clamp(base, -0.25, 0.25)


def market_probability(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return clamp(float(value), 0.01, 0.98)


def discipline_absence_penalty(profile: TeamProfile, yellow_cards: int, red_suspensions: int) -> float:
    penalty = 0.06 * clamp(yellow_cards, 0, 6) * (0.55 - centered(profile.squad.discipline_index))
    penalty += 0.18 * clamp(red_suspensions, 0, 4)
    return clamp(penalty, 0.0, 0.55)


def state_float(state: Optional[dict], key: str, default: float) -> float:
    if not state:
        return default
    return float(state.get(key, default))


def state_int(state: Optional[dict], key: str, default: int) -> int:
    if not state:
        return default
    return int(state.get(key, default))


def effective_elo(team: Team, state: Optional[dict] = None) -> float:
    return calculate_effective_elo(team, state=state, clamp=clamp, state_float=state_float)


def recent_form_signal(state: Optional[dict]) -> float:
    return clamp(state_float(state, "recent_form", 0.0), -1.0, 1.0)


def attack_form_signal(state: Optional[dict]) -> float:
    return clamp(state_float(state, "attack_form", 0.0), -1.0, 1.0)


def defense_form_signal(state: Optional[dict]) -> float:
    return clamp(state_float(state, "defense_form", 0.0), -1.0, 1.0)


def fatigue_level(state: Optional[dict]) -> float:
    return clamp(state_float(state, "fatigue", 0.0), 0.0, 1.0)


def availability_level(state: Optional[dict]) -> float:
    return clamp(state_float(state, "availability", 1.0), 0.40, 1.0)


def discipline_trend(state: Optional[dict]) -> float:
    return clamp(state_float(state, "discipline_drift", 0.0), -1.0, 0.5)


def predictive_yellow_cards(state: Optional[dict]) -> int:
    yellow_load = state_float(state, "yellow_load", 0.0)
    accumulated = state_int(state, "yellow_cards", 0)
    return int(round(clamp(max(yellow_load, 0.35 * accumulated), 0.0, 6.0)))


def dynamic_injury_load(team: Team, state: Optional[dict]) -> float:
    profile = profile_for(team)
    baseline = 0.08 * (1.0 - profile.squad.availability)
    fatigue_pressure = 0.24 * fatigue_level(state)
    availability_pressure = 0.34 * (1.0 - availability_level(state))
    return clamp(baseline + fatigue_pressure + availability_pressure, 0.0, 0.75)


def context_components(
    team: Team,
    profile: TeamProfile,
    opponent: Team,
    ctx: MatchContext,
    side: str,
    state: Optional[dict] = None,
) -> Dict[str, float]:
    return calculate_context_components(
        team,
        profile,
        opponent,
        ctx,
        side,
        state=state,
        current_morale=current_morale,
        discipline_absence_penalty=discipline_absence_penalty,
        group_pressure=group_pressure,
        rivalry_intensity=rivalry_intensity,
        fatigue_level=fatigue_level,
        availability_level=availability_level,
        recent_form_signal=recent_form_signal,
        clamp=clamp,
        host_countries=HOST_COUNTRIES,
    )


def attack_metric(team: Team, profile: TeamProfile, state: Optional[dict] = None) -> float:
    return calculate_attack_metric(
        team,
        profile,
        state=state,
        effective_elo=effective_elo,
        centered=centered,
        attack_form_signal=attack_form_signal,
        recent_form_signal=recent_form_signal,
        tactical_attack_signal=tactical_attack_signal,
        tactical_tempo_signal=tactical_tempo_signal,
        fatigue_level=fatigue_level,
        availability_level=availability_level,
    )


def defense_metric(team: Team, profile: TeamProfile, state: Optional[dict] = None) -> float:
    return calculate_defense_metric(
        team,
        profile,
        state=state,
        effective_elo=effective_elo,
        centered=centered,
        defense_form_signal=defense_form_signal,
        recent_form_signal=recent_form_signal,
        discipline_trend=discipline_trend,
        tactical_defense_signal=tactical_defense_signal,
        tactical_tempo_signal=tactical_tempo_signal,
        fatigue_level=fatigue_level,
        availability_level=availability_level,
    )


def expected_goals(
    team_a: Team,
    team_b: Team,
    ctx: MatchContext,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> Tuple[float, float]:
    return calculate_expected_goals(
        team_a,
        team_b,
        ctx,
        state_a=state_a,
        state_b=state_b,
        profile_for=profile_for,
        context_components_fn=context_components,
        attack_metric_fn=attack_metric,
        defense_metric_fn=defense_metric,
        effective_elo=effective_elo,
        logistic=logistic,
        centered=centered,
        rivalry_intensity=rivalry_intensity,
        attack_form_signal=attack_form_signal,
        defense_form_signal=defense_form_signal,
        recent_form_signal=recent_form_signal,
        tactical_attack_signal=tactical_attack_signal,
        tactical_defense_signal=tactical_defense_signal,
        tactical_tempo_signal=tactical_tempo_signal,
        fatigue_level=fatigue_level,
        availability_level=availability_level,
        group_pressure=group_pressure,
        clamp=clamp,
    )


def factor_breakdown(
    team_a: Team,
    team_b: Team,
    ctx: MatchContext,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> Dict[str, float]:
    return calculate_factor_breakdown(
        team_a,
        team_b,
        ctx,
        state_a=state_a,
        state_b=state_b,
        profile_for=profile_for,
        context_components_fn=context_components,
        effective_elo=effective_elo,
        attack_form_signal=attack_form_signal,
        defense_form_signal=defense_form_signal,
        fatigue_level=fatigue_level,
        availability_level=availability_level,
        discipline_trend=discipline_trend,
        tactical_attack_signal=tactical_attack_signal,
        tactical_defense_signal=tactical_defense_signal,
        tactical_tempo_signal=tactical_tempo_signal,
    )


def bivariate_poisson_prob(x: int, y: int, lambda1: float, lambda2: float, lambda3: float) -> float:
    limit = min(x, y)
    exp_term = math.exp(-(lambda1 + lambda2 + lambda3))
    total = 0.0
    for shared in range(limit + 1):
        total += (
            (lambda1 ** (x - shared) / FACTORIALS[x - shared])
            * (lambda2 ** (y - shared) / FACTORIALS[y - shared])
            * (lambda3 ** shared / FACTORIALS[shared])
        )
    return exp_term * total


def _sample_from_distribution(dist: Dict[Tuple[int, int], float]) -> Tuple[int, int]:
    roll = fast_random()
    cumulative = 0.0
    last_score = (0, 0)
    for score, prob in dist.items():
        cumulative += prob
        last_score = score
        if roll <= cumulative:
            return score
    return last_score


def correlated_sample_score(mu_a: float, mu_b: float, ctx: Optional[MatchContext] = None) -> Tuple[int, int]:
    lambda3 = dynamic_correlation(mu_a, mu_b, ctx)
    shared = poisson_sample(lambda3)
    goals_a = poisson_sample(max(mu_a - lambda3, 0.001)) + shared
    goals_b = poisson_sample(max(mu_b - lambda3, 0.001)) + shared
    return goals_a, goals_b


def independent_sample_score(mu_a: float, mu_b: float) -> Tuple[int, int]:
    return poisson_sample(max(mu_a, 0.001)), poisson_sample(max(mu_b, 0.001))


def sample_score(mu_a: float, mu_b: float, ctx: Optional[MatchContext] = None) -> Tuple[int, int]:
    weights = model_blend_weights(mu_a, mu_b, ctx)
    roll = fast_random()
    if roll < weights["primary"]:
        return correlated_sample_score(mu_a, mu_b, ctx)
    if roll < weights["primary"] + weights["contrast"]:
        return independent_sample_score(mu_a, mu_b)
    rho = low_score_rho(mu_a, mu_b, ctx)
    low_score_dist = cached_low_score_distribution(
        int(round(mu_a * 20.0)),
        int(round(mu_b * 20.0)),
        int(round(rho * 100.0)),
        7,
    )
    return _sample_from_distribution(low_score_dist)


def penalties_context_state(ctx_morale: float, state: Optional[dict]) -> dict:
    penalties_state = normalize_team_state(state)
    penalties_state["morale"] = clamp(ctx_morale, -1.0, 1.0)
    return penalties_state


def simulation_state_signature(state: Optional[dict]) -> Tuple[float, ...]:
    return package_coerce_team_state(state).simulation_signature()


def simulation_state_from_signature(signature: Tuple[float, ...]) -> dict:
    (
        elo_shift,
        recent_form,
        attack_form,
        defense_form,
        fatigue,
        availability,
        discipline_drift,
        style_attack_bias,
        style_defense_bias,
        style_tempo,
    ) = signature
    return {
        "elo_shift": float(elo_shift),
        "recent_form": float(recent_form),
        "attack_form": float(attack_form),
        "defense_form": float(defense_form),
        "fatigue": float(fatigue),
        "availability": float(availability),
        "discipline_drift": float(discipline_drift),
        "style_attack_bias": float(style_attack_bias),
        "style_defense_bias": float(style_defense_bias),
        "style_tempo": float(style_tempo),
    }


@lru_cache(maxsize=131072)
def cached_simulation_expected_goals(
    team_a_name: str,
    team_b_name: str,
    ctx: MatchContext,
    state_signature_a: Tuple[float, ...],
    state_signature_b: Tuple[float, ...],
) -> Tuple[float, float]:
    teams = load_teams()
    team_a = teams[team_a_name]
    team_b = teams[team_b_name]
    state_a = simulation_state_from_signature(state_signature_a)
    state_b = simulation_state_from_signature(state_signature_b)
    return expected_goals(team_a, team_b, ctx, state_a=state_a, state_b=state_b)


def extra_time_expected_goals(
    mu_a: float,
    mu_b: float,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> Tuple[float, float]:
    base_share = PARAMS.extra_time_share
    extra_fatigue_a = clamp(
        1.0
        - PARAMS.extra_time_fatigue_weight * fatigue_level(state_a)
        - PARAMS.extra_time_availability_weight * (1.0 - availability_level(state_a)),
        0.58,
        1.05,
    )
    extra_fatigue_b = clamp(
        1.0
        - PARAMS.extra_time_fatigue_weight * fatigue_level(state_b)
        - PARAMS.extra_time_availability_weight * (1.0 - availability_level(state_b)),
        0.58,
        1.05,
    )
    attacking_push_a = (
        1.0
        + PARAMS.extra_time_attack_form_weight * attack_form_signal(state_a)
        + PARAMS.extra_time_recent_form_weight * recent_form_signal(state_a)
    )
    attacking_push_b = (
        1.0
        + PARAMS.extra_time_attack_form_weight * attack_form_signal(state_b)
        + PARAMS.extra_time_recent_form_weight * recent_form_signal(state_b)
    )
    et_mu_a = clamp(mu_a * base_share * extra_fatigue_a * attacking_push_a, 0.03, 1.35)
    et_mu_b = clamp(mu_b * base_share * extra_fatigue_b * attacking_push_b, 0.03, 1.35)
    return et_mu_a, et_mu_b


def knockout_resolution_detail(
    team_a: Team,
    team_b: Team,
    ctx: MatchContext,
    mu_a: float,
    mu_b: float,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> Dict[str, float]:
    et_mu_a, et_mu_b = extra_time_expected_goals(mu_a, mu_b, state_a=state_a, state_b=state_b)
    et_dist, _ = build_model_stack(et_mu_a, et_mu_b, None, max_goals=5, market_strength=0.0)
    et_win_a = 0.0
    et_draw = 0.0
    et_win_b = 0.0
    for (goals_a, goals_b), prob in et_dist.items():
        if goals_a > goals_b:
            et_win_a += prob
        elif goals_a < goals_b:
            et_win_b += prob
        else:
            et_draw += prob

    penalties_a = penalties_probability(
        team_a,
        team_b,
        penalties_context_state(ctx.morale_a, state_a),
        penalties_context_state(ctx.morale_b, state_b),
    )
    penalties_b = 1.0 - penalties_a
    return {
        "et_xg_a": et_mu_a,
        "et_xg_b": et_mu_b,
        "et_win_a": et_win_a,
        "et_draw": et_draw,
        "et_win_b": et_win_b,
        "penalties_a": penalties_a,
        "penalties_b": penalties_b,
        "reach_penalties": et_draw,
        "advance_a_from_draw": et_win_a + et_draw * penalties_a,
        "advance_b_from_draw": et_win_b + et_draw * penalties_b,
    }


def sample_knockout_resolution(
    team_a: Team,
    team_b: Team,
    ctx: MatchContext,
    score_a: int,
    score_b: int,
    mu_a: float,
    mu_b: float,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> dict:
    return calculate_sample_knockout_resolution(
        team_a,
        team_b,
        ctx,
        score_a,
        score_b,
        mu_a,
        mu_b,
        state_a=state_a,
        state_b=state_b,
        asdict=asdict,
        KnockoutResolution=KnockoutResolution,
        extra_time_expected_goals=extra_time_expected_goals,
        sample_score=sample_score,
        simulate_penalty_shootout=simulate_penalty_shootout,
        penalties_context_state=penalties_context_state,
        fast_random=fast_random,
    )


def predict_match(
    teams: Dict[str, Team],
    team_a_name: str,
    team_b_name: str,
    ctx: Optional[MatchContext] = None,
    top_scores: int = 6,
    include_advancement: bool = False,
    show_factors: bool = False,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> MatchPrediction:
    ctx = ctx or MatchContext()
    team_a = teams[team_a_name]
    team_b = teams[team_b_name]
    mu_a, mu_b = expected_goals(team_a, team_b, ctx, state_a=state_a, state_b=state_b)
    dist, model_stack = build_model_stack(mu_a, mu_b, ctx, max_goals=10, market_strength=0.30)

    win_a = 0.0
    draw = 0.0
    win_b = 0.0
    exact = []
    for (goals_a, goals_b), prob in dist.items():
        exact.append((f"{goals_a}-{goals_b}", prob))
        if goals_a > goals_b:
            win_a += prob
        elif goals_a == goals_b:
            draw += prob
        else:
            win_b += prob

    exact.sort(key=lambda item: item[1], reverse=True)
    advance_a = None
    advance_b = None
    knockout_detail = None
    penalty_shootout = None
    if include_advancement:
        knockout_detail = knockout_resolution_detail(
            team_a,
            team_b,
            ctx,
            mu_a,
            mu_b,
            state_a=state_a,
            state_b=state_b,
        )
        advance_a = win_a + draw * knockout_detail["advance_a_from_draw"]
        advance_b = win_b + draw * knockout_detail["advance_b_from_draw"]
        penalty_shootout = penalty_shootout_summary(
            team_a,
            team_b,
            ctx,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
            iterations=1600,
        )
    factors = factor_breakdown(team_a, team_b, ctx, state_a=state_a, state_b=state_b) if show_factors else None

    return MatchPrediction(
        team_a=team_a_name,
        team_b=team_b_name,
        expected_goals_a=mu_a,
        expected_goals_b=mu_b,
        win_a=win_a,
        draw=draw,
        win_b=win_b,
        exact_scores=exact[:top_scores],
        advance_a=advance_a,
        advance_b=advance_b,
        knockout_detail=knockout_detail,
        penalty_shootout=penalty_shootout,
        factors=factors,
        statistical_depth=compute_statistical_depth(dist, win_a, draw, win_b, ctx, model_stack=model_stack),
        model_stack=model_stack,
    )


def predict_match_live(
    teams: Dict[str, Team],
    team_a_name: str,
    team_b_name: str,
    ctx: MatchContext,
    current_score_a: int,
    current_score_b: int,
    status_detail: Optional[str],
    top_scores: int = 6,
    include_advancement: bool = False,
    show_factors: bool = False,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
    live_stats: Optional[Dict[str, float]] = None,
) -> MatchPrediction:
    team_a = teams[team_a_name]
    team_b = teams[team_b_name]
    base_mu_a, base_mu_b = expected_goals(team_a, team_b, ctx, state_a=state_a, state_b=state_b)
    elapsed_minutes, phase = parse_elapsed_minutes(status_detail, ctx.knockout)
    patterns = None

    if phase == "penalties":
        patterns = detect_live_play_patterns(
            live_stats,
            1.0,
            phase,
            current_score_a,
            current_score_b,
        )
        penalties_a = penalties_probability(
            team_a,
            team_b,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
        )
        penalties_b = 1.0 - penalties_a
        shootout = penalty_shootout_summary(
            team_a,
            team_b,
            ctx,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
            iterations=1600,
        )
        factors = factor_breakdown(team_a, team_b, ctx, state_a=state_a, state_b=state_b) if show_factors else None
        final_dist = {(current_score_a, current_score_b): 1.0}
        return MatchPrediction(
            team_a=team_a_name,
            team_b=team_b_name,
            expected_goals_a=float(current_score_a),
            expected_goals_b=float(current_score_b),
            win_a=0.0,
            draw=1.0,
            win_b=0.0,
            exact_scores=[(f"{current_score_a}-{current_score_b}", 1.0)],
            advance_a=penalties_a if include_advancement else None,
            advance_b=penalties_b if include_advancement else None,
            knockout_detail={
                "et_xg_a": 0.0,
                "et_xg_b": 0.0,
                "et_win_a": 0.0,
                "et_draw": 1.0,
                "et_win_b": 0.0,
                "penalties_a": penalties_a,
                "penalties_b": penalties_b,
                "reach_penalties": 1.0,
                "advance_a_from_draw": penalties_a,
                "advance_b_from_draw": penalties_b,
            }
            if include_advancement
            else None,
            penalty_shootout=shootout if include_advancement else None,
            factors=factors,
            expected_remaining_goals_a=0.0,
            expected_remaining_goals_b=0.0,
            current_score_a=current_score_a,
            current_score_b=current_score_b,
            elapsed_minutes=elapsed_minutes,
            live_phase=phase,
            statistical_depth=compute_statistical_depth(final_dist, 0.0, 1.0, 0.0, ctx),
            live_patterns=patterns,
        )

    if phase == "extra_time":
        base_remaining_a, base_remaining_b = extra_time_expected_goals(base_mu_a, base_mu_b, state_a=state_a, state_b=state_b)
        remaining_fraction = 1.0 if elapsed_minutes is None else clamp((120.0 - elapsed_minutes) / 30.0, 0.0, 1.0)
        progress = 1.0 if elapsed_minutes is None else clamp((elapsed_minutes - 90.0) / 30.0, 0.0, 1.0)
        rem_mu_a, rem_mu_b = live_game_state_adjustment(
            base_remaining_a * remaining_fraction,
            base_remaining_b * remaining_fraction,
            current_score_a,
            current_score_b,
            progress,
            "extra_time",
        )
        rem_mu_a, rem_mu_b = live_stats_adjustment(
            base_mu_a + base_mu_b,
            rem_mu_a,
            rem_mu_b,
            progress,
            "extra_time",
            live_stats=live_stats,
        )
        patterns = detect_live_play_patterns(
            live_stats,
            progress,
            phase,
            current_score_a,
            current_score_b,
        )
        rem_mu_a, rem_mu_b = apply_live_pattern_adjustment(rem_mu_a, rem_mu_b, patterns, "extra_time")
        remainder_dist, model_stack = build_model_stack(rem_mu_a, rem_mu_b, None, max_goals=4, market_strength=0.0)
        final_dist = combine_current_score_distribution(current_score_a, current_score_b, remainder_dist)
        win_a = 0.0
        draw = 0.0
        win_b = 0.0
        exact = []
        for (goals_a, goals_b), prob in final_dist.items():
            exact.append((f"{goals_a}-{goals_b}", prob))
            if goals_a > goals_b:
                win_a += prob
            elif goals_b > goals_a:
                win_b += prob
            else:
                draw += prob
        exact.sort(key=lambda item: item[1], reverse=True)
        penalties_a = penalties_probability(
            team_a,
            team_b,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
        )
        penalties_b = 1.0 - penalties_a
        advance_a = win_a + draw * penalties_a if include_advancement else None
        advance_b = win_b + draw * penalties_b if include_advancement else None
        shootout = penalty_shootout_summary(
            team_a,
            team_b,
            ctx,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
            iterations=1600,
        ) if include_advancement else None
        factors = factor_breakdown(team_a, team_b, ctx, state_a=state_a, state_b=state_b) if show_factors else None
        return MatchPrediction(
            team_a=team_a_name,
            team_b=team_b_name,
            expected_goals_a=current_score_a + rem_mu_a,
            expected_goals_b=current_score_b + rem_mu_b,
            win_a=win_a,
            draw=draw,
            win_b=win_b,
            exact_scores=exact[:top_scores],
            advance_a=advance_a,
            advance_b=advance_b,
            knockout_detail={
                "et_xg_a": rem_mu_a,
                "et_xg_b": rem_mu_b,
                "et_win_a": win_a,
                "et_draw": draw,
                "et_win_b": win_b,
                "penalties_a": penalties_a,
                "penalties_b": penalties_b,
                "reach_penalties": draw,
                "advance_a_from_draw": penalties_a,
                "advance_b_from_draw": penalties_b,
            }
            if include_advancement
            else None,
            penalty_shootout=shootout,
            factors=factors,
            expected_remaining_goals_a=rem_mu_a,
            expected_remaining_goals_b=rem_mu_b,
            current_score_a=current_score_a,
            current_score_b=current_score_b,
            elapsed_minutes=elapsed_minutes,
            live_phase=phase,
            statistical_depth=compute_statistical_depth(final_dist, win_a, draw, win_b, ctx, model_stack=model_stack),
            live_patterns=patterns,
            model_stack=model_stack,
        )

    remaining_fraction = 1.0 if elapsed_minutes is None else clamp((90.0 - elapsed_minutes) / 90.0, 0.0, 1.0)
    progress = 0.0 if elapsed_minutes is None else clamp(elapsed_minutes / 90.0, 0.0, 1.0)
    rem_mu_a, rem_mu_b = live_game_state_adjustment(
        base_mu_a * remaining_fraction,
        base_mu_b * remaining_fraction,
        current_score_a,
        current_score_b,
        progress,
        "regulation",
    )
    rem_mu_a, rem_mu_b = live_stats_adjustment(
        base_mu_a + base_mu_b,
        rem_mu_a,
        rem_mu_b,
        progress,
        "regulation",
        live_stats=live_stats,
    )
    patterns = detect_live_play_patterns(
        live_stats,
        progress,
        phase,
        current_score_a,
        current_score_b,
    )
    rem_mu_a, rem_mu_b = apply_live_pattern_adjustment(rem_mu_a, rem_mu_b, patterns, "regulation")
    live_market_strength = 0.08 if progress > 0.0 else 0.20
    remainder_dist, model_stack = build_model_stack(rem_mu_a, rem_mu_b, ctx, max_goals=6, market_strength=live_market_strength)
    final_dist = combine_current_score_distribution(current_score_a, current_score_b, remainder_dist)

    win_a = 0.0
    draw = 0.0
    win_b = 0.0
    exact = []
    for (goals_a, goals_b), prob in final_dist.items():
        exact.append((f"{goals_a}-{goals_b}", prob))
        if goals_a > goals_b:
            win_a += prob
        elif goals_b > goals_a:
            win_b += prob
        else:
            draw += prob
    exact.sort(key=lambda item: item[1], reverse=True)

    advance_a = None
    advance_b = None
    knockout_detail = None
    penalty_shootout = None
    if include_advancement:
        knockout_detail = knockout_resolution_detail(
            team_a,
            team_b,
            ctx,
            base_mu_a,
            base_mu_b,
            state_a=state_a,
            state_b=state_b,
        )
        advance_a = win_a + draw * knockout_detail["advance_a_from_draw"]
        advance_b = win_b + draw * knockout_detail["advance_b_from_draw"]
        penalty_shootout = penalty_shootout_summary(
            team_a,
            team_b,
            ctx,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
            iterations=1600,
        )
    factors = factor_breakdown(team_a, team_b, ctx, state_a=state_a, state_b=state_b) if show_factors else None

    return MatchPrediction(
        team_a=team_a_name,
        team_b=team_b_name,
        expected_goals_a=current_score_a + rem_mu_a,
        expected_goals_b=current_score_b + rem_mu_b,
        win_a=win_a,
        draw=draw,
        win_b=win_b,
        exact_scores=exact[:top_scores],
        advance_a=advance_a,
        advance_b=advance_b,
        knockout_detail=knockout_detail,
        penalty_shootout=penalty_shootout,
        factors=factors,
        expected_remaining_goals_a=rem_mu_a,
        expected_remaining_goals_b=rem_mu_b,
        current_score_a=current_score_a,
        current_score_b=current_score_b,
        elapsed_minutes=elapsed_minutes,
        live_phase="regulation",
        statistical_depth=compute_statistical_depth(final_dist, win_a, draw, win_b, ctx, model_stack=model_stack),
        live_patterns=patterns,
        model_stack=model_stack,
    )


def monte_carlo_match_summary(
    teams: Dict[str, Team],
    team_a_name: str,
    team_b_name: str,
    ctx: MatchContext,
    iterations: int,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> dict:
    team_a = teams[team_a_name]
    team_b = teams[team_b_name]
    penalties_state_a = dict(state_a or {})
    penalties_state_b = dict(state_b or {})
    penalties_state_a["morale"] = ctx.morale_a
    penalties_state_b["morale"] = ctx.morale_b
    mu_a, mu_b = expected_goals(team_a, team_b, ctx, state_a=state_a, state_b=state_b)
    counts: Dict[Tuple[int, int], int] = {}
    win_a = 0
    draw = 0
    win_b = 0
    advance_a = 0
    advance_b = 0
    total_goals_a = 0
    total_goals_b = 0
    extra_time_count = 0
    penalties_count = 0

    for _ in range(iterations):
        goals_a, goals_b = sample_score(mu_a, mu_b, ctx)
        if goals_a > goals_b:
            counts[(goals_a, goals_b)] = counts.get((goals_a, goals_b), 0) + 1
            total_goals_a += goals_a
            total_goals_b += goals_b
            win_a += 1
            advance_a += 1
        elif goals_b > goals_a:
            counts[(goals_a, goals_b)] = counts.get((goals_a, goals_b), 0) + 1
            total_goals_a += goals_a
            total_goals_b += goals_b
            win_b += 1
            advance_b += 1
        else:
            draw += 1
            if ctx.knockout:
                resolution = sample_knockout_resolution(
                    team_a,
                    team_b,
                    ctx,
                    goals_a,
                    goals_b,
                    mu_a,
                    mu_b,
                    state_a=penalties_state_a,
                    state_b=penalties_state_b,
                )
                counts[(resolution["score_a"], resolution["score_b"])] = counts.get((resolution["score_a"], resolution["score_b"]), 0) + 1
                total_goals_a += resolution["score_a"]
                total_goals_b += resolution["score_b"]
                extra_time_count += 1 if resolution["went_extra_time"] else 0
                penalties_count += 1 if resolution["went_penalties"] else 0
                if resolution["winner"] == team_a_name:
                    advance_a += 1
                else:
                    advance_b += 1
            else:
                counts[(goals_a, goals_b)] = counts.get((goals_a, goals_b), 0) + 1
                total_goals_a += goals_a
                total_goals_b += goals_b

    top_scores = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:6]
    return {
        "iterations": iterations,
        "win_a": win_a / float(iterations),
        "draw": draw / float(iterations),
        "win_b": win_b / float(iterations),
        "advance_a": advance_a / float(iterations) if ctx.knockout else None,
        "advance_b": advance_b / float(iterations) if ctx.knockout else None,
        "avg_goals_a": total_goals_a / float(iterations),
        "avg_goals_b": total_goals_b / float(iterations),
        "extra_time_rate": extra_time_count / float(iterations) if ctx.knockout else None,
        "penalties_rate": penalties_count / float(iterations) if ctx.knockout else None,
        "top_scores": [(f"{score[0]}-{score[1]}", count / float(iterations)) for score, count in top_scores],
    }


def pretty_status(status: str) -> str:
    return {
        "qualified": "Clasificado",
        "uefa_playoff": "Repechaje UEFA",
        "fifa_playoff": "Repechaje FIFA",
        "eliminated": "Eliminado",
    }.get(status, status)


UEFA_PLAYOFF_PATHS = {
    "UEFA_A": {
        "semi_1": ("Italy", "Northern Ireland"),
        "semi_2": ("Wales", "Bosnia and Herzegovina"),
        "final_host": "semi_2",
    },
    "UEFA_B": {
        "semi_1": ("Ukraine", "Sweden"),
        "semi_2": ("Poland", "Albania"),
        "final_host": "semi_1",
    },
    "UEFA_C": {
        "semi_1": ("Turkey", "Romania"),
        "semi_2": ("Slovakia", "Kosovo"),
        "final_host": "semi_2",
    },
    "UEFA_D": {
        "semi_1": ("Denmark", "North Macedonia"),
        "semi_2": ("Czech Republic", "Republic of Ireland"),
        "final_host": "semi_2",
    },
}

FIFA_PLAYOFF_PATHS = {
    "FIFA_1": {
        "host": "Dem. Rep. of Congo",
        "semi": ("Jamaica", "New Caledonia"),
    },
    "FIFA_2": {
        "host": "Iraq",
        "semi": ("Bolivia", "Suriname"),
    },
}


def resolved_uefa_path_winners(teams: Dict[str, Team]) -> Dict[str, str]:
    return calculate_resolved_uefa_path_winners(teams, uefa_playoff_paths=UEFA_PLAYOFF_PATHS)


def resolved_fifa_path_winners(teams: Dict[str, Team]) -> Dict[str, str]:
    return calculate_resolved_fifa_path_winners(teams, fifa_playoff_paths=FIFA_PLAYOFF_PATHS)


def confirmed_teams(teams: Dict[str, Team]) -> List[Team]:
    return [team for team in teams.values() if team.status == "qualified"]


def average_opponent_metrics(team: Team, opponents: Sequence[Team]) -> Tuple[float, float, float]:
    xgf = 0.0
    xga = 0.0
    xpts = 0.0
    count = 0
    for opponent in opponents:
        if opponent.name == team.name:
            continue
        prediction = predict_match(
            {team.name: team, opponent.name: opponent},
            team.name,
            opponent.name,
            MatchContext(),
            top_scores=0,
        )
        xgf += prediction.expected_goals_a
        xga += prediction.expected_goals_b
        xpts += 3.0 * prediction.win_a + prediction.draw
        count += 1
    if count == 0:
        return 0.0, 0.0, 0.0
    return xgf / count, xga / count, xpts / count


def uefa_playoff_probabilities(teams: Dict[str, Team]) -> Dict[str, float]:
    probabilities = {name: 0.0 for name in teams}
    resolved = resolved_uefa_path_winners(teams)
    for winner in resolved.values():
        probabilities[winner] = 1.0

    for placeholder, path in UEFA_PLAYOFF_PATHS.items():
        if placeholder in resolved:
            continue
        semi_1 = predict_match(
            teams,
            path["semi_1"][0],
            path["semi_1"][1],
            MatchContext(neutral=False, home_team=path["semi_1"][0], knockout=True),
            include_advancement=True,
        )
        semi_2 = predict_match(
            teams,
            path["semi_2"][0],
            path["semi_2"][1],
            MatchContext(neutral=False, home_team=path["semi_2"][0], knockout=True),
            include_advancement=True,
        )

        semi_1_adv = {
            path["semi_1"][0]: semi_1.advance_a or 0.0,
            path["semi_1"][1]: semi_1.advance_b or 0.0,
        }
        semi_2_adv = {
            path["semi_2"][0]: semi_2.advance_a or 0.0,
            path["semi_2"][1]: semi_2.advance_b or 0.0,
        }

        for finalist_1, finalist_1_prob in semi_1_adv.items():
            for finalist_2, finalist_2_prob in semi_2_adv.items():
                if finalist_1_prob == 0.0 or finalist_2_prob == 0.0:
                    continue
                final_host = finalist_1 if path["final_host"] == "semi_1" else finalist_2
                ctx = MatchContext(neutral=False, home_team=final_host, knockout=True)
                final_prediction = predict_match(
                    teams,
                    finalist_1,
                    finalist_2,
                    ctx,
                    include_advancement=True,
                )
                probabilities[finalist_1] += finalist_1_prob * finalist_2_prob * (final_prediction.advance_a or 0.0)
                probabilities[finalist_2] += finalist_1_prob * finalist_2_prob * (final_prediction.advance_b or 0.0)

    return probabilities


def fifa_playoff_probabilities(teams: Dict[str, Team]) -> Dict[str, float]:
    probabilities = {name: 0.0 for name in teams}
    resolved = resolved_fifa_path_winners(teams)
    for winner in resolved.values():
        probabilities[winner] = 1.0

    if "FIFA_1" not in resolved:
        path_1_semi = predict_match(
            teams,
            "Jamaica",
            "New Caledonia",
            MatchContext(neutral=True, venue_country="Mexico", knockout=True),
            include_advancement=True,
        )

        path_1_adv = {
            "Jamaica": path_1_semi.advance_a or 0.0,
            "New Caledonia": path_1_semi.advance_b or 0.0,
        }

        for finalist, finalist_prob in path_1_adv.items():
            final_prediction = predict_match(
                teams,
                "Dem. Rep. of Congo",
                finalist,
                MatchContext(neutral=True, venue_country="Mexico", knockout=True),
                include_advancement=True,
            )
            probabilities["Dem. Rep. of Congo"] += finalist_prob * (final_prediction.advance_a or 0.0)
            probabilities[finalist] += finalist_prob * (final_prediction.advance_b or 0.0)

    if "FIFA_2" not in resolved:
        path_2_semi = predict_match(
            teams,
            "Bolivia",
            "Suriname",
            MatchContext(neutral=True, venue_country="Mexico", knockout=True),
            include_advancement=True,
        )

        path_2_adv = {
            "Bolivia": path_2_semi.advance_a or 0.0,
            "Suriname": path_2_semi.advance_b or 0.0,
        }

        for finalist, finalist_prob in path_2_adv.items():
            final_prediction = predict_match(
                teams,
                "Iraq",
                finalist,
                MatchContext(neutral=True, venue_country="Mexico", knockout=True),
                include_advancement=True,
            )
            probabilities["Iraq"] += finalist_prob * (final_prediction.advance_a or 0.0)
            probabilities[finalist] += finalist_prob * (final_prediction.advance_b or 0.0)

    return probabilities


def qualification_probabilities(teams: Dict[str, Team]) -> Dict[str, float]:
    return calculate_qualification_probabilities(
        teams,
        uefa_playoff_probabilities_fn=uefa_playoff_probabilities,
        fifa_playoff_probabilities_fn=fifa_playoff_probabilities,
    )


def sample_knockout_winner(teams: Dict[str, Team], team_a: str, team_b: str, ctx: MatchContext) -> str:
    mu_a, mu_b = expected_goals(teams[team_a], teams[team_b], ctx)
    goals_a, goals_b = sample_score(mu_a, mu_b, ctx)
    return sample_knockout_resolution(
        teams[team_a],
        teams[team_b],
        ctx,
        goals_a,
        goals_b,
        mu_a,
        mu_b,
    )["winner"]


def simulate_playoffs(teams: Dict[str, Team], iterations: int) -> Dict[str, float]:
    counts = {name: 0 for name in teams}
    resolved = resolved_uefa_path_winners(teams)
    resolved_fifa = resolved_fifa_path_winners(teams)
    for _ in range(iterations):
        if "UEFA_A" in resolved:
            counts[resolved["UEFA_A"]] += 1
        else:
            semi_a_1 = sample_knockout_winner(
                teams, "Italy", "Northern Ireland", MatchContext(neutral=False, home_team="Italy", knockout=True)
            )
            semi_a_2 = sample_knockout_winner(
                teams, "Wales", "Bosnia and Herzegovina", MatchContext(neutral=False, home_team="Wales", knockout=True)
            )
            counts[
                sample_knockout_winner(
                    teams, semi_a_1, semi_a_2, MatchContext(neutral=False, home_team=semi_a_2, knockout=True)
                )
            ] += 1

        if "UEFA_B" in resolved:
            counts[resolved["UEFA_B"]] += 1
        else:
            semi_b_1 = sample_knockout_winner(
                teams, "Ukraine", "Sweden", MatchContext(neutral=False, home_team="Ukraine", knockout=True)
            )
            semi_b_2 = sample_knockout_winner(
                teams, "Poland", "Albania", MatchContext(neutral=False, home_team="Poland", knockout=True)
            )
            counts[
                sample_knockout_winner(
                    teams, semi_b_1, semi_b_2, MatchContext(neutral=False, home_team=semi_b_1, knockout=True)
                )
            ] += 1

        if "UEFA_C" in resolved:
            counts[resolved["UEFA_C"]] += 1
        else:
            semi_c_1 = sample_knockout_winner(
                teams, "Turkey", "Romania", MatchContext(neutral=False, home_team="Turkey", knockout=True)
            )
            semi_c_2 = sample_knockout_winner(
                teams, "Slovakia", "Kosovo", MatchContext(neutral=False, home_team="Slovakia", knockout=True)
            )
            counts[
                sample_knockout_winner(
                    teams, semi_c_1, semi_c_2, MatchContext(neutral=False, home_team=semi_c_2, knockout=True)
                )
            ] += 1

        if "UEFA_D" in resolved:
            counts[resolved["UEFA_D"]] += 1
        else:
            semi_d_1 = sample_knockout_winner(
                teams, "Denmark", "North Macedonia", MatchContext(neutral=False, home_team="Denmark", knockout=True)
            )
            semi_d_2 = sample_knockout_winner(
                teams,
                "Czech Republic",
                "Republic of Ireland",
                MatchContext(neutral=False, home_team="Czech Republic", knockout=True),
            )
            counts[
                sample_knockout_winner(
                    teams, semi_d_1, semi_d_2, MatchContext(neutral=False, home_team=semi_d_2, knockout=True)
                )
            ] += 1

        if "FIFA_1" in resolved_fifa:
            counts[resolved_fifa["FIFA_1"]] += 1
        else:
            fifa_1 = sample_knockout_winner(
                teams, "Jamaica", "New Caledonia", MatchContext(neutral=True, venue_country="Mexico", knockout=True)
            )
            counts[
                sample_knockout_winner(
                    teams,
                    "Dem. Rep. of Congo",
                    fifa_1,
                    MatchContext(neutral=True, venue_country="Mexico", knockout=True),
                )
            ] += 1

        if "FIFA_2" in resolved_fifa:
            counts[resolved_fifa["FIFA_2"]] += 1
        else:
            fifa_2 = sample_knockout_winner(
                teams, "Bolivia", "Suriname", MatchContext(neutral=True, venue_country="Mexico", knockout=True)
            )
            counts[
                sample_knockout_winner(
                    teams, "Iraq", fifa_2, MatchContext(neutral=True, venue_country="Mexico", knockout=True)
                )
            ] += 1

    return {name: count / float(iterations) for name, count in counts.items()}


def load_tournament_config(path: Path) -> dict:
    return calculate_load_tournament_config(path)


def sample_uefa_path_winner(
    teams: Dict[str, Team],
    semi_1: Tuple[str, str],
    semi_2: Tuple[str, str],
    final_host_path: str,
) -> str:
    return calculate_sample_uefa_path_winner(
        teams,
        semi_1,
        semi_2,
        final_host_path,
        sample_knockout_winner=sample_knockout_winner,
        MatchContextCls=MatchContext,
    )


def sample_playoff_placeholders(teams: Dict[str, Team]) -> Dict[str, str]:
    return calculate_sample_playoff_placeholders(
        teams,
        resolved_uefa_path_winners_fn=resolved_uefa_path_winners,
        resolved_fifa_path_winners_fn=resolved_fifa_path_winners,
        sample_uefa_path_winner_fn=sample_uefa_path_winner,
        sample_knockout_winner=sample_knockout_winner,
        MatchContextCls=MatchContext,
    )


def resolve_group_entry(entry: object, placeholders: Dict[str, str]) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and "placeholder" in entry:
        placeholder = entry["placeholder"]
        if placeholder not in placeholders:
            raise SystemExit(f"Placeholder no reconocido: {placeholder}")
        return placeholders[placeholder]
    raise SystemExit(f"Entrada de grupo no soportada: {entry}")


def resolve_groups_for_iteration(config: dict, placeholders: Dict[str, str]) -> Dict[str, List[str]]:
    groups = {}
    for group_name, entries in config["groups"].items():
        groups[group_name] = [resolve_group_entry(entry, placeholders) for entry in entries]
    return groups


def initial_simulation_states(payload: Optional[dict] = None) -> Dict[str, dict]:
    if not payload:
        return {}
    return copy_states(payload)


def ensure_state(states: Dict[str, dict], team_name: str) -> dict:
    if team_name not in states:
        states[team_name] = default_team_state()
    else:
        states[team_name] = normalize_team_state(states[team_name])
    return states[team_name]


def sample_cards(
    teams: Dict[str, Team],
    team_a: str,
    team_b: str,
    importance: float,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> Tuple[int, int, int, int]:
    return calculate_sample_cards(
        teams,
        team_a,
        team_b,
        importance,
        state_a=state_a,
        state_b=state_b,
        profile_for=profile_for,
        rivalry_intensity=rivalry_intensity,
        fatigue_level=fatigue_level,
        discipline_trend=discipline_trend,
        poisson_sample=poisson_sample,
        fast_random=fast_random,
        clamp=clamp,
    )


def penalties_probability(team_a: Team, team_b: Team, state_a: dict, state_b: dict) -> float:
    return calculate_penalties_probability(
        team_a,
        team_b,
        state_a,
        state_b,
        profile_for=profile_for,
        logistic=logistic,
        recent_form_signal=recent_form_signal,
        fatigue_level=fatigue_level,
    )


def penalty_conversion_probability(
    taker: Team,
    keeper_team: Team,
    ctx: MatchContext,
    taker_state: dict,
    keeper_state: dict,
    *,
    taker_first: bool,
    sudden_death: bool,
    trailing: bool,
    round_number: int,
) -> float:
    return calculate_penalty_conversion_probability(
        taker,
        keeper_team,
        ctx,
        taker_state,
        keeper_state,
        taker_first=taker_first,
        sudden_death=sudden_death,
        trailing=trailing,
        round_number=round_number,
        profile_for=profile_for,
        centered=centered,
        recent_form_signal=recent_form_signal,
        fatigue_level=fatigue_level,
        availability_level=availability_level,
        clamp=clamp,
    )


def simulate_penalty_shootout(
    team_a: Team,
    team_b: Team,
    ctx: MatchContext,
    state_a: dict,
    state_b: dict,
    *,
    a_starts: bool,
) -> dict:
    return run_penalty_shootout(
        team_a,
        team_b,
        ctx,
        state_a,
        state_b,
        a_starts=a_starts,
        penalty_conversion_probability_fn=penalty_conversion_probability,
        penalties_probability_fn=penalties_probability,
        fast_random=fast_random,
    )


def penalty_shootout_summary(
    team_a: Team,
    team_b: Team,
    ctx: MatchContext,
    state_a: dict,
    state_b: dict,
    iterations: int = 2400,
) -> dict:
    return calculate_penalty_shootout_summary(
        team_a,
        team_b,
        ctx,
        state_a,
        state_b,
        iterations=iterations,
        simulate_penalty_shootout_fn=simulate_penalty_shootout,
    )


def build_simulation_context(
    teams: Dict[str, Team],
    states: Dict[str, dict],
    team_a: str,
    team_b: str,
    stage: str,
    group_name: Optional[str] = None,
) -> MatchContext:
    return calculate_build_simulation_context(
        teams,
        states,
        team_a,
        team_b,
        stage,
        group_name=group_name,
        ensure_state=ensure_state,
        dynamic_injury_load=dynamic_injury_load,
        predictive_yellow_cards=predictive_yellow_cards,
        stage_importance=STAGE_IMPORTANCE,
        random_choice=random.choice,
        MatchContext=MatchContext,
    )


def update_simulation_state(
    teams: Dict[str, Team],
    states: Dict[str, dict],
    team_a: str,
    team_b: str,
    ctx: MatchContext,
    expected_goals_a: float,
    expected_goals_b: float,
    score_a: int,
    score_b: int,
    yellows_a: int,
    reds_a: int,
    yellows_b: int,
    reds_b: int,
    stage: str,
    winner: Optional[str] = None,
    went_extra_time: bool = False,
    went_penalties: bool = False,
    live_stats: Optional[Dict[str, float]] = None,
) -> None:
    return calculate_update_simulation_state(
        teams,
        states,
        team_a,
        team_b,
        ctx,
        expected_goals_a,
        expected_goals_b,
        score_a,
        score_b,
        yellows_a,
        reds_a,
        yellows_b,
        reds_b,
        stage,
        winner=winner,
        went_extra_time=went_extra_time,
        went_penalties=went_penalties,
        live_stats=live_stats,
        ensure_state=ensure_state,
        effective_elo=effective_elo,
        elo_delta_for_match=calculate_elo_delta_for_match,
        profile_for=profile_for,
        live_signature_metrics=live_signature_metrics,
        update_tactical_signature_state=update_tactical_signature_state,
        clamp=clamp,
    )


def simulate_match_sample(
    teams: Dict[str, Team],
    states: Dict[str, dict],
    team_a: str,
    team_b: str,
    stage: str,
    group_name: Optional[str] = None,
) -> dict:
    return calculate_simulate_match_sample(
        teams,
        states,
        team_a,
        team_b,
        stage,
        group_name=group_name,
        build_simulation_context_fn=build_simulation_context,
        ensure_state=ensure_state,
        cached_simulation_expected_goals=cached_simulation_expected_goals,
        simulation_state_signature=simulation_state_signature,
        sample_score=sample_score,
        sample_cards_fn=sample_cards,
        sample_knockout_resolution_fn=sample_knockout_resolution,
        update_simulation_state_fn=update_simulation_state,
    )


def standings_entry(teams: Dict[str, Team], states: Dict[str, dict], group_name: str, team_name: str) -> dict:
    return calculate_standings_entry(
        teams,
        states,
        group_name,
        team_name,
        ensure_state=ensure_state,
    )


def sort_standings(entries: Sequence[dict]) -> List[dict]:
    return calculate_sort_standings(entries)


def simulate_group_stage(
    teams: Dict[str, Team],
    groups: Dict[str, List[str]],
    states: Dict[str, dict],
) -> Dict[str, List[dict]]:
    return calculate_simulate_group_stage(
        teams,
        groups,
        states,
        ensure_state=ensure_state,
        group_match_pairs=GROUP_MATCH_PAIRS,
        simulate_match_sample_fn=simulate_match_sample,
        standings_entry_fn=standings_entry,
        sort_standings_fn=sort_standings,
    )


def assign_third_place_slots(
    standings: Dict[str, List[dict]],
    winner_ranks: Dict[str, int],
) -> Tuple[List[dict], Dict[str, str]]:
    return calculate_assign_third_place_slots(
        standings,
        winner_ranks,
        sort_standings_fn=sort_standings,
        r32_matches=R32_MATCHES,
    )


def resolve_r32_team(
    slot: dict,
    standings: Dict[str, List[dict]],
    third_assignments: Dict[str, str],
    match_id: str,
) -> str:
    return calculate_resolve_r32_team(slot, standings, third_assignments, match_id)


def run_knockout_round(
    teams: Dict[str, Team],
    states: Dict[str, dict],
    stage: str,
    fixtures: Sequence[Tuple[str, str, str]],
    previous_winners: Dict[str, str],
) -> Tuple[Dict[str, str], Dict[str, dict]]:
    return calculate_run_knockout_round(
        teams,
        states,
        stage,
        fixtures,
        previous_winners,
        simulate_match_sample_fn=simulate_match_sample,
    )


def simulate_tournament_iteration(
    teams: Dict[str, Team],
    config: dict,
    initial_payload: Optional[dict] = None,
) -> dict:
    return calculate_simulate_tournament_iteration(
        teams,
        config,
        initial_payload=initial_payload,
        sample_playoff_placeholders=sample_playoff_placeholders,
        resolve_groups_for_iteration=resolve_groups_for_iteration,
        initial_simulation_states=initial_simulation_states,
        simulate_group_stage_fn=simulate_group_stage,
        sort_standings_fn=sort_standings,
        assign_third_place_slots_fn=assign_third_place_slots,
        resolve_r32_team_fn=resolve_r32_team,
        run_knockout_round_fn=run_knockout_round,
        r32_matches=R32_MATCHES,
        knockout_matches=KNOCKOUT_MATCHES,
        simulate_match_sample_fn=simulate_match_sample,
    )


def _simulate_tournament_batch(
    batch_size: int,
    seed: int,
    teams: Dict[str, Team],
    config: dict,
    initial_payload: Optional[dict],
) -> Dict[str, dict]:
    return calculate_simulate_tournament_batch(
        batch_size,
        seed,
        teams,
        config,
        initial_payload,
        seed_all_rng=seed_all_rng,
        empty_tournament_summary=empty_tournament_summary,
        ensure_state=ensure_state,
        simulate_tournament_iteration_fn=simulate_tournament_iteration,
    )


def _project_bracket_batch(
    batch_size: int,
    seed: int,
    teams: Dict[str, Team],
    config: dict,
    initial_payload: Optional[dict],
) -> Dict[str, dict]:
    return calculate_project_bracket_batch(
        batch_size,
        seed,
        teams,
        config,
        initial_payload,
        seed_all_rng=seed_all_rng,
        empty_bracket_aggregate=empty_bracket_aggregate,
        bracket_match_order_fn=bracket_match_order,
        simulate_tournament_iteration_fn=simulate_tournament_iteration,
    )


def command_simulate_tournament(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    if args.seed is not None:
        seed_all_rng(args.seed)

    config = load_tournament_config(Path(args.config))
    initial_payload = None if getattr(args, "ignore_state", False) else load_persistent_payload(Path(args.state_file), teams)
    workers = args.workers if args.workers > 0 else default_parallel_workers(args.iterations)
    summary = empty_tournament_summary(teams)
    if workers > 1:
        for batch_summary in run_parallel_batches(
            iterations=args.iterations,
            workers=workers,
            seed=args.seed,
            worker_fn=_simulate_tournament_batch,
            teams=teams,
            config=config,
            initial_payload=initial_payload,
            progress_every=args.progress_every,
        ):
            merge_tournament_summary(summary, batch_summary)
    else:
        for iteration in range(1, args.iterations + 1):
            result = simulate_tournament_iteration(teams, config, initial_payload=initial_payload)
            participants = set(result["participants"])
            for team_name in participants:
                stats = summary[team_name]
                state = ensure_state(result["states"], team_name)
                stats["appear"] += 1
                stats["avg_group_points"] += state["group_points"]
                stats["avg_goals_for"] += state["goals_for"]
                stats["avg_goals_against"] += state["goals_against"]

            for group_table in result["standings"].values():
                summary[group_table[0]["team"]]["group_winner"] += 1

            for team_name, stage in result["stage_reached"].items():
                stats = summary[team_name]
                if stage in {"round32", "round16", "quarterfinal", "semifinal", "final", "champion"}:
                    stats["advance_group"] += 1
                if stage in {"round16", "quarterfinal", "semifinal", "final", "champion"}:
                    stats["reach_round16"] += 1
                if stage in {"quarterfinal", "semifinal", "final", "champion"}:
                    stats["reach_quarterfinal"] += 1
                if stage in {"semifinal", "final", "champion"}:
                    stats["reach_semifinal"] += 1
                if stage in {"final", "champion"}:
                    stats["reach_final"] += 1
                if stage == "champion":
                    stats["champion"] += 1
            summary[result["third_place"]]["third_place"] += 1
            summary[result["fourth_place"]]["fourth_place"] += 1
            if args.progress_every and iteration % args.progress_every == 0:
                print(f"Progreso: {iteration}/{args.iterations} iteraciones")

    rows = []
    for team_name, stats in summary.items():
        appear = stats["appear"] / float(args.iterations)
        if appear == 0.0 and not args.full:
            continue
        rows.append(
            (
                team_name,
                appear,
                stats["advance_group"] / float(args.iterations),
                stats["reach_round16"] / float(args.iterations),
                stats["reach_quarterfinal"] / float(args.iterations),
                stats["reach_semifinal"] / float(args.iterations),
                stats["reach_final"] / float(args.iterations),
                stats["third_place"] / float(args.iterations),
                stats["fourth_place"] / float(args.iterations),
                stats["champion"] / float(args.iterations),
                stats["group_winner"] / float(args.iterations),
                stats["avg_group_points"] / max(stats["appear"], 1),
            )
        )

    rows.sort(key=lambda row: (row[9], row[6], row[5], row[1], row[0]), reverse=True)
    if not args.full:
        rows = rows[: args.top]

    print(
        f"Simulacion Monte Carlo del torneo | iteraciones={args.iterations} | "
        f"config={Path(args.config).name} | workers={workers}"
    )
    print("Equipo                     Mundial  Grupo  Octavos Cuartos Semis  Final   3ro    4to Campeon  1roGrp PtsGrp")
    print("-" * 118)
    for row in rows:
        name, appear, advance_group, reach_round16, reach_quarterfinal, reach_semifinal, reach_final, third_place, fourth_place, champion, group_winner, avg_points = row
        print(
            f"{name:25} {appear:7.1%} {advance_group:6.1%} {reach_round16:8.1%} "
            f"{reach_quarterfinal:7.1%} {reach_semifinal:6.1%} {reach_final:6.1%} "
            f"{third_place:6.1%} {fourth_place:6.1%} {champion:8.1%} {group_winner:7.1%} {avg_points:6.2f}"
        )


def bracket_match_order() -> List[str]:
    return calculate_bracket_match_order(
        r32_matches=R32_MATCHES,
        knockout_matches=KNOCKOUT_MATCHES,
    )


def stage_for_match_id(match_id: str) -> str:
    match_number = int(match_id[1:])
    if 73 <= match_number <= 88:
        return "round32"
    if 89 <= match_number <= 96:
        return "round16"
    if 97 <= match_number <= 100:
        return "quarterfinal"
    if 101 <= match_number <= 102:
        return "semifinal"
    if match_id == "M104":
        return "third_place"
    if match_id == "M103":
        return "final"
    raise SystemExit(f"ID de llave no reconocido: {match_id}")


def structured_match_projection(match_id: str, aggregate: dict, iterations: int) -> dict:
    modal_outcome, modal_count = max(aggregate["outcomes"].items(), key=lambda item: item[1])
    team_a, team_b, winner = modal_outcome
    appearance_counts: Dict[str, int] = {}
    opponent_counts: Dict[str, Dict[str, int]] = {}
    matchup_counts: Dict[Tuple[str, str], int] = {}
    matchup_winner_counts: Dict[Tuple[str, str], Dict[str, int]] = {}
    for outcome, count in aggregate["outcomes"].items():
        scenario_a, scenario_b, _ = outcome
        appearance_counts[scenario_a] = appearance_counts.get(scenario_a, 0) + count
        appearance_counts[scenario_b] = appearance_counts.get(scenario_b, 0) + count
        opponent_counts.setdefault(scenario_a, {})
        opponent_counts.setdefault(scenario_b, {})
        opponent_counts[scenario_a][scenario_b] = opponent_counts[scenario_a].get(scenario_b, 0) + count
        opponent_counts[scenario_b][scenario_a] = opponent_counts[scenario_b].get(scenario_a, 0) + count
        matchup_key = (scenario_a, scenario_b)
        matchup_counts[matchup_key] = matchup_counts.get(matchup_key, 0) + count
        matchup_winner_counts.setdefault(matchup_key, {})
        matchup_winner_counts[matchup_key][outcome[2]] = matchup_winner_counts[matchup_key].get(outcome[2], 0) + count
    top_scenarios = []
    for outcome, count in sorted(aggregate["outcomes"].items(), key=lambda item: item[1], reverse=True)[:3]:
        scenario_a, scenario_b, scenario_winner = outcome
        top_scenarios.append(
            {
                "team_a": scenario_a,
                "team_b": scenario_b,
                "winner": scenario_winner,
                "prob": count / float(iterations),
            }
        )
    appearance_probabilities = {
        team: count / float(iterations)
        for team, count in sorted(appearance_counts.items(), key=lambda item: item[1], reverse=True)
    }
    advance_probabilities = {
        team: count / float(iterations)
        for team, count in sorted(aggregate["winner"].items(), key=lambda item: item[1], reverse=True)
    }
    opponent_map = {}
    for team, counts in opponent_counts.items():
        total = appearance_counts.get(team, 0)
        if total <= 0:
            continue
        opponent_map[team] = [
            {
                "opponent": opponent,
                "matchup_prob": count / float(iterations),
                "conditional_if_reaches": count / float(total),
            }
            for opponent, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:3]
        ]
    matchup_scenarios = []
    for (scenario_a, scenario_b), count in sorted(matchup_counts.items(), key=lambda item: item[1], reverse=True):
        winner_rows = []
        winners_for_matchup = matchup_winner_counts.get((scenario_a, scenario_b), {})
        for matchup_winner, winner_count in sorted(winners_for_matchup.items(), key=lambda item: item[1], reverse=True):
            winner_rows.append(
                {
                    "team": matchup_winner,
                    "conditional_prob": winner_count / float(count),
                    "overall_prob": winner_count / float(iterations),
                }
            )
        lead_winner = winner_rows[0]["team"] if winner_rows else scenario_a
        lead_conditional = winner_rows[0]["conditional_prob"] if winner_rows else 0.0
        lead_overall = winner_rows[0]["overall_prob"] if winner_rows else 0.0
        matchup_scenarios.append(
            {
                "team_a": scenario_a,
                "team_b": scenario_b,
                "winner": lead_winner,
                "matchup_prob": count / float(iterations),
                "conditional_winner_prob": lead_conditional,
                "winner_prob": lead_overall,
                "conditional_winners": winner_rows[:3],
            }
        )
    penalty_scores = sorted(aggregate.get("penalty_scores", {}).items(), key=lambda item: item[1], reverse=True)[:3]
    return {
        "match_id": match_id,
        "title": BRACKET_MATCH_TITLES.get(match_id, match_id),
        "stage": stage_for_match_id(match_id),
        "team_a": team_a,
        "team_b": team_b,
        "winner": winner,
        "matchup_prob": modal_count / float(iterations),
        "winner_prob": aggregate["winner"][winner] / float(iterations),
        "extra_time_prob": aggregate["went_extra_time"] / float(iterations),
        "penalties_prob": aggregate["went_penalties"] / float(iterations),
        "top_scenarios": top_scenarios,
        "matchup_scenarios": matchup_scenarios,
        "appearance_probabilities": appearance_probabilities,
        "advance_probabilities": advance_probabilities,
        "opponent_map": opponent_map,
        "top_penalty_scores": [
            {"score": f"{score[0]}-{score[1]}", "prob": count / float(iterations)}
            for score, count in penalty_scores
        ],
    }


def format_match_projection(match_id: str, aggregate: dict, iterations: int) -> List[str]:
    projection = structured_match_projection(match_id, aggregate, iterations)
    team_a = projection["team_a"]
    team_b = projection["team_b"]
    winner = projection["winner"]
    outcome_prob = projection["matchup_prob"]
    winner_prob = projection["winner_prob"]
    extra_time_prob = projection["extra_time_prob"]
    penalties_prob = projection["penalties_prob"]
    lines = [
        f"### {BRACKET_MATCH_TITLES.get(match_id, match_id)}",
        f"- Cruce que aparece mas veces en la simulacion: {team_a} vs {team_b}",
        f"- Probabilidad de que este cruce ocurra: {outcome_prob:.1%}",
        f"- Equipo con mas probabilidad de salir de esta llave: {winner} ({winner_prob:.1%})",
    ]
    alternatives = [
        f"{scenario['team_a']} vs {scenario['team_b']} | gana mas probable {scenario['winner']} | este escenario aparece {scenario['prob']:.1%}"
        for scenario in projection.get("top_scenarios", [])[1:]
    ]
    if alternatives:
        lines.append(f"- Otros cruces que tambien aparecen seguido: {'; '.join(alternatives)}")
    if match_id != "M104":
        lines.append(f"- Va a proroga en {extra_time_prob:.1%} y a penales en {penalties_prob:.1%}")
        penalty_scores = projection.get("top_penalty_scores", [])
        if penalty_scores:
            lines.append(
                "- Marcadores de penales mas probables en este cruce: "
                + "; ".join(f"{item['score']} ({item['prob']:.1%})" for item in penalty_scores)
            )
    return lines


def command_project_bracket(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    if args.seed is not None:
        seed_all_rng(args.seed)

    config = load_tournament_config(Path(args.config))
    initial_payload = None if getattr(args, "ignore_state", False) else load_persistent_payload(Path(args.state_file), teams)
    workers = args.workers if args.workers > 0 else default_parallel_workers(args.iterations)
    match_aggregate = empty_bracket_aggregate(bracket_match_order())
    if workers > 1:
        for batch_aggregate in run_parallel_batches(
            iterations=args.iterations,
            workers=workers,
            seed=args.seed,
            worker_fn=_project_bracket_batch,
            teams=teams,
            config=config,
            initial_payload=initial_payload,
            progress_every=args.progress_every,
        ):
            merge_bracket_aggregate(match_aggregate, batch_aggregate)
    else:
        for iteration in range(1, args.iterations + 1):
            result = simulate_tournament_iteration(teams, config, initial_payload=initial_payload)
            for match_id, match_result in result["bracket_matches"].items():
                aggregate = match_aggregate[match_id]
                outcome_key = (match_result["team_a"], match_result["team_b"], match_result["winner"])
                aggregate["outcomes"][outcome_key] = aggregate["outcomes"].get(outcome_key, 0) + 1
                aggregate["winner"][match_result["winner"]] = aggregate["winner"].get(match_result["winner"], 0) + 1
                aggregate["went_extra_time"] += 1 if match_result.get("went_extra_time") else 0
                aggregate["went_penalties"] += 1 if match_result.get("went_penalties") else 0
                if match_result.get("went_penalties") and match_result.get("penalty_score_a") is not None and match_result.get("penalty_score_b") is not None:
                    penalty_key = (int(match_result["penalty_score_a"]), int(match_result["penalty_score_b"]))
                    aggregate["penalty_scores"][penalty_key] = aggregate["penalty_scores"].get(penalty_key, 0) + 1
            if args.progress_every and iteration % args.progress_every == 0:
                print(f"Progreso llave: {iteration}/{args.iterations} iteraciones")

    sections = [
        f"# Llave actual proyectada | iteraciones={args.iterations}",
        "",
        "## Dieciseisavos de final",
    ]
    for match_id in [match["id"] for match in R32_MATCHES]:
        sections.extend(format_match_projection(match_id, match_aggregate[match_id], args.iterations))
        sections.append("")

    sections.append("## Octavos de final")
    for match_id, _, _ in KNOCKOUT_MATCHES["round16"]:
        sections.extend(format_match_projection(match_id, match_aggregate[match_id], args.iterations))
        sections.append("")

    sections.append("## Cuartos de final")
    for match_id, _, _ in KNOCKOUT_MATCHES["quarterfinal"]:
        sections.extend(format_match_projection(match_id, match_aggregate[match_id], args.iterations))
        sections.append("")

    sections.append("## Semifinales")
    for match_id, _, _ in KNOCKOUT_MATCHES["semifinal"]:
        sections.extend(format_match_projection(match_id, match_aggregate[match_id], args.iterations))
        sections.append("")

    sections.append("## Partido por el tercer puesto")
    sections.extend(format_match_projection("M104", match_aggregate["M104"], args.iterations))
    sections.append("")

    sections.append("## Final")
    sections.extend(format_match_projection("M103", match_aggregate["M103"], args.iterations))
    sections.append("")

    content = "\n".join(sections)
    structured = {
        "updated_at": iso_timestamp(),
        "iterations": args.iterations,
        "workers": workers,
        "matches": {
            match_id: structured_match_projection(match_id, aggregate, args.iterations)
            for match_id, aggregate in match_aggregate.items()
        },
    }
    output_path = Path(args.output)
    output_json_path = Path(args.json_output)
    output_path.write_text(content)
    output_json_path.write_text(json.dumps(structured, indent=2))
    print(f"Llave proyectada guardada en {output_path} | workers={workers}")
    print(f"Llave estructurada guardada en {output_json_path}")
    print(content)


def format_pct(value: float) -> str:
    return f"{value:.1%}"


def dashboard_stage_label(stage: str, group: Optional[str]) -> str:
    if stage == "group" and group:
        return f"Grupo {group}"
    labels = {
        "group": "Fase de grupos",
        "round32": "Dieciseisavos de final",
        "round16": "Octavos de final",
        "quarterfinal": "Cuartos de final",
        "semifinal": "Semifinal",
        "third_place": "Tercer puesto",
        "final": "Final",
    }
    return labels.get(stage, stage)


def resolved_team_name_from_penalties(
    penalties_winner: Optional[str],
    team_a: str,
    team_b: str,
) -> Optional[str]:
    return package_resolved_team_name_from_penalties(
        penalties_winner,
        team_a,
        team_b,
        aliases=TEAM_NAME_ALIASES,
    )


def resolved_winner_for_entry(entry: dict, prediction: MatchPrediction) -> Optional[str]:
    score_a = entry.get("actual_score_a")
    score_b = entry.get("actual_score_b")
    if score_a is None or score_b is None:
        return None
    if int(score_a) > int(score_b):
        return prediction.team_a
    if int(score_b) > int(score_a):
        return prediction.team_b
    return resolved_team_name_from_penalties(entry.get("penalties_winner"), prediction.team_a, prediction.team_b)


def next_round_projection_note(
    entry: dict,
    prediction: MatchPrediction,
    bracket_payload: dict,
) -> Optional[str]:
    match_id = entry.get("match_id")
    if not match_id:
        return None
    winner_name = resolved_winner_for_entry(entry, prediction)
    if not winner_name:
        return None
    next_match_id = WINNER_NEXT_MATCH.get(str(match_id))
    if not next_match_id:
        return None
    next_projection = (bracket_payload.get("matches") or {}).get(next_match_id)
    if not next_projection:
        return None
    appearance_prob = float((next_projection.get("appearance_probabilities") or {}).get(winner_name, 0.0))
    advance_prob = float((next_projection.get("advance_probabilities") or {}).get(winner_name, 0.0))
    opponent_scenarios = (next_projection.get("opponent_map") or {}).get(winner_name) or []
    if opponent_scenarios:
        top = opponent_scenarios[0]
        return (
            f"Con este resultado, el siguiente cruce mas probable de {winner_name} es contra {top['opponent']}. "
            f"Ese cruce aparece en {format_pct(float(top['matchup_prob']))} de las simulaciones; "
            f"si {winner_name} llega a ese partido, su rival mas frecuente es {top['opponent']} en {format_pct(float(top['conditional_if_reaches']))}. "
            f"Probabilidad actual de que {winner_name} alcance ese cruce: {format_pct(appearance_prob)} | "
            f"probabilidad de avanzar desde esa llave: {format_pct(advance_prob)}."
        )
    return (
        f"Con este resultado, {winner_name} pasa a la siguiente llave {BRACKET_MATCH_TITLES.get(next_match_id, next_match_id)} "
        f"con probabilidad de presencia {format_pct(appearance_prob)} y probabilidad de avanzar {format_pct(advance_prob)}."
    )


def dashboard_fixture_title(fixture: dict) -> str:
    label = str(fixture.get("label", "")).strip()
    if label:
        return label
    return f"{fixture['team_a']} vs {fixture['team_b']}"


def extract_live_stats_payload(source: dict) -> Dict[str, float]:
    payload = {}
    stat_names = (
        "shots",
        "shots_on_target",
        "shots_off_target",
        "blocked_shots",
        "shots_inside_box",
        "shots_outside_box",
        "big_chances",
        "possession",
        "corners",
        "fouls",
        "yellow_cards",
        "red_cards",
        "xg",
        "xg_proxy",
    )
    for stat in stat_names:
        for prefix in ("a", "b"):
            key = f"live_{stat}_{prefix}"
            value = source.get(key)
            if value is None:
                continue
            payload[f"{stat}_{prefix}"] = float(value)
    return payload


def dashboard_live_stats_lines(entry: dict, team_a: str, team_b: str) -> List[str]:
    stats = extract_live_stats_payload(entry)
    if not stats:
        return []
    lines = []
    if stats.get("shots_a") is not None or stats.get("shots_b") is not None:
        lines.append(
            f"- Tiros: {team_a} {int(stats.get('shots_a', 0.0))} | {team_b} {int(stats.get('shots_b', 0.0))}"
        )
    if stats.get("shots_on_target_a") is not None or stats.get("shots_on_target_b") is not None:
        lines.append(
            f"- Tiros al arco: {team_a} {int(stats.get('shots_on_target_a', 0.0))} | {team_b} {int(stats.get('shots_on_target_b', 0.0))}"
        )
    if stats.get("shots_off_target_a") is not None or stats.get("shots_off_target_b") is not None:
        lines.append(
            f"- Tiros fuera: {team_a} {int(stats.get('shots_off_target_a', 0.0))} | {team_b} {int(stats.get('shots_off_target_b', 0.0))}"
        )
    if stats.get("blocked_shots_a") is not None or stats.get("blocked_shots_b") is not None:
        lines.append(
            f"- Tiros bloqueados: {team_a} {int(stats.get('blocked_shots_a', 0.0))} | {team_b} {int(stats.get('blocked_shots_b', 0.0))}"
        )
    if stats.get("big_chances_a") is not None or stats.get("big_chances_b") is not None:
        lines.append(
            f"- Grandes ocasiones: {team_a} {int(stats.get('big_chances_a', 0.0))} | {team_b} {int(stats.get('big_chances_b', 0.0))}"
        )
    if stats.get("possession_a") is not None or stats.get("possession_b") is not None:
        lines.append(
            f"- Posesion: {team_a} {stats.get('possession_a', 0.0):.0f}% | {team_b} {stats.get('possession_b', 0.0):.0f}%"
        )
    xg_a = stats.get("xg_a", stats.get("xg_proxy_a"))
    xg_b = stats.get("xg_b", stats.get("xg_proxy_b"))
    if xg_a is not None or xg_b is not None:
        label = "Calidad de ocasiones en vivo" if stats.get("xg_a") is not None or stats.get("xg_b") is not None else "Calidad de ocasiones en vivo (estimada)"
        lines.append(
            f"- {label}: {team_a} {float(xg_a or 0.0):.2f} | {team_b} {float(xg_b or 0.0):.2f}"
        )
    if stats.get("red_cards_a") or stats.get("red_cards_b"):
        lines.append(
            f"- Rojas en vivo: {team_a} {int(stats.get('red_cards_a', 0.0))} | {team_b} {int(stats.get('red_cards_b', 0.0))}"
        )
    return lines


def dashboard_shot_timeline_lines(entry: dict, team_a: str, team_b: str) -> List[str]:
    lines = []
    provider = entry.get("live_feed_provider")
    if provider:
        lines.append(f"- Datos en vivo enriquecidos: {provider}")
    for side, team_name in (("a", team_a), ("b", team_b)):
        shot_log = entry.get(f"live_shot_log_{side}") or []
        if not shot_log:
            continue
        pieces = []
        for event in shot_log[-6:]:
            minute = event.get("minute")
            detail = event.get("detail") or event.get("type") or "evento"
            player = event.get("player")
            label = f"{minute}' {detail}" if minute is not None else str(detail)
            if player:
                label += f" ({player})"
            pieces.append(label)
        lines.append(f"- Cronologia de disparos {team_name}: {'; '.join(pieces)}")
    return lines


def dashboard_pattern_lines(entry: dict, prediction: MatchPrediction) -> List[str]:
    return pattern_lines_from_payload(infer_entry_patterns(entry, prediction), prediction.team_a, prediction.team_b)


def infer_entry_patterns(entry: dict, prediction: MatchPrediction) -> Optional[Dict[str, object]]:
    if prediction.live_patterns:
        return prediction.live_patterns
    live_stats = extract_live_stats_payload(entry)
    if not live_stats:
        return None
    score_a = (
        int(entry["actual_score_a"])
        if entry.get("actual_score_a") is not None
        else int(entry.get("live_score_a", 0) or 0)
    )
    score_b = (
        int(entry["actual_score_b"])
        if entry.get("actual_score_b") is not None
        else int(entry.get("live_score_b", 0) or 0)
    )
    phase = "extra_time" if entry.get("went_extra_time") else "regulation"
    return detect_live_play_patterns(
        live_stats,
        1.0 if entry.get("actual_score_a") is not None else clamp((prediction.elapsed_minutes or 0.0) / 90.0, 0.0, 1.0),
        phase,
        score_a,
        score_b,
    )


def pattern_lines_from_payload(patterns: Optional[Dict[str, object]], team_a: str, team_b: str) -> List[str]:
    payload = patterns or {}
    side_a = payload.get("a")
    side_b = payload.get("b")
    if not side_a or not side_b:
        return []
    lines = [
        f"- Patron de juego {team_a}: {side_a.get('summary', 'sin patron dominante claro')}.",
        f"- Patron de juego {team_b}: {side_b.get('summary', 'sin patron dominante claro')}.",
        f"- Ritmo detectado: {payload.get('tempo_label', 'ritmo equilibrado')}.",
    ]
    signals_a = side_a.get("signals") or []
    signals_b = side_b.get("signals") or []
    if signals_a:
        lines.append(f"- Senales {team_a}: {'; '.join(str(signal) for signal in signals_a[:3])}")
    if signals_b:
        lines.append(f"- Senales {team_b}: {'; '.join(str(signal) for signal in signals_b[:3])}")
    return lines


def dashboard_weather_summary(fixture: dict) -> Optional[str]:
    if fixture.get("weather_temperature_c") is None:
        return None
    return (
        f"{fixture.get('weather_temperature_c', 0.0):.1f} C | "
        f"HR {fixture.get('weather_humidity_pct', 0.0):.0f}% | "
        f"viento {fixture.get('weather_wind_kmh', 0.0):.0f} km/h | "
        f"estres {fixture.get('weather_stress', 0.0):.2f}"
    )


def dashboard_fixture_entries(
    fixtures: Sequence[dict],
    teams: Dict[str, Team],
    states: Dict[str, dict],
    top_scores: int,
) -> List[dict]:
    entries = []
    for fixture in fixtures:
        if fixture.get("projection_only"):
            continue
        fixture = resolve_fixture_names(dict(fixture), teams)
        team_a = fixture["team_a"]
        team_b = fixture["team_b"]
        state_a = normalize_team_state(states.get(team_a, {}))
        state_b = normalize_team_state(states.get(team_b, {}))
        ctx = context_from_fixture(fixture, teams, states)
        stage = fixture_stage_name(fixture)
        if fixture.get("status_state") == "in" and fixture.get("live_score_a") is not None and fixture.get("live_score_b") is not None:
            prediction = predict_match_live(
                teams,
                team_a,
                team_b,
                ctx,
                current_score_a=int(fixture.get("live_score_a", 0)),
                current_score_b=int(fixture.get("live_score_b", 0)),
                status_detail=fixture.get("status_detail"),
                top_scores=top_scores,
                include_advancement=stage != "group",
                show_factors=True,
                state_a=state_a,
                state_b=state_b,
                live_stats=extract_live_stats_payload(fixture),
            )
        else:
            prediction = predict_match(
                teams,
                team_a,
                team_b,
                ctx,
                top_scores=top_scores,
                include_advancement=stage != "group",
                show_factors=True,
                state_a=state_a,
                state_b=state_b,
            )
        entries.append(
            {
                "title": dashboard_fixture_title(fixture),
                "stage_label": dashboard_stage_label(stage, fixture.get("group")),
                "match_id": fixture.get("match_id"),
                "team_a": team_a,
                "team_b": team_b,
                "prediction": prediction,
                "actual_score_a": fixture.get("actual_score_a"),
                "actual_score_b": fixture.get("actual_score_b"),
                "went_extra_time": bool(fixture.get("went_extra_time", False)),
                "went_penalties": bool(fixture.get("went_penalties", False)),
                "penalties_winner": fixture.get("penalties_winner"),
                "kickoff_utc": fixture.get("kickoff_utc"),
                "venue_name": fixture.get("venue_name"),
                "venue_country": fixture.get("venue_country"),
                "status_state": fixture.get("status_state"),
                "status_detail": fixture.get("status_detail"),
                "live_score_a": fixture.get("live_score_a"),
                "live_score_b": fixture.get("live_score_b"),
                "weather_summary": dashboard_weather_summary(fixture),
                "weather_stress": fixture.get("weather_stress"),
                "referee": fixture.get("referee"),
                "lineup_status_a": fixture.get("lineup_status_a"),
                "lineup_status_b": fixture.get("lineup_status_b"),
                "lineup_change_count_a": int(fixture.get("lineup_change_count_a", 0)),
                "lineup_change_count_b": int(fixture.get("lineup_change_count_b", 0)),
                "tactical_signature_a": tactical_signature_text(state_a),
                "tactical_signature_b": tactical_signature_text(state_b),
                "tactical_sample_matches_a": int(state_a.get("tactical_sample_matches", 0)),
                "tactical_sample_matches_b": int(state_b.get("tactical_sample_matches", 0)),
                "injuries_a": fixture.get("injuries_a"),
                "injuries_b": fixture.get("injuries_b"),
                "unavailable_count_a": int(fixture.get("unavailable_count_a", 0)),
                "unavailable_count_b": int(fixture.get("unavailable_count_b", 0)),
                "questionable_count_a": int(fixture.get("questionable_count_a", 0)),
                "questionable_count_b": int(fixture.get("questionable_count_b", 0)),
                "unavailable_notes_a": fixture.get("unavailable_notes_a", []),
                "unavailable_notes_b": fixture.get("unavailable_notes_b", []),
                "news_headlines": fixture.get("news_headlines", []),
                "news_notes_a": fixture.get("news_notes_a", []),
                "news_notes_b": fixture.get("news_notes_b", []),
                "live_feed_provider": fixture.get("live_feed_provider"),
                "live_feed_depth": fixture.get("live_feed_depth"),
                "provider_fixture_id": fixture.get("provider_fixture_id"),
                "live_shots_a": fixture.get("live_shots_a"),
                "live_shots_b": fixture.get("live_shots_b"),
                "live_shots_on_target_a": fixture.get("live_shots_on_target_a"),
                "live_shots_on_target_b": fixture.get("live_shots_on_target_b"),
                "live_shots_off_target_a": fixture.get("live_shots_off_target_a"),
                "live_shots_off_target_b": fixture.get("live_shots_off_target_b"),
                "live_blocked_shots_a": fixture.get("live_blocked_shots_a"),
                "live_blocked_shots_b": fixture.get("live_blocked_shots_b"),
                "live_shots_inside_box_a": fixture.get("live_shots_inside_box_a"),
                "live_shots_inside_box_b": fixture.get("live_shots_inside_box_b"),
                "live_shots_outside_box_a": fixture.get("live_shots_outside_box_a"),
                "live_shots_outside_box_b": fixture.get("live_shots_outside_box_b"),
                "live_big_chances_a": fixture.get("live_big_chances_a"),
                "live_big_chances_b": fixture.get("live_big_chances_b"),
                "live_shot_events_a": fixture.get("live_shot_events_a"),
                "live_shot_events_b": fixture.get("live_shot_events_b"),
                "live_shot_log_a": fixture.get("live_shot_log_a", []),
                "live_shot_log_b": fixture.get("live_shot_log_b", []),
                "live_possession_a": fixture.get("live_possession_a"),
                "live_possession_b": fixture.get("live_possession_b"),
                "live_corners_a": fixture.get("live_corners_a"),
                "live_corners_b": fixture.get("live_corners_b"),
                "live_red_cards_a": fixture.get("live_red_cards_a"),
                "live_red_cards_b": fixture.get("live_red_cards_b"),
                "live_xg_a": fixture.get("live_xg_a"),
                "live_xg_b": fixture.get("live_xg_b"),
                "live_xg_proxy_a": fixture.get("live_xg_proxy_a"),
                "live_xg_proxy_b": fixture.get("live_xg_proxy_b"),
                "market_provider": fixture.get("market_provider"),
                "market_summary": fixture.get("market_summary"),
                "market_prob_a": fixture.get("market_prob_a"),
                "market_prob_draw": fixture.get("market_prob_draw"),
                "market_prob_b": fixture.get("market_prob_b"),
                "projection": False,
            }
        )
    return entries


def load_bracket_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def dashboard_entry_key(entry: dict) -> str:
    match_id = entry.get("match_id")
    if match_id:
        return str(match_id)
    return str(entry.get("title", "partido"))


def load_previous_site_snapshot(
    current_fixtures_path: Path,
    current_bracket_json_path: Path,
    teams: Dict[str, Team],
    states: Dict[str, dict],
    top_scores: int,
) -> Tuple[List[dict], dict, Optional[str]]:
    site_dir = Path(__file__).with_name("site")
    previous_fixtures_path = site_dir / current_fixtures_path.name
    previous_bracket_json_path = site_dir / current_bracket_json_path.name
    previous_latest_path = site_dir / "latest.json"

    previous_entries: List[dict] = []
    previous_bracket_payload: dict = {}
    previous_updated_at: Optional[str] = None

    if previous_latest_path.exists():
        try:
            previous_updated_at = json.loads(previous_latest_path.read_text()).get("updated_at_utc")
        except Exception:
            previous_updated_at = None

    if previous_bracket_json_path.exists():
        previous_bracket_payload = load_bracket_json(previous_bracket_json_path)

    if previous_fixtures_path.exists():
        try:
            previous_fixtures = read_fixtures(previous_fixtures_path)
            previous_entries = dashboard_fixture_entries(previous_fixtures, teams, states, top_scores)
            previous_entries.extend(
                projected_bracket_entries(
                    previous_fixtures,
                    previous_bracket_payload,
                    teams,
                    states,
                    top_scores,
                    [entry["match_id"] for entry in previous_entries if entry.get("match_id")],
                )
            )
        except Exception:
            previous_entries = []

    return previous_entries, previous_bracket_payload, previous_updated_at


def compare_entry_predictions(current_entries: Sequence[dict], previous_entries: Sequence[dict]) -> dict:
    return calculate_compare_entry_predictions(
        current_entries,
        previous_entries,
        dashboard_entry_key=dashboard_entry_key,
        pick_summary=pick_summary,
        projected_score_value=projected_score_value,
    )


def compare_bracket_payloads(current_bracket: dict, previous_bracket: dict) -> dict:
    return calculate_compare_bracket_payloads(current_bracket, previous_bracket)


def build_recent_changes_markdown(
    current_entries: Sequence[dict],
    previous_entries: Sequence[dict],
    current_bracket: dict,
    previous_bracket: dict,
    previous_updated_at: Optional[str],
) -> List[str]:
    if not previous_entries and not previous_bracket:
        return ["_Todavia no hay una publicacion anterior comparable para mostrar cambios recientes._"]

    entry_changes = compare_entry_predictions(current_entries, previous_entries)
    bracket_changes = compare_bracket_payloads(current_bracket, previous_bracket)
    lines = []
    if previous_updated_at:
        lines.append(f"- Comparado contra la publicacion anterior de: {previous_updated_at}")
    lines.append(
        "- Esta seccion muestra solo movimientos reales frente a la version anterior ya publicada: picks que cambiaron, marcadores nuevos y cruces que entran o salen de la llave principal."
    )
    if bracket_changes["new_teams"]:
        lines.append("- Equipos que entran en la ruta principal de la llave: " + "; ".join(bracket_changes["new_teams"]))
    if bracket_changes["dropped_teams"]:
        lines.append("- Equipos que salen de la ruta principal de la llave: " + "; ".join(bracket_changes["dropped_teams"]))
    if bracket_changes["matchup_changes"]:
        lines.append(
            "- Cruces principales que cambiaron: "
            + "; ".join(
                f"{item['title']}: {item['previous_matchup']} -> {item['current_matchup']} ({format_pct(item['current_prob'])})"
                for item in bracket_changes["matchup_changes"]
            )
        )
    if bracket_changes["favorite_flips"]:
        lines.append(
            "- Cruces donde cambio el favorito de avance: "
            + "; ".join(
                f"{item['title']}: {item['matchup']} | antes {item['previous_winner']} -> ahora {item['current_winner']} ({format_pct(item['current_prob'])})"
                for item in bracket_changes["favorite_flips"]
            )
        )
    if entry_changes["movers"]:
        lines.append(
            "- Partidos donde mas se movio el pick principal: "
            + "; ".join(
                f"{item['title']}: {item['previous_label']} {format_pct(item['previous_prob'])} -> {item['current_label']} {format_pct(item['current_prob'])}"
                for item in entry_changes["movers"]
            )
        )
    if entry_changes["score_changes"]:
        lines.append(
            "- Partidos cuyo marcador proyectado cambio: "
            + "; ".join(
                f"{item['title']}: {item['previous_score']} -> {item['current_score']}"
                for item in entry_changes["score_changes"]
            )
        )
    if entry_changes["label_changes"]:
        lines.append(
            "- Partidos donde cambio el resultado mas probable: "
            + "; ".join(
                f"{item['title']}: {item['previous_label']} -> {item['current_label']}"
                for item in entry_changes["label_changes"]
            )
        )
    if len(lines) <= 2:
        lines.append("- Todavia no hay un cambio grande frente a la publicacion anterior.")
    return lines


def build_recent_changes_html(
    current_entries: Sequence[dict],
    previous_entries: Sequence[dict],
    current_bracket: dict,
    previous_bracket: dict,
    previous_updated_at: Optional[str],
) -> str:
    if not previous_entries and not previous_bracket:
        return (
            "<section class=\"panel changes-panel\">"
            "<div class=\"panel-head\"><div><p class=\"eyebrow\">Comparativo</p><h2>Que cambio desde la ultima actualizacion</h2>"
            "<p class=\"lede-tight\">Todavia no hay una publicacion anterior comparable para resumir movimientos del tablero.</p>"
            "</div></div></section>"
        )

    entry_changes = compare_entry_predictions(current_entries, previous_entries)
    bracket_changes = compare_bracket_payloads(current_bracket, previous_bracket)

    def text_list(items: Sequence[str]) -> str:
        return "".join(f"<li><strong>{html.escape(item)}</strong></li>" for item in items)

    def detailed_rows(rows: Sequence[dict], formatter) -> str:
        return "".join(
            f"<li><strong>{html.escape(formatter(row)[0])}</strong><span>{html.escape(formatter(row)[1])}</span></li>"
            for row in rows
        )

    matchup_html = (
        "<article><h3>Cruces principales que cambiaron</h3><ul>"
        + (
            detailed_rows(
                bracket_changes["matchup_changes"],
                lambda row: (
                    row["title"],
                    f"{row['previous_matchup']} -> {row['current_matchup']} | este cruce ahora aparece {format_pct(row['current_prob'])}",
                ),
            )
            if bracket_changes["matchup_changes"]
            else "<li><strong>Sin cambios grandes</strong><span>La ruta principal del cuadro se mantiene respecto de la version anterior.</span></li>"
        )
        + "</ul></article>"
    )
    teams_html = (
        "<article><h3>Equipos que entran o salen de la ruta principal</h3><ul>"
        + (
            text_list([f"Entran: {', '.join(bracket_changes['new_teams'])}"] if bracket_changes["new_teams"] else [])
            + text_list([f"Salen: {', '.join(bracket_changes['dropped_teams'])}"] if bracket_changes["dropped_teams"] else [])
            if bracket_changes["new_teams"] or bracket_changes["dropped_teams"]
            else "<li><strong>Sin entradas o salidas nuevas</strong><span>Los equipos visibles en la ruta principal no cambiaron frente a la publicacion anterior.</span></li>"
        )
        + "</ul></article>"
    )
    movers_html = (
        "<article><h3>Partidos donde mas se movio el pick</h3><ul>"
        + (
            detailed_rows(
                entry_changes["movers"],
                lambda row: (
                    row["title"],
                    f"{row['previous_label']} {format_pct(row['previous_prob'])} -> {row['current_label']} {format_pct(row['current_prob'])}",
                ),
            )
            if entry_changes["movers"]
            else "<li><strong>Sin cambios detectables</strong><span>Los picks principales siguen practicamente iguales que en la ultima publicacion.</span></li>"
        )
        + "</ul></article>"
    )
    score_html = (
        "<article><h3>Marcadores proyectados que cambiaron</h3><ul>"
        + (
            detailed_rows(
                entry_changes["score_changes"],
                lambda row: (row["title"], f"{row['previous_score']} -> {row['current_score']}"),
            )
            if entry_changes["score_changes"]
            else "<li><strong>Sin cambio de marcador principal</strong><span>El resultado entero mas probable sigue igual en los partidos comparables.</span></li>"
        )
        + "</ul></article>"
    )
    flip_html = (
        "<article><h3>Cruces donde cambio el favorito</h3><ul>"
        + (
            detailed_rows(
                bracket_changes["favorite_flips"],
                lambda row: (
                    row["title"],
                    f"{row['matchup']} | antes {row['previous_winner']} -> ahora {row['current_winner']} ({format_pct(row['current_prob'])})",
                ),
            )
            if bracket_changes["favorite_flips"]
            else "<li><strong>Sin giro de favorito</strong><span>En los cruces principales comparables no cambio el equipo con mas probabilidad de avanzar.</span></li>"
        )
        + "</ul></article>"
    )

    compared_html = ""
    if previous_updated_at:
        compared_html = f"<p class=\"meta\">Comparado contra la publicacion anterior de {html.escape(previous_updated_at)}.</p>"

    movers_chart_rows = [
        {
            "label": row["title"],
            "value": min(1.0, float(row["abs_delta"]) * 4.0),
            "value_text": format_pct(float(row["abs_delta"])),
            "detail": f"{row['previous_label']} {format_pct(row['previous_prob'])} -> {row['current_label']} {format_pct(row['current_prob'])}",
        }
        for row in entry_changes["movers"][:6]
    ]
    changes_chart_html = render_chart_grid(
        [
            render_rank_chart(
                "Mayores movimientos del pick principal",
                movers_chart_rows,
                tone="rose",
                description="Cuanto se movio el resultado principal frente a la publicacion anterior. El valor muestra el cambio absoluto de probabilidad, no la probabilidad final del partido.",
                empty_body="Todavia no hubo un movimiento material del pick principal frente a la version anterior.",
            )
        ]
    )

    return (
        "<section class=\"panel changes-panel\">"
        "<div class=\"panel-head\"><div><p class=\"eyebrow\">Comparativo</p><h2>Que cambio desde la ultima actualizacion</h2>"
        "<p class=\"lede-tight\">Este bloque resume solo movimientos reales respecto de la version anterior ya publicada, para que se note rapido si el tablero se movio poco o mucho.</p>"
        f"{compared_html}"
        "</div></div>"
        f"{changes_chart_html}"
        "<div class=\"confidence-grid\">"
        f"{teams_html}"
        f"{matchup_html}"
        f"{movers_html}"
        f"{score_html}"
        f"{flip_html}"
        "</div>"
        "</section>"
    )


def projected_bracket_entries(
    fixtures: Sequence[dict],
    bracket_payload: dict,
    teams: Dict[str, Team],
    states: Dict[str, dict],
    top_scores: int,
    seen_match_ids: Sequence[str],
) -> List[dict]:
    unresolved_fixtures = {
        str(fixture["match_id"]): fixture
        for fixture in fixtures
        if fixture.get("projection_only") and fixture.get("match_id")
    }
    entries = []
    seen = set(seen_match_ids)
    for match_id in bracket_match_order():
        if match_id in seen:
            continue
        match_projection = bracket_payload.get("matches", {}).get(match_id)
        if not match_projection:
            continue
        team_a = match_projection["team_a"]
        team_b = match_projection["team_b"]
        if team_a not in teams or team_b not in teams:
            continue
        base_fixture = dict(unresolved_fixtures.get(match_id, {}))
        base_fixture.update(
            {
                "team_a": team_a,
                "team_b": team_b,
                "stage": match_projection["stage"],
                "neutral": True,
                "match_id": match_id,
                "label": f"{match_projection['title']}: {team_a} vs {team_b}",
            }
        )
        state_a = normalize_team_state(states.get(team_a, {}))
        state_b = normalize_team_state(states.get(team_b, {}))
        ctx = context_from_fixture(base_fixture, teams, states)
        prediction = predict_match(
            teams,
            team_a,
            team_b,
            ctx,
            top_scores=top_scores,
            include_advancement=True,
            show_factors=True,
            state_a=state_a,
            state_b=state_b,
        )
        entries.append(
            {
                "title": base_fixture["label"],
                "stage_label": dashboard_stage_label(match_projection["stage"], None),
                "match_id": match_id,
                "team_a": team_a,
                "team_b": team_b,
                "prediction": prediction,
                "actual_score_a": None,
                "actual_score_b": None,
                "went_extra_time": False,
                "went_penalties": False,
                "penalties_winner": None,
                "kickoff_utc": base_fixture.get("kickoff_utc"),
                "venue_name": base_fixture.get("venue_name"),
                "venue_country": base_fixture.get("venue_country"),
                "status_state": base_fixture.get("status_state"),
                "status_detail": base_fixture.get("status_detail"),
                "live_score_a": base_fixture.get("live_score_a"),
                "live_score_b": base_fixture.get("live_score_b"),
                "weather_summary": dashboard_weather_summary(base_fixture),
                "weather_stress": base_fixture.get("weather_stress"),
                "projection": True,
                "projection_note": (
                    f"Cruce mas probable hoy: {team_a} vs {team_b} | "
                    f"probabilidad de que se de {format_pct(match_projection['matchup_prob'])} | "
                    f"favorito para avanzar si se juega hoy: {match_projection['winner']} {format_pct(match_projection['winner_prob'])}"
                ),
                "projection_alternatives": match_projection.get("top_scenarios", [])[1:],
                "projection_penalties": match_projection.get("penalties_prob", 0.0),
                "projection_extra_time": match_projection.get("extra_time_prob", 0.0),
                "tactical_signature_a": tactical_signature_text(state_a),
                "tactical_signature_b": tactical_signature_text(state_b),
                "tactical_sample_matches_a": int(state_a.get("tactical_sample_matches", 0)),
                "tactical_sample_matches_b": int(state_b.get("tactical_sample_matches", 0)),
                "injuries_a": base_fixture.get("injuries_a"),
                "injuries_b": base_fixture.get("injuries_b"),
                "unavailable_count_a": int(base_fixture.get("unavailable_count_a", 0)),
                "unavailable_count_b": int(base_fixture.get("unavailable_count_b", 0)),
                "questionable_count_a": int(base_fixture.get("questionable_count_a", 0)),
                "questionable_count_b": int(base_fixture.get("questionable_count_b", 0)),
                "unavailable_notes_a": base_fixture.get("unavailable_notes_a", []),
                "unavailable_notes_b": base_fixture.get("unavailable_notes_b", []),
                "news_headlines": base_fixture.get("news_headlines", []),
                "news_notes_a": base_fixture.get("news_notes_a", []),
                "news_notes_b": base_fixture.get("news_notes_b", []),
            }
        )
    return entries


def dashboard_status(entry: dict) -> Tuple[str, str]:
    if entry.get("actual_score_a") is not None and entry.get("actual_score_b") is not None:
        return ("final", "Final")
    if entry.get("live_score_a") is not None and entry.get("live_score_b") is not None:
        detail = entry.get("status_detail")
        return ("live", f"En vivo{f' | {detail}' if detail else ''}")
    if entry.get("projection"):
        return ("projection", "Proyeccion")
    detail = entry.get("status_detail")
    return ("pending", detail or "Pendiente")


def dashboard_absence_lines(entry: dict, team_a: str, team_b: str) -> List[str]:
    lines = []
    count_a = int(entry.get("unavailable_count_a", 0))
    count_b = int(entry.get("unavailable_count_b", 0))
    questionable_a = int(entry.get("questionable_count_a", 0))
    questionable_b = int(entry.get("questionable_count_b", 0))
    if count_a or count_b or questionable_a or questionable_b:
        lines.append(
            f"- Bajas/dudas: {team_a} {count_a} bajas, {questionable_a} dudas | "
            f"{team_b} {count_b} bajas, {questionable_b} dudas"
        )
    notes_a = entry.get("unavailable_notes_a") or []
    notes_b = entry.get("unavailable_notes_b") or []
    if notes_a:
        lines.append(f"- Detalle {team_a}: {'; '.join(notes_a[:3])}")
    if notes_b:
        lines.append(f"- Detalle {team_b}: {'; '.join(notes_b[:3])}")
    return lines


def dashboard_news_lines(entry: dict, team_a: str, team_b: str) -> List[str]:
    lines = []
    headlines = entry.get("news_headlines") or []
    notes_a = entry.get("news_notes_a") or []
    notes_b = entry.get("news_notes_b") or []
    if headlines:
        lines.append(f"- Noticias relevantes: {'; '.join(headlines[:3])}")
    if notes_a:
        lines.append(f"- Impacto noticioso {team_a}: {'; '.join(notes_a[:2])}")
    if notes_b:
        lines.append(f"- Impacto noticioso {team_b}: {'; '.join(notes_b[:2])}")
    return lines


def dashboard_tactical_signature_lines(entry: dict, team_a: str, team_b: str) -> List[str]:
    lines = []
    signature_a = str(entry.get("tactical_signature_a") or "sin muestra suficiente")
    signature_b = str(entry.get("tactical_signature_b") or "sin muestra suficiente")
    sample_a = int(entry.get("tactical_sample_matches_a", 0))
    sample_b = int(entry.get("tactical_sample_matches_b", 0))
    if sample_a > 0 or sample_b > 0:
        lines.append(
            f"- Estilo reciente: {team_a} {signature_a} ({sample_a} partidos) | {team_b} {signature_b} ({sample_b} partidos)"
        )
    return lines


def adjustment_reason_lines(entry: dict, prediction: MatchPrediction) -> List[str]:
    lines = []
    if int(entry.get("tactical_sample_matches_a", 0)) > 0 or int(entry.get("tactical_sample_matches_b", 0)) > 0:
        lines.append(
            f"- Cambio por el estilo reciente de cada equipo: {prediction.team_a} {entry.get('tactical_signature_a', 'sin muestra suficiente')} | "
            f"{prediction.team_b} {entry.get('tactical_signature_b', 'sin muestra suficiente')}."
        )
    if entry.get("status_state") == "in" and prediction.current_score_a is not None and prediction.current_score_b is not None:
        minute_text = f"{prediction.elapsed_minutes:.1f}" if prediction.elapsed_minutes is not None else "?"
        lines.append(
            f"- Cambio por el partido en vivo: marcador {prediction.team_a} {prediction.current_score_a} - {prediction.current_score_b} {prediction.team_b} en el minuto {minute_text}."
        )
    if int(entry.get("unavailable_count_a", 0)) or int(entry.get("unavailable_count_b", 0)):
        lines.append(
            f"- Cambio por bajas confirmadas: {prediction.team_a} {int(entry.get('unavailable_count_a', 0))} | {prediction.team_b} {int(entry.get('unavailable_count_b', 0))}."
        )
    if int(entry.get("questionable_count_a", 0)) or int(entry.get("questionable_count_b", 0)):
        lines.append(
            f"- Cambio por dudas fisicas: {prediction.team_a} {int(entry.get('questionable_count_a', 0))} | {prediction.team_b} {int(entry.get('questionable_count_b', 0))}."
        )
    if entry.get("lineup_status_a") == "confirmada" or entry.get("lineup_status_b") == "confirmada":
        lines.append(
            f"- Cambio por alineaciones: {prediction.team_a} {entry.get('lineup_status_a', 'sin confirmar')} | {prediction.team_b} {entry.get('lineup_status_b', 'sin confirmar')}."
        )
    if entry.get("lineup_change_count_a") or entry.get("lineup_change_count_b"):
        lines.append(
            f"- Cambio por cambios en el XI: {prediction.team_a} {entry.get('lineup_change_count_a', 0)} | {prediction.team_b} {entry.get('lineup_change_count_b', 0)}."
        )
    if entry.get("weather_stress") is not None and float(entry.get("weather_stress", 0.0)) >= 0.18:
        lines.append(f"- Cambio por clima exigente: estres climatico {float(entry.get('weather_stress', 0.0)):.2f}.")
    if entry.get("market_prob_a") is not None:
        lines.append("- Cambio por cuotas del mercado: se mezclan con la estimacion propia del modelo.")
    live_stats = extract_live_stats_payload(entry)
    if live_stats:
        shots_on_target_a = int(live_stats.get("shots_on_target_a", 0.0))
        shots_on_target_b = int(live_stats.get("shots_on_target_b", 0.0))
        xg_a = float(live_stats.get("xg_a", live_stats.get("xg_proxy_a", 0.0)))
        xg_b = float(live_stats.get("xg_b", live_stats.get("xg_proxy_b", 0.0)))
        red_a = int(live_stats.get("red_cards_a", 0.0))
        red_b = int(live_stats.get("red_cards_b", 0.0))
        if shots_on_target_a or shots_on_target_b or xg_a or xg_b:
            lines.append(
                f"- Cambio por lo que va pasando en la cancha: tiros al arco {prediction.team_a} {shots_on_target_a} | {prediction.team_b} {shots_on_target_b}; "
                f"calidad de ocasiones en vivo {prediction.team_a} {xg_a:.2f} | {prediction.team_b} {xg_b:.2f}."
            )
        if red_a or red_b:
            lines.append(
                f"- Cambio por expulsiones en vivo: rojas {prediction.team_a} {red_a} | {prediction.team_b} {red_b}."
            )
    patterns = infer_entry_patterns(entry, prediction) or {}
    side_a = patterns.get("a")
    side_b = patterns.get("b")
    if side_a and side_b:
        lines.append(
            f"- Cambio por patrones de juego: {prediction.team_a} muestra {side_a.get('summary', 'sin patron claro')}; "
            f"{prediction.team_b} muestra {side_b.get('summary', 'sin patron claro')}."
        )
        if patterns.get("tempo_label"):
            lines.append(f"- Ritmo detectado del partido: {patterns['tempo_label']}.")
    if entry.get("news_headlines"):
        lines.append("- Cambio por noticias relevantes detectadas en el feed del partido.")
    drivers = top_factor_drivers(prediction.factors, limit=2)
    if drivers:
        lines.append(
            "- Factores que mas pesan ahora: "
            + "; ".join(f"{label} {value:+.3f}" for label, value in drivers)
        )
    return lines


def goals_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Goles esperados al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Goles esperados al final de la prorroga"
    if prediction.live_phase == "penalties":
        return "Marcador actual"
    return "Goles esperados"


def projected_score_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Marcador proyectado al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Marcador proyectado al final de la prorroga"
    if prediction.live_phase == "penalties":
        return "Marcador actual"
    return "Marcador proyectado"


def projected_score_value(prediction: MatchPrediction) -> str:
    if prediction.exact_scores:
        return prediction.exact_scores[0][0]
    return f"{int(round(prediction.expected_goals_a))}-{int(round(prediction.expected_goals_b))}"


def average_goals_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Promedio estimado de goles al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Promedio estimado de goles al final de la prorroga"
    if prediction.live_phase == "penalties":
        return "Marcador actual"
    return "Promedio estimado de goles del modelo"


def result_prob_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Probabilidades de resultado al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Probabilidades de resultado al final de la prorroga"
    if prediction.live_phase == "penalties":
        return "Probabilidades de clasificar en penales"
    return "Probabilidades de resultado (90')"


def top_result_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Desenlace mas probable al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Desenlace mas probable al final de la prorroga"
    if prediction.live_phase == "penalties":
        return "Equipo con mayor probabilidad de clasificar en penales"
    return "Desenlace mas probable en 90 minutos"


def top_result_summary(prediction: MatchPrediction) -> str:
    outcomes = [
        (prediction.win_a, f"Gana {prediction.team_a}"),
        (prediction.draw, "Empate"),
        (prediction.win_b, f"Gana {prediction.team_b}"),
    ]
    best_prob, best_label = max(outcomes, key=lambda item: item[0])
    return f"{best_label} {format_pct(best_prob)}"


def build_dashboard_markdown(
    entries: Sequence[dict],
    bracket_text: str,
    bracket_payload: dict,
    backtest: dict,
    state_path: Path,
    fixtures_path: Path,
    previous_entries: Optional[Sequence[dict]] = None,
    previous_bracket_payload: Optional[dict] = None,
    previous_updated_at: Optional[str] = None,
) -> str:
    lines = [
        "# Reporte actual del Mundial 2026",
        "",
        f"Actualizado: {iso_timestamp()}",
        f"Estado usado: {state_path}",
        f"Fixtures leidos: {fixtures_path}",
        "",
        "## Resumen rapido del torneo",
        "",
    ]
    lines.extend(build_global_confidence_markdown(entries))
    lines.extend(["", "## Que cambio desde la ultima actualizacion", ""])
    lines.extend(
        build_recent_changes_markdown(
            entries,
            previous_entries or [],
            bracket_payload,
            previous_bracket_payload or {},
            previous_updated_at,
        )
    )
    lines.extend(["", "## Como viene acertando el modelo", ""])
    lines.extend(build_backtesting_markdown(backtest))
    lines.extend([
        "",
        "## Llave actual",
        "",
    ])
    if bracket_text.strip():
        lines.append(bracket_text.strip())
    else:
        lines.append("_No hay llave generada todavia._")
    lines.extend(["", "## Partidos cargados", ""])

    if not entries:
        lines.append("_No hay partidos en fixtures_template.json._")
        return "\n".join(lines)

    for entry in entries:
        prediction: MatchPrediction = entry["prediction"]
        lines.append(f"### {entry['title']}")
        lines.append(f"- Etapa: {entry['stage_label']}")
        _, status_text = dashboard_status(entry)
        lines.append(f"- Estado: {status_text}")
        if prediction.elapsed_minutes is not None:
            lines.append(f"- Minuto modelado: {prediction.elapsed_minutes:.1f}")
        if entry.get("kickoff_utc"):
            venue_bits = [entry.get("venue_name"), entry.get("venue_country")]
            venue_bits = [bit for bit in venue_bits if bit]
            lines.append(f"- Sede: {' | '.join(venue_bits)}")
            lines.append(f"- Hora UTC: {entry['kickoff_utc']}")
        if entry.get("weather_summary"):
            lines.append(f"- Clima estimado: {entry['weather_summary']}")
        if entry.get("referee"):
            lines.append(f"- Arbitro: {entry['referee']}")
        if entry.get("market_summary"):
            provider = entry.get("market_provider") or "mercado"
            lines.append(f"- Odds {provider}: {entry['market_summary']}")
        if entry.get("market_prob_a") is not None:
            lines.append(
                f"- Referencia de cuotas (victoria/empate/derrota): {prediction.team_a} {format_pct(float(entry['market_prob_a']))} | "
                f"empate {format_pct(float(entry.get('market_prob_draw', 0.0)))} | "
                f"{prediction.team_b} {format_pct(float(entry.get('market_prob_b', 0.0)))}"
            )
        if entry.get("lineup_status_a") or entry.get("lineup_status_b"):
            lines.append(
                f"- Alineaciones: {prediction.team_a} {entry.get('lineup_status_a', 'sin confirmar')} | "
                f"{prediction.team_b} {entry.get('lineup_status_b', 'sin confirmar')}"
            )
        if entry.get("lineup_change_count_a") or entry.get("lineup_change_count_b"):
            lines.append(
                f"- Cambios de alineacion: {prediction.team_a} {entry.get('lineup_change_count_a', 0)} | "
                f"{prediction.team_b} {entry.get('lineup_change_count_b', 0)}"
            )
        lines.extend(dashboard_absence_lines(entry, prediction.team_a, prediction.team_b))
        lines.extend(dashboard_news_lines(entry, prediction.team_a, prediction.team_b))
        lines.extend(dashboard_tactical_signature_lines(entry, prediction.team_a, prediction.team_b))
        lines.extend(dashboard_live_stats_lines(entry, prediction.team_a, prediction.team_b))
        lines.extend(dashboard_shot_timeline_lines(entry, prediction.team_a, prediction.team_b))
        lines.extend(dashboard_pattern_lines(entry, prediction))
        lines.extend(adjustment_reason_lines(entry, prediction))
        next_round_note = next_round_projection_note(entry, prediction, bracket_payload)
        if next_round_note:
            lines.append(f"- Siguiente cruce del ganador real: {next_round_note}")
        if entry.get("projection"):
            lines.append(f"- Proyeccion automatica: {entry.get('projection_note', '')}")
            alternatives = entry.get("projection_alternatives") or []
            if alternatives:
                lines.append(
                    "- Otras opciones de cruce: "
                    + "; ".join(
                        f"{scenario['team_a']} vs {scenario['team_b']} -> {scenario['winner']} {format_pct(float(scenario['prob']))}"
                        for scenario in alternatives
                    )
                )
        if entry["actual_score_a"] is not None and entry["actual_score_b"] is not None:
            result_line = f"- Resultado real: {prediction.team_a} {entry['actual_score_a']} - {entry['actual_score_b']} {prediction.team_b}"
            if entry["went_penalties"]:
                result_line += f" | penales: {entry['penalties_winner']}"
            elif entry["went_extra_time"]:
                result_line += " | con proroga"
            lines.append(result_line)
        elif entry.get("live_score_a") is not None and entry.get("live_score_b") is not None:
            lines.append(
                f"- Marcador en vivo: {prediction.team_a} {entry['live_score_a']} - {entry['live_score_b']} {prediction.team_b}"
            )
        else:
            pass
        lines.append(f"- {projected_score_label(prediction)}: {projected_score_value(prediction)}")
        if prediction.live_phase != "penalties":
            lines.append(
                f"- {average_goals_label(prediction)}: {prediction.team_a} {prediction.expected_goals_a:.2f} | "
                f"{prediction.team_b} {prediction.expected_goals_b:.2f}"
            )
        if prediction.expected_remaining_goals_a is not None and prediction.expected_remaining_goals_b is not None:
            lines.append(
                f"- Promedio estimado de goles restantes: {prediction.team_a} {prediction.expected_remaining_goals_a:.2f} | "
                f"{prediction.team_b} {prediction.expected_remaining_goals_b:.2f}"
            )
        lines.append(
            f"- {result_prob_label(prediction)}: {format_pct(prediction.win_a)} / {format_pct(prediction.draw)} / {format_pct(prediction.win_b)}"
        )
        lines.extend(statistical_depth_lines(prediction))
        lines.extend(model_comparison_lines(prediction))
        if prediction.advance_a is not None and prediction.advance_b is not None:
            detail = prediction.knockout_detail or {}
            lines.append(
                f"- Quien tiene mas probabilidad de avanzar: {prediction.team_a} {format_pct(prediction.advance_a)} | {prediction.team_b} {format_pct(prediction.advance_b)}"
            )
            lines.append(
                f"- Si empatan tras 90': gana en prorroga {prediction.team_a} {format_pct(detail.get('et_win_a', 0.0))} | "
                f"siguen empatados {format_pct(detail.get('et_draw', 0.0))} | {prediction.team_b} {format_pct(detail.get('et_win_b', 0.0))}"
            )
            lines.append(
                f"- Si llegan a penales: {prediction.team_a} {format_pct(detail.get('penalties_a', 0.0))} | "
                f"{prediction.team_b} {format_pct(detail.get('penalties_b', 0.0))}"
            )
            if prediction.penalty_shootout:
                shootout = prediction.penalty_shootout
                projected_shootout = (shootout.get("top_scores") or [("5-4", 0.0)])[0][0]
                lines.append(
                    f"- Marcador mas probable de la tanda: {projected_shootout}"
                )
                lines.append(
                    f"- Marcador medio esperado en la tanda: {prediction.team_a} {shootout.get('avg_score_a', 0.0):.2f} | "
                    f"{prediction.team_b} {shootout.get('avg_score_b', 0.0):.2f}"
                )
                lines.append(
                    "- Marcadores de tanda mas probables: "
                    + ", ".join(
                        f"{score} {format_pct(prob)}" for score, prob in shootout.get("top_scores", [])
                    )
                )
        score_line = ", ".join(f"{score} {format_pct(prob)}" for score, prob in prediction.exact_scores)
        lines.append(f"- Marcadores mas probables: {score_line}")
        lines.append("")

    return "\n".join(lines)


def probability_rows(prediction: MatchPrediction) -> List[Tuple[str, float, str]]:
    return [
        (f"Victoria {prediction.team_a}", prediction.win_a, "a"),
        ("Empate", prediction.draw, "draw"),
        (f"Victoria {prediction.team_b}", prediction.win_b, "b"),
    ]


def pick_summary(prediction: MatchPrediction) -> Tuple[str, float]:
    options = [
        (f"Victoria {prediction.team_a}", prediction.win_a),
        ("Empate", prediction.draw),
        (f"Victoria {prediction.team_b}", prediction.win_b),
    ]
    return max(options, key=lambda item: item[1])


def confidence_tier(confidence: float) -> str:
    if confidence >= 0.90:
        return "Pick muy fuerte"
    if confidence >= 0.75:
        return "Pick fuerte"
    if confidence >= 0.60:
        return "Pick utilizable"
    return "Pronóstico parejo: sin favorito estadístico claro"


def statistical_depth_lines(prediction: MatchPrediction) -> List[str]:
    depth = prediction.statistical_depth or {}
    lines = []
    if not depth:
        return lines
    confidence = float(depth.get("confidence_index", 0.0))
    pick_label, pick_prob = pick_summary(prediction)
    both_score = float(depth.get("both_teams_score", 0.0))
    over_2_5 = float(depth.get("over_2_5", 0.0))
    top3_coverage = float(depth.get("top3_coverage", 0.0))
    clean_sheet_a = float(depth.get("clean_sheet_a", 0.0))
    clean_sheet_b = float(depth.get("clean_sheet_b", 0.0))
    market_gap = depth.get("market_gap")
    model_agreement = depth.get("model_agreement")
    modal_margin = int(depth.get("modal_margin", 0))
    modal_margin_prob = float(depth.get("modal_margin_prob", 0.0))

    lines.append(
        f"- Lectura estadistica: {confidence_tier(confidence)} | pick actual {pick_label} {format_pct(pick_prob)} | confianza {format_pct(confidence)}"
    )
    lines.append(
        f"- Escenario de goles: ambos marcan {format_pct(both_score)} | mas de 2.5 goles {format_pct(over_2_5)}"
    )
    lines.append(
        f"- Probabilidad de que no reciba goles: {prediction.team_a} {format_pct(clean_sheet_a)} | {prediction.team_b} {format_pct(clean_sheet_b)}"
    )
    lines.append(
        f"- Cuanta probabilidad cubren los 3 marcadores mas probables: {format_pct(top3_coverage)} | ventaja final mas probable {modal_margin:+d} ({format_pct(modal_margin_prob)})"
    )
    if model_agreement is not None:
        lines.append(f"- Que tanto coinciden los modelos entre si: {format_pct(float(model_agreement))}")
    if market_gap is not None:
        lines.append(f"- Diferencia frente a las cuotas de mercado: {format_pct(float(market_gap))}")
    stack_names = [name for name in depth.get("model_stack_names", []) if name]
    if stack_names:
        lines.append(f"- Stack estadistico usado: {' + '.join(stack_names)}")
    drivers = top_factor_drivers(prediction.factors, limit=3)
    if drivers:
        lines.append(
            "- Factores dominantes: "
            + "; ".join(f"{label} {value:+.3f}" for label, value in drivers)
        )
    return lines


def statistical_depth_html(prediction: MatchPrediction) -> str:
    depth = prediction.statistical_depth or {}
    if not depth:
        return ""
    confidence = float(depth.get("confidence_index", 0.0))
    pick_label, pick_prob = pick_summary(prediction)
    market_gap = depth.get("market_gap")
    model_agreement = depth.get("model_agreement")
    market_html = ""
    if market_gap is not None:
        market_html = (
            f"<div><span>Diferencia vs mercado</span><strong>{format_pct(float(market_gap))}</strong></div>"
        )
    agreement_html = ""
    if model_agreement is not None:
        agreement_html = f"<div><span>Coincidencia entre modelos</span><strong>{format_pct(float(model_agreement))}</strong></div>"
    drivers = top_factor_drivers(prediction.factors, limit=3)
    drivers_html = ""
    if drivers:
        drivers_html = (
            "<p class=\"meta\"><strong>Factores dominantes:</strong> "
            + html.escape("; ".join(f"{label} {value:+.3f}" for label, value in drivers))
            + "</p>"
        )
    stack_names = [name for name in depth.get("model_stack_names", []) if name]
    stack_html = ""
    if stack_names:
        stack_html = (
            "<p class=\"meta\"><strong>Stack estadistico:</strong> "
            + html.escape(" + ".join(stack_names))
            + "</p>"
        )
    return (
        "<div class=\"depth-block\">"
        "<h4>Profundidad estadística</h4>"
        f"<p class=\"meta\"><strong>{html.escape(confidence_tier(confidence))}</strong> | pick actual: {html.escape(pick_label)} {format_pct(pick_prob)}</p>"
        "<div class=\"depth-grid\">"
        f"<div><span>Confianza del pronóstico</span><strong>{format_pct(confidence)}</strong></div>"
        f"<div><span>Ambos marcan</span><strong>{format_pct(float(depth.get('both_teams_score', 0.0)))}</strong></div>"
        f"<div><span>Mas de 2.5 goles</span><strong>{format_pct(float(depth.get('over_2_5', 0.0)))}</strong></div>"
        f"<div><span>Probabilidad cubierta por los 3 marcadores mas probables</span><strong>{format_pct(float(depth.get('top3_coverage', 0.0)))}</strong></div>"
        f"<div><span>Prob. de que {html.escape(prediction.team_a)} no reciba goles</span><strong>{format_pct(float(depth.get('clean_sheet_a', 0.0)))}</strong></div>"
        f"<div><span>Prob. de que {html.escape(prediction.team_b)} no reciba goles</span><strong>{format_pct(float(depth.get('clean_sheet_b', 0.0)))}</strong></div>"
        f"<div><span>Ventaja final mas probable</span><strong>{int(depth.get('modal_margin', 0)):+d}</strong></div>"
        f"<div><span>Probabilidad de esa ventaja</span><strong>{format_pct(float(depth.get('modal_margin_prob', 0.0)))}</strong></div>"
        f"{agreement_html}"
        f"{market_html}"
        "</div>"
        f"{stack_html}"
        f"{drivers_html}"
        "</div>"
    )


def model_comparison_lines(prediction: MatchPrediction) -> List[str]:
    stack = prediction.model_stack or {}
    if not stack:
        return []

    def row(name_key: str, probs_key: str, score_key: str) -> str:
        name = str(stack.get(name_key, "Modelo"))
        probs = stack.get(probs_key, {}) or {}
        top_score, top_score_prob = stack.get(score_key, ("0-0", 0.0))
        weight_key = "primary" if name_key == "primary_name" else "contrast" if name_key == "contrast_name" else "low_score" if name_key == "low_score_name" else None
        weight_label = ""
        if weight_key and stack.get("weights", {}).get(weight_key) is not None:
            weight_label = f" | peso actual {format_pct(float(stack['weights'][weight_key]))}"
        return (
            f"- {name}: victoria {prediction.team_a} {format_pct(float(probs.get('a', 0.0)))} | "
            f"empate {format_pct(float(probs.get('draw', 0.0)))} | "
            f"victoria {prediction.team_b} {format_pct(float(probs.get('b', 0.0)))} | "
            f"marcador mas probable {top_score} ({format_pct(float(top_score_prob))}){weight_label}"
        )

    lines = ["- Comparativa entre modelos:"]
    lines.append(row("primary_name", "primary_probs", "primary_top_score"))
    lines.append(row("contrast_name", "contrast_probs", "contrast_top_score"))
    lines.append(row("low_score_name", "low_score_probs", "low_score_top_score"))
    lines.append(row("final_name", "ensemble_probs", "ensemble_top_score"))
    return lines


def model_comparison_html(prediction: MatchPrediction) -> str:
    stack = prediction.model_stack or {}
    if not stack:
        return ""

    def card(name_key: str, probs_key: str, score_key: str, tone: str) -> str:
        name = str(stack.get(name_key, "Modelo"))
        probs = stack.get(probs_key, {}) or {}
        top_score, top_score_prob = stack.get(score_key, ("0-0", 0.0))
        weight_key = "primary" if name_key == "primary_name" else "contrast" if name_key == "contrast_name" else "low_score" if name_key == "low_score_name" else None
        weight_html = ""
        if weight_key and stack.get("weights", {}).get(weight_key) is not None:
            weight_html = f"<p><strong>Peso actual:</strong> {format_pct(float(stack['weights'][weight_key]))}</p>"
        return (
            f"<article class=\"model-card {tone}\">"
            f"<h5>{html.escape(name)}</h5>"
            f"<p>Victoria {html.escape(prediction.team_a)} {format_pct(float(probs.get('a', 0.0)))}</p>"
            f"<p>Empate {format_pct(float(probs.get('draw', 0.0)))}</p>"
            f"<p>Victoria {html.escape(prediction.team_b)} {format_pct(float(probs.get('b', 0.0)))}</p>"
            f"<p><strong>Marcador mas probable:</strong> {html.escape(str(top_score))} ({format_pct(float(top_score_prob))})</p>"
            f"{weight_html}"
            "</article>"
        )

    return (
        "<div class=\"reason-block model-compare-block\">"
        "<h4>Que dice cada modelo</h4>"
        "<p class=\"meta\">Aqui se ven por separado el modelo principal, el contraste y el ajuste de baja anotacion. El ensamble final repondera esos modelos segun consenso y cercania al mercado cuando hay cuotas confiables.</p>"
        "<div class=\"model-compare-grid\">"
        f"{card('primary_name', 'primary_probs', 'primary_top_score', 'primary')}"
        f"{card('contrast_name', 'contrast_probs', 'contrast_top_score', 'contrast')}"
        f"{card('low_score_name', 'low_score_probs', 'low_score_top_score', 'low-score')}"
        f"{card('final_name', 'ensemble_probs', 'ensemble_top_score', 'ensemble')}"
        "</div>"
        "</div>"
    )


def build_global_confidence_markdown(entries: Sequence[dict]) -> List[str]:
    if not entries:
        return ["_Sin partidos cargados para armar el resumen rapido del torneo._"]

    ranked = []
    ranked_market = []
    live_matches = 0
    for entry in entries:
        prediction: MatchPrediction = entry["prediction"]
        depth = prediction.statistical_depth or {}
        confidence = float(depth.get("confidence_index", 0.0))
        top3 = float(depth.get("top3_coverage", 0.0))
        ranked.append((confidence, top3, entry))
        market_gap = depth.get("market_gap")
        if market_gap is not None:
            ranked_market.append((abs(float(market_gap)), entry))
        if entry.get("status_state") == "in":
            live_matches += 1

    avg_confidence = sum(item[0] for item in ranked) / len(ranked)
    avg_top3 = sum(item[1] for item in ranked) / len(ranked)
    strongest = sorted(ranked, key=lambda item: item[0], reverse=True)[:3]
    most_open = sorted(ranked, key=lambda item: item[0])[:3]
    market_edges = sorted(ranked_market, key=lambda item: item[0], reverse=True)[:3]

    lines = [
        "- Que significa esta seccion: resume si hoy el torneo se ve mas claro o mas incierto. No es una nota del modelo; es una foto de que tan firmes o parejos salen los partidos publicados.",
        f"- Que tan claro sale, en promedio, el pick principal: {format_pct(avg_confidence)}",
        f"- Cuanta probabilidad concentran, en promedio, los 3 marcadores mas probables: {format_pct(avg_top3)}",
        f"- Partidos en vivo ahora mismo: {live_matches}",
        "- Como validar la actualizacion en vivo: revisa la hora de publicacion de la portada, el badge 'En vivo', el minuto modelado y el archivo latest.json del sitio.",
    ]
    if strongest:
        lines.append(
            "- Partidos con favorito mas claro: "
            + "; ".join(f"{item[2]['title']} {format_pct(item[0])}" for item in strongest)
        )
    if most_open:
        lines.append(
            "- Partidos mas cerrados o parejos: "
            + "; ".join(f"{item[2]['title']} {format_pct(item[0])}" for item in most_open)
        )
    group_metrics = {}
    for confidence, _, entry in ranked:
        stage_label = str(entry.get("stage_label", ""))
        if not stage_label.startswith("Grupo "):
            continue
        prediction: MatchPrediction = entry["prediction"]
        bucket = group_metrics.setdefault(
            stage_label,
            {"matches": 0, "confidence_sum": 0.0, "draw_sum": 0.0},
        )
        bucket["matches"] += 1
        bucket["confidence_sum"] += confidence
        bucket["draw_sum"] += float(prediction.draw)
    if group_metrics:
        group_rows = []
        for group_label, stats in group_metrics.items():
            avg_conf = stats["confidence_sum"] / max(stats["matches"], 1)
            avg_draw = stats["draw_sum"] / max(stats["matches"], 1)
            balance = (1.0 - avg_conf) * 0.65 + avg_draw * 0.35
            group_rows.append((group_label, avg_conf, avg_draw, balance, int(stats["matches"])))
        balanced_groups = sorted(group_rows, key=lambda row: (row[3], row[2]), reverse=True)
        favorite_groups = sorted(group_rows, key=lambda row: (row[1], -row[2]), reverse=True)
        lines.append(
            "- Grupos mas parejos hasta ahora: "
            + "; ".join(
                f"{label} | equilibrio {format_pct(balance)} | empate medio {format_pct(avg_draw)} | partidos {matches}"
                for label, avg_conf, avg_draw, balance, matches in balanced_groups
            )
        )
        lines.append(
            "- Grupos con favoritos mas claros hasta ahora: "
            + "; ".join(
                f"{label} | certeza media {format_pct(avg_conf)} | empate medio {format_pct(avg_draw)} | partidos {matches}"
                for label, avg_conf, avg_draw, balance, matches in favorite_groups
            )
        )
    if market_edges:
        lines.append(
            "- Partidos donde mas se separan modelo y cuotas: "
            + "; ".join(f"{item[1]['title']} {format_pct(item[0])}" for item in market_edges)
        )
    return lines


def build_global_confidence_html(entries: Sequence[dict]) -> str:
    if not entries:
        return ""

    ranked = []
    ranked_market = []
    live_matches = 0
    for entry in entries:
        prediction: MatchPrediction = entry["prediction"]
        depth = prediction.statistical_depth or {}
        confidence = float(depth.get("confidence_index", 0.0))
        top3 = float(depth.get("top3_coverage", 0.0))
        ranked.append((confidence, top3, entry))
        market_gap = depth.get("market_gap")
        if market_gap is not None:
            ranked_market.append((abs(float(market_gap)), entry))
        if entry.get("status_state") == "in":
            live_matches += 1

    avg_confidence = sum(item[0] for item in ranked) / len(ranked)
    avg_top3 = sum(item[1] for item in ranked) / len(ranked)
    strongest = sorted(ranked, key=lambda item: item[0], reverse=True)[:4]
    most_open = sorted(ranked, key=lambda item: item[0])[:4]
    market_edges = sorted(ranked_market, key=lambda item: item[0], reverse=True)[:4]
    group_metrics = {}
    for confidence, _, entry in ranked:
        stage_label = str(entry.get("stage_label", ""))
        if not stage_label.startswith("Grupo "):
            continue
        prediction: MatchPrediction = entry["prediction"]
        bucket = group_metrics.setdefault(
            stage_label,
            {"matches": 0, "confidence_sum": 0.0, "draw_sum": 0.0},
        )
        bucket["matches"] += 1
        bucket["confidence_sum"] += confidence
        bucket["draw_sum"] += float(prediction.draw)

    def favorite_summary(entry: dict) -> Tuple[str, float]:
        prediction: MatchPrediction = entry["prediction"]
        favorite = max(
            (
                (prediction.win_a, f"Victoria {prediction.team_a}"),
                (prediction.draw, "Empate"),
                (prediction.win_b, f"Victoria {prediction.team_b}"),
            ),
            key=lambda item: item[0],
        )
        return favorite[1], float(favorite[0])

    def bullet_list(items: Sequence[Tuple[float, float, dict]], mode: str) -> str:
        rows = []
        for confidence, _, entry in items:
            prediction: MatchPrediction = entry["prediction"]
            favorite_label, favorite_prob = favorite_summary(entry)
            tail = (
                f"Certeza del pick {format_pct(confidence)} | resultado mas probable {favorite_label} {format_pct(favorite_prob)}"
                if mode == "firm"
                else f"Certeza del pick {format_pct(confidence)} | empate {format_pct(prediction.draw)}"
            )
            rows.append(
                "<li>"
                f"<strong>{html.escape(entry['title'])}</strong>"
                f"<span>{html.escape(tail)}</span>"
                "</li>"
            )
        return "".join(rows)

    def market_list(items: Sequence[Tuple[float, dict]]) -> str:
        rows = []
        for gap, entry in items:
            rows.append(
                "<li>"
                f"<strong>{html.escape(entry['title'])}</strong>"
                f"<span>Diferencia media vs mercado {format_pct(gap)}</span>"
                "</li>"
            )
        return "".join(rows)

    def group_list(items: Sequence[Tuple[str, float, float, float, int]], mode: str) -> str:
        rows = []
        for group_label, avg_conf, avg_draw, balance, matches in items:
            if mode == "balanced":
                tail = f"Equilibrio {format_pct(balance)} | empate medio {format_pct(avg_draw)} | partidos {matches}"
            else:
                tail = f"Certeza media {format_pct(avg_conf)} | empate medio {format_pct(avg_draw)} | partidos {matches}"
            rows.append(
                "<li>"
                f"<strong>{html.escape(group_label)}</strong>"
                f"<span>{html.escape(tail)}</span>"
                "</li>"
            )
        return "".join(rows)

    group_closed_html = ""
    group_open_html = ""
    group_rows: List[Tuple[str, float, float, float, int]] = []
    if group_metrics:
        for group_label, stats in group_metrics.items():
            avg_conf = stats["confidence_sum"] / max(stats["matches"], 1)
            avg_draw = stats["draw_sum"] / max(stats["matches"], 1)
            balance = (1.0 - avg_conf) * 0.65 + avg_draw * 0.35
            group_rows.append((group_label, avg_conf, avg_draw, balance, int(stats["matches"])))
        balanced_groups = sorted(group_rows, key=lambda row: (row[3], row[2]), reverse=True)
        favorite_groups = sorted(group_rows, key=lambda row: (row[1], -row[2]), reverse=True)
        group_closed_html = (
            "<article><h3>Grupos mas parejos</h3><ul>"
            f"{group_list(balanced_groups, 'balanced')}"
            "</ul></article>"
        )
        group_open_html = (
            "<article><h3>Grupos con favoritos mas claros</h3><ul>"
            f"{group_list(favorite_groups, 'favorite')}"
            "</ul></article>"
        )

    strongest_chart_rows = []
    for confidence, _, entry in strongest:
        favorite_label, favorite_prob = favorite_summary(entry)
        strongest_chart_rows.append(
            {
                "label": entry["title"],
                "value": confidence,
                "value_text": format_pct(confidence),
                "detail": f"{favorite_label} {format_pct(favorite_prob)}",
            }
        )

    most_open_chart_rows = []
    for confidence, _, entry in most_open:
        prediction: MatchPrediction = entry["prediction"]
        favorite_label, favorite_prob = favorite_summary(entry)
        parity = max(0.0, min(1.0, (1.0 - confidence) * 0.72 + float(prediction.draw) * 0.28))
        most_open_chart_rows.append(
            {
                "label": entry["title"],
                "value": parity,
                "value_text": format_pct(parity),
                "detail": f"Pick mas fuerte {favorite_label} {format_pct(favorite_prob)} | empate {format_pct(prediction.draw)}",
            }
        )

    balanced_chart_rows = []
    favorite_group_chart_rows = []
    if group_rows:
        balanced_groups = sorted(group_rows, key=lambda row: (row[3], row[2]), reverse=True)
        favorite_groups = sorted(group_rows, key=lambda row: (row[1], -row[2]), reverse=True)
        for group_label, avg_conf, avg_draw, balance, matches in balanced_groups[:4]:
            balanced_chart_rows.append(
                {
                    "label": group_label,
                    "value": balance,
                    "value_text": format_pct(balance),
                    "detail": f"Empate medio {format_pct(avg_draw)} | partidos cargados {matches}",
                }
            )
        for group_label, avg_conf, avg_draw, balance, matches in favorite_groups[:4]:
            favorite_group_chart_rows.append(
                {
                    "label": group_label,
                    "value": avg_conf,
                    "value_text": format_pct(avg_conf),
                    "detail": f"Empate medio {format_pct(avg_draw)} | partidos cargados {matches}",
                }
            )

    charts_html = render_chart_grid(
        [
            render_rank_chart(
                "Donde el favorito se ve mas fuerte",
                strongest_chart_rows,
                tone="accent",
                description="Lectura rapida de los cruces donde hoy el modelo ve mas diferencia entre el pick principal y el resto.",
                empty_body="Todavia no hay partidos comparables con ventaja clara.",
            ),
            render_rank_chart(
                "Donde el partido se ve mas parejo",
                most_open_chart_rows,
                tone="slate",
                description="No es lo mismo que empate seguro. Aqui sube cuando el duelo se ve abierto y ningun desenlace domina con claridad.",
                empty_body="Todavia no hay partidos comparables lo bastante parejos para dibujar esta lectura.",
            ),
            render_rank_chart(
                "Grupos mas parejos",
                balanced_chart_rows,
                tone="gold",
                description="Resumen por grupo usando equilibrio medio, probabilidad de empate y los partidos que ya estan cargados.",
                empty_body="Todavia no hay suficientes partidos de grupos para construir este grafico.",
            ),
            render_rank_chart(
                "Grupos con favoritos mas claros",
                favorite_group_chart_rows,
                tone="rose",
                description="Estos grupos muestran la mayor ventaja media del pick principal en los partidos publicados hasta ahora.",
                empty_body="Todavia no hay suficiente informacion de grupos para dibujar esta lectura.",
            ),
        ]
    )

    return (
        "<section class=\"panel confidence-panel\">"
        "<div class=\"panel-head\">"
        "<div>"
        "<p class=\"eyebrow\">Lectura global</p>"
        "<h2>Resumen rapido del torneo</h2>"
        "<p class=\"lede-tight\">Este bloque te deja ver rapido donde hay favoritos mas claros, donde los cruces se ven mas parejos y en que partidos el modelo se aleja mas de las cuotas. No es una nota del modelo; es una foto del tablero de hoy.</p>"
        "</div>"
        "</div>"
        "<div class=\"confidence-tiles\">"
        f"<div class=\"summary-tile\"><span>Claridad media del pick principal</span><strong>{format_pct(avg_confidence)}</strong></div>"
        f"<div class=\"summary-tile\"><span>Probabilidad media cubierta por los 3 marcadores mas probables</span><strong>{format_pct(avg_top3)}</strong></div>"
        f"<div class=\"summary-tile\"><span>Partidos en vivo detectados</span><strong>{live_matches}</strong></div>"
        "<div class=\"summary-tile\"><span>Como comprobar actualizacion</span><strong><a href=\"latest.json\">latest.json</a> + badge En vivo + minuto</strong></div>"
        "</div>"
        f"{charts_html}"
        "<div class=\"confidence-grid\">"
        "<article><h3>Partidos con favorito mas claro</h3><ul>"
        f"{bullet_list(strongest, 'firm')}"
        "</ul></article>"
        "<article><h3>Partidos mas cerrados o parejos</h3><ul>"
        f"{bullet_list(most_open, 'open')}"
        "</ul></article>"
        "<article><h3>Modelo vs cuotas</h3><ul>"
        f"{market_list(market_edges) if market_edges else '<li><strong>Sin odds comparables</strong><span>Aun no llegaron cuotas utilizables del feed.</span></li>'}"
        "</ul></article>"
        f"{group_closed_html}"
        f"{group_open_html}"
        "</div>"
        "</section>"
    )


def bracket_stage_sections(bracket_payload: dict) -> List[Tuple[str, str, List[dict]]]:
    matches = bracket_payload.get("matches", {})
    stage_order = [
        ("round32", "Dieciseisavos"),
        ("round16", "Octavos"),
        ("quarterfinal", "Cuartos"),
        ("semifinal", "Semifinales"),
        ("final", "Final"),
        ("third_place", "Tercer puesto"),
    ]

    def match_order(item: Tuple[str, dict]) -> Tuple[int, str]:
        match_id = item[0]
        digits = "".join(char for char in str(match_id) if char.isdigit())
        return (int(digits), str(match_id)) if digits else (10**9, str(match_id))

    sections = []
    for stage_key, label in stage_order:
        stage_matches = [
            match for _, match in sorted(matches.items(), key=match_order) if match.get("stage") == stage_key
        ]
        if stage_matches:
            sections.append((stage_key, label, stage_matches))
    return sections


def build_bracket_visual_html(bracket_payload: dict) -> str:
    iterations = bracket_payload.get("iterations")
    sections = {stage_key: (label, stage_matches) for stage_key, label, stage_matches in bracket_stage_sections(bracket_payload)}

    source_map = {
        match_id: (left_source, right_source, "winner")
        for round_matches in KNOCKOUT_MATCHES.values()
        for match_id, left_source, right_source in round_matches
    }
    source_map["M104"] = ("M101", "M102", "loser")

    def fallback_visual_match(match: dict) -> dict:
        winner = str(match.get("winner", "?"))
        team_a = str(match.get("team_a", "?"))
        team_b = str(match.get("team_b", "?"))
        loser = team_b if winner == team_a else team_a
        conditional_prob = float(match.get("conditional_winner_prob", match.get("winner_prob", 0.0)))
        visual = dict(match)
        visual["selected_winner"] = winner
        visual["selected_loser"] = loser
        visual["conditional_winner_prob"] = conditional_prob
        return visual

    def find_consistent_matchup(match: dict, team_a: str, team_b: str) -> Optional[dict]:
        for scenario in match.get("matchup_scenarios", []):
            if scenario.get("team_a") == team_a and scenario.get("team_b") == team_b:
                return scenario
        return None

    def coherent_visual_matches(payload: dict) -> dict:
        payload_matches = payload.get("matches", {})
        resolved: Dict[str, dict] = {}
        ordered_match_ids = [match["id"] for match in R32_MATCHES]
        for round_matches in KNOCKOUT_MATCHES.values():
            ordered_match_ids.extend(match_id for match_id, _, _ in round_matches)
        ordered_match_ids.append("M104")

        for match_id in ordered_match_ids:
            match = payload_matches.get(match_id)
            if not match:
                continue
            source_info = source_map.get(match_id)
            if not source_info:
                resolved[match_id] = fallback_visual_match(match)
                continue
            left_source, right_source, source_kind = source_info
            left_match = resolved.get(left_source)
            right_match = resolved.get(right_source)
            if not left_match or not right_match:
                resolved[match_id] = fallback_visual_match(match)
                continue
            left_team = left_match.get("selected_winner") if source_kind == "winner" else left_match.get("selected_loser")
            right_team = right_match.get("selected_winner") if source_kind == "winner" else right_match.get("selected_loser")
            if not left_team or not right_team:
                resolved[match_id] = fallback_visual_match(match)
                continue
            matchup = find_consistent_matchup(match, str(left_team), str(right_team))
            if not matchup:
                resolved[match_id] = fallback_visual_match(match)
                continue
            conditional_winners = matchup.get("conditional_winners", [])
            selected_winner = conditional_winners[0]["team"] if conditional_winners else matchup.get("winner", left_team)
            conditional_prob = (
                float(conditional_winners[0]["conditional_prob"])
                if conditional_winners
                else float(matchup.get("conditional_winner_prob", match.get("winner_prob", 0.0)))
            )
            overall_prob = (
                float(conditional_winners[0]["overall_prob"])
                if conditional_winners
                else float(matchup.get("winner_prob", match.get("winner_prob", 0.0)))
            )
            visual = dict(match)
            visual["team_a"] = matchup.get("team_a", match.get("team_a"))
            visual["team_b"] = matchup.get("team_b", match.get("team_b"))
            visual["winner"] = selected_winner
            visual["matchup_prob"] = float(matchup.get("matchup_prob", match.get("matchup_prob", 0.0)))
            visual["conditional_winner_prob"] = conditional_prob
            visual["winner_prob"] = overall_prob
            visual["selected_winner"] = selected_winner
            visual["selected_loser"] = visual["team_b"] if selected_winner == visual["team_a"] else visual["team_a"]
            resolved[match_id] = visual
        return resolved

    visual_matches = coherent_visual_matches(bracket_payload)
    sections = {
        stage_key: (
            label,
            [visual_matches.get(match.get("match_id")) or match for match in stage_matches],
        )
        for stage_key, (label, stage_matches) in sections.items()
    }

    def split_stage(stage_key: str) -> Tuple[List[dict], List[dict]]:
        stage_matches = sections.get(stage_key, ("", []))[1]
        midpoint = len(stage_matches) // 2
        return stage_matches[:midpoint], stage_matches[midpoint:]

    def build_match_card(match: dict) -> str:
        match_cards = []
        team_a = html.escape(match.get("team_a", "?"))
        team_b = html.escape(match.get("team_b", "?"))
        winner = html.escape(match.get("winner", "?"))

        extra_parts = []
        alternatives = match.get("top_scenarios", [])[1:]
        if alternatives:
            extra_parts.append(
                "<div class=\"mini\">"
                "<strong>Otros cruces que tambien aparecen:</strong> "
                + html.escape(
                    "; ".join(
                        f"{scenario['team_a']} vs {scenario['team_b']} | favorito {scenario['winner']} | escenario {format_pct(float(scenario['prob']))}"
                        for scenario in alternatives[:2]
                    )
                )
                + "</div>"
            )
        if match.get("stage") != "third_place":
            extra_parts.append(
                "<div class=\"mini\">"
                f"<strong>Prórroga:</strong> {format_pct(float(match.get('extra_time_prob', 0.0)))} | "
                f"<strong>Penales:</strong> {format_pct(float(match.get('penalties_prob', 0.0)))}"
                "</div>"
            )
        penalty_scores = match.get("top_penalty_scores", [])
        if penalty_scores:
            extra_parts.append(
                "<p class=\"mini penalty-note\"><strong>Si se define por penales:</strong> "
                + html.escape(
                    "; ".join(
                        f"{item['score']} ({format_pct(float(item['prob']))})"
                        for item in penalty_scores[:2]
                    )
                )
                + "</p>"
            )
        detail_html = ""
        if extra_parts:
            detail_html = (
                "<details class=\"bracket-extra\">"
                "<summary>Mas detalle</summary>"
                + "".join(extra_parts)
                + "</details>"
            )

        row_a_class = "team-row favorite" if match.get("winner") == match.get("team_a") else "team-row"
        row_b_class = "team-row favorite" if match.get("winner") == match.get("team_b") else "team-row"
        row_a_badge = "<span class=\"team-badge\">Favorito</span>" if "favorite" in row_a_class else ""
        row_b_badge = "<span class=\"team-badge\">Favorito</span>" if "favorite" in row_b_class else ""
        conditional_prob = float(match.get("conditional_winner_prob", match.get("winner_prob", 0.0)))
        return (
            "<article class=\"bracket-match\">"
            f"<p class=\"match-kicker\">{html.escape(str(match.get('title', '')))}</p>"
            "<div class=\"match-teams\">"
            f"<div class=\"{row_a_class}\"><span class=\"team-name\">{team_a}</span>{row_a_badge}</div>"
            "<div class=\"team-divider\"></div>"
            f"<div class=\"{row_b_class}\"><span class=\"team-name\">{team_b}</span>{row_b_badge}</div>"
            "</div>"
            "<div class=\"bracket-pills\">"
            f"<span>Cruce {format_pct(float(match.get('matchup_prob', 0.0)))}</span>"
            f"<span>Si se juega, avanza {winner} {format_pct(conditional_prob)}</span>"
            "</div>"
            f"{detail_html}"
            "</article>"
        )

    def build_stage_column(side_class: str, stage_key: str, label: str, stage_matches: List[dict]) -> str:
        if not stage_matches:
            return ""
        return (
            f"<section class=\"bracket-column {side_class} stage-{html.escape(stage_key)}\">"
            f"<div class=\"stage-head\"><p class=\"stage-kicker\">Ronda</p><h3>{html.escape(label)}</h3></div>"
            f"<div class=\"stage-matches\">{''.join(build_match_card(match) for match in stage_matches)}</div>"
            "</section>"
        )

    left_round32, right_round32 = split_stage("round32")
    left_round16, right_round16 = split_stage("round16")
    left_quarterfinal, right_quarterfinal = split_stage("quarterfinal")
    left_semifinal, right_semifinal = split_stage("semifinal")
    final_matches = sections.get("final", ("Final", []))[1]
    third_place_matches = sections.get("third_place", ("Tercer puesto", []))[1]

    if not any([left_round32, right_round32, left_round16, right_round16, left_quarterfinal, right_quarterfinal, left_semifinal, right_semifinal, final_matches, third_place_matches]):
        return "<p class=\"meta\">No hay llave estructurada todavía.</p>"

    sections_html = [
        build_stage_column("left left-round32", "round32", "Dieciseisavos", left_round32),
        build_stage_column("left left-round16", "round16", "Octavos", left_round16),
        build_stage_column("left left-quarterfinal", "quarterfinal", "Cuartos", left_quarterfinal),
        build_stage_column("left left-semifinal", "semifinal", "Semifinales", left_semifinal),
        (
            "<section class=\"bracket-column center-column\">"
            "<div class=\"center-stack\">"
            f"{build_stage_column('center center-final', 'final', 'Final', final_matches)}"
            f"{build_stage_column('center center-third_place', 'third_place', 'Tercer puesto', third_place_matches)}"
            "</div>"
            "</section>"
        ),
        build_stage_column("right right-semifinal", "semifinal", "Semifinales", right_semifinal),
        build_stage_column("right right-quarterfinal", "quarterfinal", "Cuartos", right_quarterfinal),
        build_stage_column("right right-round16", "round16", "Octavos", right_round16),
        build_stage_column("right right-round32", "round32", "Dieciseisavos", right_round32),
    ]

    board_width = 1908
    board_height = 1210
    column_width = 196
    column_gap = 18
    head_total = 86
    card_height = 126
    center_stack_top = 362
    center_stack_gap = 180

    def column_x(index: int) -> float:
        return float(index * (column_width + column_gap))

    def left_edge(index: int) -> float:
        return column_x(index)

    def right_edge(index: int) -> float:
        return column_x(index) + column_width

    def stage_centers(count: int, top_padding: int, gap: int, stack_offset: int = 0) -> List[float]:
        centers = []
        base = stack_offset + head_total + top_padding + (card_height / 2.0)
        for idx in range(count):
            centers.append(base + idx * (card_height + gap))
        return centers

    left_r32_y = stage_centers(len(left_round32), 0, 14)
    left_r16_y = stage_centers(len(left_round16), 56, 74)
    left_qf_y = stage_centers(len(left_quarterfinal), 158, 230)
    left_sf_y = stage_centers(len(left_semifinal), 362, 500)
    right_r32_y = stage_centers(len(right_round32), 0, 14)
    right_r16_y = stage_centers(len(right_round16), 56, 74)
    right_qf_y = stage_centers(len(right_quarterfinal), 158, 230)
    right_sf_y = stage_centers(len(right_semifinal), 362, 500)
    final_y = stage_centers(len(final_matches), 0, 20, stack_offset=center_stack_top)
    third_y = stage_centers(len(third_place_matches), 0, 20, stack_offset=center_stack_top + head_total + card_height + center_stack_gap)

    def connector_path(x1: float, y1: float, x2: float, y2: float) -> str:
        mid = (x1 + x2) / 2.0
        return f"M {x1:.1f} {y1:.1f} H {mid:.1f} V {y2:.1f} H {x2:.1f}"

    svg_paths: List[str] = []

    def link_pairs(source_centers: Sequence[float], target_centers: Sequence[float], source_x: float, target_x: float) -> None:
        for idx, target_y in enumerate(target_centers):
            source_idx = idx * 2
            if source_idx + 1 >= len(source_centers):
                break
            svg_paths.append(f"<path class=\"bracket-link\" d=\"{connector_path(source_x, source_centers[source_idx], target_x, target_y)}\" />")
            svg_paths.append(f"<path class=\"bracket-link\" d=\"{connector_path(source_x, source_centers[source_idx + 1], target_x, target_y)}\" />")

    link_pairs(left_r32_y, left_r16_y, right_edge(0), left_edge(1))
    link_pairs(left_r16_y, left_qf_y, right_edge(1), left_edge(2))
    link_pairs(left_qf_y, left_sf_y, right_edge(2), left_edge(3))
    link_pairs(right_r32_y, right_r16_y, left_edge(8), right_edge(7))
    link_pairs(right_r16_y, right_qf_y, left_edge(7), right_edge(6))
    link_pairs(right_qf_y, right_sf_y, left_edge(6), right_edge(5))

    if left_sf_y and final_y:
        svg_paths.append(f"<path class=\"bracket-link bracket-link-strong\" d=\"{connector_path(right_edge(3), left_sf_y[0], left_edge(4), final_y[0])}\" />")
    if right_sf_y and final_y:
        svg_paths.append(f"<path class=\"bracket-link bracket-link-strong\" d=\"{connector_path(left_edge(5), right_sf_y[0], right_edge(4), final_y[0])}\" />")
    if left_sf_y and third_y:
        svg_paths.append(f"<path class=\"bracket-link bracket-link-secondary\" d=\"{connector_path(right_edge(3), left_sf_y[0], left_edge(4), third_y[0])}\" />")
    if right_sf_y and third_y:
        svg_paths.append(f"<path class=\"bracket-link bracket-link-secondary\" d=\"{connector_path(left_edge(5), right_sf_y[0], right_edge(4), third_y[0])}\" />")

    bracket_svg = (
        f"<svg class=\"bracket-svg\" viewBox=\"0 0 {board_width} {board_height}\" preserveAspectRatio=\"none\" aria-hidden=\"true\">"
        "<defs>"
        "<filter id=\"bracketGlow\" x=\"-20%\" y=\"-20%\" width=\"140%\" height=\"140%\">"
        "<feDropShadow dx=\"0\" dy=\"0\" stdDeviation=\"2.5\" flood-color=\"rgba(15,109,102,0.16)\"/>"
        "</filter>"
        "</defs>"
        f"{''.join(svg_paths)}"
        "</svg>"
    )

    subtitle = ""
    if iterations:
        subtitle = (
            f"<p class=\"lede-tight\">Llave Monte Carlo dinámica con {int(iterations)} iteraciones publicadas. "
            "El cuadro se abre en dos ramas y converge hacia la final. Cada cruce muestra la combinación que más aparece hoy en esa zona; si la probabilidad del cruce es baja, esa parte de la llave sigue abierta y puede cambiar con resultados reales.</p>"
        )
    return (
        "<section class=\"panel bracket-panel\">"
        "<div class=\"panel-head\">"
        "<div>"
        "<p class=\"eyebrow\">Hoja de Ruta</p>"
        "<h2>Llave Proyectada</h2>"
        f"{subtitle}"
        "</div>"
        "</div>"
        "<div class=\"bracket-shell\">"
        "<div class=\"bracket-canvas\">"
        f"{bracket_svg}"
        "<div class=\"bracket-grid bracket-board\">"
        f"{''.join(sections_html)}"
        "</div>"
        "</div>"
        "</div>"
        "</section>"
    )


def build_backtesting_markdown(backtest: dict) -> List[str]:
    if not backtest or not backtest.get("completed_matches"):
        return ["_Todavia no hay suficientes partidos terminados para medir como viene acertando el modelo._"]

    lines = [
        f"- Partidos cerrados analizados: {int(backtest.get('completed_matches', 0))}",
        f"- Partidos comparables en 90 minutos: {int(backtest.get('regular_time_samples', 0))}",
    ]
    if backtest.get("favorite_hit_rate") is not None:
        lines.append(f"- Cuantas veces acertamos el resultado mas probable: {format_pct(float(backtest['favorite_hit_rate']))}")
    if backtest.get("top1_score_hit_rate") is not None:
        lines.append(f"- Cuantas veces acertamos exactamente el marcador principal: {format_pct(float(backtest['top1_score_hit_rate']))}")
    if backtest.get("top3_score_hit_rate") is not None:
        lines.append(f"- Cuantas veces el marcador real estuvo dentro de nuestros 3 resultados principales: {format_pct(float(backtest['top3_score_hit_rate']))}")
    if backtest.get("logloss_result") is not None:
        lines.append(f"- Error log-loss en resultado: {float(backtest['logloss_result']):.3f}")
    if backtest.get("brier_result") is not None:
        lines.append(f"- Error Brier en resultado: {float(backtest['brier_result']):.3f}")
    if backtest.get("brier_reliability") is not None:
        lines.append(f"- Brier descompuesto | calibracion {float(backtest['brier_reliability']):.3f} | separacion {float(backtest['brier_resolution']):.3f} | incertidumbre base {float(backtest['brier_uncertainty']):.3f}")
    if backtest.get("logloss_advance") is not None:
        lines.append(f"- Error log-loss en clasificacion knockout: {float(backtest['logloss_advance']):.3f}")
    if backtest.get("brier_advance") is not None:
        lines.append(f"- Error Brier en clasificacion knockout: {float(backtest['brier_advance']):.3f}")
    if backtest.get("market_logloss_result") is not None:
        lines.append(f"- Error log-loss de las cuotas en esos mismos partidos: {float(backtest['market_logloss_result']):.3f}")
    if backtest.get("temporal_cv_logloss") is not None:
        lines.append(
            f"- Validacion temporal por ventanas | log-loss {float(backtest['temporal_cv_logloss']):.3f} | "
            f"Brier {float(backtest['temporal_cv_brier']):.3f} | acierto {format_pct(float(backtest['temporal_cv_accuracy']))}"
        )
    buckets = backtest.get("calibration_buckets") or []
    if buckets:
        lines.append(
            "- Si el modelo dice una probabilidad parecida, esto es lo que paso en la realidad: "
            + "; ".join(
                f"{bucket['bucket']} -> confianza media {format_pct(float(bucket['avg_confidence']))}, acierto real {format_pct(float(bucket['hit_rate']))}, n={int(bucket['matches'])}"
                for bucket in buckets
            )
        )
    return lines


def build_backtesting_html(backtest: dict) -> str:
    if not backtest or not backtest.get("completed_matches"):
        return (
            "<section class=\"panel backtest-panel\">"
            "<div class=\"panel-head\"><div><p class=\"eyebrow\">Validacion</p><h2>Como viene acertando el modelo</h2>"
            "<p class=\"lede-tight\">Todavia no hay suficientes partidos terminados en el torneo para medir con datos reales como viene rindiendo el modelo. Esta seccion se llenara sola cuando aparezcan resultados.</p>"
            "</div></div></section>"
        )

    metrics = []
    def tile(label: str, value: str) -> str:
        return f"<div class=\"summary-tile\"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>"

    metrics.append(tile("Partidos cerrados", str(int(backtest.get("completed_matches", 0)))))
    metrics.append(tile("Muestra en reglamentario", str(int(backtest.get("regular_time_samples", 0)))))
    if backtest.get("favorite_hit_rate") is not None:
        metrics.append(tile("Acierto del pick principal", format_pct(float(backtest["favorite_hit_rate"]))))
    if backtest.get("top3_score_hit_rate") is not None:
        metrics.append(tile("Marcador dentro del top-3", format_pct(float(backtest["top3_score_hit_rate"]))))

    quality_rows = []
    if backtest.get("logloss_result") is not None:
        quality_rows.append(f"<li><strong>Log-loss resultado</strong><span>{float(backtest['logloss_result']):.3f}</span></li>")
    if backtest.get("brier_result") is not None:
        quality_rows.append(f"<li><strong>Brier resultado</strong><span>{float(backtest['brier_result']):.3f}</span></li>")
    if backtest.get("brier_reliability") is not None:
        quality_rows.append(f"<li><strong>Brier calibracion</strong><span>{float(backtest['brier_reliability']):.3f}</span></li>")
        quality_rows.append(f"<li><strong>Brier separacion</strong><span>{float(backtest['brier_resolution']):.3f}</span></li>")
        quality_rows.append(f"<li><strong>Incertidumbre base</strong><span>{float(backtest['brier_uncertainty']):.3f}</span></li>")
    if backtest.get("logloss_advance") is not None:
        quality_rows.append(f"<li><strong>Log-loss clasificacion</strong><span>{float(backtest['logloss_advance']):.3f}</span></li>")
    if backtest.get("brier_advance") is not None:
        quality_rows.append(f"<li><strong>Brier clasificacion</strong><span>{float(backtest['brier_advance']):.3f}</span></li>")
    if backtest.get("market_logloss_result") is not None:
        quality_rows.append(f"<li><strong>Log-loss mercado</strong><span>{float(backtest['market_logloss_result']):.3f}</span></li>")
    if backtest.get("temporal_cv_logloss") is not None:
        quality_rows.append(f"<li><strong>Log-loss por ventanas</strong><span>{float(backtest['temporal_cv_logloss']):.3f}</span></li>")
        quality_rows.append(f"<li><strong>Brier por ventanas</strong><span>{float(backtest['temporal_cv_brier']):.3f}</span></li>")
        quality_rows.append(f"<li><strong>Acierto por ventanas</strong><span>{format_pct(float(backtest['temporal_cv_accuracy']))}</span></li>")

    calibration_rows = []
    for bucket in backtest.get("calibration_buckets", []):
        calibration_rows.append(
            "<li>"
            f"<strong>{html.escape(bucket['bucket'])}</strong>"
            f"<span>confianza media {format_pct(float(bucket['avg_confidence']))} | acierto real {format_pct(float(bucket['hit_rate']))} | n={int(bucket['matches'])}</span>"
            "</li>"
        )

    performance_chart_rows = []
    if backtest.get("favorite_hit_rate") is not None:
        performance_chart_rows.append(
            {
                "label": "Pick principal",
                "value": float(backtest["favorite_hit_rate"]),
                "value_text": format_pct(float(backtest["favorite_hit_rate"])),
                "detail": "Cuantas veces acierta el resultado principal que publicamos.",
            }
        )
    if backtest.get("top1_score_hit_rate") is not None:
        performance_chart_rows.append(
            {
                "label": "Marcador principal exacto",
                "value": float(backtest["top1_score_hit_rate"]),
                "value_text": format_pct(float(backtest["top1_score_hit_rate"])),
                "detail": "Cuantas veces el marcador exacto numero uno coincide con el resultado real.",
            }
        )
    if backtest.get("top3_score_hit_rate") is not None:
        performance_chart_rows.append(
            {
                "label": "Marcador dentro del top-3",
                "value": float(backtest["top3_score_hit_rate"]),
                "value_text": format_pct(float(backtest["top3_score_hit_rate"])),
                "detail": "Cuantas veces el marcador real cae dentro de nuestros tres marcadores principales.",
            }
        )
    if backtest.get("temporal_cv_accuracy") is not None:
        performance_chart_rows.append(
            {
                "label": "Acierto por ventanas",
                "value": float(backtest["temporal_cv_accuracy"]),
                "value_text": format_pct(float(backtest["temporal_cv_accuracy"])),
                "detail": "Walk-forward temporal para ver si el rendimiento aguanta cuando el torneo avanza.",
            }
        )

    calibration_chart_rows = [
        {
            "label": bucket["bucket"],
            "primary": float(bucket["avg_confidence"]),
            "secondary": float(bucket["hit_rate"]),
            "sample": int(bucket["matches"]),
            "detail": (
                f"Modelo {format_pct(float(bucket['avg_confidence']))} | "
                f"real {format_pct(float(bucket['hit_rate']))}"
            ),
        }
        for bucket in backtest.get("calibration_buckets", [])
    ]
    charts_html = render_chart_grid(
        [
            render_rank_chart(
                "Que tan seguido pega lo visible",
                performance_chart_rows,
                tone="accent",
                description="Este grafico se enfoca en lo que mas se ve en la web: pick principal, marcador exacto y aciertos por ventanas temporales.",
                empty_body="Todavia no hay suficientes partidos cerrados para medir rendimiento visible.",
            ),
            render_dual_bar_chart(
                "Calibracion por tramos",
                calibration_chart_rows,
                description="Compara lo que el modelo prometia en cada tramo de confianza contra lo que termino pasando de verdad.",
                primary_label="Confianza media",
                secondary_label="Acierto real",
                primary_tone="accent",
                secondary_tone="gold",
                empty_body="Todavia no hay suficientes buckets de confianza para comparar modelo y realidad.",
            ),
        ]
    )

    return (
        "<section class=\"panel backtest-panel\">"
        "<div class=\"panel-head\"><div><p class=\"eyebrow\">Validacion</p><h2>Como viene acertando el modelo</h2>"
        "<p class=\"lede-tight\">Aqui reconstruimos el torneo partido por partido, siempre pronosticando antes de cargar el resultado real. Asi medimos con justicia si el modelo esta bien calibrado y cuanto se acerca a lo que termino pasando.</p>"
        "</div></div>"
        f"<div class=\"confidence-tiles\">{''.join(metrics)}</div>"
        f"{charts_html}"
        "<div class=\"confidence-grid\">"
        "<article><h3>Errores del modelo</h3><ul>"
        f"{''.join(quality_rows) if quality_rows else '<li><strong>Sin muestra suficiente</strong><span>Aun no hay datos comparables.</span></li>'}"
        "</ul></article>"
        "<article><h3>Cuando el modelo dice X, que tanto se cumple</h3><ul>"
        f"{''.join(calibration_rows) if calibration_rows else '<li><strong>Sin buckets</strong><span>Aun no hay suficientes partidos.</span></li>'}"
        "</ul></article>"
        "</div>"
        "</section>"
    )


def build_methodology_html(bracket_payload: dict, backtest: dict) -> str:
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    montecarlo_line = f"{iterations:,}".replace(",", ".") + " iteraciones" if iterations else "iteraciones variables"
    return (
        "<section class=\"panel methodology\">"
        "<div class=\"panel-head\">"
        "<div>"
        "<p class=\"eyebrow\">Cómo Leer Esto</p>"
        "<h2>Como esta armado el modelo</h2>"
        "<p class=\"lede-tight\">La idea aqui no es complicar por complicar. El modelo ya es fuerte para quiniela; lo que mas valor agrega ahora es que explique bien por que cambia y que luego podamos medir con datos reales si viene acertando.</p>"
        "</div>"
        "</div>"
        "<div class=\"method-grid\">"
        "<article>"
        "<h3>Partido a partido</h3>"
        "<p>Combina fuerza de cada seleccion, contexto del partido y un stack de modelos para estimar marcador final y probabilidades de victoria, empate y derrota.</p>"
        "</article>"
        "<article>"
        "<h3>Capa historica desde 1990</h3>"
        "<p>Ademas del Elo y la forma actual, el modelo incorpora resultados de selecciones desde 1990: rendimiento total, competitivo, mundialista, ataque, defensa y tandas de penales. Esa memoria historica ahora usa shrinkage bayesiano empirico para no sobrepremiar muestras chicas y para sumar contexto sin tapar lo que esta pasando hoy.</p>"
        "</article>"
        "<article>"
        "<h3>Cuadro completo</h3>"
        f"<p>La llave publicada se construye con Monte Carlo dinamico de {html.escape(montecarlo_line)} por corrida para que el cuadro no cambie solo por ruido de simulacion. El muestreo de goles ya usa un RNG rapido con NumPy y semillas deterministas para sostener mas simulaciones sin volver lento el procesamiento.</p>"
        "</article>"
        "<article>"
        "<h3>Stack estadistico</h3>"
        "<p>La capa prepartido mezcla el modelo principal Bivariante Poisson, un modelo de contraste Poisson independiente, un ajuste de baja anotacion y un ensamble ligero final. Ese ensamble ahora repondera los modelos segun consenso y cercania al mercado cuando hay cuotas confiables.</p>"
        "</article>"
        "<article>"
        "<h3>Estrategia de datos</h3>"
        "<p>El modelo prioriza fuentes solidas y trazables antes que volumen bruto. Aqui la meta no es meter cientos de terabytes por marketing, sino usar capas de alta señal: datos oficiales, historia desde 1990, feed en vivo y mercado como referencia suave.</p>"
        "</article>"
        "<article>"
        "<h3>Modelos visibles en la web</h3>"
        "<p>En cada tarjeta de partido veras por separado que dice Bivariante Poisson, que dice Poisson independiente, que dice el ajuste de baja anotacion y cual es el ensamble final publicado. Asi puedes comparar si coinciden o si hay dispersion entre modelos.</p>"
        "</article>"
        "<article>"
        "<h3>Estado dinámico</h3>"
        "<p>Actualiza Elo, forma, fatiga, disponibilidad, disciplina, clima, alineaciones, bajas y mercado a medida que aparecen datos nuevos. Ademas, acumula el estilo reciente de cada seleccion para no arrancar cada cruce desde cero.</p>"
        "</article>"
        "<article>"
        "<h3>Validacion y calibracion</h3>"
        "<p>El seguimiento del rendimiento no se queda en acierto bruto. La web ahora muestra log-loss, Brier, descomposicion de calibracion y una lectura temporal por ventanas para ver si el modelo se mantiene estable cuando el torneo avanza.</p>"
        "</article>"
        "<article>"
        "<h3>Modo in-play</h3>"
        "<p>Durante un partido, condiciona las probabilidades por minuto, marcador actual y fase del juego. Si el feed trae datos mas ricos, tambien usa tiros, tiros al arco, posesion, calidad de ocasiones, corners, disciplina y expulsiones para recalcular todo.</p>"
        "</article>"
        "<article>"
        "<h3>Noticias y bajas</h3>"
        "<p>Si el feed publica ausencias, cambios de XI o noticias relevantes del partido, esas señales entran como disponibilidad, moral o contexto adicional.</p>"
        "</article>"
        "<article>"
        "<h3>Como validar el refresh</h3>"
        "<p>La portada publica hora de actualizacion, badge En vivo, minuto modelado y un latest.json. Si esos campos cambian, el in-play se esta recalculando bien.</p>"
        "</article>"
        "</div>"
        f"<p class=\"lede-tight\">Backtesting actual: {html.escape(str(int(backtest.get('completed_matches', 0))))} partidos cerrados reconstruidos secuencialmente.</p>"
        "</section>"
    )


def build_dashboard_html(
    entries: Sequence[dict],
    bracket_text: str,
    bracket_payload: dict,
    backtest: dict,
    state_path: Path,
    fixtures_path: Path,
    previous_entries: Optional[Sequence[dict]] = None,
    previous_bracket_payload: Optional[dict] = None,
    previous_updated_at: Optional[str] = None,
) -> str:
    cards = []
    for entry in entries:
        prediction: MatchPrediction = entry["prediction"]
        status_class, status_text = dashboard_status(entry)
        status_html = f"<p class=\"badge {status_class}\">{html.escape(status_text)}</p>"
        probability_rows_html = "".join(
            (
                "<div class=\"prob-row\">"
                f"<div class=\"prob-label\">{html.escape(label)}</div>"
                f"<div class=\"prob-bar\"><span class=\"prob-fill {row_class}\" style=\"width:{prob * 100:.1f}%\"></span></div>"
                f"<div class=\"prob-value\">{format_pct(prob)}</div>"
                "</div>"
            )
            for label, prob, row_class in probability_rows(prediction)
        )
        result_html = ""
        if entry["actual_score_a"] is not None and entry["actual_score_b"] is not None:
            result_text = f"Resultado real: {prediction.team_a} {entry['actual_score_a']} - {entry['actual_score_b']} {prediction.team_b}"
            if entry["went_penalties"]:
                result_text += f" | penales: {entry['penalties_winner']}"
            elif entry["went_extra_time"]:
                result_text += " | con proroga"
            result_html = f"<p class=\"meta\">{html.escape(result_text)}</p>"
        elif entry.get("live_score_a") is not None and entry.get("live_score_b") is not None:
            result_html = (
                f"<p class=\"meta\">En vivo: {html.escape(prediction.team_a)} {entry['live_score_a']} - "
                f"{entry['live_score_b']} {html.escape(prediction.team_b)}</p>"
            )
        else:
            result_html = ""

        venue_html = ""
        if entry.get("kickoff_utc") or entry.get("venue_name"):
            venue_bits = [entry.get("venue_name"), entry.get("venue_country")]
            venue_bits = [bit for bit in venue_bits if bit]
            venue_html = (
                f"<p class=\"meta\">{html.escape(' | '.join(venue_bits))}</p>"
                f"<p class=\"meta\">UTC: {html.escape(str(entry.get('kickoff_utc', '')))}</p>"
            )
        minute_html = ""
        if prediction.elapsed_minutes is not None:
            minute_html = f"<p class=\"meta\">Minuto modelado: {prediction.elapsed_minutes:.1f}</p>"

        weather_html = ""
        if entry.get("weather_summary"):
            weather_html = f"<p class=\"meta\">Clima: {html.escape(entry['weather_summary'])}</p>"

        officiating_html = ""
        if entry.get("referee"):
            officiating_html = f"<p class=\"meta\">Arbitro: {html.escape(str(entry['referee']))}</p>"

        market_html = ""
        if entry.get("market_summary"):
            market_text = entry["market_summary"]
            if entry.get("market_provider"):
                market_text = f"{entry['market_provider']}: {market_text}"
            market_html += f"<p class=\"meta\">Odds: {html.escape(market_text)}</p>"
        if entry.get("market_prob_a") is not None:
            market_html += (
                f"<p class=\"meta\">Referencia de cuotas (victoria/empate/derrota): {html.escape(prediction.team_a)} {format_pct(float(entry['market_prob_a']))} | "
                f"empate {format_pct(float(entry.get('market_prob_draw', 0.0)))} | "
                f"{html.escape(prediction.team_b)} {format_pct(float(entry.get('market_prob_b', 0.0)))}</p>"
            )

        lineup_html = ""
        if entry.get("lineup_status_a") or entry.get("lineup_status_b"):
            lineup_html += (
                f"<p class=\"meta\">Alineaciones: {html.escape(prediction.team_a)} {html.escape(str(entry.get('lineup_status_a', 'sin confirmar')))} | "
                f"{html.escape(prediction.team_b)} {html.escape(str(entry.get('lineup_status_b', 'sin confirmar')))}</p>"
            )
        if entry.get("lineup_change_count_a") or entry.get("lineup_change_count_b"):
            lineup_html += (
                f"<p class=\"meta\">Cambios XI: {html.escape(prediction.team_a)} {entry.get('lineup_change_count_a', 0)} | "
                f"{html.escape(prediction.team_b)} {entry.get('lineup_change_count_b', 0)}</p>"
            )

        absence_html = ""
        for line in dashboard_absence_lines(entry, prediction.team_a, prediction.team_b):
            absence_html += f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"

        news_html = ""
        for line in dashboard_news_lines(entry, prediction.team_a, prediction.team_b):
            news_html += f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"
        tactical_signature_html = ""
        for line in dashboard_tactical_signature_lines(entry, prediction.team_a, prediction.team_b):
            tactical_signature_html += f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"
        live_stats_html = ""
        for line in dashboard_live_stats_lines(entry, prediction.team_a, prediction.team_b):
            live_stats_html += f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"
        shot_timeline_html = ""
        shot_timeline_lines = dashboard_shot_timeline_lines(entry, prediction.team_a, prediction.team_b)
        if shot_timeline_lines:
            shot_timeline_html = (
                "<div class=\"reason-block\"><h4>Cronologia de disparos y eventos</h4>"
                + "".join(
                    f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"
                    for line in shot_timeline_lines
                )
                + "</div>"
            )
        pattern_html = ""
        pattern_lines = dashboard_pattern_lines(entry, prediction)
        if pattern_lines:
            pattern_html = (
                "<div class=\"reason-block\"><h4>Patrones de juego detectados</h4>"
                + "".join(
                    f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"
                    for line in pattern_lines
                )
                + "</div>"
            )

        reason_html = ""
        reason_lines = adjustment_reason_lines(entry, prediction)
        if reason_lines:
            reason_html = (
                "<div class=\"reason-block\"><h4>Por que cambia el pronostico</h4>"
                + "".join(
                    f"<p class=\"meta\">{html.escape(line[2:] if line.startswith('- ') else line)}</p>"
                    for line in reason_lines
                )
                + "</div>"
            )
        next_round_html = ""
        next_round_note = next_round_projection_note(entry, prediction, bracket_payload)
        if next_round_note:
            next_round_html = (
                "<div class=\"reason-block\"><h4>Siguiente cruce del ganador real</h4>"
                f"<p class=\"meta\">{html.escape(next_round_note)}</p>"
                "</div>"
            )

        projection_html = ""
        if entry.get("projection"):
            projection_html = f"<p class=\"meta\">{html.escape(entry.get('projection_note', ''))}</p>"
            alternatives = entry.get("projection_alternatives") or []
            if alternatives:
                projection_html += (
                    "<p class=\"meta\">Otras opciones de cruce: "
                    + html.escape(
                        "; ".join(
                            f"{scenario['team_a']} vs {scenario['team_b']} -> {scenario['winner']} {format_pct(float(scenario['prob']))}"
                            for scenario in alternatives
                        )
                    )
                    + "</p>"
                )
        depth_html = statistical_depth_html(prediction)
        model_compare_html = model_comparison_html(prediction)

        knockout_html = ""
        if prediction.advance_a is not None and prediction.advance_b is not None:
            detail = prediction.knockout_detail or {}
            shootout_html = ""
            if prediction.penalty_shootout:
                projected_shootout = ((prediction.penalty_shootout.get("top_scores") or [("5-4", 0.0)])[0][0])
                shootout_scores = "".join(
                    f"<li><strong>{html.escape(score)}</strong><span>{format_pct(prob)}</span></li>"
                    for score, prob in prediction.penalty_shootout.get("top_scores", [])
                )
                shootout_html = (
                    f"<div><span>Marcador mas probable de la tanda</span><strong>{html.escape(projected_shootout)}</strong></div>"
                    f"<div><span>Marcador medio esperado en la tanda</span><strong>{prediction.team_a} {prediction.penalty_shootout.get('avg_score_a', 0.0):.2f} | "
                    f"{prediction.team_b} {prediction.penalty_shootout.get('avg_score_b', 0.0):.2f}</strong></div>"
                    "<div class=\"scores\"><h4>Marcadores de tanda mas probables</h4>"
                    f"<ul>{shootout_scores}</ul></div>"
                )
            knockout_html = (
                "<div class=\"subgrid\">"
                f"<div><span>Quien tiene mas probabilidad de avanzar</span><strong>{html.escape(prediction.team_a)} {format_pct(prediction.advance_a)} | "
                f"{html.escape(prediction.team_b)} {format_pct(prediction.advance_b)}</strong></div>"
                f"<div><span>Si empatan tras 90'</span><strong>{html.escape(prediction.team_a)} {format_pct(detail.get('et_win_a', 0.0))} | "
                f"siguen empatados {format_pct(detail.get('et_draw', 0.0))} | {html.escape(prediction.team_b)} {format_pct(detail.get('et_win_b', 0.0))}</strong></div>"
                f"<div><span>Si llegan a penales</span><strong>{html.escape(prediction.team_a)} {format_pct(detail.get('penalties_a', 0.0))} | "
                f"{html.escape(prediction.team_b)} {format_pct(detail.get('penalties_b', 0.0))}</strong></div>"
                f"{shootout_html}"
                "</div>"
            )

        top_scores_html = "".join(
            f"<li><strong>{html.escape(score)}</strong><span>{format_pct(prob)}</span></li>"
            for score, prob in prediction.exact_scores
        )
        remaining_goals_html = ""
        if prediction.expected_remaining_goals_a is not None and prediction.expected_remaining_goals_b is not None:
            remaining_goals_html = (
                f"<p class=\"meta\">Promedio estimado de goles restantes: {html.escape(prediction.team_a)} {prediction.expected_remaining_goals_a:.2f} | "
                f"{html.escape(prediction.team_b)} {prediction.expected_remaining_goals_b:.2f}</p>"
            )
        average_goals_html = ""
        if prediction.live_phase != "penalties":
            average_goals_html = (
                f"<p class=\"meta\">{html.escape(average_goals_label(prediction))}: "
                f"{html.escape(prediction.team_a)} {prediction.expected_goals_a:.2f} | "
                f"{html.escape(prediction.team_b)} {prediction.expected_goals_b:.2f}</p>"
            )
        cards.append(
            "<section class=\"card\">"
            f"{status_html}"
            f"<h3>{html.escape(entry['title'])}</h3>"
            f"<p class=\"meta\">{html.escape(entry['stage_label'])}</p>"
            f"{result_html}"
            f"{venue_html}"
            f"{minute_html}"
            f"{weather_html}"
            f"{officiating_html}"
            f"{market_html}"
            f"{lineup_html}"
            f"{absence_html}"
            f"{news_html}"
            f"{tactical_signature_html}"
            f"{live_stats_html}"
            f"{shot_timeline_html}"
            f"{pattern_html}"
            f"{reason_html}"
            f"{next_round_html}"
            f"{projection_html}"
            "<div class=\"hero-metrics\">"
            f"<div class=\"metric metric-score\"><span>{html.escape(projected_score_label(prediction))}</span><strong>{html.escape(projected_score_value(prediction))}</strong></div>"
            f"<div class=\"metric metric-probs\"><span>{html.escape(top_result_label(prediction))}</span><strong>{html.escape(top_result_summary(prediction))}</strong></div>"
            "</div>"
            f"{average_goals_html}"
            f"<div class=\"prob-block\">{probability_rows_html}</div>"
            f"{remaining_goals_html}"
            f"{depth_html}"
            f"{model_compare_html}"
            f"{knockout_html}"
            "<div class=\"scores\">"
            "<h4>Marcadores finales mas probables</h4>"
            f"<ul>{top_scores_html}</ul>"
            "</div>"
            "</section>"
        )

    if not cards:
        cards.append("<section class=\"card\"><h3>Sin partidos cargados</h3><p class=\"meta\">Agrega partidos a fixtures_template.json para ver probabilidades aqui.</p></section>")

    bracket_html = html.escape(bracket_text.strip() or "No hay llave generada todavia.")
    bracket_visual_html = build_bracket_visual_html(bracket_payload)
    methodology_html = build_methodology_html(bracket_payload, backtest)
    global_confidence_html = build_global_confidence_html(entries)
    recent_changes_html = build_recent_changes_html(
        entries,
        previous_entries or [],
        bracket_payload,
        previous_bracket_payload or {},
        previous_updated_at,
    )
    backtesting_html = build_backtesting_html(backtest)
    return render_dashboard_html(
        {
            "updated_at": html.escape(iso_timestamp()),
            "state_path": html.escape(str(state_path)),
            "fixtures_path": html.escape(str(fixtures_path)),
            "methodology_html": methodology_html,
            "global_confidence_html": global_confidence_html,
            "recent_changes_html": recent_changes_html,
            "backtesting_html": backtesting_html,
            "bracket_visual_html": bracket_visual_html,
            "bracket_html": bracket_html,
            "cards_html": "".join(cards),
        }
    )


def command_project_dashboard(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    fixture_path = Path(args.fixtures)
    fixtures = read_fixtures(fixture_path)
    payload = load_persistent_payload(Path(args.state_file), teams)
    states = copy_states(payload)
    bracket_path = Path(args.bracket_file)
    bracket_json_path = Path(args.bracket_json_file)
    bracket_text = bracket_path.read_text() if bracket_path.exists() else ""
    bracket_payload = load_bracket_json(bracket_json_path)
    previous_entries, previous_bracket_payload, previous_updated_at = load_previous_site_snapshot(
        fixture_path,
        bracket_json_path,
        teams,
        states,
        args.top_scores,
    )

    entries = dashboard_fixture_entries(fixtures, teams, states, args.top_scores)
    entries.extend(
        projected_bracket_entries(
            fixtures,
            bracket_payload,
            teams,
            states,
            args.top_scores,
            [entry["match_id"] for entry in entries if entry.get("match_id")],
        )
    )
    backtest = compute_backtest_summary(fixtures, teams, args.top_scores)
    markdown = build_dashboard_markdown(
        entries,
        bracket_text,
        bracket_payload,
        backtest,
        Path(args.state_file),
        fixture_path,
        previous_entries=previous_entries,
        previous_bracket_payload=previous_bracket_payload,
        previous_updated_at=previous_updated_at,
    )
    html_content = build_dashboard_html(
        entries,
        bracket_text,
        bracket_payload,
        backtest,
        Path(args.state_file),
        fixture_path,
        previous_entries=previous_entries,
        previous_bracket_payload=previous_bracket_payload,
        previous_updated_at=previous_updated_at,
    )

    output_md = Path(args.output_md)
    output_html = Path(args.output_html)
    output_md.write_text(markdown)
    output_html.write_text(html_content)
    print(f"Reporte Markdown guardado en {output_md}")
    print(f"Reporte HTML guardado en {output_html}")


def read_fixtures(path: Path) -> List[dict]:
    return calculate_read_fixtures(path)


def iso_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def default_team_state() -> dict:
    return package_default_team_state()


def normalize_team_state(state: Optional[dict]) -> dict:
    return package_normalize_team_state(state)


def initial_team_states(teams: Dict[str, Team]) -> Dict[str, dict]:
    return package_initial_team_states(teams)


def empty_persistent_payload(teams: Dict[str, Team]) -> dict:
    return {
        "meta": {
            "version": 3,
            "updated_at": iso_timestamp(),
            "description": "Estado persistente del Mundial 2026 para actualizar automaticamente predicciones futuras.",
        },
        "applied_results": [],
        "teams": initial_team_states(teams),
    }


def normalize_persistent_payload(payload: dict, teams: Dict[str, Team]) -> dict:
    normalized = empty_persistent_payload(teams)
    normalized["meta"].update(payload.get("meta", {}))
    normalized["applied_results"] = list(payload.get("applied_results", []))

    team_payload = payload.get("teams", payload if isinstance(payload, dict) else {})
    for team_name in teams:
        normalized["teams"][team_name] = normalize_team_state(team_payload.get(team_name, {}))
    return normalized


def load_persistent_payload(path: Path, teams: Dict[str, Team]) -> dict:
    if not path.exists():
        return empty_persistent_payload(teams)
    text = path.read_text()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        payload, _ = decoder.raw_decode(text)
    return normalize_persistent_payload(payload, teams)


def save_persistent_payload(path: Path, payload: dict) -> None:
    payload["meta"]["updated_at"] = iso_timestamp()
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        dir=path.parent,
        prefix=f".{path.stem}-",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(serialized)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def copy_states(payload: dict) -> Dict[str, dict]:
    return package_copy_states(payload)


def print_state(state_name: str, state: dict) -> None:
    state = normalize_team_state(state)
    print(f"{state_name}")
    print(f"  Moral: {state['morale']:+.2f}")
    print(f"  Elo dinamico: {state['elo_shift']:+.1f}")
    print(f"  Forma reciente: {state['recent_form']:+.2f}")
    print(f"  Forma ataque: {state['attack_form']:+.2f}")
    print(f"  Forma defensa: {state['defense_form']:+.2f}")
    print(f"  Fatiga: {state['fatigue']:.2f}")
    print(f"  Disponibilidad: {state['availability']:.2f}")
    print(f"  Tendencia disciplinaria: {state['discipline_drift']:+.2f}")
    print(f"  Firma tactica reciente: {state['tactical_signature']}")
    print(
        f"  Rasgos tacticos: posesion {state['style_possession']:+.2f} | verticalidad {state['style_verticality']:+.2f} | "
        f"presion {state['style_pressure']:+.2f} | calidad {state['style_chance_quality']:+.2f} | ritmo {state['style_tempo']:+.2f}"
    )
    print(f"  Muestra tactica acumulada: {state['tactical_sample_matches']}")
    print(f"  Amarillas acumuladas: {state['yellow_cards']}")
    print(f"  Carga disciplinaria reciente: {state['yellow_load']:.2f}")
    print(f"  Suspensiones por roja: {state['red_suspensions']}")
    print(f"  Puntos de grupo: {state['group_points']}")
    print(f"  Diferencia de gol de grupo: {state['group_goal_diff']}")
    print(f"  Partidos de grupo: {state['group_matches_played']}")
    print(f"  Partidos totales: {state['matches_played']}")
    print(f"  Goles a favor: {state['goals_for']}")
    print(f"  Goles en contra: {state['goals_against']}")
    print(f"  Ultima actualizacion: {state['updated_at']}")


def state_has_activity(state: dict) -> bool:
    return package_state_has_activity(state)


def tactical_state_value(state: Optional[dict], key: str, default: float = 0.0) -> float:
    if not state:
        return default
    return float(normalize_team_state(state).get(key, default))


def tactical_attack_signal(state: Optional[dict]) -> float:
    return tactical_state_value(state, "style_attack_bias", 0.0)


def tactical_defense_signal(state: Optional[dict]) -> float:
    return tactical_state_value(state, "style_defense_bias", 0.0)


def tactical_tempo_signal(state: Optional[dict]) -> float:
    return tactical_state_value(state, "style_tempo", 0.0)


def tactical_signature_text(state: Optional[dict]) -> str:
    return str(normalize_team_state(state).get("tactical_signature", "sin muestra suficiente"))


def tactical_signature_from_metrics(
    style_possession: float,
    style_verticality: float,
    style_pressure: float,
    style_chance_quality: float,
    style_tempo: float,
    style_attack_bias: float,
    style_defense_bias: float,
    sample_matches: int,
) -> str:
    return calculate_tactical_signature_from_metrics(
        style_possession,
        style_verticality,
        style_pressure,
        style_chance_quality,
        style_tempo,
        style_attack_bias,
        style_defense_bias,
        sample_matches,
    )


def live_signature_metrics(side: str, live_stats: Dict[str, float]) -> Optional[Dict[str, float]]:
    return calculate_live_signature_metrics(side, live_stats, clamp=clamp)


def update_tactical_signature_state(state: dict, metrics: Optional[Dict[str, float]]) -> None:
    calculate_update_tactical_signature_state(state, metrics, clamp=clamp)


def fixture_stage_name(fixture: dict) -> str:
    stage = fixture.get("stage")
    if stage is not None:
        return normalize_stage_name(str(stage))
    if fixture.get("group"):
        return "group"
    if fixture.get("knockout", False):
        return "round32"
    return "group"


def resolve_fixture_winner(
    fixture: dict,
    teams: Dict[str, Team],
    team_a: str,
    team_b: str,
) -> Optional[str]:
    score_a = int(fixture["actual_score_a"])
    score_b = int(fixture["actual_score_b"])
    if score_a > score_b:
        return team_a
    if score_b > score_a:
        return team_b

    raw_winner = fixture.get("penalties_winner", fixture.get("actual_winner"))
    if raw_winner is None:
        return None
    if isinstance(raw_winner, str):
        normalized = raw_winner.strip().lower()
        if normalized in {"a", "team_a"}:
            return team_a
        if normalized in {"b", "team_b"}:
            return team_b
    return resolve_team_name(str(raw_winner), teams)


def fixture_state_ids(fixture: dict, fixture_path: Optional[Path] = None, index: Optional[int] = None) -> List[str]:
    ids = []
    if fixture.get("id"):
        ids.append(str(fixture["id"]))
    location = fixture_path.name if fixture_path else "fixture"
    label = fixture.get("label", "")
    if index is None:
        ids.append(f"{location}:{fixture['team_a']}:{fixture['team_b']}:{label}")
    else:
        ids.append(f"{location}:{index}:{fixture['team_a']}:{fixture['team_b']}:{label}")
    return ids


def apply_state_updates(
    teams: Dict[str, Team],
    states: Dict[str, dict],
    fixture: dict,
    ctx: MatchContext,
    prediction: MatchPrediction,
) -> None:
    if "actual_score_a" not in fixture or "actual_score_b" not in fixture:
        return

    team_a = fixture["team_a"]
    team_b = fixture["team_b"]
    score_a = int(fixture["actual_score_a"])
    score_b = int(fixture["actual_score_b"])
    yellows_a = int(fixture.get("actual_yellows_a", 0))
    yellows_b = int(fixture.get("actual_yellows_b", 0))
    reds_a = int(fixture.get("actual_reds_a", 0))
    reds_b = int(fixture.get("actual_reds_b", 0))
    stage = fixture_stage_name(fixture)
    winner = resolve_fixture_winner(fixture, teams, team_a, team_b)
    live_stats = extract_live_stats_payload(fixture)
    update_simulation_state(
        teams,
        states,
        team_a,
        team_b,
        ctx,
        prediction.expected_goals_a,
        prediction.expected_goals_b,
        score_a,
        score_b,
        yellows_a,
        reds_a,
        yellows_b,
        reds_b,
        stage,
        winner=winner,
        went_extra_time=bool(fixture.get("went_extra_time", False)),
        went_penalties=bool(fixture.get("went_penalties", False)),
        live_stats=live_stats,
    )
    states[team_a]["updated_at"] = iso_timestamp()
    states[team_b]["updated_at"] = iso_timestamp()


def context_from_fixture(
    fixture: dict,
    teams: Dict[str, Team],
    states: Optional[Dict[str, dict]] = None,
) -> MatchContext:
    states = states or {}
    state_a = normalize_team_state(states.get(fixture["team_a"], {}))
    state_b = normalize_team_state(states.get(fixture["team_b"], {}))
    stage = fixture_stage_name(fixture)
    knockout = stage != "group"
    default_rest_days = 4 if stage == "group" else 5

    return MatchContext(
        neutral=bool(fixture.get("neutral", fixture.get("home_team") is None)),
        home_team=fixture.get("home_team"),
        venue_country=fixture.get("venue_country"),
        rest_days_a=int(fixture.get("rest_days_a", default_rest_days)),
        rest_days_b=int(fixture.get("rest_days_b", default_rest_days)),
        injuries_a=float(fixture.get("injuries_a", dynamic_injury_load(teams[fixture["team_a"]], state_a))),
        injuries_b=float(fixture.get("injuries_b", dynamic_injury_load(teams[fixture["team_b"]], state_b))),
        altitude_m=int(fixture.get("altitude_m", 0)),
        travel_km_a=float(fixture.get("travel_km_a", 0.0)),
        travel_km_b=float(fixture.get("travel_km_b", 0.0)),
        knockout=knockout,
        morale_a=float(fixture.get("morale_a", state_a.get("morale", 0.0))),
        morale_b=float(fixture.get("morale_b", state_b.get("morale", 0.0))),
        yellow_cards_a=int(fixture.get("yellow_cards_a", predictive_yellow_cards(state_a))),
        yellow_cards_b=int(fixture.get("yellow_cards_b", predictive_yellow_cards(state_b))),
        red_suspensions_a=int(fixture.get("red_suspensions_a", state_a.get("red_suspensions", 0))),
        red_suspensions_b=int(fixture.get("red_suspensions_b", state_b.get("red_suspensions", 0))),
        group=fixture.get("group"),
        group_points_a=int(fixture.get("group_points_a", state_a.get("group_points", 0))),
        group_points_b=int(fixture.get("group_points_b", state_b.get("group_points", 0))),
        group_goal_diff_a=int(fixture.get("group_goal_diff_a", state_a.get("group_goal_diff", 0))),
        group_goal_diff_b=int(fixture.get("group_goal_diff_b", state_b.get("group_goal_diff", 0))),
        group_matches_played_a=int(
            fixture.get("group_matches_played_a", state_a.get("group_matches_played", 0))
        ),
        group_matches_played_b=int(
            fixture.get("group_matches_played_b", state_b.get("group_matches_played", 0))
        ),
        weather_stress=float(fixture.get("weather_stress", 0.0)),
        market_prob_a=market_probability(fixture.get("market_prob_a")),
        market_prob_draw=market_probability(fixture.get("market_prob_draw")),
        market_prob_b=market_probability(fixture.get("market_prob_b")),
        market_total_line=float(fixture["market_total_line"]) if fixture.get("market_total_line") is not None else None,
        lineup_confirmed_a=bool(fixture.get("lineup_confirmed_a", False)),
        lineup_confirmed_b=bool(fixture.get("lineup_confirmed_b", False)),
        lineup_change_count_a=int(fixture.get("lineup_change_count_a", 0)),
        lineup_change_count_b=int(fixture.get("lineup_change_count_b", 0)),
        importance=float(fixture.get("importance", STAGE_IMPORTANCE[stage])),
    )


def fixture_has_final_result(fixture: dict) -> bool:
    return fixture.get("actual_score_a") is not None and fixture.get("actual_score_b") is not None


def regular_time_result_available(fixture: dict) -> bool:
    return fixture_stage_name(fixture) == "group" or not bool(fixture.get("went_extra_time", False))


def actual_regular_time_outcome(fixture: dict) -> Optional[str]:
    if not fixture_has_final_result(fixture) or not regular_time_result_available(fixture):
        return None
    score_a = int(fixture["actual_score_a"])
    score_b = int(fixture["actual_score_b"])
    if score_a > score_b:
        return "a"
    if score_b > score_a:
        return "b"
    return "draw"


def actual_advancement_outcome(fixture: dict, teams: Dict[str, Team]) -> Optional[str]:
    if fixture_stage_name(fixture) == "group" or not fixture_has_final_result(fixture):
        return None
    winner = resolve_fixture_winner(fixture, teams, fixture["team_a"], fixture["team_b"])
    if winner == fixture["team_a"]:
        return "a"
    if winner == fixture["team_b"]:
        return "b"
    return None


def confidence_bucket(value: float) -> str:
    pct = value * 100.0
    if pct < 50.0:
        return "<50%"
    if pct < 60.0:
        return "50-59%"
    if pct < 70.0:
        return "60-69%"
    if pct < 80.0:
        return "70-79%"
    return "80%+"


def compute_backtest_summary(fixtures: Sequence[dict], teams: Dict[str, Team], top_scores: int) -> dict:
    return calculate_compute_backtest_summary(
        fixtures,
        teams,
        top_scores,
        BacktestMetricsCls=BacktestMetrics,
        fixture_has_final_result=fixture_has_final_result,
        copy_states=copy_states,
        empty_persistent_payload=empty_persistent_payload,
        resolve_fixture_names=resolve_fixture_names,
        context_from_fixture=context_from_fixture,
        fixture_stage_name=fixture_stage_name,
        predict_match=predict_match,
        normalize_team_state=normalize_team_state,
        actual_regular_time_outcome=actual_regular_time_outcome,
        actual_advancement_outcome=actual_advancement_outcome,
        confidence_bucket=confidence_bucket,
        apply_state_updates=apply_state_updates,
        brier_decomposition=brier_decomposition,
        summarize_temporal_windows=summarize_temporal_windows,
        avg_or_none=avg_or_none,
        temporal_cv_fold_size=PARAMS.temporal_cv_fold_size,
    )


def print_prediction(prediction: MatchPrediction, show_factors: bool = False) -> None:
    print(f"{prediction.team_a} vs {prediction.team_b}")
    if prediction.elapsed_minutes is not None:
        print(f"  Minuto modelado: {prediction.elapsed_minutes:.1f}")
    if prediction.current_score_a is not None and prediction.current_score_b is not None:
        print(f"  Marcador actual: {prediction.team_a} {prediction.current_score_a} - {prediction.current_score_b} {prediction.team_b}")
    print(
        f"  {projected_score_label(prediction)}: {projected_score_value(prediction)} | "
        f"{result_prob_label(prediction)}: {prediction.win_a:.1%} / {prediction.draw:.1%} / {prediction.win_b:.1%}"
    )
    if prediction.live_phase != "penalties":
        print(
            f"  {average_goals_label(prediction)}: {prediction.team_a} {prediction.expected_goals_a:.2f} | "
            f"{prediction.team_b} {prediction.expected_goals_b:.2f}"
        )
    if prediction.expected_remaining_goals_a is not None and prediction.expected_remaining_goals_b is not None:
        print(
            f"  Promedio estimado de goles restantes: {prediction.team_a} {prediction.expected_remaining_goals_a:.2f} | "
            f"{prediction.team_b} {prediction.expected_remaining_goals_b:.2f}"
        )
    if prediction.advance_a is not None and prediction.advance_b is not None:
        detail = prediction.knockout_detail or {}
        print(
            f"  Si llegan empatados al siguiente corte: goles esperados en prorroga {detail.get('et_xg_a', 0.0):.2f} - {detail.get('et_xg_b', 0.0):.2f}"
        )
        print(
            f"    Prorroga: {prediction.team_a} {detail.get('et_win_a', 0.0):.1%} | "
            f"seguir empatados {detail.get('et_draw', 0.0):.1%} | {prediction.team_b} {detail.get('et_win_b', 0.0):.1%}"
        )
        print(
            f"    Penales si llegan: {prediction.team_a} {detail.get('penalties_a', 0.0):.1%} | "
            f"{prediction.team_b} {detail.get('penalties_b', 0.0):.1%}"
        )
        if prediction.penalty_shootout:
            shootout = prediction.penalty_shootout
            print(
                f"    Marcador esperado en penales: {prediction.team_a} {shootout.get('avg_score_a', 0.0):.2f} | "
                f"{prediction.team_b} {shootout.get('avg_score_b', 0.0):.2f}"
            )
            print("    Marcadores de penales mas probables:")
            for score, prob in shootout.get("top_scores", []):
                print(f"      {score}: {prob:.1%}")
        print(
            f"  Clasificar: {prediction.team_a} {prediction.advance_a:.1%} | "
            f"{prediction.team_b} {prediction.advance_b:.1%}"
        )
    if prediction.live_patterns:
        print("  Patrones detectados en el partido:")
        for line in pattern_lines_from_payload(prediction.live_patterns, prediction.team_a, prediction.team_b):
            print(f"    {line[2:] if line.startswith('- ') else line}")
    if prediction.model_stack:
        agreement = float(prediction.model_stack.get("agreement", 0.0))
        print(
            "  Stack estadistico: "
            f"{prediction.model_stack.get('primary_name')} + {prediction.model_stack.get('contrast_name')} + "
            f"{prediction.model_stack.get('low_score_name')} + {prediction.model_stack.get('final_name')} "
            f"| coincidencia entre modelos {agreement:.1%}"
        )
    print("  Marcadores finales mas probables:" if prediction.advance_a is not None else "  Marcadores mas probables:")
    for score, prob in prediction.exact_scores:
        print(f"    {score}: {prob:.1%}")
    if show_factors and prediction.factors:
        print("  Factores principales (A menos B):")
        for key in sorted(prediction.factors):
            print(f"    {key}: {prediction.factors[key]:+.3f}")


def print_inferred_entry_patterns(entry: dict, prediction: MatchPrediction) -> None:
    patterns = infer_entry_patterns(entry, prediction)
    if not patterns or prediction.live_patterns:
        return
    lines = pattern_lines_from_payload(patterns, prediction.team_a, prediction.team_b)
    if not lines:
        return
    print("  Patrones detectados en el partido:")
    for line in lines:
        print(f"    {line[2:] if line.startswith('- ') else line}")


def print_monte_carlo_summary(team_a: str, team_b: str, summary: dict) -> None:
    print(f"  Monte Carlo ({summary['iterations']} iteraciones):")
    print(
        f"    Goles promedio: {team_a} {summary['avg_goals_a']:.2f} | "
        f"{team_b} {summary['avg_goals_b']:.2f}"
    )
    print(
        f"    Probabilidades simuladas de victoria/empate/derrota: {summary['win_a']:.1%} / {summary['draw']:.1%} / {summary['win_b']:.1%}"
    )
    if summary["advance_a"] is not None and summary["advance_b"] is not None:
        print(
            f"    Ir a proroga: {summary['extra_time_rate']:.1%} | "
            f"ir a penales: {summary['penalties_rate']:.1%}"
        )
        print(
            f"    Clasificar simulado: {team_a} {summary['advance_a']:.1%} | "
            f"{team_b} {summary['advance_b']:.1%}"
        )
    print("    Marcadores mas frecuentes:")
    for score, prob in summary["top_scores"]:
        print(f"      {score}: {prob:.1%}")


def print_team_profile(team: Team) -> None:
    profile = profile_for(team)
    squad = profile.squad
    history = profile.history
    fifa_note = " (proxy calibrado)" if fifa_points_are_proxy(team) else ""
    print(f"{team.name} ({pretty_status(team.status)})")
    print(f"  Elo: {team.elo:.0f}")
    print(f"  Puntos FIFA{fifa_note}: {profile.fifa_points:.1f}")
    print(f"  Ranking FIFA{fifa_note}: {profile.fifa_rank}")
    print(f"  PIB/recursos proxy: {profile.resource_index:.2f}")
    print(f"  Historia mundialista: {profile.heritage_index:.2f}")
    print(f"  Titulos del mundo: {profile.world_cup_titles}")
    print(f"  Trayectoria futbolistica: {profile.trajectory_index:.2f}")
    print(f"  Experiencia proxy del entrenador: {profile.coach_index:.2f}")
    print(f"  Quimica/cohesion: {profile.chemistry_index:.2f}")
    print(f"  Moral base: {profile.morale_base:.2f}")
    print(f"  Flexibilidad tactica: {profile.tactical_flexibility:.2f}")
    print(f"  Resiliencia de viaje: {profile.travel_resilience:.2f}")
    print(f"  Ritmo de juego: {profile.tempo:.2f}")
    print(f"  Partidos historicos desde 1990: {history.matches_since_1990}")
    print(f"  Puntos por partido desde 1990: {history.points_per_match:.2f}")
    print(f"  Puntos ponderados recientes desde 1990: {history.weighted_points_per_match:.2f}")
    print(f"  Rendimiento competitivo desde 1990: {history.competitive_points_per_match:.2f}")
    print(f"  Partidos de Mundial desde 1990: {history.world_cup_matches_since_1990}")
    print(f"  Rendimiento en Mundiales desde 1990: {history.world_cup_points_per_match:.2f}")
    print(f"  Tandas de penales desde 1990: {history.shootout_matches_since_1990}")
    print(f"  Eficacia en penales desde 1990: {history.shootout_win_rate:.2f}")
    print(f"  Fuerza historica desde 1990: {history.strength_index:.2f}")
    print(f"  Ataque historico desde 1990: {history.attack_index:.2f}")
    print(f"  Defensa historica desde 1990: {history.defense_index:.2f}")
    print(f"  Rendimiento competitivo historico: {history.competitive_index:.2f}")
    print(f"  Rendimiento mundialista moderno: {history.world_cup_index:.2f}")
    print(f"  Solidez historica en penales: {history.shootout_index:.2f}")
    print(f"  Calidad global de plantilla: {squad.squad_quality:.2f}")
    print(f"  Ataque de plantilla: {squad.attack_unit:.2f}")
    print(f"  Mediocampo/control: {squad.midfield_unit:.2f}")
    print(f"  Defensa de plantilla: {squad.defense_unit:.2f}")
    print(f"  Arquero: {squad.goalkeeper_unit:.2f}")
    print(f"  Profundidad de banco: {squad.bench_depth:.2f}")
    print(f"  Experiencia de jugadores: {squad.player_experience:.2f}")
    print(f"  Pelota parada ataque: {squad.set_piece_attack:.2f}")
    print(f"  Pelota parada defensa: {squad.set_piece_defense:.2f}")
    print(f"  Disciplina: {squad.discipline_index:.2f}")
    print(f"  Amarillas proxy por jugador: {squad.yellow_rate:.2f}")
    print(f"  Rojas proxy por jugador: {squad.red_rate:.3f}")
    print(f"  Disponibilidad: {squad.availability:.2f}")
    print(f"  Definicion: {squad.finishing:.2f}")
    print(f"  Generacion de ocasiones: {squad.shot_creation:.2f}")
    print(f"  Presion/recuperacion: {squad.pressing:.2f}")


def coalesce(value: Optional[float], fallback: float) -> float:
    return fallback if value is None else value


def coalesce_int(value: Optional[int], fallback: int) -> int:
    return fallback if value is None else value


def command_predict(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    team_a_name = resolve_team_name(args.team_a, teams)
    team_b_name = resolve_team_name(args.team_b, teams)
    home_team = resolve_optional_team_name(args.home_team, teams)
    venue_country = resolve_venue_country(args.venue_country, teams)
    payload = load_persistent_payload(Path(args.state_file), teams) if not args.ignore_state else empty_persistent_payload(teams)
    state_a = normalize_team_state(payload["teams"][team_a_name])
    state_b = normalize_team_state(payload["teams"][team_b_name])
    stage = normalize_stage_name(args.stage) if args.stage else ("round32" if args.knockout else "group")
    ctx = MatchContext(
        neutral=bool(args.neutral or home_team is None),
        home_team=home_team,
        venue_country=venue_country,
        rest_days_a=coalesce_int(args.rest_a, 4),
        rest_days_b=coalesce_int(args.rest_b, 4),
        injuries_a=coalesce(args.injuries_a, dynamic_injury_load(teams[team_a_name], state_a)),
        injuries_b=coalesce(args.injuries_b, dynamic_injury_load(teams[team_b_name], state_b)),
        altitude_m=coalesce_int(args.altitude, 0),
        travel_km_a=coalesce(args.travel_a, 0.0),
        travel_km_b=coalesce(args.travel_b, 0.0),
        knockout=stage != "group",
        morale_a=coalesce(args.morale_a, float(state_a["morale"])),
        morale_b=coalesce(args.morale_b, float(state_b["morale"])),
        yellow_cards_a=coalesce_int(args.yellow_cards_a, predictive_yellow_cards(state_a)),
        yellow_cards_b=coalesce_int(args.yellow_cards_b, predictive_yellow_cards(state_b)),
        red_suspensions_a=coalesce_int(args.red_suspensions_a, int(state_a["red_suspensions"])),
        red_suspensions_b=coalesce_int(args.red_suspensions_b, int(state_b["red_suspensions"])),
        group=args.group,
        group_points_a=coalesce_int(args.group_points_a, int(state_a["group_points"])),
        group_points_b=coalesce_int(args.group_points_b, int(state_b["group_points"])),
        group_goal_diff_a=coalesce_int(args.group_goal_diff_a, int(state_a["group_goal_diff"])),
        group_goal_diff_b=coalesce_int(args.group_goal_diff_b, int(state_b["group_goal_diff"])),
        group_matches_played_a=coalesce_int(args.group_matches_played_a, int(state_a["group_matches_played"])),
        group_matches_played_b=coalesce_int(args.group_matches_played_b, int(state_b["group_matches_played"])),
        weather_stress=coalesce(args.weather_stress, 0.0),
        importance=coalesce(args.importance, STAGE_IMPORTANCE[stage]),
    )
    prediction = predict_match(
        teams,
        team_a_name,
        team_b_name,
        ctx,
        top_scores=args.top_scores,
        include_advancement=stage != "group",
        show_factors=args.show_factors,
        state_a=state_a,
        state_b=state_b,
    )
    print_prediction(prediction, show_factors=args.show_factors)
    monte_carlo_iterations = getattr(args, "monte_carlo", 0)
    seed = getattr(args, "seed", None)
    if monte_carlo_iterations and monte_carlo_iterations > 0:
        if seed is not None:
            seed_all_rng(seed)
        summary = monte_carlo_match_summary(
            teams,
            team_a_name,
            team_b_name,
            ctx,
            monte_carlo_iterations,
            state_a=state_a,
            state_b=state_b,
        )
        print_monte_carlo_summary(team_a_name, team_b_name, summary)


def command_score_prob(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    team_a_name = resolve_team_name(args.team_a, teams)
    team_b_name = resolve_team_name(args.team_b, teams)
    home_team = resolve_optional_team_name(args.home_team, teams)
    venue_country = resolve_venue_country(args.venue_country, teams)
    payload = load_persistent_payload(Path(args.state_file), teams) if not args.ignore_state else empty_persistent_payload(teams)
    state_a = normalize_team_state(payload["teams"][team_a_name])
    state_b = normalize_team_state(payload["teams"][team_b_name])
    stage = normalize_stage_name(args.stage) if args.stage else ("round32" if args.knockout else "group")
    ctx = MatchContext(
        neutral=bool(args.neutral or home_team is None),
        home_team=home_team,
        venue_country=venue_country,
        rest_days_a=4,
        rest_days_b=4,
        injuries_a=dynamic_injury_load(teams[team_a_name], state_a),
        injuries_b=dynamic_injury_load(teams[team_b_name], state_b),
        altitude_m=0,
        travel_km_a=0.0,
        travel_km_b=0.0,
        knockout=stage != "group",
        morale_a=float(state_a["morale"]),
        morale_b=float(state_b["morale"]),
        yellow_cards_a=predictive_yellow_cards(state_a),
        yellow_cards_b=predictive_yellow_cards(state_b),
        red_suspensions_a=int(state_a["red_suspensions"]),
        red_suspensions_b=int(state_b["red_suspensions"]),
        group=args.group,
        group_points_a=int(state_a["group_points"]),
        group_points_b=int(state_b["group_points"]),
        group_goal_diff_a=int(state_a["group_goal_diff"]),
        group_goal_diff_b=int(state_b["group_goal_diff"]),
        group_matches_played_a=int(state_a["group_matches_played"]),
        group_matches_played_b=int(state_b["group_matches_played"]),
        weather_stress=0.0,
        importance=STAGE_IMPORTANCE[stage],
    )
    mu_a, mu_b = expected_goals(teams[team_a_name], teams[team_b_name], ctx, state_a=state_a, state_b=state_b)
    distribution, _ = build_model_stack(
        mu_a,
        mu_b,
        ctx,
        max_goals=max(args.goals_a, args.goals_b, 10),
        market_strength=0.30,
    )
    probability = distribution.get((args.goals_a, args.goals_b), 0.0)
    print(f"{team_a_name} vs {team_b_name}")
    print(f"  Promedio estimado de goles del modelo: {team_a_name} {mu_a:.2f} | {team_b_name} {mu_b:.2f}")
    print(f"  Probabilidad de {args.goals_a}-{args.goals_b}: {probability:.2%}")
    if stage != "group" and args.goals_a == args.goals_b:
        detail = knockout_resolution_detail(
            teams[team_a_name],
            teams[team_b_name],
            ctx,
            mu_a,
            mu_b,
            state_a=state_a,
            state_b=state_b,
        )
        print(f"  Si acaba {args.goals_a}-{args.goals_b} en 90':")
        print(
            f"    Prorroga: {team_a_name} {detail['et_win_a']:.1%} | "
            f"seguir empatados {detail['et_draw']:.1%} | {team_b_name} {detail['et_win_b']:.1%}"
        )
        print(
            f"    Penales si llegan: {team_a_name} {detail['penalties_a']:.1%} | "
            f"{team_b_name} {detail['penalties_b']:.1%}"
        )
        shootout = penalty_shootout_summary(
            teams[team_a_name],
            teams[team_b_name],
            ctx,
            penalties_context_state(ctx.morale_a, state_a),
            penalties_context_state(ctx.morale_b, state_b),
            iterations=1600,
        )
        print(
            f"    Marcador esperado en penales: {team_a_name} {shootout['avg_score_a']:.2f} | "
            f"{team_b_name} {shootout['avg_score_b']:.2f}"
        )
        print("    Marcadores de penales mas probables:")
        for score, shootout_prob in shootout["top_scores"]:
            print(f"      {score}: {shootout_prob:.1%}")


def command_power_table(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    qual_probs = qualification_probabilities(teams)
    opponent_pool = confirmed_teams(teams)
    rows = []
    for team in teams.values():
        if args.only_confirmed and team.status != "qualified":
            continue
        xgf, xga, xpts = average_opponent_metrics(team, opponent_pool)
        profile = profile_for(team)
        rows.append(
            (
                team.name,
                pretty_status(team.status),
                qual_probs[team.name],
                xgf,
                xga,
                xpts,
                profile.resource_index,
                profile.heritage_index,
                profile.coach_index,
            )
        )

    rows.sort(key=lambda item: (item[2], item[5], item[3]), reverse=True)
    print("Equipo                     Estado             Prob.Mundial  xGF   xGA   xPts  PIB   Hist  DT")
    print("-" * 92)
    for name, status, prob, xgf, xga, xpts, resource, heritage, coach in rows:
        print(
            f"{name:25} {status:17} {prob:10.1%} {xgf:5.2f} {xga:5.2f} {xpts:5.2f} "
            f"{resource:4.2f} {heritage:4.2f} {coach:4.2f}"
        )


def command_playoffs(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    exact = qualification_probabilities(teams)
    simulated = simulate_playoffs(teams, args.iterations) if args.iterations > 0 else {}
    contenders = [team for team in teams.values() if team.status in {"uefa_playoff", "fifa_playoff"}]
    contenders.sort(key=lambda team: exact[team.name], reverse=True)
    print("Equipo                     Estado             Exacta    Simulada")
    print("-" * 62)
    for team in contenders:
        simulated_prob = simulated.get(team.name, 0.0)
        print(
            f"{team.name:25} {pretty_status(team.status):17} "
            f"{exact[team.name]:7.1%} {simulated_prob:10.1%}"
        )


def command_fixtures(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    fixture_path = Path(args.path)
    fixtures = read_fixtures(fixture_path)
    payload = empty_persistent_payload(teams) if args.reset_state else load_persistent_payload(Path(args.state_file), teams)
    states = copy_states(payload)
    applied_results = set(payload.get("applied_results", []))

    for index, fixture in enumerate(fixtures):
        if fixture.get("projection_only"):
            if fixture.get("label"):
                print(f"\n{fixture['label']}")
            print("  Cruce futuro con placeholders: se omite en la actualizacion de estado.")
            continue
        try:
            fixture = resolve_fixture_names(fixture, teams)
        except SystemExit as exc:
            label = fixture.get("label", fixture.get("id", "fixture"))
            print(f"\n{label}")
            print(f"  Fixture omitido: {exc}")
            continue
        team_a = fixture["team_a"]
        team_b = fixture["team_b"]
        if team_a not in teams or team_b not in teams:
            raise SystemExit(f"Equipo no encontrado en fixture: {team_a} vs {team_b}")
        if fixture.get("label"):
            print(f"\n{fixture['label']}")
        state_a = normalize_team_state(states.get(team_a, {}))
        state_b = normalize_team_state(states.get(team_b, {}))
        ctx = context_from_fixture(fixture, teams, states)
        prediction = predict_match(
            teams,
            team_a,
            team_b,
            ctx,
            top_scores=args.top_scores,
            include_advancement=fixture_stage_name(fixture) != "group",
            show_factors=args.show_factors,
            state_a=state_a,
            state_b=state_b,
        )
        print_prediction(prediction, show_factors=args.show_factors)
        print_inferred_entry_patterns(fixture, prediction)
        result_ids = fixture_state_ids(fixture, fixture_path=fixture_path, index=index)
        result_id = result_ids[0]
        if fixture.get("update_state") and "actual_score_a" in fixture and "actual_score_b" in fixture:
            if not any(existing_id in applied_results for existing_id in result_ids):
                apply_state_updates(teams, states, fixture, ctx, prediction)
                applied_results.update(result_ids)
                print(f"  Estado actualizado automaticamente con resultado real [{result_id}]")
            else:
                print(f"  Resultado ya aplicado antes, se omite duplicado [{result_id}]")

    if not args.no_save_state:
        payload["teams"] = states
        payload["applied_results"] = sorted(applied_results)
        save_persistent_payload(Path(args.state_file), payload)
        print(f"\nEstado persistente guardado en {args.state_file}")


def command_state_show(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    payload = load_persistent_payload(Path(args.state_file), teams)
    if args.team:
        team_name = resolve_team_name(args.team, teams)
        print_state(team_name, payload["teams"][team_name])
        return

    print(f"Archivo de estado: {args.state_file}")
    print(f"IDs de resultados ya aplicados: {len(payload.get('applied_results', []))}")
    for team_name in sorted(payload["teams"]):
        state = payload["teams"][team_name]
        if not args.full and not state_has_activity(state):
            continue
        print_state(team_name, state)


def command_state_reset(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    payload = empty_persistent_payload(teams)
    save_persistent_payload(Path(args.state_file), payload)
    print(f"Estado reiniciado en {args.state_file}")


def command_list_teams(teams: Dict[str, Team]) -> None:
    for team in sorted(teams.values(), key=lambda item: (item.status, -item.elo, item.name)):
        print(f"{team.name:25} {pretty_status(team.status):17} Elo {team.elo:4.0f}")


def build_parser() -> argparse.ArgumentParser:
    return package_build_parser(
        state_file=str(STATE_FILE),
        tournament_config_file=str(TOURNAMENT_CONFIG_FILE),
        bracket_file=str(BRACKET_FILE),
        bracket_json_file=str(BRACKET_JSON_FILE),
        dashboard_html_file=str(DASHBOARD_HTML_FILE),
        dashboard_md_file=str(DASHBOARD_MD_FILE),
        fixtures_template_file=str(Path(__file__).with_name("fixtures_template.json")),
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    teams = load_teams()
    package_dispatch_command(
        args,
        teams,
        parser=parser,
        command_predict=command_predict,
        command_score_prob=command_score_prob,
        command_power_table=command_power_table,
        command_playoffs=command_playoffs,
        command_fixtures=command_fixtures,
        command_simulate_tournament=command_simulate_tournament,
        command_project_bracket=command_project_bracket,
        command_project_dashboard=command_project_dashboard,
        command_state_show=command_state_show,
        command_state_reset=command_state_reset,
        command_list_teams=command_list_teams,
        print_team_profile=print_team_profile,
        resolve_team_name=resolve_team_name,
    )


if __name__ == "__main__":
    main()
