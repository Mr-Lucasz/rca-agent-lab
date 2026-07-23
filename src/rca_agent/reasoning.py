from __future__ import annotations

from collections import Counter
from typing import Any

from .config import load_yaml
from .utils import UNKNOWN, redact


def build_evidence(bugs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    counter = 1
    fields = (
        ("dev_analysis_notes", "dev_note", "high"),
        ("qa_analysis_notes", "qa_note", "high"),
        ("actual_behavior", "actual_behavior", "high"),
        ("description", "description", "high"),
        ("title", "title", "low"),
    )
    for bug in bugs:
        for field, source_type, reliability in fields:
            value = bug.get(field, UNKNOWN)
            if value == UNKNOWN:
                continue
            evidence.append(
                {
                    "evidence_id": f"EV-{counter:04d}",
                    "source_type": source_type,
                    "source_ref": f"{bug['source_file']}#row={bug['source_row']}:{field}",
                    "bug_id": bug["bug_id"],
                    "excerpt": redact(value),
                    "reliability": reliability,
                    "observed_at": None,
                }
            )
            counter += 1
    return evidence


def build_rule_insights(
    bugs: list[dict[str, Any]], clusters: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    evidence_by_bug: dict[str, list[str]] = {}
    for item in evidence:
        evidence_by_bug.setdefault(item["bug_id"], []).append(item["evidence_id"])
    insights: list[dict[str, Any]] = []
    for cluster in clusters[:3]:
        high_severity = sum(
            1 for bug in bugs if bug["cluster_id"] == cluster["cluster_id"] and bug["severity"] in {"high", "critical"}
        )
        ids = [
            evidence_id
            for bug_id in cluster["bug_ids"]
            for evidence_id in evidence_by_bug.get(bug_id, [])[:1]
        ]
        if not ids:
            continue
        insights.append(
            {
                "insight_id": f"IN-{len(insights) + 1:03d}",
                "statement": (
                    f"{cluster['name']} reúne {cluster['size']} bugs, com {high_severity} ocorrências de alta criticidade "
                    f"e score de investigação {cluster['investigation_score']}."
                ),
                "evidence_ids": ids[:5],
                "limitations": [
                    "É um sinal quantitativo de concentração; sem validação técnica, o agrupamento não confirma o mecanismo causal."
                ],
            }
        )
    return insights


def build_rule_hypotheses(
    bugs: list[dict[str, Any]], clusters: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    evidence_by_bug: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        evidence_by_bug.setdefault(item["bug_id"], []).append(item)
    hypotheses: list[dict[str, Any]] = []
    for cluster in [item for item in clusters if item["prioritized"]]:
        group = [bug for bug in bugs if bug["cluster_id"] == cluster["cluster_id"]]
        cause_counts = Counter(
            bug["agent_suggested_root_cause_category"]
            if bug["agent_suggested_root_cause_category"] != UNKNOWN
            else bug["root_cause_category"]
            for bug in group
        )
        cause = cause_counts.most_common(1)[0][0] if cause_counts else UNKNOWN
        minority_bug_ids = []
        if len(cause_counts) > 1:
            majority = cause_counts.most_common(1)[0][0]
            minority_bug_ids = [
                bug["bug_id"]
                for bug in group
                if (
                    bug["agent_suggested_root_cause_category"]
                    if bug["agent_suggested_root_cause_category"] != UNKNOWN
                    else bug["root_cause_category"]
                )
                != majority
            ]
        supporting = [
            item["evidence_id"]
            for bug in group
            for item in evidence_by_bug.get(bug["bug_id"], [])
            if item["source_type"] in {"dev_note", "qa_note", "actual_behavior"}
        ][:6]
        counter = [
            item["evidence_id"]
            for bug in group
            if bug["bug_id"] in minority_bug_ids
            for item in evidence_by_bug.get(bug["bug_id"], [])
            if item["source_type"] in {"dev_note", "qa_note", "actual_behavior"}
        ][:3]
        if not supporting:
            supporting = [
                item["evidence_id"]
                for bug in group
                for item in evidence_by_bug.get(bug["bug_id"], [])
            ][:3]
        if not supporting:
            continue
        confidence = "medium" if len(supporting) >= 3 and len(group) >= 2 else "low"
        number = len(hypotheses) + 1
        hypotheses.append(
            {
                "hypothesis_id": f"HY-{number:03d}",
                "cluster_id": cluster["cluster_id"],
                "statement": f"Mecanismo plausível ligado a {cause} no cluster {cluster['name']}.",
                "mechanism": (
                    f"Os bugs do cluster exibem sinais compatíveis com uma falha na categoria {cause}. "
                    "A hipótese é que o mesmo mecanismo operacional esteja repetindo o sintoma em cenários parecidos."
                ),
                "confidence": confidence,
                "confidence_rationale": (
                    f"A avaliação usa {len(supporting)} evidências textuais e {len(group)} bug(s) correlatos. "
                    "Ainda falta uma prova técnica independente que reproduza o mecanismo de ponta a ponta."
                ),
                "supporting_evidence_ids": supporting,
                "counter_evidence_ids": counter,
                "missing_information": [
                    "Linha do tempo técnica correlacionando mudança, primeira ocorrência e mitigação.",
                    "Teste ou log que falhe antes da correção e passe depois da barreira aplicada.",
                ],
                "confirmation_questions": [
                    "Qual mudança de código, configuração ou contrato imediatamente precedeu a primeira ocorrência?",
                    "Qual teste reproduz o mecanismo, e não apenas o sintoma observado pelo usuário?",
                ],
                "validation_method": (
                    "Reproduzir o cenário em ambiente controlado, correlacionar logs ou traces com a mudança suspeita "
                    "e executar o teste de regressão antes e depois da correção proposta."
                ),
                "status": "requires_human_review",
            }
        )
    return hypotheses


def build_rule_actions(
    hypotheses: list[dict[str, Any]], bugs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    matrix = load_yaml("action-matrix.yml")
    defaults = matrix["defaults"]
    by_cause = matrix["by_root_cause"]
    actions: list[dict[str, Any]] = []
    for hypothesis in hypotheses:
        group = [bug for bug in bugs if bug["cluster_id"] == hypothesis["cluster_id"]]
        cause_counts = Counter(
            bug["agent_suggested_root_cause_category"]
            if bug["agent_suggested_root_cause_category"] != UNKNOWN
            else bug["root_cause_category"]
            for bug in group
        )
        cause = cause_counts.most_common(1)[0][0] if cause_counts else UNKNOWN
        templates = by_cause.get(cause, by_cause["unknown"])
        for barrier_type in ("corrective", "detective", "preventive"):
            rule = defaults[barrier_type]
            actions.append(
                {
                    "action_id": f"AC-{len(actions) + 1:03d}",
                    "hypothesis_id": hypothesis["hypothesis_id"],
                    "cluster_id": hypothesis["cluster_id"],
                    "barrier_type": barrier_type,
                    "statement": (
                        f"{templates[barrier_type]} Priorizar o cluster {hypothesis['cluster_id']} "
                        f"e cobrir explicitamente os bugs {', '.join(bug['bug_id'] for bug in group)}."
                    ),
                    "owner_role": rule["owner_role"],
                    "horizon": rule["horizon"],
                    "priority": "high" if barrier_type != "preventive" else "medium",
                    "expected_impact": "high",
                    "effort": "medium",
                    "success_metric": rule["success_metric"],
                    "validation_method": (
                        "Comparar a taxa do cluster antes e depois da ação e auditar no gate o teste ou a barreira adicionada."
                    ),
                    "residual_risk": "Se a hipótese for refutada, a ação pode reduzir apenas o sintoma; reavaliar após a validação causal.",
                    "evidence_ids": hypothesis["supporting_evidence_ids"][:3],
                    "status": "requires_human_review",
                }
            )
    return actions

