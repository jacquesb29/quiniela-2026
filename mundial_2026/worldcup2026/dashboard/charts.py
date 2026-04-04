from __future__ import annotations

import html
from typing import Mapping, Sequence


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _format_pct(value: float) -> str:
    return f"{float(value):.1%}"


def render_chart_grid(cards: Sequence[str]) -> str:
    visible_cards = [card for card in cards if card]
    if not visible_cards:
        return ""
    return f"<div class=\"chart-grid\">{''.join(visible_cards)}</div>"


def render_rank_chart(
    title: str,
    rows: Sequence[Mapping[str, object]],
    *,
    tone: str = "accent",
    description: str | None = None,
    empty_title: str = "Sin datos comparables",
    empty_body: str = "Todavia no hay suficiente informacion para dibujar este grafico.",
) -> str:
    note_html = f"<p class=\"chart-note\">{html.escape(description)}</p>" if description else ""
    if not rows:
        return (
            "<article class=\"chart-card\">"
            f"<h3>{html.escape(title)}</h3>"
            f"{note_html}"
            "<div class=\"chart-empty\">"
            f"<strong>{html.escape(empty_title)}</strong>"
            f"<span>{html.escape(empty_body)}</span>"
            "</div>"
            "</article>"
        )

    rendered_rows = []
    for row in rows:
        label = html.escape(str(row.get("label", "")))
        detail = html.escape(str(row.get("detail", "")))
        value = _clamp01(float(row.get("value", 0.0)))
        value_text = html.escape(str(row.get("value_text", _format_pct(value))))
        rendered_rows.append(
            "<div class=\"bar-row\">"
            "<div class=\"bar-head\">"
            f"<strong>{label}</strong>"
            f"<span>{value_text}</span>"
            "</div>"
            "<div class=\"bar-track\">"
            f"<span class=\"bar-fill tone-{html.escape(tone)}\" style=\"width:{value * 100:.1f}%\"></span>"
            "</div>"
            f"<p class=\"bar-caption\">{detail}</p>"
            "</div>"
        )

    return (
        "<article class=\"chart-card\">"
        f"<h3>{html.escape(title)}</h3>"
        f"{note_html}"
        "<div class=\"bar-chart\">"
        f"{''.join(rendered_rows)}"
        "</div>"
        "</article>"
    )


def render_dual_bar_chart(
    title: str,
    rows: Sequence[Mapping[str, object]],
    *,
    description: str | None = None,
    primary_label: str = "Modelo",
    secondary_label: str = "Real",
    primary_tone: str = "accent",
    secondary_tone: str = "gold",
    empty_title: str = "Sin buckets comparables",
    empty_body: str = "Todavia no hay suficientes partidos cerrados para dibujar esta comparacion.",
) -> str:
    note_html = f"<p class=\"chart-note\">{html.escape(description)}</p>" if description else ""
    legend_html = (
        "<div class=\"chart-legend\">"
        f"<span><i class=\"legend-dot tone-{html.escape(primary_tone)}\"></i>{html.escape(primary_label)}</span>"
        f"<span><i class=\"legend-dot tone-{html.escape(secondary_tone)}\"></i>{html.escape(secondary_label)}</span>"
        "</div>"
    )
    if not rows:
        return (
            "<article class=\"chart-card\">"
            f"<h3>{html.escape(title)}</h3>"
            f"{note_html}"
            f"{legend_html}"
            "<div class=\"chart-empty\">"
            f"<strong>{html.escape(empty_title)}</strong>"
            f"<span>{html.escape(empty_body)}</span>"
            "</div>"
            "</article>"
        )

    rendered_rows = []
    for row in rows:
        label = html.escape(str(row.get("label", "")))
        primary = _clamp01(float(row.get("primary", 0.0)))
        secondary = _clamp01(float(row.get("secondary", 0.0)))
        sample = row.get("sample")
        sample_text = f"n={int(sample)}" if sample is not None else ""
        detail = html.escape(
            str(
                row.get(
                    "detail",
                    f"{primary_label} {_format_pct(primary)} | {secondary_label} {_format_pct(secondary)}",
                )
            )
        )
        rendered_rows.append(
            "<div class=\"dual-bar-row\">"
            "<div class=\"dual-bar-head\">"
            f"<strong>{label}</strong>"
            f"<span>{html.escape(sample_text)}</span>"
            "</div>"
            "<div class=\"dual-bar-stack\">"
            "<div class=\"mini-bar\">"
            f"<span class=\"mini-fill tone-{html.escape(primary_tone)}\" style=\"width:{primary * 100:.1f}%\"></span>"
            "</div>"
            "<div class=\"mini-bar\">"
            f"<span class=\"mini-fill tone-{html.escape(secondary_tone)}\" style=\"width:{secondary * 100:.1f}%\"></span>"
            "</div>"
            "</div>"
            f"<p class=\"bar-caption\">{detail}</p>"
            "</div>"
        )

    return (
        "<article class=\"chart-card\">"
        f"<h3>{html.escape(title)}</h3>"
        f"{note_html}"
        f"{legend_html}"
        "<div class=\"dual-chart\">"
        f"{''.join(rendered_rows)}"
        "</div>"
        "</article>"
    )
