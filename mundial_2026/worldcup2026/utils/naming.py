from __future__ import annotations

import unicodedata


def normalize_team_text(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return "".join(char.lower() for char in ascii_text if char.isalnum())


def normalize_team_name(value: str, *, aliases: dict[str, str]) -> str:
    normalized = normalize_team_text(value)
    return aliases.get(normalized, str(value).strip())


def normalize_stage_name(raw_stage, *, stage_importance: dict[str, float], stage_aliases: dict[str, str]):
    if raw_stage is None:
        return None
    if raw_stage in stage_importance:
        return raw_stage
    lowered = str(raw_stage).strip().lower()
    alias = stage_aliases.get(lowered)
    if alias:
        return alias
    compact = lowered.replace(" ", "_")
    alias = stage_aliases.get(compact)
    if alias:
        return alias
    normalized = normalize_team_text(lowered)
    alias = stage_aliases.get(normalized)
    if alias:
        return alias
    raise SystemExit(f"Stage no soportado: {raw_stage}")


def resolve_team_name(raw_name: str, teams, *, aliases: dict[str, str]) -> str:
    if raw_name in teams:
        return raw_name

    normalized = normalize_team_text(raw_name)
    if normalized in aliases:
        return aliases[normalized]

    for team_name in teams:
        if normalize_team_text(team_name) == normalized:
            return team_name

    raise SystemExit(
        f"Equipo no encontrado: {raw_name}. Usa list-teams para ver los nombres disponibles."
    )


def resolve_optional_team_name(raw_name, teams, *, aliases: dict[str, str]):
    if raw_name is None:
        return None
    return resolve_team_name(raw_name, teams, aliases=aliases)


def resolve_venue_country(raw_name, teams, *, aliases: dict[str, str]):
    if raw_name is None:
        return None

    normalized = normalize_team_text(raw_name)
    host_countries = {team.host_country for team in teams.values() if team.host_country}
    for country in host_countries:
        if country and normalize_team_text(country) == normalized:
            return country

    aliased_team = aliases.get(normalized)
    if aliased_team and aliased_team in teams and teams[aliased_team].host_country:
        return teams[aliased_team].host_country

    return raw_name


def resolved_team_name_from_penalties(penalties_winner, team_a: str, team_b: str, *, aliases: dict[str, str]):
    if not penalties_winner:
        return None
    winner = str(penalties_winner).strip()
    if winner == "A":
        return team_a
    if winner == "B":
        return team_b
    resolved = normalize_team_name(winner, aliases=aliases)
    if resolved == team_a or winner == team_a:
        return team_a
    if resolved == team_b or winner == team_b:
        return team_b
    return None
