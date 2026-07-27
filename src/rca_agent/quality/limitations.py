from __future__ import annotations

from typing import Any, Protocol

from ..core.config import load_yaml


class Findings(Protocol):
    def warn(self, code: str, message: str) -> None: ...


def check_data_limitations(
    analysis: dict[str, Any],
    findings: Findings,
) -> None:
    data_quality = analysis.get("data_quality", {})
    warning_policy = load_yaml("quality-policy.yml")["warnings"]
    total = len(analysis.get("bugs", []))
    small_sample_threshold = warning_policy.get(
        "small_sample_below_records"
    )
    if not isinstance(small_sample_threshold, int):
        raise ValueError("Limite de amostra pequena inválido.")
    if total < small_sample_threshold:
        findings.warn(
            "small_sample",
            f"Amostra de {total} bug(s); evitar generalização.",
        )
    coverage_threshold = warning_policy.get(
        "causal_signal_coverage_below_percent"
    )
    if not isinstance(coverage_threshold, (int, float)):
        raise ValueError("Limite de cobertura de sinais causais inválido.")
    causal_coverage = data_quality.get(
        "causal_signal_coverage_percent",
        0,
    )
    if total and causal_coverage < coverage_threshold:
        findings.warn(
            "low_causal_signal_coverage",
            (
                f"Apenas {causal_coverage}% dos bugs possuem sinais causais "
                "documentados em notas QA/Dev; padrões sistêmicos podem estar "
                "sub-representados."
            ),
        )
    if data_quality.get("prompt_injection_rows"):
        findings.warn(
            "untrusted_content",
            "A entrada contém texto semelhante a instruções; foi tratado como dado.",
        )


def check_clarification_questions(
    analysis: dict[str, Any],
    findings: Findings,
) -> None:
    open_questions = [
        item
        for item in analysis.get("clarification_questions", [])
        if item.get("status") == "open"
    ]
    if open_questions:
        fields = sorted(
            {str(item.get("field", "unknown")) for item in open_questions}
        )
        findings.warn(
            "open_clarifications",
            (
                f"Há {len(open_questions)} pergunta(s) de esclarecimento pendente(s) "
                f"para os campos: {', '.join(fields)}. Valores reportados permanecem unknown."
            ),
        )

    declined = [
        item
        for item in analysis.get("clarification_questions", [])
        if item.get("status") == "declined"
    ]
    if declined:
        fields = sorted(
            {str(item.get("field", "unknown")) for item in declined}
        )
        findings.warn(
            "clarifications_declined",
            (
                f"O humano optou por não informar ou atribuir {len(declined)} "
                f"campo(s): {', '.join(fields)}. Os valores permanecem unknown."
            ),
        )
