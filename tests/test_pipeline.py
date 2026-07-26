import csv
import json
from pathlib import Path
from uuid import uuid4

import pytest

from rca_agent.pipeline import (
    QualityGateError,
    finalize,
    prepare,
    prepare_review_questions,
    record_clarification,
    report_bug,
    validate_report,
)
from rca_agent.pipeline.clarifications import build_clarification_questions
from rca_agent.reporting import write_html

ROOT = Path(__file__).resolve().parents[1]


def test_rules_pipeline_generates_factual_outputs_without_fabricated_rca():
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex
    prepared = prepare(ROOT / "data" / "input" / "bugs-demo.csv", output)
    review = json.loads(
        Path(prepared["review_template"]).read_text(encoding="utf-8")
    )
    review_path = Path(prepared["work_dir"]) / "agent-review.json"
    review_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for question in review["clarification_questions"]:
        status = (
            "accepted"
            if question["question_type"].startswith("confirm_")
            else "declined"
        )
        record_clarification(
            prepared["work_dir"],
            question["question_id"],
            status,
        )
    result = finalize(prepared["work_dir"], output, review_path)

    assert Path(result["csv"]).exists()
    assert Path(result["html"]).exists()
    assert result["quality_gate"]["status"] == "passed"

    with Path(result["csv"]).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 12
    assert all(row["source_row"] for row in rows)
    assert all(row["requires_human_review"] == "true" for row in rows)
    final_analysis = json.loads(
        (Path(prepared["work_dir"]) / "analysis.final.json").read_text(
            encoding="utf-8"
        )
    )
    assert final_analysis["metadata"]["mode"] == "rules-baseline"
    assert final_analysis["insights"] == []
    assert final_analysis["hypotheses"] == []
    assert final_analysis["actions"] == []
    assert all(
        item["insight"] == "" and item["detailed_analysis"] == ""
        for item in final_analysis["metrics"]["kpis"]
    )

    html = Path(result["html"]).read_text(encoding="utf-8")
    for section in (
        "Resumo executivo",
        "KPIs principais",
        "Análise detalhada dos KPIs",
        "Distribuição geral de bugs",
        "Análise de causa raiz",
        "Plano de Ação e Prioridades",
        "Auditoria e rastreabilidade",
    ):
        assert section in html
    assert "plotly.js" in html
    assert "{chart_codigo}" not in html
    assert "{chart_testes}" not in html
    assert '<script id="rca-analysis" type="application/json">' in html
    assert "Dados insuficientes para formular hipótese rastreável." not in html
    assert "Por que não há hipótese neste cluster?" in html
    assert "O que falta" in html
    assert validate_report(result["html"])["status"] == "passed"


def test_prepare_creates_agent_review_surface():
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex
    prepared = prepare(ROOT / "data" / "input" / "bugs-demo.csv", output)
    template = json.loads(Path(prepared["review_template"]).read_text(encoding="utf-8"))
    analysis = json.loads(Path(prepared["analysis"]).read_text(encoding="utf-8"))

    assert template["insights"] == []
    assert template["hypotheses"] == []
    assert template["actions"] == []
    assert "clarification_questions" in template
    assert Path(prepared["clarification_questions"]).exists()
    assert "narrative" not in template
    assert analysis["narrative_inputs"]["kpi_briefs"]
    assert analysis["narrative_inputs"]["root_cause_signal_briefs"]
    signal_context = analysis["narrative_inputs"]["causal_signal_context"]
    assert len(signal_context["records"]) == 12
    assert sum(
        len(record["signals"]) for record in signal_context["records"]
    ) == 24
    assert all(
        signal["evidence_id"]
        for record in signal_context["records"]
        for signal in record["signals"]
    )
    assert analysis["metadata"]["mode"] == "rules-baseline"
    assert all(
        {
            "definition",
            "supporting_bug_ids",
            "requires_human_review",
        }
        <= set(item)
        for item in analysis["metrics"]["kpis"]
    )
    serialized = json.dumps(template, ensure_ascii=False).casefold()
    assert "substitua" not in serialized
    assert "escreva" not in serialized


def test_empty_agent_review_is_blocked_before_final_dashboard():
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex
    prepared = prepare(ROOT / "data" / "input" / "bugs-demo.csv", output)
    review_path = Path(prepared["work_dir"]) / "agent-review.json"
    review = json.loads(
        Path(prepared["review_template"]).read_text(encoding="utf-8")
    )
    review["reviewed_by"] = "semantic-gate-test"
    review["model"] = "test-model"
    review_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for question in review["clarification_questions"]:
        record_clarification(
            prepared["work_dir"],
            question["question_id"],
            "declined",
        )

    with pytest.raises(QualityGateError, match="análise semântica"):
        finalize(prepared["work_dir"], output, review_path)

    assert not (output / "rca-report.html").exists()


def test_agent_triage_becomes_human_confirmation_without_keyword_rules():
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex
    source = output / "missing-type.json"
    output.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "id": "SEM-1",
                "titulo": "Comportamento específico da empresa",
                "descricao": "O fluxo não segue a política interna.",
                "comportamento_esperado": "Aplicar a política aprovada.",
                "comportamento_obtido": "Aplicou outra regra.",
                "severidade": "alta",
                "ambiente": "produção",
                "modulo": "motor",
                "causa_raiz": "Política ACME",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    prepared = prepare(source, output)
    review_path = Path(prepared["work_dir"]) / "agent-review.json"
    review = json.loads(
        Path(prepared["review_template"]).read_text(encoding="utf-8")
    )
    review["triage"] = [
        {
            "bug_id": "SEM-1",
            "suggested_bug_type": "Regra interna ACME",
            "confidence": "medium",
            "rationale": (
                "A diferença entre o comportamento esperado e o observado "
                "está vinculada à política descrita no próprio ticket."
            ),
            "review_status": "insufficient_evidence",
        }
    ]
    review_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = prepare_review_questions(prepared["work_dir"], review_path)
    question = next(
        item
        for item in result["open_questions"]
        if item["field"] == "bug_type"
    )

    assert question["question_type"] == "confirm_suggestions"
    assert question["proposals"] == [
        {
            "bug_id": "SEM-1",
            "suggested_value": "Regra interna ACME",
            "confidence": "medium",
            "rationale": (
                "A diferença entre o comportamento esperado e o observado "
                "está vinculada à política descrita no próprio ticket."
            ),
        }
    ]


def test_clarification_questions_offer_inference_and_request_factual_context():
    bugs = [
        {
            "bug_id": "BUG-1",
            "severity": "unknown",
            "bug_type": "unknown",
            "environment": "unknown",
            "agent_suggested_severity": "high",
            "agent_suggested_bug_type": "functional",
            "agent_suggestion_confidence": "medium",
            "agent_suggestion_rationale": "Descrição e comportamentos indicam impacto funcional alto.",
        },
        {
            "bug_id": "BUG-2",
            "severity": "medium",
            "bug_type": "unknown",
            "environment": "production",
            "agent_suggested_severity": "medium",
            "agent_suggested_bug_type": "performance",
            "agent_suggestion_confidence": "high",
            "agent_suggestion_rationale": "O relato registra timeout reproduzível.",
        },
    ]

    questions = build_clarification_questions(bugs)
    by_field = {item["field"]: item for item in questions}

    assert by_field["severity"]["question_type"] == "confirm_suggestions"
    assert by_field["severity"]["bug_ids"] == ["BUG-1"]
    assert by_field["severity"]["proposals"][0]["suggested_value"] == "high"
    assert by_field["bug_type"]["bug_ids"] == ["BUG-1", "BUG-2"]
    assert by_field["environment"]["question_type"] == "request_information"
    assert by_field["environment"]["bug_ids"] == ["BUG-1"]
    assert by_field["environment"]["proposals"] == []
    assert all(item["status"] == "open" for item in questions)


def test_report_bug_generates_structured_outputs():
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex
    source = output / "single-bug.json"
    output.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "id": "BUG-777",
                "titulo": "Webhook falha no retry",
                "severidade": "alta",
                "descricao": "Retry do webhook devolve 401 após expiração da sessão.",
                "comportamento_esperado": "O retry deve renovar a credencial.",
                "comportamento_obtido": "O segundo envio reutiliza token expirado.",
                "bug_type": "security",
                "causa_raiz": "implementation",
                "modulo": "autenticação",
                "ambiente": "produção",
                "notas_dev": "Token foi armazenado fora do ciclo de retry.",
                "notas_qa": "Cenário reproduzido após o TTL.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = report_bug(source, output)

    assert Path(result["json"]).exists()
    assert Path(result["markdown"]).exists()
    markdown = Path(result["markdown"]).read_text(encoding="utf-8")
    assert "Webhook falha no retry" in markdown
    assert "Comportamento observado" in markdown


def test_write_html_repairs_common_corrupted_accent_tokens():
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex
    prepared = prepare(ROOT / "data" / "input" / "bugs-demo.csv", output)
    analysis = json.loads(Path(prepared["analysis"]).read_text(encoding="utf-8"))
    analysis["narrative"] = {
        "headline": "Teste de valida??o",
        "executive_summary": "A an?lise n?o deve manter texto corrompido no relat?rio.",
        "key_findings": ["Identifica??o corrigida automaticamente."],
        "systemic_patterns": ["Recorr?ncia descrita com acentua??o corrigida."],
        "root_cause_signal_reviews": [],
    }

    html_path = output / "accent-fix-report.html"
    write_html(html_path, analysis)
    html = html_path.read_text(encoding="utf-8")

    assert "análise" in html
    assert "não" in html
    assert "relatório" in html
    assert "validação" in html
    assert "an?lise" not in html
    assert "A an?lise n?o deve manter texto corrompido no relat?rio." not in html
    assert "valida??o" not in html
