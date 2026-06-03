from __future__ import annotations
import math
from worldcup2026.constants import (
    COACH_OVERRIDES,
    DISCIPLINE_BY_CONFEDERATION,
    DISCIPLINE_OVERRIDES,
    HISTORICAL_BY_CONFEDERATION,
    RESOURCE_BY_CONFEDERATION,
    RESOURCE_OVERRIDES,
    TEMPO_BY_CONFEDERATION,
    TRADITION_BONUS,
    TRAVEL_BY_CONFEDERATION,
    WORLD_CUP_TITLES,
)


def resource_index(team, *, clamp):
    base = RESOURCE_OVERRIDES.get(team.name, RESOURCE_BY_CONFEDERATION[team.confederation])
    base += 0.04 * ((team.elo - 1650.0) / 400.0)
    base += team.resource_bias
    if team.is_host:
        base += 0.05
    return clamp(base, 0.18, 1.00)


def population_index(team, *, resource_index_value, clamp):
    population = getattr(team, "population_millions", None)
    if population is None or population <= 0:
        return clamp(0.34 + 0.46 * resource_index_value, 0.18, 0.92)
    return clamp(math.log1p(float(population)) / math.log1p(1450.0), 0.18, 0.98)


def gdp_index(team, *, resource_index_value, clamp):
    gdp_per_capita = getattr(team, "gdp_per_capita_usd", None)
    gdp_ppp = getattr(team, "gdp_ppp_usd_billion", None)
    components = []
    if gdp_per_capita is not None and gdp_per_capita > 0:
        components.append(clamp(math.log1p(float(gdp_per_capita)) / math.log1p(95000.0), 0.18, 1.0))
    if gdp_ppp is not None and gdp_ppp > 0:
        components.append(clamp(math.log1p(float(gdp_ppp)) / math.log1p(32000.0), 0.18, 1.0))
    if not components:
        return clamp(0.30 + 0.52 * resource_index_value, 0.18, 0.96)
    return clamp(sum(components) / len(components), 0.18, 1.0)


def league_strength_index(team, *, resource_index_value, fifa_strength_index_value, clamp):
    explicit = getattr(team, "league_strength_index", None)
    if explicit is not None:
        return clamp(float(explicit), 0.12, 1.0)
    top_minutes = getattr(team, "top_league_minutes_share", None)
    top_minutes_component = clamp(float(top_minutes), 0.0, 1.0) if top_minutes is not None else resource_index_value
    return clamp(
        0.34 * resource_index_value
        + 0.30 * fifa_strength_index_value
        + 0.24 * top_minutes_component
        + 0.12 * (0.65 if team.confederation == "UEFA" else 0.52 if team.confederation == "CONMEBOL" else 0.38),
        0.14,
        0.98,
    )


def macro_resource_index(*, resource_index_value, population_index_value, gdp_index_value, league_strength_index_value, clamp):
    return clamp(
        0.32 * resource_index_value
        + 0.22 * population_index_value
        + 0.24 * gdp_index_value
        + 0.22 * league_strength_index_value,
        0.16,
        1.0,
    )


def geography_2026_index(team, *, travel_resilience_value, resource_index_value, clamp):
    heat = clamp(float(getattr(team, "heat_humidity_load", 0.0) or 0.0), 0.0, 1.0)
    timezone = clamp(abs(float(getattr(team, "time_zone_shift", 0.0) or 0.0)) / 8.0, 0.0, 1.0)
    surface = clamp(abs(float(getattr(team, "venue_surface_adjustment", 0.0) or 0.0)), 0.0, 1.0)
    cluster = clamp(float(getattr(team, "travel_cluster_difficulty", 0.0) or 0.0), 0.0, 1.0)
    return clamp(
        0.56 * travel_resilience_value
        + 0.16 * resource_index_value
        + 0.12 * (1.0 - heat)
        + 0.06 * (1.0 - timezone)
        + 0.05 * (1.0 - surface)
        + 0.05 * (1.0 - cluster),
        0.18,
        0.98,
    )


def heritage_index(team, *, historical_snapshot, clamp, centered):
    history = historical_snapshot(team)
    titles = WORLD_CUP_TITLES.get(team.name, 0)
    base = HISTORICAL_BY_CONFEDERATION[team.confederation]
    base += TRADITION_BONUS.get(team.name, 0.0)
    base += 0.05 * titles
    base += 0.18 * centered(history.strength_index)
    base += 0.14 * centered(history.world_cup_index)
    base += 0.06 * centered(history.competitive_index)
    base += 0.02 if team.status == "qualified" else 0.0
    base += team.heritage_bias
    return clamp(base, 0.10, 1.00)


def trajectory_index(team, *, historical_snapshot, heritage_index_value, resource_index_value, clamp):
    history = historical_snapshot(team)
    value = 0.28
    value += 0.30 * heritage_index_value
    value += 0.18 * resource_index_value
    value += 0.14 * history.strength_index
    value += 0.08 * history.competitive_index
    value += 0.05 * history.attack_index
    value += 0.05 * history.defense_index
    value += 0.06 * clamp((team.elo - 1650.0) / 350.0, -0.2, 0.4)
    value += 0.03 if team.status == "qualified" else 0.0
    return clamp(value, 0.12, 1.00)


def coach_index(team, *, historical_snapshot, heritage_index_value, resource_index_value, clamp):
    history = historical_snapshot(team)
    value = 0.32
    value += 0.26 * heritage_index_value
    value += 0.14 * resource_index_value
    value += 0.06 * history.world_cup_index
    value += 0.04 * history.competitive_index
    value += 0.05 * clamp((team.elo - 1650.0) / 300.0, -0.3, 0.5)
    value += COACH_OVERRIDES.get(team.name, 0.0)
    value += team.coach_bias
    return clamp(value, 0.20, 0.98)


def chemistry_index(team, *, coach_index_value, heritage_index_value, resource_index_value, clamp):
    value = 0.36
    value += 0.22 * coach_index_value
    value += 0.14 * heritage_index_value
    value += 0.08 * resource_index_value
    value += team.chemistry_bias
    return clamp(value, 0.20, 0.98)


def discipline_proxy(team, *, clamp):
    value = 0.56
    value += DISCIPLINE_BY_CONFEDERATION[team.confederation]
    value += DISCIPLINE_OVERRIDES.get(team.name, 0.0)
    value += team.discipline_bias
    return clamp(value, 0.18, 0.96)


def tactical_flexibility(*, coach_index_value, resource_index_value, heritage_index_value, clamp):
    value = 0.34
    value += 0.24 * coach_index_value
    value += 0.10 * resource_index_value
    value += 0.06 * heritage_index_value
    return clamp(value, 0.20, 0.96)


def morale_base(*, chemistry_index_value, heritage_index_value, coach_index_value, clamp):
    value = 0.38
    value += 0.18 * chemistry_index_value
    value += 0.10 * heritage_index_value
    value += 0.06 * coach_index_value
    return clamp(value, 0.20, 0.95)


def travel_resilience(team, *, resource_index_value, chemistry_index_value, clamp):
    value = TRAVEL_BY_CONFEDERATION[team.confederation]
    value += 0.08 * resource_index_value
    value += 0.05 * chemistry_index_value
    value += 0.04 if team.is_host else 0.0
    return clamp(value, 0.35, 0.98)


def tempo_proxy(team, *, trajectory_index_value, coach_index_value, clamp, centered):
    value = TEMPO_BY_CONFEDERATION[team.confederation]
    value += 0.03 * centered(trajectory_index_value)
    value += 0.02 * centered(coach_index_value)
    return clamp(value, 0.32, 0.78)
