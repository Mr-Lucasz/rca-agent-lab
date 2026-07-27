from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..core.utils import read_json, write_json
from .review import stage_review_clarifications

SchemaValidation = Callable[[Any, str], None]


def prepare_review_question_artifacts(
    work_dir: str | Path,
    review_path: str | Path,
    schema_validation: SchemaValidation,
) -> dict[str, Any]:
    work = Path(work_dir).expanduser().resolve()
    path = Path(review_path).expanduser().resolve()
    analysis = read_json(work / "analysis.json")
    review = read_json(path)
    schema_validation(review, "agent-review.schema.json")
    stage_review_clarifications(analysis, review)
    questions_path = work / "clarification-questions.json"
    write_json(work / "analysis.json", analysis)
    write_json(path, review)
    write_json(questions_path, analysis["clarification_questions"])
    return {
        "review": str(path),
        "clarification_questions": str(questions_path),
        "open_questions": [
            item
            for item in review["clarification_questions"]
            if item.get("status") == "open"
        ],
    }
