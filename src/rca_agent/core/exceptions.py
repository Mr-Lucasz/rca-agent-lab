class QualityGateError(RuntimeError):
    """Raised when an analysis or published report fails its quality gate."""


class ClarificationRequiredError(RuntimeError):
    """Raised when finalization is attempted before the human clarification gate."""
