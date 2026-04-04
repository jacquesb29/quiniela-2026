from __future__ import annotations

import argparse
from pathlib import Path


def build_parser(
    *,
    state_file: str,
    tournament_config_file: str,
    bracket_file: str,
    bracket_json_file: str,
    dashboard_html_file: str,
    dashboard_md_file: str,
    fixtures_template_file: str,
):
    parser = argparse.ArgumentParser(description="Modelo probabilistico para quinielas del Mundial 2026.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    predict = subparsers.add_parser("predict", help="Predice un partido puntual.")
    predict.add_argument("team_a")
    predict.add_argument("team_b")
    predict.add_argument("--neutral", action="store_true", default=False)
    predict.add_argument("--home-team", default=None)
    predict.add_argument("--venue-country", default=None)
    predict.add_argument("--rest-a", type=int, default=None)
    predict.add_argument("--rest-b", type=int, default=None)
    predict.add_argument("--injuries-a", type=float, default=None)
    predict.add_argument("--injuries-b", type=float, default=None)
    predict.add_argument("--altitude", type=int, default=None)
    predict.add_argument("--travel-a", type=float, default=None)
    predict.add_argument("--travel-b", type=float, default=None)
    predict.add_argument("--knockout", action="store_true")
    predict.add_argument("--stage", default=None, help="Etapa real del partido. Acepta group, round32, round16, round8, round4, semifinal, final, third_place.")
    predict.add_argument("--morale-a", type=float, default=None)
    predict.add_argument("--morale-b", type=float, default=None)
    predict.add_argument("--yellow-cards-a", type=int, default=None)
    predict.add_argument("--yellow-cards-b", type=int, default=None)
    predict.add_argument("--red-suspensions-a", type=int, default=None)
    predict.add_argument("--red-suspensions-b", type=int, default=None)
    predict.add_argument("--group", default=None)
    predict.add_argument("--group-points-a", type=int, default=None)
    predict.add_argument("--group-points-b", type=int, default=None)
    predict.add_argument("--group-goal-diff-a", type=int, default=None)
    predict.add_argument("--group-goal-diff-b", type=int, default=None)
    predict.add_argument("--group-matches-played-a", type=int, default=None)
    predict.add_argument("--group-matches-played-b", type=int, default=None)
    predict.add_argument("--weather-stress", type=float, default=None)
    predict.add_argument("--importance", type=float, default=None)
    predict.add_argument("--top-scores", type=int, default=6)
    predict.add_argument("--show-factors", action="store_true")
    predict.add_argument("--monte-carlo", type=int, default=0)
    predict.add_argument("--seed", type=int, default=None)
    predict.add_argument("--state-file", default=state_file)
    predict.add_argument("--ignore-state", action="store_true")

    power_table = subparsers.add_parser("power-table", help="Tabla base de fuerza y gol esperado vs rival promedio.")
    power_table.add_argument("--only-confirmed", action="store_true")

    playoffs = subparsers.add_parser("playoffs", help="Probabilidades de clasificar desde repechajes.")
    playoffs.add_argument("--iterations", type=int, default=10000)

    fixtures = subparsers.add_parser("fixtures", help="Lee un JSON de partidos y genera predicciones.")
    fixtures.add_argument("path")
    fixtures.add_argument("--top-scores", type=int, default=5)
    fixtures.add_argument("--show-factors", action="store_true")
    fixtures.add_argument("--state-file", default=state_file)
    fixtures.add_argument("--reset-state", action="store_true")
    fixtures.add_argument("--no-save-state", action="store_true")

    simulate = subparsers.add_parser("simulate-tournament", help="Simula el Mundial completo con Monte Carlo a partir de un cuadro en JSON.")
    simulate.add_argument("--config", default=tournament_config_file, help="Ruta al JSON del cuadro del torneo.")
    simulate.add_argument("--iterations", type=int, default=5000)
    simulate.add_argument("--top", type=int, default=20)
    simulate.add_argument("--full", action="store_true")
    simulate.add_argument("--seed", type=int, default=None)
    simulate.add_argument("--workers", type=int, default=0, help="Procesos para Monte Carlo. 0 = auto.")
    simulate.add_argument("--progress-every", type=int, default=0)
    simulate.add_argument("--state-file", default=state_file)
    simulate.add_argument("--ignore-state", action="store_true")

    project = subparsers.add_parser("project-bracket", help="Genera una llave proyectada actual en Markdown usando Monte Carlo.")
    project.add_argument("--config", default=tournament_config_file, help="Ruta al JSON del cuadro del torneo.")
    project.add_argument("--iterations", type=int, default=15000)
    project.add_argument("--seed", type=int, default=None)
    project.add_argument("--workers", type=int, default=0, help="Procesos para Monte Carlo. 0 = auto.")
    project.add_argument("--progress-every", type=int, default=0)
    project.add_argument("--output", default=bracket_file)
    project.add_argument("--json-output", default=bracket_json_file)
    project.add_argument("--state-file", default=state_file)
    project.add_argument("--ignore-state", action="store_true")

    dashboard = subparsers.add_parser("project-dashboard", help="Genera un reporte actual con llave y probabilidades por partido.")
    dashboard.add_argument("--fixtures", default=fixtures_template_file)
    dashboard.add_argument("--bracket-file", default=bracket_file)
    dashboard.add_argument("--bracket-json-file", default=bracket_json_file)
    dashboard.add_argument("--output-html", default=dashboard_html_file)
    dashboard.add_argument("--output-md", default=dashboard_md_file)
    dashboard.add_argument("--top-scores", type=int, default=5)
    dashboard.add_argument("--state-file", default=state_file)

    score_prob = subparsers.add_parser("score-prob", help="Da la probabilidad exacta de un marcador especifico.")
    score_prob.add_argument("team_a")
    score_prob.add_argument("team_b")
    score_prob.add_argument("goals_a", type=int)
    score_prob.add_argument("goals_b", type=int)
    score_prob.add_argument("--neutral", action="store_true", default=False)
    score_prob.add_argument("--home-team", default=None)
    score_prob.add_argument("--venue-country", default=None)
    score_prob.add_argument("--knockout", action="store_true")
    score_prob.add_argument("--stage", default=None)
    score_prob.add_argument("--group", default=None)
    score_prob.add_argument("--state-file", default=state_file)
    score_prob.add_argument("--ignore-state", action="store_true")

    profile_parser = subparsers.add_parser("team-profile", help="Muestra todas las variables internas de una seleccion.")
    profile_parser.add_argument("team")

    state_show = subparsers.add_parser("state-show", help="Muestra el estado persistente que se actualiza automaticamente.")
    state_show.add_argument("--team", default=None)
    state_show.add_argument("--state-file", default=state_file)
    state_show.add_argument("--full", action="store_true")

    state_reset = subparsers.add_parser("state-reset", help="Reinicia el archivo de estado persistente del torneo.")
    state_reset.add_argument("--state-file", default=state_file)

    subparsers.add_parser("list-teams", help="Lista las selecciones cargadas.")
    return parser


def dispatch_command(
    args,
    teams,
    *,
    parser,
    command_predict,
    command_score_prob,
    command_power_table,
    command_playoffs,
    command_fixtures,
    command_simulate_tournament,
    command_project_bracket,
    command_project_dashboard,
    command_state_show,
    command_state_reset,
    command_list_teams,
    print_team_profile,
    resolve_team_name,
):
    if args.command == "predict":
        command_predict(args, teams)
    elif args.command == "score-prob":
        command_score_prob(args, teams)
    elif args.command == "power-table":
        command_power_table(args, teams)
    elif args.command == "playoffs":
        command_playoffs(args, teams)
    elif args.command == "fixtures":
        command_fixtures(args, teams)
    elif args.command == "simulate-tournament":
        command_simulate_tournament(args, teams)
    elif args.command == "project-bracket":
        command_project_bracket(args, teams)
    elif args.command == "project-dashboard":
        command_project_dashboard(args, teams)
    elif args.command == "state-show":
        command_state_show(args, teams)
    elif args.command == "state-reset":
        command_state_reset(args, teams)
    elif args.command == "list-teams":
        command_list_teams(teams)
    elif args.command == "team-profile":
        team_name = resolve_team_name(args.team, teams)
        print_team_profile(teams[team_name])
    else:
        parser.error("Comando no soportado.")
