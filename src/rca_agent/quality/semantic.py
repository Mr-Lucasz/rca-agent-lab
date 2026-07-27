from __future__ import annotations

from typing import Any, Protocol


class Findings(Protocol):
    def error(self, code: str, message: str) -> None: ...


def check_semantic_review(
    analysis: dict[str, Any], findings: Findings
) -> None:
    if analysis.get("metadata", {}).get("mode") != "agent-reviewed":
        return

    required_sections = ("insights", "hypotheses", "actions")
    missing = [name for name in required_sections if not analysis.get(name)]
    narrative = analysis.get("narrative", {})
    required_narrative = (
        "headline",
        "executive_summary",
        "key_findings",
        "systemic_patterns",
    )
    if not narrative or any(not narrative.get(name) for name in required_narrative):
        missing.append("narrative")
    if missing:
        findings.error(
            "semantic_review_incomplete",
            (
                "A publicação final exige análise semântica produzida a partir das "
                f"evidências. Seções ausentes: {', '.join(missing)}."
            ),
        )

    serialized = str(
        {
            "insights": analysis.get("insights", []),
            "hypotheses": analysis.get("hypotheses", []),
            "actions": analysis.get("actions", []),
            "narrative": narrative,
        }
    ).casefold()
    placeholders = ("substitua", "escreva uma", "replace-with")
    if any(token in serialized for token in placeholders):
        findings.error(
            "semantic_placeholder",
            "A revisão semântica ainda contém texto de placeholder.",
        )


def check_insights(analysis: dict[str, Any], findings: Findings) -> None:
    evidence_ids = {
        item.get("evidence_id") for item in analysis.get("evidence", [])
    }
    insight_ids: list[Any] = []
    for insight in analysis.get("insights", []):
        identifier = insight.get("insight_id", "?")
        insight_ids.append(identifier)
        referenced = insight.get("evidence_ids", [])
        if not referenced:
            findings.error(
                "insight_without_evidence",
                f"{identifier} não possui evidência.",
            )
        missing = set(referenced) - evidence_ids
        if missing:
            findings.error(
                "insight_missing_evidence",
                f"{identifier} referencia {sorted(missing)}.",
            )
    if len(set(insight_ids)) != len(insight_ids):
        findings.error("duplicate_insight_id", "Há insight_id repetido.")


def check_methodology_reviews(
    analysis: dict[str, Any], findings: Findings
) -> None:
    reviews = analysis.get("narrative", {}).get("methodology_reviews", [])
    evidence_ids = {
        item.get("evidence_id") for item in analysis.get("evidence", [])
    }
    for index, review in enumerate(reviews, 1):
        referenced = review.get("evidence_ids", [])
        if not referenced:
            findings.error(
                "methodology_without_evidence",
                f"Bloco metodológico {index} não possui evidência.",
            )
        missing = set(referenced) - evidence_ids
        if missing:
            findings.error(
                "methodology_missing_evidence",
                f"Bloco metodológico {index} referencia {sorted(missing)}.",
            )
        if len(review.get("labels", [])) != len(review.get("values", [])):
            findings.error(
                "methodology_dimension_mismatch",
                f"Bloco metodológico {index} tem rótulos e valores incompatíveis.",
            )


def check_cluster_gap_reviews(
    analysis: dict[str, Any], findings: Findings
) -> None:
    reviews = analysis.get("narrative", {}).get("cluster_gap_reviews", [])
    cluster_ids = {
        item.get("cluster_id") for item in analysis.get("clusters", [])
    }
    evidence_ids = {
        item.get("evidence_id") for item in analysis.get("evidence", [])
    }
    seen: set[Any] = set()
    for review in reviews:
        cluster_id = review.get("cluster_id")
        if cluster_id in seen:
            findings.error(
                "duplicate_cluster_gap_review",
                f"Há mais de uma revisão de lacuna para {cluster_id}.",
            )
        seen.add(cluster_id)
        if cluster_id not in cluster_ids:
            findings.error(
                "cluster_gap_missing_cluster",
                f"A revisão de lacuna referencia {cluster_id} inexistente.",
            )
        missing = set(review.get("evidence_ids", [])) - evidence_ids
        if missing:
            findings.error(
                "cluster_gap_missing_evidence",
                f"{cluster_id} referencia {sorted(missing)}.",
            )
