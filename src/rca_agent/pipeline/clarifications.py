from __future__ import annotations

import json
from typing import Any

from ..core.config import load_yaml
from ..core.utils import UNKNOWN, fold, slug

_IMMUTABLE_FIELDS = (
    "question_id",
    "field",
    "question_type",
    "question",
    "bug_ids",
    "proposals",
    "rationale",
)


def build_clarification_questions(
    bugs: list[dict[str, Any]],
    data_quality: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Group business questions for fields that cannot be silently attributed."""

    questions = _field_mapping_questions(bugs, data_quality or {})
    specifications = (
        ("severity", "Severidade", "agent_suggested_severity", "confirm_suggestions"),
        ("bug_type", "Bug type", "agent_suggested_bug_type", "confirm_suggestions"),
        (
            "root_cause_category",
            "Categoria RCA de triagem",
            "agent_suggested_root_cause_category",
            "confirm_suggestions",
        ),
        ("environment", "Ambiente", None, "request_information"),
        ("affected_module", "Módulo afetado", None, "request_information"),
    )
    for field, label, suggestion_field, question_type in specifications:
        missing = [bug for bug in bugs if bug.get(field, UNKNOWN) == UNKNOWN]
        if not missing:
            continue
        proposals = []
        if suggestion_field:
            proposals = [
                {
                    "bug_id": bug["bug_id"],
                    "suggested_value": bug[suggestion_field],
                    "confidence": bug["agent_suggestion_confidence"],
                    "rationale": bug["agent_suggestion_rationale"],
                }
                for bug in missing
                if bug.get(suggestion_field, UNKNOWN) != UNKNOWN
            ]
        if question_type == "confirm_suggestions" and proposals:
            question = (
                f"Posso registrar as sugestões de {label.lower()} para os bugs "
                "listados, com base em título, descrição, comportamento esperado "
                "e comportamento obtido?"
            )
        else:
            question_type = "request_information"
            question = (
                f"Qual é o {label.lower()} dos bugs listados? "
                "O valor reportado está ausente e permanecerá unknown sem resposta."
            )
        questions.append(
            {
                "question_id": f"CQ-VAL-{slug(field).upper()}",
                "field": field,
                "question_type": question_type,
                "question": question,
                "bug_ids": [bug["bug_id"] for bug in missing],
                "proposals": proposals,
                "rationale": (
                    "A confirmação evita transformar inferência semântica em valor "
                    "reportado e mantém a decisão auditável."
                ),
                "status": "open",
            }
        )
    return questions


def _field_mapping_questions(
    bugs: list[dict[str, Any]],
    data_quality: dict[str, Any],
) -> list[dict[str, Any]]:
    questions = []
    for mapping in data_quality.get("schema_mapping", []):
        if mapping.get("status") != "needs_confirmation":
            continue
        source_field = mapping["source_field"]
        canonical_field = mapping["canonical_field"]
        bug_ids = [
            bug["bug_id"]
            for bug in bugs
            if source_field in bug.get("source_fields", {})
        ]
        if not bug_ids:
            continue
        questions.append(
            {
                "question_id": (
                    f"CQ-MAP-{slug(source_field).upper()}-"
                    f"{slug(canonical_field).upper()}"
                ),
                "field": canonical_field,
                "question_type": "confirm_field_mapping",
                "question": (
                    f"A coluna '{source_field}' representa o campo "
                    f"'{canonical_field}' nesta empresa?"
                ),
                "bug_ids": bug_ids,
                "proposals": [
                    {
                        "source_field": source_field,
                        "suggested_value": canonical_field,
                        "confidence": mapping["confidence"],
                        "rationale": (
                            f"Correspondência adaptativa por {mapping['method']} "
                            f"com score {mapping['score']}."
                        ),
                    }
                ],
                "rationale": (
                    "Mapeamentos não exatos precisam de confirmação antes de "
                    "alimentar métricas e conclusões."
                ),
                "status": "open",
            }
        )
    return questions


def synchronize_clarification_review(
    review: dict[str, Any],
    questions: list[dict[str, Any]],
) -> None:
    """Carry prior human decisions to regenerated questions by semantic identity."""

    previous = {
        _question_identity(item): item
        for item in review.get("clarification_questions", [])
    }
    synchronized = []
    for question in questions:
        current = dict(question)
        prior = previous.get(_question_identity(question))
        if prior and prior.get("status") != "open":
            current["status"] = prior["status"]
            if prior.get("answer"):
                current["answer"] = prior["answer"]
        synchronized.append(current)
    review["clarification_questions"] = synchronized


def _question_identity(item: dict[str, Any]) -> tuple[str, str, str]:
    source_field = ""
    if item.get("question_type") == "confirm_field_mapping":
        proposals = item.get("proposals", [])
        if proposals:
            source_field = str(proposals[0].get("source_field", ""))
    return (
        str(item.get("question_type", "")),
        str(item.get("field", "")),
        source_field,
    )


def merge_clarification_responses(
    analysis: dict[str, Any],
    responses: list[dict[str, Any]],
) -> None:
    """Merge only human decisions while preserving the generated questions."""

    questions = analysis.get("clarification_questions", [])
    questions_by_id = {item["question_id"]: item for item in questions}
    response_ids = [item["question_id"] for item in responses]
    if len(response_ids) != len(set(response_ids)):
        raise ValueError("O review contém question_id de esclarecimento repetido.")

    for response in responses:
        question_id = response["question_id"]
        original = questions_by_id.get(question_id)
        if original is None:
            raise ValueError(
                f"O review referencia pergunta de esclarecimento inexistente: {question_id}."
            )
        changed_fields = [
            field
            for field in _IMMUTABLE_FIELDS
            if response.get(field) != original.get(field)
        ]
        if changed_fields:
            raise ValueError(
                f"O review tenta alterar a pergunta {question_id}: "
                f"{', '.join(changed_fields)}."
            )

        status = response["status"]
        question_type = original["question_type"]
        if status == "accepted" and question_type not in {
            "confirm_suggestions",
            "confirm_field_mapping",
        }:
            raise ValueError(
                f"{question_id} solicita informação factual e não aceita status accepted."
            )
        if status == "answered":
            answer = str(response.get("answer", "")).strip()
            if not answer:
                raise ValueError(f"{question_id} exige uma resposta factual não vazia.")
            original["answer"] = answer
        elif "answer" in original:
            original.pop("answer")
        original["status"] = status


def promote_accepted_suggestions(
    bugs: list[dict[str, Any]],
    questions: list[dict[str, Any]],
) -> None:
    """Promote approved suggestions to effective analytical values."""

    supported_fields = ("severity", "bug_type", "root_cause_category")
    for bug in bugs:
        for field in (*supported_fields, "environment"):
            reported = bug.get(field, UNKNOWN)
            bug[f"effective_{field}"] = reported
            bug[f"effective_{field}_source"] = (
                "reported" if reported != UNKNOWN else "unknown"
            )

    bugs_by_id = {bug["bug_id"]: bug for bug in bugs}
    for question in questions:
        field = question.get("field")
        if (
            question.get("status") != "accepted"
            or question.get("question_type") != "confirm_suggestions"
            or field not in supported_fields
        ):
            continue
        suggestion_field = f"agent_suggested_{field}"
        for bug_id in question.get("bug_ids", []):
            bug = bugs_by_id.get(bug_id)
            if bug is None:
                continue
            suggestion = bug.get(suggestion_field, UNKNOWN)
            if bug.get(field, UNKNOWN) == UNKNOWN and suggestion != UNKNOWN:
                bug[f"effective_{field}"] = suggestion
                bug[f"effective_{field}_source"] = (
                    "human_approved_agent_suggestion"
                )


def apply_field_mapping_decisions(
    bugs: list[dict[str, Any]],
    questions: list[dict[str, Any]],
) -> None:
    """Remove provisional mappings explicitly declined by the human."""

    for question in questions:
        if (
            question.get("question_type") != "confirm_field_mapping"
            or question.get("status") != "declined"
        ):
            continue
        field = str(question.get("field", ""))
        source_fields = {
            proposal.get("source_field")
            for proposal in question.get("proposals", [])
        }
        for bug in bugs:
            if source_fields & set(bug.get("source_fields", {})):
                bug[field] = UNKNOWN


def apply_factual_answers(
    bugs: list[dict[str, Any]],
    questions: list[dict[str, Any]],
) -> None:
    """Apply human-provided facts to effective fields without changing the source."""

    bugs_by_id = {bug["bug_id"]: bug for bug in bugs}
    for question in questions:
        if (
            question.get("question_type") != "request_information"
            or question.get("status") != "answered"
        ):
            continue
        field = str(question.get("field", ""))
        answers = _answer_values(
            str(question.get("answer", "")),
            question.get("bug_ids", []),
        )
        for bug_id, value in answers.items():
            bug = bugs_by_id.get(bug_id)
            if bug is None or not value:
                continue
            bug[f"effective_{field}"] = _canonical_answer(field, value)
            bug[f"effective_{field}_source"] = "human_answered"


def _answer_values(answer: str, bug_ids: list[str]) -> dict[str, str]:
    try:
        parsed = json.loads(answer)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return {
            bug_id: str(parsed.get(bug_id, "")).strip()
            for bug_id in bug_ids
        }
    return {bug_id: answer.strip() for bug_id in bug_ids}


def _canonical_answer(field: str, value: str) -> str:
    filename = {
        "severity": "severity.yml",
        "bug_type": "bug-types.yml",
        "root_cause_category": "root-causes.yml",
        "environment": "environments.yml",
    }.get(field)
    if filename is None:
        return value
    canonical = load_yaml(filename).get("canonical", {})
    for target, details in canonical.items():
        aliases = (
            details.get("aliases", [])
            if isinstance(details, dict)
            else details or []
        )
        if fold(value) in {fold(target), *(fold(alias) for alias in aliases)}:
            return target
    return value
