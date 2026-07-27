from __future__ import annotations

from typing import Any

from ..core.utils import UNKNOWN


def check_schema_adaptation(
    analysis: dict[str, Any],
    findings: Any,
) -> None:
    data_quality = analysis.get("data_quality", {})
    if data_quality.get("usable_for_metrics", 0) == 0:
        findings.error(
            "no_usable_bug_content",
            "Nenhum registro possui título ou descrição utilizável.",
        )
    unmapped = data_quality.get("unmapped_source_fields", [])
    if unmapped:
        fields = ", ".join(str(item) for item in unmapped[:8])
        suffix = "..." if len(unmapped) > 8 else ""
        findings.warn(
            "unmapped_source_fields",
            (
                f"{len(unmapped)} campo(s) da empresa foram preservados sem "
                f"mapeamento analítico: {fields}{suffix}"
            ),
        )


def check_effective_values(
    analysis: dict[str, Any],
    findings: Any,
) -> None:
    fields = (
        "severity",
        "bug_type",
        "root_cause_category",
        "affected_module",
        "environment",
    )
    for bug in analysis.get("bugs", []):
        for category_field in fields:
            _check_effective_field(bug, category_field, findings)


def _check_effective_field(
    bug: dict[str, Any],
    field: str,
    findings: Any,
) -> None:
    bug_id = bug.get("bug_id", "?")
    reported = bug.get(field, UNKNOWN)
    effective = bug.get(f"effective_{field}", reported)
    source = bug.get(
        f"effective_{field}_source",
        "reported" if reported != UNKNOWN else "unknown",
    )
    if reported != UNKNOWN and effective != reported:
        findings.error(
            "reported_value_overwritten",
            f"{bug_id}: {field} efetivo diverge do valor reportado.",
        )
    if source == "human_approved_agent_suggestion":
        suggestion = bug.get(f"agent_suggested_{field}", UNKNOWN)
        if reported != UNKNOWN or suggestion == UNKNOWN or effective != suggestion:
            findings.error(
                "invalid_effective_suggestion",
                f"{bug_id}: promoção inválida de {field}.",
            )
    if source == "unknown" and effective != UNKNOWN:
        findings.error(
            "effective_value_without_provenance",
            f"{bug_id}: {field} efetivo não tem proveniência.",
        )
    if source == "human_answered" and (
        reported != UNKNOWN or effective == UNKNOWN
    ):
        findings.error(
            "invalid_human_answer",
            f"{bug_id}: resposta humana inválida para {field}.",
        )
