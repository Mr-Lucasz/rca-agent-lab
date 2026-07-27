from __future__ import annotations

import json
from typing import Any

from plotly.offline import get_plotlyjs

from ..core.utils import UNKNOWN, utc_now
from .charts import (
    _bar_chart,
    _kpi_indicator,
    _mini_bar_chart,
    _stacked_chart,
    _timeline_chart_plot,
)
from .common import (
    _causal_signal_audit,
    _cause_display_name,
    _display,
    _escape,
    _repair_structure,
    _summary_sentence,
    _systemic_patterns,
)
from .methodology import _methodological_analysis_v2
from .styles import _DASHBOARD_CSS


def _kpi_cards_v2(kpis: list[dict[str, Any]]) -> str:
    cards = []
    for kpi in kpis:
        insight = str(kpi.get("insight", "")).strip()
        semantic_copy = f"<p>{_escape(insight)}</p>" if insight else ""
        cards.append(
            f'<article class="kpi-card {_escape(kpi.get("status", "pending_review"))}">'
            f'<span>{_escape(kpi["label"])}</span>'
            f'<strong>{_display(kpi.get("value"), kpi.get("unit", ""))}</strong>'
            f"{semantic_copy}</article>"
        )
    return "".join(cards)


def _kpi_details_v2(kpis: list[dict[str, Any]]) -> str:
    sections = []
    for index, kpi in enumerate(kpis, 1):
        ids = ", ".join(kpi.get("supporting_bug_ids", [])) or "nenhum ID disponível"
        limitations = " ".join(kpi.get("limitations", [])) or "Sem limitação adicional registrada."
        methodology = kpi.get("methodology", {})
        source_counts = (
            ", ".join(
                f"{source}: {count}"
                for source, count in methodology.get("source_counts", {}).items()
            )
            or "sem observações válidas"
            if methodology.get("calculation_type") == "duration_mean"
            else "não aplicável"
        )
        insight = str(kpi.get("insight", "")).strip()
        detailed = str(kpi.get("detailed_analysis", "")).strip()
        semantic_blocks = ""
        if insight:
            semantic_blocks += (
                f'<div class="copy-block"><b>Insight revisado</b>'
                f"<p>{_escape(insight)}</p></div>"
            )
        if detailed:
            semantic_blocks += (
                f'<div class="copy-block"><b>Análise revisada</b>'
                f"<p>{_escape(detailed)}</p></div>"
            )
        sections.append(
            f'<article class="kpi-detail" id="kpi-{_escape(kpi["id"])}">'
            f'<div class="kpi-visual"><span class="hero-kicker">KPI {index:02d}</span>'
            f'<h3>{_escape(kpi["label"])}</h3><p>{_escape(kpi.get("definition", ""))}</p>'
            f'{_kpi_indicator(kpi)}</div><div class="kpi-copy">{semantic_blocks}'
            f'<div class="copy-block"><b>Rastreabilidade</b><p><b>Fórmula:</b> {_escape(kpi.get("formula", ""))}<br>'
            f'<b>Amostra:</b> n={_escape(kpi.get("sample_size"))}<br>'
            f'<b>Método configurado:</b> {_escape(methodology.get("calculation_type", ""))}<br>'
            f'<b>Fontes de duração:</b> {_escape(source_counts)}<br>'
            f'<b>Bugs de apoio:</b> {_escape(ids)}</p></div>'
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
    gap_reviews = {
        item["cluster_id"]: item
        for item in analysis.get("narrative", {}).get(
            "cluster_gap_reviews", []
        )
    }
    hypotheses: dict[str, list[dict[str, Any]]] = {}
    actions: dict[str, list[dict[str, Any]]] = {}
    for item in analysis["hypotheses"]:
        hypotheses.setdefault(item["cluster_id"], []).append(item)
    for item in analysis["actions"]:
        actions.setdefault(item["hypothesis_id"], []).append(item)
    sections = []
    for cluster in analysis["clusters"]:
        boundary_cases = cluster.get("boundary_cases", [])
        boundary_html = (
            '<details><summary>Casos limítrofes do agrupamento</summary><ul>'
            + "".join(
                '<li>'
                f'{_escape(item["left_bug_id"])} ↔ {_escape(item["right_bug_id"])}: '
                f'similaridade {_escape(item["similarity"])}; '
                f'limiar {_escape(item["decision_threshold"])}; '
                f'decisão {_escape(item["relation"])}.'
                '</li>'
                for item in boundary_cases
            )
            + "</ul></details>"
            if boundary_cases
            else ""
        )
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
            impact_hours = hypothesis.get("estimated_rework_hours")
            estimate_basis = hypothesis.get("estimate_basis", {})
            impact_html = (
                '<p class="impact-alert">Estimativa de retrabalho reportada: '
                f'~{_escape(impact_hours)} horas. '
                f'Método: {_escape(estimate_basis.get("method", "não informado"))}</p>'
                if impact_hours is not None
                else ""
            )
            
            hypothesis_sections.append(
                f'<article class="hypothesis"><div class="hyp-head"><div><span class="hero-kicker">{_escape(hypothesis["hypothesis_id"])}</span>'
                f'<h4>{_escape(hypothesis["statement"])}</h4></div><span class="badge">{_escape(hypothesis["confidence"])}</span></div>'
                f'{impact_html}'
                f'<p><b>Hipótese de mecanismo:</b> {_escape(hypothesis["mechanism"])}</p>'
                f'<p><b>Racional:</b> {_escape(hypothesis["confidence_rationale"])}</p>'
                f'<div class="evidence-grid"><div class="evidence-box"><h5>Evidências favoráveis</h5><ul>{supporting}</ul></div>'
                f'<div class="evidence-box"><h5>Contraevidências</h5><ul>{counter}</ul></div>'
                f'<div class="evidence-box"><h5>Perguntas para confirmar/refutar</h5><ul>{questions}</ul></div>'
                f'<div class="evidence-box"><h5>Validação</h5><p>{_escape(hypothesis["validation_method"])}</p></div></div>'
                f'<div class="actions">{action_cards}</div></article>'
            )
        if not hypothesis_sections:
            hypothesis_sections.append(
                _cluster_gap_review(cluster, gap_reviews.get(cluster["cluster_id"]), evidence)
            )
        sections.append(
            f'<details class="cluster" {"open" if cluster["prioritized"] else ""}><summary><div>'
            f'<span class="hero-kicker">{_escape(cluster["cluster_id"])} · rank {cluster["priority_rank"]}</span>'
            f'<h3>{_escape(cluster["name"])}</h3><p>{_escape(", ".join(cluster["bug_ids"]))}</p></div>'
            f'<span class="score">{cluster["investigation_score"]}<small>score</small></span></summary>'
            f'<div class="cluster-body"><p><b>Produção:</b> {cluster["production_count"]} · '
            f'<b>Reabertos:</b> {cluster["reopened_count"]} · <b>Confiança:</b> {_escape(cluster["cluster_confidence"])}</p>'
            f'<p class="muted">{_escape(cluster.get("confidence_basis", ""))}</p>{boundary_html}'
            f'{"".join(hypothesis_sections)}</div></details>'
        )
    return "".join(sections)


def _cluster_gap_review(
    cluster: dict[str, Any],
    review: dict[str, Any] | None,
    evidence: dict[str, dict[str, Any]],
) -> str:
    if review:
        reason = review["reason"]
        available = review["available_evidence"]
        missing = review["missing_information"]
        next_step = review["next_step"]
        evidence_ids = review["evidence_ids"]
    else:
        reason = (
            f"O cluster ficou fora do corte de priorização desta execução "
            f"(rank {cluster['priority_rank']}); isso não significa ausência de dados."
            if not cluster.get("prioritized")
            else "O cluster foi priorizado, mas a revisão não registrou uma hipótese causal."
        )
        evidence_ids = [
            identifier
            for identifier, item in evidence.items()
            if item.get("bug_id") in cluster.get("bug_ids", [])
        ][:6]
        available = [
            f"{len(evidence_ids)} evidência(s) textual(is) estão registradas para o cluster."
        ]
        missing = [
            "Revisão semântica do mecanismo que conecte as ocorrências.",
            "Contraevidência explícita e teste capaz de confirmar ou refutar a hipótese.",
        ]
        next_step = (
            "Promover o cluster para revisão e registrar hipótese, evidências, "
            "lacunas e método de validação no agent-review.json."
        )
    available_html = "".join(f"<li>{_escape(item)}</li>" for item in available)
    missing_html = "".join(f"<li>{_escape(item)}</li>" for item in missing)
    trace_html = "".join(
        f'<li><code>{_escape(identifier)}</code> '
        f'{_escape(evidence.get(identifier, {}).get("excerpt", "evidência ausente"))}</li>'
        for identifier in evidence_ids
    )
    return (
        '<article class="hypothesis"><div class="hyp-head"><div>'
        '<span class="hero-kicker">Lacuna causal explícita</span>'
        '<h4>Por que não há hipótese neste cluster?</h4></div></div>'
        f"<p>{_escape(reason)}</p><div class=\"evidence-grid\">"
        '<div class="evidence-box"><h5>O que já existe</h5>'
        f"<ul>{available_html}</ul></div>"
        '<div class="evidence-box"><h5>O que falta</h5>'
        f"<ul>{missing_html}</ul></div>"
        '<div class="evidence-box"><h5>Evidências disponíveis</h5>'
        f"<ul>{trace_html}</ul></div>"
        '<div class="evidence-box"><h5>Próximo passo</h5>'
        f"<p>{_escape(next_step)}</p></div></div></article>"
    )


def _schema_mapping_rows(data_quality: dict[str, Any]) -> str:
    rows = []
    for item in data_quality.get("schema_mapping", []):
        canonical = item.get("canonical_field") or "Preservado sem mapeamento"
        rows.append(
            "<tr>"
            f"<td>{_escape(item['source_field'])}</td>"
            f"<td>{_escape(canonical)}</td>"
            f"<td>{_escape(item['confidence'])}</td>"
            f"<td>{item['score']}</td>"
            f"<td>{_escape(item['status'])}</td>"
            "</tr>"
        )
    return "".join(rows) or (
        '<tr><td colspan="5">Nenhum cabeçalho disponível para auditoria.</td></tr>'
    )


def _patterns_section(patterns: list[str]) -> str:
    if not patterns:
        return ""
    cards = "".join(
        f'<article class="pattern"><p>{_escape(item)}</p></article>'
        for item in patterns
    )
    return (
        '<section class="section" id="rca"><h2 class="section-title">'
        'Leitura sistêmica revisada</h2><p class="section-subtitle">'
        'Interpretações vinculadas às evidências da revisão.</p>'
        f'<div class="pattern-grid">{cards}</div></section>'
    )


def _conclusion_section(analysis: dict[str, Any]) -> str:
    metrics = analysis.get("metrics", {})
    profiles = metrics.get("root_cause_profiles", [])
    top_themes = profiles[:3]
    themes_html = "".join(
        f'<li><b>{_escape(_cause_display_name(t["root_cause_category"]))}:</b> Responsável por {t["share_percent"]}% dos problemas analisados.</li>'
        for t in top_themes
    ) if top_themes else "<li>Temas sistêmicos pendentes de identificação.</li>"

    actions = analysis.get("actions", [])
    top_actions = actions[:3]
    actions_html = "".join(
        f'<li><b>{_escape(a.get("barrier_type", "Controle"))} ({_escape(a.get("horizon", "N/A"))}):</b> {_escape(a.get("statement", ""))}</li>'
        for a in top_actions
    ) if top_actions else "<li>Nenhuma ação prioritária definida na revisão.</li>"

    limitations = analysis.get("narrative", {}).get("limitations", [])
    limitations_html = "".join(
        f'<li>{_escape(l)}</li>'
        for l in limitations
    ) if limitations else "<li>Sem limitações críticas registradas que invalidem as hipóteses principais.</li>"

    verdict = _summary_sentence(analysis)

    return (
        '<section class="section" id="conclusao"><h2 class="section-title">Conclusão da Análise (Executive Summary)</h2>'
        '<div style="display: flex; flex-direction: column; gap: 16px;">'
        '<article class="panel"><h3>1. O Veredito Sistêmico</h3>'
        f'<p>{_escape(verdict)}</p></article>'
        '<article class="panel"><h3>2. Principais Fatores Contribuintes</h3>'
        f'<ul>{themes_html}</ul></article>'
        '<article class="panel"><h3>3. Plano de Ação Estratégico (Top 3 Ações)</h3>'
        f'<ul>{actions_html}</ul></article>'
        '<article class="panel" style="background-color: #fffaf0; border-left: 4px solid #f59e0b;">'
        '<h3>4. Limitações e Pontos Cegos</h3>'
        f'<ul>{limitations_html}</ul></article>'
        '</div></section>'
    )


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
    patterns_section = _patterns_section(patterns)
    distributions = metrics["distributions"]
    cross = metrics["cross_tabs"]
    profiles = metrics.get("root_cause_profiles", [])
    root_causes = distributions.get("root_cause_category", {})
    data_quality = analysis["data_quality"]
    mapping_rows = _schema_mapping_rows(data_quality)
    ingestion_profile = ", ".join(
        f"{key}: {value}"
        for key, value in analysis["data_quality"]
        .get("ingestion_profile", {})
        .items()
    ) or "Metadados de ingestão indisponíveis"
    quality_items = gate.get("errors", []) + gate.get("warnings", [])
    quality_html = "".join(
        f'<li><code>{_escape(item["code"])}</code> {_escape(item["message"])}</li>'
        for item in quality_items
    ) or "<li>Nenhum erro ou alerta.</li>"
    clarification_html = "".join(
        f'<li><code>{_escape(item["question_id"])}</code> '
        f'<b>{_escape(item["field"])}</b> · {_escape(item["status"])} — '
        f'{_escape(item["question"])}<br><span class="muted">'
        f'Bugs: {_escape(", ".join(item["bug_ids"]))}</span></li>'
        for item in analysis.get("clarification_questions", [])
    ) or "<li>Nenhuma pergunta de esclarecimento necessária.</li>"
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
<title>RCA Agent Lab · Analisando indicadores</title><style>{_DASHBOARD_CSS}</style><script>{plotly_js}</script></head><body>
<nav class="topbar"><div class="shell nav"><div class="brand"><i class="brand-mark"></i>RCA Agent Lab</div>
<div class="nav-links"><a href="#resumo">Resumo</a><a href="#kpis">KPIs</a><a href="#metodologia">Metodologia</a><a href="#graficos">Indicadores</a><a href="#rca">RCA</a><a href="#clusters">Clusters</a><a href="#conclusao">Conclusão</a><a href="#auditoria">Auditoria</a></div></div></nav>
<header class="hero"><div class="shell hero-grid"><div><span class="hero-kicker">Relatório HTML auditável</span><h1>Analisando Indicadores</h1>
<p>{_escape(_summary_sentence(analysis))}</p><span class="review-flag">Hipóteses · requires human review</span></div>
<aside class="hero-summary"><strong>{total}</strong><span>bugs analisados</span><p>{len(analysis["clusters"])} clusters · {len(analysis["hypotheses"])} hipóteses · {len(analysis["actions"])} controles</p></aside></div></header>
<main class="shell">
<section class="section" id="resumo"><h2 class="section-title">Resumo executivo</h2><div class="executive"><article class="panel"><h3>Leitura principal</h3><p>{_escape(_summary_sentence(analysis))}</p>
<div class="gate"><span>Quality gate</span><b>{_escape(gate["status"])}</b></div></article>
<div class="findings">{"".join(f'<article class="finding">{_escape(item)}</article>' for item in highlights)}</div></div></section>
<section class="section" id="clusters"><h2 class="section-title">Plano de Ação e Prioridades</h2><p class="section-subtitle">Investigação priorizada com evidência favorável, contraevidência, perguntas e ações mensuráveis.</p>
{_cluster_sections_v2(analysis)}</section>
<section class="section" id="kpis"><h2 class="section-title">KPIs principais</h2><p class="section-subtitle">Visão rápida dos indicadores; cada card possui uma análise detalhada logo abaixo.</p>
<div class="kpi-grid">{_kpi_cards_v2(metrics["kpis"])}</div></section>
<section class="section"><h2 class="section-title">Análise detalhada dos KPIs</h2><p class="section-subtitle">Definição, cálculo, leitura, evidência, limitações e interpretação de cada indicador.</p>
<div class="kpi-detail-list">{_kpi_details_v2(metrics["kpis"])}</div></section>
{_methodological_analysis_v2(analysis)}
<section class="section" id="graficos"><h2 class="section-title">Onde os problemas habitam (Distribuição)</h2>
<div class="slide-grid">
<article class="slide"><div class="slide-head"><h3>Evolução da qualidade</h3><p>Comparativo de criação, detecção e resolução de bugs</p></div>{_timeline_chart_plot(metrics.get("timelines", {}))}</article>
<article class="slide"><div class="slide-head"><h3>Distribuição geral de bugs</h3><p>Base total: {total} bugs. Valores ausentes usam sugestões somente após aprovação humana explícita.</p></div><div class="chart-two">
<div class="chart-box">{_mini_bar_chart(distributions.get("severity", {}), "Por severidade")}</div>
<div class="chart-box">{_mini_bar_chart(distributions.get("bug_type", {}), "Por tipo")}</div></div></article>
<article class="slide"><div class="chart-two">
<div class="chart-box">{_mini_bar_chart(distributions.get("environment", {}), "Por ambiente")}</div>
<div class="chart-box">{_mini_bar_chart(distributions.get("affected_module", {}), "Por componente")}</div></div></article>
<article class="slide"><div class="slide-head"><h3>Análise de causa raiz</h3><p>Categorias reportadas como sinais de triagem, não como causalidade confirmada</p></div>
{_bar_chart(root_causes, "Distribuição dos sinais RCA")}</article>
<article class="slide"><div class="slide-head"><h3>Resumo visual da análise de causa raiz</h3><p>Concentração dos sinais prioritários</p></div>{_cause_summary_v2(profiles, total)}</article>
<article class="slide"><div class="slide-head"><h3>Tipos de bugs por principais sinais RCA</h3></div>
{_stacked_chart(cross.get("bug_type_by_root_cause", {}), "Distribuição de tipos de bugs")}</article>
<article class="slide"><div class="slide-head"><h3>Criticidade por principais sinais RCA</h3></div>
{_stacked_chart(cross.get("severity_by_root_cause", {}), "Criticidade de bugs")}</article></div></section>
{patterns_section}
<section class="section"><h2 class="section-title">Perguntas de esclarecimento</h2>
<article class="panel"><ul>{clarification_html}</ul></article></section>
{_conclusion_section(analysis)}
<section class="section" id="auditoria"><h2 class="section-title">Auditoria e rastreabilidade</h2><article class="panel"><h3>Qualidade dos dados</h3>
<p>{_causal_signal_audit(data_quality)}</p><ul>{quality_html}</ul></article>
<h3 style="margin-top:24px">Adaptação do dataset</h3>
<p class="muted">Perfil de ingestão: {_escape(ingestion_profile)}. Mapeamento detectado entre os cabeçalhos da empresa e o modelo analítico. Campos não mapeados continuam preservados na fonte.</p>
<div class="table-wrap"><table><thead><tr><th>Campo da empresa</th><th>Campo analítico</th><th>Confiança</th><th>Score</th><th>Status</th></tr></thead><tbody>{mapping_rows}</tbody></table></div>
<div class="table-wrap" style="margin-top:20px"><table><thead><tr><th>Bug</th><th>Linha</th><th>Cluster</th><th>Hipótese</th><th>Ações</th></tr></thead><tbody>{trace_rows}</tbody></table></div>
<p class="muted" style="margin-top:18px">Similaridade, concentração e categoria reportada são sinais. Causa confirmada exige sequência temporal, mecanismo técnico e teste reproduzível.</p></section>
</main><footer>RCA Agent Lab · objeto canônico incorporado · gerado em {_escape(utc_now())}</footer>
<script id="rca-analysis" type="application/json">{embedded}</script></body></html>"""
