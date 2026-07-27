from __future__ import annotations

from typing import Any, Protocol


class Findings(Protocol):
    def error(self, code: str, message: str) -> None: ...

    def warn(self, code: str, message: str) -> None: ...


def check_hypothesis_evidence_quality(
    hypothesis: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    findings: Findings,
) -> None:
    identifier = hypothesis.get("hypothesis_id", "?")
    supporting = [
        evidence_by_id[evidence_id]
        for evidence_id in hypothesis.get("supporting_evidence_ids", [])
        if evidence_id in evidence_by_id
    ]
    if not supporting:
        return
    reported_roles = {"reported_statement", "reported_causal_signal"}
    only_unverified_reported_signals = all(
        item.get("evidence_role") in reported_roles
        and item.get("epistemic_status") == "unverified"
        for item in supporting
    )
    if not only_unverified_reported_signals:
        return
    findings.warn(
        "hypothesis_only_unverified_statements",
        (
            f"{identifier} está apoiada somente por sinais reportados ainda "
            "não verificados. A convergência independente e a coerência com "
            "outros indicadores podem sustentar um forte indicativo, mas não "
            "confirmam a causa sem validação."
        ),
    )
    if hypothesis.get("confidence") == "high":
        findings.error(
            "high_confidence_from_unverified_statements",
            (
                f"{identifier} não pode ter confiança alta somente com sinais "
                "causais reportados ainda não verificados; registre como "
                "hipótese forte e aplique o método de validação."
            ),
        )
