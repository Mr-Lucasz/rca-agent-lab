from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from ..analysis.classification import classify_rules
from ..core.causal_signals import causal_signal_config
from ..core.schema_validation import validate_schema
from ..core.utils import utc_now
from ..metrics import calculate_metrics
from .clarifications import (
    apply_factual_answers,
    apply_field_mapping_decisions,
    build_clarification_questions,
    merge_clarification_responses,
    promote_accepted_suggestions,
    synchronize_clarification_review,
)

SchemaValidation = Callable[[Any, str], None]


def build_review_template(analysis: dict[str, Any]) -> dict[str, Any]:
    """Create an empty surface for evidence-grounded agent analysis."""

    return {
        "reviewed_by": "",
        "model": "",
        "sources_consulted": analysis["metadata"]["sources_consulted"],
        "clarification_questions": analysis.get("clarification_questions", []),
        "triage": [],
        "evidence": [],
        "insights": [],
        "hypotheses": [],
        "actions": [],
    }


def build_narrative_inputs(
    bugs: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Build deterministic context for the semantic review step."""

    evidence_by_bug = _index_evidence_by_bug(evidence)
    signal_config = causal_signal_config()
    return {
        "kpi_briefs": [_build_kpi_brief(kpi) for kpi in metrics.get("kpis", [])],
        "root_cause_signal_briefs": [
            _build_root_cause_brief(
                profile,
                bugs,
                evidence_by_bug,
                signal_config,
            )
            for profile in metrics.get("root_cause_profiles", [])
        ],
        "causal_signal_context": _build_causal_signal_context(
            bugs,
            evidence_by_bug,
            metrics,
            signal_config,
        ),
    }


def stage_review_clarifications(
    analysis: dict[str, Any],
    review: dict[str, Any],
) -> None:
    """Turn agent triage suggestions into auditable human questions."""

    preview_bugs = deepcopy(analysis["bugs"])
    _apply_triage(preview_bugs, review.get("triage", []))
    questions = build_clarification_questions(
        preview_bugs,
        analysis.get("data_quality", {}),
    )
    synchronize_clarification_review(review, questions)
    analysis["clarification_questions"] = questions


def _index_evidence_by_bug(
    evidence: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        result.setdefault(item["bug_id"], []).append(item)
    return result


def _build_kpi_brief(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "kpi_id": item["id"],
        "label": item["label"],
        "value": item["value"],
        "unit": item["unit"],
        "formula": item["formula"],
        "sample_size": item["sample_size"],
        "definition": item["definition"],
        "supporting_bug_ids": item["supporting_bug_ids"],
        "limitations": item["limitations"],
    }


def _build_root_cause_brief(
    profile: dict[str, Any],
    bugs: list[dict[str, Any]],
    evidence_by_bug: dict[str, list[dict[str, Any]]],
    signal_config: dict[str, Any],
) -> dict[str, Any]:
    cause = profile["root_cause_category"]
    related_bugs = [
        bug
        for bug in bugs
        if bug.get(
            "effective_root_cause_category",
            bug.get("root_cause_category"),
        )
        == cause
    ]
    causal_signals = _collect_causal_signals(
        related_bugs,
        evidence_by_bug,
        signal_config,
    )
    return {
        "root_cause_category": cause,
        "signal_axis": profile.get("signal_axis", "unassessed"),
        "related_bug_ids": [bug["bug_id"] for bug in related_bugs],
        "top_modules": profile.get("top_modules", []),
        "predominant_severity": profile.get("predominant_severity"),
        "avg_detection_lead_time_hours": profile.get(
            "avg_detection_lead_time_hours"
        ),
        "reopened_total": profile.get("reopened_total"),
        "production_total": profile.get("production_total"),
        "causal_signal_highlights": causal_signals,
        "causal_signal_evidence_ids": [
            item["evidence_id"] for item in causal_signals
        ],
        "corroborating_evidence_ids": _collect_corroborating_evidence_ids(
            related_bugs,
            evidence_by_bug,
            signal_config,
        ),
    }


def _collect_causal_signals(
    bugs: list[dict[str, Any]],
    evidence_by_bug: dict[str, list[dict[str, Any]]],
    signal_config: dict[str, Any],
) -> list[dict[str, Any]]:
    source_names = {
        source["source_type"]: name
        for name, source in signal_config["sources"].items()
    }
    return [
        {
            "bug_id": bug["bug_id"],
            "evidence_id": item["evidence_id"],
            "source": source_names[item["source_type"]],
            "excerpt": item["excerpt"],
            "epistemic_status": item["epistemic_status"],
        }
        for bug in bugs
        for item in evidence_by_bug.get(bug["bug_id"], [])
        if item["source_type"] in source_names
    ]


def _collect_corroborating_evidence_ids(
    bugs: list[dict[str, Any]],
    evidence_by_bug: dict[str, list[dict[str, Any]]],
    signal_config: dict[str, Any],
) -> list[str]:
    corroborating_sources = set(
        signal_config["corroborating_source_types"]
    )
    return [
        item["evidence_id"]
        for bug in bugs
        for item in evidence_by_bug.get(bug["bug_id"], [])
        if item["source_type"] in corroborating_sources
        and item.get("epistemic_status") in {"corroborated", "verified"}
    ]


def _build_causal_signal_context(
    bugs: list[dict[str, Any]],
    evidence_by_bug: dict[str, list[dict[str, Any]]],
    metrics: dict[str, Any],
    signal_config: dict[str, Any],
) -> dict[str, Any]:
    records = []
    for bug in bugs:
        signals = _collect_causal_signals(
            [bug],
            evidence_by_bug,
            signal_config,
        )
        if not signals:
            continue
        records.append(
            {
                "bug_id": bug["bug_id"],
                "cluster_id": bug.get("cluster_id"),
                "dimensions": {
                    field: bug.get(f"effective_{field}", bug.get(field))
                    for field in signal_config["contextual_dimensions"]
                },
                "signals": signals,
            }
        )
    return {
        "interpretation_scope": signal_config["interpretation_scope"],
        "methodology_config": "config/confidence-rules.yml",
        "summary": metrics.get("causal_signal_patterns", {}),
        "records": records,
    }


def apply_review(
    analysis: dict[str, Any],
    review: dict[str, Any],
    schema_validation: SchemaValidation = validate_schema,
) -> None:
    """Validate and merge a semantic review without overwriting reported values."""

    schema_validation(review, "agent-review.schema.json")
    _merge_evidence(analysis, review["evidence"])
    if "clarification_questions" in review:
        merge_clarification_responses(
            analysis,
            review["clarification_questions"],
        )
    apply_field_mapping_decisions(
        analysis["bugs"],
        analysis.get("clarification_questions", []),
    )
    classify_rules(analysis["bugs"])
    _apply_triage(analysis["bugs"], review["triage"])
    _replace_review_sections(analysis, review)
    promote_accepted_suggestions(
        analysis["bugs"],
        analysis.get("clarification_questions", []),
    )
    apply_factual_answers(
        analysis["bugs"],
        analysis.get("clarification_questions", []),
    )
    analysis["metrics"] = calculate_metrics(analysis["bugs"])
    analysis["narrative_inputs"] = build_narrative_inputs(
        analysis["bugs"],
        analysis["evidence"],
        analysis["metrics"],
    )
    _apply_narrative(analysis, review.get("narrative"))
    _record_review_metadata(analysis["metadata"], review)


def _merge_evidence(
    analysis: dict[str, Any], review_evidence: list[dict[str, Any]]
) -> None:
    existing = {item["evidence_id"]: item for item in analysis["evidence"]}
    for item in review_evidence:
        evidence_id = item["evidence_id"]
        if evidence_id in existing and existing[evidence_id] != item:
            raise ValueError(f"Review tenta redefinir {evidence_id}. Use um novo ID.")
        existing[evidence_id] = item
    analysis["evidence"] = list(existing.values())


def _apply_triage(
    bugs: list[dict[str, Any]], triage_items: list[dict[str, Any]]
) -> None:
    triage_by_bug = {item["bug_id"]: item for item in triage_items}
    suggested_fields = {
        "suggested_severity": "agent_suggested_severity",
        "suggested_bug_type": "agent_suggested_bug_type",
        "suggested_root_cause_category": "agent_suggested_root_cause_category",
    }
    for bug in bugs:
        triage = triage_by_bug.get(bug["bug_id"])
        if triage is None:
            continue
        for review_field, bug_field in suggested_fields.items():
            bug[bug_field] = triage.get(review_field, bug[bug_field])
        bug["agent_suggestion_confidence"] = triage["confidence"]
        bug["agent_suggestion_rationale"] = triage["rationale"]
        bug["agent_review_status"] = triage["review_status"]


def _replace_review_sections(
    analysis: dict[str, Any], review: dict[str, Any]
) -> None:
    for section in ("insights", "hypotheses", "actions"):
        if review[section]:
            analysis[section] = review[section]


def _apply_narrative(
    analysis: dict[str, Any], narrative: dict[str, Any] | None
) -> None:
    if not narrative:
        return
    analysis["narrative"] = narrative
    reviews_by_kpi = {
        item["kpi_id"]: item for item in narrative.get("kpi_reviews", [])
    }
    for kpi in analysis.get("metrics", {}).get("kpis", []):
        review = reviews_by_kpi.get(kpi["id"])
        if review is None:
            continue
        kpi["insight"] = review["insight"]
        kpi["detailed_analysis"] = review["detailed_analysis"]
        if review.get("limitations"):
            kpi["limitations"] = review["limitations"]
        if review.get("supporting_bug_ids"):
            kpi["supporting_bug_ids"] = review["supporting_bug_ids"]


def _record_review_metadata(
    metadata: dict[str, Any], review: dict[str, Any]
) -> None:
    semantic_review_requested = bool(
        str(review.get("reviewed_by", "")).strip()
        or str(review.get("model", "")).strip()
        or review.get("insights")
        or review.get("hypotheses")
        or review.get("actions")
        or review.get("narrative")
    )
    if not semantic_review_requested:
        metadata["sources_consulted"] = review["sources_consulted"]
        return
    metadata.update(
        {
            "sources_consulted": review["sources_consulted"],
            "reviewed_by": review["reviewed_by"],
            "model": review.get("model", ""),
            "mode": "agent-reviewed",
            "reviewed_at": utc_now(),
        }
    )
