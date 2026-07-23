from rca_agent.quality import run_quality_gate


def test_gate_rejects_hypothesis_without_evidence():
    analysis = {
        "bugs": [{"bug_id": "B-1"}],
        "data_quality": {
            "total_records": 1,
            "causal_coverage_percent": 0,
            "prompt_injection_rows": [],
        },
        "metrics": {"distributions": {"severity": {"unknown": 1}}},
        "clusters": [
            {"cluster_id": "CL-001", "bug_ids": ["B-1"], "prioritized": True}
        ],
        "evidence": [],
        "hypotheses": [
            {
                "hypothesis_id": "HY-001",
                "cluster_id": "CL-001",
                "supporting_evidence_ids": [],
                "counter_evidence_ids": [],
                "status": "requires_human_review",
                "validation_method": "Executar teste reproduzível.",
                "confirmation_questions": ["Qual log confirma?"],
            }
        ],
        "actions": [],
    }
    gate = run_quality_gate(analysis)
    assert gate["status"] == "failed"
    assert any(item["code"] == "hypothesis_without_evidence" for item in gate["errors"])

