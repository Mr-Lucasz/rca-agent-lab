from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from ..core.config import load_yaml
from ..core.utils import UNKNOWN
from .adaptation import check_effective_values, check_schema_adaptation
from .evidence_claims import check_hypothesis_evidence_quality
from .limitations import (
    check_clarification_questions,
    check_data_limitations,
)
from .semantic import (
    check_cluster_gap_reviews,
    check_insights,
    check_methodology_reviews,
    check_semantic_review,
)

Analysis = dict[str, Any]

@dataclass
class QualityFindings:
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)

    def error(self, code: str, message: str) -> None:
        self.errors.append({"code": code, "message": message})

    def warn(self, code: str, message: str) -> None:
        self.warnings.append({"code": code, "message": message})


class QualityCheck(Protocol):
    def __call__(self, analysis: Analysis, findings: QualityFindings) -> None:
        """Append errors and warnings for one quality concern."""


class QualityGate:
    """Runs independently replaceable checks over a canonical analysis."""

    def __init__(self, checks: Iterable[QualityCheck]) -> None:
        self._checks = tuple(checks)

    def run(self, analysis: Analysis) -> dict[str, Any]:
        findings = QualityFindings()
        for check in self._checks:
            check(analysis, findings)
        return {
            "status": "passed" if not findings.errors else "failed",
            "errors": findings.errors,
            "warnings": findings.warnings,
            "checks": {
                "bug_count": len(analysis.get("bugs", [])),
                "evidence_count": len(analysis.get("evidence", [])),
                "hypothesis_count": len(analysis.get("hypotheses", [])),
                "action_count": len(analysis.get("actions", [])),
            },
        }


def _check_review_metadata(analysis: Analysis, findings: QualityFindings) -> None:
    metadata = analysis.get("metadata", {})
    if metadata.get("mode") != "agent-reviewed":
        return
    reviewer = str(metadata.get("reviewed_by", "")).strip()
    model = str(metadata.get("model", "")).strip()
    if (
        not reviewer
        or not model
        or reviewer.startswith("replace-")
        or model.startswith("replace-")
    ):
        findings.error(
            "review_metadata_placeholder",
            "A revisão semântica precisa identificar agente e modelo reais.",
        )


def _check_counts_and_distributions(
    analysis: Analysis, findings: QualityFindings
) -> None:
    total = len(analysis.get("bugs", []))
    quality_total = analysis.get("data_quality", {}).get("total_records")
    if quality_total != total:
        findings.error(
            "record_count_mismatch",
            f"Qualidade informa {quality_total}; análise contém {total}.",
        )
    for name, values in analysis.get("metrics", {}).get("distributions", {}).items():
        if sum(int(value) for value in values.values()) != total:
            findings.error(
                "distribution_mismatch",
                f"Distribuição {name} não soma {total}.",
            )


def _check_kpis(analysis: Analysis, findings: QualityFindings) -> None:
    required = ("definition", "supporting_bug_ids")
    for kpi in analysis.get("metrics", {}).get("kpis", []):
        identifier = kpi.get("id", "?")
        if any(key not in kpi for key in required):
            findings.error(
                "incomplete_kpi_analysis",
                f"{identifier} não tem definição ou bugs de apoio.",
            )
        if kpi.get("requires_human_review") is not True:
            findings.error(
                "kpi_review_status",
                f"{identifier} não está marcado para revisão humana.",
            )


def _check_evidence(analysis: Analysis, findings: QualityFindings) -> None:
    evidence_ids = [item.get("evidence_id") for item in analysis.get("evidence", [])]
    duplicate_ids = [
        identifier
        for identifier, count in Counter(evidence_ids).items()
        if count > 1
    ]
    if duplicate_ids:
        findings.error("duplicate_evidence_id", f"IDs repetidos: {duplicate_ids}.")


def _check_cluster_references(
    analysis: Analysis, findings: QualityFindings
) -> None:
    bug_ids = {bug.get("bug_id") for bug in analysis.get("bugs", [])}
    for cluster in analysis.get("clusters", []):
        missing_bugs = set(cluster.get("bug_ids", [])) - bug_ids
        if missing_bugs:
            findings.error(
                "cluster_missing_bug",
                f"{cluster['cluster_id']} referencia {sorted(missing_bugs)}.",
            )


def _check_hypotheses(analysis: Analysis, findings: QualityFindings) -> None:
    hypotheses = analysis.get("hypotheses", [])
    hypothesis_ids = [item.get("hypothesis_id") for item in hypotheses]
    if len(set(hypothesis_ids)) != len(hypothesis_ids):
        findings.error("duplicate_hypothesis_id", "Há hypothesis_id repetido.")

    cluster_ids = {item.get("cluster_id") for item in analysis.get("clusters", [])}
    evidence_by_id = {
        item.get("evidence_id"): item
        for item in analysis.get("evidence", [])
    }
    evidence_ids = set(evidence_by_id)
    hypotheses_by_cluster: Counter[Any] = Counter()
    for hypothesis in hypotheses:
        identifier = hypothesis.get("hypothesis_id", "?")
        cluster_id = hypothesis.get("cluster_id")
        hypotheses_by_cluster[cluster_id] += 1
        if cluster_id not in cluster_ids:
            findings.error(
                "hypothesis_missing_cluster",
                f"{identifier} referencia cluster inexistente.",
            )
        supporting = hypothesis.get("supporting_evidence_ids", [])
        if not supporting:
            findings.error(
                "hypothesis_without_evidence",
                f"{identifier} não possui evidência.",
            )
        referenced = supporting + hypothesis.get("counter_evidence_ids", [])
        missing_evidence = set(referenced) - evidence_ids
        if missing_evidence:
            findings.error(
                "hypothesis_missing_evidence",
                f"{identifier} referencia {sorted(missing_evidence)}.",
            )
        if hypothesis.get("status") != "requires_human_review":
            findings.error(
                "causality_status",
                f"{identifier} não está requires_human_review.",
            )
        if not hypothesis.get("validation_method") or not hypothesis.get(
            "confirmation_questions"
        ):
            findings.error(
                "hypothesis_not_falsifiable",
                f"{identifier} não tem validação/perguntas.",
            )
        _check_rework_estimate(
            hypothesis,
            evidence_ids,
            identifier,
            findings,
        )
        check_hypothesis_evidence_quality(
            hypothesis,
            evidence_by_id,
            findings,
        )

    for cluster in analysis.get("clusters", []):
        cluster_id = cluster["cluster_id"]
        if cluster.get("prioritized") and hypotheses_by_cluster.get(cluster_id, 0) == 0:
            findings.warn(
                "prioritized_cluster_without_hypothesis",
                f"{cluster_id} não tem hipótese; dados podem ser insuficientes.",
            )


def _check_actions(analysis: Analysis, findings: QualityFindings) -> None:
    actions = analysis.get("actions", [])
    action_ids = [item.get("action_id") for item in actions]
    if len(set(action_ids)) != len(action_ids):
        findings.error("duplicate_action_id", "Há action_id repetido.")

    hypothesis_ids = {
        item.get("hypothesis_id") for item in analysis.get("hypotheses", [])
    }
    cluster_ids = {item.get("cluster_id") for item in analysis.get("clusters", [])}
    evidence_ids = {
        item.get("evidence_id") for item in analysis.get("evidence", [])
    }
    action_policy = _action_policy()
    coverage = action_policy["coverage"]
    allowed_control_types = set(action_policy["allowed_control_types"])
    required_fields = tuple(action_policy["required_fields"])
    content_validation = action_policy["content_validation"]
    actions_by_hypothesis: Counter[Any] = Counter()
    for action in actions:
        identifier = action.get("action_id", "?")
        hypothesis_id = action.get("hypothesis_id")
        if hypothesis_id not in hypothesis_ids:
            findings.error(
                "action_missing_hypothesis",
                f"{identifier} referencia hipótese inexistente.",
            )
        if action.get("cluster_id") not in cluster_ids:
            findings.error(
                "action_missing_cluster",
                f"{identifier} referencia cluster inexistente.",
            )
        missing_evidence = set(action.get("evidence_ids", [])) - evidence_ids
        if missing_evidence:
            findings.error(
                "action_missing_evidence",
                f"{identifier} referencia {sorted(missing_evidence)}.",
            )
        if action.get("barrier_type") not in allowed_control_types:
            findings.error(
                "unsupported_control_type",
                f"{identifier} usa um tipo de controle não configurado.",
            )
        actions_by_hypothesis[hypothesis_id] += 1
        _check_action_content(
            action,
            identifier,
            findings,
            required_fields,
            content_validation,
        )

    minimum_actions = coverage["minimum_actions_per_hypothesis"]
    for hypothesis_id in hypothesis_ids:
        if actions_by_hypothesis[hypothesis_id] < minimum_actions:
            findings.error(
                "missing_action",
                (
                    f"{hypothesis_id} tem menos de {minimum_actions} ação(ões) "
                    "específica(s) exigida(s) pela política configurada."
                ),
            )


def _check_action_content(
    action: dict[str, Any],
    identifier: str,
    findings: QualityFindings,
    required_fields: tuple[str, ...],
    content_validation: dict[str, Any],
) -> None:
    normalized_statement = str(action.get("statement", "")).casefold().strip(" .")
    generic_statements = {
        str(item).casefold().strip(" .")
        for item in content_validation["generic_statements"]
    }
    minimum_length = content_validation["minimum_statement_length"]
    if (
        normalized_statement in generic_statements
        or len(normalized_statement) < minimum_length
    ):
        findings.error("generic_action", f"{identifier} é genérica.")

    if any(
        not action.get(name) or action.get(name) == UNKNOWN
        for name in required_fields
    ):
        findings.error(
            "incomplete_action",
            f"{identifier} não tem dono, horizonte, métrica ou validação.",
        )
    if action.get("status") != "requires_human_review":
        findings.error(
            "action_status",
            f"{identifier} não está requires_human_review.",
        )


def _check_rework_estimate(
    hypothesis: dict[str, Any],
    evidence_ids: set[Any],
    identifier: str,
    findings: QualityFindings,
) -> None:
    estimate = hypothesis.get("estimated_rework_hours")
    if estimate is None:
        return
    basis = hypothesis.get("estimate_basis")
    if not isinstance(basis, dict):
        findings.error(
            "unsupported_rework_estimate",
            f"{identifier} estima retrabalho sem base reproduzível.",
        )
        return
    supporting = set(basis.get("supporting_evidence_ids", []))
    if not basis.get("method") or not supporting:
        findings.error(
            "incomplete_rework_estimate",
            f"{identifier} não documenta método e evidências da estimativa.",
        )
    missing = supporting - evidence_ids
    if missing:
        findings.error(
            "rework_estimate_missing_evidence",
            f"{identifier} referencia {sorted(missing)} na estimativa.",
        )


def _action_policy() -> dict[str, Any]:
    policy = load_yaml("action-policy.yml")
    required = {
        "allowed_control_types",
        "coverage",
        "content_validation",
        "required_fields",
    }
    if not required <= set(policy):
        raise ValueError("config/action-policy.yml está incompleto.")
    if not policy["allowed_control_types"] or not policy["required_fields"]:
        raise ValueError("Política de ações não pode ter listas vazias.")
    minimum_actions = policy["coverage"].get(
        "minimum_actions_per_hypothesis"
    )
    if not isinstance(minimum_actions, int) or minimum_actions < 1:
        raise ValueError("minimum_actions_per_hypothesis deve ser positivo.")
    minimum_length = policy["content_validation"].get(
        "minimum_statement_length"
    )
    if not isinstance(minimum_length, int) or minimum_length < 1:
        raise ValueError("minimum_statement_length deve ser positivo.")
    if not isinstance(
        policy["content_validation"].get("generic_statements"),
        list,
    ):
        raise ValueError("generic_statements deve ser uma lista.")
    return policy


DEFAULT_CHECKS: tuple[QualityCheck, ...] = (
    _check_review_metadata,
    _check_counts_and_distributions,
    _check_kpis,
    check_semantic_review,
    _check_evidence,
    check_insights,
    check_cluster_gap_reviews,
    check_methodology_reviews,
    _check_cluster_references,
    _check_hypotheses,
    _check_actions,
    check_data_limitations,
    check_schema_adaptation,
    check_clarification_questions,
    check_effective_values,
)

_DEFAULT_GATE = QualityGate(DEFAULT_CHECKS)


def run_quality_gate(analysis: Analysis) -> dict[str, Any]:
    """Backward-compatible facade for the default quality gate."""

    return _DEFAULT_GATE.run(analysis)
