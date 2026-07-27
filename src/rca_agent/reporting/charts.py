from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import plotly.io as pio

from .common import _cause_display_name, _pretty
from .styles import PLOT_COLORS, SEVERITY_COLORS


def _plot_html(fig: go.Figure, height: int = 390) -> str:
    fig.update_layout(
        height=height,
        margin=dict(l=28, r=28, t=36, b=42),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color="#314158"),
        hoverlabel=dict(font_size=13),
    )
    return pio.to_html(
        fig,
        include_plotlyjs=False,
        full_html=False,
        config={"displayModeBar": False, "responsive": True},
    )


def _mini_bar_chart(values: dict[str, int], title: str) -> str:
    ordered = sorted(values.items(), key=lambda item: item[1])
    total = sum(values.values())
    labels = [_pretty(key) for key, _ in ordered]
    counts = [value for _, value in ordered]
    colors = [
        SEVERITY_COLORS.get(key, PLOT_COLORS[index % len(PLOT_COLORS)])
        for index, (key, _) in enumerate(ordered)
    ]
    fig = go.Figure(
        go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            marker_color=colors,
            text=[
                f"{value} ({(value / total * 100 if total else 0):.0f}%)"
                for value in counts
            ],
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=15)),
        showlegend=False,
        margin=dict(l=10, r=40, t=40, b=10),
        xaxis=dict(showgrid=False, visible=False),
        yaxis=dict(showgrid=False, automargin=True),
    )
    return _plot_html(fig, max(240, 34 * len(ordered) + 80))


def _bar_chart(values: dict[str, int], title: str) -> str:
    ordered = sorted(values.items(), key=lambda item: item[1])
    total = sum(values.values())
    fig = go.Figure(
        go.Bar(
            x=[value for _, value in ordered],
            y=[_cause_display_name(key) for key, _ in ordered],
            orientation="h",
            marker_color="#55aee6",
            text=[
                f"{value} ({(value / total * 100 if total else 0):.1f}%)"
                for _, value in ordered
            ],
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.update_layout(
        title=dict(text=title, x=0.5),
        showlegend=False,
        xaxis=dict(showgrid=True, gridcolor="#e5e9ef", title="Bugs"),
        yaxis=dict(showgrid=False, automargin=True),
    )
    return _plot_html(fig, max(430, 48 * len(ordered) + 120))


def _stacked_chart(
    matrix: dict[str, dict[str, int]], title: str, top_rows: int = 6
) -> str:
    rows = sorted(matrix, key=lambda key: sum(matrix[key].values()), reverse=True)[:top_rows]
    columns = sorted({column for row in rows for column in matrix[row]})
    fig = go.Figure()
    for index, column in enumerate(columns):
        color = SEVERITY_COLORS.get(column, PLOT_COLORS[index % len(PLOT_COLORS)])
        fig.add_bar(
            y=[_cause_display_name(row) for row in rows],
            x=[matrix[row].get(column, 0) for row in rows],
            name=_pretty(column),
            orientation="h",
            marker_color=color,
        )
    fig.update_layout(
        title=dict(text=title, x=0.5),
        barmode="stack",
        legend=dict(orientation="h", y=-0.2),
        xaxis=dict(showgrid=True, gridcolor="#e5e9ef", title="Bugs"),
        yaxis=dict(categoryorder="total ascending", automargin=True),
    )
    return _plot_html(fig, max(430, 60 * len(rows) + 150))


def _timeline_chart_plot(timelines: dict[str, dict[str, int]]) -> str:
    labels = {
        "created_by_day": "Criados",
        "detected_by_day": "Detectados",
        "resolved_by_day": "Resolvidos",
    }
    all_dates = sorted({date for values in timelines.values() for date in values})
    fig = go.Figure()
    for index, key in enumerate(labels):
        values = timelines.get(key, {})
        fig.add_bar(
            x=all_dates,
            y=[values.get(date, 0) for date in all_dates],
            name=labels[key],
            marker_color=PLOT_COLORS[index + 2],
        )
    fig.update_layout(
        title=dict(text="Evolução da qualidade por período", x=0.5),
        barmode="group",
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
        xaxis=dict(title="Data", showgrid=False),
        yaxis=dict(title="Total", showgrid=True, gridcolor="#e5e9ef"),
    )
    return _plot_html(fig, 460)


def _kpi_indicator(kpi: dict[str, Any]) -> str:
    value = kpi.get("value")
    if value is None:
        return '<div class="plot" style="display:grid;place-items:center"><strong>N/D</strong></div>'
    unit = kpi.get("unit")
    suffix = "%" if unit == "percent" else " h" if unit == "hours" else ""
    max_value = 100 if unit == "percent" else max(float(value) * 1.3, 1)
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=float(value),
            number=dict(suffix=suffix, font=dict(size=46, color="#0b172a")),
            gauge=dict(
                axis=dict(range=[0, max_value], visible=False),
                bar=dict(color="#2463eb"),
                bgcolor="#e7ecf3",
                borderwidth=0,
            ),
            domain=dict(x=[0.05, 0.95], y=[0.1, 0.9]),
        )
    )
    return _plot_html(fig, 210)
