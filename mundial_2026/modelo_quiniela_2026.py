#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import random
import re
import shutil
import tempfile
import unicodedata
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from worldcup2026.calibration import empirical_bayes_shrinkage
from worldcup2026.config import MIN_MONTE_CARLO_ITERATIONS, PARAMS
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
    ml_calibrated_score_distribution,
    model_blend_weights,
    overdispersed_score_distribution,
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
from worldcup2026.profiles.lineup import lineup_intelligence
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
    gdp_index as calculate_gdp_index,
    geography_2026_index as calculate_geography_2026_index,
    heritage_index as calculate_heritage_index,
    league_strength_index as calculate_league_strength_index,
    macro_resource_index as calculate_macro_resource_index,
    morale_base as calculate_morale_base,
    population_index as calculate_population_index,
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
HISTORICAL_FEATURES_FILE = Path(__file__).with_name("historical_features_1950.json")
TOURNAMENT_CONFIG_FILE = Path(__file__).with_name("tournament_2026_draw.json")
RUNTIME_DIR = Path(__file__).with_name("runtime")
LEGACY_STATE_FILE = Path(__file__).with_name("tournament_state_2026.json")
STATE_FILE = RUNTIME_DIR / "tournament_state_2026.json"
FACTORIALS = [math.factorial(i) for i in range(16)]
HOST_COUNTRIES = {"Canada", "Mexico", "United States"}
BRACKET_FILE = Path(__file__).with_name("llave_actual_2026.md")
BRACKET_JSON_FILE = Path(__file__).with_name("llave_actual_2026.json")
DASHBOARD_HTML_FILE = Path(__file__).with_name("dashboard_actual_2026.html")
DASHBOARD_MD_FILE = Path(__file__).with_name("reporte_actual_2026.md")
CONSENSUS_CHAMPION_PRIORS = {
    # Guardrail externo de quiniela: mezcla odds publicas/modelos publicados.
    # No reemplaza el Monte Carlo; evita que la llave se sobreconcentre en un solo favorito.
    "Spain": 0.19,
    "France": 0.15,
    "England": 0.13,
    "Argentina": 0.12,
    "Brazil": 0.11,
    "Portugal": 0.075,
    "Germany": 0.075,
    "Netherlands": 0.05,
    "Colombia": 0.018,
    "Croatia": 0.015,
    "Belgium": 0.014,
}
CONSENSUS_CHAMPION_BLEND = 0.50
CONSENSUS_CHAMPION_MIN_BLEND = 0.08
CONSENSUS_LIVE_PROGRESS_WEIGHT = 0.55
CHAMPION_MODEL_TEMPERATURE = 1.20
STRICT_REAL_INPUTS_ONLY = True
NEUTRAL_INDEX_VALUE = 0.50
PROXY_INPUT_POLICY = (
    "Solo datos reales explícitos pueden mover el modelo. "
    "Si una variable falta, se neutraliza; no se reemplaza con proxies."
)
DISABLE_PUBLIC_POPULARITY_PROXY = True
DARK_HORSE_ESTABLISHED_FAVORITES = {
    "Spain",
    "France",
    "England",
    "Argentina",
    "Brazil",
    "Germany",
}
DARK_HORSE_EXTERNAL_SIGNALS = {
    "Portugal": {
        "signal_weight": 0.95,
        "source": "Opta post-sorteo + Klement",
        "url": "https://www.si.com/soccer/opta-supercomputer-predicts-2026-world-cup-winner-groups-complete",
        "note": "No es tapado puro: aparece como candidato secundario serio y también como finalista en un modelo alternativo.",
    },
    "Netherlands": {
        "signal_weight": 0.92,
        "source": "Sports Illustrated + Klement",
        "url": "https://www.si.com/soccer/10-dark-horse-candidates-to-win-2026-world-cup",
        "note": "Tiene recorrido de tapado fuerte: varias lecturas externas lo mantienen vivo y un modelo alternativo lo proyecta campeón.",
    },
    "Morocco": {
        "signal_weight": 0.88,
        "source": "FIFA + World Soccer Talk",
        "url": "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/morocco-preview-team-profile-history",
        "note": "El antecedente de semifinales en 2022 y su continuidad competitiva justifican vigilar su ruta.",
    },
    "Colombia": {
        "signal_weight": 0.84,
        "source": "Sky Sports",
        "url": "https://www.skysports.com/football/news/11096/13621739/luis-diaz-led-colombia-labelled-a-dark-horse-for-world-cup-2026-by-nuno-espirito-santo",
        "note": "Su techo ofensivo y la lectura externa reciente la convierten en candidata para romper una rama.",
    },
    "Norway": {
        "signal_weight": 0.74,
        "source": "World Soccer Talk",
        "url": "https://worldsoccertalk.com/news/dark-horses-you-cannot-ignore-for-the-2026-fifa-world-cup/",
        "note": "Su capacidad de gol puede elevar la varianza de una eliminatoria incluso sin convertirla en favorita estructural.",
    },
    "Japan": {
        "signal_weight": 0.72,
        "source": "World Soccer Talk",
        "url": "https://worldsoccertalk.com/news/dark-horses-you-cannot-ignore-for-the-2026-fifa-world-cup/",
        "note": "La disciplina táctica y la ruta simulada pueden darle valor en cruces cerrados.",
    },
    "Ecuador": {
        "signal_weight": 0.68,
        "source": "World Soccer Talk",
        "url": "https://worldsoccertalk.com/news/dark-horses-you-cannot-ignore-for-the-2026-fifa-world-cup/",
        "note": "Perfil físico y defensivo útil para incomodar favoritos; exige confirmar que la ruta siga abierta.",
    },
}
EXTERNAL_FORECAST_BENCHMARKS = (
    {
        "name": "Goldman Sachs GIR",
        "published_at": "30 may 2026",
        "snapshot": "Post-sorteo, pretorneo",
        "champion": "Spain",
        "champion_prob": 0.257,
        "final": "Spain vs Argentina",
        "methodology": "Casi 20.000 partidos oficiales desde 1978; Elo, ataque, momentum, mentalidad y geografía. El informe prevé actualización tras cada jornada.",
        "source_url": "https://static.poder360.com.br/2026/05/Goldman-Sachs-Copa-do-Mundo-2026-30mai2026.pdf",
    },
    {
        "name": "Opta Analyst",
        "published_at": "8 dic 2025",
        "snapshot": "Pretorneo",
        "champion": "Spain",
        "champion_prob": 0.170,
        "final": "No publicado en el corte",
        "methodology": "Supercomputador Opta con ratings de equipos y simulación repetida del torneo. Sirve como control probabilístico independiente.",
        "source_url": "https://theanalyst.com/articles/spain-2026-world-cup-favourites-opta-supercomputer",
    },
    {
        "name": "PwC",
        "published_at": "9 dic 2025",
        "snapshot": "Pretorneo",
        "champion": "Spain",
        "champion_prob": 0.260,
        "final": "No publicado en el corte",
        "methodology": "Regresión logística + Bradley-Terry, variables económicas y futbolísticas, y 100.000 simulaciones de torneo.",
        "source_url": "https://www.pwc.co.uk/press-room/press-releases/research-commentary/2025/PwC-analysis-England-favourites-to-win-2026-World-Cup.html",
    },
    {
        "name": "FairCast / University of Portsmouth",
        "published_at": "14 abr 2026",
        "snapshot": "Pretorneo",
        "champion": "England",
        "champion_prob": 0.159,
        "final": "No publicado en el corte",
        "methodology": "Rating FairCast calibrado por backtesting y un millón de simulaciones. Es un contraste útil porque no coincide con el favorito principal.",
        "source_url": "https://www.port.ac.uk/news-events-and-blogs/news/computer-model-predicts-england-as-favourites-for-the-2026-fifa-world-cup",
    },
    {
        "name": "Panmure Liberum / Joachim Klement",
        "published_at": "abr 2026",
        "snapshot": "Modelo alternativo",
        "champion": "Netherlands",
        "champion_prob": None,
        "final": "Netherlands vs Portugal",
        "methodology": "Modelo macro-futbolístico alternativo con población, clima, PIB per cápita, localía y puntos FIFA. Útil como alerta de tapados, no como ancla principal.",
        "source_url": "https://assets.sbs.com.au/07/69/796b14374c579c3eae5db7ed4a6d/2026-wc-prediction.pdf",
    },
    {
        "name": "Oddschecker / mercado público",
        "published_at": "jun 2026",
        "snapshot": "Outrights de mercado",
        "champion": "Spain",
        "champion_prob": None,
        "final": "No publica llave; ordena candidatos por cuota",
        "methodology": "Consenso de cuotas públicas. Se usa como lectura de sabiduría de mercado y liquidez, no como verdad ni como sustituto del modelo.",
        "source_url": "https://www.oddschecker.com/insight/football/20260603-who-is-favourite-to-win-the-world-cup-2026-latest-team-odds",
    },
    {
        "name": "Covers / mercado de outrights",
        "published_at": "jun 2026",
        "snapshot": "Outrights de mercado",
        "champion": "France",
        "champion_prob": None,
        "final": "No publica llave; muestra bloque de favoritos",
        "methodology": "Lectura de cuotas y movimiento de favoritos. Sirve para detectar si Francia, Portugal o Brasil ganan fuerza frente al prior del modelo.",
        "source_url": "https://www.covers.com/world-cup/odds",
    },
)
DARK_HORSE_STAGE_MATCH_IDS = {
    "reach_round16": tuple(f"M{match_id}" for match_id in range(73, 89)),
    "reach_quarterfinal": tuple(f"M{match_id}" for match_id in range(89, 97)),
    "reach_semifinal": tuple(f"M{match_id}" for match_id in range(97, 101)),
    "reach_final": ("M101", "M102"),
    "champion": ("M103",),
}
GOAL_CONSENSUS_TOTAL_FIELDS = (
    "market_total_line",
    "consensus_total_goals",
    "external_total_goals",
    "external_goal_total",
    "bookmaker_total_line",
    "serious_total_line",
)
QUINIELA_BRACKET_OVERRIDES: Dict[str, dict] = {}


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
    market_value_eur_m: float = 0.0
    total_minutes_last_12_months: float = 0.0
    club_world_cup_minutes: float = 0.0
    days_since_last_match: float = 14.0
    injury_proneness: float = 0.0
    expected_threat: float = 0.0
    progressive_passes: float = 0.0
    progressive_carries: float = 0.0
    ppda: float = 0.0
    field_tilt: float = 0.0
    penalty_taker_quality: float = 0.0
    goalkeeper_penalty_save_rate: float = 0.0
    shootout_pressure_experience: float = 0.0


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
    population_millions: Optional[float] = None
    gdp_per_capita_usd: Optional[float] = None
    gdp_ppp_usd_billion: Optional[float] = None
    league_strength_index: Optional[float] = None
    top_league_minutes_share: Optional[float] = None
    avg_age: Optional[float] = None
    squad_market_value_eur_m: Optional[float] = None
    heat_humidity_load: float = 0.0
    time_zone_shift: float = 0.0
    venue_surface_adjustment: float = 0.0
    travel_cluster_difficulty: float = 0.0
    expected_threat: float = 0.0
    progressive_passes: float = 0.0
    progressive_carries: float = 0.0
    ppda: float = 0.0
    field_tilt: float = 0.0
    high_press_resistance: float = 0.0
    low_block_breaking: float = 0.0
    transition_defense: float = 0.0
    aerial_matchup_advantage: float = 0.0
    penalty_taker_quality: float = 0.0
    goalkeeper_penalty_save_rate: float = 0.0
    shootout_pressure_experience: float = 0.0
    keeper_taker_strategy_matchup: float = 0.0
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
    recent_minutes_load: float
    goalkeeper_minutes_load: float
    bench_impact: float
    squad_market_value: float
    top_5_players_value_share: float
    value_depth_ratio: float
    talent_market_index: float
    total_minutes_last_12_months: float
    club_world_cup_minutes: float
    days_since_last_match: float
    injury_proneness: float
    physical_load_index: float
    expected_threat: float
    progressive_passes: float
    progressive_carries: float
    ppda: float
    field_tilt: float
    advanced_style_index: float
    high_press_resistance: float
    low_block_breaking: float
    transition_defense: float
    aerial_matchup_advantage: float
    tactical_matchup_index: float
    penalty_taker_quality: float
    goalkeeper_penalty_save_rate: float
    shootout_pressure_experience: float
    keeper_taker_strategy_matchup: float
    penalty_granular_index: float


@dataclass(frozen=True)
class HistoricalSnapshot:
    source_names: Tuple[str, ...]
    history_start_year: int
    matches_since_start: int
    weighted_matches_since_start: float
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
    competitive_matches_since_start: int
    competitive_points_per_match: float
    competitive_goal_diff_per_match: float
    world_cup_matches_since_start: int
    world_cup_points_per_match: float
    world_cup_goal_diff_per_match: float
    shootout_matches_since_start: int
    shootout_win_rate: float
    scoreline_family_rates: Dict[str, float]
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
    population_index: float
    gdp_index: float
    league_strength_index: float
    macro_resource_index: float
    heritage_index: float
    world_cup_titles: int
    trajectory_index: float
    coach_index: float
    chemistry_index: float
    morale_base: float
    tactical_flexibility: float
    travel_resilience: float
    geography_2026_index: float
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
    heat_humidity_load: float = 0.0
    time_zone_shift_a: float = 0.0
    time_zone_shift_b: float = 0.0
    venue_surface_adjustment_a: float = 0.0
    venue_surface_adjustment_b: float = 0.0
    travel_cluster_difficulty_a: float = 0.0
    travel_cluster_difficulty_b: float = 0.0
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
    market_move_a: float = 0.0
    market_move_draw: float = 0.0
    market_move_b: float = 0.0
    lineup_confirmed_a: bool = False
    lineup_confirmed_b: bool = False
    lineup_change_count_a: int = 0
    lineup_change_count_b: int = 0
    starting_xi_a: Tuple[str, ...] = ()
    starting_xi_b: Tuple[str, ...] = ()
    lineup_strength_delta_a: float = 0.0
    lineup_strength_delta_b: float = 0.0
    lineup_attack_delta_a: float = 0.0
    lineup_attack_delta_b: float = 0.0
    lineup_defense_delta_a: float = 0.0
    lineup_defense_delta_b: float = 0.0
    lineup_goalkeeper_delta_a: float = 0.0
    lineup_goalkeeper_delta_b: float = 0.0
    lineup_coverage_a: float = 0.0
    lineup_coverage_b: float = 0.0
    lineup_intelligence_mode_a: str = "sin XI nominal"
    lineup_intelligence_mode_b: str = "sin XI nominal"
    starting_goalkeeper_a: Optional[str] = None
    starting_goalkeeper_b: Optional[str] = None
    goalkeeper_confirmed_a: bool = False
    goalkeeper_confirmed_b: bool = False
    goalkeeper_change_a: bool = False
    goalkeeper_change_b: bool = False
    live_substitutions_a: int = 0
    live_substitutions_b: int = 0
    substitution_impact_a: float = 0.0
    substitution_impact_b: float = 0.0
    referee_yellow_bias: float = 0.0
    referee_red_bias: float = 0.0
    referee_penalty_bias: float = 0.0
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
    penca_scores: Optional[List[Dict[str, float | str]]] = None
    score_guidance: Optional[Dict[str, object]] = None


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
    expected_total_goals = sum((goals_a + goals_b) * prob for (goals_a, goals_b), prob in final_dist.items())
    clean_sheet_a = sum(prob for (_, goals_b), prob in final_dist.items() if goals_b == 0)
    clean_sheet_b = sum(prob for (goals_a, _), prob in final_dist.items() if goals_a == 0)
    over_1_5 = sum(prob for (goals_a, goals_b), prob in final_dist.items() if goals_a + goals_b >= 2)
    over_2_5 = sum(prob for (goals_a, goals_b), prob in final_dist.items() if goals_a + goals_b >= 3)
    under_2_5 = 1.0 - over_2_5
    over_3_5 = sum(prob for (goals_a, goals_b), prob in final_dist.items() if goals_a + goals_b >= 4)
    under_3_5 = 1.0 - over_3_5
    top_scores = sorted(final_dist.items(), key=lambda item: item[1], reverse=True)
    top3_coverage = sum(prob for _, prob in top_scores[:3])
    top5_coverage = sum(prob for _, prob in top_scores[:5])
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
    goal_consensus_line = float(ctx.market_total_line) if ctx and ctx.market_total_line is not None else None
    goal_consensus_gap = expected_total_goals - goal_consensus_line if goal_consensus_line is not None else None
    if goal_consensus_gap is None:
        goal_consensus_status = "sin consenso externo de goles"
    elif abs(goal_consensus_gap) < 0.25:
        goal_consensus_status = "alineado"
    elif abs(goal_consensus_gap) < 0.55:
        goal_consensus_status = "ajuste moderado aplicado"
    else:
        goal_consensus_status = "ajuste fuerte aplicado"

    return {
        "confidence_index": confidence,
        "entropy_index": entropy,
        "expected_total_goals": expected_total_goals,
        "goal_consensus_line": goal_consensus_line,
        "goal_consensus_gap": goal_consensus_gap,
        "goal_consensus_status": goal_consensus_status,
        "top_outcome_prob": top_outcome_prob,
        "second_outcome_prob": second_outcome_prob,
        "both_teams_score": both_score,
        "clean_sheet_a": clean_sheet_a,
        "clean_sheet_b": clean_sheet_b,
        "over_1_5": over_1_5,
        "over_2_5": over_2_5,
        "under_2_5": under_2_5,
        "over_3_5": over_3_5,
        "under_3_5": under_3_5,
        "top3_coverage": top3_coverage,
        "top5_coverage": top5_coverage,
        "modal_margin": modal_margin,
        "modal_margin_prob": modal_margin_prob,
        "market_gap": market_gap,
        "model_agreement": model_agreement,
        "model_stack_names": (
            [
                str((model_stack or {}).get("primary_name", "")),
                str((model_stack or {}).get("contrast_name", "")),
                str((model_stack or {}).get("low_score_name", "")),
                str((model_stack or {}).get("overdispersed_name", "")),
                str((model_stack or {}).get("ml_name", "")),
                str((model_stack or {}).get("bayesian_name", "")),
                str((model_stack or {}).get("final_name", "")),
            ]
            if model_stack
            else []
        ),
        "model_stack_weights": dict((model_stack or {}).get("weights", {})) if model_stack else {},
        "market_shrink": float((model_stack or {}).get("market_shrink", 0.0)) if model_stack else 0.0,
        "outcome_temperature": float((model_stack or {}).get("outcome_temperature", 1.0)) if model_stack else 1.0,
    }


def top_factor_drivers(factors: Optional[Dict[str, float]], limit: int = 3) -> List[Tuple[str, float]]:
    if not factors:
        return []
    labels = {
        "elo_diff": "Elo dinámico",
        "fifa_strength_diff": "Ranking FIFA / puntos FIFA",
        "resource_diff": "Recursos explícitos neutralizados si faltan",
        "population_diff": "Población futbolística/económica",
        "gdp_diff": "PIB explícito",
        "league_strength_diff": "Ranking/fuerza de liga",
        "macro_resource_diff": "Recursos macro explícitos",
        "heritage_diff": "Historia mundialista",
        "historical_strength_diff": "Historia competitiva desde 1950",
        "historical_attack_diff": "Ataque histórico desde 1950",
        "historical_defense_diff": "Defensa histórica desde 1950",
        "competitive_history_diff": "Rendimiento competitivo desde 1950",
        "world_cup_history_diff": "Rendimiento en Mundiales desde 1950",
        "coach_diff": "Entrenador",
        "trajectory_diff": "Trayectoria futbolística",
        "attack_unit_diff": "Ataque",
        "midfield_diff": "Mediocampo",
        "defense_diff": "Defensa",
        "goalkeeper_diff": "Portero",
        "bench_depth_diff": "Profundidad de banco",
        "market_value_diff": "Valor de plantilla",
        "squad_market_value_raw_diff": "Valor bruto de plantilla",
        "top5_value_share_diff": "Concentración de valor top-5",
        "value_depth_ratio_diff": "Profundidad de valor de plantilla",
        "discipline_diff": "Disciplina estructural",
        "experience_diff": "Experiencia de plantilla",
        "morale_diff": "Moral",
        "home_diff": "Localía/sede",
        "travel_diff": "Viaje",
        "geography_2026_diff": "Geografía 2026: calor, huso y sedes",
        "injury_diff": "Bajas/lesiones",
        "cards_diff": "Tarjetas y suspensiones",
        "group_pressure_diff": "Presión de grupo",
        "lineup_diff": "Alineaciones",
        "lineup_strength_diff": "Calidad ponderada del XI",
        "lineup_attack_diff": "Ataque del XI confirmado",
        "lineup_defense_diff": "Defensa del XI confirmado",
        "lineup_goalkeeper_diff": "Portero del XI confirmado",
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
        "recent_xg_for_adj_diff": "xG reciente ajustado por rival",
        "recent_xga_adj_diff": "xGA reciente ajustado por rival",
        "recent_opponent_strength_diff": "Fortaleza reciente de rivales",
        "recent_minutes_load_diff": "Carga reciente de minutos",
        "physical_load_diff": "Carga física pre-Mundial",
        "club_world_cup_minutes_diff": "Minutos Mundial de Clubes",
        "days_since_last_match_diff": "Días desde último partido",
        "injury_proneness_diff": "Riesgo físico/lesiones",
        "goalkeeper_minutes_load_diff": "Carga reciente del portero",
        "bench_impact_diff": "Impacto del banquillo",
        "goalkeeper_context_diff": "Portero confirmado / cambio de portero",
        "substitution_diff": "Cambios en vivo y banco restante",
        "market_move_diff": "Movimiento reciente de cuotas",
        "referee_profile_diff": "Perfil del árbitro",
        "expected_threat_diff": "xT / amenaza esperada",
        "progressive_passes_diff": "Pases progresivos",
        "progressive_carries_diff": "Conducciones progresivas",
        "ppda_pressing_diff": "Intensidad de presión / PPDA",
        "field_tilt_diff": "Dominio territorial / field tilt",
        "advanced_style_diff": "Estilo avanzado",
        "high_press_resistance_diff": "Resistencia a presión alta",
        "low_block_breaking_diff": "Capacidad contra bloque bajo",
        "transition_defense_diff": "Defensa de transiciones",
        "aerial_matchup_diff": "Ventaja aérea",
        "tactical_matchup_diff": "Compatibilidad táctica rival",
        "penalty_taker_quality_diff": "Calidad de cobradores",
        "goalkeeper_penalty_save_rate_diff": "Portero atajando penales",
        "shootout_pressure_experience_diff": "Experiencia bajo presión en tanda",
        "penalty_granular_diff": "Penales granulares",
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


def has_real_number(value: object, *, allow_zero: bool = False) -> bool:
    if value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(number):
        return False
    return allow_zero or number > 0.0


def has_any_nonzero_team_field(team: Team, fields: Sequence[str]) -> bool:
    return any(has_real_number(getattr(team, field, None), allow_zero=False) for field in fields)


def neutral_historical_snapshot(team: Team) -> HistoricalSnapshot:
    neutral_scoreline_families = {
        "clean_sheet_win_1": 0.105,
        "clean_sheet_win_2": 0.078,
        "clean_sheet_win_3_plus": 0.047,
        "btts_win_1": 0.128,
        "btts_win_2_plus": 0.037,
        "draw_00": 0.076,
        "draw_11": 0.116,
        "draw_22_plus": 0.052,
        "clean_sheet_loss_1": 0.105,
        "clean_sheet_loss_2": 0.078,
        "clean_sheet_loss_3_plus": 0.047,
        "btts_loss_1": 0.128,
        "btts_loss_2_plus": 0.037,
        "btts": 0.498,
        "total_0_1": 0.274,
        "total_2_3": 0.487,
        "total_4_plus": 0.239,
    }
    return HistoricalSnapshot(
        source_names=(team.name, "neutral_no_proxy"),
        history_start_year=1950,
        matches_since_start=0,
        weighted_matches_since_start=0.0,
        points_per_match=1.25,
        weighted_points_per_match=1.25,
        goals_for_per_match=1.2,
        goals_against_per_match=1.2,
        goal_diff_per_match=0.0,
        weighted_goals_for_per_match=1.2,
        weighted_goals_against_per_match=1.2,
        weighted_goal_diff_per_match=0.0,
        scoring_rate=0.62,
        clean_sheet_rate=0.26,
        competitive_matches_since_start=0,
        competitive_points_per_match=1.25,
        competitive_goal_diff_per_match=0.0,
        world_cup_matches_since_start=0,
        world_cup_points_per_match=0.0,
        world_cup_goal_diff_per_match=0.0,
        shootout_matches_since_start=0,
        shootout_win_rate=0.5,
        scoreline_family_rates=neutral_scoreline_families,
        strength_index=NEUTRAL_INDEX_VALUE,
        attack_index=NEUTRAL_INDEX_VALUE,
        defense_index=NEUTRAL_INDEX_VALUE,
        competitive_index=NEUTRAL_INDEX_VALUE,
        world_cup_index=NEUTRAL_INDEX_VALUE,
        shootout_index=NEUTRAL_INDEX_VALUE,
    )


def neutral_squad_aggregate(team: Team) -> SquadAggregate:
    explicit_market_value = float(team.squad_market_value_eur_m or 0.0) if team.squad_market_value_eur_m is not None else 0.0
    explicit_top_minutes = (
        clamp(float(team.top_league_minutes_share), 0.0, 1.0)
        if team.top_league_minutes_share is not None
        else NEUTRAL_INDEX_VALUE
    )
    market_index = (
        clamp(math.log1p(explicit_market_value) / math.log1p(1600.0), 0.10, 1.0)
        if explicit_market_value > 0.0
        else NEUTRAL_INDEX_VALUE
    )
    style_fields = ("expected_threat", "progressive_passes", "progressive_carries", "ppda", "field_tilt")
    has_style = has_any_nonzero_team_field(team, style_fields)
    expected_threat_value = clamp(float(team.expected_threat), 0.0, 1.0) if has_style else NEUTRAL_INDEX_VALUE
    progressive_passes_value = clamp(float(team.progressive_passes), 0.0, 1.0) if has_style else NEUTRAL_INDEX_VALUE
    progressive_carries_value = clamp(float(team.progressive_carries), 0.0, 1.0) if has_style else NEUTRAL_INDEX_VALUE
    ppda_value = clamp(float(team.ppda), 0.0, 1.0) if has_style else NEUTRAL_INDEX_VALUE
    field_tilt_value = clamp(float(team.field_tilt), 0.0, 1.0) if has_style else NEUTRAL_INDEX_VALUE
    advanced_style_index = clamp(
        0.28 * expected_threat_value
        + 0.20 * progressive_passes_value
        + 0.18 * progressive_carries_value
        + 0.16 * ppda_value
        + 0.18 * field_tilt_value,
        0.0,
        1.0,
    )

    tactical_fields = (
        "high_press_resistance",
        "low_block_breaking",
        "transition_defense",
        "aerial_matchup_advantage",
    )
    has_tactical = has_any_nonzero_team_field(team, tactical_fields)
    high_press_resistance = (
        clamp(float(team.high_press_resistance), 0.0, 1.0) if has_tactical else NEUTRAL_INDEX_VALUE
    )
    low_block_breaking = clamp(float(team.low_block_breaking), 0.0, 1.0) if has_tactical else NEUTRAL_INDEX_VALUE
    transition_defense = clamp(float(team.transition_defense), 0.0, 1.0) if has_tactical else NEUTRAL_INDEX_VALUE
    aerial_matchup_advantage = (
        clamp(float(team.aerial_matchup_advantage), 0.0, 1.0) if has_tactical else NEUTRAL_INDEX_VALUE
    )
    tactical_matchup_index = clamp(
        0.28 * high_press_resistance
        + 0.26 * low_block_breaking
        + 0.25 * transition_defense
        + 0.21 * aerial_matchup_advantage,
        0.0,
        1.0,
    )

    penalty_fields = (
        "penalty_taker_quality",
        "goalkeeper_penalty_save_rate",
        "shootout_pressure_experience",
        "keeper_taker_strategy_matchup",
    )
    has_penalty = has_any_nonzero_team_field(team, penalty_fields)
    penalty_taker_quality = (
        clamp(float(team.penalty_taker_quality), 0.0, 1.0) if has_penalty else NEUTRAL_INDEX_VALUE
    )
    goalkeeper_penalty_save_rate = (
        clamp(float(team.goalkeeper_penalty_save_rate), 0.0, 1.0) if has_penalty else NEUTRAL_INDEX_VALUE
    )
    shootout_pressure_experience = (
        clamp(float(team.shootout_pressure_experience), 0.0, 1.0) if has_penalty else NEUTRAL_INDEX_VALUE
    )
    keeper_taker_strategy_matchup = (
        clamp(float(team.keeper_taker_strategy_matchup), -1.0, 1.0) if has_penalty else 0.0
    )
    penalty_granular_index = clamp(
        0.38 * penalty_taker_quality
        + 0.26 * goalkeeper_penalty_save_rate
        + 0.24 * shootout_pressure_experience
        + 0.12 * (0.5 + 0.5 * keeper_taker_strategy_matchup),
        0.0,
        1.0,
    )

    return SquadAggregate(
        squad_quality=NEUTRAL_INDEX_VALUE,
        attack_unit=NEUTRAL_INDEX_VALUE,
        midfield_unit=NEUTRAL_INDEX_VALUE,
        defense_unit=NEUTRAL_INDEX_VALUE,
        goalkeeper_unit=NEUTRAL_INDEX_VALUE,
        bench_depth=NEUTRAL_INDEX_VALUE,
        player_experience=NEUTRAL_INDEX_VALUE,
        set_piece_attack=NEUTRAL_INDEX_VALUE,
        set_piece_defense=NEUTRAL_INDEX_VALUE,
        discipline_index=NEUTRAL_INDEX_VALUE,
        yellow_rate=0.12,
        red_rate=0.01,
        availability=1.0,
        finishing=NEUTRAL_INDEX_VALUE,
        shot_creation=NEUTRAL_INDEX_VALUE,
        pressing=NEUTRAL_INDEX_VALUE,
        recent_minutes_load=NEUTRAL_INDEX_VALUE,
        goalkeeper_minutes_load=NEUTRAL_INDEX_VALUE,
        bench_impact=NEUTRAL_INDEX_VALUE,
        squad_market_value=explicit_market_value,
        top_5_players_value_share=NEUTRAL_INDEX_VALUE,
        value_depth_ratio=NEUTRAL_INDEX_VALUE,
        talent_market_index=clamp(0.72 * market_index + 0.28 * explicit_top_minutes, 0.08, 1.0),
        total_minutes_last_12_months=0.0,
        club_world_cup_minutes=0.0,
        days_since_last_match=14.0,
        injury_proneness=0.0,
        physical_load_index=0.0,
        expected_threat=expected_threat_value,
        progressive_passes=progressive_passes_value,
        progressive_carries=progressive_carries_value,
        ppda=ppda_value,
        field_tilt=field_tilt_value,
        advanced_style_index=advanced_style_index,
        high_press_resistance=high_press_resistance,
        low_block_breaking=low_block_breaking,
        transition_defense=transition_defense,
        aerial_matchup_advantage=aerial_matchup_advantage,
        tactical_matchup_index=tactical_matchup_index,
        penalty_taker_quality=penalty_taker_quality,
        goalkeeper_penalty_save_rate=goalkeeper_penalty_save_rate,
        shootout_pressure_experience=shootout_pressure_experience,
        keeper_taker_strategy_matchup=keeper_taker_strategy_matchup,
        penalty_granular_index=penalty_granular_index,
    )


@lru_cache(maxsize=None)
def estimated_fifa_points(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY:
        return 1500.0
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
    if STRICT_REAL_INPUTS_ONLY and team.fifa_points is None:
        return NEUTRAL_INDEX_VALUE
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
    if STRICT_REAL_INPUTS_ONLY:
        return neutral_historical_snapshot(team)
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
    if STRICT_REAL_INPUTS_ONLY:
        return NEUTRAL_INDEX_VALUE
    return calculate_resource_index(team, clamp=clamp)


@lru_cache(maxsize=None)
def population_index(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY and not has_real_number(team.population_millions):
        return NEUTRAL_INDEX_VALUE
    return calculate_population_index(
        team,
        resource_index_value=resource_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def gdp_index(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY and not (
        has_real_number(team.gdp_per_capita_usd) or has_real_number(team.gdp_ppp_usd_billion)
    ):
        return NEUTRAL_INDEX_VALUE
    return calculate_gdp_index(
        team,
        resource_index_value=resource_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def league_strength_index(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY:
        if team.league_strength_index is not None:
            return clamp(float(team.league_strength_index), 0.12, 1.0)
        if team.top_league_minutes_share is not None:
            return clamp(float(team.top_league_minutes_share), 0.0, 1.0)
        return NEUTRAL_INDEX_VALUE
    return calculate_league_strength_index(
        team,
        resource_index_value=resource_index(team),
        fifa_strength_index_value=fifa_strength_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def macro_resource_index(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY:
        components = []
        if has_real_number(team.population_millions):
            components.append(population_index(team))
        if has_real_number(team.gdp_per_capita_usd) or has_real_number(team.gdp_ppp_usd_billion):
            components.append(gdp_index(team))
        if team.league_strength_index is not None or team.top_league_minutes_share is not None:
            components.append(league_strength_index(team))
        if not components:
            return NEUTRAL_INDEX_VALUE
        return clamp(sum(components) / len(components), 0.16, 1.0)
    return calculate_macro_resource_index(
        resource_index_value=resource_index(team),
        population_index_value=population_index(team),
        gdp_index_value=gdp_index(team),
        league_strength_index_value=league_strength_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def heritage_index(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY:
        history = historical_snapshot(team)
        titles = WORLD_CUP_TITLES.get(team.name, 0)
        return clamp(
            NEUTRAL_INDEX_VALUE
            + 0.16 * centered(history.strength_index)
            + 0.12 * centered(history.world_cup_index)
            + 0.06 * centered(history.competitive_index)
            + 0.03 * titles,
            0.10,
            1.00,
        )
    return calculate_heritage_index(
        team,
        historical_snapshot=historical_snapshot,
        clamp=clamp,
        centered=centered,
    )


@lru_cache(maxsize=None)
def trajectory_index(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY:
        history = historical_snapshot(team)
        return clamp(
            NEUTRAL_INDEX_VALUE
            + 0.20 * centered(history.strength_index)
            + 0.12 * centered(history.competitive_index)
            + 0.08 * centered(history.attack_index)
            + 0.08 * centered(history.defense_index)
            + 0.05 * clamp((team.elo - 1650.0) / 350.0, -0.2, 0.4),
            0.12,
            1.00,
        )
    return calculate_trajectory_index(
        team,
        historical_snapshot=historical_snapshot,
        heritage_index_value=heritage_index(team),
        resource_index_value=resource_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def coach_index(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY:
        return NEUTRAL_INDEX_VALUE
    return calculate_coach_index(
        team,
        historical_snapshot=historical_snapshot,
        heritage_index_value=heritage_index(team),
        resource_index_value=resource_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def chemistry_index(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY:
        return NEUTRAL_INDEX_VALUE
    return calculate_chemistry_index(
        team,
        coach_index_value=coach_index(team),
        heritage_index_value=heritage_index(team),
        resource_index_value=resource_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def discipline_proxy(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY:
        return NEUTRAL_INDEX_VALUE
    return calculate_discipline_proxy(team, clamp=clamp)


@lru_cache(maxsize=None)
def tactical_flexibility(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY:
        return NEUTRAL_INDEX_VALUE
    return calculate_tactical_flexibility(
        coach_index_value=coach_index(team),
        resource_index_value=resource_index(team),
        heritage_index_value=heritage_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def morale_base(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY:
        return NEUTRAL_INDEX_VALUE
    return calculate_morale_base(
        chemistry_index_value=chemistry_index(team),
        heritage_index_value=heritage_index(team),
        coach_index_value=coach_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def travel_resilience(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY:
        return NEUTRAL_INDEX_VALUE
    return calculate_travel_resilience(
        team,
        resource_index_value=resource_index(team),
        chemistry_index_value=chemistry_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def geography_2026_index(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY and not has_any_nonzero_team_field(
        team,
        ("heat_humidity_load", "time_zone_shift", "venue_surface_adjustment", "travel_cluster_difficulty"),
    ):
        return NEUTRAL_INDEX_VALUE
    return calculate_geography_2026_index(
        team,
        travel_resilience_value=travel_resilience(team),
        resource_index_value=resource_index(team),
        clamp=clamp,
    )


@lru_cache(maxsize=None)
def tempo_proxy(team: Team) -> float:
    if STRICT_REAL_INPUTS_ONLY:
        return NEUTRAL_INDEX_VALUE
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
    if STRICT_REAL_INPUTS_ONLY:
        return ()

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
        position_value_multiplier = {"GK": 0.70, "DF": 0.86, "MF": 1.06, "FW": 1.18}[position]
        market_value_eur_m = clamp(
            (2.0 + 135.0 * (quality ** 2.55)) * position_value_multiplier * (0.72 + 0.38 * resource),
            0.35,
            210.0,
        )
        total_minutes_last_12_months = clamp(
            850.0 + 2750.0 * minutes_share + 280.0 * chemistry + rng.uniform(-260.0, 260.0),
            280.0,
            5200.0,
        )
        club_world_cup_minutes = clamp(
            (190.0 if resource > 0.72 and position in {"MF", "FW", "DF"} else 70.0 * resource)
            * minutes_share
            + rng.uniform(0.0, 80.0),
            0.0,
            720.0,
        )
        days_since_last_match = clamp(10.0 + rng.uniform(-4.0, 9.0) - 2.0 * minutes_share, 2.0, 38.0)
        injury_proneness = clamp(0.16 + 0.20 * minutes_share - 0.18 * availability + rng.uniform(-0.04, 0.08), 0.02, 0.64)
        expected_threat = clamp(0.46 * attack + 0.38 * creation + 0.10 * quality + 0.06 * trajectory, 0.02, 0.98)
        progressive_passes = clamp(0.54 * creation + 0.20 * defense + 0.16 * quality + 0.10 * coach, 0.02, 0.98)
        progressive_carries = clamp(0.42 * attack + 0.30 * creation + 0.18 * quality + 0.10 * chemistry, 0.02, 0.98)
        ppda = clamp(0.42 * defense + 0.24 * quality + 0.20 * coach + 0.14 * chemistry, 0.02, 0.98)
        field_tilt = clamp(0.36 * attack + 0.26 * creation + 0.20 * quality + 0.18 * resource, 0.02, 0.98)
        penalty_taker_quality = 0.0
        if position in {"FW", "MF"}:
            penalty_taker_quality = clamp(0.50 * attack + 0.22 * creation + 0.18 * quality + 0.10 * caps / 120.0, 0.05, 0.98)
        elif position == "DF":
            penalty_taker_quality = clamp(0.18 * attack + 0.18 * creation + 0.36 * quality + 0.28 * caps / 120.0, 0.03, 0.86)
        goalkeeper_penalty_save_rate = clamp(
            (0.45 * goalkeeping + 0.20 * defense + 0.20 * caps / 120.0 + 0.15 * coach) if position == "GK" else 0.0,
            0.0,
            0.92,
        )
        shootout_pressure_experience = clamp(0.42 * caps / 120.0 + 0.22 * heritage + 0.18 * quality + 0.18 * discipline_player, 0.04, 0.98)

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
                market_value_eur_m=market_value_eur_m,
                total_minutes_last_12_months=total_minutes_last_12_months,
                club_world_cup_minutes=club_world_cup_minutes,
                days_since_last_match=days_since_last_match,
                injury_proneness=injury_proneness,
                expected_threat=expected_threat,
                progressive_passes=progressive_passes,
                progressive_carries=progressive_carries,
                ppda=ppda,
                field_tilt=field_tilt,
                penalty_taker_quality=penalty_taker_quality,
                goalkeeper_penalty_save_rate=goalkeeper_penalty_save_rate,
                shootout_pressure_experience=shootout_pressure_experience,
            )
        )
    return tuple(players)


def sort_by(players: Sequence[Player], key_name: str) -> List[Player]:
    return sorted(players, key=lambda player: getattr(player, key_name), reverse=True)


@lru_cache(maxsize=None)
def aggregate_squad(team: Team) -> SquadAggregate:
    if STRICT_REAL_INPUTS_ONLY and not team.players:
        return neutral_squad_aggregate(team)
    return calculate_aggregate_squad(
        team,
        proxy_players_fn=(lambda selected_team: selected_team.players) if STRICT_REAL_INPUTS_ONLY else proxy_players,
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
        population_index_fn=population_index,
        gdp_index_fn=gdp_index,
        league_strength_index_fn=league_strength_index,
        macro_resource_index_fn=macro_resource_index,
        heritage_index_fn=heritage_index,
        world_cup_titles=WORLD_CUP_TITLES,
        trajectory_index_fn=trajectory_index,
        coach_index_fn=coach_index,
        chemistry_index_fn=chemistry_index,
        morale_base_fn=morale_base,
        tactical_flexibility_fn=tactical_flexibility,
        travel_resilience_fn=travel_resilience,
        geography_2026_index_fn=geography_2026_index,
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


def goal_consensus_total_line(fixture: dict) -> Optional[float]:
    for field in GOAL_CONSENSUS_TOTAL_FIELDS:
        value = fixture.get(field)
        if value is None or value == "":
            continue
        try:
            return clamp(float(value), 1.35, 4.75)
        except (TypeError, ValueError):
            continue
    return None


def goal_consensus_source(fixture: dict) -> Optional[str]:
    if fixture.get("market_total_line") is not None:
        return str(fixture.get("market_provider") or "mercado over/under")
    if fixture.get("consensus_total_goals") is not None:
        return str(fixture.get("consensus_goal_provider") or "consenso externo de goles")
    if fixture.get("external_total_goals") is not None or fixture.get("external_goal_total") is not None:
        return str(fixture.get("external_goal_provider") or "pronostico externo de goles")
    if fixture.get("bookmaker_total_line") is not None:
        return str(fixture.get("market_provider") or "bookmaker total line")
    if fixture.get("serious_total_line") is not None:
        return str(fixture.get("consensus_goal_provider") or "referencia seria de goles")
    return None


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


def recent_xg_for_signal(state: Optional[dict]) -> float:
    return clamp(state_float(state, "recent_xg_for_adj", 0.0), -1.0, 1.0)


def recent_xga_signal(state: Optional[dict]) -> float:
    return clamp(state_float(state, "recent_xga_adj", 0.0), -1.0, 1.0)


def recent_opponent_strength_signal(state: Optional[dict]) -> float:
    return clamp(state_float(state, "recent_opponent_strength", 0.0), -1.0, 1.0)


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
    model_team = replace(team, attack_bias=0.0) if STRICT_REAL_INPUTS_ONLY else team
    return calculate_attack_metric(
        model_team,
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
    model_team = replace(team, defense_bias=0.0) if STRICT_REAL_INPUTS_ONLY else team
    return calculate_defense_metric(
        model_team,
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
        recent_xg_for_signal=recent_xg_for_signal,
        recent_xga_signal=recent_xga_signal,
        recent_opponent_strength_signal=recent_opponent_strength_signal,
        group_pressure=group_pressure,
        clamp=clamp,
    )


def scoreline_family_signal(history: HistoricalSnapshot, key: str, baseline: float, scale: float) -> float:
    rate = float(history.scoreline_family_rates.get(key, baseline))
    return clamp((rate - baseline) / max(scale, 1e-6), -1.0, 1.0)


def score_shape_team_signal(profile: TeamProfile, state: Optional[dict] = None) -> Dict[str, float]:
    """Historical scoring profile used to choose better exact-score shapes.

    The expected-goals model already decides the broad strength of each side.
    This layer only changes the shape inside each W/D/L bucket: teams with a
    long-run tendency to score/concede asymmetrically get more 2-1, 3-0, 3-1
    mass when the data supports it, without changing the winner probability.
    """
    history = profile.history
    gf_signal = clamp((history.weighted_goals_for_per_match - 1.25) / 0.75, -1.0, 1.0)
    ga_signal = clamp((history.weighted_goals_against_per_match - 1.15) / 0.75, -1.0, 1.0)
    scoring_rate_signal = clamp((history.scoring_rate - 0.62) / 0.24, -1.0, 1.0)
    clean_sheet_signal = clamp((history.clean_sheet_rate - 0.26) / 0.22, -1.0, 1.0)
    attack = clamp(
        0.24 * centered(history.attack_index)
        + 0.18 * centered(profile.squad.finishing)
        + 0.16 * centered(profile.squad.shot_creation)
        + 0.14 * gf_signal
        + 0.12 * scoring_rate_signal
        + 0.10 * attack_form_signal(state)
        + 0.06 * tactical_attack_signal(state),
        -1.0,
        1.0,
    )
    defense = clamp(
        0.24 * centered(history.defense_index)
        + 0.18 * centered(profile.squad.defense_unit)
        + 0.14 * centered(profile.squad.goalkeeper_unit)
        + 0.14 * clean_sheet_signal
        - 0.10 * ga_signal
        + 0.08 * defense_form_signal(state)
        + 0.06 * tactical_defense_signal(state),
        -1.0,
        1.0,
    )
    concede = clamp(
        0.26 * ga_signal
        - 0.16 * centered(history.defense_index)
        - 0.14 * centered(profile.squad.goalkeeper_unit)
        - 0.12 * clean_sheet_signal
        + 0.10 * recent_xga_signal(state),
        -1.0,
        1.0,
    )
    high_goal = clamp(
        0.46 * attack
        + 0.22 * gf_signal
        + 0.18 * centered(profile.tempo)
        + 0.14 * tactical_tempo_signal(state),
        -1.0,
        1.0,
    )
    clean_sheet_win_2 = scoreline_family_signal(history, "clean_sheet_win_2", 0.078, 0.070)
    clean_sheet_win_3_plus = scoreline_family_signal(history, "clean_sheet_win_3_plus", 0.047, 0.055)
    btts_win = clamp(
        0.72 * scoreline_family_signal(history, "btts_win_1", 0.128, 0.100)
        + 0.28 * scoreline_family_signal(history, "btts_win_2_plus", 0.037, 0.045),
        -1.0,
        1.0,
    )
    btts_loss = clamp(
        0.72 * scoreline_family_signal(history, "btts_loss_1", 0.128, 0.100)
        + 0.28 * scoreline_family_signal(history, "btts_loss_2_plus", 0.037, 0.045),
        -1.0,
        1.0,
    )
    heavy_loss = clamp(
        0.68 * scoreline_family_signal(history, "clean_sheet_loss_3_plus", 0.047, 0.055)
        + 0.32 * scoreline_family_signal(history, "btts_loss_2_plus", 0.037, 0.045),
        -1.0,
        1.0,
    )
    btts = scoreline_family_signal(history, "btts", 0.498, 0.180)
    open_match = scoreline_family_signal(history, "total_4_plus", 0.239, 0.160)
    low_total = scoreline_family_signal(history, "total_0_1", 0.274, 0.160)
    draw_11 = scoreline_family_signal(history, "draw_11", 0.116, 0.085)
    draw_22_plus = scoreline_family_signal(history, "draw_22_plus", 0.052, 0.065)
    return {
        "attack": attack,
        "defense": defense,
        "concede": concede,
        "clean_sheet": clean_sheet_signal,
        "scoring_rate": scoring_rate_signal,
        "high_goal": high_goal,
        "clean_sheet_win_2": clean_sheet_win_2,
        "clean_sheet_win_3_plus": clean_sheet_win_3_plus,
        "btts_win": btts_win,
        "btts_loss": btts_loss,
        "heavy_loss": heavy_loss,
        "btts": btts,
        "open_match": open_match,
        "low_total": low_total,
        "draw_11": draw_11,
        "draw_22_plus": draw_22_plus,
        "strength": clamp(
            0.42 * centered(profile.fifa_strength_index)
            + 0.24 * centered(history.strength_index)
            + 0.18 * centered(profile.squad.attack_unit)
            + 0.16 * centered(profile.squad.defense_unit),
            -1.0,
            1.0,
        ),
    }


def score_shape_outcome(goals_a: int, goals_b: int) -> str:
    if goals_a > goals_b:
        return "a"
    if goals_b > goals_a:
        return "b"
    return "draw"


def score_shape_weight(
    goals_a: int,
    goals_b: int,
    mu_a: float,
    mu_b: float,
    signal_a: Dict[str, float],
    signal_b: Dict[str, float],
    ctx: MatchContext,
) -> float:
    def side_exponent(goals_for: int, goals_against: int, mu_for: float, own: Dict[str, float], opp: Dict[str, float]) -> float:
        exponent = 0.0
        if goals_for == 0:
            exponent += -0.11 * own["attack"] - 0.07 * own["scoring_rate"] + 0.08 * opp["defense"]
        elif goals_for == 1:
            exponent += -0.02 * own["high_goal"] + 0.02 * opp["defense"]
        elif goals_for == 2:
            exponent += 0.055 * own["attack"] + 0.045 * opp["concede"] + 0.025 * max(mu_for - 1.35, 0.0)
        else:
            exponent += 0.15 * own["attack"] + 0.11 * opp["concede"] + 0.07 * own["high_goal"] + 0.04 * max(mu_for - 1.45, 0.0)

        if goals_against == 0:
            exponent += 0.10 * own["defense"] + 0.08 * own["clean_sheet"] - 0.09 * opp["attack"] - 0.05 * opp["scoring_rate"]
        elif goals_against >= 2:
            exponent += 0.09 * own["concede"] + 0.08 * opp["attack"] - 0.05 * own["defense"]
        return exponent

    exponent = side_exponent(goals_a, goals_b, mu_a, signal_a, signal_b)
    exponent += side_exponent(goals_b, goals_a, mu_b, signal_b, signal_a)

    total_goals = goals_a + goals_b
    margin = abs(goals_a - goals_b)
    expected_total = mu_a + mu_b
    strength_gap = signal_a["strength"] - signal_b["strength"]
    both_score_signal = 0.5 * (
        signal_a["attack"] + signal_b["attack"] + signal_a["concede"] + signal_b["concede"]
    )

    if goals_a > goals_b and margin >= 2:
        exponent += 0.12 * max(strength_gap, 0.0) + 0.05 * max(expected_total - 2.25, 0.0)
    elif goals_b > goals_a and margin >= 2:
        exponent += 0.12 * max(-strength_gap, 0.0) + 0.05 * max(expected_total - 2.25, 0.0)
    elif margin == 1 and abs(strength_gap) > 0.22 and expected_total >= 2.35:
        exponent -= 0.045 * abs(strength_gap)

    if goals_a > 0 and goals_b > 0:
        exponent += 0.08 * both_score_signal
    if total_goals >= 4:
        exponent += 0.07 * (signal_a["high_goal"] + signal_b["high_goal"])
        exponent += 0.05 * max(expected_total - 2.65, 0.0)
    if ctx.knockout and total_goals >= 4:
        exponent -= 0.08

    # Team-specific empirical families from the traceable historical base.
    # This is deliberately a bounded correction: the expected-goals ensemble
    # still leads, but a generic 2-0 or 1-1 no longer wins only by being common.
    if goals_a == goals_b == 1:
        exponent += 0.060 * (signal_a.get("draw_11", 0.0) + signal_b.get("draw_11", 0.0))
    elif goals_a == goals_b and goals_a >= 2:
        exponent += 0.070 * (signal_a.get("draw_22_plus", 0.0) + signal_b.get("draw_22_plus", 0.0))
    elif goals_a > goals_b:
        if goals_b == 0 and margin == 2:
            exponent += 0.085 * signal_a.get("clean_sheet_win_2", 0.0)
            exponent += 0.050 * signal_b.get("heavy_loss", 0.0)
        elif goals_b == 0 and margin >= 3:
            exponent += 0.145 * signal_a.get("clean_sheet_win_3_plus", 0.0)
            exponent += 0.110 * signal_b.get("heavy_loss", 0.0)
        elif goals_b > 0:
            exponent += 0.090 * signal_a.get("btts_win", 0.0)
            exponent += 0.060 * signal_b.get("btts_loss", 0.0)
    elif goals_b > goals_a:
        if goals_a == 0 and margin == 2:
            exponent += 0.085 * signal_b.get("clean_sheet_win_2", 0.0)
            exponent += 0.050 * signal_a.get("heavy_loss", 0.0)
        elif goals_a == 0 and margin >= 3:
            exponent += 0.145 * signal_b.get("clean_sheet_win_3_plus", 0.0)
            exponent += 0.110 * signal_a.get("heavy_loss", 0.0)
        elif goals_a > 0:
            exponent += 0.090 * signal_b.get("btts_win", 0.0)
            exponent += 0.060 * signal_a.get("btts_loss", 0.0)

    if goals_a > 0 and goals_b > 0:
        exponent += 0.045 * (signal_a.get("btts", 0.0) + signal_b.get("btts", 0.0))
    if total_goals >= 4:
        exponent += 0.045 * (signal_a.get("open_match", 0.0) + signal_b.get("open_match", 0.0))
    elif total_goals <= 1:
        exponent += 0.035 * (signal_a.get("low_total", 0.0) + signal_b.get("low_total", 0.0))

    central_scores = {(1, 0), (0, 1), (2, 0), (0, 2), (1, 1)}
    if (goals_a, goals_b) in central_scores and (expected_total >= 2.55 or abs(strength_gap) >= 0.30):
        exponent -= 0.035 + 0.030 * max(expected_total - 2.55, 0.0) + 0.025 * abs(strength_gap)

    return math.exp(clamp(exponent, -0.48, 0.48))


def apply_historical_score_shape_adjustment(
    dist: Dict[Tuple[int, int], float],
    team_a: Team,
    team_b: Team,
    profile_a: TeamProfile,
    profile_b: TeamProfile,
    mu_a: float,
    mu_b: float,
    ctx: MatchContext,
    *,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
    strength: float = 0.42,
) -> Tuple[Dict[Tuple[int, int], float], Dict[str, object]]:
    strength = clamp(strength, 0.0, 1.0)
    if strength <= 0.0 or not dist:
        return dict(dist), {"applied": False, "strength": 0.0}

    signal_a = score_shape_team_signal(profile_a, state_a)
    signal_b = score_shape_team_signal(profile_b, state_b)
    original_bucket = {"a": 0.0, "draw": 0.0, "b": 0.0}
    for (goals_a, goals_b), prob in dist.items():
        original_bucket[score_shape_outcome(goals_a, goals_b)] += float(prob)

    raw: Dict[Tuple[int, int], float] = {}
    raw_bucket = {"a": 0.0, "draw": 0.0, "b": 0.0}
    for (goals_a, goals_b), prob in dist.items():
        base_weight = score_shape_weight(goals_a, goals_b, mu_a, mu_b, signal_a, signal_b, ctx)
        weight = 1.0 + strength * (base_weight - 1.0)
        adjusted = max(float(prob) * clamp(weight, 0.72, 1.30), 0.0)
        outcome = score_shape_outcome(goals_a, goals_b)
        raw[(goals_a, goals_b)] = adjusted
        raw_bucket[outcome] += adjusted

    adjusted_dist: Dict[Tuple[int, int], float] = {}
    for score, prob in raw.items():
        outcome = score_shape_outcome(*score)
        if raw_bucket[outcome] <= 0.0:
            adjusted_dist[score] = float(dist.get(score, 0.0))
        else:
            adjusted_dist[score] = prob * original_bucket[outcome] / raw_bucket[outcome]

    total = sum(adjusted_dist.values())
    if total > 0.0:
        for key in list(adjusted_dist):
            adjusted_dist[key] /= total

    top_before_pair, top_before_prob = max(dist.items(), key=lambda item: item[1])
    top_after_pair, top_after_prob = max(adjusted_dist.items(), key=lambda item: item[1])
    stronger_is_a = signal_a["strength"] >= signal_b["strength"]
    favorite_name = team_a.name if stronger_is_a else team_b.name
    favorite_signal = signal_a if stronger_is_a else signal_b
    rival_signal = signal_b if stronger_is_a else signal_a
    if favorite_signal["clean_sheet_win_3_plus"] > 0.12 and rival_signal["heavy_loss"] > -0.10:
        label = "histórico por equipo respalda una ventaja amplia con portería a cero"
    elif favorite_signal["btts_win"] > 0.08 and rival_signal["btts_loss"] > -0.08:
        label = "histórico por equipo respalda triunfo con goles de ambos"
    elif favorite_signal["attack"] > 0.10 and rival_signal["concede"] > 0.05:
        label = "favorece ventajas más amplias si el favorito domina"
    elif signal_a["attack"] > 0.05 and signal_b["attack"] > 0.05 and (signal_a["concede"] + signal_b["concede"]) > -0.10:
        label = "sube escenarios donde ambos equipos anotan"
    elif favorite_signal["defense"] > 0.12 and rival_signal["attack"] < 0.02:
        label = "refuerza marcadores con portería a cero del favorito"
    else:
        label = "mantiene marcador conservador, pero corrige por perfil histórico"

    meta = {
        "applied": True,
        "strength": strength,
        "label": label,
        "favorite_name": favorite_name,
        "favorite_is_a": stronger_is_a,
        "top_before": f"{top_before_pair[0]}-{top_before_pair[1]}",
        "top_before_prob": float(top_before_prob),
        "top_after": f"{top_after_pair[0]}-{top_after_pair[1]}",
        "top_after_prob": float(top_after_prob),
        "attack_signal_a": signal_a["attack"],
        "attack_signal_b": signal_b["attack"],
        "concede_signal_a": signal_a["concede"],
        "concede_signal_b": signal_b["concede"],
        "scoreline_signal_a": dict(signal_a),
        "scoreline_signal_b": dict(signal_b),
        "favorite_clean_sheet_win_2_signal": favorite_signal["clean_sheet_win_2"],
        "favorite_clean_sheet_win_3_plus_signal": favorite_signal["clean_sheet_win_3_plus"],
        "favorite_btts_win_signal": favorite_signal["btts_win"],
        "rival_heavy_loss_signal": rival_signal["heavy_loss"],
        "rival_btts_loss_signal": rival_signal["btts_loss"],
        "scoreline_family_note": (
            "La recomendación exacta usa familias empíricas por selección con shrinkage bayesiano: "
            "victorias amplias con portería a cero, triunfos con goles de ambos, empates y derrotas amplias."
        ),
        "historical_sample_a": float(profile_a.history.weighted_matches_since_start),
        "historical_sample_b": float(profile_b.history.weighted_matches_since_start),
        "historical_data_note": (
            f"{team_a.name}: {profile_a.history.matches_since_start} partidos desde {profile_a.history.history_start_year}; "
            f"{team_b.name}: {profile_b.history.matches_since_start} partidos desde {profile_b.history.history_start_year}"
        ),
    }
    return adjusted_dist, meta


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
        recent_xg_for_signal=recent_xg_for_signal,
        recent_xga_signal=recent_xga_signal,
        recent_opponent_strength_signal=recent_opponent_strength_signal,
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
    cutoff = weights["primary"]
    if roll < cutoff:
        return correlated_sample_score(mu_a, mu_b, ctx)
    cutoff += weights["contrast"]
    if roll < cutoff:
        return independent_sample_score(mu_a, mu_b)
    cutoff += weights.get("low_score", 0.0)
    if roll < cutoff:
        rho = low_score_rho(mu_a, mu_b, ctx)
        low_score_dist = cached_low_score_distribution(
            int(round(mu_a * 20.0)),
            int(round(mu_b * 20.0)),
            int(round(rho * 100.0)),
            7,
        )
        return _sample_from_distribution(low_score_dist)
    cutoff += weights.get("overdispersed", 0.0)
    if roll < cutoff:
        return _sample_from_distribution(overdispersed_score_distribution(mu_a, mu_b, ctx, max_goals=7))
    return _sample_from_distribution(ml_calibrated_score_distribution(mu_a, mu_b, ctx, max_goals=7))


def penalties_context_state(ctx_morale: float, state: Optional[dict]) -> dict:
    penalties_state = normalize_team_state(state)
    penalties_state["morale"] = clamp(ctx_morale, -1.0, 1.0)
    return penalties_state


def simulation_state_signature(state: Optional[dict]) -> Tuple[float, ...]:
    return package_coerce_team_state(state).simulation_signature()


def simulation_state_from_signature(signature: Tuple[float, ...]) -> dict:
    fields = (
        "elo_shift",
        "recent_form",
        "attack_form",
        "defense_form",
        "fatigue",
        "availability",
        "discipline_drift",
        "recent_xg_for_adj",
        "recent_xga_adj",
        "recent_opponent_strength",
        "style_attack_bias",
        "style_defense_bias",
        "style_tempo",
        "expected_threat_live",
        "progressive_passes_live",
        "progressive_carries_live",
        "ppda_live",
        "field_tilt_live",
        "high_press_resistance_live",
        "low_block_breaking_live",
        "transition_defense_live",
        "aerial_matchup_advantage_live",
    )
    defaults = {
        "availability": 1.0,
    }
    reconstructed = {
        field: float(signature[index]) if index < len(signature) else float(defaults.get(field, 0.0))
        for index, field in enumerate(fields)
    }
    return {
        key: value
        for key, value in reconstructed.items()
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
    profile_a = profile_for(team_a)
    profile_b = profile_for(team_b)
    mu_a, mu_b = expected_goals(team_a, team_b, ctx, state_a=state_a, state_b=state_b)
    dist, model_stack = build_model_stack(mu_a, mu_b, ctx, max_goals=10, market_strength=0.30)
    dist, score_shape_meta = apply_historical_score_shape_adjustment(
        dist,
        team_a,
        team_b,
        profile_a,
        profile_b,
        mu_a,
        mu_b,
        ctx,
        state_a=state_a,
        state_b=state_b,
        strength=0.46,
    )
    if model_stack is not None:
        model_stack = dict(model_stack)
        top_pair, top_prob = max(dist.items(), key=lambda item: item[1])
        model_stack["score_shape_adjustment"] = score_shape_meta
        model_stack["final_name"] = "Ensamble + asimetría histórica"
        model_stack["ensemble_top_score"] = (f"{top_pair[0]}-{top_pair[1]}", float(top_prob))

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
    penca_scores = penca_ovacion_score_options(dist, top_scores, score_shape_meta=score_shape_meta)
    score_guidance = score_precision_profile(dist, penca_scores, score_shape_meta)
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
        penca_scores=penca_scores,
        score_guidance=score_guidance,
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
    profile_a = profile_for(team_a)
    profile_b = profile_for(team_b)
    base_mu_a, base_mu_b = expected_goals(team_a, team_b, ctx, state_a=state_a, state_b=state_b)
    elapsed_minutes, phase = parse_elapsed_minutes(status_detail, ctx.knockout)
    patterns = None
    live_stats = dict(live_stats or {})
    live_stats["substitutions_a"] = max(float(live_stats.get("substitutions_a", 0.0)), float(ctx.live_substitutions_a))
    live_stats["substitutions_b"] = max(float(live_stats.get("substitutions_b", 0.0)), float(ctx.live_substitutions_b))
    live_stats["substitution_impact_a"] = float(ctx.substitution_impact_a)
    live_stats["substitution_impact_b"] = float(ctx.substitution_impact_b)
    live_stats["bench_remaining_a"] = clamp(
        profile_a.squad.bench_impact * max(0.0, 1.0 - float(ctx.live_substitutions_a) / 5.0),
        0.0,
        1.0,
    )
    live_stats["bench_remaining_b"] = clamp(
        profile_b.squad.bench_impact * max(0.0, 1.0 - float(ctx.live_substitutions_b) / 5.0),
        0.0,
        1.0,
    )

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
        penca_scores = penca_ovacion_score_options(final_dist, top_scores)
        return MatchPrediction(
            team_a=team_a_name,
            team_b=team_b_name,
            expected_goals_a=float(current_score_a),
            expected_goals_b=float(current_score_b),
            win_a=0.0,
            draw=1.0,
            win_b=0.0,
            exact_scores=[(f"{current_score_a}-{current_score_b}", 1.0)],
            penca_scores=penca_scores,
            score_guidance=score_precision_profile(final_dist, penca_scores),
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
        final_dist, score_shape_meta = apply_historical_score_shape_adjustment(
            final_dist,
            team_a,
            team_b,
            profile_a,
            profile_b,
            current_score_a + rem_mu_a,
            current_score_b + rem_mu_b,
            ctx,
            state_a=state_a,
            state_b=state_b,
            strength=0.18 * (1.0 - progress),
        )
        if model_stack is not None:
            model_stack = dict(model_stack)
            top_pair, top_prob = max(final_dist.items(), key=lambda item: item[1])
            model_stack["score_shape_adjustment"] = score_shape_meta
            model_stack["final_name"] = "Ensamble live + asimetría histórica"
            model_stack["ensemble_top_score"] = (f"{top_pair[0]}-{top_pair[1]}", float(top_prob))
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
        penca_scores = penca_ovacion_score_options(final_dist, top_scores)
        return MatchPrediction(
            team_a=team_a_name,
            team_b=team_b_name,
            expected_goals_a=current_score_a + rem_mu_a,
            expected_goals_b=current_score_b + rem_mu_b,
            win_a=win_a,
            draw=draw,
            win_b=win_b,
            exact_scores=exact[:top_scores],
            penca_scores=penca_scores,
            score_guidance=score_precision_profile(final_dist, penca_scores, score_shape_meta),
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
    final_dist, score_shape_meta = apply_historical_score_shape_adjustment(
        final_dist,
        team_a,
        team_b,
        profile_a,
        profile_b,
        current_score_a + rem_mu_a,
        current_score_b + rem_mu_b,
        ctx,
        state_a=state_a,
        state_b=state_b,
        strength=0.46 * (1.0 - progress),
    )
    if model_stack is not None:
        model_stack = dict(model_stack)
        top_pair, top_prob = max(final_dist.items(), key=lambda item: item[1])
        model_stack["score_shape_adjustment"] = score_shape_meta
        model_stack["final_name"] = "Ensamble live + asimetría histórica"
        model_stack["ensemble_top_score"] = (f"{top_pair[0]}-{top_pair[1]}", float(top_prob))

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
    penca_scores = penca_ovacion_score_options(final_dist, top_scores)

    return MatchPrediction(
        team_a=team_a_name,
        team_b=team_b_name,
        expected_goals_a=current_score_a + rem_mu_a,
        expected_goals_b=current_score_b + rem_mu_b,
        win_a=win_a,
        draw=draw,
        win_b=win_b,
        exact_scores=exact[:top_scores],
        penca_scores=penca_scores,
        score_guidance=score_precision_profile(final_dist, penca_scores, score_shape_meta),
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


LIVE_STATUS_STATES = {
    "in",
    "live",
    "in_progress",
    "in-progress",
    "halftime",
    "half_time",
    "half-time",
    "ht",
    "extra_time",
    "extra-time",
    "et",
    "penalties",
    "shootout",
}
FINAL_STATUS_STATES = {
    "post",
    "final",
    "finished",
    "full_time",
    "full-time",
    "ft",
    "aet",
    "after_extra_time",
    "after-extra-time",
    "penalties_final",
    "after_penalties",
    "after-penalties",
}


def normalized_match_status_state(status_state: Optional[str]) -> str:
    status = str(status_state or "").strip().lower()
    if status in LIVE_STATUS_STATES:
        return "live"
    if status in FINAL_STATUS_STATES:
        return "final"
    return "pending"


def fixture_is_live(entry: dict) -> bool:
    return normalized_match_status_state(entry.get("status_state")) == "live"


def fixture_is_final(entry: dict) -> bool:
    return normalized_match_status_state(entry.get("status_state")) == "final"


def fixture_has_live_score(entry: dict) -> bool:
    return entry.get("live_score_a") is not None and entry.get("live_score_b") is not None


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
        simulation_score_sampler=sample_simulation_scoreline,
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


def ensure_minimum_monte_carlo_iterations(iterations: int, *, label: str, allow_zero: bool = False) -> None:
    if allow_zero and iterations == 0:
        return
    if iterations < MIN_MONTE_CARLO_ITERATIONS:
        raise SystemExit(
            f"{label} requiere al menos {MIN_MONTE_CARLO_ITERATIONS} simulaciones Monte Carlo; recibió {iterations}."
        )


def command_simulate_tournament(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    ensure_minimum_monte_carlo_iterations(args.iterations, label="simulate-tournament")
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
    slot_winner, slot_winner_count = max(aggregate["winner"].items(), key=lambda item: item[1])
    primary_matchup = matchup_scenarios[0]
    team_a = primary_matchup["team_a"]
    team_b = primary_matchup["team_b"]
    matchup_favorite = primary_matchup["winner"]
    matchup_favorite_prob = primary_matchup["conditional_winner_prob"]
    matchup_favorite_overall_prob = primary_matchup["winner_prob"]
    winner = matchup_favorite
    winner_row = next(
        (
            row
            for row in primary_matchup.get("conditional_winners", [])
            if row.get("team") == winner
        ),
        None,
    )
    conditional_winner_prob = (
        float(winner_row.get("conditional_prob", primary_matchup["conditional_winner_prob"]))
        if winner_row
        else float(primary_matchup["conditional_winner_prob"])
    )
    winner_prob = (
        float(primary_matchup["winner_prob"])
    )
    penalty_scores = sorted(aggregate.get("penalty_scores", {}).items(), key=lambda item: item[1], reverse=True)[:3]
    return {
        "match_id": match_id,
        "title": BRACKET_MATCH_TITLES.get(match_id, match_id),
        "stage": stage_for_match_id(match_id),
        "team_a": team_a,
        "team_b": team_b,
        "winner": winner,
        "matchup_prob": primary_matchup["matchup_prob"],
        "conditional_winner_prob": conditional_winner_prob,
        "winner_prob": winner_prob,
        "global_slot_winner": slot_winner,
        "global_slot_winner_prob": float(slot_winner_count) / float(iterations),
        "matchup_favorite": matchup_favorite,
        "matchup_favorite_prob": matchup_favorite_prob,
        "matchup_favorite_overall_prob": matchup_favorite_overall_prob,
        "slot_winner_mode": "conditional_favorite",
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
    conditional_winner_prob = projection.get("conditional_winner_prob", winner_prob)
    extra_time_prob = projection["extra_time_prob"]
    penalties_prob = projection["penalties_prob"]
    lines = [
        f"### {BRACKET_MATCH_TITLES.get(match_id, match_id)}",
        f"- Cruce usado para este casillero: {team_a} vs {team_b}",
        f"- Probabilidad de que este cruce ocurra: {outcome_prob:.1%}",
        f"- Ganador proyectado del casillero: {winner} ({winner_prob:.1%} global)",
    ]
    matchup_favorite = projection.get("matchup_favorite", winner)
    matchup_favorite_prob = float(projection.get("matchup_favorite_prob", conditional_winner_prob) or 0.0)
    if matchup_favorite == winner:
        lines.append(f"- Si se juega ese cruce, {winner} avanza {conditional_winner_prob:.1%}.")
    else:
        lines.append(
            f"- Nota de lectura: en ese cruce específico el favorito condicional es "
            f"{matchup_favorite} ({matchup_favorite_prob:.1%}), pero {winner} es quien más sale "
            "del casillero al sumar todas las rutas simuladas."
        )
    alternatives = [
        f"{scenario['team_a']} vs {scenario['team_b']} | gana más probable {scenario['winner']} | este escenario aparece {scenario['prob']:.1%}"
        for scenario in projection.get("top_scenarios", [])[1:]
    ]
    if alternatives:
        lines.append(f"- Otros cruces que también aparecen seguido: {'; '.join(alternatives)}")
    if match_id != "M104":
        lines.append(f"- Va a proroga en {extra_time_prob:.1%} y a penales en {penalties_prob:.1%}")
        penalty_scores = projection.get("top_penalty_scores", [])
        if penalty_scores:
            lines.append(
                "- Marcadores de penales más probables en este cruce: "
                + "; ".join(f"{item['score']} ({item['prob']:.1%})" for item in penalty_scores)
            )
    return lines


def command_project_bracket(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    ensure_minimum_monte_carlo_iterations(args.iterations, label="project-bracket")
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
        "scoreline_engine": "ensamble_no_solo_poisson_bayes_dinamico_v2",
        "input_data_policy": "solo_datos_reales_explicitos",
        "proxy_input_policy": PROXY_INPUT_POLICY,
        "strict_real_inputs_only": STRICT_REAL_INPUTS_ONLY,
        "public_popularity_proxy_enabled": not DISABLE_PUBLIC_POPULARITY_PROXY,
        "bracket_recalculated_from_scoreline_ensemble": True,
        "recalculation_policy": (
            f"Los marcadores directos se refrescan cada 5 minutos. La llave completa se reconstruye con "
            f"{args.iterations:,} simulaciones en esta corrida. Si aparece 15.000, es solo el mínimo técnico "
            "del carril horario para no publicar corridas débiles; el snapshot principal de alta estabilidad "
            "usa 100.000 simulaciones y corre cada 8 horas/manual/push relevante por costo de cómputo. "
            "Si cambian marcadores, estados o señales relevantes, se propagan primero en el tablero live "
            "de 5 minutos y después en la siguiente corrida profunda."
        ).replace(",", "."),
        "matches": {
            match_id: structured_match_projection(match_id, aggregate, args.iterations)
            for match_id, aggregate in match_aggregate.items()
        },
    }
    structured["matches"] = coherent_bracket_matches(structured)
    output_path = Path(args.output)
    output_json_path = Path(args.json_output)
    output_path.write_text(content)
    output_json_path.write_text(json.dumps(structured, indent=2))
    print(f"Llave proyectada guardada en {output_path} | workers={workers}")
    print(f"Llave estructurada guardada en {output_json_path}")
    print(content)


def format_pct(value: float) -> str:
    return f"{value:.1%}"


def conditional_winner_rows(matchup: dict) -> List[dict]:
    rows = matchup.get("conditional_winners") or []
    return [row for row in rows if row.get("team")]


def conditional_winner_for_team(matchup: dict, team: str) -> Optional[dict]:
    for row in conditional_winner_rows(matchup):
        if row.get("team") == team:
            return row
    return None


def quiniela_override_for_match(match_id: str, matchup: dict, selected_winner: str) -> Optional[dict]:
    override = QUINIELA_BRACKET_OVERRIDES.get(match_id)
    if not override:
        return None
    teams = {matchup.get("team_a"), matchup.get("team_b")}
    if teams != set(override["teams"]):
        return None
    target = str(override["winner"])
    if selected_winner == target:
        return None
    rows = conditional_winner_rows(matchup)
    if not rows:
        return None
    target_row = conditional_winner_for_team(matchup, target)
    if target_row is None:
        return None
    top_prob = float(rows[0].get("conditional_prob", 0.0) or 0.0)
    target_prob = float(target_row.get("conditional_prob", 0.0) or 0.0)
    model_edge = max(0.0, top_prob - target_prob)
    if model_edge > float(override.get("max_model_edge", 0.0)):
        return None
    return {
        "winner": target,
        "conditional_prob": target_prob,
        "overall_prob": float(target_row.get("overall_prob", 0.0) or 0.0),
        "model_winner": selected_winner,
        "model_winner_prob": top_prob,
        "model_edge": model_edge,
        "reason": str(override.get("reason", "")),
    }


def champion_probabilities_from_bracket(bracket_payload: dict) -> Dict[str, float]:
    final_match = (bracket_payload.get("matches") or {}).get("M103", {})
    raw = final_match.get("advance_probabilities") or {}
    return {
        str(team): float(prob)
        for team, prob in raw.items()
        if float(prob or 0.0) > 0.0
    }


def consensus_distribution_for_teams(team_names: Sequence[str], model_probs: Dict[str, float]) -> Dict[str, float]:
    explicit = {
        team: float(CONSENSUS_CHAMPION_PRIORS[team])
        for team in team_names
        if team in CONSENSUS_CHAMPION_PRIORS
    }
    explicit_sum = sum(explicit.values())
    missing = [team for team in team_names if team not in explicit]
    missing_model_sum = sum(model_probs.get(team, 0.0) for team in missing)
    remaining = max(0.0, 1.0 - explicit_sum)
    consensus = dict(explicit)
    if missing:
        for team in missing:
            share = model_probs.get(team, 0.0) / missing_model_sum if missing_model_sum > 0 else 1.0 / len(missing)
            consensus[team] = remaining * share
    total = sum(consensus.values())
    if total <= 0:
        return {team: 1.0 / max(len(team_names), 1) for team in team_names}
    return {team: value / total for team, value in consensus.items()}


def temperature_calibrated_champion_model(
    model_probs: Dict[str, float],
    temperature: float = CHAMPION_MODEL_TEMPERATURE,
) -> Dict[str, float]:
    """Flatten champion probabilities before external blending.

    The tournament Monte Carlo already combines Elo/FIFA/squad/history/path. A mild
    temperature keeps the public champion table from treating correlated strength
    signals as independent certainty, while preserving the raw model probability
    separately for auditability.
    """
    total = sum(max(float(value), 0.0) for value in model_probs.values())
    if total <= 0:
        return {}
    normalized = {team: max(float(value), 0.0) / total for team, value in model_probs.items()}
    if temperature <= 1.0:
        return normalized
    powered = {
        team: (prob ** (1.0 / temperature)) if prob > 0 else 0.0
        for team, prob in normalized.items()
    }
    powered_total = sum(powered.values())
    if powered_total <= 0:
        return normalized
    return {team: value / powered_total for team, value in powered.items()}


def consensus_live_update_context(entries: Optional[Sequence[dict]] = None) -> dict:
    fixture_entries = [entry for entry in entries or [] if not entry.get("projection")]
    total = len(fixture_entries)
    live_count = sum(1 for entry in fixture_entries if fixture_is_live(entry))
    final_count = sum(1 for entry in fixture_entries if fixture_is_final(entry))
    pending_count = max(total - live_count - final_count, 0)
    weighted_progress = (
        clamp((final_count + CONSENSUS_LIVE_PROGRESS_WEIGHT * live_count) / total, 0.0, 1.0)
        if total
        else 0.0
    )
    consensus_blend = clamp(
        CONSENSUS_CHAMPION_BLEND * (1.0 - 0.84 * weighted_progress),
        CONSENSUS_CHAMPION_MIN_BLEND,
        CONSENSUS_CHAMPION_BLEND,
    )
    return {
        "total": total,
        "live_count": live_count,
        "final_count": final_count,
        "pending_count": pending_count,
        "weighted_progress": weighted_progress,
        "consensus_blend": consensus_blend,
        "model_blend": 1.0 - consensus_blend,
    }


def consensus_champion_blend(entries: Optional[Sequence[dict]] = None) -> float:
    return float(consensus_live_update_context(entries)["consensus_blend"])


def consensus_adjusted_champion_probabilities(bracket_payload: dict, entries: Optional[Sequence[dict]] = None) -> List[dict]:
    model_probs = champion_probabilities_from_bracket(bracket_payload)
    if not model_probs:
        return []
    team_names = sorted(model_probs)
    consensus = consensus_distribution_for_teams(team_names, model_probs)
    model_total = sum(model_probs.values())
    normalized_model = {team: value / model_total for team, value in model_probs.items()} if model_total > 0 else model_probs
    calibrated_model = temperature_calibrated_champion_model(normalized_model)
    consensus_blend = consensus_champion_blend(entries)
    model_blend = 1.0 - consensus_blend
    rows = []
    for team in team_names:
        model_prob = float(normalized_model.get(team, 0.0))
        calibrated_model_prob = float(calibrated_model.get(team, model_prob))
        consensus_prob = float(consensus.get(team, 0.0))
        adjusted = model_blend * calibrated_model_prob + consensus_blend * consensus_prob
        rows.append(
            {
                "team": team,
                "model_prob": model_prob,
                "calibrated_model_prob": calibrated_model_prob,
                "consensus_prob": consensus_prob,
                "adjusted_prob": adjusted,
                "delta": calibrated_model_prob - consensus_prob,
                "raw_delta": model_prob - consensus_prob,
                "overconfidence_adjustment": calibrated_model_prob - model_prob,
                "champion_model_temperature": CHAMPION_MODEL_TEMPERATURE,
                "model_blend": model_blend,
                "consensus_blend": consensus_blend,
            }
        )
    total = sum(row["adjusted_prob"] for row in rows)
    if total > 0:
        for row in rows:
            row["adjusted_prob"] = float(row["adjusted_prob"]) / total
    return sorted(rows, key=lambda row: row["adjusted_prob"], reverse=True)


def bracket_stage_team_probabilities(bracket_payload: dict, match_ids: Sequence[str]) -> Dict[str, float]:
    totals: Dict[str, float] = {}
    matches = bracket_payload.get("matches") or {}
    for match_id in match_ids:
        raw = (matches.get(match_id) or {}).get("advance_probabilities") or {}
        for team, prob in raw.items():
            name = str(team)
            totals[name] = totals.get(name, 0.0) + float(prob or 0.0)
    return {team: clamp(prob, 0.0, 1.0) for team, prob in totals.items()}


def dark_horse_candidates(bracket_payload: dict, entries: Optional[Sequence[dict]] = None) -> List[dict]:
    adjusted_rows = consensus_adjusted_champion_probabilities(bracket_payload, entries)
    if not adjusted_rows:
        return []
    adjusted_map = {str(row["team"]): row for row in adjusted_rows}
    stage_maps = {
        stage: bracket_stage_team_probabilities(bracket_payload, match_ids)
        for stage, match_ids in DARK_HORSE_STAGE_MATCH_IDS.items()
    }
    team_names = sorted(
        set(adjusted_map)
        | set(DARK_HORSE_EXTERNAL_SIGNALS)
        | {team for stage_map in stage_maps.values() for team in stage_map}
    )
    candidates = []
    for team in team_names:
        if team in DARK_HORSE_ESTABLISHED_FAVORITES:
            continue
        adjusted_row = adjusted_map.get(team, {})
        model_prob = float(adjusted_row.get("model_prob", stage_maps["champion"].get(team, 0.0)) or 0.0)
        consensus_prob = float(adjusted_row.get("consensus_prob", 0.0) or 0.0)
        adjusted_prob = float(adjusted_row.get("adjusted_prob", model_prob) or 0.0)
        quarterfinal_prob = float(stage_maps["reach_quarterfinal"].get(team, 0.0) or 0.0)
        semifinal_prob = float(stage_maps["reach_semifinal"].get(team, 0.0) or 0.0)
        final_prob = float(stage_maps["reach_final"].get(team, 0.0) or 0.0)
        external = DARK_HORSE_EXTERNAL_SIGNALS.get(team)
        has_live_route = adjusted_prob >= 0.0025 or semifinal_prob >= 0.015 or quarterfinal_prob >= 0.045
        if not has_live_route:
            continue
        if external is None and adjusted_prob < 0.008 and semifinal_prob < 0.045:
            continue
        if adjusted_prob >= 0.045 or semifinal_prob >= 0.15:
            tier = "Candidato secundario"
            action = "Mantener como alternativa real de llave y revisar antes de cada eliminatoria."
        elif adjusted_prob >= 0.012 or semifinal_prob >= 0.065:
            tier = "Tapado serio"
            action = "Vigilar su rama: puede justificar cobertura si enfrenta a un favorito en un cruce cerrado."
        else:
            tier = "Tapado de mayor varianza"
            action = "No sustituye la llave base; usarlo como alerta de sorpresa si la ruta y el live lo favorecen."
        external_weight = float((external or {}).get("signal_weight", 0.0) or 0.0)
        watch_index = 100.0 * clamp(
            0.34 * min(adjusted_prob / 0.07, 1.0)
            + 0.26 * min(semifinal_prob / 0.18, 1.0)
            + 0.16 * min(final_prob / 0.10, 1.0)
            + 0.14 * min(quarterfinal_prob / 0.30, 1.0)
            + 0.10 * external_weight,
            0.0,
            1.0,
        )
        delta = model_prob - consensus_prob
        adjusted_delta = adjusted_prob - consensus_prob
        path_index = 0.50 * quarterfinal_prob + 0.32 * semifinal_prob + 0.18 * final_prob
        ceiling_index = 0.55 * semifinal_prob + 0.45 * final_prob
        undervalued_edge = max(delta, adjusted_delta, 0.0)
        undervalued_score = 100.0 * clamp(
            0.36 * min(undervalued_edge / 0.025, 1.0)
            + 0.28 * min(path_index / 0.24, 1.0)
            + 0.20 * min(ceiling_index / 0.16, 1.0)
            + 0.16 * min(watch_index / 100.0, 1.0),
            0.0,
            1.0,
        )
        if undervalued_edge >= 0.01 and path_index >= 0.16 and undervalued_score >= 70.0:
            undervalued_label = "Tapado infravalorado fuerte"
            undervalued_action = "Considerar como diferencial de llave si necesitas separarte del consenso."
        elif undervalued_edge >= 0.004 and path_index >= 0.10 and undervalued_score >= 50.0:
            undervalued_label = "Tapado infravalorado jugable"
            undervalued_action = "Vigilar antes de octavos/cuartos; usar solo si su ruta se confirma."
        elif path_index >= 0.15:
            undervalued_label = "Tapado por camino favorable"
            undervalued_action = "No subirlo por talento puro; subirlo solo si el cuadro queda abierto."
        else:
            undervalued_label = "Alerta secundaria"
            undervalued_action = "Mantener en watchlist, no mover la llave base sin nueva evidencia."
        if delta >= 0.01:
            contrast = "El modelo propio lo ve más alto que el consenso."
        elif delta <= -0.01:
            contrast = "El consenso externo lo sostiene más que el modelo propio."
        else:
            contrast = "Modelo propio y consenso están razonablemente alineados."
        candidates.append(
            {
                "team": team,
                "tier": tier,
                "action": action,
                "watch_index": watch_index,
                "model_prob": model_prob,
                "consensus_prob": consensus_prob,
                "adjusted_prob": adjusted_prob,
                "quarterfinal_prob": quarterfinal_prob,
                "semifinal_prob": semifinal_prob,
                "final_prob": final_prob,
                "path_index": path_index,
                "ceiling_index": ceiling_index,
                "undervalued_score": undervalued_score,
                "undervalued_label": undervalued_label,
                "undervalued_action": undervalued_action,
                "contrast": contrast,
                "external_source": str((external or {}).get("source", "Detección interna por ruta Monte Carlo")),
                "external_url": str((external or {}).get("url", "")),
                "external_note": str(
                    (external or {}).get(
                        "note",
                        "El motor la detecta por su recorrido simulado; no hay una señal editorial externa añadida.",
                    )
                ),
            }
        )
    return sorted(
        candidates,
        key=lambda item: (
            float(item["watch_index"]),
            float(item["adjusted_prob"]),
            float(item["semifinal_prob"]),
        ),
        reverse=True,
    )


def consensus_bracket_alerts(bracket_payload: dict) -> List[dict]:
    alerts = []
    for match_id, override in QUINIELA_BRACKET_OVERRIDES.items():
        match = (bracket_payload.get("matches") or {}).get(match_id)
        if not match:
            continue
        matchup = None
        for scenario in match.get("matchup_scenarios", []):
            if {scenario.get("team_a"), scenario.get("team_b")} == set(override["teams"]):
                matchup = scenario
                break
        if matchup is None and {match.get("team_a"), match.get("team_b")} == set(override["teams"]):
            matchup = match
        if matchup is None:
            continue
        rows = conditional_winner_rows(matchup)
        if not rows:
            continue
        target = str(override["winner"])
        target_row = conditional_winner_for_team(matchup, target)
        if target_row is None:
            continue
        model_winner = str(rows[0].get("team"))
        model_prob = float(rows[0].get("conditional_prob", 0.0) or 0.0)
        target_prob = float(target_row.get("conditional_prob", 0.0) or 0.0)
        model_edge = max(0.0, model_prob - target_prob)
        applies = model_winner != target and model_edge <= float(override.get("max_model_edge", 0.0))
        alerts.append(
            {
                "match_id": match_id,
                "title": match.get("title", match_id),
                "team_a": matchup.get("team_a"),
                "team_b": matchup.get("team_b"),
                "model_winner": model_winner,
                "model_prob": model_prob,
                "recommended_winner": target if applies else model_winner,
                "recommended_prob": target_prob if applies else model_prob,
                "model_edge": model_edge,
                "applies": applies,
                "reason": str(override.get("reason", "")),
            }
        )
    return alerts


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
            f"Con este resultado, el siguiente cruce más probable de {winner_name} es contra {top['opponent']}. "
            f"Ese cruce aparece en {format_pct(float(top['matchup_prob']))} de las simulaciones; "
            f"si {winner_name} llega a ese partido, su rival más frecuente es {top['opponent']} en {format_pct(float(top['conditional_if_reaches']))}. "
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
        "substitutions",
        "substitution_impact",
        "bench_remaining",
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
    if stats.get("substitutions_a") is not None or stats.get("substitutions_b") is not None:
        lines.append(
            f"- Cambios usados: {team_a} {int(stats.get('substitutions_a', 0.0))} | {team_b} {int(stats.get('substitutions_b', 0.0))}"
        )
    if stats.get("possession_a") is not None or stats.get("possession_b") is not None:
        lines.append(
            f"- Posesion: {team_a} {stats.get('possession_a', 0.0):.0f}% | {team_b} {stats.get('possession_b', 0.0):.0f}%"
        )
    xg_a = stats.get("xg_a")
    xg_b = stats.get("xg_b")
    if xg_a is not None or xg_b is not None:
        lines.append(
            f"- Calidad de ocasiones en vivo: {team_a} {float(xg_a or 0.0):.2f} | {team_b} {float(xg_b or 0.0):.2f}"
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
        lines.append(f"- Cronología de disparos {team_name}: {'; '.join(pieces)}")
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
        lines.append(f"- Señales {team_a}: {'; '.join(str(signal) for signal in signals_a[:3])}")
    if signals_b:
        lines.append(f"- Señales {team_b}: {'; '.join(str(signal) for signal in signals_b[:3])}")
    return lines


def dashboard_weather_summary(fixture: dict) -> Optional[str]:
    if fixture.get("weather_temperature_c") is None:
        return None
    return (
        f"{fixture.get('weather_temperature_c', 0.0):.1f} C | "
        f"HR {fixture.get('weather_humidity_pct', 0.0):.0f}% | "
        f"viento {fixture.get('weather_wind_kmh', 0.0):.0f} km/h | "
        f"estrés {fixture.get('weather_stress', 0.0):.2f}"
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
        profile_a = profile_for(teams[team_a])
        profile_b = profile_for(teams[team_b])
        state_a = normalize_team_state(states.get(team_a, {}))
        state_b = normalize_team_state(states.get(team_b, {}))
        ctx = context_from_fixture(fixture, teams, states)
        stage = fixture_stage_name(fixture)
        if fixture_is_live(fixture) and fixture_has_live_score(fixture):
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
                "referee_sample_matches": int(fixture.get("referee_sample_matches", 0)),
                "referee_yellow_bias": fixture.get("referee_yellow_bias"),
                "referee_red_bias": fixture.get("referee_red_bias"),
                "referee_penalty_bias": fixture.get("referee_penalty_bias"),
                "lineup_status_a": fixture.get("lineup_status_a"),
                "lineup_status_b": fixture.get("lineup_status_b"),
                "lineup_change_count_a": int(fixture.get("lineup_change_count_a", 0)),
                "lineup_change_count_b": int(fixture.get("lineup_change_count_b", 0)),
                "starting_xi_a": list(ctx.starting_xi_a),
                "starting_xi_b": list(ctx.starting_xi_b),
                "lineup_strength_delta_a": ctx.lineup_strength_delta_a,
                "lineup_strength_delta_b": ctx.lineup_strength_delta_b,
                "lineup_coverage_a": ctx.lineup_coverage_a,
                "lineup_coverage_b": ctx.lineup_coverage_b,
                "lineup_intelligence_mode_a": ctx.lineup_intelligence_mode_a,
                "lineup_intelligence_mode_b": ctx.lineup_intelligence_mode_b,
                "starting_goalkeeper_a": fixture.get("starting_goalkeeper_a"),
                "starting_goalkeeper_b": fixture.get("starting_goalkeeper_b"),
                "goalkeeper_change_a": bool(fixture.get("goalkeeper_change_a", False)),
                "goalkeeper_change_b": bool(fixture.get("goalkeeper_change_b", False)),
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
                "unavailable_players_a": fixture.get("unavailable_players_a", []),
                "unavailable_players_b": fixture.get("unavailable_players_b", []),
                "news_headlines": fixture.get("news_headlines", []),
                "news_notes_a": fixture.get("news_notes_a", []),
                "news_notes_b": fixture.get("news_notes_b", []),
                "open_news_provider": fixture.get("open_news_provider"),
                "open_news_sources": fixture.get("open_news_sources", []),
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
                "live_substitutions_a": fixture.get("live_substitutions_a"),
                "live_substitutions_b": fixture.get("live_substitutions_b"),
                "live_substitution_impact_a": ctx.substitution_impact_a,
                "live_substitution_impact_b": ctx.substitution_impact_b,
                "live_bench_remaining_a": clamp(
                    profile_a.squad.bench_impact * max(0.0, 1.0 - float(ctx.live_substitutions_a) / 5.0),
                    0.0,
                    1.0,
                ),
                "live_bench_remaining_b": clamp(
                    profile_b.squad.bench_impact * max(0.0, 1.0 - float(ctx.live_substitutions_b) / 5.0),
                    0.0,
                    1.0,
                ),
                "live_xg_a": fixture.get("live_xg_a"),
                "live_xg_b": fixture.get("live_xg_b"),
                "live_xg_proxy_a": fixture.get("live_xg_proxy_a"),
                "live_xg_proxy_b": fixture.get("live_xg_proxy_b"),
                "market_provider": fixture.get("market_provider"),
                "market_summary": fixture.get("market_summary"),
                "market_prob_a": fixture.get("market_prob_a"),
                "market_prob_draw": fixture.get("market_prob_draw"),
                "market_prob_b": fixture.get("market_prob_b"),
                "market_total_line": goal_consensus_total_line(fixture),
                "goal_consensus_source": goal_consensus_source(fixture),
                "market_move_a": fixture.get("market_move_a"),
                "market_move_draw": fixture.get("market_move_draw"),
                "market_move_b": fixture.get("market_move_b"),
                "source": fixture.get("source"),
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
        return ["_Todavía no hay una publicación anterior comparable para mostrar cambios recientes._"]

    entry_changes = compare_entry_predictions(current_entries, previous_entries)
    bracket_changes = compare_bracket_payloads(current_bracket, previous_bracket)
    lines = []
    if previous_updated_at:
        lines.append(f"- Comparado contra la publicación anterior de: {previous_updated_at}")
    lines.append(
        "- Esta sección separa dos cosas distintas: cambios de cruce proyectado y cambios de probabilidad dentro del mismo partido. Solo compara picks cuando los dos equipos son los mismos; si cambia el cruce, aparece como cambio de llave, no como movimiento de probabilidad."
    )
    combined_matchup_changes = []
    seen_matchup_changes = set()
    for item in list(bracket_changes["matchup_changes"]) + list(entry_changes.get("matchup_changes", [])):
        key = (item.get("title"), item.get("previous_matchup"), item.get("current_matchup"))
        if key in seen_matchup_changes:
            continue
        seen_matchup_changes.add(key)
        combined_matchup_changes.append(item)
    if bracket_changes["new_teams"]:
        lines.append("- Equipos que entran en la ruta principal de la llave: " + "; ".join(bracket_changes["new_teams"]))
    if bracket_changes["dropped_teams"]:
        lines.append("- Equipos que salen de la ruta principal de la llave: " + "; ".join(bracket_changes["dropped_teams"]))
    if combined_matchup_changes:
        lines.append(
            "- Cruces principales que cambiaron: "
            + "; ".join(
                f"{item['title']}: antes {item['previous_matchup']} -> ahora {item['current_matchup']}"
                + (f" ({format_pct(item['current_prob'])})" if item.get("current_prob") is not None else "")
                for item in combined_matchup_changes
            )
        )
    if bracket_changes["favorite_flips"]:
        lines.append(
            "- Cruces donde cambió el favorito de avance: "
            + "; ".join(
                f"{item['title']}: {item['matchup']} | antes {item['previous_winner']} -> ahora {item['current_winner']} ({format_pct(item['current_prob'])})"
                for item in bracket_changes["favorite_flips"]
            )
        )
    if entry_changes["movers"]:
        lines.append(
            "- Partidos comparables donde más se movió el pick principal: "
            + "; ".join(
                f"{item['title']}: {item['previous_label']} {format_pct(item['previous_prob'])} -> {item['current_label']} {format_pct(item['current_prob'])}"
                for item in entry_changes["movers"]
            )
        )
    if entry_changes["score_changes"]:
        lines.append(
            "- Partidos cuyo marcador proyectado cambió: "
            + "; ".join(
                f"{item['title']}: {item['previous_score']} -> {item['current_score']}"
                for item in entry_changes["score_changes"]
            )
        )
    if entry_changes["label_changes"]:
        lines.append(
            "- Partidos donde cambió el resultado más probable: "
            + "; ".join(
                f"{item['title']}: {item['previous_label']} -> {item['current_label']}"
                for item in entry_changes["label_changes"]
            )
        )
    if len(lines) <= 2:
        lines.append("- Todavía no hay un cambio grande frente a la publicación anterior.")
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
            "<div class=\"panel-head\"><div><p class=\"eyebrow\">Comparativo</p><h2>Qué cambió desde la última actualización</h2>"
            "<p class=\"lede-tight\">Todavía no hay una publicación anterior comparable para resumir movimientos del tablero.</p>"
            "<p class=\"meta\">Regla de lectura: Solo compara partidos con los mismos dos equipos. Si cambia el cruce proyectado, se reporta como cambio de llave, no como movimiento de probabilidad.</p>"
            "</div></div></section>"
        )

    entry_changes = compare_entry_predictions(current_entries, previous_entries)
    bracket_changes = compare_bracket_payloads(current_bracket, previous_bracket)
    combined_matchup_changes = []
    seen_matchup_changes = set()
    for item in list(bracket_changes["matchup_changes"]) + list(entry_changes.get("matchup_changes", [])):
        key = (item.get("title"), item.get("previous_matchup"), item.get("current_matchup"))
        if key in seen_matchup_changes:
            continue
        seen_matchup_changes.add(key)
        combined_matchup_changes.append(item)

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
                combined_matchup_changes,
                lambda row: (
                    row["title"],
                    "Antes: "
                    f"{row['previous_matchup']} | Ahora: {row['current_matchup']}"
                    + (
                        f" | El nuevo cruce aparece {format_pct(row['current_prob'])}"
                        if row.get("current_prob") is not None
                        else ""
                    )
                    + ". No se compara la probabilidad del pick porque cambiaron los equipos.",
                ),
            )
            if combined_matchup_changes
            else "<li><strong>Sin cambios grandes</strong><span>La ruta principal del cuadro se mantiene respecto de la versión anterior.</span></li>"
        )
        + "</ul></article>"
    )
    teams_html = (
        "<article><h3>Equipos que entran o salen de la ruta principal</h3><ul>"
        + (
            text_list([f"Entran: {', '.join(bracket_changes['new_teams'])}"] if bracket_changes["new_teams"] else [])
            + text_list([f"Salen: {', '.join(bracket_changes['dropped_teams'])}"] if bracket_changes["dropped_teams"] else [])
            if bracket_changes["new_teams"] or bracket_changes["dropped_teams"]
            else "<li><strong>Sin entradas o salidas nuevas</strong><span>Los equipos visibles en la ruta principal no cambiaron frente a la publicación anterior.</span></li>"
        )
        + "</ul></article>"
    )
    movers_html = (
        "<article><h3>Partidos comparables donde más se movió el pick</h3><ul>"
        + (
            detailed_rows(
                entry_changes["movers"],
                lambda row: (
                    row["title"],
                    f"{row['previous_label']} {format_pct(row['previous_prob'])} -> {row['current_label']} {format_pct(row['current_prob'])}",
                ),
            )
            if entry_changes["movers"]
            else "<li><strong>Sin cambios detectables</strong><span>En los partidos con los mismos dos equipos, los picks principales siguen prácticamente iguales que en la última publicación.</span></li>"
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
            else "<li><strong>Sin cambio de marcador principal</strong><span>El resultado entero más probable sigue igual en los partidos comparables.</span></li>"
        )
        + "</ul></article>"
    )
    flip_html = (
        "<article><h3>Cruces donde cambió el favorito</h3><ul>"
        + (
            detailed_rows(
                bracket_changes["favorite_flips"],
                lambda row: (
                    row["title"],
                    f"{row['matchup']} | antes {row['previous_winner']} -> ahora {row['current_winner']} ({format_pct(row['current_prob'])})",
                ),
            )
            if bracket_changes["favorite_flips"]
            else "<li><strong>Sin giro de favorito</strong><span>En los cruces principales comparables no cambió el equipo con más probabilidad de avanzar.</span></li>"
        )
        + "</ul></article>"
    )

    compared_html = ""
    if previous_updated_at:
        compared_html = f"<p class=\"meta\">Comparado contra la publicación anterior de {html.escape(previous_updated_at)}.</p>"

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
                "Mayores movimientos del pick principal comparable",
                movers_chart_rows,
                tone="rose",
                description="Solo compara partidos con los mismos dos equipos. Si cambió el cruce proyectado, aparece en 'Cruces principales que cambiaron' y no aquí. El valor muestra el cambio absoluto de probabilidad, no la probabilidad final del partido.",
                empty_body="Todavía no hubo un movimiento material del pick principal en partidos comparables frente a la versión anterior.",
            )
        ]
    )

    return (
        "<section class=\"panel changes-panel\">"
        "<div class=\"panel-head\"><div><p class=\"eyebrow\">Comparativo</p><h2>Qué cambió desde la última actualización</h2>"
        "<p class=\"lede-tight\">Este bloque separa cambios de llave y cambios de probabilidad. Si cambia el cruce proyectado, no se compara como si fuera el mismo partido.</p>"
        "<p class=\"meta\">Regla de lectura: solo compara partidos con los mismos dos equipos. Si antes era Turkey vs Iran y ahora Paraguay vs Iran, eso es un cambio de cruce, no una caída/subida del pick de Paraguay.</p>"
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
                "market_total_line": goal_consensus_total_line(base_fixture),
                "goal_consensus_source": goal_consensus_source(base_fixture),
                "projection": True,
                "projection_note": (
                    f"Cruce usado para este casillero hoy: {team_a} vs {team_b} | "
                    f"probabilidad de que se dé {format_pct(match_projection['matchup_prob'])} | "
                    f"ganador global del casillero: {match_projection['winner']} "
                    f"{format_pct(match_projection['winner_prob'])} | "
                    f"si se juega exactamente este cruce: "
                    f"{match_projection.get('matchup_favorite', match_projection['winner'])} "
                    f"{format_pct(float(match_projection.get('matchup_favorite_prob', match_projection.get('conditional_winner_prob', 0.0))))}"
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
        return ("projection", "Proyección")
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
    if entry.get("starting_goalkeeper_a") or entry.get("starting_goalkeeper_b"):
        lines.append(
            f"- Portero esperado: {team_a} {entry.get('starting_goalkeeper_a') or 'sin confirmar'} | "
            f"{team_b} {entry.get('starting_goalkeeper_b') or 'sin confirmar'}"
        )
    if entry.get("starting_xi_a") or entry.get("starting_xi_b"):
        lines.append(
            f"- Lectura ponderada del XI: {team_a} {entry.get('lineup_intelligence_mode_a', 'sin XI nominal')} "
            f"(cobertura {float(entry.get('lineup_coverage_a', 0.0)):.0%}, impacto {float(entry.get('lineup_strength_delta_a', 0.0)):+.3f}) | "
            f"{team_b} {entry.get('lineup_intelligence_mode_b', 'sin XI nominal')} "
            f"(cobertura {float(entry.get('lineup_coverage_b', 0.0)):.0%}, impacto {float(entry.get('lineup_strength_delta_b', 0.0)):+.3f})"
        )
    if entry.get("goalkeeper_change_a") or entry.get("goalkeeper_change_b"):
        lines.append(
            f"- Cambio de portero respecto a la actualización anterior: {team_a} {'sí' if entry.get('goalkeeper_change_a') else 'no'} | "
            f"{team_b} {'sí' if entry.get('goalkeeper_change_b') else 'no'}"
        )
    if entry.get("referee"):
        sample_matches = int(entry.get("referee_sample_matches", 0) or 0)
        lines.append(
            f"- Árbitro: {entry.get('referee')} | perfil {sample_matches} muestras, amarillas {float(entry.get('referee_yellow_bias', 0.0)):+.2f}, "
            f"rojas {float(entry.get('referee_red_bias', 0.0)):+.2f}, penales {float(entry.get('referee_penalty_bias', 0.0)):+.2f}"
        )
    market_move_a = float(entry.get("market_move_a", 0.0) or 0.0)
    market_move_draw = float(entry.get("market_move_draw", 0.0) or 0.0)
    market_move_b = float(entry.get("market_move_b", 0.0) or 0.0)
    if any(abs(value) >= 0.005 for value in (market_move_a, market_move_draw, market_move_b)):
        lines.append(
            f"- Movimiento reciente de cuotas: {team_a} {market_move_a:+.1%} | empate {market_move_draw:+.1%} | {team_b} {market_move_b:+.1%}"
        )
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
    if fixture_is_live(entry) and prediction.current_score_a is not None and prediction.current_score_b is not None:
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
    if abs(float(entry.get("lineup_strength_delta_a", 0.0) or 0.0)) >= 0.005 or abs(float(entry.get("lineup_strength_delta_b", 0.0) or 0.0)) >= 0.005:
        lines.append(
            f"- Cambio por calidad ponderada del XI: {prediction.team_a} {float(entry.get('lineup_strength_delta_a', 0.0)):+.3f} | "
            f"{prediction.team_b} {float(entry.get('lineup_strength_delta_b', 0.0)):+.3f}."
        )
    if entry.get("lineup_change_count_a") or entry.get("lineup_change_count_b"):
        lines.append(
            f"- Cambio por cambios en el XI: {prediction.team_a} {entry.get('lineup_change_count_a', 0)} | {prediction.team_b} {entry.get('lineup_change_count_b', 0)}."
        )
    if entry.get("goalkeeper_change_a") or entry.get("goalkeeper_change_b"):
        lines.append(
            f"- Cambio por portero distinto al de la actualización anterior: {prediction.team_a} {'sí' if entry.get('goalkeeper_change_a') else 'no'} | "
            f"{prediction.team_b} {'sí' if entry.get('goalkeeper_change_b') else 'no'}."
        )
    if entry.get("weather_stress") is not None and float(entry.get("weather_stress", 0.0)) >= 0.18:
        lines.append(f"- Cambio por clima exigente: estrés climático {float(entry.get('weather_stress', 0.0)):.2f}.")
    if entry.get("market_prob_a") is not None:
        lines.append("- Cambio por cuotas del mercado: se mezclan con la estimación propia del modelo.")
    if any(abs(float(entry.get(key, 0.0) or 0.0)) >= 0.005 for key in ("market_move_a", "market_move_draw", "market_move_b")):
        lines.append(
            f"- Cambio por movimiento reciente de cuotas: {prediction.team_a} {float(entry.get('market_move_a', 0.0)):+.1%} | "
            f"empate {float(entry.get('market_move_draw', 0.0)):+.1%} | {prediction.team_b} {float(entry.get('market_move_b', 0.0)):+.1%}."
        )
    if entry.get("referee_sample_matches"):
        lines.append(
            f"- Cambio por perfil del árbitro: amarillas {float(entry.get('referee_yellow_bias', 0.0)):+.2f}, "
            f"rojas {float(entry.get('referee_red_bias', 0.0)):+.2f}, penales {float(entry.get('referee_penalty_bias', 0.0)):+.2f}."
        )
    live_stats = extract_live_stats_payload(entry)
    if live_stats:
        shots_on_target_a = int(live_stats.get("shots_on_target_a", 0.0))
        shots_on_target_b = int(live_stats.get("shots_on_target_b", 0.0))
        xg_a = float(live_stats.get("xg_a", 0.0))
        xg_b = float(live_stats.get("xg_b", 0.0))
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
        substitutions_a = int(live_stats.get("substitutions_a", 0.0))
        substitutions_b = int(live_stats.get("substitutions_b", 0.0))
        if substitutions_a or substitutions_b:
            lines.append(
                f"- Cambio por sustituciones y banco restante: cambios {prediction.team_a} {substitutions_a} | {prediction.team_b} {substitutions_b}."
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
            "- Factores que más pesan ahora: "
            + "; ".join(f"{label} {value:+.3f}" for label, value in drivers)
        )
    return lines


def goals_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Goles esperados al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Goles esperados al final de la prórroga"
    if prediction.live_phase == "penalties":
        return "Marcador actual"
    return "Goles esperados"


def projected_score_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Marcador proyectado al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Marcador proyectado al final de la prórroga"
    if prediction.live_phase == "penalties":
        return "Marcador actual"
    return "Marcador proyectado"


def projected_score_value(prediction: MatchPrediction) -> str:
    if prediction.exact_scores:
        return prediction.exact_scores[0][0]
    return f"{int(round(prediction.expected_goals_a))}-{int(round(prediction.expected_goals_b))}"


def score_label_with_teams(team_a: str, team_b: str, score: object) -> str:
    """Make exact scores unambiguous for Penca entry order."""

    parts = str(score or "").replace("–", "-").split("-")
    if len(parts) != 2:
        return str(score or "")
    left = parts[0].strip()
    right = parts[1].strip()
    if not left or not right:
        return str(score or "")
    return f"{team_a} {left} - {right} {team_b}"


def prediction_score_label(prediction: MatchPrediction, score: object) -> str:
    return score_label_with_teams(prediction.team_a, prediction.team_b, score)


def average_goals_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Promedio estimado de goles al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Promedio estimado de goles al final de la prórroga"
    if prediction.live_phase == "penalties":
        return "Marcador actual"
    return "Promedio estimado de goles del modelo"


def result_prob_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Probabilidades de resultado al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Probabilidades de resultado al final de la prórroga"
    if prediction.live_phase == "penalties":
        return "Probabilidades de clasificar en penales"
    return "Probabilidades de resultado (90')"


def top_result_label(prediction: MatchPrediction) -> str:
    if prediction.live_phase == "regulation":
        return "Desenlace más probable al final del tiempo reglamentario"
    if prediction.live_phase == "extra_time":
        return "Desenlace más probable al final de la prórroga"
    if prediction.live_phase == "penalties":
        return "Equipo con mayor probabilidad de clasificar en penales"
    return "Desenlace más probable en 90 minutos"


def top_result_summary(prediction: MatchPrediction) -> str:
    outcomes = [
        (prediction.win_a, f"Gana {prediction.team_a}"),
        (prediction.draw, "Empate"),
        (prediction.win_b, f"Gana {prediction.team_b}"),
    ]
    best_prob, best_label = max(outcomes, key=lambda item: item[0])
    return f"{best_label} {format_pct(best_prob)}"


def quiniela_outcome_options(prediction: MatchPrediction) -> List[Tuple[float, str, str]]:
    return [
        (float(prediction.win_a), f"Gana {prediction.team_a}", "1"),
        (float(prediction.draw), "Empate", "X"),
        (float(prediction.win_b), f"Gana {prediction.team_b}", "2"),
    ]


PENCA_OVACION_POINTS = {
    "exact": 8.0,
    "goal_difference": 5.0,
    "winner": 3.0,
}

EMPIRICAL_SCORE_PRIOR = {
    (1, 0): 0.112,
    (0, 1): 0.092,
    (1, 1): 0.116,
    (2, 0): 0.088,
    (0, 2): 0.067,
    (2, 1): 0.086,
    (1, 2): 0.073,
    (0, 0): 0.076,
    (2, 2): 0.043,
    (3, 0): 0.041,
    (0, 3): 0.030,
    (3, 1): 0.039,
    (1, 3): 0.031,
    (3, 2): 0.020,
    (2, 3): 0.018,
    (4, 0): 0.011,
    (0, 4): 0.008,
    (4, 1): 0.010,
    (1, 4): 0.008,
}


def score_result_code(goals_a: int, goals_b: int) -> str:
    if goals_a > goals_b:
        return "1"
    if goals_b > goals_a:
        return "2"
    return "X"


def empirical_score_prior(goals_a: int, goals_b: int) -> float:
    """Broad football prior so exact-score picks are not pure Poisson artifacts."""

    direct = EMPIRICAL_SCORE_PRIOR.get((goals_a, goals_b))
    if direct is not None:
        return direct
    total = goals_a + goals_b
    margin = abs(goals_a - goals_b)
    if total >= 7:
        return 0.0015
    if total >= 5:
        return 0.006 * math.exp(-0.35 * max(total - 5, 0)) * (0.75 if margin >= 4 else 1.0)
    if margin >= 4:
        return 0.004
    return 0.012 * math.exp(-0.38 * total - 0.22 * margin)


CONVENTIONAL_SCORE_POPULARITY = {
    (1, 0): 0.92,
    (0, 1): 0.88,
    (2, 0): 0.95,
    (0, 2): 0.90,
    (1, 1): 0.94,
    (2, 1): 0.84,
    (1, 2): 0.80,
    (0, 0): 0.74,
    (3, 0): 0.58,
    (0, 3): 0.52,
    (3, 1): 0.56,
    (1, 3): 0.50,
    (2, 2): 0.50,
}


def public_scoreline_popularity_proxy(
    pick_a: int,
    pick_b: int,
    mean_goals_a: float,
    mean_goals_b: float,
    exact_prob: float,
    top_exact_prob: float,
    difference_prob: float,
    prior_index: float,
) -> float:
    """Estimate how crowded a scoreline is likely to be in a casual pool.

    This is not treated as truth or market data. It is a strategic proxy: many
    participants over-select familiar scores such as 1-0, 2-0, 2-1 and 1-1.
    The Penca optimizer can use that signal to distinguish "safe/obvious" from
    "differential but still defensible" score choices.
    """

    if DISABLE_PUBLIC_POPULARITY_PROXY:
        return 0.0

    total_goals = pick_a + pick_b
    margin = abs(pick_a - pick_b)
    mean_edge = mean_goals_a - mean_goals_b
    pick_result = score_result_code(pick_a, pick_b)
    favorite_result = "1" if mean_edge > 0.25 else "2" if mean_edge < -0.25 else "X"
    conventional = CONVENTIONAL_SCORE_POPULARITY.get(
        (pick_a, pick_b),
        clamp(0.42 - 0.055 * max(total_goals - 3, 0) - 0.035 * max(margin - 2, 0), 0.16, 0.46),
    )
    exact_visibility = clamp(exact_prob / max(top_exact_prob, 1e-9), 0.0, 1.0)
    difference_visibility = clamp(difference_prob / 0.34, 0.0, 1.0)
    simple_score_bias = clamp(1.0 - 0.13 * max(total_goals - 2, 0) - 0.08 * max(margin - 2, 0), 0.22, 1.0)
    if pick_result == favorite_result:
        result_visibility = 0.78
    elif pick_result == "X" and abs(mean_edge) <= 0.45:
        result_visibility = 0.66
    elif pick_result != "X":
        result_visibility = 0.42
    else:
        result_visibility = 0.34
    if pick_result != "X" and min(pick_a, pick_b) == 0 and margin <= 2:
        result_visibility += 0.05

    return clamp(
        0.31 * conventional
        + 0.22 * exact_visibility
        + 0.16 * simple_score_bias
        + 0.14 * result_visibility
        + 0.10 * difference_visibility
        + 0.07 * prior_index,
        0.0,
        1.0,
    )


def score_shape_decision_boost(goals_a: int, goals_b: int, score_shape_meta: Optional[Dict[str, object]] = None) -> float:
    if not score_shape_meta:
        return 1.0
    label = str(score_shape_meta.get("label", ""))
    total = goals_a + goals_b
    margin = abs(goals_a - goals_b)
    both_score = goals_a > 0 and goals_b > 0
    boost = 1.0
    if "ambos equipos anotan" in label and both_score:
        boost += 0.07
    if "ventajas más amplias" in label and margin >= 2:
        boost += 0.06
    if "portería a cero" in label and min(goals_a, goals_b) == 0:
        boost += 0.05
    if "conservador" in label and total <= 2:
        boost += 0.03
    favorite_is_a = bool(score_shape_meta.get("favorite_is_a", True))
    favorite_goals = goals_a if favorite_is_a else goals_b
    rival_goals = goals_b if favorite_is_a else goals_a
    favorite_wins = favorite_goals > rival_goals
    if favorite_wins and rival_goals == 0 and favorite_goals == 2:
        boost += 0.045 * float(score_shape_meta.get("favorite_clean_sheet_win_2_signal", 0.0))
    if favorite_wins and rival_goals == 0 and favorite_goals >= 3:
        empirical_support = (
            0.62 * float(score_shape_meta.get("favorite_clean_sheet_win_3_plus_signal", 0.0))
            + 0.38 * float(score_shape_meta.get("rival_heavy_loss_signal", 0.0))
        )
        boost += 0.15 * empirical_support
    if favorite_wins and rival_goals > 0:
        empirical_support = (
            0.60 * float(score_shape_meta.get("favorite_btts_win_signal", 0.0))
            + 0.40 * float(score_shape_meta.get("rival_btts_loss_signal", 0.0))
        )
        boost += 0.10 * empirical_support
    return clamp(boost, 0.84, 1.18)


def matchup_scoreline_family_index(
    goals_a: int,
    goals_b: int,
    score_shape_meta: Optional[Dict[str, object]] = None,
) -> float:
    """Compatibility of an exact score with both teams' empirical families.

    A 2-0 remains a perfectly valid football score, but it no longer receives
    the same treatment for every matchup. The historical family profile asks:
    does this team often win this way, and does this rival often lose this way?
    """

    if not score_shape_meta:
        return 0.50
    signal_a = score_shape_meta.get("scoreline_signal_a")
    signal_b = score_shape_meta.get("scoreline_signal_b")
    if not isinstance(signal_a, dict) or not isinstance(signal_b, dict):
        return 0.50
    margin = abs(goals_a - goals_b)
    if goals_a == goals_b == 1:
        raw = 0.5 * float(signal_a.get("draw_11", 0.0)) + 0.5 * float(signal_b.get("draw_11", 0.0))
    elif goals_a == goals_b and goals_a >= 2:
        raw = 0.5 * float(signal_a.get("draw_22_plus", 0.0)) + 0.5 * float(signal_b.get("draw_22_plus", 0.0))
    elif goals_a > goals_b and goals_b == 0 and margin >= 3:
        raw = 0.62 * float(signal_a.get("clean_sheet_win_3_plus", 0.0)) + 0.38 * float(signal_b.get("heavy_loss", 0.0))
    elif goals_b > goals_a and goals_a == 0 and margin >= 3:
        raw = 0.62 * float(signal_b.get("clean_sheet_win_3_plus", 0.0)) + 0.38 * float(signal_a.get("heavy_loss", 0.0))
    elif goals_a > goals_b and goals_b == 0 and margin == 2:
        raw = 0.68 * float(signal_a.get("clean_sheet_win_2", 0.0)) + 0.32 * float(signal_b.get("heavy_loss", 0.0))
    elif goals_b > goals_a and goals_a == 0 and margin == 2:
        raw = 0.68 * float(signal_b.get("clean_sheet_win_2", 0.0)) + 0.32 * float(signal_a.get("heavy_loss", 0.0))
    elif goals_a > goals_b and goals_b > 0:
        raw = 0.60 * float(signal_a.get("btts_win", 0.0)) + 0.40 * float(signal_b.get("btts_loss", 0.0))
    elif goals_b > goals_a and goals_a > 0:
        raw = 0.60 * float(signal_b.get("btts_win", 0.0)) + 0.40 * float(signal_a.get("btts_loss", 0.0))
    elif goals_a + goals_b <= 1:
        raw = 0.5 * float(signal_a.get("low_total", 0.0)) + 0.5 * float(signal_b.get("low_total", 0.0))
    else:
        raw = 0.5 * float(signal_a.get("open_match", 0.0)) + 0.5 * float(signal_b.get("open_match", 0.0))
    return clamp(0.50 + 0.42 * raw, 0.08, 0.92)


def score_marginal_fit(
    dist: Dict[Tuple[int, int], float],
    pick_a: int,
    pick_b: int,
    mean_goals_a: float,
    mean_goals_b: float,
) -> float:
    marginal_a = sum(float(prob) for (goals_a, _), prob in dist.items() if goals_a == pick_a)
    marginal_b = sum(float(prob) for (_, goals_b), prob in dist.items() if goals_b == pick_b)
    distance = abs(pick_a - mean_goals_a) + abs(pick_b - mean_goals_b)
    return clamp(0.54 * marginal_a + 0.46 * marginal_b - 0.025 * distance, 0.0, 1.0)


def calibrated_integer_score_profile(
    pick_a: int,
    pick_b: int,
    mean_goals_a: float,
    mean_goals_b: float,
    prior_index: float,
) -> Dict[str, float | str]:
    """Scoreline calibration layer for Penca.

    Poisson-like distributions often put the mode on 1-0, 2-0 or 1-1. That is
    reasonable as a probability mode, but Penca rewards exact goals and goal
    difference, so the submitted score should also respect the expected goal
    total, expected margin and whether the underdog is likely to score.
    """

    mean_total = mean_goals_a + mean_goals_b
    pick_total = pick_a + pick_b
    mean_edge = mean_goals_a - mean_goals_b
    pick_edge = pick_a - pick_b
    expected_margin = abs(mean_edge)
    pick_margin = abs(pick_edge)
    favorite_mean = max(mean_goals_a, mean_goals_b)
    underdog_mean = min(mean_goals_a, mean_goals_b)
    favorite_pick = pick_a if mean_goals_a >= mean_goals_b else pick_b
    underdog_pick = pick_b if mean_goals_a >= mean_goals_b else pick_a

    side_fit = math.exp(-0.48 * (abs(pick_a - mean_goals_a) + abs(pick_b - mean_goals_b)))
    total_fit = math.exp(-0.42 * abs(pick_total - mean_total))
    margin_fit = math.exp(-0.52 * abs(pick_margin - expected_margin))
    edge_direction_fit = 1.0 if pick_edge == 0 or mean_edge == 0 or (pick_edge > 0) == (mean_edge > 0) else 0.62

    penalty = 0.0
    boost = 0.0
    notes: List[str] = []

    if favorite_mean >= 2.10 and favorite_pick <= 1:
        penalty += 0.22
        notes.append("sube goles del favorito: su media esperada supera 2")
    elif favorite_mean >= 1.70 and favorite_pick <= 1 and expected_margin >= 0.75:
        penalty += 0.13
        notes.append("evita infravalorar al favorito")

    if favorite_mean < 1.62 and favorite_pick >= 3:
        penalty += 0.14
        notes.append("recorta goleada sin volumen esperado")
    if pick_total >= mean_total + 2.15:
        penalty += 0.11
        notes.append("evita cola alta de goles")

    if underdog_mean <= 0.42 and underdog_pick >= 1:
        penalty += 0.15
        notes.append("baja gol del equipo con poca producción esperada")
    elif underdog_mean >= 0.72 and underdog_pick == 0 and favorite_mean >= 1.35:
        penalty += 0.08
        notes.append("el rival tiene señal suficiente para anotar")

    if pick_a == pick_b == 1 and mean_total >= 2.55:
        penalty += 0.12
        notes.append("1-1 queda corto para el total esperado")
    if pick_a == pick_b == 0 and mean_total >= 1.85:
        penalty += 0.14
        notes.append("0-0 queda demasiado conservador")

    if favorite_pick >= 2 and underdog_pick == 0 and favorite_mean >= 1.85 and underdog_mean <= 0.58:
        boost += 0.11
        notes.append("ventaja con portería en cero sí tiene soporte")
    if favorite_pick >= 2 and underdog_pick >= 1 and favorite_mean >= 1.55 and underdog_mean >= 0.62:
        boost += 0.10
        notes.append("ambos anotan con favorito superior")
    if favorite_pick >= 3 and underdog_pick == 0 and favorite_mean >= 2.25 and underdog_mean <= 0.35:
        boost += 0.10
        notes.append("goleada moderada plausible por brecha de goles")
    if pick_margin >= 2 and expected_margin >= 1.20 and favorite_pick >= 2:
        boost += 0.08
        notes.append("margen amplio alineado con la brecha esperada")
    if pick_margin == 1 and 0.38 <= expected_margin <= 1.20 and pick_total >= 2:
        boost += 0.05
        notes.append("margen de un gol encaja con partido competitivo")

    index = clamp(
        0.34 * side_fit
        + 0.25 * total_fit
        + 0.20 * margin_fit
        + 0.09 * edge_direction_fit
        + 0.12 * prior_index
        + boost
        - penalty,
        0.0,
        1.0,
    )
    note = "; ".join(notes[:2]) if notes else "marcador entero alineado con goles esperados y margen"
    return {
        "scoreline_calibration_index": index,
        "scoreline_calibration_boost": boost,
        "scoreline_calibration_penalty": penalty,
        "scoreline_calibration_note": note,
        "side_fit": side_fit,
        "total_fit": total_fit,
        "margin_fit": margin_fit,
    }


def scoreline_scenario_profile(
    pick_a: int,
    pick_b: int,
    mean_goals_a: float,
    mean_goals_b: float,
    exact_prob: float,
    top_exact_prob: float,
    result_prob: float,
    difference_prob: float,
    prior_index: float,
) -> Dict[str, float | str]:
    """Non-Poisson scenario layer for the score submitted to Penca.

    Exact-score modes in football naturally cluster around 1-0, 2-0 and 1-1.
    That is useful information, but the Penca score should also reflect the
    match script: dominant favorite, favorite with BTTS risk, low-tempo trap,
    or balanced/open match. This layer gives those scripts an explicit vote so
    Poisson's modal score is not the only force in the recommendation.
    """

    mean_total = mean_goals_a + mean_goals_b
    mean_edge = mean_goals_a - mean_goals_b
    favorite_is_a = mean_edge >= 0.0
    favorite_mean = mean_goals_a if favorite_is_a else mean_goals_b
    underdog_mean = mean_goals_b if favorite_is_a else mean_goals_a
    favorite_pick = pick_a if favorite_is_a else pick_b
    underdog_pick = pick_b if favorite_is_a else pick_a
    pick_total = pick_a + pick_b
    pick_margin = abs(pick_a - pick_b)
    expected_margin = abs(mean_edge)
    exact_ratio = clamp(exact_prob / max(top_exact_prob, 1e-9), 0.0, 1.0)
    result_strength = clamp(result_prob, 0.0, 1.0)
    diff_strength = clamp(difference_prob / 0.32, 0.0, 1.0)

    scenario_family = "marcador balanceado"
    note = "escenario mixto: combina marcador exacto, diferencia y lectura del partido"
    scenario_index = 0.42 * exact_ratio + 0.20 * prior_index + 0.20 * result_strength + 0.18 * diff_strength
    modal_lock_penalty = 0.0

    is_narrow_clean_sheet = underdog_pick == 0 and favorite_pick == 1
    is_modal_clean_sheet = underdog_pick == 0 and favorite_pick == 2
    is_higher_clean_sheet = underdog_pick == 0 and favorite_pick in {3, 4}
    is_favorite_btss = favorite_pick >= 2 and underdog_pick == 1
    is_low_margin_favorite = favorite_pick == 1 and underdog_pick == 0
    is_one_one = pick_a == pick_b == 1
    is_two_two = pick_a == pick_b == 2
    is_scoreless = pick_a == pick_b == 0
    is_draw = pick_a == pick_b

    if favorite_mean >= 2.30 and underdog_mean <= 0.26:
        scenario_family = "favorito dominante"
        if is_higher_clean_sheet and favorite_pick == 3:
            scenario_index += 0.34
            note = "favorito muy superior: el 3-0 tiene mejor lectura de escenario que el 2-0 modal"
        elif is_higher_clean_sheet and favorite_pick == 4:
            scenario_index += 0.10 if exact_ratio >= 0.45 else -0.08
            note = "goleada alta: solo sirve si la cola de goles tiene soporte"
        elif is_modal_clean_sheet:
            scenario_index -= 0.12
            modal_lock_penalty = 0.34
            note = "evita que el 2-0 gane solo por ser el modo Poisson"
        elif is_narrow_clean_sheet:
            scenario_index -= 0.24
            modal_lock_penalty = 0.28
            note = "1-0 queda corto para un favorito dominante"
        elif is_low_margin_favorite:
            scenario_index -= 0.24
            note = "1-0 queda corto para un favorito con más de dos goles esperados"
        elif is_favorite_btss:
            scenario_index -= 0.10
            modal_lock_penalty = 0.12
            note = "gol del débil poco respaldado por su producción esperada"
        elif is_one_one or is_scoreless:
            scenario_index -= 0.22
            modal_lock_penalty = 0.22
            note = "empate corto no encaja con favorito dominante"
    elif favorite_mean >= 1.85 and expected_margin >= 0.90:
        scenario_family = "favorito claro"
        if is_modal_clean_sheet:
            scenario_index += 0.08
            note = "favorito claro: 2-0 sigue defendible por ganador y diferencia"
        elif is_narrow_clean_sheet and mean_total >= 2.25:
            scenario_index -= 0.10
            modal_lock_penalty = 0.18
            note = "1-0 puede quedar corto: revisar 2-0/2-1 según gol rival"
        elif is_higher_clean_sheet and favorite_pick == 3:
            scenario_index += 0.15 if exact_ratio >= 0.62 else 0.02
            note = "3-0 alternativo si está cerca del modo y el total esperado lo soporta"
        elif is_favorite_btss and underdog_mean >= 0.48:
            scenario_index += 0.12
            note = "favorito claro con riesgo de gol rival: 2-1/3-1 gana sentido"
        elif favorite_pick == 3 and underdog_pick == 1 and underdog_mean >= 0.50 and favorite_mean >= 2.20:
            scenario_index += 0.10
            note = "favorito claro y abierto: 3-1 tiene lectura si el rival anota"
        elif is_low_margin_favorite and mean_total >= 2.30:
            scenario_index -= 0.08
            note = "1-0 queda algo corto para el total esperado"
        elif is_draw:
            scenario_index -= 0.12
            modal_lock_penalty = 0.16
            note = "empate no es el guion base de un favorito claro"
    elif favorite_mean >= 1.35 and underdog_mean >= 0.55 and expected_margin <= 1.10:
        scenario_family = "partido competitivo"
        if is_favorite_btss:
            scenario_index += 0.20
            note = "partido competitivo: ganador por un gol con ambos anotando"
        elif favorite_pick == 1 and underdog_pick == 0 and underdog_mean >= 0.66:
            scenario_index -= 0.12
            modal_lock_penalty = 0.18
            note = "1-0 es frágil: el rival tiene señal suficiente para marcar"
        elif is_draw and pick_total in {2, 4}:
            if is_one_one and mean_total >= 2.65:
                scenario_index -= 0.08
                modal_lock_penalty = 0.16
                note = "1-1 queda bajo para un partido parejo con volumen de goles"
            elif is_two_two and mean_total >= 2.65:
                scenario_index += 0.18
                note = "partido parejo y abierto: 2-2 entra como escenario real"
            else:
                scenario_index += 0.12
                note = "partido parejo: empate con goles tiene soporte de escenario"
        elif underdog_pick == 0 and favorite_pick >= 2:
            scenario_index -= 0.10
            modal_lock_penalty = 0.14
            note = "portería a cero menos sólida en partido competitivo"
    elif mean_total <= 2.05:
        scenario_family = "partido de baja anotación"
        if pick_total <= 2 and pick_margin <= 1:
            scenario_index += 0.14
            note = "baja anotación: marcador corto es el escenario natural"
        elif pick_total >= 3:
            scenario_index -= 0.12
            note = "total bajo: no sobrecargar goles sin evidencia"
    else:
        if is_one_one and mean_total >= 2.55:
            scenario_index -= 0.08
            modal_lock_penalty = 0.14
            note = "1-1 puede quedar corto para el total esperado"
        elif is_two_two and mean_total >= 2.70:
            scenario_index += 0.12
            note = "2-2 recibe soporte por partido abierto"
        elif is_narrow_clean_sheet and mean_total >= 2.30:
            scenario_index -= 0.08
            modal_lock_penalty = 0.14
            note = "1-0 puede quedar corto frente al total esperado"

    if pick_total >= mean_total + 2.35 and exact_ratio < 0.55:
        scenario_index -= 0.16
        note = "cola alta de goles: exige soporte fuerte para jugarla"
    if pick_margin >= expected_margin + 2.15 and exact_ratio < 0.60:
        scenario_index -= 0.12
        note = "margen demasiado amplio frente a la brecha esperada"

    return {
        "scenario_ensemble_index": clamp(scenario_index, 0.0, 1.0),
        "scoreline_scenario_family": scenario_family,
        "scoreline_scenario_note": note,
        "poisson_modal_lock_penalty": clamp(modal_lock_penalty, 0.0, 1.0),
    }


def score_expected_points_for_penca(
    dist: Dict[Tuple[int, int], float],
    pick_a: int,
    pick_b: int,
    score_shape_meta: Optional[Dict[str, object]] = None,
) -> dict:
    pick_diff = pick_a - pick_b
    pick_result = score_result_code(pick_a, pick_b)
    exact_prob = 0.0
    difference_prob = 0.0
    result_prob = 0.0
    expected_points_squared = 0.0
    for (actual_a, actual_b), prob in dist.items():
        actual_prob = float(prob)
        same_exact = actual_a == pick_a and actual_b == pick_b
        same_difference = actual_a - actual_b == pick_diff
        same_result = score_result_code(actual_a, actual_b) == pick_result
        if same_exact:
            exact_prob += actual_prob
        if same_difference:
            difference_prob += actual_prob
        if same_result:
            result_prob += actual_prob
        if same_exact:
            points = PENCA_OVACION_POINTS["exact"]
        elif same_difference:
            points = PENCA_OVACION_POINTS["goal_difference"]
        elif same_result:
            points = PENCA_OVACION_POINTS["winner"]
        else:
            points = 0.0
        expected_points_squared += actual_prob * points * points
    expected_points = (
        PENCA_OVACION_POINTS["exact"] * exact_prob
        + PENCA_OVACION_POINTS["goal_difference"] * max(0.0, difference_prob - exact_prob)
        + PENCA_OVACION_POINTS["winner"] * max(0.0, result_prob - difference_prob)
    )
    points_sd = math.sqrt(max(0.0, expected_points_squared - expected_points * expected_points))
    margin = abs(pick_diff)
    total_goals = pick_a + pick_b
    mean_total_goals = sum((goals_a + goals_b) * float(prob) for (goals_a, goals_b), prob in dist.items())
    mean_goals_a = sum(goals_a * float(prob) for (goals_a, _), prob in dist.items())
    mean_goals_b = sum(goals_b * float(prob) for (_, goals_b), prob in dist.items())
    expected_goal_edge = abs(mean_goals_a - mean_goals_b)
    top_exact_prob = max((float(prob) for prob in dist.values()), default=0.0)
    relative_exact_strength = exact_prob / max(top_exact_prob, 1e-9)
    prior_prob = empirical_score_prior(pick_a, pick_b)
    top_prior_prob = max(EMPIRICAL_SCORE_PRIOR.values())
    prior_index = clamp(prior_prob / max(top_prior_prob, 1e-9), 0.0, 1.0)
    marginal_fit = score_marginal_fit(dist, pick_a, pick_b, mean_goals_a, mean_goals_b)
    calibration_profile = calibrated_integer_score_profile(
        pick_a,
        pick_b,
        mean_goals_a,
        mean_goals_b,
        prior_index,
    )
    scoreline_calibration_index = float(calibration_profile["scoreline_calibration_index"])
    scoreline_calibration_boost = float(calibration_profile["scoreline_calibration_boost"])
    scoreline_calibration_penalty = float(calibration_profile["scoreline_calibration_penalty"])
    scenario_profile = scoreline_scenario_profile(
        pick_a,
        pick_b,
        mean_goals_a,
        mean_goals_b,
        exact_prob,
        top_exact_prob,
        result_prob,
        difference_prob,
        prior_index,
    )
    scenario_ensemble_index = float(scenario_profile["scenario_ensemble_index"])
    poisson_modal_lock_penalty = float(scenario_profile["poisson_modal_lock_penalty"])
    shape_boost = score_shape_decision_boost(pick_a, pick_b, score_shape_meta)
    matchup_family_index = matchup_scoreline_family_index(pick_a, pick_b, score_shape_meta)
    public_score_popularity_index = public_scoreline_popularity_proxy(
        pick_a,
        pick_b,
        mean_goals_a,
        mean_goals_b,
        exact_prob,
        top_exact_prob,
        difference_prob,
        prior_index,
    )
    high_total_penalty = max(0.0, total_goals - (mean_total_goals + 2.15))
    tail_score_penalty = 0.10 if total_goals >= 5 and relative_exact_strength < 0.45 else 0.0
    extreme_score_penalty = 0.12 if max(pick_a, pick_b) >= 4 and exact_prob < 0.025 else 0.0
    empirical_tail_penalty = 0.0
    if prior_index < 0.16 and exact_prob < 0.60 * top_exact_prob:
        empirical_tail_penalty = 0.08
    clean_sheet_margin_penalty = 0.0
    if margin >= 2 and min(pick_a, pick_b) == 0:
        if result_prob < 0.68 or expected_goal_edge < 0.72:
            clean_sheet_margin_penalty += 0.16
        if margin >= 3 and (result_prob < 0.82 or exact_prob < 0.70 * top_exact_prob):
            clean_sheet_margin_penalty += 0.18
        if relative_exact_strength < 0.62:
            clean_sheet_margin_penalty += 0.08
    realism_index = clamp(
        1.0
        - 0.10 * high_total_penalty
        - tail_score_penalty
        - extreme_score_penalty,
        0.55,
        1.0,
    )
    plausibility_index = clamp(
        realism_index
        - clean_sheet_margin_penalty
        - empirical_tail_penalty
        - 0.05 * clamp(points_sd / 3.8, 0.0, 1.0),
        0.48,
        1.0,
    )
    asymmetric_bonus = 1.0 if (margin >= 2 or total_goals >= 3 or (pick_a > 0 and pick_b > 0 and max(pick_a, pick_b) >= 2)) else 0.0
    safety_index = clamp(
        0.40 * result_prob
        + 0.32 * difference_prob
        + 0.14 * clamp(exact_prob / 0.24, 0.0, 1.0)
        + 0.10 * clamp(expected_points / 4.2, 0.0, 1.0)
        - 0.04 * clamp(points_sd / 3.6, 0.0, 1.0),
        0.0,
        1.0,
    )
    risk_adjusted_points = expected_points - 0.18 * points_sd + 0.70 * difference_prob + 0.25 * result_prob
    upside_score = expected_points + 1.65 * exact_prob + 0.18 * asymmetric_bonus - 0.08 * max(0, total_goals - 5)
    model_score_index = clamp(exact_prob / max(top_exact_prob, 1e-9), 0.0, 1.0)
    penca_points_index = clamp(expected_points / 4.2, 0.0, 1.0)
    ensemble_score_index = clamp(
        (
            0.27 * penca_points_index
            + 0.07 * model_score_index
            + 0.15 * clamp(result_prob, 0.0, 1.0)
            + 0.12 * clamp(difference_prob / 0.32, 0.0, 1.0)
            + 0.10 * prior_index
            + 0.08 * marginal_fit
            + 0.12 * scoreline_calibration_index
            + 0.08 * scenario_ensemble_index
            + 0.05 * matchup_family_index
        )
        * shape_boost
        - 0.035 * clamp(points_sd / 3.8, 0.0, 1.0),
        0.0,
        1.0,
    )
    differential_value_index = clamp(
        0.30 * ensemble_score_index
        + 0.20 * plausibility_index
        + 0.17 * scoreline_calibration_index
        + 0.13 * scenario_ensemble_index
        + 0.10 * prior_index
        + 0.06 * model_score_index
        + 0.04 * asymmetric_bonus
        - 0.26 * public_score_popularity_index,
        0.0,
        1.0,
    )
    ensemble_adjusted_points = (
        expected_points * (0.70 + 0.30 * ensemble_score_index)
        + 0.42 * exact_prob
        + 0.12 * difference_prob
        + 0.10 * prior_index
        + 0.06 * marginal_fit
        + 0.24 * scoreline_calibration_index
        + 0.34 * scenario_ensemble_index
        + 0.22 * (matchup_family_index - 0.50)
        + 0.08 * scoreline_calibration_boost
        - 0.18 * scoreline_calibration_penalty
        - 0.22 * poisson_modal_lock_penalty
        - 0.16 * clean_sheet_margin_penalty
        - 0.10 * empirical_tail_penalty
    )
    competitive_adjusted_points = (
        ensemble_adjusted_points
        + 0.28 * differential_value_index
        - 0.08 * public_score_popularity_index
    )
    realism_adjusted_points = (
        expected_points * (0.78 + 0.22 * plausibility_index)
        + 0.26 * exact_prob
        + 0.08 * difference_prob
        - 0.18 * clean_sheet_margin_penalty
    )
    plausibility_note = "marcador de forma normal"
    if clean_sheet_margin_penalty > 0.0:
        plausibility_note = "marcador amplio con portería a cero: exige ventaja clara para ser recomendado"
    return {
        "score": f"{pick_a}-{pick_b}",
        "expected_points": expected_points,
        "realism_adjusted_points": realism_adjusted_points,
        "exact_prob": exact_prob,
        "difference_prob": difference_prob,
        "result_prob": result_prob,
        "points_sd": points_sd,
        "risk_adjusted_points": risk_adjusted_points,
        "safety_index": safety_index,
        "upside_score": upside_score,
        "ensemble_adjusted_points": ensemble_adjusted_points,
        "competitive_adjusted_points": competitive_adjusted_points,
        "ensemble_score_index": ensemble_score_index,
        "model_score_index": model_score_index,
        "penca_points_index": penca_points_index,
        "public_score_popularity_index": public_score_popularity_index,
        "differential_value_index": differential_value_index,
        "empirical_prior": prior_prob,
        "empirical_prior_index": prior_index,
        "marginal_fit": marginal_fit,
        "scoreline_calibration_index": scoreline_calibration_index,
        "scoreline_calibration_boost": scoreline_calibration_boost,
        "scoreline_calibration_penalty": scoreline_calibration_penalty,
        "scoreline_calibration_note": str(calibration_profile["scoreline_calibration_note"]),
        "scoreline_side_fit": float(calibration_profile["side_fit"]),
        "scoreline_total_fit": float(calibration_profile["total_fit"]),
        "scoreline_margin_fit": float(calibration_profile["margin_fit"]),
        "scenario_ensemble_index": scenario_ensemble_index,
        "scoreline_scenario_family": str(scenario_profile["scoreline_scenario_family"]),
        "scoreline_scenario_note": str(scenario_profile["scoreline_scenario_note"]),
        "poisson_modal_lock_penalty": poisson_modal_lock_penalty,
        "shape_boost": shape_boost,
        "matchup_family_index": matchup_family_index,
        "realism_index": realism_index,
        "plausibility_index": plausibility_index,
        "clean_sheet_margin_penalty": clean_sheet_margin_penalty,
        "empirical_tail_penalty": empirical_tail_penalty,
        "plausibility_note": plausibility_note,
        "asymmetric_bonus": asymmetric_bonus,
    }


def parse_score_pair(score: object) -> Tuple[int, int]:
    try:
        left, right = str(score).split("-", 1)
        return int(left), int(right)
    except (TypeError, ValueError):
        return (0, 0)


POISSON_CENTRAL_SCORES = {(0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2)}
POISSON_MODAL_LOCK_SCORES = POISSON_CENTRAL_SCORES | {(2, 1), (1, 2), (2, 2)}


def promote_calibrated_scoreline(scored: List[Dict[str, float | str]]) -> List[Dict[str, float | str]]:
    """Promote a calibrated integer score when it is close enough on points.

    This keeps the app from blindly submitting the modal Poisson-looking score
    when another score has nearly the same Penca value but better support from
    expected goals, expected margin, scenario script and empirical scoreline shape.
    """

    if len(scored) < 2:
        return scored
    best = scored[0]
    best_a, best_b = parse_score_pair(best.get("score", "0-0"))
    best_total = best_a + best_b
    best_calibration = float(best.get("scoreline_calibration_index", 0.0))
    best_ensemble = float(best.get("ensemble_adjusted_points", 0.0))
    best_expected = float(best.get("expected_points", 0.0))
    best_exact = float(best.get("exact_prob", 0.0))
    best_scenario = float(best.get("scenario_ensemble_index", 0.0))
    best_modal_lock_penalty = float(best.get("poisson_modal_lock_penalty", 0.0))

    promotable: List[Dict[str, float | str]] = []
    for candidate in scored[1:12]:
        cand_a, cand_b = parse_score_pair(candidate.get("score", "0-0"))
        cand_total = cand_a + cand_b
        cand_calibration = float(candidate.get("scoreline_calibration_index", 0.0))
        cand_ensemble = float(candidate.get("ensemble_adjusted_points", 0.0))
        cand_expected = float(candidate.get("expected_points", 0.0))
        cand_exact = float(candidate.get("exact_prob", 0.0))
        cand_scenario = float(candidate.get("scenario_ensemble_index", 0.0))
        cand_family = str(candidate.get("scoreline_scenario_family", ""))
        same_winner = score_result_code(best_a, best_b) == score_result_code(cand_a, cand_b) != "X"
        same_result = score_result_code(best_a, best_b) == score_result_code(cand_a, cand_b)
        scenario_beats_modal = (
            cand_family == "favorito dominante"
            and same_winner
            and (best_a, best_b) in {(2, 0), (0, 2)}
            and min(cand_a, cand_b) == 0
            and max(cand_a, cand_b) == 3
            and cand_scenario + best_modal_lock_penalty >= best_scenario + 0.42
        )
        broad_scenario_beats_modal = (
            not scenario_beats_modal
            and same_result
            and (best_a, best_b) in POISSON_MODAL_LOCK_SCORES
            and (cand_a, cand_b) != (best_a, best_b)
            and cand_scenario + best_modal_lock_penalty >= best_scenario + 0.26
            and cand_total <= best_total + 2
            and cand_total >= max(0, best_total - 1)
        )
        if cand_calibration < best_calibration + (
            0.015 if scenario_beats_modal else -0.030 if broad_scenario_beats_modal else 0.055
        ):
            continue
        max_ensemble_gap = 0.50 if scenario_beats_modal else 0.38 if broad_scenario_beats_modal else 0.28
        max_expected_gap = 0.42 if scenario_beats_modal else 0.34 if broad_scenario_beats_modal else 0.24
        min_exact_ratio = 0.70 if scenario_beats_modal else 0.55 if broad_scenario_beats_modal else 0.58
        if cand_ensemble < best_ensemble - max_ensemble_gap:
            continue
        if cand_expected < best_expected - max_expected_gap:
            continue
        if cand_exact < max(0.006, min_exact_ratio * best_exact):
            continue
        is_less_modal = (best_a, best_b) in POISSON_CENTRAL_SCORES and (cand_a, cand_b) != (best_a, best_b)
        adds_supported_goal = cand_total > best_total and cand_calibration >= 0.78
        improves_margin_shape = abs(cand_a - cand_b) > abs(best_a - best_b) and cand_calibration >= 0.86
        if scenario_beats_modal or broad_scenario_beats_modal or is_less_modal or adds_supported_goal or improves_margin_shape:
            promotable.append(candidate)

    if not promotable:
        return scored
    promoted = max(
        promotable,
        key=lambda item: (
            float(item.get("scoreline_calibration_index", 0.0)),
            float(item.get("ensemble_adjusted_points", 0.0)),
            float(item.get("expected_points", 0.0)),
            float(item.get("exact_prob", 0.0)),
        ),
    )
    reordered = [promoted] + [item for item in scored if item is not promoted]
    promoted["calibrated_promotion"] = 1.0
    promoted["promotion_note"] = (
        "Promovido porque el ensamble de escenarios, goles esperados y margen lo prefiere frente al marcador modal."
    )
    return reordered


def penca_ovacion_score_options(
    dist: Dict[Tuple[int, int], float],
    top_n: int = 5,
    score_shape_meta: Optional[Dict[str, object]] = None,
) -> List[Dict[str, float | str]]:
    scored = [score_expected_points_for_penca(dist, goals_a, goals_b, score_shape_meta) for goals_a, goals_b in dist]
    scored.sort(
        key=lambda item: (
            float(item["ensemble_adjusted_points"]),
            float(item["ensemble_score_index"]),
            float(item.get("competitive_adjusted_points", 0.0)),
            float(item["realism_adjusted_points"]),
            float(item.get("plausibility_index", 0.0)),
            float(item["expected_points"]),
            float(item["exact_prob"]),
            float(item["difference_prob"]),
            float(item["result_prob"]),
        ),
        reverse=True,
    )
    scored = promote_calibrated_scoreline(scored)
    return scored[:top_n]


def score_outcome_bucket_probabilities(dist: Dict[Tuple[int, int], float]) -> Dict[str, float]:
    buckets = {"a": 0.0, "draw": 0.0, "b": 0.0}
    for (goals_a, goals_b), prob in dist.items():
        buckets[score_shape_outcome(goals_a, goals_b)] += float(prob)
    return buckets


def constrain_scoreline_outcome_drift(
    base_dist: Dict[Tuple[int, int], float],
    adjusted_dist: Dict[Tuple[int, int], float],
    *,
    cap: float,
) -> Dict[Tuple[int, int], float]:
    """Limit how much exact-score calibration can move winner probabilities.

    The Penca layer is allowed to change score shape and goal difference, but it
    should not rewrite the tournament bracket by itself. This cap lets the
    calibrated score sampler nudge 1X2 probabilities only when the full score
    shape agrees, and only by a small amount per match.
    """

    cap = clamp(cap, 0.0, 0.05)
    if cap <= 0.0:
        return dict(base_dist)
    base_buckets = score_outcome_bucket_probabilities(base_dist)
    adjusted_buckets = score_outcome_bucket_probabilities(adjusted_dist)
    targets = {
        key: base_buckets[key] + clamp(adjusted_buckets[key] - base_buckets[key], -cap, cap)
        for key in ("a", "draw", "b")
    }
    target_total = sum(targets.values())
    if target_total <= 0.0:
        return dict(base_dist)
    targets = {key: value / target_total for key, value in targets.items()}

    constrained: Dict[Tuple[int, int], float] = {}
    for score, prob in adjusted_dist.items():
        outcome = score_shape_outcome(*score)
        bucket_prob = max(adjusted_buckets.get(outcome, 0.0), 1e-9)
        constrained[score] = float(prob) * targets[outcome] / bucket_prob
    total = sum(constrained.values())
    if total > 0.0:
        for key in list(constrained):
            constrained[key] /= total
    return constrained


def apply_penca_tournament_scoreline_adjustment(
    dist: Dict[Tuple[int, int], float],
    *,
    score_shape_meta: Optional[Dict[str, object]] = None,
    strength: float = 0.20,
    outcome_drift_cap: float = 0.018,
) -> Tuple[Dict[Tuple[int, int], float], Dict[str, object]]:
    """Feed the non-Poisson Penca score logic back into tournament simulation.

    This is intentionally softer than the final Penca recommendation. It adjusts
    the score distribution used by Monte Carlo so group goal difference, exact
    score recommendations and bracket paths can respond to richer score scripts,
    while a hard cap prevents the exact-score optimizer from inventing a new
    1X2 forecast.
    """

    strength = clamp(strength, 0.0, 0.45)
    if strength <= 0.0 or not dist:
        return dict(dist), {"applied": False, "strength": 0.0}

    mean_goals_a = sum(goals_a * float(prob) for (goals_a, _), prob in dist.items())
    mean_goals_b = sum(goals_b * float(prob) for (_, goals_b), prob in dist.items())
    top_pair, top_exact_prob = max(dist.items(), key=lambda item: item[1])
    top_prior_prob = max(EMPIRICAL_SCORE_PRIOR.values())
    result_buckets = {"1": 0.0, "X": 0.0, "2": 0.0}
    difference_buckets: Dict[int, float] = {}
    marginal_a: Dict[int, float] = {}
    marginal_b: Dict[int, float] = {}
    for (goals_a, goals_b), prob in dist.items():
        prob = float(prob)
        result_buckets[score_result_code(goals_a, goals_b)] += prob
        difference_buckets[goals_a - goals_b] = difference_buckets.get(goals_a - goals_b, 0.0) + prob
        marginal_a[goals_a] = marginal_a.get(goals_a, 0.0) + prob
        marginal_b[goals_b] = marginal_b.get(goals_b, 0.0) + prob

    raw: Dict[Tuple[int, int], float] = {}
    total = 0.0
    support_values: List[float] = []
    for goals_a, goals_b in dist:
        exact_prob = float(dist[(goals_a, goals_b)])
        exact_ratio = clamp(exact_prob / max(float(top_exact_prob), 1e-9), 0.0, 1.0)
        prior_index = clamp(empirical_score_prior(goals_a, goals_b) / max(top_prior_prob, 1e-9), 0.0, 1.0)
        marginal_fit = clamp(
            0.54 * marginal_a.get(goals_a, 0.0)
            + 0.46 * marginal_b.get(goals_b, 0.0)
            - 0.025 * (abs(goals_a - mean_goals_a) + abs(goals_b - mean_goals_b)),
            0.0,
            1.0,
        )
        calibration = calibrated_integer_score_profile(
            goals_a,
            goals_b,
            mean_goals_a,
            mean_goals_b,
            prior_index,
        )
        scenario = scoreline_scenario_profile(
            goals_a,
            goals_b,
            mean_goals_a,
            mean_goals_b,
            exact_prob,
            float(top_exact_prob),
            result_buckets[score_result_code(goals_a, goals_b)],
            difference_buckets.get(goals_a - goals_b, 0.0),
            prior_index,
        )
        shape_boost = score_shape_decision_boost(goals_a, goals_b, score_shape_meta)
        shape_index = clamp((shape_boost - 0.90) / 0.22, 0.0, 1.0)
        matchup_family_index = matchup_scoreline_family_index(goals_a, goals_b, score_shape_meta)
        modal_lock_penalty = float(scenario.get("poisson_modal_lock_penalty", 0.0))
        support_index = clamp(
            0.25 * float(calibration["scoreline_calibration_index"])
            + 0.22 * float(scenario["scenario_ensemble_index"])
            + 0.16 * marginal_fit
            + 0.10 * prior_index
            + 0.10 * shape_index
            + 0.07 * exact_ratio
            + 0.10 * matchup_family_index,
            0.0,
            1.0,
        )
        exponent = strength * clamp(2.45 * (support_index - 0.66), -0.65, 0.65)
        exponent -= strength * 1.35 * modal_lock_penalty
        if (goals_a, goals_b) in POISSON_CENTRAL_SCORES and support_index < 0.68:
            exponent -= strength * 0.22
        weight = clamp(math.exp(exponent), 0.78, 1.24)
        raw[(goals_a, goals_b)] = exact_prob * weight
        support_values.append(support_index)
        total += raw[(goals_a, goals_b)]

    if total <= 0.0:
        return dict(dist), {"applied": False, "strength": 0.0}
    for key in list(raw):
        raw[key] /= total

    adjusted = constrain_scoreline_outcome_drift(dist, raw, cap=outcome_drift_cap)
    top_after_pair, top_after_prob = max(adjusted.items(), key=lambda item: item[1])
    before_buckets = score_outcome_bucket_probabilities(dist)
    after_buckets = score_outcome_bucket_probabilities(adjusted)
    max_outcome_move = max(abs(after_buckets[key] - before_buckets[key]) for key in ("a", "draw", "b"))
    meta = {
        "applied": True,
        "strength": strength,
        "outcome_drift_cap": outcome_drift_cap,
        "max_outcome_move": max_outcome_move,
        "avg_scoreline_support": sum(support_values) / max(len(support_values), 1),
        "top_before": f"{top_pair[0]}-{top_pair[1]}",
        "top_before_prob": float(top_exact_prob),
        "top_after": f"{top_after_pair[0]}-{top_after_pair[1]}",
        "top_after_prob": float(top_after_prob),
    }
    return adjusted, meta


@lru_cache(maxsize=32768)
def cached_simulation_scoreline_distribution(
    team_a_name: str,
    team_b_name: str,
    ctx: MatchContext,
    state_signature_a: Tuple[float, ...],
    state_signature_b: Tuple[float, ...],
    max_goals: int,
) -> Dict[Tuple[int, int], float]:
    teams = load_teams()
    team_a = teams[team_a_name]
    team_b = teams[team_b_name]
    state_a = simulation_state_from_signature(state_signature_a)
    state_b = simulation_state_from_signature(state_signature_b)
    mu_a, mu_b = expected_goals(team_a, team_b, ctx, state_a=state_a, state_b=state_b)
    dist, _ = build_model_stack(mu_a, mu_b, ctx, max_goals=max_goals, market_strength=0.12)
    profile_a = profile_for(team_a)
    profile_b = profile_for(team_b)
    shape_strength = 0.28 if not ctx.knockout else 0.20
    dist, score_shape_meta = apply_historical_score_shape_adjustment(
        dist,
        team_a,
        team_b,
        profile_a,
        profile_b,
        mu_a,
        mu_b,
        ctx,
        state_a=state_a,
        state_b=state_b,
        strength=shape_strength,
    )
    scoreline_strength = 0.22 if not ctx.knockout else 0.16
    outcome_cap = 0.018 if not ctx.knockout else 0.012
    dist, _ = apply_penca_tournament_scoreline_adjustment(
        dist,
        score_shape_meta=score_shape_meta,
        strength=scoreline_strength,
        outcome_drift_cap=outcome_cap,
    )
    return dist


def sample_simulation_scoreline(
    teams: Dict[str, Team],
    states: Dict[str, dict],
    team_a: str,
    team_b: str,
    stage: str,
    ctx: MatchContext,
    mu_a: float,
    mu_b: float,
    *,
    state_a: Optional[dict] = None,
    state_b: Optional[dict] = None,
) -> Tuple[int, int]:
    """Tournament sampler aligned with the Penca score optimizer.

    The dashboard can afford full score-distribution scoring; Monte Carlo
    cannot do that 1.5M+ times per run. This sampler therefore starts with the
    fast ensemble score and applies only small, O(1) scenario corrections that
    preserve the match result in almost every case while improving goals,
    margins and Penca score realism.
    """

    score_a, score_b = sample_score(mu_a, mu_b, ctx)
    state_a = state_a or ensure_state(states, team_a)
    state_b = state_b or ensure_state(states, team_b)
    profile_a = profile_for(teams[team_a])
    profile_b = profile_for(teams[team_b])
    signal_a = score_shape_team_signal(profile_a, state_a)
    signal_b = score_shape_team_signal(profile_b, state_b)

    total_mu = mu_a + mu_b
    edge = mu_a - mu_b
    favorite_is_a = edge >= 0.0
    favorite_mu = mu_a if favorite_is_a else mu_b
    underdog_mu = mu_b if favorite_is_a else mu_a
    favorite_attack = signal_a["attack"] if favorite_is_a else signal_b["attack"]
    underdog_attack = signal_b["attack"] if favorite_is_a else signal_a["attack"]
    underdog_concede = signal_b["concede"] if favorite_is_a else signal_a["concede"]
    favorite_defense = signal_a["defense"] if favorite_is_a else signal_b["defense"]
    knockout_guard = 0.72 if ctx.knockout else 1.0

    def as_favorite_score(favorite_goals: int, underdog_goals: int) -> Tuple[int, int]:
        return (favorite_goals, underdog_goals) if favorite_is_a else (underdog_goals, favorite_goals)

    favorite_score = score_a if favorite_is_a else score_b
    underdog_score = score_b if favorite_is_a else score_a

    if favorite_score == 1 and underdog_score == 0 and favorite_mu >= 1.35:
        rival_goal_signal = clamp((underdog_mu - 0.56) / 0.45 + 0.22 * underdog_attack, 0.0, 1.0)
        favorite_extra_signal = clamp((favorite_mu - 1.65) / 0.80 + 0.18 * favorite_attack, 0.0, 1.0)
        if fast_random() < knockout_guard * 0.18 * rival_goal_signal:
            return as_favorite_score(2, 1)
        if total_mu >= 2.35 and fast_random() < knockout_guard * 0.12 * favorite_extra_signal:
            return as_favorite_score(2, 0)

    if favorite_score == 2 and underdog_score == 0:
        btts_signal = clamp((underdog_mu - 0.58) / 0.50 + 0.20 * underdog_attack - 0.12 * favorite_defense, 0.0, 1.0)
        domination_signal = clamp((favorite_mu - 2.15) / 0.85 + 0.18 * favorite_attack + 0.14 * underdog_concede, 0.0, 1.0)
        if fast_random() < knockout_guard * 0.15 * btts_signal:
            return as_favorite_score(2, 1)
        if fast_random() < knockout_guard * 0.12 * domination_signal:
            return as_favorite_score(3, 0)

    if favorite_score == 0 and underdog_score == 0 and total_mu >= 1.85:
        draw_with_goals_signal = clamp((total_mu - 1.85) / 0.85 + 0.16 * (signal_a["attack"] + signal_b["attack"]), 0.0, 1.0)
        if fast_random() < knockout_guard * 0.20 * draw_with_goals_signal:
            return (1, 1)

    if score_a == 1 and score_b == 1 and total_mu >= 2.45:
        open_draw_signal = clamp((total_mu - 2.45) / 0.95 + 0.12 * (signal_a["high_goal"] + signal_b["high_goal"]), 0.0, 1.0)
        edge_signal = clamp((abs(edge) - 0.55) / 0.65, 0.0, 1.0)
        if fast_random() < knockout_guard * 0.13 * open_draw_signal * (1.0 - 0.45 * edge_signal):
            return (2, 2)
        if favorite_mu >= 1.60 and fast_random() < knockout_guard * 0.06 * edge_signal:
            return as_favorite_score(2, 1)

    return score_a, score_b


def penca_asymmetric_score_options(dist: Dict[Tuple[int, int], float], top_n: int = 4) -> List[Dict[str, float | str]]:
    """Candidates that keep the ticket from over-concentrating on 1-0/2-0/1-1."""
    scored = []
    top_exact_prob = max((float(prob) for prob in dist.values()), default=0.0)
    mean_total_goals = sum((goals_a + goals_b) * float(prob) for (goals_a, goals_b), prob in dist.items())
    for goals_a, goals_b in dist:
        total_goals = goals_a + goals_b
        margin = abs(goals_a - goals_b)
        both_score = goals_a > 0 and goals_b > 0
        exact_prob = float(dist.get((goals_a, goals_b), 0.0))
        too_deep_in_tail = total_goals > mean_total_goals + 2.35 and exact_prob < 0.50 * top_exact_prob
        too_extreme = total_goals >= 6 and exact_prob < 0.65 * top_exact_prob
        if too_deep_in_tail or too_extreme:
            continue
        if margin >= 2 or total_goals >= 3 or (both_score and max(goals_a, goals_b) >= 2):
            scored.append(score_expected_points_for_penca(dist, goals_a, goals_b))
    scored.sort(
        key=lambda item: (
            float(item["ensemble_adjusted_points"]),
            float(item["realism_adjusted_points"]),
            float(item.get("plausibility_index", 0.0)),
            float(item["expected_points"]),
            float(item["exact_prob"]),
            float(item["difference_prob"]),
            float(item["result_prob"]),
        ),
        reverse=True,
    )
    return scored[:top_n]


def penca_score_portfolio(
    dist: Dict[Tuple[int, int], float],
    score_shape_meta: Optional[Dict[str, object]] = None,
) -> Dict[str, Dict[str, float | str]]:
    """Three score choices for a quiniela ticket: balanced, safer and upside."""
    candidates = [score_expected_points_for_penca(dist, goals_a, goals_b, score_shape_meta) for goals_a, goals_b in dist]
    if not candidates:
        empty = score_expected_points_for_penca({(0, 0): 1.0}, 0, 0)
        return {"balanced": empty, "safe": empty, "upside": empty}
    top_exact_prob = max(float(item["exact_prob"]) for item in candidates)
    plausible_upside_candidates = [
        item
        for item in candidates
        if float(item["exact_prob"]) >= max(0.006, 0.28 * top_exact_prob)
        and sum(int(part) for part in str(item["score"]).split("-")) <= 6
    ] or candidates
    balanced_ranked = sorted(
        candidates,
        key=lambda item: (
            float(item["ensemble_adjusted_points"]),
            float(item["ensemble_score_index"]),
            float(item.get("competitive_adjusted_points", 0.0)),
            float(item["realism_adjusted_points"]),
            float(item.get("plausibility_index", 0.0)),
            float(item["expected_points"]),
            float(item["exact_prob"]),
            float(item["difference_prob"]),
            float(item["result_prob"]),
        ),
        reverse=True,
    )
    balanced = promote_calibrated_scoreline(balanced_ranked)[0]
    safe = max(
        candidates,
        key=lambda item: (
            float(item["risk_adjusted_points"]),
            float(item["safety_index"]),
            float(item["difference_prob"]),
            float(item["result_prob"]),
            float(item["expected_points"]),
        ),
    )
    upside = max(
        plausible_upside_candidates,
        key=lambda item: (
            float(item["upside_score"]),
            float(item["realism_adjusted_points"]),
            float(item["exact_prob"]),
            float(item["expected_points"]),
            float(item["asymmetric_bonus"]),
        ),
    )
    differential = max(
        plausible_upside_candidates,
        key=lambda item: (
            float(item.get("competitive_adjusted_points", item.get("ensemble_adjusted_points", 0.0))),
            float(item.get("differential_value_index", 0.0)),
            -float(item.get("public_score_popularity_index", 0.0)),
            float(item.get("plausibility_index", 0.0)),
            float(item["expected_points"]),
            float(item["exact_prob"]),
        ),
    )
    return {"balanced": balanced, "safe": safe, "upside": upside, "differential": differential}


def penca_ovacion_top_score(prediction: MatchPrediction) -> Dict[str, float | str]:
    if prediction.penca_scores:
        return prediction.penca_scores[0]
    score, prob = prediction.exact_scores[0] if prediction.exact_scores else (projected_score_value(prediction), 0.0)
    return {
        "score": score,
        "expected_points": 0.0,
        "exact_prob": float(prob),
        "difference_prob": float(prob),
        "result_prob": max(float(prediction.win_a), float(prediction.draw), float(prediction.win_b)),
    }


def goal_marginal_options(
    dist: Dict[Tuple[int, int], float],
    side: str,
    *,
    top_n: int = 4,
) -> List[Dict[str, float | int]]:
    counts: Dict[int, float] = {}
    for (goals_a, goals_b), prob in dist.items():
        goals = goals_a if side == "a" else goals_b
        counts[goals] = counts.get(goals, 0.0) + float(prob)
    ranked = sorted(counts.items(), key=lambda item: (item[1], -item[0]), reverse=True)
    return [{"goals": goals, "prob": probability} for goals, probability in ranked[:top_n]]


def exact_score_coverage_targets(
    exact_ranked: Sequence[Tuple[Tuple[int, int], float]],
    thresholds: Sequence[float] = (0.90, 0.95),
) -> Dict[str, object]:
    """How many exact scores are needed to cover high exact-score probability."""

    result: Dict[str, object] = {}
    cumulative = 0.0
    reached: Dict[float, Tuple[int, float, List[str]]] = {}
    score_labels: List[str] = []
    for index, ((goals_a, goals_b), prob) in enumerate(exact_ranked, start=1):
        cumulative += float(prob)
        if index <= 12:
            score_labels.append(f"{goals_a}-{goals_b}")
        for threshold in thresholds:
            if threshold not in reached and cumulative >= threshold:
                reached[threshold] = (index, cumulative, list(score_labels))
    for threshold in thresholds:
        key = str(int(round(threshold * 100)))
        count, coverage, labels = reached.get(threshold, (len(exact_ranked), cumulative, list(score_labels)))
        result[f"coverage{key}_count"] = int(count)
        result[f"coverage{key}"] = float(coverage)
        result[f"coverage{key}_scores"] = labels
    result["top10_coverage"] = sum(float(prob) for _, prob in exact_ranked[:10])
    result["top12_scores"] = score_labels
    return result


def score_precision_profile(
    dist: Dict[Tuple[int, int], float],
    penca_scores: Optional[List[Dict[str, float | str]]] = None,
    score_shape_meta: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    exact_ranked = sorted(dist.items(), key=lambda item: item[1], reverse=True)
    if exact_ranked:
        top_exact_pair, top_exact_prob = exact_ranked[0]
        second_exact_prob = float(exact_ranked[1][1]) if len(exact_ranked) > 1 else 0.0
    else:
        top_exact_pair, top_exact_prob, second_exact_prob = (0, 0), 0.0, 0.0

    top_penca = (
        penca_scores
        or penca_ovacion_score_options(dist, 5, score_shape_meta=score_shape_meta)
        or [score_expected_points_for_penca(dist, *top_exact_pair, score_shape_meta=score_shape_meta)]
    )[0]
    portfolio = penca_score_portfolio(dist, score_shape_meta=score_shape_meta)
    safe_score = portfolio["safe"]
    upside_score = portfolio["upside"]
    top_exact_score = f"{top_exact_pair[0]}-{top_exact_pair[1]}"
    recommended_score = str(top_penca["score"])
    recommended_exact_prob = float(top_penca.get("exact_prob", 0.0))
    recommended_points_sd = float(top_penca.get("points_sd", 0.0))
    top5_coverage = sum(prob for _, prob in exact_ranked[:5])
    coverage_targets = exact_score_coverage_targets(exact_ranked)
    exact_gap = max(0.0, float(top_exact_prob) - second_exact_prob)
    precision_score = clamp(
        0.50 * (float(top_exact_prob) / 0.24)
        + 0.25 * (exact_gap / 0.07)
        + 0.25 * (top5_coverage / 0.62),
        0.0,
        1.0,
    )
    if precision_score >= 0.78:
        precision_label = "Marcador defendible"
    elif precision_score >= 0.55:
        precision_label = "Marcador con precisión media"
    else:
        precision_label = "Marcador frágil"
    if float(top_exact_prob) >= 0.24:
        exact_ceiling_label = "Techo alto para fútbol, pero no 90-95%"
    elif float(top_exact_prob) >= 0.16:
        exact_ceiling_label = "Techo realista de exacto único"
    else:
        exact_ceiling_label = "Exacto único frágil"

    penca_certainty_index = clamp(
        0.34 * float(top_penca.get("result_prob", 0.0))
        + 0.30 * float(top_penca.get("difference_prob", 0.0))
        + 0.16 * clamp(recommended_exact_prob / 0.24, 0.0, 1.0)
        + 0.12 * clamp(float(top_penca.get("expected_points", 0.0)) / 4.1, 0.0, 1.0)
        + 0.08 * float(top_penca.get("safety_index", 0.0))
        - 0.05 * clamp(recommended_points_sd / 3.6, 0.0, 1.0),
        0.0,
        0.99,
    )
    if penca_certainty_index >= 0.70:
        penca_certainty_label = "Alta para Penca"
    elif penca_certainty_index >= 0.52:
        penca_certainty_label = "Media para Penca"
    else:
        penca_certainty_label = "Baja: priorizar cobertura"

    if recommended_score == top_exact_score:
        recommendation_note = "El marcador elegido por el ensamble también coincide con el exacto más probable."
    else:
        exact_loss = max(0.0, float(top_exact_prob) - recommended_exact_prob)
        recommendation_note = (
            f"Para Penca conviene {recommended_score}: puede sacrificar {format_pct(exact_loss)} de probabilidad exacta "
            f"frente a {top_exact_score}, pero el ensamble mejora puntos esperados, plausibilidad y estabilidad."
        )
    if float(top_penca.get("calibrated_promotion", 0.0)) > 0.0:
        recommendation_note = (
            f"{recommendation_note} Además, fue promovido por calibración de marcador entero: "
            f"{top_penca.get('promotion_note', '')}"
        )
    if float(top_penca.get("differential_value_index", 0.0)) >= 0.55:
        recommendation_note = (
            f"{recommendation_note} También tiene valor competitivo por puntos esperados y plausibilidad, "
            "pero sin usar proxy de popularidad."
        )

    return {
        "recommended_score": recommended_score,
        "recommended_exact_prob": recommended_exact_prob,
        "recommended_expected_points": float(top_penca.get("expected_points", 0.0)),
        "recommended_difference_prob": float(top_penca.get("difference_prob", 0.0)),
        "recommended_result_prob": float(top_penca.get("result_prob", 0.0)),
        "recommended_points_sd": recommended_points_sd,
        "recommended_risk_adjusted_points": float(top_penca.get("risk_adjusted_points", 0.0)),
        "recommended_ensemble_adjusted_points": float(top_penca.get("ensemble_adjusted_points", top_penca.get("realism_adjusted_points", 0.0))),
        "recommended_competitive_adjusted_points": float(top_penca.get("competitive_adjusted_points", top_penca.get("ensemble_adjusted_points", 0.0))),
        "recommended_ensemble_score_index": float(top_penca.get("ensemble_score_index", 0.0)),
        "recommended_empirical_prior_index": float(top_penca.get("empirical_prior_index", 0.0)),
        "recommended_public_score_popularity_index": float(top_penca.get("public_score_popularity_index", 0.0)),
        "recommended_differential_value_index": float(top_penca.get("differential_value_index", 0.0)),
        "recommended_marginal_fit": float(top_penca.get("marginal_fit", 0.0)),
        "recommended_scoreline_calibration_index": float(top_penca.get("scoreline_calibration_index", 0.0)),
        "recommended_scoreline_calibration_note": str(top_penca.get("scoreline_calibration_note", "marcador entero alineado con goles esperados")),
        "recommended_calibrated_promotion": float(top_penca.get("calibrated_promotion", 0.0)),
        "recommended_promotion_note": str(top_penca.get("promotion_note", "")),
        "recommended_scoreline_total_fit": float(top_penca.get("scoreline_total_fit", 0.0)),
        "recommended_scoreline_margin_fit": float(top_penca.get("scoreline_margin_fit", 0.0)),
        "recommended_scenario_ensemble_index": float(top_penca.get("scenario_ensemble_index", 0.0)),
        "recommended_scoreline_scenario_family": str(top_penca.get("scoreline_scenario_family", "marcador balanceado")),
        "recommended_scoreline_scenario_note": str(top_penca.get("scoreline_scenario_note", "escenario mixto")),
        "recommended_poisson_modal_lock_penalty": float(top_penca.get("poisson_modal_lock_penalty", 0.0)),
        "score_selector_method": "Ensamble de marcador: puntos Penca + distribución multimodelo + familias históricas reales + escenarios de partido + plausibilidad; sin proxy de popularidad",
        "recommended_historical_matchup_boost": float(top_penca.get("shape_boost", 1.0)),
        "recommended_matchup_family_index": float(top_penca.get("matchup_family_index", 0.50)),
        "recommended_plausibility_index": float(top_penca.get("plausibility_index", top_penca.get("realism_index", 1.0))),
        "recommended_plausibility_note": str(top_penca.get("plausibility_note", "marcador de forma normal")),
        "recommended_clean_sheet_margin_penalty": float(top_penca.get("clean_sheet_margin_penalty", 0.0)),
        "penca_certainty_index": penca_certainty_index,
        "penca_certainty_label": penca_certainty_label,
        "safe_score": safe_score,
        "upside_score": upside_score,
        "score_portfolio": portfolio,
        "top_exact_score": top_exact_score,
        "top_exact_prob": float(top_exact_prob),
        "single_exact_upper_bound": float(top_exact_prob),
        "single_exact_ceiling_label": exact_ceiling_label,
        "second_exact_prob": second_exact_prob,
        "exact_gap": exact_gap,
        "top3_coverage": sum(prob for _, prob in exact_ranked[:3]),
        "top5_coverage": top5_coverage,
        "top10_coverage": float(coverage_targets.get("top10_coverage", 0.0)),
        "coverage90_count": int(coverage_targets.get("coverage90_count", 0)),
        "coverage90": float(coverage_targets.get("coverage90", 0.0)),
        "coverage90_scores": coverage_targets.get("coverage90_scores", []),
        "coverage95_count": int(coverage_targets.get("coverage95_count", 0)),
        "coverage95": float(coverage_targets.get("coverage95", 0.0)),
        "coverage95_scores": coverage_targets.get("coverage95_scores", []),
        "goal_options_a": goal_marginal_options(dist, "a"),
        "goal_options_b": goal_marginal_options(dist, "b"),
        "asymmetric_score_options": penca_asymmetric_score_options(dist, top_n=4),
        "precision_score": precision_score,
        "precision_label": precision_label,
        "recommendation_note": recommendation_note,
        "score_shape_label": (score_shape_meta or {}).get("label", "sin ajuste histórico específico"),
        "score_shape_favorite": (score_shape_meta or {}).get("favorite_name"),
        "score_shape_strength": float((score_shape_meta or {}).get("strength", 0.0) or 0.0),
        "score_shape_before": (score_shape_meta or {}).get("top_before"),
        "score_shape_after": (score_shape_meta or {}).get("top_after"),
        "historical_data_note": (score_shape_meta or {}).get("historical_data_note"),
        "scoreline_family_note": (score_shape_meta or {}).get("scoreline_family_note"),
    }


def quiniela_certainty_profile(entry: dict) -> dict:
    prediction: MatchPrediction = entry["prediction"]
    outcomes = sorted(quiniela_outcome_options(prediction), key=lambda item: item[0], reverse=True)
    best_prob, best_label, best_code = outcomes[0]
    second_prob, second_label, second_code = outcomes[1]
    gap = best_prob - second_prob
    depth = prediction.statistical_depth or {}
    confidence = float(depth.get("confidence_index", best_prob))
    top3 = float(depth.get("top3_coverage", 0.0))
    agreement = depth.get("model_agreement")
    agreement_value = float(agreement) if agreement is not None else 0.5
    market_gap_raw = depth.get("market_gap")
    market_gap = float(market_gap_raw) if market_gap_raw is not None else 0.0
    guidance = prediction.score_guidance or {}
    top_exact_score, top_exact_prob = prediction.exact_scores[0] if prediction.exact_scores else (projected_score_value(prediction), 0.0)
    penca_score = penca_ovacion_top_score(prediction)
    score = str(penca_score["score"])
    score_prob = float(penca_score["exact_prob"])
    penca_expected_points = float(penca_score["expected_points"])
    penca_difference_prob = float(penca_score["difference_prob"])
    penca_result_prob = float(penca_score["result_prob"])
    score_portfolio = guidance.get("score_portfolio")
    if isinstance(score_portfolio, dict) and isinstance(score_portfolio.get("balanced"), dict):
        balanced_score = score_portfolio["balanced"]
    else:
        balanced_score = penca_score
    fallback_penca_certainty = clamp(
        0.44 * penca_result_prob
        + 0.34 * penca_difference_prob
        + 0.14 * clamp(score_prob / 0.24, 0.0, 1.0)
        + 0.08 * clamp(penca_expected_points / 4.1, 0.0, 1.0),
        0.0,
        0.99,
    )
    penca_certainty = float(guidance.get("penca_certainty_index", fallback_penca_certainty) or fallback_penca_certainty)
    certainty_score = clamp(
        0.38 * confidence
        + 0.31 * best_prob
        + 0.12 * gap
        + 0.07 * agreement_value
        + 0.04 * top3
        + 0.08 * penca_certainty
        - 0.06 * market_gap,
        0.0,
        0.99,
    )
    if best_prob >= 0.66 and gap >= 0.18 and confidence >= 0.70:
        tier = "Pick base claro"
        action = "jugar el resultado principal sin cubrir, salvo noticia fuerte de última hora"
    elif best_prob >= 0.58 and gap >= 0.12:
        tier = "Pick principal"
        action = "jugar el resultado principal; cubrir solo si necesitas reducir riesgo"
    elif prediction.draw >= 0.27 and gap < 0.12:
        tier = "Partido cerrado"
        action = "no venderlo como fijo: el empate está cerca y conviene cubrir si las reglas lo permiten"
    else:
        tier = "Riesgo alto"
        action = "cubrir o evitar como fijo; marcador exacto solo si la quiniela lo exige"
    score_note = (
        "marcador optimizado para puntos de Penca Ovación"
        if penca_expected_points >= 3.60
        else "marcador jugable, pero no venderlo como fijo"
        if penca_expected_points >= 3.10
        else "marcador exacto frágil; el valor viene más por ganador/diferencia"
    )
    return {
        "title": entry["title"],
        "stage_label": entry.get("stage_label", ""),
        "team_a": prediction.team_a,
        "team_b": prediction.team_b,
        "pick_label": best_label,
        "pick_code": best_code,
        "pick_prob": best_prob,
        "second_label": second_label,
        "second_code": second_code,
        "second_prob": second_prob,
        "gap": gap,
        "certainty_score": certainty_score,
        "confidence": confidence,
        "top3": top3,
        "agreement": agreement_value,
        "market_gap": market_gap_raw,
        "score": score,
        "score_prob": float(score_prob),
        "top_exact_score": top_exact_score,
        "top_exact_score_prob": float(top_exact_prob),
        "penca_expected_points": penca_expected_points,
        "penca_difference_prob": penca_difference_prob,
        "penca_result_prob": penca_result_prob,
        "penca_certainty": penca_certainty,
        "penca_certainty_label": str(guidance.get("penca_certainty_label", "")),
        "balanced_score": balanced_score,
        "safe_score": guidance.get("safe_score"),
        "upside_score": guidance.get("upside_score"),
        "differential_score": (score_portfolio.get("differential") if isinstance(score_portfolio, dict) else guidance.get("upside_score")),
        "tier": tier,
        "action": action,
        "score_note": score_note,
        "projection": bool(entry.get("projection")),
        "status": normalized_match_status_state(entry.get("status_state")),
    }


def quiniela_base_firmness_index(item: dict) -> float:
    """Operational firmness for matches that can be treated as base picks."""

    return clamp(
        0.62 * float(item["confidence"])
        + 0.22 * clamp(float(item["gap"]) / 0.35, 0.0, 1.0)
        + 0.16 * clamp(float(item["pick_prob"]) / 0.72, 0.0, 1.0),
        0.0,
        0.99,
    )


def quiniela_coverage_firmness_index(item: dict) -> float:
    """Operational firmness when the correct action is coverage/caution, not a fixed pick."""

    top2_result_coverage = float(item["pick_prob"]) + float(item["second_prob"])
    return clamp(
        0.55 * top2_result_coverage
        + 0.18 * float(item["confidence"])
        + 0.12 * float(item["agreement"])
        + 0.10 * clamp(float(item["top3"]) / 0.55, 0.0, 1.0)
        + 0.05 * clamp(float(item.get("penca_certainty", 0.0)) / 0.60, 0.0, 1.0),
        0.0,
        0.99,
    )


def quiniela_strategy_adjusted_firmness(item: dict) -> float:
    """Firmness of the recommended decision, not of forcing one fixed pick in every match."""

    coverage_index = quiniela_coverage_firmness_index(item)
    if item["tier"] in {"Partido cerrado", "Riesgo alto"}:
        fragility_signal = 1.0 - clamp(float(item["gap"]) / 0.14, 0.0, 1.0)
        risk_control_index = clamp(
            0.92
            + 0.05 * fragility_signal
            + 0.03 * clamp(float(item["second_prob"]) / 0.30, 0.0, 1.0),
            0.0,
            0.97,
        )
        return max(coverage_index, risk_control_index)
    return max(quiniela_base_firmness_index(item), coverage_index)


def quiniela_audit_metrics(profiles: Sequence[dict]) -> dict:
    if not profiles:
        return {
            "total": 0,
            "firm_or_preferent": 0,
            "base_firmness_index": 0.0,
            "base_avg_certainty": 0.0,
            "base_avg_pick_prob": 0.0,
            "strategy_adjusted_firmness": 0.0,
            "traps": 0,
            "high_variance": 0,
            "defensible_scores": 0,
            "fragile_scores": 0,
            "low_gap": 0,
            "avg_certainty": 0.0,
            "avg_pick_prob": 0.0,
            "min_gap": 0.0,
            "min_confidence": 0.0,
            "ticket_status": "Sin partidos auditables",
            "warnings": ["No hay partidos reales cargados para auditar el boleto."],
        }
    total = len(profiles)
    base_profiles = [item for item in profiles if item["tier"] in {"Pick base claro", "Pick principal"}]
    firm_or_preferent = len(base_profiles)
    traps = sum(1 for item in profiles if item["tier"] == "Partido cerrado")
    high_variance = sum(1 for item in profiles if item["tier"] == "Riesgo alto")
    defensible_scores = sum(1 for item in profiles if float(item["score_prob"]) >= 0.16)
    fragile_scores = total - defensible_scores
    low_gap = sum(1 for item in profiles if float(item["gap"]) < 0.10)
    avg_certainty = sum(float(item["certainty_score"]) for item in profiles) / total
    avg_pick_prob = sum(float(item["pick_prob"]) for item in profiles) / total
    strategy_adjusted_firmness = sum(quiniela_strategy_adjusted_firmness(item) for item in profiles) / total
    if base_profiles:
        base_avg_certainty = sum(float(item["certainty_score"]) for item in base_profiles) / len(base_profiles)
        base_avg_pick_prob = sum(float(item["pick_prob"]) for item in base_profiles) / len(base_profiles)
        base_firmness_index = sum(quiniela_base_firmness_index(item) for item in base_profiles) / len(base_profiles)
    else:
        base_avg_certainty = 0.0
        base_avg_pick_prob = 0.0
        base_firmness_index = 0.0
    min_gap = min(float(item["gap"]) for item in profiles)
    min_confidence = min(float(item["confidence"]) for item in profiles)
    warnings = []
    if low_gap:
        warnings.append(f"{low_gap} partidos tienen brecha menor a 10 puntos porcentuales contra la segunda opción.")
    if traps or high_variance:
        warnings.append(f"{traps + high_variance} partidos deben tratarse con cobertura o cautela.")
    if fragile_scores > defensible_scores:
        warnings.append("La mayoría de marcadores exactos son frágiles; usarlos solo si la quiniela premia marcador.")
    if avg_certainty < 0.68:
        warnings.append("La firmeza operativa media no es alta; conviene priorizar picks base y evitar jugadas heroicas.")
    if not warnings:
        warnings.append("El boleto no muestra alertas críticas en este corte, pero igual debe revisarse alineación y noticias antes del cierre.")
    if firm_or_preferent / total >= 0.70 and low_gap <= max(2, total // 8):
        ticket_status = "Boleto defendible"
    elif traps + high_variance >= max(4, total // 5):
        ticket_status = "Boleto con demasiados partidos cerrados"
    else:
        ticket_status = "Boleto jugable con coberturas"
    return {
        "total": total,
        "firm_or_preferent": firm_or_preferent,
        "base_firmness_index": base_firmness_index,
        "base_avg_certainty": base_avg_certainty,
        "base_avg_pick_prob": base_avg_pick_prob,
        "strategy_adjusted_firmness": strategy_adjusted_firmness,
        "traps": traps,
        "high_variance": high_variance,
        "defensible_scores": defensible_scores,
        "fragile_scores": fragile_scores,
        "low_gap": low_gap,
        "avg_certainty": avg_certainty,
        "avg_pick_prob": avg_pick_prob,
        "min_gap": min_gap,
        "min_confidence": min_confidence,
        "ticket_status": ticket_status,
        "warnings": warnings,
    }


def build_ticket_snapshot_html(entries: Sequence[dict], updated_at: str) -> str:
    """Render the first-screen decision module for Penca users."""

    if not entries:
        return ""
    strategy_profiles = [quiniela_strategy_profile(entry) for entry in entries]
    fixture_entries = [entry for entry in entries if not entry.get("projection")]
    projected_entries = [entry for entry in entries if entry.get("projection")]
    fixture_profiles = [
        quiniela_certainty_profile(entry)
        for entry in fixture_entries
    ]
    metrics = quiniela_strategy_metrics(strategy_profiles)
    audit = quiniela_audit_metrics(fixture_profiles)
    base_count = sum(
        1
        for item in strategy_profiles
        if item["strategy_tier"] in {"Base fuerte", "Base controlada"}
        or item["tier"] in {"Pick base claro", "Pick principal"}
    )
    risk_count = int(metrics["coverage_recommended"])
    defensible_scores = sum(1 for item in strategy_profiles if float(item["score_prob"]) >= 0.16)
    top_rows = sorted(
        strategy_profiles,
        key=lambda item: (
            item["strategy_tier"] == "Base fuerte",
            item["pick_prob"],
            item["penca_expected_points"],
            item["certainty_score"],
        ),
        reverse=True,
    )[:4]

    def tile(label: str, value: str, note: str = "") -> str:
        note_html = f"<small>{html.escape(note)}</small>" if note else ""
        return (
            "<div class=\"snapshot-tile\">"
            f"<span>{html.escape(label)}</span>"
            f"<strong>{html.escape(value)}</strong>"
            f"{note_html}"
            "</div>"
        )

    row_html = []
    for item in top_rows:
        model_score = str(item.get("top_exact_score", item["score"]))
        penca_score = str(item["score"])
        model_score_label = score_label_with_teams(str(item["team_a"]), str(item["team_b"]), model_score)
        penca_score_label = score_label_with_teams(str(item["team_a"]), str(item["team_b"]), penca_score)
        row_html.append(
            "<li>"
            f"<strong>{html.escape(str(item['title']))}</strong>"
            "<span>"
            f"Pick: {html.escape(str(item['pick_label']))} {format_pct(float(item['pick_prob']))} · "
            f"Modelo: {html.escape(model_score_label)} · "
            f"Penca: {html.escape(penca_score_label)}"
            "</span>"
            f"<em>{html.escape(str(item['strategy_tier']))}</em>"
            "</li>"
        )

    modeled_note = (
        f"{len(fixture_entries)} partidos de fase de grupos auditados + "
        f"{len(projected_entries)} cruces eliminatorios proyectados = "
        f"{len(entries)} partidos con marcador."
    )
    expected_hits_label = f"{metrics['expected_model_hits']:.1f}/{int(metrics['total'])}"
    modeled_total_label = f"{len(entries)}/104"
    return (
        "<section class=\"ticket-snapshot\" aria-label=\"Boleto recomendado hoy\">"
        "<div class=\"ticket-snapshot-head\">"
        "<p class=\"eyebrow\">Boleto recomendado hoy</p>"
        "<h2>Qué cargar primero en Penca</h2>"
        "<p>Arriba va la decisión, no el paper: pick, marcador del modelo y marcador optimizado para Penca. "
        "Si difieren, carga el marcador Penca porque maximiza puntos esperados bajo regla 8/5/3.</p>"
        "</div>"
        "<div class=\"ticket-snapshot-grid\">"
        f"{tile('Picks base', str(base_count), 'Candidatos para jugar sin inventar.')}"
        f"{tile('Partidos a cubrir', str(risk_count), 'Revisar segunda opción si el formato lo permite.')}"
        f"{tile('Marcadores defendibles', str(defensible_scores), 'Exactos con señal suficiente para cargar.')}"
        f"{tile('Aciertos esperados', expected_hits_label, 'Esperanza del resultado principal, no garantía.')}"
        f"{tile('Partidos cubiertos', modeled_total_label, modeled_note)}"
        f"{tile('Última actualización', updated_at, 'GitHub Actions publica tarjetas live cada 5 minutos; la llave profunda se recalcula por separado.')}"
        "</div>"
        "<div class=\"ticket-snapshot-actions\">"
        "<a class=\"primary-action\" href=\"#marcadores\">Ver marcadores para cargar</a>"
        "<a class=\"secondary-action\" href=\"#riesgos\">Ver partidos de riesgo</a>"
        "<a class=\"secondary-action\" href=\"#llave\">Ver llave proyectada</a>"
        "<a class=\"secondary-action\" href=\"#modelo\">Auditar modelo</a>"
        "</div>"
        "<div class=\"ticket-snapshot-list\">"
        "<h3>Atajo de carga: primeros picks defendibles</h3>"
        f"<ul>{''.join(row_html)}</ul>"
        "</div>"
        "<p class=\"ticket-snapshot-note\">Modelo de apoyo para quiniela; no garantiza resultados. "
        f"Estado de auditoría: {html.escape(str(audit['ticket_status']))}. "
        "Confirma hora local, alineaciones y reglas exactas de tu grupo antes de cerrar.</p>"
        "</section>"
    )


def team_public_popularity_index(team_name: str) -> float:
    if DISABLE_PUBLIC_POPULARITY_PROXY:
        return NEUTRAL_INDEX_VALUE
    teams = load_teams()
    team = teams.get(team_name)
    if not team:
        return 0.50
    profile = profile_for(team)
    elo_index = clamp((float(team.elo) - 1350.0) / 520.0, 0.0, 1.0)
    title_index = clamp(float(profile.world_cup_titles) / 5.0, 0.0, 1.0)
    return clamp(
        0.30 * profile.fifa_strength_index
        + 0.22 * profile.heritage_index
        + 0.16 * profile.resource_index
        + 0.12 * profile.history.world_cup_index
        + 0.10 * elo_index
        + 0.10 * title_index,
        0.0,
        1.0,
    )


def public_pick_proxy(prediction: MatchPrediction) -> Dict[str, float]:
    """Proxy de como podria escoger un participante promedio por nombre/fama.

    No pretende ser una encuesta; sirve para encontrar picks donde el modelo
    tiene ventaja relativa frente a una quiniela llenada por favoritos obvios.
    """

    if DISABLE_PUBLIC_POPULARITY_PROXY:
        return {"1": float(prediction.win_a), "X": float(prediction.draw), "2": float(prediction.win_b)}

    pop_a = team_public_popularity_index(prediction.team_a)
    pop_b = team_public_popularity_index(prediction.team_b)
    pop_total = max(pop_a + pop_b, 1e-9)
    pop_share_a = pop_a / pop_total
    pop_share_b = pop_b / pop_total
    draw_bias = 0.04 + (0.04 if prediction.draw >= 0.30 else 0.0)
    fame_bonus_a = 0.03 if pop_a > pop_b + 0.08 else 0.0
    fame_bonus_b = 0.03 if pop_b > pop_a + 0.08 else 0.0
    raw = {
        "1": 0.42 * float(prediction.win_a) + 0.50 * pop_share_a + 0.04 + fame_bonus_a,
        "X": 0.38 * float(prediction.draw) + draw_bias,
        "2": 0.42 * float(prediction.win_b) + 0.50 * pop_share_b + 0.04 + fame_bonus_b,
    }
    total = sum(raw.values()) or 1.0
    return {key: value / total for key, value in raw.items()}


def quiniela_strategy_profile(entry: dict) -> dict:
    prediction: MatchPrediction = entry["prediction"]
    base = quiniela_certainty_profile(entry)
    options = sorted(quiniela_outcome_options(prediction), key=lambda item: item[0], reverse=True)
    public_probs = public_pick_proxy(prediction)
    option_by_code = {code: (prob, label) for prob, label, code in options}
    public_code = max(public_probs, key=lambda code: public_probs[code])
    public_prob = float(public_probs[public_code])
    popular_model_prob, popular_label = option_by_code[public_code]
    best_code = str(base["pick_code"])
    best_public_prob = float(public_probs.get(best_code, 0.0))
    edge_vs_public = float(base["pick_prob"]) - best_public_prob
    expected_gain_vs_popular = float(base["pick_prob"]) - float(popular_model_prob)
    leverage_score = clamp(float(base["pick_prob"]) * (1.0 - best_public_prob) + max(0.0, edge_vs_public), 0.0, 1.0)

    second_prob = float(base["second_prob"])
    second_code = str(base["second_code"])
    second_public_prob = float(public_probs.get(second_code, 0.0))
    second_edge = second_prob - second_public_prob

    if float(base["pick_prob"]) >= 0.66 and float(base["gap"]) >= 0.18:
        strategy_tier = "Base fuerte"
        strategy_action = "No inventar: jugar el pick del modelo."
    elif (
        public_code != best_code and expected_gain_vs_popular >= 0.025 and float(base["pick_prob"]) >= 0.44
    ) or (edge_vs_public >= 0.055 and 0.44 <= float(base["pick_prob"]) < 0.66):
        strategy_tier = "Diferencial positivo"
        strategy_action = "Usarlo solo si hay fuente real de consenso; con proxy apagado, prioriza puntos esperados."
    elif second_edge >= 0.035 and second_prob >= 0.26 and float(base["gap"]) <= 0.12:
        strategy_tier = "Cubrir si puedes"
        strategy_action = (
            f"Pick base: {base['pick_label']}. Si tu quiniela permite marcar dos resultados, "
            f"agrega también {base['second_label']}. Si solo permite uno, usa el pick base pero no lo trates como fijo."
        )
    elif float(base["gap"]) < 0.08 or float(base["pick_prob"]) < 0.48:
        strategy_tier = "Riesgo alto"
        strategy_action = "No gastes aquí un diferencial heroico: cubre o acepta el riesgo con marcador sugerido."
    else:
        strategy_tier = "Base controlada"
        strategy_action = "Jugar el pick del modelo, sin sobreponderar marcador exacto."

    return {
        **base,
        "public_code": public_code,
        "public_label": popular_label,
        "public_prob": public_prob,
        "popular_model_prob": float(popular_model_prob),
        "best_public_prob": best_public_prob,
        "edge_vs_public": edge_vs_public,
        "expected_gain_vs_popular": expected_gain_vs_popular,
        "leverage_score": leverage_score,
        "second_edge": second_edge,
        "strategy_tier": strategy_tier,
        "strategy_action": strategy_action,
    }


def penca_score_from_profile(item: dict, key: str) -> dict:
    """Return a score option from a strategy profile with a safe fallback."""

    value = item.get(key)
    if isinstance(value, dict):
        return value
    return {
        "score": item.get("score", ""),
        "expected_points": float(item.get("penca_expected_points", 0.0)),
        "exact_prob": float(item.get("score_prob", 0.0)),
        "difference_prob": float(item.get("penca_difference_prob", 0.0)),
        "result_prob": float(item.get("penca_result_prob", item.get("pick_prob", 0.0))),
    }


def penca_optimal_score_from_profile(item: dict) -> dict:
    return penca_score_from_profile(item, "balanced_score")


def format_penca_score_with_teams(prediction: MatchPrediction, score: object) -> str:
    return prediction_score_label(prediction, score)


def penca_decision_profile(entry: dict) -> dict:
    """Choose the scenario and exact score to load for this refresh."""

    prediction: MatchPrediction = entry["prediction"]
    item = quiniela_strategy_profile(entry)
    status_class, status_text = dashboard_status(entry)
    optimal_score = penca_optimal_score_from_profile(item)
    live_score_available = entry.get("live_score_a") is not None and entry.get("live_score_b") is not None
    final_score_available = entry.get("actual_score_a") is not None and entry.get("actual_score_b") is not None

    if final_score_available:
        score = {
            "score": f"{int(entry.get('actual_score_a'))}-{int(entry.get('actual_score_b'))}",
            "expected_points": 0.0,
            "exact_prob": 1.0,
            "difference_prob": 1.0,
            "result_prob": 1.0,
        }
        scenario = "Finalizado"
        action = "No cargar como predicción: usar solo para recalibrar el modelo y la llave."
        reason = "Resultado cerrado; la siguiente corrida recalcula cruces, probabilidades y marcadores futuros."
        priority = 0
    elif live_score_available or status_class == "live":
        score = optimal_score
        scenario = "In-play real"
        action = "Si la Penca permite cambios en vivo, cargar este marcador actualizado; si no, usarlo solo para seguimiento."
        reason = f"El partido está en vivo ({status_text}); el marcador se recalcula con minuto, marcador, eventos y momentum disponibles."
        priority = 100
    elif item["strategy_tier"] == "Diferencial positivo" and float(item.get("expected_gain_vs_popular", 0.0)) > 0.0:
        score = penca_score_from_profile(item, "upside_score")
        scenario = "Diferencial"
        action = "Escoger este escenario solo si hay consenso real; si vas liderando, baja a modo óptimo."
        reason = (
            f"El modelo ve ventaja contra el pick popular: ganancia esperada "
            f"{float(item.get('expected_gain_vs_popular', 0.0)):+.1%}."
        )
        priority = 75
    elif item["strategy_tier"] in {"Cubrir si puedes", "Riesgo alto"} or float(item["gap"]) < 0.12 or float(item["pick_prob"]) < 0.52:
        score = penca_score_from_profile(item, "safe_score")
        scenario = "Seguro / cobertura"
        action = (
            f"Si solo puedes cargar un marcador, pon este. Si la app permite cobertura, considera también "
            f"{item['second_label']}."
        )
        reason = f"Partido abierto: brecha contra segunda opción {format_pct(float(item['gap']))}."
        priority = 65
    else:
        score = optimal_score
        scenario = "Óptimo"
        action = "Escoger este escenario como carga principal: maximiza puntos esperados bajo regla 8/5/3."
        reason = "El pick del modelo y el marcador Penca están alineados con mejor expectativa de puntos."
        priority = 55 if not entry.get("projection") else 35

    return {
        **item,
        "status_class": status_class,
        "status_text": status_text,
        "scenario": scenario,
        "scenario_action": action,
        "scenario_reason": reason,
        "scenario_priority": priority,
        "scenario_score": score,
        "score_to_enter": str(score.get("score", "")),
        "score_to_enter_with_teams": format_penca_score_with_teams(prediction, score.get("score", "")),
        "scenario_expected_points": float(score.get("expected_points", 0.0)),
        "scenario_exact_prob": float(score.get("exact_prob", 0.0)),
        "scenario_difference_prob": float(score.get("difference_prob", 0.0)),
        "scenario_result_prob": float(score.get("result_prob", 0.0)),
    }


def quiniela_strategy_metrics(strategy_profiles: Sequence[dict]) -> dict:
    if not strategy_profiles:
        return {
            "total": 0,
            "expected_model_hits": 0.0,
            "expected_popular_hits": 0.0,
            "expected_gain": 0.0,
            "expected_exact_scores": 0.0,
            "expected_top3_scores": 0.0,
            "expected_penca_points": 0.0,
            "expected_penca_points_per_match": 0.0,
            "expected_penca_exact_scores": 0.0,
            "expected_penca_difference_scores": 0.0,
            "avg_penca_certainty": 0.0,
            "exact_score_range_low": 0.0,
            "exact_score_range_high": 0.0,
            "variance_sd": 0.0,
            "range_low": 0.0,
            "range_high": 0.0,
            "differentials": 0,
            "coverage_min": 0,
            "coverage_recommended": 0,
            "coverage_aggressive": 0,
        }
    total = len(strategy_profiles)
    expected_model_hits = sum(float(item["pick_prob"]) for item in strategy_profiles)
    expected_popular_hits = sum(float(item["popular_model_prob"]) for item in strategy_profiles)
    expected_exact_scores = sum(float(item["score_prob"]) for item in strategy_profiles)
    expected_top3_scores = sum(float(item["top3"]) for item in strategy_profiles)
    expected_penca_points = sum(float(item["penca_expected_points"]) for item in strategy_profiles)
    expected_penca_exact_scores = sum(float(item["score_prob"]) for item in strategy_profiles)
    expected_penca_difference_scores = sum(float(item["penca_difference_prob"]) for item in strategy_profiles)
    avg_penca_certainty = sum(float(item.get("penca_certainty", 0.0)) for item in strategy_profiles) / float(total)
    exact_score_sd = math.sqrt(
        sum(float(item["score_prob"]) * (1.0 - float(item["score_prob"])) for item in strategy_profiles)
    )
    variance_sd = math.sqrt(sum(float(item["pick_prob"]) * (1.0 - float(item["pick_prob"])) for item in strategy_profiles))
    differentials = sum(1 for item in strategy_profiles if item["strategy_tier"] == "Diferencial positivo")
    coverage_min = sum(1 for item in strategy_profiles if item["strategy_tier"] in {"Cubrir si puedes", "Riesgo alto"})
    coverage_recommended = sum(
        1
        for item in strategy_profiles
        if item["strategy_tier"] in {"Cubrir si puedes", "Riesgo alto"}
        or float(item["pick_prob"]) < 0.62
        or float(item["gap"]) < 0.14
        or (float(item["second_prob"]) >= 0.25 and float(item["second_edge"]) >= 0.005)
    )
    coverage_aggressive = sum(
        1
        for item in strategy_profiles
        if item["strategy_tier"] in {"Cubrir si puedes", "Riesgo alto"}
        or float(item["pick_prob"]) < 0.70
        or float(item["gap"]) < 0.20
        or float(item["second_prob"]) >= 0.22
    )
    return {
        "total": total,
        "expected_model_hits": expected_model_hits,
        "expected_popular_hits": expected_popular_hits,
        "expected_gain": expected_model_hits - expected_popular_hits,
        "expected_exact_scores": expected_exact_scores,
        "expected_top3_scores": expected_top3_scores,
        "expected_penca_points": expected_penca_points,
        "expected_penca_points_per_match": expected_penca_points / float(total),
        "expected_penca_exact_scores": expected_penca_exact_scores,
        "expected_penca_difference_scores": expected_penca_difference_scores,
        "avg_penca_certainty": avg_penca_certainty,
        "exact_score_range_low": max(0.0, expected_exact_scores - 1.64 * exact_score_sd),
        "exact_score_range_high": min(float(total), expected_exact_scores + 1.64 * exact_score_sd),
        "variance_sd": variance_sd,
        "range_low": max(0.0, expected_model_hits - 1.64 * variance_sd),
        "range_high": min(float(total), expected_model_hits + 1.64 * variance_sd),
        "differentials": differentials,
        "coverage_min": coverage_min,
        "coverage_recommended": coverage_recommended,
        "coverage_aggressive": coverage_aggressive,
    }


def championship_penca_optimizer_metrics(entries: Sequence[dict]) -> dict:
    """Summarize the real target: maximize Penca points as the tournament evolves.

    Exact score betting pools are noisy. This profile keeps the product honest:
    it reports what the model can optimize, what it cannot guarantee, and how
    much of the recommendation is dynamic once matches start finishing.
    """

    if not entries:
        return {
            "total": 0,
            "fixture_count": 0,
            "projected_count": 0,
            "live_count": 0,
            "final_count": 0,
            "pending_count": 0,
            "expected_penca_points": 0.0,
            "expected_penca_points_per_match": 0.0,
            "expected_exact_scores": 0.0,
            "exact_score_range_low": 0.0,
            "exact_score_range_high": 0.0,
            "expected_top3_scores": 0.0,
            "avg_single_exact_ceiling": 0.0,
            "avg_penca_certainty": 0.0,
            "active_decision_total": 0,
            "scenario_expected_penca_points": 0.0,
            "scenario_expected_penca_points_per_match": 0.0,
            "scenario_expected_exact_scores": 0.0,
            "scenario_expected_difference_scores": 0.0,
            "scenario_exact_range_low": 0.0,
            "scenario_exact_range_high": 0.0,
            "coverage_recommended": 0,
            "coverage_min": 0,
            "dominant_scenario": "Sin datos",
            "decisions": [],
        }
    profiles = [quiniela_strategy_profile(entry) for entry in entries]
    decisions = [penca_decision_profile(entry) for entry in entries]
    metrics = quiniela_strategy_metrics(profiles)
    fixture_entries = [entry for entry in entries if not entry.get("projection")]
    live_count = sum(1 for entry in fixture_entries if fixture_is_live(entry))
    final_count = sum(1 for entry in fixture_entries if fixture_is_final(entry))
    projected_count = sum(1 for entry in entries if entry.get("projection"))
    pending_count = max(len(fixture_entries) - live_count - final_count, 0)
    mode_counts: Dict[str, int] = {}
    for decision in decisions:
        mode_counts[str(decision.get("scenario", "Óptimo"))] = mode_counts.get(str(decision.get("scenario", "Óptimo")), 0) + 1
    dominant_scenario = max(mode_counts.items(), key=lambda item: item[1])[0] if mode_counts else "Óptimo"
    active_decisions = [item for item in decisions if str(item.get("scenario")) != "Finalizado"]
    active_total = len(active_decisions)
    scenario_expected_penca_points = sum(float(item.get("scenario_expected_points", 0.0)) for item in active_decisions)
    scenario_expected_exact_scores = sum(float(item.get("scenario_exact_prob", 0.0)) for item in active_decisions)
    scenario_expected_difference_scores = sum(float(item.get("scenario_difference_prob", 0.0)) for item in active_decisions)
    scenario_exact_sd = math.sqrt(
        sum(
            float(item.get("scenario_exact_prob", 0.0))
            * (1.0 - float(item.get("scenario_exact_prob", 0.0)))
            for item in active_decisions
        )
    )
    top_decisions = sorted(
        decisions,
        key=lambda item: (
            int(item.get("status_class") == "live"),
            float(item.get("scenario_priority", 0.0)),
            float(item.get("scenario_expected_points", 0.0)),
            float(item.get("pick_prob", 0.0)),
        ),
        reverse=True,
    )[:10]
    avg_single_exact_ceiling = (
        sum(float(item.get("score_prob", 0.0)) for item in profiles) / float(len(profiles))
        if profiles
        else 0.0
    )
    return {
        **metrics,
        "fixture_count": len(fixture_entries),
        "projected_count": projected_count,
        "live_count": live_count,
        "final_count": final_count,
        "pending_count": pending_count,
        "dominant_scenario": dominant_scenario,
        "avg_single_exact_ceiling": avg_single_exact_ceiling,
        "active_decision_total": active_total,
        "scenario_expected_penca_points": scenario_expected_penca_points,
        "scenario_expected_penca_points_per_match": (
            scenario_expected_penca_points / float(active_total) if active_total else 0.0
        ),
        "scenario_expected_exact_scores": scenario_expected_exact_scores,
        "scenario_expected_difference_scores": scenario_expected_difference_scores,
        "scenario_exact_range_low": max(0.0, scenario_expected_exact_scores - 1.64 * scenario_exact_sd),
        "scenario_exact_range_high": min(float(active_total), scenario_expected_exact_scores + 1.64 * scenario_exact_sd),
        "decisions": top_decisions,
    }


def build_championship_penca_optimizer_html(entries: Sequence[dict]) -> str:
    """Render the championship-level Penca plan without promising impossible certainty."""

    if not entries:
        return ""
    metrics = championship_penca_optimizer_metrics(entries)
    total = int(metrics["total"])
    if total <= 0:
        return ""
    active_total = int(metrics.get("active_decision_total", total) or total)
    active_points_denominator = max(active_total * 8, 0)

    def decision_rows() -> str:
        rows = []
        for item in metrics["decisions"]:
            detail = (
                f"{item['scenario']} | {item['pick_label']} {format_pct(float(item['pick_prob']))} | "
                f"marcador que debo poner en Penca: {item['score_to_enter_with_teams']} | "
                f"{float(item['scenario_expected_points']):.2f}/8 pts esperados | "
                f"exacto {format_pct(float(item['scenario_exact_prob']))} | "
                f"diferencia {format_pct(float(item['scenario_difference_prob']))}"
            )
            rows.append(
                "<li>"
                f"<strong>{html.escape(str(item['title']))}</strong>"
                f"<span>{html.escape(detail)}</span>"
                f"<em>{html.escape(str(item['scenario_action']))}</em>"
                f"<small>{html.escape(str(item['scenario_reason']))}</small>"
                "</li>"
            )
        return "".join(rows)

    return (
        "<section class=\"panel championship-penca-panel\" id=\"campeonato\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Modo campeonato</p>"
        "<h2>La meta no es prometer 104/104: es maximizar puntos de Penca en cada corte.</h2>"
        "<p class=\"lede-tight\">No existe una metodología seria que garantice acertar todos los marcadores exactos antes de que se jueguen. Lo robusto es otra cosa: escoger el marcador con mayor valor esperado, cambiarlo cuando cambia la evidencia y no tratar como fijo un partido que el propio modelo marca como abierto.</p>"
        "</div></div>"
        "<div class=\"confidence-tiles championship-tiles\">"
        f"<div class=\"summary-tile\"><span>Objetivo honesto</span><strong>Maximizar puntos</strong><small>No se promete 104/104 marcadores exactos; se optimiza regla 8/5/3.</small></div>"
        f"<div class=\"summary-tile\"><span>Puntos esperados activos</span><strong>{float(metrics['scenario_expected_penca_points']):.1f}/{active_points_denominator}</strong><small>{float(metrics['scenario_expected_penca_points_per_match']):.2f} por partido según el marcador que realmente se recomienda cargar ahora.</small></div>"
        f"<div class=\"summary-tile\"><span>Exactos realistas activos</span><strong>{float(metrics['scenario_expected_exact_scores']):.1f}/{active_total}</strong><small>Rango 90%: {float(metrics['scenario_exact_range_low']):.0f}-{float(metrics['scenario_exact_range_high']):.0f}. Un exacto único no llega a 90-95% en fútbol.</small></div>"
        f"<div class=\"summary-tile\"><span>Diferencias esperadas activas</span><strong>{float(metrics['scenario_expected_difference_scores']):.1f}/{active_total}</strong><small>Incluye exactos; en Penca normalmente es donde se recuperan puntos cuando no entra el marcador exacto.</small></div>"
        f"<div class=\"summary-tile\"><span>Si hubiera 3 marcadores</span><strong>{float(metrics['expected_top3_scores']):.1f}/{total}</strong><small>Cobertura teórica con tres opciones por partido; Penca normalmente exige uno.</small></div>"
        f"<div class=\"summary-tile\"><span>Escenario dominante</span><strong>{html.escape(str(metrics['dominant_scenario']))}</strong><small>Puede pasar a in-play, seguro/cobertura o diferencial.</small></div>"
        f"<div class=\"summary-tile\"><span>Partidos a cubrir</span><strong>{int(metrics['coverage_recommended'])}</strong><small>Partidos donde conviene cautela si tu formato permite cobertura.</small></div>"
        f"<div class=\"summary-tile\"><span>Estado vivo</span><strong>{int(metrics['live_count'])} live / {int(metrics['final_count'])} final</strong><small>Los finales recalculan forma, tabla, llave y marcadores futuros.</small></div>"
        f"<div class=\"summary-tile\"><span>Llave dinámica</span><strong>{int(metrics['projected_count'])} cruces</strong><small>Cuando cambia un clasificado, cambia el rival y también el marcador recomendado.</small></div>"
        "</div>"
        "<div class=\"championship-explain-grid\">"
        "<article><h3>Cómo subir la probabilidad real de ganar</h3><p>Subir el número de “certeza” a 90-95 sin evidencia sería maquillaje. La mejora real viene de priorizar puntos esperados, usar el exacto solo donde sea defendible, cubrir partidos cerrados y actualizar tras cada final o evento live.</p></article>"
        "<article><h3>Cómo cambian los marcadores</h3><p>Antes del torneo cambian poco; durante el Mundial cambian por resultados reales, tabla de grupo, rival proyectado, bajas, noticias, tarjetas, fatiga, minuto, marcador en vivo y eventos disponibles del feed.</p></article>"
        "<article><h3>Qué cargar en la app</h3><p>Si solo tienes un marcador, usa la columna “Marcador para cargar en Penca”. Si la app permite editar antes del cierre, vuelve a revisar el corte más reciente antes de cada partido.</p></article>"
        "</div>"
        "<div class=\"scenario-table-card championship-action-card\">"
        "<h3>Marcadores prioritarios de este corte</h3>"
        "<ul class=\"scenario-decision-list\">"
        f"{decision_rows()}"
        "</ul>"
        "</div>"
        "<p class=\"meta\">Guardrail: si el exacto recomendado tiene baja probabilidad, el sistema todavía puede recomendarlo por puntos esperados, pero lo etiqueta como frágil. Eso es normal: en fútbol el marcador exacto es la parte más incierta de la quiniela.</p>"
        "</section>"
    )


def build_quiniela_strategy_markdown(entries: Sequence[dict]) -> List[str]:
    if not entries:
        return ["_Sin partidos cargados para optimizar estrategia de quiniela._"]
    profiles = [quiniela_strategy_profile(entry) for entry in entries]
    metrics = quiniela_strategy_metrics(profiles)
    differentials = sorted(
        [item for item in profiles if item["strategy_tier"] == "Diferencial positivo"],
        key=lambda item: (item["expected_gain_vs_popular"], item["leverage_score"], item["pick_prob"]),
        reverse=True,
    )[:10]
    coverage = sorted(
        [item for item in profiles if item["strategy_tier"] in {"Cubrir si puedes", "Riesgo alto"}],
        key=lambda item: (item["gap"], -item["second_edge"]),
    )[:10]
    lines = [
        "### Estrategia para ganar la quiniela",
        "- Objetivo: aumentar expectativa de puntos y controlar riesgo, no inflar porcentajes.",
        "- Reglas Penca Ovación usadas para optimizar marcador: 8 puntos por resultado exacto, 5 por diferencia de goles y 3 por ganador.",
        f"- Aciertos esperados del boleto modelo: {metrics['expected_model_hits']:.1f}/{int(metrics['total'])}.",
        f"- Puntos esperados por marcadores recomendados para la app: {metrics['expected_penca_points']:.1f}/{int(metrics['total']) * 8} ({metrics['expected_penca_points_per_match']:.2f} por partido).",
        "- Señales de popularidad pública: desactivadas mientras no haya fuente real de consenso de la Penca.",
        f"- Marcador exacto recomendado esperado: {metrics['expected_penca_exact_scores']:.1f}/{int(metrics['total'])}. Esto NO mide acierto de ganador; mide cuántas veces esperarías acertar el marcador optimizado para puntos.",
        f"- Diferencia de goles esperada con el marcador recomendado: {metrics['expected_penca_difference_scores']:.1f}/{int(metrics['total'])}.",
        f"- Rango realista 90% del marcador exacto principal: {metrics['exact_score_range_low']:.0f}-{metrics['exact_score_range_high']:.0f} aciertos.",
        f"- Si la quiniela permite poner 3 marcadores alternativos por partido, la cobertura esperada sube a {metrics['expected_top3_scores']:.1f}/{int(metrics['total'])}.",
        f"- Rango estadístico aproximado de resultados principales: {metrics['range_low']:.0f}-{metrics['range_high']:.0f} aciertos.",
        f"- Cobertura mínima/recomendada/agresiva: {int(metrics['coverage_min'])}/{int(metrics['coverage_recommended'])}/{int(metrics['coverage_aggressive'])} partidos.",
        "",
        "### Diferenciales positivos",
    ]
    if differentials:
        for item in differentials:
            lines.append(
                f"- {item['title']}: {item['pick_label']} {format_pct(item['pick_prob'])}; diferencial solo habilitado con fuente real de consenso; proxy de popularidad apagado."
            )
    else:
        lines.append("- No hay diferenciales positivos fuertes en este corte; conviene priorizar acierto base.")
    lines.extend(["", "### Partidos para cubrir o no sobrearriesgar"])
    if coverage:
        for item in coverage:
            lines.append(
                f"- {item['title']}: {item['pick_label']} {format_pct(item['pick_prob'])}; marcador Penca {item['score']} | {item['penca_expected_points']:.2f} pts esp. | exacto {format_pct(item['score_prob'])} | diferencia {format_pct(item['penca_difference_prob'])}; segunda opción {item['second_label']} {format_pct(item['second_prob'])}; {item['strategy_action']}"
            )
    else:
        lines.append("- No hay coberturas críticas en este corte.")
    return lines


def build_quiniela_strategy_html(entries: Sequence[dict]) -> str:
    if not entries:
        return ""
    profiles = [quiniela_strategy_profile(entry) for entry in entries]
    metrics = quiniela_strategy_metrics(profiles)
    base_strong = sorted(
        [item for item in profiles if item["strategy_tier"] == "Base fuerte"],
        key=lambda item: (item["pick_prob"], item["certainty_score"]),
        reverse=True,
    )[:8]
    differentials = sorted(
        [item for item in profiles if item["strategy_tier"] == "Diferencial positivo"],
        key=lambda item: (item["expected_gain_vs_popular"], item["leverage_score"], item["pick_prob"]),
        reverse=True,
    )[:8]
    coverage = sorted(
        [
            item
            for item in profiles
            if item["strategy_tier"] in {"Cubrir si puedes", "Riesgo alto"}
            or float(item["pick_prob"]) < 0.62
            or float(item["gap"]) < 0.14
            or (float(item["second_prob"]) >= 0.25 and float(item["second_edge"]) >= 0.005)
        ],
        key=lambda item: (item["gap"], -item["second_edge"]),
    )[:8]

    def strategy_rows(items: Sequence[dict], empty: str) -> str:
        if not items:
            return f"<li><strong>{html.escape(empty)}</strong><span>En este corte no hay suficientes casos para esta categoría.</span></li>"
        rows = []
        for item in items:
            detail = (
                f"{item['pick_label']} {format_pct(float(item['pick_prob']))} | "
                f"marcador Penca {item['score']} ({float(item['penca_expected_points']):.2f} pts esp.; "
                f"exacto {format_pct(float(item['score_prob']))}; diferencia {format_pct(float(item['penca_difference_prob']))}) | "
                f"riesgo {item['strategy_tier']} | "
                "sin proxy de popularidad"
            )
            rows.append(
                "<li>"
                f"<strong>{html.escape(str(item['title']))}</strong>"
                f"<span>{html.escape(detail)}</span>"
                f"<em>{html.escape(str(item['strategy_tier']))}: {html.escape(str(item['strategy_action']))}</em>"
                "</li>"
            )
        return "".join(rows)

    tiles = (
        "<div class=\"confidence-tiles strategy-tiles\">"
        f"<div class=\"summary-tile\"><span>Aciertos esperados 1X2</span><strong>{metrics['expected_model_hits']:.1f}/{int(metrics['total'])}</strong></div>"
        f"<div class=\"summary-tile\"><span>Puntos esperados Penca</span><strong>{metrics['expected_penca_points']:.1f}/{int(metrics['total']) * 8}</strong><small>{metrics['expected_penca_points_per_match']:.2f} puntos por partido con marcador optimizado.</small></div>"
        f"<div class=\"summary-tile\"><span>Firmeza media Penca</span><strong>{format_pct(float(metrics['avg_penca_certainty']))}</strong><small>Índice de decisión: combina ganador, diferencia, exacto, varianza del marcador y puntos esperados.</small></div>"
        f"<div class=\"summary-tile\"><span>Rango estadístico 90%</span><strong>{metrics['range_low']:.0f}-{metrics['range_high']:.0f}</strong></div>"
        "<div class=\"summary-tile\"><span>Ventaja vs boleto popular</span><strong>Solo con consenso real</strong><small>La popularidad pública está desactivada y no mueve picks sin fuente real de la Penca.</small></div>"
        f"<div class=\"summary-tile\"><span>Marcador exacto principal</span><strong>{metrics['expected_penca_exact_scores']:.1f}/{int(metrics['total'])}</strong><small>Marcador recomendado para cargar: maximiza puntos esperados de Penca, no solo probabilidad aislada. Rango 90%: {metrics['exact_score_range_low']:.0f}-{metrics['exact_score_range_high']:.0f}</small></div>"
        f"<div class=\"summary-tile\"><span>Diferencia de goles esperada</span><strong>{metrics['expected_penca_difference_scores']:.1f}/{int(metrics['total'])}</strong><small>Incluye exactos; en Penca esto vale 5 puntos si no clavas el marcador.</small></div>"
        f"<div class=\"summary-tile\"><span>Si puedes poner 3 marcadores</span><strong>{metrics['expected_top3_scores']:.1f}/{int(metrics['total'])}</strong><small>Cobertura esperada usando los tres marcadores más probables por partido.</small></div>"
        f"<div class=\"summary-tile\"><span>Diferenciales positivos</span><strong>{int(metrics['differentials'])}</strong></div>"
        f"<div class=\"summary-tile\"><span>Partidos a cubrir mínimo</span><strong>{int(metrics['coverage_min'])}</strong><small>Solo partidos cerrados o de riesgo alto.</small></div>"
        f"<div class=\"summary-tile\"><span>Cobertura recomendada</span><strong>{int(metrics['coverage_recommended'])}</strong><small>Si tu formato permite dos resultados, agrega la segunda opción indicada.</small></div>"
        f"<div class=\"summary-tile\"><span>Cobertura agresiva</span><strong>{int(metrics['coverage_aggressive'])}</strong><small>Si necesitas diferenciarte mucho.</small></div>"
        "</div>"
    )
    return (
        "<section class=\"panel strategy-panel\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Optimización del boleto</p>"
        "<h2>Estrategia para ganar la quiniela</h2>"
        "<p class=\"lede-tight\">Esta capa busca subir tus probabilidades de ganar la quiniela: maximiza puntos esperados, separa picks seguros de coberturas y evita sobreapostar marcadores frágiles.</p>"
        "<p class=\"meta\">Reglas públicas de Penca Ovación usadas aquí: 8 puntos por marcador exacto, 5 por diferencia de goles y 3 por ganador. Por eso el marcador recomendado puede diferir del marcador exacto más probable: se elige el que da más puntos esperados.</p>"
        "<p class=\"meta\">No se inflan probabilidades: se mejora la estrategia. Las señales de popularidad pública quedan apagadas hasta tener una fuente real; no se usa fama, intuición ni proxy para mover picks.</p>"
        "</div></div>"
        f"{tiles}"
        "<div class=\"certainty-grid strategy-grid\">"
        "<article><h3>Base fuerte: no inventar</h3><ul>"
        f"{strategy_rows(base_strong, 'Sin base fuerte suficiente')}"
        "</ul></article>"
        "<article><h3>Diferenciales que pueden subir tu upside</h3><ul>"
        f"{strategy_rows(differentials, 'Sin diferenciales positivos fuertes')}"
        "</ul></article>"
        "<article><h3>Coberturas y partidos peligrosos</h3><ul>"
        f"{strategy_rows(coverage, 'Sin coberturas críticas')}"
        "</ul></article>"
        "</div>"
        "</section>"
    )


def build_competitive_penca_html(entries: Sequence[dict]) -> str:
    """Render a quick decision board with safe, optimal and differential Penca modes."""

    if not entries:
        return ""
    profiles = [quiniela_strategy_profile(entry) for entry in entries]
    if not profiles:
        return ""

    def as_score_dict(item: dict, key: str) -> dict:
        value = item.get(key)
        if isinstance(value, dict):
            return value
        return {
            "score": item.get("score", ""),
            "expected_points": float(item.get("penca_expected_points", 0.0)),
            "exact_prob": float(item.get("score_prob", 0.0)),
            "difference_prob": float(item.get("penca_difference_prob", 0.0)),
            "result_prob": float(item.get("penca_result_prob", item.get("pick_prob", 0.0))),
        }

    def optimal_score(item: dict) -> dict:
        return {
            "score": item.get("score", ""),
            "expected_points": float(item.get("penca_expected_points", 0.0)),
            "exact_prob": float(item.get("score_prob", 0.0)),
            "difference_prob": float(item.get("penca_difference_prob", 0.0)),
            "result_prob": float(item.get("penca_result_prob", item.get("pick_prob", 0.0))),
        }

    def mode_row(item: dict, score: dict, label: str) -> str:
        score_label = score_label_with_teams(str(item["team_a"]), str(item["team_b"]), score.get("score", ""))
        detail = (
            f"{item['pick_label']} {format_pct(float(item['pick_prob']))} | "
            f"marcador {score_label} | "
            f"{float(score.get('expected_points', 0.0)):.2f} pts esp. | "
            f"exacto {format_pct(float(score.get('exact_prob', 0.0)))} | "
            f"diferencia {format_pct(float(score.get('difference_prob', 0.0)))}"
        )
        if label == "Diferencial":
            detail += (
                f" | edge vs popular {float(item.get('edge_vs_public', 0.0)):+.1%} | "
                f"ganancia esperada {float(item.get('expected_gain_vs_popular', 0.0)):+.1%} | "
                f"valor diferencial marcador {format_pct(float(score.get('differential_value_index', 0.0)))}"
            )
        return (
            "<li>"
            f"<strong>{html.escape(str(item['title']))}</strong>"
            f"<span>{html.escape(detail)}</span>"
            f"<em>{html.escape(label)}: {html.escape(str(item['strategy_action']))}</em>"
            "</li>"
        )

    safe_items = sorted(
        profiles,
        key=lambda item: (
            float(as_score_dict(item, "safe_score").get("result_prob", 0.0)),
            float(as_score_dict(item, "safe_score").get("difference_prob", 0.0)),
            float(item["pick_prob"]),
            float(item["gap"]),
        ),
        reverse=True,
    )[:8]
    optimal_items = sorted(
        profiles,
        key=lambda item: (
            float(item["penca_expected_points"]),
            float(item["pick_prob"]),
            float(item["score_prob"]),
        ),
        reverse=True,
    )[:8]
    differential_items = sorted(
        [
            item
            for item in profiles
            if float(item.get("expected_gain_vs_popular", 0.0)) > 0.0
            or item["strategy_tier"] == "Diferencial positivo"
        ],
        key=lambda item: (
            float(item.get("expected_gain_vs_popular", 0.0)),
            float(item.get("leverage_score", 0.0)),
            float(as_score_dict(item, "differential_score").get("competitive_adjusted_points", 0.0)),
            float(as_score_dict(item, "differential_score").get("differential_value_index", 0.0)),
        ),
        reverse=True,
    )[:8]

    def rows(items: Sequence[dict], mode: str) -> str:
        if not items:
            return "<li><strong>Sin candidatos claros</strong><span>El corte actual no muestra suficiente ventaja para este modo.</span></li>"
        if mode == "safe":
            return "".join(mode_row(item, as_score_dict(item, "safe_score"), "Seguro") for item in items)
        if mode == "differential":
            return "".join(mode_row(item, as_score_dict(item, "differential_score"), "Diferencial") for item in items)
        return "".join(mode_row(item, optimal_score(item), "Óptimo") for item in items)

    safe_points = sum(float(as_score_dict(item, "safe_score").get("expected_points", 0.0)) for item in safe_items)
    optimal_points = sum(float(optimal_score(item).get("expected_points", 0.0)) for item in optimal_items)
    differential_points = sum(float(as_score_dict(item, "differential_score").get("expected_points", 0.0)) for item in differential_items)
    return (
        "<section class=\"panel competitive-penca-panel\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Modo Penca competitivo</p>"
        "<h2>Tres formas de cargar el marcador según tu estrategia.</h2>"
        "<p class=\"lede-tight\">No todos juegan igual: si quieres proteger puntos usa modo seguro; si quieres maximizar puntos esperados usa modo óptimo; si necesitas ganarle a boletos populares usa modo diferencial.</p>"
        "</div></div>"
        "<div class=\"confidence-tiles competitive-penca-tiles\">"
        f"<div class=\"summary-tile\"><span>Modo seguro</span><strong>{safe_points:.1f} pts esp.</strong><small>Prioriza ganador/diferencia y baja varianza.</small></div>"
        f"<div class=\"summary-tile\"><span>Modo óptimo</span><strong>{optimal_points:.1f} pts esp.</strong><small>Maximiza puntos esperados bajo regla 8/5/3.</small></div>"
        f"<div class=\"summary-tile\"><span>Modo diferencial</span><strong>{differential_points:.1f} pts esp.</strong><small>Busca ventaja contra el pick popular cuando hay edge.</small></div>"
        "</div>"
        "<div class=\"certainty-grid competitive-penca-grid\">"
        "<article><h3>Jugar seguro</h3><ul>"
        f"{rows(safe_items, 'safe')}"
        "</ul></article>"
        "<article><h3>Jugar óptimo</h3><ul>"
        f"{rows(optimal_items, 'optimal')}"
        "</ul></article>"
        "<article><h3>Jugar diferencial</h3><ul>"
        f"{rows(differential_items, 'differential')}"
        "</ul></article>"
        "</div>"
        "<p class=\"meta\">Lectura rápida: si solo quieres llenar una vez, usa modo óptimo. Si vas líder o quieres evitar daño, usa seguro en partidos cerrados. Si necesitas remontar o diferenciarte, mira diferencial.</p>"
        "</section>"
    )


def build_current_penca_decision_html(entries: Sequence[dict]) -> str:
    """Render the current scenario and exact score to enter in Penca."""

    if not entries:
        return ""
    decisions = [penca_decision_profile(entry) for entry in entries]
    live_decisions = [item for item in decisions if item["status_class"] == "live"]
    pending_decisions = [item for item in decisions if item["status_class"] in {"pending", "projection"}]
    final_count = sum(1 for item in decisions if item["status_class"] == "final")
    live_count = len(live_decisions)
    projected_count = sum(1 for item in decisions if item.get("projection"))
    next_decisions = sorted(
        pending_decisions,
        key=lambda item: (
            float(item["scenario_priority"]),
            float(item["scenario_expected_points"]),
            float(item["pick_prob"]),
        ),
        reverse=True,
    )
    visible = (sorted(live_decisions, key=lambda item: float(item["scenario_priority"]), reverse=True) + next_decisions)[:14]
    if not visible:
        visible = sorted(decisions, key=lambda item: float(item["scenario_priority"]), reverse=True)[:14]

    def row(item: dict) -> str:
        projection_badge = " | cruce proyectado" if item.get("projection") else ""
        detail = (
            f"{item['scenario']} | {item['pick_label']} {format_pct(float(item['pick_prob']))} | "
            f"marcador {item['score_to_enter_with_teams']} | {float(item['scenario_expected_points']):.2f} pts esp. | "
            f"exacto {format_pct(float(item['scenario_exact_prob']))} | diferencia {format_pct(float(item['scenario_difference_prob']))}"
        )
        return (
            "<li>"
            f"<strong>{html.escape(str(item['title']))}</strong>"
            f"<span>{html.escape(detail)}{html.escape(projection_badge)}</span>"
            f"<em>{html.escape(str(item['scenario_action']))}</em>"
            f"<small>{html.escape(str(item['scenario_reason']))}</small>"
            "</li>"
        )

    mode_counts: Dict[str, int] = {}
    for item in decisions:
        mode_counts[str(item["scenario"])] = mode_counts.get(str(item["scenario"]), 0) + 1
    dominant_mode = max(mode_counts.items(), key=lambda item: item[1])[0] if mode_counts else "Óptimo"
    return (
        "<section class=\"panel current-penca-panel\" id=\"escenarios\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Decisión dinámica</p>"
        "<h2>Escenario recomendado ahora y marcador que debes poner en Penca</h2>"
        "<p class=\"lede-tight\">Esta es la capa operativa: en cada refresh decide si conviene modo óptimo, seguro/cobertura, diferencial o in-play. El marcador mostrado es el que debes cargar si solo puedes poner un marcador.</p>"
        "</div></div>"
        "<div class=\"confidence-tiles current-penca-tiles\">"
        f"<div class=\"summary-tile\"><span>Modo dominante ahora</span><strong>{html.escape(dominant_mode)}</strong><small>No es fijo: cambia con resultados, live, noticias, lesiones y llave.</small></div>"
        f"<div class=\"summary-tile\"><span>Partidos en vivo</span><strong>{live_count}</strong><small>Si entra live, el escenario pasa a in-play real.</small></div>"
        f"<div class=\"summary-tile\"><span>Partidos ya cerrados</span><strong>{final_count}</strong><small>Se usan para recalibrar y mover cruces futuros.</small></div>"
        f"<div class=\"summary-tile\"><span>Cruces proyectados</span><strong>{projected_count}</strong><small>Cambian automáticamente cuando un equipo gana, empata o queda eliminado.</small></div>"
        "</div>"
        "<div class=\"scenario-table-card\">"
        "<h3>Qué escoger en este corte</h3>"
        "<ul class=\"scenario-decision-list\">"
        f"{''.join(row(item) for item in visible)}"
        "</ul>"
        "</div>"
        "<p class=\"meta\">Se recalcula cada 5 minutos el carril live de GitHub Actions durante el torneo. Cuando cambie un resultado real, se actualizan probabilidades, escenario recomendado y marcador para Penca; la llave completa se propaga en la siguiente corrida profunda horaria o manual.</p>"
        "</section>"
    )


def build_full_scorecard_markdown(entries: Sequence[dict]) -> List[str]:
    if not entries:
        return ["### Marcadores para cargar en Penca", "_Sin partidos cargados._"]
    lines = [
        "### Marcadores para cargar en Penca",
        "- Orden del marcador: equipo A - equipo B, exactamente como aparece en el partido.",
        f"- Total modelado: {len(entries)} partidos/cruces.",
    ]
    for entry in entries:
        prediction: MatchPrediction = entry["prediction"]
        top_penca = penca_ovacion_top_score(prediction)
        guidance = prediction.score_guidance or {}
        pick_label, pick_prob = pick_summary(prediction)
        projection_note = " | cruce proyectado" if entry.get("projection") else ""
        lines.append(
            f"- {entry['stage_label']} | {entry['title']}: {top_penca['score']} "
            f"({prediction.team_a} - {prediction.team_b}) | pick {pick_label} {format_pct(pick_prob)} | "
            f"exacto {format_pct(float(top_penca.get('exact_prob', 0.0)))} | "
            f"puntos esp. {float(top_penca.get('expected_points', 0.0)):.2f}/8 | "
            f"exacto más probable {guidance.get('top_exact_score', prediction.exact_scores[0][0] if prediction.exact_scores else top_penca['score'])}"
            f"{projection_note}"
        )
    return lines


def build_full_scorecard_html(entries: Sequence[dict]) -> str:
    if not entries:
        return ""
    fixture_entries = [entry for entry in entries if not entry.get("projection")]
    projected_entries = [entry for entry in entries if entry.get("projection")]
    rows = []
    for index, entry in enumerate(entries, start=1):
        prediction: MatchPrediction = entry["prediction"]
        top_penca = penca_ovacion_top_score(prediction)
        decision = penca_decision_profile(entry)
        guidance = prediction.score_guidance or {}
        pick_label, pick_prob = pick_summary(prediction)
        status_class, status_text = dashboard_status(entry)
        precision_label = str(guidance.get("precision_label", "sin clasificar"))
        top_exact = str(guidance.get("top_exact_score", prediction.exact_scores[0][0] if prediction.exact_scores else top_penca["score"]))
        top_exact_label = prediction_score_label(prediction, top_exact)
        row_classes = "scorecard-row"
        if entry.get("projection"):
            row_classes += " projected"
        rows.append(
            f"<tr class=\"{row_classes}\">"
            f"<td>{index:03d}</td>"
            f"<td><strong>{html.escape(str(entry['title']))}</strong><span>{html.escape(str(entry['stage_label']))} | {html.escape(status_text)}</span></td>"
            f"<td><strong>{html.escape(prediction.team_a)} {html.escape(str(top_penca['score']).split('-')[0])} - {html.escape(str(top_penca['score']).split('-')[-1])} {html.escape(prediction.team_b)}</strong><span>Orden: {html.escape(prediction.team_a)} - {html.escape(prediction.team_b)}</span></td>"
            f"<td><strong>{html.escape(str(decision['scenario']))}</strong><span>{html.escape(str(decision['score_to_enter_with_teams']))}</span><em>{html.escape(str(decision['scenario_action']))}</em></td>"
            f"<td>{html.escape(pick_label)} <span>{format_pct(pick_prob)}</span></td>"
            f"<td>{html.escape(top_exact_label)} <span>marcador más probable del modelo</span></td>"
            f"<td>{format_pct(float(top_penca.get('exact_prob', 0.0)))} <span>exacto recomendado</span></td>"
            f"<td>{float(top_penca.get('expected_points', 0.0)):.2f}/8 <span>{html.escape(precision_label)}</span></td>"
            "</tr>"
        )
    return (
        "<section class=\"panel scorecard-panel\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Boleto completo</p>"
        "<h2>Marcadores para cargar en Penca</h2>"
        "<p class=\"lede-tight\">Esta es la lista operativa dinámica: un marcador para cada partido modelado, recalculado en cada refresh con el modelo, resultados reales, noticias, estado live y cruces proyectados. El marcador siempre está en el orden Equipo A - Equipo B.</p>"
        "</div></div>"
        "<div class=\"confidence-tiles scorecard-tiles\">"
        f"<div class=\"summary-tile\"><span>Total con marcador</span><strong>{len(entries)}/104</strong><small>{len(fixture_entries)} partidos de fase de grupos auditados + {len(projected_entries)} cruces eliminatorios proyectados.</small></div>"
        "<div class=\"summary-tile\"><span>Regla usada</span><strong>8 / 5 / 3</strong><small>Exacto, diferencia de goles, ganador.</small></div>"
        "<div class=\"summary-tile\"><span>Actualización</span><strong>Dinámica</strong><small>Cambia durante el torneo si cambian partidos, llave, lesiones o live.</small></div>"
        "<div class=\"summary-tile\"><span>Cómo leerlo</span><strong>Equipo A - Equipo B</strong><small>No inviertas el orden al cargarlo en la app.</small></div>"
        "</div>"
        "<div class=\"scorecard-table-wrap\"><table class=\"scorecard-table\">"
        "<thead><tr><th>#</th><th>Partido</th><th>Marcador para cargar en Penca</th><th>Escenario a escoger</th><th>Pick</th><th>Más probable del modelo</th><th>Prob. exacto</th><th>Puntos esperados</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
        "</section>"
    )


def build_max_certainty_markdown(entries: Sequence[dict]) -> List[str]:
    if not entries:
        return ["_Sin partidos cargados para construir una hoja de picks._"]
    profiles = [quiniela_certainty_profile(entry) for entry in entries if not entry.get("projection")]
    projected_count = sum(1 for entry in entries if entry.get("projection"))
    if not profiles:
        return ["_Sin partidos reales cargados para construir una hoja de picks._"]
    audit = quiniela_audit_metrics(profiles)
    safest = sorted(profiles, key=lambda item: (item["certainty_score"], item["pick_prob"], item["gap"]), reverse=True)[:12]
    traps = sorted(
        [item for item in profiles if item["tier"] in {"Partido cerrado", "Riesgo alto"}],
        key=lambda item: (item["gap"], item["pick_prob"]),
    )[:8]
    score_picks = sorted(profiles, key=lambda item: (item["score_prob"], item["top3"]), reverse=True)[:8]
    lines = [
        "- Lectura: la firmeza operativa no es probabilidad garantizada de acierto; es un ranking conservador que mezcla probabilidad del resultado, diferencia contra la segunda opción, cobertura de marcadores y acuerdo entre modelos.",
        "- Regla base sin conocer tu quiniela exacta: en picks base juega resultado; en partidos cerrados cubre empate/upset si el formato lo permite; para marcador exacto usa el marcador principal solo si la quiniela lo premia mucho.",
        "",
        "### Auditoría del boleto",
        f"- Estado: {audit['ticket_status']}",
        f"- Partidos auditados: {audit['total']} de fase de grupos + {projected_count} cruces eliminatorios proyectados = {audit['total'] + projected_count} partidos con marcador.",
        f"- Picks base o principales: {audit['firm_or_preferent']}",
        f"- Partidos cerrados o de riesgo alto: {audit['traps'] + audit['high_variance']}",
        f"- Marcadores exactos defendibles: {audit['defensible_scores']} | frágiles: {audit['fragile_scores']}",
        f"- Brecha mínima contra la segunda opción: {format_pct(float(audit['min_gap']))}",
        f"- Firmeza de picks base: {format_pct(float(audit['base_firmness_index']))} como índice operativo; no es probabilidad garantizada.",
        f"- Firmeza con estrategia aplicada: {format_pct(float(audit['strategy_adjusted_firmness']))}; mide pick base o cobertura según lo que convenga.",
        f"- Firmeza si fuerzas pick único: {format_pct(float(audit['avg_certainty']))}; incluye partidos cerrados como si fueran fijos.",
        "- Checklist de auditoría: revisar bajas confirmadas, once inicial, mercado de última hora, clima y estado live antes de cerrar el boleto.",
        "- Alertas: " + " ".join(str(item) for item in audit["warnings"]),
        "",
        "### Picks más defendibles",
    ]
    for item in safest:
        lines.append(
            f"- {item['title']}: {item['pick_label']} ({format_pct(item['pick_prob'])}) | índice de firmeza {format_pct(item['certainty_score'])} | marcador {item['score']} ({format_pct(item['score_prob'])}) | {item['tier']}: {item['action']}"
        )
    lines.extend(["", "### Partidos que no conviene jugar con exceso de confianza"])
    if traps:
        for item in traps:
            lines.append(
                f"- {item['title']}: pick principal {item['pick_label']} {format_pct(item['pick_prob'])}, marcador sugerido {item['score']} {format_pct(item['score_prob'])}, segunda opción {item['second_label']} {format_pct(item['second_prob'])} | brecha {format_pct(item['gap'])} | {item['action']}"
            )
    else:
        lines.append("- No hay partidos cerrados críticos en este corte.")
    lines.extend(["", "### Marcadores exactos más defendibles"])
    for item in score_picks:
        lines.append(
            f"- {item['title']}: {item['score']} ({format_pct(item['score_prob'])}) | cobertura con tres marcadores {format_pct(item['top3'])} | {item['score_note']}"
        )
    return lines


def build_max_certainty_html(entries: Sequence[dict]) -> str:
    if not entries:
        return ""
    profiles = [quiniela_certainty_profile(entry) for entry in entries if not entry.get("projection")]
    if not profiles:
        return ""
    projected_count = sum(1 for entry in entries if entry.get("projection"))
    audit = quiniela_audit_metrics(profiles)
    safest = sorted(profiles, key=lambda item: (item["certainty_score"], item["pick_prob"], item["gap"]), reverse=True)[:10]
    traps = sorted(
        [item for item in profiles if item["tier"] in {"Partido cerrado", "Riesgo alto"}],
        key=lambda item: (item["gap"], item["pick_prob"]),
    )[:6]
    score_picks = sorted(profiles, key=lambda item: (item["score_prob"], item["top3"]), reverse=True)[:6]

    def rows(items: Sequence[dict], mode: str) -> str:
        html_rows = []
        for item in items:
            if mode == "safe":
                detail = (
                    f"{item['pick_label']} {format_pct(item['pick_prob'])} | "
                    f"índice de firmeza {format_pct(item['certainty_score'])} | "
                    f"marcador Penca {item['score']} {format_pct(item['score_prob'])}"
                )
            elif mode == "trap":
                detail = (
                    f"Pick principal {item['pick_label']} {format_pct(item['pick_prob'])}; "
                    f"marcador sugerido {item['score']} {format_pct(item['score_prob'])}; "
                    f"segunda opción {item['second_label']} {format_pct(item['second_prob'])}; "
                    f"brecha {format_pct(item['gap'])}"
                )
            else:
                detail = (
                    f"Marcador {item['score']} {format_pct(item['score_prob'])} | "
                    f"cobertura con tres marcadores {format_pct(item['top3'])} | {item['score_note']}"
                )
            html_rows.append(
                "<li>"
                f"<strong>{html.escape(str(item['title']))}</strong>"
                f"<span>{html.escape(detail)}</span>"
                f"<em>{html.escape(str(item['tier']))}: {html.escape(str(item['action']))}</em>"
                "</li>"
            )
        return "".join(html_rows)

    audit_tiles = (
        "<div class=\"confidence-tiles quiniela-audit-tiles\">"
        f"<div class=\"summary-tile\"><span>Estado del boleto</span><strong>{html.escape(str(audit['ticket_status']))}</strong></div>"
        f"<div class=\"summary-tile\"><span>Fase de grupos auditada</span><strong>{int(audit['total'])}</strong><small>{int(audit['total'])} partidos de fase de grupos auditados + {projected_count} cruces eliminatorios proyectados = {int(audit['total']) + projected_count} con marcador.</small></div>"
        f"<div class=\"summary-tile\"><span>Picks base o principales</span><strong>{int(audit['firm_or_preferent'])}</strong></div>"
        f"<div class=\"summary-tile\"><span>Partidos cerrados o de riesgo alto</span><strong>{int(audit['traps']) + int(audit['high_variance'])}</strong></div>"
        f"<div class=\"summary-tile\"><span>Marcadores exactos defendibles</span><strong>{int(audit['defensible_scores'])}</strong></div>"
        f"<div class=\"summary-tile\"><span>Brecha mínima contra la segunda opción</span><strong>{format_pct(float(audit['min_gap']))}</strong></div>"
        f"<div class=\"summary-tile\"><span>Firmeza de picks base</span><strong>{format_pct(float(audit['base_firmness_index']))}</strong><small>Índice operativo de los {int(audit['firm_or_preferent'])} picks principales; objetivo 90+.</small></div>"
        f"<div class=\"summary-tile\"><span>Firmeza con estrategia aplicada</span><strong>{format_pct(float(audit['strategy_adjusted_firmness']))}</strong><small>Pick base donde conviene; cobertura/cautela en partidos cerrados.</small></div>"
        f"<div class=\"summary-tile\"><span>Firmeza si fuerzas pick único</span><strong>{format_pct(float(audit['avg_certainty']))}</strong><small>Esta baja porque trata los partidos cerrados como fijos.</small></div>"
        "</div>"
    )
    warning_rows = "".join(
        "<li>"
        f"<strong>{html.escape(str(warning))}</strong>"
        "<span>Acción: revisar antes de cerrar la quiniela y no sobreapostar marcadores exactos frágiles.</span>"
        "</li>"
        for warning in audit["warnings"]
    )
    audit_panel = (
        "<article class=\"ticket-audit-card\">"
        "<h3>Auditoría del boleto</h3>"
        "<p class=\"meta\">Esta capa revisa si el boleto está defendible como estrategia de quiniela: no promete certeza artificial. La firmeza sube de forma robusta cuando el boleto deja de forzar fijos en partidos cerrados y aplica cobertura/cautela donde el modelo detecta fragilidad.</p>"
        f"{audit_tiles}"
        "<h4>Checklist de auditoría</h4>"
        "<ul>"
        "<li><strong>Antes de cerrar</strong><span>Confirmar bajas, once inicial, portero, cuotas de última hora, clima y noticias.</span></li>"
        "<li><strong>Durante partido en vivo</strong><span>Si la quiniela permite cambios, priorizar minuto, marcador, tiros, xG live, rojas y momentum.</span></li>"
        f"{warning_rows}"
        "</ul>"
        "</article>"
    )
    trap_rows = rows(traps, "trap") if traps else "<li><strong>Sin partidos cerrados críticos</strong><span>El corte actual no marca partidos con brecha estrecha crítica.</span><em>Igual revisar alineaciones antes de cerrar.</em></li>"
    return (
        "<section class=\"panel certainty-panel\">"
        "<div class=\"panel-head\">"
        "<div>"
        "<p class=\"eyebrow\">Modo quiniela</p>"
        "<h2>Hoja de máxima firmeza</h2>"
        "<p class=\"lede-tight\">Esta sección traduce el modelo a decisiones de quiniela. No infla probabilidades: ordena los picks por firmeza operativa, separa partidos cerrados y avisa cuando el marcador exacto es frágil.</p>"
        "</div>"
        "</div>"
        f"{audit_panel}"
        "<div class=\"certainty-grid\">"
        "<article><h3>Picks más defendibles</h3><ul>"
        f"{rows(safest, 'safe')}"
        "</ul></article>"
        "<article><h3>Partidos para cubrir o tratar con cuidado</h3><ul>"
        f"{trap_rows}"
        "</ul></article>"
        "<article><h3>Marcadores exactos más defendibles</h3><ul>"
        f"{rows(score_picks, 'score')}"
        "</ul></article>"
        "</div>"
        "</section>"
    )


def build_consensus_guardrail_markdown(bracket_payload: dict, entries: Optional[Sequence[dict]] = None) -> List[str]:
    context = consensus_live_update_context(entries)
    rows = consensus_adjusted_champion_probabilities(bracket_payload, entries)
    alerts = consensus_bracket_alerts(bracket_payload)
    if not rows and not alerts:
        return ["_Sin llave generada para comparar contra consenso externo._"]
    lines = [
        "- Lectura: esta capa no reemplaza el modelo. Lo calibra contra consenso externo definido para evitar dos errores típicos de quiniela: sobreconcentrarse en un favorito y dejar vivo muy poco a contendientes fuertes.",
        f"- Mezcla dinámica usada para campeón recomendado: {format_pct(float(context['model_blend']))} modelo propio/live + {format_pct(float(context['consensus_blend']))} consenso externo.",
        f"- Actualización live de esa mezcla: {int(context['final_count'])} partidos finales, {int(context['live_count'])} en vivo y {int(context['pending_count'])} pendientes. A medida que entran resultados reales, el consenso externo pesa menos y la simulación Monte Carlo publicada pesa más.",
        "- Transparencia: el consenso externo no es una caja negra; combina priors declarados de campeón, ratings tipo Elo/FIFA, fuerza ofensiva-defensiva tipo SPI, mercado cuando existe y simulación Monte Carlo para dependencias de llave.",
    ]
    if rows:
        leader = rows[0]
        lines.append(
            f"- Campeón recomendado de boleto: {leader['team']} | probabilidad calibrada {format_pct(float(leader['adjusted_prob']))} | modelo puro {format_pct(float(leader['model_prob']))} | consenso {format_pct(float(leader['consensus_prob']))}."
        )
        lines.append("- Top calibrado de campeón:")
        for row in rows[:8]:
            direction = "sobreponderado" if float(row["delta"]) > 0.04 else "subponderado" if float(row["delta"]) < -0.025 else "alineado"
            lines.append(
                f"  - {row['team']}: calibrado {format_pct(float(row['adjusted_prob']))} | modelo {format_pct(float(row['model_prob']))} | consenso {format_pct(float(row['consensus_prob']))} | {direction}"
            )
    if alerts:
        lines.extend(["", "### Ajustes estratégicos de llave"])
        for alert in alerts:
            status = "Aplicar en boleto" if alert["applies"] else "Mantener modelo"
            lines.append(
                f"- {alert['title']}: {alert['team_a']} vs {alert['team_b']} | modelo {alert['model_winner']} {format_pct(float(alert['model_prob']))} | boleto {alert['recommended_winner']} {format_pct(float(alert['recommended_prob']))} | margen {format_pct(float(alert['model_edge']))} | {status}."
            )
    return lines


def external_estimator_methodology_items() -> List[dict]:
    return [
        {
            "name": "Ratings tipo Elo / ClubElo",
            "signal": "Diferencia de fuerza entre equipos, localia/neutralidad, margen e importancia del partido.",
            "usage": "Se usa como señal de fuerza relativa y como control para no sobrerreaccionar a un solo resultado.",
        },
        {
            "name": "Ranking FIFA oficial",
            "signal": "Puntos acumulados con peso de resultado, expectativa previa e importancia del partido.",
            "usage": "Entra como variable estructural: no predice solo, pero ayuda a calibrar jerarquia inicial.",
        },
        {
            "name": "SPI / modelos ofensivo-defensivos",
            "signal": "Ataque y defensa convertidos a goles esperados y probabilidades de marcador.",
            "usage": "El modelo replica esa lógica con goles esperados, distribución de marcadores, Dixon-Coles, overdispersión calibrada y una capa ML ligera regularizada.",
        },
        {
            "name": "Mercado y consenso profesional",
            "signal": "Probabilidades implícitas, líneas de goles y consenso pretorneo de campeón.",
            "usage": "Funciona como guardrail: corrige extremos, pero pierde peso cuando aparecen datos reales del Mundial.",
        },
        {
            "name": "Transparencia de fuentes",
            "signal": "Priors declarados, feeds live, noticias abiertas, mercado si existe y resultados finales.",
            "usage": "Cada corrida muestra que peso tuvo el modelo y que peso tuvo el consenso; si no hay feed profundo, no se finge que existe.",
        },
        {
            "name": "Monte Carlo de torneo",
            "signal": "Miles de rutas completas para grupos, cruces, prorroga, penales y dependencias de llave.",
            "usage": "El snapshot principal profundo usa 100.000 simulaciones para estabilizar llave, campeón y marcadores; 15.000 queda como mínimo técnico del carril horario.",
        },
        {
            "name": "Bradley-Terry jerárquico dinámico",
            "signal": "Probabilidad relativa de que un equipo supere a otro, con regularización por confederación, ranking, Elo y fuerza de plantilla.",
            "usage": "Modelo estadístico adicional recomendado como contraste: mejora lectura de favoritos/tapados sin depender de marcadores Poisson.",
        },
        {
            "name": "Glicko / TrueSkill de incertidumbre",
            "signal": "No solo mide fuerza: mide cuánta incertidumbre hay sobre esa fuerza cuando faltan partidos comparables.",
            "usage": "Útil para no sobreconfiar en selecciones con poca muestra reciente y para ajustar la agresividad del boleto.",
        },
        {
            "name": "Skellam / margen calibrado",
            "signal": "Distribución de diferencia de goles y no solo marcador exacto crudo.",
            "usage": "Ayuda a optimizar Penca porque 5 puntos por diferencia pueden valer más que perseguir un exacto frágil.",
        },
    ]


def statistical_upgrade_recommendations() -> List[dict]:
    return [
        {
            "name": "Variables explícitas de plantilla, macro, estilo, carga, geografía y penales",
            "status": "Implementado",
            "why": "PIB, población, valor de plantilla, edad/media de liga, minutos top, carga física, xT, progresión, PPDA, compatibilidad táctica, geografía 2026 y penales granulares ya entran como señales separadas.",
            "impact": "Permite auditar qué mueve cada pick y evita que todo quede escondido dentro de un resource_index genérico.",
        },
        {
            "name": "Agregar Bradley-Terry jerárquico dinámico",
            "status": "Recomendado",
            "why": "Es el mejor siguiente modelo estadístico porque estima fuerza relativa partido a partido y se integra bien con Elo, FIFA, plantilla, mercado y ruta Monte Carlo.",
            "impact": "Debería mejorar la separación entre favorito real, tapado vigilado y falso positivo de una rama fácil.",
        },
        {
            "name": "Agregar Glicko/TrueSkill para incertidumbre",
            "status": "Recomendado",
            "why": "Dos equipos pueden tener fuerza parecida, pero distinta incertidumbre. Esa incertidumbre debe decidir si se juega fijo, cobertura o diferencial.",
            "impact": "Reduce sobreconfianza y mejora la estrategia de cobertura en Penca.",
        },
        {
            "name": "Refinar margen con Skellam/ordinal calibrado",
            "status": "Recomendado para marcadores",
            "why": "El marcador exacto no debe salir de Poisson puro. El margen optimizado para regla 8/5/3 necesita otra capa.",
            "impact": "Mejora puntos esperados cuando no entra el exacto pero sí entra la diferencia de goles.",
        },
        {
            "name": "ML regularizado solo con dataset limpio",
            "status": "Agregar con cautela",
            "why": "Un gradient boosting puede aportar, pero solo si se entrena con partidos históricos limpios y validación temporal. Sin eso memoriza ruido.",
            "impact": "Buen miembro de ensamble cuando haya matriz histórica oficial, features estables y backtesting walk-forward.",
        },
        {
            "name": "Variables macro como prior débil",
            "status": "Usar, no duplicar",
            "why": "PIB, población, valor de liga y recursos explican infraestructura, pero muchas veces ya están absorbidos por Elo, FIFA, plantilla y mercado.",
            "impact": "Sirven para desempatar priors pretorneo; no deben mover en vivo un partido por sí solas.",
        },
    ]


def external_scenario_stress_tests(bracket_payload: dict, entries: Optional[Sequence[dict]] = None) -> List[dict]:
    adjusted_rows = consensus_adjusted_champion_probabilities(bracket_payload, entries)
    if not adjusted_rows:
        return []
    leader = adjusted_rows[0]
    consensus_leader = max(adjusted_rows, key=lambda row: float(row.get("consensus_prob", 0.0) or 0.0))
    model_leader = max(adjusted_rows, key=lambda row: float(row.get("model_prob", 0.0) or 0.0))
    dark_candidates = dark_horse_candidates(bracket_payload, entries)
    top_dark = dark_candidates[0] if dark_candidates else None
    benchmark_comparison = external_forecast_comparison(bracket_payload, entries)
    divergent = [
        item for item in benchmark_comparison["benchmarks"]
        if str(item["champion"]) != str(leader["team"])
    ]
    top_divergent = max(divergent, key=lambda item: float(item.get("ours_prob", 0.0) or 0.0), default=None)

    scenarios = [
        {
            "name": "Escenario modelo propio",
            "team": str(model_leader["team"]),
            "value": format_pct(float(model_leader.get("model_prob", 0.0) or 0.0)),
            "action": "Si coincide con el calibrado, mantener la llave base.",
        },
        {
            "name": "Escenario calibrado para boleto",
            "team": str(leader["team"]),
            "value": format_pct(float(leader.get("adjusted_prob", 0.0) or 0.0)),
            "action": "Este es el campeón que guía el boleto salvo noticias, lesiones o mercado fuerte en contra.",
        },
        {
            "name": "Escenario consenso externo",
            "team": str(consensus_leader["team"]),
            "value": format_pct(float(consensus_leader.get("consensus_prob", 0.0) or 0.0)),
            "action": "Si difiere del modelo, revisar ruta y no sobrecargar el favorito propio.",
        },
    ]
    if top_dark:
        scenarios.append(
            {
                "name": "Escenario tapado vigilado",
                "team": str(top_dark["team"]),
                "value": f"{float(top_dark['watch_index']):.0f}/100",
                "action": "No cambia el campeón base; activa vigilancia de rama y posibles diferenciales.",
            }
        )
    if top_divergent:
        scenarios.append(
            {
                "name": "Escenario externo disidente",
                "team": str(top_divergent["champion"]),
                "value": str(top_divergent["name"]),
                "action": "No copiar: usarlo como alarma para auditar variables y evitar ceguera de confirmación.",
            }
        )
    return scenarios


def build_consensus_guardrail_html(bracket_payload: dict, entries: Optional[Sequence[dict]] = None) -> str:
    context = consensus_live_update_context(entries)
    rows = consensus_adjusted_champion_probabilities(bracket_payload, entries)
    alerts = consensus_bracket_alerts(bracket_payload)
    if not rows and not alerts:
        return ""

    def champion_rows() -> str:
        html_rows = []
        for row in rows[:8]:
            delta = float(row["delta"])
            if delta > 0.04:
                tag = "Modelo alto"
            elif delta < -0.025:
                tag = "Modelo bajo"
            else:
                tag = "Alineado"
            html_rows.append(
                "<li>"
                f"<strong>{html.escape(str(row['team']))}</strong>"
                f"<span>Final {format_pct(float(row['adjusted_prob']))} | modelo anti-sobreconfianza {format_pct(float(row.get('calibrated_model_prob', row['model_prob'])))} | crudo 100k {format_pct(float(row['model_prob']))} | consenso {format_pct(float(row['consensus_prob']))}</span>"
                f"<em>{html.escape(tag)}</em>"
                "</li>"
            )
        return "".join(html_rows)

    def alert_rows() -> str:
        if not alerts:
            return "<li><strong>Sin ajustes de llave</strong><span>No hay cruces donde el consenso recomiende apartarse del modelo.</span><em>Mantener modelo</em></li>"
        html_rows = []
        for alert in alerts:
            status = "Aplicar en boleto" if alert["applies"] else "Mantener modelo"
            html_rows.append(
                "<li>"
                f"<strong>{html.escape(str(alert['title']))}: {html.escape(str(alert['team_a']))} vs {html.escape(str(alert['team_b']))}</strong>"
                f"<span>Modelo: {html.escape(str(alert['model_winner']))} {format_pct(float(alert['model_prob']))} | boleto: {html.escape(str(alert['recommended_winner']))} {format_pct(float(alert['recommended_prob']))} | margen {format_pct(float(alert['model_edge']))}</span>"
                f"<em>{html.escape(status)}</em>"
                "</li>"
            )
        return "".join(html_rows)

    def methodology_rows() -> str:
        html_rows = []
        for item in external_estimator_methodology_items():
            html_rows.append(
                "<li>"
                f"<strong>{html.escape(str(item['name']))}</strong>"
                f"<span>{html.escape(str(item['signal']))}</span>"
                f"<em>{html.escape(str(item['usage']))}</em>"
                "</li>"
            )
        return "".join(html_rows)

    leader = rows[0] if rows else None
    leader_tile = (
        f"<div class=\"summary-tile\"><span>Campeón recomendado</span><strong>{html.escape(str(leader['team']))}</strong></div>"
        f"<div class=\"summary-tile\"><span>Probabilidad calibrada</span><strong>{format_pct(float(leader['adjusted_prob']))}</strong></div>"
        if leader
        else ""
    )
    return (
        "<section class=\"panel consensus-panel\">"
        "<div class=\"panel-head\">"
        "<div>"
        "<p class=\"eyebrow\">Guardrail de consenso</p>"
        "<h2>Ajustes para boleto de quiniela</h2>"
        "<p class=\"lede-tight\">Esta capa compara la llave contra consenso externo definido: priors declarados de campeón, ratings tipo Elo/FIFA, fuerza ofensiva-defensiva tipo SPI, mercado cuando existe y señales live/finales. No es una caja negra ni reemplaza el Monte Carlo; solo evita extremos hasta que haya evidencia real del Mundial.</p>"
        "</div>"
        "</div>"
        "<div class=\"confidence-tiles\">"
        f"{leader_tile}"
        f"<div class=\"summary-tile\"><span>Peso modelo/live</span><strong>{format_pct(float(context['model_blend']))}</strong></div>"
        f"<div class=\"summary-tile\"><span>Peso consenso externo</span><strong>{format_pct(float(context['consensus_blend']))}</strong></div>"
        f"<div class=\"summary-tile\"><span>Partidos usados</span><strong>{int(context['final_count'])} final / {int(context['live_count'])} live</strong></div>"
        "</div>"
        "<div class=\"certainty-grid consensus-grid\">"
        "<article><h3>Campeón calibrado</h3><ul>"
        f"{champion_rows()}"
        "</ul></article>"
        "<article><h3>Ajustes de llave recomendados</h3><ul>"
        f"{alert_rows()}"
        "</ul></article>"
        "<article><h3>Metodología de estimadores externos</h3><ul>"
        f"{methodology_rows()}"
        "</ul></article>"
        "</div>"
        "</section>"
    )


def external_forecast_comparison(bracket_payload: dict, entries: Optional[Sequence[dict]] = None) -> dict:
    adjusted_rows = consensus_adjusted_champion_probabilities(bracket_payload, entries)
    adjusted_map = {str(row["team"]): row for row in adjusted_rows}
    leader = adjusted_rows[0] if adjusted_rows else None
    leader_team = str((leader or {}).get("team", "Sin llave"))
    benchmarks = []
    for benchmark in EXTERNAL_FORECAST_BENCHMARKS:
        item = dict(benchmark)
        champion = str(item["champion"])
        ours = adjusted_map.get(champion, {})
        ours_prob = float(ours.get("adjusted_prob", 0.0) or 0.0)
        external_prob = item.get("champion_prob")
        delta = ours_prob - float(external_prob) if external_prob is not None else None
        if champion == leader_team:
            reading = "Coincide con nuestro líder vigente."
        elif ours_prob >= 0.06:
            reading = "No lidera nuestra corrida, pero sigue siendo candidato serio."
        elif champion in DARK_HORSE_EXTERNAL_SIGNALS:
            reading = "Funciona como alerta de tapado; vigilar su ruta antes de subirlo."
        else:
            reading = "Divergencia visible: revisar variables y ruta, no copiar el pick."
        item.update(
            {
                "ours_prob": ours_prob,
                "delta": delta,
                "agrees_with_leader": champion == leader_team,
                "reading": reading,
            }
        )
        benchmarks.append(item)
    return {
        "leader": leader,
        "benchmarks": benchmarks,
        "agreement_count": sum(1 for item in benchmarks if item["agrees_with_leader"]),
        "distinct_champions": sorted({str(item["champion"]) for item in benchmarks}),
    }


def build_external_forecast_benchmarks_markdown(
    bracket_payload: dict,
    entries: Optional[Sequence[dict]] = None,
) -> List[str]:
    comparison = external_forecast_comparison(bracket_payload, entries)
    scenarios = external_scenario_stress_tests(bracket_payload, entries)
    upgrades = statistical_upgrade_recommendations()
    leader = comparison["leader"]
    if not leader:
        return ["_Sin llave generada para comparar contra modelos externos publicados._"]
    lines = [
        f"- Nuestro líder vigente: {leader['team']} con {format_pct(float(leader['adjusted_prob']))} de probabilidad calibrada de campeón.",
        f"- Coincidencias: {int(comparison['agreement_count'])}/{len(comparison['benchmarks'])} benchmarks publicados eligen al mismo campeón. No se promedian a ciegas: se usan para auditar divergencias.",
        "- Próxima mejora que sí mueve calidad: recalibrar pesos con walk-forward apenas entren resultados reales del Mundial y añadir mercado live solo cuando exista un feed verificable.",
    ]
    for item in comparison["benchmarks"]:
        external_prob = item.get("champion_prob")
        external_text = format_pct(float(external_prob)) if external_prob is not None else "probabilidad no publicada"
        lines.append(
            f"- {item['name']} ({item['published_at']}): campeón {item['champion']} | externo {external_text} | "
            f"nuestro modelo hoy {format_pct(float(item['ours_prob']))} | final {item['final']} | {item['reading']}"
        )
    if scenarios:
        lines.append("- Escenarios de estrés para no casarnos con un solo relato:")
        for scenario in scenarios:
            lines.append(f"  - {scenario['name']}: {scenario['team']} | {scenario['value']} | {scenario['action']}")
    lines.append("- Modelos/variables que sí conviene agregar o reforzar:")
    for upgrade in upgrades:
        lines.append(f"  - {upgrade['name']} ({upgrade['status']}): {upgrade['why']} Impacto: {upgrade['impact']}")
    return lines


def build_external_forecast_benchmarks_html(
    bracket_payload: dict,
    entries: Optional[Sequence[dict]] = None,
) -> str:
    comparison = external_forecast_comparison(bracket_payload, entries)
    scenarios = external_scenario_stress_tests(bracket_payload, entries)
    upgrades = statistical_upgrade_recommendations()
    leader = comparison["leader"]
    if not leader:
        return ""
    cards = []
    for item in comparison["benchmarks"]:
        external_prob = item.get("champion_prob")
        external_text = format_pct(float(external_prob)) if external_prob is not None else "No publicada"
        delta = item.get("delta")
        delta_text = f"{float(delta) * 100:+.1f} pp" if delta is not None else "Sin comparación porcentual"
        agreement = "Coincide" if item["agrees_with_leader"] else "Contraste"
        cards.append(
            "<article class=\"benchmark-card\">"
            "<div class=\"benchmark-card-top\">"
            f"<span>{html.escape(str(item['snapshot']))}</span>"
            f"<strong>{html.escape(str(item['name']))}</strong>"
            f"<em>{html.escape(str(item['published_at']))}</em>"
            "</div>"
            "<div class=\"benchmark-metrics\">"
            f"<span>Campeón publicado<strong>{html.escape(str(item['champion']))}</strong></span>"
            f"<span>Probabilidad externa<strong>{html.escape(external_text)}</strong></span>"
            f"<span>Nuestro modelo hoy<strong>{format_pct(float(item['ours_prob']))}</strong></span>"
            f"<span>Brecha propia vs externa<strong>{html.escape(delta_text)}</strong></span>"
            "</div>"
            f"<p><strong>Final publicada:</strong> {html.escape(str(item['final']))}</p>"
            f"<p><strong>Lectura:</strong> {html.escape(str(item['reading']))}</p>"
            f"<p><strong>Método:</strong> {html.escape(str(item['methodology']))}</p>"
            f"<p class=\"benchmark-source\"><a href=\"{html.escape(str(item['source_url']), quote=True)}\" target=\"_blank\" rel=\"noopener noreferrer\">Abrir fuente publicada</a><em>{html.escape(agreement)}</em></p>"
            "</article>"
        )
    scenario_rows = []
    for scenario in scenarios:
        scenario_rows.append(
            "<li>"
            f"<strong>{html.escape(str(scenario['name']))}: {html.escape(str(scenario['team']))}</strong>"
            f"<span>{html.escape(str(scenario['value']))}</span>"
            f"<em>{html.escape(str(scenario['action']))}</em>"
            "</li>"
        )
    upgrade_rows = []
    for item in upgrades:
        upgrade_rows.append(
            "<li>"
            f"<strong>{html.escape(str(item['name']))}</strong>"
            f"<span>{html.escape(str(item['why']))}</span>"
            f"<em>{html.escape(str(item['status']))}: {html.escape(str(item['impact']))}</em>"
            "</li>"
        )
    return (
        "<section class=\"panel benchmark-panel\" id=\"comparadores\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Comparadores externos</p>"
        "<h2>Qué dicen otros modelos y dónde debemos desconfiar</h2>"
        "<p class=\"lede-tight\">Esta mesa compara nuestra llave vigente contra cortes publicados por Goldman Sachs, Opta, PwC, FairCast, Panmure Liberum/Klement y mercado público. No se promedian a ciegas ni se usan para maquillar probabilidades: sirven para detectar divergencias, revisar supuestos y vigilar tapados.</p>"
        "</div></div>"
        "<div class=\"confidence-tiles\">"
        f"<div class=\"summary-tile\"><span>Nuestro líder vigente</span><strong>{html.escape(str(leader['team']))}</strong><small>{format_pct(float(leader['adjusted_prob']))} campeón calibrado en esta corrida.</small></div>"
        f"<div class=\"summary-tile\"><span>Benchmarks publicados</span><strong>{len(comparison['benchmarks'])}</strong><small>Cada tarjeta muestra fuente, fecha y metodología.</small></div>"
        f"<div class=\"summary-tile\"><span>Coinciden con nuestro líder</span><strong>{int(comparison['agreement_count'])}/{len(comparison['benchmarks'])}</strong><small>El desacuerdo es información útil, no un error que deba ocultarse.</small></div>"
        f"<div class=\"summary-tile\"><span>Campeones externos distintos</span><strong>{len(comparison['distinct_champions'])}</strong><small>{html.escape(', '.join(comparison['distinct_champions']))}</small></div>"
        "</div>"
        f"<div class=\"benchmark-grid\">{''.join(cards)}</div>"
        "<div class=\"scenario-table-card benchmark-stress-card\">"
        "<h3>Escenarios de estrés: qué pasa si otro relato tiene razón</h3>"
        "<p>No cambiaremos la llave por una opinión externa aislada. Sí usamos estos escenarios para auditar si el modelo está ignorando a Portugal, Netherlands, France u otro tapado serio.</p>"
        "<ul class=\"scenario-decision-list\">"
        f"{''.join(scenario_rows)}"
        "</ul>"
        "</div>"
        "<div class=\"scenario-table-card benchmark-upgrade-card\">"
        "<h3>Modelos y variables que sí conviene reforzar</h3>"
        "<p>La mejora real no es subir simulaciones sin fin ni inflar certezas: es añadir capas que expliquen fuerza relativa, incertidumbre, margen y variables live trazables.</p>"
        "<ul class=\"scenario-decision-list\">"
        f"{''.join(upgrade_rows)}"
        "</ul>"
        "</div>"
        "<div class=\"benchmark-next-step\">"
        "<h3>Qué agregaría después</h3>"
        "<p><strong>Sí:</strong> Bradley-Terry jerárquico dinámico, Glicko/TrueSkill de incertidumbre, margen Skellam/ordinal calibrado, calibración walk-forward apenas haya resultados reales y mercado live verificable. <strong>No:</strong> sumar PIB, población o clima dos veces si ya están absorbidos por recursos, FIFA, Elo y contexto; eso crea falsa precisión.</p>"
        "</div>"
        "</section>"
    )


def build_dark_horses_markdown(bracket_payload: dict, entries: Optional[Sequence[dict]] = None) -> List[str]:
    candidates = dark_horse_candidates(bracket_payload, entries)
    if not candidates:
        return ["_La corrida vigente no detecta tapados con una ruta suficientemente abierta._"]
    lines = [
        "- Regla: un tapado no se agrega por intuición. Debe conservar una ruta Monte Carlo visible hacia cuartos/semifinales o aparecer en una señal externa trazable. Las menciones externas son alertas; no reemplazan probabilidades ni fuerzan la llave.",
        "- Lectura: candidato secundario no significa favorito. Tapado serio indica que conviene vigilar su rama. Tapado de mayor varianza solo justifica una alerta, no cambiar el boleto base.",
    ]
    for candidate in candidates:
        lines.append(
            f"- {candidate['team']} | {candidate['tier']} | índice de vigilancia {float(candidate['watch_index']):.0f}/100 | "
            f"valor tapado {float(candidate.get('undervalued_score', 0.0)):.0f}/100 ({candidate.get('undervalued_label', 'alerta')}) | "
            f"campeón calibrado {format_pct(float(candidate['adjusted_prob']))} | cuartos {format_pct(float(candidate['quarterfinal_prob']))} | "
            f"semifinal {format_pct(float(candidate['semifinal_prob']))} | final {format_pct(float(candidate['final_prob']))} | "
            f"{candidate['contrast']} Señal: {candidate['external_source']}."
        )
    return lines


def build_dark_horses_html(bracket_payload: dict, entries: Optional[Sequence[dict]] = None) -> str:
    candidates = dark_horse_candidates(bracket_payload, entries)
    if not candidates:
        return ""
    cards = []
    for candidate in candidates:
        source_url = str(candidate["external_url"])
        source_html = html.escape(str(candidate["external_source"]))
        if source_url:
            source_html = (
                f"<a href=\"{html.escape(source_url, quote=True)}\" target=\"_blank\" rel=\"noopener noreferrer\">"
                f"{source_html}</a>"
            )
        cards.append(
            "<article class=\"dark-horse-card\">"
            "<div class=\"dark-horse-card-top\">"
            f"<span>{html.escape(str(candidate['tier']))}</span>"
            f"<strong>{html.escape(str(candidate['team']))}</strong>"
            f"<em>{float(candidate['watch_index']):.0f}/100 vigilancia</em>"
            "</div>"
            "<div class=\"dark-horse-metrics\">"
            f"<span>Valor tapado <strong>{float(candidate.get('undervalued_score', 0.0)):.0f}/100</strong></span>"
            f"<span>Tipo <strong>{html.escape(str(candidate.get('undervalued_label', 'Alerta')))}</strong></span>"
            f"<span>Campeón calibrado <strong>{format_pct(float(candidate['adjusted_prob']))}</strong></span>"
            f"<span>Cuartos <strong>{format_pct(float(candidate['quarterfinal_prob']))}</strong></span>"
            f"<span>Semifinal <strong>{format_pct(float(candidate['semifinal_prob']))}</strong></span>"
            f"<span>Final <strong>{format_pct(float(candidate['final_prob']))}</strong></span>"
            "</div>"
            f"<p><strong>Contraste:</strong> {html.escape(str(candidate['contrast']))}</p>"
            f"<p><strong>Señal trazable:</strong> {source_html}. {html.escape(str(candidate['external_note']))}</p>"
            f"<p class=\"dark-horse-action\"><strong>Acción:</strong> {html.escape(str(candidate.get('undervalued_action') or candidate['action']))}</p>"
            "</article>"
        )
    leader = candidates[0]
    external_count = sum(1 for candidate in candidates if candidate["external_url"])
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    iterations_label = f"{iterations:,}".replace(",", ".") if iterations else "sin dato"
    return (
        "<section class=\"panel dark-horse-panel\" id=\"tapados\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Radar de tapados</p>"
        "<h2>Tapados con ruta realista</h2>"
        f"<p class=\"lede-tight\">Este módulo busca equipos capaces de romper la llave sin disfrazarlos de favoritos. Combina la ruta vigente de {iterations_label} simulaciones Monte Carlo, la probabilidad calibrada de campeón y señales externas recientes. El índice de vigilancia ordena alertas; no es una probabilidad de título. La señal editorial solo activa vigilancia: no reemplaza la llave base ni maquilla el pronóstico.</p>"
        "</div></div>"
        "<div class=\"confidence-tiles\">"
        f"<div class=\"summary-tile\"><span>Tapados vigilados</span><strong>{len(candidates)}</strong><small>Se recalculan con cada corrida y cambian si cambia la llave.</small></div>"
        f"<div class=\"summary-tile\"><span>Radar principal</span><strong>{html.escape(str(leader['team']))}</strong><small>{html.escape(str(leader['tier']))} | {float(leader['watch_index']):.0f}/100 vigilancia.</small></div>"
        f"<div class=\"summary-tile\"><span>Señales externas trazables</span><strong>{external_count}</strong><small>Sirven como contraste visible; no fuerzan probabilidades.</small></div>"
        "<div class=\"summary-tile\"><span>Regla de uso</span><strong>Vigilar, no inventar</strong><small>Un tapado exige ruta abierta; no sustituye automáticamente el boleto base.</small></div>"
        "</div>"
        f"<div class=\"dark-horse-grid\">{''.join(cards)}</div>"
        "</section>"
    )


def calibration_depth_metrics(entries: Sequence[dict], backtest: dict) -> dict:
    fixture_entries = [entry for entry in entries if not entry.get("projection")]
    agreements = [
        float((entry.get("prediction").statistical_depth or {}).get("model_agreement"))
        for entry in fixture_entries
        if entry.get("prediction")
        and (entry.get("prediction").statistical_depth or {}).get("model_agreement") is not None
    ]
    market_gaps = [
        abs(float((entry.get("prediction").statistical_depth or {}).get("market_gap")))
        for entry in fixture_entries
        if entry.get("prediction")
        and (entry.get("prediction").statistical_depth or {}).get("market_gap") is not None
    ]
    completed = int(backtest.get("completed_matches", 0) or 0)
    regular_samples = int(backtest.get("regular_time_samples", 0) or 0)
    reliability = backtest.get("brier_reliability")
    temporal_accuracy = backtest.get("temporal_cv_accuracy")
    buckets = backtest.get("calibration_buckets") or []
    avg_agreement = sum(agreements) / len(agreements) if agreements else None
    avg_market_gap = sum(market_gaps) / len(market_gaps) if market_gaps else None
    if regular_samples >= 20 and reliability is not None:
        calibration_state = "Brier 2026 con muestra"
        calibration_action = (
            f"Ya recalcula Brier, log-loss y buckets con {regular_samples} partidos comparables; "
            "usar esta lectura para ajustar confianza operativa."
        )
    elif regular_samples > 0 and reliability is not None:
        calibration_state = "Brier 2026 activo"
        calibration_action = (
            f"Ya recalcula Brier, log-loss y acierto con {regular_samples} partido(s) finalizado(s); "
            "la lectura es provisional hasta acumular muestra."
        )
    elif completed > 0:
        calibration_state = "Resultado real detectado"
        calibration_action = "Ya hay partidos cerrados; el Brier de 90 minutos se activa cuando el resultado sea comparable."
    else:
        calibration_state = "Calibración previa activa"
        calibration_action = "Aún no hay partidos cerrados de 2026; el Brier arranca automáticamente con el primer resultado final."
    if reliability is not None and float(reliability) > 0.035:
        confidence_rule = "Bajar agresividad: el modelo está mostrando error de calibración."
    elif avg_agreement is not None and avg_agreement < 0.56:
        confidence_rule = "Bajar picks heroicos: los modelos internos discrepan."
    else:
        confidence_rule = "Mantener picks base, pero cubrir partidos con brecha pequeña."
    return {
        "completed": completed,
        "regular_samples": regular_samples,
        "buckets": len(buckets),
        "reliability": reliability,
        "temporal_accuracy": temporal_accuracy,
        "avg_agreement": avg_agreement,
        "avg_market_gap": avg_market_gap,
        "historical_prior_active": completed == 0,
        "calibration_state": calibration_state,
        "calibration_action": calibration_action,
        "confidence_rule": confidence_rule,
    }


def calibration_depth_items(metrics: dict) -> List[dict]:
    return [
        {
            "label": "Shrinkage bayesiano",
            "status": "Activo",
            "detail": "Reduce el peso de muestras pequeñas: historia, forma y rendimiento por confederación no dominan si hay poca evidencia.",
        },
        {
            "label": "Desacuerdo entre modelos",
            "status": "Activo" if metrics["avg_agreement"] is not None else "Preparado",
            "detail": (
                f"Coincidencia interna media {format_pct(float(metrics['avg_agreement']))}; si baja, se reduce la confianza del pick."
                if metrics["avg_agreement"] is not None
                else "Se activará cuando todos los partidos tengan stack de modelos comparable."
            ),
        },
        {
            "label": "Mercado y consenso",
            "status": "Activo",
            "detail": (
                f"Brecha media vs mercado {format_pct(float(metrics['avg_market_gap']))}; se usa como ancla suave, no como reemplazo del modelo."
                if metrics["avg_market_gap"] is not None
                else "Consenso de campeón activo; líneas de goles entran cuando el feed las traiga."
            ),
        },
        {
            "label": "Backtesting por buckets",
            "status": "Activo" if metrics["buckets"] else "Listo para resultados 2026",
            "detail": (
                f"{metrics['buckets']} tramos de confianza medidos con {metrics['regular_samples']} partidos comparables."
                if metrics["buckets"]
                else "No existe Brier real del Mundial 2026 antes de que se jueguen partidos; se activa automáticamente con el primer resultado final."
            ),
        },
        {
            "label": "Límite de confianza operativa",
            "status": "Activo",
            "detail": metrics["confidence_rule"],
        },
    ]


def build_calibration_depth_markdown(entries: Sequence[dict], backtest: dict) -> List[str]:
    metrics = calibration_depth_metrics(entries, backtest)
    lines = [
        f"- Estado: {metrics['calibration_state']}. {metrics['calibration_action']}",
        f"- Partidos cerrados para calibrar: {metrics['completed']} | muestra 90 minutos: {metrics['regular_samples']}.",
    ]
    if metrics["reliability"] is not None:
        lines.append(f"- Brier calibración/reliability: {float(metrics['reliability']):.3f}. Menor es mejor.")
    if metrics["temporal_accuracy"] is not None:
        lines.append(f"- Acierto temporal por ventanas: {format_pct(float(metrics['temporal_accuracy']))}.")
    for item in calibration_depth_items(metrics):
        lines.append(f"- {item['label']}: {item['status']} | {item['detail']}")
    return lines


def build_calibration_depth_html(entries: Sequence[dict], backtest: dict) -> str:
    metrics = calibration_depth_metrics(entries, backtest)

    def tile(label: str, value: str, note: str = "") -> str:
        note_html = f"<small>{html.escape(note)}</small>" if note else ""
        return (
            "<div class=\"summary-tile\">"
            f"<span>{html.escape(label)}</span><strong>{html.escape(value)}</strong>{note_html}"
            "</div>"
        )

    items = calibration_depth_items(metrics)
    rows = "".join(
        "<article class=\"method-quality-card\">"
        f"<span class=\"method-status {'ok' if item['status'] == 'Activo' else 'neutral'}\">{html.escape(str(item['status']))}</span>"
        f"<h3>{html.escape(str(item['label']))}</h3>"
        f"<p>{html.escape(str(item['detail']))}</p>"
        "</article>"
        for item in items
    )
    reliability_value = (
        f"{float(metrics['reliability']):.3f}"
        if metrics["reliability"] is not None
        else "sin Brier 2026"
    )
    agreement_value = (
        format_pct(float(metrics["avg_agreement"]))
        if metrics["avg_agreement"] is not None
        else "pendiente"
    )
    temporal_value = (
        format_pct(float(metrics["temporal_accuracy"]))
        if metrics["temporal_accuracy"] is not None
        else "listo al 1er final"
    )
    return (
        "<section class=\"panel calibration-panel\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Calibración avanzada</p>"
        "<h2>Cómo evitamos que el modelo se sobreconfíe</h2>"
        "<p class=\"lede-tight\">Profundizar la metodología sí vale la pena, pero solo si se traduce en mejores decisiones de quiniela. Esta capa muestra los frenos estadísticos que corrigen probabilidades extremas y separan pick fuerte de partido cerrado.</p>"
        "</div></div>"
        "<div class=\"confidence-tiles\">"
        f"{tile('Estado de calibración', str(metrics['calibration_state']), str(metrics['calibration_action']))}"
        f"{tile('Brier calibración', reliability_value, 'Arranca con el primer partido finalizado y se recalcula en cada refresh de 5 minutos.')}"
        f"{tile('Coincidencia entre modelos', agreement_value, 'Si baja, el boleto debe cubrir más partidos.')}"
        f"{tile('Acierto por ventanas', temporal_value, 'Empieza con la primera muestra y se estabiliza a medida que avanza el campeonato.')}"
        "</div>"
        "<div class=\"method-quality calibration-quality\">"
        "<div class=\"method-quality-head\">"
        "<p class=\"eyebrow\">Controles activos</p>"
        "<h3>Calibraciones que sí cambian la forma de decidir</h3>"
        "<p>No fuerzan una confianza artificial de 90%: reducen sobreconfianza, activan cobertura y hacen que el modelo aprenda con resultados reales.</p>"
        "</div>"
        f"<div class=\"method-quality-grid\">{rows}</div>"
        "</div>"
        "</section>"
    )


def professional_team_strength_index(team_name: str) -> float:
    team = load_teams().get(team_name)
    if not team:
        return 0.50
    profile = profile_for(team)
    elo_index = clamp((float(team.elo) - 1320.0) / 620.0, 0.0, 1.0)
    fifa_rank_index = clamp(1.0 - (float(profile.fifa_rank) - 1.0) / 85.0, 0.0, 1.0)
    squad_index = clamp(
        0.24 * profile.squad.squad_quality
        + 0.18 * profile.squad.attack_unit
        + 0.17 * profile.squad.midfield_unit
        + 0.17 * profile.squad.defense_unit
        + 0.10 * profile.squad.goalkeeper_unit
        + 0.08 * profile.squad.bench_depth
        + 0.06 * profile.squad.player_experience,
        0.0,
        1.0,
    )
    history_index = clamp(
        0.36 * profile.history.strength_index
        + 0.24 * profile.history.competitive_index
        + 0.22 * profile.history.world_cup_index
        + 0.10 * profile.history.attack_index
        + 0.08 * profile.history.defense_index,
        0.0,
        1.0,
    )
    return clamp(
        0.22 * elo_index
        + 0.17 * profile.fifa_strength_index
        + 0.16 * fifa_rank_index
        + 0.16 * squad_index
        + 0.12 * history_index
        + 0.07 * profile.resource_index
        + 0.05 * profile.coach_index
        + 0.03 * profile.chemistry_index
        + 0.02 * profile.heritage_index,
        0.0,
        1.0,
    )


def professional_pick_support(prediction: MatchPrediction, pick_code: str) -> float:
    strength_a = professional_team_strength_index(prediction.team_a)
    strength_b = professional_team_strength_index(prediction.team_b)
    if pick_code == "1":
        return clamp(0.50 + 0.92 * (strength_a - strength_b), 0.05, 0.98)
    if pick_code == "2":
        return clamp(0.50 + 0.92 * (strength_b - strength_a), 0.05, 0.98)
    parity = 1.0 - abs(strength_a - strength_b)
    return clamp(0.32 + 0.38 * parity + 0.70 * max(0.0, float(prediction.draw) - 0.25), 0.05, 0.90)


def prediction_power_profile(entry: dict) -> dict:
    prediction: MatchPrediction = entry["prediction"]
    base = quiniela_strategy_profile(entry)
    market_gap_raw = base.get("market_gap")
    market_gap = abs(float(market_gap_raw)) if market_gap_raw is not None else 0.0
    market_alignment = 1.0 if market_gap_raw is None else clamp(1.0 - 1.8 * market_gap, 0.0, 1.0)
    gap_strength = clamp(float(base["gap"]) / 0.28, 0.0, 1.0)
    structural_support = professional_pick_support(prediction, str(base["pick_code"]))
    draw_risk = clamp(float(prediction.draw) + max(0.0, 0.14 - float(base["gap"])), 0.0, 1.0)
    conviction = clamp(
        0.42
        + 0.30 * float(base["pick_prob"])
        + 0.12 * gap_strength
        + 0.11 * float(base["agreement"])
        + 0.10 * structural_support
        + 0.07 * float(base["certainty_score"])
        + 0.05 * float(base["top3"])
        + 0.04 * market_alignment
        - 0.10 * draw_risk,
        0.05,
        0.99,
    )
    if conviction >= 0.88 and float(base["pick_prob"]) >= 0.55:
        power_tier = "Potenciado alto"
        power_action = "Puede ser pick central del boleto."
    elif conviction >= 0.78:
        power_tier = "Potenciado jugable"
        power_action = "Usar como pick, pero revisar cobertura si el margen es pequeño."
    elif conviction >= 0.66:
        power_tier = "Potenciado con cautela"
        power_action = "No subirlo demasiado: jugar solo si necesitas cubrir ese tramo."
    else:
        power_tier = "No potenciar"
        power_action = "Mantener como partido de riesgo o cobertura."
    drivers = []
    if structural_support >= 0.62:
        drivers.append("fuerza estructural")
    if float(base["agreement"]) >= 0.72:
        drivers.append("modelos alineados")
    if float(base["gap"]) >= 0.14:
        drivers.append("brecha clara")
    if not DISABLE_PUBLIC_POPULARITY_PROXY and float(base["edge_vs_public"]) >= 0.04:
        drivers.append("edge vs boleto popular")
    if market_alignment >= 0.70:
        drivers.append("sin choque fuerte con mercado")
    if not drivers:
        drivers.append("señal moderada")
    return {
        **base,
        "structural_support": structural_support,
        "market_alignment": market_alignment,
        "draw_risk": draw_risk,
        "power_conviction": conviction,
        "power_boost": conviction - float(base["pick_prob"]),
        "power_tier": power_tier,
        "power_action": power_action,
        "power_drivers": drivers[:3],
    }


def prediction_power_metrics(profiles: Sequence[dict]) -> dict:
    if not profiles:
        return {
            "total": 0,
            "avg_conviction": 0.0,
            "avg_boost": 0.0,
            "high_power": 0,
            "watchlist": 0,
            "avg_structural": 0.0,
        }
    total = len(profiles)
    return {
        "total": total,
        "avg_conviction": sum(float(item["power_conviction"]) for item in profiles) / total,
        "avg_boost": sum(float(item["power_boost"]) for item in profiles) / total,
        "high_power": sum(1 for item in profiles if item["power_tier"] == "Potenciado alto"),
        "watchlist": sum(1 for item in profiles if item["power_tier"] in {"Potenciado con cautela", "No potenciar"}),
        "avg_structural": sum(float(item["structural_support"]) for item in profiles) / total,
    }


def build_prediction_power_markdown(entries: Sequence[dict]) -> List[str]:
    profiles = [prediction_power_profile(entry) for entry in entries]
    metrics = prediction_power_metrics(profiles)
    strongest = sorted(
        profiles,
        key=lambda item: (item["power_conviction"], item["pick_prob"], item["gap"]),
        reverse=True,
    )[:10]
    lines = [
        "### Predicción potenciada",
        "- Lectura: no es una probabilidad nueva; es un índice de firmeza para decidir boleto.",
        f"- Índice de firmeza medio: {format_pct(float(metrics['avg_conviction']))}.",
        f"- Picks de potencia alta: {int(metrics['high_power'])}/{int(metrics['total'])}; watchlist: {int(metrics['watchlist'])}.",
    ]
    for item in strongest:
        lines.append(
            f"- {item['title']}: {item['pick_label']} | probabilidad pura {format_pct(float(item['pick_prob']))} | índice de firmeza {format_pct(float(item['power_conviction']))} | drivers: {', '.join(item['power_drivers'])}."
        )
    return lines


def build_prediction_power_html(entries: Sequence[dict]) -> str:
    if not entries:
        return ""
    profiles = [prediction_power_profile(entry) for entry in entries]
    metrics = prediction_power_metrics(profiles)
    strongest = sorted(
        profiles,
        key=lambda item: (item["power_conviction"], item["pick_prob"], item["gap"]),
        reverse=True,
    )[:8]
    caution = sorted(
        [item for item in profiles if item["power_tier"] in {"Potenciado con cautela", "No potenciar"}],
        key=lambda item: (item["power_conviction"], item["pick_prob"]),
    )[:8]

    def tile(label: str, value: str, note: str = "") -> str:
        note_html = f"<small>{html.escape(note)}</small>" if note else ""
        return (
            "<div class=\"summary-tile\">"
            f"<span>{html.escape(label)}</span><strong>{html.escape(value)}</strong>{note_html}"
            "</div>"
        )

    def rows(items: Sequence[dict], empty: str) -> str:
        if not items:
            return f"<li><strong>{html.escape(empty)}</strong><span>Sin casos en este corte.</span></li>"
        rendered = []
        for item in items:
            rendered.append(
                "<li>"
                f"<strong>{html.escape(str(item['title']))}</strong>"
                f"<span>{html.escape(str(item['pick_label']))}: probabilidad pura {format_pct(float(item['pick_prob']))} | índice de firmeza {format_pct(float(item['power_conviction']))} | fuerza estructural {format_pct(float(item['structural_support']))}</span>"
                f"<em>{html.escape(str(item['power_tier']))}: {html.escape(str(item['power_action']))} Drivers: {html.escape(', '.join(item['power_drivers']))}</em>"
                "</li>"
            )
        return "".join(rendered)

    return (
        "<section class=\"panel power-panel\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Predicción potenciada</p>"
        "<h2>Probabilidad pura vs índice de firmeza para jugar la quiniela</h2>"
        "<p class=\"lede-tight\">Aquí potenciamos la decisión sin maquillar la probabilidad: cruzamos la predicción base con fuerza estructural FIFA/Elo/squad/historia, acuerdo entre modelos, mercado y riesgo de empate.</p>"
        "<p class=\"meta\">El índice de firmeza no es una probabilidad de que ocurra el resultado; es un índice de decisión para ordenar el boleto y saber dónde puedes jugar más firme.</p>"
        "</div></div>"
        "<div class=\"confidence-tiles\">"
        f"{tile('Índice de firmeza medio', format_pct(float(metrics['avg_conviction'])), '0-100 para ordenar el boleto; no probabilidad pura.')}"
        f"{tile('Picks de potencia alta', str(int(metrics['high_power'])) + '/' + str(int(metrics['total'])), 'Candidatos a columna vertebral del boleto.')}"
        f"{tile('Fuerza estructural media', format_pct(float(metrics['avg_structural'])), 'FIFA, Elo, squad, historia y recursos.')}"
        f"{tile('Watchlist de riesgo', str(int(metrics['watchlist'])), 'Partidos que no conviene vender como fijos.')}"
        "</div>"
        "<div class=\"certainty-grid power-grid\">"
        "<article><h3>Picks más potenciados</h3><ul>"
        f"{rows(strongest, 'Sin picks potenciados')}"
        "</ul></article>"
        "<article><h3>No forzar como fijo</h3><ul>"
        f"{rows(caution, 'Sin watchlist')}"
        "</ul></article>"
        "</div>"
        "</section>"
    )


def agentic_learning_items() -> List[dict]:
    return [
        {
            "agent": "Agente de ingesta",
            "job": "Lee fixtures, estado del partido, mercado, noticias, bajas, alineaciones y proveedor live cuando exista.",
            "learns": "No inventa datos: solo convierte fuentes disponibles en señales trazables.",
        },
        {
            "agent": "Agente de señales",
            "job": "Traduce cada dato a variables futbolísticas: disponibilidad, forma, fatiga, tarjetas, momentum, tiros, ocasiones y riesgo de empate.",
            "learns": "Si un evento cambia el partido, ajusta goles restantes, probabilidad de resultado y marcador exacto.",
        },
        {
            "agent": "Agente predictivo",
            "job": "Combina Poisson/Dixon-Coles, overdispersión calibrada, predictivo bayesiano dinámico, ML ligero, Elo/FIFA, ensamble, consenso externo y Monte Carlo de torneo.",
            "learns": "Cuando cambia un resultado, recalcula de inmediato el tablero live y propaga grupos, cruces, llave y campeón en la siguiente corrida profunda.",
        },
        {
            "agent": "Agente de calibración",
            "job": "Mide Brier, log-loss, buckets de confianza y backtesting temporal.",
            "learns": "Baja la agresividad si el modelo está sobreconfiado y sube cobertura si los modelos discrepan.",
        },
        {
            "agent": "Agente de quiniela",
            "job": "Convierte probabilidades en decisiones: pick base, marcador principal, segunda opción y cobertura.",
            "learns": "Optimiza puntos esperados, marcador principal, segunda opción y cobertura sin usar popularidad estimada como dato.",
        },
        {
            "agent": "Agente auditor",
            "job": "Bloquea publicación si falta el mínimo operativo de simulaciones, llave coherente, consenso, goles, auditoría o refresh de 5 minutos.",
            "learns": "Cada falla deja una regla verificable para que el pipeline no publique una versión incompleta.",
        },
    ]


def sports_news_source_policy_items() -> List[dict]:
    return [
        {
            "source": "ESPN / scoreboard público",
            "use": "Base de calendario, estado y resultado cuando no hay feed más profundo.",
        },
        {
            "source": "FIFA Match Centre / datos oficiales",
            "use": "Confirmación de partido, sedes, plantillas, sanciones, XI y eventos oficiales si el feed está disponible.",
        },
        {
            "source": "Reuters / AP / BBC / Sky / The Athletic / Guardian",
            "use": "Noticias confirmadas, bajas, lesiones, decisiones técnicas y contexto prepartido.",
        },
        {
            "source": "Federaciones, clubes y cuentas oficiales",
            "use": "Validación de lesionados, convocatorias, suspensiones y cambios de portero o once.",
        },
        {
            "source": "Proveedor live profundo",
            "use": "Tiros, tiros al arco, calidad de ocasión, corners, rojas, sustituciones, xG live y secuencia minuto a minuto.",
        },
    ]


def live_provider_catalog() -> List[dict]:
    return [
        {
            "name": "ESPN scoreboard",
            "category": "Base pública",
            "priority": "Automático sin key",
            "coverage": "Calendario, marcador, estado, resumen, odds y noticias si el endpoint lo expone.",
            "integration": "Ya integrado",
            "env": "sin key",
            "role": "Mantenerlo como piso: nunca debe ser el único proveedor cuando haya partidos en vivo.",
        },
        {
            "name": "Open-Meteo",
            "category": "Clima/sedes",
            "priority": "Automático sin key",
            "coverage": "Pronóstico y baseline meteorológico por sede: temperatura, humedad, viento, lluvia y wet bulb.",
            "integration": "Ya integrado sin key",
            "env": "sin key",
            "role": "Ajusta desgaste, ritmo y riesgo de partido sin pedirte ninguna cuenta externa.",
        },
        {
            "name": "GDELT",
            "category": "Noticias abiertas",
            "priority": "Automático sin key",
            "coverage": "Monitoreo global de noticias y menciones; lesiones, sanciones, lineup probable y contexto de selección.",
            "integration": "Ya integrado sin key",
            "env": "sin key",
            "role": "Fuente multi-prensa para no depender de una sola redacción; el filtro solo mueve el modelo si detecta señal relevante.",
        },
        {
            "name": "API-Football / API-SPORTS",
            "category": "Live profundo",
            "priority": "Opcional premium",
            "coverage": "Fixtures live, lineups, eventos, estadísticas, tiros, tarjetas, sustituciones y xG si viene en el feed.",
            "integration": "Ya cableado si hay credencial",
            "env": "API_FOOTBALL_KEY",
            "role": "Primer proveedor real para in-play: activa eventos minuto a minuto y estadísticas live.",
        },
        {
            "name": "Sportmonks Football API",
            "category": "Live profundo",
            "priority": "Opcional premium",
            "coverage": "Livescores, eventos, World Cup 2026, odds, lineups, stats y endpoints de partidos en vivo.",
            "integration": "Adaptador preparado si hay credencial",
            "env": "SPORTMONKS_TOKEN",
            "role": "Mejor segundo proveedor práctico: buena documentación y cobertura directa para apps de Mundial.",
        },
        {
            "name": "Sportradar Soccer API",
            "category": "Enterprise live",
            "priority": "Prioridad 3",
            "coverage": "Soccer API, timelines, cobertura por competición, feeds oficiales, odds y datos editoriales según contrato.",
            "integration": "Requiere contrato",
            "env": "SPORTRADAR_KEY",
            "role": "Proveedor premium para robustez y SLA; ideal si quieres máxima fiabilidad.",
        },
        {
            "name": "Opta / Stats Perform",
            "category": "Enterprise xG/eventos",
            "priority": "Prioridad 4",
            "coverage": "Opta live, data feeds, play-by-play, xG, player/team stats, histórico, predicciones y FIFA packages.",
            "integration": "Requiere contrato",
            "env": "OPTA_KEY",
            "role": "La mejor capa profesional si se consigue acceso; no es normalmente gratis.",
        },
        {
            "name": "StatsBomb",
            "category": "Histórico + xG",
            "priority": "Referencia metodológica",
            "coverage": "Open data histórica con eventos, lineups y 360 en competiciones seleccionadas; live/pro depende de contrato.",
            "integration": "Referencia/open data",
            "env": "STATSBOMB_TOKEN",
            "role": "Excelente para calibrar xG, eventos y backtesting; no como feed live gratuito del Mundial.",
        },
        {
            "name": "The Odds API",
            "category": "Mercado/odds",
            "priority": "Prioridad mercado",
            "coverage": "Odds por deporte, eventos, scores, h2h, totales, histórico y event odds según plan.",
            "integration": "Requiere adaptador",
            "env": "THE_ODDS_API_KEY",
            "role": "Ancla externa para detectar si el modelo se está alejando demasiado del mercado.",
        },
        {
            "name": "OddsJam / Pinnacle / Betfair Exchange",
            "category": "Mercado avanzado",
            "priority": "Referencia mercado",
            "coverage": "Movimiento de líneas, liquidez, cuotas sharp y consenso de apuestas según acceso.",
            "integration": "Requiere contrato/API",
            "env": "ODDS_PROVIDER_KEY",
            "role": "Sirve para calibrar picks cerrados y detectar steam moves de última hora.",
        },
        {
            "name": "NewsAPI",
            "category": "Noticias",
            "priority": "Opcional noticias",
            "coverage": "Búsqueda de artículos por palabra, fecha, dominio, idioma, relevancia y fuente.",
            "integration": "Adaptador preparado si hay credencial",
            "env": "NEWSAPI_KEY",
            "role": "Capa para lesiones, bajas, alineaciones probables y contexto de selección sin depender de ESPN.",
        },
        {
            "name": "FIFA Match Centre / fuentes oficiales",
            "category": "Oficial",
            "priority": "Validación oficial",
            "coverage": "Partidos, Match Centre, plantillas, sanciones, sedes, comunicados y estado oficial.",
            "integration": "Best-effort/manual/API si existe",
            "env": "FIFA_SOURCE_URLS",
            "role": "Fuente de verdad para confirmar datos críticos antes de mover probabilidades.",
        },
        {
            "name": "Federaciones y clubes",
            "category": "Oficial/noticias",
            "priority": "Validación lesiones",
            "coverage": "Convocatorias, lesionados, suspensiones, entrenamiento, ruedas de prensa y XI.",
            "integration": "RSS/web/manual",
            "env": "OFFICIAL_FEED_URLS",
            "role": "Mejor fuente para noticias que afecten disponibilidad real de jugadores.",
        },
        {
            "name": "football-data.org",
            "category": "Fixture/resultados",
            "priority": "Backup abierto",
            "coverage": "Competiciones, equipos, partidos y resultados vía API v4.",
            "integration": "Ya cableado si hay token",
            "env": "FOOTBALL_DATA_TOKEN",
            "role": "Buen backup de calendario/resultados; no reemplaza eventos live profundos.",
        },
        {
            "name": "TheSportsDB",
            "category": "Free/backup",
            "priority": "Backup gratuito",
            "coverage": "JSON API, datos, arte, eventos, highlights y livescores premium cada 2 minutos.",
            "integration": "Ya cableado como backup público ligero",
            "env": "THESPORTSDB_KEY",
            "role": "Backup económico para datos públicos, arte y highlights; menor profundidad analítica.",
        },
        {
            "name": "ScoreBat",
            "category": "Video/highlights",
            "priority": "Contexto visual",
            "coverage": "Highlights, clips de goles, streams públicos disponibles y embeds oficiales.",
            "integration": "Requiere adaptador",
            "env": "SCOREBAT_KEY",
            "role": "No mejora el modelo numérico directamente, pero ayuda a revisar jugadas y narrativa.",
        },
        {
            "name": "SofaScore / FotMob / Flashscore / 365Scores",
            "category": "Referencia no oficial",
            "priority": "Solo con licencia",
            "coverage": "Eventos, ratings, momentum y estadísticas en vivo según plataforma.",
            "integration": "No scrapear sin permiso",
            "env": "LICENSED_LIVESCORE_KEY",
            "role": "Buenos para contrastar visualmente; no conviene automatizar sin API/licencia clara.",
        },
    ]


def provider_catalog_metrics() -> dict:
    catalog = live_provider_catalog()
    return {
        "total": len(catalog),
        "wired": sum(1 for item in catalog if "Ya" in item["integration"]),
        "adapters": sum(1 for item in catalog if "adaptador" in item["integration"].lower()),
        "enterprise": sum(1 for item in catalog if "contrato" in item["integration"].lower()),
        "reference": sum(1 for item in catalog if "Referencia" in item["priority"] or "Validación" in item["priority"]),
    }


def provider_env_names(env_label: str) -> List[str]:
    if not env_label or env_label.lower() == "sin key":
        return []
    return [part.strip() for part in re.split(r"[/|,]", env_label) if part.strip()]


def provider_env_configured(env_label: str) -> bool:
    names = provider_env_names(env_label)
    if not names:
        return True
    return any(bool(os.environ.get(name)) for name in names)


def provider_runtime_diagnostics(entries: Optional[Sequence[dict]] = None) -> dict:
    fixture_entries = [entry for entry in (entries or []) if not entry.get("projection")]
    deep_sources = sorted({str(entry.get("live_feed_provider")) for entry in fixture_entries if entry.get("live_feed_provider")})
    live_sources = sorted({str(entry.get("source")) for entry in fixture_entries if entry.get("source")})
    catalog = live_provider_catalog()
    configured = [
        item["name"]
        for item in catalog
        if provider_env_names(str(item.get("env") or "")) and provider_env_configured(str(item.get("env") or ""))
    ]
    configured_wired = [
        item["name"]
        for item in catalog
        if provider_env_names(str(item.get("env") or ""))
        and provider_env_configured(str(item.get("env") or ""))
        and "ya" in str(item.get("integration", "")).lower()
    ]
    missing_wired = [
        item["name"]
        for item in catalog
        if not provider_env_configured(str(item.get("env") or "")) and "ya" in str(item.get("integration", "")).lower()
    ]
    return {
        "configured": configured,
        "configured_wired": configured_wired,
        "missing_wired": missing_wired,
        "deep_sources": deep_sources,
        "live_sources": live_sources,
        "fixture_count": len(fixture_entries),
    }


def build_provider_matrix_markdown() -> List[str]:
    metrics = provider_catalog_metrics()
    lines = [
        "### Mapa de proveedores buscados",
        f"- Proveedores catalogados: {metrics['total']} | ya cableados: {metrics['wired']} | adaptadores pendientes: {metrics['adapters']} | enterprise/contrato: {metrics['enterprise']}.",
        "- Regla: usar automáticamente fuentes sin key primero: ESPN público, Open-Meteo, GDELT, FIFA rankings y datos históricos. Las fuentes premium quedan como mejora opcional, no como requisito para que el modelo funcione.",
    ]
    for item in live_provider_catalog():
        lines.append(
            f"- {item['name']} ({item['category']}): {item['coverage']} Integracion: {item['integration']} | env: {item['env']}."
        )
    return lines


def build_provider_matrix_html(entries: Sequence[dict]) -> str:
    fixture_entries = [entry for entry in entries if not entry.get("projection")]
    live_sources = sorted({str(entry.get("source")) for entry in fixture_entries if entry.get("source")})
    deep_sources = sorted({str(entry.get("live_feed_provider")) for entry in fixture_entries if entry.get("live_feed_provider")})
    open_news_sources = sorted({str(entry.get("open_news_provider")) for entry in fixture_entries if entry.get("open_news_provider")})
    runtime = provider_runtime_diagnostics(entries)
    active_label = " + ".join(deep_sources or live_sources or ["feed base público"])
    configured_wired = runtime["configured_wired"]
    automatic_label = "ESPN + Open-Meteo + GDELT"
    if configured_wired:
        automatic_label = f"{automatic_label} + {' + '.join(str(item) for item in configured_wired)}"
    news_usage_label = " + ".join(open_news_sources) if open_news_sources else "GDELT listo; sin señal relevante en este corte"
    deep_usage_label = " + ".join(deep_sources) if deep_sources else "sin eventos tiro-a-tiro en este corte"
    metrics = provider_catalog_metrics()

    def tile(label: str, value: str, note: str) -> str:
        return (
            "<div class=\"summary-tile\">"
            f"<span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><small>{html.escape(note)}</small>"
            "</div>"
        )

    priority_order = {
        "Live profundo": 0,
        "Enterprise live": 1,
        "Enterprise xG/eventos": 1,
        "Mercado/odds": 2,
        "Mercado avanzado": 2,
        "Noticias": 3,
        "Noticias abiertas": 3,
        "Oficial": 4,
        "Oficial/noticias": 4,
        "Clima/sedes": 5,
        "Historico + xG": 5,
        "Fixture/resultados": 6,
        "Free/backup": 7,
        "Video/highlights": 8,
        "Referencia no oficial": 9,
        "Base pública": 10,
    }
    catalog = sorted(live_provider_catalog(), key=lambda item: (priority_order.get(item["category"], 99), item["name"]))
    def provider_env_status(item: dict) -> str:
        env_label = str(item.get("env") or "")
        if not provider_env_names(env_label):
            return "automático sin key"
        return "key configurada" if provider_env_configured(env_label) else "credencial opcional no configurada"

    rows = "".join(
        "<li>"
        f"<strong>{html.escape(str(item['name']))}</strong>"
        f"<span>{html.escape(str(item['category']))} | {html.escape(str(item['coverage']))}</span>"
        f"<em>{html.escape(str(item['priority']))}: {html.escape(str(item['integration']))} | {html.escape(str(item['env']))} | "
        f"{html.escape(provider_env_status(item))}</em>"
        "</li>"
        for item in catalog
    )
    best_next = [
        "Ya corre automático: fixture/resultados ESPN, clima Open-Meteo, noticias abiertas GDELT, FIFA rankings e histórico trazable desde 1950.",
        "Los marcadores Penca se recalculan en cada refresh: si cambia el resultado real, una baja, el cruce proyectado o la evidencia live, cambia el marcador recomendado.",
        "Si aparece una fuente sin key con eventos tiro-a-tiro confiables para Mundial 2026, se puede sumar; por ahora no conviene scrapear SofaScore/FotMob/Flashscore sin licencia.",
    ]
    if deep_sources:
        best_next.append("Evento profundo activo en esta corrida: el modelo ya está usando tiros/eventos del proveedor live.")
    else:
        best_next.append("Sin credencial premium no hay feed universal de tiros minuto a minuto; usamos ESPN+GDELT+clima+histórico y live profundo cuando el feed público lo expone.")
    next_rows = "".join(
        "<li>"
        f"<strong>{html.escape(item)}</strong>"
        "<span>Esto aumenta robustez; no garantiza acertar más si el proveedor no cubre Mundial 2026 o no trae datos live profundos.</span>"
        "</li>"
        for item in best_next
    )
    return (
        "<section class=\"panel provider-panel\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Mapa de proveedores</p>"
        "<h2>No depender solo de ESPN</h2>"
        "<p class=\"lede-tight\">El pipeline usa primero lo que sí se puede extraer automáticamente sin que tengas que registrar cuentas: ESPN público, Open-Meteo, GDELT, FIFA rankings e histórico. Las fuentes premium aparecen separadas como opcionales, no como una tarea para ti.</p>"
        "</div></div>"
        "<div class=\"confidence-tiles\">"
        f"{tile('Fuente activa visible', active_label, 'Lo que está entrando en este corte publicado.')}"
        f"{tile('Automático sin cuentas', automatic_label, 'No requiere que pegues keys ni busques contratos.')}"
        f"{tile('Noticias abiertas usadas', news_usage_label, 'GDELT puede mover lesiones, sanciones y contexto si detecta señal fuerte.')}"
        f"{tile('Eventos live profundos', deep_usage_label, 'Tiros minuto a minuto solo si existe feed público/premium válido.')}"
        f"{tile('Proveedores catalogados', str(int(metrics['total'])), 'Live, odds, noticias, histórico, oficial y video.')}"
        "</div>"
        "<div class=\"certainty-grid provider-grid\">"
        "<article><h3>Proveedores posibles</h3><ul>"
        f"{rows}"
        "</ul></article>"
        "<article><h3>Siguiente paso recomendado</h3><ul>"
        f"{next_rows}"
        "</ul></article>"
        "</div>"
        "</section>"
    )


def provider_stack_summary(entries: Optional[Sequence[dict]] = None) -> dict:
    runtime = provider_runtime_diagnostics(entries)
    live_sources = runtime["live_sources"]
    deep_sources = runtime["deep_sources"]
    configured_wired = runtime["configured_wired"]
    active = " + ".join(deep_sources or live_sources or ["espn_scoreboard"])
    prepared = [
        "ESPN público",
        "Open-Meteo",
        "GDELT",
        "API-Football",
        "Sportmonks",
        "Sportradar",
        "Opta",
        "The Odds API",
        "NewsAPI",
        "GDELT",
    ]
    return {
        "active": active,
        "configured": configured_wired,
        "prepared": prepared,
        "deep_active": bool(deep_sources),
        "fixture_count": runtime["fixture_count"],
    }


def build_agentic_learning_markdown(entries: Sequence[dict], bracket_payload: dict, backtest: dict) -> List[str]:
    fixture_entries = [entry for entry in entries if not entry.get("projection")]
    final_count = sum(1 for entry in fixture_entries if fixture_is_final(entry))
    live_count = sum(1 for entry in fixture_entries if fixture_is_live(entry))
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    lines = [
        "### Agentes de aprendizaje",
        "- Lectura: esto no es un chatbot generando opiniones. Es un pipeline de agentes que ingiere datos, los transforma en señales, predice, calibra, decide y audita.",
        f"- Monte Carlo publicado en este corte: {iterations:,} simulaciones. El snapshot profundo de referencia usa 100.000; 15.000 queda como guardrail mínimo horario.".replace(",", "."),
        f"- Aprendizaje real disponible hoy: {final_count} partidos finalizados y {live_count} en vivo dentro del fixture cargado.",
        f"- Backtesting/calibración: {int(backtest.get('completed_matches', 0) or 0)} partidos cerrados reconstruidos.",
        "- Noticias multi-fuente: no depende solo de ESPN; ESPN puede ser fuente base, pero el modelo acepta fuentes oficiales, prensa internacional, mercado y proveedor live profundo.",
    ]
    for item in agentic_learning_items():
        lines.append(f"- {item['agent']}: {item['job']} {item['learns']}")
    lines.extend(["", *build_provider_matrix_markdown()])
    return lines


def build_agentic_learning_html(entries: Sequence[dict], bracket_payload: dict, backtest: dict) -> str:
    fixture_entries = [entry for entry in entries if not entry.get("projection")]
    live_count = sum(1 for entry in fixture_entries if fixture_is_live(entry))
    final_count = sum(1 for entry in fixture_entries if fixture_is_final(entry))
    projected_count = sum(1 for entry in entries if entry.get("projection"))
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    iterations_label = f"{iterations:,}".replace(",", ".") if iterations else "sin dato"
    completed = int(backtest.get("completed_matches", 0) or 0)
    live_sources = sorted({str(entry.get("source")) for entry in fixture_entries if entry.get("source")})
    deep_sources = sorted({str(entry.get("live_feed_provider")) for entry in fixture_entries if entry.get("live_feed_provider")})
    source_label = " + ".join(deep_sources or live_sources or ["feed base público"])
    prepared_stack = "API-Football + Sportmonks + Sportradar + Opta + Odds + News"

    def tile(label: str, value: str, note: str) -> str:
        return (
            "<div class=\"summary-tile\">"
            f"<span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><small>{html.escape(note)}</small>"
            "</div>"
        )

    agent_rows = "".join(
        "<li>"
        f"<strong>{html.escape(str(item['agent']))}</strong>"
        f"<span>{html.escape(str(item['job']))}</span>"
        f"<em>{html.escape(str(item['learns']))}</em>"
        "</li>"
        for item in agentic_learning_items()
    )
    source_rows = "".join(
        "<li>"
        f"<strong>{html.escape(str(item['source']))}</strong>"
        f"<span>{html.escape(str(item['use']))}</span>"
        "</li>"
        for item in sports_news_source_policy_items()
    )
    return (
        "<section class=\"panel agentic-panel\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">IA operacional</p>"
        "<h2>Agentes de aprendizaje, no solo texto generativo</h2>"
        "<p class=\"lede-tight\">El modelo aprende de sí mismo en sentido operativo: cada resultado real, baja confirmada, cambio de mercado o evento live se convierte en estado, calibración y nuevas probabilidades. No inventa noticias; las exige como fuente trazable.</p>"
        "</div></div>"
        "<div class=\"confidence-tiles\">"
        f"{tile('Monte Carlo publicado', iterations_label + ' simulaciones', 'Esta es la corrida visible en el artefacto actual; el snapshot principal profundo es 100.000.')}"
        f"{tile('Eficiencia operativa', 'live ligero cada 5 min', '15.000 es solo el mínimo técnico del carril horario; no la meta final del modelo.')}"
        f"{tile('Datos ya incorporados', f'{final_count} final / {live_count} live', f'Además {projected_count} cruces de llave recalculables.')}"
        f"{tile('Noticias multi-fuente', 'No solo ESPN', f'Fuente activa visible: {source_label}; stack preparado: {prepared_stack}.')}"
        "</div>"
        "<div class=\"certainty-grid agentic-grid\">"
        "<article><h3>Cómo aprende el sistema</h3><ul>"
        f"{agent_rows}"
        "</ul></article>"
        "<article><h3>Fuentes deportivas aceptadas</h3><ul>"
        f"{source_rows}"
        "</ul></article>"
        "<article><h3>Qué tan eficiente es</h3><ul>"
        f"<li><strong>{html.escape(iterations_label)} simulaciones publicadas</strong><span>La llave vigente se calcula con rutas completas de torneo, no solo favoritos sueltos.</span><em>Cuando el artefacto viene del workflow 100k, el snapshot profundo usa 100.000 simulaciones.</em></li>"
        f"<li><strong>Refresh live cada 5 minutos</strong><span>GitHub Actions reconstruye el tablero ligero y recalcula in-play cuando el feed trae cambios.</span><em>El carril horario puede usar el guardrail 15.000; el corte de alta estabilidad se actualiza con 100.000 cada 8h/manual/push.</em></li>"
        f"<li><strong>Calibración acumulada</strong><span>{completed} partidos cerrados disponibles para backtesting en este corte.</span><em>Cuando crece la muestra, el agente de calibración ajusta confianza y coberturas.</em></li>"
        "</ul></article>"
        "</div>"
        "</section>"
    )


def prediction_operating_system_payload() -> dict:
    path = Path(__file__).with_name("data") / "prediction_operating_system_2026.json"
    try:
        return json.loads(path.read_text())
    except Exception:
        return {
            "schema_version": "fallback",
            "core_rule": "Actualizar datos; no cambiar metodología durante el torneo salvo bug real.",
            "final_freeze": {"status": "no disponible", "target_file": "modelo_quiniela_2026_final_pre_torneo.py"},
            "runtime_modes": {},
            "penca_position_strategy": {},
            "daily_resimulation": {"minimum_iterations": 15000, "recommended_deep_iterations": 50000},
            "alerts": [],
            "post_round_review": [],
        }


def build_prediction_operating_system_markdown(
    entries: Sequence[dict],
    bracket_payload: dict,
    backtest: dict,
) -> List[str]:
    payload = prediction_operating_system_payload()
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    completed_matches = int(backtest.get("completed_matches", 0) or 0)
    final_freeze = payload.get("final_freeze", {})
    daily = payload.get("daily_resimulation", {})
    position = payload.get("penca_position_strategy", {})
    alerts = payload.get("alerts", [])
    review = payload.get("post_round_review", [])
    target_file = str(final_freeze.get("target_file", "modelo_quiniela_2026_final_pre_torneo.py"))
    status = str(final_freeze.get("status", "pendiente"))

    lines = [
        "- Regla central: durante el Mundial se actualizan datos, estado dinámico, lesiones, alineaciones, mercado y feed live; no se cambian pesos ni funciones salvo bug real documentado.",
        f"- Congelación final pre-torneo: {target_file} está {status}. No debe crearse como final hasta completar backtesting, calibración y ablations.",
        f"- Re-simulación diaria: mínimo {int(daily.get('minimum_iterations', 15000)):,} simulaciones; reporte profundo recomendado {int(daily.get('recommended_deep_iterations', 50000)):,} si el tiempo de cómputo lo permite.".replace(",", "."),
        f"- Estado actual: llave publicada con {iterations:,} simulaciones y {completed_matches} partidos cerrados 2026 para calibración real.".replace(",", "."),
        "- Estrategia según posición en Penca:",
    ]
    for key, value in position.items():
        lines.append(f"  - {key}: {value}")
    if alerts:
        lines.append("- Alertas que deben disparar revisión:")
        for alert in alerts[:7]:
            lines.append(f"  - {alert}")
    if review:
        lines.append("- Revisión post-jornada:")
        for item in review[:7]:
            lines.append(f"  - {item}")
    return lines


def build_prediction_operating_system_html(
    entries: Sequence[dict],
    bracket_payload: dict,
    backtest: dict,
) -> str:
    payload = prediction_operating_system_payload()
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    completed_matches = int(backtest.get("completed_matches", 0) or 0)
    final_freeze = payload.get("final_freeze", {})
    daily = payload.get("daily_resimulation", {})
    runtime_modes = payload.get("runtime_modes", {})
    position = payload.get("penca_position_strategy", {})
    alerts = payload.get("alerts", [])
    review = payload.get("post_round_review", [])
    state_updates = payload.get("dynamic_state_updates", [])
    freeze_status = str(final_freeze.get("status", "pendiente"))
    target_file = str(final_freeze.get("target_file", "modelo_quiniela_2026_final_pre_torneo.py"))
    min_iterations = int(daily.get("minimum_iterations", 15000) or 15000)
    deep_iterations = int(daily.get("recommended_deep_iterations", 50000) or 50000)

    if "pendiente" in freeze_status:
        freeze_reading = "No congelado todavía"
        freeze_note = "Correcto: falta demostrar mejora con backtesting, calibración, ablations y benchmarks antes de crear el final pre-torneo."
        freeze_tone = "warn"
    else:
        freeze_reading = "Congelado"
        freeze_note = "Desde esta versión solo se actualizan datos y estado; la metodología queda cerrada salvo bug real."
        freeze_tone = "ok"

    def card(title: str, value: str, detail: str) -> str:
        return (
            "<article class=\"method-quality-card ops-card\">"
            f"<h3>{html.escape(title)}</h3>"
            f"<strong>{html.escape(value)}</strong>"
            f"<p>{html.escape(detail)}</p>"
            "</article>"
        )

    def list_rows(items: Sequence[str], limit: int = 7) -> str:
        rows = []
        for item in list(items)[:limit]:
            rows.append(f"<li>{html.escape(str(item))}</li>")
        return "".join(rows) or "<li>Sin reglas cargadas.</li>"

    mode_rows = []
    for mode, meta in runtime_modes.items():
        outputs = ", ".join(str(item) for item in meta.get("outputs", [])[:5])
        mode_rows.append(
            "<li>"
            f"<strong>{html.escape(str(mode).replace('_', '-'))}</strong>"
            f"<span>{html.escape(str(meta.get('objective', '')))}</span>"
            f"<em>{html.escape(outputs)}</em>"
            "</li>"
        )
    position_rows = [
        "<li>"
        f"<strong>{html.escape(str(key))}</strong>"
        f"<span>{html.escape(str(value))}</span>"
        "</li>"
        for key, value in position.items()
    ]

    return (
        "<section class=\"panel operating-system-panel\" id=\"sistema-operativo\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Sistema operativo de predicción</p>"
        "<h2>Cómo usar el modelo durante el Mundial sin sobreajustarlo.</h2>"
        "<p class=\"lede-tight\">La ventaja no sale de cambiar el modelo después de cada sorpresa. Sale de congelar metodología, actualizar datos trazables, re-simular, escoger el marcador Penca correcto y auditar cada jornada.</p>"
        "</div></div>"
        "<div class=\"confidence-tiles operating-tiles\">"
        f"{card('Congelar modelo final pre-torneo', freeze_reading, f'{target_file}: {freeze_note}')}"
        f"{card('Re-simulación diaria', f'{min_iterations:,}+ / ideal {deep_iterations:,}'.replace(',', '.'), f'El corte actual publica {iterations:,} simulaciones; compara movimientos contra el snapshot anterior.'.replace(',', '.'))}"
        f"{card('Calibración viva', f'{completed_matches} finales 2026', 'Brier/log-loss empiezan apenas haya resultados; antes de eso no se inventa track record.')}"
        f"{card('No cambiar pesos durante el Mundial', 'Regla dura', str(payload.get('core_rule', 'Actualizar datos, no tocar metodología.')))}"
        "</div>"
        "<div class=\"certainty-grid operating-grid\">"
        "<article><h3>Modos del sistema</h3><ul class=\"ops-list\">"
        f"{''.join(mode_rows) or '<li>Sin modos cargados.</li>'}"
        "</ul></article>"
        "<article><h3>Estrategia según posición en Penca</h3><ul class=\"ops-list\">"
        f"{''.join(position_rows) or '<li>Sin estrategia cargada.</li>'}"
        "</ul></article>"
        "<article><h3>Alertas que cambian decisiones</h3><ul class=\"ops-list\">"
        f"{list_rows(alerts)}"
        "</ul></article>"
        "<article><h3>Actualizar estado dinámico</h3><ul class=\"ops-list compact\">"
        f"{list_rows(state_updates, limit=12)}"
        "</ul></article>"
        "<article><h3>Revisión post-jornada</h3><ul class=\"ops-list\">"
        f"{list_rows(review)}"
        "</ul></article>"
        "<article><h3>Salida que debes usar</h3><p>Para cada partido: marcador probable del modelo, marcador recomendado para Penca, safe score, óptimo, diferencial, riesgo, cobertura y consenso. Si difieren, Penca manda para cargar la app.</p></article>"
        "</div>"
        "</section>"
    )


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
        "## Resumen rápido del torneo",
        "",
    ]
    lines.extend(build_global_confidence_markdown(entries))
    lines.extend(["", "## Hoja de máxima firmeza para quiniela", ""])
    lines.extend(build_max_certainty_markdown(entries))
    lines.extend(["", "## Estrategia para ganar la quiniela", ""])
    lines.extend(build_quiniela_strategy_markdown(entries))
    lines.extend(["", "## Marcadores para cargar en Penca", ""])
    lines.extend(build_full_scorecard_markdown(entries))
    lines.extend(["", "## Calibración avanzada y límites de confianza", ""])
    lines.extend(build_calibration_depth_markdown(entries, backtest))
    lines.extend(["", "## Auditoría metodológica profunda", ""])
    lines.extend(build_methodology_governance_markdown(entries, bracket_payload, backtest))
    lines.extend(["", "## Sistema operativo de predicción", ""])
    lines.extend(build_prediction_operating_system_markdown(entries, bracket_payload, backtest))
    lines.extend(["", "## Predicción potenciada", ""])
    lines.extend(build_prediction_power_markdown(entries))
    lines.extend(["", "## Agentes de aprendizaje y fuentes", ""])
    lines.extend(build_agentic_learning_markdown(entries, bracket_payload, backtest))
    lines.extend(["", "## Ajustes contra consenso externo", ""])
    lines.extend(build_consensus_guardrail_markdown(bracket_payload, entries))
    lines.extend(["", "## Comparación contra modelos externos publicados", ""])
    lines.extend(build_external_forecast_benchmarks_markdown(bracket_payload, entries))
    lines.extend(["", "## Tapados con ruta realista", ""])
    lines.extend(build_dark_horses_markdown(bracket_payload, entries))
    lines.extend(["", "## Qué cambió desde la última actualización", ""])
    lines.extend(
        build_recent_changes_markdown(
            entries,
            previous_entries or [],
            bracket_payload,
            previous_bracket_payload or {},
            previous_updated_at,
        )
    )
    lines.extend(["", "## Cómo viene acertando el modelo", ""])
    lines.extend(build_backtesting_markdown(backtest))
    lines.extend([
        "",
        "## Llave actual",
        "",
    ])
    if bracket_text.strip():
        lines.append(bracket_text.strip())
    else:
        lines.append("_No hay llave generada todavía._")
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
            lines.append(f"- Árbitro: {entry['referee']}")
        if entry.get("market_summary"):
            provider = entry.get("market_provider") or "mercado"
            lines.append(f"- Odds {provider}: {entry['market_summary']}")
        if entry.get("market_prob_a") is not None:
            lines.append(
                f"- Referencia de cuotas (victoria/empate/derrota): {prediction.team_a} {format_pct(float(entry['market_prob_a']))} | "
                f"empate {format_pct(float(entry.get('market_prob_draw', 0.0)))} | "
                f"{prediction.team_b} {format_pct(float(entry.get('market_prob_b', 0.0)))}"
            )
        if entry.get("market_total_line") is not None:
            provider = entry.get("goal_consensus_source") or "consenso externo"
            lines.append(f"- Referencia seria de goles ({provider}): total {float(entry['market_total_line']):.2f}")
        if entry.get("lineup_status_a") or entry.get("lineup_status_b"):
            lines.append(
                f"- Alineaciones: {prediction.team_a} {entry.get('lineup_status_a', 'sin confirmar')} | "
                f"{prediction.team_b} {entry.get('lineup_status_b', 'sin confirmar')}"
            )
        if entry.get("lineup_change_count_a") or entry.get("lineup_change_count_b"):
            lines.append(
                f"- Cambios de alineación: {prediction.team_a} {entry.get('lineup_change_count_a', 0)} | "
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
            lines.append(f"- Proyección automática: {entry.get('projection_note', '')}")
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
                result_line += " | con prórroga"
            lines.append(result_line)
        elif entry.get("live_score_a") is not None and entry.get("live_score_b") is not None:
            lines.append(
                f"- Marcador en vivo: {prediction.team_a} {entry['live_score_a']} - {entry['live_score_b']} {prediction.team_b}"
            )
        else:
            pass
        lines.append(f"- {projected_score_label(prediction)}: {projected_score_value(prediction)}")
        guidance = prediction.score_guidance or {}
        top_penca = penca_ovacion_top_score(prediction)
        lines.append(
            f"- Marcador para cargar en Penca: {top_penca['score']} | "
            f"{float(top_penca['expected_points']):.2f} pts esp. | exacto {format_pct(float(top_penca['exact_prob']))} | "
            f"diferencia {format_pct(float(top_penca['difference_prob']))}"
        )
        if guidance:
            lines.append(
                f"- Precisión de marcador: {guidance.get('precision_label')} | exacto más probable {guidance.get('top_exact_score')} "
                f"{format_pct(float(guidance.get('top_exact_prob', 0.0)))} | top-5 cubre {format_pct(float(guidance.get('top5_coverage', 0.0)))}"
            )
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
                f"- Quién tiene más probabilidad de avanzar: {prediction.team_a} {format_pct(prediction.advance_a)} | {prediction.team_b} {format_pct(prediction.advance_b)}"
            )
            lines.append(
                f"- Si empatan tras 90': gana en prórroga {prediction.team_a} {format_pct(detail.get('et_win_a', 0.0))} | "
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
                    f"- Marcador más probable de la tanda: {projected_shootout}"
                )
                lines.append(
                    f"- Marcador medio esperado en la tanda: {prediction.team_a} {shootout.get('avg_score_a', 0.0):.2f} | "
                    f"{prediction.team_b} {shootout.get('avg_score_b', 0.0):.2f}"
                )
                lines.append(
                    "- Marcadores de tanda más probables: "
                    + ", ".join(
                        f"{score} {format_pct(prob)}" for score, prob in shootout.get("top_scores", [])
                    )
                )
        score_line = ", ".join(f"{score} {format_pct(prob)}" for score, prob in prediction.exact_scores)
        lines.append(f"- Marcadores más probables: {score_line}")
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
    expected_total_goals = float(depth.get("expected_total_goals", prediction.expected_goals_a + prediction.expected_goals_b))
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
        f"- Escenario de goles: ambos marcan {format_pct(both_score)} | más de 2.5 goles {format_pct(over_2_5)}"
    )
    if depth.get("goal_consensus_line") is not None:
        lines.append(
            f"- Calibración de goles vs consenso externo: modelo {expected_total_goals:.2f} goles totales | consenso {float(depth['goal_consensus_line']):.2f} | brecha {float(depth.get('goal_consensus_gap', 0.0)):+.2f} ({depth.get('goal_consensus_status')})."
        )
    else:
        lines.append(
            f"- Goles totales esperados por el modelo: {expected_total_goals:.2f}. Sin línea externa de goles cargada para ese partido."
        )
    lines.append(
        f"- Probabilidad de que no reciba goles: {prediction.team_a} {format_pct(clean_sheet_a)} | {prediction.team_b} {format_pct(clean_sheet_b)}"
    )
    lines.append(
        f"- Cuánta probabilidad cubren los 3 marcadores más probables: {format_pct(top3_coverage)} | ventaja final más probable {modal_margin:+d} ({format_pct(modal_margin_prob)})"
    )
    if model_agreement is not None:
        lines.append(f"- Qué tanto coinciden los modelos entre sí: {format_pct(float(model_agreement))}")
    if market_gap is not None:
        lines.append(f"- Diferencia frente a las cuotas de mercado: {format_pct(float(market_gap))}")
    stack_names = [name for name in depth.get("model_stack_names", []) if name]
    if stack_names:
        lines.append(f"- Stack estadístico usado: {' + '.join(stack_names)}")
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
    goal_consensus_html = ""
    if depth.get("goal_consensus_line") is not None:
        goal_consensus_html = (
            f"<div><span>Consenso externo de goles</span><strong>{float(depth['goal_consensus_line']):.2f}</strong></div>"
            f"<div><span>Brecha modelo-consenso</span><strong>{float(depth.get('goal_consensus_gap', 0.0)):+.2f}</strong></div>"
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
            "<p class=\"meta\"><strong>Stack estadístico:</strong> "
            + html.escape(" + ".join(stack_names))
            + "</p>"
        )
    return (
        "<div class=\"depth-block\">"
        "<h4>Profundidad estadística</h4>"
        f"<p class=\"meta\"><strong>{html.escape(confidence_tier(confidence))}</strong> | pick actual: {html.escape(pick_label)} {format_pct(pick_prob)}</p>"
        "<div class=\"depth-grid\">"
        f"<div><span>Confianza del pronóstico</span><strong>{format_pct(confidence)}</strong></div>"
        f"<div><span>Goles totales esperados</span><strong>{float(depth.get('expected_total_goals', prediction.expected_goals_a + prediction.expected_goals_b)):.2f}</strong></div>"
        f"<div><span>Ambos marcan</span><strong>{format_pct(float(depth.get('both_teams_score', 0.0)))}</strong></div>"
        f"<div><span>Más de 1.5 goles</span><strong>{format_pct(float(depth.get('over_1_5', 0.0)))}</strong></div>"
        f"<div><span>Más de 2.5 goles</span><strong>{format_pct(float(depth.get('over_2_5', 0.0)))}</strong></div>"
        f"<div><span>Probabilidad cubierta por los 3 marcadores más probables</span><strong>{format_pct(float(depth.get('top3_coverage', 0.0)))}</strong></div>"
        f"<div><span>Probabilidad cubierta por los 5 marcadores más probables</span><strong>{format_pct(float(depth.get('top5_coverage', 0.0)))}</strong></div>"
        f"<div><span>Prob. de que {html.escape(prediction.team_a)} no reciba goles</span><strong>{format_pct(float(depth.get('clean_sheet_a', 0.0)))}</strong></div>"
        f"<div><span>Prob. de que {html.escape(prediction.team_b)} no reciba goles</span><strong>{format_pct(float(depth.get('clean_sheet_b', 0.0)))}</strong></div>"
        f"<div><span>Ventaja final más probable</span><strong>{int(depth.get('modal_margin', 0)):+d}</strong></div>"
        f"<div><span>Probabilidad de esa ventaja</span><strong>{format_pct(float(depth.get('modal_margin_prob', 0.0)))}</strong></div>"
        f"{agreement_html}"
        f"{market_html}"
        f"{goal_consensus_html}"
        "</div>"
        f"{stack_html}"
        f"{drivers_html}"
        "</div>"
    )


def goal_forecast_html(entry: dict, prediction: MatchPrediction) -> str:
    depth = prediction.statistical_depth or {}
    guidance = prediction.score_guidance or {}
    expected_total = float(depth.get("expected_total_goals", prediction.expected_goals_a + prediction.expected_goals_b))
    consensus_line = depth.get("goal_consensus_line")
    source = entry.get("goal_consensus_source") or "consenso externo"
    def goal_options_summary(options: object) -> str:
        if not isinstance(options, list) or not options:
            return "sin muestra"
        return ", ".join(
            f"{int(item.get('goals', 0))} ({format_pct(float(item.get('prob', 0.0)))})"
            for item in options[:3]
            if isinstance(item, dict)
        )

    if consensus_line is not None:
        consensus_note = (
            f"Calibrado contra {html.escape(str(source))}: linea {float(consensus_line):.2f}, "
            f"brecha final {float(depth.get('goal_consensus_gap', 0.0)):+.2f} ({html.escape(str(depth.get('goal_consensus_status', 'alineado')))})."
        )
    else:
        consensus_note = "Sin línea externa de goles cargada; usa el modelo propio y se ajustará automáticamente si el feed trae mercado/consenso de goles."
    shape_label = str(guidance.get("score_shape_label", "sin ajuste histórico específico"))
    shape_before = guidance.get("score_shape_before")
    shape_after = guidance.get("score_shape_after")
    historical_data_note = guidance.get("historical_data_note")
    scoreline_family_note = guidance.get("scoreline_family_note")
    if shape_before and shape_after and shape_before != shape_after:
        shape_note = (
            f"El ajuste histórico de asimetría movió el marcador líder de {shape_before} a {shape_after}: "
            f"se revisan equipos que históricamente convierten o conceden con marcadores menos centrados."
        )
    else:
        shape_note = (
            "El ajuste histórico de asimetría no cambió el marcador líder; el exacto recomendado sigue siendo "
            "el que mejor combina probabilidad y puntos esperados."
        )
    historical_note_html = (
        f"<p class=\"meta\">Datos históricos usados para el perfil de marcador: {html.escape(str(historical_data_note))}.</p>"
        if historical_data_note
        else ""
    )
    family_note_html = (
        f"<p class=\"meta\">{html.escape(str(scoreline_family_note))}</p>"
        if scoreline_family_note
        else ""
    )
    model_score_label = prediction_score_label(prediction, projected_score_value(prediction))
    penca_score_label = prediction_score_label(
        prediction,
        guidance.get("recommended_score", penca_ovacion_top_score(prediction)["score"]),
    )
    top_exact_score_label = prediction_score_label(
        prediction,
        guidance.get("top_exact_score", projected_score_value(prediction)),
    )
    return (
        "<div class=\"goal-forecast-block\">"
        "<h4>Pronóstico de goles</h4>"
        "<div class=\"goal-forecast-grid\">"
        f"<div><span>Marcador más probable del modelo</span><strong>{html.escape(model_score_label)}</strong></div>"
        f"<div><span>Marcador para cargar en Penca Ovación</span><strong>{html.escape(penca_score_label)}</strong></div>"
        f"<div><span>Exacto puro más probable</span><strong>{html.escape(top_exact_score_label)}</strong></div>"
        f"<div><span>Precisión del marcador</span><strong>{html.escape(str(guidance.get('precision_label', 'sin clasificar')))}</strong></div>"
        f"<div><span>Goles más probables de {html.escape(prediction.team_a)}</span><strong>{html.escape(goal_options_summary(guidance.get('goal_options_a')))}</strong></div>"
        f"<div><span>Goles más probables de {html.escape(prediction.team_b)}</span><strong>{html.escape(goal_options_summary(guidance.get('goal_options_b')))}</strong></div>"
        f"<div><span>Promedio total estimado</span><strong>{expected_total:.2f}</strong></div>"
        f"<div><span>Más de 1.5 goles</span><strong>{format_pct(float(depth.get('over_1_5', 0.0)))}</strong></div>"
        f"<div><span>Más de 2.5 goles</span><strong>{format_pct(float(depth.get('over_2_5', 0.0)))}</strong></div>"
        f"<div><span>Ambos equipos anotan</span><strong>{format_pct(float(depth.get('both_teams_score', 0.0)))}</strong></div>"
        f"<div><span>Cobertura top-5 marcadores</span><strong>{format_pct(float(guidance.get('top5_coverage', depth.get('top5_coverage', 0.0))))}</strong></div>"
        f"<div><span>Estado vs consenso</span><strong>{html.escape(str(depth.get('goal_consensus_status', 'sin consenso externo')))}</strong></div>"
        f"<div><span>Ajuste histórico del marcador</span><strong>{html.escape(shape_label)}</strong></div>"
        f"<div><span>Firmeza para puntuar en Penca</span><strong>{html.escape(str(guidance.get('penca_certainty_label', 'sin clasificar')))} | {format_pct(float(guidance.get('penca_certainty_index', 0.0)))}</strong></div>"
        "</div>"
        f"<p class=\"meta\">{consensus_note}</p>"
        f"<p class=\"meta\">{html.escape(str(guidance.get('recommendation_note', 'El marcador recomendado se calcula con la distribución completa de marcadores.')))}</p>"
        f"<p class=\"meta\">{html.escape(shape_note)}</p>"
        f"{historical_note_html}"
        f"{family_note_html}"
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
        weight_key = (
            "primary"
            if name_key == "primary_name"
            else "contrast"
            if name_key == "contrast_name"
            else "low_score"
            if name_key == "low_score_name"
            else "overdispersed"
            if name_key == "overdispersed_name"
            else "ml"
            if name_key == "ml_name"
            else "bayesian"
            if name_key == "bayesian_name"
            else None
        )
        weight_label = ""
        if weight_key and stack.get("weights", {}).get(weight_key) is not None:
            weight_label = f" | peso actual {format_pct(float(stack['weights'][weight_key]))}"
        return (
            f"- {name}: victoria {prediction.team_a} {format_pct(float(probs.get('a', 0.0)))} | "
            f"empate {format_pct(float(probs.get('draw', 0.0)))} | "
            f"victoria {prediction.team_b} {format_pct(float(probs.get('b', 0.0)))} | "
            f"marcador más probable {top_score} ({format_pct(float(top_score_prob))}){weight_label}"
        )

    lines = ["- Comparativa entre modelos:"]
    lines.append(row("primary_name", "primary_probs", "primary_top_score"))
    lines.append(row("contrast_name", "contrast_probs", "contrast_top_score"))
    lines.append(row("low_score_name", "low_score_probs", "low_score_top_score"))
    if "overdispersed_name" in stack:
        lines.append(row("overdispersed_name", "overdispersed_probs", "overdispersed_top_score"))
    if "ml_name" in stack:
        lines.append(row("ml_name", "ml_probs", "ml_top_score"))
    if "bayesian_name" in stack:
        lines.append(row("bayesian_name", "bayesian_probs", "bayesian_top_score"))
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
        weight_key = (
            "primary"
            if name_key == "primary_name"
            else "contrast"
            if name_key == "contrast_name"
            else "low_score"
            if name_key == "low_score_name"
            else "overdispersed"
            if name_key == "overdispersed_name"
            else "ml"
            if name_key == "ml_name"
            else "bayesian"
            if name_key == "bayesian_name"
            else None
        )
        weight_html = ""
        if weight_key and stack.get("weights", {}).get(weight_key) is not None:
            weight_html = f"<p><strong>Peso actual:</strong> {format_pct(float(stack['weights'][weight_key]))}</p>"
        return (
            f"<article class=\"model-card {tone}\">"
            f"<h5>{html.escape(name)}</h5>"
            f"<p>Victoria {html.escape(prediction.team_a)} {format_pct(float(probs.get('a', 0.0)))}</p>"
            f"<p>Empate {format_pct(float(probs.get('draw', 0.0)))}</p>"
            f"<p>Victoria {html.escape(prediction.team_b)} {format_pct(float(probs.get('b', 0.0)))}</p>"
            f"<p><strong>Marcador más probable:</strong> {html.escape(str(top_score))} ({format_pct(float(top_score_prob))})</p>"
            f"{weight_html}"
            "</article>"
        )

    inner = (
        "<div class=\"reason-block model-compare-block\">"
        "<p class=\"meta\">Aquí se ven por separado el modelo principal, el contraste, el ajuste de baja anotación, la overdispersión calibrada, el calibrador ML ligero y el predictivo bayesiano dinámico. El ensamble final repondera esos modelos según consenso, dispersión, evidencia del XI y cercanía al mercado cuando hay cuotas confiables.</p>"
        "<div class=\"model-compare-grid\">"
        f"{card('primary_name', 'primary_probs', 'primary_top_score', 'primary')}"
        f"{card('contrast_name', 'contrast_probs', 'contrast_top_score', 'contrast')}"
        f"{card('low_score_name', 'low_score_probs', 'low_score_top_score', 'low-score')}"
        f"{card('overdispersed_name', 'overdispersed_probs', 'overdispersed_top_score', 'overdispersed') if 'overdispersed_name' in stack else ''}"
        f"{card('ml_name', 'ml_probs', 'ml_top_score', 'ml') if 'ml_name' in stack else ''}"
        f"{card('bayesian_name', 'bayesian_probs', 'bayesian_top_score', 'bayesian') if 'bayesian_name' in stack else ''}"
        f"{card('final_name', 'ensemble_probs', 'ensemble_top_score', 'ensemble')}"
        "</div>"
        "</div>"
    )
    return (
        "<details class=\"inline-collapse model-compare-collapse\">"
        "<summary>Qué dice cada modelo</summary>"
        f"<div class=\"inline-collapse-body\">{inner}</div>"
        "</details>"
    )


def penca_ovacion_score_html(prediction: MatchPrediction) -> str:
    if not prediction.penca_scores:
        return ""
    top = penca_ovacion_top_score(prediction)
    guidance = prediction.score_guidance or {}
    top_score_label = prediction_score_label(prediction, top["score"])
    top_exact_label = prediction_score_label(
        prediction,
        guidance.get("top_exact_score", prediction.exact_scores[0][0] if prediction.exact_scores else top["score"]),
    )
    def goal_options_list(options: object, team_name: str) -> str:
        if not isinstance(options, list) or not options:
            return ""
        rows = "".join(
            "<li>"
            f"<strong>{int(item.get('goals', 0))} {'gol' if int(item.get('goals', 0)) == 1 else 'goles'}</strong>"
            f"<span>{format_pct(float(item.get('prob', 0.0)))} para {html.escape(team_name)}</span>"
            "</li>"
            for item in options[:4]
            if isinstance(item, dict)
        )
        return f"<div class=\"scores score-marginals\"><h4>{html.escape(team_name)}: goles más probables</h4><ul>{rows}</ul></div>"

    def asymmetric_options_list(options: object) -> str:
        if not isinstance(options, list) or not options:
            return ""
        rows = "".join(
            "<li>"
            f"<strong>{html.escape(prediction_score_label(prediction, item['score']))}</strong>"
            f"<span>{float(item['expected_points']):.2f} pts esp. | exacto {format_pct(float(item['exact_prob']))} | "
            f"diferencia {format_pct(float(item['difference_prob']))}</span>"
            "</li>"
            for item in options[:4]
            if isinstance(item, dict)
        )
        return (
            "<div class=\"scores asymmetric-scores\">"
            "<h4>Marcadores amplios o menos centrados a vigilar</h4>"
            f"<ul>{rows}</ul>"
            "</div>"
        )

    def portfolio_tile(label: str, item: object, note: str) -> str:
        if not isinstance(item, dict):
            return ""
        score_label = prediction_score_label(prediction, item.get("score", ""))
        return (
            "<div>"
            f"<span>{html.escape(label)}</span>"
            f"<strong>{html.escape(score_label)}</strong>"
            f"<small>{float(item.get('expected_points', 0.0)):.2f} pts esp. | exacto {format_pct(float(item.get('exact_prob', 0.0)))} | "
            f"diferencia {format_pct(float(item.get('difference_prob', 0.0)))}. {html.escape(note)}</small>"
            "</div>"
        )

    def exact_coverage_tile(label: str, count_key: str, coverage_key: str, scores_key: str) -> str:
        count = int(guidance.get(count_key, 0) or 0)
        coverage = float(guidance.get(coverage_key, 0.0) or 0.0)
        scores = guidance.get(scores_key, [])
        score_text = ", ".join(str(score) for score in scores[:6]) if isinstance(scores, list) else ""
        if count > 6:
            score_text = f"{score_text}..."
        note = (
            "No es viable como un solo marcador; requiere cartera de marcadores."
            if count > 1
            else "Cobertura alcanzada con un marcador, caso extremadamente raro."
        )
        return (
            "<div>"
            f"<span>{html.escape(label)}</span>"
            f"<strong>{count} marcadores</strong>"
            f"<small>{format_pct(coverage)} cubierto. {html.escape(score_text)}. {note}</small>"
            "</div>"
        )

    options = "".join(
        "<li>"
        f"<strong>{html.escape(prediction_score_label(prediction, item['score']))}</strong>"
        f"<span>{float(item['expected_points']):.2f} pts esp. | exacto {format_pct(float(item['exact_prob']))} | "
        f"diferencia {format_pct(float(item['difference_prob']))} | resultado {format_pct(float(item['result_prob']))}</span>"
        "</li>"
        for item in prediction.penca_scores[:5]
    )
    promotion_tile = (
        f"<div><span>Corrección anti-Poisson modal</span><strong>Aplicada</strong><small>{html.escape(str(guidance.get('recommended_promotion_note', 'Se eligió una alternativa más calibrada.')))}</small></div>"
        if float(guidance.get("recommended_calibrated_promotion", 0.0) or 0.0) > 0.0
        else ""
    )
    return (
        "<div class=\"reason-block penca-block\">"
        "<h4>Penca Ovación: marcador optimizado por ensamble</h4>"
        "<p class=\"meta\">Regla aplicada: 8 puntos por marcador exacto, 5 por diferencia de goles y 3 por ganador. La lista ya no depende solo de Poisson: combina probabilidad multimodelo, escenarios de partido, familias históricas de cada selección, marginales de goles, plausibilidad y puntos esperados.</p>"
        "<div class=\"subgrid\">"
        f"<div><span>Marcador recomendado para cargar</span><strong>{html.escape(top_score_label)}</strong></div>"
        f"<div><span>Marcador exacto más probable</span><strong>{html.escape(top_exact_label)}</strong></div>"
        f"<div><span>Selector de marcador</span><strong>Ensamble no solo Poisson</strong><small>{html.escape(str(guidance.get('score_selector_method', 'Distribución + puntos + plausibilidad')))}</small></div>"
        f"<div><span>Escenario de partido</span><strong>{html.escape(str(guidance.get('recommended_scoreline_scenario_family', 'marcador balanceado')).title())}</strong><small>{html.escape(str(guidance.get('recommended_scoreline_scenario_note', 'Escenario mixto.')))}</small></div>"
        f"<div><span>Calibración de goles enteros</span><strong>{format_pct(float(guidance.get('recommended_scoreline_calibration_index', 0.0)))}</strong><small>{html.escape(str(guidance.get('recommended_scoreline_calibration_note', 'Ajusta el marcador contra goles esperados, margen y prior histórico.')))}</small></div>"
        f"{promotion_tile}"
        f"<div><span>Calidad del marcador exacto</span><strong>{html.escape(str(guidance.get('precision_label', 'sin clasificar')))}</strong></div>"
        f"<div><span>Ajuste histórico del marcador</span><strong>{format_pct(float(guidance.get('recommended_empirical_prior_index', 0.0)))}</strong><small>Compatibilidad con frecuencias históricas de marcadores de fútbol.</small></div>"
        f"<div><span>Perfil histórico específico del cruce</span><strong>{float(guidance.get('recommended_historical_matchup_boost', 1.0)) - 1.0:+.1%}</strong><small>Corrección acotada por las familias de marcador de ambas selecciones; no es una probabilidad.</small></div>"
        f"<div><span>Compatibilidad histórica del marcador con el cruce</span><strong>{format_pct(float(guidance.get('recommended_matchup_family_index', 0.50)))}</strong><small>Compara cómo suele ganar una selección y cómo suele perder la otra. No reemplaza la probabilidad multimodelo.</small></div>"
        f"<div><span>Consenso real del marcador</span><strong>{format_pct(float(guidance.get('recommended_public_score_popularity_index', 0.0)))}</strong><small>Desactivado hasta tener fuente real; no se estima con fama ni intuición.</small></div>"
        f"<div><span>Valor diferencial del marcador</span><strong>{format_pct(float(guidance.get('recommended_differential_value_index', 0.0)))}</strong><small>Útil solo si existe consenso real para comparar; no altera la probabilidad futbolística.</small></div>"
        f"<div><span>Filtro de plausibilidad</span><strong>{format_pct(float(guidance.get('recommended_plausibility_index', 1.0)))}</strong><small>{html.escape(str(guidance.get('recommended_plausibility_note', 'marcador de forma normal')))}</small></div>"
        f"<div><span>Máximo realista exacto único</span><strong>{format_pct(float(guidance.get('single_exact_upper_bound', top['exact_prob'])))}</strong><small>{html.escape(str(guidance.get('single_exact_ceiling_label', 'un exacto único no llega a 90-95%')))}</small></div>"
        f"<div><span>Puntos esperados del pick</span><strong>{float(top['expected_points']):.2f} / 8</strong></div>"
        f"<div><span>Probabilidad de clavar exacto</span><strong>{format_pct(float(top['exact_prob']))}</strong></div>"
        f"<div><span>Probabilidad de al menos diferencia correcta</span><strong>{format_pct(float(top['difference_prob']))}</strong></div>"
        f"<div><span>Cobertura top-5 marcadores</span><strong>{format_pct(float(guidance.get('top5_coverage', 0.0)))}</strong></div>"
        f"{exact_coverage_tile('Marcadores para cubrir 90%', 'coverage90_count', 'coverage90', 'coverage90_scores')}"
        f"{exact_coverage_tile('Marcadores para cubrir 95%', 'coverage95_count', 'coverage95', 'coverage95_scores')}"
        f"<div><span>Ajuste histórico del marcador</span><strong>{html.escape(str(guidance.get('score_shape_label', 'sin ajuste histórico específico')))}</strong></div>"
        f"<div><span>Firmeza del marcador Penca</span><strong>{html.escape(str(guidance.get('penca_certainty_label', 'sin clasificar')))} | {format_pct(float(guidance.get('penca_certainty_index', 0.0)))}</strong></div>"
        "</div>"
        "<p class=\"meta\"><strong>Guardrail exacto:</strong> ningún marcador único se mostrará como 90-95% salvo que la distribución real lo soporte. Para llegar a 90-95% en marcador exacto necesitas una cartera de marcadores; si Penca solo permite uno, usamos el que maximiza puntos esperados.</p>"
        f"<p class=\"meta\">{html.escape(str(guidance.get('recommendation_note', 'Usa este marcador como entrada principal y revisa las alternativas si quieres cubrir.')))}</p>"
        f"<p class=\"meta\">Marcador del modelo: {html.escape(top_exact_label)}. Marcador para Penca: {html.escape(top_score_label)}. Si difieren, Penca usa el ensamble de exacto, diferencia, ganador, prior histórico, goles marginales y plausibilidad.</p>"
        "<div class=\"subgrid penca-mode-grid\">"
        f"{portfolio_tile('Modo principal', guidance.get('score_portfolio', {}).get('balanced') if isinstance(guidance.get('score_portfolio'), dict) else top, 'Maximiza puntos esperados.')}"
        f"{portfolio_tile('Modo seguro', guidance.get('safe_score'), 'Baja varianza: favorece diferencia/ganador.')}"
        f"{portfolio_tile('Modo diferencial', guidance.get('score_portfolio', {}).get('differential') if isinstance(guidance.get('score_portfolio'), dict) else guidance.get('upside_score'), 'Menos obvio: solo busca valor contra consenso real disponible.')}"
        "</div>"
        "<div class=\"certainty-grid score-guidance-grid\">"
        f"{goal_options_list(guidance.get('goal_options_a'), prediction.team_a)}"
        f"{goal_options_list(guidance.get('goal_options_b'), prediction.team_b)}"
        "</div>"
        f"{asymmetric_options_list(guidance.get('asymmetric_score_options'))}"
        "<div class=\"scores\"><h4>Alternativas por puntos esperados</h4>"
        f"<ul>{options}</ul></div>"
        "</div>"
    )


def build_global_confidence_markdown(entries: Sequence[dict]) -> List[str]:
    if not entries:
        return ["_Sin partidos cargados para armar el resumen rápido del torneo._"]

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
        if fixture_is_live(entry):
            live_matches += 1

    avg_confidence = sum(item[0] for item in ranked) / len(ranked)
    avg_top3 = sum(item[1] for item in ranked) / len(ranked)
    strongest = sorted(ranked, key=lambda item: item[0], reverse=True)[:3]
    most_open = sorted(ranked, key=lambda item: item[0])[:3]
    market_edges = sorted(ranked_market, key=lambda item: item[0], reverse=True)[:3]

    lines = [
        "- Qué significa esta sección: resume si hoy el torneo se ve más claro o más incierto. No es una nota del modelo; es una foto de qué tan firmes o parejos salen los partidos publicados.",
        f"- Qué tan claro sale, en promedio, el pick principal: {format_pct(avg_confidence)}",
        f"- Cuánta probabilidad concentran, en promedio, los 3 marcadores más probables: {format_pct(avg_top3)}",
        f"- Partidos en vivo ahora mismo: {live_matches}",
        "- Cómo validar la actualización en vivo: revisa la hora de publicación de la portada, el badge 'En vivo', el minuto modelado y el archivo latest.json del sitio.",
    ]
    if strongest:
        lines.append(
            "- Partidos con favorito más claro: "
            + "; ".join(f"{item[2]['title']} {format_pct(item[0])}" for item in strongest)
        )
    if most_open:
        lines.append(
            "- Partidos más cerrados o parejos: "
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
            "- Grupos más parejos hasta ahora: "
            + "; ".join(
                f"{label} | equilibrio {format_pct(balance)} | empate medio {format_pct(avg_draw)} | partidos {matches}"
                for label, avg_conf, avg_draw, balance, matches in balanced_groups
            )
        )
        lines.append(
            "- Grupos con favoritos más claros hasta ahora: "
            + "; ".join(
                f"{label} | firmeza media {format_pct(avg_conf)} | empate medio {format_pct(avg_draw)} | partidos {matches}"
                for label, avg_conf, avg_draw, balance, matches in favorite_groups
            )
        )
    if market_edges:
        lines.append(
            "- Partidos donde más se separan modelo y cuotas: "
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
        if fixture_is_live(entry):
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
                f"Firmeza del pick {format_pct(confidence)} | resultado más probable {favorite_label} {format_pct(favorite_prob)}"
                if mode == "firm"
                else f"Firmeza del pick {format_pct(confidence)} | empate {format_pct(prediction.draw)}"
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
                tail = f"Firmeza media {format_pct(avg_conf)} | empate medio {format_pct(avg_draw)} | partidos {matches}"
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
            "<article><h3>Grupos más parejos</h3><ul>"
            f"{group_list(balanced_groups, 'balanced')}"
            "</ul></article>"
        )
        group_open_html = (
            "<article><h3>Grupos con favoritos más claros</h3><ul>"
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
                "detail": f"Pick más fuerte {favorite_label} {format_pct(favorite_prob)} | empate {format_pct(prediction.draw)}",
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
                "Dónde el favorito se ve más fuerte",
                strongest_chart_rows,
                tone="accent",
                description="Lectura rápida de los cruces donde hoy el modelo ve más diferencia entre el pick principal y el resto.",
                empty_body="Todavía no hay partidos comparables con ventaja clara.",
            ),
            render_rank_chart(
                "Dónde el partido se ve más parejo",
                most_open_chart_rows,
                tone="slate",
                description="No es lo mismo que empate seguro. Aquí sube cuando el duelo se ve abierto y ningún desenlace domina con claridad.",
                empty_body="Todavía no hay partidos comparables lo bastante parejos para dibujar esta lectura.",
            ),
            render_rank_chart(
                "Grupos más parejos",
                balanced_chart_rows,
                tone="gold",
                description="Resumen por grupo usando equilibrio medio, probabilidad de empate y los partidos que ya están cargados.",
                empty_body="Todavía no hay suficientes partidos de grupos para construir este gráfico.",
            ),
            render_rank_chart(
                "Grupos con favoritos más claros",
                favorite_group_chart_rows,
                tone="rose",
                description="Estos grupos muestran la mayor ventaja media del pick principal en los partidos publicados hasta ahora.",
                empty_body="Todavía no hay suficiente información de grupos para dibujar esta lectura.",
            ),
        ]
    )

    return (
        "<section class=\"panel confidence-panel\">"
        "<div class=\"panel-head\">"
        "<div>"
        "<p class=\"eyebrow\">Lectura global</p>"
        "<h2>Resumen rápido del torneo</h2>"
        "<p class=\"lede-tight\">Este bloque te deja ver rápido dónde hay favoritos más claros, dónde los cruces se ven más parejos y en qué partidos el modelo se aleja más de las cuotas. No es una nota del modelo; es una foto del tablero de hoy.</p>"
        "</div>"
        "</div>"
        "<div class=\"confidence-tiles\">"
        f"<div class=\"summary-tile\"><span>Claridad media del pick principal</span><strong>{format_pct(avg_confidence)}</strong></div>"
        f"<div class=\"summary-tile\"><span>Probabilidad media cubierta por los 3 marcadores más probables</span><strong>{format_pct(avg_top3)}</strong></div>"
        f"<div class=\"summary-tile\"><span>Partidos en vivo detectados</span><strong>{live_matches}</strong></div>"
        "<div class=\"summary-tile\"><span>Cómo comprobar actualización</span><strong><a href=\"latest.json\">latest.json</a> + badge En vivo + minuto</strong></div>"
        "</div>"
        f"{charts_html}"
        "<div class=\"confidence-grid\">"
        "<article><h3>Partidos con favorito más claro</h3><ul>"
        f"{bullet_list(strongest, 'firm')}"
        "</ul></article>"
        "<article><h3>Partidos más cerrados o parejos</h3><ul>"
        f"{bullet_list(most_open, 'open')}"
        "</ul></article>"
        "<article><h3>Modelo vs cuotas</h3><ul>"
        f"{market_list(market_edges) if market_edges else '<li><strong>Sin odds comparables</strong><span>Aún no llegaron cuotas utilizables del feed.</span></li>'}"
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


def coherent_bracket_matches(bracket_payload: dict) -> Dict[str, dict]:
    payload_matches = bracket_payload.get("matches", {})
    source_map = {
        match_id: (left_source, right_source, "winner")
        for round_matches in KNOCKOUT_MATCHES.values()
        for match_id, left_source, right_source in round_matches
    }
    source_map["M104"] = ("M101", "M102", "loser")

    def fallback_match(match: dict) -> dict:
        team_a = str(match.get("team_a", "?"))
        team_b = str(match.get("team_b", "?"))
        winner = str(match.get("winner", "?"))
        matchup = find_consistent_matchup(match, team_a, team_b)
        conditional_winners = conditional_winner_rows(matchup or match)
        matchup_favorite = (
            str(conditional_winners[0]["team"])
            if conditional_winners
            else str((matchup or match).get("winner", winner))
        )
        matchup_favorite_prob = (
            float(conditional_winners[0].get("conditional_prob", 0.0) or 0.0)
            if conditional_winners
            else float((matchup or match).get("conditional_winner_prob", match.get("winner_prob", 0.0)) or 0.0)
        )
        matchup_favorite_overall_prob = (
            float(conditional_winners[0].get("overall_prob", 0.0) or 0.0)
            if conditional_winners
            else float((matchup or match).get("winner_prob", match.get("winner_prob", 0.0)) or 0.0)
        )
        global_slot_winner = winner
        global_slot_winner_prob = float(match.get("winner_prob", 0.0) or 0.0)
        winner = matchup_favorite
        loser = team_b if winner == team_a else team_a
        conditional_prob = matchup_favorite_prob
        visual = dict(match)
        if matchup:
            visual["team_a"] = matchup.get("team_a", team_a)
            visual["team_b"] = matchup.get("team_b", team_b)
        visual["selected_winner"] = winner
        visual["selected_loser"] = loser
        visual["conditional_winner_prob"] = conditional_prob
        visual["winner"] = winner
        visual["winner_prob"] = matchup_favorite_overall_prob
        visual["global_slot_winner"] = global_slot_winner
        visual["global_slot_winner_prob"] = global_slot_winner_prob
        visual["matchup_favorite"] = matchup_favorite
        visual["matchup_favorite_prob"] = matchup_favorite_prob
        visual["matchup_favorite_overall_prob"] = matchup_favorite_overall_prob
        visual["slot_winner_mode"] = "conditional_favorite"
        return visual

    def find_consistent_matchup(match: dict, team_a: str, team_b: str) -> Optional[dict]:
        fallback = None
        for scenario in match.get("matchup_scenarios", []):
            if scenario.get("team_a") == team_a and scenario.get("team_b") == team_b:
                return scenario
            if {scenario.get("team_a"), scenario.get("team_b")} == {team_a, team_b}:
                fallback = scenario
        return fallback

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
            resolved[match_id] = fallback_match(match)
            continue
        left_source, right_source, source_kind = source_info
        left_match = resolved.get(left_source)
        right_match = resolved.get(right_source)
        if not left_match or not right_match:
            resolved[match_id] = fallback_match(match)
            continue
        left_team = left_match.get("selected_winner") if source_kind == "winner" else left_match.get("selected_loser")
        right_team = right_match.get("selected_winner") if source_kind == "winner" else right_match.get("selected_loser")
        if not left_team or not right_team:
            resolved[match_id] = fallback_match(match)
            continue
        matchup = find_consistent_matchup(match, str(left_team), str(right_team))
        if not matchup:
            resolved[match_id] = fallback_match(match)
            continue
        conditional_winners = conditional_winner_rows(matchup)
        matchup_favorite = (
            str(conditional_winners[0]["team"])
            if conditional_winners
            else str(matchup.get("winner", left_team))
        )
        matchup_favorite_prob = (
            float(conditional_winners[0].get("conditional_prob", 0.0) or 0.0)
            if conditional_winners
            else float(matchup.get("conditional_winner_prob", match.get("winner_prob", 0.0)) or 0.0)
        )
        matchup_favorite_overall_prob = (
            float(conditional_winners[0].get("overall_prob", 0.0) or 0.0)
            if conditional_winners
            else float(matchup.get("winner_prob", match.get("winner_prob", 0.0)) or 0.0)
        )
        slot_winner = str(match.get("winner", ""))
        selected_winner = matchup_favorite
        selected_row = conditional_winner_for_team(matchup, selected_winner)
        conditional_prob = (
            float(selected_row.get("conditional_prob", matchup_favorite_prob) or 0.0)
            if selected_row
            else matchup_favorite_prob
        )
        advance_probabilities = match.get("advance_probabilities") or {}
        overall_prob = (
            float((selected_row or {}).get("overall_prob", matchup.get("winner_prob", 0.0)) or 0.0)
        )
        visual = dict(match)
        visual["team_a"] = matchup.get("team_a", match.get("team_a"))
        visual["team_b"] = matchup.get("team_b", match.get("team_b"))
        visual["winner"] = selected_winner
        visual["matchup_prob"] = float(matchup.get("matchup_prob", match.get("matchup_prob", 0.0)))
        visual["conditional_winner_prob"] = conditional_prob
        visual["winner_prob"] = overall_prob
        visual["global_slot_winner"] = slot_winner
        visual["global_slot_winner_prob"] = float(advance_probabilities.get(slot_winner, match.get("winner_prob", 0.0)) or 0.0)
        visual["matchup_favorite"] = matchup_favorite
        visual["matchup_favorite_prob"] = matchup_favorite_prob
        visual["matchup_favorite_overall_prob"] = matchup_favorite_overall_prob
        visual["slot_winner_mode"] = "conditional_favorite"
        visual["selected_winner"] = selected_winner
        visual["selected_loser"] = visual["team_b"] if selected_winner == visual["team_a"] else visual["team_a"]
        resolved[match_id] = visual
    return resolved


def build_bracket_visual_html(bracket_payload: dict, entries: Optional[Sequence[dict]] = None) -> str:
    iterations = bracket_payload.get("iterations")
    updated_at = str(bracket_payload.get("updated_at") or "sin timestamp")
    iterations_label = f"{int(iterations):,}".replace(",", ".") if iterations else "sin dato"
    provider_stack = provider_stack_summary(entries)
    provider_mode = "live profundo activo" if provider_stack["deep_active"] else "base + proveedores preparados"
    sections = {stage_key: (label, stage_matches) for stage_key, label, stage_matches in bracket_stage_sections(bracket_payload)}

    visual_matches = coherent_bracket_matches(bracket_payload)
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
                "<strong>Otros cruces que también aparecen:</strong> "
                + html.escape(
                    "; ".join(
                        f"{scenario['team_a']} vs {scenario['team_b']} | avanza {scenario['winner']} | escenario {format_pct(float(scenario['prob']))}"
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
        if match.get("quiniela_override"):
            extra_parts.append(
                "<div class=\"mini override-note\">"
                f"<strong>Ajuste de quiniela:</strong> el modelo puro favorecia a {html.escape(str(match.get('model_winner', '')))} "
                f"por solo {format_pct(float(match.get('model_edge', 0.0)))} de margen; el boleto recomienda {winner} por consenso externo."
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
        badge_text = "Boleto" if match.get("quiniela_override") else "Avanza"
        row_a_badge = f"<span class=\"team-badge\">{badge_text}</span>" if "favorite" in row_a_class else ""
        row_b_badge = f"<span class=\"team-badge\">{badge_text}</span>" if "favorite" in row_b_class else ""
        conditional_prob = float(match.get("conditional_winner_prob", match.get("winner_prob", 0.0)))
        matchup_favorite = str(match.get("matchup_favorite") or match.get("winner", "?"))
        matchup_favorite_prob = float(match.get("matchup_favorite_prob", conditional_prob) or 0.0)
        if matchup_favorite == str(match.get("winner")):
            conditional_label = f"Si se juega, avanza {winner} {format_pct(conditional_prob)}"
        else:
            conditional_label = (
                f"Cruce: favorito condicional {html.escape(matchup_favorite)} "
                f"{format_pct(matchup_favorite_prob)}"
            )
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
            f"<span>Casillero: avanza {winner} {format_pct(float(match.get('winner_prob', 0.0)))}</span>"
            f"<span>{conditional_label}</span>"
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
    update_stamp = (
        "<aside class=\"bracket-update-card\">"
        "<span>Llave actualizada</span>"
        f"<strong>{html.escape(updated_at)}</strong>"
        "<span>Monte Carlo publicado</span>"
        f"<strong>{html.escape(iterations_label)} simulaciones</strong>"
        "<span>Snapshot profundo</span>"
        "<strong>100.000 simulaciones</strong>"
        "<span>Proveedor activo</span>"
        f"<strong>{html.escape(str(provider_stack['active']))}</strong>"
        "</aside>"
    )
    provider_note = (
        "<div class=\"bracket-provider-strip\">"
        f"<span>Stack de datos de la llave: {html.escape(provider_mode)}</span>"
        f"<strong>Activo: {html.escape(str(provider_stack['active']))}</strong>"
        f"<span>Configurado: {html.escape(' + '.join(str(item) for item in provider_stack['configured']) or 'sin key profunda')}</span>"
        f"<em>Preparado: {html.escape(' + '.join(str(item) for item in provider_stack['prepared']))}</em>"
        "</div>"
    )
    return (
        "<section class=\"panel bracket-panel\">"
        "<div class=\"panel-head\">"
        "<div>"
        "<p class=\"eyebrow\">Hoja de Ruta</p>"
        "<h2>Llave Proyectada</h2>"
        f"{subtitle}"
        "</div>"
        f"{update_stamp}"
        "</div>"
        f"{provider_note}"
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
        return ["_El Brier 2026 se activa automáticamente con el primer partido terminado; antes no se inventa muestra._"]

    lines = [
        f"- Partidos cerrados analizados: {int(backtest.get('completed_matches', 0))}",
        f"- Partidos comparables en 90 minutos: {int(backtest.get('regular_time_samples', 0))}",
    ]
    if backtest.get("favorite_hit_rate") is not None:
        lines.append(f"- Cuántas veces acertamos el resultado más probable: {format_pct(float(backtest['favorite_hit_rate']))}")
    if backtest.get("top1_score_hit_rate") is not None:
        lines.append(f"- Cuántas veces acertamos exactamente el marcador principal: {format_pct(float(backtest['top1_score_hit_rate']))}")
    if backtest.get("top3_score_hit_rate") is not None:
        lines.append(f"- Cuántas veces el marcador real estuvo dentro de nuestros 3 resultados principales: {format_pct(float(backtest['top3_score_hit_rate']))}")
    if backtest.get("logloss_result") is not None:
        lines.append(f"- Error log-loss en resultado: {float(backtest['logloss_result']):.3f}")
    if backtest.get("brier_result") is not None:
        lines.append(f"- Error Brier en resultado: {float(backtest['brier_result']):.3f}")
    if backtest.get("brier_reliability") is not None:
        lines.append(f"- Brier descompuesto | calibración {float(backtest['brier_reliability']):.3f} | separación {float(backtest['brier_resolution']):.3f} | incertidumbre base {float(backtest['brier_uncertainty']):.3f}")
    if backtest.get("logloss_advance") is not None:
        lines.append(f"- Error log-loss en clasificación knockout: {float(backtest['logloss_advance']):.3f}")
    if backtest.get("brier_advance") is not None:
        lines.append(f"- Error Brier en clasificación knockout: {float(backtest['brier_advance']):.3f}")
    if backtest.get("market_logloss_result") is not None:
        lines.append(f"- Error log-loss de las cuotas en esos mismos partidos: {float(backtest['market_logloss_result']):.3f}")
    if backtest.get("temporal_cv_logloss") is not None:
        lines.append(
            f"- Validación temporal por ventanas | log-loss {float(backtest['temporal_cv_logloss']):.3f} | "
            f"Brier {float(backtest['temporal_cv_brier']):.3f} | acierto {format_pct(float(backtest['temporal_cv_accuracy']))}"
        )
    buckets = backtest.get("calibration_buckets") or []
    if buckets:
        lines.append(
            "- Si el modelo dice una probabilidad parecida, esto es lo que pasó en la realidad: "
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
            "<div class=\"panel-head\"><div><p class=\"eyebrow\">Validación</p><h2>Cómo viene acertando el modelo</h2>"
            "<p class=\"lede-tight\">El Brier 2026 no se inventa antes del torneo: se activa solo y desde el primer partido terminado. En cuanto ESPN/proveedor marque un resultado final, esta sección mostrará Brier, log-loss, acierto y buckets con la muestra disponible.</p>"
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
        quality_rows.append(f"<li><strong>Brier calibración</strong><span>{float(backtest['brier_reliability']):.3f}</span></li>")
        quality_rows.append(f"<li><strong>Brier separación</strong><span>{float(backtest['brier_resolution']):.3f}</span></li>")
        quality_rows.append(f"<li><strong>Incertidumbre base</strong><span>{float(backtest['brier_uncertainty']):.3f}</span></li>")
    if backtest.get("logloss_advance") is not None:
        quality_rows.append(f"<li><strong>Log-loss clasificación</strong><span>{float(backtest['logloss_advance']):.3f}</span></li>")
    if backtest.get("brier_advance") is not None:
        quality_rows.append(f"<li><strong>Brier clasificación</strong><span>{float(backtest['brier_advance']):.3f}</span></li>")
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
                "detail": "Cuántas veces acierta el resultado principal que publicamos.",
            }
        )
    if backtest.get("top1_score_hit_rate") is not None:
        performance_chart_rows.append(
            {
                "label": "Marcador principal exacto",
                "value": float(backtest["top1_score_hit_rate"]),
                "value_text": format_pct(float(backtest["top1_score_hit_rate"])),
                "detail": "Cuántas veces el marcador exacto número uno coincide con el resultado real.",
            }
        )
    if backtest.get("top3_score_hit_rate") is not None:
        performance_chart_rows.append(
            {
                "label": "Marcador dentro del top-3",
                "value": float(backtest["top3_score_hit_rate"]),
                "value_text": format_pct(float(backtest["top3_score_hit_rate"])),
                "detail": "Cuántas veces el marcador real cae dentro de nuestros tres marcadores principales.",
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
                "Qué tan seguido pega lo visible",
                performance_chart_rows,
                tone="accent",
                description="Este gráfico se enfoca en lo que más se ve en la web: pick principal, marcador exacto y aciertos por ventanas temporales.",
                empty_body="Todavía no hay suficientes partidos cerrados para medir rendimiento visible.",
            ),
            render_dual_bar_chart(
                "Calibración por tramos",
                calibration_chart_rows,
                description="Compara lo que el modelo prometía en cada tramo de confianza contra lo que terminó pasando de verdad.",
                primary_label="Confianza media",
                secondary_label="Acierto real",
                primary_tone="accent",
                secondary_tone="gold",
                empty_body="Todavía no hay suficientes buckets de confianza para comparar modelo y realidad.",
            ),
        ]
    )

    return (
        "<section class=\"panel backtest-panel\">"
        "<div class=\"panel-head\"><div><p class=\"eyebrow\">Validación</p><h2>Cómo viene acertando el modelo</h2>"
        "<p class=\"lede-tight\">Aquí reconstruimos el torneo partido por partido, siempre pronosticando antes de cargar el resultado real. Así medimos con justicia si el modelo está bien calibrado y cuánto se acerca a lo que terminó pasando.</p>"
        "</div></div>"
        f"<div class=\"confidence-tiles\">{''.join(metrics)}</div>"
        f"{charts_html}"
        "<div class=\"confidence-grid\">"
        "<article><h3>Errores del modelo</h3><ul>"
        f"{''.join(quality_rows) if quality_rows else '<li><strong>Sin muestra suficiente</strong><span>Aún no hay datos comparables.</span></li>'}"
        "</ul></article>"
        "<article><h3>Cuando el modelo dice X, qué tanto se cumple</h3><ul>"
        f"{''.join(calibration_rows) if calibration_rows else '<li><strong>Sin buckets</strong><span>Aún no hay suficientes partidos.</span></li>'}"
        "</ul></article>"
        "</div>"
        "</section>"
    )


def build_methodology_quality_html(
    entries: Optional[Sequence[dict]],
    bracket_payload: dict,
    backtest: dict,
) -> str:
    fixture_entries = [entry for entry in (entries or []) if not entry.get("projection")]
    total_fixtures = len(fixture_entries)
    live_count = sum(1 for entry in fixture_entries if fixture_is_live(entry))
    final_count = sum(1 for entry in fixture_entries if fixture_is_final(entry))
    goal_consensus_count = sum(1 for entry in fixture_entries if entry.get("market_total_line") is not None)
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    champion_rows = consensus_adjusted_champion_probabilities(bracket_payload, entries)
    consensus_context = consensus_live_update_context(entries)
    completed_matches = int(backtest.get("completed_matches", 0) or 0)

    checks = [
        {
            "label": "Monte Carlo",
            "status": "OK" if iterations >= 15000 else "Revisar",
            "tone": "ok" if iterations >= 15000 else "warn",
            "detail": (
                f"{iterations:,}".replace(",", ".")
                + " simulaciones en esta corrida; 15.000 es solo el mínimo técnico permitido."
                if iterations
                else "La llave no reporta número de simulaciones."
            ),
        },
        {
            "label": "Consenso externo campeón",
            "status": "Activo" if champion_rows else "Pendiente",
            "tone": "ok" if champion_rows else "warn",
            "detail": (
                "Probabilidades de campeón mezcladas dinámicamente: "
                f"{format_pct(float(consensus_context.get('model_blend', 0.0)))} modelo/live y "
                f"{format_pct(float(consensus_context.get('consensus_blend', 0.0)))} consenso externo."
                if champion_rows
                else "Falta una llave con campeones agregados para calcular el guardrail externo."
            ),
        },
        {
            "label": "Pronóstico de goles",
            "status": "Activo" if goal_consensus_count else "Listo",
            "tone": "ok" if goal_consensus_count else "neutral",
            "detail": (
                f"{goal_consensus_count}/{total_fixtures} partidos tienen línea externa seria de goles para ajustar el total esperado."
                if total_fixtures
                else "Sin fixtures cargados todavía."
            )
            if goal_consensus_count
            else (
                "El modelo publica goles esperados, marcador entero principal y over/under; cuando entre una línea externa, ajusta la brecha automáticamente."
                if total_fixtures
                else "Sin fixtures cargados todavía."
            ),
        },
        {
            "label": "In-play cada 5 minutos",
            "status": "Activo" if live_count else "Preparado",
            "tone": "ok" if live_count else "neutral",
            "detail": (
                f"{live_count} partidos en vivo y {final_count} cerrados. El tablero live recalcula cada 5 minutos; el guardrail 15k corre cada hora y el snapshot 100k corre cada 8 horas/manual o tras push relevante."
                if total_fixtures
                else "El workflow está listo, pero no hay partidos para monitorear."
            ),
        },
        {
            "label": "Backtesting y calibración",
            "status": "Activo" if completed_matches else "Listo al primer final",
            "tone": "ok" if completed_matches else "neutral",
            "detail": (
                f"{completed_matches} partidos cerrados reconstruidos secuencialmente con log-loss, Brier y calibración por tramos."
                if completed_matches
                else "No espera una muestra grande: empieza a medir Brier apenas haya un partido terminado."
            ),
        },
    ]
    rows = []
    for check in checks:
        rows.append(
            "<article class=\"method-quality-card\">"
            f"<span class=\"method-status {html.escape(str(check['tone']))}\">{html.escape(str(check['status']))}</span>"
            f"<h3>{html.escape(str(check['label']))}</h3>"
            f"<p>{html.escape(str(check['detail']))}</p>"
            "</article>"
        )
    return (
        "<div class=\"method-quality\">"
        "<div class=\"method-quality-head\">"
        "<p class=\"eyebrow\">Semáforo metodológico</p>"
        "<h3>Control de calidad del pronóstico</h3>"
        "<p>Este bloque separa lo que ya está activo de lo que está preparado para activarse cuando entren partidos, goles, noticias y feed live reales.</p>"
        "</div>"
        f"<div class=\"method-quality-grid\">{''.join(rows)}</div>"
        "</div>"
    )


def methodology_governance_items(
    entries: Optional[Sequence[dict]],
    bracket_payload: dict,
    backtest: dict,
) -> List[dict]:
    fixture_entries = [entry for entry in (entries or []) if not entry.get("projection")]
    live_count = sum(1 for entry in fixture_entries if fixture_is_live(entry))
    final_count = sum(1 for entry in fixture_entries if fixture_is_final(entry))
    completed_matches = int(backtest.get("completed_matches", 0) or 0)
    regular_samples = int(backtest.get("regular_time_samples", 0) or 0)
    market_samples = sum(
        1
        for entry in fixture_entries
        if entry.get("market_prob_a") is not None
        and entry.get("market_prob_draw") is not None
        and entry.get("market_prob_b") is not None
    )
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    history_meta = historical_features_payload().get("meta", {})
    official_history_count = int(history_meta.get("official_matches_since_start", 0) or 0)
    history_start_year = int(history_meta.get("start_year", 1950) or 1950)
    has_brier = backtest.get("brier_result") is not None
    has_temporal = backtest.get("temporal_cv_brier") is not None
    has_market_logloss = backtest.get("market_logloss_result") is not None
    history_count_text = f"{official_history_count:,}".replace(",", ".")
    iteration_text = f"{iterations:,}".replace(",", ".") if iterations else "sin dato"

    return [
        {
            "title": "Baseline v1 congelado",
            "status": "Congelado en commit 0370dfd",
            "tone": "ok",
            "detail": "El modelo base queda fijado por commit y SHA-256 en modelo_quiniela_2026_v1_base.py; las mejoras futuras se comparan contra ese checkpoint, no contra una versión móvil.",
            "action": "Antes de decir que una mejora sube el poder predictivo, debe superar este baseline en Brier, log-loss, calibración y puntos esperados Penca.",
        },
        {
            "title": "Tabla maestra histórica anti-fuga",
            "status": "Esquema creado",
            "tone": "ok",
            "detail": "data/historical_match_master_schema.json define partidos históricos con solo variables disponibles antes del juego: Elo, FIFA, plantilla, mercado, descanso, viajes, lesiones, táctica y contexto.",
            "action": "Backtesting 2010-2022, Euro/Copa América y benchmarks deben leer esa tabla sin usar resultados futuros, valores posteriores ni rankings posteriores.",
        },
        {
            "title": "Tres modos separados",
            "status": "Definido",
            "tone": "ok",
            "detail": "Pre-torneo estima campeón/llave con señales estructurales; pre-partido añade bajas, mercado y alineación probable; live añade minuto, marcador, eventos, tarjetas y momentum.",
            "action": "No mezclar capas: una variable live nunca puede entrar en la predicción pre-torneo ni en un backtest de partido previo.",
        },
        {
            "title": "Predicción fútbol vs optimización Penca",
            "status": "Separado",
            "tone": "ok",
            "detail": "El marcador más probable no siempre maximiza puntos Penca. Por eso el sistema distingue probabilidad futbolística, puntos esperados, diferencial y cobertura.",
            "action": "Publicar siempre marcador probable del modelo y marcador recomendado para cargar en Penca cuando difieran por estrategia.",
        },
        {
            "title": "Backtesting serio",
            "status": "Activo 2026" if completed_matches else "Preparado; falta muestra 2026",
            "tone": "ok" if completed_matches else "neutral",
            "detail": (
                f"{completed_matches} partidos cerrados y {regular_samples} muestras reglamentarias reconstruidas sin mirar el futuro."
                if completed_matches
                else "Arranca con el primer partido terminado: resultado, marcador, over/under, clasificación y eliminación se miden desde la muestra real disponible."
            ),
            "action": "Siguiente capa: cargar fixtures/resultados históricos curados de Mundiales 2010, 2014, 2018, 2022 y Euro/Copa América recientes para comparar torneos completos.",
        },
        {
            "title": "Validación rolling / temporal",
            "status": "Activa" if has_temporal else "Lista",
            "tone": "ok" if has_temporal else "neutral",
            "detail": (
                f"Walk-forward ya calcula ventanas temporales: Brier {float(backtest['temporal_cv_brier']):.3f}, log-loss {float(backtest['temporal_cv_logloss']):.3f}."
                if has_temporal
                else "La lógica ya pronostica antes de actualizar estados; no entrena con información futura."
            ),
            "action": "Para simular 2018 o 2022, cada fold debe usar solo datos disponibles antes de ese torneo.",
        },
        {
            "title": "Calibración probabilística",
            "status": "Con Brier" if has_brier else "Arranca al primer final",
            "tone": "ok" if has_brier else "neutral",
            "detail": (
                f"Brier actual {float(backtest['brier_result']):.3f}; log-loss {float(backtest.get('logloss_result', 0.0)):.3f}; buckets publicados cuando hay muestra."
                if has_brier
                else "No se inventa calibración. Cuando el modelo diga 70%, se medirá si resultados parecidos ganan cerca de 70%."
            ),
            "action": "Publicar reliability curves y buckets por tramo cuando haya suficientes partidos cerrados.",
        },
        {
            "title": "Ablation tests",
            "status": "Protocolo definido",
            "tone": "warn",
            "detail": "Comparar modelo completo contra versiones sin mercado, sin historia, sin Elo, sin plantilla, sin live y sin sesgo histórico.",
            "action": "No publicar números de ablation hasta correrlos con dataset temporal cerrado; si una capa no mejora Brier/log-loss, se baja su peso.",
        },
        {
            "title": "Benchmarks base",
            "status": "Parcial" if has_market_logloss else "Preparado",
            "tone": "ok" if has_market_logloss else "neutral",
            "detail": (
                "Mercado ya tiene log-loss comparable en esta muestra; faltan benchmarks puros Elo, FIFA y Poisson simple para el mismo corte."
                if has_market_logloss
                else "La web debe comparar contra Elo puro, FIFA puro, mercado puro, Poisson simple y modelo completo antes de decir que el modelo agrega valor."
            ),
            "action": "Si el modelo completo no supera benchmarks simples en validación temporal, está sobrecomplicado y debe simplificarse.",
        },
        {
            "title": "Pesos aprendidos del ensamble",
            "status": "Regularización pendiente",
            "tone": "warn",
            "detail": "Los pesos no deben elegirse por gusto: deben aprenderse con historial cerrado, regularización y walk-forward.",
            "action": "Usar los pesos manuales solo como prior; migrar a stacking calibrado cuando la matriz histórica por partido esté limpia.",
        },
        {
            "title": "Dependencia dinámica de partidos",
            "status": "Activo en estado",
            "tone": "ok",
            "detail": f"El estado acumula fatiga, tarjetas, moral, forma, lesiones y disponibilidad; live actual {live_count}, finales {final_count}.",
            "action": "Formalizar esta capa como modelo bayesiano dinámico: cada partido actualiza priors del siguiente y no trata los encuentros como independientes.",
        },
        {
            "title": "Intervalos de incertidumbre",
            "status": "Recomendado",
            "tone": "warn",
            "detail": f"La llave corre {iteration_text} simulaciones, suficiente para publicar rangos tipo España campeona 14%-19% en vez de un número aislado.",
            "action": "Agregar intervalos por campeón, final, clasificación y marcador modal usando varianza Monte Carlo y bootstrap de parámetros.",
        },
        {
            "title": "Stress testing",
            "status": "Escenarios definidos",
            "tone": "neutral",
            "detail": "Baja de estrella, baja de mediocentro, roja temprana, calor extremo, descanso corto, viaje largo y tanda de penales ya tienen variables de entrada.",
            "action": "Publicar sensibilidad por escenario: cuánto cambia pick, marcador Penca y llave si entra una noticia crítica.",
        },
        {
            "title": "Explicabilidad por predicción",
            "status": "Activa",
            "tone": "ok",
            "detail": "Cada partido ya puede mostrar drivers: fuerza, mercado, bajas, forma, clima, estilos, noticia/live y marcador recomendado.",
            "action": "Mantener la explicación en lenguaje de quiniela: por qué jugar fijo, cubrir o buscar diferencial.",
        },
        {
            "title": "Base histórica oficial",
            "status": "Cargada como memoria",
            "tone": "ok" if official_history_count else "warn",
            "detail": f"{history_count_text} partidos oficiales desde {history_start_year} alimentan priors, familias de marcador y penales; no sustituyen el backtest rolling.",
            "action": "Separar claramente memoria histórica de evaluación predictiva: una cosa entrena/regulariza, otra mide si acertamos.",
        },
        {
            "title": "Feeds, noticias y mercado",
            "status": "Activo" if market_samples else "Sin mercado profundo en este corte",
            "tone": "ok" if market_samples else "neutral",
            "detail": f"{market_samples} partidos tienen referencia de mercado; lesiones, alineaciones y noticias deben mover disponibilidad y marcador Penca cuando sean trazables.",
            "action": "No depender de una sola fuente: ESPN es base, noticias abiertas y proveedores profundos validan señales críticas.",
        },
    ]


def build_methodology_governance_markdown(
    entries: Optional[Sequence[dict]],
    bracket_payload: dict,
    backtest: dict,
) -> List[str]:
    lines = [
        "- Lectura: esta capa no promete que el modelo ya sea mejor que todos; define cómo se prueba si realmente agrega valor.",
        "- Regla dura: no se publican métricas históricas, Brier o ablation si no hay muestra comparable y temporalmente correcta.",
    ]
    for item in methodology_governance_items(entries, bracket_payload, backtest):
        lines.append(
            f"- {item['title']} | {item['status']}: {item['detail']} Acción: {item['action']}"
        )
    return lines


def build_methodology_governance_html(
    entries: Optional[Sequence[dict]],
    bracket_payload: dict,
    backtest: dict,
) -> str:
    items = methodology_governance_items(entries, bracket_payload, backtest)
    rows = []
    for item in items:
        rows.append(
            "<article class=\"method-quality-card governance-card\">"
            f"<span class=\"method-status {html.escape(str(item['tone']))}\">{html.escape(str(item['status']))}</span>"
            f"<h3>{html.escape(str(item['title']))}</h3>"
            f"<p>{html.escape(str(item['detail']))}</p>"
            f"<small>{html.escape(str(item['action']))}</small>"
            "</article>"
        )
    return (
        "<section class=\"panel methodology-governance-panel\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Auditoría metodológica profunda</p>"
        "<h2>Cómo probamos si el modelo realmente agrega valor</h2>"
        "<p class=\"lede-tight\">La mejora del poder predictivo no sale de subir porcentajes a mano. Sale de backtesting serio, calibración, ablations, benchmarks, stress testing y validación temporal sin información futura.</p>"
        "<p class=\"meta\">Si un bloque dice preparado o pendiente, significa que no se está maquillando una métrica: falta muestra real, proveedor activo o dataset histórico curado para publicarla.</p>"
        "</div></div>"
        f"<div class=\"method-quality-grid governance-grid\">{''.join(rows)}</div>"
        "</section>"
    )


def build_methodology_html(
    bracket_payload: dict,
    backtest: dict,
    entries: Optional[Sequence[dict]] = None,
) -> str:
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    montecarlo_line = f"{iterations:,}".replace(",", ".") + " iteraciones" if iterations else "iteraciones variables"
    history_meta = historical_features_payload().get("meta", {})
    official_history_count = int(history_meta.get("official_matches_since_start", 0) or 0)
    history_start_year = int(history_meta.get("start_year", 1950) or 1950)
    official_history_line = f"{official_history_count:,}".replace(",", ".")
    quality_html = build_methodology_quality_html(entries, bracket_payload, backtest)
    return (
        "<section class=\"panel methodology\">"
        "<div class=\"panel-head\">"
        "<div>"
        "<p class=\"eyebrow\">Cómo Leer Esto</p>"
        "<h2>Cómo está armado el modelo</h2>"
        "<p class=\"lede-tight\">La idea aquí no es complicar por complicar. El modelo ya es fuerte para quiniela; lo que más valor agrega ahora es que explique bien por qué cambia y que luego podamos medir con datos reales si viene acertando.</p>"
        "</div>"
        "</div>"
        f"{quality_html}"
        "<div class=\"method-grid\">"
        "<article>"
        "<h3>Partido a partido</h3>"
        "<p>Combina fuerza de cada selección, contexto del partido y un stack de modelos para estimar marcador final y probabilidades de victoria, empate y derrota.</p>"
        "</article>"
        "<article>"
        "<h3>Capa histórica desde 1950</h3>"
        f"<p>Además del Elo y la forma actual, el modelo incorpora una base trazable de {html.escape(official_history_line)} partidos oficiales cerrados desde {history_start_year}: rendimiento total, competitivo, mundialista, ataque, defensa, tandas de penales y 17 familias empíricas de marcador por selección. Para esta cifra se excluyen amistosos. Esa memoria histórica usa decaimiento temporal y shrinkage bayesiano empírico: aprende del pasado largo sin permitir que partidos antiguos tapen lo que está pasando hoy.</p>"
        "</article>"
        "<article>"
        "<h3>Cuadro completo</h3>"
        f"<p>La llave publicada se construye con Monte Carlo dinámico de {html.escape(montecarlo_line)} por corrida para que el cuadro no cambie solo por ruido de simulación. El snapshot profundo de referencia usa 100.000 simulaciones; 15.000 queda como guardrail mínimo horario. El muestreo de goles ya usa un RNG rápido con NumPy y semillas deterministas para sostener más simulaciones sin volver lento el procesamiento.</p>"
        "</article>"
        "<article>"
        "<h3>Stack estadístico</h3>"
        "<p>La capa prepartido mezcla el modelo principal Bivariante Poisson, un modelo de contraste Poisson independiente, un ajuste de baja anotación, una distribución de overdispersión calibrada, un calibrador ML ligero regularizado, un predictivo bayesiano dinámico y un ensamble final. Para elegir el marcador que cargas en Penca añade una capa distinta: compara familias históricas específicas de ambas selecciones para no someter el exacto únicamente a Poisson. El ensamble repondera los modelos según consenso, dispersión, evidencia del XI y cercanía al mercado cuando hay cuotas confiables.</p>"
        "</article>"
        "<article>"
        "<h3>Estrategia de datos</h3>"
        f"<p>El modelo prioriza fuentes sólidas y trazables antes que volumen bruto. Aquí la meta no es inflar cifras por marketing, sino usar capas de alta señal: {html.escape(official_history_line)} partidos oficiales cerrados desde {history_start_year}, datos oficiales, feed en vivo y mercado como referencia suave.</p>"
        "</article>"
        "<article>"
        "<h3>Modelos visibles en la web</h3>"
        "<p>En cada tarjeta de partido verás por separado qué dice Bivariante Poisson, qué dice Poisson independiente, qué dice el ajuste de baja anotación, qué dice la overdispersión calibrada, qué aporta el ML ligero, qué aporta el predictivo bayesiano dinámico y cuál es el ensamble final publicado. Así puedes comparar si coinciden o si hay dispersión entre modelos.</p>"
        "</article>"
        "<article>"
        "<h3>Estado dinámico</h3>"
        "<p>Actualiza Elo, forma, fatiga, disponibilidad, disciplina, clima, alineaciones, bajas, mercado y ahora también xG/xGA reciente ajustado por rival. Además, acumula el estilo reciente de cada selección para no arrancar cada cruce desde cero.</p>"
        "</article>"
        "<article>"
        "<h3>Validación y calibración</h3>"
        "<p>El seguimiento del rendimiento no se queda en acierto bruto. La web ahora muestra log-loss, Brier, descomposición de calibración y una lectura temporal por ventanas para ver si el modelo se mantiene estable cuando el torneo avanza.</p>"
        "</article>"
        "<article>"
        "<h3>Modo in-play</h3>"
        "<p>Durante un partido, condiciona las probabilidades por minuto, marcador actual y fase del juego. Si el feed trae datos más ricos, también usa tiros, tiros al arco, posesión, calidad de ocasiones, corners, disciplina, sustituciones, banco restante y el portero confirmado para recalcular todo.</p>"
        "</article>"
        "<article>"
        "<h3>Noticias y bajas</h3>"
        "<p>Si el feed publica ausencias, cambios de XI, movimiento de cuotas, árbitro o noticias relevantes del partido, esas señales entran como disponibilidad, moral o contexto adicional. El XI se pondera jugador por jugador cuando existe roster nominal; si faltan nombres locales, el ajuste se limita y la web lo declara para no inventar precisión.</p>"
        "</article>"
        "<article>"
        "<h3>Cómo validar el refresh</h3>"
        "<p>La portada publica hora de actualización, badge En vivo, minuto modelado y un latest.json. Si esos campos cambian, el in-play se está recalculando bien.</p>"
        "</article>"
        "</div>"
        f"<p class=\"lede-tight\">Backtesting actual: {html.escape(str(int(backtest.get('completed_matches', 0))))} partidos cerrados reconstruidos secuencialmente.</p>"
        "</section>"
    )


def build_runtime_status_html(entries: Sequence[dict], bracket_payload: dict) -> str:
    fixture_entries = [entry for entry in entries if not entry.get("projection")]
    projected_entries = [entry for entry in entries if entry.get("projection")]
    modeled_total = len(fixture_entries) + len(projected_entries)
    live_count = sum(1 for entry in fixture_entries if fixture_is_live(entry))
    final_count = sum(1 for entry in fixture_entries if fixture_is_final(entry))
    pending_count = max(len(fixture_entries) - live_count - final_count, 0)
    now_utc = datetime.now(timezone.utc)

    def _should_be_live_by_clock(entry: dict) -> bool:
        kickoff_text = str(entry.get("kickoff_utc") or "").strip()
        if not kickoff_text or fixture_is_final(entry):
            return False
        try:
            kickoff = datetime.fromisoformat(kickoff_text.replace("Z", "+00:00"))
        except ValueError:
            return False
        return kickoff <= now_utc and (now_utc - kickoff).total_seconds() <= 150 * 60

    should_be_live = [entry for entry in fixture_entries if _should_be_live_by_clock(entry)]
    missing_live_payload = [
        entry
        for entry in should_be_live
        if entry.get("live_score_a") is None
        and entry.get("live_score_b") is None
        and entry.get("live_elapsed_minutes") is None
        and entry.get("minute") is None
    ]
    runtime = provider_runtime_diagnostics(entries)
    deep_providers = runtime["deep_sources"]
    live_sources = runtime["live_sources"]
    configured_wired = runtime["configured_wired"]
    if deep_providers:
        provider_label = " + ".join(deep_providers)
        feed_depth_label = "Enriquecido"
    elif live_sources:
        provider_label = " + ".join(live_sources)
        feed_depth_label = "Base pública"
    else:
        provider_label = "espn_scoreboard"
        feed_depth_label = "Base pública"
    feed_limit_note = (
        "In-play enriquecido: hay proveedor profundo en esta corrida; si trae eventos, el modelo puede usar tiros, "
        "disciplina, sustituciones, xG/ocasiones y contexto minuto a minuto."
        if deep_providers
        else "In-play limitado: sin proveedor profundo activo, el modelo recalcula con marcador, estado, minuto, "
        "fixture, noticias abiertas y clima disponibles; no finge xG tiro-a-tiro si el feed no lo trae."
    )
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    iterations_label = f"{iterations:,}".replace(",", ".") if iterations else "sin dato"
    in_play_label = "Activo" if live_count > 0 else "Listo para activarse"
    cards = [
        (
            "Estado operativo",
            "Publicación automática en <strong>GitHub Actions + Pages</strong>. "
            "El tablero live, los marcadores recomendados y los picks Penca se reconstruyen cada <strong>5 minutos</strong>. "
            f"Esta publicación trae una llave de <strong>{iterations_label} simulaciones</strong>; "
            "el snapshot profundo principal usa <strong>100.000 simulaciones</strong> y corre en un carril separado cada 8 horas/manual o tras push relevante.",
        ),
        (
            "Monte Carlo publicado",
            f"Simulaciones visibles en este corte: <strong>{iterations_label}</strong>. "
            "Si ves <strong>15.000</strong>, léelo como mínimo técnico del carril horario; la referencia estable del modelo es <strong>100.000</strong>.",
        ),
        (
            "Frecuencia real de actualización",
            "Marcadores y tablero: <strong>cada 5 minutos</strong>. "
            "Guardrail horario: <strong>15.000 simulaciones como mínimo</strong>. "
            "Snapshot principal 100k: <strong>cada 8 horas, manual o por push relevante</strong> después de cambios grandes, porque esa corrida es costosa.",
        ),
        (
            "Proveedor live activo",
            f"<strong>{html.escape(provider_label)}</strong> | {html.escape(feed_depth_label)}. "
            f"Adaptador con key en esta corrida: <strong>{html.escape(' + '.join(configured_wired) or 'ninguno')}</strong>. "
            "Si aparece un proveedor profundo en fixtures, el in-play entra con más señales del partido.",
        ),
        (
            "Lectura prudente del feed",
            html.escape(feed_limit_note),
        ),
        (
            "Estado del tablero",
            f"<strong>{modeled_total}</strong> partidos del Mundial modelados: "
            f"<strong>{len(fixture_entries)}</strong> con fixture/live directo y "
            f"<strong>{len(projected_entries)}</strong> cruces eliminatorios proyectados. "
            f"Estado live de fixtures directos: <strong>{live_count}</strong> en vivo, "
            f"<strong>{final_count}</strong> finales y <strong>{pending_count}</strong> pendientes.",
        ),
    ]
    if missing_live_payload:
        labels = ", ".join(str(entry.get("label") or entry.get("id") or "partido") for entry in missing_live_payload[:3])
        cards.insert(
            0,
            (
                "Alerta de ingestión live",
                f"Por horario ya debería haber datos en vivo para <strong>{html.escape(labels)}</strong>, "
                "pero este corte no trae minuto ni marcador. El modelo queda en modo prepartido/fallback "
                "hasta que ESPN o un proveedor conectado entregue datos reales.",
            ),
        )
    card_html = "".join(
        (
            "<article class=\"runtime-card\">"
            f"<h3>{html.escape(title)}</h3>"
            f"<p>{body}</p>"
            "</article>"
        )
        for title, body in cards
    )
    chip_html = (
        "<div class=\"runtime-chip-row\">"
        f"<span class=\"runtime-chip\">In-play <strong>{html.escape(in_play_label)}</strong></span>"
        f"<span class=\"runtime-chip\">Validación <strong>{html.escape('latest.json + badge En vivo + minuto')}</strong></span>"
        f"<span class=\"runtime-chip\">Frecuencia <strong>{html.escape('marcadores 5 min | guardrail 15k horario | snapshot 100k cada 8h/manual/push')}</strong></span>"
        "</div>"
    )
    return (
        "<section class=\"panel runtime-panel\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Estado Del Modelo</p>"
        "<h2>Qué está corriendo ahora mismo</h2>"
        "<p class=\"lede-tight\">Esta caja resume lo que de verdad está publicado: cuántas simulaciones usa la llave, qué feed live está activo y cuántas tarjetas del tablero están en vivo, cerradas o pendientes.</p>"
        "</div></div>"
        f"<div class=\"runtime-grid\">{card_html}</div>"
        f"{chip_html}"
        "</section>"
    )


def build_landing_proof_html(entries: Sequence[dict], bracket_payload: dict, backtest: dict) -> str:
    fixture_entries = [entry for entry in entries if not entry.get("projection")]
    projected_entries = [entry for entry in entries if entry.get("projection")]
    modeled_total = len(fixture_entries) + len(projected_entries)
    live_count = sum(1 for entry in fixture_entries if fixture_is_live(entry))
    final_count = sum(1 for entry in fixture_entries if fixture_is_final(entry))
    pending_count = max(len(fixture_entries) - live_count - final_count, 0)
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    iterations_label = f"{iterations:,}".replace(",", ".") if iterations else "sin dato"
    champion_rows = consensus_adjusted_champion_probabilities(bracket_payload, entries)
    completed_matches = int(backtest.get("completed_matches", 0) or 0)
    goal_consensus_count = sum(1 for entry in fixture_entries if entry.get("market_total_line") is not None)
    model_status = "Activo" if iterations >= 15000 and champion_rows else "En preparación"
    live_status = "En vivo" if live_count else "Listo"
    evidence_cards = [
        (
            "Motor probado",
            f"{iterations_label} simulaciones Monte Carlo, ensamble de modelos y auditoría bloqueante antes de publicar.",
            "ok" if iterations >= 15000 else "warn",
        ),
        (
            "Actualización real",
            f"GitHub Actions regenera marcadores y picks cada 5 minutos, el guardrail 15k cada hora y el snapshot 100k cada 8 horas/manual o tras push relevante. Modela {modeled_total} partidos: {len(fixture_entries)} fixtures directos y {len(projected_entries)} cruces de llave proyectados. Estado directo: {live_count} live, {final_count} final, {pending_count} pendientes.",
            "ok",
        ),
        (
            "Decisión de quiniela",
            "Separa picks base, partidos cerrados, marcadores defendibles y coberturas. No fuerza una falsa certeza del 90%.",
            "ok",
        ),
        (
            "Contraste externo",
            "Mezcla consenso de campeón y líneas serias de goles cuando existen, sin dejar que tapen el modelo propio.",
            "ok" if champion_rows or goal_consensus_count else "neutral",
        ),
        (
            "Calibración",
            f"{completed_matches} partidos cerrados reconstruidos con log-loss, Brier y tramos de confianza.",
            "ok" if completed_matches else "neutral",
        ),
        (
            "In-play",
            "Cuando empieza el partido recalcula marcador, probabilidades y goles restantes con minuto, score y eventos disponibles.",
            "ok" if live_count else "neutral",
        ),
    ]
    card_html = "".join(
        (
            f"<article class=\"proof-card {html.escape(tone)}\">"
            f"<h3>{html.escape(title)}</h3>"
            f"<p>{html.escape(detail)}</p>"
            "</article>"
        )
        for title, detail, tone in evidence_cards
    )
    return (
        "<section class=\"panel landing-proof\" id=\"prueba-operacional\">"
        "<div class=\"proof-layout\">"
        "<div class=\"proof-copy\">"
        "<p class=\"eyebrow\">Prueba operacional</p>"
        "<h2>Cómo sabes que no es una página bonita pegada encima de números muertos</h2>"
        "<p class=\"lede-tight\">El sitio publica evidencia de funcionamiento: simulaciones, frecuencia de refresco, auditoría, calibración, consenso externo y estado in-play. Para ganar la quiniela, esta capa importa tanto como el pronóstico: te dice cuándo confiar, cuándo cubrir y cuándo no sobreapostar un partido abierto.</p>"
        "<div class=\"proof-status-row\">"
        f"<span>Modelo <strong>{html.escape(model_status)}</strong></span>"
        f"<span>In-play <strong>{html.escape(live_status)}</strong></span>"
        f"<span>Partidos modelados <strong>{modeled_total}</strong></span>"
        "</div>"
        "</div>"
        f"<div class=\"proof-grid\">{card_html}</div>"
        "</div>"
        "</section>"
    )


def _quality_artifact_exists(base_dir: Path, candidates: Sequence[str]) -> bool:
    for candidate in candidates:
        if (base_dir / candidate).exists():
            return True
    return False


def _quality_csv_metric(base_dir: Path, candidates: Sequence[str], metric: str) -> str:
    for candidate in candidates:
        path = base_dir / candidate
        if not path.exists():
            continue
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    if str(row.get("metric", "")).strip() == metric:
                        return str(row.get("value", "")).strip()
        except (OSError, csv.Error):
            continue
    return ""


def _quality_csv_row_count(base_dir: Path, candidates: Sequence[str]) -> int:
    for candidate in candidates:
        path = base_dir / candidate
        if not path.exists():
            continue
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                return sum(1 for _ in csv.DictReader(handle))
        except (OSError, csv.Error):
            continue
    return 0


def _quality_json_payload(base_dir: Path, candidates: Sequence[str]) -> dict:
    for candidate in candidates:
        path = base_dir / candidate
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def model_quality_audit_items(
    entries: Sequence[dict],
    bracket_payload: dict,
    backtest: dict,
) -> Tuple[float, List[dict]]:
    """Score the project as an auditable prediction product, not as a promise."""

    base_dir = Path(__file__).resolve().parent
    fixture_entries = [entry for entry in entries if not entry.get("projection")]
    projected_entries = [entry for entry in entries if entry.get("projection")]
    runtime = provider_runtime_diagnostics(entries)
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    completed_matches = int(backtest.get("completed_matches", 0) or 0)
    regular_samples = int(backtest.get("regular_time_samples", 0) or 0)
    live_count = sum(1 for entry in fixture_entries if fixture_is_live(entry))
    final_count = sum(1 for entry in fixture_entries if fixture_is_final(entry))
    profiles = [
        quiniela_certainty_profile(entry)
        for entry in entries
        if entry.get("prediction") is not None and not entry.get("projection")
    ]
    ticket_audit = quiniela_audit_metrics(profiles)
    has_historical = _quality_artifact_exists(
        base_dir,
        [
            "historical_matches.csv",
            "data/historical_matches.csv",
            "worldcup2026/data/historical_matches.csv",
        ],
    )
    has_benchmarks = _quality_artifact_exists(
        base_dir,
        [
            "benchmark_results.csv",
            "outputs/benchmark_results.csv",
            "site/benchmark_results.csv",
        ],
    )
    has_backtest = _quality_artifact_exists(
        base_dir,
        [
            "backtest_summary.csv",
            "outputs/backtest_summary.csv",
            "outputs/real_backtest/backtest_summary.csv",
            "site/backtest_summary.csv",
        ],
    )
    historical_backtest_rows = _quality_csv_row_count(
        base_dir,
        [
            "outputs/real_backtest/backtest_predictions.csv",
            "site/backtest_predictions.csv",
        ],
    )
    historical_rows_text = _quality_csv_metric(
        base_dir,
        ["data/real_data_coverage_report.csv", "site/real_data_coverage_report.csv"],
        "selected_rows",
    )
    try:
        historical_rows_number = int(float(historical_rows_text)) if historical_rows_text else historical_backtest_rows
    except ValueError:
        historical_rows_number = historical_backtest_rows
    historical_missing_fields = _quality_csv_metric(
        base_dir,
        ["data/real_data_coverage_report.csv", "site/real_data_coverage_report.csv"],
        "real_pre_match_fields_missing",
    )
    has_calibration = _quality_artifact_exists(
        base_dir,
        [
            "calibration_report.csv",
            "outputs/calibration_report.csv",
            "outputs/real_backtest/calibration_report.csv",
            "site/calibration_report.csv",
        ],
    )
    has_calibration_bins = _quality_artifact_exists(
        base_dir,
        [
            "calibration_bins.csv",
            "outputs/calibration_bins.csv",
            "outputs/real_backtest/calibration_bins.csv",
            "site/calibration_bins.csv",
        ],
    )
    has_ablation = _quality_artifact_exists(
        base_dir,
        [
            "ablation_results.csv",
            "outputs/ablation_results.csv",
            "outputs/real_backtest/ablation_results.csv",
            "site/ablation_results.csv",
        ],
    )
    ablation_rows = _quality_csv_row_count(
        base_dir,
        [
            "ablation_results.csv",
            "outputs/ablation_results.csv",
            "outputs/real_backtest/ablation_results.csv",
            "site/ablation_results.csv",
        ],
    )
    live_sync = _quality_json_payload(base_dir, ["live_sync_status.json", "site/live_sync_status.json"])
    deep_live_provider_used = bool(live_sync.get("deep_live_provider_used") or runtime["deep_sources"])
    live_provider_names = [
        str(item)
        for item in (
            live_sync.get("providers_used")
            or live_sync.get("deep_live_providers")
            or runtime["deep_sources"]
            or []
        )
        if item
    ]
    stale_live_warning = bool(live_sync.get("stale_live_warning"))

    def score_item(
        title: str,
        score: float,
        status: str,
        detail: str,
        next_step: str,
        weight: float,
    ) -> dict:
        return {
            "title": title,
            "score": clamp(score, 0.0, 10.0),
            "status": status,
            "detail": detail,
            "next_step": next_step,
            "weight": weight,
        }

    monte_score = 10.0 if iterations >= 100000 else 9.0 if iterations >= 50000 else 8.0 if iterations >= 15000 else 4.0
    fixture_total = len(fixture_entries) + len(projected_entries)
    penca_score = 8.0
    if ticket_audit.get("total"):
        defensible_ratio = float(ticket_audit.get("defensible_scores", 0)) / max(float(ticket_audit.get("total", 0)), 1.0)
        penca_score = 6.5 + 2.0 * defensible_ratio
        if float(ticket_audit.get("strategy_adjusted_firmness", 0.0)) >= 0.90:
            penca_score += 1.0
        if fixture_total >= 104:
            penca_score += 0.5
    historical_calibration_ready = bool(has_backtest and has_calibration and has_calibration_bins and historical_rows_number >= 1000)
    calibration_score = (
        10.0
        if historical_calibration_ready
        else 9.0
        if completed_matches >= 20 and has_calibration
        else 7.0
        if has_calibration_bins and has_backtest
        else 5.0
        if completed_matches
        else 4.0
    )
    benchmark_score = 10.0 if has_benchmarks and has_backtest and historical_rows_number >= 1000 else 9.0 if has_benchmarks else 6.0
    ablation_score = 9.2 if has_ablation and ablation_rows >= 10 else 9.0 if has_ablation else 5.5
    historical_score = 10.0 if has_historical and has_backtest and historical_rows_number >= 1000 else 6.0 if has_historical else 4.0
    provider_score = (
        10.0
        if deep_live_provider_used and live_count > 0 and not stale_live_warning
        else 8.0
        if live_count > 0
        else 7.0
        if runtime["configured_wired"]
        else 6.0
    )
    exact_score_score = 8.0 if ticket_audit.get("defensible_scores", 0) else 6.0
    if has_backtest and completed_matches >= 20:
        exact_score_score += 1.0
    operations_score = 9.0 if fixture_total >= 104 and iterations >= 15000 else 7.0
    if live_count or final_count:
        operations_score += 0.5

    items = [
        score_item(
            "Motor Monte Carlo",
            monte_score,
            "Excelente" if monte_score >= 9.5 else "Fuerte",
            f"Última llave publicada con {iterations:,} simulaciones.".replace(",", "."),
            "Mantener 100k como snapshot principal; 15k queda solo como mínimo técnico del carril horario. Más simulaciones reducen ruido, no garantizan exactos.",
            0.12,
        ),
        score_item(
            "Operación y refresh",
            operations_score,
            "Live profundo activo" if deep_live_provider_used and live_count else "Fuerte",
            f"{len(fixture_entries)} fixtures directos + {len(projected_entries)} cruces proyectados; {live_count} live y {final_count} finales aplicados.",
            (
                "Proveedor live profundo activo: el carril de 5 minutos puede mover marcadores, estado, eventos y llave con datos reales."
                if deep_live_provider_used and live_count
                else "Carril live de 5 minutos activo; si entra proveedor profundo, se habilita lectura tiro-a-tiro/eventos sin cambiar metodología."
            ),
            0.10,
        ),
        score_item(
            "Optimización Penca",
            penca_score,
            "Muy fuerte" if penca_score >= 8.5 else "Fuerte",
            "La capa Penca separa marcador probable del modelo, marcador para cargar, cobertura y diferencial.",
            "Validar puntos esperados contra resultados históricos o contra el scoring real de la app cuando empiece la Penca.",
            0.13,
        ),
        score_item(
            "Calibración probabilística",
            calibration_score,
            "Histórica publicada" if historical_calibration_ready else "Pendiente de muestra 2026" if not completed_matches else "En medición",
            (
                f"Reliability/Brier/log-loss publicados con {historical_rows_number} partidos históricos; la calibración 2026 se activa con el primer final."
                if historical_calibration_ready and not completed_matches
                else f"Reliability/Brier/log-loss publicados con {historical_rows_number} partidos históricos y {completed_matches} partidos 2026 cerrados."
                if historical_calibration_ready
                else
                f"{completed_matches} partidos cerrados y {regular_samples} muestras de tiempo regular para Brier/log-loss."
                if completed_matches
                else "El Brier 2026 empieza con el primer final; antes de eso no hay track record real del torneo."
            ),
            (
                "Mantener calibration_report.csv y calibration_bins.csv publicados; recalibrar 2026 cuando entren finales reales."
                if historical_calibration_ready
                else "Conectar calibration_report.csv y reliability bins cuando existan suficientes partidos cerrados."
            ),
            0.16,
        ),
        score_item(
            "Benchmarks externos/simples",
            benchmark_score,
            "Medido con histórico" if benchmark_score >= 10.0 else "Estructura lista" if not has_benchmarks else "Medido",
            (
                f"benchmark_results.csv y benchmark_summary.csv publicados contra el set histórico de {historical_rows_number} partidos."
                if benchmark_score >= 10.0
                else "El módulo de benchmarks existe; el 10/10 requiere comparar contra Elo, FIFA, mercado, Poisson simple e histórico en CSV publicado."
            ),
            (
                "Usar estos benchmarks como piso: si el modelo completo no los supera fuera de muestra, simplificar."
                if benchmark_score >= 10.0
                else "Correr benchmark_results.csv con el mismo set histórico usado para backtesting."
            ),
            0.12,
        ),
        score_item(
            "Ablation tests",
            ablation_score,
            "Publicado" if has_ablation else "Estructura lista",
            (
                f"ablation_results.csv publicado con {ablation_rows} variantes; ya se ve qué bloques conviene conservar, reducir o tratar como neutros."
                if has_ablation
                else "El módulo de ablation existe; falta publicar qué bloques suben o bajan Brier/log-loss fuera de muestra."
            ),
            (
                "Siguiente mejora: conectar el adaptador del full model a ablation para que no sea solo baseline histórico."
                if has_ablation
                else "Ejecutar ablation_results.csv antes de congelar pesos finales."
            ),
            0.10,
        ),
        score_item(
            "Histórico anti-fuga",
            historical_score,
            "Medido con datos reales" if has_historical and has_backtest else "Pendiente crítico" if not has_historical else "Preparado",
            (
                f"Backtest real con {historical_rows_number or historical_rows_text or 'dataset historico'} partidos de Mundial, Euro y Copa América desde 1950; "
                f"campos no inventados siguen vacíos: {historical_missing_fields or 'FIFA/mercado/plantilla/fase exacta'}."
                if has_historical and has_backtest
                else "Sin historical_matches.csv trazable, el modelo es auditable en estructura pero no puede reclamar validación histórica completa."
            ),
            "Seguir incorporando fuentes reales para rankings FIFA pre-partido, mercado y plantillas históricas; no usar proxies para llenar huecos.",
            0.13,
        ),
        score_item(
            "Fuentes y proveedores",
            provider_score,
            "Live profundo activo" if provider_score >= 10.0 else "Live base activo" if live_count else "Base sólida",
            (
                f"Proveedor live profundo activo: {', '.join(live_provider_names or runtime['deep_sources'])}."
                if provider_score >= 10.0
                else f"Hay {live_count} partido(s) live con fuente base; falta proveedor profundo válido para eventos tiro-a-tiro."
                if live_count
                else "Corre con fuentes abiertas/base; eventos tiro-a-tiro dependen de proveedor válido."
            ),
            (
                "Mantener validación de freshness: si el proveedor profundo se cae, bajar automáticamente a live base."
                if provider_score >= 10.0
                else "No scrapear sin licencia; activar o sumar proveedor profundo verificable cuando cubra Mundial 2026."
            ),
            0.07,
        ),
        score_item(
            "Realismo de marcadores",
            exact_score_score,
            "Fuerte, no perfecto",
            "Los marcadores ya no deben leerse como Poisson puro: hay ensamble, Penca, baja anotación, overdispersion y optimización por puntos.",
            "El 10/10 exige backtest específico de marcador exacto y puntos Penca, no solo intuición visual.",
            0.07,
        ),
    ]
    total_weight = sum(float(item["weight"]) for item in items) or 1.0
    overall = sum(float(item["score"]) * float(item["weight"]) for item in items) / total_weight
    return clamp(overall, 0.0, 10.0), items


def build_model_quality_audit_html(
    entries: Sequence[dict],
    bracket_payload: dict,
    backtest: dict,
) -> str:
    overall, items = model_quality_audit_items(entries, bracket_payload, backtest)
    complete = overall >= 9.5 and all(float(item["score"]) >= 9.0 for item in items)
    overall_label = f"{overall:.1f}/10"
    if complete:
        verdict = "Candidato real a 10/10"
        verdict_note = "Todos los pilares principales tienen evidencia suficiente. Aun así, no garantiza resultados deportivos."
    else:
        verdict = "No se maquilla como 10/10"
        verdict_note = "La herramienta es fuerte, pero el 10/10 real exige histórico, benchmarks, ablation y calibración publicados."

    cards = []
    for item in items:
        tone = "ok" if float(item["score"]) >= 8.5 else "warn" if float(item["score"]) < 6.5 else "neutral"
        cards.append(
            "<article class=\"quality-audit-card\">"
            "<div class=\"quality-audit-card-top\">"
            f"<span class=\"method-status {tone}\">{html.escape(str(item['status']))}</span>"
            f"<strong>{float(item['score']):.1f}/10</strong>"
            "</div>"
            f"<h3>{html.escape(str(item['title']))}</h3>"
            f"<p>{html.escape(str(item['detail']))}</p>"
            f"<em>{html.escape(str(item['next_step']))}</em>"
            "</article>"
        )

    return (
        "<section class=\"panel quality-audit-panel\" id=\"auditoria-10\">"
        "<div class=\"quality-audit-hero\">"
        "<div>"
        "<p class=\"eyebrow\">Auditoría 10/10</p>"
        "<h2>Qué falta para que el modelo sea 10/10 de verdad.</h2>"
        "<p class=\"lede-tight\">Este bloque no evalúa si una selección va a ganar; evalúa si el sistema es verificable, calibrado, reproducible y útil para Penca sin vender certeza artificial.</p>"
        "</div>"
        "<div class=\"quality-audit-score\">"
        f"<span>{html.escape(verdict)}</span>"
        f"<strong>{html.escape(overall_label)}</strong>"
        f"<p>{html.escape(verdict_note)}</p>"
        "</div>"
        "</div>"
        f"<div class=\"quality-audit-grid\">{''.join(cards)}</div>"
        "<p class=\"quality-audit-footnote\"><strong>Regla:</strong> no subimos una métrica a 90/95 o 10/10 por diseño visual. Solo sube si mejora Brier, log-loss, benchmarks, ablation o puntos Penca fuera de muestra.</p>"
        "</section>"
    )


def predictive_robustness_gate(
    entries: Sequence[dict],
    bracket_payload: dict,
    backtest: dict,
) -> dict:
    """Expose the guardrails that keep the prediction system honest."""

    base_dir = Path(__file__).resolve().parent
    fixture_entries = [entry for entry in entries if not entry.get("projection")]
    projected_entries = [entry for entry in entries if entry.get("projection")]
    runtime = provider_runtime_diagnostics(entries)
    completed_matches = int(backtest.get("completed_matches", 0) or 0)
    brier_result = backtest.get("brier_result")
    brier_active = completed_matches > 0 and brier_result is not None
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    live_count = sum(1 for entry in fixture_entries if fixture_is_live(entry))
    final_count = sum(1 for entry in fixture_entries if fixture_is_final(entry))

    has_historical = _quality_artifact_exists(
        base_dir,
        [
            "historical_matches.csv",
            "data/historical_matches.csv",
            "site/historical_matches.csv",
        ],
    )
    has_backtest = _quality_artifact_exists(
        base_dir,
        [
            "backtest_summary.csv",
            "outputs/backtest_summary.csv",
            "outputs/real_backtest/backtest_summary.csv",
            "site/backtest_summary.csv",
        ],
    )
    has_benchmarks = _quality_artifact_exists(
        base_dir,
        [
            "benchmark_results.csv",
            "outputs/benchmark_results.csv",
            "site/benchmark_results.csv",
        ],
    )
    historical_rows_text = _quality_csv_metric(
        base_dir,
        ["data/real_data_coverage_report.csv", "site/real_data_coverage_report.csv"],
        "selected_rows",
    )

    exact_probs: List[float] = []
    top3_coverages: List[float] = []
    for entry in entries:
        prediction = entry.get("prediction")
        if not prediction:
            continue
        if prediction.exact_scores:
            exact_probs.append(float(prediction.exact_scores[0][1]))
        depth = prediction.statistical_depth or {}
        top3_value = depth.get("top3_coverage")
        if isinstance(top3_value, (int, float)):
            top3_coverages.append(float(top3_value))

    avg_exact = sum(exact_probs) / len(exact_probs) if exact_probs else None
    max_exact = max(exact_probs) if exact_probs else None
    avg_top3 = sum(top3_coverages) / len(top3_coverages) if top3_coverages else None
    deep_live_active = bool(runtime["deep_sources"])
    historical_ready = bool(has_historical and has_backtest)
    benchmark_ready = bool(has_benchmarks)
    strict_inputs = bool(STRICT_REAL_INPUTS_ONLY and DISABLE_PUBLIC_POPULARITY_PROXY)

    if brier_active and historical_ready and benchmark_ready and strict_inputs:
        status = "operativo_con_evidencia"
    elif live_count > 0:
        status = "torneo_en_curso_live_activo"
    elif final_count > 0 or completed_matches > 0:
        status = "torneo_en_curso_con_finales"
    elif strict_inputs and (historical_ready or benchmark_ready or iterations >= 100000):
        status = "operativo_con_guardrails"
    else:
        status = "operativo_en_preparacion"

    return {
        "status": status,
        "tournament_phase": "en_curso" if live_count > 0 or final_count > 0 or completed_matches > 0 else "pretorneo",
        "iterations": iterations,
        "fixture_count": len(fixture_entries),
        "projected_count": len(projected_entries),
        "live_count": live_count,
        "final_count": final_count,
        "completed_matches": completed_matches,
        "brier_2026_active": brier_active,
        "brier_result": brier_result,
        "historical_backtest_available": historical_ready,
        "historical_rows": historical_rows_text,
        "benchmarks_available": benchmark_ready,
        "deep_live_feed_active": deep_live_active,
        "configured_deep_providers": runtime["configured_wired"],
        "deep_sources": runtime["deep_sources"],
        "avg_exact_score_probability": avg_exact,
        "max_exact_score_probability": max_exact,
        "avg_top3_score_coverage": avg_top3,
        "proxy_inputs_blocked": strict_inputs,
        "methodology_lock": (
            "Datos, resultados, lesiones, sanciones, alineaciones y mercado pueden cambiar; "
            "pesos y metodología no deben tocarse durante el torneo salvo bug real o mejora validada por backtest."
        ),
        "exact_score_single_pick_policy": (
            "Un marcador único no se etiqueta como 90-95% sin evidencia; la mejora robusta viene de cartera, "
            "cobertura y optimización de puntos Penca."
        ),
    }


def build_predictive_robustness_gate_html(
    entries: Sequence[dict],
    bracket_payload: dict,
    backtest: dict,
) -> str:
    """Render the operational fixes for the model's predictive weak points."""

    gate = predictive_robustness_gate(entries, bracket_payload, backtest)
    tournament_label = "Torneo en curso" if gate.get("tournament_phase") == "en_curso" else "Preinicio"
    tournament_detail = (
        f"Fixtures directos: {gate['live_count']} en vivo y {gate['final_count']} finales. "
        "El modelo ya debe leerse como in-play/torneo, no como pretorneo."
        if gate.get("tournament_phase") == "en_curso"
        else "Todavía no hay fixture live ni final en el corte publicado."
    )
    brier_label = "Activo" if gate["brier_2026_active"] else "Espera primer final"
    brier_detail = (
        f"Brier 2026 ya mide {gate['completed_matches']} partidos cerrados."
        if gate["brier_2026_active"]
        else "No se inventa Brier antes de tener finales reales del Mundial 2026."
    )
    historical_label = "Publicado" if gate["historical_backtest_available"] else "Pendiente"
    historical_detail = (
        f"Backtest histórico disponible; filas reales seleccionadas: {gate['historical_rows'] or 'dataset publicado'}."
        if gate["historical_backtest_available"]
        else "Sin backtest histórico completo publicado, el modelo no debe reclamar validación total."
    )
    benchmark_label = "Medido" if gate["benchmarks_available"] else "Pendiente"
    benchmark_detail = (
        "Hay comparación contra benchmarks simples."
        if gate["benchmarks_available"]
        else "Debe compararse contra Elo, FIFA, mercado, Poisson simple y versión sin mercado."
    )
    feed_label = "Profundo activo" if gate["deep_live_feed_active"] else "Base limitado"
    feed_detail = (
        f"Fuentes profundas activas: {', '.join(gate['deep_sources'])}."
        if gate["deep_live_feed_active"]
        else "Si no hay proveedor profundo, no se finge xG tiro-a-tiro ni eventos que el feed no trae."
    )
    exact_detail_bits = []
    if gate["avg_exact_score_probability"] is not None:
        exact_detail_bits.append(f"Exacto medio top-1: {format_pct(float(gate['avg_exact_score_probability']))}")
    if gate["max_exact_score_probability"] is not None:
        exact_detail_bits.append(f"Mayor exacto individual: {format_pct(float(gate['max_exact_score_probability']))}")
    if gate["avg_top3_score_coverage"] is not None:
        exact_detail_bits.append(f"Cobertura top-3 media: {format_pct(float(gate['avg_top3_score_coverage']))}")
    exact_detail = "; ".join(exact_detail_bits) or "Sin muestra suficiente de marcadores exactos en este corte."

    tiles = [
        (
            "Estado del Mundial",
            tournament_label,
            tournament_detail,
            "ok" if gate.get("tournament_phase") == "en_curso" else "neutral",
        ),
        (
            "Calibración 2026",
            brier_label,
            brier_detail,
            "ok" if gate["brier_2026_active"] else "warn",
        ),
        (
            "Backtest histórico",
            historical_label,
            historical_detail,
            "ok" if gate["historical_backtest_available"] else "warn",
        ),
        (
            "Benchmarks",
            benchmark_label,
            benchmark_detail,
            "ok" if gate["benchmarks_available"] else "warn",
        ),
        (
            "Feed in-play",
            feed_label,
            feed_detail,
            "ok" if gate["deep_live_feed_active"] else "neutral",
        ),
        (
            "Marcador exacto",
            "Guardrail activo",
            f"{exact_detail}. Un marcador único no se fuerza a 90-95%.",
            "ok",
        ),
        (
            "Inputs proxy",
            "Bloqueados" if gate["proxy_inputs_blocked"] else "Revisar",
            "Si falta una variable real, queda neutral; no se llena con fama, intuición ni popularidad pública.",
            "ok" if gate["proxy_inputs_blocked"] else "warn",
        ),
    ]
    tile_html = "".join(
        (
            f"<article class=\"robustness-tile {html.escape(tone)}\">"
            f"<span>{html.escape(title)}</span>"
            f"<strong>{html.escape(label)}</strong>"
            f"<p>{html.escape(detail)}</p>"
            "</article>"
        )
        for title, label, detail, tone in tiles
    )
    return (
        "<section class=\"panel robustness-panel\" id=\"robustez-predictiva\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Robustez predictiva</p>"
        "<h2>Correcciones que evitan que el modelo se contamine o se sobrevenda.</h2>"
        "<p class=\"lede-tight\">Este bloque convierte las limitaciones críticas en controles visibles: no inventar muestra, no fingir feed profundo, no usar proxies, no cambiar metodología por intuición y no prometer exact-score imposible.</p>"
        "</div></div>"
        f"<div class=\"robustness-grid\">{tile_html}</div>"
        "<div class=\"robustness-policy\">"
        "<strong>Bloqueo metodológico durante el Mundial.</strong> "
        f"{html.escape(str(gate['methodology_lock']))}"
        "</div>"
        "</section>"
    )


def build_score_dynamics_html(entries: Sequence[dict]) -> str:
    """Explain and expose why score recommendations are not static."""

    fixture_entries = [entry for entry in entries if not entry.get("projection")]
    projected_entries = [entry for entry in entries if entry.get("projection")]
    live_count = sum(1 for entry in fixture_entries if fixture_is_live(entry))
    final_count = sum(1 for entry in fixture_entries if fixture_is_final(entry))
    pending_count = max(len(fixture_entries) - live_count - final_count, 0)
    live_tone = "ok" if live_count else "neutral"
    final_tone = "ok" if final_count else "neutral"
    cards = [
        (
            "Durante el partido",
            "Si el fixture entra en vivo, el marcador recomendado deja de ser prepartido: usa marcador actual, minuto, goles restantes, eventos, tiros, tarjetas y patrones disponibles.",
            live_tone,
        ),
        (
            "Después de cada final",
            "Cada resultado real actualiza forma, Elo dinámico, goles a favor/en contra, tabla, fatiga, disciplina y señales recientes; eso puede mover los marcadores de los próximos partidos.",
            final_tone,
        ),
        (
            "En la llave",
            f"Los {len(projected_entries)} cruces eliminatorios proyectados se reconstruyen por Monte Carlo. Si cambia un clasificado o un ganador real, cambian rival, probabilidades y marcador recomendado.",
            "ok" if projected_entries else "neutral",
        ),
        (
            "En Penca Ovación",
            "El marcador Penca no se copia ciegamente del exacto más probable: se reordena en cada corrida para maximizar puntos esperados bajo regla 8/5/3.",
            "ok",
        ),
    ]
    card_html = "".join(
        (
            f"<article class=\"score-dynamics-card {html.escape(tone)}\">"
            f"<h3>{html.escape(title)}</h3>"
            f"<p>{html.escape(body)}</p>"
            "</article>"
        )
        for title, body, tone in cards
    )
    return (
        "<section class=\"panel score-dynamics-panel\" id=\"marcadores-dinamicos\">"
        "<div class=\"panel-head\"><div>"
        "<p class=\"eyebrow\">Marcadores dinámicos</p>"
        "<h2>Los marcadores cambian a medida que avanza el campeonato.</h2>"
        "<p class=\"lede-tight\">No son picks congelados. En cada refresh se recalculan el marcador más probable del modelo, el marcador para cargar en Penca y las alternativas por puntos esperados.</p>"
        "</div></div>"
        "<div class=\"score-dynamics-status\">"
        f"<span>Fixtures directos <strong>{len(fixture_entries)}</strong></span>"
        f"<span>En vivo <strong>{live_count}</strong></span>"
        f"<span>Finales aplicados <strong>{final_count}</strong></span>"
        f"<span>Pendientes <strong>{pending_count}</strong></span>"
        "</div>"
        f"<div class=\"score-dynamics-grid\">{card_html}</div>"
        "<p class=\"score-dynamics-note\"><strong>Regla práctica:</strong> antes del torneo verás cambios menores; durante partidos y después de resultados reales, el marcador puede cambiar más porque el estado del equipo y la llave ya no son supuestos.</p>"
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
                result_text += " | con prórroga"
            result_html = f"<p class=\"meta\">{html.escape(result_text)}</p>"
        elif entry.get("live_score_a") is not None and entry.get("live_score_b") is not None:
            result_html = (
                f"<p class=\"meta\">En vivo: {html.escape(prediction.team_a)} {entry['live_score_a']} - "
                f"{entry['live_score_b']} {html.escape(prediction.team_b)}</p>"
            )
        else:
            result_html = ""
        timezone_html = ""
        if "EDT" in str(status_text):
            timezone_html = (
                "<p class=\"meta timezone-note\">Horario del feed en EDT; confirma la hora local "
                "en Uruguay/Venezuela/tu calendario antes de cargar el boleto.</p>"
            )

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
        if entry.get("market_total_line") is not None:
            provider = entry.get("goal_consensus_source") or "consenso externo"
            market_html += f"<p class=\"meta\">Referencia seria de goles ({html.escape(str(provider))}): total {float(entry['market_total_line']):.2f}</p>"

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
                "<div class=\"reason-block\"><h4>Cronología de disparos y eventos</h4>"
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
                "<div class=\"reason-block\"><h4>Por qué cambia el pronóstico</h4>"
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
        goal_forecast_block_html = goal_forecast_html(entry, prediction)
        model_compare_html = model_comparison_html(prediction)
        penca_score_block_html = penca_ovacion_score_html(prediction)
        top_penca_score = penca_ovacion_top_score(prediction)

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
                    f"<div><span>Marcador más probable de la tanda</span><strong>{html.escape(projected_shootout)}</strong></div>"
                    f"<div><span>Marcador medio esperado en la tanda</span><strong>{prediction.team_a} {prediction.penalty_shootout.get('avg_score_a', 0.0):.2f} | "
                    f"{prediction.team_b} {prediction.penalty_shootout.get('avg_score_b', 0.0):.2f}</strong></div>"
                    "<details class=\"inline-collapse shootout-collapse\">"
                    "<summary>Marcadores de tanda más probables</summary>"
                    "<div class=\"inline-collapse-body scores\">"
                    f"<ul>{shootout_scores}</ul></div>"
                    "</details>"
                )
            knockout_html = (
                "<div class=\"subgrid\">"
                f"<div><span>Quién tiene más probabilidad de avanzar</span><strong>{html.escape(prediction.team_a)} {format_pct(prediction.advance_a)} | "
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
            f"{timezone_html}"
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
            f"<div class=\"metric metric-score\"><span>Marcador más probable del modelo</span><strong>{html.escape(prediction_score_label(prediction, projected_score_value(prediction)))}</strong></div>"
            f"<div class=\"metric metric-penca\"><span>Marcador recomendado Penca Ovación</span><strong>{html.escape(prediction_score_label(prediction, top_penca_score['score']))}</strong></div>"
            f"<div class=\"metric metric-probs\"><span>{html.escape(top_result_label(prediction))}</span><strong>{html.escape(top_result_summary(prediction))}</strong></div>"
            "</div>"
            f"{average_goals_html}"
            f"{goal_forecast_block_html}"
            f"<div class=\"prob-block\">{probability_rows_html}</div>"
            f"{remaining_goals_html}"
            f"{depth_html}"
            f"{penca_score_block_html}"
            f"{model_compare_html}"
            f"{knockout_html}"
            "<div class=\"scores\">"
            "<h4>Marcadores finales más probables</h4>"
            f"<ul>{top_scores_html}</ul>"
            "</div>"
            "</section>"
        )

    if not cards:
        cards.append("<section class=\"card\"><h3>Sin partidos cargados</h3><p class=\"meta\">Agrega partidos a fixtures_template.json para ver probabilidades aquí.</p></section>")

    bracket_html = html.escape(bracket_text.strip() or "No hay llave generada todavía.")
    bracket_visual_html = build_bracket_visual_html(bracket_payload, entries)
    updated_at = iso_timestamp()
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    monte_carlo_iterations_label = f"{iterations:,}".replace(",", ".") if iterations else "sin dato"
    ticket_snapshot_html = build_ticket_snapshot_html(entries, updated_at)
    landing_proof_html = build_landing_proof_html(entries, bracket_payload, backtest)
    model_quality_audit_html = build_model_quality_audit_html(entries, bracket_payload, backtest)
    predictive_robustness_gate_html = build_predictive_robustness_gate_html(entries, bracket_payload, backtest)
    runtime_status_html = build_runtime_status_html(entries, bracket_payload)
    score_dynamics_html = build_score_dynamics_html(entries)
    championship_penca_html = build_championship_penca_optimizer_html(entries)
    methodology_html = build_methodology_html(bracket_payload, backtest, entries)
    methodology_governance_html = build_methodology_governance_html(entries, bracket_payload, backtest)
    prediction_operating_system_html = build_prediction_operating_system_html(entries, bracket_payload, backtest)
    calibration_depth_html = build_calibration_depth_html(entries, backtest)
    prediction_power_html = build_prediction_power_html(entries)
    agentic_learning_html = build_agentic_learning_html(entries, bracket_payload, backtest)
    provider_matrix_html = build_provider_matrix_html(entries)
    global_confidence_html = build_global_confidence_html(entries)
    max_certainty_html = build_max_certainty_html(entries)
    current_penca_decision_html = build_current_penca_decision_html(entries)
    competitive_penca_html = build_competitive_penca_html(entries)
    strategy_html = build_quiniela_strategy_html(entries)
    full_scorecard_html = build_full_scorecard_html(entries)
    consensus_guardrail_html = build_consensus_guardrail_html(bracket_payload, entries)
    external_benchmarks_html = build_external_forecast_benchmarks_html(bracket_payload, entries)
    dark_horses_html = build_dark_horses_html(bracket_payload, entries)
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
            "updated_at": html.escape(updated_at),
            "monte_carlo_iterations_label": html.escape(monte_carlo_iterations_label),
            "state_path": html.escape(str(state_path)),
            "fixtures_path": html.escape(str(fixtures_path)),
            "ticket_snapshot_html": ticket_snapshot_html,
            "landing_proof_html": landing_proof_html,
            "model_quality_audit_html": model_quality_audit_html,
            "predictive_robustness_gate_html": predictive_robustness_gate_html,
            "runtime_status_html": runtime_status_html,
            "score_dynamics_html": score_dynamics_html,
            "championship_penca_html": championship_penca_html,
            "methodology_html": methodology_html,
            "methodology_governance_html": methodology_governance_html,
            "prediction_operating_system_html": prediction_operating_system_html,
            "calibration_depth_html": calibration_depth_html,
            "prediction_power_html": prediction_power_html,
            "agentic_learning_html": agentic_learning_html,
            "provider_matrix_html": provider_matrix_html,
            "global_confidence_html": global_confidence_html,
            "max_certainty_html": max_certainty_html,
            "current_penca_decision_html": current_penca_decision_html,
            "competitive_penca_html": competitive_penca_html,
            "strategy_html": strategy_html,
            "full_scorecard_html": full_scorecard_html,
            "consensus_guardrail_html": consensus_guardrail_html,
            "external_benchmarks_html": external_benchmarks_html,
            "dark_horses_html": dark_horses_html,
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


def expected_bracket_match_ids() -> set:
    ids = {match["id"] for match in R32_MATCHES}
    ids.update(match_id for round_matches in KNOCKOUT_MATCHES.values() for match_id, _, _ in round_matches)
    ids.add("M104")
    return ids


def audit_tournament_draw(config: dict, teams: Dict[str, Team]) -> List[str]:
    errors: List[str] = []
    groups = config.get("groups", {})
    if len(groups) != 12:
        errors.append(f"El sorteo debe tener 12 grupos; tiene {len(groups)}.")
    group_teams = []
    for group_name, members in sorted(groups.items()):
        if len(members) != 4:
            errors.append(f"Grupo {group_name} debe tener 4 equipos; tiene {len(members)}.")
        group_teams.extend(members)
    if len(group_teams) != 48:
        errors.append(f"El sorteo debe tener 48 equipos; tiene {len(group_teams)}.")
    duplicates = sorted({team for team in group_teams if group_teams.count(team) > 1})
    if duplicates:
        errors.append("Equipos duplicados en sorteo: " + ", ".join(duplicates))
    missing = [team for team in group_teams if team not in teams]
    if missing:
        errors.append("Equipos del sorteo no existen en teams_2026.json: " + ", ".join(missing))
    not_qualified = [team for team in group_teams if team in teams and teams[team].status != "qualified"]
    if not_qualified:
        errors.append("Equipos no clasificados aparecen en el sorteo: " + ", ".join(not_qualified))
    for team in ("Bosnia and Herzegovina", "Dem. Rep. of Congo", "Iraq"):
        if team not in group_teams:
            errors.append(f"Falta clasificado resuelto en el sorteo: {team}.")
    for team in ("Italy", "Jamaica", "Bolivia", "Suriname", "New Caledonia"):
        if team in group_teams:
            errors.append(f"Equipo eliminado aparece indebidamente en el sorteo: {team}.")
    return errors


def audit_fixtures_payload(fixtures: Sequence[dict], teams: Dict[str, Team]) -> List[str]:
    errors: List[str] = []
    ids = []
    for index, fixture in enumerate(fixtures):
        if fixture.get("projection_only"):
            continue
        fixture_id = str(fixture.get("id") or fixture.get("match_id") or index)
        ids.append(fixture_id)
        for key in ("team_a", "team_b"):
            raw_name = fixture.get(key)
            if not raw_name:
                errors.append(f"Fixture {fixture_id} no tiene {key}.")
                continue
            try:
                team_name = resolve_team_name(str(raw_name), teams)
            except SystemExit:
                errors.append(f"Fixture {fixture_id} tiene equipo no reconocido: {raw_name}.")
                continue
            if teams[team_name].status != "qualified":
                errors.append(f"Fixture {fixture_id} usa equipo no clasificado: {team_name}.")
        status = normalized_match_status_state(fixture.get("status_state"))
        if status == "live" and not fixture_has_live_score(fixture):
            errors.append(f"Fixture {fixture_id} esta en vivo pero no tiene marcador live completo.")
    duplicate_ids = sorted({fixture_id for fixture_id in ids if ids.count(fixture_id) > 1})
    if duplicate_ids:
        errors.append("Fixtures con ids duplicados: " + ", ".join(duplicate_ids))
    return errors


def audit_bracket_payload(bracket_payload: dict, teams: Dict[str, Team], min_iterations: int) -> List[str]:
    errors: List[str] = []
    iterations = int(bracket_payload.get("iterations", 0) or 0)
    if iterations < min_iterations:
        errors.append(f"La llave usa {iterations} simulaciones; minimo requerido {min_iterations}.")
    if bracket_payload.get("updated_at") and bracket_payload.get("scoreline_engine") != "ensamble_no_solo_poisson_bayes_dinamico_v2":
        errors.append("La llave publicada no declara el motor de marcador Bayes dinámico vigente.")
    matches = bracket_payload.get("matches", {})
    missing_ids = sorted(expected_bracket_match_ids() - set(matches))
    if missing_ids:
        errors.append("Faltan partidos de llave en JSON: " + ", ".join(missing_ids))
    for match_id, match in matches.items():
        team_a = match.get("team_a")
        team_b = match.get("team_b")
        winner = match.get("winner")
        if not team_a or not team_b:
            errors.append(f"{match_id} no tiene ambos equipos.")
            continue
        if team_a not in teams:
            errors.append(f"{match_id} contiene equipo A no reconocido: {team_a}.")
        if team_b not in teams:
            errors.append(f"{match_id} contiene equipo B no reconocido: {team_b}.")
        if winner not in {team_a, team_b}:
            errors.append(f"{match_id} tiene ganador incoherente: {winner} no esta entre {team_a} y {team_b}.")
        for prob_key in ("matchup_prob", "winner_prob"):
            if prob_key in match:
                prob = float(match.get(prob_key) or 0.0)
                if prob < 0.0 or prob > 1.0:
                    errors.append(f"{match_id} tiene {prob_key} fuera de rango: {prob}.")
        advance_probabilities = match.get("advance_probabilities") or {}
        slot_mode = str(match.get("slot_winner_mode", "global_slot"))
        if slot_mode == "conditional_favorite":
            global_slot_winner = match.get("global_slot_winner")
            if global_slot_winner in advance_probabilities and "global_slot_winner_prob" in match:
                expected_global_prob = float(advance_probabilities.get(global_slot_winner, 0.0) or 0.0)
                published_global_prob = float(match.get("global_slot_winner_prob", 0.0) or 0.0)
                if abs(expected_global_prob - published_global_prob) > 0.000001:
                    errors.append(
                        f"{match_id} mezcla probabilidad global del casillero: "
                        f"{global_slot_winner} aparece con {published_global_prob:.4f}, "
                        f"pero su avance global es {expected_global_prob:.4f}."
                    )
        elif winner in advance_probabilities and "winner_prob" in match:
            expected_winner_prob = float(advance_probabilities.get(winner, 0.0) or 0.0)
            published_winner_prob = float(match.get("winner_prob", 0.0) or 0.0)
            if abs(expected_winner_prob - published_winner_prob) > 0.000001:
                errors.append(
                    f"{match_id} mezcla probabilidad global del casillero: "
                    f"{winner} aparece con {published_winner_prob:.4f}, pero su avance global es {expected_winner_prob:.4f}."
                )
        penalties_prob = float(match.get("penalties_prob", 0.0) or 0.0)
        if penalties_prob > 0.01 and not match.get("top_penalty_scores"):
            errors.append(f"{match_id} tiene probabilidad de penales pero no publica marcadores probables de tanda.")
        matchup_scenarios = match.get("matchup_scenarios") or []
        if matchup_scenarios:
            published = None
            for scenario in matchup_scenarios:
                if (match.get("team_a"), match.get("team_b")) == (scenario.get("team_a"), scenario.get("team_b")):
                    published = scenario
                    break
            if published is None:
                for scenario in matchup_scenarios:
                    if {match.get("team_a"), match.get("team_b")} == {scenario.get("team_a"), scenario.get("team_b")}:
                        published = scenario
                        break
            if published is None:
                errors.append(f"{match_id} publica un cruce que no existe entre sus escenarios simulados.")
            else:
                override = bool(match.get("quiniela_override"))
                winner_rows = conditional_winner_rows(published)
                favorite = winner_rows[0].get("team") if winner_rows else published.get("winner")
                if match.get("winner") != favorite:
                    published_teams = {row.get("team") for row in winner_rows}
                    if override and (match.get("winner") not in published_teams or not match.get("override_reason")):
                        errors.append(f"{match_id} aplica ajuste de quiniela sin trazabilidad suficiente.")
                    else:
                        errors.append(f"{match_id} no publica el favorito condicional del cruce mostrado.")
                if abs(float(match.get("matchup_prob", 0.0) or 0.0) - float(published.get("matchup_prob", 0.0) or 0.0)) > 0.000001:
                    errors.append(f"{match_id} mezcla probabilidad del escenario con probabilidad del cruce mostrado.")
            if "conditional_winner_prob" not in match:
                errors.append(f"{match_id} no separa probabilidad condicional de avanzar si el cruce se juega.")
    def sourced_team(match: dict, source_kind: str) -> Optional[str]:
        if source_kind == "winner":
            return match.get("winner")
        if source_kind == "loser":
            winner = match.get("winner")
            team_a = match.get("team_a")
            team_b = match.get("team_b")
            if winner == team_a:
                return team_b
            if winner == team_b:
                return team_a
        return None

    source_map = {
        match_id: (left_source, right_source, "winner")
        for round_matches in KNOCKOUT_MATCHES.values()
        for match_id, left_source, right_source in round_matches
    }
    source_map["M104"] = ("M101", "M102", "loser")
    coherent_matches = coherent_bracket_matches(bracket_payload)
    for match_id, (left_source, right_source, source_kind) in source_map.items():
        if match_id == "M104":
            match = matches.get(match_id)
            left = matches.get(left_source)
            right = matches.get(right_source)
        else:
            match = coherent_matches.get(match_id) or matches.get(match_id)
            left = coherent_matches.get(left_source) or matches.get(left_source)
            right = coherent_matches.get(right_source) or matches.get(right_source)
        if not match or not left or not right:
            continue
        expected_pair = {sourced_team(left, source_kind), sourced_team(right, source_kind)}
        actual_pair = {match.get("team_a"), match.get("team_b")}
        if None not in expected_pair and expected_pair != actual_pair:
            errors.append(
                f"{match_id} no sigue la rama proyectada: esperaba {sorted(expected_pair)}, recibio {sorted(actual_pair)}."
            )
    return errors


def audit_dashboard_html(dashboard_html: str) -> List[str]:
    errors = []
    required_snippets = [
        "Boleto recomendado hoy",
        "Qué cargar primero en Penca",
        "Marcador para cargar en Penca",
        "Hoja de máxima firmeza",
        "Quiniela Intelligence 2026",
        "Prueba operacional",
        "Una sala de decisión",
        "De datos a boleto",
        "Primero decide como una mesa profesional",
        "Monte Carlo publicado",
        "simulaciones por corrida",
        "actualiza picks, goles y marcadores live; la llave se propaga en el carril profundo",
        "Marcadores dinámicos",
        "Los marcadores cambian a medida que avanza el campeonato",
        "Modo campeonato",
        "La meta no es prometer 104/104",
        "No se promete 104/104 marcadores exactos",
        "marcador que debo poner en Penca",
        "Exactos realistas",
        "Llave dinámica",
        "Escenario recomendado ahora",
        "marcador que debes poner en Penca",
        "Escenario a escoger",
        "Se recalcula cada 5 minutos",
        "Modo Penca competitivo",
        "Jugar seguro",
        "Jugar óptimo",
        "Jugar diferencial",
        "Durante el partido",
        "Después de cada final",
        "marcador para cargar en Penca",
        "Partidos totales del Mundial 2026",
        "No son 72 en total",
        "Solo compara partidos con los mismos dos equipos",
        "Si cambia el cruce proyectado",
        "Estrategia para ganar la quiniela",
        "Marcadores para cargar en Penca",
        "marcador optimizado por ensamble",
        "Ensamble no solo Poisson",
        "Boleto completo",
        "Ventaja vs boleto popular",
        "Diferenciales positivos",
        "Cobertura recomendada",
        "Marcador exacto principal",
        "Máximo realista exacto único",
        "Marcadores para cubrir 90%",
        "Guardrail exacto",
        "certainty-panel",
        "Auditoría del boleto",
        "Picks base o principales",
        "Partidos cerrados o de riesgo alto",
        "Marcadores exactos defendibles",
        "Brecha mínima contra la segunda opción",
        "Firmeza de picks base",
        "Firmeza con estrategia aplicada",
        "Firmeza si fuerzas pick único",
        "Checklist de auditoría",
        "Picks más defendibles",
        "Marcadores exactos más defendibles",
        "Ajustes para boleto de quiniela",
        "Guardrail de consenso",
        "Comparadores externos",
        "Qué dicen otros modelos y dónde debemos desconfiar",
        "No se promedian a ciegas",
        "Goldman Sachs GIR",
        "FairCast / University of Portsmouth",
        "Panmure Liberum / Joachim Klement",
        "Radar de tapados",
        "Tapados con ruta realista",
        "índice de vigilancia",
        "no reemplaza la llave base",
        "Metodología de estimadores externos",
        "Ratings tipo Elo / ClubElo",
        "Ranking FIFA oficial",
        "SPI / modelos ofensivo-defensivos",
        "Mercado y consenso profesional",
        "Calibración avanzada",
        "Cómo evitamos que el modelo se sobreconfíe",
        "Shrinkage bayesiano",
        "Desacuerdo entre modelos",
        "Overdispersión calibrada",
        "Predictivo bayesiano dinámico",
        "Backtesting por buckets",
        "Límite de confianza operativa",
        "Predicción potenciada",
        "Probabilidad pura vs índice de firmeza",
        "Índice de firmeza medio",
        "Fuerza estructural media",
        "Watchlist de riesgo",
        "Agentes de aprendizaje",
        "Noticias multi-fuente",
        "No solo ESPN",
        "Eficiencia operativa",
        "Mapa de proveedores",
        "API-Football",
        "Sportmonks",
        "Sportradar",
        "Opta",
        "The Odds API",
        "NewsAPI",
        "GDELT",
        "StatsBomb",
        "ScoreBat",
        "Semáforo metodológico",
        "Control de calidad del pronóstico",
        "Baseline v1 congelado",
        "Tabla maestra histórica anti-fuga",
        "Tres modos separados",
        "Predicción fútbol vs optimización Penca",
        "Sistema operativo de predicción",
        "Congelar modelo final pre-torneo",
        "Re-simulación diaria",
        "No cambiar pesos durante el Mundial",
        "Estrategia según posición en Penca",
        "Revisión post-jornada",
        "Pronóstico de goles",
    ]
    for snippet in required_snippets:
        if snippet not in dashboard_html:
            errors.append(f"Dashboard no contiene bloque requerido: {snippet}.")
    if "15000" not in dashboard_html and "15.000" not in dashboard_html:
        errors.append("Dashboard no contiene bloque requerido: 15000 o 15.000.")
    if "&lt;section class=&quot;certainty-panel&quot;&gt;" in dashboard_html:
        errors.append("Dashboard escapó el HTML del módulo de máxima firmeza.")
    if "&lt;section class=&#34;panel competitive-penca-panel&#34;&gt;" in dashboard_html:
        errors.append("Dashboard escapó el HTML del módulo Penca competitivo.")
    if "&lt;section class=&#34;panel current-penca-panel&#34;" in dashboard_html:
        errors.append("Dashboard escapó el HTML del módulo de decisión dinámica.")
    if "&lt;section class=&#34;panel championship-penca-panel&#34;" in dashboard_html:
        errors.append("Dashboard escapó el HTML del módulo campeonato Penca.")
    if "&lt;section class=&#34;panel operating-system-panel&#34;" in dashboard_html:
        errors.append("Dashboard escapó el HTML del sistema operativo de predicción.")
    return errors


def audit_workflow_text(workflow_text: str, min_iterations: int, deep_workflow_text: str = "") -> List[str]:
    errors = []
    combined_workflow_text = f"{workflow_text}\n{deep_workflow_text}"
    required = [
        "cron: \"*/5 * * * *\"",
        "python3 -m unittest discover -s mundial_2026/tests",
        "audit-quiniela",
        "API_FOOTBALL_KEY",
        "cancel-in-progress: true",
    ]
    for snippet in required:
        if snippet not in combined_workflow_text:
            errors.append(f"Workflow no contiene requisito: {snippet}.")
    iteration_values = [int(value) for value in re.findall(r"--iterations\s+(\d+)", combined_workflow_text)]
    if not iteration_values or max(iteration_values) < min_iterations:
        errors.append(f"Workflow no contiene una llave con al menos {min_iterations} iteraciones.")
    return errors


def run_quiniela_audit(
    teams: Dict[str, Team],
    *,
    config_path: Path,
    bracket_json_path: Path,
    dashboard_html_path: Path,
    fixtures_path: Path,
    workflow_path: Path,
    deep_workflow_path: Optional[Path] = None,
    min_iterations: int = 15000,
) -> List[str]:
    errors: List[str] = []
    config = load_tournament_config(config_path)
    errors.extend(audit_tournament_draw(config, teams))
    if fixtures_path.exists():
        errors.extend(audit_fixtures_payload(read_fixtures(fixtures_path), teams))
    else:
        errors.append(f"No existe archivo de fixtures: {fixtures_path}.")
    if bracket_json_path.exists():
        errors.extend(audit_bracket_payload(load_bracket_json(bracket_json_path), teams, min_iterations))
    else:
        errors.append(f"No existe JSON de llave: {bracket_json_path}.")
    if dashboard_html_path.exists():
        errors.extend(audit_dashboard_html(dashboard_html_path.read_text()))
    else:
        errors.append(f"No existe dashboard HTML: {dashboard_html_path}.")
    if workflow_path.exists():
        deep_workflow_text = ""
        if deep_workflow_path and deep_workflow_path.exists():
            deep_workflow_text = deep_workflow_path.read_text()
        elif deep_workflow_path:
            errors.append(f"No existe workflow profundo: {deep_workflow_path}.")
        errors.extend(audit_workflow_text(workflow_path.read_text(), min_iterations, deep_workflow_text))
    else:
        errors.append(f"No existe workflow: {workflow_path}.")
    return errors


def command_audit_quiniela(args: argparse.Namespace, teams: Dict[str, Team]) -> None:
    ensure_minimum_monte_carlo_iterations(int(args.min_iterations), label="audit-quiniela --min-iterations")
    errors = run_quiniela_audit(
        teams,
        config_path=Path(args.config),
        bracket_json_path=Path(args.bracket_json_file),
        dashboard_html_path=Path(args.dashboard_html),
        fixtures_path=Path(args.fixtures),
        workflow_path=Path(args.workflow_file),
        deep_workflow_path=Path(args.deep_workflow_file) if args.deep_workflow_file else None,
        min_iterations=int(args.min_iterations),
    )
    if errors:
        print("AUDITORIA QUINIELA: FALLA")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print("AUDITORIA QUINIELA: OK")


def read_fixtures(path: Path) -> List[dict]:
    return calculate_read_fixtures(path)


def iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_team_state() -> dict:
    return package_default_team_state()


def normalize_team_state(state: Optional[dict]) -> dict:
    return package_normalize_team_state(state)


def initial_team_states(teams: Dict[str, Team]) -> Dict[str, dict]:
    return package_initial_team_states(teams)


def empty_persistent_payload(teams: Dict[str, Team]) -> dict:
    return {
        "meta": {
            "version": 4,
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
    if path.resolve() == STATE_FILE.resolve() and not path.exists() and LEGACY_STATE_FILE.exists():
        path = LEGACY_STATE_FILE
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
    print(f"  xG reciente ajustado por rival: {state['recent_xg_for_adj']:+.2f}")
    print(f"  xGA reciente ajustado por rival: {state['recent_xga_adj']:+.2f}")
    print(f"  Fortaleza reciente de rivales: {state['recent_opponent_strength']:+.2f}")
    print(f"  Firma tactica reciente: {state['tactical_signature']}")
    print(
        f"  Rasgos tacticos: posesion {state['style_possession']:+.2f} | verticalidad {state['style_verticality']:+.2f} | "
        f"presion {state['style_pressure']:+.2f} | calidad {state['style_chance_quality']:+.2f} | ritmo {state['style_tempo']:+.2f}"
    )
    print(
        f"  Rasgos avanzados live: xT {state['expected_threat_live']:+.2f} | pases prog {state['progressive_passes_live']:+.2f} | "
        f"conducciones prog {state['progressive_carries_live']:+.2f} | PPDA {state['ppda_live']:+.2f} | field tilt {state['field_tilt_live']:+.2f}"
    )
    print(
        f"  Matchup tactico live: presion {state['high_press_resistance_live']:+.2f} | bloque bajo {state['low_block_breaking_live']:+.2f} | "
        f"transicion defensiva {state['transition_defense_live']:+.2f} | aereo {state['aerial_matchup_advantage_live']:+.2f}"
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
    normalized = normalize_team_state(state) if state else {}
    return clamp(
        0.44 * float(normalized.get("style_attack_bias", 0.0))
        + 0.20 * float(normalized.get("expected_threat_live", 0.0))
        + 0.12 * float(normalized.get("progressive_passes_live", 0.0))
        + 0.10 * float(normalized.get("progressive_carries_live", 0.0))
        + 0.08 * float(normalized.get("low_block_breaking_live", 0.0))
        + 0.06 * float(normalized.get("high_press_resistance_live", 0.0)),
        -1.0,
        1.0,
    )


def tactical_defense_signal(state: Optional[dict]) -> float:
    normalized = normalize_team_state(state) if state else {}
    return clamp(
        0.48 * float(normalized.get("style_defense_bias", 0.0))
        + 0.24 * float(normalized.get("transition_defense_live", 0.0))
        + 0.12 * float(normalized.get("high_press_resistance_live", 0.0))
        + 0.10 * float(normalized.get("aerial_matchup_advantage_live", 0.0))
        - 0.06 * float(normalized.get("field_tilt_live", 0.0)),
        -1.0,
        1.0,
    )


def tactical_tempo_signal(state: Optional[dict]) -> float:
    normalized = normalize_team_state(state) if state else {}
    return clamp(
        0.55 * float(normalized.get("style_tempo", 0.0))
        + 0.20 * float(normalized.get("ppda_live", 0.0))
        + 0.15 * float(normalized.get("field_tilt_live", 0.0))
        + 0.10 * float(normalized.get("progressive_carries_live", 0.0)),
        -1.0,
        1.0,
    )


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
    team_a_name = fixture["team_a"]
    team_b_name = fixture["team_b"]
    profile_a = profile_for(teams[team_a_name])
    profile_b = profile_for(teams[team_b_name])
    state_a = normalize_team_state(states.get(fixture["team_a"], {}))
    state_b = normalize_team_state(states.get(fixture["team_b"], {}))
    stage = fixture_stage_name(fixture)
    knockout = stage != "group"
    default_rest_days = 4 if stage == "group" else 5
    live_substitutions_a = int(fixture.get("live_substitutions_a", 0) or 0)
    live_substitutions_b = int(fixture.get("live_substitutions_b", 0) or 0)
    substitution_impact_a = fixture.get("substitution_impact_a")
    substitution_impact_b = fixture.get("substitution_impact_b")
    if substitution_impact_a is None:
        substitution_impact_a = clamp((live_substitutions_a / 5.0) * (0.55 + 0.90 * profile_a.squad.bench_impact), 0.0, 1.0)
    if substitution_impact_b is None:
        substitution_impact_b = clamp((live_substitutions_b / 5.0) * (0.55 + 0.90 * profile_b.squad.bench_impact), 0.0, 1.0)
    lineup_a = lineup_intelligence(
        teams[team_a_name],
        starting_xi=tuple(fixture.get("starting_xi_a", []) or ()),
        unavailable_players=tuple(fixture.get("unavailable_players_a", []) or ()),
        lineup_confirmed=bool(fixture.get("lineup_confirmed_a", False)),
        lineup_changes=int(fixture.get("lineup_change_count_a", 0) or 0),
        goalkeeper_change=bool(fixture.get("goalkeeper_change_a", False)),
    )
    lineup_b = lineup_intelligence(
        teams[team_b_name],
        starting_xi=tuple(fixture.get("starting_xi_b", []) or ()),
        unavailable_players=tuple(fixture.get("unavailable_players_b", []) or ()),
        lineup_confirmed=bool(fixture.get("lineup_confirmed_b", False)),
        lineup_changes=int(fixture.get("lineup_change_count_b", 0) or 0),
        goalkeeper_change=bool(fixture.get("goalkeeper_change_b", False)),
    )

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
        heat_humidity_load=float(fixture.get("heat_humidity_load", fixture.get("weather_heat_humidity_load", 0.0)) or 0.0),
        time_zone_shift_a=float(fixture.get("time_zone_shift_a", teams[team_a_name].time_zone_shift) or 0.0),
        time_zone_shift_b=float(fixture.get("time_zone_shift_b", teams[team_b_name].time_zone_shift) or 0.0),
        venue_surface_adjustment_a=float(fixture.get("venue_surface_adjustment_a", teams[team_a_name].venue_surface_adjustment) or 0.0),
        venue_surface_adjustment_b=float(fixture.get("venue_surface_adjustment_b", teams[team_b_name].venue_surface_adjustment) or 0.0),
        travel_cluster_difficulty_a=float(fixture.get("travel_cluster_difficulty_a", teams[team_a_name].travel_cluster_difficulty) or 0.0),
        travel_cluster_difficulty_b=float(fixture.get("travel_cluster_difficulty_b", teams[team_b_name].travel_cluster_difficulty) or 0.0),
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
        market_total_line=goal_consensus_total_line(fixture),
        market_move_a=float(fixture.get("market_move_a", 0.0) or 0.0),
        market_move_draw=float(fixture.get("market_move_draw", 0.0) or 0.0),
        market_move_b=float(fixture.get("market_move_b", 0.0) or 0.0),
        lineup_confirmed_a=bool(fixture.get("lineup_confirmed_a", False)),
        lineup_confirmed_b=bool(fixture.get("lineup_confirmed_b", False)),
        lineup_change_count_a=int(fixture.get("lineup_change_count_a", 0)),
        lineup_change_count_b=int(fixture.get("lineup_change_count_b", 0)),
        starting_xi_a=tuple(str(name) for name in fixture.get("starting_xi_a", []) or ()),
        starting_xi_b=tuple(str(name) for name in fixture.get("starting_xi_b", []) or ()),
        lineup_strength_delta_a=lineup_a.overall_delta,
        lineup_strength_delta_b=lineup_b.overall_delta,
        lineup_attack_delta_a=lineup_a.attack_delta,
        lineup_attack_delta_b=lineup_b.attack_delta,
        lineup_defense_delta_a=lineup_a.defense_delta,
        lineup_defense_delta_b=lineup_b.defense_delta,
        lineup_goalkeeper_delta_a=lineup_a.goalkeeper_delta,
        lineup_goalkeeper_delta_b=lineup_b.goalkeeper_delta,
        lineup_coverage_a=lineup_a.coverage,
        lineup_coverage_b=lineup_b.coverage,
        lineup_intelligence_mode_a=lineup_a.mode,
        lineup_intelligence_mode_b=lineup_b.mode,
        starting_goalkeeper_a=fixture.get("starting_goalkeeper_a"),
        starting_goalkeeper_b=fixture.get("starting_goalkeeper_b"),
        goalkeeper_confirmed_a=bool(fixture.get("goalkeeper_confirmed_a", fixture.get("starting_goalkeeper_a"))),
        goalkeeper_confirmed_b=bool(fixture.get("goalkeeper_confirmed_b", fixture.get("starting_goalkeeper_b"))),
        goalkeeper_change_a=bool(fixture.get("goalkeeper_change_a", False)),
        goalkeeper_change_b=bool(fixture.get("goalkeeper_change_b", False)),
        live_substitutions_a=live_substitutions_a,
        live_substitutions_b=live_substitutions_b,
        substitution_impact_a=float(substitution_impact_a),
        substitution_impact_b=float(substitution_impact_b),
        referee_yellow_bias=float(fixture.get("referee_yellow_bias", 0.0) or 0.0),
        referee_red_bias=float(fixture.get("referee_red_bias", 0.0) or 0.0),
        referee_penalty_bias=float(fixture.get("referee_penalty_bias", 0.0) or 0.0),
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
            print("    Marcadores de penales más probables:")
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
            f"{prediction.model_stack.get('low_score_name')} + {prediction.model_stack.get('overdispersed_name')} + "
            f"{prediction.model_stack.get('bayesian_name')} + {prediction.model_stack.get('ml_name')} + "
            f"{prediction.model_stack.get('final_name')} "
            f"| coincidencia entre modelos {agreement:.1%}"
        )
    print("  Marcadores finales más probables:" if prediction.advance_a is not None else "  Marcadores más probables:")
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
    print("    Marcadores más frecuentes:")
    for score, prob in summary["top_scores"]:
        print(f"      {score}: {prob:.1%}")


def print_team_profile(team: Team) -> None:
    profile = profile_for(team)
    squad = profile.squad
    history = profile.history
    fifa_note = " (neutralizado si faltan puntos reales)" if fifa_points_are_proxy(team) else ""
    print(f"{team.name} ({pretty_status(team.status)})")
    print(f"  Elo: {team.elo:.0f}")
    print(f"  Puntos FIFA{fifa_note}: {profile.fifa_points:.1f}")
    print(f"  Ranking FIFA{fifa_note}: {profile.fifa_rank}")
    print(f"  Recursos base: {profile.resource_index:.2f}")
    print(f"  Población explícita: {team.population_millions if team.population_millions is not None else 'sin dato real; neutral'} | índice {profile.population_index:.2f}")
    print(f"  PIB explícito: {team.gdp_ppp_usd_billion if team.gdp_ppp_usd_billion is not None else 'sin dato real; neutral'} | índice {profile.gdp_index:.2f}")
    print(f"  Liga/minutos top: liga {profile.league_strength_index:.2f} | minutos top {team.top_league_minutes_share if team.top_league_minutes_share is not None else 'sin dato real; neutral'}")
    print(f"  Macro-recursos auditables: {profile.macro_resource_index:.2f}")
    print(f"  Historia mundialista: {profile.heritage_index:.2f}")
    print(f"  Títulos del mundo: {profile.world_cup_titles}")
    print(f"  Trayectoria futbolística: {profile.trajectory_index:.2f}")
    print(f"  Entrenador: {profile.coach_index:.2f} (neutral si no hay dato real auditable)")
    print(f"  Química/cohesión: {profile.chemistry_index:.2f}")
    print(f"  Moral base: {profile.morale_base:.2f}")
    print(f"  Flexibilidad táctica: {profile.tactical_flexibility:.2f}")
    print(f"  Resiliencia de viaje: {profile.travel_resilience:.2f}")
    print(f"  Geografía 2026: {profile.geography_2026_index:.2f}")
    print(f"  Ritmo de juego: {profile.tempo:.2f}")
    print(f"  Partidos históricos desde {history.history_start_year}: {history.matches_since_start}")
    print(f"  Puntos por partido desde {history.history_start_year}: {history.points_per_match:.2f}")
    print(f"  Puntos ponderados recientes desde {history.history_start_year}: {history.weighted_points_per_match:.2f}")
    print(f"  Rendimiento competitivo desde {history.history_start_year}: {history.competitive_points_per_match:.2f}")
    print(f"  Partidos de Mundial desde {history.history_start_year}: {history.world_cup_matches_since_start}")
    print(f"  Rendimiento en Mundiales desde {history.history_start_year}: {history.world_cup_points_per_match:.2f}")
    print(f"  Tandas de penales desde {history.history_start_year}: {history.shootout_matches_since_start}")
    print(f"  Eficacia en penales desde {history.history_start_year}: {history.shootout_win_rate:.2f}")
    print(f"  Fuerza histórica desde {history.history_start_year}: {history.strength_index:.2f}")
    print(f"  Ataque histórico desde {history.history_start_year}: {history.attack_index:.2f}")
    print(f"  Defensa histórica desde {history.history_start_year}: {history.defense_index:.2f}")
    print(f"  Rendimiento competitivo histórico: {history.competitive_index:.2f}")
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
    print(f"  Amarillas por jugador: {squad.yellow_rate:.2f} (neutral si no hay plantilla real)")
    print(f"  Rojas por jugador: {squad.red_rate:.3f} (neutral si no hay plantilla real)")
    print(f"  Disponibilidad: {squad.availability:.2f}")
    print(f"  Definición: {squad.finishing:.2f}")
    print(f"  Generación de ocasiones: {squad.shot_creation:.2f}")
    print(f"  Presión/recuperación: {squad.pressing:.2f}")
    print(f"  Carga reciente de minutos del XI: {squad.recent_minutes_load:.2f}")
    print(f"  Carga reciente de minutos del portero: {squad.goalkeeper_minutes_load:.2f}")
    print(f"  Impacto estimado del banquillo: {squad.bench_impact:.2f}")
    print(f"  Valor de plantilla explícito: {squad.squad_market_value:.1f} M EUR | índice mercado {squad.talent_market_index:.2f}")
    print(f"  Concentración top-5 valor: {squad.top_5_players_value_share:.2f} | profundidad valor banco/XI {squad.value_depth_ratio:.2f}")
    print(f"  Carga física pre-Mundial: {squad.physical_load_index:.2f} | minutos XI 12m {squad.total_minutes_last_12_months:.0f} | Mundial Clubes {squad.club_world_cup_minutes:.0f}")
    print(f"  Descanso medio último partido: {squad.days_since_last_match:.1f} días | propensión lesión {squad.injury_proneness:.2f}")
    print(f"  Estilo avanzado: xT {squad.expected_threat:.2f} | pases prog {squad.progressive_passes:.2f} | conducciones prog {squad.progressive_carries:.2f} | PPDA {squad.ppda:.2f} | field tilt {squad.field_tilt:.2f}")
    print(f"  Compatibilidad táctica: presión {squad.high_press_resistance:.2f} | bloque bajo {squad.low_block_breaking:.2f} | transición defensiva {squad.transition_defense:.2f} | aéreo {squad.aerial_matchup_advantage:.2f}")
    print(f"  Penales granulares: lanzadores {squad.penalty_taker_quality:.2f} | arquero penales {squad.goalkeeper_penalty_save_rate:.2f} | experiencia tanda {squad.shootout_pressure_experience:.2f} | matchup {squad.keeper_taker_strategy_matchup:.2f}")


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
        heat_humidity_load=max(teams[team_a_name].heat_humidity_load, teams[team_b_name].heat_humidity_load),
        time_zone_shift_a=teams[team_a_name].time_zone_shift,
        time_zone_shift_b=teams[team_b_name].time_zone_shift,
        venue_surface_adjustment_a=teams[team_a_name].venue_surface_adjustment,
        venue_surface_adjustment_b=teams[team_b_name].venue_surface_adjustment,
        travel_cluster_difficulty_a=teams[team_a_name].travel_cluster_difficulty,
        travel_cluster_difficulty_b=teams[team_b_name].travel_cluster_difficulty,
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
        ensure_minimum_monte_carlo_iterations(monte_carlo_iterations, label="predict --monte-carlo")
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
        heat_humidity_load=max(teams[team_a_name].heat_humidity_load, teams[team_b_name].heat_humidity_load),
        time_zone_shift_a=teams[team_a_name].time_zone_shift,
        time_zone_shift_b=teams[team_b_name].time_zone_shift,
        venue_surface_adjustment_a=teams[team_a_name].venue_surface_adjustment,
        venue_surface_adjustment_b=teams[team_b_name].venue_surface_adjustment,
        travel_cluster_difficulty_a=teams[team_a_name].travel_cluster_difficulty,
        travel_cluster_difficulty_b=teams[team_b_name].travel_cluster_difficulty,
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
        print("    Marcadores de penales más probables:")
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
    ensure_minimum_monte_carlo_iterations(args.iterations, label="playoffs --iterations", allow_zero=True)
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
        command_audit_quiniela=command_audit_quiniela,
        command_state_show=command_state_show,
        command_state_reset=command_state_reset,
        command_list_teams=command_list_teams,
        print_team_profile=print_team_profile,
        resolve_team_name=resolve_team_name,
    )


if __name__ == "__main__":
    main()
