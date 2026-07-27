from pathlib import Path
from uuid import uuid4

import pytest

from rca_agent.pipeline import RcaPipeline
from rca_agent.pipeline.review import apply_review

ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_uses_injected_input_and_quality_boundaries():
    gate_calls: list[int] = []

    def ingest_records(_: str | Path) -> list[dict[str, str]]:
        return [{"id": "BUG-INJECTED", "title": "Registro de teste"}]

    def quality_gate(analysis: dict) -> dict:
        gate_calls.append(len(analysis["bugs"]))
        return {
            "status": "passed",
            "errors": [],
            "warnings": [],
            "checks": {"bug_count": len(analysis["bugs"])},
        }

    pipeline = RcaPipeline(
        input_ingestor=ingest_records,
        quality_gate=quality_gate,
    )
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex

    prepared = pipeline.prepare(output / "virtual-source.json", output)

    assert Path(prepared["analysis"]).exists()
    assert gate_calls == [1]


def test_review_cannot_overwrite_existing_evidence():
    original = {
        "evidence_id": "EV-001",
        "bug_id": "BUG-1",
        "source_type": "qa_note",
        "source_reference": "row:2",
        "excerpt": "Original",
        "reliability": "unassessed",
        "evidence_role": "reported_causal_signal",
        "epistemic_status": "unverified",
    }
    analysis = {"evidence": [original]}
    review = {"evidence": [{**original, "excerpt": "Alterado"}]}

    with pytest.raises(ValueError, match="redefinir EV-001"):
        apply_review(analysis, review, schema_validation=lambda _value, _name: None)
