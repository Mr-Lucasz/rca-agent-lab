from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .utils import UNKNOWN

GENERIC_ACTIONS = {
    "melhorar testes",
    "aumentar cobertura",
    "melhorar comunicação",
    "prestar mais atenção",
    "revisar processo",
}


def run_quality_gate(analysis: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def error(code: str, message: str) -> None:
        errors.append({"code": code, "message": message})

    def warn(code: str, message: str) -> None:
        warnings.append({"code": code, "message": message})

    bugs = analysis.get("bugs", [])
    total = len(bugs)
    metadata = analysis.get("metadata", {})
    if metadata.get("mode") == "agent-reviewed":
        reviewer = str(metadata.get("reviewed_by", ""))
        model = str(metadata.get("model", ""))
        if reviewer.startswith("replace-") or model.startswith("replace-"):
            error("review_metadata_placeholder", "O review ainda contém metadados de placeholder.")
    quality_total = analysis.get("data_quality", {}).get("total_records")
    if quality_total != total:
        error("record_count_mismatch", f"Qualidade informa {quality_total}; análise contém {total}.")

    for field, values in analysis.get("metrics", {}).get("distributions", {}).items():
        if sum(int(value) for value in values.values()) != total:
            error("distribution_mismatch", f"Distribuição {field} não soma {total}.")

    for kpi in analysis.get("metrics", {}).get("kpis", []):
        required = ("definition", "insight", "detailed_analysis", "supporting_bug_ids")
        if any(key not in kpi for key in required):
            error(
                "incomplete_kpi_analysis",
                f"{kpi.get('id', '?')} não tem definição, insight, análise detalhada ou evidências.",
            )
        if kpi.get("requires_human_review") is not True:
            error(
                "kpi_review_status",
                f"{kpi.get('id', '?')} não está marcado para revisão humana.",
            )

    evidence = analysis.get("evidence", [])
    evidence_ids = [item.get("evidence_id") for item in evidence]
    duplicate_evidence = [item for item, count in Counter(evidence_ids).items() if count > 1]
    if duplicate_evidence:
        error("duplicate_evidence_id", f"IDs repetidos: {duplicate_evidence}.")
    evidence_set = set(evidence_ids)

    cluster_ids = {item.get("cluster_id") for item in analysis.get("clusters", [])}
    bug_ids = {bug.get("bug_id") for bug in bugs}
    for cluster in analysis.get("clusters", []):
        missing_bugs = set(cluster.get("bug_ids", [])) - bug_ids
        if missing_bugs:
            error("cluster_missing_bug", f"{cluster['cluster_id']} referencia {sorted(missing_bugs)}.")

    hypotheses = analysis.get("hypotheses", [])
    hypothesis_ids = [item.get("hypothesis_id") for item in hypotheses]
    if len(set(hypothesis_ids)) != len(hypothesis_ids):
        error("duplicate_hypothesis_id", "Há hypothesis_id repetido.")
    hypothesis_set = set(hypothesis_ids)
    hypotheses_by_cluster: dict[str, int] = Counter()
    for hypothesis in hypotheses:
        identifier = hypothesis.get("hypothesis_id", "?")
        cluster_id = hypothesis.get("cluster_id")
        hypotheses_by_cluster[cluster_id] += 1
        if cluster_id not in cluster_ids:
            error("hypothesis_missing_cluster", f"{identifier} referencia cluster inexistente.")
        supporting = hypothesis.get("supporting_evidence_ids", [])
        if not supporting:
            error("hypothesis_without_evidence", f"{identifier} não possui evidência.")
        missing = set(supporting + hypothesis.get("counter_evidence_ids", [])) - evidence_set
        if missing:
            error("hypothesis_missing_evidence", f"{identifier} referencia {sorted(missing)}.")
        if hypothesis.get("status") != "requires_human_review":
            error("causality_status", f"{identifier} não está requires_human_review.")
        if not hypothesis.get("validation_method") or not hypothesis.get("confirmation_questions"):
            error("hypothesis_not_falsifiable", f"{identifier} não tem validação/perguntas.")

    for cluster in analysis.get("clusters", []):
        if cluster.get("prioritized") and hypotheses_by_cluster.get(cluster["cluster_id"], 0) == 0:
            warn(
                "prioritized_cluster_without_hypothesis",
                f"{cluster['cluster_id']} não tem hipótese; dados podem ser insuficientes.",
            )

    actions = analysis.get("actions", [])
    action_ids = [item.get("action_id") for item in actions]
    if len(set(action_ids)) != len(action_ids):
        error("duplicate_action_id", "Há action_id repetido.")
    barriers: dict[str, set[str]] = defaultdict(set)
    for action in actions:
        identifier = action.get("action_id", "?")
        hypothesis_id = action.get("hypothesis_id")
        if hypothesis_id not in hypothesis_set:
            error("action_missing_hypothesis", f"{identifier} referencia hipótese inexistente.")
        if action.get("cluster_id") not in cluster_ids:
            error("action_missing_cluster", f"{identifier} referencia cluster inexistente.")
        missing = set(action.get("evidence_ids", [])) - evidence_set
        if missing:
            error("action_missing_evidence", f"{identifier} referencia {sorted(missing)}.")
        barriers[hypothesis_id].add(action.get("barrier_type"))
        normalized = str(action.get("statement", "")).casefold().strip(" .")
        if normalized in GENERIC_ACTIONS or len(normalized) < 16:
            error("generic_action", f"{identifier} é genérica.")
        required_text = ("owner_role", "horizon", "success_metric", "validation_method")
        if any(not action.get(field) or action.get(field) == UNKNOWN for field in required_text):
            error("incomplete_action", f"{identifier} não tem dono, horizonte, métrica ou validação.")
        if action.get("status") != "requires_human_review":
            error("action_status", f"{identifier} não está requires_human_review.")
    expected_barriers = {"corrective", "detective", "preventive"}
    for hypothesis_id in hypothesis_set:
        if barriers.get(hypothesis_id, set()) != expected_barriers:
            error("missing_barrier", f"{hypothesis_id} não tem as três barreiras.")

    coverage = analysis.get("data_quality", {}).get("causal_coverage_percent", 0)
    if coverage < 50:
        warn("low_causal_coverage", f"Apenas {coverage}% dos bugs têm notas QA/Dev.")
    if total < 5:
        warn("small_sample", f"Amostra de {total} bug(s); evitar generalização.")
    if analysis.get("data_quality", {}).get("prompt_injection_rows"):
        warn("untrusted_content", "A entrada contém texto semelhante a instruções; foi tratado como dado.")

    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "bug_count": total,
            "evidence_count": len(evidence),
            "hypothesis_count": len(hypotheses),
            "action_count": len(actions),
        },
    }
