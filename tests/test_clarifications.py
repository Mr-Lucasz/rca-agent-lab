import json
from pathlib import Path
from uuid import uuid4

import pytest

from rca_agent.metrics import calculate_metrics
from rca_agent.pipeline import (
    ClarificationRequiredError,
    finalize,
    prepare,
    record_clarification,
)
from rca_agent.pipeline.clarifications import (
    apply_factual_answers,
    promote_accepted_suggestions,
    synchronize_clarification_review,
)
from rca_agent.quality import run_quality_gate

ROOT = Path(__file__).resolve().parents[1]


def test_quality_gate_warns_about_open_clarifications():
    analysis = {
        "metadata": {},
        "data_quality": {
            "total_records": 0,
            "causal_signal_coverage_percent": 100,
            "prompt_injection_rows": [],
        },
        "bugs": [],
        "metrics": {"distributions": {}, "kpis": []},
        "clusters": [],
        "evidence": [],
        "hypotheses": [],
        "actions": [],
        "clarification_questions": [
            {
                "question_id": "CQ-001",
                "field": "environment",
                "status": "open",
            }
        ],
    }

    gate = run_quality_gate(analysis)

    assert any(
        item["code"] == "open_clarifications" for item in gate["warnings"]
    )


def test_quality_gate_distinguishes_declined_from_open_clarifications():
    analysis = {
        "metadata": {},
        "data_quality": {
            "total_records": 0,
            "causal_signal_coverage_percent": 100,
            "prompt_injection_rows": [],
        },
        "bugs": [],
        "metrics": {"distributions": {}, "kpis": []},
        "clusters": [],
        "evidence": [],
        "hypotheses": [],
        "actions": [],
        "clarification_questions": [
            {
                "question_id": "CQ-001",
                "field": "environment",
                "status": "declined",
            }
        ],
    }

    gate = run_quality_gate(analysis)
    warning_codes = {item["code"] for item in gate["warnings"]}

    assert "clarifications_declined" in warning_codes
    assert "open_clarifications" not in warning_codes


def test_finalize_blocks_until_human_resolves_every_open_question():
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex
    source = output / "bug-with-missing-triage.json"
    output.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "id": "BUG-GATE-1",
                "titulo": "Timeout crítico impede pagamento",
                "descricao": "Checkout expira e impede concluir a compra.",
                "comportamento_esperado": "Pagamento deve concluir sem timeout.",
                "comportamento_obtido": "A API devolve timeout e bloqueia o usuário.",
                "modulo": "pagamentos",
                "causa_raiz": "implementation",
                "notas_dev": "A chamada externa não possui fallback.",
                "notas_qa": "Falha reproduzida em três tentativas.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    prepared = prepare(source, output)

    with pytest.raises(ClarificationRequiredError, match="gate humano"):
        finalize(prepared["work_dir"], output)

    assert not (output / "rca-report.html").exists()
    assert (
        Path(prepared["work_dir"]) / "analysis.awaiting-clarification.json"
    ).exists()

    review = json.loads(
        Path(prepared["review_template"]).read_text(encoding="utf-8")
    )
    for question in review["clarification_questions"]:
        if question["question_type"] == "confirm_suggestions":
            decision = record_clarification(
                prepared["work_dir"],
                question["question_id"],
                "accepted",
            )
        else:
            decision = record_clarification(
                prepared["work_dir"],
                question["question_id"],
                "answered",
                "production",
            )
    assert decision["open_questions"] == []

    result = finalize(prepared["work_dir"], output, decision["review"])

    assert Path(result["html"]).exists()
    assert result["quality_gate"]["status"] == "passed"


def test_accepted_suggestion_becomes_effective_without_overwriting_source():
    bugs = [
        {
            "bug_id": "BUG-APPROVED",
            "severity": "medium",
            "bug_type": "unknown",
            "environment": "production",
            "affected_module": "checkout",
            "root_cause_category": "unknown",
            "team": "unknown",
            "version": "unknown",
            "reopened": "unknown",
            "created_at": "unknown",
            "detected_at": "unknown",
            "resolved_at": "unknown",
            "dev_analysis_notes": "unknown",
            "qa_analysis_notes": "unknown",
            "effective_severity": "medium",
            "effective_severity_source": "reported",
            "effective_bug_type": "unknown",
            "effective_bug_type_source": "unknown",
            "effective_environment": "production",
            "effective_environment_source": "reported",
            "agent_suggested_bug_type": "functional",
            "agent_suggested_severity": "medium",
        }
    ]
    questions = [
        {
            "question_id": "CQ-001",
            "field": "bug_type",
            "question_type": "confirm_suggestions",
            "bug_ids": ["BUG-APPROVED"],
            "status": "accepted",
        }
    ]

    promote_accepted_suggestions(bugs, questions)
    metrics = calculate_metrics(bugs)

    assert bugs[0]["bug_type"] == "unknown"
    assert bugs[0]["effective_bug_type"] == "functional"
    assert (
        bugs[0]["effective_bug_type_source"]
        == "human_approved_agent_suggestion"
    )
    assert metrics["distributions"]["bug_type"] == {"functional": 1}


def test_factual_answer_becomes_effective_and_supports_per_bug_json():
    bugs = [
        {
            "bug_id": "BUG-FACT",
            "environment": "unknown",
            "affected_module": "unknown",
            "effective_environment": "unknown",
            "effective_environment_source": "unknown",
            "effective_affected_module": "unknown",
            "effective_affected_module_source": "unknown",
        }
    ]
    questions = [
        {
            "field": "environment",
            "question_type": "request_information",
            "bug_ids": ["BUG-FACT"],
            "status": "answered",
            "answer": "produção",
        },
        {
            "field": "affected_module",
            "question_type": "request_information",
            "bug_ids": ["BUG-FACT"],
            "status": "answered",
            "answer": '{"BUG-FACT": "Motor Fiscal"}',
        },
    ]

    apply_factual_answers(bugs, questions)

    assert bugs[0]["environment"] == "unknown"
    assert bugs[0]["effective_environment"] == "production"
    assert bugs[0]["effective_environment_source"] == "human_answered"
    assert bugs[0]["effective_affected_module"] == "Motor Fiscal"


def test_regenerated_questions_keep_prior_decision_by_semantic_identity():
    review = {
        "clarification_questions": [
            {
                "question_id": "CQ-001",
                "field": "bug_type",
                "question_type": "confirm_suggestions",
                "status": "accepted",
            }
        ]
    }
    regenerated = [
        {
            "question_id": "CQ-MAP-COL-SEVERITY",
            "field": "severity",
            "question_type": "confirm_field_mapping",
            "proposals": [{"source_field": "Criticality"}],
            "status": "open",
        },
        {
            "question_id": "CQ-VAL-BUG-TYPE",
            "field": "bug_type",
            "question_type": "confirm_suggestions",
            "proposals": [],
            "status": "open",
        },
    ]

    synchronize_clarification_review(review, regenerated)

    assert review["clarification_questions"][0]["status"] == "open"
    assert review["clarification_questions"][1]["status"] == "accepted"
