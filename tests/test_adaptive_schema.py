import json
from pathlib import Path
from uuid import uuid4

from rca_agent.analysis.classification import classify_rules
from rca_agent.analysis.normalization import normalize
from rca_agent.pipeline import finalize, prepare, record_clarification
from rca_agent.pipeline.clarifications import build_clarification_questions

ROOT = Path(__file__).resolve().parents[1]


def test_adaptive_mapping_preserves_custom_taxonomies_and_source_fields():
    raw = [
        {
            "Defect Reference": "D-77",
            "Short Summary": "Regra regional incorreta",
            "Problem Statement": "O cálculo não segue a política local.",
            "Desired Outcome": "Aplicar a política ACME.",
            "Observed Outcome": "Aplicou a política global.",
            "Impact Level": "S1-Bloqueante",
            "Defect Category": "Regra Fiscal ACME",
            "Cause Category": "Handoff Tributário",
            "Service Area": "Motor Fiscal",
            "Deployment Tier": "Pré-Produção ACME",
        }
    ]

    bugs, quality = normalize(raw, Path("empresa-acme.csv"))

    assert bugs[0]["bug_id"] == "D-77"
    assert bugs[0]["title"] == "Regra regional incorreta"
    assert bugs[0]["severity"] == "S1-Bloqueante"
    assert bugs[0]["bug_type"] == "Regra Fiscal ACME"
    assert bugs[0]["root_cause_category"] == "Handoff Tributário"
    assert bugs[0]["environment"] == "Pré-Produção ACME"
    assert bugs[0]["source_fields"]["Service Area"] == "Motor Fiscal"
    assert quality["unmapped_source_fields"] == []


def test_medium_confidence_schema_mapping_creates_human_gate():
    raw = [
        {
            "Ticket": "BUG-1",
            "Summary": "Falha total no checkout",
            "Defect Criticality": "High",
            "Description": "Pagamento fica bloqueado.",
            "Expected": "Concluir pagamento.",
            "Actual": "Retorna erro.",
            "Module": "Checkout",
            "Environment": "Production",
            "Bug Type": "Functional",
            "Root Cause": "Implementation",
        }
    ]

    bugs, quality = normalize(raw, Path("empresa-beta.csv"))
    classify_rules(bugs)
    questions = build_clarification_questions(bugs, quality)

    mapping = next(
        item
        for item in quality["schema_mapping"]
        if item["source_field"] == "Defect Criticality"
    )
    question = next(
        item
        for item in questions
        if item["question_type"] == "confirm_field_mapping"
    )

    assert mapping["canonical_field"] == "severity"
    assert mapping["status"] == "needs_confirmation"
    assert bugs[0]["severity"] == "high"
    assert question["field"] == "severity"
    assert question["proposals"][0]["source_field"] == "Defect Criticality"


def test_confirmed_adaptive_mapping_continues_to_auditable_dashboard():
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex
    output.mkdir(parents=True)
    source = output / "company-export.json"
    source.write_text(
        json.dumps(
            [
                {
                    "Ticket": "BETA-1",
                    "Summary": "Falha total no checkout",
                    "Defect Criticality": "High",
                    "Description": "Pagamento fica bloqueado.",
                    "Expected": "Concluir pagamento.",
                    "Actual": "Retorna erro.",
                    "Module": "Checkout",
                    "Environment": "Production",
                    "Bug Type": "Functional",
                    "Root Cause": "Implementation",
                }
            ]
        ),
        encoding="utf-8",
    )
    prepared = prepare(source, output)
    review = json.loads(
        Path(prepared["review_template"]).read_text(encoding="utf-8")
    )
    mapping_question = next(
        item
        for item in review["clarification_questions"]
        if item["question_type"] == "confirm_field_mapping"
    )

    decision = record_clarification(
        prepared["work_dir"],
        mapping_question["question_id"],
        "accepted",
    )
    result = finalize(prepared["work_dir"], output, decision["review"])
    final_analysis = json.loads(
        (
            Path(prepared["work_dir"]) / "analysis.final.json"
        ).read_text(encoding="utf-8")
    )

    assert decision["open_questions"] == []
    assert result["quality_gate"]["status"] == "passed"
    assert final_analysis["metrics"]["distributions"]["severity"] == {"high": 1}
    assert "Adaptação do dataset" in Path(result["html"]).read_text(
        encoding="utf-8"
    )
