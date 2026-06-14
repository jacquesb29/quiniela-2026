#!/usr/bin/env python3
"""Run one audited pre-tournament Monte Carlo pass.

This runner does not change model logic. It calls the current
`modelo_quiniela_2026` functions and aggregates tournament, bracket and Penca
outputs in one pass so 100k simulations do not need to be run twice.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import modelo_quiniela_2026 as model  # noqa: E402


ADVANCED_STAGES = {"round32", "round16", "quarterfinal", "semifinal", "final", "champion"}


def _empty_group_summary(config: dict) -> dict[str, dict[str, dict[str, float]]]:
    groups = config.get("groups", {})
    return {
        group_name: {
            team_name: {
                "qualified": 0,
                "winner": 0,
                "top2": 0,
                "third": 0,
                "fourth": 0,
                "avg_points": 0.0,
                "avg_goal_diff": 0.0,
                "avg_goals_for": 0.0,
            }
            for team_name in teams
        }
        for group_name, teams in groups.items()
    }


def _merge_numeric_dict(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict):
            child = target.setdefault(key, {})
            _merge_numeric_dict(child, value)
        else:
            target[key] = target.get(key, 0) + value


def _merge_tournament_summary(target: dict[str, dict], source: dict[str, dict]) -> None:
    model.merge_tournament_summary(target, source)


def _merge_group_summary(target: dict[str, dict], source: dict[str, dict]) -> None:
    _merge_numeric_dict(target, source)


def _merge_bracket_aggregate(target: dict[str, dict], source: dict[str, dict]) -> None:
    model.merge_bracket_aggregate(target, source)


def _update_tournament_summary(summary: dict[str, dict], result: dict, teams: dict[str, Any]) -> None:
    participants = set(result["participants"])
    for team_name in participants:
        stats = summary[team_name]
        state = model.ensure_state(result["states"], team_name)
        stats["appear"] += 1
        stats["avg_group_points"] += state["group_points"]
        stats["avg_goals_for"] += state["goals_for"]
        stats["avg_goals_against"] += state["goals_against"]

    for group_table in result["standings"].values():
        summary[group_table[0]["team"]]["group_winner"] += 1

    for team_name, stage in result["stage_reached"].items():
        stats = summary[team_name]
        if stage in ADVANCED_STAGES:
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


def _update_group_summary(group_summary: dict[str, dict], result: dict) -> None:
    for group_name, table in result["standings"].items():
        group_bucket = group_summary.setdefault(group_name, {})
        for pos, row in enumerate(table, start=1):
            team_name = row["team"]
            team_bucket = group_bucket.setdefault(
                team_name,
                {
                    "qualified": 0,
                    "winner": 0,
                    "top2": 0,
                    "third": 0,
                    "fourth": 0,
                    "avg_points": 0.0,
                    "avg_goal_diff": 0.0,
                    "avg_goals_for": 0.0,
                },
            )
            if result["stage_reached"].get(team_name) in ADVANCED_STAGES:
                team_bucket["qualified"] += 1
            if pos == 1:
                team_bucket["winner"] += 1
            if pos <= 2:
                team_bucket["top2"] += 1
            if pos == 3:
                team_bucket["third"] += 1
            if pos == 4:
                team_bucket["fourth"] += 1
            team_bucket["avg_points"] += float(row.get("points", 0.0))
            team_bucket["avg_goal_diff"] += float(row.get("goal_diff", 0.0))
            team_bucket["avg_goals_for"] += float(row.get("goals_for", 0.0))


def _update_bracket_aggregate(bracket_aggregate: dict[str, dict], result: dict) -> None:
    for match_id, match_result in result["bracket_matches"].items():
        aggregate = bracket_aggregate[match_id]
        outcome_key = (match_result["team_a"], match_result["team_b"], match_result["winner"])
        aggregate["outcomes"][outcome_key] = aggregate["outcomes"].get(outcome_key, 0) + 1
        aggregate["winner"][match_result["winner"]] = aggregate["winner"].get(match_result["winner"], 0) + 1
        aggregate["went_extra_time"] += 1 if match_result.get("went_extra_time") else 0
        aggregate["went_penalties"] += 1 if match_result.get("went_penalties") else 0
        if (
            match_result.get("went_penalties")
            and match_result.get("penalty_score_a") is not None
            and match_result.get("penalty_score_b") is not None
        ):
            penalty_key = (int(match_result["penalty_score_a"]), int(match_result["penalty_score_b"]))
            aggregate["penalty_scores"][penalty_key] = aggregate["penalty_scores"].get(penalty_key, 0) + 1


def _worker(batch_size: int, seed: int, project_dir: str) -> dict[str, Any]:
    os.chdir(project_dir)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    import modelo_quiniela_2026 as worker_model

    teams = worker_model.load_teams()
    config = worker_model.load_tournament_config(worker_model.TOURNAMENT_CONFIG_FILE)
    worker_model.seed_all_rng(seed)

    tournament_summary = worker_model.empty_tournament_summary(teams)
    bracket_aggregate = worker_model.empty_bracket_aggregate(worker_model.bracket_match_order())
    group_summary = _empty_group_summary(config)

    for _ in range(batch_size):
        result = worker_model.simulate_tournament_iteration(teams, config, initial_payload=None)
        _update_tournament_summary(tournament_summary, result, teams)
        _update_group_summary(group_summary, result)
        _update_bracket_aggregate(bracket_aggregate, result)

    return {
        "iterations": batch_size,
        "tournament_summary": tournament_summary,
        "group_summary": group_summary,
        "bracket_aggregate": bracket_aggregate,
    }


def _team_rows(summary: dict[str, dict], iterations: int) -> list[dict[str, Any]]:
    rows = []
    for team_name, stats in summary.items():
        appear_count = max(stats["appear"], 1)
        rows.append(
            {
                "team": team_name,
                "appear": stats["appear"] / iterations,
                "advance_group": stats["advance_group"] / iterations,
                "reach_round16": stats["reach_round16"] / iterations,
                "reach_quarterfinal": stats["reach_quarterfinal"] / iterations,
                "reach_semifinal": stats["reach_semifinal"] / iterations,
                "reach_final": stats["reach_final"] / iterations,
                "third_place": stats["third_place"] / iterations,
                "fourth_place": stats["fourth_place"] / iterations,
                "champion": stats["champion"] / iterations,
                "group_winner": stats["group_winner"] / iterations,
                "avg_group_points": stats["avg_group_points"] / appear_count,
                "avg_goals_for": stats["avg_goals_for"] / appear_count,
                "avg_goals_against": stats["avg_goals_against"] / appear_count,
            }
        )
    return sorted(rows, key=lambda row: (row["champion"], row["reach_final"], row["reach_semifinal"], row["team"]), reverse=True)


def _group_rows(group_summary: dict[str, dict], iterations: int) -> list[dict[str, Any]]:
    rows = []
    for group_name in sorted(group_summary):
        for team_name, stats in group_summary[group_name].items():
            rows.append(
                {
                    "group": group_name,
                    "team": team_name,
                    "qualified": stats["qualified"] / iterations,
                    "winner": stats["winner"] / iterations,
                    "top2": stats["top2"] / iterations,
                    "third": stats["third"] / iterations,
                    "fourth": stats["fourth"] / iterations,
                    "avg_points": stats["avg_points"] / iterations,
                    "avg_goal_diff": stats["avg_goal_diff"] / iterations,
                    "avg_goals_for": stats["avg_goals_for"] / iterations,
                }
            )
    return sorted(rows, key=lambda row: (row["group"], -row["qualified"], -row["winner"], row["team"]))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _build_bracket_payload(bracket_aggregate: dict[str, dict], iterations: int, workers: int) -> dict[str, Any]:
    payload = {
        "updated_at": model.iso_timestamp(),
        "iterations": iterations,
        "workers": workers,
        "simulation_mode": "pre_tournament_100k_ignore_state",
        "random_seed": 2026,
        "scoreline_engine": "ensamble_no_solo_poisson_bayes_dinamico_v2",
        "bracket_recalculated_from_scoreline_ensemble": True,
        "recalculation_policy": (
            "Corte pre-torneo manual de 100.000 simulaciones. Durante el Mundial, "
            "solo deben actualizarse datos de estado, resultados, lesiones, sanciones, "
            "alineaciones, descanso, fatiga, grupo y mercado; no pesos ni metodologia salvo bug real."
        ),
        "matches": {
            match_id: model.structured_match_projection(match_id, aggregate, iterations)
            for match_id, aggregate in bracket_aggregate.items()
        },
    }
    payload["matches"] = model.coherent_bracket_matches(payload)
    return payload


def _build_bracket_markdown(bracket_aggregate: dict[str, dict], iterations: int) -> str:
    sections = [
        f"# Llave actual proyectada | iteraciones={iterations}",
        "",
        "## Dieciseisavos de final",
    ]
    for match_id in [match["id"] for match in model.R32_MATCHES]:
        sections.extend(model.format_match_projection(match_id, bracket_aggregate[match_id], iterations))
        sections.append("")
    sections.append("## Octavos de final")
    for match_id, _, _ in model.KNOCKOUT_MATCHES["round16"]:
        sections.extend(model.format_match_projection(match_id, bracket_aggregate[match_id], iterations))
        sections.append("")
    sections.append("## Cuartos de final")
    for match_id, _, _ in model.KNOCKOUT_MATCHES["quarterfinal"]:
        sections.extend(model.format_match_projection(match_id, bracket_aggregate[match_id], iterations))
        sections.append("")
    sections.append("## Semifinales")
    for match_id, _, _ in model.KNOCKOUT_MATCHES["semifinal"]:
        sections.extend(model.format_match_projection(match_id, bracket_aggregate[match_id], iterations))
        sections.append("")
    sections.append("## Partido por el tercer puesto")
    sections.extend(model.format_match_projection("M104", bracket_aggregate["M104"], iterations))
    sections.append("")
    sections.append("## Final")
    sections.extend(model.format_match_projection("M103", bracket_aggregate["M103"], iterations))
    sections.append("")
    return "\n".join(sections)


def _score_label(team_a: str, team_b: str, score: str) -> str:
    left, _, right = str(score).partition("-")
    return f"{team_a} {left.strip()} - {right.strip()} {team_b}"


def _penca_rows(bracket_payload: dict[str, Any], top_scores: int) -> list[dict[str, Any]]:
    teams = model.load_teams()
    states = model.empty_persistent_payload(teams)["teams"]
    fixtures = model.read_fixtures(PROJECT_DIR / "fixtures_live_2026.json")
    fixture_entries = model.dashboard_fixture_entries(fixtures, teams, states, top_scores)
    seen_match_ids = [entry.get("match_id") for entry in fixture_entries if entry.get("match_id")]
    entries = fixture_entries + model.projected_bracket_entries(fixtures, bracket_payload, teams, states, top_scores, seen_match_ids)

    rows = []
    for entry in entries:
        prediction = entry["prediction"]
        top_penca = model.penca_ovacion_top_score(prediction)
        exact_score, exact_prob = prediction.exact_scores[0] if prediction.exact_scores else (top_penca["score"], 0.0)
        result_options = {
            "win_a": float(prediction.win_a),
            "draw": float(prediction.draw),
            "win_b": float(prediction.win_b),
        }
        result_key = max(result_options, key=result_options.get)
        result_label = {
            "win_a": f"Gana {prediction.team_a}",
            "draw": "Empate",
            "win_b": f"Gana {prediction.team_b}",
        }[result_key]
        rows.append(
            {
                "title": entry["title"],
                "stage": entry["stage_label"],
                "match_id": entry.get("match_id") or "",
                "team_a": prediction.team_a,
                "team_b": prediction.team_b,
                "model_result": result_label,
                "model_result_prob": result_options[result_key],
                "model_score": _score_label(prediction.team_a, prediction.team_b, exact_score),
                "model_score_prob": float(exact_prob),
                "penca_score": _score_label(prediction.team_a, prediction.team_b, str(top_penca["score"])),
                "penca_expected_points": float(top_penca.get("expected_points", 0.0) or 0.0),
                "penca_exact_prob": float(top_penca.get("exact_prob", 0.0) or 0.0),
                "penca_difference_prob": float(top_penca.get("difference_prob", 0.0) or 0.0),
                "penca_result_prob": float(top_penca.get("result_prob", 0.0) or 0.0),
                "projection": bool(entry.get("projection")),
            }
        )
    return sorted(rows, key=lambda row: (row["penca_expected_points"], row["penca_result_prob"], row["penca_exact_prob"]), reverse=True)


def _dark_horse_rows(bracket_payload: dict[str, Any], top_scores: int) -> list[dict[str, Any]]:
    teams = model.load_teams()
    states = model.empty_persistent_payload(teams)["teams"]
    fixtures = model.read_fixtures(PROJECT_DIR / "fixtures_live_2026.json")
    fixture_entries = model.dashboard_fixture_entries(fixtures, teams, states, top_scores)
    seen_match_ids = [entry.get("match_id") for entry in fixture_entries if entry.get("match_id")]
    entries = fixture_entries + model.projected_bracket_entries(fixtures, bracket_payload, teams, states, top_scores, seen_match_ids)
    candidates = model.dark_horse_candidates(bracket_payload, entries)
    rows = []
    for item in candidates:
        rows.append({key: item.get(key, "") for key in sorted(item.keys())})
    return rows


def _valuation_rows(bracket_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = model.consensus_adjusted_champion_probabilities(bracket_payload, entries=None)
    overvalued = []
    undervalued = []
    for row in rows:
        item = {
            "team": row["team"],
            "model_prob": row["model_prob"],
            "consensus_prob": row["consensus_prob"],
            "adjusted_prob": row["adjusted_prob"],
            "delta_model_minus_consensus": row["delta"],
        }
        if row["delta"] < -0.01:
            overvalued.append(item)
        if row["delta"] > 0.01:
            undervalued.append(item)
    overvalued.sort(key=lambda item: item["delta_model_minus_consensus"])
    undervalued.sort(key=lambda item: item["delta_model_minus_consensus"], reverse=True)
    return overvalued, undervalued


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--top-scores", type=int, default=8)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.iterations <= 0:
        raise SystemExit("--iterations debe ser positivo")
    chunks = []
    remaining = args.iterations
    index = 0
    while remaining > 0:
        size = min(args.chunk_size, remaining)
        chunks.append((size, args.seed + index * 1009, str(PROJECT_DIR)))
        remaining -= size
        index += 1

    start = time.perf_counter()
    teams = model.load_teams()
    config = model.load_tournament_config(model.TOURNAMENT_CONFIG_FILE)
    tournament_summary = model.empty_tournament_summary(teams)
    bracket_aggregate = model.empty_bracket_aggregate(model.bracket_match_order())
    group_summary = _empty_group_summary(config)

    completed = 0
    print(
        f"Pre-torneo Monte Carlo | iteraciones={args.iterations} | "
        f"workers={args.workers} | chunk_size={args.chunk_size} | seed={args.seed}",
        flush=True,
    )
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_worker, size, seed, project_dir) for size, seed, project_dir in chunks]
        for future in as_completed(futures):
            result = future.result()
            completed += int(result["iterations"])
            _merge_tournament_summary(tournament_summary, result["tournament_summary"])
            _merge_group_summary(group_summary, result["group_summary"])
            _merge_bracket_aggregate(bracket_aggregate, result["bracket_aggregate"])
            elapsed = max(time.perf_counter() - start, 0.001)
            rate = completed / elapsed
            eta = (args.iterations - completed) / rate if rate > 0 else math.nan
            print(
                f"Progreso 100k: {completed}/{args.iterations} "
                f"({completed / args.iterations:.1%}) | {rate:.1f} iter/s | ETA {eta/60:.1f} min",
                flush=True,
            )

    out = args.output_dir
    team_rows = _team_rows(tournament_summary, args.iterations)
    group_rows = _group_rows(group_summary, args.iterations)
    bracket_payload = _build_bracket_payload(bracket_aggregate, args.iterations, args.workers)
    bracket_md = _build_bracket_markdown(bracket_aggregate, args.iterations)
    penca_rows = _penca_rows(bracket_payload, args.top_scores)
    dark_rows = _dark_horse_rows(bracket_payload, args.top_scores)
    overvalued_rows, undervalued_rows = _valuation_rows(bracket_payload)

    summary_payload = {
        "version": "pre_tournament_100k_v1",
        "updated_at": model.iso_timestamp(),
        "iterations": args.iterations,
        "random_seed": args.seed,
        "methodology_lock": "No cambia pesos ni metodologia; usa simulate_tournament_iteration actual con initial_payload=None.",
        "champion_top10": team_rows[:10],
        "finalist_top10": sorted(team_rows, key=lambda row: (row["reach_final"], row["champion"]), reverse=True)[:10],
        "semifinalist_top12": sorted(team_rows, key=lambda row: (row["reach_semifinal"], row["reach_final"]), reverse=True)[:12],
        "group_qualifiers": group_rows,
        "dark_horses": dark_rows,
        "overvalued_teams": overvalued_rows,
        "undervalued_teams": undervalued_rows,
    }

    (out / "pre_tournament_100k_summary.json").write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    (out / "pre_tournament_100k_bracket.json").write_text(json.dumps(bracket_payload, indent=2), encoding="utf-8")
    (out / "pre_tournament_100k_bracket.md").write_text(bracket_md, encoding="utf-8")
    (out / "llave_actual_2026.json").write_text(json.dumps(bracket_payload, indent=2), encoding="utf-8")
    (out / "llave_actual_2026.md").write_text(bracket_md, encoding="utf-8")

    _write_csv(out / "pre_tournament_100k_team_probabilities.csv", team_rows)
    _write_csv(out / "pre_tournament_100k_group_qualifiers.csv", group_rows)
    _write_csv(out / "pre_tournament_100k_penca_picks.csv", penca_rows)
    _write_csv(out / "pre_tournament_100k_dark_horses.csv", dark_rows)
    _write_csv(out / "pre_tournament_100k_overvalued_teams.csv", overvalued_rows)
    _write_csv(out / "pre_tournament_100k_undervalued_teams.csv", undervalued_rows)

    elapsed = time.perf_counter() - start
    print(f"Listo en {elapsed/60:.1f} min")
    print("Top campeon:", ", ".join(f"{row['team']} {row['champion']:.1%}" for row in team_rows[:5]))
    print("Top Penca:", ", ".join(f"{row['title']} -> {row['penca_score']}" for row in penca_rows[:5]))


if __name__ == "__main__":
    main()
