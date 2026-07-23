from __future__ import annotations

import csv
import html
import json
import math
import re
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

from .config import load_yaml
from .utils import UNKNOWN, utc_now

FIELD_LABELS = {
    "severity": "Severidade",
    "environment": "Ambiente",
    "affected_module": "Módulo",
    "bug_type": "Tipo do defeito",
    "root_cause_category": "Categoria RCA reportada",
    "team": "Time",
    "version": "Versão",
}

VALUE_LABELS = {
    "critical": "Crítica",
    "high": "Alta",
    "medium": "Média",
    "low": "Baixa",
    "production": "Produção",
    "staging": "Staging",
    "qa": "QA",
    "unknown": "Não informado",
    "true": "Sim",
    "false": "Não",
}

SYSTEMIC_RULES = {
    "reopen": "As reaberturas estão altas e sugerem correções que aliviam o sintoma, mas não fecham o mecanismo por completo.",
    "production": "Boa parte do volume já escapa para produção, sinal de prevenção insuficiente antes do deploy.",
    "concentration": "O volume está concentrado em poucos pontos do produto, o que facilita atacar prevenção de forma mais cirúrgica.",
    "coverage": "As notas de QA e Dev estão ricas o bastante para sustentar hipóteses melhores do que um RCA genérico de template.",
}

# Defensive fixes for corrupted text fragments that can appear when review text
# was authored with a mismatched terminal/code-page encoding.
_TEXT_FIXUPS = {
    "Ap?s": "Após",
    "Identifica??o": "Identificação",
    "identifica??o": "identificação",
    "Oscila??o": "Oscilação",
    "Predom?nio": "Predomínio",
    "Recorr?ncia": "Recorrência",
    "a??es": "ações",
    "an?lise": "análise",
    "ass?ncrono": "assíncrono",
    "can?nica": "canônica",
    "cen?rios": "cenários",
    "confian?a": "confiança",
    "corre??es": "correções",
    "cr?tico": "crítico",
    "degrada??o": "degradação",
    "espec?ficos": "específicos",
    "evid?ncia": "evidência",
    "evid?ncias": "evidências",
    "execu??o": "execução",
    "experi?ncia": "experiência",
    "fam?lia": "família",
    "hip?teses": "hipóteses",
    "implementa??o": "implementação",
    "integra??o": "integração",
    "interrup??o": "interrupção",
    "investiga??o": "investigação",
    "m?dulos": "módulos",
    "n?o": "não",
    "normaliza??o": "normalização",
    "padr?o": "padrão",
    "pol?tica": "política",
    "por?m": "porém",
    "priorit?rios": "prioritários",
    "prioriza??o": "priorização",
    "prov?vel": "provável",
    "re?ne": "reúne",
    "recorr?ncia": "recorrência",
    "reincid?ncia": "reincidência",
    "relat?rio": "relatório",
    "renderiza??o": "renderização",
    "repeti??o": "repetição",
    "revis?o": "revisão",
    "s?o": "são",
    "seguran?a": "segurança",
    "sem?ntica": "semântica",
    "sincroniza??o": "sincronização",
    "t?cnicas": "técnicas",
    "transi??o": "transição",
    "valida??es": "validações",
    "valida??o": "validação",
}


def _repair_text(value: Any) -> str:
    text = str(value)
    # Common mojibake path: UTF-8 bytes interpreted as Latin-1.
    if any(marker in text for marker in ("Ã", "â", "€", "™")):
        try:
            text = text.encode("latin-1").decode("utf-8")
        except UnicodeError:
            pass
    if "?" in text:
        for broken, fixed in _TEXT_FIXUPS.items():
            text = text.replace(broken, fixed)
        # Preserve intentional question marks and only flag suspicious leftovers.
        if "??" in text:
            text = re.sub(r"\?{2,}", "?", text)
    return text


def _repair_structure(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _repair_structure(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_repair_structure(item) for item in value]
    if isinstance(value, str):
        return _repair_text(value)
    return value


def _root_cause_catalog() -> dict[str, Any]:
    return load_yaml("root-causes.yml").get("canonical", {})


def write_normalized_csv(path: Path, analysis: dict[str, Any]) -> None:
    bugs = analysis["bugs"]
    cluster_by_id = {item["cluster_id"]: item for item in analysis["clusters"]}
    hypotheses_by_cluster: dict[str, list[dict[str, Any]]] = {}
    actions_by_cluster: dict[str, list[dict[str, Any]]] = {}
    for item in analysis["hypotheses"]:
        hypotheses_by_cluster.setdefault(item["cluster_id"], []).append(item)
    for item in analysis["actions"]:
        actions_by_cluster.setdefault(item["cluster_id"], []).append(item)
    rows: list[dict[str, Any]] = []
    for bug in bugs:
        cluster = cluster_by_id.get(bug["cluster_id"], {})
        row = dict(bug)
        row.update(
            {
                "cluster_name": cluster.get("name", UNKNOWN),
                "cluster_investigation_score": cluster.get("investigation_score", UNKNOWN),
                "hypothesis_ids": "|".join(
                    item["hypothesis_id"]
                    for item in hypotheses_by_cluster.get(bug["cluster_id"], [])
                )
                or UNKNOWN,
                "hypothesis_summary": " | ".join(
                    item["statement"]
                    for item in hypotheses_by_cluster.get(bug["cluster_id"], [])
                )
                or UNKNOWN,
                "action_ids": "|".join(
                    item["action_id"] for item in actions_by_cluster.get(bug["cluster_id"], [])
                )
                or UNKNOWN,
                "requires_human_review": "true",
            }
        )
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _escape(value: Any) -> str:
    return html.escape(_repair_text(value), quote=True)


def _display(value: Any, unit: str = "") -> str:
    if value is None:
        return "N/D"
    if unit == "percent":
        return f"{value}%"
    if unit == "hours":
        return f"{value} h"
    return _repair_text(value)


def _pretty(value: Any) -> str:
    text = str(value)
    return VALUE_LABELS.get(text, text.replace("_", " ").replace("-", " ").title())


def _cause_explanation(cause: str) -> str:
    catalog = _root_cause_catalog()
    entry = catalog.get(cause, catalog.get("unknown", {}))
    lens = entry.get("analysis_lens", {})
    return lens.get(
        "likely_mechanism",
        "Ainda não há evidência suficiente para reduzir o problema a um único mecanismo sem risco de simplificação indevida.",
    )


def _cause_display_name(cause: str) -> str:
    catalog = _root_cause_catalog()
    entry = catalog.get(cause, catalog.get("unknown", {}))
    return entry.get("display_name", _pretty(cause))


def _summary_sentence(analysis: dict[str, Any]) -> str:
    narrative = analysis.get("narrative", {})
    if narrative.get("executive_summary"):
        return str(narrative["executive_summary"])
    profiles = analysis["metrics"].get("root_cause_profiles", [])
    total = len(analysis["bugs"])
    if not profiles:
        return f"A amostra tem {total} bugs, mas ainda não trouxe sinal suficiente para priorizar uma causa dominante."
    first = profiles[0]
    second = profiles[1] if len(profiles) > 1 else None
    sentence = (
        f"A leitura geral mostra {total} bugs com concentração em {_cause_display_name(first['root_cause_category'])} "
        f"({first['count']} casos; {first['share_percent']}%)."
    )
    if second and second.get("share_percent"):
        sentence += f" O segundo bloco de peso está em {_cause_display_name(second['root_cause_category'])} ({second['count']} casos; {second['share_percent']}%)."
    return sentence


def _systemic_patterns(analysis: dict[str, Any]) -> list[str]:
    narrative = analysis.get("narrative", {})
    if narrative.get("systemic_patterns"):
        return list(narrative["systemic_patterns"])
    metrics = analysis["metrics"]
    kpis = {item["id"]: item for item in metrics.get("kpis", [])}
    profiles = metrics.get("root_cause_profiles", [])
    patterns: list[str] = []
    reopen_rate = kpis.get("reopen_rate", {}).get("value")
    if reopen_rate is not None and reopen_rate >= 20:
        patterns.append(SYSTEMIC_RULES["reopen"])
    production_escape = kpis.get("production_escape_rate", {}).get("value")
    if production_escape is not None and production_escape >= 50:
        patterns.append(SYSTEMIC_RULES["production"])
    top_module_share = kpis.get("top_module_share", {}).get("value")
    if top_module_share is not None and top_module_share >= 20:
        patterns.append(SYSTEMIC_RULES["concentration"])
    coverage = kpis.get("causal_coverage_rate", {}).get("value")
    if coverage is not None and coverage >= 60:
        patterns.append(SYSTEMIC_RULES["coverage"])
    if profiles:
        patterns.append(_cause_explanation(profiles[0]["root_cause_category"]))
    return patterns[:5]


def _root_cause_cards_from_analysis(analysis: dict[str, Any]) -> str:
    profiles = analysis["metrics"].get("root_cause_profiles", [])
    if not profiles:
        return '<p class="muted">Sem categorias suficientes para consolidar uma leitura por causa.</p>'
    narrative_reviews = {
        item["root_cause_category"]: item
        for item in analysis.get("narrative", {}).get("root_cause_reviews", [])
    }
    cards: list[str] = []
    for profile in profiles[:5]:
        review = narrative_reviews.get(profile["root_cause_category"], {})
        modules = ", ".join(_pretty(item) for item in profile.get("top_modules", [])) or "Sem módulo dominante"
        detection = "N/D" if profile.get("avg_detect_hours") is None else f"{profile['avg_detect_hours']} h"
        title = review.get("title", _cause_display_name(profile["root_cause_category"]))
        summary = review.get("summary", _cause_explanation(profile["root_cause_category"]))
        symptom_pattern = review.get("symptom_pattern")
        likely_mechanism = review.get("likely_mechanism")
        business_impact = review.get("business_impact")
        why_it_persists = review.get("why_it_persists")
        evidence_refs = review.get("evidence_ids", [])
        narrative_block = ""
        if any([symptom_pattern, likely_mechanism, business_impact, why_it_persists]):
            narrative_block = (
                '<div class="cause-narrative">'
                + (f'<p><b>Sintoma recorrente:</b> {_escape(symptom_pattern)}</p>' if symptom_pattern else "")
                + (f'<p><b>Mecanismo provável:</b> {_escape(likely_mechanism)}</p>' if likely_mechanism else "")
                + (f'<p><b>Impacto:</b> {_escape(business_impact)}</p>' if business_impact else "")
                + (f'<p><b>Por que persiste:</b> {_escape(why_it_persists)}</p>' if why_it_persists else "")
                + (
                    f'<p class="cause-evidence"><b>Evidências-chave:</b> {_escape(", ".join(evidence_refs))}</p>'
                    if evidence_refs
                    else ""
                )
                + '</div>'
            )
        cards.append(
            '<article class="cause-card">'
            f'<div class="cause-top"><span class="eyebrow">{_escape(profile["count"])} bugs · {_escape(profile.get("share_percent"))}%</span>'
            f'<h3>{_escape(title)}</h3></div>'
            f'<p>{_escape(summary)}</p>'
            f'{narrative_block}'
            '<div class="cause-metrics">'
            f'<span><b>Severidade que mais aparece:</b> {_escape(_pretty(profile["predominant_severity"]))}</span>'
            f'<span><b>Módulos mais afetados:</b> {_escape(modules)}</span>'
            f'<span><b>Tempo médio de detecção:</b> {_escape(detection)}</span>'
            f'<span><b>Reaberturas:</b> {_escape(profile["reopened_total"])}</span>'
            f'<span><b>Em produção:</b> {_escape(profile["production_total"])}</span>'
            f'<span><b>Amostra:</b> {_escape(", ".join(profile["sample_bug_ids"]))}</span>'
            '</div></article>'
        )
    return "".join(cards)


def _bars(values: dict[str, int], total: int) -> str:
    if not values:
        return '<p class="muted">Sem dados.</p>'
    maximum = max(values.values()) or 1
    return "".join(
        f'<div class="bar-row"><span title="{_escape(label)}">{_escape(_pretty(label))}</span>'
        f'<div class="track"><i style="width:{round(value / maximum * 100, 1)}%"></i></div>'
        f'<strong>{value}</strong><small>{round(value / total * 100, 1) if total else 0}%</small></div>'
        for label, value in sorted(values.items(), key=lambda item: (-item[1], item[0]))
    )


def _line_chart(series: dict[str, dict[str, int]]) -> str:
    dates = sorted({date for values in series.values() for date in values})
    if not dates:
        return '<p class="muted">Sem datas válidas para tendência.</p>'
    width = 820
    height = 250
    left = 48
    top = 18
    chart_width = width - left - 24
    chart_height = height - top - 42
    max_value = max((max(values.values()) for values in series.values() if values), default=1)
    palette = ["#0f766e", "#e76f51", "#2a9d8f"]
    grid = "".join(
        f'<line x1="{left}" y1="{top + (chart_height / 4) * index:.1f}" '
        f'x2="{left + chart_width}" y2="{top + (chart_height / 4) * index:.1f}" />'
        for index in range(5)
    )
    labels = "".join(
        f'<text x="{left + (chart_width / max(len(dates) - 1, 1)) * index:.1f}" y="{height - 12}" '
        f'text-anchor="middle">{_escape(date[5:])}</text>'
        for index, date in enumerate(dates)
    )
    y_labels = "".join(
        f'<text x="{left - 10}" y="{top + chart_height - (chart_height / 4) * index + 4:.1f}" '
        f'text-anchor="end">{round(max_value / 4 * index)}</text>'
        for index in range(5)
    )
    paths = []
    legend = []
    for index, (label, values) in enumerate(series.items()):
        points = []
        for point_index, date in enumerate(dates):
            value = values.get(date, 0)
            x = left + (chart_width / max(len(dates) - 1, 1)) * point_index
            y = top + chart_height - (value / max_value * chart_height if max_value else 0)
            points.append(f"{x:.1f},{y:.1f}")
        color = palette[index % len(palette)]
        paths.append(f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{" ".join(points)}" />')
        legend.append(f'<span><i style="background:{color}"></i>{_escape(label)}</span>')
    return (
        '<div class="chart-shell">'
        f'<svg viewBox="0 0 {width} {height}" class="svg-chart line-chart" role="img" '
        'aria-label="Tendência temporal dos bugs">'
        f'<g class="grid">{grid}</g>'
        f'<g class="y-labels">{y_labels}</g>'
        f'<g class="x-labels">{labels}</g>'
        f'<g class="paths">{"".join(paths)}</g>'
        '</svg>'
        f'<div class="legend">{"".join(legend)}</div>'
        '</div>'
    )


def _heatmap(values: dict[str, dict[str, int]], row_label: str, column_label: str) -> str:
    columns = sorted({column for row in values.values() for column in row})
    if not values or not columns:
        return '<p class="muted">Sem dados suficientes.</p>'
    maximum = max(max(row.values()) for row in values.values()) or 1
    header = ''.join(f'<span class="heat-cell head">{_escape(_pretty(column))}</span>' for column in columns)
    rows: list[str] = []
    for label, row in values.items():
        cells = []
        for column in columns:
            value = row.get(column, 0)
            opacity = 0.14 + (value / maximum) * 0.86 if value else 0.08
            cells.append(
                f'<span class="heat-cell" style="--strength:{opacity:.2f}" title="{_escape(_pretty(label))} × {_escape(_pretty(column))}: {value}">{value}</span>'
            )
        rows.append(
            f'<div class="heat-row"><span class="heat-label">{_escape(_pretty(label))}</span>{"".join(cells)}</div>'
        )
    return (
        f'<div class="heatmap" aria-label="{_escape(row_label)} por {_escape(column_label)}">'
        f'<div class="heat-row head"><span class="heat-label">{_escape(row_label)}</span>{header}</div>'
        f'{"".join(rows)}</div>'
    )


def _term_cloud(values: dict[str, int]) -> str:
    if not values:
        return '<p class="muted">Sem termos suficientes para destacar.</p>'
    maximum = max(values.values()) or 1
    return '<div class="term-cloud">' + ''.join(
        f'<span style="font-size:{0.9 + (count / maximum) * 1.4:.2f}rem">{_escape(term)}</span>'
        for term, count in values.items()
    ) + '</div>'


def _kpi_card(kpi: dict[str, Any]) -> str:
    total = kpi.get("context_total") or 0
    numerator = kpi.get("context_value") or 0
    if kpi.get("unit") == "percent" and kpi.get("value") is not None:
        progress = min(max(float(kpi["value"]), 0.0), 100.0)
    elif total:
        progress = min(max(float(numerator) / float(total) * 100, 0.0), 100.0)
    else:
        progress = 100.0
    limitation = kpi.get("limitations", [])
    footnote = limitation[0] if limitation else ""
    return (
        '<article class="kpi">'
        f'<span>{_escape(kpi["label"])}</span>'
        f'<strong>{_display(kpi["value"], kpi["unit"])}</strong>'
        f'<div class="kpi-meter"><i style="width:{progress:.1f}%"></i></div>'
        f'<small>n={_escape(kpi["sample_size"])} · {_escape(kpi["formula"])}</small>'
        f'<p>{_escape(footnote)}</p>'
        '</article>'
    )


def render_html(analysis: dict[str, Any]) -> str:
    total = len(analysis["bugs"])
    gate = analysis["quality_gate"]
    kpi_cards = "".join(_kpi_card(kpi) for kpi in analysis["metrics"]["kpis"])
    distribution_order = ["severity", "affected_module", "environment"]
    distribution_cards = "".join(
        f'<article class="panel chart"><h3>{_escape(FIELD_LABELS.get(field, field.replace("_", " ").title()))}</h3>'
        f'{_bars(values, total)}</article>'
        for field in distribution_order
        for values in [analysis["metrics"]["distributions"].get(field, {})]
    )
    timelines = analysis["metrics"].get("timelines", {})
    timeline_chart = _line_chart(
        {
            "Criados": timelines.get("created_by_day", {}),
            "Detectados": timelines.get("detected_by_day", {}),
            "Resolvidos": timelines.get("resolved_by_day", {}),
        }
    )
    cross_meta = analysis["metrics"].get("cross_tab_meta", {})
    cross_order = ["severity_by_module", "root_cause_by_bug_type"]
    cross_sections = "".join(
        f'<article class="panel heat-panel"><h3>{_escape(meta.get("label", name))}</h3>'
        f'{_heatmap(values, meta.get("row_label", "Linha"), meta.get("column_label", "Coluna"))}</article>'
        for name in cross_order
        for values in [analysis["metrics"]["cross_tabs"].get(name, {})]
        for meta in [cross_meta.get(name, {})]
    )
    note_terms = analysis["metrics"].get("note_terms", {})
    highlights = analysis["metrics"].get("highlights", {})
    summary_sentence = _summary_sentence(analysis)
    systemic_patterns = _systemic_patterns(analysis)
    highlight_items = list(analysis.get("narrative", {}).get("key_findings", [])) or [
        f"{highlights.get('production', {}).get('count', 0)} de {highlights.get('production', {}).get('total', 0)} bugs conhecidos escaparam para produção.",
        f"{highlights.get('reopened', {}).get('count', 0)} bugs foram reabertos, sinal de correção parcial ou validação incompleta.",
        f"O módulo mais pressionado é {_pretty(highlights.get('top_module', {}).get('label', UNKNOWN))}, que concentra {highlights.get('top_module', {}).get('count', 0)} casos.",
        f"A leitura causal mais forte hoje está em {_cause_display_name(highlights.get('top_root_cause', {}).get('label', UNKNOWN))}, mas ainda depende de validação técnica.",
    ]
    header_title = analysis.get("narrative", {}).get("headline") or "Da recorrência observada à barreira verificável."
    evidence_by_id = {item["evidence_id"]: item for item in analysis["evidence"]}
    hypothesis_by_cluster: dict[str, list[dict[str, Any]]] = {}
    actions_by_hypothesis: dict[str, list[dict[str, Any]]] = {}
    for item in analysis["hypotheses"]:
        hypothesis_by_cluster.setdefault(item["cluster_id"], []).append(item)
    for item in analysis["actions"]:
        actions_by_hypothesis.setdefault(item["hypothesis_id"], []).append(item)

    cluster_sections: list[str] = []
    for cluster in analysis["clusters"]:
        hypotheses_html: list[str] = []
        for hypothesis in hypothesis_by_cluster.get(cluster["cluster_id"], []):
            supporting = "".join(
                f'<li><code>{_escape(identifier)}</code> '
                f'{_escape(evidence_by_id.get(identifier, {}).get("excerpt", "evidência ausente"))}</li>'
                for identifier in hypothesis["supporting_evidence_ids"]
            )
            counter = "".join(
                f'<li><code>{_escape(identifier)}</code> '
                f'{_escape(evidence_by_id.get(identifier, {}).get("excerpt", "evidência ausente"))}</li>'
                for identifier in hypothesis["counter_evidence_ids"]
            ) or "<li>Nenhuma contraevidência registrada; isto é uma lacuna, não confirmação.</li>"
            questions = "".join(f"<li>{_escape(item)}</li>" for item in hypothesis["confirmation_questions"])
            missing = "".join(f"<li>{_escape(item)}</li>" for item in hypothesis["missing_information"])
            action_cards = "".join(
                f'<article class="action {_escape(action["barrier_type"])}">'
                f'<span class="eyebrow">{_escape(action["barrier_type"])}</span>'
                f'<h5>{_escape(action["statement"])}</h5>'
                f'<p><b>Dono:</b> {_escape(action["owner_role"])} · <b>Horizonte:</b> {_escape(action["horizon"])}</p>'
                f'<p><b>Métrica:</b> {_escape(action["success_metric"])}</p>'
                f'<p><b>Risco residual:</b> {_escape(action["residual_risk"])}</p></article>'
                for action in actions_by_hypothesis.get(hypothesis["hypothesis_id"], [])
            )
            hypotheses_html.append(
                f'<article class="hypothesis" id="{_escape(hypothesis["hypothesis_id"])}">'
                f'<div class="hyp-head"><div><span class="eyebrow">{_escape(hypothesis["hypothesis_id"])}</span>'
                f'<h4>{_escape(hypothesis["statement"])}</h4></div>'
                f'<span class="badge confidence-{_escape(hypothesis["confidence"])}">{_escape(hypothesis["confidence"])}</span></div>'
                f'<p><b>Mecanismo:</b> {_escape(hypothesis["mechanism"])}</p>'
                f'<p><b>Racional:</b> {_escape(hypothesis["confidence_rationale"])}</p>'
                f'<div class="split"><div><h5>Evidências favoráveis</h5><ul>{supporting}</ul></div>'
                f'<div><h5>Contraevidências</h5><ul>{counter}</ul></div></div>'
                f'<div class="split"><div><h5>Informação ausente</h5><ul>{missing}</ul></div>'
                f'<div><h5>Perguntas para confirmar/refutar</h5><ul>{questions}</ul></div></div>'
                f'<p class="validation"><b>Método de validação:</b> {_escape(hypothesis["validation_method"])}</p>'
                f'<div class="actions">{action_cards}</div></article>'
            )
        terms = ", ".join(cluster["shared_characteristics"]["distinctive_terms"]) or "sem termos distintivos"
        cluster_sections.append(
            f'<details class="cluster" {"open" if cluster["prioritized"] else ""}>'
            f'<summary><div><span class="eyebrow">{_escape(cluster["cluster_id"])} · rank {cluster["priority_rank"]}</span>'
            f'<h3>{_escape(cluster["name"])}</h3><p>{_escape(", ".join(cluster["bug_ids"]))}</p></div>'
            f'<span class="score">{cluster["investigation_score"]}<small>score</small></span></summary>'
            f'<div class="cluster-body"><p><b>Assinatura:</b> {_escape(terms)}</p>'
            f'<p><b>Produção:</b> {cluster["production_count"]} · <b>Reabertos:</b> {cluster["reopened_count"]} · '
            f'<b>Confiança do agrupamento:</b> {_escape(cluster["cluster_confidence"])}</p>'
            f'{"".join(hypotheses_html) or "<p class=muted>Dados insuficientes para hipótese.</p>"}</div></details>'
        )

    quality_issues = "".join(
        f'<li><code>{_escape(item["code"])}</code> {_escape(item["message"])}</li>'
        for item in gate["errors"] + gate["warnings"]
    ) or "<li>Nenhum erro ou alerta.</li>"
    sources = "".join(
        f'<li><b>{_escape(item["source"])}</b>: {_escape(item["status"])}'
        f' — {_escape(item.get("details", ""))}</li>'
        for item in analysis["metadata"].get("sources_consulted", [])
    )
    trace_rows = "".join(
        f'<tr><td>{_escape(bug["bug_id"])}</td><td>{bug["source_row"]}</td><td>{_escape(bug["cluster_id"])}</td>'
        f'<td>{_escape(", ".join(h["hypothesis_id"] for h in hypothesis_by_cluster.get(bug["cluster_id"], [])) or UNKNOWN)}</td>'
        f'<td>{_escape(", ".join(a["action_id"] for h in hypothesis_by_cluster.get(bug["cluster_id"], []) for a in actions_by_hypothesis.get(h["hypothesis_id"], [])) or UNKNOWN)}</td></tr>'
        for bug in analysis["bugs"]
    )
    embedded = json.dumps(_repair_structure(analysis), ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RCA Agent Lab · relatório auditável</title>
<style>
:root{{--ink:#19232f;--muted:#687789;--paper:#f5efe5;--card:#fffdf8;--line:#d7cdbd;--navy:#17324a;--teal:#0f766e;--amber:#d97706;--red:#b9483e;--green:#2f7d5a;--sky:#dcecf2;--sand:#efe6d5}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at top,#fffdf8 0,#f5efe5 42%,#efe4d2 100%);color:var(--ink);font:15px/1.6 "Segoe UI",Arial,sans-serif}}
header{{position:relative;overflow:hidden;background:linear-gradient(135deg,#11283b,#184b5e 58%,#c77b2f 170%);color:white;padding:60px max(24px,calc((100vw - 1220px)/2)) 54px;border-bottom:1px solid rgba(255,255,255,.12)}}
header::after{{content:"";position:absolute;inset:auto -5% -90px auto;width:420px;height:420px;border-radius:50%;background:radial-gradient(circle,#f5c57a55 0,#f5c57a00 70%)}}
header h1{{font:700 46px/1.04 Georgia,serif;margin:8px 0 12px;max-width:760px}} header p{{max-width:760px;color:#e3eef1;margin:0}}
.eyebrow{{font-size:11px;text-transform:uppercase;letter-spacing:.16em;font-weight:800;color:var(--teal)}} header .eyebrow{{color:#ffd388}}
.hero-grid{{display:grid;grid-template-columns:1.3fr .9fr;gap:24px;align-items:end}}
.summary-card{{background:rgba(255,255,255,.08);backdrop-filter:blur(4px);border:1px solid rgba(255,255,255,.12);border-radius:18px;padding:18px 20px}}
.summary-card strong{{display:block;font:700 34px/1 Georgia,serif;margin-bottom:6px}}
main{{max-width:1220px;margin:auto;padding:28px 20px 88px}} section{{margin:34px 0}} h2{{font:700 30px Georgia,serif;margin:0 0 16px}} h3{{font:700 19px Georgia,serif;margin:0 0 14px}}
.notice{{padding:15px 18px;border-left:5px solid var(--amber);background:#fff7e7;margin:18px 0;border-radius:10px}} .notice.passed{{border-color:var(--green);background:#e9f6ef}}
.highlights{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-top:16px}} .highlight{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;box-shadow:0 16px 32px rgba(17,40,59,.06)}}
.highlight p{{margin:0;color:var(--muted)}}
.lede{{font-size:18px;max-width:930px;color:#264154;margin:10px 0 0}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}} .kpi,.panel,.hypothesis,.action{{background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:0 14px 30px rgba(30,43,54,.06)}}
.kpi{{padding:18px;display:flex;flex-direction:column;gap:8px;min-height:188px}} .kpi span{{color:var(--muted);font-weight:600}} .kpi strong{{font:700 31px/1.05 Georgia,serif}} .kpi p{{margin:0;color:var(--muted);font-size:13px}}
.kpi-meter{{height:8px;background:var(--sand);border-radius:999px;overflow:hidden;margin:2px 0 4px}} .kpi-meter i{{display:block;height:100%;background:linear-gradient(90deg,var(--teal),#58b7a4)}} .kpi small{{color:var(--muted)}}
.charts,.cross-grid,.context-grid,.cause-grid,.agent-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}} .panel{{padding:18px}}
.bar-row{{display:grid;grid-template-columns:120px 1fr 38px 44px;gap:10px;align-items:center;margin:9px 0}} .bar-row span{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.track{{height:11px;background:#ebe3d7;border-radius:999px;overflow:hidden}} .track i{{display:block;height:100%;background:linear-gradient(90deg,#123047,#2aa198)}} .bar-row small{{color:var(--muted)}}
.chart-shell{{display:flex;flex-direction:column;gap:10px}} .svg-chart{{width:100%;height:auto;background:linear-gradient(180deg,#fdfaf4,#f8f1e7);border-radius:14px;border:1px solid #eadfce}}
.line-chart .grid line{{stroke:#dccfbf;stroke-dasharray:4 6}} .line-chart text{{fill:#667687;font-size:11px;font-family:Segoe UI,Arial,sans-serif}}
.legend{{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:13px}} .legend span{{display:inline-flex;align-items:center;gap:6px}} .legend i{{width:10px;height:10px;border-radius:50%;display:inline-block}}
.heat-panel{{overflow:auto}} .heatmap{{display:flex;flex-direction:column;gap:8px;min-width:520px}} .heat-row{{display:grid;grid-template-columns:180px repeat(auto-fit,minmax(56px,1fr));gap:8px;align-items:center}} .heat-label{{font-size:13px;font-weight:600;color:var(--ink)}}
.heat-cell{{display:grid;place-items:center;min-height:42px;border-radius:10px;background:rgba(15,118,110,var(--strength));color:#0f1720;font-weight:700;border:1px solid rgba(15,118,110,.08)}} .heat-cell.head{{background:#e7ecef;color:var(--muted);font-weight:600}}
.term-cloud{{display:flex;flex-wrap:wrap;gap:10px 12px;align-items:center}} .term-cloud span{{padding:6px 10px;border-radius:999px;background:#e7f1ef;color:#12443f}}
.pattern-list{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}} .pattern{{background:linear-gradient(180deg,#fffdf8,#f6efe3);border:1px solid var(--line);border-radius:16px;padding:16px 18px}} .pattern p{{margin:0;color:#314657}}
.cause-card{{background:linear-gradient(180deg,#fffdf8,#f8f0e4);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 14px 30px rgba(30,43,54,.06)}} .cause-top{{display:flex;justify-content:space-between;gap:12px;align-items:start}} .cause-card h3{{margin:4px 0 10px}} .cause-card p{{margin:0 0 14px;color:#3b5264}} .cause-metrics{{display:grid;grid-template-columns:1fr 1fr;gap:10px 18px}} .cause-metrics span{{font-size:13px;color:#425668}} .cause-narrative{{display:grid;gap:8px;margin:0 0 14px}} .cause-narrative p{{margin:0;color:#314657}} .cause-evidence{{color:#526476}}
.agent-aside{{display:grid;gap:16px}}
.cluster{{background:var(--card);border:1px solid var(--line);border-radius:18px;margin:14px 0;overflow:hidden;box-shadow:0 14px 28px rgba(17,40,59,.06)}} summary{{cursor:pointer;padding:22px;display:flex;justify-content:space-between;gap:20px;align-items:center}} summary h3{{margin:4px 0}} summary p{{margin:0;color:var(--muted)}}
.score{{font:700 30px Georgia,serif;color:var(--navy);text-align:center}} .score small{{display:block;font:11px Segoe UI,Arial,sans-serif;text-transform:uppercase;letter-spacing:.12em}}
.cluster-body{{padding:0 22px 24px}} .hypothesis{{padding:20px;margin:18px 0}} .hyp-head{{display:flex;justify-content:space-between;gap:15px}} .hypothesis h4{{font:700 21px Georgia,serif;margin:4px 0}}
.badge{{padding:5px 10px;border-radius:99px;height:max-content;text-transform:uppercase;font-size:11px;font-weight:800}} .confidence-high{{background:#dff3e6;color:#176341}} .confidence-medium{{background:#fff0c9;color:#8a5a09}} .confidence-low{{background:#f6dfdd;color:#8b332e}}
.split{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .split>div{{background:#f7f1e7;padding:12px;border-radius:10px}} h5{{margin:3px 0 8px}} ul{{margin:5px 0;padding-left:20px}} code{{font-size:12px}}
.validation{{border-left:4px solid var(--teal);padding:10px 12px;background:#e9f6f4;border-radius:8px}} .actions{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}} .action{{padding:14px}} .action h5{{font-size:14px}} .action p{{font-size:13px}} .action.corrective{{border-top:4px solid var(--red)}} .action.detective{{border-top:4px solid var(--amber)}} .action.preventive{{border-top:4px solid var(--green)}}
.table-wrap{{overflow:auto}} table{{border-collapse:collapse;width:100%;background:var(--card)}} th,td{{padding:10px;border:1px solid var(--line);text-align:left}} thead th{{background:#e9eee9}}
.muted{{color:var(--muted)}} footer{{padding:26px;text-align:center;color:var(--muted)}} @media(max-width:900px){{.hero-grid{{grid-template-columns:1fr}}}} @media(max-width:760px){{header h1{{font-size:35px}}.split,.actions,.context-grid,.cause-grid,.cause-metrics,.agent-grid{{grid-template-columns:1fr}}.charts,.cross-grid,.kpis{{grid-template-columns:1fr}}.heatmap{{min-width:unset}}.heat-row{{grid-template-columns:140px repeat(auto-fit,minmax(48px,1fr))}}}}
</style></head><body>
<header><div class="hero-grid"><div><span class="eyebrow">RCA Agent Lab · requires human review</span><h1>{_escape(header_title)}</h1>
<p>Relatório auditável por clusters, com números determinísticos, sinais semânticos rastreáveis e limites explícitos. Gerado em {_escape(utc_now())}.</p></div><aside class="summary-card"><strong>{total} bugs</strong><p>{len(analysis['clusters'])} clusters mapeados · {len(analysis['hypotheses'])} hipóteses ativas · {len(analysis['actions'])} ações propostas.</p></aside></div></header>
<main>
<section><h2>Resumo executivo</h2><div class="notice {'passed' if gate['status']=='passed' else ''}"><b>Quality gate: {_escape(gate['status'])}</b> · Hipóteses permanecem em revisão humana até validação causal.</div><p class="lede">{_escape(summary_sentence)}</p><div class="highlights">{"".join(f'<article class="highlight"><p>{_escape(item)}</p></article>' for item in highlight_items)}</div></section>
<section><h2>KPIs principais</h2><div class="kpis">{kpi_cards}</div></section>
<section><h2>Leitura do agente</h2><div class="agent-grid"><div class="agent-aside"><article class="panel"><h3>Padrões sistêmicos</h3><div class="pattern-list">{"".join(f'<article class="pattern"><p>{_escape(item)}</p></article>' for item in systemic_patterns)}</div></article><article class="panel"><h3>Sinais operacionais</h3>{distribution_cards}</article></div><div class="cause-grid">{_root_cause_cards_from_analysis(analysis)}</div></div></section>
<section><h2>Qualidade e cobertura dos dados</h2><p>Dos {analysis['data_quality']['total_records']} bugs, {analysis['data_quality']['usable_for_metrics']} são utilizáveis para métricas e {analysis['data_quality']['usable_for_causal_analysis']} trazem notas de QA ou Dev para análise causal.</p><ul>{quality_issues}</ul></section>
<section><h2>Tendências e cruzamentos</h2><div class="context-grid"><article class="panel"><h3>Ritmo de criação, detecção e resolução</h3>{timeline_chart}</article><article class="panel"><h3>Leitura rápida das notas</h3><p class="muted">Os termos abaixo destacam vocabulário recorrente nas notas de QA e Dev. Eles ajudam a localizar sinais operacionais, não a provar causalidade.</p>{_term_cloud(note_terms.get('qa_dev', {}))}</article></div></section>
<section><h2>Cruzamentos relevantes</h2><div class="cross-grid">{cross_sections}</div></section>
<section><h2>Famílias, clusters, hipóteses e ações</h2>{''.join(cluster_sections)}</section>
<section><h2>Rastreabilidade</h2><div class="table-wrap"><table><thead><tr><th>Bug</th><th>Linha</th><th>Cluster</th><th>Hipótese</th><th>Ações</th></tr></thead><tbody>{trace_rows}</tbody></table></div></section>
<section><h2>Fontes e limitações</h2><ul>{sources}</ul><p>Similaridade textual, concentração e categoria reportada são sinais. Confirmação causal requer evidência temporal, mecanismo técnico e teste reproduzível.</p></section>
</main><footer>RCA Agent Lab · objeto canônico incorporado para auditoria</footer>
<script id="rca-analysis" type="application/json">{embedded}</script></body></html>"""


PLOT_COLORS = [
    "#ffbf00",
    "#f45b69",
    "#3b82f6",
    "#45c97a",
    "#ff8c42",
    "#42c2b8",
    "#8b5cf6",
    "#d85bef",
    "#8e9aa1",
    "#1f5aa6",
]

SEVERITY_COLORS = {
    "critical": "#8746b8",
    "high": "#f45b69",
    "medium": "#ffd43b",
    "low": "#5b8def",
    "unknown": "#a7b0b7",
}

_DASHBOARD_CSS = """
:root{--ink:#0b172a;--muted:#687386;--yellow:#ffbf00;--blue:#2463eb;--paper:#ffffff;--soft:#f7f9fc;--line:#dfe5ec;--danger:#e64b5d;--success:#179c62}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 Inter,"Segoe UI",Arial,sans-serif}
a{color:inherit}.shell{max-width:1320px;margin:auto;padding:0 28px}.topbar{position:sticky;top:0;z-index:20;background:#fffffff2;backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.nav{display:flex;align-items:center;justify-content:space-between;gap:24px;min-height:64px}.brand{display:flex;align-items:center;gap:11px;font-weight:900}.brand-mark{width:7px;height:34px;background:var(--yellow);transform:skew(-18deg)}
.nav-links{display:flex;gap:20px;flex-wrap:wrap;font-size:13px;font-weight:700;color:#435064}.nav-links a{text-decoration:none}.nav-links a:hover{color:var(--blue)}
.hero{padding:76px 0 44px;border-bottom:1px solid var(--line)}.hero-grid{display:grid;grid-template-columns:1.45fr .65fr;gap:40px;align-items:end}.hero-kicker{font-size:13px;font-weight:900;letter-spacing:.14em;text-transform:uppercase;color:#536075}
.hero h1,.section-title{position:relative;margin:12px 0 14px;padding-left:31px;font-weight:950;letter-spacing:-.045em;line-height:1}.hero h1{font-size:clamp(48px,6vw,82px)}.hero h1:before,.section-title:before{content:"";position:absolute;left:5px;top:0;width:8px;height:100%;background:var(--yellow);transform:skew(-17deg)}
.hero p{max-width:800px;margin:0;color:#4e5b70;font-size:18px}.hero-summary{border:1px solid var(--line);padding:22px;border-radius:4px;box-shadow:0 12px 28px #0b172a10}.hero-summary strong{display:block;font-size:45px;line-height:1}.hero-summary span{color:var(--muted)}
.review-flag{display:inline-flex;align-items:center;gap:8px;margin-top:20px;padding:8px 12px;background:#fff8df;border:1px solid #f0d46a;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}
main{padding:20px 0 96px}.section{padding:64px 0;border-bottom:1px solid var(--line)}.section-title{font-size:clamp(34px,4vw,58px);margin:0 0 32px}.section-subtitle{margin:-18px 0 34px;padding-left:31px;color:var(--muted);font-size:17px}
.executive{display:grid;grid-template-columns:1.15fr .85fr;gap:22px}.panel{background:#fff;border:1px solid var(--line);border-radius:4px;padding:26px;box-shadow:0 8px 24px #0b172a0b}.panel h3{margin:0 0 10px;font-size:20px}.panel p{margin:0;color:#435064}
.findings{display:grid;gap:12px}.finding{border-left:5px solid var(--yellow);background:var(--soft);padding:15px 17px;color:#27364d}.gate{display:flex;justify-content:space-between;gap:16px;align-items:center;border-top:1px solid var(--line);margin-top:22px;padding-top:18px}.gate b{color:var(--success)}
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.kpi-card{border:1px solid var(--line);padding:18px;background:#fff;min-height:152px}.kpi-card.attention{border-top:5px solid var(--danger)}.kpi-card.watch{border-top:5px solid var(--yellow)}.kpi-card.stable{border-top:5px solid var(--success)}.kpi-card.context,.kpi-card.insufficient{border-top:5px solid #76849a}
.kpi-card span{display:block;color:var(--muted);font-size:13px;font-weight:700}.kpi-card strong{display:block;font-size:34px;line-height:1.15;margin:7px 0}.kpi-card p{font-size:13px;margin:0;color:#435064}
.kpi-detail-list{display:grid;gap:28px}.kpi-detail{display:grid;grid-template-columns:330px 1fr;border:1px solid var(--line);background:#fff;box-shadow:0 10px 30px #0b172a0b}.kpi-visual{background:var(--soft);padding:22px;border-right:1px solid var(--line)}.kpi-visual h3{font-size:22px;margin:0 0 4px}.kpi-visual>p{color:var(--muted);margin:0}.kpi-copy{padding:26px 30px;display:grid;gap:18px}.copy-block{display:grid;grid-template-columns:150px 1fr;gap:18px}.copy-block b{font-size:12px;text-transform:uppercase;letter-spacing:.11em}.copy-block p{margin:0;color:#34435a}.kpi-meta{display:flex;flex-wrap:wrap;gap:8px}.chip{background:#eef2f7;border:1px solid #dce3eb;padding:5px 9px;font-size:12px}.chip.review{background:#fff8df;border-color:#f0d46a}
.slide{border:1px solid var(--line);background:#fff;padding:28px;margin:20px 0;box-shadow:0 9px 26px #0b172a0b}.slide-head{text-align:center;margin-bottom:8px}.slide-head h3{font-size:28px;margin:0}.slide-head p{margin:4px 0;color:var(--muted)}
.chart-two{display:grid;grid-template-columns:1fr 1fr;gap:22px}.chart-box{min-width:0}.chart-box h4{text-align:center;font-size:18px;margin:4px 0 0}.plot{min-height:390px}.plot>div{width:100%!important}
.cause-summary{display:grid;grid-template-columns:1fr 1fr;gap:24px}.cause-primary,.cause-other{padding:26px;border:1px solid var(--line)}.cause-primary{background:#eef5ff;border-color:#b9d2ff}.cause-stat{text-align:center;background:#fff;padding:17px;margin:14px 0 20px}.cause-stat strong{display:block;color:var(--blue);font-size:46px;line-height:1}.cause-stat span{font-weight:800}.cause-row{margin:14px 0}.cause-row-head{display:flex;justify-content:space-between;gap:10px;font-weight:700}.cause-track{height:9px;background:#cfe0fb;margin-top:6px}.cause-track i{display:block;height:100%;background:var(--blue)}.cause-other ul{list-style:none;margin:16px 0 0;padding:0}.cause-other li{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid #edf0f4}
.pattern-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}.pattern{padding:20px;border:1px solid var(--line);background:var(--soft)}.pattern p{margin:0;color:#34435a}
.cluster{border:1px solid var(--line);margin:16px 0;background:#fff}.cluster summary{cursor:pointer;display:grid;grid-template-columns:1fr auto;gap:20px;align-items:center;padding:22px}.cluster summary h3{font-size:22px;margin:3px 0}.cluster summary p{margin:0;color:var(--muted)}.score{font-size:34px;font-weight:900;text-align:center}.score small{display:block;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.cluster-body{padding:0 22px 24px}.hypothesis{border-top:1px solid var(--line);padding-top:22px;margin-top:18px}.hyp-head{display:flex;justify-content:space-between;gap:20px}.hyp-head h4{font-size:20px;margin:3px 0}.badge{height:max-content;padding:5px 10px;text-transform:uppercase;font-size:11px;font-weight:900;background:#fff1c9}
.evidence-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.evidence-box{background:var(--soft);padding:16px}.evidence-box h5{margin:0 0 8px}.evidence-box ul{margin:0;padding-left:18px}.actions{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:15px}.action{border:1px solid var(--line);border-top:5px solid #789;padding:15px}.action.corrective{border-top-color:var(--danger)}.action.detective{border-top-color:var(--yellow)}.action.preventive{border-top-color:var(--success)}.action h5{font-size:14px;margin:5px 0 8px}.action p{margin:5px 0;font-size:13px;color:#435064}
.table-wrap{overflow:auto;border:1px solid var(--line)}table{border-collapse:collapse;width:100%;background:#fff}th,td{padding:11px 13px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{background:var(--soft);font-size:12px;text-transform:uppercase;letter-spacing:.06em}
.muted{color:var(--muted)}code{font-size:12px}footer{padding:28px;border-top:1px solid var(--line);color:var(--muted);text-align:center}
@media(max-width:1000px){.hero-grid,.executive,.kpi-detail,.cause-summary{grid-template-columns:1fr}.kpi-visual{border-right:0;border-bottom:1px solid var(--line)}.kpi-grid{grid-template-columns:repeat(2,1fr)}.actions{grid-template-columns:1fr}.nav-links{display:none}}
@media(max-width:720px){.shell{padding:0 16px}.hero{padding-top:44px}.hero h1{font-size:46px}.section{padding:44px 0}.section-title{font-size:36px}.kpi-grid,.chart-two,.pattern-grid,.evidence-grid{grid-template-columns:1fr}.copy-block{grid-template-columns:1fr;gap:5px}.slide{padding:12px}.plot{min-height:330px}}
"""


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


def _donut_chart(values: dict[str, int], title: str) -> str:
    labels = [_pretty(item) for item in values]
    counts = list(values.values())
    colors = [
        SEVERITY_COLORS.get(item, PLOT_COLORS[index % len(PLOT_COLORS)])
        for index, item in enumerate(values)
    ]
    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=counts,
            hole=0.52,
            textinfo="value+percent",
            textposition="inside",
            marker=dict(colors=colors, line=dict(color="white", width=2)),
            sort=False,
        )
    )
    fig.update_layout(title=dict(text=title, x=0.5), legend=dict(orientation="h", y=-0.12))
    return _plot_html(fig, 420)


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


def _word_cloud_plot(values: dict[str, int]) -> str:
    items = list(values.items())[:18]
    if not items:
        return (
            '<div class="slide-head"><h3>Palavras-chave nas análises de causa raiz</h3></div>'
            '<p class="muted">Sem termos suficientes nas notas de QA/Dev.</p>'
        )
    positions = [
        (0, 0),
        (-1.4, 0.1),
        (1.35, 0.15),
        (0.1, 1.0),
        (-0.1, -1.0),
        (-1.25, 1.0),
        (1.25, -0.9),
        (1.55, 1.0),
        (-1.6, -0.9),
        (0.75, 1.65),
        (-0.8, 1.7),
        (0.8, -1.65),
        (-0.8, -1.65),
        (2.0, 0.1),
        (-2.0, 0.15),
        (1.8, 1.65),
        (-1.8, 1.65),
        (0, 2.05),
    ]
    maximum = max(value for _, value in items)
    fig = go.Figure(
        go.Scatter(
            x=[positions[index][0] for index in range(len(items))],
            y=[positions[index][1] for index in range(len(items))],
            mode="text",
            text=[term for term, _ in items],
            textfont=dict(
                size=[18 + int(value / maximum * 44) for _, value in items],
                color=[PLOT_COLORS[index % len(PLOT_COLORS)] for index in range(len(items))],
            ),
            hovertext=[f"{term}: {value}" for term, value in items],
            hoverinfo="text",
        )
    )
    fig.update_layout(
        title=dict(text="Palavras-chave nas análises de causa raiz", x=0.5),
        xaxis=dict(visible=False, range=[-2.7, 2.7]),
        yaxis=dict(visible=False, range=[-2.4, 2.6]),
        showlegend=False,
    )
    return _plot_html(fig, 520)


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


def _kpi_cards_v2(kpis: list[dict[str, Any]]) -> str:
    return "".join(
        f'<article class="kpi-card {_escape(kpi.get("status", "context"))}">'
        f'<span>{_escape(kpi["label"])}</span><strong>{_display(kpi.get("value"), kpi.get("unit", ""))}</strong>'
        f'<p>{_escape(kpi.get("insight", ""))}</p></article>'
        for kpi in kpis
    )


def _kpi_details_v2(kpis: list[dict[str, Any]]) -> str:
    sections = []
    for index, kpi in enumerate(kpis, 1):
        ids = ", ".join(kpi.get("supporting_bug_ids", [])) or "nenhum ID disponível"
        limitations = " ".join(kpi.get("limitations", [])) or "Sem limitação adicional registrada."
        sections.append(
            f'<article class="kpi-detail" id="kpi-{_escape(kpi["id"])}">'
            f'<div class="kpi-visual"><span class="hero-kicker">KPI {index:02d}</span>'
            f'<h3>{_escape(kpi["label"])}</h3><p>{_escape(kpi.get("definition", ""))}</p>'
            f'{_kpi_indicator(kpi)}</div><div class="kpi-copy">'
            f'<div class="copy-block"><b>Insight</b><p>{_escape(kpi.get("insight", ""))}</p></div>'
            f'<div class="copy-block"><b>Análise detalhada</b><p>{_escape(kpi.get("detailed_analysis", ""))}</p></div>'
            f'<div class="copy-block"><b>Rastreabilidade</b><p><b>Fórmula:</b> {_escape(kpi.get("formula", ""))}<br>'
            f'<b>Amostra:</b> n={_escape(kpi.get("sample_size"))}<br><b>Bugs de apoio:</b> {_escape(ids)}</p></div>'
            f'<div class="copy-block"><b>Limitações</b><p>{_escape(limitations)}</p></div>'
            f'<div class="kpi-meta"><span class="chip">{_escape(kpi.get("status", "context"))}</span>'
            f'<span class="chip review">requires human review</span></div></div></article>'
        )
    return "".join(sections)


def _cause_summary_v2(profiles: list[dict[str, Any]], total: int) -> str:
    leading = profiles[:4]
    remaining = profiles[4:]
    leading_total = sum(item["count"] for item in leading)
    remaining_total = max(total - leading_total, 0)
    rows = "".join(
        f'<div class="cause-row"><div class="cause-row-head"><span>{_escape(_cause_display_name(item["root_cause_category"]))}</span>'
        f'<span>{item["count"]} bugs ({item["share_percent"]}%)</span></div>'
        f'<div class="cause-track"><i style="width:{item["share_percent"]}%"></i></div></div>'
        for item in leading
    )
    other = "".join(
        f'<li><span>{_escape(_cause_display_name(item["root_cause_category"]))}</span><b>{item["count"]}</b></li>'
        for item in remaining
    ) or "<li><span>Sem outras categorias</span><b>0</b></li>"
    share = round(leading_total / total * 100, 1) if total else 0
    return (
        f'<div class="cause-summary"><article class="cause-primary"><h3>Principais sinais RCA</h3>'
        f'<div class="cause-stat"><strong>{leading_total}</strong><span>Bugs ({share}%)</span></div>{rows}</article>'
        f'<article class="cause-other"><h3>Outros sinais RCA</h3><div class="cause-stat">'
        f'<strong style="color:#435064">{remaining_total}</strong><span>Bugs ({round(100-share,1)}%)</span></div>'
        f'<ul>{other}</ul></article></div>'
    )


def _cluster_sections_v2(analysis: dict[str, Any]) -> str:
    evidence = {item["evidence_id"]: item for item in analysis["evidence"]}
    hypotheses: dict[str, list[dict[str, Any]]] = {}
    actions: dict[str, list[dict[str, Any]]] = {}
    for item in analysis["hypotheses"]:
        hypotheses.setdefault(item["cluster_id"], []).append(item)
    for item in analysis["actions"]:
        actions.setdefault(item["hypothesis_id"], []).append(item)
    sections = []
    for cluster in analysis["clusters"]:
        hypothesis_sections = []
        for hypothesis in hypotheses.get(cluster["cluster_id"], []):
            supporting = "".join(
                f'<li><code>{_escape(identifier)}</code> {_escape(evidence.get(identifier, {}).get("excerpt", "evidência ausente"))}</li>'
                for identifier in hypothesis["supporting_evidence_ids"]
            )
            counter = "".join(
                f'<li><code>{_escape(identifier)}</code> {_escape(evidence.get(identifier, {}).get("excerpt", "evidência ausente"))}</li>'
                for identifier in hypothesis["counter_evidence_ids"]
            ) or "<li>Nenhuma contraevidência registrada; isso é uma lacuna, não confirmação.</li>"
            questions = "".join(
                f"<li>{_escape(question)}</li>" for question in hypothesis["confirmation_questions"]
            )
            action_cards = "".join(
                f'<article class="action {_escape(action["barrier_type"])}"><span class="hero-kicker">{_escape(action["barrier_type"])}</span>'
                f'<h5>{_escape(action["statement"])}</h5><p><b>Dono:</b> {_escape(action["owner_role"])}</p>'
                f'<p><b>Horizonte:</b> {_escape(action["horizon"])}</p><p><b>Métrica:</b> {_escape(action["success_metric"])}</p></article>'
                for action in actions.get(hypothesis["hypothesis_id"], [])
            )
            hypothesis_sections.append(
                f'<article class="hypothesis"><div class="hyp-head"><div><span class="hero-kicker">{_escape(hypothesis["hypothesis_id"])}</span>'
                f'<h4>{_escape(hypothesis["statement"])}</h4></div><span class="badge">{_escape(hypothesis["confidence"])}</span></div>'
                f'<p><b>Hipótese de mecanismo:</b> {_escape(hypothesis["mechanism"])}</p>'
                f'<p><b>Racional:</b> {_escape(hypothesis["confidence_rationale"])}</p>'
                f'<div class="evidence-grid"><div class="evidence-box"><h5>Evidências favoráveis</h5><ul>{supporting}</ul></div>'
                f'<div class="evidence-box"><h5>Contraevidências</h5><ul>{counter}</ul></div>'
                f'<div class="evidence-box"><h5>Perguntas para confirmar/refutar</h5><ul>{questions}</ul></div>'
                f'<div class="evidence-box"><h5>Validação</h5><p>{_escape(hypothesis["validation_method"])}</p></div></div>'
                f'<div class="actions">{action_cards}</div></article>'
            )
        sections.append(
            f'<details class="cluster" {"open" if cluster["prioritized"] else ""}><summary><div>'
            f'<span class="hero-kicker">{_escape(cluster["cluster_id"])} · rank {cluster["priority_rank"]}</span>'
            f'<h3>{_escape(cluster["name"])}</h3><p>{_escape(", ".join(cluster["bug_ids"]))}</p></div>'
            f'<span class="score">{cluster["investigation_score"]}<small>score</small></span></summary>'
            f'<div class="cluster-body"><p><b>Produção:</b> {cluster["production_count"]} · '
            f'<b>Reabertos:</b> {cluster["reopened_count"]} · <b>Confiança:</b> {_escape(cluster["cluster_confidence"])}</p>'
            f'{"".join(hypothesis_sections) or "<p class=muted>Dados insuficientes para formular hipótese rastreável.</p>"}</div></details>'
        )
    return "".join(sections)


def render_html_v2(analysis: dict[str, Any]) -> str:
    analysis = _repair_structure(analysis)
    metrics = analysis["metrics"]
    total = len(analysis["bugs"])
    gate = analysis["quality_gate"]
    narrative = analysis.get("narrative", {})
    highlights = list(narrative.get("key_findings", [])) or [
        item.get("statement", "") for item in analysis.get("insights", [])[:4]
    ]
    if not highlights:
        highlights = [_summary_sentence(analysis)]
    patterns = list(narrative.get("systemic_patterns", [])) or _systemic_patterns(analysis)
    distributions = metrics["distributions"]
    cross = metrics["cross_tabs"]
    profiles = metrics.get("root_cause_profiles", [])
    root_causes = distributions.get("root_cause_category", {})
    quality_items = gate.get("errors", []) + gate.get("warnings", [])
    quality_html = "".join(
        f'<li><code>{_escape(item["code"])}</code> {_escape(item["message"])}</li>'
        for item in quality_items
    ) or "<li>Nenhum erro ou alerta.</li>"
    hypothesis_by_cluster: dict[str, list[dict[str, Any]]] = {}
    actions_by_hypothesis: dict[str, list[dict[str, Any]]] = {}
    for item in analysis["hypotheses"]:
        hypothesis_by_cluster.setdefault(item["cluster_id"], []).append(item)
    for item in analysis["actions"]:
        actions_by_hypothesis.setdefault(item["hypothesis_id"], []).append(item)
    trace_rows = "".join(
        f'<tr><td>{_escape(bug["bug_id"])}</td><td>{bug["source_row"]}</td><td>{_escape(bug["cluster_id"])}</td>'
        f'<td>{_escape(", ".join(item["hypothesis_id"] for item in hypothesis_by_cluster.get(bug["cluster_id"], [])) or UNKNOWN)}</td>'
        f'<td>{_escape(", ".join(action["action_id"] for hypothesis in hypothesis_by_cluster.get(bug["cluster_id"], []) for action in actions_by_hypothesis.get(hypothesis["hypothesis_id"], [])) or UNKNOWN)}</td></tr>'
        for bug in analysis["bugs"]
    )
    embedded = json.dumps(analysis, ensure_ascii=False).replace("</", "<\\/")
    plotly_js = get_plotlyjs()
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RCA Agent Lab · Analisando indicadores</title><style>{_DASHBOARD_CSS}</style></head><body>
<nav class="topbar"><div class="shell nav"><div class="brand"><i class="brand-mark"></i>RCA Agent Lab</div>
<div class="nav-links"><a href="#resumo">Resumo</a><a href="#kpis">KPIs</a><a href="#graficos">Indicadores</a><a href="#rca">RCA</a><a href="#clusters">Clusters</a><a href="#auditoria">Auditoria</a></div></div></nav>
<header class="hero"><div class="shell hero-grid"><div><span class="hero-kicker">Relatório HTML auditável</span><h1>Analisando Indicadores</h1>
<p>{_escape(_summary_sentence(analysis))}</p><span class="review-flag">Hipóteses · requires human review</span></div>
<aside class="hero-summary"><strong>{total}</strong><span>bugs analisados</span><p>{len(analysis["clusters"])} clusters · {len(analysis["hypotheses"])} hipóteses · {len(analysis["actions"])} barreiras</p></aside></div></header>
<main class="shell">
<section class="section" id="resumo"><h2 class="section-title">Resumo executivo</h2><div class="executive"><article class="panel"><h3>Leitura principal</h3><p>{_escape(_summary_sentence(analysis))}</p>
<div class="gate"><span>Quality gate</span><b>{_escape(gate["status"])}</b></div></article>
<div class="findings">{"".join(f'<article class="finding">{_escape(item)}</article>' for item in highlights)}</div></div></section>
<section class="section" id="kpis"><h2 class="section-title">KPIs principais</h2><p class="section-subtitle">Visão rápida dos indicadores; cada card possui uma análise detalhada logo abaixo.</p>
<div class="kpi-grid">{_kpi_cards_v2(metrics["kpis"])}</div></section>
<section class="section"><h2 class="section-title">Análise detalhada dos KPIs</h2><p class="section-subtitle">Definição, cálculo, leitura, evidência, limitações e interpretação de cada indicador.</p>
<div class="kpi-detail-list">{_kpi_details_v2(metrics["kpis"])}</div></section>
<section class="section" id="graficos"><h2 class="section-title">Analisando indicadores</h2>
<article class="slide"><div class="slide-head"><h3>Evolução da qualidade</h3><p>Comparativo de criação, detecção e resolução de bugs</p></div>{_timeline_chart_plot(metrics.get("timelines", {}))}</article>
<article class="slide"><div class="slide-head"><h3>Distribuição geral de bugs</h3><p>Base total: {total} bugs</p></div><div class="chart-two">
<div class="chart-box">{_donut_chart(distributions.get("severity", {}), "Por severidade")}</div>
<div class="chart-box">{_donut_chart(distributions.get("bug_type", {}), "Por tipo")}</div></div></article>
<article class="slide"><div class="chart-two">
<div class="chart-box">{_donut_chart(distributions.get("environment", {}), "Por ambiente")}</div>
<div class="chart-box">{_donut_chart(distributions.get("affected_module", {}), "Por componente")}</div></div></article>
<article class="slide"><div class="slide-head"><h3>Análise de causa raiz</h3><p>Categorias reportadas como sinais de triagem, não como causalidade confirmada</p></div>
{_bar_chart(root_causes, "Distribuição dos sinais RCA")}</article>
<article class="slide"><div class="slide-head"><h3>Resumo visual da análise de causa raiz</h3><p>Concentração dos sinais prioritários</p></div>{_cause_summary_v2(profiles, total)}</article>
<article class="slide"><div class="slide-head"><h3>Tipos de bugs por principais sinais RCA</h3></div>
{_stacked_chart(cross.get("bug_type_by_root_cause", {}), "Distribuição de tipos de bugs")}</article>
<article class="slide"><div class="slide-head"><h3>Criticidade por principais sinais RCA</h3></div>
{_stacked_chart(cross.get("severity_by_root_cause", {}), "Criticidade de bugs")}</article>
<article class="slide"><div class="slide-head"><h3>Palavras-chave nas análises de causa raiz</h3><p>Vocabulário recorrente nas notas de QA e Dev</p></div>
{_word_cloud_plot(metrics.get("note_terms", {}).get("qa_dev", {}))}</article></section>
<section class="section" id="rca"><h2 class="section-title">Leitura sistêmica</h2><p class="section-subtitle">Padrões que conectam indicadores, notas e recorrência.</p>
<div class="pattern-grid">{"".join(f'<article class="pattern"><p>{_escape(item)}</p></article>' for item in patterns)}</div></section>
<section class="section" id="clusters"><h2 class="section-title">Clusters, hipóteses e barreiras</h2><p class="section-subtitle">Investigação priorizada com evidência favorável, contraevidência, perguntas e ações mensuráveis.</p>
{_cluster_sections_v2(analysis)}</section>
<section class="section" id="auditoria"><h2 class="section-title">Auditoria e rastreabilidade</h2><article class="panel"><h3>Qualidade dos dados</h3>
<p>{analysis["data_quality"]["usable_for_metrics"]} de {analysis["data_quality"]["total_records"]} registros são utilizáveis para métricas; {analysis["data_quality"]["usable_for_causal_analysis"]} possuem notas de QA/Dev.</p><ul>{quality_html}</ul></article>
<div class="table-wrap" style="margin-top:20px"><table><thead><tr><th>Bug</th><th>Linha</th><th>Cluster</th><th>Hipótese</th><th>Ações</th></tr></thead><tbody>{trace_rows}</tbody></table></div>
<p class="muted" style="margin-top:18px">Similaridade, concentração e categoria reportada são sinais. Causa confirmada exige sequência temporal, mecanismo técnico e teste reproduzível.</p></section>
</main><footer>RCA Agent Lab · objeto canônico incorporado · gerado em {_escape(utc_now())}</footer>
<script>{plotly_js}</script><script id="rca-analysis" type="application/json">{embedded}</script></body></html>"""


def write_html(path: Path, analysis: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html_v2(analysis), encoding="utf-8")
