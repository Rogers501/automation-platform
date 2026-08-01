"""Abstract base class for AI failure analysis plugins.

A :class:`FailureAnalyzer` receives a :class:`FailureContext` (built from a
failed pytest test) and returns an :class:`AnalysisResult` with a root-cause
guess, suggestion, and confidence score.

Implementations may call external LLM APIs (OpenAI, Claude, local Ollama,
etc.). The framework ships a :class:`NullFailureAnalyzer` that does nothing,
so the framework never hard-depends on an AI service.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from framework.plugins.ai.models import AnalysisResult, FailureContext

__all__ = ["FailureAnalyzer"]


class FailureAnalyzer(ABC):
    """Pluggable AI failure analysis interface.

    Register an implementation in a system ``conftest.py`` to enable
    AI-powered failure analysis::

        from framework.plugins.ai import set_analyzer

        class MyAnalyzer(FailureAnalyzer):
            async def analyze(self, ctx):
                # call LLM API here
                return AnalysisResult(root_cause="...")

        set_analyzer(MyAnalyzer())
    """

    @abstractmethod
    async def analyze(self, context: FailureContext) -> AnalysisResult:
        """Analyze a test failure and return a structured result.

        Args:
            context: The failure context (test info, error, traceback, etc.).

        Returns:
            An :class:`AnalysisResult` with root cause, suggestion, etc.
        """
