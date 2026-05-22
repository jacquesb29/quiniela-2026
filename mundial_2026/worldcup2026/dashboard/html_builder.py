from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

TEMPLATE_DIR = Path(__file__).with_name("templates")

_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(enabled_extensions=("html",)),
)


def render_dashboard_html(context: Dict[str, Any]) -> str:
    template = _ENV.get_template("base.html")
    safe_keys = {
        "ticket_snapshot_html",
        "runtime_status_html",
        "score_dynamics_html",
        "landing_proof_html",
        "methodology_html",
        "calibration_depth_html",
        "prediction_power_html",
        "agentic_learning_html",
        "provider_matrix_html",
        "global_confidence_html",
        "max_certainty_html",
        "current_penca_decision_html",
        "competitive_penca_html",
        "strategy_html",
        "full_scorecard_html",
        "consensus_guardrail_html",
        "recent_changes_html",
        "backtesting_html",
        "bracket_visual_html",
        "cards_html",
        "bracket_html",
        "css",
    }
    payload: Dict[str, Any] = {
        "css": Markup((TEMPLATE_DIR / "dashboard.css").read_text()),
    }
    for key, value in context.items():
        payload[key] = Markup(value) if key in safe_keys else value
    return template.render(**payload)
