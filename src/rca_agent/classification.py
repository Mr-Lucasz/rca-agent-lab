from __future__ import annotations

from typing import Any

from .config import load_yaml
from .utils import UNKNOWN, fold


def _best_keyword_match(text: str, filename: str) -> tuple[str, int]:
    config = load_yaml(filename).get("canonical", {})
    scores: dict[str, int] = {}
    for category, details in config.items():
        keywords = details.get("keywords", []) if isinstance(details, dict) else []
        scores[category] = sum(1 for keyword in keywords if fold(keyword) in text)
    if not scores:
        return UNKNOWN, 0
    category, score = max(scores.items(), key=lambda item: (item[1], item[0]))
    return (category, score) if score else (UNKNOWN, 0)


def _suggest_severity(text: str) -> tuple[str, int]:
    rules = load_yaml("severity.yml").get("suggestion_rules", {})
    scores = {
        severity: sum(1 for keyword in keywords if fold(keyword) in text)
        for severity, keywords in rules.items()
    }
    severity, score = max(scores.items(), key=lambda item: (item[1], item[0]))
    return (severity, score) if score else (UNKNOWN, 0)


def classify_rules(bugs: list[dict[str, Any]]) -> None:
    for bug in bugs:
        text = fold(
            " ".join(
                str(bug.get(field, ""))
                for field in (
                    "title",
                    "description",
                    "actual_behavior",
                    "expected_behavior",
                    "dev_analysis_notes",
                    "qa_analysis_notes",
                )
            )
        )
        severity, severity_score = _suggest_severity(text)
        bug_type, type_score = _best_keyword_match(text, "bug-types.yml")
        cause, cause_score = _best_keyword_match(text, "root-causes.yml")
        bug["agent_suggested_severity"] = severity
        bug["agent_suggested_bug_type"] = bug_type
        bug["agent_suggested_root_cause_category"] = cause
        total_score = severity_score + type_score + cause_score
        bug["agent_suggestion_confidence"] = (
            "high" if total_score >= 5 else "medium" if total_score >= 2 else "low"
        )
        comparisons = [
            (bug.get("severity"), severity),
            (bug.get("bug_type"), bug_type),
            (bug.get("root_cause_category"), cause),
        ]
        known_pairs = [
            (reported, suggested)
            for reported, suggested in comparisons
            if reported != UNKNOWN and suggested != UNKNOWN
        ]
        if not known_pairs:
            status = "insufficient_evidence"
        elif any(reported != suggested for reported, suggested in known_pairs):
            status = "conflicting"
        elif all(reported == suggested for reported, suggested in known_pairs):
            status = "consistent"
        else:
            status = "questionable"
        bug["agent_review_status"] = status
        bug["agent_suggestion_rationale"] = (
            f"As regras encontraram {total_score} sinais textuais relevantes; "
            f"a classificação reportada foi avaliada como {status}. Requer revisão humana."
        )

