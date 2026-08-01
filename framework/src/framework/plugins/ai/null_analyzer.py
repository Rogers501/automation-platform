"""Default no-op failure analyzer.

Returned by :func:`get_analyzer` when no custom analyzer is registered.
This ensures the framework's failure-analysis hook never breaks if no AI
backend is configured.
"""

from __future__ import annotations

from framework.plugins.ai.base import FailureAnalyzer
from framework.plugins.ai.models import AnalysisResult, FailureContext

__all__ = ["NullFailureAnalyzer"]


class NullFailureAnalyzer(FailureAnalyzer):
    """A no-op analyzer that returns an empty result.

    Useful as a default when no AI backend is configured. The analyze call
    completes immediately without side effects.
    """

    async def analyze(self, context: FailureContext) -> AnalysisResult:
        """Return an empty AnalysisResult (no AI analysis performed)."""
        return AnalysisResult(
            root_cause="",
            suggestion="",
            confidence=0.0,
            category="no_analyzer",
            metadata={"analyzer": "null"},
        )
