from __future__ import annotations

from typing import Any

from ..core.utils import UNKNOWN


def classify_rules(bugs: list[dict[str, Any]]) -> None:
    """Initialize review fields without making semantic suggestions.

    Reported classifications are normalized during ingestion. Suggestions for
    missing or conflicting values belong to the agent review because their
    meaning depends on the organization's taxonomy and on the bug evidence.
    """

    for bug in bugs:
        bug["agent_suggested_severity"] = UNKNOWN
        bug["agent_suggested_bug_type"] = UNKNOWN
        bug["agent_suggested_root_cause_category"] = UNKNOWN
        bug["agent_suggestion_confidence"] = UNKNOWN
        bug["agent_suggestion_rationale"] = UNKNOWN
        bug["agent_review_status"] = "insufficient_evidence"
