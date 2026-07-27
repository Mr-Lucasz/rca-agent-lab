from pathlib import Path

from rca_agent.analysis.classification import classify_rules
from rca_agent.analysis.clustering import (
    _complete_linkage_components,
    build_clusters,
)
from rca_agent.analysis.normalization import normalize
from rca_agent.analysis.reasoning import build_evidence
from rca_agent.quality import run_quality_gate

ROOT = Path(__file__).resolve().parents[1]


def test_complete_linkage_does_not_chain_dissimilar_endpoints():
    bugs = [
        {"affected_module": "unknown", "bug_type": "unknown", "root_cause_category": "unknown", "team": "unknown"},
        {"affected_module": "unknown", "bug_type": "unknown", "root_cause_category": "unknown", "team": "unknown"},
        {"affected_module": "unknown", "bug_type": "unknown", "root_cause_category": "unknown", "team": "unknown"},
    ]
    similarities = {
        (0, 1): 0.70,
        (0, 2): 0.10,
        (1, 2): 0.70,
    }
    method = {
        "similarity_threshold": 0.60,
        "same_signature_minimum_similarity": 0.50,
        "same_signature": {
            "required_equal_fields": ["affected_module"],
            "any_equal_fields": ["bug_type"],
        },
    }

    groups = _complete_linkage_components(bugs, similarities, method)

    assert sorted(len(group) for group in groups) == [1, 2]
    assert not any(set(group) == {0, 1, 2} for group in groups)


def test_singleton_is_not_labeled_as_duplicate_family():
    source = ROOT / "data" / "input" / "single.json"
    bugs, _ = normalize(
        [{"id": "B-1", "titulo": "Falha única no pagamento"}],
        source,
    )
    classify_rules(bugs)

    clusters = build_clusters(bugs)

    assert bugs[0]["duplicate_candidate_family_id"] == "unknown"
    assert bugs[0]["duplicate_candidate_status"] == "not_candidate"
    assert clusters[0]["cluster_confidence"] == "unvalidated"
    assert (
        clusters[0]["methodology"]["calibration_status"]
        == "uncalibrated"
    )


def test_reported_notes_are_not_automatically_high_reliability():
    source = ROOT / "data" / "input" / "notes.json"
    bugs, _ = normalize(
        [
            {
                "id": "B-1",
                "titulo": "Falha no retry",
                "notas_dev": "O retry reutilizou a credencial.",
                "notas_qa": "Cenário reproduzido uma vez.",
            }
        ],
        source,
    )

    evidence = build_evidence(bugs)

    note_evidence = [
        item
        for item in evidence
        if item["source_type"] in {"dev_note", "qa_note"}
    ]
    assert note_evidence
    assert {item["reliability"] for item in note_evidence} == {"unassessed"}
    assert all(item["reliability_basis"] for item in note_evidence)
    assert {item["evidence_role"] for item in note_evidence} == {
        "reported_causal_signal"
    }
    assert {item["epistemic_status"] for item in note_evidence} == {
        "unverified"
    }


def _analysis_with_one_hypothesis() -> dict:
    evidence = {
        "evidence_id": "EV-0001",
        "source_type": "test",
        "source_ref": "tests/example.py::test_retry",
        "bug_id": "B-1",
        "excerpt": "O teste reproduz a falha.",
        "reliability": "medium",
        "evidence_role": "observed_artifact",
        "epistemic_status": "verified",
        "observed_at": None,
    }
    return {
        "metadata": {},
        "data_quality": {
            "total_records": 1,
            "usable_for_metrics": 1,
            "causal_signal_coverage_percent": 100,
            "prompt_injection_rows": [],
        },
        "bugs": [{"bug_id": "B-1"}],
        "metrics": {"distributions": {}, "kpis": []},
        "clusters": [
            {"cluster_id": "CL-001", "bug_ids": ["B-1"], "prioritized": True}
        ],
        "evidence": [evidence],
        "insights": [],
        "hypotheses": [
            {
                "hypothesis_id": "HY-001",
                "cluster_id": "CL-001",
                "supporting_evidence_ids": ["EV-0001"],
                "counter_evidence_ids": [],
                "status": "requires_human_review",
                "validation_method": "Executar o teste de retry isoladamente.",
                "confirmation_questions": ["A falha desaparece ao renovar a credencial?"],
            }
        ],
        "actions": [
            {
                "action_id": "AC-001",
                "hypothesis_id": "HY-001",
                "cluster_id": "CL-001",
                "barrier_type": "detective",
                "statement": "Adicionar teste de retry com credencial expirada.",
                "owner_role": "QA",
                "horizon": "próxima sprint",
                "success_metric": "Teste falha antes e passa depois da correção.",
                "validation_method": "Executar o teste no pipeline de integração.",
                "residual_risk": "Cenários de concorrência não cobertos.",
                "evidence_ids": ["EV-0001"],
                "status": "requires_human_review",
            }
        ],
    }


def test_quality_gate_does_not_force_three_action_types():
    gate = run_quality_gate(_analysis_with_one_hypothesis())

    assert not any(
        item["code"] in {"missing_action", "missing_barrier"}
        for item in gate["errors"]
    )


def test_rework_estimate_requires_reproducible_basis():
    analysis = _analysis_with_one_hypothesis()
    analysis["hypotheses"][0]["estimated_rework_hours"] = 40

    gate = run_quality_gate(analysis)

    assert any(
        item["code"] == "unsupported_rework_estimate"
        for item in gate["errors"]
    )


def test_high_causal_confidence_cannot_rely_only_on_team_opinion():
    analysis = _analysis_with_one_hypothesis()
    evidence = analysis["evidence"][0]
    evidence["source_type"] = "dev_note"
    evidence["evidence_role"] = "reported_causal_signal"
    evidence["epistemic_status"] = "unverified"
    evidence["reliability"] = "unassessed"
    analysis["hypotheses"][0]["confidence"] = "high"

    gate = run_quality_gate(analysis)

    assert any(
        item["code"] == "hypothesis_only_unverified_statements"
        for item in gate["warnings"]
    )
    assert any(
        item["code"] == "high_confidence_from_unverified_statements"
        for item in gate["errors"]
    )


def test_convergent_reported_signals_can_support_medium_hypothesis():
    analysis = _analysis_with_one_hypothesis()
    evidence = analysis["evidence"][0]
    evidence["source_type"] = "dev_note"
    evidence["evidence_role"] = "reported_causal_signal"
    evidence["epistemic_status"] = "unverified"
    evidence["reliability"] = "unassessed"
    analysis["hypotheses"][0]["confidence"] = "medium"

    gate = run_quality_gate(analysis)

    assert any(
        item["code"] == "hypothesis_only_unverified_statements"
        for item in gate["warnings"]
    )
    assert not any(
        item["code"] == "high_confidence_from_unverified_statements"
        for item in gate["errors"]
    )


def test_team_causal_opinion_does_not_drive_cluster_similarity():
    source = ROOT / "data" / "input" / "notes.json"
    bugs, _ = normalize(
        [
            {
                "id": "B-1",
                "titulo": "Timeout exclusivo no checkout",
                "notas_dev": "A causa raiz é falta de revisão do time.",
            },
            {
                "id": "B-2",
                "titulo": "Contraste incorreto no rodapé",
                "notas_dev": "A causa raiz é falta de revisão do time.",
            },
        ],
        source,
    )
    classify_rules(bugs)

    clusters = build_clusters(bugs)

    assert [cluster["size"] for cluster in clusters] == [1, 1]
