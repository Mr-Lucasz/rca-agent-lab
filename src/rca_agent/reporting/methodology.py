from __future__ import annotations

import html
from dataclasses import dataclass

import plotly.graph_objects as go

from .charts import _plot_html


@dataclass(frozen=True)
class MethodologyCard:
    heading: str
    subtitle: str
    chart_title: str
    values: tuple[float, ...]
    labels: tuple[str, ...]
    colors: tuple[str, ...]
    insight_html: str
    x_max: int | None = None


# The AI completely defines the content for these methodology cards at runtime.
# No hardcoded texts!


def _methodological_analysis_v2(analysis: dict) -> str:
    methodology_reviews = analysis.get("narrative", {}).get("methodology_reviews", [])
    if not isinstance(methodology_reviews, list) or not methodology_reviews:
        return ""

    default_colors = ["#45c97a", "#ffbf00", "#f45b69", "#3b82f6", "#8746b8", "#42c2b8"]
    
    cards_html = []
    for review in methodology_reviews:
        heading = html.escape(str(review.get("heading", "")), quote=True)
        subtitle = html.escape(str(review.get("subtitle", "")), quote=True)
        chart_title = str(review.get("chart_title", ""))
        labels = [str(item) for item in review.get("labels", [])]
        values = review.get("values", [])
        insight = html.escape(str(review.get("insight", "")), quote=True)
        detailed = html.escape(
            str(review.get("detailed_analysis", "")), quote=True
        )
        
        dynamic_insight = f"{insight}<br><br>{detailed}" if detailed else insight
        
        # Build the dataclass on the fly from the JSON data!
        # Re-use colors based on index
        colors = tuple(default_colors[i % len(default_colors)] for i in range(len(labels)))
        card = MethodologyCard(
            heading=heading,
            subtitle=subtitle,
            chart_title=chart_title,
            values=tuple(values),
            labels=tuple(labels),
            colors=colors,
            insight_html=dynamic_insight
        )
        
        cards_html.append(_render_card(card, dynamic_insight))

    cards = "".join(cards_html)
    return f"""
<section class="section" id="metodologia">
    <h2 class="section-title">Análise de KPIs: Metodologia Sistêmica</h2>
    <p class="section-subtitle">Métricas externas incluídas somente quando a revisão registra suas evidências.</p>
    {cards}
</section>
"""


def _render_card(card: MethodologyCard, dynamic_insight: str) -> str:
    return f"""
    <article class="slide">
        <div class="slide-head">
            <h3>{card.heading}</h3>
            <p>{card.subtitle}</p>
        </div>
        <div class="chart-two">
            <div class="chart-box" style="margin-top:-20px">{_render_chart(card)}</div>
            <div class="copy-block" style="padding-top:10px">
                <b>Insight Analítico</b>
                <p>{dynamic_insight}</p>
            </div>
        </div>
    </article>
"""


def _render_chart(card: MethodologyCard) -> str:
    figure = go.Figure(
        go.Bar(
            x=card.values,
            y=card.labels,
            orientation="h",
            marker_color=card.colors,
        )
    )
    layout: dict[str, object] = {
        "title": {"text": card.chart_title, "x": 0.5},
        "margin": {"l": 10, "r": 10, "t": 30, "b": 10},
    }
    if card.x_max is not None:
        layout["xaxis"] = {"range": [0, card.x_max]}
    figure.update_layout(**layout)
    return _plot_html(figure, 210)
