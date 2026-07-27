"""RCA use-case facade."""

from ..core.exceptions import ClarificationRequiredError, QualityGateError
from .service import (
    RcaPipeline,
    analyze,
    apply_review,
    finalize,
    prepare,
    prepare_review_questions,
    record_clarification,
    report_bug,
    validate_report,
)

__all__ = [
    "ClarificationRequiredError",
    "QualityGateError",
    "RcaPipeline",
    "analyze",
    "apply_review",
    "finalize",
    "prepare",
    "prepare_review_questions",
    "record_clarification",
    "report_bug",
    "validate_report",
]
